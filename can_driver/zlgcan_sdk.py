"""ZLG CAN 设备 SDK 封装（zlgcan.dll，周立功 V1.18 官方接口）。

结构定义与调用方式取自官方 zlgcan.py 二次开发例程，保留原始 ctypes 布局以保证 ABI 兼容。
仅做三处安全调整：DLL 路径可配置、去掉调试打印、非 Windows 明确报错。
"""
from __future__ import annotations

import ctypes
import platform
from ctypes import Structure, Union, c_ubyte, c_uint, c_ulonglong, c_ushort, c_void_p

INVALID_DEVICE_HANDLE = 0
INVALID_CHANNEL_HANDLE = 0

# 设备类型（与 can_driver/dev_info.json 的 dev_type 一致）
ZCAN_USBCAN1 = c_uint(3)
ZCAN_USBCAN2 = c_uint(4)
ZCAN_USBCAN_E_U = c_uint(20)
ZCAN_USBCAN_2E_U = c_uint(21)
ZCAN_USBCAN_4E_U = c_uint(31)
ZCAN_USBCAN_8E_U = c_uint(34)
ZCAN_PCIE_CANFD_100U = c_uint(38)
ZCAN_PCIE_CANFD_200U = c_uint(39)
ZCAN_PCIE_CANFD_400U = c_uint(40)
ZCAN_USBCANFD_200U = c_uint(41)
ZCAN_USBCANFD_100U = c_uint(42)
ZCAN_USBCANFD_MINI = c_uint(43)
ZCAN_USBCANFD_400U = c_uint(201)
ZCAN_VIRTUAL_DEVICE = c_uint(99)

ZCAN_STATUS_ERR = 0
ZCAN_STATUS_OK = 1

ZCAN_TYPE_CAN = c_uint(0)
ZCAN_TYPE_CANFD = c_uint(1)


class ZCAN_DEVICE_INFO(Structure):
    _fields_ = [("hw_Version", c_ushort), ("fw_Version", c_ushort),
                ("dr_Version", c_ushort), ("in_Version", c_ushort),
                ("irq_Num", c_ushort), ("can_Num", c_ubyte),
                ("str_Serial_Num", c_ubyte * 20), ("str_hw_Type", c_ubyte * 40),
                ("reserved", c_ushort * 4)]

    def _text(self, arr):
        out = ""
        for c in arr:
            if c > 0:
                out += chr(c)
            else:
                break
        return out

    @property
    def can_num(self):
        return self.can_Num

    @property
    def serial(self):
        return self._text(self.str_Serial_Num)

    @property
    def hw_type(self):
        return self._text(self.str_hw_Type)

    def summary(self):
        return (f"硬件类型={self.hw_type} 序列号={self.serial} "
                f"通道数={self.can_Num} "
                f"硬件版本=V{self.hw_Version:02x} 固件版本=V{self.fw_Version:02x}")


class _ZCAN_CHANNEL_CAN_INIT_CONFIG(Structure):
    _fields_ = [("acc_code", c_uint), ("acc_mask", c_uint), ("reserved", c_uint),
                ("filter", c_ubyte), ("timing0", c_ubyte), ("timing1", c_ubyte),
                ("mode", c_ubyte)]


class _ZCAN_CHANNEL_CANFD_INIT_CONFIG(Structure):
    _fields_ = [("acc_code", c_uint), ("acc_mask", c_uint), ("abit_timing", c_uint),
                ("dbit_timing", c_uint), ("brp", c_uint), ("filter", c_ubyte),
                ("mode", c_ubyte), ("pad", c_ushort), ("reserved", c_uint)]


class _ZCAN_CHANNEL_INIT_CONFIG(Union):
    _fields_ = [("can", _ZCAN_CHANNEL_CAN_INIT_CONFIG),
                ("canfd", _ZCAN_CHANNEL_CANFD_INIT_CONFIG)]


