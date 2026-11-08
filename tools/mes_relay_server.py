"""MES 中转桩：接收上位机请求 → 落盘 → 转发真实 MES → 原样回传响应。

用途：现场连真实 MES 时，既不影响上传，又能本机看到「发了什么、MES 回了什么」。
上位机把 config/mes.json 的 url 指到本桩即可：
    http://127.0.0.1:8091/WebService/MesATEApi.asmx/ATECommandCode

用法：
    python tools/mes_relay_server.py
    python tools/mes_relay_server.py --port 8091 \
        --upstream http://192.168.20.100:8090/WebService/MesATEApi.asmx/ATECommandCode
    python tools/mes_relay_server.py --upstream http://... --timeout 20

浏览器直接打开桩地址（不带 commandString）显示状态页；日志在 data/mes_relay_<日期>.log。
"""
from __future__ import annotations

import argparse
import html
import ssl
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from collections import deque
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlparse

ROOT = Path(__file__).resolve().parent.parent
LOG_DIR = ROOT / "data"

DEFAULT_UPSTREAM = ("http://192.168.20.100:8090"
                    "/WebService/MesATEApi.asmx/ATECommandCode")


def _prepare_stdout() -> None:
    """Windows 控制台默认 GBK，中文命令会乱码，统一切到 UTF-8。"""
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(encoding="utf-8", errors="replace")
        except (AttributeError, ValueError):
            pass


def _opener() -> urllib.request.OpenerDirector:
    ctx = ssl.create_default_context()
    ctx.check_hostname = False
    ctx.verify_mode = ssl.CERT_NONE
    return urllib.request.build_opener(urllib.request.HTTPSHandler(context=ctx))


def _forward(upstream: str, command: str, mode: str,
             timeout_s: float) -> str:
    """把 commandString 原样转发到上游 MES，返回响应体原文。"""
    if mode == "get":
        query = urllib.parse.urlencode({"commandString": command})
        req = urllib.request.Request(f"{upstream}?{query}", method="GET")
    else:
        body = urllib.parse.urlencode({"commandString": command}).encode("utf-8")
        req = urllib.request.Request(upstream, data=body, method="POST")
        req.add_header("Content-Type",
                       "application/x-www-form-urlencoded; charset=utf-8")
    with _opener().open(req, timeout=timeout_s) as resp:
        return resp.read().decode("utf-8", errors="replace")


