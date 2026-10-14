# Project Handoff

- Updated: 2026-10-14
- Branch: dev
- Commit: 7567a88 (== origin/dev, tag v1.8.0)
- Session focus: 记忆体系落地（project-init + 决策日志）

## Current Objective

完成 MES 04 车间联调前的收尾：`.opencode/project/` 初始化、决策日志归档；等待用户指令推进 B 组待办。

## Completed

- MES 04 全链路（组包/编排/HTTP/UI）→ v1.7.0；电压交叉校验 + 温度 9 路限值 → v1.8.0
- docs/decisions.md（23 条）+ docs/handoff-2026-10-14.md 已提交（7567a88，已推送）
- `.opencode/project/` 三件套（INDEX/MEMORY/HANDOFF）+ gitignore sessions/

## Current Changes

- 无未提交代码；工作区脏 = 约定排除项（dvtest/export_test/shots/DVtest-0911.dbc）

## Decisions and Findings

- MES 04 分隔符教训**保留在 docs/decisions.md，不晋升 AGENTS.md**（协议事实非行为规则；用户 2026-10-14 拍板）
- 记忆栈：claude-mem 插件（`~/.claude/projects/-mnt-c-can-closed/memory/`）负责自动沉淀；`.opencode/project/` 负责 agent 主状态；两者分工不重复
- 5 路无状态电压实机恒红（固件漏判）已知，暂不修

## Verification

- tests/smoke_ui.py PASS；tests/mes_ui_check.py PASS；tools/mes_demo.py PASS（均为 EXIT=0，最近一次 v1.8.0 验证）

## Blockers and Risks

- 工位字段（工号/资源/设备/治具）仍空 + `enabled=false` → 车间联调前必须填
- 过站 05 段位未确认（MES 文档 5 段 vs 现场 7 段）
- 7 个白名单检测项无语判能力已缓解：温度 9 路已有窗口；CPU2~5_Load 仍纯数值

## Exact Next Actions

1. 填 `config/mes.json` 工位字段 → `enabled=true`
2. 车间实测 form POST 是否被 MES 接受（决定是否需要 SOAP/05）
3. 待用户指令：05 过站 / 失败重传按钮 / 01 检查命令 / SOAP 1.1·1.2
