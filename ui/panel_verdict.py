"""一键判定面板：汇总全部检查项，全 PASS 显示绿框，否则红框 FAIL。"""
from __future__ import annotations

import time

from PyQt5.QtCore import Qt
from PyQt5.QtGui import QBrush, QColor, QFont
from PyQt5.QtWidgets import (QFrame, QHBoxLayout, QLabel, QPushButton,
                             QTreeWidget, QTreeWidgetItem, QVBoxLayout,
                             QWidget)

from data.limits import Limits
from data.model import BusModel
from data.verdict import VerdictReport, collect_verdict
from ui.widgets import BLUE, GREEN, RED, TEXT_DIM, YELLOW

_IDLE_STYLE = ("QFrame#result { background-color: #2b2b2b;"
               " border: 4px solid #555555; border-radius: 10px; }")
_PASS_STYLE = ("QFrame#result { background-color: #142d16;"
               " border: 4px solid #4caf50; border-radius: 10px; }")
_FAIL_STYLE = ("QFrame#result { background-color: #3a1414;"
               " border: 4px solid #e53935; border-radius: 10px; }")

_COLUMNS = ["检查项", "实测/状态", "结果", "说明"]


class VerdictPanel(QWidget):
    def __init__(self, model: BusModel, limits: Limits, parent=None):
        super().__init__(parent)
        self.model = model
        self.limits = limits
        self.report: VerdictReport | None = None
        self._judged_frames: int | None = None
        self._stale = False
        self._base_subtitle = ""

        root = QVBoxLayout(self)
        root.setContentsMargins(10, 10, 10, 10)
        root.setSpacing(10)

        header = QHBoxLayout()
        header.setSpacing(14)

        self.box = QFrame()
        self.box.setObjectName("result")
        self.box.setMinimumHeight(112)
        box_lay = QVBoxLayout(self.box)
        box_lay.setContentsMargins(22, 12, 22, 12)
        box_lay.setSpacing(2)
        self.title = QLabel("未判定")
        self.title.setFont(QFont("Microsoft YaHei", 30, QFont.Bold))
        self.subtitle = QLabel("点击「一键判定」汇总全部检查项")
        self.subtitle.setFont(QFont("Microsoft YaHei", 10))
        box_lay.addWidget(self.title)
        box_lay.addWidget(self.subtitle)
        header.addWidget(self.box, 1)

        self.judge_btn = QPushButton("一键判定")
        self.judge_btn.setFixedSize(180, 64)
        self.judge_btn.setCursor(Qt.PointingHandCursor)
        self.judge_btn.setStyleSheet(
            f"QPushButton {{ background-color: {BLUE}; color: white; border: none;"
            " border-radius: 8px; font-size: 18px; font-weight: bold; }}"
            "QPushButton:hover { background-color: #5aafff; }"
            "QPushButton:pressed { background-color: #3a8eef; }")
        self.judge_btn.clicked.connect(self.on_judge)
        header.addWidget(self.judge_btn)
        root.addLayout(header)

        self.tree = QTreeWidget()
        self.tree.setColumnCount(len(_COLUMNS))
        self.tree.setHeaderLabels(_COLUMNS)
        self.tree.setRootIsDecorated(True)
        self.tree.setAlternatingRowColors(False)
        self.tree.setUniformRowHeights(True)
        self.tree.setStyleSheet(
            "QTreeWidget { background-color: #1e1e1e; color: #cccccc;"
            " border: 1px solid #3a3a3a; font-size: 12px; }"
            "QTreeWidget::item { height: 24px; }"
            "QHeaderView::section { background-color: #2b2b2b; color: #aaaaaa;"
            " border: none; border-bottom: 1px solid #3a3a3a; padding: 5px 6px;"
            " font-weight: bold; }")
        header_view = self.tree.header()
        header_view.setStretchLastSection(True)
        self.tree.setColumnWidth(0, 260)
        self.tree.setColumnWidth(1, 110)
        self.tree.setColumnWidth(2, 80)
        root.addWidget(self.tree, 1)

        self._set_idle()

    # ---- 判定 ----
    def on_judge(self) -> None:
        self.model.refresh()
        self.report = collect_verdict(self.model, self.limits)
        self._judged_frames = self.model.frame_count
        self._stale = False
        self._render(self.report)

    def reset(self) -> None:
        self.report = None
        self._judged_frames = None
        self._stale = False
        self._base_subtitle = ""
        self.tree.clear()
        self._set_idle()
        self.subtitle.setText("点击「一键判定」汇总全部检查项")

    def note_frame_progress(self) -> None:
        """判定后收到新帧时提示结果只是判定时快照。"""
        if self.report is None or self._stale or self._judged_frames is None:
            return
        if self.model.frame_count == self._judged_frames:
            return
        self._stale = True
        self.subtitle.setText(self._base_subtitle + "　|　数据已更新，结果为判定时快照")
        self.subtitle.setStyleSheet(f"color: {YELLOW};")

    # ---- 渲染 ----
    def _set_idle(self) -> None:
        self.box.setStyleSheet(_IDLE_STYLE)
        self.title.setText("未判定")
        self.title.setStyleSheet(f"color: {TEXT_DIM};")
        self.subtitle.setStyleSheet(f"color: {TEXT_DIM};")

    def _render(self, report: VerdictReport) -> None:
        ok = report.ok
        self.box.setStyleSheet(_PASS_STYLE if ok else _FAIL_STYLE)
        self.title.setText("PASS" if ok else "FAIL")
        self.title.setStyleSheet(f"color: {GREEN if ok else RED};")
        stamp = time.strftime("%H:%M:%S", time.localtime(report.timestamp))
        self._base_subtitle = (
            f"{stamp} 判定：共 {report.total} 项，PASS {report.passed}，"
            f"FAIL {report.failed}")
        self.subtitle.setText(self._base_subtitle)
        self.subtitle.setStyleSheet(
            f"color: {GREEN if ok else '#ff8a80'};")

        self.tree.clear()
        for category, items in report.grouped():
            failed = sum(1 for item in items if not item.ok)
            top = QTreeWidgetItem([f"{category}（{failed}/{len(items)} 失败）",
                                   "", "", ""])
            font = top.font(0)
            font.setBold(True)
            top.setFont(0, font)
            top.setForeground(0, QBrush(QColor(YELLOW if failed else "#dddddd")))
            top.setForeground(2, QBrush(QColor(RED if failed else GREEN)))
            top.setBackground(0, QBrush(QColor("#252525")))
            for item in items:
                child = QTreeWidgetItem([item.name, item.measured,
                                         "PASS" if item.ok else "FAIL",
                                         item.detail])
                color = GREEN if item.ok else RED
                child.setForeground(0, QBrush(QColor("#cccccc")))
                child.setForeground(1, QBrush(QColor("#cccccc")))
                child.setForeground(2, QBrush(QColor(color)))
                child.setForeground(3, QBrush(QColor("#9a9a9a")))
                top.addChild(child)
            self.tree.addTopLevelItem(top)
            top.setExpanded(failed > 0)
