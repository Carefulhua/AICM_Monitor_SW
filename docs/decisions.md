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
| 2026-11 | 空载电压判定：`AD1`/`AD2`/`IGN`/`TBOX_WP` <1V 判 PASS（上界开区间），`CAN0_INH` 17~21V 判 PASS | 用户指令：这 4 路暂不接负载、实测 ~0V；CAN0_INH 为抑制电压。固件这 5 路状态位从未赋值，判定改为只信窗口（`ignore_status`） | `tools/gen_limits.py` `MANUAL_LIMITS`/`EXCLUSIVE_UPPER`/`IGNORE_STATUS`；`limits.py` 新增 `upper_exclusive`/`ignore_status` |
| 2026-11-04 | 温度 9 路上下限改为 **0~85℃** | 用户指令（原 -50~150℃ 来自工艺占位） | `tools/gen_limits.py` `MANUAL_LIMITS`；`config/limits.json` |
| 2026-11-04 | 新增「判定」页签：一键汇总全部检查项，全 PASS 绿框、任意 FAIL 红框 | 用户要求“所有功能 PASS 才显示绿框 PASS，只要有 Fail 都报红 Fail”；默认口径=限值 + 全量健康状态位 + DUT 报文接收 | `data/verdict.py`、`ui/panel_verdict.py`；判定页签置顶 |
| 2026-11-04 | 自动判定只要求 DUT 上报的 16 条报文；排除 `CAN1~4TEST`、`DVtest_Switch`、Vector 占位 | CAN1~4TEST 是外部节点测试帧，0x680 是上位机下发回读，都不是 DUT 健康状态 | `data/verdict.py:expected_message_names()` |
| 2026-11-04 | `json_msg_missing` 语义修正为 **0=正常、1=缺失** | 相机面板与仿真器一直按 0 正常处理；原 `signals.json`/DBC `VAL_` 标反，导致自动判定误报 | `config/signals.json` status；相机面板逻辑不变 |
| 2026-11-04 | HSD 状态值映射改为固件枚举：**0 正常 / 1 异常 / 2 过载 / 3 开路 / 4 对 VS 短路** | 实机抓包 `0x65F=03000300...` + `0x65C=8800...`：P230/P234 原始值 3、ADC=0，是**开路**不是过载；原 `signals.json` 沿用 DBC 旧 `VAL_`（3=过载），把开路显示成过载 | `config/signals.json` 7 个 `HSD_Status_P23x`；DBC 未改，仅影响 DBC 自带文本 |
| 2026-11-04 | `U1000_Test_Status`/`U1001_Test_Status` 支持 `normal_values`：判定接受 **0 启动 / 1 运行 / 2 换通道**，3 待机及以上算异常 | 原配置 `normal: 1` 把正常换通道瞬间判红；它本身是状态机状态，不是布尔健康位 | `data/decoder.py:is_status_normal()` + `config/signals.json` |
| 2026-11-04 | HSD 开路仍计入自动判定 FAIL，不因“外部未接”放行 | 开路是真实负载回路异常；是否允许空载需工艺明确规则后再改 | `data/verdict.py`、`config/signals.json` |
| 2026-11-04 | **未接 HSD 通道开路放行**（推翻上一条“开路仍 FAIL”）：P230/P234（两个芯片的 CH0）标记 `unconnected`，开路 3 判 PASS；`U1000/U1001_Test_Status` 的 6/8 仅在 `excused_by` 通道当前为开路时放行，过载/短路仍 FAIL | 用户指令：“目前未接负载，按未接通道放行” | `config/signals.json` `unconnected`/`excused_by`；`data/decoder.py:StatusDef`；`data/verdict.py` |
| 2026-11-04 | `gen_signals.py` 增加 `STATUS_OVERRIDES`，重跑生成器不会丢失 HSD 固件枚举、`normal_values`、`unconnected`、`excused_by` | DBC `VAL_` 仍是旧枚举，手工配置会被无提示覆盖 | `tools/gen_signals.py` |
| 2026-11-05 | 自动判定中的以太网只覆盖 `eth0_1/0_7/0_8/1_1`，其余 6 路标 `verdict_skip`（IO 面板仍显示） | 当前功能只做到这 4 路，未实现通道不应阻断整机 PASS | `config/signals.json`、`data/verdict.py` |
| 2026-11-05 | 判定改为**每秒自动刷新**，移除「一键判定」按钮和快照提示；明细原地更新，保留滚动位置与展开状态 | 操作员无需记得手动触发，避免看到过期结论；每秒重建树会让正在查看的失败项跳动 | `ui/panel_verdict.py`、`ui/main_window.py` |
| 2026-11-05 | 移除独立「测试模式」按钮；「启动」改为「启动测试」，点击后自动进入测试模式（1s 周期 0x680），「停止」时下发全 0 复位 | 操作员只需一个启动动作，避免忘记开测试模式；断开/关闭时先停测试模式，防止残留周期发送 | `ui/main_window.py` |
| 2026-11-05 | 判定改为在收到第一帧后才开始，清空后再次等待首帧 | 收到首帧前不判「无报文 FAIL」，直接灰框等待 | `ui/panel_verdict.py`、`ui/main_window.py` |
| 2026-11-05 | 判定增加 SPI_STATUS 门槛：SPI_Status 不通过时不进行判定 | 用户要求：SPI status pass 后才判定 | `ui/panel_verdict.py` |
