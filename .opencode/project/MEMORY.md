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

## Important Commands

```bash
# UI/协议验证（Windows anaconda，offscreen）
/mnt/c/ProgramData/anaconda3/python.exe tests/mes_ui_check.py   # MES 04 全链路
/mnt/c/ProgramData/anaconda3/python.exe tests/smoke_ui.py       # 解码/故障注入/CSV 冒烟
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
