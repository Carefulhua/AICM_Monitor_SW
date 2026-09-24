"""PCAN adapter (PEAK-System PCAN-Basic API).

Loads PCANBasic.dll via ctypes, implements same interface as ZLGCANDevice:
    open() / close() / start_receiving(cb) / stop_receiving() / send(id, data)
    is_connected / device_summary
"""
from __future__ import annotations

import ctypes as _ct
import logging
import sys
import threading
import time
from pathlib import Path
from typing import Callable, Optional

logger = logging.getLogger(__name__)

# PCAN-Basic constants (aligned with PCANBasic.h)
PCAN_ERROR_OK = 0x00000
PCAN_ERROR_QRCVEMPTY = 0x00020

PCAN_USBBUS1 = 0x51
PCAN_USBBUS2 = 0x52
PCAN_USBBUS3 = 0x53
PCAN_USBBUS4 = 0x54
PCAN_USBBUS5 = 0x55
PCAN_USBBUS6 = 0x56
PCAN_USBBUS7 = 0x57
PCAN_USBBUS8 = 0x58
PCAN_NONEBUS = 0x00

CHANNEL_MAP = {
    "PCAN_USBBUS1": PCAN_USBBUS1, "PCAN_USBBUS2": PCAN_USBBUS2,
    "PCAN_USBBUS3": PCAN_USBBUS3, "PCAN_USBBUS4": PCAN_USBBUS4,
    "PCAN_USBBUS5": PCAN_USBBUS5, "PCAN_USBBUS6": PCAN_USBBUS6,
    "PCAN_USBBUS7": PCAN_USBBUS7, "PCAN_USBBUS8": PCAN_USBBUS8,
}
CHANNEL_NAMES = {v: k for k, v in CHANNEL_MAP.items()}

# BTR0BTR1 register values (classic CAN baud rates)
PCAN_BAUD_1M   = 0x0014
PCAN_BAUD_800K = 0x0016
PCAN_BAUD_500K = 0x001C
PCAN_BAUD_250K = 0x011C
PCAN_BAUD_125K = 0x031C
PCAN_BAUD_100K = 0x432F
PCAN_BAUD_50K  = 0x472F
PCAN_BAUD_20K  = 0x532F
PCAN_BAUD_10K  = 0x672F

BAUD_MAP = {
    1000000: PCAN_BAUD_1M, 800000: PCAN_BAUD_800K, 500000: PCAN_BAUD_500K,
    250000: PCAN_BAUD_250K, 125000: PCAN_BAUD_125K, 100000: PCAN_BAUD_100K,
    50000: PCAN_BAUD_50K, 20000: PCAN_BAUD_20K, 10000: PCAN_BAUD_10K,
}

PCAN_MESSAGE_STANDARD = 0x00


class _TPCANMsg(_ct.Structure):
    _fields_ = [
        ("ID", _ct.c_ulong),
        ("MSGTYPE", _ct.c_ubyte),
        ("LEN", _ct.c_ubyte),
        ("DATA", _ct.c_ubyte * 8),
    ]


class _TPCANMsgFD(_ct.Structure):
    _fields_ = [
        ("ID", _ct.c_ulong),
        ("MSGTYPE", _ct.c_ubyte),
        ("DLC", _ct.c_ubyte),
        ("FD_LENGTH", _ct.c_ushort),
        ("DATA", _ct.c_ubyte * 64),
    ]


class _TPCANTimestamp(_ct.Structure):
    _fields_ = [
        ("millis", _ct.c_ulong),
        ("millis_overflow", _ct.c_ushort),
        ("micros", _ct.c_ushort),
    ]


_FD_DLC_MAP = {d: i for i, d in enumerate(
    [0, 1, 2, 3, 4, 5, 6, 7, 8, 12, 16, 20, 24, 32, 48, 64])}
_FD_LEN_MAP = {v: k for k, v in _FD_DLC_MAP.items()}


