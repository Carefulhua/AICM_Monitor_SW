"""DVtest 报文仿真器。

无硬件时按真实协议 100ms 周期生成 17 条报文，用于上位机自测与演示。
部分状态（如 Cam3 链接、IGN 电压、LSD、HSD 过载）会周期性地模拟异常，便于验证报警功能。
"""
from __future__ import annotations

import math
import threading
import time
from typing import Callable, Optional

from data.dbc_parser import Database, load_dbc
from can_driver.zlg_can import CANFrame

CYCLE = 0.1


def encode_signal(data: bytearray, start_bit: int, length: int, value: int) -> None:
    for i in range(length):
        bit = start_bit + i
        if (value >> i) & 1:
            data[bit // 8] |= 1 << (bit % 8)
        else:
            data[bit // 8] &= ~(1 << (bit % 8))


class DVTestSimulator:
    def __init__(self, db: Database, cycle: float = CYCLE):
        self.db = db
        self.cycle = cycle
        self._running = False
        self._thread: Optional[threading.Thread] = None
        self._callback: Optional[Callable[[CANFrame], None]] = None
        self._connected = False
        self._t0 = 0.0
        self._hsd_mask = 0x00  # 0x680 高边开关掩码, 默认全关(与UI按钮初始一致)

    def open(self, *args, **kwargs) -> bool:
        self._connected = True
        return True

    def close(self) -> bool:
        self.stop_receiving()
        self._connected = False
        return True

    @property
    def is_connected(self) -> bool:
        return self._connected

    def start_receiving(self, callback: Callable[[CANFrame], None]) -> bool:
        if not self._connected:
            return False
        self._callback = callback
        self._running = True
        self._t0 = time.time()
        self._thread = threading.Thread(target=self._loop, daemon=True)
        self._thread.start()
        return True

    def stop_receiving(self) -> None:
        self._running = False
        if self._thread and self._thread.is_alive():
            self._thread.join(timeout=2)
        self._callback = None

    def send(self, can_id: int, data: bytes) -> bool:
        if can_id == 0x680 and data:
            self._hsd_mask = data[1] & 0x7F
        return True

    def _loop(self) -> None:
        tick = 0
        while self._running:
            start = time.time()
            try:
                self._emit(tick)
            except Exception:
                pass
            tick += 1
            elapsed = time.time() - start
            time.sleep(max(0.0, self.cycle - elapsed))

    def _frame(self, msg_name: str, values: dict[str, int]) -> CANFrame:
        msg = next(m for m in self.db.messages.values() if m.name == msg_name)
        data = bytearray(msg.length)
        for sig_name, raw in values.items():
            sig = msg.signals[sig_name]
            encode_signal(data, sig.start_bit, sig.length, raw & ((1 << sig.length) - 1))
        return CANFrame(msg.frame_id, bytes(data), time.time())

    def _emit(self, tick: int) -> None:
        if self._callback is None:
            return
        t = self._t0 + tick * self.cycle
        # 周期性的异常注入：每 30 秒中第 12~15 秒模拟故障
        fault = (t % 30) > 12 and (t % 30) < 15

        def v(nominal: float, amp: float = 0.05, phase: float = 0.0,
              scale: int = 100) -> tuple[int, int]:
            val = nominal + amp * math.sin(2 * math.pi * 0.2 * (t + phase))
            return int(val), int(round((val - int(val)) * scale)) & 0xFF

        def pack(msg_name: str, **values: int) -> None:
            self._callback(self._frame(msg_name, values))

        pack("MCUVoltageData1",
             AD1_AI_i=v(12.1)[0], AD1_AI_f=v(12.1)[1],
             IGN_AI_i=v(12.4, 0.2)[0], IGN_AI_f=v(12.4, 0.2)[1],
             CAN0_INH_AI_i=v(11.9)[0], CAN0_INH_AI_f=v(11.9)[1],
             TBOX_WP_AI_i=v(12.2)[0], TBOX_WP_AI_f=v(12.2)[1])
        pack("MCUVoltageData2",
             VCC_12V_AI_i=v(12.1)[0], VCC_12V_AI_f=v(12.1)[1],
             AD2_AI_i=v(3.3)[0], AD2_AI_f=v(3.3)[1],
             VCC_3V3_AI_i=v(3.31)[0], VCC_3V3_AI_f=v(3.31)[1],
             VDD_1V25_AI_i=v(1.25, 0.01)[0], VDD_1V25_AI_f=v(1.25, 0.01)[1])
        pack("MCUVoltageData3",
             VBATT_P_AI_i=v(24.3, 0.3)[0], VBATT_P_AI_f=v(24.3, 0.3)[1],
             DC17V_AI_i=v(17.0, 0.1)[0], DC17V_AI_f=v(17.0, 0.1)[1],
             DC5V_AI_i=v(5.02, 0.02)[0], DC5V_AI_f=v(5.02, 0.02)[1],
             DV12VGMSL_AI_i=v(12.0, 0.05)[0], DV12VGMSL_AI_f=v(12.0, 0.05)[1])
        pack("MCUVoltageData4",
             DC3V3_AI_i=v(3.31, 0.01)[0], DC3V3_AI_f=v(3.31, 0.01)[1],
             VBATT_SOC_P_AI_i=v(24.1, 0.3)[0], VBATT_SOC_P_AI_f=v(24.1, 0.3)[1],
             SYS_VIN_SV_AI_i=v(3.29, 0.01)[0], SYS_VIN_SV_AI_f=v(3.29, 0.01)[1],
             DC3V3S_AI_i=v(3.30, 0.01)[0], DC3V3S_AI_f=v(3.30, 0.01)[1])
        pack("MCUVoltageData5",
             DC17VHV_AI_i=v(17.1, 0.1)[0], DC17VHV_AI_f=v(17.1, 0.1)[1],
             DC5VMV_AI_i=v(5.02, 0.02)[0], DC5VMV_AI_f=v(5.02, 0.02)[1],
             DC1V8S_AI_i=v(1.80, 0.01)[0], DC1V8S_AI_f=v(1.80, 0.01)[1],
             DC5V0S_AI_i=v(5.01, 0.02)[0], DC5V0S_AI_f=v(5.01, 0.02)[1])

        soc_temp_i, soc_temp_f = v(45, 2)
        temp5152_i, temp5152_f = v(55, 3)
        pack("MCUTempData",
             SOC_TEMP_AI_i=soc_temp_i, SOC_TEMP_AI_f=soc_temp_f,
             TEMP5152_AI_i=temp5152_i, TEMP5152_AI_f=temp5152_f,
             AD1_Status=1, IGN_Status=0 if fault else 1, CAN0_INH_Status=1,
             TBOX_WP_Status=1, VCC_12V_Status=1, AD2_Status=1, VCC_3V3_Status=1,
             VDD_1V25_Status=1, VBATT_P_Status=1, DC17V_Status=1, DC5V_Status=1,
             DV12VGMSL_Status=1, DC3V3_Status=1, VBATT_SOC_P_Status=1,
             SYSVIN_Status=1, DC3V3S_Status=1, DC17VHV_Status=1,
             DC5VMV_Status=1, DC1V8S_Status=1, DC5V0S_Status=1)

        cam_ok = [1] * 11
        if fault:
            cam_ok[3] = 0
        cam_bits = {}
        for i in range(11):
            cam_bits[f"Cam{i}Linklock"] = cam_ok[i]
            cam_bits[f"Cam{i}Videolock"] = cam_ok[i]
            cam_bits[f"Cam{i}Crc"] = cam_ok[i]
        fps = [30, 30, 30, 30, 25, 25, 25, 25, 30, 30, 30]
        pack("SocTXStatus",
             **cam_bits, json_msg_missing=0,
             Cam0FPS=fps[0], Cam1FPS=fps[1], Cam2FPS=fps[2])
        pack("SocTXStatus1",
             Cam3FPS=fps[3], Cam4FPS=fps[4], Cam5FPS=fps[5], Cam6FPS=fps[6],
             Cam7FPS=fps[7], Cam8FPS=fps[8], Cam9FPS=fps[9], Cam10FPS=fps[10])

        rc = tick & 0xFFFF
        pack("SocTXStatus2",
             I2cDes0=1, I2cSer0=1, I2cDes1=1, I2cSer1=1, I2cDes2=1, I2cSer2=1,
             I2cDes3=1, I2cSer3=1, I2cSer4=1, I2cSer5=1, I2cSer6=1,
             I2cSer7=1, I2cSer8=1, I2cSer9=1, I2cSer10=1,
             SpiR=1, Rs2320=1, Rs2321=1, RS485R=1, SsdRw=1, Rc=rc)
        pack("SocTXStatus3",
             TempTj=65, TempGpu=60, TempCpu=58, TempSoc012=55, TempSoc345=54,
             TempSsd01=42, TempSsd02=43, error_count=0)

        lsd_ok = 0 if not fault else 0
        pack("McuLSDStatus",
             LSD_Status_P322=0, LSD_Status_P323=0, LSD_Status_P324=0,
             LSD_Status_P325=1 if fault else 0,
             MCU_GPI1_DI=1, MCU_GPI2_DI=1,
             BTT3050_U1100_EC=0, BTT3050_U1101_EC=0,
             BTS3410_LSD1_EC=0, BTS3410_LSD2_EC=0 if not fault else 3,
             g_controllerState=1, g_thorState=1)
        pack("Mcu_USV_Status",
             RS485_Status=0, RS232_Status=0, SPI_Status=0, Rs485_Rev_Ec=0, Rs485_Trans_Ec=0,
             SPI_SetEB_Ec=0, SPI_Trans_Ec=0, SPI_Rev_Ec=0)
        currents = [(0.5, 0.4), (0.8, 0.6), (1.2, 1.0), (0.3, 0.2), (0.6, 0.5), (0.9, 0.7), (1.5, 1.3)]
        hsd = {"U1000_Test_Status": 1, "U1001_Test_Status": 8 if fault else 1}
        for i, (nom, amp) in enumerate(currents, start=1):
            ci, cf = v(nom, amp)
            hsd[f"HSD{i}_adc_i"] = ci & 0xF
            hsd[f"HSD{i}_adc_f"] = cf & 0xF
        pack("McuHSDStatus", **hsd)
        # 0x65F HSD_PORT_Status: 诊断回读状态，与开关使能无关；fault 时 P23.2 过载
        hsd_port = {f"HSD_Status_P23{i}": 3 if (fault and i == 2) else 0 for i in range(7)}
        pack("HSD_PORT_Status", **hsd_port)
        # 0x65E McuCpuLoad
        pack("McuCpuLoad", **{f"CPU{i}_Load": 20 + (i * 9 + tick // 20) % 55 for i in range(6)})
        pack("McuCanStatus",
             CAN1_Status=0, CAN2_Status=0, CAN3_Status=0, CAN4_Status=0,
             CAN1_EC=0, CAN2_EC=0, CAN3_EC=0, CAN4_EC=0)
