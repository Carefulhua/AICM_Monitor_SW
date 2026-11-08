"""MES ATE 协议：commandString 组包与响应解析。

接口 `ATECommandCode(commandString: string) → string`，字段以 ';' 分隔，
业务返回 `OK;` 或 `NG;NG原因;`。

本模块实现两条命令（段 1-7 段结构相同：工单号;SN;工序;;;;）：
    04  测试结果上传：04;DQ2206ZSC0160;SN;TEST-海思拓手动测试工序;;;;时间;项1:值1,项2:值2
        每条最多 7 个检测项，超过则拆成多条 04。
    05  过站：       05;DQ2206ZSC0160;SN;TEST-海思拓手动测试工序;;;;时间;OK
        NG 时：      05;DQ2206ZSC0160;SN;TEST-海思拓手动测试工序;;;;时间;NG;NG项1:值1,NG项2:值2
04 的段 9 为检测项明细；05 的段 9 为整机判定 OK/NG，NG 时段 10 附带 NG 检测项。
"""
from __future__ import annotations

import re
from dataclasses import dataclass

from mes.report import TestItem, TestResult


MAX_ITEMS_PER_COMMAND = 7
# 段 1-7 固定结构：工单号（固定）、序号（=SN）、工序名称，段 4-6 为空；
# 04/05 字面完全相同，仅命令码不同。
WORK_ORDER = "DQ2206ZSC0160"
PROCESS_NAME = "TEST-海思拓手动测试工序"


def _fixed_fields(sn: str) -> str:
    """段 1-7：工单号;序号;工序;;;;（工单号固定，序号取上位机输入的 SN，段 4-6 空）。"""
    return f"{WORK_ORDER};{sn};{PROCESS_NAME};;;;"


def _items_body(items: list[TestItem]) -> str:
    """检测项序列化：name:value，半角冒号/逗号。"""
    return ",".join(f"{it.name}:{it.value:g}" for it in items)


_ENVELOPE_TEXT = re.compile(r">([^<>]+)<")



def build_test_results(result: TestResult) -> list[str]:
    """组装 04 测试结果上传命令（每条最多 7 个检测项，超出拆条）。

    格式：段 1-7 固化，段 8 为测试时间 yyyyMMddHHmmss，段 9 为检测项
    `name:value,...`。无检测项时返回空列表（MES：04 有就传，否则可不传）。
    """
    if not result.sn:
        raise ValueError("04 命令序号(SN)必填")
    if not result.process:
        raise ValueError("04 命令工序名称必填")
    if len(result.start_time) != 14 or not result.start_time.isdigit():
        raise ValueError(f"测试开始时间须为 yyyyMMddHHmmss，实际 {result.start_time!r}")
    if not result.items:
        return []
    return [f"04;{_fixed_fields(result.sn)}{result.start_time};"
            f"{_items_body(result.items[i:i + MAX_ITEMS_PER_COMMAND])}"
            for i in range(0, len(result.items), MAX_ITEMS_PER_COMMAND)]


def build_test_results_05(result: TestResult) -> list[str]:
    """组装 05 过站命令。

    段 1-8 与 04 字面完全相同（工单号/SN/工序/时间），仅命令码为 05；
    段 9 为整机判定 OK/NG。判定 NG 时追加段 10：上位机判为 NG 的检测项。
    """
    if not result.sn:
        raise ValueError("05 命令序号(SN)必填")
    if len(result.start_time) != 14 or not result.start_time.isdigit():
        raise ValueError(f"测试开始时间须为 yyyyMMddHHmmss，实际 {result.start_time!r}")
    head = f"05;{_fixed_fields(result.sn)}{result.start_time}"
    if result.verdict == "OK":
        return [f"{head};OK"]
    ng_items = [it for it in result.items if not it.ok]
    return [f"{head};NG;{_items_body(ng_items)}"]


def verdict_text(result: TestResult) -> str:
    """整机判定文本：合格 PASS，否则 FAIL（供界面显示）。"""
    return "PASS" if result.verdict == "OK" else "FAIL"


@dataclass(frozen=True)
class Reply:
    ok: bool
    reason: str


def parse_response(body: str) -> Reply:
    """从 SOAP 信封（`<ATECommandCodeResult>OK;</ATECommandCodeResult>`）
    或裸字符串中取出业务返回并判定 OK/NG。"""
    match = _ENVELOPE_TEXT.search(body)
    text = (match.group(1) if match else body).strip()
    head, _, rest = text.partition(";")
    if head.strip().upper() == "OK":
        return Reply(True, "")
    return Reply(False, rest.strip().rstrip(";").strip())