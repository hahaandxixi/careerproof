# 2026-10-19 学生端/企业端报告一致性

范围：核对同一份固定报告在学生端与企业端的底层数据与页面显示，修复一个共享展示规则不一致的问题。没有改后端序列化、授权、快照、评分、数据库或 AI。

**结论限定**：已核对的这一份规则报告（`1b6c…`）在学生 API 与企业投递快照中的共同字段完全一致；学生/企业的规则模式与历史摘要展示文案已统一。其他报告模式、首次独立用户、候选版整体验收不在本结论内。

## 一、比较对象

正常站同一份报告：

| 项 | 值 |
| --- | --- |
| 岗位 ID | `151b3397-7cc4-48f4-96fc-aabd4f346f3c` |
| 报告 ID | `1b6c0425-848a-4229-8cc8-cc4d4447ba54` |
| 投递 ID | `b756d9c2-f7e9-47d4-a12c-8e1bc61a54f3` |
| 学生视角 | `GET /api/v1/match-reports/{id}` |
| 企业视角 | 该投递的 `report_snapshot`（投递时冻结） |
| 生成时间 | `2026-10-16T06:08:54.285260Z` |
| 规则/上下文版本 | `source-context-v8-actionable-evidence-gaps` |
| 报告模式 | `rules` |
| 共同内容 | 5 项要求、20 条证据 |

**底层数据完全一致**：学生报告 JSON 与企业投递快照 JSON 的规范化 SHA256 均为
`f8d7e47a8df1e1283f670d17c5c10325aa254bc5e911efbdd1424a89aee2d8cc`，5 个 requirementId 集合和每项 evidenceList 逐项相等。详见 [normal-same-report-comparison.json](normal-same-report-comparison.json)。

因此本轮没有把差异误判成后端序列化、角色过滤或快照改写。

## 二、问题清单

| 场景 | 学生端 | 企业端 | 判断 | 依据 | 最小处理 |
| --- | --- | --- | --- | --- | --- |
| 同一规则报告的模式 | “规则证据报告” | “报告模式：rules” | **缺陷（P2，状态用语）** | 同一 `analysisMode=rules`，企业直接暴露内部枚举 | 共享 `reportModeLabel` |
| 同一历史报告摘要 | “评级描述材料证据……且不评级” | 原摘要“分数为材料支持度……且不计分” | **缺陷（P2，共同文案）** | 同一份摘要，学生端做了展示归一，企业端没有 | 共享 `reportSummaryText` |
| 企业报告头部上下文 | “学生 × 岗位 + 时间” | 只有候选人 + “固定报告”，无岗位/时间 | **缺陷（P2，对象识别）** | 企业报告页是岗位路由，但报告区未显示岗位和生成时间 | 增加已有 `jobTitle/createdAt` 与固定快照说明 |
| 企业只看固定报告 | 学生有新版报告、私人补证任务 | 只显示投递快照 | **合理差异** | 授权范围不同；学生新版不自动分享 | 保留，不扩大企业访问 |
| 企业核验/回复、学生通知/补证 | 不显示企业核验与回复表单 | 显示核验建议、回复区 | **合理差异** | 角色专属操作 | 保留 |
| 审查/本人核对状态 | 学生可采纳/驳回 | 固定快照保留投递时状态 | **合理差异** | 历史快照不随当前核对改写 | 保留；企业页已有“固定报告”说明 |

没有发现 P0（越权/泄漏/错误收件人/快照改写）或 P1 数据错误。最高实际问题是同一报告在两端用了不同的模式和摘要文案，属于共同展示映射缺陷。

## 三、修复

新增 [report-display.ts](../../../jianli/src/lib/report-display.ts) 作为极小的共享显示层：

- `reportAiRatedCount`：只统计 `evidenceLevelSource=ai_preliminary`；
- `reportModeLabel`：规则 / AI 解释 / AI 初评 / 降级四种模式统一；**未知 `analysisMode` 返回“未知报告模式”，不再默认当作规则报告**；
- `reportSummaryText`：只替换两处旧展示措辞，不改数据、不重算。

接入：

- [ReportDetail.tsx](../../../jianli/src/components/ReportDetail.tsx)：学生报告页改用共享模式与摘要；
- [ReportList.tsx](../../../jianli/src/components/ReportList.tsx)：列表摘要复用同一归一；
- [ApplicationBoard.tsx](../../../jianli/src/components/ApplicationBoard.tsx)：企业固定报告使用同一模式/摘要，并增加已有岗位名、生成时间和“后续新版不会改写本次投递”。
- [report-display.test.mjs](../../../jianli/tests/report-display.test.mjs)：模式与历史摘要回归。

没有修改后端、快照、报告生成、证据等级、授权或通知。

## 四、验证

环境：受管理的 `backend/.tmp/dep-frontend-20261019-consistency`；Next 15.5.27、ESLint 9.39.5、Node 22.23.1；锁文件 SHA256 与仓库一致。未知模式修正后只复跑受影响检查：

