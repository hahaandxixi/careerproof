# PRODUCT-01 前端接续证据（2026-10-06，免费Flash任务）

基线：HEAD 3dc152c，旧任务 diff（GrowthWorkspace/client/domain）原样保留，未恢复旧队列、未双写。
Codex 固定快照 `20261005-PRODUCT-01-codex/race-snapshot-20261006`（hash 2ba7f4b9…/666d2ffd… 与当时文件一致）4 项 = 1 通过 / 3 失败，作为本轮修复输入；copy+save 交错通过项按实测保持，未修假问题。

## 改动文件（仅原卡允许范围）

1. `jianli/src/lib/private-answer-workflow.ts` — 会话并发模型重写：
   - 只有 `clear/dispose` 递增会话纪元（epoch）并作废全部在途回执；load/save/compare/copy 互不废弃对方，各自独立 busy 互斥，回执复位自己的 busy，不搁浅（修"reload 废弃在途 save"）。
   - `clear` 同时使会话失活：隐藏/切身份后旧按钮 save/compare/copy/setText 全部拒绝，只有 owner 显式 `activate()`（当前身份/任务 effect）恢复（修"clear 后旧 save 仍发请求"）。
   - 编辑序号：读取发起后的新输入（文字/引用选择）不被 GET 回执覆盖；显式重读仍替换点击前的本地编辑（修"GET 覆盖请求后的新输入"）。
   - 读取回执不降级基线：GET revision 旧于已知已保存版本（如在途 save 刚落账）时不覆盖 text/selected/saved。
   - options 独立票据：load 与新增 `refreshReferences` 发起即递增，最后发起者生效。
   - `refreshReferences(taskId, scope)`：目标绑定变化只刷 options/optionsNotice，不动草稿字段与未存编辑。
2. `jianli/src/components/PrivateAnswerDraft.tsx` — 接入补全：
   - visibility 恢复可见分支改为 `activate()` + `load()`（此前只 load，clear 失活后永远读不了）。
   - 新增绑定 effect（targetReportId/crossJob）：变化时 `refreshReferences` 重验来源 + 关闭旧预览（阻止基于旧来源的确认复制），不重建草稿、不重置未存编辑；taskId 变化仍走整体重读。
   - 身份切换由 `GrowthContent key={user?.id}:${id}` 重挂载（dispose），已核实存在。
3. `jianli/tests/private-answer-workflow.test.mjs` — 新增 9 测（先红后绿）+ harness 修复：
   - 复现1/2/3/3b 对应 Codex 三失败项 + 旧 GET 降级变体；回归2条（copy+save 交错、clear 后迟到 GET）；绑定刷新3条（保留编辑、与在途读取交错、失败可见）。
   - harness 修复：setup 的调用记录独立于替身实现（此前 override saveDraft 丢失 `calls.saveDraft` 记录，导致 409 测试在基线即红——上个任务遗留未消化项，非会话逻辑缺陷）。

## 验证（原始输出与 hash 见本目录）

- `races-red.raw.out`：修复前 31 测 = 24 通过 / 7 失败（7 个正是本轮新增复现；Codex 通过的 copy+save 与 clear 迟到 GET 两条回归先绿，与快照一致）。
- `races-green.raw.out`：修复后 31/31 通过。
- `full-tests.raw.out`：受影响全套 `npm test` = 184/184 通过。
- `typecheck.raw.out`：`tsc --noEmit` 通过（EXIT=0）。
- `hashes.txt`：3 个改动文件 + 4 份原始输出 sha256。
- 自审：逐项对照 Codex 20261006 反馈清单已全部消化（clear 失活/显式恢复、迟到 GET 与对照回执丢弃、独立票据与 busy 不搁浅、读取期编辑保护、绑定变化保留编辑重验引用、阻止旧预览确认、卸载 sessionRef 置空按钮 no-op）；UI 按钮 disabled 语义未放宽，helper 级交错以 deferred 测试证明。

## 第二轮（同日接续）：来源重验边界 + 迟到保存回执（对应Codex binding快照 0通过/4失败）

输入：`20261005-PRODUCT-01-codex/race-snapshot-binding-20261006/independent-binding.test.mjs`（冻结helper哈希 8021e5a8…，即本轮修复前我的 helper，红证据 red.raw.out 未改动）。新增 5 条本地回归（先红 31/35 → 后绿 36/36）+ 1 条面板测试：

- 来源可信度状态机 `sourceCheck: current|pending|failed`：保存回执/读取回执/重验成功置 current；重验中与失败后 copy 一律拒绝（pending 提示完成后再确认；failed 提示可重试或重读/保存重建验证），修"重验 pending/失败仍能复制旧原文"。
- `refreshReferences` 成功时把已保存引用中不再出现在可选列表的来源降级 `available:false`（保留身份/版本/原文/选中身份/本地文字，不删除）；预览 builder 既有 filter(available) 即排除其原文，且在"已失效引用"段提示。修"绑定变化后重开预览仍可把旧目标来源复制为有效证据"。
- 保存回执只前进不降级：回执到达前基线已被更新（GET 3）时，迟到回执（revision 2）不回写基线，saving 仍由回执正常复位，读取期间编辑保留。修探针4。
- 面板：pending/failed 状态行可见（role=status/alert），复制按钮在 sourceCheck≠current 时禁用（workflow 层同样拦截，不以UI掩盖helper）。
- 未改 binding effect/重挂载结构：本地编辑、选中引用身份、版本在重验与迟到回执下均保留（测试断言）。

## 第二轮验证原始输出

- `binding-red.raw.out`：修复前 35 测 = 31 通过 / 4 失败（4 个即新增复现）。
- `binding-green.raw.out`：修复后 36/36 通过。
- `binding-independent-green.raw.out`：用 `PRIVATE_ANSWER_SOURCE_FILE` 指向当前 helper 独立复跑 Codex binding 探针 = 4/4 通过（探针文件与红证据未改动）。
- `full-tests2.raw.out`：全套 189/189；`typecheck2.raw.out`：tsc EXIT=0。

## 未验项 / 保留门禁（不在本任务内）

- 真实页面/隔离 Mock 页面步骤、390px 可见性、双页面同版本冲突、预览人工确认复制的浏览器级验证：按卡等 Codex 安排独占目录后执行。
- 生产构建、独立 PG 并发门禁、服务 0015 迁移/生产重建：仍由 Codex 在独立目标执行；本地实现不等于生产或最终签收。
- 未动：Codex 证据、后端、runner、正式清单、.env、数据库、Git 提交推送、P2。
