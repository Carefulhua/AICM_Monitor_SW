# Project Memory

AICM-NT4K DV 监控上位机（CAN 报文监控 / MES 上报）。Durable, verified project knowledge.

## Architecture and Constraints

- Python 3 + PyQt5 + pyqtgraph + SQLite；无第三方网络库（MES 用 stdlib `urllib.request`，见 DECISIONS）。Spec: [can_monitor.spec](can_monitor.spec)。
- 数据流：`can_driver/`（3 套适配器）→ `data/model.py:record()` 收帧 + `refresh()` 定时快照 → `data/decoder.py` 解码 → `ui/` 面板。
- CAN 适配器：ZLG 官方 WinUSB 库 / ZQWL CDC 库（`zlg_can.py`，`PCAN:` 前缀路由 → [pcan_adapter.py](can_driver/pcan_adapter.py)）。
- MES 链路：`mes/report.py`（数据模型）→ `mes/protocol.py`（commandString 组包/解析）→ `mes/client.py`（编排/重试）→ `mes/transport.py`（urllib HTTP）。04 命令格式见 docs/decisions.md。
- 替代判限：MES 参数。

## Conventions

- 提交排除项：`dvtest_*.csv`、`data/export_test_*.csv`、`data/shots/*`、`dbc/DVtest-0911.dbc`（见 docs/decisions.md 末行）。
- DBC 的 min/max 是**编码量程不是限值**；限值唯一来源 = 固件 `DV_CAN.c` 窗口 → `tools/gen_limits.py` 生成 `config/limits.json`（工艺值走 `MANUAL_LIMITS`）。
- 电压合格性 = MCU 状态位与 limits 窗口交叉校验（`data/limits.py:judge()`），不单信 bit。
- 空载电压判定（2026-11）：`AD1`/`AD2`/`IGN`/`TBOX_WP` **<1V PASS**（上界开区间），`CAN0_INH` **17~21V PASS**；这 5 路 `ignore_status=true`，忽略固件从未赋值的状态位。限值定义在 `tools/gen_limits.py` 的 `MANUAL_LIMITS`/`EXCLUSIVE_UPPER`/`IGNORE_STATUS`。
- 温度 9 路限值（2026-11-04 起）：**0~85℃**。
- 自动判定（2026-11-04）：`data/verdict.py` 汇总 29 路限值 + 全部健康状态位 + DUT 16 条报文；全 PASS 才 PASS。`ui/panel_verdict.py` 是「判定」页签（置顶），每 1 秒自动刷新、无按钮，明细原地更新以保留滚动/展开状态。排除 0x680 测试开关、`ignore_status` 状态位、`CAN1~4TEST`、Vector 占位报文。`json_msg_missing` 语义为 0=正常。
- 以太网判定范围（2026-11-05）：自动判定只判 `eth0_1`/`eth0_7`/`eth0_8`/`eth1_1`；`eth0_2~6`、`eth0_9` 标 `verdict_skip`，IO 面板仍显示但不参与判定。当前总检查项 140。
- 启动测试（2026-11-05）：主界面无独立测试模式按钮；「启动测试」同时开始接收并每秒下发 0x680（DV 开关+HSD 使能），「停止」下发全 0 并停发。
- 判定前必须收到首帧（SOC 发出报文）才开始；清空后回到“等待数据”。
- SPI 判定门槛（2026-11-05）：SPI_Status 不通过时不进行判定；SPI pass 后才判。
- 未接 HSD 放行（2026-11-04）：`signals.json` 中 P230/P234 标 `unconnected`，开路 3 判 PASS；U1000/U1001 的 6/8 仅在其 `excused_by` 通道开路时放行，过载/短路仍 FAIL。接负载后删除对应标记。

## Important Commands

```bash
# UI/协议验证（Windows anaconda，offscreen）
/mnt/c/ProgramData/anaconda3/python.exe tests/mes_ui_check.py   # MES 04 全链路
/mnt/c/ProgramData/anaconda3/python.exe tests/smoke_ui.py       # 解码/故障注入/CSV/自动判定冒烟
python3 tests/test_limits.py                                     # 限值判定单测
python3 tests/test_verdict.py                                    # 自动判定汇总单测
/mnt/c/ProgramData/anaconda3/python.exe tools/mes_demo.py       # 04 组包/编排单测
python3 tools/gen_limits.py                                      # 从固件 DV_CAN.c 再生 limits.json
```

## Recurring Pitfalls

- `BusModel.refresh()` 是快照方法**不收帧**；喂帧必须 `model.record(can_id, data, ts)`。
- `DVTestSimulator(db)` 要 `load_dbc()` 的 **Database** 对象，不是 Decoder。
- `config/limits.json` 是三层结构，通道表在 `limits.limits` 下。
- MES 上报时间取 `self._t_start`（录制开始），不是当前时间。
- mes_ui_check monkeypatch 要改模块全局 `main_window.mes_send`，改类属性无效。
- offscreen 渲染 `QMessageBox.warning` 会直接崩溃（rc=5）；测试里切仿真源用 `source_cb.setCurrentIndex(1)` + `on_connect()`。

## Verified Lessons

- CAN3/CAN4 互联报错根因 = 该对无终端电阻（6 对中唯一两端都无端接），非固件问题。
- MES 04 分隔符：字段间 `;`、检测项内 `,`（曾两次弄错，详见 docs/decisions.md）。

Source: docs/decisions.md + git history; verified 2026-10-14.