class RelayHandler(BaseHTTPRequestHandler):
    upstream: str = DEFAULT_UPSTREAM
    timeout_s: float = 15.0
    mode: str = "form"
    log_path: Path = LOG_DIR / "mes_relay.log"
    recent: deque[str] = deque(maxlen=50)
    received_total: int = 0
    failed_total: int = 0

    def _command(self) -> str:
        if self.command == "GET":
            query = parse_qs(urlparse(self.path).query)
            return query.get("commandString", [""])[0]
        raw = self.rfile.read(int(self.headers.get("Content-Length", 0)))
        form = parse_qs(raw.decode("utf-8", errors="replace"))
        return form.get("commandString", [""])[0]

    def _write_log(self, line: str) -> None:
        with type(self).log_path.open("a", encoding="utf-8") as fh:
            fh.write(line + "\n")

    def _send_body(self, data: bytes, code: int = 200) -> None:
        self.send_response(code)
        self.send_header("Content-Type", "text/xml; charset=utf-8")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def _reply(self) -> None:
        command = self._command()
        if self.command == "GET" and not command:
            self._serve_page()
            return

        cls = type(self)
        stamp = time.strftime("%Y-%m-%d %H:%M:%S")
        cls.received_total += 1
        cls.recent.append(f"[{stamp}] SEND <- {command}")
        self._write_log(f"[{stamp}] SEND <- {command}")
        print(f"[{stamp}] SEND <- {command}")

        try:
            body = _forward(cls.upstream, command, cls.mode, cls.timeout_s)
        except (urllib.error.URLError, OSError, urllib.error.HTTPError) as exc:
            cls.failed_total += 1
            detail = f"{type(exc).__name__}: {exc}"
            self._write_log(f"[{stamp}] FAIL -> {detail}")
            cls.recent.append(f"[{stamp}] FAIL -> {detail}")
            print(f"[{stamp}] FAIL -> {detail}")
            err = f"<ATECommandCodeResult>NG;中转桩转发失败:{detail};</ATECommandCodeResult>"
            self._send_body(err.encode("utf-8"), 502)
            return

        flat = " ".join(body.split())
        self._write_log(f"[{stamp}] RESP -> {flat}")
        cls.recent.append(f"[{stamp}] RESP -> {flat}")
        print(f"[{stamp}] RESP -> {flat}")
        self._send_body(body.encode("utf-8"))

    def _serve_page(self) -> None:
        cls = type(self)
        rows = "\n".join(
            f"<li><code>{html.escape(line)}</code></li>"
            for line in reversed(cls.recent)
        ) or "<li class='dim'>还没有收到任何命令</li>"
        body = f"""<!doctype html>
<html lang="zh-CN"><head><meta charset="utf-8">
<title>MES 中转桩</title>
<style>
body{{font-family:Consolas,'Microsoft YaHei',monospace;margin:24px;background:#1e1e1e;color:#ddd}}
h1{{font-size:18px}} code{{color:#9cdcfe}} .dim{{color:#888}}
table{{border-collapse:collapse}} td{{padding:2px 12px 2px 0}}
</style></head><body>
<h1>MES 中转桩（记录 + 转发）</h1>
<table>
<tr><td>监听端口</td><td>{cls.port}</td></tr>
<tr><td>上游 MES</td><td><code>{html.escape(cls.upstream)}</code></td></tr>
<tr><td>转发方式</td><td>{cls.mode}</td></tr>
<tr><td>超时</td><td>{cls.timeout_s:g}s</td></tr>
<tr><td>累计收到</td><td>{cls.received_total} 条（失败 {cls.failed_total} 条）</td></tr>
<tr><td>中转日志</td><td><code>{html.escape(str(cls.log_path))}</code></td></tr>
</table>
<h1>最近中转记录（最多 50 条，倒序）</h1>
<ul>{rows}</ul>
<p class="dim">直接刷新本页不带 commandString，不会新增记录。<br>
把 <code>config/mes.json</code> 的 url 指向
<code>http://127.0.0.1:{cls.port}/WebService/MesATEApi.asmx/ATECommandCode</code>
即可让上传经本桩转发。</p>
</body></html>"""
        data = body.encode("utf-8")
        self.send_response(200)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def do_GET(self):
        self._reply()

    def do_POST(self):
        self._reply()

    def log_message(self, *args):
        pass


def main() -> None:
    _prepare_stdout()
    ap = argparse.ArgumentParser(description="MES 中转桩：记录并转发 commandString")
    ap.add_argument("--port", type=int, default=8091)
    ap.add_argument("--upstream", default=DEFAULT_UPSTREAM)
    ap.add_argument("--mode", choices=("form", "get"), default="form")
    ap.add_argument("--timeout", type=float, default=15.0)
    ap.add_argument("--log", default="")
    args = ap.parse_args()

    RelayHandler.upstream = args.upstream
    RelayHandler.mode = args.mode
    RelayHandler.timeout_s = args.timeout
    RelayHandler.port = args.port
    RelayHandler.log_path = (Path(args.log) if args.log else
                             LOG_DIR / f"mes_relay_{time.strftime('%Y%m%d')}.log")
    RelayHandler.log_path.parent.mkdir(parents=True, exist_ok=True)

    server = ThreadingHTTPServer(("0.0.0.0", args.port), RelayHandler)
    print(f"中转桩已启动: http://127.0.0.1:{args.port}"
          f"/WebService/MesATEApi.asmx/ATECommandCode")
    print(f"上游 MES    : {args.upstream}")
    print(f"中转日志    : {RelayHandler.log_path}")
    print("Ctrl+C 退出")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\n已停止")
    finally:
        server.server_close()


if __name__ == "__main__":
    main()
