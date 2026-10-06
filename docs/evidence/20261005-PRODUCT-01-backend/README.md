# PRODUCT-01 学生私人回答草稿 · 后端交棒（ZCode）

2026-10-05。基线 b1b2b8d（已核对 HEAD/stash/status，未写 Git、未动其他未跟踪证据）。
协议来源：docs/task-cards/20261005-PRODUCT-01-private-answer.md + Codex 补充第 6 条（references 可选列表接口，本轮已落实）。

## Codex 高风险审查响应：目标报告同等校验（risk2）

**改动**：`_target_report_id` 升级为 `_validated_target`，与 `EvidenceGrowthService.view` 同等校验后才认当前对照报告——本人授权（get_report，AppError→无效）、`analysis.input_snapshot.jobId == 任务固定target_job_id`（task.target_job_id 或冻结快照jobId）、`report.job_id == target_job_id`、`report.materials == 任务冻结materials`。任一漂移→无有效目标：GET 保留草稿文本、目标引用 available=false（基准引用不受影响）、新PUT引用该目标 422 拒绝、可选列表不列错配目标。

**去重复读取**：单次请求内目标报告仅经 get_report 读取一次，解析视图（target_view）与冻结基准视图（base_view）贯通 save 校验→落库→响应视图及 GET/可选列表复用；`_view` 转同步不再二次查询。

**新增回归**（test_growth_answer.py::test_answer_draft_treats_drifted_completed_target_as_unavailable，覆盖 Codex 独立测试同款预期）：完成后篡改 input_snapshot.jobId（临时库直改，房内既有漂移模拟模式）→ 文本保留 rev=1、目标引用 available=false snippet=None、基准引用 available=true、新PUT 422 且草稿不变、不含目标引用的 PUT 正常 rev=2、references 列表仅 base 条目。

**结果**：risk2-target-sqlite **11 passed** EXIT=0；risk2-target-pg **14 passed** EXIT=0（cp_test 随机 schema）；PG 受影响回归 32 passed / SQLite 受影响回归 52 passed 1 skipped；Ruff **All checks passed** EXIT=0。hash：risk2-hashes.txt。

## Codex 抽查响应（HEAD 移至 95376cf，均为 docs 提交，工作区功能改动未受影响）

1. **第三方来源条件分支**：落盘终版已无 `if reference_marked` 条件分支（首轮抽查所指为中间版本）。现为确定性合成夹具 + 无条件断言：`upload_reference_version` 以 materialRole="reference" 上传版本（仓库既有第三方约定），完成后无条件断言 `references[0].provenance == "portfolio"`、`references[1].provenance == "reference"`，缺参考数据会直接失败（test_growth_answer.py:245-246，PG/SQLite 均验证）。
2. **第三次保存刷新对齐**：清空（第三次保存）后，刷新 GET 现断言与第三次回执**整体相等**（revision/updatedAt/text/references 逐字段），不再是仅 text（test_growth_answer.py roundtrip 末行）。
3. **refs 列表四项覆盖确认在盘**（非排队态）：
   - 未建草稿可读：options 测试先断言 `answer-draft` data is None，再 GET references 得 200（:265-274）；
   - 冻结基准：基准条目取自任务 base_snapshot（服务端 `_report_view` 冻结路径），测试断言与基准报告 citationIds 全集相等（:274）；
   - 跨岗位原要求不存在：跨岗位分析后 references 仅 reportKind=="base"（forge 测试 ：378）；
   - 他人/企业拒绝：企业 403（:202）、其他学生 404（:207）。
4. 抽查后重跑：audit1-target-sqlite **10 passed** EXIT=0；audit1-target-pg **13 passed** EXIT=0；audit1-ruff **All checks passed** EXIT=0；改动仅 test_growth_answer.py（audit1-hashes.txt，service hash 未变）。

## 交付物（全部在卡列所有权内）

| 文件 | 内容 |
| --- | --- |
| app/models/growth_answer.py | `GrowthAnswerDraft`：growth_task_id 非空唯一 FK CASCADE；text 非空默认 ""（String(6000)）；references JSON 默认 []；revision 整数初始 1；id/时间沿用项目 Mixin |
| app/models/__init__.py | 仅注册新模型 |
| app/schemas/growth_answer.py | 保存 payload：StrictStr 文本≤6000（不 strip、保留换行、不脱敏）、references≤20（reportId/requirementId UUID，citationId 非空≤100）、expectedRevision StrictInt ge=0（拒绝 bool/float/str）；extra=forbid；嵌套引用同样 forbid（客户端不能提交 snippet/评级/第三方标识） |
| app/services/growth_answer.py | GET/PUT/可选引用列表；锁序 User→growth（复用 EvidenceGrowthService._owned：先锁 users 行再锁任务行）；revision 乐观锁（首建 0、更新等于当前 revision，否则 409 code=4240）；引用服务端验证（422 code=4241）：只允许基准报告（冻结 base_snapshot）或本人任务当前已完成 targetReportId，requirementId 必须等于任务原要求且存在于所选报告，citationId 必须命中该要求 evidenceList 真实条目，明确拒绝重复；响应含 taskId/原 requirementId/text/references/revision/updatedAt/私人边界文案；历史引用目标变化时 GET 保留原记录并标 available=false，新 PUT 重新验证 |
| app/api/v1/evidence_growth.py | 仅新增三路由：GET/PUT `/growth-tasks/{task_id}/answer-draft`、GET `/growth-tasks/{task_id}/answer-draft/references`（学生本人；其他学生 404、企业 403） |
| alembic/versions/0015_growth_answer_drafts.py | 接 0014；真实升级/回退验证旧任务/报告/投递 JSON 完全不变 |
| app/tests/test_growth_answer*.py | 10 个回归（SQLite）+3 个 PG 并发/迁移用例 |