```powershell
node --experimental-strip-types --test tests/report-display.test.mjs
# 2 passed；包含未知 analysisMode -> "未知报告模式"

npm run typecheck
# exit 0

node_modules/.bin/eslint src/components/ApplicationBoard.tsx src/components/ReportDetail.tsx src/components/ReportList.tsx src/lib/report-display.ts tests/report-display.test.mjs
# exit 0，无诊断

NEXT_DIST_DIR=.next-unknown-check npm run build
# exit 0，Next 15.5.27；仅既有 VisualEvidencePanel <img> 警告
```

原始输出：[report-display-unknown-mode.raw.out](report-display-unknown-mode.raw.out)、[typecheck-managed.raw.out](typecheck-managed.raw.out)、[build-after-unknown.out](build-after-unknown.out)、[eslint-managed.summary.txt](eslint-managed.summary.txt)。早先更宽的 20 项检查结果仍保留在 [targeted-tests.raw.out](targeted-tests.raw.out)，但不作为未知模式修正后的复跑证据。

### 受管理运行环境

- 前端 stage：`backend/.tmp/dep-frontend-20261019-consistency`（真实依赖副本，不是 junction）；`.next` 由 `Start-Local.ps1` 生成。
- 后端：`.venv-dependency23`；`.venv` 对本轮 pin 校验失败，不能作为日常可用环境。
- `Start-Local.ps1 -BackendVenv .venv-dependency23 -FrontendStage dep-frontend-20261019-consistency` 生成新 `backend/.tmp/local-run/processes.json`。
- `Stop-Local.ps1` 实际停止两个受管根进程，3000/8000 释放、清单删除；随后 `Start-Local.ps1` 复用已验证构建重新生成清单，3000/8000 均 200。
- 当前清单根：后端 PID 451264（`.venv-dependency23\Scripts\python.exe`）、前端 PID 449268。前端监听 PID 与清单一致；后端监听 PID 451320 是 venv launcher 启动的 base python 子进程（父 451264），不是手工临时进程。`Stop-Local.ps1` 已验证 2 个根并实际终止其子进程。
- 详细清单、监听树和说明：[local-run-processes.json](local-run-processes.json)、[managed-runtime.txt](managed-runtime.txt)、[managed-cycle.txt](managed-cycle.txt)、[normal-services.txt](normal-services.txt)。

### 页面

- 正常站 3000（受管理重启后）：学生报告 `1b6c…` 实际页面显示“规则证据报告”，摘要为“评级描述材料证据……”，桌面 1280 与 390px 均无整页横向溢出。截图：[student-report-current.png](student-report-current.png)、[student-report-mobile-390.png](student-report-mobile-390.png)。
- 隔离克隆 3001/8001：企业打开同一候选人的固定报告，显示“报告模式：规则证据报告”、岗位、生成时间和“后续新版不会改写本次投递”；390px 无整页横向溢出。截图：[enterprise-report-current.png](enterprise-report-current.png)、[enterprise-report-mobile-390.png](enterprise-report-mobile-390.png)。记录：[enterprise-report-current.json](enterprise-report-current.json)。
- 隔离页使用的是既有 E2E 克隆库 `cp_e2e_enterprise-filter-20261019`，报告 `f11c…`；学生侧同一报告 API 返回 `rules`、1 项要求，见 [isolated-same-report.json](isolated-same-report.json)。它与正常站报告不是同一份，只用于验证企业页展示，不代替正常站企业打开报告。

## 五、差异与边界

合理差异：

- 企业不读取学生新版报告、其他岗位报告、私人补证任务；只读投递快照。
- 学生有本人核对、补证、私人材料；企业有核验建议与站内回复。
- 企业固定快照不会因为学生当前核对/新版而改写。

未验证 / 未做：

- **正常站企业报告未打开**，避免写入 viewed 事件/通知；正常站企业展示由隔离克隆页验证，不是正常库企业页。
- 正常站只读检查包括登录（会话/限流写入）、学生报告 GET；没有新增/撤回/重投/发送消息。
- 没有真实模型调用、邮件、SMTP、自动外发。
- 没有做首次独立用户走查；没有重新计算历史评级。
- 没有改 3001 受保护环境；本轮 3001/8001 是自有隔离服务，截图后已停止并释放端口。
- 正常站 3000/8000 已由受管理流程启动并当前运行：3000 使用 managed stage 的 `.next`（非冻结候选），8000 使用 `.venv-dependency23` 与正常库；PIDs 见 [normal-services.txt](normal-services.txt)。开始时 3000/8000 均为离线。
- 共享函数只改展示，不改数据。旧报告如包含其他未知旧措辞，仍按原文显示，不凭空扩展替换。

## 六、提交与 Codex 下一步

- 本轮执行端已只显式暂存并提交 5 个文件 + 本证据目录；`docs/当前接力.md`、`docs/guides/使用与启动.md`、`JobDetailView.tsx` 及上一轮 backend Agent 三文件保持未提交。
- Codex 复验：5 文件 diff、干净锁定环境重跑受影响 2 项测试/typecheck/lint/构建、`local-run/processes.json` 所有权和正常站健康。
- 如需正常站企业页确认，可打开一条合成投递；该操作会写 viewed 事件/通知，需按正常站写入边界另行授权，不能算纯只读。
- 当前 3000/8000 是受管理启动的验证环境，不是冻结候选；冻结前仍按候选流程重建。
