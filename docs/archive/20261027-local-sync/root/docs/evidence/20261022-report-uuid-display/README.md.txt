# 报告页内部 UUID 显示修复

状态：显示层修复完成；不改存储、API、评分、检索或数据。未提交。

## 修复

- 前端新增纯函数 `jianli/src/lib/display-path.ts`：
  - `displayFilePath`：只剥离开头的 material-version UUID；
  - `displayFilePathText`：剥离解释/缺口文本里嵌着的 UUID 前缀。
- 用在报告页和相邻证据展示：`ReportDetail`、`EvidenceCard`、`ReportAgentEvidence`、`SkillRadar`、`SourceCoverage`、`EvidenceSnippet`、`EvidenceChain` 的卡片渲染、`ReportComparisonPanel`、`GrowthComparison`、`ReportEvidenceWorkspace`、`ReportItemExplanation`、`CareerRecommendations`、`ApplicationBoard`、`ApplicationVerification`、`PrivateAnswerDraft`。
- 隐藏了两个无助于用户识别的内部版本 ID 文本：
  - 材料版本校验中的 `material.id`；
  - 证据定位信息中的 `projectVersionId`。
  仅改显示，`href` 和 API 数据未改。
- 段一缺口文案改为短名分组，例如：
  `规则层另有未发送材料：README.md 第1–9行、第16–18行；runtime/pytest-output.txt 第1–8行。材料中可能已包含，请先核对；仅对核对后仍未覆盖的场景再补充。`
- 后端 `rule_narrative` 的 reason/gap 也通过 `display_path.py` 剥离开头 UUID，并保留完整存储值。

## 验证

- 报告页实际渲染（当前源码 dev 预览 3130，Mock 报告 `ac09...`，8108 后端）：
  - 可见文本 UUID 数：**0**
  - 去掉 script/style 后的文本 UUID 数：**0**
  - 截图：`report-1280-dom.png`
  - 原始结果：`dom-check.json`
  - 说明：Next.js 的 hydration script 仍含页面 route 参数（报告 ID），不是渲染给用户的文本；检查时已排除 script/style。
- 前端单元测试：`tests/display-path.test.mjs` 4 passed，覆盖无前缀原样返回、多段斜杠只剥第一段、文本内嵌前缀；UI 回归共 20 passed。
- 后端目标测试：`test_display_path.py`、`test_evidence_scope.py`、`test_rule_narrative.py`、`test_ai_evidence_workflow.py`：**63 passed**。
- 前端 `tsc --noEmit` exit 0；后端 Ruff 通过。
- 未调用模型，未重跑规则报告，未改证据条数、行号、verdict、level。

## 未完成 / 边界

- 全部改动尚未提交，交 Codex 审查；`ReportDetail.tsx` 还保留此前未提交的页面改动，本修复只在其上追加显示处理。
- 没有改 `filePath` 的存储值或 API 返回。
- 片段正文（`snippet`）仍按材料实际内容展示；只处理路径和解释/缺口文本。
