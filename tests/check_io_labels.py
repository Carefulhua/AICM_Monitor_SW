import os
os.environ["QT_QPA_PLATFORM"] = "offscreen"
import sys
from pathlib import Path
ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
from PyQt5.QtWidgets import QApplication
from main import load_config
from data.decoder import Decoder
from data.model import BusModel
from ui.main_window import MainWindow

app = QApplication([])
app.setStyle("Fusion")
cfg = load_config()
decoder = Decoder.load(cfg["dbc"], cfg["signals"])
model = BusModel(decoder)
win = MainWindow(decoder, model, cfg)
win.resize(1500, 900)
win.show()
win.tabs.setCurrentIndex(2)  # IO
app.processEvents()

io = win.io
# 遍历所有 LedCell
from ui.widgets import LedCell, StatusGroup
found = 0
for grp_name, grp in [("HSD", io.hsd_grp), ("LSD", io.lsd_grp),
                      ("USV", io.usv_grp), ("CAN", io.can_grp), ("I2C", io.i2c_grp)]:
    for key, cell in grp._cells.items():
        found += 1
        lbl = cell.label
        w = lbl.width()
        txt = lbl.text()
        if w < 5 or not txt:
            print(f"[缺失] {grp_name} key={key} label='{txt}' 渲染宽={w}")
print(f"共检查 {found} 个 LedCell")
app.quit()
