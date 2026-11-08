"""本地 MES 桩服务器：接收上位机上传的 04 commandString，打印并落盘。

用途：不在工厂网络时，验证上位机实际发出去的内容。
把 config/mes.json 的 url 临时改成 http://127.0.0.1:<端口>/WebService/MesATEApi.asmx/ATECommandCode
后点「上传MES(04)」，本服务会把每条 04 打印到控制台并追加写入接收日志。

用法：
    python tools/mes_mock_server.py            # 监听 0.0.0.0:8090，回 OK
    python tools/mes_mock_server.py --port 18090
    python tools/mes_mock_server.py --ng 工单不存在   # 回 NG 分支，验证拒绝处理
"""
from __future__ import annotations

import argparse
import html
import sys
import time
from collections import deque
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlparse

ROOT = Path(__file__).resolve().parent.parent
LOG_DIR = ROOT / "data"


def _prepare_stdout() -> None:
    """Windows 控制台默认 GBK，中文 04 内容会乱码，统一切到 UTF-8。"""
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(encoding="utf-8", errors="replace")
        except (AttributeError, ValueError):
            pass


class _Handler(BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"
    ng_reason: str = ""
    log_path: Path = Path()
    port: int = 8090
    # 最近收到的 04 命令，供浏览器打开地址时查看（无需去看控制台）
    recent: deque[str] = deque(maxlen=50)
    received_total: int = 0

    def _command(self) -> str:
        if self.command == "GET":
            query = parse_qs(urlparse(self.path).query)
            return query.get("commandString", [""])[0]
        raw = self.rfile.read(int(self.headers.get("Content-Length", 0)))
        form = parse_qs(raw.decode("utf-8", errors="replace"))
        return form.get("commandString", [""])[0]

    def _reply(self) -> None:
        command = self._command()
        if self.command == "GET" and not command:
            # 浏览器直接打开地址（没带 commandString）时给一张状态页，
            # 而不是一句 OK，免得误以为「只回了个 OK」。
            self._serve_page()
            return

        stamp = time.strftime("%Y-%m-%d %H:%M:%S")
        head = "NG" if self.ng_reason else "OK"
        line = f"[{stamp}] {head} <- {command}"
        print(line)
        with self.log_path.open("a", encoding="utf-8") as fh:
            fh.write(line + "\n")
        cls = type(self)
        cls.received_total += 1
        cls.recent.append(line)

        if self.ng_reason:
            body = f"<ATECommandCodeResult>NG;{self.ng_reason};</ATECommandCodeResult>"
        else:
            body = "<ATECommandCodeResult>OK;</ATECommandCodeResult>"
        data = body.encode("utf-8")
        self.send_response(200)
        self.send_header("Content-Type", "text/xml; charset=utf-8")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def _serve_page(self) -> None:
        cls = type(self)
        rows = "\n".join(
            f"<li><code>{html.escape(line)}</code></li>"
            for line in reversed(cls.recent)
        ) or "<li class='dim'>还没有收到任何 04 命令</li>"
        reply = f"NG;{cls.ng_reason};" if cls.ng_reason else "OK;"
        body = f"""<!doctype html>
<html lang="zh-CN"><head><meta charset="utf-8">
<title>本地 MES 桩</title>
<style>
body{{font-family:Consolas,'Microsoft YaHei',monospace;margin:24px;background:#1e1e1e;color:#ddd}}
h1{{font-size:18px}} code{{color:#9cdcfe}} .dim{{color:#888}}
table{{border-collapse:collapse}} td{{padding:2px 12px 2px 0}}
</style></head><body>
<h1>本地 MES 桩（模拟 MES 接口）</h1>
<table>
<tr><td>监听端口</td><td>{cls.port}</td></tr>
<tr><td>回复内容</td><td><code>&lt;ATECommandCodeResult&gt;{html.escape(reply)}&lt;/ATECommandCodeResult&gt;</code></td></tr>
<tr><td>累计收到</td><td>{cls.received_total} 条 04</td></tr>
<tr><td>接收日志</td><td><code>{html.escape(str(cls.log_path))}</code></td></tr>
</table>
<h1>最近收到的 04（最多 50 条，倒序）</h1>
<ul>{rows}</ul>
<p class="dim">这里只显示「带 commandString 的请求」。直接浏览器刷新本页不带参数，所以不会新增记录。<br>
把 <code>config/mes.json</code> 的 url 指到 <code>http://127.0.0.1:{cls.port}/WebService/MesATEApi.asmx/ATECommandCode</code>，再在界面点「上传MES(04)」。</p>
</body></html>"""
        data = body.encode("utf-8")
        self.send_response(200)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def do_POST(self) -> None:
        self._reply()

    def do_GET(self) -> None:
        self._reply()

    def log_message(self, *args) -> None:
        pass


def main() -> int:
    ap = argparse.ArgumentParser(description="本地 MES 桩服务器（04 内容回显）")
    ap.add_argument("--host", default="0.0.0.0")
    ap.add_argument("--port", type=int, default=8090)
    ap.add_argument("--ng", default="", help="非空则回 NG;<原因>;，用于验证拒绝分支")
    args = ap.parse_args()

    _prepare_stdout()
    LOG_DIR.mkdir(parents=True, exist_ok=True)
    log_path = LOG_DIR / f"mes_received_{time.strftime('%Y%m%d_%H%M%S')}.log"
    _Handler.ng_reason = args.ng
    _Handler.log_path = log_path
    _Handler.port = args.port

    server = ThreadingHTTPServer((args.host, args.port), _Handler)
    print(f"本地 MES 桩已启动: http://127.0.0.1:{args.port}/WebService/MesATEApi.asmx/ATECommandCode")
    print(f"接收日志: {log_path}")
    print(f"回复: {'NG;' + args.ng + ';' if args.ng else 'OK;'}")
    print("把 config/mes.json 的 url 指向上面的地址后，点「上传MES(04)」。Ctrl+C 退出。")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\n已停止。")
    finally:
        server.server_close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
