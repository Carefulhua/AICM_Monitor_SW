"""相机面板：11 路相机 Linklock/Videolock/Crc 状态矩阵 + FPS + 链路计数。"""
from __future__ import annotations

from PyQt5.QtCore import Qt
from PyQt5.QtGui import QFont
from PyQt5.QtWidgets import (QGridLayout, QHBoxLayout, QLabel, QVBoxLayout,
                             QWidget)

from data.model import BusModel
from ui.widgets import CounterCard, Led, LedCell, StatusGroup

CAM_COUNT = 11
STATUS_KEYS = ["Linklock", "Videolock", "Crc"]


class CameraPanel(QWidget):
    def __init__(self, model: BusModel, parent=None):
        super().__init__(parent)
        self.model = model
        lay = QVBoxLayout(self)
        lay.setContentsMargins(8, 8, 8, 8)
        lay.setSpacing(10)

        title = QLabel("相机连接状态")
        title.setFont(QFont("Microsoft YaHei", 11, QFont.Bold))
        title.setStyleSheet("color: #dddddd;")
        lay.addWidget(title)

        # 状态矩阵: 列=Cam0-10, 行=Linklock/Videolock/Crc
        self.cam_leds: dict[str, Led] = {}
        matrix = QGridLayout()
        matrix.setSpacing(12)
        for row, key in enumerate(STATUS_KEYS):
            matrix.addWidget(QLabel(key), row + 1, 0)
        for i in range(CAM_COUNT):
            matrix.addWidget(QLabel(f"Cam{i}"), 0, i + 1)
        for i in range(CAM_COUNT):
            for row, key in enumerate(STATUS_KEYS):
                sig = f"Cam{i}{key}"
                led = Led(title=sig)
                matrix.addWidget(led, row + 1, i + 1, Qt.AlignCenter)
                self.cam_leds[sig] = led
        lay.addLayout(matrix)

        # FPS 行
        fps_row = QHBoxLayout()
        fps_row.setSpacing(14)
        fps_label = QLabel("FPS")
        fps_label.setFont(QFont("Microsoft YaHei", 9, QFont.Bold))
        fps_label.setStyleSheet("color: #dddddd;")
        fps_row.addWidget(fps_label)
        self.fps_labels: dict[str, QLabel] = {}
        for i in range(CAM_COUNT):
            lb = QLabel("--")
            lb.setFont(QFont("Consolas", 11, QFont.Bold))
            lb.setStyleSheet("color: #4ecdc4;")
            lb.setAlignment(Qt.AlignCenter)
            lb.setMinimumWidth(56)
            self.fps_labels[f"Cam{i}"] = lb
            fps_row.addWidget(lb)
        fps_row.addStretch()
        lay.addLayout(fps_row)

        # 辅助状态
        aux = QHBoxLayout()
        aux.setSpacing(16)
        self.json_missing_led = Led(title="json_msg_missing")
        aux.addWidget(self.json_missing_led)
        aux.addWidget(QLabel("json报文缺失"))
        self.json_missing_led.setToolTip("json_msg_missing")
        self.rc_card = CounterCard("Rc 滚动计数")
        aux.addWidget(self.rc_card)
        self.fault_card = CounterCard("异常相机")
        aux.addWidget(self.fault_card)
        aux.addStretch()
        lay.addLayout(aux)
        lay.addStretch()

    def refresh(self):
        for sig, led in self.cam_leds.items():
            raw = self.model.raw_of(sig)
            if raw is None:
                led.set_state(None)
            else:
                led.set_state(self.model.decoder.is_status_normal(sig, raw))
        for i in range(CAM_COUNT):
            raw = self.model.raw_of(f"Cam{i}FPS")
            lb = self.fps_labels[f"Cam{i}"]
            lb.setText(str(raw) if raw is not None else "--")
        missing = self.model.raw_of("json_msg_missing")
        self.json_missing_led.set_state(
            None if missing is None else (missing == 0))
        rc = self.model.raw_of("Rc")
        self.rc_card.set_value(rc if rc is not None else "--")
        n_bad = 0
        for i in range(CAM_COUNT):
            for key in STATUS_KEYS:
                sig = f"Cam{i}{key}"
                raw = self.model.raw_of(sig)
                if raw is not None and not self.model.decoder.is_status_normal(sig, raw):
                    n_bad += 1
        self.fault_card.set_value(n_bad)
