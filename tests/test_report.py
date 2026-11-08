"""MES 数据模型单测：JSON 只输出检测项名称/数值 + 最终判定。

运行：python tests/test_report.py
"""
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from mes.protocol import build_test_results, build_test_results_05  # noqa: E402
from mes.report import TestItem, TestResult  # noqa: E402


def _result(items):
    return TestResult(
        operator="EMP001",
        sn="SN20261106001",
        process="DIP-下线",
        resource="Res001",
        machine="MachineNo",
        fixture="Fixture001",
        start_time="20261106143025",
        items=items,
    )


def main():
    items = [
        TestItem("VBATT_P", 24.57, 22.8, 25.2, True),
        TestItem("HSD1", 1.0, normal=True),
        TestItem("IGN", 0.0, normal=False),
    ]
    result = _result(items)

    data = result.to_dict()
    assert set(data) == {"operator", "sn", "process", "resource", "machine",
                         "fixture", "start_time", "items", "verdict"}, data
    assert data["items"] == ["VBATT_P:24.57", "HSD1:1", "IGN:0"], data["items"]
    assert data["verdict"] == "NG", data["verdict"]

    ok_text = _result(items[:2]).to_json()
    ok = json.loads(ok_text)
    assert ok["verdict"] == "OK", ok
    assert all(isinstance(it, str) and it.count(":") == 1 for it in ok["items"]), ok["items"]

    # 04 上传内容：仅整机测试结果，不再携带检测项明细
    # 结构：04;工单号;SN;工序;;;;时间;检测项数据
    # 第9段(索引8)为检测项数据字符串，如 VBATT_P:24.57,HSD1:1,IGN:0
    # 第10段不再存在（不再有 PASS/FAIL）
    cmd = build_test_results(result)[0]
    # 检查段数：应为9段(8个分号)，即 cmd.count(";") == 8
    sep = cmd.count(";")
    assert sep == 8, f"应有8个分号(9段)，实际{sep}"
    # 第9段(索引8)为检测项数据
    body = cmd.split(";")[8]
    assert body == "VBATT_P:24.57,HSD1:1,IGN:0", f"第9段应为检测项数据，实际: {body}"
    assert not cmd.endswith(";FAIL"), cmd
    assert cmd.split(";")[1] == "DQ2206ZSC0160", cmd
    assert cmd.split(";")[2] == "SN20261106001", cmd
    assert cmd.split(";")[3] == "TEST-海思拓手动测试工序", cmd
    # PASS 样例
    ok_cmd = build_test_results(_result(items[:2]))[0]
    ok_body = ok_cmd.split(";")[8]
    assert ok_body == "VBATT_P:24.57,HSD1:1", f"PASS样例第9段应为检测项数据，实际: {ok_body}"

    # 每条 04 最多 7 个检测项，超出拆成多条
    many = [TestItem(f"CH{i}", float(i), normal=True) for i in range(15)]
    cmds = build_test_results(_result(many))
    assert len(cmds) == 3, f"15 项应拆成 3 条，实际 {len(cmds)}"
    assert [len(c.split(";")[8].split(",")) for c in cmds] == [7, 7, 1]
    assert all(c.count(";") == 8 for c in cmds)

    # 05：段 1-8 与 04 字面相同（仅命令码 05），段 9 判定；NG 追加 NG 项
    cmd_05_ok = build_test_results_05(_result(items[:2]))[0]
    assert cmd_05_ok.startswith("05;DQ2206ZSC0160;SN20261106001;TEST-海思拓手动测试工序;;;;"), cmd_05_ok
    assert cmd_05_ok.count(";") == 8 and cmd_05_ok.split(";")[8] == "OK", cmd_05_ok
    cmd_05_ng = build_test_results_05(result)[0]
    assert cmd_05_ng.startswith("05;DQ2206ZSC0160;SN20261106001;TEST-海思拓手动测试工序;;;;"), cmd_05_ng
    assert cmd_05_ng.count(";") == 9, cmd_05_ng
    assert cmd_05_ng.split(";")[8] == "NG", cmd_05_ng
    assert cmd_05_ng.split(";")[9] == "IGN:0", cmd_05_ng

    print("TEST PASS")


if __name__ == "__main__":
    main()
