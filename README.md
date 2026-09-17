# AICM-NT4K DV Monitor

博雷顿控制器 Ares AICM-NT4K 设计验证测试（DV）CAN 总线实时监控上位机。

## 功能

- **总览面板**：报文健康（超时）指示、20 路电源电压卡片、MCU/SOC 电压状态、板温（SOC/5152/Tj/Gpu/Cpu/Soc012/Soc345/Ssd01/Ssd02）、CPU0-5 负载、异常通道计数
- **相机面板**：Cam0-10 Linklock/Videolock/Crc 状态矩阵、FPS 显示、链路计数、json 报文缺失指示
- **IO 状态面板**：HSD 高边驱动（U1000/U1001 自检 + HSD1-7 ADC + P23.0-6 端口诊断）、LSD 低边驱动、RS232/RS485/SPI/SSD/CAN/I2C 状态与错误计数
- **曲线面板**：电压/温度/CPU 负载实时滚动曲线（多通道可选）
- **报文面板**：CAN 帧日志、超时高亮、选中行 Ctrl+C 复制
- **发送面板**：原始帧 / DBC 报文两种发送方式，支持周期发送
- **测试模式**：一键周期下发 0x680 DVtest_Switch（DV 开关 + HSD 使能），关闭时下发全 0 复位
- **数据导出**：SQLite 持久化 + CSV 导出（支持时间范围筛选）
- **故障检测**：电压越限、通信错误自动标红

## 技术栈

| 组件 | 技术 |
|------|------|
| 语言 | Python 3.12+ |
| GUI | PyQt5 5.15 + Fusion 深色主题 |
| 图表 | PyQtGraph 0.14（实时滚动曲线） |
| CAN 通信 | ZLG USB-CAN 接口库 / 仿真器模式 |
| 数据存储 | SQLite (WAL) + CSV 导出 |

## 项目结构

```
├── main.py                 # 入口
├── run.bat                 # Windows 启动脚本
├── run.sh                  # Linux 启动脚本
├── config/
│   ├── app.json            # 应用配置
│   └── signals.json        # ADC 信号定义（42 路转换通道 + 106 路状态位）
├── dbc/
│   ├── DVtest.dbc          # CAN 信号 DBC 文件（18 条报文/208 信号）
│   └── DVtest.ini          # DBC 配置
├── can_driver/
│   ├── simulator.py        # CAN 仿真器（无硬件测试）
│   ├── zlg_can.py          # ZLG USB-CAN 硬件驱动
│   └── zlgcan_sdk.py       # ZLG SDK 封装
├── data/
│   ├── decoder.py          # DBC 信号解码器
│   ├── model.py            # 数据模型（ChannelState）
│   ├── dbc_parser.py       # DBC 文件解析
│   └── storage.py          # SQLite 存储 + CSV 导出
├── ui/
│   ├── main_window.py      # 主窗口（总览/相机/IO 状态/曲线/报文/发送 六个页签）
│   ├── panel_overview.py   # 总览面板（电压/温度/CPU 负载/报文健康）
│   ├── panel_camera.py     # 相机面板
│   ├── panel_io.py         # IO 状态面板（HSD/LSD/RS232/RS485/SPI/SSD/CAN/I2C）
│   ├── panel_curves.py     # 曲线面板
│   ├── panel_log.py        # 报文面板
│   ├── panel_send.py       # 发送面板（原始帧 / DBC 报文）
│   └── widgets.py          # 自定义控件
├── tools/
│   ├── can_self_test.py    # CAN 自测工具
│   └── gen_signals.py      # signals.json 生成工具
└── tests/                  # 测试脚本
```

## 快速开始

### 环境要求

- Python 3.12+
- Windows（CAN 硬件模式需要 ZLG 驱动）

### 安装依赖

```bash
pip install -r requirements.txt
```

### 启动

```bash
# Windows
run.bat

# 或直接运行
python main.py
```

### CAN 通信模式

| 模式 | 说明 | 配置 |
|------|------|------|
| 仿真器 | 无硬件自测，自动生成模拟数据 | `can_driver/simulator.py` |
| ZLG 硬件 | 连接 ZLG USB-CAN 适配器 | `can_driver/zlg_can.py` |

由 `config/app.json` 的 `simulation` 字段切换。

## CAN 协议概览

DBC 共 18 条报文 / 208 信号。其中 0x650-0x65F 为 ADCU→总线 TX（8 字节，100ms 周期），0x680 由上位机下发：

| CAN ID | 报文名 | 内容 |
|--------|--------|------|
| 0x650-0x654 | MCUVoltageData1-5 | 20 路 ADC 电压（每帧 4 路，i/f 各一） |
| 0x655 | MCUTempData | SOC/5152 温度 + 20 路电压状态位 |
| 0x656-0x658 | SocTXStatus/1/2 | Cam0-10 Linklock/Videolock/Crc + FPS、I2C/SPI/RS232/RS485/SSD 状态 |
| 0x659 | SocTXStatus3 | SOC 温度（Tj/Gpu/Cpu/Soc012/Soc345/Ssd01/Ssd02）+ error_count |
| 0x65A | McuLSDStatus | LSD P32.2-5 状态、GPI、BTT3050/BTS3410 错误计数、控制器/Thor 状态 |
| 0x65B | Mcu_USV_Status | RS485/RS232/SPI 状态与错误计数 |
| 0x65C | McuHSDStatus | U1000/U1001 自检状态 + HSD1-7 ADC 值 |
| 0x65D | McuCanStatus | CAN1-4 状态与错误计数 |
| 0x65E | McuCpuLoad | CPU0-5 负载 |
| 0x65F | HSD_PORT_Status | HSD P23.0-6 端口诊断状态 |
| 0x680 | DVtest_Switch | 上位机下发（1000ms）：DV 开关、HSD 使能、LSD 开关 |

## 开发

```bash
# 打包为 exe
build.bat

# 运行 UI 冒烟测试
python tests/smoke_ui.py
```

## License

Internal use only.
