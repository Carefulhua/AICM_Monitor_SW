"""offscreen 验证 MES 上传链路：SN 输入 -> 04 组包 -> HTTP 发送 -> 状态显示。

用本地 HTTP 服务模拟 MES（回 OK / NG），不依赖真实 MES 即可验证 UI 接线。
用法: python tests/mes_ui_check.py
"""
import os
import sys
import threading
import time
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path
from urllib.parse import parse_qs

os.environ["QT_QPA_PLATFORM"] = "offscreen"
ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

RECEIVED: list[str] = []


class _MesStub(BaseHTTPRequestHandler):
    def do_POST(self):
        raw = self.rfile.read(int(self.headers.get("Content-Length", 0))).decode("utf-8")
        RECEIVED.append(parse_qs(raw).get("commandString", [""])[0])
        data = "<ATECommandCodeResult>OK;</ATECommandCodeResult>".encode("utf-8")
        self.send_response(200)
        self.send_header("Content-Type", "text/xml; charset=utf-8")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def log_message(self, *args):
        pass


def main():
    server = HTTPServer(("127.0.0.1", 0), _MesStub)
    threading.Thread(target=server.serve_forever, daemon=True).start()

    from PyQt5.QtCore import QTimer
    from PyQt5.QtWidgets import QApplication

    from main import load_config
    from data.decoder import Decoder
    from data.model import BusModel
    from ui import main_window as mw

    cfg = load_config()
    assert "mes" in cfg, "config/mes.json not loaded by load_config()"
    cfg["mes"].update(enabled=True, mode="form", operator="EMP001",
                      process="Station001", resource="Res001",
                      machine="MachineNo", fixture="Fixture001",
                      url=f"http://127.0.0.1:{server.server_port}/mesateapi.asmx")

    decoder = Decoder.load(cfg["dbc"], cfg["signals"])
    model = BusModel(decoder)
    app = QApplication(sys.argv)
    app.setStyle("Fusion")
    win = mw.MainWindow(decoder, model, cfg)
    win.show()
    assert win.mes_btn.isEnabled(), "enabled=true should enable the MES button"

    def check():
        try:
            _check(win, mw)
            print("MES UI CHECK PASS")
        except Exception:
            import traceback
            traceback.print_exc()
            app.exit(1)
        else:
            app.quit()

    def connect_sim():
        win.source_cb.setCurrentIndex(1)
        win.on_connect()

    QTimer.singleShot(300, connect_sim)
    QTimer.singleShot(600, win.on_start)
    QTimer.singleShot(4500, check)
    rc = app.exec_()
    server.shutdown()
    sys.exit(rc)


def _check(win, mw):
    items = win._collect_mes_items()
    assert items, "no items collected from simulator"
    print(f"channels={len(win.model.channels)} items={len(items)}")

    win.sn_edit.setText("SN20261014001")
    win.on_upload_mes()
    print("status:", win.mes_status.text())
    print("commands:", len(RECEIVED))
    for cmd in RECEIVED:
        print("  ->", cmd[:120] + ("..." if len(cmd) > 120 else ""))
    assert RECEIVED, "MES stub received no command"
    assert win.mes_status.text().startswith("MES 接收"), win.mes_status.text()
    expected = max(1, -(-len(items) // 7))
    assert len(RECEIVED) == expected, f"expected {expected} commands, got {len(RECEIVED)}"

    RECEIVED.clear()

    def _ng_send(cmd, cfg):
        return "<ATECommandCodeResult>NG;工单不存在;</ATECommandCodeResult>"

    real_send = mw.mes_send
    mw.mes_send = _ng_send
    try:
        win.on_upload_mes()
    finally:
        mw.mes_send = real_send
    print("NG status:", win.mes_status.text())
    assert "工单不存在" in win.mes_status.text(), win.mes_status.text()
    assert "已发 0/" in win.mes_status.text(), win.mes_status.text()

    win.cfg["mes"]["channels"] = ["VBATT_P", "IGN", "DC17V"]
    only = win._collect_mes_items()
    print("whitelist:", [i.name for i in only])
    assert {i.name for i in only} == {"VBATT_P", "IGN", "DC17V"}, only


if __name__ == "__main__":
    main()