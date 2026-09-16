"""ZLG CAN 硬件驱动（zlgcan.dll，V1.18 官方接口）。

与旧 CAN 工具相同的物理通讯方案：zlgcan.dll + dev_info.json 设备参数。
打开流程与官方 demo 一致：OpenDevice -> ZCAN_SetValue(波特率) -> InitCAN -> StartCAN，
接收线程轮询 GetReceiveNum/Receive。回调运行在接收线程，只做纯数据层操作。
"""
from __future__ import annotations

import json
import logging
import sys
import threading
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Optional

logger = logging.getLogger(__name__)

_SDK_DIR = (Path(getattr(sys, "_MEIPASS", "")) / "can_driver"
            if getattr(sys, "frozen", False)
            else Path(__file__).resolve().parent)


@dataclass
class CANFrame:
    can_id: int
    data: bytes
    timestamp: float


def _load_dev_info() -> dict:
    path = _SDK_DIR / "dev_info.json"
    if path.exists():
        return json.loads(path.read_text(encoding="utf-8"))
    logger.warning("缺少 dev_info.json，设备参数表不可用")
    return {}


class ZLGCANDevice:
    """基于 zlgcan.dll 的 CAN 设备。config 示例:
    {"device": "USBCANFD-200U", "device_index": 0, "channel": 0, "baudrate": 500000}
    """

    def __init__(self, config: Optional[dict] = None):
        self.config = config or {}
        self._dev_info = _load_dev_info()
        self._zcan = None
        self._dev_handle = 0
        self._chn_handle = 0
        self._connected = False
        self._callback: Optional[Callable[[CANFrame], None]] = None
        self._running = False
        self._thread: Optional[threading.Thread] = None
        self._hw_info: str = ""

    # ---- 驱动加载 ----
    def load_driver(self) -> bool:
        from can_driver.zlgcan_sdk import ZCAN

        candidates = [
            _SDK_DIR / "zlgcan.dll",
            Path.cwd() / "zlgcan.dll",
            Path.cwd() / "can_driver" / "zlgcan.dll",
        ]
        errors = []
        for path in candidates:
            if not path.exists():
                continue
            try:
                self._zcan = ZCAN(str(path))
                logger.info(f"成功加载 zlgcan.dll: {path}")
                return True
            except Exception as e:  # noqa: BLE001 - 逐个候选尝试
                errors.append(f"{path}: {e}")
        logger.error("加载 zlgcan.dll 失败: %s", " | ".join(errors) or "未找到 dll")
        return False

    # ---- 设备/通道 ----
    @property
    def is_connected(self) -> bool:
        return self._connected

    @property
    def device_summary(self) -> str:
        return self._hw_info

    def open(self) -> bool:
        if self._zcan is None:
            return False
        dev_name = self.config.get("device", "USBCANFD-200U")
        dev_index = int(self.config.get("device_index", 0))
        chn = int(self.config.get("channel", 0))
        baud = int(self.config.get("baudrate", 500000))

        entry = self._dev_info.get(dev_name)
        if entry is None:
            logger.error(f"dev_info.json 中无设备型号: {dev_name}")
            return False
        dev_type = int(entry["dev_type"])
        is_canfd = bool(entry["chn_info"]["is_canfd"])

        from can_driver.zlgcan_sdk import (
            INVALID_CHANNEL_HANDLE, INVALID_DEVICE_HANDLE, ZCAN_STATUS_OK,
            ZCAN_CHANNEL_INIT_CONFIG, ZCAN_TYPE_CAN, ZCAN_TYPE_CANFD)

        try:
            self._dev_handle = self._zcan.OpenDevice(dev_type, dev_index, 0)
            if self._dev_handle == INVALID_DEVICE_HANDLE:
                logger.error(f"打开设备失败: {dev_name} idx={dev_index} (请确认 USB 已连接、驱动已安装)")
                return False

            info = self._zcan.GetDeviceInf(self._dev_handle)
            if info:
                self._hw_info = info.summary()
                logger.info(f"设备信息: {self._hw_info}")

            if not self._set_baudrate(chn, baud):
                self._zcan.CloseDevice(self._dev_handle)
                return False

            cfg = ZCAN_CHANNEL_INIT_CONFIG()
            cfg.can_type = ZCAN_TYPE_CANFD if is_canfd else ZCAN_TYPE_CAN
            if is_canfd:
                cfg.config.canfd.mode = 0
                cfg.config.canfd.filter = 0
                cfg.config.canfd.acc_code = 0
                cfg.config.canfd.acc_mask = 0x00000000  # 接受所有 CAN ID
            else:
                cfg.config.can.mode = 0
                cfg.config.can.filter = 0
                cfg.config.can.acc_code = 0
                cfg.config.can.acc_mask = 0x00000000  # 接受所有 CAN ID

            self._chn_handle = self._zcan.InitCAN(self._dev_handle, chn, cfg)
            if self._chn_handle == INVALID_CHANNEL_HANDLE:
                logger.error("初始化 CAN 通道失败")
                self._zcan.CloseDevice(self._dev_handle)
                return False

            ret = self._zcan.StartCAN(self._chn_handle)
            if ret != ZCAN_STATUS_OK:
                logger.error(f"启动 CAN 通道失败: {ret}")
                self._zcan.ResetCAN(self._chn_handle)
                self._zcan.CloseDevice(self._dev_handle)
                return False

            self._connected = True
            logger.info(f"CAN 设备已连接: {dev_name} ch{chn} {baud}bps")
            return True
        except Exception as e:  # noqa: BLE001 - 硬件调用失败统一处理
            logger.error(f"CAN 设备打开异常: {e}")
            return False

    def _set_baudrate(self, chn: int, baud: int) -> bool:
        try:
            self._zcan.SetValue(self._dev_handle, f"{chn}/canfd_abit_baud_rate", str(baud))
            self._zcan.SetValue(self._dev_handle, f"{chn}/canfd_dbit_baud_rate", str(baud))
            return True
        except Exception as e:  # noqa: BLE001
            logger.error(f"设置波特率失败: {e}")
            return False

    def close(self) -> bool:
        self.stop_receiving()
        if self._zcan is None or self._dev_handle == 0:
            self._connected = False
            return True
        try:
            if self._chn_handle:
                self._zcan.ResetCAN(self._chn_handle)
            self._zcan.CloseDevice(self._dev_handle)
            self._connected = False
            self._chn_handle = 0
            self._dev_handle = 0
            logger.info("CAN 设备已关闭")
            return True
        except Exception as e:  # noqa: BLE001
            logger.error(f"关闭 CAN 设备失败: {e}")
            return False

    # ---- 接收 ----
    def start_receiving(self, callback: Callable[[CANFrame], None]) -> bool:
        if not self._connected:
            logger.error("设备未连接")
            return False
        self._callback = callback
        self._running = True
        self._thread = threading.Thread(target=self._receive_loop, daemon=True)
        self._thread.start()
        logger.info("开始接收 CAN 数据")
        return True

    def stop_receiving(self) -> None:
        self._running = False
        if self._thread and self._thread.is_alive():
            self._thread.join(timeout=2)
        self._callback = None

    def _receive_loop(self) -> None:
        from can_driver.zlgcan_sdk import ZCAN_TYPE_CAN

        while self._running:
            try:
                num = self._zcan.GetReceiveNum(self._chn_handle, ZCAN_TYPE_CAN)
                if num > 0:
                    msgs, got = self._zcan.Receive(self._chn_handle, num)
                    ts = time.time()
                    for i in range(got):
                        frame = msgs[i].frame
                        data = bytes(frame.data[:frame.can_dlc])
                        if self._callback:
                            self._callback(CANFrame(frame.can_id, data, ts))
                else:
                    # 无数据时让出 GIL：busy-spin 会占满一核并饿死 GUI 线程
                    time.sleep(0.002)
            except Exception as e:  # noqa: BLE001
                logger.error(f"硬件接收异常: {e}")
                time.sleep(0.05)

    # ---- 发送（预留）----
    def send(self, can_id: int, data: bytes) -> bool:
        if not self._connected or self._zcan is None:
            return False
        from can_driver.zlgcan_sdk import ZCAN_Transmit_Data

        msg = ZCAN_Transmit_Data()
        msg.transmit_type = 0
        msg.frame.eff = 0
        msg.frame.rtr = 0
        msg.frame.can_id = can_id
        msg.frame.can_dlc = len(data)
        for i, b in enumerate(data):
            msg.frame.data[i] = b
        try:
            return self._zcan.Transmit(self._chn_handle, msg, 1) == 1
        except Exception as e:  # noqa: BLE001
            logger.error(f"发送 CAN 数据失败: {e}")
            return False