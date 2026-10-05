# E2E-03-PREFLIGHT：学生补证新版闭环只读调查

日期：2026-10-05。基线：AI 旧范围已签收本地提交 9e87fec。本调查只读源码与既有证据，未读写数据库、未开浏览器、未重启/构建服务、未执行 Git 操作、未触碰产品/测试/运行器/正式文档。隔离 run 现状沿用 `docs/evidence/20261004-E2E-enterprise/SCENARIO-SUMMARY.md`：run A 已撤回不可恢复，A2（8032fdb1）/B（d9c64113）有效；岗位 A/B 由合成企业持有，各只有 1 条 Python 要求。

## 1. 学生补证链路的准确页面步骤（含 file:line）

1. **建任务**：学生登录 → `/reports/{reportId}` 打开本人报告 → 目标要求项内点"从这条缺口创建或打开补证任务"（`jianli/src/components/GrowthTaskStart.tsx:28`）→ 展开时 GET 已有任务与企业回复上下文（`GrowthTaskStart.tsx:33-46`）→ 填缺口类型/交付物/步骤/核验条件（每类最多 5 行）→ "保存并进入补证" POST（`GrowthTaskStart.tsx:60-69`）→ 跳 `/growth/{id}`。
   - 若企业回复存在，报告 URL 带 `?enterpriseReply={requirementId}` 可自动展开（`GrowthTaskStart.tsx:29-31`）。
   - 同一 (报告, 要求) 重复创建会返回原任务（`backend/app/services/evidence_growth.py:61-69`）。
2. **传新版材料**：任务页第 2 节"前往上传新版材料"链接到 `/portfolio?growthTask={id}`（`GrowthWorkspace.tsx:86`）→ 上传页顶部显示回跳提示（`GrowthUploadReturn.tsx:6-10`）→ 新建项目 POST `/portfolio/projects`（`backend/app/api/v1/portfolio.py:155`，字段 name/description）或给原项目上传版本 POST `/portfolio/projects/{id}/versions`（`portfolio.py:167`，multipart：file、materialRole=portfolio|reference，202 后台解析）→ 新简历版本 POST `/portfolio/resumes`（`portfolio.py:130`）。解析完成后回任务页。
3. **保存材料选择**：任务页第 2 节选简历版本 + 项目版本 → "保存本次材料选择" PUT `/growth-tasks/{id}/materials`（`client.ts:291`）。服务端约束：分析已开始则锁定选择（`evidence_growth.py:155-164`）；所选材料键 (kind, contentHash, materialRole) 必须与基准不同，否则 409"与基准内容相同"（`evidence_growth.py:26-28,166-171`）。
4. **生成新报告**：第 3 节勾选 AI 外发同意 → "生成新报告" POST `/growth-tasks/{id}/analyze`（`client.ts:292`，`external_ai_consent` 布尔）。服务端：固定 jobId=基准报告岗位、use_previous_report=False（`evidence_growth.py:191-201`），材料快照复核一致后才建任务并 202（`evidence_growth.py:178-208` → `analysis.py:186`）。任务执行在 `/tasks/{analysisTaskId}` 页可看进度（claim→25%读材料→55%规则证据→85%保存，`analysis.py:511-601`）。
5. **逐项变化解释**：完成后任务页第 4 节 GrowthComparison 渲染：背景变化标签、逐项等级 base→target、新增/不再展示证据（带引用锚点与第三方参考标注）、企业问题核对块、limitations（`GrowthComparison.tsx:16-45`）。比较数据来自 `compare_views`（`backend/app/services/report_comparison.py:73-165`）；报告侧另有 GET `/match-reports/{base}/comparison/{target}`（`api/v1/analysis.py:222-230`）与 previous-comparison（`analysis.py:213`）。
6. **企业回看不变**：学生新报告不更新投递快照（`evidence_growth.py:283-286` 边界文案；growth 分析从不写 Application）。

## 2. 关键接口字段（页面→后端）

