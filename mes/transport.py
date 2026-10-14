"""MES HTTP 传输：urllib 直发 commandString，不引入第三方依赖。

现场接口是自签证书 HTTPS（同厂实测代码用 verify=False），故默认不校验证书；
MES 换成可信证书后可把 verify_tls 置 true。
"""
from __future__ import annotations

import ssl
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass

from mes.client import MesTransportError


@dataclass(frozen=True)
class HttpConfig:
    url: str
    mode: str = "form"
    timeout_s: float = 15.0
    verify_tls: bool = False


def _opener(verify_tls: bool) -> urllib.request.OpenerDirector:
    if verify_tls:
        return urllib.request.build_opener()
    ctx = ssl.create_default_context()
    ctx.check_hostname = False
    ctx.verify_mode = ssl.CERT_NONE
    return urllib.request.build_opener(urllib.request.HTTPSHandler(context=ctx))


def send(command: str, cfg: HttpConfig) -> str:
    """发送一条 commandString，返回 MES 响应体原文。

    仅网络/HTTP 层失败抛 MesTransportError；MES 的业务判定（OK/NG）由响应体表达，
    交 protocol.parse_response 处理。
    """
    if cfg.mode == "get":
        query = urllib.parse.urlencode({"commandString": command})
        req = urllib.request.Request(f"{cfg.url}?{query}", method="GET")
    else:
        body = urllib.parse.urlencode({"commandString": command}).encode("utf-8")
        req = urllib.request.Request(cfg.url, data=body, method="POST")
        req.add_header("Content-Type",
                       "application/x-www-form-urlencoded; charset=utf-8")
    try:
        with _opener(cfg.verify_tls).open(req, timeout=cfg.timeout_s) as resp:
            return resp.read().decode("utf-8", errors="replace")
    except urllib.error.HTTPError as e:
        detail = e.read().decode("utf-8", errors="replace")[:200]
        raise MesTransportError(f"HTTP {e.code}: {detail}") from e
    except (urllib.error.URLError, OSError) as e:
        raise MesTransportError(f"{type(e).__name__}: {e}") from e