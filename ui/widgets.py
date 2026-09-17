"""通用 UI 控件：LED 指示灯、状态卡片、报文健康指示。"""
from __future__ import annotations

from PyQt5.QtCore import Qt
from PyQt5.QtGui import QColor, QFont, QPainter
from PyQt5.QtWidgets import (QFrame, QGridLayout, QHBoxLayout, QLabel,
                             QSizePolicy, QVBoxLayout, QWidget)

DARK = "#1e1e1e"
CARD_BG = "#2b2b2b"
BORDER = "#3a3a3a"
TEXT_DIM = "#9a9a9a"
GREEN = "#4caf50"
RED = "#e53935"
YELLOW = "#fdd835"
GRAY = "#555555"
BLUE = "#4a9eff"


def _elide_label(text: str, font_size: int = 10) -> QLabel:
    label = QLabel(text)
    label.setFont(QFont("Microsoft YaHei", font_size))
    label.setStyleSheet(f"color: {TEXT_DIM};")
    return label


class Led(QWidget):
    """圆形 LED，set_state(ok: bool, text: str)。"""

    def __init__(self, title: str = "", radius: int = 7, parent=None):
        super().__init__(parent)
        self.title = title
        self.radius = radius
        self._ok: bool | None = None
        self.setFixedSize(radius * 2 + 2, radius * 2 + 2)
        self.setToolTip(title)

    def set_state(self, ok: bool):
        self._ok = ok
        self.update()

    def paintEvent(self, event):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        if self._ok is None:
            color = QColor(GRAY)
        else:
            color = QColor(GREEN if self._ok else RED)
        p.setBrush(color)
        p.setPen(QColor("#000000"))
        p.drawEllipse(1, 1, self.radius * 2, self.radius * 2)


class ValueCard(QFrame):
    """带 LED 状态与数值的卡片。"""

    def __init__(self, title: str, unit: str = "", parent=None):
        super().__init__(parent)
        self.setObjectName("card")
        self.setStyleSheet(
            f"#card {{ background-color: {CARD_BG}; border: 1px solid {BORDER};"
            f" border-radius: 6px; }}")
        self.setMinimumSize(96, 56)

        lay = QVBoxLayout(self)
        lay.setContentsMargins(10, 6, 10, 6)
        lay.setSpacing(2)

        top = QHBoxLayout()
        self.title_label = QLabel(title)
        self.title_label.setFont(QFont("Microsoft YaHei", 9))
        self.title_label.setStyleSheet(f"color: {TEXT_DIM};")
        self.led = Led(title=title, radius=5)
        top.addWidget(self.title_label)
        top.addStretch()
        top.addWidget(self.led)
        lay.addLayout(top)

        val_lay = QHBoxLayout()
        self.value_label = QLabel("--.-")
        self.value_label.setFont(QFont("Microsoft YaHei", 15, QFont.Bold))
        self.value_label.setStyleSheet(f"color: {BLUE};")
        self.unit_label = QLabel(unit)
        self.unit_label.setFont(QFont("Microsoft YaHei", 9))
        self.unit_label.setStyleSheet(f"color: {TEXT_DIM};")
        val_lay.addWidget(self.value_label)
        val_lay.addWidget(self.unit_label)
        val_lay.addStretch()
        lay.addLayout(val_lay)

    def set_value(self, value: float | None, ok: bool = True):
        self.value_label.setText(f"{value:.2f}" if value is not None else "--.-")
        self.led.set_state(ok)
        color = BLUE if ok else RED
        self.value_label.setStyleSheet(f"color: {color};")

    def set_led(self, ok: bool | None):
        if ok is None:
            self.led.set_state(ok)
        else:
            self.led.set_state(ok)


