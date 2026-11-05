"""限值判定单测：无负载电压窗口 + MCU 状态位交叉校验。

运行：python tests/test_limits.py
"""
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from data.limits import LED_GREEN, LED_RED, Limits  # noqa: E402


def check(result, ok, led, label):
    assert result.ok is ok, f"{label}: ok={result.ok}, want {ok} ({result.note})"
    assert result.led == led, f"{label}: led={result.led}, want {led} ({result.note})"


def main():
    cfg = Limits.load(ROOT / "config" / "limits.json")

    # AD1/AD2/IGN/TBOX_WP：< 1V 合格（上界开区间），且忽略固件未赋值的状态位
    for name in ("AD1", "AD2", "IGN", "TBOX_WP"):
        assert cfg.has(name), f"{name} 无窗口"
        check(cfg.judge(name, 0.0, False), True, LED_GREEN, f"{name} 0V")
        check(cfg.judge(name, 0.99, False), True, LED_GREEN, f"{name} 0.99V")
        check(cfg.judge(name, 1.0, False), False, LED_RED, f"{name} 1.00V")
        check(cfg.judge(name, 1.01, False), False, LED_RED, f"{name} 1.01V")

    # CAN0_INH：17~21V 合格，含端点
    assert cfg.has("CAN0_INH"), "CAN0_INH 无窗口"
    check(cfg.judge("CAN0_INH", 17.0, False), True, LED_GREEN, "CAN0_INH 17V")
    check(cfg.judge("CAN0_INH", 21.0, False), True, LED_GREEN, "CAN0_INH 21V")
    check(cfg.judge("CAN0_INH", 16.99, False), False, LED_RED, "CAN0_INH 16.99V")
    check(cfg.judge("CAN0_INH", 21.01, False), False, LED_RED, "CAN0_INH 21.01V")

    # 常规通道：状态位与窗口交叉校验规则不变
    check(cfg.judge("VBATT_P", 24.3, True), True, LED_GREEN, "VBATT_P 24.3V/正常")
    check(cfg.judge("VBATT_P", 20.0, False), False, LED_RED, "VBATT_P 20V/异常")
    check(cfg.judge("VBATT_P", 20.0, True), False, LED_RED, "VBATT_P 20V/固件正常")
    check(cfg.judge("VBATT_P", 24.3, False), True, "yellow", "VBATT_P 24.3V/固件异常")

    # 无状态位、仅按窗口判定的通道
    check(cfg.judge("SOC_TEMP", 0.0, None), True, LED_GREEN, "SOC_TEMP 0℃")
    check(cfg.judge("SOC_TEMP", 85.0, None), True, LED_GREEN, "SOC_TEMP 85℃")
    check(cfg.judge("SOC_TEMP", -0.1, None), False, LED_RED, "SOC_TEMP -0.1℃")
    check(cfg.judge("SOC_TEMP", 85.1, None), False, LED_RED, "SOC_TEMP 85.1℃")
    check(cfg.judge("TEMP5152", 45.0, None), True, LED_GREEN, "TEMP5152 45℃")

    print("TEST PASS")


if __name__ == "__main__":
    main()
