# 传智杯51：报告页"动作层"收敛建议

基线：main/f781a5b，Git 根 D:\jbcode\web ai\jianli。建议提出时间：2026-10-13 23:46（北京时间），非高峰。

来源：用户同学作为目标用户的实际反馈（"更希望优先看到推荐的职业而不是一堆证据""补证计划与待补材料应结合，点待补材料展开补证计划""补充工作台没必要出现"）+ 对当前工作区的只读代码核对 + 用户提供的三张真实报告截图。

**状态（2026-10-14）：第一、二优先已由Codex在四个报告页源码文件实施；第三优先仍待取舍。分组/数量/列表来自全部report.items，建议仅作附加，保留非学生ActionPlan。组件渲染与前端回归通过；真实页面交互、390px及目标用户前后对比尚未验证。以下保留原建议与当时未验证声明，实施证据见[本轮记录](../evidence/20261014-report-action-layer/README.md)。**

---

## 结论（一句话）

不需要新增功能。需要把报告页里**已经存在的两样东西合并成一个**，并把阅读顺序从"证据 → 动作"倒转为"动作 → 证据"。

---

## 已核对的事实（只读代码 + 用户截图）

1. **「建议行动」与「对应缺口」同句重复**：`backend/app/services/action_plan.py:37-40` 的 `rules` 分支令 `action = item.evidence_level_gap`，而第 49-53 行的 `evidence_gap` 同样是 `item.evidence_level_gap`。同一字段灌两个槽位，前端 `jianli/src/components/ActionPlan.tsx:30-31` 各自渲染一次。截图第 1、2 项（Python、pytest）复现；第 3 项（SQL）因走 `ai_suggestion` 路径而不重复。
2. **报告页存在两份几乎相同的清单**：
   - `ReportEvidenceWorkspace.tsx:17-24`「优先补齐的证据」`state.priorities.slice(0,3)`
   - `ReportDetail.tsx:73`「下一步补证计划」`ActionPlan`（最多 3 条）
   两者都展示"要求标题 + 缺口文字 + 按权重排序"；前者正文用的正是后者的 `evidenceLevelGap`（`ReportEvidenceWorkspace.tsx:20`），但排序口径不同（前者仅 `weight`，见 `lib/evidence-workspace.ts:9`；后者 `weight` → `evidence_level` → 报告顺序，见 `action_plan.py:14-20`）。
3. **`actionPlan` 硬上限 3 条**：`action_plan.py:11` `build_action_plan(items, *, limit=3)`，第 58 行截断。而 `lib/evidence-workspace.ts:6` 的 `gaps`（`gap` / `claimed_only`）无上限。**因此若按"筛选 actionPlan"实现展开，会出现卡片显示 N 而展开后少于 N、甚至为 0 的情况。**
4. **四个状态框当前是不可交互的只读数字**：`ReportEvidenceWorkspace.tsx:14-16`。
5. **`ReportDetail.tsx:69` 的 workspace 仅对 `student` 渲染**，而第 73 行的 `ActionPlan` 对所有角色渲染；`/reports/[id]` 的 `AccessGate` 为 `["student","admin"]`。**直接合并会让 admin 丢失补证计划。**
6. 缺口条目已有可跳转锚点 `#requirement-{id}`（`ActionPlan.tsx:26`、`ReportEvidenceWorkspace.tsx:21`），无需新建通道。

---

## 建议（按性价比排序）

### 第一优先：合并「工作台」与「补证计划」

一次改动同时修掉：装饰性数字框、两份清单不同步、重复文案、数字与列表不同源、"缺什么→干什么→缺在哪"断链。

**目标形态**：四张状态卡变为可展开的分组开关（默认展开「待补材料」）；展开内容即该状态下的项，有建议/引用则附加，无则只显示缺口文字 + 「核对来源与逐项解释」锚点；`ActionPlan` 不再作为独立区块重复出现。

**三条硬约束**：
1. 分组、计数、展开内容**必须由 `state`（`report.items`）派生**，不得由 `actionPlan` 派生——这是"点开变少"的唯一根治办法。
2. **不得为填满卡片生成任何建议**。`actionPlan` 仅作附加；`ActionPlan.tsx:5-9` 的 `SOURCE_LABELS`（本地规则提示 / AI 证据建议 / 人工复核后）必须照实显示，不得默认写成本地规则。
3. **保留 `ActionPlan` 给非学生角色兜底渲染**（如 `user?.role !== "student"`），否则 admin 丢失补证计划。

