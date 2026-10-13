"""MES ATE 协议：commandString 组包与响应解析。

接口 `ATECommandCode(commandString: string) → string`，字段以 ';' 分隔，
业务返回 `OK;` 或 `NG;NG原因;`。当前只实现 04 测试结果命令：
    04;工号;序号;工序名称;资源名称;设备编码;工治具编码;测试开始时间;项1:值1,项2:值2;
每条命令最多 7 个检测项，超出需另发一条 04。
"""
from __future__ import annotations

import re
from dataclasses import dataclass

from mes.report import TestItem, TestResult

MAX_ITEMS_PER_COMMAND = 7

_ENVELOPE_TEXT = re.compile(r">([^<>]+)<")


def _fmt(value: float) -> str:
    return f"{value:g}"


def build_test_results(result: TestResult) -> list[str]:
    """组装 04 上传命令。检测项每条最多 MAX_ITEMS_PER_COMMAND 个，超过拆成多条。

    MES 规定 04「有就传，否则可以不用」，故无检测项时返回空列表（不发命令）。
    """
    if not result.sn:
        raise ValueError("04 命令序号必填")
    if not result.process:
        raise ValueError("04 命令工序名称必填")
    if len(result.start_time) != 14 or not result.start_time.isdigit():
        raise ValueError(f"测试开始时间须为 yyyyMMddHHmmss，实际 {result.start_time!r}")
    return [
        _build_one(result, result.items[i:i + MAX_ITEMS_PER_COMMAND])
        for i in range(0, len(result.items), MAX_ITEMS_PER_COMMAND)
    ]


def _build_one(result: TestResult, items: list[TestItem]) -> str:
    body = result.item_sep.join(f"{it.name}:{_fmt(it.value)}" for it in items)
    return (f"04;{result.operator};{result.sn};{result.process};{result.resource};"
            f"{result.machine};{result.fixture};{result.start_time};{body};")


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