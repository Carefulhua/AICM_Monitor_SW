"""MES 上传编排：顺序发送、遇 NG 即停、网络失败整组重发。

发包由调用方注入（urllib 实现后续放在 mes/transport.py），本模块只管策略，
因此可在离线单测中验证发送顺序与重试行为。
"""
from __future__ import annotations

import time
from collections.abc import Callable
from dataclasses import dataclass

from mes.protocol import Reply, build_test_results
from mes.report import TestResult


class MesTransportError(RuntimeError):
    """网络/协议层发送失败（区别于 MES 返回的业务 NG）。"""


@dataclass(frozen=True)
class UploadPolicy:
    max_retry: int = 3
    retry_delay_s: float = 1.0
    sleep: Callable[[float], None] = time.sleep


@dataclass(frozen=True)
class UploadResult:
    ok: bool
    kind: str  # 'ok' | 'ng' | 'failed' | 'empty'
    reason: str = ""
    sent: int = 0   # 已成功发送的条数
    total: int = 0  # 应发条数


SendFn = Callable[[str], Reply]


def upload(result: TestResult, send: SendFn,
           policy: UploadPolicy = UploadPolicy()) -> UploadResult:
    """把一次测试结果按 04 命令逐条发往 MES。"""
    commands = build_test_results(result)
    total = len(commands)
    if not total:
        return UploadResult(ok=True, kind="empty")

    attempt = 0
    while True:
        for idx, cmd in enumerate(commands, 1):
            try:
                reply = send(cmd)
            except MesTransportError as exc:
                if attempt >= policy.max_retry:
                    return UploadResult(False, "failed", str(exc), idx - 1, total)
                policy.sleep(policy.retry_delay_s * (2 ** attempt))
                break  # 整组重发
            if not reply.ok:
                return UploadResult(False, "ng", reply.reason, idx - 1, total)
        else:
            return UploadResult(True, "ok", sent=total, total=total)
        attempt += 1