import os
os.environ["QT_QPA_PLATFORM"] = "offscreen"
import sys, json
from pathlib import Path
ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
from PyQt5.QtWidgets import QApplication
from data.decoder import Decoder
from data.model import BusModel
from can_driver.zlg_can import CANFrame
from ui.panel_log import LogPanel

def main():
    cfg = json.load(open(ROOT/"config/app.json"))
    decoder = Decoder.load(cfg["dbc"], cfg["signals"])
    model = BusModel(decoder)
    app = QApplication([])
    panel = LogPanel(model)
    panel.show()
    # 模拟 main_window.on_frame -> _log_queue -> add_frames 的真实数据类型
    ids = list(decoder.db.messages.keys())[:4]
    frames = [CANFrame(can_id=i, data=bytes(range(8)), timestamp=i*0.1+0.123) for i in ids]
    model.record(frames[0].can_id, frames[0].data, frames[0].timestamp)
    panel.add_frames(frames)
    rows = panel.table.rowCount()
    assert rows == len(frames), f"rows={rows} != {len(frames)}"
    print(f"[OK] 渲染 {rows} 行, 首行 时间={panel.table.item(0,0).text()} ID={panel.table.item(0,1).text()}")
    print("LOG PANEL RENDER PASS")

if __name__ == "__main__":
    main()