**预计写入面**（4 处，全部在报告页范围）：`jianli/src/components/ReportEvidenceWorkspace.tsx`、`ActionPlan.tsx`、`ReportDetail.tsx`、`jianli/src/lib/evidence-workspace.ts`。不动后端即可完成。

**附带收益**：约束 1 会让第一优先的第 1 号问题（重复文案）自然消失——`gaps` 分组直接渲染 `item.evidenceLevelGap`，不再经过 `action` + `evidence_gap` 两个槽位。是否仍单独改后端由实施者决定。

### 第二优先：报告顶部加一句"无损压缩"

**必须是已保存状态的压缩，不是评价。**

- 反例：「值得投递」——当前数据不支持该断言。
- 正例：「5 项要求：1 项有证据支持、2 项待补；按岗位权重先补「Python」。」——每个字可由现有字段读出（`verdict` 计数、`weight`、`evidenceLevel`）。

这是"用户第一眼要的是结论、当前第一屏全是证据"的直接回应；也是在不新增承诺的前提下唯一能安全建立的结论层。

### 第三优先：换主从（需项目负责人拍板，前两条验证后再议）

- 报告首屏 = 推荐结论，报告本体 = 该推荐底下的证据。推荐能力已存在（`/recommendations` + `CareerRecommendations`），只是被放在另一页；此为**换主从**，不是新增功能。
- 首页三步当前是核验轴（整理材料 → 对照岗位 → 核对证据，见 `jianli/src/app/page.tsx`），应改为决策轴（适合什么 → 缺什么 → 先补哪项）。属信息架构级决定，不应由实施者自行拍板。

---

## 反向约束（防止把用户反馈读过头）

- **收敛信息架构 ≠ 删除可追溯性。** 用户所说"补充工作台没必要出现"指首屏装饰性只读状态框，不是证据体系。做法是降级为展开/折叠，不是移除。可追溯性是本项目的核心差异点，移除后仅剩一个更弱的推荐工具。
- 不新增页面、不新增依赖、不改数据库、不新增"AI 判断/认证"类文案、不改动演示数据。

## 真实性边界（沿用既有约束）

- 合成示例与真实操作必须继续可区分；本次改动不得使二者混同。
- 不得出现认证、录用、提级、成功率类承诺。
- 不得为界面完整而虚构建议文字或引用。

---

## 前置核实清单（未完成，实施前必须先做）

1. `build_action_plan` 的 `limit` 实参取值来自何处，是否可按视图需要取全量。
2. 是否有测试断言 `limit == 3`（`backend/app/tests/test_action_plan.py:38、64` 断言了 `source == "rules"`，第 42 行断言 AI 分支的 `evidence_gap`；**未见任何断言覆盖 `rules` 分支的文案**，这是重复文案得以发布的直接原因）。建议补一条 `assert plan[0].evidence_gap is None`（或 `action != evidence_gap`）。
3. 无证据/未覆盖的要求，其 `#requirement-{id}` 区块当前是否有内容可看；若为空，跳转等于跳进空白，需先补空态说明。
4. 确认 Codex 是否正在编辑上述四个文件——并行约定中它只碰 `SkillRadar.tsx` 与雷达回归，**此项需负责人确认后再派活**，否则会撞车。

---

## 验证方式（不需要构建或测试）

同一个同学、同一份真实简历，改动前后各看一次，只问一句：**「这页如果只能留一句话，你会留哪句？」**

- 改动前预期得到含糊回答（"信息挺多的"）。
- 若改动后他能说出具体一句（例如"我该先补 Python"），结论层成立。

理由：现有测试覆盖的是"输出对不对"，而"差点意思"位于"输出有没有用"，两者无交集，故功能测试无法发现该问题。

---

## 本次建议中未验证的事项

- **未渲染任何页面**。本卡所有结论来自只读代码阅读、用户提供的三张截图、以及用户同学的口头反馈。
- 未启动或重启任何服务（核查时 3000/3001/5173/8000/8080 均无监听，无相关进程）。
- 未运行 typecheck / build / 测试，未安装依赖。
- 截图为用户提供，非本次生成；未包含在证据目录中，其原始状态与工作区改动的关系未核实。
