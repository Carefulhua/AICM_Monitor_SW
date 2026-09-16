"""ZLG CAN 硬件自检：加载 zlgcan.dll -> 打开设备 -> 初始化通道 -> 接收报文。

在 Windows（已连接 USB-CAN 并安装驱动）上运行，逐步报告结果：
    python tools/can_self_test.py [--device USBCANFD-200U] [--channel 0] [--baud 500000]
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
    ap = argparse.ArgumentParser(description="ZLG CAN 硬件自检")
    ap.add_argument("--device", default="USBCANFD-200U")
    ap.add_argument("--device_index", type=int, default=0)
    ap.add_argument("--channel", type=int, default=0)
    ap.add_argument("--baud", type=int, default=500000)
    ap.add_argument("--dur", type=float, default=5.0, help="接收持续时间(秒)")
    args = ap.parse_args()

    from can_driver.zlg_can import ZLGCANDevice

    dev = ZLGCANDevice({
        "device": args.device,
        "device_index": args.device_index,
        "channel": args.channel,
        "baudrate": args.baud,
    })

    print(f"[1/4] 加载 zlgcan.dll ...")
    if not dev.load_driver():
        print("  [FAIL] 无法加载 zlgcan.dll。请确认存在 can_driver/zlgcan.dll")
        sys.exit(1)
    print("  [OK] 驱动加载成功")

    print(f"[2/4] 打开设备 {args.device} idx={args.device_index} ...")
    if not dev.open():
        print("  [FAIL] 打开设备失败。请确认 USB 已连接、ZLG 驱动已安装、设备型号匹配")
        sys.exit(1)
    print(f"  [OK] 设备已打开: {dev.device_summary}")

    print(f"[3/4] 开始接收 {args.dur}s ...")
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

    print(f"[4/4] 关闭设备 ...")
    dev.close()
    print("  [OK] 已关闭")

    if count:
        print("\n自检通过: 物理通讯正常")
        sys.exit(0)
    print("\n自检完成但未收到报文: 设备正常但总线上无数据(检查 DBC 报文是否对应对端发送)")
    sys.exit(2)


if __name__ == "__main__":
    main()