"""自动判定汇总逻辑单测：限值 + 状态位 + 报文接收。

运行：python tests/test_verdict.py
"""
import json
import sys
import time
from pathlib import Path
from types import SimpleNamespace

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from data.decoder import Decoder  # noqa: E402
from data.limits import Limits  # noqa: E402
from data.verdict import COMMAND_STATUSES, collect_verdict, expected_message_names  # noqa: E402


class FakeModel:
    """只实现 collect_verdict 需要的接口，避免依赖 Qt 和真实收帧。"""

    def __init__(self, decoder, limits_cfg):
        self.decoder = decoder
        self.timeout_s = 0.3
        self.frame_count = 100
        self.channels = {}
        for name, lim in limits_cfg.items():
            mid = (lim["lower"] + lim["upper"]) / 2
            self.channels[name] = SimpleNamespace(
                value=mid, normal=True, unit=lim.get("unit", ""),
                desc=name)
        ignored = {lim["status_sig"] for lim in limits_cfg.values()
                   if lim.get("ignore_status") and lim.get("status_sig")}
        self.raw = {}
        for sig, sd in decoder.statuses.items():
            # 被忽略的状态位故意给异常值，确认它们不参与判定
            self.raw[sig] = 0 if (sig in ignored or sig in COMMAND_STATUSES) else sd.normal
        now = time.time()
        self.messages = {
            fid: SimpleNamespace(name=msg.name, seen=True, timeout=False,
                                 last_ts=now)
            for fid, msg in decoder.db.messages.items()
            if not msg.name.startswith("VECTOR__")
        }

    def raw_of(self, sig):
        return self.raw.get(sig)


def main():
    decoder = Decoder.load(ROOT / "dbc" / "DVtest.dbc",
                           ROOT / "config" / "signals.json")
    limits = Limits.load(ROOT / "config" / "limits.json")
    limits_cfg = json.loads(
        (ROOT / "config" / "limits.json").read_text(encoding="utf-8"))["limits"]
    model = FakeModel(decoder, limits_cfg)

    report = collect_verdict(model, limits)
    skipped = {sig for sig, sd in decoder.statuses.items() if sd.verdict_skip}
    expected = (len(limits_cfg)
                + len(decoder.statuses) - len(COMMAND_STATUSES)
                - len(limits.ignored_status_signals())
                - len(skipped)
                + len(expected_message_names(decoder)))
    assert report.total == expected, f"total={report.total}, want {expected}"
    assert report.ok, f"应全部 PASS，实际失败 {report.failed}：" + ", ".join(
        i.name for i in report.items if not i.ok)
    assert report.failed == 0 and report.passed == report.total

    # 命令回读、固件未赋值状态位不得出现在检查项里
    names = {i.name for i in report.items}
    for sig in COMMAND_STATUSES:
        assert sig not in names, f"{sig} 不应参与判定"
    for sig in limits.ignored_status_signals():
        assert sig not in names, f"{sig} 不应参与判定"

    # 以太网暂时只实现 eth0_1/0_7/0_8/1_1，其余通道不参与判定
    assert skipped == {f"eth0_{i}" for i in (2, 3, 4, 5, 6, 9)}, skipped
    for sig in skipped:
        assert sig not in names, f"{sig} 未实现，不应参与判定"
    for sig in ("eth0_1", "eth0_7", "eth0_8", "eth1_1"):
        assert sig in names, f"{sig} 应参与判定"

    # 已实现的以太网通道异常 -> FAIL
    model.raw["eth0_7"] = 0
    assert not collect_verdict(model, limits).ok
    model.raw["eth0_7"] = 1

    # 未实现的以太网通道异常 -> 不影响判定
    model.raw["eth0_2"] = 0
    assert collect_verdict(model, limits).ok
    model.raw["eth0_2"] = 1

    # 单个状态位异常 -> FAIL
    model.raw["Cam0Linklock"] = 0
    report = collect_verdict(model, limits)
    assert not report.ok
    assert any(i.name == "Cam0Linklock" and not i.ok for i in report.items)
    model.raw["Cam0Linklock"] = 1

    # HSD 状态值以固件 HSD_Status_t 枚举为准：2=过载 3=开路 4=对VS短路
    assert decoder.status_text("HSD_Status_P230", 3) == "开路"
    assert decoder.status_text("HSD_Status_P230", 2) == "过载"

    # U1000/U1001 是诊断状态机状态而非健康位：启动/运行/换通道均正常，错误(8)异常
    for raw in (0, 1, 2):
        assert decoder.is_status_normal("U1000_Test_Status", raw), raw
    assert not decoder.is_status_normal("U1000_Test_Status", 8)
    model.raw["U1000_Test_Status"] = 0
    assert collect_verdict(model, limits).ok
    model.raw["U1000_Test_Status"] = 8
    assert not collect_verdict(model, limits).ok

    # 未接负载放行：P230 开路 -> PASS；U1000 的错误(8)由 P230 开路解释 -> PASS
    model.raw["HSD_Status_P230"] = 3
    report = collect_verdict(model, limits)
    assert report.ok, [i.name for i in report.items if not i.ok]
    item = next(i for i in report.items if i.name == "HSD_Status_P230")
    assert item.ok and "放行" in item.detail
    item = next(i for i in report.items if i.name == "U1000_Test_Status")
    assert item.ok and "放行" in item.detail

    # 未接通道不在此芯片上时，错误(8)仍判 FAIL
    model.raw["HSD_Status_P230"] = 0
    assert not collect_verdict(model, limits).ok

    # 未接通道过载同样不放行
    model.raw["HSD_Status_P230"] = 2
    model.raw["U1000_Test_Status"] = 0
    assert not collect_verdict(model, limits).ok

    # U1001 只由 P234~P236 的开路解释
    model.raw["HSD_Status_P230"] = 0
    model.raw["HSD_Status_P234"] = 3
    model.raw["U1001_Test_Status"] = 8
    assert collect_verdict(model, limits).ok
    model.raw["U1001_Test_Status"] = 0
    model.raw["HSD_Status_P234"] = 0

    # 状态位未收到 -> FAIL
    model.raw.pop("Cam0Linklock")
    report = collect_verdict(model, limits)
    assert any(i.name == "Cam0Linklock" and i.measured == "--"
               and not i.ok for i in report.items)

    # 报文超时 -> FAIL
    model.messages[0x650].timeout = True
    report = collect_verdict(model, limits)
    assert not report.ok
    assert any(i.category == "报文接收" and i.name == "MCUVoltageData1"
               and not i.ok for i in report.items)

    # 报文从未收到 -> FAIL
    model.messages[0x651].seen = False
    report = collect_verdict(model, limits)
    assert any(i.category == "报文接收" and i.name == "MCUVoltageData2"
               and i.measured == "未收到" and not i.ok for i in report.items)

    print("TEST PASS")


if __name__ == "__main__":
    main()
