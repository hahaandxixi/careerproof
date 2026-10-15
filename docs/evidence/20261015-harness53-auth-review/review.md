# 传智杯53 · 认证并发与限流只读审查（DeepSeek-V41-Flash High）

- 仓库：`D:\jbcode\web ai\jianli`（实际 Git 根，非 D:\jbcode）
- HEAD：`a3292804193d9245fe6a78643ecb640cd232ddac`（`a329280 fix: use consistent evidence verdict labels across report views`）— 已用 `git rev-parse HEAD` 核对
- 审查时间：2026-10-15 18:05–18:12 (+08:00)
- 模式：只读。未改业务源码/测试/配置/文档，未启动或停止任何服务，未连任何数据库，未读 `.env`/凭据/客户端库，未安装，未 Git 提交/推送，未触碰 P2。本次仅新建本文件与 `source-hashes.json`（该目录事前不存在，已确认）。
- 结论分级：**实测**=我实际执行过的命令/读取；**静态推断**=仅凭代码路径 + 事务隔离语义推导（本次不允许跑测试/脚本/起服务，故所有并发结论均为静态推断，置信度高）。

## 0. 工作树状态与并发写入警示（实测）

`git status --porcelain`（首次 18:06，复审 18:08）：

- 首轮仅 3 个已跟踪修改：`backend/app/services/analysis.py`、`docs/当前接力.md`、`jianli/next.config.mjs`。
- 18:07:22 出现两个新修改：**`backend/app/tests/test_auth.py`**（mtime 18:07:22，+32 行，新增 `test_analysis_task_visibility_keeps_owner_admin_and_denies_other_roles`）与 `jianli/.env.example`。

`backend/app/tests/test_auth.py` 属于本次审查范围，且**在我审查过程中被另一方（Codex）写入**，与"Codex 只改 next.config 与 analysis 角色枚举"的分工声明不符。因此：该文件的 worktree sha256 对应 18:07:22 版本（`36165ef0…`），**不等于 HEAD 内容**（HEAD blob `2e220b88be4459b6cccbb22ba62bb5380ef32949`）。其余被审查文件 worktree 与 HEAD 一致。我未读取/触碰该新增测试内容以外的任何凭据，也未修改它。

## 1. F1（高）同一 refresh 并发可签出两条有效后继 —— 静态推断（高置信度）

代码路径（实测读取）：

- `backend/app/services/auth.py:64-75` `AuthService.refresh()`：`get_active_refresh_token(digest(jti))` → 检查通过后 `stored.revoked_at = datetime.now(UTC)` → `_issue_tokens()`（新增一条 refresh 行）→ `session.commit()`。
- `backend/app/repositories/users.py:29-37`：`SELECT … WHERE jti_hash = ? AND revoked_at IS NULL AND expires_at > now`，**无 `with_for_update()`**，无行锁。
- `stored.revoked_at = …` 是 Python 侧属性赋值，SQLAlchemy 发出的是 `UPDATE refresh_tokens SET revoked_at=… WHERE id=:id`，**WHERE 里没有 `revoked_at IS NULL` 条件**。
- `backend/app/core/database.py:23-25`：每请求一个独立 `AsyncSession`；未设置隔离级别 → PostgreSQL 默认 READ COMMITTED（测试用 SQLite）。
- `backend/app/models/identity.py:24`：`RefreshToken` **未混入 `VersionMixin`** → 没有 `version_id_col`，第二次提交不会触发 `StaleDataError`。
- `identity.py:28` 的 `jti_hash` 唯一约束**不能**阻止本问题：两条后继的 jti 不同，各自唯一。

可复现反例（交错序列，无需改代码即可手工复现）：

1. 登录得到 refresh R0（jti = j0，行 `revoked_at IS NULL`）。
2. 两个标签页/两个客户端在同一瞬间带着**同一个 R0** cookie 打 `POST /api/v1/auth/refresh`。
3. A 的 SELECT 看到 j0 有效；B 的快照早于 A 的 commit，**也**看到 j0 有效。
4. A：`UPDATE … WHERE id=j0` 置 revoked_at；`INSERT` j1。B：同一 UPDATE（PG 上在 A 提交后拿到行锁再执行，条件仍匹配）并 `INSERT` j2。
5. 两个请求都返回 200 且都 `Set-Cookie`；浏览器 cookie jar 以最后到达者为准。

后果：一次轮换产生**两条 `revoked_at IS NULL` 的有效 refresh**。其中未被浏览器保留的那条成为**从未投递、也未撤销的孤儿凭证**，默认可在 `refresh_token_days = 7`（`core/config.py:25`）内一直有效，且没有任何重放检测会发现它（见 F2）。

反例验证建议（我不写、不跑，仅为最小可证伪测试）：同一 engine 起两个 `AsyncSession`，在 SELECT 与 UPDATE 之间插入 await 屏障（可用 monkeypatch 的仓储包一层 `asyncio.sleep(0)`），并发调用 `AuthService.refresh(R0)`；断言**恰好一个**成功，并断言该用户 `revoked_at IS NULL` 的 refresh 行数为 1。现有覆盖缺口（实测）：`backend/app/tests/test_auth.py:183-198` 只在**同一 session 内顺序**轮换，从未并发。

