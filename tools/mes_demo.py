"""MES 04/05 命令案例演示：JSON 数据 → commandString → 响应判定。

运行：python tools/mes_demo.py
"""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from mes.client import (MesTransportError, UploadPolicy, upload,
                        upload_transit)
from mes.protocol import build_test_results, build_test_results_05, parse_response
from mes.report import TestItem, TestResult

ITEMS = [
    TestItem("VBATT_P", 24.57, 22.0, 26.0),
    TestItem("VBATT_SOC_P", 24.31, 22.0, 26.0),
    TestItem("IGN", 11.10, 12.0, 16.0),
    TestItem("AD1", 3.28, 3.0, 3.6),
    TestItem("AD2", 3.30, 3.0, 3.6),
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


def _ok_result() -> TestResult:
    """整机判定的干净样例。"""
    return TestResult(
        operator="EMP001", sn="SN20261013001", process="Station001",
        resource="Res001", machine="MachineNo", fixture="Fixture001",
        start_time="20261013143025",
        items=[TestItem("VBATT_P", 24.57, 22.0, 26.0),
               TestItem("AD1", 3.28, 3.0, 3.6)],
    )


def main() -> int:
    print("=== 1. 应用内部 JSON（数据模型） ===")
    print(RESULT.to_json())

    print("\n=== 2. 应用内部综合判定 ===")
    ng = [f"{it.name}={it.value:g}" for it in RESULT.items if not it.ok]
    print(f"检测项 {len(RESULT.items)} 个 -> verdict = {RESULT.verdict}，"
          f"不良项 = {', '.join(ng)}")
    assert RESULT.verdict == "NG"

    print("\n=== 3. 04 测试结果命令（9 段，段 9 为检测项） ===")
    cmd_04 = build_test_results(RESULT)[0]
    print(cmd_04)
    assert cmd_04.count(";") == 8 and cmd_04.startswith("04;")

    print("\n=== 4. 05 过站命令（段 9 判定 OK/NG，NG 时段 10 带 NG 项） ===")
    print(build_test_results_05(RESULT)[0])
    ok = _ok_result()
    cmd_05 = build_test_results_05(ok)[0]
    print(cmd_05)
    assert cmd_05.count(";") == 8 and cmd_05.split(";")[8] == "OK"

    print("\n=== 5. 无检测项时 04 不发命令（有就传，否则可不传） ===")
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

    print("\n=== 7. 上传编排：OK/NG 都先 04 再 05；NG 的 05 带 NG 项 ===")
    fast = UploadPolicy(max_retry=3, retry_delay_s=0, sleep=lambda _: None)

    def make_send(log: list[str]):
        def send(cmd: str):
            log.append(cmd)
            return parse_response("OK;")
        return send

    log: list[str] = []
    send = make_send(log)
    upload(ok, send, fast)
    upload_transit(ok, send, fast)
    print(f"OK: 发出 {len(log)} 条 -> " + " | ".join(c.split(';')[0] for c in log))
    assert [c.split(";")[0] for c in log] == ["04", "05"]

    log = []
    send = make_send(log)
    upload(RESULT, send, fast)
    upload_transit(RESULT, send, fast)
    print(f"NG: 发出 {len(log)} 条 -> " + " | ".join(c.split(';')[0] for c in log))
    assert [c.split(";")[0] for c in log] == ["04", "05"]
    print("NG 的 05:", log[-1])

    print("\n=== 8. 网络失败后整组重发 ===")
    calls: list[str] = []
    fails_left = [1]

    def flaky(cmd: str):
        calls.append(cmd)
        if len(calls) == 1 and fails_left[0]:
            fails_left[0] = 0
            raise MesTransportError("connection reset")
        return parse_response("OK;")

    res = upload(ok, flaky, fast)
    print(f"失败1次后重试: kind={res.kind} 实际调用={len(calls)}")
    assert res.kind == "ok" and len(calls) == 2

    print("\nMES 04/05 DEMO PASS")
    return 0


if __name__ == "__main__":
    sys.exit(main())
