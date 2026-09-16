"""总线数据模型：跨报文组装通道状态 + 报文超时/帧统计。

电压值在 0x650~0x654，状态位在 0x655(MCUTempData)，此处统一融合。
CAN 接收线程只调用 record()，UI 主线程定时 refresh() 拉取快照。
"""
from __future__ import annotations

import time
from dataclasses import dataclass
from typing import Dict, Optional

from data.decoder import Decoder


@dataclass
class ChannelState:
    name: str
    desc: str
    value: Optional[float] = None
    unit: str = ""
    status: Optional[int] = None
    status_text: Optional[str] = None
    normal: bool = True

    @property
    def valid(self) -> bool:
        return self.value is not None


@dataclass
class MsgState:
    frame_id: int
    name: str
    last_ts: float = 0.0
    timeout: bool = False

    @property
    def seen(self) -> bool:
        return self.last_ts > 0


class BusModel:
    def __init__(self, decoder: Decoder, cycle_ms: int = 100, timeout_factor: int = 3):
        self.decoder = decoder
        self.cycle_ms = cycle_ms
        self.timeout_s = cycle_ms * timeout_factor / 1000.0
        self.channels: Dict[str, ChannelState] = {}
        for name, ch in decoder.channels.items():
            self.channels[name] = ChannelState(name=name, desc=ch.desc, unit=ch.unit)
        self.messages: Dict[int, MsgState] = {}
        for fid, msg in decoder.db.messages.items():
            self.messages[fid] = MsgState(frame_id=fid, name=msg.name)
        # 报文ID -> {信号名: 原始值}
        self.msg_raw: Dict[int, Dict[str, int]] = {fid: {} for fid in decoder.db.messages}
        self.frame_count = 0
        self.recorded = 0

    def record(self, frame_id: int, data: bytes, ts: float) -> None:
        self.frame_count += 1
        decoded = self.decoder.decode(frame_id, data)
        if decoded is None:
            return
        self.recorded += 1
        self.messages[frame_id].last_ts = ts
        raw_map = self.msg_raw[frame_id]
        raw_map.clear()
        for name, sig in decoded["signals"].items():
            raw_map[name] = sig.raw

    def raw_of(self, signal_name: str) -> Optional[int]:
        for raw_map in self.msg_raw.values():
            if signal_name in raw_map:
                return raw_map[signal_name]
        return None

    def refresh(self, now: Optional[float] = None) -> None:
        now = now if now is not None else time.time()
        for mst in self.messages.values():
            mst.timeout = mst.seen and (now - mst.last_ts) > self.timeout_s
        for name, ch in self.decoder.channels.items():
            st = self.channels[name]
            int_raw = self.raw_of(ch.int_sig)
            frac_raw = self.raw_of(ch.frac_sig)
            if int_raw is None or frac_raw is None:
                st.value = None
                continue
            if ch.int_sig == ch.frac_sig:
                st.value = round(int_raw, 3)
            else:
                st.value = round(int_raw + frac_raw / ch.frac_div, 3)
            if ch.status_sig:
                raw = self.raw_of(ch.status_sig)
                st.status = raw
                st.status_text = self.decoder._status_text(ch.status_sig, raw)
                st.normal = self.decoder.is_status_normal(ch.status_sig, raw) if raw is not None else True
            else:
                st.status, st.status_text, st.normal = 0, None, True