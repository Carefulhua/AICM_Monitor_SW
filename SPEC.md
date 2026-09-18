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
./run.sh                      # 按 config/app.json 的 simulation 字段预选数据源（false=硬件, true=仿真）
./run.sh --dbc <path>         # 指定 DBC
```

- **数据源切换**: 主界面「数据源」下拉选「ZLG CAN 硬件」；无 DLL/设备时自动回退仿真。
- **故障演示**: 仿真器每 30s 的第 12~15s 注入故障（IGN 电压异常、Cam3 链路断、HSD P23.2、LSD P32.5、BTS3410_LSD2_EC=3），LED 变红、异常计数上升。
- **记录/导出**: 「记录」开关控制落库；「导出CSV」输出 `*_signals.csv`（解码值）与 `*_frames.csv`（原始帧）。

## 5.1 硬件物理通讯（ZLG CAN）

采用**两套可切换的驱动库**（由 UI「适配器」下拉选择，见下）：周立功**官方 x64 二次开发库** `can_driver/zlgcan.dll`（PE32+ x86-64，310272 B，md5 `a1f52874118ef3c0b799cd2d569e796c`）+ `can_driver/kerneldlls/`（官方 x64，含 `devices_property/`），取自官方「CAN(FD)接口卡二次开发接口函数库」`CAN_lib.zip`（zlg.cn 下载页 id/223，2025-08-15）；以及智嵌物联 ZQWL 适配器用的 `can_driver/zlgcan_zqwl.dll`（103936 B，md5 `0d8b9ba207b781eed79695845757b6ff`，USB-CDC/串口，自包含）。设备参数表为 `can_driver/dev_info.json`。

> **历史坑（务必不要回退）**：本仓库早期捆绑的 64 位 `zlgcan.dll`（103936 B）不是周立功官方库，而是第三方（智嵌物联 ZQWL）为 USB-CDC/虚拟串口适配器写的 ZCAN 兼容库——导入表只有串口 API（`BuildCommDCBW`/`SetCommState`/`PurgeComm`/`ReadFile`/`WriteFile`）+ SetupAPI，**没有任何 `WinUsb_*`**。而 USBCANFD 系列是 WinUSB 设备（`Service=WINUSB`，无厂商 `.sys`），所以那份 DLL 对 200U 永远 `OpenDevice` 失败：枚举不到设备 → 退化为打开 `\\.\COM0` → `m_hComm == INVALID_HANDLE_VALUE` → 打印 `Device Open Error.`。官方库则通过 `kerneldlls/USBCANFD.dll`（导入 `WINUSB.DLL` + `WinUsb_Initialize/ReadPipe/WritePipe/...`）真实驱动设备。该库现已另存为 `can_driver/zlgcan_zqwl.dll` 专供 ZQWL 适配器使用（型号→库映射见 `zlg_can.py` 的 `_DEVICE_LIB`），不要再把它当官方库用。

- 驱动: `can_driver/zlg_can.py`（本驱动）+ `can_driver/zlgcan_sdk.py`（官方接口封装，结构 ABI 与官方一致）。
- 二进制: `can_driver/zlgcan.dll`（官方 x64）、`can_driver/kerneldlls/`（官方 x64，`zlgcan.dll` 用 `LoadLibraryA`+`GetModuleFileNameA` 按自身目录加载，必须与 DLL 同目录）、`can_driver/zlgcan_zqwl.dll`（ZQWL 库，自包含、不加载 kerneldlls，但依赖同目录的 140 系列运行库）、`can_driver/msvcr120.dll` + `can_driver/msvcp120.dll`（官方库依赖的 VS2013 运行库；`kerneldlls/ZPSCANFD.dll` 另需已随包的 140 系列）、`can_driver/dev_info.json`。实测：把 DLL 自己的目录放一份无效 `msvcr120.dll` 会导致加载失败（`WinError 193`），证明依赖确实按 DLL 自身目录解析——故随包分发即可，无需目标机预装运行库。
- 流程（与官方 demo 一致）：`OpenDevice(dev_type, idx) -> SetValue(通道参数) -> InitCAN -> StartCAN -> GetReceiveNum/Receive`。
- 通道参数 key（取自 `zlgcan.dll` 属性表，通道 0-3）：CANFD 设备为 `{chn}/canfd_standard`、`{chn}/canfd_abit_baud_rate`、`{chn}/canfd_dbit_baud_rate`（bps 字符串，数据域不能复用仲裁域的值）；CAN 设备为 `{chn}/baud_rate`。任一步 SetValue 返回非 1 即中止连接并记录具体 key。
- `InitCAN` 配置：`acc_code=0`、`acc_mask=0xFFFFFFFF`（手册：屏蔽码全 1 = 全部接收）；USBCANFD-200U 会忽略 `acc_code/acc_mask`，过滤由 GetIProperty 负责。
- 终端电阻不在属性表内，由 `ZCAN_SetResistanceEnable` 单独控制，本工程不改动设备默认值。
- 接收：经典帧走 `GetReceiveNum(chn, ZCAN_TYPE_CAN)` + `Receive`（CANFD 通道同样适用，DBC 全部为 8 字节经典帧）。
- 配置: `config/app.json` 的 `zlg` 块（device/device_index/channel/baudrate/data_baudrate），`device` 同时决定启动时「适配器」下拉的初始选中项。型号→库映射在 `zlg_can.py` 的 `_DEVICE_LIB`（`ZQWL-*` → ZQWL 库，其余 → 官方库）；`ADAPTERS` 定义下拉项（自动探测 / 周立功 USBCANFD-200U / 智嵌 ZQWL-UCANFD-100E），`AUTO_DEVICES` 定义自动探测顺序（先官方库、后 ZQWL 库，后者 OpenDevice 会向控制台打印调试串）。`ZLGCANDevice.connect(device)` 传 `None` 时依次探测各适配器，每项失败均记日志。
- 支持的设备型号见 `dev_info.json`: USBCANFD-200U/100U/MINI、USBCAN-E/2E-U、USBCAN-I/II。

Windows 上物理连通自检（连好 USB-CAN，装好 ZLG 驱动后执行）:
```
venv\Scripts\python tools/can_self_test.py --device USBCANFD-200U --baud 500000
```
自检逐步报告：加载驱动库 → 打开设备 → 初始化通道 → 接收报文，末尾打印"自检通过"；`--device auto` 可自动探测适配器。

## 6. 测试

```bash
venv/bin/python tests/smoke_ui.py     # 无头冒烟：解码/故障注入/恢复/CSV导出
venv/bin/python tests/render_ui.py    # offscreen 渲染各页截图为 data/shots/*.png
venv/bin/python tests/analyze_shots.py # 像素级验证（LED 颜色/曲线/深色主题）
```

## 7. 已知限制

- **硬件模式需在 Windows 上运行**：zlgcan.dll 为 Windows 动态库；Linux/WSL 下驱动优雅失败并回退仿真。
- **USB-CAN 驱动**：需在 Windows 上安装周立功官方 USB 驱动（USBCANFD 系列是 WinUSB 设备，本机 inf 为 `oem42.inf`），设备管理器应显示「USBCANFD-200U」。该驱动是系统级 WinUSB 驱动，**不能**随 exe 内嵌分发，换机器需单独安装。
- **部署**：`can_driver/` 必须整体随 exe 分发（`zlgcan.dll` 按自身目录查找 `kerneldlls/` 与 VC 运行库）；如 Python 为 32 位需改用官方 `zlgcan_x86`。
- `index.html` 为早期 HTML 演示，与本应用无关，保留未动。
