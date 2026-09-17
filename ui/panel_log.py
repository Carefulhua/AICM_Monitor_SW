"""报文日志面板：实时报文列表（ID/名称/数据/解析值）+ 超时高亮。"""
from __future__ import annotations

from PyQt5.QtCore import Qt
from PyQt5.QtGui import QColor, QFont
from PyQt5.QtWidgets import (QHBoxLayout, QHeaderView, QLabel, QPushButton,
                             QTableWidget, QTableWidgetItem, QVBoxLayout, QWidget)

from typing import TYPE_CHECKING

from data.model import BusModel
from ui.widgets import BLUE, RED, TEXT_DIM, YELLOW

if TYPE_CHECKING:
    from can_driver.zlg_can import CANFrame

MAX_ROWS = 500


class LogPanel(QWidget):
    def __init__(self, model: BusModel, parent=None):
        super().__init__(parent)
        self.model = model
        lay = QVBoxLayout(self)
        lay.setContentsMargins(8, 8, 8, 8)

        top = QHBoxLayout()
        top.addWidget(QLabel(f"报文实时日志（显示最近 {MAX_ROWS} 帧）"))
        top.addStretch()
        self.pause_btn = QPushButton("暂停")
        self.pause_btn.setCheckable(True)
        top.addWidget(self.pause_btn)
        self.clear_btn = QPushButton("清空")
        top.addWidget(self.clear_btn)
        lay.addLayout(top)

        self.table = QTableWidget(0, 5)
        self.table.setHorizontalHeaderLabels(["时间", "ID", "报文", "数据(hex)", "解析值"])
        self.table.setStyleSheet(
            "QTableWidget { background-color: #1e1e1e; color: #cccccc;"
            " alternate-background-color: #232323; gridline-color: #3a3a3a;"
            " selection-background-color: #3d3d3d; selection-color: #ffffff; }"
            "QHeaderView::section { background-color: #2b2b2b; color: #bbbbbb;"
            " border: none; border-bottom: 1px solid #3a3a3a; padding: 4px; }"
            "QScrollBar:vertical { background: #1e1e1e; width: 10px; }"
            "QScrollBar::handle:vertical { background: #3d3d3d; border-radius: 5px;"
            " min-height: 20px; }"
            "QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical { height: 0; }")
        hdr = self.table.horizontalHeader()
        # 固定列宽而非 ResizeToContents: 后者每次 setItem 整表重算列宽, 500行下 ~2.2s/tick
        fixed_widths = (70, 90, 150, 150, 320)
        for col, w in enumerate(fixed_widths):
            hdr.setSectionResizeMode(col, QHeaderView.Fixed)
            self.table.setColumnWidth(col, w)
        self.table.verticalHeader().setVisible(False)
        self.table.setEditTriggers(QTableWidget.NoEditTriggers)
        font = QFont("Consolas", 9)
        self.table.setFont(font)
        lay.addWidget(self.table)

        self.clear_btn.clicked.connect(self.clear_rows)
        self._rows = 0
        self._ch_by_msg: dict[str, list] = {}
        for ch in self.model.decoder.channels.values():
            self._ch_by_msg.setdefault(ch.msg, []).append(ch)

    def add_frames(self, frames: list["CANFrame"]):
        """批量渲染一 tick 的报文：一次 setRowCount 裁剪/扩容 + 逐行 setItem +
        一次 scrollToBottom。逐帧 insertRow/removeRow 在高帧率下是 O(n²) 卡顿源。"""
        if self.pause_btn.isChecked() or not frames:
            return
        existing = self.table.rowCount()
        n = min(len(frames), MAX_ROWS)
        start = existing
        if existing + n > MAX_ROWS:
            start = existing - (existing + n - MAX_ROWS)
        if start + n != existing:
            self.table.setRowCount(start + n)
        row = start
        for f in frames[:n]:
            frame_id = f.can_id
            data = f.data
            ts = f.timestamp
            msg = self.model.decoder.db.get_message(frame_id)
            name = msg.name if msg else "?"
            summary = self._summarize(frame_id, msg, data)
            items = [
                f"{ts - int(ts):.3f}",
                f"0x{frame_id:X}",
                name,
                data.hex().upper(),
                summary,
            ]
            timed_out = bool(self.model.messages.get(frame_id)
                             and self.model.messages[frame_id].timeout)
            for col, text in enumerate(items):
                item = QTableWidgetItem(text)
                if col == 4:
                    item.setForeground(QColor(BLUE))
                if timed_out:
                    item.setForeground(QColor(RED))
                self.table.setItem(row, col, item)
            row += 1
            self._rows += 1
        self.table.scrollToBottom()

    def _summarize(self, frame_id: int, msg, data: bytes):
        if msg is None:
            return ""
        parts = []
        raw_map = self.model.msg_raw.get(frame_id, {})
        for ch in self._ch_by_msg.get(msg.name, ()):
            int_raw = raw_map.get(ch.int_sig)
            frac_raw = raw_map.get(ch.frac_sig)
            if int_raw is not None and frac_raw is not None:
                if ch.int_sig == ch.frac_sig:
                    value = round(int_raw, 2)
                else:
                    value = round(int_raw + frac_raw / ch.frac_div, 2)
                parts.append(f"{ch.name}={value:.2f}{ch.unit}")
        return "  ".join(parts)

    def clear_rows(self):
        self.table.setRowCount(0)
        self._rows = 0