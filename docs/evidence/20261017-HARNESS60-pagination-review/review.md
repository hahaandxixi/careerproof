# 传智杯60：分页后端独立复核（HARNESS60 / Flash LOW）

- 实际 Git 根：`D:/jbcode/web ai/jianli`（`git rev-parse --show-toplevel` 一致）
- HEAD（复核开始与结束一致）：`ef774cb13d9187a8afaeedad03351006acfed198`
- status：Z57 后端分页改动仍全部未提交（`M` api/services、`?? schemas/pagination.py`、`?? tests/test_z57_pagination.py`、`?? tests/test_paginated_lists_postgres.py`）。本复核未还原、未提交、未改任何源码/测试/配置/前端/正式文档。
- 复核窗口：2026-10-17 08:20:09 → 08:26（Asia/Shanghai）。**窗口内 Codex 正在并发改文件**（见 §4 时间证据）。
- 一句话结论：**分页后端实现本身未发现越权、计数/切片不一致或排序缺陷；“信封 vs 数组”不兼容存在 2 处仍未修复的可复现缺陷（均在验证脚本侧）；另有 2 处曾成立但已在复核窗口内被 Codex 修掉；八条 Z57 测试因沙箱环境阻塞未能执行。**

## 一、仍未修复的缺陷

### D1 — 高：私有恢复通知 runner 预检自检恒失败（每次运行必现）
- 位置：`scripts/e2e/private-recovery-notice-runner.mjs:836-838`
- 现状（08:26 实读，mtime 2026-10-11 未变）：
  - `:836` `const tasks = await auth.getJson("/growth-tasks");`
  - `:837` `if (!Array.isArray(tasks) || tasks.length === 0) throw new Error("no own growth task visible through the read-only API");`
  - `:838` `const target = tasks[0];`
- 机制：`getJson` 返回 `(await r.json())?.data`（同文件 `:249-253`）。Z57 后 `/growth-tasks` 的 `data` 是信封 `{items,total,page,pageSize,unavailableCount}`（`schemas/pagination.py:6-15`、`api/v1/evidence_growth.py:33`），恒为对象。
- 反例：`Array.isArray(对象) === false` → 恒抛 `no own growth task visible through the read-only API`；即使绕过该断言，`tasks[0]` 为 `undefined`，`target.id` 立即 TypeError。
- 影响：runner 在 `:844` 的 DB 身份校验与 §"invariants before" 采集之前终止，整条恢复通知 E2E 无法进入页面动作。
- HEAD 对照：HEAD 该路由为 `ApiResponse[list[dict]]`、`EvidenceGrowthService.list` 返回数组，故属 Z57 引入的回归面。

### D2 — 中：`seed_e2e.py` 对 `/applications/mine` 与投递板按数组迭代
- 位置 A：`backend/evals/seed_e2e.py:749-757`（mtime 2026-10-16 未变）
  - `:750-751` `"student": _payload(await student_client.get("/applications/mine"))`（`_payload` 定义于 `:349`，取 `["data"]`）
  - `:756` `for key, items in mine.items():`
  - `:757` `if {item["id"] for item in items} != recorded_by_student[key]:`
- 反例：`/applications/mine` 现返回信封（`api/v1/applications.py:33`）。`items` 是信封 dict，迭代得到键字符串 `"items"/"total"/"page"/"pageSize"`，`item["id"]` → `TypeError: string indices must be integers`。
- 位置 B：`:818-826` 同样对 `/jobs/{job_key}/applications` 的 `_payload(...)` 直接 `for item in ...` 取 `item["id"]`（该端点见 `api/v1/applications.py:44`）。实测该块当前仍为数组式迭代。
- 影响：E2E 播种/隔离校验脚本不可运行；`seed_e2e.py` 是手工/评测入口（`__main__` 于 `:1019`），不在 CI。

### 非缺陷（已逐条核对）
- 计数与切片同归属：`services/applications.py:363-390`（mine）、`:400-425`（candidates）；`services/analysis.py:558-576`；`services/evidence_growth.py:134-150`；`services/notifications.py:84-97` — 五处计数与切片共用同一 `conditions`。
- 企业管理权限 + 撤回排除：`candidates` 先判 `user.role == ENTERPRISE` 与 `JobService.can_manage`，否则 404（`:394-399`）；`conditions` 含 `Application.status != "withdrawn"` 与 `Application.consent_at.is_not(None)`（`:400-404`）。
- `jobId` 不跨学生：`job_id` 追加进 `mine` 的同一 `conditions`（`:367-368`），在计数与切片之前生效，不存在"先取任意首页再过滤"。
- 稳定排序 / 末页夹取：四处均 `created_at DESC, id DESC`；`_clamp`（`:353-356`）与 `min(page, max(1, ceil(total/page_size)))` 在 `total == 0` 时停留第 1 页。
- 增长不可读记录有界不补页：`services/evidence_growth.py:153-169` 仅捕 `AppError/ValidationError/KeyError`，逐行计 `unavailable`，不追扫更深历史；`total` 仍计全部自有行（`schemas/pagination.py:6-15` 语义）。
- 通知 `pageSize` 冲突 422：`api/v1/notifications.py:33-39` 两别名并存且不等 → `AppError(..., 422, code 4224)`；等值放行；仅 `page_size` 保持兼容（`:24-25,39`）。
- 前端 TS 侧：`jianli/src/lib/api/client.ts:261,268,317,322` 已按 `Page<T>` / `unavailableCount` 消费，未见数组残留。

