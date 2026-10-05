# PHASE-PG 当前源码全量回归 — 交棒（一屏）

日期：2026-10-05 ｜ Git根：`D:\jbcode\web ai\jianli` ｜ HEAD：`76dfd59`（非父项目master）
本次测试源码 = 工作区现状（含未提交岗位选择协议、0014迁移及前端改动）；实际文件 sha256 见 `01-source-hashes.txt`（16个文件），status 见 `00-head-status.txt`。

## 结论：全部通过（4/4 绿）

| 项 | 命令 | EXIT | 结果 |
|---|---|---|---|
| 后端全量 PG pytest | `backend/.venv/Scripts/python.exe -m pytest app/tests -q -rs -p no:cacheprovider --basetemp=D:/jbcode/tmp/pytest-phase-pg-20261005`（env `CAREERPROOF_TEST_DATABASE_URL=postgresql+asyncpg://careerproof:careerproof@127.0.0.1:5432/careerproof`，未改.env） | 0 | **939 passed / 0 failed / 0 skipped**，245.33s，7 warnings（均为弃用类：swig/anyio/fastembed mean-pooling 提示，非失败） |
| 后端 Ruff | `python -m ruff check app evals` | 0 | All checks passed! |
| 前端全量测试 | `npm test`（node --test tests/*.test.mjs） | 0 | **153 pass / 0 fail / 0 skipped**，528ms |
| 前端类型检查 | `tsc --noEmit --incremental false` | 0 | 无输出（干净）；执行前确认无 build 在跑（仅 `next start -p 3001` 生产终态服务，未重启） |

## 夹具隔离核对（02-fixture-check.md）
- conftest autouse 强制 `ai_provider="mock"`、`ai_external_enabled=False`：无真实模型/外部AI。
- `matching_db` 仅在显式配置 TEST URL 时用 PG；每次 `cp_test_{uuid4().hex}`（断言 32hex），setup CREATE SCHEMA、teardown DROP SCHEMA CASCADE；非 PG 自动 skip（本次未 skip）。
- 未写 public/业务表；`cp_e2e_closure-20261005` 未触碰（本库中亦无该名 schema）。

## 观察（非失败，报告Codex）
- PG 库存在 2 个**孤儿** schema：`cp_test_97d401ff…`、`cp_test_df81fcf1…`。本次运行全部通过且夹具自清理（结束后查询时无其他活动会话），判断为先前中断会话遗留；按本任务只读约束未删除，留 Codex 决定。
- 学生浏览器任务并行未受影响：全程未访问浏览器/E2E夹具/凭据/服务。

## 约束遵守
只写本目录；产品/测试/其他证据/正式文档只读；无构建重复、无安装、无外发、无真实模型、Git只读、未动 .env/stash/服务。

## 文件清单
00-head-status.txt ｜ 01-source-hashes.txt ｜ 02-fixture-check.md ｜ 10-pytest-{output,exit}.txt ｜ 20-ruff-{output,exit}.txt ｜ 30-frontend-test-{output,exit}.txt ｜ 31-tsc-{output,exit}.txt ｜ 40-pg-schema-final.txt
