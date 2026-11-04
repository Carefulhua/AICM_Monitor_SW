"""限值交叉校验：用固件窗口（config/limits.json）复算一遍电压合格性，与 MCU 状态位比对。

MCU 状态位是单 bit，漏判（固件未赋值）或误判时上位机无法察觉。这里用收到的数值
按同一窗口复算，得出三态：
    一致          → 采信，绿/红
    数值超限      → 强制 NG（不等 MCU 的「正常」位）
    MCU 说异常但数值合格 → 判合格，界面黄灯提示疑似固件漏判
    MCU 无状态位  → 仅按窗口判定：窗口内绿、超窗口红（不看 MCU 位）

窗口可选字段（仅工艺补充的通道使用）：
    upper_exclusive  上界开区间，值必须严格小于 upper
    ignore_status    固件状态位未赋值，判定只看窗口
"""
from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

LED_GREEN = "green"
LED_RED = "red"
LED_YELLOW = "yellow"

_EPS = 1e-6


@dataclass(frozen=True)
class Verdict:
    ok: bool | None
    led: str
    note: str


class Limits:
    def __init__(self, data: dict | None = None):
        self._limits: dict[str, dict] = (data or {}).get("limits", {}) or {}

    @classmethod
    def load(cls, path: str | Path) -> "Limits":
        p = Path(path)
        if not p.exists():
            return cls({})
        return cls(json.loads(p.read_text(encoding="utf-8")))

    def has(self, channel: str) -> bool:
        return channel in self._limits

    def judge(self, channel: str, value: float | None,
              mcu_normal: bool | None) -> Verdict:
        lim = self._limits.get(channel)
        if lim is None:
            if mcu_normal is None:
                return Verdict(None, LED_RED, "无窗口且 MCU 无状态位")
            return Verdict(mcu_normal, LED_GREEN if mcu_normal else LED_RED, "仅 MCU 状态位")
        if value is None:
            return Verdict(None, LED_RED, "无数值，无法按窗口判定")
        ignore_status = bool(lim.get("ignore_status"))
        if ignore_status:
            mcu_normal = None
        below_upper = (value < lim["upper"] if lim.get("upper_exclusive")
                       else value <= lim["upper"] + _EPS)
        in_range = lim["lower"] - _EPS <= value and below_upper
        upper_txt = (f"<{lim['upper']}" if lim.get("upper_exclusive")
                     else str(lim["upper"]))
        window = f"{lim['lower']}~{upper_txt}{lim.get('unit', '')}"
        if mcu_normal is None:
            source = "固件状态位未赋值，已忽略" if ignore_status else "无 MCU 状态位"
            return Verdict(in_range, LED_GREEN if in_range else LED_RED,
                           f"{source}，按窗口 {window} 判定")
        if mcu_normal == in_range:
            return Verdict(in_range, LED_GREEN if in_range else LED_RED,
                           f"MCU 与窗口 {window} 一致")
        if in_range:
            return Verdict(True, LED_YELLOW, f"MCU 报异常但数值在窗口 {window} 内，判合格")
        return Verdict(False, LED_RED, f"MCU 报正常但数值超窗口 {window}，强制 NG")