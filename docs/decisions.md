# 决策日志

一行一条，只记**不可从代码/commit 直接推出**的决策与理由。新增追加在末尾。
格式：`日期 | 决策 | 理由/依据 | 影响`

| 日期 | 决策 | 理由/依据 | 影响 |
|---|---|---|---|
| 2026-09-18 | 保留两套 DLL：官方 x64 WinUSB 为默认，ZQWL 的 CDC 兼容库另存 `zlgcan_zqwl.dll` | 官方库不含串口代码、CDC 库不含 WinUsb，不能互换（早期踩坑：ZQWL 库对 200U 永远打不开） | `zlg_can.py` `_DEVICE_LIB`；v1.3.0 |
| 2026-09-18 | 报文栏新增 Bin 列，复制改为单元格级（Ctrl+C 复制光标列） | 原来整行复制包含时间戳/解析值，贴不进别的工具 | `panel_log.py`；v1.3.1 |
| 2026-09-18 | 适配器路由统一走 `make_adapter(cfg, device)`，PCAN 用 `PCAN:` 前缀 | 上层 UI 零改动；三套库 API 不同但要同接口 | `zlg_can.py`/`pcan_adapter.py`；v1.4.0 |
| 2026-10 | 曲线页删除电压曲线，改 8000 点自适应抽稀 + HH:MM:SS 时间轴 | 用户要"长期记录看温度/负载变化"；40s 翻页太短 | `panel_curves.py`；v1.6.0 |
| 2026-09-18 | MES 上报不引 requests/zeep，用 stdlib urllib | 项目依赖刻意精简；打包体积约束 | `mes/transport.py` |
| 2026-09-18 | SN 用扫码枪（键盘模拟）输入，回车即触发上传；上报为手动按钮触发 | 测试员要先看结果再传 | `main_window.py` `sn_edit`/`mes_btn` |
| 2026-09-18 | MES 上报粒度为「综合判定 + 关键项」而非全信号明细 | 用户选择 | `mes.json` `channels` 白名单 |
| 2026-10 | 04 报文 9 段：`04;工号;序;工序;资源;设备;治具;yyyyMMddHHmmss;项:值,...;` | MES 权威文档；检测项内英文逗号、字段间英文分号（**曾两次弄错分隔符，以本文为准**） | `mes/protocol.py` |
| 2026-10 | 每命令最多 7 项，超出拆多条；无检测项不发 04 | MES 文档"有就传，否则可以不用" | `protocol.py MAX_ITEMS_PER_COMMAND=7` |
| 2026-10 | 拆条后某条返 NG → 不发后续；网络失败 → 整组重发（默认 3 次，2^n 退避） | 用户明确决策；允许 MES 侧重复数据 | `client.upload` |
| 2026-10 | SN 原样透传，上位机不校验格式 | MES 侧可能是主工单条码或 MAC，由 MES 自己解析 | `protocol.build_test_results` |
| 2026-10 | 响应判定用字符串：首段 `OK`=成功，`NG;原因`=拒绝取原因；兼容 SOAP 信封/裸串 | 用户选择"字符串判断"，不解析 XML | `protocol.parse_response` |
| 2026-10 | mes.json `process="DIP-下线"`，工号/资源/设备/治具留空，`enabled=false` | 现场别人家代码工序名；防误传，车间联调通过后再开 | `config/mes.json` |
| 2026-10 | MES URL 用 HTTPS 自签证书，`verify_tls=false` 必须保留 | 现场同款链路 `verify=False` 才连得上 | `transport.py` |
| 2026-10 | 白名单 26 项 = 20 电压 + 4 温度(SOC_TEMP/TEMP5152/TempCpu/TempGpu) + CPU0/CPU1_Load | 用户选"关键项白名单"未列举，暂按此定；改 `mes.json` 即生效 | `config/mes.json` |
| 2026-10 | 电压合格性=MCU 状态位 + limits 窗口**交叉校验**，不单信 bit | MCU status 是单 bit，漏判/误判都无法察觉（5 路固件从未赋值 → 恒红） | `data/limits.py`；v1.8.0 |
| 2026-10 | 交叉校验规则：一致→绿/红；MCU 异常但窗口内→黄；MCU 正常但超窗→红（强制 NG）；无状态位按窗口判 | 抓 MCU 漏判的过压/欠压，同时区分"产品红/固件黄" | `limits.py judge()` |
| 2026-10 | 温度 9 路（SOC_TEMP/TEMP5152/TempCpu/TempGpu/TempSoc012/TempSoc345/TempSsd01/TempSsd02/TempTj）统一 -50~150℃，不需要 MCU 状态位 | 用户明确"在上下限就直接绿灯"；MCU 本来不发温度状态 | `config/limits.json` |
| 2026-10 | limits.json 由 `tools/gen_limits.py` 从固件 `DV_CAN.c` 窗口**生成**，工艺输入走 `MANUAL_LIMITS` | 防止两份限值漂移；改固件窗口后重跑一次即可 | `tools/gen_limits.py` |
| 2026-10 | ADC 5 路无状态电压（AD1/AD2/IGN/CAN0_INH/TBOX_WP）、Adc_Monitor.c 欠压笔误：**暂不修固件** | 用户原话"暂时不更新，先保持原样"；待硬件/固件团队另行排期 | 实机这 5 张卡仍恒红 |
| 2026-10 | Cache Read 不追求清零（命中缓存本就降价 ~90%），目标砍总上下文体积 | 用户问减少 Cache Read | 工作方式：一任务一会话/主动 compress/派子代理 |
| 2026-10 | 过站 05 暂不实现：MES 文档 5 段 vs 现场代码 7 段冲突，待 MES 方给准确段位 | 段位布局未确认，实现=赌 | 待用户指令 |
| 2026-10 | `dvtest_*.csv`、`data/export_test_*.csv`、`data/shots/*`、`dbc/DVtest-0911.dbc` 不提交 | 运行导出/截图产物/旧 DBC 备份 | .git 提交范围 |
| 2026-10 | MES 04 分隔符教训（字段间 `;`、检测项内 `,`，曾两次弄错）**保留在 decisions.md，不晋升 AGENTS.md** | 用户拍板；理由是协议事实而非行为规则，AGENTS.md 管行为 | docs/decisions.md |
| 2026-10 | 初始化 `.opencode/project/`（INDEX/MEMORY/HANDOFF），sessions/ 入 .gitignore | instructions 注入的 MEMORY/HANDOFF 此前不存在=静默失效；claude-mem 插件负责自动沉淀，本目录负责权威状态 | `.opencode/project/` |