class LedCell(QWidget):
    """带标签的 LED 单元格（相机矩阵、IO 状态用）。

    with_value=True 时额外显示一列状态文字。
    """

    def __init__(self, title: str, desc: str = "", with_value: bool = False, parent=None):
        super().__init__(parent)
        self.setToolTip(f"{title}\n{desc}" if desc else title)
        lay = QHBoxLayout(self)
        lay.setContentsMargins(4, 2, 4, 2)
        lay.setSpacing(6)
        self.led = Led(title=title)
        self.label = QLabel(title)
        self.label.setFont(QFont("Microsoft YaHei", 8))
        self.label.setStyleSheet(f"color: {TEXT_DIM};")
        # 用 Preferred 而非 Ignored：Ignored 会让 sizeHint 不参与布局，
        # 网格宽度紧张时 label 被压缩到 0 宽，文字标签彻底不可见
        self.label.setSizePolicy(QSizePolicy.Preferred, QSizePolicy.Preferred)
        self.label.setMinimumWidth(0)
        lay.addWidget(self.led)
        lay.addWidget(self.label, 1)
        self.value_label: QLabel | None = None
        if with_value:
            self.value_label = QLabel("--")
            self.value_label.setFont(QFont("Microsoft YaHei", 8))
            self.value_label.setStyleSheet(f"color: {TEXT_DIM};")
            lay.addWidget(self.value_label)
        lay.addStretch()

    def set_state(self, ok: bool | None, text: str | None = None):
        self.led.set_state(ok)
        if text is not None and self.value_label is not None:
            self.value_label.setText(text)
            color = TEXT_DIM if ok is None else (GREEN if ok else RED)
            self.value_label.setStyleSheet(f"color: {color};")


class StatusGroup(QFrame):
    """一组状态 LED：grid 布局，标题可选。"""

    def __init__(self, title: str, cols: int = 4, parent=None):
        super().__init__(parent)
        self.setObjectName("grp")
        self.setStyleSheet(
            f"#grp {{ background-color: {CARD_BG}; border: 1px solid {BORDER};"
            f" border-radius: 6px; }}")
        lay = QVBoxLayout(self)
        lay.setContentsMargins(10, 8, 10, 8)
        lay.setSpacing(6)
        if title:
            t = QLabel(title)
            t.setFont(QFont("Microsoft YaHei", 10, QFont.Bold))
            t.setStyleSheet(f"color: #dddddd;")
            lay.addWidget(t)
        self.grid = QGridLayout()
        self.grid.setSpacing(6)
        lay.addLayout(self.grid)
        self._cells: dict[str, LedCell] = {}
        self._cols = cols

    def add_cell(self, key: str, label: str, desc: str = "", with_value: bool = False):
        cell = LedCell(label, desc, with_value)
        idx = len(self._cells)
        self.grid.addWidget(cell, idx // self._cols, idx % self._cols, Qt.AlignLeft)
        self._cells[key] = cell
        if idx % self._cols == self._cols - 1:
            for c in range(self._cols):
                self.grid.setColumnStretch(c, 1)

    def update_led(self, key: str, ok: bool | None, text: str | None = None):
        cell = self._cells.get(key)
        if cell:
            cell.set_state(ok, text)


class CounterCard(QFrame):
    """错误计数/统计卡片。"""

    def __init__(self, title: str, parent=None):
        super().__init__(parent)
        self.setObjectName("cnt")
        self.setStyleSheet(
            f"#cnt {{ background-color: {CARD_BG}; border: 1px solid {BORDER};"
            f" border-radius: 6px; }}")
        lay = QHBoxLayout(self)
        lay.setContentsMargins(8, 5, 8, 5)
        self.label = QLabel(title)
        self.label.setFont(QFont("Microsoft YaHei", 9))
        self.label.setStyleSheet(f"color: {TEXT_DIM};")
        self.label.setSizePolicy(QSizePolicy.Ignored, QSizePolicy.Preferred)
        self.label.setMinimumWidth(0)
        self.value = QLabel("0")
        self.value.setFont(QFont("Consolas", 11, QFont.Bold))
        self.value.setStyleSheet(f"color: {YELLOW};")
        lay.addWidget(self.label, 1)
        lay.addWidget(self.value)

    def set_value(self, v: int | str):
        self.value.setText(str(v))
