"""无头(offscreen)冒烟测试：真实启动 MainWindow + 仿真数据，运行数秒后验证状态/导出。"""
import os
os.environ["QT_QPA_PLATFORM"] = "offscreen"
import sys, time
from pathlib import Path
ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from PyQt5.QtWidgets import QApplication
from PyQt5.QtCore import QTimer

from data.decoder import Decoder
from data.model import BusModel
from ui.main_window import MainWindow


def main():
    from main import load_config
    cfg = load_config()
    decoder = Decoder.load(cfg["dbc"], cfg["signals"])
    model = BusModel(decoder)
    app = QApplication(sys.argv)
    app.setStyle("Fusion")
    win = MainWindow(decoder, model, cfg)
    win.show()

    errors = []

    def on_start():
        win.source_cb.setCurrentIndex(1)  # 显式选仿真: 默认已改为硬件(0), 无头环境无 zlgcan.dll
        win.on_connect()            # 连接(仿真)
        win.on_start()              # 启动接收

    def on_finish():
        try:
            win.model.refresh()
            win.overview.refresh()
            win.camera.refresh()
            win.io.refresh()
            f = win.model.frame_count
            st = win.model.channels["VBATT_P"]
            print(f"[OK] frames={f} msg={len(win.model.messages)} "
                  f"VBATT_P={st.value} status={st.status_text}")
            assert f > 0, "no frames"
            assert st.value is not None, "no decode"
            win.storage.export_csv(str(ROOT / "data" / "export_test"))
            assert Path(ROOT / "data" / "export_test_signals.csv").exists()
            print("[OK] CSV export done")

            # 故障注入验证：确定性驱动 t=14s(故障窗口)
            from can_driver.simulator import DVTestSimulator
            fault_sim = DVTestSimulator(decoder.db)
            fault_sim._callback = lambda fr: model.record(fr.can_id, fr.data, fr.timestamp)
            fault_sim._emit(140)      # t = 0 + 140*0.1 = 14s -> fault
            model.refresh()
            bad = [n for n, st2 in model.channels.items() if st2.valid and not st2.normal]
            print(f"[OK] fault abnormal channels: {bad}")
            assert "IGN" in bad, "IGN not abnormal"
            hsd3 = next(n for n, ch in decoder.channels.items()
                        if ch.status_sig == "HSD_Status_P232")
            assert hsd3 in bad, f"{hsd3} not abnormal"
            assert model.decoder.is_status_normal("Cam3Linklock",
                        model.raw_of("Cam3Linklock")) is False, "Cam3 not abnormal"
            assert model.decoder.is_status_normal("LSD_Status_P325",
                        model.raw_of("LSD_Status_P325")) is False, "LSD not abnormal"

            fault_sim._emit(0)        # t=0 -> 正常窗口
            model.refresh()
            assert model.channels["IGN"].normal is True, "IGN stuck abnormal"
            assert model.decoder.is_status_normal("Cam3Linklock",
                        model.raw_of("Cam3Linklock")) is True, "Cam3 stuck abnormal"
            print("[OK] fault recovery OK")
        except Exception as e:
            errors.append(repr(e))
            import traceback; traceback.print_exc()
        QTimer.singleShot(100, app.quit)

    QTimer.singleShot(200, on_start)
    QTimer.singleShot(3000, on_finish)
    app.exec_()
    if errors:
        print("FAIL:", errors); sys.exit(1)
    print("SMOKE TEST PASS")


if __name__ == "__main__":
    main()