# 传智杯31：学生与企业页面错误恢复审查（audit）

- 日期：2026-10-11。审查基线：HEAD `3d76a5b6883987987bb4ff0d0fd4f74ec694a65a`（任务卡写 ff0c170；3d76a5b 仅改 docs 两个文件，代码基线一致，`git merge-base --is-ancestor ff0c170 HEAD` 通过）。
- 范围：补证任务（/growth、GrowthWorkspace、PrivateAnswerDraft）、新报告对比（GrowthComparison、EvidenceAnchorRestore）、投递看板（/applications 学生、/jobs/[id]/applications 企业、ApplicationBoard/ApplicationList）、通知页（NotificationCenter、NotificationLink）、会话客户端（lib/api/client.ts、AuthProvider、lib/*-session.ts、refresh-gate、application-anchor、notification-session）。30 号查 AI、32 号查启动器，均不在本范围。
- 方法：只读源码 + 3 个纯 Node 函数探针（无浏览器/服务/DB/构建/网络）。基线测试 `node --test tests/*.test.mjs` 193 项全绿（未改动）。20261010-enterprise-question-growth / 20261010-question-growth-frozen 的正向链路、390px 无横向溢出、通知等待真实列表已验证，本次不重复。
- 唯一写：本目录（audit.md、manifest.sha256、probes/）。源码、测试、历史证据零修改。

## 按严重性的发现

### P1-1 私人回答草稿：窗口隐藏丢弃声明永远不可见，事前也无警告
- 触发（学生）：/growth/<id> 的"私人回答草稿"输入未保存文字 → 最小化窗口或切标签页（visibilitychange hidden）→ 切回（visible）。
- 期望：恢复后看到 clear() 发布的声明"页面已隐藏或切换身份：私人草稿状态已清除，未保存的修改已丢弃"（workflow 层确有此声明，且 tests/private-answer-workflow.test.mjs:160 专门断言它必须存在）。
- 实际：声明从未被用户看到。PrivateAnswerDraft.tsx:55-57 在 visible 分支立即 `session.load()`；load 首段同步执行 `set({ reading: true, error: "", notice: "", ... })`（private-answer-workflow.ts:209），把 notice 清空。React 在同一事件循环内批处理，浏览器重绘时 notice 已被替换为读取态。成功路径最终文本框回服务器版本、无任何解释；网络中断时 load 失败只显示 error（探针1两序列均断言通过）。且面板事前没有"离开窗口会丢弃未保存编辑"的常驻警告——对比 ApplicationBoard 有常驻声明（ApplicationBoard.tsx:104"离开窗口会清空未发送的回复"）。
- 证据：jianli/src/components/PrivateAnswerDraft.tsx:50-58；jianli/src/lib/private-answer-workflow.ts:209、455-466；jianli/tests/private-answer-workflow.test.mjs:146-161（只覆盖 session 层，组装层不可见性是盲区）。探针1 `probes/probe1-private-answer-loss-notice.mjs`（输出 probe1.raw.out，hash 见 manifest 与 probes/probes.sha256）。
- 复现：`cd docs/evidence/20261011-page-recovery-audit/probes && node probe1-private-answer-loss-notice.mjs`（纯 Node，仅本地 fs + sucrase 转译）。
- 真实页面步骤（实施后复核）：390px 或任意宽度，草稿输入文字→Alt+Tab 切走→切回→观察无任何"已丢弃"提示、文本框回空/回服务器版本。
- 最小修复协议（优先顺序）：
  1. 零风险先行：PrivateAnswerDraftPanel 顶部加常驻一行声明"离开窗口会丢弃未保存的编辑，请先保存"（对齐 ApplicationBoard 做法）。允许文件：PrivateAnswerDraft.tsx。
  2. 声明可见性：visibility visible 分支不立即 load，先保留 clear 的丢失声明并显示"重新读取"入口；或 load 首段不清 notice、由完成路径统一覆盖并把丢弃声明并入读取完成 notice。允许文件：PrivateAnswerDraft.tsx（如选后者需 private-answer-workflow.ts 一处）。

### P2-2 跨标签页账号/角色切换：旧页面以新身份静默取数，无任何提示
- 触发：tab A 停留在学生"我的投递"/通知页；tab B 同一浏览器退出并登录企业账号（cookie 是浏览器级共享）；回到 tab A 点"刷新投递状态"。
- 期望：身份已变化时有明确提示或要求重新登录。
- 实际：旧请求 401 → refreshSession()（client.ts:141-158）用已被企业登录轮换的 refresh cookie 刷新成功 → 以同一 init 静默重试（client.ts:174-176）→ 返回**企业账号**的 /applications/mine 空列表。全程无 session-expired 事件（该事件只在 refresh 失败后的 401 分支派发，client.ts:186-188），AuthProvider（AuthProvider.tsx:55-59）与页面身份（页头仍显示学生 displayName）完全不知情。学生页显示企业数据。
- 证据：jianli/src/lib/api/client.ts:160-199；探针2 `probes/probe2-identity-switch-retry.mjs`（mock fetch，断言重试成功、refresh 单飞、0 次 session-expired；输出 probe2.raw.out）。api-client.test.mjs 覆盖了 refresh 单飞与网络错误分类，未覆盖"refresh 成功但身份已变"。
- 限制说明：探针证明前端静默转发路径可达；真实后端对企业调 /applications/mine 的响应形态（403/空）不影响"无提示"结论。双 tab 是否属演示环境可接受行为，由实施方判断。
- 最小修复协议：refresh 成功后、重试前核对身份——refreshSession 里并行/追加 `GET /users/me`，将返回 id 与 AuthProvider 最近已知身份比对（需经回调或模块级缓存注入），不一致则派发 careerproof:session-expired 并把原请求按 401 处理。允许文件：lib/api/client.ts、components/AuthProvider.tsx。优先级低于 P1-1：需要双 tab 才触发。

- **更正（2026-10-11，Codex 证据复核后）**：上一条"实际"段中"返回企业账号的空列表/学生页显示企业数据"是过度结论，原探针2及其输出 probe2.raw.out **原样保留作为过度结论记录**。真实后端 `backend/app/services/applications.py:161-165` 的 `_student` 对非学生角色必抛 `AppError("请使用学生账号", code=4037, status_code=403)`，`:349-350` 的 `mine()` 先过该门槛——**跨角色（企业 cookie）调 /applications/mine 必然 403，不存在 200 空列表**。更正后的真实行为（probe2b，`probes/probe2b-identity-switch-corrected.mjs`，输出 probe2b.raw.out）：
  - 跨角色（序列B，对齐真实后端 403 形态）：重试返回 403，前端显示"请使用学生账号（请求编号…）"错误，**数据不串**；但仍无 session-expired、AuthProvider 不感知、页头仍显示学生名、不引导重新登录——错误文案与页头身份自相矛盾。
  - 同角色另一学生（序列A，**离线 mock 模拟同角色另一学生的有效 cookie**，非真实双标签页实测、非越权实测）：401 → refresh 成功 → 重试 200 返回另一学生的投递列表 → 旧页面静默渲染他人数据，无任何提示或事件。这是"显示他人数据"的可达路径。
  - 核心缺陷结论不变：refresh 成功路径（client.ts:174-176）没有任何身份同步；数据串号仅限同角色跨账号，且为离线 mock 层证明。最小修复协议不变。

### P2-3 补证任务分析轮询：一次网络抖动/5xx 即清空整个任务面板，需手动恢复
- 触发（学生）：/growth/<id> 状态 analyzing，自动轮询（1.5s 间隔，GrowthWorkspace.tsx:76-82）任意一次 `api.growthTask(id)` 失败（网络中断、瞬时 5xx、或 401 走到 errorMessage 的任何路径）。
- 实际：catch → `setTask(null); setError(...)`（GrowthWorkspace.tsx:78-80）。任务面板（基准、材料、分析、对比全部 section）整体卸载；error 同时使 growthAutoQueryStep 停止轮询（growth-workflow.ts:104）。恢复唯一入口是手动点"读取已保存任务"（revision++ 重跑 effect）；恢复后未保存的改选 targetJobId 草稿被服务器值覆盖。注意面板数据来自**只读 GET**，服务器状态未变，清空并非为避免陈旧写回。
- 对比：TaskView 的轮询失败**保留 task**，只 setError + 继续自动轮询自愈（TaskView.tsx:98-103），体验差距明显。
- 最小修复协议：轮询 catch 分支保留 task，仅 setError（提示"暂时无法读取最新进度，将自动重试"），并让轮询在 error 后经一小段退避自愈（对齐 TaskView 模式）；perform（用户主动写操作）的失败清空保持现状（写请求可能已改服务器状态，回服务器真相是合理的）。允许文件：GrowthWorkspace.tsx（如需退避常量可动 growth-workflow.ts）。
- 复现（代码层）：读取 GrowthWorkspace.tsx:71-83 effect 的 catch；真实复现需断网注入（本审查未执行浏览器/服务操作，行为由代码直接可证）。

### P3-4 目标岗位选择器：jobTotal 过期偏大时放行越界页请求，停留空页码（可手动恢复）
- 触发（学生）：任务页岗位选择器搜索结果 25 条 → 翻到页2（本地 jobTotal=25）→ 期间 13 个岗位下架（服务端实际 total=12）→ 点"下一页"：`growthJobPageBounds(25,2,10).hasNext = 20<25 = true` 放行页3请求（offset=20 越界）→ 后端无裁剪原样回显 page=3 空列表 → UI 停在"没有匹配的已发布岗位。共 12 个已发布岗位 · 第 3 页"。
- 期望：与通知中心一致的越界自纠。
- 已正确对照组：通知分页越界有双重防护——服务端 `page = min(page, max(1, ceil(total/page_size)))`（backend/app/services/notifications.py:90）+ 前端 `result.page !== page` 自纠（NotificationCenter.tsx:23）。
- 证据：jianli/src/lib/growth-workflow.ts:47-50；jianli/src/components/GrowthWorkspace.tsx:109、115（bounds 基于本地 jobTotal）、94-101（回执不校验 list.page）；backend/app/services/jobs.py:42-44 与 65-67（PaginatedData 的 page 原样回显，无 min 裁剪）；backend/app/api/v1/jobs.py:102-115。探针3 `probes/probe3-growth-job-page-bounds.mjs`（输出 probe3.raw.out）。
- 恢复路径：上一页可点、重新搜索从页1开始——可恢复，无数据损坏，故 P3。
- 最小修复协议（二选一，推荐 a）：a) backend JobService.list 与 mine 分支加与 notifications 相同的 `page = min(page, max(1, ((total or 0) + page_size - 1) // page_size))`（2 处）；b) 前端 loadJobList 回执若 `list.page < page` 则以 list.page 重拉。允许文件：backend/app/services/jobs.py，或 jianli/src/components/GrowthWorkspace.tsx。

### P3-5（证据不足，需浏览器实测）390px 窄屏失败提示/草稿面板的视口与焦点恢复
- 可证代码事实：全前端仅 JobForm.tsx:85 与 ResumeVersionPicker.tsx:35 两处调用 focus()，均在正常流程；**所有失败路径没有 focus/scrollIntoView 把视口带到错误提示**。
- 场景A（企业，390px）：看板底部点"确认发送站内回复"失败 → error 渲染在页面顶部（ApplicationBoard.tsx:109），UnconfirmedReplyDraft 面板在中部（:110），底部回复表单随 selected 清空而消失；视口停在原按钮位置，390px 上可能只见空白。role="alert" 对读屏可达，视觉滚动无保证。
- 场景B（学生/企业，390px）：通知中心底部点翻页/列表项失败 → 错误条在顶部（NotificationCenter.tsx:55），视口不动。
- 本审查无浏览器，无法证伪实际视口落点；列出为可证伪问题。验证步骤：DevTools 390px 实测上述两步，记录失败后视口位置与是否需手动滚动。
- 最小修复（若实测确认）：失败路径对错误条/草稿面板 `scrollIntoView({ block: "center" })` 或对草稿 textarea 调用 focus()。允许文件：ApplicationBoard.tsx、NotificationCenter.tsx。
- 说明：锚点恢复的 sticky header 遮挡问题不存在——report 锚点目标有 scroll-mt-24（ReportDetail.tsx:76、83），GrowthComparison 锚点目标也有 scroll-mt-24（GrowthComparison.tsx:22），投递锚点用 block:"center" 不受遮挡。

### 观察（不构成缺陷，记录约束）
- ApplicationVerification 的 visibilitychange 只处理 hidden（ApplicationVerification.tsx:35-39），visible 无 activate 恢复；若会话失效后恢复，load/generate 会因 active=false 静默拒绝。现行唯一宿主 ApplicationBoard 在 hidden 时先 clear 并清空 selected（ApplicationBoard.tsx:78-81），该组件必然先被卸载重挂载，**失效路径当前不可达**。若未来复用于不被卸载的宿主会成为死按钮——改动宿主结构时需回头补 visible 分支。
- ApplicationList 的锚点在 reveal 成功后 hash 不清除（仅目标 404 时清，notification-session.ts:19-23）：后续该投递变得不可访问时，用户手动刷新会看到"通知对应的投递已不可访问"提示，文案与"用户未从通知进入"的当下情境略有出入；行为本身正确（确实不可访问），不列缺陷。
- GrowthTaskStart `?enterpriseReply=` 自动展开与报告页 EvidenceAnchorRestore（展开全部 DETAILS 祖先再滚动，evidence-anchor.ts:2-8）行为正确；报告页 390px 布局已由既有证据覆盖，不重复。

## 已验证为正确的现行行为（不再改、不再测）
| 主题 | 结论 | 证据 |
|---|---|---|
| 通知分页越界 | 服务端裁剪+前端自纠，闭环 | notifications.py:90；NotificationCenter.tsx:23 |
| 投递锚点单次 reveal / filtered-out / dismiss | B-15 十项测试覆盖 | tests/application-anchor.test.mjs |
| 返回标签页刷新合并（B-06） | 闸门+blur 重置正确 | refresh-gate.ts；ApplicationBoard.tsx:73-93、ApplicationList.tsx:25-37 |
| 企业回复失败草稿归属 | 代际规则防迟到回调污染新草稿 | ApplicationBoard.tsx:136-151；tests/failure-reply-draft.test.mjs |
| refresh 单飞、网络错误分类 | 六项测试覆盖 | tests/api-client.test.mjs |
| 私人草稿 409 冲突/以本人编辑重存/迟到保存回执不降级 | 逻辑与测试完备 | private-answer-workflow.ts:328-397；tests/private-answer-workflow.test.mjs |
| 分析任务 SSE 断线→轮询自愈 | onerror→poll→成功→重连 SSE | TaskView.tsx:31-103 |
| 迟到响应防护 | 各会话 generation/ticket 模式一致 | application-board-session.ts:29-58、application-list-session.ts:11-23、growth-workflow.ts:67-74 |

## 未验证项（如实标注）
- P3-5 的实际视口/焦点行为（需浏览器）。
- P2-2 在真实后端的跨角色响应形态（探针为 mock 层证明；前端无提示的结论不依赖后端形态）。
- P2-3、P3-4 的端到端真实触发（代码路径直接可证，未注入断网/下架环境）。

## Manifest
- 本目录源文件与探针哈希：manifest.sha256（24 个审查对象文件）、probes/probes.sha256（4 探针 + 4 原始输出，probe2/probe2.raw.out 保留过度结论原状，更正见 P2-2 更正块与 probe2b）。
- 实际原始命令（均在 Git 根 `D:\jbcode\web ai\jianli` 执行）：
  - `node --test tests/*.test.mjs`（在 jianli/ 下；193 pass / 0 fail，未改动）
  - `node probe1-private-answer-loss-notice.mjs`、`node probe2-identity-switch-retry.mjs`、`node probe3-growth-job-page-bounds.mjs`、`node probe2b-identity-switch-corrected.mjs`（在 docs/evidence/20261011-page-recovery-audit/probes/ 下；各自输出 tee 到 probe*.raw.out）
  - `sha256sum ...`（生成两份清单）
- 探针依赖：Node v22.23.1 原生类型剥离 + jianli/node_modules/sucrase（既有 devDependency，未安装任何新包）；无网络访问。

## 自审
- 未改任何源码/测试/历史证据/正式清单；未运行服务、数据库、浏览器、构建；未触碰 .env、真实模型、外发、安装、Git 提交推送；未进入 30（AI）与 32（启动器）范围；P2 未动。
- 每条发现都给出 file:line + 至少一个探针或代码级复现路径，无凭猜测报告的 bug；4 条"已验证正确"路径明确声明不重复测试。
- 数量：3 个可证缺陷（P1-1、P2-2、P2-3）、1 个低危竞态（P3-4）、1 个证据不足待实测问题（P3-5）、2 条观察。不凑数。
- 更正记录：P2-2 的"跨角色 200 空列表"过度结论已被 Codex 复核指正并保留原状（probe2/probe2.raw.out），由 probe2b 按 applications.py:161-165、349-350 的真实 403 形态更正；同角色另一学生的串号路径为离线 mock 层证明，非真实双标签页实测。后续 34 号将单独处理私人草稿提示（P1-1），实施源码不属本审查范围。
