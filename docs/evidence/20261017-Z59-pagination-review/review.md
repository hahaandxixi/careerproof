# 传智杯59：分页前端独立审查报告（GLM-5.3-Flash / 低）

- 日期：2026-10-17 · HEAD `ef774cb` · 审查对象：未提交分页集成（前端组件/会话库 + 少量后端分页服务只读核对）
- 审查范围：ApplicationList / ApplicationBoard / ReportList / GrowthWorkspace / NotificationCenter / JobDetailView / ListPagination、lib/{list-pagination,application-list-session,application-board-session,notification-session,job-application-status}、api/client.ts；hash 见 `hashes.txt`（快照时点，Codex 仍在集成中，可能已变化）。
- 方法：逐文件通读 + 纯离线探针（data-URL 加载真实 `lib/list-pagination.js` 源码执行）+ 只读 grep 后端钳制逻辑。未运行测试套件、未构建、未启服务。

## 结论：无 P1/P2，13/13 探针通过，可继续 Codex 集成

核心不变量均成立：
1. **过期翻页响应不恢复私有内容**：三套会话均有代次票据（application-list-session / application-board-session `current(ticket)`；NotificationCenter/GrowthWorkspace generation+guard）。离窗即清：ApplicationList.tsx:62、ApplicationBoard.tsx:159、GrowthWorkspace.tsx:259-261、NotificationCenter.tsx:123、ReportList useEffect `setData(null)`；board-session `run()` 每次都重取列表并 `stillAuthorized` 复查（application-board-session.ts:49-55），不在列表即清 selected 并显式提示。
2. **通知目标补入不改变页数**：notification-session.ts `includeApplicationTarget` 校验 404/id/jobId（企业侧强制 jobId 匹配），补入项单独记 `pageItemCount=result.items.length`，total/pageBounds 用服务端原值；两处 UI 注明"不计入本页记录数"（ApplicationList.tsx:78、ApplicationBoard.tsx:184）。
3. **撤回/回复/下载重新核对**：board-session download/reply 均走 `run(..., id)` 全量重取并复核授权，失败/迟到回调有代际防护（replyDraftGeneration）。
4. **末页/空集/越界**：探针 5 例通过（空集、整除/非整除末页、越界防御、第1页）；后端四端点均钳制页码：applications.py:356、evidence_growth.py:141、notifications.py:90、analysis.py:568；前端 ReportList/NotificationCenter/GrowthWorkspace 另有 `result.page !== page` 回设，双保险。
5. **成长不可读计数**：`unavailable_count` 只计本页窗口内跳过记录、`total` 仍全量（schemas/pagination.py 文档一致），UI 如实说明"仍计入总数，不代表已删除"。
6. **岗位状态 jobId 服务端过滤**：client.ts:268 `myApplications(page,pageSize,jobId)` 传 `jobId` 参数；`resolveJobApplicationStatus` 对 jobId 逐条校验，缺记录→unknown→不渲染（绝不显示"未投递"）。
7. **筛选只作用当前页**：ApplicationBoard.tsx:183 说明文案明确"筛选仅作用于当前页及额外核对的通知目标，不代表所有候选人的检索结果"。

## 发现（均 P3，不阻塞）

- **F1 [P3]** JobDetailView.tsx:405 — MatchForm 只取 `myApplications(1, 20, jobId)` 第一页。同一岗位可因多次投递产生多条记录，若该岗位记录超过 20 条且最新活跃恰好不在第 1 页，状态判为 unknown，已有投递提示静默不渲染。方向保守（不会误报"未投递"），且服务端按 jobId 过滤后最新记录通常在首页，故 P3。可选修复：增大 pageSize 或循环取页。
- **F2 [P3]** ListPagination.tsx:8 / list-pagination.js `pageBounds` — 防御态缺陷：若调用方传入 page > pages，显示 `start > end`（探针"越界页"：start=161, end=45）。当前四个端点均服务端钳制、组件层也有回设，正常流不可达；仅作防御性备注（可钳 `start = Math.min(start, end)` 或 `page = Math.min(page, pages)`）。
- **F3 [P3]** NotificationCenter.tsx:139 — 单条"核对授权并打开投递"成功后 router.push，不触发 setRevision；返回页面依赖 visibilitychange/focus 刷新覆盖，语义可达，仅记录。

## 证据

- `probe.mjs` / `probe-output.txt`：13 passed, 0 failed（含服务端钳制不可达性验证所依赖的边界用例）
- `hashes.txt`：13 个被审文件的 SHA-256 快照

## 未验证项

- 未运行 jest/vitest/next build；未实跑真实浏览器分页交互；后端 services 仅只读 grep 钳制行，未审查其翻页 SQL 正确性（属 Z57 后端卡范围）。
- 快照时点：审查期间 Codex 可能继续改动源码，hash 仅代表本次审查对象。
