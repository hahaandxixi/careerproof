# E2E-02-R1 回复失败草稿可编辑 — 前端最小修复与回归证据

- 日期：2026-10-05；基线 HEAD：`70aafb0`；仓库：`D:\jbcode\web ai\jianli`
- 任务卡：`docs/task-cards/20261005-E2E-reply-draft.md`
- 故障复现依据（既有，未重复调查）：`docs/evidence/20261004-E2E-enterprise/reply-failure-2026-10-05T04-26-18-917Z/`

## 修复摘要（仅改 `jianli/src/components/ApplicationBoard.tsx`，见 application-board.diff）

1. 失败草稿面板由 `readOnly` 文本框改为可编辑的 `UnconfirmedReplyDraft`：正文可编辑、可复制，`maxLength={2000}`，保留"先刷新授权投递核对回复状态"提示，并明示"不会自动重发"；aria-label `未确认发送的回复草稿` 不变。
2. 新增导出 `applyReplyDraftEdit(text, edit, confirm)`：编辑即撤销人工发送确认的唯一规则，正常回复正文编辑与失败草稿编辑共用（行为与原实现一致，仅收敛为单点）。
3. 未新增发送入口、未新增重试/重发逻辑、未持久化草稿；刷新/离窗清空草稿与重新核对授权的既有规则全部未动；`selected.status!=="replied"` 的已送达不可再发送闸门未动。

## 测试方法（无浏览器、无新依赖）

环境无 jsdom 且禁止安装依赖：`tests/failure-reply-draft.test.mjs` 内置 sucrase 同步转译钩子，把真实 `ApplicationBoard.tsx`（完整组件图）加载进 node，再用 `react-dom/server` 渲染真实元素、直接调用真实 onChange 管线与共享编辑规则——不匹配源码字符串。React 19 SSR 将 `maxLength` 按驼峰原样输出（`maxLength="2000"`）；HTML 属性名大小写不敏感，浏览器按 `maxlength=2000` 生效，与主编辑框一致。

## 命令与真实退出码

| 命令 | 结果 | 原始输出 |
| --- | --- | --- |
| `node --test tests/failure-reply-draft.test.mjs`（在 `jianli/` 下） | 5/5 通过，EXIT=0 | failure-reply-draft-tests.raw.out |
| `node --experimental-strip-types --test tests/*.test.mjs`（在 `jianli/` 下） | 128/128 通过，EXIT=0 | full-frontend-suite.raw.out |

全量输出尾部均含 `EXIT=$?` 真实退出码；环境见 environment.txt（node v22.23.1）。

## 任务卡第 6 条覆盖映射

- 故障后真实文本框可输入：测试 1（真实渲染无 `readonly`、含 maxlength/aria-label）+ 测试 2（调用真实 onChange，新文本到达页面状态回调）。
- 发送入口缺失：测试 1（失败面板无 `<button>`、无"已发送回复"）+ 会话既有回归（失败后 `selected/items` 清空）。
- 无自动重试，分别覆盖请求失败与响应丢失：测试 4/5（各只发出一次 `reply`，事件循环两拍后仍为一次，无自动重发；错误态无旧报告）。
- 保留既有会话竞态/授权回归：全量 128 项全部通过，未改任何既有测试文件。

## 第二轮：Codex 复核发现的渲染门槛缺陷

- 缺陷：面板门槛 `error&&replyText.trim()` 导致在失败草稿中删掉最后一个字后面板整体消失，无法重新输入。
- 修复（仍在 `ApplicationBoard.tsx`）：新增显式未确认草稿状态 `unconfirmedReply`——发送失败且草稿未被清理时置位，只由既有 `resetReply` 生命周期（刷新按钮/离窗 visibilitychange/focus/hashchange/换投递 open/报告不可用）清除；面板门槛改为 `unconfirmedReply`，与正文是否为空解耦，删空后仍可编辑重输，编辑仍清发送确认。
- 防复活：`replyTextRef` 镜像正文（覆盖全部 4 个正文写入路径：两个编辑框、AI 问题插入、各清理函数）。发送失败时仅当草稿未被清理（`unconfirmedReplyDraftAfterFailedSend(replyTextRef.current)`，新导出规则）才置位——请求若被刷新/离窗取代（草稿已被清空），不得为后续无关错误复活空面板。
- 不变项：无发送入口/旧报告/自动重发；无草稿持久化；`status!=="replied"` 防二次发送闸门未动。

