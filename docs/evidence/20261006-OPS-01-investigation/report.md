# OPS-01A 只读调查（2026-10-06）

状态：调查完成；协议、迁移和故障实验均未实施。开始只读核对时 HEAD 为 `95376cf`；记录命令日志时主会话已推进至 `c31d557`，本会话未操作 Git。调查所引两条用量链的文件在后续 `git diff` 中无工作树差异。任务卡：`docs/task-cards/20261005-OPS-01-investigation.md`。PRODUCT-01 文件、P2 stash 均未由本会话改动。

## 一屏交棒

**已证实缺口。** 核验链已对“收到可信用量且进程尚在”的记录以 `(run_token, request_seq)` 独立事务幂等入账，且撤回、租约失效不回滚该事实；但 `usage_records` 仅在内存，响应捕获至提交前硬停即失去可信用量。主匹配链在报告终结事务才写一个聚合 `AiUsageLog`，没有每次物理外发的持久标识，硬停或终结失败可漏账。两条链 `_daily_ai_budget` 均只看已写账目；核验链检查后主动提交释放锁，主链在长调用期间其短事务也会经进度更新提交，因此不能凭用户行锁阻止多个已获准的在途请求越过日限额。`backend/app/services/application_verification.py:484-560,572-601,612-624`；`backend/app/services/analysis.py:137-179,565-598,631-702,920-937`。

**未验证。** 未运行真实子进程硬停、数据库故障或 PG 并发实验；PG 端口不可用，Docker Desktop 启动有本机 Inference manager `dockerInference` 监听文件错误。没有 provider 收据或查询能力的证据，故发送后响应未持久化的 token 只能标 unknown，不能承诺精确恢复。

**建议协议/范围。** 新增每个*物理 HTTP 尝试*的持久请求行和每用户每日容量行：短事务预留与标记 `in_flight`，响应可信用量先持久化，再在同一事务幂等写 `AiUsageLog` 并结清预留；未知用量保守占额、独立对账，不把任务状态或 `usageKnown` 当账本状态。锁序统一为用户日预算行 → 请求/预留行 → 用量行；撤回/投递授权锁在外发前独立短事务核验，终结时再核验，不持锁外发。相关预期文件：`models/analysis.py`、新 Alembic 迁移、`services/analysis.py`、`services/application_verification.py`、`agents/provider.py`、`agents/evidence_workflow.py`、`services/task_lifecycle.py` 及专属测试。需要先由主会话签收协议和迁移范围。

**最多两个首修项。** ① 持久请求状态和可信响应的原子幂等入账，先覆盖核验，再覆盖主链全部规划/分析/修正/HTTP 重试尝试。② 两链共用每日已账+在途预留准入与跨日、超时、旧 run 对账。更广的 `career_planning`、`visual_evidence`、`job_drafting` 等也调用 `_daily_ai_budget`，系统级统一预算声明必须另核这些路径（搜索命中见下）。

## 生命周期事实表

| 环节 | 主匹配链 | 企业投递核验链 |
|---|---|---|
| 创建/客户端重复 | `create_match_task` 冻结岗位/材料快照，同输入的 pending/running 任务复用，已成功缓存可复用；失败任务的 retry 在同 task 重置，下一 claim 新 `run_token`。`analysis.py:187-284,289-314`；`task_lifecycle.py:24-43,130-160` | 绑定 `applicationId`、固定报告 `snapshotHash`、授权版本、provider/model/prompt `cacheKey`；pending/running 与有效完成结果复用，失败后新建 task，15 分钟频率门槛。没有通用 verification retry 端点。`application_verification.py:276-291,324-390`；`api/v1/applications.py:70-105` |
| 外发与物理重试 | 工作流可发规划、分析、一次定向修正；`request_count` 在调用前加一，不等于 HTTP 投递数。provider 在 `client.post` 发出，429/5xx/网络超时按配置最多 2 次（可配置 1–3），每次重试是可能独立消耗的一次外发；失败响应未入 usage_records。`evidence_workflow.py:375-409,542-585`；`provider.py:456-460,494-554`；`config.py:52-62` | 预算/授权和快照检查后提交、释放锁，再构造发送数据；`_max_attempts=1`，每个新核验 task 至多一次 HTTP 调用；`generate_bounded_json` 经 `client.post` 发出。`application_verification.py:569-602`；`provider.py:611-634,494-539` |
| 响应捕获 | `_completion` 只对非可重试成功响应返回 JSON；随后 `_capture_usage` 将响应计数与可信标志放入 provider 内存，再解析内容；规划、分析、修正皆如此。`provider.py:537-554,571-599,723-732,858-859` | 同一个 `_capture_usage` 在解析结果之前执行；若结构校验失败，已收到的可信用量仍应入账。`provider.py:632-634`；`application_verification.py:597-602` |
| 入账 | provider 聚合已捕获用量；工作流成功将规划+分析/修正合并，fallback 取 `combined_usage`；报告与单条聚合 `AiUsageLog` 在终结事务 `commit`，`run_token/request_seq` 留空。无可信与不可信用量的逐响应区分。`evidence_workflow.py:605-621,650-675`；`analysis.py:631-702,920-937` | 可信且非负整数的 prompt/completion token 才入独立事务，冲突键 `(run_token,request_seq)`，数据库唯一索引和 `ON CONFLICT DO NOTHING`；`usageKnown` 仅描述响应数据，不证明账本提交。`provider.py:565-599`；`application_verification.py:484-529,612-624,677-710`；`models/analysis.py:167-193` |
| 任务/授权变化 | `finish_task` 按 `run_token` CAS；失租后不保存报告，而此前外发的消费仍可能存在。`task_lifecycle.py:46-74,163-216`；`analysis.py:669-671` | 账本先写、终结后重新锁定授权，撤回/快照变化阻止显示分析；已消费事实仍独立。学生撤回更新 application 状态。`application_verification.py:612-710`；`applications.py:423-431` |

