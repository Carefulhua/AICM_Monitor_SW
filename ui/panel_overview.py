"""总览面板：电源电压/温度卡片 + 报文健康（超时检测）。"""
from __future__ import annotations

from PyQt5.QtCore import Qt
from PyQt5.QtGui import QFont
from PyQt5.QtWidgets import (QGridLayout, QHBoxLayout, QLabel, QScrollArea,
                             QVBoxLayout, QWidget)

from data.model import BusModel
from ui.widgets import CounterCard, Led, StatusGroup, ValueCard

VOLTAGE_ORDER = [
    "VBATT_P", "VBATT_SOC_P", "DC17V", "DC17VHV", "VCC_12V", "DV12VGMSL",
    "IGN", "CAN0_INH", "TBOX_WP", "DC5V", "DC5VMV", "DC5V0S",
    "DC3V3", "DC3V3S", "SYS_VIN_SV", "VCC_3V3", "AD1", "AD2", "DC1V8S", "VDD_1V25",
]


class OverviewPanel(QWidget):
    def __init__(self, model: BusModel, parent=None):
        super().__init__(parent)
        self.model = model
        root = QVBoxLayout(self)
        root.setContentsMargins(8, 8, 8, 8)
        root.setSpacing(8)

        # 报文健康条
        health_row = QHBoxLayout()
        health_row.setSpacing(10)
        title = QLabel("报文健康")
        title.setFont(QFont("Microsoft YaHei", 10, QFont.Bold))
        title.setStyleSheet("color: #dddddd;")
        health_row.addWidget(title)
        self.msg_leds: dict[str, Led] = {}
        for fid, mst in model.messages.items():
            led = Led(title=mst.name, radius=5)
            health_row.addWidget(led)
            self.msg_leds[mst.name] = led
        health_row.addStretch()
        self.alarm_count = CounterCard("异常通道")
        health_row.addWidget(self.alarm_count)
        root.addLayout(health_row)

        # 供电状态 (0x65B Mcu_USV_Status)
        self.power_grp = StatusGroup("供电状态", cols=4)
        self.power_grp.add_cell("MCU_V_Status", "MCU供电")
        self.power_grp.add_cell("SOC_V_Status", "SOC供电")
        root.addWidget(self.power_grp)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QScrollArea.NoFrame)
        scroll.setStyleSheet(
            "QScrollArea { background-color: #1e1e1e; border: none; }"
            "QScrollArea > QWidget > QWidget { background-color: #1e1e1e; }"
            "QScrollBar:vertical { background: #1e1e1e; width: 10px; }"
            "QScrollBar::handle:vertical { background: #3d3d3d; border-radius: 5px;"
            " min-height: 20px; }"
            "QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical { height: 0; }")
        body = QWidget()
        body_lay = QVBoxLayout(body)
        body_lay.setContentsMargins(0, 0, 0, 0)
        body_lay.setSpacing(10)

        # 电源电压卡片 (20)
        v_title = QLabel("电源电压")
        v_title.setFont(QFont("Microsoft YaHei", 10, QFont.Bold))
        v_title.setStyleSheet("color: #dddddd;")
        body_lay.addWidget(v_title)
        v_grid = QGridLayout()
        v_grid.setSpacing(8)
        self.voltage_cards: dict[str, ValueCard] = {}
        names = [n for n in VOLTAGE_ORDER if n in model.channels]
        names += [n for n in model.channels if n not in VOLTAGE_ORDER and model.channels[n].unit == "V"]
        for i, name in enumerate(names):
            card = ValueCard(name, "V")
            v_grid.addWidget(card, i // 5, i % 5)
            self.voltage_cards[name] = card
        for i in range(5):
            v_grid.setColumnStretch(i, 1)
        body_lay.addLayout(v_grid)

        # 温度卡片
        t_title = QLabel("板温")
        t_title.setFont(QFont("Microsoft YaHei", 10, QFont.Bold))
        t_title.setStyleSheet("color: #dddddd;")
        body_lay.addWidget(t_title)
        t_row = QHBoxLayout()
        self.temp_cards: dict[str, ValueCard] = {}
        for name in ("SOC_TEMP", "TEMP5152"):
            if name in model.channels:
                ch = model.channels[name]
                card = ValueCard(ch.desc, "℃")
                t_row.addWidget(card)
                self.temp_cards[name] = card
        t_row.addStretch()
        body_lay.addLayout(t_row)

        # CPU 负载 (0x65E McuCpuLoad)
        c_title = QLabel("CPU 负载")
        c_title.setFont(QFont("Microsoft YaHei", 10, QFont.Bold))
        c_title.setStyleSheet("color: #dddddd;")
        body_lay.addWidget(c_title)
        cpu_row = QHBoxLayout()
        self.cpu_cards: dict[str, CounterCard] = {}
        for i in range(6):
            name = f"CPU{i}_Load"
            card = CounterCard(f"CPU{i}")
            cpu_row.addWidget(card)
            self.cpu_cards[name] = card
        cpu_row.addStretch()
        body_lay.addLayout(cpu_row)
        body_lay.addStretch()

        scroll.setWidget(body)
        root.addWidget(scroll, 1)

    def refresh(self):
        model = self.model
        for name, card in self.voltage_cards.items():
            st = model.channels[name]
            card.set_value(st.value if st.valid else None, ok=st.normal)
        for name, card in self.temp_cards.items():
            st = model.channels[name]
            card.set_value(st.value if st.valid else None)
        for name, card in self.cpu_cards.items():
            card.set_value(model.raw_of(name) if model.raw_of(name) is not None else "--")
        for mname, led in self.msg_leds.items():
            mst = next((m for m in model.messages.values() if m.name == mname), None)
            if mst is None:
                led.set_state(None)
                continue
            led.set_state(not mst.timeout if mst.seen else None)
        for sig in ("MCU_V_Status", "SOC_V_Status"):
            raw = model.raw_of(sig)
            self.power_grp.update_led(
                sig, None if raw is None else model.decoder.is_status_normal(sig, raw))
        n_alarm = sum(1 for st in model.channels.values() if st.valid and not st.normal)
        self.alarm_count.set_value(n_alarm)
