"""CAN 报文发送面板：原始帧 + DBC 报文两种方式，支持周期发送，用于调试时手动下发报文。"""
from __future__ import annotations

import time
from typing import Callable

from PyQt5.QtCore import Qt, QTimer
from PyQt5.QtGui import QFont
from PyQt5.QtWidgets import (QComboBox, QFrame, QHBoxLayout, QHeaderView,
                             QLabel, QLineEdit, QPlainTextEdit, QPushButton,
                             QScrollArea, QSpinBox, QTableWidget,
                             QTableWidgetItem, QVBoxLayout, QWidget)

from data.dbc_parser import Database
from ui.widgets import BLUE, BORDER, CARD_BG, GREEN, RED, TEXT_DIM

MAX_LOG_LINES = 500
STD_ID_MAX = 0x7FF
DEFAULT_PERIOD_MS = 100

_INPUT_QSS = (
    "QLineEdit, QSpinBox, QComboBox { background-color: #3a3a3a; color: #cccccc;"
    " border: 1px solid #555; border-radius: 4px; padding: 4px; font-size: 13px; }"
    "QComboBox QAbstractItemView { background-color: #3a3a3a; color: #cccccc;"
    " selection-background-color: #4a9eff; }"
)

_SEND_BTN_QSS = (
    f"QPushButton {{ background-color: {GREEN}; color: white; border: none;"
    " border-radius: 5px; font-size: 13px; font-weight: bold;"
    " min-height: 30px; min-width: 96px; }"
    "QPushButton:hover { background-color: #5cbf60; }"
    "QPushButton:disabled { background-color: #555555; }"
)

_CYCLE_BTN_QSS = (
    f"QPushButton {{ background-color: {BLUE}; color: white; border: none;"
    " border-radius: 5px; font-size: 13px; font-weight: bold;"
    " min-height: 30px; min-width: 96px; }"
    "QPushButton:hover { background-color: #5aafff; }"
    f"QPushButton:checked {{ background-color: {RED}; }}"
    "QPushButton:checked:hover { background-color: #f44336; }"
    "QPushButton:disabled { background-color: #555555; }"
)

_TABLE_QSS = (
    "QTableWidget { background-color: #2b2b2b; color: #cccccc;"
    " gridline-color: #3a3a3a; border: 1px solid #3a3a3a; border-radius: 4px;"
    " font-size: 12px; }"
    "QHeaderView::section { background-color: #333333; color: #bbbbbb;"
    " border: none; padding: 4px; font-size: 12px; }"
)

_LOG_QSS = (
    "QPlainTextEdit { background-color: #161616; color: #cccccc;"
    " border: 1px solid #3a3a3a; border-radius: 4px;"
    ' font-family: "Consolas", monospace; font-size: 12px; }'
)

_SCROLL_QSS = (
    "QScrollArea { background-color: #1e1e1e; border: none; }"
    "QScrollArea > QWidget > QWidget { background-color: #1e1e1e; }"
    "QScrollBar:vertical { background: #1e1e1e; width: 10px; }"
    "QScrollBar::handle:vertical { background: #3d3d3d; border-radius: 5px;"
    " min-height: 20px; }"
)


def _title(text: str) -> QLabel:
    label = QLabel(text)
    label.setFont(QFont("Microsoft YaHei", 10, QFont.Bold))
    label.setStyleSheet("color: #dddddd;")
    return label


def _hint(text: str) -> QLabel:
    label = QLabel(text)
    label.setFont(QFont("Microsoft YaHei", 9))
    label.setStyleSheet(f"color: {TEXT_DIM};")
    return label


def _card(title_text: str) -> tuple[QFrame, QVBoxLayout]:
    frame = QFrame()
    frame.setObjectName("card")
    frame.setStyleSheet(
        f"#card {{ background-color: {CARD_BG}; border: 1px solid {BORDER};"
        " border-radius: 6px; }")
    lay = QVBoxLayout(frame)
    lay.setContentsMargins(12, 10, 12, 10)
    lay.setSpacing(8)
    lay.addWidget(_title(title_text))
    return frame, lay


