"""自动判定面板：每秒汇总全部检查项，全 PASS 显示绿框，否则红框 FAIL。

判定前必须收到首帧（0x659）且 SPI 状态（SPI_Status）通过后才开始判定；
SPI 未通过时保持等待框。"""
from __future__ import annotations

import time

from PyQt5.QtCore import QTimer
from PyQt5.QtGui import QBrush, QColor, QFont
from PyQt5.QtWidgets import (QFrame, QLabel, QTreeWidget, QTreeWidgetItem,
                             QVBoxLayout, QWidget)

from data.limits import Limits
from data.model import BusModel
from data.verdict import VerdictReport, collect_verdict
from ui.widgets import GREEN, RED, TEXT_DIM, YELLOW

_IDLE_STYLE = ("QFrame#result { background-color: #2b2b2b;"
               " border: 4px solid #555555; border-radius: 10px; }")
_PASS_STYLE = ("QFrame#result { background-color: #142d16;"
               " border: 4px solid #4caf50; border-radius: 10px; }")
_FAIL_STYLE = ("QFrame#result { background-color: #3a1414;"
               " border: 4px solid #e53935; border-radius: 10px; }")

_COLUMNS = ["检查项", "实测/状态", "结果", "说明"]

# 判定开始前需要收到该报文的数据（SOC 发出的首个周期报文 0x659）
FIRST_JUDGE_FRAME_ID = 0x659

# SPI 状态：SPI_Status 判定为 pass 后才进行自动判定
SPI_STATUS_SIGNAL = "SPI_Status"


class VerdictPanel(QWidget):
    REFRESH_MS = 1000

    def __init__(self, model: BusModel, limits: Limits, parent=None):
        super().__init__(parent)
        self.model = model
        self.limits = limits
        self.report: VerdictReport | None = None
        self._judged_started = False
        self._rows: dict[tuple[str, str], QTreeWidgetItem] = {}
        self._groups: dict[str, QTreeWidgetItem] = {}
        self._group_failed: dict[str, int] = {}

        root = QVBoxLayout(self)
        root.setContentsMargins(10, 10, 10, 10)
        root.setSpacing(10)

        self.box = QFrame()
        self.box.setObjectName("result")
        self.box.setMinimumHeight(112)
        box_lay = QVBoxLayout(self.box)
        box_lay.setContentsMargins(22, 12, 22, 12)
        box_lay.setSpacing(2)
        self.title = QLabel("未判定")
        self.title.setFont(QFont("Microsoft YaHei", 30, QFont.Bold))
        self.subtitle = QLabel("等待数据，每秒自动判定")
        self.subtitle.setFont(QFont("Microsoft YaHei", 10))
        box_lay.addWidget(self.title)
        box_lay.addWidget(self.subtitle)
        root.addWidget(self.box)

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

        self.timer = QTimer(self)
        self.timer.setInterval(self.REFRESH_MS)
        self.timer.timeout.connect(self.on_judge)
        self.timer.start()

    # ---- 判定 ----
    def _spi_ok(self) -> bool:
        # SPI 状态（SPI_Status：MCU 端 SPI 监控）不通过时，不进行判定
        return self.model.decoder.is_status_normal(
            "SPI_Status", self.model.raw_of("SPI_Status"))

    def _waiting_for_data(self) -> bool:
        if self.model.frame_count == 0:
            return True
        mst = self.model.messages.get(FIRST_JUDGE_FRAME_ID)
        if mst is None or not mst.seen:
            return True
        if not self._spi_ok():
            return True
        return False

    def on_judge(self) -> None:
        self.model.refresh()
        if self._waiting_for_data():
            self.report = None
            self._clear_tree()
            self._set_idle()
            self.subtitle.setText("等待数据，每秒自动判定")
            return
        self._judged_started = True
        self.report = collect_verdict(self.model, self.limits)
        self._render(self.report)

    def reset(self) -> None:
        self.report = None
        self._judged_started = False
        self._clear_tree()
        self._set_idle()
        self.subtitle.setText("等待数据，每秒自动判定")

    # ---- 渲染 ----
    def _set_idle(self) -> None:
        self.box.setStyleSheet(_IDLE_STYLE)
        self.title.setText("未判定")
        self.title.setStyleSheet(f"color: {TEXT_DIM};")
        self.subtitle.setStyleSheet(f"color: {TEXT_DIM};")

    def _clear_tree(self) -> None:
        self.tree.clear()
        self._rows.clear()
        self._groups.clear()
        self._group_failed.clear()

    def _render(self, report: VerdictReport) -> None:
        ok = report.ok
        self.box.setStyleSheet(_PASS_STYLE if ok else _FAIL_STYLE)
        self.title.setText("PASS" if ok else "FAIL")
        self.title.setStyleSheet(f"color: {GREEN if ok else RED};")
        stamp = time.strftime("%H:%M:%S", time.localtime(report.timestamp))
        self.subtitle.setText(
            f"{stamp} 自动判定：共 {report.total} 项，PASS {report.passed}，"
            f"FAIL {report.failed}")
        self.subtitle.setStyleSheet(
            f"color: {GREEN if ok else '#ff8a80'};")
        self._sync_tree(report)

    def _sync_tree(self, report: VerdictReport) -> None:
        """原地刷新，避免每秒重建导致滚动位置和展开状态丢失。"""
        grouped = report.grouped()
        keys = {(category, item.name)
                for category, items in grouped for item in items}
        if self._rows and set(self._rows) != keys:
            self._clear_tree()

        for category, items in grouped:
            failed = sum(1 for item in items if not item.ok)
            top = self._groups.get(category)
            first = top is None
            if first:
                top = QTreeWidgetItem()
                font = top.font(0)
                font.setBold(True)
                top.setFont(0, font)
                top.setBackground(0, QBrush(QColor("#252525")))
                self._groups[category] = top
                self.tree.addTopLevelItem(top)

            top.setText(0, f"{category}（{failed}/{len(items)} 失败）")
            top.setForeground(0, QBrush(QColor(YELLOW if failed else "#dddddd")))
            top.setForeground(2, QBrush(QColor(RED if failed else GREEN)))

            prev_failed = self._group_failed.get(category, 0)
            self._group_failed[category] = failed
            if first:
                top.setExpanded(failed > 0)
            elif failed > prev_failed:
                top.setExpanded(True)

            for item in items:
                key = (category, item.name)
                child = self._rows.get(key)
                if child is None:
                    child = QTreeWidgetItem()
                    self._rows[key] = child
                    top.addChild(child)
                color = GREEN if item.ok else RED
                child.setText(0, item.name)
                child.setText(1, item.measured)
                child.setText(2, "PASS" if item.ok else "FAIL")
                child.setText(3, item.detail)
                child.setForeground(0, QBrush(QColor("#cccccc")))
                child.setForeground(1, QBrush(QColor("#cccccc")))
                child.setForeground(2, QBrush(QColor(color)))
                child.setForeground(3, QBrush(QColor("#9a9a9a")))
