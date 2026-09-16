# AICM-NT4K DV Monitor

博雷顿控制器 Ares AICM-NT4K 设计验证测试（DV）CAN 总线实时监控上位机。

## 功能

- **总览面板**：系统概览、电压/温度/电流实时数值、故障状态指示
- **相机面板**：Cam0-10 FPS 显示、I2C/SPI/RS232/RS485 通信状态
- **IO 面板**：20 路 ADC 电压、板温度、SOC 温度（Tj/Gpu/Cpu/Soc012/Soc345/Ssd01/Ssd02）、HSD ADC 值、CPU 负载
- **曲线面板**：电压/温度/HSD/CPU 负载/SOC 温度实时滚动曲线
- **日志面板**：CAN 帧日志、信号变化事件
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
│   └── signals.json        # ADC 信号定义（42路转换通道）
├── dbc/
│   ├── DVtest.dbc          # CAN 信号 DBC 文件（14条报文/191信号）
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
│   ├── main_window.py      # 主窗口
│   ├── panel_overview.py   # 总览面板
│   ├── panel_camera.py     # 相机面板
│   ├── panel_io.py         # IO 面板（ADC/温度/HSD/CPU）
│   ├── panel_curves.py     # 曲线面板
│   ├── panel_log.py        # 日志面板
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

## CAN 协议概览

14 条报文，全部为 ADCU→总线 TX，8 字节，100ms 周期：

| CAN ID | 报文名 | 内容 |
|--------|--------|------|
| 0x650-0x654 | MCUVoltageData1-5 | 20 路 ADC 电压 |
| 0x655 | MCUTempData | SOC 温度 + 电压状态位 |
| 0x656-0x658 | SocTXStatus/1/2 | 相机 FPS、I2C/SPI/RS232/RS485 状态 |
| 0x659 | SocTXStatus3 | SOC 温度（Tj/Gpu/Cpu/Soc/Ssd） |
| 0x65A | McuLSDStatus | LSD 状态 + 错误计数 |
| 0x65B | Mcu_USV_Status | RS485/SPI 状态、MCU/SOC 电压状态 |
| 0x65C | McuHSDStatus | HSD 状态 + HSD1-7 ADC 值 |
| 0x65D | McuCanStatus | CAN1-4 状态与错误计数 |

## 开发

```bash
# 打包为 exe
build.bat

# 运行测试
python tests/smoke_ui.py
```

## License

Internal use only.
