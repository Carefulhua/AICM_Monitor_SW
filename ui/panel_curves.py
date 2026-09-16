"""曲线面板：电压/温度/CPU负载 实时曲线（多选通道，滚动窗口）。"""
from __future__ import annotations

from PyQt5.QtWidgets import (QCheckBox, QGridLayout, QHBoxLayout, QLabel,
                             QVBoxLayout, QWidget)
import pyqtgraph as pg

# pyqtgraph 默认 foreground 是深色 (d≈0.3)，深色背景下轴文字/刻度不可见
pg.setConfigOption("foreground", "#cccccc")
from data.model import BusModel
from ui.widgets import DARK

VOLTAGE_PRESET = ["VBATT_P", "VCC_12V", "DC17V", "DC5V", "DC3V3", "VDD_1V25", "SYS_VIN_SV"]
ROLL = 400


class CurvePlot(QWidget):
    def __init__(self, title: str, unit: str, channel_names: list[str], parent=None):
        super().__init__(parent)
        lay = QVBoxLayout(self)
        lay.setContentsMargins(4, 4, 4, 4)
        self.plot = pg.PlotWidget()
        self.plot.setBackground(DARK)
        self.plot.setMinimumHeight(120)
        pi = self.plot.getPlotItem()
        pi.showGrid(x=True, y=True, alpha=0.3)
        pi.setLabel("bottom", "相对时间", units="s")
        pi.setLabel("left", title, units=unit)
        self.title = title
        lay.addWidget(self.plot)

        # 标题行
        title_row = QHBoxLayout()
        title_lbl = QLabel(title)
        title_lbl.setStyleSheet("color: #dddddd; font-weight: bold;")
        title_row.addWidget(title_lbl)
        title_row.addStretch()
        lay.addLayout(title_row)

        # 勾选通道按每行 12 个换行排列
        cfg_grid = QGridLayout()
        self.checks: dict[str, QCheckBox] = {}
        for i, name in enumerate(channel_names):
            cb = QCheckBox(name)
            if title == "电压":
                cb.setChecked(name in VOLTAGE_PRESET)
            elif title == "板温":
                cb.setChecked(name in ("SOC_TEMP", "TEMP5152"))
            elif title == "SOC温度":
                cb.setChecked(name in ("TempCpu", "TempGpu"))
            elif title == "CPU负载":
                cb.setChecked(name in ("CPU0_Load", "CPU1_Load"))
            else:
                cb.setChecked(False)
            cb.toggled.connect(self._rebuild)
            self.checks[name] = cb
            cfg_grid.addWidget(cb, i // 12, i % 12)
        lay.addLayout(cfg_grid)

        self.curves: dict[str, pg.PlotDataItem] = {}
        self.data_x: dict[str, list] = {}
        self.data_y: dict[str, list] = {}
        colors = ["#4ecdc4", "#ff6b6b", "#4a9eff", "#ffe66d", "#a78bfa",
                  "#f97316", "#22c55e", "#e879f9", "#94a3b8", "#facc15",
                  "#38bdf8", "#fb7185", "#84cc16"]
        self.colors = colors
        self._rebuild()

    def _rebuild(self):
        selected = [n for n, cb in self.checks.items() if cb.isChecked()]
        for n, cur in list(self.curves.items()):
            if n not in selected:
                self.plot.removeItem(cur)
                self.curves.pop(n, None)
        for n in selected:
            if n not in self.curves:
                self.data_x[n] = []
                self.data_y[n] = []
                ci = self.colors[len(self.curves) % len(self.colors)]
                self.curves[n] = self.plot.plot(pen=pg.mkPen(ci, width=1.5))

    def set_checked(self, names: list[str], checked: bool):
        for n in names:
            if n in self.checks:
                self.checks[n].setChecked(checked)

    def push(self, rel_time: float, get_value):
        for n in self.curves:
            v = get_value(n)
            if v is None:
                continue
            self.data_x[n].append(rel_time)
            self.data_y[n].append(v)
            if len(self.data_x[n]) > ROLL:
                self.data_x[n] = self.data_x[n][-ROLL:]
                self.data_y[n] = self.data_y[n][-ROLL:]
        for n, cur in self.curves.items():
            if cur.xData is None or len(self.data_x[n]) != len(cur.xData):
                cur.setData(self.data_x[n], self.data_y[n])

    def clear_all(self):
        for n in list(self.curves):
            self.data_x[n] = []
            self.data_y[n] = []
            self.curves[n].setData([], [])


class CurvesPanel(QWidget):
    """曲线面板：3 行布局 — 电压(满宽) + 板温/SOC温度(并列) + CPU负载(满宽)。"""
    def __init__(self, model: BusModel, parent=None):
        super().__init__(parent)
        self.model = model
        layout = QVBoxLayout(self)
        layout.setContentsMargins(8, 8, 8, 8)
        layout.setSpacing(8)

        dch = model.decoder.channels

        # ── 第一行: 电压曲线 (满宽) ───────────────────────────
        vnames = [n for n in model.channels if model.channels[n].unit == "V"]
        self.volt_plot = CurvePlot("电压", "V", vnames)
        layout.addWidget(self.volt_plot, 3)  # stretch=3

        # ── 第二行: 板温 + SOC温度 (并列) ─────────────────────
        row2 = QHBoxLayout()
        row2.setSpacing(8)
        tnames = [n for n in model.channels if model.channels[n].unit == "℃"
                  and dch[n].msg == "MCUTempData"]
        self.temp_plot = CurvePlot("板温", "℃", tnames)
        row2.addWidget(self.temp_plot)

        soc_tnames = [n for n in model.channels if model.channels[n].unit == "℃"
                      and dch[n].msg == "SocTXStatus3"]
        self.soc_temp_plot = CurvePlot("SOC温度", "℃", soc_tnames)
        row2.addWidget(self.soc_temp_plot)

        row2_widget = QWidget()
        row2_widget.setLayout(row2)
        layout.addWidget(row2_widget, 2)  # stretch=2

        # ── 第三行: CPU 负载 (满宽) ──────────────────────────
        cpu_names = [n for n in model.channels if model.channels[n].unit == "%"]
        self.cpu_plot = CurvePlot("CPU负载", "%", cpu_names)
        layout.addWidget(self.cpu_plot, 1)  # stretch=1

    def push(self, rel_time: float):
        self.volt_plot.push(rel_time, lambda n: self.model.channels[n].value)
        self.temp_plot.push(rel_time, lambda n: self.model.channels[n].value)
        self.soc_temp_plot.push(rel_time, lambda n: self.model.channels[n].value)
        self.cpu_plot.push(rel_time, lambda n: self.model.channels[n].value)

    def clear_all(self):
        for p in (self.volt_plot, self.temp_plot, self.soc_temp_plot, self.cpu_plot):
            p.clear_all()
