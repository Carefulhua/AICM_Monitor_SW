# AICM-NT400 DVtest CAN 监控上位机规格文档

## 1. 项目概述

- **项目名称**: AICM-NT400 DVtest 监控上位机
- **项目类型**: 桌面监控软件（纯监控 + 曲线 + 记录导出，不发送报文）
- **用途**: 博雷顿控制器 Ares AICM-NT400 设计验证测试（DVtest）期间的 CAN 总线实时监控
- **协议来源**: `dbc/DVtest.dbc`（14 条报文 / 191 信号）
- **参考实现**: CANoe 工程 `DV_TEST`（.xvp 面板布局）

## 2. 技术栈

- **语言**: Python 3.12+
- **GUI框架**: PyQt5 5.15 + Fusion 深色主题
- **图表库**: PyQtGraph 0.14（实时滚动曲线）
- **CAN通信**: 仿真器（无硬件自测）/ ZLG USB-CAN 接口库（硬件模式）
- **数据存储**: SQLite（WAL）+ CSV 导出

## 3. CAN 通讯协议

### 3.1 报文总览

14 条报文全部为 ADCU→总线 TX，8 字节，100ms 周期：

| CAN ID | 报文名 | 内容 |
|--------|--------|------|
| 0x650 | MCUVoltageData1 | AD1/IGN/CAN0_INH/TBOX_WP 电压 |
| 0x651 | MCUVoltageData2 | VCC_12V/AD2/VCC_3V3/VDD_1V25 电压 |
| 0x652 | MCUVoltageData3 | VBATT_P/DC17V/DC5V/DV12VGMSL 电压 |
| 0x653 | MCUVoltageData4 | DC3V3/VBATT_SOC_P/SYS_VIN_SV/DC3V3S 电压 |
| 0x654 | MCUVoltageData5 | DC17VHV/DC5VMV/DC1V8S/DC5V0S 电压 |
| 0x655 | MCUTempData | SOC_TEMP/TEMP5152 温度 + 全部电压状态位(22个) |
| 0x656 | SocTXStatus | Cam0-2 三状态+FPS、json_msg_missing |
| 0x657 | SocTXStatus1 | Cam3-10 FPS |
| 0x658 | SocTXStatus2 | I2C Des/Ser(11路)、SpiR、Rs232、RS485、SsdRw、Rc 计数 |
| 0x659 | SocTXStatus3 | TempTj/TempGpu/TempCpu/TempSoc/TempSsd、error_count |
| 0x65A | McuLSDStatus | LSD P32.2-5 状态、BTT3050/BTS3410 错误计数 |
| 0x65B | Mcu_USV_Status | RS485/SPI 状态与收发错误计数、MCU/SOC 电压状态 |
| 0x65C | McuHSDStatus | HSD P23.0-6 状态 + HSD1-7 电流（4bit+4bit 编码） |
| 0x65D | McuCanStatus | CAN1-4 状态与错误计数 |

### 3.2 数值编码

| 类型 | 编码 | 物理值公式 |
|------|------|-----------|
| 电压/温度 | `XXX_AI_i`（整数字节）+ `XXX_AI_f`（小数字节） | `V = i + f/256` |
| HSD 电流 | `HSDn_adc_i`（低 4 位）+ `HSDn_adc_f`（高 4 位） | `A = i + f/16` |
| Rc 滚动计数 | 16bit 无符号 | 直接读取 |

### 3.3 状态位语义

| 信号族 | 0 | 1 | 2 |
|--------|---|---|---|
| 电压状态（AD1_Status 等） | 异常 | 正常 | - |
| HSD_Status_P23x | 异常 | 正常 | - |
| Cam*Linklock/Videolock/Crc、json_msg_missing | 异常/缺失 | 正常 | - |
| LSD_Status_P32x | **正常** | 异常 | - |
| CAN1-4_Status | **正常** | 异常 | - |
| MCU_V_Status / SOC_V_Status | - | 正常(仅1位) | - |
| RS485_Status / SPI_Status | 正常 | 接收异常 | 发送异常 |

> 反相语义（LSD/CAN/USV 0=正常）由 `tools/gen_signals.py` 依据 VAL_ 定义自动推导，写入 `config/signals.json` 的 `status` 表。

## 4. 架构