## 二、曾成立但已在窗口内被修掉（保留为过程证据，勿重复报）
| 编号 | 位置 | 我在 08:21 读到的内容 | 08:26 现状 | 文件 mtime |
|---|---|---|---|---|
| D0-1 | `scripts/e2e/private-answer-page-runner.mjs:189-190` | `const tasks = await auth.getJson("/growth-tasks"); const uiIds = tasks.map(...)` → `TypeError: tasks.map is not a function` | `:189` 取 `/growth-tasks?page=1&pageSize=20`；`:190` 断言 `Array.isArray(taskPage.items)`；`:191` `const tasks = taskPage.items` → 已兼容 | 2026-10-17 08:22:09 (+08:00) |
| D0-2 | `backend/evals/release_smoke.py:167` | `{item["id"] for item in board}` → 迭代信封键 | `{item["id"] for item in board["items"]}` → 已兼容 | 2026-10-17 08:22:09 (+08:00) |

## 三、八条 Z57 测试未执行：环境阻塞（非产品缺陷，也不构成通过证据）
- 唯一一轮尝试（命令见 `z57-focused.raw.out`）在六种 basetemp 下全部失败：Git 树内、工作区 ASCII 新目录、平台 `%TEMP%`、预先存在目录、全新不存在目录，均 `PermissionError [WinError 5]`。
- 独立探针（`backend\.venv\Scripts\python.exe` 跑 `D:\jbcode\.probe\h60-fs-probe.py`）：Python 在 `D:\jbcode\.probe` 下 `iterdir / chmod / mkdir / rmdir` **全部 WinError 5**，而同一会话 PowerShell 的 `New-Item/Remove-Item/Out-File` 成功。pytest tmpdir 插件在 sessionstart 与 sessionfinish 都要 list/chmod basetemp（`_pytest/tmpdir.py:301 cleanup_dead_symlinks`、`_pytest/pathlib.py:357 root.iterdir()`），故 `tmp_path`/`tmp_path_factory` 不可用；八条 Z57 测试全部依赖 `tmp_path`（`jobs_db`/`matching_db`），一律卡在 fixture setup，`EEEEEEEE [100%]`。
- 对照：仅把 `--tb`/`-q` 换成 `-p no:tmpdir` 时才露出真实 setup 原因 `fixture 'tmp_path' not found`（`z57-focused.raw.out` 记 r5 为诊断对照，不是验收运行）。
- 结论：**本轮没有任何后端断言被执行过**；分页运行期行为（分页越界夹取、`unavailableCount` 计数、422 冲突）仍属未验证。

## 四、方法与并发说明（重要）
- **源码读取存在陈旧快照现象**：我在 08:21 读到的 `private-answer-page-runner.mjs` / `release_smoke.py` 内容是修复前版本，但两文件 mtime 为 08:22:09（晚于我的读取），且 `git status` 在复核期间新增了 `M test_ci_junit_gate.py`、`M test_release_reconsent_checks.py`、`M scripts/check_ci_junit.py`、`?? test_paginated_lists_postgres.py` 等条目 —— 证实 Codex 并发编辑，且我对这两个文件的首读为陈旧内容。
- 因此 §2 两条**不作为缺陷上报**；本章缺陷结论仅基于 08:26 实读且 mtime 未变的文件（D1 的 recovery runner mtime 2026-10-11、D2 的 seed_e2e mtime 2026-10-16）。
- `source-hashes.sha256` 中的哈希为**复核时点值**，对 08:22:09 被改写的两个文件已不代表当前字节，已在该文件内标注。

## 五、未验证项（交 Codex）
1. 八条 Z57 测试的**真实执行**（本沙箱下 Python 无法做目录操作，必须在正常权限环境重跑，并显式独占 basetemp/cache）。
2. D1/D2 均未在浏览器或真实 HTTP 上实跑（本轮不放行服务、禁连 PG/业务库）；D1 的 `TypeError`/抛错由类型推导 + 代码路径确定，D2 同理。
3. `/match-reports` 由 `ApiResponse[list[...]]` 改信封未发现同类调用者（`backend/evals` 内无该路径引用），但未做全仓非 py/mjs 制品普查。
4. 前端组件运行期消费未验证（不在本轮范围）。

## 六、原始证据与哈希
- `source-hashes.sha256`：11 个被审后端文件 + 4 个调用者文件 SHA256（含"时点值、非当前值"标注）。
- `z57-focused.raw.out`：唯一一轮测试尝试的完整记录（r1–r6 命令、原始尾部 traceback、文件系统探针输出、清理与副作用声明）。
- 本轮另两份产出文件哈希（SHA256，写定后未再改动；`review.md` 为版本记录本身，不自我认证）：
  - `source-hashes.sha256` `20FD823FD4F93F12F7F6ED4F1E7DB936806EF65965E60016D3E2298CB37590FA`
  - `z57-focused.raw.out` `EE1125918B961FEB4BD10C76408B73E0C42AE483CF4D975726FE5D147422E3CC`
- 哈希采用 `Get-FileHash -Algorithm SHA256`；注意本环境 `Get-FileHash` 对 08:22:09 前后被改写的文件曾返回陈旧值（见 §4），故上述哈希仅对被审文件的"复核时点字节"负责，D1/D2 的结论以 08:26 实读文本为准。
- 仅在 `docs/evidence/20261017-HARNESS60-pagination-review/` 写入；临时目录 `D:\jbcode\.probe\`（Git 树外、只读证据，可删）。
