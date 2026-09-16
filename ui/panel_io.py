"""IO 状态面板：HSD/LSD/USV(CAN/SPI/UART)/I2C 高边低边驱动状态与计数。"""
from __future__ import annotations

from PyQt5.QtCore import pyqtSignal
from PyQt5.QtWidgets import (QGridLayout, QHBoxLayout, QLabel, QPushButton,
                             QScrollArea, QVBoxLayout, QWidget)

from data.model import BusModel
from ui.widgets import CounterCard, GREEN, StatusGroup, ValueCard

HSD_PINS = ["HSD_Status_P230", "HSD_Status_P231", "HSD_Status_P232", "HSD_Status_P233",
            "HSD_Status_P234", "HSD_Status_P235", "HSD_Status_P236"]
LSD_PINS = ["LSD_Status_P322", "LSD_Status_P323", "LSD_Status_P324", "LSD_Status_P325"]


class IOPanel(QWidget):
    hsd_control_requested = pyqtSignal(int)  # 0x680 byte0 掩码 (bit0~6 = HSD1~7)

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

        # 高边驱动 HSD
        self.hsd_grp = StatusGroup("高边驱动 HSD")
        self.hsd_current: dict[str, ValueCard] = {}
        for i, pin in enumerate(HSD_PINS):
            self.hsd_grp.add_cell(pin, f"P23.{i}")
            cur = ValueCard(f"P23.{i} 电流", "A")
            self.hsd_current[f"HSD{i + 1}"] = cur
        hsd_right = QWidget()
        hr = QGridLayout(hsd_right)
        hr.setContentsMargins(0, 0, 0, 0)
        for idx, (name, card) in enumerate(self.hsd_current.items()):
            hr.addWidget(card, idx // 4, idx % 4)
        hsd_box = QHBoxLayout()
        hsd_box.addWidget(self.hsd_grp)
        hsd_box.addWidget(hsd_right, 1)
        hsd_v = QVBoxLayout()
        hsd_v.addLayout(hsd_box)
        # U1000/U1001 测试状态 (0x65C 4bit, 260810 新协议)
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
        ctl_row = QHBoxLayout()
        ctl_row.addWidget(QLabel("HSD 开关 (0x680):"))
        self.hsd_switches: dict[int, QPushButton] = {}
        for i in range(1, 8):
            btn = QPushButton(f"HSD{i}")
            btn.setCheckable(True)
            btn.setEnabled(False)
            btn.setMinimumSize(64, 30)
            btn.toggled.connect(self._hsd_switch_changed)
            self.hsd_switches[i] = btn
            ctl_row.addWidget(btn)
        ctl_row.addStretch()
        hsd_v.addLayout(ctl_row)
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
        # GPI 输入电平 (0x65A McuLSDStatus 同报文, Test Plan case 47~50)
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

        # USV (UART/SPI)
        self.usv_grp = StatusGroup("串口/SPI 状态")
        self.usv_grp.add_cell("RS485_Status", "RS485/串口", "MCU端Uart监控状态")
        self.usv_grp.add_cell("SPI_Status", "SPI", "MCU端SPI监控状态")
        self.usv_grp.add_cell("MCU_V_Status", "MCU供电")
        self.usv_grp.add_cell("SOC_V_Status", "SOC供电")
        self.usv_grp.add_cell("SpiR", "SPI外设")
        self.usv_grp.add_cell("Rs2320", "RS232.0")
        self.usv_grp.add_cell("Rs2321", "RS232.1")
        self.usv_grp.add_cell("RS485R", "RS485")
        self.usv_grp.add_cell("SsdRw", "SSD读写")
        self.usv_ec: dict[str, CounterCard] = {}
        usv_ec_row = QHBoxLayout()
        for sig in ["Rs485_Rev_Ec", "Rs485_Trans_Ec", "SPI_SetEB_Ec", "SPI_Trans_Ec", "SPI_Rev_Ec"]:
            c = CounterCard(sig.replace("_Ec", ""))
            self.usv_ec[sig] = c
            usv_ec_row.addWidget(c)
        usv_box = QVBoxLayout()
        usv_box.addWidget(self.usv_grp)
        usv_box.addLayout(usv_ec_row)
        usv_wrap = QWidget()
        usv_wrap.setLayout(usv_box)
        grid.addWidget(usv_wrap, 0, 2)

        # CAN 状态 + I2C 矩阵
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
        grid.addWidget(can_wrap, 1, 0)

        # I2C 矩阵
        i2c_grp = StatusGroup("I2C 链路状态", cols=4)
        for i in range(11):
            i2c_grp.add_cell(f"I2cDes{i}", f"I2C{i} Des")
            i2c_grp.add_cell(f"I2cSer{i}", f"I2C{i} Ser")
        self.i2c_grp = i2c_grp
        # 垂直堆叠单列：三列并排的最小宽度远超窗口最小宽，缩小时必然
        # 撑出横向滚动条；单列布局宽度只取决于最宽一块，随窗口自适应
        grid.addWidget(hsd_wrap, 0, 0)
        grid.addWidget(lsd_wrap, 1, 0)
        grid.addWidget(usv_wrap, 2, 0)
        grid.addWidget(can_wrap, 3, 0)
        grid.addWidget(i2c_grp, 4, 0)
        grid.setColumnStretch(0, 1)
        grid.setRowStretch(4, 1)
        scroll.setWidget(body)
        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.addWidget(scroll)

    def refresh(self):
        for group, keys in [
            (self.hsd_grp, HSD_PINS),
            (self.lsd_grp, LSD_PINS),
            (self.usv_grp, ["RS485_Status", "SPI_Status", "MCU_V_Status", "SOC_V_Status",
                            "SpiR", "Rs2320", "Rs2321", "RS485R", "SsdRw"]),
            (self.can_grp, [f"CAN{i}_Status" for i in range(1, 5)]),
            (self.i2c_grp, [f"I2c{k}{i}" for i in range(11) for k in ("Des", "Ser")]),
        ]:
            for sig in keys:
                raw = self.model.raw_of(sig)
                group.update_led(sig, None if raw is None
                                 else self.model.decoder.is_status_normal(sig, raw))
        for i in range(7):
            st = self.model.channels[f"HSD{i + 1}"]
            card = self.hsd_current[f"HSD{i + 1}"]
            card.set_value(st.value if st.valid else None, ok=st.normal)
        for sig, card in self.lsd_ec.items():
            card.set_value(self._cnt(sig))
        for sig, card in self.gpi_cards.items():
            card.set_value(self._cnt(sig))
        for sig, card in self.usv_ec.items():
            card.set_value(self._cnt(sig))
        for sig, card in self.can_ec.items():
            card.set_value(self._cnt(sig))
        for sig, label in (("U1000_Test_Status", self.test_u1000),
                           ("U1001_Test_Status", self.test_u1001)):
            raw = self.model.raw_of(sig)
            label.setText(self.model.decoder._status_text(sig, raw)
                          if raw is not None else "--")

    def _cnt(self, sig: str):
        raw = self.model.raw_of(sig)
        return raw if raw is not None else "--"

    def _style_hsd_btn(self, btn: QPushButton):
        c = GREEN if btn.isChecked() else "#555555"
        btn.setStyleSheet(
            f"QPushButton {{ background-color: {c}; color: white; border: none;"
            f" border-radius: 4px; font-weight: bold; }}")

    def _hsd_mask(self) -> int:
        mask = 0
        for i, btn in self.hsd_switches.items():
            if btn.isChecked():
                mask |= 1 << (i - 1)
        return mask

    def _hsd_switch_changed(self, _checked: bool):
        for btn in self.hsd_switches.values():
            self._style_hsd_btn(btn)
        self.hsd_control_requested.emit(self._hsd_mask())

    def set_hsd_enabled(self, enable: bool):
        for btn in self.hsd_switches.values():
            if not enable:
                btn.setChecked(False)
            btn.setEnabled(enable)
            self._style_hsd_btn(btn)