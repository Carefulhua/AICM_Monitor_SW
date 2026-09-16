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
from can_driver.simulator import DVTestSimulator
from ui.main_window import MainWindow

def main():
    cfg = load_config()
    decoder = Decoder.load(cfg["dbc"], cfg["signals"])
    model = BusModel(decoder)
    app = QApplication([])
    app.setStyle("Fusion")
    win = MainWindow(decoder, model, cfg)
    win.resize(1500, 900)
    win.tabs.setCurrentIndex(2)
    win.show()
    app.processEvents()
    io = win.io

    # 故障帧: hsd_ok[2]=0 -> HSD3 状态异常; 其余正常
    sim = DVTestSimulator(decoder.db)
    sim._callback = lambda fr: model.record(fr.can_id, fr.data, fr.timestamp)
    sim._emit(140)
    model.refresh()
    io.refresh()

    st3 = model.channels["HSD3"]
    st1 = model.channels["HSD1"]
    led3 = io.hsd_grp._cells["HSD_Status_P232"].led._ok
    card3 = io.hsd_current["HSD3"].led._ok
    led1 = io.hsd_grp._cells["HSD_Status_P230"].led._ok
    card1 = io.hsd_current["HSD1"].led._ok
    print(f"HSD3 normal={st3.normal} 状态灯={led3} 电流卡={card3}")
    print(f"HSD1 normal={st1.normal} 状态灯={led1} 电流卡={card1}")
    assert led3 is False and card3 is False, "HSD3 异常应红灯"
    assert led1 is True and card1 is True, "HSD1 正常应绿灯"
    print("OK: 电流卡 LED 已跟随 HSD 状态")
    app.quit()

if __name__ == "__main__":
    main()
