"""MES 测试结果数据模型：应用内部用结构化对象描述一次测试，commandString 由它派生。

传输层只认 commandString 字符串，检测项增删改因此不会波及协议层与传输层。
"""
from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field


@dataclass(frozen=True)
class TestItem:
    """单个检测项：实测值 + 判定依据。

    判定优先级：normal（上位机按 signals.json 的 status 判定结果）> 上下限 > 默认合格。
    上下限目前暂无数据源 —— DBC 中信号的 min/max 是量程（如 [0|255]），不是产品限值，
    实际限值需由工艺/测试规范给定。
    """
    name: str
    value: float
    lower: float | None = None
    upper: float | None = None
    normal: bool | None = None

    @property
    def ok(self) -> bool:
        if self.normal is not None:
            return self.normal
        if self.lower is not None and self.value < self.lower:
            return False
        if self.upper is not None and self.value > self.upper:
            return False
        return True


@dataclass
class TestResult:
    """一次测试的完整结果，字段对应 MES 04 命令的各段。

    序号既可能是主工单条码，也可能是组的 MAC 地址（MES 侧自行映射到主 SN），
    因此这里不对 sn 做格式校验，原样传给 MES。
    """
    operator: str          # 工号
    sn: str                # 序号（主工单条码 或 组 MAC 地址）
    process: str           # 工序名称
    resource: str          # 资源名称
    machine: str           # 设备编码
    fixture: str           # 工治具编码
    start_time: str        # 测试开始时间 yyyyMMddHHmmss
    items: list[TestItem] = field(default_factory=list)
    item_sep: str = ","    # 检测项之间用英文逗号（MES 文档明确）

    @property
    def verdict(self) -> str:
        return "OK" if all(it.ok for it in self.items) else "NG"

    def to_dict(self) -> dict[str, object]:
        data: dict[str, object] = asdict(self)
        data["verdict"] = self.verdict
        return data

    def to_json(self, indent: int = 2) -> str:
        return json.dumps(self.to_dict(), ensure_ascii=False, indent=indent)