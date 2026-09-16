"""DVtest 报文解码器。

输入 CANFrame -> 输出该帧所属报文的全部信号值，以及整数/小数合并通道的物理值。
合并通道: V = int_part + frac_part / frac_div (电压 8bit+8bit /256, HSD 电流 4bit+4bit /16)
"""
from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, Optional

from data.dbc_parser import Database, Signal, load_dbc


@dataclass
class DecodedSignal:
    name: str
    raw: int
    phys: float
    text: Optional[str] = None

    @property
    def is_normal(self) -> bool:
        return True


@dataclass
class Channel:
    name: str
    desc: str
    msg: str
    int_sig: str
    frac_sig: str
    frac_div: int
    unit: str
    status_sig: Optional[str] = None

    @property
    def is_voltage(self) -> bool:
        return self.unit == "V"


@dataclass
class StatusDef:
    name: str
    desc: str
    msg: str
    normal: int
    values: Dict[int, str] = field(default_factory=dict)


class Decoder:
    def __init__(self, db: Database, signals_cfg: dict):
        self.db = db
        self.channels: Dict[str, Channel] = {}
        self.statuses: Dict[str, StatusDef] = {}
        self.descriptions: Dict[str, str] = {}
        self._init_from_config(signals_cfg)

    def _init_from_config(self, cfg: dict):
        self.descriptions = {k: v for k, v in cfg.get("descriptions", {}).items()}
        for name, c in cfg.get("conversion", {}).items():
            self.channels[name] = Channel(name=name, **c)
        for name, s in cfg.get("status", {}).items():
            values = {int(k): v for k, v in s.get("values", {}).items()}
            self.statuses[name] = StatusDef(name=name, values=values, **{k: v for k, v in s.items() if k != "values"})

    def decode(self, frame_id: int, data: bytes) -> Optional[dict]:
        msg = self.db.get_message(frame_id)
        if msg is None:
            return None
        return self._decode_message(msg, data)

    def _decode_message(self, msg, data: bytes) -> dict:
        signals = {}
        for sig in msg.signals.values():
            raw = sig.decode_raw(data)
            phys = raw * sig.scale + sig.offset
            signals[sig.name] = DecodedSignal(
                name=sig.name, raw=raw, phys=phys, text=sig.value_text(raw))

        merged = {}
        for name, ch in self.channels.items():
            if ch.msg != msg.name:
                continue
            int_sig = signals[ch.int_sig]
            frac_sig = signals[ch.frac_sig]
            if ch.int_sig == ch.frac_sig:
                value = int_sig.phys
            else:
                value = int_sig.phys + frac_sig.phys / ch.frac_div
            status_raw = signals[ch.status_sig].raw if ch.status_sig in signals else None
            merged[name] = {
                "value": round(value, 3),
                "unit": ch.unit,
                "desc": ch.desc,
                "status": status_raw,
                "status_text": self._status_text(ch.status_sig, status_raw) if ch.status_sig else None,
            }
        return {"signals": signals, "merged": merged, "msg_name": msg.name}

    def _status_text(self, sig_name: Optional[str], raw: Optional[int]) -> Optional[str]:
        if sig_name is None or raw is None:
            return None
        st = self.statuses.get(sig_name)
        if st is None:
            return str(raw)
        return st.values.get(raw, str(raw))

    def is_status_normal(self, sig_name: str, raw: int) -> bool:
        st = self.statuses.get(sig_name)
        if st is None:
            return True
        return raw == st.normal

    def status_def(self, sig_name: str) -> Optional[StatusDef]:
        return self.statuses.get(sig_name)

    @staticmethod
    def load(dbc_path: str | Path, signals_path: str | Path) -> "Decoder":
        db = load_dbc(dbc_path)
        cfg = json.loads(Path(signals_path).read_text(encoding="utf-8"))
        return Decoder(db, cfg)