最小修复（任一，按改动量排序）：

```python
# 方案 A（推荐，~10 行，无 schema 变更）：把"检查+撤销"合并成一次条件 UPDATE
updated = await session.execute(
    update(RefreshToken)
    .where(
        RefreshToken.jti_hash == jti_hash,
        RefreshToken.revoked_at.is_(None),
        RefreshToken.expires_at > datetime.now(UTC),
    )
    .values(revoked_at=datetime.now(UTC))
    .returning(RefreshToken.user_id)
)
row = updated.first()
if row is None:
    raise AppError("刷新凭证已失效", code=4013, status_code=401)
# 同一事务内再 _issue_tokens(user)
```

方案 B（更小但更钝）：给 `RefreshToken` 混入 `VersionMixin`，让第二个提交抛 `StaleDataError` 并映射为 401 —— 只是把"两条有效后继"变成"一方 500/401"，语义不如方案 A 清晰。
方案 C（仅 PG）：`SELECT … FOR UPDATE`；缺点是对 SQLite 测试无效，不建议单独使用。

## 2. F2（高）正常跨标签并发 / 网络重试与重放无法区分，且无重用检测

现状（实测读取）：

- `auth.py:66-68`、`api/v1/auth.py:75-77`：已撤销/未知 jti 一律 `4013 / 401`，信息量相同 —— 这本身是好的（不泄露状态），**但同时也没有任何"重用=疑似盗用"的处理**：不撤销后继、不撤销整个 family、不记审计。
- `jianli/src/lib/api/client.ts:186-187`：业务请求 401 → 派发 `careerproof:session-expired`；`AuthProvider.tsx:55-59` 收到即 `setUser(null)` —— 于是"另一个标签页刚轮换成功导致的 401"表现为**静默登出**，服务端无任何信号。
- `client.ts:139-158`：`refreshInFlight` 是**模块级变量，仅限单个 JS realm（单个标签页）**。跨标签页没有 BroadcastChannel/localStorage 锁，N 个标签页 = N 次 refresh 调用 —— 正好落进 F1 的竞态窗口。既有 `api-client.test.mjs:32-46` 断言 `refreshCount === 1`，但它跑在单 realm 内，**不覆盖跨标签**（该测试本次未运行）。

建议协议（可同时解决"区分"和"盗用"）：

1. 保留轮换链：`refresh_tokens` 增加 `replaced_by`（子 jti_hash）与 `family_id`（链首 jti 或"登录会话 id"）。
2. **宽限/幂等窗口**（例如 20-30s，覆盖网络重试与跨标签竞态）：对 j0 的重放在窗口内、且**其后继尚未被使用**时，按重试处理 —— 幂等返回**同一条**后继（或从同一 family 再发一条），不告警。
3. **窗口外重放**，或"祖先被重放时其后继已被使用" → 判定为盗用：一次性撤销整个 family（`UPDATE … WHERE family_id = :f AND revoked_at IS NULL`）、401、写审计、要求重新登录。
4. 判别信号强弱：同一 jti + 窗口内 + 后继未用（强）；UA 一致（弱）；**IP 一致只能作为软信号**，绝不能作为杀 family 的唯一依据（F3 说明为何 IP 不可信）。
5. 关键约束：宽限路径必须返回**已存在的那条后继**，绝不能在 j0 上再铸一条**新的独立链** —— 否则等于把 F1 的漏洞合法化。因此 F1 的原子化必须先落地。
6. 前端以"消除竞态"而非"放宽服务端"来配合：用 `navigator.locks.request("careerproof-refresh", …)`（同源跨标签）包住 `refreshSession()`，或用 BroadcastChannel 广播新会话让跟随者改走 `/users/me`；并在 `careerproof:session-expired` 处理里**先做一次 `getMe()`**，因为 cookie jar 是共享的 —— 若另一标签页刚轮换成功，这次 `getMe()` 会成功，从而避免误登出。

## 3. F3（高）登录失败限流：当前完全不存在；给定设计要求下的三个坑

实测（穷尽 grep `backend/app`）：`rate_limit|RateLimit|login_attempt|failed_attempt|lockout|client_ip|request.client|X-Forwarded-For|forwarded|real_ip` **零命中**。即：

- `auth.py:54-62` `login()`：未知邮箱与错误口令同为 `4012`，停用账号 `4032`；**无计数、无退避、无锁定、无 429/Retry-After**。唯一成本是 pwdlib 的 argon2（`core/security.py:14`）。未知邮箱走的也是 `verify_password` 之外的分支，无诱饵哈希。
- 后端唯一的 IP 相关事实：`api/core/request_context.py` 只处理 `X-Request-ID`，不读客户端 IP；`backend/Dockerfile:11` 为 `uvicorn app.main:app`（**未开 `--proxy-headers`**），因此当前 `request.client.host` 就是 socket 对端地址。

