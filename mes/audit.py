"""MES 发送审计日志：把每次请求与响应原文追加到本地日志。

用途：现场连真实 MES 时，事后仍能核对「发了什么、MES 回了什么」。
日志格式（一行一条，追加写）：
    2026-11-08 13:16:26  BEGIN  SN=6666 verdict=OK url=http://...
    2026-11-08 13:16:26  SEND   04;DQ2206ZSC0160;6666;...
    2026-11-08 13:16:26  RESP   <ATECommandCodeResult>OK;</ATECommandCodeResult>
    2026-11-08 13:16:27  FAIL   URLError: <urlopen error [Errno 111] Connection refused>
"""
from __future__ import annotations

import threading
import time
from pathlib import Path

_LOCK = threading.Lock()


def log(path: Path | str, tag: str, text: str) -> None:
    """追加一条审计记录。写盘失败静默忽略（不能阻断现场上传）。"""
    stamp = time.strftime("%Y-%m-%d %H:%M:%S")
    line = f"{stamp}  {tag:<5}  {text}"
    try:
        p = Path(path)
        p.parent.mkdir(parents=True, exist_ok=True)
        with _LOCK, p.open("a", encoding="utf-8") as fh:
            fh.write(line + "\n")
    except OSError:
        pass
