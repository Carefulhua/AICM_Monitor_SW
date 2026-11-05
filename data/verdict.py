"""一键判定：汇总电压/温度限值、状态位、报文接收三类检查。

判定口径（2026-11 与工艺确认）：
    - 电压/温度按 config/limits.json 的窗口判定，红灯即 FAIL；
    - signals.json 里所有健康状态位必须收到且为 normal，未收到算 FAIL；
    - DBC 报文必须全部收到且未超时，未收到算 FAIL；
    - 0x680 回读的测试开关和固件未赋值的状态位不参与判定；
    - signals.json 标记 unconnected 的 HSD 通道，开路（3）放行；
      其对应测试芯片的开路/错误状态（6/8）仅在未接通道确实开路时放行。
只有全部检查项通过，汇总结果才是 PASS。
"""
from __future__ import annotations

import time
from dataclasses import dataclass

from data.limits import LED_RED, Limits
from data.model import BusModel

# 0x680 DVtest_Switch 是上位机下发的测试开关回读，属于操作状态而非健康状态
COMMAND_STATUSES = frozenset({
    "DV_Switch",
    "HSD_U1000_Error_Switch",
    "HSD_U1000_Stanby_Switch",
    "HSD_U1001_Error_Switch",
    "HSD_U1001_Stanby_Switch",
    "LSD_P322_Switch",
    "LSD_P323_Switch",
    "LSD_P324_Switch",
    "LSD_P325_Switch",
    "LSD_TEST_Switch",
})

# 状态位归属的报文 -> 界面分组
MSG_CATEGORY = {
    "MCUTempData": "电压状态位",
    "SocTXStatus": "相机",
    "SocTXStatus1": "相机",
    "SocTXStatus2": "IO/通信",
    "SocTXStatus3": "IO/通信",
    "McuLSDStatus": "低边/控制器",
    "Mcu_USV_Status": "RS232/RS485/SPI",
    "McuHSDStatus": "高边驱动",
    "McuCanStatus": "CAN",
    "HSD_PORT_Status": "高边驱动",
}

CATEGORY_ORDER = [
    "电压/温度", "电压状态位", "相机", "IO/通信", "低边/控制器",
    "高边驱动", "CAN", "RS232/RS485/SPI", "其他状态", "报文接收",
]

# HSD 固件枚举：3=开路；U100x 测试状态机 6=开路、8=错误
HSD_OPEN_LOAD = 3
HSD_TEST_OPEN_OR_ERROR = frozenset({6, 8})

# 判定需要收到的报文由 expected_message_names() 从 signals.json 推导

@dataclass(frozen=True)
class CheckItem:
    category: str
    name: str
    measured: str
    ok: bool
    detail: str = ""


@dataclass
class VerdictReport:
    items: list[CheckItem]
    timestamp: float
    frame_count: int

    @property
    def total(self) -> int:
        return len(self.items)

    @property
    def passed(self) -> int:
        return sum(1 for item in self.items if item.ok)

    @property
    def failed(self) -> int:
        return self.total - self.passed

    @property
    def ok(self) -> bool:
        return bool(self.items) and self.failed == 0

    def grouped(self) -> list[tuple[str, list[CheckItem]]]:
        buckets: dict[str, list[CheckItem]] = {}
        for item in self.items:
            buckets.setdefault(item.category, []).append(item)
        order = {name: i for i, name in enumerate(CATEGORY_ORDER)}
        return sorted(buckets.items(), key=lambda kv: order.get(kv[0], len(order)))


def expected_message_names(decoder) -> set[str]:
    """判定需要收到的报文：DUT 周期上报的报文。

    排除 Vector 占位报文、0x680 DVtest_Switch（上位机下发的开关回读）
    和 CAN1~4TEST（外部节点测试帧）。
    """
    return {
        msg.name for msg in decoder.db.messages.values()
        if not msg.name.startswith("VECTOR__")
        and msg.name != "DVtest_Switch"
        and not (msg.name.startswith("CAN") and msg.name.endswith("TEST"))
    }


def collect_verdict(model: BusModel, limits: Limits) -> VerdictReport:
    items: list[CheckItem] = []

    for name in limits.names():
        st = model.channels.get(name)
        if st is None:
            items.append(CheckItem("电压/温度", name, "--", False,
                                   "配置存在但数据模型无此通道"))
            continue
        value = st.value
        verdict = limits.judge(name, value, st.normal)
        measured = f"{value:.2f} {st.unit}".strip() if value is not None else "--"
        items.append(CheckItem("电压/温度", name, measured,
                               verdict.led != LED_RED, verdict.note))

    ignored = limits.ignored_status_signals()
    for sig_name, status_def in model.decoder.statuses.items():
        if sig_name in COMMAND_STATUSES or sig_name in ignored:
            continue
        category = MSG_CATEGORY.get(status_def.msg, "其他状态")
        raw = model.raw_of(sig_name)
        if raw is None:
            items.append(CheckItem(category, sig_name, "--", False,
                                   "未收到该状态位"))
            continue
        ok = model.decoder.is_status_normal(sig_name, raw)
        detail = status_def.desc
        if status_def.unconnected and raw == HSD_OPEN_LOAD:
            ok = True
            detail = "未接负载，按未接通道放行（开路）"
        elif (not ok and status_def.excused_by
              and raw in HSD_TEST_OPEN_OR_ERROR
              and any(model.raw_of(dep) == HSD_OPEN_LOAD
                      for dep in status_def.excused_by)):
            ok = True
            detail = "由未接通道开路引起的测试状态，已放行"
        text = model.decoder.status_text(sig_name, raw) or str(raw)
        items.append(CheckItem(category, sig_name, text, ok, detail))

    now = time.time()
    expected = expected_message_names(model.decoder)
    for msg in model.messages.values():
        if msg.name not in expected:
            continue
        if not msg.seen:
            items.append(CheckItem("报文接收", msg.name, "未收到", False,
                                   "该报文从未收到"))
            continue
        age = max(0.0, now - msg.last_ts)
        items.append(CheckItem("报文接收", msg.name, f"{age:.1f}s 前",
                               not msg.timeout,
                               f"超时阈值 {model.timeout_s:.1f}s"
                               + ("，已超时" if msg.timeout else "")))

    return VerdictReport(items=items, timestamp=now,
                         frame_count=model.frame_count)
