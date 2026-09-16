"""AICM-NT400 DVtest 监控上位机入口。

用法: python main.py [--dbc 路径] [--signals 路径]
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = (Path(getattr(sys, "_MEIPASS", "")) if getattr(sys, "frozen", False)
        else Path(__file__).resolve().parent)
sys.path.insert(0, str(ROOT))


def load_config() -> dict:
    cfg = json.loads((ROOT / "config" / "app.json").read_text(encoding="utf-8"))
    cfg["dbc"] = str(ROOT / cfg["dbc"])
    cfg["signals"] = str(ROOT / cfg["signals"])
    if not cfg.get("database") or Path(cfg["database"]).is_absolute() is False:
        cfg["database"] = str(ROOT / (cfg["database"] or "data/dvtest.db"))
    return cfg


def main():
    ap = argparse.ArgumentParser(description="AICM-NT400 DVtest 监控上位机")
    ap.add_argument("--dbc", help="DBC 文件路径")
    ap.add_argument("--signals", help="signals.json 配置路径")
    ap.add_argument("--offscreen", action="store_true", help="无头模式(测试)")
    args, _ = ap.parse_known_args()

    cfg = load_config()
    if args.dbc:
        cfg["dbc"] = args.dbc
    if args.signals:
        cfg["signals"] = args.signals

    from PyQt5.QtWidgets import QApplication
    if args.offscreen or "--offscreen" in sys.argv:
        import os
        os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

    from data.decoder import Decoder
    from data.model import BusModel
    from ui.main_window import MainWindow

    decoder = Decoder.load(cfg["dbc"], cfg["signals"])
    model = BusModel(decoder, cycle_ms=cfg.get("cycle_ms", 100),
                     timeout_factor=cfg.get("timeout_factor", 3))

    app = QApplication(sys.argv)
    app.setStyle("Fusion")
    # 全局暗色主题：未单独设色的 QLabel/QCheckBox 使用亮灰文字，避免黑字在深色背景不可见
    app.setStyleSheet("QLabel { color: #cccccc; }"
                      "QCheckBox { color: #cccccc; }"
                      "QToolTip { background-color: #2b2b2b; color: #cccccc;"
                      " border: 1px solid #555555; }")
    win = MainWindow(decoder, model, cfg)
    win.show()
    sys.exit(app.exec_())


if __name__ == "__main__":
    main()