`request_seq` 当前只在处理成功响应时递增（`provider.py:594-598`），不是物理投递编号；在 HTTP 重试/超时后无法识别先前尝试。客户端 retry 的新 `run_token` 或新 task 与一次响应的重复入账是不同问题；现有唯一索引只解决后者的核验链场景。非可信 usage 被展示为零但不应成为实际账目；主链现有聚合记录未保留此区分。

## 建议状态机及原子边界（待签收）

| 状态/转移 | 必须持久的事实 | 事务边界与恢复动作 |
|---|---|---|
| `not_sent`：获准并预留 | user、task、不可复用的 claim `run_token`、物理 `attempt_id`、step、固定投递快照摘要/授权版本、provider/model、保守输入/输出上界、归属日、创建时间 | 锁该用户归属日容量行，核对已账+所有未结清占额+报告槽位后，原子建立请求行与预留；不能把预留记作消费。敏感原文只保存在既有受控快照边界内。 |
| `not_sent` → `in_flight` | 发送意图时间和唯一 attempt_id | 外发前短事务提交；HTTP POST 在事务外。硬停后此状态只能表示“可能已发送”，不能由本机精确判断。若授权已撤回，直接终止未发送请求并释放预留；不得重新发送。 |
| `in_flight` → `received_unbooked` | 可信 provider usage 的原值、响应标识/摘要、接收时间、可信校验结果；缺字段/无效字段记 `usage_unknown` | 一收到响应即短事务保存，不等待业务 JSON 校验或 task finalize。若此持久化事务失败，进程内可有界重试；硬停仍会失去内存事实。无 provider 查询时该区间不可完全消除。 |
| `received_unbooked` → `booked` | `AiUsageLog` 对 attempt_id 唯一、实际用量、booked_at，预留转结清 | 同一事务 `INSERT ... ON CONFLICT DO NOTHING` + 结清预留；重复恢复只读已存响应，不重发 HTTP，账目不可因撤回/租约失效回滚。`usageKnown` 与 `usageBooked` 分字段。 |
| `in_flight` → `usage_unknown` | 超时/租约恢复/进程硬停等原因与最后观察时间、仍占用的保守额度 | 没有可信响应/收据只能保留 unknown；TTL 不自动释放。仅有权威 provider 对账证明未消费/给出用量，或有记录的人工额度政策，才可结清。旧 run 延迟响应按原 attempt_id 接收及入账，不恢复旧 task 的分析结果。 |

预算计数应是“该归属日已账实际 token + 未结清尝试的保守输入/输出上界”，报告数按 distinct task 的实际已账或未结清占槽去重；一个 task 的多次尝试占 token，但不重复占报告槽。主链的每次规划/分析/修正与 provider 内 HTTP retry 都需独立上界；未知消耗按上界持续占额。归属日采用 Asia/Shanghai 且以**实际外发前提交的发送日**固化，午夜前获准但午夜后发送须重新校验/迁移预留；午夜跨越中的旧请求仍归其发送日，延迟响应改正原日账目，不能按入账日错误挤占新日。现有预算按 `AiUsageLog.created_at >= 当日零点`，还没有发送日概念（`analysis.py:143-158`）。若产品规则要求按 provider 计费日，应先由主会话定口径。

