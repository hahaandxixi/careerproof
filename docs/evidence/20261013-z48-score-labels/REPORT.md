# 传智杯48 终态报告：报告尺度与证据等级文案整改（2026-10-13）

基线 main/71a2fd3（git 根 D:\jbcode\web ai\jianli）。唯一实现写入者 ZCode；Codex 并行仅改后端生产配置与正式文档（git status 中 Start/Stop-Local.ps1、backend/app/*、scripts/local-runtime.ps1、docs/当前接功.md 等非本卡改动均非本人所写，未触碰）。

## 交付内容
- 新纯格式模块 `jianli/src/lib/evidence-display.ts`：`evidenceLevelName(level)`（1/2/3 → 基础线索/局部操作/任务实现，与后端 evidence_levels.py:229 一致；未知历史等级 → `等级 N` 保留原数字，不造 /3、/5 比例）；`RULE_SCORE_CAP_NOTE`（“当前规则上限 65，分数仅表示材料支持度，不是能力满分或录用概率。”）。
- 6 组件整改：
  - SkillRadar：去 `/ 100` 后缀与 `实践证据 N/5`；分数下方与简介加规则上限说明；SVG 环刻度（雷达坐标）不动。
  - ApplicationBoard：表格头“数值为原报告0—100分”→分数+上限说明；格子 `实践证据 N/5`→等级名；完整逐项报告 `{finalScore} / 100`→`材料支持度 {finalScore}`，实践证据优先 `evidenceLevelLabel`，并注明“历史投递按原报告数值显示，不限制到 65”。
  - ReportDetail：逐项等级优先 `evidenceLevelLabel`，无标签数字兜底纯函数；`岗位权重 N / 5` 保留。
  - GrowthComparison / ReportComparisonPanel：`N/5` → 等级名；`null` → 未评级。
  - ActionPlan：`当前证据N/5` → 等级名/未评级；`岗位权重 N/5` 保留。
- `jianli/src/lib/types.ts`：MatchResult.overallScore 处 2 行注释，注明 0-100 是 MVP 遗留口径、线上为材料支持度（上限 65），防止再按成绩口径复用。
- 未改：分数公式、后端 API、历史快照数值、雷达坐标、岗位权重 /5。

## 测试（先红后绿）
- 新增 `tests/evidence-display.test.mjs`（3 用例）、`tests/score-labels-render.test.mjs`（4 用例，sucrase+react-dom/server 渲染真实组件断言可观察输出，非源码正则）。红：5/5 失败（red-run.log）。
- 正常测试数据可达值化：skill-radar-render/skill-radar 85/55/20→65/40/10；历史/异常兼容用例（等级 4、等级 80）保留并注明。
- 目标测试 41/41 绿（target-tests.log）；全量前端 249/249 绿（frontend-full.log）；`tsc --noEmit` 0 错（typecheck.log）。无失败日志需单独保留（红日志即失败留档）。

## 工具来源与约束
- Node v22.23.1；sucrase 3.35.1 解析自 `jianli/node_modules`（前端自身已装依赖，非 backend/.tmp/dep-frontend-20261010 目录）。未安装依赖、未构建共享 Next、未启停服务、未改 DB/.env/launcher/旧guard/P2、未真实模型调用、未提交推送。

## 未运行（须注明）
- 真实浏览器页面验收未运行，按卡由 Codex 后续安排。
- ApplicationBoard/ReportDetail 整树渲染受 AccessGate/useAuth 会话限制，沿用仓库既有“导出纯函数 + 纯属性子树渲染”测试形态；其新文案中的常量与等级名与已渲染组件同源（evidence-display.ts / RULE_SCORE_CAP_NOTE）。

文件 hash 见 hashes.txt。