```
main.py                    入口（加载配置、构建 Decoder/BusModel/MainWindow）
config/app.json            运行配置（dbc/signals/波特率/超时/仿真开关/数据库）
config/signals.json        生成配置（191信号/29合并通道/100状态定义）
tools/gen_signals.py       配置生成器（输入 DVtest_output.xlsx + dbc）
data/
  dbc_parser.py            DBC 解析（14 报文/191 信号）
  decoder.py               信号解码 + 状态语义判定
  model.py                 BusModel：跨报文融合 + 超时/帧统计（线程安全）
  storage.py               SQLite 落库 + CSV 导出
can_driver/
  simulator.py             无硬件仿真器（100ms 周期 + 周期性故障注入）
  zlg_can.py               ZLG USB-CAN 硬件驱动（仿真/硬件双模式）
ui/
  main_window.py           主窗口（连接/启动/记录/导出控制 + 状态栏）
  widgets.py               通用控件（Led/ValueCard/LedCell/StatusGroup/CounterCard）
  panel_overview.py        总览（20 电压卡 + 2 温度卡 + 报文健康 LED + 异常计数）
  panel_camera.py          相机（11 路 × 3 状态 LED + FPS + Rc + json 缺失）
  panel_io.py              IO 状态（HSD/LSD/USV/CAN/I2C 组 + 错误计数）
  panel_curves.py          曲线（电压/板温/FPS 三子图，通道勾选）
  panel_log.py             报文日志（时间/ID/报文/hex/解析值，超时红显）
```

**线程模型**: CAN 接收线程只调用 `BusModel.record()`（纯数据操作）；Qt 控件与 SQLite 仅在主线程 100ms 定时器 `on_refresh` 中访问（帧经队列排空）。

## 5. 运行

```bash
./run.sh                      # 仿真模式（无硬件自测，config/app.json simulation=true）
./run.sh --dbc <path>         # 指定 DBC
```

- **数据源切换**: 主界面「数据源」下拉选「ZLG CAN 硬件」；无 DLL/设备时自动回退仿真。
- **故障演示**: 仿真器每 30s 的第 12~15s 注入故障（IGN 电压异常、Cam3 链路断、HSD P23.2、LSD P32.5、BTS3410_LSD2_EC=3），LED 变红、异常计数上升。
- **记录/导出**: 「记录」开关控制落库；「导出CSV」输出 `*_signals.csv`（解码值）与 `*_frames.csv`（原始帧）。

## 5.1 硬件物理通讯（ZLG CAN）

整合自旧 CAN 工具（NXP 48V 工程）的已验证方案：`zlgcan.dll`（周立功 V1.18 官方 64 位库）+ `dev_info.json` 设备参数表。

- 驱动: `can_driver/zlg_can.py`（本驱动）+ `can_driver/zlgcan_sdk.py`（官方接口封装，结构 ABI 与官方一致）。
- 二进制: `can_driver/zlgcan.dll`（与旧工具捆绑版本 MD5 一致）、`can_driver/dev_info.json`。
- 流程（与官方 demo 一致）：`OpenDevice(dev_type, idx) -> SetValue(通道波特率) -> InitCAN -> StartCAN -> GetReceiveNum/Receive`。
- 配置: `config/app.json` 的 `zlg` 块（device/device_index/channel/baudrate）。
- 支持的设备型号见 `dev_info.json`: USBCANFD-200U/100U/MINI、USBCAN-E/2E-U、USBCAN-I/II。

Windows 上物理连通自检（连好 USB-CAN，装好 ZLG 驱动后执行）:
```
venv\Scripts\python tools/can_self_test.py --device USBCANFD-200U --baud 500000
```
自检逐步报告：加载 dll → 打开设备 → 初始化通道 → 接收报文，末尾打印"自检通过"。

## 6. 测试

```bash
venv/bin/python tests/smoke_ui.py     # 无头冒烟：解码/故障注入/恢复/CSV导出
venv/bin/python tests/render_ui.py    # offscreen 渲染各页截图为 data/shots/*.png
venv/bin/python tests/analyze_shots.py # 像素级验证（LED 颜色/曲线/深色主题）
```

## 7. 已知限制

- **硬件模式需在 Windows 上运行**：zlgcan.dll 为 Windows 动态库；Linux/WSL 下驱动优雅失败并回退仿真。
- **USB-CAN 驱动**：首次使用需在 Windows 上安装 ZLG 官方 USB 驱动（zlgcan.dll 厂商内核驱动），并保持 USB-CAN 在线。
- **部署**：Windows 运行时 zlgcan.dll 已随工程放在 `can_driver/`，无需额外拷贝；如 Python 为 32 位需改用 32 位 zlgcan.dll。
- `index.html` 为早期 HTML 演示，与本应用无关，保留未动。
