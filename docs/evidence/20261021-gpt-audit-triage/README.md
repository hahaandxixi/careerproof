# GPT 整改清单三态 triage（2026-10-21）

基线：仓库外 `D:\jbcode\CareerProof-整改清单.md` 为 `71a2fd3`（10-13），当前执行基线 `f17be7a`。本文件只做差量，不把旧清单当当前缺陷全集。

状态说明：`已修/已存在`、`仍开放`、`不修/接受`、`需复核`。本轮只做三个状态核验：CI、账号注销为「需复核」，pgvector 为「已修/已存在」；均不连正常库/站、不调用模型。

## 1. CI 远端是否真实运行

- 本地 `.github/workflows/ci.yml` 存在，定义 `pull_request`/`push main` 触发、backend-unit、PostgreSQL 和 frontend 作业。
- 未读取 GitHub Actions 结果；没有远端 run URL、PR 阻塞记录或最近一次绿色证据。
- 结论：**本地工作流存在；远端实际运行 UNVERIFIED**。不写“CI 已通过”。

## 2. 账号注销 RESTRICT 路径

- 静态核对：`backend/app/models/recruitment.py` 中 `applications.report_id`、`jobs.created_by`、`audit_logs.actor_id` 等仍有 `ondelete="RESTRICT"`。
- 未连接正常库，未执行账号删除，未做 DELETE 事务验证。
- 结论：**代码层仍存在硬删除阻断迹象；实际注销路径 UNVERIFIED**。本计划不修，避免影响历史快照。

## 3. 过滤场景 pgvector 后过滤

- 状态：**已修（fa8fbbd）**。
- 当前事实：`backend/app/services/retrieval.py:315-326` 用
  `select(...).where(source_id.in_(allowed_ids)).cte("owned_chunks").prefix_with("MATERIALIZED")`
  先物化允许行，`distance` 在 CTE 列上计算，之后才 `order_by(distance)`——过滤先于排序。
- 修复前（fa8fbbd 之前）确为后置过滤：HNSW 在 `ef_search` 预算内可能把自有命中整批漏掉。
  该风险已由 fa8fbbd 的预过滤消除，**不是本轮新改动**。
- 未验证：未连 PG、未执行 EXPLAIN、未构造上千 allowed ids 的过滤召回用例；
  运行时召回率 **UNVERIFIED**。本项只做代码层复核，不改索引/查询/迁移。
- 附注：`retrieval.py:312-314` 注释第三行「交给外层排序则召回与计划无关」即该修复说明。

## 其余清单项

未在本轮批量重做旧 P0/P1。已存在当前证据的项（JWT/生产 debug/生产 docs、CI 文件、`.tmp*` ignore、分数/等级标签、通知 README 等）标为“旧基线已修/已存在，需按当前提交复查”；未复核项不写成已通过。
