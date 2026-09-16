"""IO 状态面板：HSD/LSD/通信状态/CAN/I2C 高边低边驱动状态与计数。"""
from __future__ import annotations

from PyQt5.QtCore import pyqtSignal
from PyQt5.QtWidgets import (QGridLayout, QHBoxLayout, QLabel,
                             QScrollArea, QVBoxLayout, QWidget)

from data.model import BusModel
from ui.widgets import CounterCard, StatusGroup, ValueCard

HSD_PINS = ["HSD_Status_P230", "HSD_Status_P231", "HSD_Status_P232", "HSD_Status_P233",
            "HSD_Status_P234", "HSD_Status_P235", "HSD_Status_P236"]
LSD_PINS = ["LSD_Status_P322", "LSD_Status_P323", "LSD_Status_P324", "LSD_Status_P325"]

# I2C: DBC 只有 Des0-3 + Ser0-10
I2C_DES_COUNT = 4
I2C_SER_COUNT = 11


class IOPanel(QWidget):
    def __init__(self, model: BusModel, parent=None):
        super().__init__(parent)
        self.model = model
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QScrollArea.NoFrame)
        scroll.setStyleSheet(
            "QScrollArea { background-color: #1e1e1e; border: none; }"
            "QScrollArea > QWidget > QWidget { background-color: #1e1e1e; }"
            "QScrollBar:vertical { background: #1e1e1e; width: 10px; }"
            "QScrollBar::handle:vertical { background: #3d3d3d; border-radius: 5px;"
            " min-height: 20px; }")
        body = QWidget()
        grid = QGridLayout(body)
        grid.setContentsMargins(8, 8, 8, 8)
        grid.setSpacing(10)

        # ── 第一行: HSD + LSD ──────────────────────────────────
        # 高边驱动 HSD — 状态 + ADC 值
        self.hsd_grp = StatusGroup("高边驱动 HSD")
        self.hsd_adc: dict[str, ValueCard] = {}
        for i, pin in enumerate(HSD_PINS):
            self.hsd_grp.add_cell(pin, f"P23.{i}")
            card = ValueCard(f"P23.{i} ADC", "ADC")
            self.hsd_adc[f"HSD{i + 1}"] = card
        hsd_right = QWidget()
        hr = QGridLayout(hsd_right)
        hr.setContentsMargins(0, 0, 0, 0)
        for idx, (name, card) in enumerate(self.hsd_adc.items()):
            hr.addWidget(card, idx // 4, idx % 4)
        hsd_box = QHBoxLayout()
        hsd_box.addWidget(self.hsd_grp)
        hsd_box.addWidget(hsd_right, 1)
        hsd_v = QVBoxLayout()
        hsd_v.addLayout(hsd_box)
        # U1000/U1001 测试状态 (0x65C 4bit)
        test_row = QHBoxLayout()
        test_row.addWidget(QLabel("U1000 测试状态:"))
        self.test_u1000 = QLabel("--")
        test_row.addWidget(self.test_u1000)
        test_row.addSpacing(20)
        test_row.addWidget(QLabel("U1001 测试状态:"))
        self.test_u1001 = QLabel("--")
        test_row.addWidget(self.test_u1001)
        test_row.addStretch()
        hsd_v.addLayout(test_row)
        hsd_wrap = QWidget()
        hsd_wrap.setLayout(hsd_v)
        grid.addWidget(hsd_wrap, 0, 0)

        # 低边驱动 LSD
        self.lsd_grp = StatusGroup("低边驱动 LSD")
        self.lsd_ec: dict[str, CounterCard] = {}
        for pin in LSD_PINS:
            self.lsd_grp.add_cell(pin, pin.replace("LSD_Status_", "LSD "))
        lsd_box = QVBoxLayout()
        lsd_box.addWidget(self.lsd_grp)
        ec_row = QHBoxLayout()
        for sig in ["BTT3050_U1100_EC", "BTT3050_U1101_EC", "BTS3410_LSD1_EC", "BTS3410_LSD2_EC"]:
            c = CounterCard(sig.replace("_EC", ""))
            self.lsd_ec[sig] = c
            ec_row.addWidget(c)
        lsd_box.addLayout(ec_row)
        # GPI 输入电平 (0x65A McuLSDStatus)
        gpi_row = QHBoxLayout()
        gpi_row.addWidget(QLabel("GPI 输入:"))
        self.gpi_cards: dict[str, CounterCard] = {}
        for sig, label in [("MCU_GPI1_DI", "GPI1"), ("MCU_GPI2_DI", "GPI2")]:
            c = CounterCard(f"{label} 电平")
            self.gpi_cards[sig] = c
            gpi_row.addWidget(c)
        gpi_row.addStretch()
        lsd_box.addLayout(gpi_row)
        lsd_wrap = QWidget()
        lsd_wrap.setLayout(lsd_box)
        grid.addWidget(lsd_wrap, 0, 1)

        # ── 第二行: 通信状态（按分类） ─────────────────────────
        comm_wrap = QWidget()
        comm_lay = QVBoxLayout(comm_wrap)
        comm_lay.setContentsMargins(0, 0, 0, 0)
        comm_lay.setSpacing(6)

        comm_title = QLabel("通信状态")
        comm_title.setStyleSheet("color: #dddddd; font-weight: bold;")
        comm_lay.addWidget(comm_title)

        # RS232 子组
        rs232_grp = StatusGroup("RS232")
        self.rs232_grp = rs232_grp
        rs232_grp.add_cell("Rs2320", "RS232.0")
        rs232_grp.add_cell("Rs2321", "RS232.1")
        comm_lay.addWidget(rs232_grp)

        # RS485 子组 + 错误计数
        rs485_row = QHBoxLayout()
        rs485_grp = StatusGroup("RS485")
        self.rs485_grp = rs485_grp
        rs485_grp.add_cell("RS485_Status", "RS485/串口", "MCU端Uart监控状态")
        rs485_grp.add_cell("RS485R", "RS485")
        rs485_row.addWidget(rs485_grp)
        rs485_ec_row = QHBoxLayout()
        self.rs485_ec: dict[str, CounterCard] = {}
        for sig in ["Rs485_Rev_Ec", "Rs485_Trans_Ec"]:
            c = CounterCard(sig.replace("_Ec", ""))
            self.rs485_ec[sig] = c
            rs485_ec_row.addWidget(c)
        rs485_ec_row.addStretch()
        rs485_inner = QVBoxLayout()
        rs485_inner.addWidget(rs485_grp)
        rs485_inner.addLayout(rs485_ec_row)
        rs485_wrap = QWidget()
        rs485_wrap.setLayout(rs485_inner)
        comm_lay.addWidget(rs485_wrap)

        # SPI 子组 + 错误计数
        spi_inner = QVBoxLayout()
        spi_grp = StatusGroup("SPI")
        self.spi_grp = spi_grp
        spi_grp.add_cell("SPI_Status", "SPI", "MCU端SPI监控状态")
        spi_grp.add_cell("SpiR", "SPI外设")
        spi_inner.addWidget(spi_grp)
        spi_ec_row = QHBoxLayout()
        self.spi_ec: dict[str, CounterCard] = {}
        for sig in ["SPI_SetEB_Ec", "SPI_Trans_Ec", "SPI_Rev_Ec"]:
            c = CounterCard(sig.replace("_Ec", ""))
            self.spi_ec[sig] = c
            spi_ec_row.addWidget(c)
        spi_ec_row.addStretch()
        spi_inner.addLayout(spi_ec_row)
        spi_wrap = QWidget()
        spi_wrap.setLayout(spi_inner)
        comm_lay.addWidget(spi_wrap)

        # SSD + 供电状态
        ssd_row = QHBoxLayout()
        ssd_grp = StatusGroup("SSD/供电")
        self.ssd_grp = ssd_grp
        ssd_grp.add_cell("SsdRw", "SSD读写")
        ssd_grp.add_cell("MCU_V_Status", "MCU供电")
        ssd_grp.add_cell("SOC_V_Status", "SOC供电")
        ssd_row.addWidget(ssd_grp)
        ssd_row.addStretch()
        comm_lay.addLayout(ssd_row)

        grid.addWidget(comm_wrap, 1, 0, 1, 2)  # 横跨两列

        # ── 第三行: CAN 状态 ───────────────────────────────────
        self.can_grp = StatusGroup("CAN 通道状态")
        for i in range(1, 5):
            self.can_grp.add_cell(f"CAN{i}_Status", f"CAN{i}")
        self.can_ec: dict[str, CounterCard] = {}
        can_ec_row = QHBoxLayout()
        for i in range(1, 5):
            c = CounterCard(f"CAN{i} EC")
            self.can_ec[f"CAN{i}_EC"] = c
            can_ec_row.addWidget(c)
        can_box = QVBoxLayout()
        can_box.addWidget(self.can_grp)
        can_box.addLayout(can_ec_row)
        can_wrap = QWidget()
        can_wrap.setLayout(can_box)
        grid.addWidget(can_wrap, 2, 0)

        # ── 第四行: I2C 链路状态（修正: 只有 4 Des + 11 Ser） ──
        i2c_grp = StatusGroup("I2C 链路状态", cols=4)
        for i in range(I2C_DES_COUNT):
            i2c_grp.add_cell(f"I2cDes{i}", f"I2C{i} Des")
        for i in range(I2C_SER_COUNT):
            i2c_grp.add_cell(f"I2cSer{i}", f"I2C{i} Ser")
        self.i2c_grp = i2c_grp
        grid.addWidget(i2c_grp, 3, 0, 1, 2)  # 横跨两列

        grid.setColumnStretch(0, 1)
        grid.setColumnStretch(1, 1)
        grid.setRowStretch(3, 1)
        scroll.setWidget(body)
        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.addWidget(scroll)

    def refresh(self):
        # 状态 LED 刷新
        for group, keys in [
            (self.hsd_grp, HSD_PINS),
            (self.lsd_grp, LSD_PINS),
            (self.rs232_grp, ["Rs2320", "Rs2321"]),
            (self.rs485_grp, ["RS485_Status", "RS485R"]),
            (self.spi_grp, ["SPI_Status", "SpiR"]),
            (self.ssd_grp, ["SsdRw", "MCU_V_Status", "SOC_V_Status"]),
            (self.can_grp, [f"CAN{i}_Status" for i in range(1, 5)]),
            (self.i2c_grp, [f"I2cDes{i}" for i in range(I2C_DES_COUNT)]
                           + [f"I2cSer{i}" for i in range(I2C_SER_COUNT)]),
        ]:
            for sig in keys:
                raw = self.model.raw_of(sig)
                group.update_led(sig, None if raw is None
                                 else self.model.decoder.is_status_normal(sig, raw))
        # HSD ADC 值
        for i in range(7):
            st = self.model.channels[f"HSD{i + 1}"]
            card = self.hsd_adc[f"HSD{i + 1}"]
            card.set_value(st.value if st.valid else None, ok=st.normal)
        # 错误计数
        for sig, card in self.lsd_ec.items():
            card.set_value(self._cnt(sig))
        for sig, card in self.gpi_cards.items():
            card.set_value(self._cnt(sig))
        for sig, card in self.rs485_ec.items():
            card.set_value(self._cnt(sig))
        for sig, card in self.spi_ec.items():
            card.set_value(self._cnt(sig))
        for sig, card in self.can_ec.items():
            card.set_value(self._cnt(sig))
        # 测试状态
        for sig, label in (("U1000_Test_Status", self.test_u1000),
                           ("U1001_Test_Status", self.test_u1001)):
            raw = self.model.raw_of(sig)
            label.setText(self.model.decoder._status_text(sig, raw)
                          if raw is not None else "--")

    def _cnt(self, sig: str):
        raw = self.model.raw_of(sig)
        return raw if raw is not None else "--"