- POST `/match-reports/{report_id}/growth-tasks`：`{requirementId, gapKind: implementation|execution|contribution|review, deliverable≤1000, steps 1..5, acceptanceChecks 1..5}`（`schemas/evidence_growth.py:12-18`）。
- PUT `/growth-tasks/{id}/materials`：`{resumeVersionId, projectVersionIds[]≤10}`（`schemas/analysis.py:14-16`）；项目版本必须 `analysis_status=completed`、简历必须 `parse_status=completed` 且有提取文字（`services/matching_materials.py:63,71,96-97`）。
- POST `/growth-tasks/{id}/analyze`：`{externalAiConsent}`；返回含 `status/analysisTaskId/analysisStatus/targetReportId/comparison`（`evidence_growth.py:256-287`）。
- 比较结果：`contextChanges[]`、逐项 `changes[]/addedEvidence[]/removedEvidence[]/baseLevel/targetLevel/baseRequirement/targetRequirement`、`limitations[5]`（`report_comparison.py:155-165`）。

## 3. Mock 如何产生"真实新版分析"

- 隔离环境强制 `AI_EXTERNAL_ENABLED=false`/`AI_PROVIDER=mock`（`docs/task-cards/20261004-E2E-isolated-environment.md` 第2条）。执行链：`execute_match_task` → `analyze_materials` 规则检索证据（`analysis.py:519-521`）→ `run_evidence_workflow`：`get_ai_provider()` 返回 `MockAIProvider`（`agents/provider.py:935-937`），工作流遇 `provider.name=="mock"` 直接返回 `analysis=None`（`agents/evidence_workflow.py:365-366`）→ 报告 `analysis_metadata.mode="rules"`、`evidence_context_version="source-context-v8-actionable-evidence-gaps"`（`analysis.py:616,633-635`）。
- **结论：Mock 模式的新报告是完整真实的规则分析**（matcher 证据检测、证据分级、评分、逐项引用），不是 AI 解释。勾选外发同意在 mock 下不产生任何外呼（`analysis.py:556` 直接跳过）。比较页的"新增/缺失证据与准确引用"全部来自规则证据列表差异，可闭环验证；"解释/建议"变化在 mock 下为空或不参与（`ai_status=not_used`，`analysis.py:746-748`）。
- 等级/verdict 由证据强度决定：Python 技能检测器只有 `python_code`（high，AST 验证函数有实际行为，`tools/code_analyzer.py:161-168,494-546`）与 `python_dependency`（medium，requirements/pyproject 含框架名，但依赖类强制降为 low，`code_analyzer.py:666`）；`.md/.txt` 对 Python 不产证据（`code_analyzer.py:576-578`；DOCUMENT_RUBRICS 仅活动策划/用户调研/内容运营，`code_analyzer.py:375-379`）。verdict：有 claim 无代码证据=claimed_only，high=supported，medium/low=partial（`tools/matcher.py:126-144`）。

## 4. 三种归因场景可行性

`compare_views` 背景标签：materials（材料键含 id/hash 变化）、requirements（两份报告冻结的 job_snapshot.requirements 不等）、retrieval_version、model_or_mode、rule_version（`report_comparison.py:84-95,114-119`）。

1. **只换材料**：✅ 页面完整支持，无需扩展。基准若用 seed 报告，会额外出现 `requirements`+`rule_version`+`retrieval_version` 标签——因为 seed 报告 job_snapshot 只有 title/category 无 requirements 键（`seed_e2e.py:471`）、formula_version="e2e-fixture-v1"（`seed_e2e.py:486`）且无 analysis_metadata。这是**夹具形状差异，不是真实要求变化**，须在证据中"分别说明"；或先经页面生成一份同引擎基准报告再做干净对比。
2. **只改岗位要求**：❌ 页面不可达，属产品设计而非缺陷。岗位要求一旦存在任何 MatchReport 即锁定（`services/jobs.py:135-142`"岗位已有匹配任务或报告，要求已锁定；请新建岗位以调整要求"，判据含 seed 报告，`repositories/jobs.py:98-110`）；而补证分析永远用基准岗位 id（`evidence_growth.py:193`），比较又要求同岗位（`report_comparison.py:74-75`）。因此同一岗位两份页面报告的需求快照必然相同，"requirements"背景变化无法经页面产生。
3. **两者同时改变**：❌ 同上，requirements 半边不可达；materials 半边可达。

另注意：seed 岗位只有 1 条要求，任务按 (报告,要求) 唯一去重（`evidence_growth.py:61-67`），两个材料场景不能复用同一基准报告的同一要求——可用学生两份有效基准（B 与 A 底层报告，学生本人报告不受投递撤回影响，页面阶段需实测确认）或从新报告链式建第二任务（UI 文案支持）。

## 5. 夹具缺口与是否需要隔离 fixture 扩展