class SendPanel(QWidget):
    def __init__(self, db: Database, send_cb: Callable[[int, bytes], bool],
                 parent=None):
        super().__init__(parent)
        self.db = db
        self.send_cb = send_cb

        self._cycle_raw = QTimer(self)
        self._cycle_raw.timeout.connect(self._on_cycle_raw)
        self._cycle_dbc = QTimer(self)
        self._cycle_dbc.timeout.connect(self._on_cycle_dbc)

        body = QWidget()
        root = QVBoxLayout(body)
        root.setContentsMargins(10, 10, 10, 10)
        root.setSpacing(12)
        root.addWidget(self._build_raw_group())
        root.addWidget(self._build_dbc_group())
        root.addWidget(self._build_log_group(), 1)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QScrollArea.NoFrame)
        scroll.setStyleSheet(_SCROLL_QSS)
        scroll.setWidget(body)

        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.addWidget(scroll)

        self._on_msg_changed(0)

    # ---------- 界面构建 ----------
    def _build_raw_group(self) -> QFrame:
        frame, lay = _card("原始帧发送")

        row1 = QHBoxLayout()
        row1.setSpacing(8)
        row1.addWidget(_hint("CAN ID (hex)"))
        self.raw_id = QLineEdit()
        self.raw_id.setPlaceholderText("680")
        self.raw_id.setFixedWidth(120)
        self.raw_id.setStyleSheet(_INPUT_QSS)
        row1.addWidget(self.raw_id)
        row1.addSpacing(12)
        row1.addWidget(_hint("数据 (hex, ≤8 字节)"))
        self.raw_data = QLineEdit()
        self.raw_data.setPlaceholderText("01 00 00 00 00 00 00 00")
        self.raw_data.setStyleSheet(_INPUT_QSS)
        row1.addWidget(self.raw_data, 1)
        lay.addLayout(row1)

        row2 = QHBoxLayout()
        row2.setSpacing(8)
        self.raw_send_btn = QPushButton("发送一次")
        self.raw_send_btn.setStyleSheet(_SEND_BTN_QSS)
        self.raw_send_btn.clicked.connect(self._on_send_raw)
        row2.addWidget(self.raw_send_btn)

        self.raw_cycle_btn = QPushButton("周期发送")
        self.raw_cycle_btn.setCheckable(True)
        self.raw_cycle_btn.setStyleSheet(_CYCLE_BTN_QSS)
        self.raw_cycle_btn.toggled.connect(self._on_toggle_cycle_raw)
        row2.addWidget(self.raw_cycle_btn)

        row2.addWidget(_hint("周期"))
        self.raw_period = QSpinBox()
        self.raw_period.setRange(10, 60000)
        self.raw_period.setValue(DEFAULT_PERIOD_MS)
        self.raw_period.setSuffix(" ms")
        self.raw_period.setFixedWidth(110)
        self.raw_period.setStyleSheet(_INPUT_QSS)
        self.raw_period.valueChanged.connect(self._on_raw_period_changed)
        row2.addWidget(self.raw_period)
        row2.addStretch()
        lay.addLayout(row2)
        return frame

    def _build_dbc_group(self) -> QFrame:
        frame, lay = _card("DBC 报文发送")

        row1 = QHBoxLayout()
        row1.setSpacing(8)
        row1.addWidget(_hint("报文"))
        self.msg_cb = QComboBox()
        self.msg_cb.setStyleSheet(_INPUT_QSS)
        for mid in sorted(self.db.messages):
            msg = self.db.messages[mid]
            if msg.length <= 0:
                continue
            self.msg_cb.addItem(
                f"0x{mid:03X}  {msg.name}  ({msg.length} 字节)", mid)
        self.msg_cb.currentIndexChanged.connect(self._on_msg_changed)
        row1.addWidget(self.msg_cb, 1)
        lay.addLayout(row1)

        self.sig_table = QTableWidget(0, 3)
        self.sig_table.setHorizontalHeaderLabels(["信号", "物理值", "单位"])
        self.sig_table.verticalHeader().setVisible(False)
        self.sig_table.setStyleSheet(_TABLE_QSS)
        header = self.sig_table.horizontalHeader()
        header.setSectionResizeMode(0, QHeaderView.Stretch)
        header.setSectionResizeMode(1, QHeaderView.ResizeToContents)
        header.setSectionResizeMode(2, QHeaderView.ResizeToContents)
        self.sig_table.setMinimumHeight(160)
        self.sig_table.itemChanged.connect(self._on_sig_edited)
        lay.addWidget(self.sig_table)

        prev_row = QHBoxLayout()
        prev_row.setSpacing(8)
        prev_row.addWidget(_hint("编码预览 (hex)"))
        self.preview = QLineEdit()
        self.preview.setReadOnly(True)
        self.preview.setStyleSheet(
            _INPUT_QSS + ' QLineEdit { font-family: "Consolas", monospace; }')
        prev_row.addWidget(self.preview, 1)
        lay.addLayout(prev_row)

        row2 = QHBoxLayout()
        row2.setSpacing(8)
        self.dbc_send_btn = QPushButton("发送一次")
        self.dbc_send_btn.setStyleSheet(_SEND_BTN_QSS)
        self.dbc_send_btn.clicked.connect(self._on_send_dbc)
        row2.addWidget(self.dbc_send_btn)

        self.dbc_cycle_btn = QPushButton("周期发送")
        self.dbc_cycle_btn.setCheckable(True)
        self.dbc_cycle_btn.setStyleSheet(_CYCLE_BTN_QSS)
        self.dbc_cycle_btn.toggled.connect(self._on_toggle_cycle_dbc)
        row2.addWidget(self.dbc_cycle_btn)

        row2.addWidget(_hint("周期"))
        self.dbc_period = QSpinBox()
        self.dbc_period.setRange(10, 60000)
        self.dbc_period.setValue(DEFAULT_PERIOD_MS)
        self.dbc_period.setSuffix(" ms")
        self.dbc_period.setFixedWidth(110)
        self.dbc_period.setStyleSheet(_INPUT_QSS)
        self.dbc_period.valueChanged.connect(self._on_dbc_period_changed)
        row2.addWidget(self.dbc_period)
        row2.addStretch()
        lay.addLayout(row2)
        return frame

    def _build_log_group(self) -> QFrame:
        frame, lay = _card("发送日志")
        self.log = QPlainTextEdit()
        self.log.setReadOnly(True)
        self.log.setStyleSheet(_LOG_QSS)
        self.log.setMinimumHeight(120)
        self.log.document().setMaximumBlockCount(MAX_LOG_LINES)
        lay.addWidget(self.log)
        return frame

    # ---------- 日志 ----------
    def _append_log(self, text: str, ok: bool = True) -> None:
        color = "#4caf50" if ok else "#e53935"
        self.log.appendHtml(f'<span style="color:{color}">{text}</span>')

    def _log_frame(self, can_id: int, data: bytes, ok: bool) -> None:
        now = time.time()
        stamp = time.strftime("%H:%M:%S", time.localtime(now))
        stamp = f"{stamp}.{int(now * 1000) % 1000:03d}"
        hexs = " ".join(f"{b:02X}" for b in data)
        status = "OK" if ok else "失败(未连接?)"
        self._append_log(
            f"{stamp}  0x{can_id:03X}  [{len(data)}]  {hexs}  {status}", ok)

    # ---------- 原始帧 ----------
    @staticmethod
    def _parse_hex_id(text: str) -> int | None:
        token = text.strip().lower().replace("0x", "").replace(" ", "")
        if not token:
            return None
        try:
            value = int(token, 16)
        except ValueError:
            return None
        return value if 0 <= value <= STD_ID_MAX else None

    @staticmethod
    def _parse_hex_data(text: str) -> bytes | None:
        tokens = text.replace(",", " ").split()
        if len(tokens) > 8:
            return None
        out = bytearray()
        for token in tokens:
            token = token.lower().replace("0x", "")
            if not token or len(token) > 2:
                return None
            try:
                out.append(int(token, 16))
            except ValueError:
                return None
        return bytes(out)

    def _current_raw(self) -> tuple[int, bytes] | None:
        can_id = self._parse_hex_id(self.raw_id.text())
        if can_id is None:
            self._append_log("原始帧: CAN ID 非法 (应为 0..0x7FF 的 hex)", False)
            return None
        data = self._parse_hex_data(self.raw_data.text())
        if data is None:
            self._append_log(
                "原始帧: 数据非法 (每字节 1-2 位 hex, 最多 8 字节)", False)
            return None
        return can_id, data

    def _on_send_raw(self) -> None:
        parsed = self._current_raw()
        if parsed is None:
            return
        can_id, data = parsed
        self._log_frame(can_id, data, self.send_cb(can_id, data))

    def _on_cycle_raw(self) -> None:
        parsed = self._current_raw()
        if parsed is None:
            self._stop_cycle_raw()
            return
        can_id, data = parsed
        self._log_frame(can_id, data, self.send_cb(can_id, data))

    def _on_toggle_cycle_raw(self, checked: bool) -> None:
        if checked:
            self._stop_cycle_dbc()
            self.raw_cycle_btn.setText("停止周期")
            self._cycle_raw.start(self.raw_period.value())
        else:
            self._cycle_raw.stop()
            self.raw_cycle_btn.setText("周期发送")

    def _stop_cycle_raw(self) -> None:
        self._cycle_raw.stop()
        self.raw_cycle_btn.setChecked(False)
        self.raw_cycle_btn.setText("周期发送")

    def _on_raw_period_changed(self, value: int) -> None:
        if self._cycle_raw.isActive():
            self._cycle_raw.start(value)

    # ---------- DBC 报文 ----------
    def _on_msg_changed(self, _index: int) -> None:
        mid = self.msg_cb.currentData()
        msg = self.db.messages.get(mid) if mid is not None else None
        self.sig_table.blockSignals(True)
        self.sig_table.setRowCount(0)
        if msg is not None:
            for sig in msg.signals.values():
                row = self.sig_table.rowCount()
                self.sig_table.insertRow(row)
                name_item = QTableWidgetItem(sig.name)
                name_item.setFlags(Qt.ItemIsEnabled)
                self.sig_table.setItem(row, 0, name_item)
                val_item = QTableWidgetItem(f"{sig.offset:g}")
                val_item.setTextAlignment(Qt.AlignRight | Qt.AlignVCenter)
                self.sig_table.setItem(row, 1, val_item)
                unit_item = QTableWidgetItem(sig.unit)
                unit_item.setFlags(Qt.ItemIsEnabled)
                self.sig_table.setItem(row, 2, unit_item)
        self.sig_table.blockSignals(False)
        self._update_preview()

    def _on_sig_edited(self, _item: QTableWidgetItem) -> None:
        self._update_preview()

    def _build_dbc_bytes(self) -> tuple[int, bytes] | None:
        mid = self.msg_cb.currentData()
        msg = self.db.messages.get(mid) if mid is not None else None
        if msg is None:
            self._append_log("DBC: 未选择报文", False)
            return None
        data = bytearray(msg.length)
        for row, sig in enumerate(msg.signals.values()):
            item = self.sig_table.item(row, 1)
            if item is None:
                continue
            try:
                phys = float(item.text())
            except ValueError:
                self._append_log(
                    f"DBC: 信号 {sig.name} 值非法: {item.text()!r}", False)
                return None
            sig.encode_phys(data, phys)
        return msg.frame_id, bytes(data)

    def _update_preview(self) -> None:
        mid = self.msg_cb.currentData()
        msg = self.db.messages.get(mid) if mid is not None else None
        if msg is None:
            self.preview.setText("")
            return
        data = bytearray(msg.length)
        for row, sig in enumerate(msg.signals.values()):
            item = self.sig_table.item(row, 1)
            if item is None:
                continue
            try:
                sig.encode_phys(data, float(item.text()))
            except ValueError:
                continue
        self.preview.setText(" ".join(f"{b:02X}" for b in data))

    def _on_send_dbc(self) -> None:
        parsed = self._build_dbc_bytes()
        if parsed is None:
            return
        can_id, data = parsed
        self._log_frame(can_id, data, self.send_cb(can_id, data))

    def _on_cycle_dbc(self) -> None:
        parsed = self._build_dbc_bytes()
        if parsed is None:
            self._stop_cycle_dbc()
            return
        can_id, data = parsed
        self._log_frame(can_id, data, self.send_cb(can_id, data))

    def _on_toggle_cycle_dbc(self, checked: bool) -> None:
        if checked:
            self._stop_cycle_raw()
            self.dbc_cycle_btn.setText("停止周期")
            self._cycle_dbc.start(self.dbc_period.value())
        else:
            self._cycle_dbc.stop()
            self.dbc_cycle_btn.setText("周期发送")

    def _stop_cycle_dbc(self) -> None:
        self._cycle_dbc.stop()
        self.dbc_cycle_btn.setChecked(False)
        self.dbc_cycle_btn.setText("周期发送")

    def _on_dbc_period_changed(self, value: int) -> None:
        if self._cycle_dbc.isActive():
            self._cycle_dbc.start(value)
