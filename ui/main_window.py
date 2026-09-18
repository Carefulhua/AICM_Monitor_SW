"""主窗口：连接控制 + 标签页面板 + 状态栏。"""
from __future__ import annotations

import time
from collections import deque

from PyQt5.QtCore import Qt, QTimer
from PyQt5.QtGui import QGuiApplication
from PyQt5.QtWidgets import (QComboBox, QDialog, QDialogButtonBox, QFileDialog,
                             QLabel, QMainWindow, QMessageBox, QPushButton,
                             QTabWidget, QVBoxLayout, QWidget)

from can_driver.simulator import DVTestSimulator
from can_driver.zlg_can import ADAPTERS, AUTO_DEVICES, ZLGCANDevice
from data.decoder import Decoder
from data.model import BusModel
from data.storage import DataStorage
from ui.panel_camera import CameraPanel
from ui.panel_curves import CurvesPanel
from ui.panel_io import IOPanel
from ui.panel_log import LogPanel
from ui.panel_overview import OverviewPanel
from ui.panel_send import SendPanel
from ui.widgets import BLUE, DARK, GREEN, RED, TEXT_DIM, YELLOW

MAX_LOG_PER_TICK = 200
LOG_RENDER_DIV = 5  # 报文日志渲染降频: 每 5 个刷新周期(100ms)渲染一次 = 500ms


def _style_btn(btn: QPushButton, color: str):
    btn.setMinimumSize(110, 34)
    btn.setStyleSheet(
        f"QPushButton {{ background-color: {color}; color: white; border: none;"
        f" border-radius: 5px; font-size: 13px; font-weight: bold; }}"
        f"QPushButton:hover {{ background-color: {color}; }}"
        f"QPushButton:disabled {{ background-color: #555; }}")