三个必须避开的设计坑：

**3.1 不能相信任意 `X-Forwarded-For`。** 这不是"归属算错"这么轻：如果限流键取自客户端可写的 XFF，攻击者每次换一个 header 值就获得无限尝试额 —— 这是**绕过**，即"限流形同不存在"。正确做法是让 ASGI 服务器做可信代理链解析：加反代后使用 `uvicorn --proxy-headers --forwarded-allow-ips=<显式列出的代理 CIDR>`（或 `FORWARDED_ALLOW_IPS`），使 Starlette 重写 `request.client`，应用代码**只读 `request.client.host`，永不自行解析 XFF**。取不到可信用 IP 时归入"unknown"**全局兜底桶**继续计数，绝不因"键缺失"而关闭限流。IPv6 按 /64、IPv4 按 /24（NAT/CGNAT）粗粒度归并，避免同校/同运营商连坐。

**3.2 不能有"永久演示豁免"。** 不要把 demo 邮箱写进硬编码的 skip-lockout 白名单 —— 那等于给一个已知邮箱发无限次爆破许可（而 `backend/evals/demo_credentials.py` 恰恰依赖这些邮箱，naive 的"按邮箱锁定"会打断演示/CI，naive 的"按邮箱豁免"会开一个 oracle，两者都错）。豁免应**按路径/环境而非按身份**：演示流程改用预发会话令牌或独立的 dev-only 路由（由 `app_env in {development,test}` + 显式环境开关控制），而 `/auth/login` 对**所有**邮箱（含 demo）一律计数。

**3.3 不能造成误锁。** 三个不同键、不同阈值的计数器，且都不是永久状态：

- `(email, client_ip)` 组合键：例如 15 分钟内 ≥5 次失败 → 429 + `Retry-After`，指数退避到上限，**成功即清零**。攻击者在这里付费。
- 仅 email：阈值高得多，且只**限速/加验证**（延迟、验证码），**绝不硬锁** —— 否则任何知道受害者邮箱的人都能锁死他人；共享出口 IP 同理不能只按 IP 计数。
- 仅 IP：粗粒度上限 + unknown 兜底桶。

其他硬约束：口令正确时绝不计入/绝不上锁（先校验再计数，或成功即清）；窗口自动过期，不用"停用账号"当锁 —— 本仓库唯一的停用状态是 `users.is_active=False`（`auth.py:58-59`），那是全账号禁用且**没有解锁流程**，一旦写入只能手工改库，误锁代价过高；若确实要硬锁，必须同时给出管理员解锁路径 + 审计行。持久化必须跨进程共享（多 worker / task runner 是独立进程，进程内内存计数可被轮询绕过）；若无 Redis，用 Postgres 小表 `(key, window_start, count)` + `INSERT … ON CONFLICT DO UPDATE` 即可，不引入新依赖。

## 4. 最小修复清单（按性价比）

1. `repositories/users.py`：把 `get_active_refresh_token` 换成原子 `revoke_active_refresh_token(jti_hash) -> user_id | None`（条件 `UPDATE … RETURNING`），`AuthService.refresh` 改用它。约 10 行，无 schema 变更 —— **修掉 F1 唯一必需项**。
2. `jianli/src/lib/api/client.ts` + `AuthProvider.tsx`：`navigator.locks` 包住 refresh；`session-expired` 前先试一次 `getMe()`。约 15 行，可在服务端改造前先消除跨标签误登出。
3. 补一个并发回归测试（两个 session + await 屏障），断言恰好一方成功 —— 当前最高价值的缺失覆盖（本次不允许我写测试）。
4. F2 的 `family_id`/`replaced_by` + 宽限窗口：需要 migration，建议在 1、2 之后单独排期。
5. F3 登录限流：独立设计，且**不要**基于 XFF 建键（先定反代与 `--forwarded-allow-ips` 事实）。

## 5. 实测 / 静态推断边界

- **实测**：`git rev-parse/status/diff`；文件读取（`services/auth.py`、`repositories/users.py`、`models/identity.py`、`api/v1/auth.py`、`core/security.py`、`core/database.py`、`core/config.py`、`core/request_context.py`、`tests/test_auth.py`、`jianli/src/lib/api/client.ts`、`AuthProvider.tsx`、`jianli/tests/api-client.test.mjs`）；grep（限流/IP 关键字零命中）；SHA-256 与 git blob id 计算；目录不存在性检查。
- **未执行**：pytest、任何 `app.*` 导入、任何数据库连接、任何服务启停、任何网络/模型调用、任何 .env 读取。
- **静态推断**：F1 的双后继结论（代码路径 + PG READ COMMITTED / SQLite 语义 + 无 `version_id_col` 推导，未运行复现）；F2 的跨标签竞态（依据 `refreshInFlight` 为 realm 级模块变量这一代码事实）；F3 全部为"当前无实现"的实测事实 + 建议性设计。
