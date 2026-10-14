"""从 MCU 固件源码生成 config/limits.json（电压合格窗口限值）。

限值唯一来源：DV_CAN.c 的 Generate_ADC_CANMsg()，形如
    if (adcInfo[7].physicValue >= 11.4f && adcInfo[7].physicValue <= 12.64f)
        {dv_adc_ai_status.VCC12V_STATUS = 1;}  //VCC_12V_AI
固件改窗口后重跑本脚本即可，避免上位机限值与固件漂移。

用法:
    python tools/gen_limits.py [DV_CAN.c 路径]
输出:
    config/limits.json
"""
from __future__ import annotations

import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SIGNALS = ROOT / "config" / "signals.json"
OUT = ROOT / "config" / "limits.json"

WIN_SOURCE = Path(
    r"D:\AICM-SW-package\MCU\tc397_platform_T4000_1009_V2"
    r"\tc397_platform_T4000\Components\DVTEST\DV_CAN.c")
WSL_SOURCE = Path(
    "/mnt/d/AICM-SW-package/MCU/tc397_platform_T4000_1009_V2"
    "/tc397_platform_T4000/Components/DVTEST/DV_CAN.c")

WINDOW_RE = re.compile(
    r"if\s*\(\s*adcInfo\[(\d+)\]\.physicValue\s*>=\s*([0-9.]+)f\s*&&\s*"
    r"adcInfo\[\d+\]\.physicValue\s*<=\s*([0-9.]+)f\s*\)\s*\{\s*"
    r"dv_adc_ai_status\.(\w+)_STATUS\s*=\s*1;")

# 固件不给状态位的测温项，限值由工艺提供（-50~150℃），不来自 DV_CAN.c
MANUAL_LIMITS = {
    "SOC_TEMP": (-50.0, 150.0),
    "TEMP5152": (-50.0, 150.0),
    "TempCpu": (-50.0, 150.0),
    "TempGpu": (-50.0, 150.0),
}


def default_source() -> Path:
    for p in (WIN_SOURCE, WSL_SOURCE):
        if p.exists():
            return p
    raise SystemExit(
        "找不到 DV_CAN.c，请把固件路径作为参数传入：python tools/gen_limits.py <DV_CAN.c>")


def main() -> int:
    src = Path(sys.argv[1]) if len(sys.argv) > 1 else default_source()
    text = src.read_text(encoding="utf-8", errors="replace")
    conv = json.loads(SIGNALS.read_text(encoding="utf-8"))["conversion"]
    by_norm = {n.replace("_", "").upper(): n for n in conv}

    limits: dict[str, dict] = {}
    unmatched: list[str] = []
    for idx, lo, hi, status_field in WINDOW_RE.findall(text):
        channel = by_norm.get(status_field.replace("_", "").upper())
        if channel is None:
            unmatched.append(status_field)
            continue
        limits[channel] = {
            "lower": float(lo),
            "upper": float(hi),
            "unit": conv[channel].get("unit", ""),
            "status_sig": conv[channel].get("status_sig", ""),
        }

    if unmatched:
        raise SystemExit("以下状态字段在 signals.json 里找不到对应通道，请先核对："
                         + ", ".join(unmatched))
    if not limits:
        raise SystemExit(f"未从 {src} 解析出任何窗口，正则是否与固件版本匹配？")

    for name, (lo, hi) in MANUAL_LIMITS.items():
        if name not in conv:
            raise SystemExit(f"MANUAL_LIMITS 里的 {name} 在 signals.json 中不存在")
        limits[name] = {
            "lower": lo,
            "upper": hi,
            "unit": conv[name].get("unit", ""),
            "status_sig": conv[name].get("status_sig", ""),
            "source": "工艺",
        }

    covered = {c["status_sig"] for c in limits.values()}
    no_window = sorted(n for n, c in conv.items()
                       if c.get("status_sig") and c["status_sig"] not in covered)

    OUT.write_text(json.dumps({
        "_source": f"{src.name} Generate_ADC_CANMsg() 电压合格窗口"
                   f" + MANUAL_LIMITS（工艺）",
        "_generator": "tools/gen_limits.py",
        "limits": dict(sorted(limits.items())),
    }, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    print(f"已写入 {OUT.relative_to(ROOT)}：{len(limits)} 路限值"
          f"（固件 {len(limits) - len(MANUAL_LIMITS)} + 工艺 {len(MANUAL_LIMITS)}）")
    for name, lim in sorted(limits.items()):
        print(f"  {name:<14} {lim['lower']} ~ {lim['upper']} {lim['unit']}")
    print(f"固件未设窗口（有状态信号但无合格窗口）的通道 {len(no_window)} 路："
          + ", ".join(no_window))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())