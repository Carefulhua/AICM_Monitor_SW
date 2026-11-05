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
        assert win.start_btn.text() == "启动测试", "start button label"
        assert not hasattr(win, "test_mode_btn"), "test mode button still exists"
        assert not win.verdict._judged_started, "verdict should wait for first frame"
        win.on_connect()            # 连接(仿真)
        win.on_start()              # 启动接收并自动进入测试模式

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

            # 自动判定：无按钮，定时器每秒刷新
            assert not hasattr(win.verdict, "judge_btn"), "judge button still exists"
            assert win.verdict.timer.isActive(), "verdict timer not running"
            assert win.verdict.timer.interval() == 1000, "verdict timer interval"
            win.verdict.report = None
            win.model.refresh()
            mst = win.model.messages.get(0x659)
            assert mst is not None and mst.seen, "no first frame 0x659 before judging"
            win.verdict._judged_started = True
            win.verdict.timer.timeout.emit()
            assert win.verdict.report is not None, "auto judge not wired"
            print("[OK] verdict timer 1s")

            # 自动判定：正常窗口应 PASS
            assert not win.verdict._waiting_for_data(), "should not wait when data+SPI ok"
            win.verdict.on_judge()
            assert win.verdict.report is not None
            assert win.verdict.report.ok, (
                "verdict not PASS: " + ", ".join(
                    i.name for i in win.verdict.report.items if not i.ok))
            print(f"[OK] verdict PASS ({win.verdict.report.total} items)")

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

            # 故障注入后自动判定必须 FAIL
            win.verdict.on_judge()
            assert not win.verdict.report.ok
            assert any(i.name == "IGN" and not i.ok
                       for i in win.verdict.report.items)
            print(f"[OK] verdict FAIL under fault "
                  f"({win.verdict.report.failed} items)")

            fault_sim._emit(0)        # t=0 -> 正常窗口
            model.refresh()
            assert model.channels["IGN"].normal is True, "IGN stuck abnormal"
            assert model.decoder.is_status_normal("Cam3Linklock",
                        model.raw_of("Cam3Linklock")) is True, "Cam3 stuck abnormal"
            win.verdict.on_judge()
            assert win.verdict.report.ok, "verdict not recovered"
            print("[OK] fault recovery OK")

            # 启动测试：启动即进入测试模式，停止时复位
            assert win.start_btn.text() == "停止", "start button not in test state"
            assert win.test_mode_timer.isActive(), "test mode timer not started"
            assert win.test_mode_timer.interval() == 1000, "test mode period"
            win.on_start()            # 停止测试
            assert win.start_btn.text() == "启动测试", "start button label not restored"
            assert not win.test_mode_timer.isActive(), "test mode timer not stopped"
            print("[OK] auto test mode ON/OFF")
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