class MainWindow(QMainWindow):
    def __init__(self, decoder: Decoder, model: BusModel, cfg: dict):
        super().__init__()
        self.decoder = decoder
        self.model = model
        self.cfg = cfg
        self.source = None
        self.storage = DataStorage(cfg.get("database", "data/dvtest.db"))
        self._refresh_count = 0
        self._t_start = None
        self._dropped = 0
        self._log_queue: deque = deque(maxlen=4000)
        self._log_visible = False

        self.setWindowTitle("AICM-NT4K DV监控界面")
        avail = QGuiApplication.primaryScreen().availableGeometry()
        w = min(cfg.get("window", {}).get("width", 1500), avail.width() - 80)
        h = min(cfg.get("window", {}).get("height", 900), avail.height() - 80)
        self.setGeometry(80, 80, w, h)
        self.setMinimumSize(700, 480)
        self.statusBar().setSizeGripEnabled(True)
        self.setStyleSheet(
            f"QMainWindow {{ background-color: {DARK}; }}"
            "QToolBar { background-color: #2b2b2b; border: none; spacing: 6px; }"
            "QTabWidget::pane { border: 1px solid #3a3a3a; }"
            "QTabBar::tab { background: #2b2b2b; color: #bbbbbb;"
            " padding: 8px 16px; }"
            "QTabBar::tab:selected { background: #3d3d3d; color: white; }"
            "QMessageBox { background-color: #2b2b2b; }"
            "QMessageBox QLabel { color: #cccccc; font-size: 13px; }"
            "QMessageBox QPushButton { background-color: #4a9eff; color: white;"
            " border: none; border-radius: 4px; padding: 6px 18px;"
            " font-size: 13px; font-weight: bold; min-width: 60px; }"
            "QMessageBox QPushButton:hover { background-color: #5aafff; }"
            "QFileDialog { background-color: #2b2b2b; color: #cccccc; }"
            "QFileDialog QLabel { color: #cccccc; }"
            "QFileDialog QLineEdit { background-color: #3a3a3a; color: #cccccc;"
            " border: 1px solid #555; padding: 4px; }"
        )
        self._build_ui()
        self._init_timers()

    def _build_ui(self):
        tb = self.addToolBar("控制")
        tb.setMovable(False)

        self.connect_btn = QPushButton("连接")
        _style_btn(self.connect_btn, BLUE)
        self.connect_btn.clicked.connect(self.on_connect)
        tb.addWidget(self.connect_btn)

        self.start_btn = QPushButton("启动")
        _style_btn(self.start_btn, GREEN)
        self.start_btn.setEnabled(False)
        self.start_btn.clicked.connect(self.on_start)
        tb.addWidget(self.start_btn)

        self.test_mode_btn = QPushButton("测试模式: OFF")
        self.test_mode_btn.setMinimumSize(140, 34)
        self.test_mode_btn.setStyleSheet(
            "QPushButton { background-color: #555; color: white; border: 2px solid #888;"
            " border-radius: 5px; font-size: 14px; font-weight: bold; }"
            "QPushButton:hover { background-color: #666; }"
            "QPushButton:disabled { background-color: #444; }")
        self.test_mode_btn.setCheckable(True)
        self.test_mode_btn.toggled.connect(self.on_test_mode)
        tb.addWidget(self.test_mode_btn)

        tb.addWidget(QLabel("  数据源"))
        self.source_cb = QComboBox()
        self.source_cb.addItem("CAN 硬件")
        self.source_cb.addItem("仿真 (无硬件)")
        self.source_cb.setCurrentIndex(1 if self.cfg.get("simulation") else 0)
        tb.addWidget(self.source_cb)

        tb.addWidget(QLabel("  适配器"))
        self.adapter_cb = QComboBox()
        for label, _device in ADAPTERS:
            self.adapter_cb.addItem(label)
        cur_device = self.cfg.get("zlg", {}).get("device")
        self.adapter_cb.setCurrentIndex(
            next((i for i, (_label, d) in enumerate(ADAPTERS) if d == cur_device), 0))
        self.adapter_cb.setEnabled(self.source_cb.currentIndex() == 0)
        self.source_cb.currentIndexChanged.connect(self._on_source_changed)
        tb.addWidget(self.adapter_cb)

        self.export_btn = QPushButton("导出CSV")
        _style_btn(self.export_btn, "#ff9800")
        self.export_btn.clicked.connect(self.on_export)
        tb.addWidget(self.export_btn)

        self.clear_btn = QPushButton("清空")
        _style_btn(self.clear_btn, "#607d8b")
        self.clear_btn.clicked.connect(self.on_clear_all)
        tb.addWidget(self.clear_btn)

        self.tabs = QTabWidget()
        self.overview = OverviewPanel(self.model)
        self.camera = CameraPanel(self.model)
        self.io = IOPanel(self.model)
        self.curves = CurvesPanel(self.model)
        self.log = LogPanel(self.model)
        self.send = SendPanel(self.decoder.db, self._send_can)
        self.tabs.addTab(self.overview, "总览")
        self.tabs.addTab(self.camera, "相机")
        self.tabs.addTab(self.io, "IO 状态")
        self.tabs.addTab(self.curves, "曲线")
        self.tabs.addTab(self.log, "报文")
        self.tabs.addTab(self.send, "发送")
        self.setCentralWidget(self.tabs)

        self.status = QLabel("未连接")
        self.status.setStyleSheet(f"color: {TEXT_DIM}; padding: 4px;")
        self.statusBar().addWidget(self.status, 1)

    def _init_timers(self):
        self.refresh_timer = QTimer(self)
        self.refresh_timer.timeout.connect(self.on_refresh)
        self.refresh_timer.start(100)

        self.test_mode_timer = QTimer(self)
        self.test_mode_timer.timeout.connect(self._on_test_mode_tick)

    def _on_source_changed(self, index: int):
        self.adapter_cb.setEnabled(index == 0)

    # ---- 连接/启动 ----
    def on_connect(self):
        if self.source is not None:
            if self.test_mode_btn.isChecked():
                QMessageBox.warning(self, "测试模式未关闭",
                                    "请先关闭测试模式再断开连接。")
                return
            self.source.stop_receiving()
            self.source.close()
            self.source = None
            self._log_visible = False
            self.connect_btn.setText("连接")
            self.connect_btn.setEnabled(True)
            self.start_btn.setEnabled(False)
            self.status.setText("未连接")
            return

        use_hw = self.source_cb.currentIndex() == 0
        if use_hw:
            dev = ZLGCANDevice(self.cfg.get("zlg", {}))
            device = ADAPTERS[self.adapter_cb.currentIndex()][1]
            if not dev.connect(device):
                QMessageBox.warning(self, "硬件连接失败",
                                    "CAN 适配器打开失败，已切换到仿真模式。\n"
                                    f"尝试的适配器：{device or ' / '.join(AUTO_DEVICES)}\n"
                                    "请确认：适配器 USB 已插好、驱动已安装、"
                                    "下拉框选的型号与实际硬件一致。")
                dev = DVTestSimulator(self.decoder.db)
                dev.open()
                self.source_cb.setCurrentIndex(1)
        elif self.source_cb.currentIndex() == 1:
            dev = DVTestSimulator(self.decoder.db)
            dev.open()
        self.source = dev
        self.connect_btn.setText("断开")
        self.start_btn.setEnabled(True)
        self.status.setText(
            "已连接 (仿真)" if self.source_cb.currentIndex() == 1 else "已连接 (硬件)")

    def on_start(self):
        if self.source is None:
            return
        if self.start_btn.text() == "启动":
            self.model.frame_count = 0
            self.model.recorded = 0
            self._t_start = time.time()
            self.curves.clear_all()
            self.log.clear_rows()
            self._log_visible = True
            self.source.start_receiving(self.on_frame)
            self.start_btn.setText("停止")
            _style_btn(self.start_btn, RED)
        else:
            self.source.stop_receiving()
            self._log_visible = False
            self._t_start = None
            self.start_btn.setText("启动")
            _style_btn(self.start_btn, GREEN)

    def on_frame(self, frame):
        # 回调运行在仿真/采集线程：只做纯数据层操作，Qt 与 SQLite 留到主线程 on_refresh 处理
        self.model.record(frame.can_id, frame.data, frame.timestamp)
        self._log_queue.append(frame)

    def on_refresh(self):
        self.model.refresh()
        self.overview.refresh()
        self.camera.refresh()
        self.io.refresh()
        if self._t_start is not None:
            rel = time.time() - self._t_start
            self.curves.push(rel)
        # 主线程排空帧队列：落库全部帧，报文日志降频渲染
        batch = []
        while self._log_queue:
            f = self._log_queue.popleft()
            msg = self.decoder.db.get_message(f.can_id)
            name = msg.name if msg else ""
            self.storage.add_frame(f.timestamp, f.can_id, name, f.data)
            batch.append(f)
        if self._log_visible and batch and self._refresh_count % LOG_RENDER_DIV == 0:
            self._dropped += max(0, len(batch) - MAX_LOG_PER_TICK)
            self.log.add_frames(batch[-MAX_LOG_PER_TICK:])
        elif self._log_visible:
            self._dropped += len(batch)
        self._refresh_count += 1
        if self._refresh_count % 5 == 0:
            now = time.time()
            for name, st in self.model.channels.items():
                if st.value is not None:
                    self.storage.add_sample(now, name, st.value, st.unit)
            self.storage.flush()
        self._update_status()

    def _update_status(self):
        timeouts = [m.name for m in self.model.messages.values() if m.timeout]
        n_alarm = sum(1 for st in self.model.channels.values()
                      if st.valid and not st.normal)
        if self.source_cb.currentIndex() == 1:
            src = "仿真"
        else:
            model = getattr(self.source, "config", {}).get("device", "")
            src = f"硬件 {model}" if model else "硬件"
        lost = self.model.frame_count - self.model.recorded
        dropped = f" | 日志丢弃: {self._dropped}" if self._dropped else ""
        self.status.setText(
            f"数据源: {src} | 帧: {self.model.frame_count} | 未解析: {lost}"
            f" | 报文超时: {len(timeouts)}"
            + (f" ({', '.join(timeouts)})" if timeouts else "")
            + f" | 异常通道: {n_alarm}"
            + dropped)

    # ---- 发送面板回调 ----
    def _send_can(self, can_id: int, data: bytes) -> bool:
        if self.source is None:
            return False
        return bool(self.source.send(can_id, data))

    # ---- DV 产线模式 ----
    # 0x680 DVtest_Switch 报文编码: byte0=DV_Switch, byte1=HSD_Mask, 其余默认0
    DV_SWITCH_CAN_ID = 0x680
    TEST_MODE_PERIOD_MS = 1000

    def on_test_mode(self, checked: bool):
        if self.source is None:
            self.test_mode_timer.stop()
            self.test_mode_btn.setChecked(False)
            return
        if checked:
            self._send_test_mode_frame()
            self.test_mode_timer.start(self.TEST_MODE_PERIOD_MS)
        else:
            self.test_mode_timer.stop()
            self.source.send(self.DV_SWITCH_CAN_ID, bytes(8))
        self.test_mode_btn.setText("测试模式: ON" if checked else "测试模式: OFF")
        self.connect_btn.setEnabled(not checked)
        self.test_mode_btn.setStyleSheet(
            "QPushButton { background-color: #e53935; color: white; border: 2px solid #ff6659;"
            " border-radius: 5px; font-size: 14px; font-weight: bold; }"
            "QPushButton:hover { background-color: #f44336; }"
            if checked else
            "QPushButton { background-color: #555; color: white; border: 2px solid #888;"
            " border-radius: 5px; font-size: 14px; font-weight: bold; }"
            "QPushButton:hover { background-color: #666; }")

    def _on_test_mode_tick(self):
        if self.source is None:
            self.test_mode_timer.stop()
            return
        self._send_test_mode_frame()

    def _send_test_mode_frame(self):
        data = bytearray(8)
        data[0] = 0x01
        data[1] = 0x01
        self.source.send(self.DV_SWITCH_CAN_ID, bytes(data))

    # ---- 按钮 ----
    def on_export(self):
        dlg = ExportDialog(self._t_start, self.model.frame_count, self)
        if dlg.exec_() != QDialog.Accepted:
            return
        seconds = dlg.selected_seconds()
        if seconds is not None and self._t_start is not None:
            cutoff = time.time() - seconds
            self.storage.flush()
            self.storage.trim_before(cutoff)
        path, _ = QFileDialog.getSaveFileName(
            self, "导出CSV", "dvtest", "CSV Files (*.csv)")
        if path:
            self.storage.export_csv(path)
            QMessageBox.information(self, "导出完成",
                                    f"已导出:\n{path}_signals.csv\n{path}_frames.csv")

    def on_clear_all(self):
        self.curves.clear_all()
        self.log.clear_rows()
        self.model.frame_count = 0
        self.model.recorded = 0
        self._dropped = 0
        self._t_start = time.time()
        self.storage.clear_all()

    def _stop_all(self):
        if self.source is not None:
            self.source.stop_receiving()

    def closeEvent(self, event):
        self._stop_all()
        if self.source is not None:
            self.source.close()
        self.storage.close()
        event.accept()