## 第二轮回归（先红后绿）

| 命令（在 `jianli/` 下） | 结果 | 原始输出 |
| --- | --- | --- |
| `node --test tests/failure-reply-draft.test.mjs`（修复前） | 6/7，EXIT=1，仅新置位规则测试红（导出缺失） | gate-regression-red-first.raw.out |
| `node --test tests/failure-reply-draft.test.mjs`（修复后） | 7/7，EXIT=0 | failure-reply-draft-tests.raw.out |
| `node --experimental-strip-types --test tests/*.test.mjs`（修复后全量） | 130/130，EXIT=0 | full-frontend-suite.raw.out |

新增覆盖：测试 4"草稿被删空后面板仍渲染为可编辑文本框，可重新输入"（真实渲染空文本 + 真实 onChange）；测试 5"发送失败仅在草稿未被生命周期清理时置位；被清理后不得为无关错误复活空面板"。既有 5 项全部保留。

## 第三轮：Codex 复核发现的失败归属漏洞（代际护栏）

- 缺陷：第二轮的 `replyTextRef` 非空判定无法保证失败归属——旧 send 等待期间 `resetReply` 清理、随后新投递产生新草稿后，迟到的旧 send 回调（以 false 结束）会把新草稿错误标为未确认。
- 修复（仍在 `ApplicationBoard.tsx`，未改 session 协议）：新增清理代际 `replyDraftGeneration`（useRef），`resetReply`/`verificationUnavailable`（仅有的两个草稿清理路径）各递增一次；发送前捕获本次代际，`await session.reply` 返回后经新导出规则 `replySendOutcome(sent, generationUnchanged)` 分派——代际一致时失败才 `mark-unconfirmed`、成功才 `reset`；代际不一致一律 `ignore`。第二轮的 ref 非空判定及其导出 `unconfirmedReplyDraftAfterFailedSend` 已整体移除（见第二轮历史输出）。
- 附带收紧：迟到的旧发送即使**成功**也不再触发 `resetReply`，不会清掉清理后产生的新草稿。
- 不变项：删空→重输可编辑（门槛仍为 `unconfirmedReply`）、编辑清发送确认、无发送入口/旧报告/自动重发、刷新与离窗清理、`status!=="replied"` 防二次发送闸门、aria-label。

## 第三轮回归（先红后绿，独立证据不覆盖第二轮）

| 命令（在 `jianli/` 下） | 结果 | 原始输出 |
| --- | --- | --- |
| `node --test tests/failure-reply-draft.test.mjs`（修复前） | 6/8，EXIT=1，两个代际测试红（`replySendOutcome` 缺失） | round3-generation-guard-red-first.raw.out |
| `node --test tests/failure-reply-draft.test.mjs`（修复后） | 8/8，EXIT=0 | round3-failure-reply-draft-tests.raw.out |
| `node --experimental-strip-types --test tests/*.test.mjs`（修复后全量） | 131/131，EXIT=0 | round3-full-frontend-suite.raw.out |

新增覆盖：测试 5 按时间线脚本化复现"旧失败→清理→新草稿→旧回调迟到"（断言 `ignore` 且未确认状态不变，并覆盖旧回调迟到成功的对称情形）；测试 6 断言代际一致时失败→标记未确认、成功→重置。第二轮 6 项全部保留。

## 边界与未决（交棒 Codex）

- 无 DOM 环境未做完整浏览器挂载与人工点击路径验证；代际递增与捕获/比较接线经 `replySendOutcome` 规则测试与调用点审查覆盖。页面级表现（删空后重输、迟到回调不影响新草稿、刷新/离窗清理时机、无关错误不出现空面板、编辑前后文本、请求次数、服务端事件数、刷新授权后的状态与快照哈希）按任务卡第 7 条由 E2E-02 运行器在同一隔离环境复测桌面与 390px；生产重建由 Codex 统一执行。
- 本环境遵守禁令：未运行浏览器/数据库/构建/类型检查/服务重启，未改后端、会话协议、AI 评测、企业运行器与正式状态文档，未安装依赖，未提交或推送 Git。
