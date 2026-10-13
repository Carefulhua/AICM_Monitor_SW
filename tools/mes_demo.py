"""MES 04 测试结果上传命令的案例演示：JSON 数据 → commandString → 响应判定。

运行：python tools/mes_demo.py
"""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from mes.client import MesTransportError, UploadPolicy, upload
from mes.protocol import MAX_ITEMS_PER_COMMAND, build_test_results, parse_response
from mes.report import TestItem, TestResult

ITEMS = [
    TestItem("VBATT_P", 24.57, 22.0, 26.0),
    TestItem("VBATT_SOC_P", 24.31, 22.0, 26.0),
    TestItem("IGN", 11.10, 12.0, 16.0),
    TestItem("AD1", 3.28, 3.0, 3.6),
    TestItem("AD2", 3.30, 3.0, 3.6),
    TestItem("VCC_12V", 12.05, 11.4, 12.6),
    TestItem("VCC_3V3", 3.31, 3.1, 3.5),
    TestItem("VDD_1V25", 1.24, 1.1, 1.4),
    TestItem("DC5V", 5.02, 4.75, 5.25),
    TestItem("DC3V3", 3.30, 3.1, 3.5),
    TestItem("DC17V", 17.02, 16.5, 17.5),
    TestItem("HSD1", 0.0, 0.0, 0.0),
    TestItem("CAN1", 0.0, 0.0, 0.0),
    TestItem("eth0_1", 1.0, 1.0, 1.0),
    TestItem("SOC_TEMP", 42.1, -20.0, 85.0),
]

RESULT = TestResult(
    operator="EMP001",
    sn="SN20261013001",
    process="Station001",
    resource="Res001",
    machine="MachineNo",
    fixture="Fixture001",
    start_time="20261013143025",
    items=ITEMS,
)


def main() -> int:
    print("=== 1. 应用内部 JSON（数据模型） ===")
    print(RESULT.to_json())

    print("\n=== 2. 应用内部综合判定 ===")
    ng = [f"{it.name}={it.value:g}" for it in RESULT.items if not it.ok]
    print(f"检测项 {len(RESULT.items)} 个 -> verdict = {RESULT.verdict}，不良项 = {', '.join(ng)}")
    assert RESULT.verdict == "NG"

    print(f"\n=== 3. 组包（{len(RESULT.items)} 项 > 每条上限 {MAX_ITEMS_PER_COMMAND}，自动拆条） ===")
    commands = build_test_results(RESULT)
    for idx, cmd in enumerate(commands, 1):
        print(f"[{idx}] {cmd}")
        assert cmd.count(";") == 9
        assert cmd.endswith(";")
    expected = -(-len(RESULT.items) // MAX_ITEMS_PER_COMMAND)
    assert len(commands) == expected, f"应拆成 {expected} 条，实际 {len(commands)} 条"
    assert all(c.count(",") == MAX_ITEMS_PER_COMMAND - 1 for c in commands[:-1])
    assert commands[-1].count(",") == len(RESULT.items) % MAX_ITEMS_PER_COMMAND - (1 if len(RESULT.items) % MAX_ITEMS_PER_COMMAND else 0)

    print("\n=== 4. 序号为组 MAC 地址时原样透传（MES 侧映射主 SN） ===")
    RESULT.sn = "A4C138B21E40"
    print(build_test_results(RESULT)[0])
    assert build_test_results(RESULT)[0].split(";")[2] == "A4C138B21E40"
    RESULT.sn = "SN20261013001"

    print("\n=== 5. 无检测项时不发命令（MES：04「有就传，否则可以不用」） ===")
    empty = TestResult(operator="EMP001", sn="SN20261013002", process="Station001",
                       resource="Res001", machine="MachineNo", fixture="Fixture001",
                       start_time="20261013143100")
    assert build_test_results(empty) == []
    print("检测项为空 -> 命令数 0")

    print("\n=== 6. 响应判定 ===")
    cases = [
        ('<ATECommandCodeResult>OK;</ATECommandCodeResult>', True, ""),
        ('<string xmlns="http://mesateapi.com/">OK;</string>', True, ""),
        ("OK;", True, ""),
        ("NG;NG原因;", False, "NG原因"),
        ("NG; MAC地址未找到对应主SN;", False, "MAC地址未找到对应主SN"),
    ]
    for body, want_ok, want_reason in cases:
        reply = parse_response(body)
        print(f"{body[:46]:48} -> ok={reply.ok} reason={reply.reason!r}")
        assert (reply.ok, reply.reason) == (want_ok, want_reason)

    print("\n=== 7. 上传编排策略（顺序发 / NG 即停 / 网络失败整组重发） ===")
    commands = build_test_results(RESULT)
    fast = UploadPolicy(max_retry=3, retry_delay_s=0, sleep=lambda _: None)

    def ok_send(log: list[str]) -> object:
        def send(cmd: str):
            log.append(cmd.split(";")[8][:20])
            return parse_response("OK;")
        return send

    log: list[str] = []
    res = upload(RESULT, ok_send(log), fast)
    print(f"全成功: kind={res.kind} sent={res.sent}/{res.total} 实际调用={len(log)}")
    assert res.kind == "ok" and len(log) == 3

    calls: list[str] = []

    def ng_on_second(cmd: str):
        calls.append(cmd.split(";")[8][:20])
        if len(calls) == 2:
            return parse_response("NG;NG原因;")
        return parse_response("OK;")

    res = upload(RESULT, ng_on_second, fast)
    print(f"第2条NG: kind={res.kind} reason={res.reason!r} sent={res.sent}/{res.total} "
          f"实际调用={len(calls)}")
    assert (res.kind, res.sent, len(calls)) == ("ng", 1, 2), "NG 后不应再发第 3 条"

    calls2: list[str] = []
    fails_left = [1]

    def fail_once(cmd: str):
        calls2.append(cmd.split(";")[8][:20])
        if len(calls2) == 2 and fails_left[0]:
            fails_left[0] = 0
            raise MesTransportError("connection reset")
        return parse_response("OK;")

    res = upload(RESULT, fail_once, fast)
    print(f"网络失败1次: kind={res.kind} sent={res.sent}/{res.total} "
          f"实际调用={len(calls2)} (第2条失败→整组重发)")
    assert (res.kind, len(calls2)) == ("ok", 5), "应为 2 条 + 整组重发 3 条 = 5 次"

    calls3: list[str] = []

    def always_fail(cmd: str):
        calls3.append(cmd)
        raise MesTransportError("timeout")

    res = upload(RESULT, always_fail, fast)
    print(f"持续失败: kind={res.kind} reason={res.reason!r} 实际调用={len(calls3)} "
          f"(首次 + 重试 {fast.max_retry} 次)")
    assert (res.kind, len(calls3)) == ("failed", 4)

    print("\nMES 04 DEMO PASS")
    return 0


if __name__ == "__main__":
    sys.exit(main())