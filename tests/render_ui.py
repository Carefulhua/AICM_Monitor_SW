"""offscreen 渲染各标签页为 PNG，供视觉 QA。用法: python tests/render_ui.py <输出目录>"""
import os, sys
os.environ["QT_QPA_PLATFORM"] = "offscreen"
from pathlib import Path
ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from PyQt5.QtWidgets import QApplication
from PyQt5.QtCore import QTimer

from main import load_config
from data.decoder import Decoder
from data.model import BusModel
from ui.main_window import MainWindow

OUT = Path(sys.argv[1]) if len(sys.argv) > 1 else Path(ROOT) / "data" / "shots"
OUT.mkdir(parents=True, exist_ok=True)


def main():
    cfg = load_config()
    decoder = Decoder.load(cfg["dbc"], cfg["signals"])
    model = BusModel(decoder)
    app = QApplication(sys.argv)
    app.setStyle("Fusion")
    win = MainWindow(decoder, model, cfg)
    win.resize(1500, 900)
    win.show()

    names = ["overview", "camera", "io", "curves", "log"]

    def capture_tabs():
        for i, name in enumerate(names):
            win.tabs.setCurrentIndex(i)
            app.processEvents()
            pix = win.grab()
            pix.save(str(OUT / f"tab_{i}_{name}.png"))
            print(f"[OK] rendered tab_{i}_{name}.png {pix.width()}x{pix.height()}")

        # 故障态：停掉真实仿真 → 注入 t=14s 故障帧 → 刷新后截取前三个标签页
        win.on_start()
        from can_driver.simulator import DVTestSimulator
        fault_sim = DVTestSimulator(decoder.db)
        fault_sim._callback = lambda fr: model.record(fr.can_id, fr.data, fr.timestamp)
        fault_sim._emit(140)
        model.refresh()
        for i, name in enumerate(names[:3]):
            win.tabs.setCurrentIndex(i)
            app.processEvents()
            win.grab().save(str(OUT / f"tab_{i}_{name}_fault.png"))
            print(f"[OK] rendered tab_{i}_{name}_fault.png")
        app.quit()

    QTimer.singleShot(300, win.on_connect)     # 连接(仿真)
    QTimer.singleShot(600, win.on_start)       # 启动接收
    QTimer.singleShot(5200, capture_tabs)      # 等5s数据积累后逐页截图
    app.exec_()
    print("RENDER DONE ->", OUT)


if __name__ == "__main__":
    main()