# ---- 对话框样式 ----
_DIALOG_QSS = (
    "QDialog { background-color: #2b2b2b; }"
    "QLabel  { color: #cccccc; font-size: 13px; }"
    "QPushButton { background-color: #4a9eff; color: white; border: none;"
    " border-radius: 4px; padding: 6px 18px; font-size: 13px; font-weight: bold; }"
    "QPushButton:hover { background-color: #5aafff; }"
    "QPushButton[flat=\"true\"] { background-color: #555; }"
    "QComboBox { background-color: #3a3a3a; color: #cccccc; border: 1px solid #555;"
    " padding: 4px; font-size: 13px; }"
    "QComboBox QAbstractItemView { background-color: #3a3a3a; color: #cccccc;"
    " selection-background-color: #4a9eff; }"
)


class ExportDialog(QDialog):
    def __init__(self, t_start: float | None, frame_count: int, parent=None):
        super().__init__(parent)
        self.setWindowTitle("导出 CSV")
        self.setMinimumWidth(340)
        self.setStyleSheet(_DIALOG_QSS)

        lay = QVBoxLayout(self)
        lay.setSpacing(12)

        info = "开始录制后已停止" if t_start is None else \
            f"已录制 {time.time() - t_start:.0f} 秒 / {frame_count} 帧"
        lay.addWidget(QLabel(info))

        lay.addWidget(QLabel("选择导出数据范围:"))

        self._combo = QComboBox()
        self._combo.addItem("全部数据", None)
        self._combo.addItem("最近 30 秒", 30)
        self._combo.addItem("最近 60 秒", 60)
        self._combo.addItem("最近 120 秒", 120)
        self._combo.addItem("最近 300 秒 (5 分钟)", 300)
        lay.addWidget(self._combo)

        lay.addWidget(QLabel("选择保存路径后即可导出。"))

        btns = QDialogButtonBox(
            QDialogButtonBox.Ok | QDialogButtonBox.Cancel, parent=self)
        btns.accepted.connect(self.accept)
        btns.rejected.connect(self.reject)
        btns.button(QDialogButtonBox.Ok).setText("确认导出")
        btns.button(QDialogButtonBox.Cancel).setText("取消")
        btns.button(QDialogButtonBox.Ok).setStyleSheet(
            "QPushButton { background-color: #4caf50; color: white; border: none;"
            " border-radius: 4px; padding: 6px 18px; font-size: 13px; font-weight: bold; }"
            "QPushButton:hover { background-color: #5cbf60; }")
        btns.button(QDialogButtonBox.Cancel).setStyleSheet(
            "QPushButton { background-color: #555; color: #ccc; border: none;"
            " border-radius: 4px; padding: 6px 18px; font-size: 13px; }"
            "QPushButton:hover { background-color: #666; }")
        lay.addWidget(btns)

    def selected_seconds(self) -> int | None:
        return self._combo.currentData()
