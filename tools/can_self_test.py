"""CAN 硬件自检：加载驱动库 -> 打开设备 -> 接收报文。

在 Windows（已连接 USB-CAN 并安装驱动）上运行，逐步报告结果：
    python tools/can_self_test.py [--device USBCANFD-200U|ZQWL-UCANFD-100E|PCAN:PCAN_USBBUS1|auto]
正常结尾打印 "自检通过" 并 exit 0。
"""
from __future__ import annotations

import argparse
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))


def main():
    ap = argparse.ArgumentParser(description="CAN 硬件自检")
    ap.add_argument("--device", default="USBCANFD-200U",
                    help="设备型号，PCAN 用 PCAN:PCAN_USBBUS1 格式，或 auto 自动探测")
    ap.add_argument("--channel", type=int, default=0)
    ap.add_argument("--baud", type=int, default=500000)
    ap.add_argument("--dur", type=float, default=5.0, help="接收持续时间(秒)")
    args = ap.parse_args()

    from can_driver.zlg_can import make_adapter

    device = None if args.device == "auto" else args.device
    cfg = {"channel": args.channel, "baudrate": args.baud}
    dev = make_adapter(cfg, device)
    print(f"[1/3] 加载驱动库并打开设备 {args.device} ...")
    if not dev.connect(device):
        print("  [FAIL] 打开设备失败。请确认适配器已插好、驱动已安装、型号与实际硬件一致")
        sys.exit(1)
    print(f"  [OK] 设备已打开: {dev.device_summary}")

    print(f"[2/3] 开始接收 {args.dur}s ...")
    count = 0
    seen = set()

    def on_frame(frame):
        nonlocal count
        count += 1
        seen.add(frame.can_id)

    dev.start_receiving(on_frame)
    time.sleep(args.dur)
    dev.stop_receiving()

    print(f"  [{'OK' if count else 'WARN'}] 收到 {count} 帧, 涉及 {len(seen)} 个不同 ID")
    if seen:
        print("  报文 ID:", ", ".join(f"0x{x:X}" for x in sorted(seen)))

    print(f"[3/3] 关闭设备 ...")
    dev.close()
    print("  [OK] 已关闭")

    if count:
        print("\n自检通过: 物理通讯正常")
        sys.exit(0)
    print("\n自检完成但未收到报文: 设备正常但总线上无数据")
    sys.exit(2)


if __name__ == "__main__":
    main()