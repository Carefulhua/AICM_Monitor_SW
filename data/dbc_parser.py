"""DBC 文件解析器。

支持标准 DBC 语法子集：
- BU_ / BO_ / SG_ / VAL_ / BA_("GenMsgCycleTime") / CM_ SG_
- Intel(Motorola) 字节序、有符号/无符号信号
- VAL_ 枚举值文本映射

DBC 注释文本可能为 GBK 编码（Windows 导出），自动探测编码。
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, List, Optional


@dataclass
class Signal:
    name: str
    start_bit: int
    length: int
    byte_order: str  # 'Intel' | 'Motorola'
    is_signed: bool
    scale: float
    offset: float
    minimum: Optional[float] = None
    maximum: Optional[float] = None
    unit: str = ""
    receivers: List[str] = field(default_factory=list)
    values: Dict[int, str] = field(default_factory=dict)
    comment: str = ""

    def decode_raw(self, data: bytes) -> int:
        """从报文数据提取原始整数值。"""
        raw = _extract_bits(data, self.start_bit, self.length, self.byte_order)
        if self.is_signed and raw >= (1 << (self.length - 1)):
            raw -= 1 << self.length
        return raw

    def decode_phys(self, data: bytes) -> float:
        """原始值转物理值：phys = raw * scale + offset。"""
        return self.decode_raw(data) * self.scale + self.offset

    def value_text(self, raw: int) -> Optional[str]:
        return self.values.get(raw)


@dataclass
class Message:
    frame_id: int
    name: str
    length: int
    transmitter: str
    signals: Dict[str, Signal] = field(default_factory=dict)
    cycle_time: int = 0
    comment: str = ""


@dataclass
class Database:
    messages: Dict[int, Message] = field(default_factory=dict)
    nodes: List[str] = field(default_factory=list)
    version: str = ""

    def get_message(self, frame_id: int) -> Optional[Message]:
        return self.messages.get(frame_id)


def _extract_bits(data: bytes, start_bit: int, length: int, byte_order: str) -> int:
    """从 CAN 帧字节中提取信号原始值。

    Intel 字节序: start_bit 为信号 LSB 的位序号 (bit 0-63, 低位在前)。
    Motorola 字节序: start_bit 为信号 MSB 的位序号 (bit 0-63, 高位在前)。
    """
    if length <= 0 or length > 64:
        raise ValueError(f"非法信号长度: {length}")

    if byte_order == "Intel":
        value = 0
        for i in range(length):
            bit = start_bit + i
            byte_idx = bit // 8
            if byte_idx >= len(data):
                break
            bit_idx = bit % 8
            value |= ((data[byte_idx] >> bit_idx) & 1) << i
        return value

    # Motorola (big-endian): DBC 规范中 start_bit 是 MSB 的位序号。
    # 位序号 n -> 字节 n//8, 字节内位 7-(n%8)（字节内 bit7 是最低位序号）。
    # 信号从 MSB 向 LSB 延伸，位序号递增，跨字节时向高字节号方向。
    value = 0
    for i in range(length):
        bit = start_bit + i
        byte_idx = bit // 8
        if byte_idx >= len(data):
            break
        bit_idx = 7 - (bit % 8)
        value = (value << 1) | ((data[byte_idx] >> bit_idx) & 1)
    return value


_RE_BO = re.compile(r"^BO_\s+(\d+)\s+([A-Za-z0-9_]+)\s*:\s*(\d+)\s+([A-Za-z0-9_]+)\s*$")
_RE_SG = re.compile(
    r"^SG_\s+([A-Za-z0-9_]+)\s*(?:[A-Za-z0-9_]+)?\s*:\s*(\d+)\|(\d+)@([01])([+-])\s*"
    r"\((-?[\d.eE+-]+)\s*,\s*(-?[\d.eE+-]+)\)\s*\[(-?[\d.eE+-]+)\|(-?[\d.eE+-]+)\]\s*\"([^\"]*)\"\s*(.*)$"
)
_RE_VAL = re.compile(r'^VAL_\s+(\d+)\s+([A-Za-z0-9_]+)\s+(.*)$')
_RE_BA_CYCLE = re.compile(r'^BA_\s+"GenMsgCycleTime"\s+BO_\s+(\d+)\s+(\d+)\s*;?\s*$')
_RE_CM_SG = re.compile(r'^CM_\s+SG_\s+(\d+)\s+([A-Za-z0-9_]+)\s+"(.*)"\s*$')


def _detect_encoding(data: bytes) -> str:
    for enc in ("utf-8", "gbk", "latin-1"):
        try:
            data.decode(enc)
            return enc
        except (UnicodeDecodeError, LookupError):
            continue
    return "latin-1"


def parse_dbc(text: str) -> Database:
    db = Database()
    current_msg: Optional[Message] = None

    for raw_line in text.splitlines():
        line = raw_line.strip()
        if not line:
            continue

        if line.startswith("VERSION"):
            m = re.match(r'VERSION\s+"(.*)"', line)
            if m:
                db.version = m.group(1)
            continue
        if line.startswith("BU_"):
            nodes = line[3:].strip().split()
            db.nodes = [n for n in nodes if n]
            continue

        m = _RE_BO.match(line)
        if m:
            frame_id, name, length, transmitter = (
                int(m.group(1)), m.group(2), int(m.group(3)), m.group(4))
            current_msg = Message(frame_id, name, length, transmitter)
            db.messages[frame_id] = current_msg
            continue

        m = _RE_SG.match(line)
        if m and current_msg is not None:
            sig = Signal(
                name=m.group(1),
                start_bit=int(m.group(2)),
                length=int(m.group(3)),
                byte_order="Intel" if m.group(4) == "1" else "Motorola",
                is_signed=(m.group(5) == "-"),
                scale=float(m.group(6)),
                offset=float(m.group(7)),
                minimum=float(m.group(8)),
                maximum=float(m.group(9)),
                unit=m.group(10),
                receivers=[r for r in m.group(11).split() if r],
            )
            current_msg.signals[sig.name] = sig
            continue

        m = _RE_VAL.match(line)
        if m:
            frame_id = int(m.group(1))
            sig_name = m.group(2)
            msg = db.messages.get(frame_id)
            if msg and sig_name in msg.signals:
                # 解析 "0 "异常" 1 "正常"" 形式的枚举
                body = m.group(3)
                for vm in re.finditer(r'(\d+)\s+"([^"]*)"', body):
                    msg.signals[sig_name].values[int(vm.group(1))] = vm.group(2)
            continue

        m = _RE_BA_CYCLE.match(line)
        if m:
            msg = db.messages.get(int(m.group(1)))
            if msg:
                msg.cycle_time = int(m.group(2))
            continue

        m = _RE_CM_SG.match(line)
        if m:
            msg = db.messages.get(int(m.group(1)))
            if msg and m.group(2) in msg.signals:
                msg.signals[m.group(2)].comment = m.group(3)
            continue

    return db


def load_dbc(path: str | Path) -> Database:
    data = Path(path).read_bytes()
    encoding = _detect_encoding(data)
    return parse_dbc(data.decode(encoding))