class ZCAN_CHANNEL_INIT_CONFIG(Structure):
    _fields_ = [("can_type", c_uint), ("config", _ZCAN_CHANNEL_INIT_CONFIG)]


class ZCAN_CAN_FRAME(Structure):
    _fields_ = [("can_id", c_uint, 29), ("err", c_uint, 1), ("rtr", c_uint, 1),
                ("eff", c_uint, 1), ("can_dlc", c_ubyte), ("__pad", c_ubyte),
                ("__res0", c_ubyte), ("__res1", c_ubyte), ("data", c_ubyte * 8)]


class ZCAN_Receive_Data(Structure):
    _fields_ = [("frame", ZCAN_CAN_FRAME), ("timestamp", c_ulonglong)]


class ZCAN_Transmit_Data(Structure):
    _fields_ = [("frame", ZCAN_CAN_FRAME), ("transmit_type", c_uint)]


class ZCAN:
    """zlgcan.dll 接口封装。Windows 上加载成功后即可调用各方法。"""

    def __init__(self, dll_path="zlgcan.dll"):
        if platform.system() != "Windows":
            raise RuntimeError("zlgcan.dll 为 Windows 动态库，当前平台不支持硬件通讯")
        self._dll = ctypes.WinDLL(dll_path)
        self._dll.ZCAN_OpenDevice.restype = ctypes.c_longlong
        self._dll.ZCAN_InitCAN.restype = ctypes.c_longlong
        self._dll.ZCAN_StartCAN.restype = ctypes.c_longlong
        self._dll.ZCAN_ResetCAN.restype = ctypes.c_longlong

    def OpenDevice(self, device_type, device_index, reserved=0):
        return self._dll.ZCAN_OpenDevice(device_type, device_index, reserved)

    def CloseDevice(self, device_handle):
        return self._dll.ZCAN_CloseDevice(device_handle)

    def GetDeviceInf(self, device_handle):
        info = ZCAN_DEVICE_INFO()
        ret = self._dll.ZCAN_GetDeviceInf(device_handle, ctypes.byref(info))
        return info if ret == ZCAN_STATUS_OK else None

    def IsDeviceOnLine(self, device_handle):
        return self._dll.ZCAN_IsDeviceOnLine(device_handle)

    def SetValue(self, handle, path, value):
        self._dll.ZCAN_SetValue.restype = ctypes.c_longlong
        h = ctypes.c_ulonglong(handle)
        return self._dll.ZCAN_SetValue(h, ctypes.c_char_p(path.encode("utf-8")),
                                       ctypes.c_char_p(value.encode("utf-8")))

    def InitCAN(self, device_handle, can_index, init_config):
        return self._dll.ZCAN_InitCAN(device_handle, can_index,
                                      ctypes.byref(init_config))

    def StartCAN(self, chn_handle):
        return self._dll.ZCAN_StartCAN(ctypes.c_ulonglong(chn_handle))

    def ResetCAN(self, chn_handle):
        return self._dll.ZCAN_ResetCAN(ctypes.c_ulonglong(chn_handle))

    def ClearBuffer(self, chn_handle):
        return self._dll.ZCAN_ClearBuffer(ctypes.c_ulonglong(chn_handle))

    def GetReceiveNum(self, chn_handle, can_type=ZCAN_TYPE_CAN):
        return self._dll.ZCAN_GetReceiveNum(ctypes.c_ulonglong(chn_handle), can_type)

    def Transmit(self, chn_handle, msgs, count):
        return self._dll.ZCAN_Transmit(ctypes.c_ulonglong(chn_handle),
                                       ctypes.byref(msgs), count)

    def Receive(self, chn_handle, rcv_num, wait_time=-1):
        msgs = (ZCAN_Receive_Data * rcv_num)()
        ret = self._dll.ZCAN_Receive(ctypes.c_ulonglong(chn_handle),
                                     ctypes.byref(msgs), rcv_num,
                                     ctypes.c_int(wait_time))
        return msgs, ret