class PCANAdapter:
    """PCAN-Basic adapter. config:
    {"channel": "PCAN_USBBUS1", "baudrate": 500000, "fd": false}
    """

    def __init__(self, config: Optional[dict] = None):
        self.config = dict(config or {})
        self._dll = None
        self._handle: int = 0
        self._connected = False
        self._callback: Optional[Callable] = None
        self._running = False
        self._thread: Optional[threading.Thread] = None
        self._hw_info = ""
        self._use_fd = bool(self.config.get("fd", False))

    def load_driver(self) -> bool:
        sdk_dir = (Path(sys._MEIPASS) / "can_driver"
                   if getattr(sys, "frozen", False)
                   else Path(__file__).resolve().parent)
        dll_name = "PCANBasic.dll"
        dll_path = sdk_dir / dll_name
        search = [dll_path]
        if not dll_path.exists():
            search.append(Path(dll_name))
        for p in search:
            if p.exists():
                try:
                    self._dll = _ct.windll.LoadLibrary(str(p))
                    logger.info(f"loaded PCANBasic: {p}")
                    return True
                except OSError as e:
                    logger.warning(f"load {p} failed: {e}")
        logger.error("PCANBasic.dll not found")
        return False

    def _bind(self):
        if self._dll is None:
            return
        d = self._dll
        d.CAN_Initialize.argtypes = [_ct.c_ushort, _ct.c_ushort,
                                      _ct.c_ubyte, _ct.c_uint, _ct.c_ushort]
        d.CAN_Initialize.restype = _ct.c_long
        d.CAN_InitializeFD.argtypes = [_ct.c_ushort, _ct.c_char_p]
        d.CAN_InitializeFD.restype = _ct.c_long
        d.CAN_Uninitialize.argtypes = [_ct.c_ushort]
        d.CAN_Uninitialize.restype = _ct.c_long
        d.CAN_Reset.argtypes = [_ct.c_ushort]
        d.CAN_Reset.restype = _ct.c_long
        d.CAN_GetStatus.argtypes = [_ct.c_ushort]
        d.CAN_GetStatus.restype = _ct.c_long
        d.CAN_Read.argtypes = [_ct.c_ushort, _ct.POINTER(_TPCANMsg),
                                _ct.POINTER(_TPCANTimestamp)]
        d.CAN_Read.restype = _ct.c_long
        d.CAN_ReadFD.argtypes = [_ct.c_ushort, _ct.POINTER(_TPCANMsgFD)]
        d.CAN_ReadFD.restype = _ct.c_long
        d.CAN_Write.argtypes = [_ct.c_ushort, _ct.POINTER(_TPCANMsg)]
        d.CAN_Write.restype = _ct.c_long
        d.CAN_WriteFD.argtypes = [_ct.c_ushort, _ct.POINTER(_TPCANMsgFD)]
        d.CAN_WriteFD.restype = _ct.c_long
        d.CAN_GetValue.argtypes = [_ct.c_ushort, _ct.c_ubyte,
                                    _ct.c_void_p, _ct.c_ulong]
        d.CAN_GetValue.restype = _ct.c_long

    def _resolve_channel(self) -> int:
        ch = self.config.get("channel", "PCAN_USBBUS1")
        if isinstance(ch, int):
            return ch
        s = str(ch).upper().strip()
        if s in CHANNEL_MAP:
            return CHANNEL_MAP[s]
        try:
            n = int(s)
            if 1 <= n <= 8:
                return 0x50 + n
        except ValueError:
            pass
        return PCAN_USBBUS1

    def connect(self, device: Optional[str] = None) -> bool:
        if not self.load_driver():
            return False
        self._bind()
        handle = self._resolve_channel()
        baud = int(self.config.get("baudrate", 500000))
        try:
            if self._use_fd:
                fd_br = self.config.get("fd_bitrate",
                    "f_clock_mhz=80,nom_brp=10,nom_tseg1=5,nom_tseg2=2,"
                    "nom_sjw=1,data_brp=4,data_tseg1=7,data_tseg2=2,data_sjw=1")
                ret = self._dll.CAN_InitializeFD(handle, fd_br.encode("ascii"))
            else:
                btr = BAUD_MAP.get(baud)
                if btr is None:
                    logger.error(f"unsupported baudrate: {baud}")
                    return False
                ret = self._dll.CAN_Initialize(handle, btr, 0, 0, 0)
            if ret != PCAN_ERROR_OK:
                err = self._get_error_text(ret)
                logger.error(f"CAN_Initialize failed: 0x{ret:05X} {err}")
                return False
            self._handle = handle
            self._connected = True
            name = CHANNEL_NAMES.get(handle, f"0x{handle:02X}")
            self._hw_info = f"PCAN-USB {name}"
            logger.info(f"PCAN connected: {name} {baud}bps"
                        + (" (FD)" if self._use_fd else ""))
            return True
        except Exception as e:
            logger.error(f"PCAN connect exception: {e}")
            return False

    def _get_error_text(self, error: int) -> str:
        if self._dll is None:
            return ""
        buf = _ct.create_string_buffer(256)
        self._dll.CAN_GetErrorText(error, 0, buf)
        return buf.value.decode("ascii", errors="replace")

    @property
    def is_connected(self) -> bool:
        return self._connected

    @property
    def device_summary(self) -> str:
        return self._hw_info

    def close(self) -> bool:
        self.stop_receiving()
        if self._dll and self._handle:
            try:
                self._dll.CAN_Uninitialize(self._handle)
            except Exception:
                pass
        self._connected = False
        self._handle = 0
        logger.info("PCAN closed")
        return True

    def start_receiving(self, callback: Callable) -> bool:
        if not self._connected:
            return False
        self._callback = callback
        self._running = True
        self._thread = threading.Thread(target=self._loop, daemon=True)
        self._thread.start()
        logger.info("PCAN receiving started")
        return True

    def stop_receiving(self) -> None:
        self._running = False
        if self._thread and self._thread.is_alive():
            self._thread.join(timeout=2)
        self._callback = None

    def _loop(self) -> None:
        from can_driver.zlg_can import CANFrame
        while self._running:
            try:
                if self._use_fd:
                    self._poll_fd(CANFrame)
                else:
                    self._poll_can(CANFrame)
            except Exception as e:
                logger.error(f"PCAN receive error: {e}")
                time.sleep(0.05)

    def _poll_can(self, CANFrame) -> None:
        msg = _TPCANMsg()
        ts = _TPCANTimestamp()
        while self._running:
            ret = self._dll.CAN_Read(self._handle, _ct.byref(msg), _ct.byref(ts))
            if ret == PCAN_ERROR_QRCVEMPTY:
                time.sleep(0.002)
                break
            if ret != PCAN_ERROR_OK:
                time.sleep(0.005)
                break
            if self._callback:
                data = bytes(msg.DATA[:msg.LEN])
                self._callback(CANFrame(msg.ID, data, time.time()))

    def _poll_fd(self, CANFrame) -> None:
        msg = _TPCANMsgFD()
        while self._running:
            ret = self._dll.CAN_ReadFD(self._handle, _ct.byref(msg))
            if ret == PCAN_ERROR_QRCVEMPTY:
                time.sleep(0.002)
                break
            if ret != PCAN_ERROR_OK:
                time.sleep(0.005)
                break
            if self._callback:
                length = _FD_LEN_MAP.get(msg.DLC, msg.DLC)
                data = bytes(msg.DATA[:length])
                self._callback(CANFrame(msg.ID, data, time.time()))

    def send(self, can_id: int, data: bytes) -> bool:
        if not self._connected or self._dll is None:
            return False
        try:
            if self._use_fd:
                msg = _TPCANMsgFD()
                msg.ID = can_id
                msg.MSGTYPE = PCAN_MESSAGE_STANDARD
                msg.DLC = _FD_DLC_MAP.get(len(data), 8)
                msg.FD_LENGTH = len(data)
                for i, b in enumerate(data[:64]):
                    msg.DATA[i] = b
                return self._dll.CAN_WriteFD(
                    self._handle, _ct.byref(msg)) == PCAN_ERROR_OK
            else:
                msg = _TPCANMsg()
                msg.ID = can_id
                msg.MSGTYPE = PCAN_MESSAGE_STANDARD
                msg.LEN = min(len(data), 8)
                for i, b in enumerate(data[:8]):
                    msg.DATA[i] = b
                return self._dll.CAN_Write(
                    self._handle, _ct.byref(msg)) == PCAN_ERROR_OK
        except Exception as e:
            logger.error(f"PCAN send failed: {e}")
            return False