- **缺口 1（必须处理）**：seed 只建 ResumeVersion v1，未建 ResumeSection（`seed_e2e.py:412-441`）；补证 analyze 时 `resolve_materials` 拼简历文字为空 → 4095"简历未提取到文字"（`matching_materials.py:65-72`）。**但无需扩展夹具**：让学生经页面真实上传简历 v2（真实解析管线会建 ResumeSection，`services/portfolio.py:434-442`），attach 选 v2 即可；若选 v1 会得到明确 409 且任务停在 materials_selected 可重试（`evidence_growth.py:199` 在建任务前失败，不留悬挂状态）。
- **缺口 2（需裁决）**：场景 2/3 的 requirements 归因无法页面产生（见第 4 节）。
- **缺口 3（时间依赖）**：card 第 4 条的"企业具名回复"需先由企业在 A2/B 投递上经页面发送回复（`_enterprise_reply` 查 consent+reply_text，`evidence_growth.py:115-126`）；E2E-02 前端修复与运行器审查尚在进行，页面测试须等 Codex 统一重建后执行。
- 结论：**场景 1（只换材料）+ 失败路径 + 企业回看不变，均可用现夹具+页面真实操作完成，不需要扩展 fixture**；扩展仅在与 requirements 归因相关的裁决项上可能需要。

## 6. 需 Codex 裁决的最小依赖

1. **requirements 归因覆盖方式**：(a) 接受"页面证据证明产品正确锁定要求（PATCH 返回 4095 留证）+ 离线 compare_views 回归覆盖 requirements 标签"；(b) 或批准 seed 扩展一个明确标注的合成对照报告对（同岗位、不同冻结要求快照，仅用于比较页展示，绝不冒充页面生成报告）。二选一，不允许 SQL 改旧快照。
2. **两个材料场景的基准分配**：用 B/A 两份报告分别承载"声明不足版"与"新版"，还是单报告从新报告链式建第二任务。
3. **页面阶段开工时间**：等待 E2E-02 前端修复落地与统一重建；本 preflight 不启动任何页面测试。
4. 确认 E2E-03 允许文件范围是否包含新学生端运行器（如 `scripts/e2e/student-growth-runner.mjs`）——现卡只写"本卡新运行器"，未命名。

## 7. 合成材料示例（本目录 materials/，全部标注合成，未假冒实际执行）

| 文件 | 用途 | 离线规则引擎验证结果 |
| --- | --- | --- |
| `resume-v2.txt` | 页面上传的新简历版本（含技能声明行供 claim 检测） | 未单独验证（依赖真实解析管线建 ResumeSection） |
| `claims-only-project.zip`（sha256 前缀 38d3ff76bd3cccc2） | 声明不足版：README 夸大声明 + pipeline.py 仅 pass/... 占位 | `find_evidence(files,"Python")=[]` → 新报告 verdict 保持 claimed_only，**不冒充实现** ✅ |
| `new-version-project.zip`（sha256 前缀 06399fb3e95be902） | 新版：pipeline.py 具名实现 `process_records`（AST 有行为）+ tests/test_pipeline.py 两条 assert 用例 + requirements.txt(pandas) + docs/run-log.md 合成运行记录 | `[python_code high ×2, python_dependency low]` → verdict 升 supported，新增证据可被比较页逐条引用 ✅ |

验证方式：直接调用 `app.tools.code_analyzer.find_evidence` 纯函数（离线、无数据库），2026-10-05。运行记录文件本身明示"合成示例，未实际执行"；页面阶段如需真实执行记录须另行真实生成。

## 8. 未验项与风险

- 学生对已撤回投递（A 底层报告）的报告访问在页面的实际表现未实测（代码上报告为学生自有，服务端 get_report 按创建者校验）；建议优先用 B。
- 上传 zip 的 archive_scanner 对小 zip/中文文件名的接受度未实测。
- 语义检索在隔离库的 embedding 行为未查（enable_semantic 默认 True，`matching_materials.py:140`）；如隔离环境关闭语义检索，证据结果仍由关键词检测器保证。
- 简历 v2 的技能声明行与 seed 岗位要求文案不同——claim 检测按技能名归并（matcher claims_by_skill），已保证含"Python 编写数据处理脚本"字样；页面阶段需确认 claimed_only→supported 链路。
- 本调查的所有结论来自源码阅读与纯函数验证，未经页面复现；页面首验仍是 E2E-03 的必要环节。