references 列表接口（补充第 6 条）：基准取任务冻结 snapshot；目标仅"分析已完成且原 requirementId 存在于该报告"才列出——同名技能跨岗位报告不列目标；返回 reportId/requirementId/citationId/reportKind/filePath/lineStart/lineEnd/provenance；与保存/GET 共用 `_report_view`/`_target_report_id` 来源验证；student 本人授权。

## 验证结果（原始完整输出/退出码见同目录 .raw.out，均为真实退出码）

| 套件 | 命令要点 | 结果 |
| --- | --- | --- |
| final-target-sqlite | pytest test_growth_answer.py + test_growth_answer_migration.py（SQLite 夹具，--basetemp 专属临时目录） | **10 passed**，EXIT=0 |
| final-target-pg | 同上 + test_growth_answer_postgres.py，env CAREERPROOF_TEST_DATABASE_URL=postgresql+asyncpg://…@127.0.0.1:5432/careerproof（命令行传入，未改 .env），cp_test_<32hex> 随机 schema | **13 passed**，EXIT=0 |
| regression-sqlite | 原 growth/目标岗位/迁移/real_matching/function_coverage | **52 passed, 3 skipped**（PG-only 跳过），EXIT=0 |
| regression-pg | 原 growth 三件套在真实 PG | **18 passed**，EXIT=0 |
| ruff | 对 9 个触碰文件 check | **All checks passed**，EXIT=0 |

红→绿：三个测试文件先写并于实现前运行：**9 failed / 3 skipped**（404+FileNotFoundError，见 red-notes.md，尾部捕获如实标注）。

## 覆盖的回归点（卡"必须验证"逐条）

- 创建/更新/清空与刷新读取一致（含换行缩进逐字保留、6000 边界、6001/非严格类型/额外字段/缺字段 422）。
- 首建 revision≠0 → 409(4240)；旧 revision 409 且新版本不被覆盖；PG 真实并发：首建两请求恰一胜（一 200 一 409）、同 revision 并发恰一胜（200/409/409）。
- 其他学生 GET/PUT 404（含猜 taskId）、企业 403；references 列表接口同样 403/404。
- 伪造报告/他人报告/伪造 citationId/要求不符/完全重复/超 20 条/嵌套伪造 snippet+provenance 全部 422 且草稿不变。
- 跨岗位同名技能（新岗位 skills=("Python",)）分析完成后：冒充引用 422；references 列表不列该目标（仅基准条目）。
- 第三方来源仍标参考：materialRole=reference 版本产生的证据在保存响应与列表中均 provenance="reference"。
- 目标关联变化（唯一合规返工路径：分析脱钩重选）：GET 保留原记录 available=false 不删；新 PUT 422。
- 保存前后：投递完整快照、企业回复、双方通知、ApplicationEvent 数、AnalysisTask 集合及 input_snapshot、AiUsageLog 数、growth 状态/计划/材料/固定基准全部逐字段相等；保存不创建分析或用量记录。
- SQLite 真实迁移：0009→0014→0015 升级、插入草稿、唯一约束、CASCADE、回退后 growth_answer_drafts 消失且旧任务/报告/投递 JSON 完全不变；PG 上 0015 downgrade/upgrade 与模型 schema 等价，evidence_growth_tasks 行不变。

## 自审发现与处理

1. PUT 响应与刷新读取的 updatedAt 时区后缀不一致（SQLite 重载丢 tzinfo）→ 服务层统一归一化为 UTC-aware。
2. 修订守卫测试初版时序写错（revision=1 后再提交 1 本是合法更新）→ 修正为 0→1→2→(旧1 拒)→2→3 链。
3. 下游不变测试初版在企业回复前捕获投递基线（回复合法改变视图）→ 基线改在回复后、存草稿前捕获。
4. 合成链路默认无第三方 reference 证据 → 用 materialRole=reference 项目版本（仓库既有约定）使断言确定性执行。
5. 企业回复文本需含【第1项：标题】标记（既有协议）→ 测试补齐。
6. 迁移测试比较范围误含被级联删除的行 → 限定 legacy 行。

## 边界与未验证项

- 未跑全量 939 测试套件（按卡只跑目标+受影响）；未触碰：前端、旧协议、public/cp_e2e、.env、生产建库/迁移/构建/重启、真实模型/材料/外部消息、Git 写入、P2stash。
- 迁移以模块直接加载在真实 SQLite/PG 验证（与 0014 同模式）；未走 alembic env.py 完整链升级，标未验证。
- 草稿不在企业 API/投递快照中（无新增企业端点；快照逐字段相等已验证）。前端 guard 依卡待后端交棒后另派。
