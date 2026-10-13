# 传智杯27：依赖、升级页面与离线AI质量目标逐项完成审计

2026-10-11。ZCode按[任务卡](../历史任务协议.md#task-057)对[原目标](../../任务清单.md#当前目标首版交付线)逐项映射证据。开始HEAD 61c3d54；审计期间HEAD前进到02df7b1（fed29db=本卡派发、02df7b1=传智杯28协议卡，`git diff 61c3d54..02df7b1`仅docs 3文件45行插入，无源码/测试变更）。审计方式：只读核对原始日志与JSON数字，不重跑全量已通过测试（原始pytest/浏览器/SQL日志已在对应证据目录且经Codex签收，重复执行只增加成本不增加信息）；未触库/未起服务/未联网/未安装。原始核对输出见[raw.out](raw.out)，文件hash见[manifest.json](manifest.json)。

状态取值：已证明＝原始日志/JSON数字与声明一致且范围如实标注；受控缓解＝按原目标"已修/受控缓解/需后续"授权的权威残余处置；矛盾/未完成＝无。本次审计未发现矛盾项。

## 一、依赖（DEP-01/02/03 + 传智杯24）

| 原目标要求 | 证据 | 核对结果 | 状态 |
|---|---|---|---|
| 首批3包multipart 0.0.31/Pillow 12.3.0/PyJWT 2.15.0，独立venv、新旧版本差异、pip check、正反例、失败与绿灯分开 | [20261009-DEP-01-first-batch/README.md](../20261009-DEP-01-first-batch/README.md) | 独立.venv-dependency23、逐包pip check、基线117→升级目标、17项真实行为回归、fastembed pillow<12冲突如实留为交棒未冒称兼容 | 已证明 |
| 首批遗留冲突闭合＋真实CPU模型3项零跳过、受影响130零跳过（df7f3fa） | [README](../20261010-DEP-fastembed-compatibility/README.md)、[codex-signoff.md](../20261010-DEP-fastembed-compatibility/codex-signoff.md) | `pytest-affected-11files.raw.out`=130 passed, 0 skipped；Codex独立重跑3项兼容测试3 passed 0 skipped、真实CPU ONNX；两venv 6×384最大差0、余弦≥1-1e-9、5权重hash一致、pip check干净 | 已证明 |
| FastAPI0.143.0/Starlette1.3.1联合解析，声明兼容＋实际目标/受影响/阶段全量，不仅强装 | [DEP-framework/README.md](../20261010-DEP-framework/README.md) | Starlette同钉prod+mcp extra；OpenAPI 64路径一致+逐字段差异记录；旧目标68/升级目标72/离线全量1090/PG专项59；旧venv启动被guard拒绝（old-e2e-refusal） | 已证明 |
| Next15.5.27、sharp0.35.5、source-map-js1.2.2、**Next嵌套**PostCSS单独修复不以root掩盖 | [DEP-frontend/README.md](../20261010-DEP-frontend/README.md)＋HEAD实测`jianli/package.json` overrides=`{sharp:0.35.5, source-map-js:1.2.2, next.postcss:8.5.28}` | next专属override，声明仍8.4.31如实记录；193测试×2+typecheck+生产构建；5组合成CSS含390px/中文与source map同基线 | 已证明 |
| pip26.2.1、pytest9.0.3+asyncio1.4.0、Mako1.4.2 | [DEP-toolchain/README.md](../20261010-DEP-toolchain/README.md) | 完整离线1094通过/46跳过（每类PG跳过理由列出）；Mako真实模板渲染7项（收集后加入，未冒称计入1094）；PG专项79 | 已证明 |
| 13项各有权威依据；未升级两项braces3.0.3/selector-parser6.1.4处置 | [dependency-disposition.md](../20261010-DEP-residual/dependency-disposition.md)＋npm-audit-official.json | 官方审计7受影响包=两公告经父依赖传播（high 5）；braces first_patched_version=null、selector-parser修复7.1.6跨major超范围——不编造补丁、不强装、不audit fix --force；缓解=受信源码入口边界；Tailwind4迁移裁决暂缓并写明重新排序条件 | 已证明（受控缓解+需后续，残余不入清零） |

生产pin与处置表逐项一致（HEAD `backend/pyproject.toml` 实测核对，见raw.out §2）。

## 二、升级后真实页面（E2E）

| 原目标要求 | 证据 | 核对结果 | 状态 |
|---|---|---|---|
| 独立库/存储/端口/构建、升级解释器与前端stage实际使用、迁移0017 | 四个隔离run（upgrade-20261010 / upgrade-budget-20261010 / budget-matrix2-20261010 / question-chain-20261010），cp_e2e同名库、0017、8001/3001、MockTransport；Start-E2E `-BackendVenv` guard | alembic当前head=0017（实测）；旧venv被运行时guard拒绝；旧.venv/旧服务不升级＝原目标明文设计 | 已证明 |
| 学生：缺口→补证→上传新版→新报告→逐项变化（材料/岗位/两者）＋390px | [student-enterprise-checkpoint.md](../20261010-E2E-upgraded-runtime/student-enterprise-checkpoint.md) | variant-materials/job/both均exit 0，变化背景对应、逐条解释、刷新一致、390无溢出；夹具不足的两轮失败原文保留并修runner前置等待 | 已证明 |
| 企业核验/回复/撤回/通知，旧锚点旧通知不可访问；刷新可读 | [budget-first-verification-checkpoint.md](../20261010-E2E-upgraded-runtime/budget-first-verification-checkpoint.md) | 生成/复用/重开可读；撤回A后旧A锚点与旧通知不可用、B正常；首探针blocked不算通过，补点击后31项保护通过，失败原文保留 | 已证明 |
| 预算known/held/unknown/失败提示＋严格390px＋合法库存闸门 | [README](../20261010-e2e-budget-matrix/README.md)＋audit-final.json＋results.json | 独立只读SQL：恰3 attempt（1 booked 100/80＋2 usage_unknown）、3预留（1 settled 100/80＋2 held 4013/3000）；页面八状态文本与SQL一致；503失败不自动重试、刷新不归零；八次innerWidth=scrollWidth=390（断言实现于共享runner `enterprise-browser-runner.mjs:777,1559`）；预算激活走生产SharedBudgetService审计，旧run激活被真实审计拒绝回滚 | 已证明 |
| 企业具名问题→站内回复→学生补证→新报告逐项解释→通知 | [README](../20261010-enterprise-question-growth/README.md)＋independent-chain-with-jobs.json | 同owner同岗位sameFrozenRequirements=true、种子要求逐字段相等、目标分析completed；recheck-window-only明确标记，全链不变量由种子冻结要求独立证明——未用窄窗口冒充 | 已证明 |
| 三固定投递hash不变；跨run不混用任务ID | both-run-snapshot-check.json、budget-known-independent.json、audit-final.json、independent-chain-with-jobs.json | 4个run各自3快照hash全部不变（跨run独立只读核对）；matrix任务ID（078c6aa6等3个）与question-chain任务ID独立成套，无混用 | 已证明 |

失败修复复验链完整：chain-reply夹具缺企业回复上下文→修复后question-chain闭合；预算单列显示d290aec→known 200/160复验；matrix三次失败（CDP等待/鼠标定位/正则转义）→成功run重验、旧库保留；390px窗口限制假象→显式Emulation视口三次记录。

## 三、AI离线三维评测

| 原目标要求 | 证据 | 核对结果 | 状态 |
|---|---|---|---|
| 固定离线样例＋一键runner＋正反例/基线/指标/原始结果 | [handoff-20261010.md](../20261010-AI-quality-dimensions/handoff-20261010.md) | 冻结cases.json先于runner；引用8例/建议6类×13探针/变化9组；两遍除generatedAt字节一致（run1/run2） | 已证明 |
| 三维指标＋6类缺口＋无变化/恶意引用/第三方参考 | handoff样例族对照表 | 6缺口各有正反例；no-change；旧报告越界引用（cit-old-report-reorder+chg-old-citation-out-of-bounds）；第三方参考cit-reference-only拒＋cit-gap-reference-mention合法提及裁决保持gap | 已证明 |
| 生产对应性（contract/retrieval/comparison） | final-run1.json sourceHashes | 契约=app.agents.contracts、检索=enrich_evidence/build_evidence_contexts、比较=report_comparison+evidence_key，9个生产模块逐一入册hash | 已证明 |
| 固定数据可重跑两遍＋独立反例 | [codex-holdout/README.md](../20261010-AI-codex-holdout/README.md) | `final-target.raw.out`=15 passed（10目标+5独立反例：跨版本重放/角色改变/空泛建议/哈希篡改/分母注入）；repeat-check equalExceptGeneratedAt=true；ruff通过 | 已证明 |
| 不把Mock冒称真实模型能力 | final-run1.json | generatedWebsiteModelOutputs=0、operabilityCounts=null（"not-measured: authored draft labels only"）、semanticQualityPassRate=null、humanReview=false——声明一致 | 已证明 |
| 独立模型盲评（传智杯26，范围外补强） | [codex-review.md](../20261010-AI-blind-plan-review/codex-review.md) | 2负例识别、3实质缺口、2待裁点已裁决；来源矛盾单列不被总分抵消 | 已证明（不升级为网站真实质量） |

**局限（必须随结论带入）**：真实网站生成样本0、humanReview=false、语义类指标null——现有全部指标是结构/契约/规则指标，作者覆盖率（6/6）不是实际可执行性。原目标文字只要求"固定数据可重跑+不冒称真实"，未把真实模型或人工语义设为离线完成条件，故不构成本目标缺口；口径修正（改名authoredOperabilityCounts、分母/作者覆盖率修正）已由Codex签收完成。最小有界动作＝传智杯28组合CLI（协议卡02df7b1已派发）：把三维结构报告与8例盲评确定性回放合成一键可审计基线，null进分母、来源矛盾不通过不被抵消——直接消解"结构过线≠草稿可执行"的表述残余，不新增真实模型前提。

## 四、完成条件判定与P2

- 依赖处置、升级后页面、AI可重复评测三大块：逐项有原始证据且数字核对一致，**未发现矛盾项或未完成项**。
- 本审计发现的唯一重大限制是上述语义盲区（样本0/语义null）＋两项依赖残余＋SQLite全量46项PG跳过未补（已有PG专项59+79覆盖高风险，跳过如实声明）——均为原目标框架内已声明的边界，非缺口。
- **P2**：按证据保持暂停（真实模型语义与独立人工均未测量，恢复无基线）。下一有界方向：①执行传智杯28组合CLI；②以"来源矛盾直接不通过、具名交付物/可执行步骤/可观察核验单列理由"为生成样本验收门槛，采集真实授权输出后单独请求P2决策。不以Token余额为开发理由。

## 签收建议（最终Codex裁决）

建议按原目标范围签收"依赖13项处置（含两项受控残余）、升级后独立环境页面链路、AI离线可重复三维评测"为完成；三条限制必须写入接力：语义盲区（0样本/语义null）、braces/selector-parser残余与Tailwind4迁移未做、PG跳过46项未补。

## 优先动作（≤3）

1. **执行传智杯28**（已派发）：组合CLI固化"结构三维＋盲评回放"基线，来源矛盾不抵消、null进分母；完成后更新接力引用。
2. **残余依赖跟踪**：Codex阶段签收时按处置表复核braces/selector-parser公告与registry/lock；出现6.x补丁、Tailwind4候选或新CSS入口即启动单独有界批次（含panel/field/button、中文、390px验收）。
3. **P2决策前置**：传智杯28后若采集到真实授权输出，以来源矛盾/可执行性门槛为验收基线单独请求恢复或扩链决策，默认保持暂停。
