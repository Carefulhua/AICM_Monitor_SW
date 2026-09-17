"""IO 状态面板：HSD ADC/LSD/通信状态/CAN/I2C 高边低边驱动状态与计数。"""
from __future__ import annotations

from PyQt5.QtCore import pyqtSignal
from PyQt5.QtWidgets import (QGridLayout, QHBoxLayout, QLabel,
                             QScrollArea, QVBoxLayout, QWidget)

from data.model import BusModel
from ui.widgets import CounterCard, StatusGroup, ValueCard

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

        # ── Row 0 Col 0: HSD ADC 值 + 测试状态 ───────────────
        hsd_wrap = QWidget()
        hsd_lay = QVBoxLayout(hsd_wrap)
        hsd_lay.setContentsMargins(0, 0, 0, 0)
        hsd_lay.setSpacing(6)

        hsd_title = QLabel("高边驱动 HSD")
        hsd_title.setStyleSheet("color: #dddddd; font-weight: bold;")
        hsd_lay.addWidget(hsd_title)

        self.hsd_adc: dict[str, ValueCard] = {}
        adc_grid = QGridLayout()
        adc_grid.setSpacing(6)
        for i in range(7):
            card = ValueCard(f"P23.{i} ADC", "ADC")
            self.hsd_adc[f"HSD{i + 1}"] = card
            adc_grid.addWidget(card, i // 4, i % 4)
        hsd_lay.addLayout(adc_grid)

        # U1000/U1001 测试状态
        test_row = QHBoxLayout()
        test_row.addWidget(QLabel("U1000:"))
        self.test_u1000 = QLabel("--")
        test_row.addWidget(self.test_u1000)
        test_row.addSpacing(16)
        test_row.addWidget(QLabel("U1001:"))
        self.test_u1001 = QLabel("--")
        test_row.addWidget(self.test_u1001)
        test_row.addStretch()
        hsd_lay.addLayout(test_row)
        hsd_lay.addStretch()
        grid.addWidget(hsd_wrap, 0, 0)

        # ── Row 0 Col 1: LSD 状态 + 错误计数 + GPI ──────────
        lsd_wrap = QWidget()
        lsd_lay = QVBoxLayout(lsd_wrap)
        lsd_lay.setContentsMargins(0, 0, 0, 0)
        lsd_lay.setSpacing(6)

        self.lsd_grp = StatusGroup("低边驱动 LSD")
        for pin in LSD_PINS:
            self.lsd_grp.add_cell(pin, pin.replace("LSD_Status_", "LSD "))
        lsd_lay.addWidget(self.lsd_grp)

        self.lsd_ec: dict[str, CounterCard] = {}
        ec_row = QHBoxLayout()
        for sig in ["BTT3050_U1100_EC", "BTT3050_U1101_EC", "BTS3410_LSD1_EC", "BTS3410_LSD2_EC"]:
            c = CounterCard(sig.replace("_EC", ""))
            self.lsd_ec[sig] = c
            ec_row.addWidget(c)
        lsd_lay.addLayout(ec_row)

        gpi_row = QHBoxLayout()
        gpi_row.addWidget(QLabel("GPI:"))
        self.gpi_cards: dict[str, CounterCard] = {}
        for sig, label in [("MCU_GPI1_DI", "GPI1"), ("MCU_GPI2_DI", "GPI2")]:
            c = CounterCard(label)
            self.gpi_cards[sig] = c
            gpi_row.addWidget(c)
        gpi_row.addStretch()
        lsd_lay.addLayout(gpi_row)
        lsd_lay.addStretch()
        grid.addWidget(lsd_wrap, 0, 1)

        # ── Row 1 Col 0: RS232 + RS485 ──────────────────────
        uart_wrap = QWidget()
        uart_lay = QVBoxLayout(uart_wrap)
        uart_lay.setContentsMargins(0, 0, 0, 0)
        uart_lay.setSpacing(6)

        self.rs232_grp = StatusGroup("RS232")
        self.rs232_grp.add_cell("Rs2320", "RS232.0")
        self.rs232_grp.add_cell("Rs2321", "RS232.1")
        uart_lay.addWidget(self.rs232_grp)

        self.rs485_grp = StatusGroup("RS485")
        self.rs485_grp.add_cell("RS485_Status", "RS485/串口", "MCU端Uart监控状态")
        self.rs485_grp.add_cell("RS485R", "RS485")
        uart_lay.addWidget(self.rs485_grp)

        self.rs485_ec: dict[str, CounterCard] = {}
        ec_row = QHBoxLayout()
        for sig in ["Rs485_Rev_Ec", "Rs485_Trans_Ec"]:
            c = CounterCard(sig.replace("_Ec", ""))
            self.rs485_ec[sig] = c
            ec_row.addWidget(c)
        ec_row.addStretch()
        uart_lay.addLayout(ec_row)
        uart_lay.addStretch()
        grid.addWidget(uart_wrap, 1, 0)

        # ── Row 1 Col 1: SPI + SSD/供电 ─────────────────────
        spi_wrap = QWidget()
        spi_lay = QVBoxLayout(spi_wrap)
        spi_lay.setContentsMargins(0, 0, 0, 0)
        spi_lay.setSpacing(6)

        self.spi_grp = StatusGroup("SPI")
        self.spi_grp.add_cell("SPI_Status", "SPI", "MCU端SPI监控状态")
        self.spi_grp.add_cell("SpiR", "SPI外设")
        spi_lay.addWidget(self.spi_grp)

        self.spi_ec: dict[str, CounterCard] = {}
        ec_row = QHBoxLayout()
        for sig in ["SPI_SetEB_Ec", "SPI_Trans_Ec", "SPI_Rev_Ec"]:
            c = CounterCard(sig.replace("_Ec", ""))
            self.spi_ec[sig] = c
            ec_row.addWidget(c)
        ec_row.addStretch()
        spi_lay.addLayout(ec_row)

        self.ssd_grp = StatusGroup("SSD")
        self.ssd_grp.add_cell("SsdRw", "SSD读写")
        spi_lay.addWidget(self.ssd_grp)
        spi_lay.addStretch()
        grid.addWidget(spi_wrap, 1, 1)

        # ── Row 2 Col 0: CAN 状态 ───────────────────────────
        can_wrap = QWidget()
        can_lay = QVBoxLayout(can_wrap)
        can_lay.setContentsMargins(0, 0, 0, 0)
        can_lay.setSpacing(6)

        self.can_grp = StatusGroup("CAN 通道状态")
        for i in range(1, 5):
            self.can_grp.add_cell(f"CAN{i}_Status", f"CAN{i}")
        can_lay.addWidget(self.can_grp)

        self.can_ec: dict[str, CounterCard] = {}
        ec_row = QHBoxLayout()
        for i in range(1, 5):
            c = CounterCard(f"CAN{i} EC")
            self.can_ec[f"CAN{i}_EC"] = c
            ec_row.addWidget(c)
        can_lay.addLayout(ec_row)
        can_lay.addStretch()
        grid.addWidget(can_wrap, 2, 0)

        # ── Row 2 Col 1: I2C 链路状态 ──────────────────────
        i2c_wrap = QWidget()
        i2c_lay = QVBoxLayout(i2c_wrap)
        i2c_lay.setContentsMargins(0, 0, 0, 0)
        i2c_lay.setSpacing(6)

        i2c_grp = StatusGroup("I2C 链路状态", cols=4)
        for i in range(I2C_DES_COUNT):
            i2c_grp.add_cell(f"I2cDes{i}", f"I2C{i} Des")
        for i in range(I2C_SER_COUNT):
            i2c_grp.add_cell(f"I2cSer{i}", f"I2C{i} Ser")
        self.i2c_grp = i2c_grp
        i2c_lay.addWidget(i2c_grp)
        i2c_lay.addStretch()
        grid.addWidget(i2c_wrap, 2, 1)

        # 均匀分布
        for col in range(2):
            grid.setColumnStretch(col, 1)
        for row in range(3):
            grid.setRowStretch(row, 1)

        scroll.setWidget(body)
        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.addWidget(scroll)

    def refresh(self):
        # 状态 LED 刷新
        for group, keys in [
            (self.lsd_grp, LSD_PINS),
            (self.rs232_grp, ["Rs2320", "Rs2321"]),
            (self.rs485_grp, ["RS485_Status", "RS485R"]),
            (self.spi_grp, ["SPI_Status", "SpiR"]),
            (self.ssd_grp, ["SsdRw"]),
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
            card.set_value(st.value if st.valid else None)
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