锁序：在同一短事务里按用户/归属日容量行，再按稳定 `attempt_id` 锁请求行，再写账；涉及多天时按日期升序锁。授权 application 锁应与预算事务分离并二次核验，避免撤回阻塞于 HTTP。`User.id ... with_for_update(key_share=True)` 对并发读预算不足以形成写入互斥，且核验链 `session.commit()` 明确释放了锁（`analysis.py:137-142`；`application_verification.py:583-589`）。所有入账/释放/调整必须使用数据库唯一键与 CAS，不能以进程内 `usage_persisted_seq` 作为唯一恢复进度。

## 合成故障实验设计——全部未执行

1. **真实子进程硬停（mock provider，仅专属 cp_test 或临时 SQLite）。** 建自有子进程，父进程记录 PID、创建时间、测试随机 nonce，并用双向栅栏证明进程身份后才硬停该 PID；不按进程名或端口杀。mock transport 分别卡在：预留前、发送意图提交后/响应前、可信响应返回后/持久化前、响应持久化后/入账前、账目提交后/业务终结前。重启恢复后断言：未发送可释放，可能发送保持 unknown，已持久可信响应只入一账，已入账不重记；旧 run 的业务结果不可复活。当前没有响应前持久化协议，前两处只能观察缺口，不能写“通过”。
2. **DB 暂时失败后恢复（mock provider）。** 注入仅账本会话 `commit` 失败、超时及随后恢复；检查响应持久行与 ledger 原子性，重启对账重复执行不再外发且不重复入账；即使核验 finalize 已失败/取消，可信已存响应仍可入账。区分“响应已返回但 DB 从未成功写入”的不可恢复窗口。仅专属数据库；不复用 closure 投递或真实模型。
3. **PG 并发预算争夺。** 专属 `cp_test` 同用户两链各一请求，以 barrier 同时越过旧预算检查，在临界剩余额度下验证新协议只放行有容量者；覆盖输入、输出、distinct 报告槽、不同用户、午夜换日、旧 run 延迟响应与 unknown 保留。审计行锁顺序、死锁重试和事务提交后数值。PG 未恢复，本轮仅设计。

已有 B-08 测试包含 mock 的失租、finalize 失败、重复入账、取消以及无效 usage 场景，但均在同一进程内，不能替代硬停证据：`backend/app/tests/test_b08_usage_accounting.py:47-129,133-259`。本轮没有执行测试、迁移或服务操作。

## 只读命令与脱敏输出摘要

`read-only-commands.txt` 保存所列复核命令的完整本地输出（仅路径、代码行号和依赖版本，无凭据或文件内容）；下面是索引。

- `git rev-parse --show-toplevel` → `D:/jbcode/web ai/jianli`；最初 `git rev-parse --short HEAD` → `95376cf`，命令日志复核时 → `c31d557`（主会话并发推进）。
- `git status --short` → PRODUCT-01 的 `evidence_growth.py`、models、迁移、growth service/schema/tests 与任务文档为修改/未跟踪；另有既存 E2E/evidence 文件与脚本。出现三个 `backend/.tmp-product01-codex-*` 目录 Permission denied 警告。完整文件列表见命令日志。
- `git stash list` → `stash@{0}: On main: P2 RRF fusion draft - paused by user 20261002`。
- `rg -n 'persist_verification_usage|usage_records|_daily_ai_budget|AiUsageLog|request_seq|run_token' backend/app -g '*.py'` → 核心路径见上表；其余预算调用命中 `career_planning.py:543`、`visual_evidence.py:183`、`job_drafting.py:101`。这些属于后续全系统范围核对，不在本次两链实现承诺内。
- `rg --files -g '*lock*'` → 仅前端 `jianli/package-lock.json`；后端根无 lock 文件，`backend/pyproject.toml:10-40` 固定直接依赖版本。只读 `importlib.metadata` 本地已安装：FastAPI 0.116.1、Pydantic 2.11.7、SQLAlchemy 2.0.43、Alembic 1.16.5、asyncpg 0.30.0、httpx 0.28.1、pytest 8.4.2、aiosqlite 0.21.0。未访问外部漏洞源；旧漏洞表不能当当前审计。
- 未找到适用 `AGENTS.md`。本轮只新写本报告与只读命令日志；未改源码、正式清单、环境、数据库或 Git。
