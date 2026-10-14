# Project State Index

## Project

- Root: /mnt/c/can_closed（Windows C:\can_closed）
- Repository: git@github.com:Carefulhua/AICM_Monitor_SW.git (branch dev)

## Agent State

- `MEMORY.md` — durable project facts
- `HANDOFF.md` — continuation delta for the current branch
- `CHARTER.md` — protected intent and constraints, when present
- `SPEC.md` — agent working specification, when present
- `ROADMAP.md` — milestone sequence, when present
- `PROGRESS.md` — current whole-project snapshot, when present
- `FINDINGS.md` — hypotheses and verified discoveries, when present
- `DECISIONS.md` — material choices and supersession ledger, when present

## Existing Project Documentation

- [README.md](../../README.md) — 使用说明/功能总览，面向使用者的第一入口。
- [SPEC.md](../../SPEC.md) — 工程规格：适配器物理通讯细节（ZLG/ZQWL/PCAN）、DBC 协议概览、电压交叉校验判定表。与 agent SPEC 不互为副本；SPEC.md 是实现事实来源。
- [docs/decisions.md](../../docs/decisions.md) — 材料决策台账（日期/决策/理由/影响），含提交排除项、MES 04 报文格式。
- [docs/handoff-2026-10-14.md](../../docs/handoff-2026-10-14.md) — 一次性历史交接留档（USER REQUESTS 原文+当时 state），已被本目录 HANDOFF.md 取代为活状态。
- `~/.claude/projects/-mnt-c-can-closed/memory/` — claude-mem 插件自动沉淀区，与 MEMORY.md 分工：插件做检索式回忆，本目录做权威项目状态。

## Archives

Completed milestone detail lives under `archive/<milestone>/`.
