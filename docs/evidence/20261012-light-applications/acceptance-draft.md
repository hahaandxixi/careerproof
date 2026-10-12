# 传智杯44 验收草稿：轻量投递与投递进度（GLM goal44）

日期 2026-10-12 · 起点 939a796 · 唯一写权限范围：两组件 + 必要 lib/测试 + 本目录。

## 修改（9 文件）

| 文件 | 变更 |
| --- | --- |
| `jianli/src/components/ApplicationSubmit.tsx` | 重写：首屏三项核心风险改为列表直述（固定报告/引用、简历下载可能含联系方式、撤回但已下载副本无法追回）；其余分享说明折叠进 `<details>`（不预展开）；授权复选框保持不预勾选；提交管线抽出 session（忙碌防重、失败提示玫红、可重试）；保留 `#application-submit` 锚点、"查看我的投递"链接 |
| `jianli/src/components/ApplicationList.tsx` | 渲染层重构：抽出无状态导出组件 `ApplicationItemCard`；卡片首行突出岗位/公司/状态，新增"下一步：…"行动行（按状态映射，查看/下载不推断录用）；完整投递记录默认折叠（`<details>`+条数摘要）；页首解释文字可收起；**会话/刷新代际/锚点/visibility/撤回协议代码逐字未动** |
| `jianli/src/lib/application-display.ts` | 新增：状态/回复文案与下一动作映射集中（含未知状态回退） |
| `jianli/src/lib/application-submit-session.ts` | 新增：提交单飞 + busy/notice/done 状态发布 |
| `jianli/tests/application-display.test.mjs` | 新增 6 用例：五状态文案、未知回退、回复映射、查看/下载不推断录用、事件摘要 |
| `jianli/tests/application-submit-session.test.mjs` | 新增 4 用例：忙碌先发布、单飞只发一次、失败可见+重试真实二次请求、重试仍失败替换提示 |
| `jianli/tests/application-submit.test.mjs` | 新增 4 用例（SSR 真实 .tsx）：不预勾选+初始禁用、首屏三风险、高级说明默认折叠且完整、锚点/链接保留 |
| `jianli/tests/application-list.test.mjs` | 新增 8 用例：四要素突出、事件折叠、不推断录用、回复/问题/引用/补证链接、撤回二次确认交互（元素树直调真实 onClick）、已撤回入口、忙碌禁用 |
| `docs/evidence/20261012-light-applications/` | 本目录（原始日志×3 + 本草稿） |

保留验证：主动授权不预勾选、固定快照文案、撤回二次确认（确认/取消/忙碌禁用）、重新投递入口（`/reports/{id}#application-submit`）、刷新代际（B-06 gate）、锚点单次滚动（B-15）、通知目标核对（includeApplicationTarget）全部未改。

## 测试（原始输出见本目录）

- 目标测试 6 文件：**36/36 通过**（`targeted-tests.raw.out`）
- 全量前端测试：**242/242 通过，0 失败**（`frontend-tests.raw.out`，其中 22 例为本卡新增）
- `tsc --noEmit`：**0 错误**（`typecheck.raw.out`）
- 未运行构建/真实模型/业务库（按卡禁令）；未装依赖（沿用 sucrase 既有测试设施）。

## 自审

- `git diff` 核对：ApplicationList 删除行仅 STATUS 表（移入 lib）与渲染 JSX；session/useEffect/锚点/refresh-gate 行零删除（关键字过滤验证）。
- 已知取舍：① 失败提示由靛蓝改为玫红（`role="status"` 保留，可重试语义更清楚）；② 未知 replyKind 现在显示原始 kind 而非空白（展示层，非协议）；③ 事件列表 `<ol>` 从常驻改为折叠——SSR 内容仍在 DOM，锚点 `#application-{id}` 与卡片级滚动不受影响。
- 风险声明：本次全部为 Node SSR/元素树测试，未做真实浏览器 320/390px 截图与键盘走查（无浏览器环境授权）；`<details>/<summary>` 为原生键盘可访问元素，320px 布局用 flex-wrap，属低风险但未实测。

## 只读 UX 缺口（主要流程，按影响排序）

1. **[P2] 岗位列表/报告列表无"已生成报告/已投递"状态**：学生主流程（岗位→报告→投递→跟踪）里，岗位卡片与报告卡片都不标记"该岗位已投递/该报告已用于投递"，唯一投递入口在 /applications；容易重复生成报告或找不到回投递的路径。（`JobList.tsx:46-51`、`ReportList.tsx:27`）
2. **[P3] 报告与通知的分页无总数**："第 N 页"不知道共几页；ReportList"下一页"按 `length<20` 判断，恰好整除时多一次空翻页；JobList 有"共 N 个"，口径不一致。（`ReportList.tsx:28`、`NotificationCenter.tsx:60`）
3. **[P3] 推荐生成后不滚动到结果**：结果区在长表单下方，生成成功后视口留在原地，需手动找"本次生成的规划"。（`CareerRecommendations.tsx:140`）
4. **[P3] "全部标为已读"无确认**：一键影响全部未读；与撤回授权的二次确认相比风险提示不对称。（`NotificationCenter.tsx:55`）
5. **[P3] 成长对照条目全部展开**：每条要求的新增/不再展示两组代码片段直接铺开，长对比页滚动负担大——与本次"投递记录默认折叠"同类问题。（`GrowthComparison.tsx:39-46`）
6. **[P3] 材料中心首访无步骤指引**：简历/项目两个上传卡并列，首次进入的学生没有"先简历→再项目→去岗位分析"的顺序提示（各卡片内文案已有，缺一条主线）。（`portfolio/page.tsx:320-433`）

未深审：材料预览页（materials/[kind]/[id]）、企业端 ApplicationBoard 详情（Codex 持有，仅粗读）；不做功能重设计建议。

## 未验证 / 下一项

- 未验证：真实浏览器渲染（320/390px、键盘、读屏）、生产构建、双端集成——均由 Codex 验收步骤覆盖。
- 下一项建议：P2 缺口 1（岗位/报告卡片投递状态标记）最能放大本次"轻量投递"收益，可作为下一卡评估；涉及列表 API 增量字段，需与后端及 Codex 协调，不在本卡范围。
