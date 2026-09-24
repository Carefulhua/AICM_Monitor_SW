"""CAN 硬件驱动：三套适配器库。

1. 周立功 USBCANFD/USBCAN：官方 x64 库（zlgcan.dll + kerneldlls，WinUSB）。
2. 智嵌物联 ZQWL：CDC 串口兼容库（zlgcan_zqwl.dll）。
3. PEAK PCAN：PCANBasic API（PCANBasic.dll）。

三者导出不同的 DLL API，但对上层暴露相同接口：
    open() / close() / start_receiving(cb) / stop_receiving() / send(id, data)
    is_connected / device_summary
回调运行在接收线程，只做纯数据层操作。
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

# ---- 驱动库选择 ----
# 官方周立功库：WinUSB 传输，支持 USBCANFD/USBCAN 系列（含 200U）。
# ZQWL 库：智嵌物联随适配器提供的 ZCAN 兼容库，USB-CDC/串口传输；自包含，不加载
# kerneldlls，且其 MSVC 依赖必须与自身同目录（实测：DLL 的依赖不会搜索上一级目录）。
_LIB_OFFICIAL = "official"
_LIB_ZQWL = "zqwl"
_DEVICE_LIB = {
    "ZQWL-UCANFD-100E": _LIB_ZQWL,
    "ZOWL-UCANFD-110E": _LIB_ZQWL,
}
_DLL_BY_LIB = {
    _LIB_OFFICIAL: "zlgcan.dll",
    _LIB_ZQWL: "zlgcan_zqwl.dll",
}

# UI「适配器」下拉项：(显示名, device 型号)
# device 为 None = 自动探测；PCAN 设备以 "PCAN:" 前缀标识
ADAPTERS = [
    ("自动探测", None),
    ("周立功 USBCANFD-200U", "USBCANFD-200U"),
    ("智嵌 ZQWL-UCANFD-100E", "ZQWL-UCANFD-100E"),
    ("PEAK PCAN-USBBUS1", "PCAN:PCAN_USBBUS1"),
]
# 自动探测顺序（仅 ZLG/ZQWL，不含 PCAN —— PCAN 无探测机制）
AUTO_DEVICES = ["USBCANFD-200U", "ZQWL-UCANFD-100E"]


def dll_path(device: str) -> Path:
    return _SDK_DIR / _DLL_BY_LIB[_DEVICE_LIB.get(device, _LIB_OFFICIAL)]


def is_pcan_device(device: str) -> bool:
    return device.startswith("PCAN:")


def make_adapter(config: dict, device: Optional[str] = None):
    """按 device 型号创建对应的适配器实例（ZLG/ZQWL -> ZLGCANDevice，PCAN -> PCANAdapter）。"""
    dev = device or config.get("device", "USBCANFD-200U")
    if is_pcan_device(dev):
        from can_driver.pcan_adapter import PCANAdapter
        channel = dev.split(":", 1)[1] if ":" in dev else "PCAN_USBBUS1"
        pcan_cfg = dict(config.get("pcan", {}))
        pcan_cfg["channel"] = channel
        return PCANAdapter(pcan_cfg)
    return ZLGCANDevice(config)


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
        self.config = dict(config or {})
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
    def load_driver(self, device: Optional[str] = None) -> bool:
        from can_driver.zlgcan_sdk import ZCAN

        name = device or self.config.get("device", "USBCANFD-200U")
        path = dll_path(name)
        if not path.exists():
            logger.error(f"{name} 缺少对应驱动库: {path}")
            return False
        try:
            self._zcan = ZCAN(str(path))
            logger.info(f"成功加载驱动库: {path} ({name})")
            return True
        except Exception as e:  # noqa: BLE001
            logger.error(f"加载驱动库失败: {path}: {e}")
            return False

    def connect(self, device: Optional[str] = None) -> bool:
        """按型号加载对应驱动库并打开设备；device 为 None 时依次自动探测各适配器。"""
        for name in ([device] if device else AUTO_DEVICES):
            self.config["device"] = name
            if not self.load_driver(name):
                continue
            if self.open():
                return True
            logger.warning(f"{name} 打开失败，尝试下一个适配器")
            self._dev_handle = 0
            self._chn_handle = 0
            self._connected = False
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
        data_baud = int(self.config.get("data_baudrate", 2000000))

        entry = self._dev_info.get(dev_name)
        if entry is None:
            logger.error(f"dev_info.json 中无设备型号: {dev_name}")
            return False
        dev_type = int(entry["dev_type"])
        is_canfd = bool(entry["chn_info"]["is_canfd"])
        chn_num = int(entry["chn_num"])
        if not 0 <= chn < chn_num:
            logger.error(f"{dev_name} 只有 {chn_num} 路通道, channel={chn} 越界")
            return False

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

            if not self._set_baudrate(chn, baud, data_baud, is_canfd):
                self._zcan.CloseDevice(self._dev_handle)
                return False

            cfg = ZCAN_CHANNEL_INIT_CONFIG()
            cfg.can_type = ZCAN_TYPE_CANFD if is_canfd else ZCAN_TYPE_CAN
            if is_canfd:
                cfg.config.canfd.mode = 0
                cfg.config.canfd.filter = 0
                cfg.config.canfd.acc_code = 0
                cfg.config.canfd.acc_mask = 0xFFFFFFFF  # 屏蔽码全 1 = 全部接收（手册推荐）
            else:
                cfg.config.can.mode = 0
                cfg.config.can.filter = 0
                cfg.config.can.acc_code = 0
                cfg.config.can.acc_mask = 0xFFFFFFFF  # 屏蔽码全 1 = 全部接收（手册推荐）

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
            rate = f"{baud}bps" if not is_canfd else f"仲裁{baud}bps/数据{data_baud}bps"
            logger.info(f"CAN 设备已连接: {dev_name} ch{chn} {rate}")
            return True
        except Exception as e:  # noqa: BLE001 - 硬件调用失败统一处理
            logger.error(f"CAN 设备打开异常: {e}")
            return False

    def _set_baudrate(self, chn: int, baud: int, data_baud: int, is_canfd: bool) -> bool:
        """按官方 demo 的 key 设置通道参数（值均为字符串）。

        手册：CAN 设备波特率 key 为 "{chn}/baud_rate"；CANFD 设备仲裁域为
        "{chn}/canfd_abit_baud_rate"、数据域为 "{chn}/canfd_dbit_baud_rate"
        （数据域取值 1M/2M/4M/5M，与仲裁域不同，不能复用仲裁域的值）。
        上述 key 均取自 zlgcan.dll 的属性表；终端电阻不在属性表内，
        由 ZCAN_SetResistanceEnable 单独设置，此处不改动设备默认值。
        """
        from can_driver.zlgcan_sdk import ZCAN_STATUS_OK

        items = [(f"{chn}/baud_rate", str(baud))]
        if is_canfd:
            items = [
                (f"{chn}/canfd_standard", "0"),
                (f"{chn}/canfd_abit_baud_rate", str(baud)),
                (f"{chn}/canfd_dbit_baud_rate", str(data_baud)),
            ]
        try:
            for path, value in items:
                ret = self._zcan.SetValue(self._dev_handle, path, value)
                if ret != ZCAN_STATUS_OK:
                    logger.error(f"设置 {path}={value} 失败: ret={ret}")
                    return False
                logger.info(f"设置 {path}={value} 成功")
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