# HARNESS46 独立审查：release_smoke / seed_e2e 隔离守卫（传智杯52 续用 46 号卡）

- 实际 Git 根：`D:\jbcode\web ai\jianli`
- 审查开始 HEAD：`8f40ca8df5aef8f84b0d48a55dcca27075560448`（任务卡给定值，已只读核对）
- 审查中 HEAD 被外部提交移动到：`c022230432e779c7044920979344fdd87db2f961`（reflog 时间 2026-10-14 21:40:28，提交 `fix: clarify first-use demo steps and verify public evidence linking`，改动 `jianli/src/app/demo/page.tsx`、`docs/` 与新证据目录）
- **本审查涉及的全部源码在两次 HEAD 上字节相同**，故结论对 `8f40ca8` 与 `c0222304` 同时成立：
  - `backend/evals/release_smoke.py` sha256 `adc31e1e…2fe1`
  - `backend/evals/seed_e2e.py` sha256 `df8857b3…ab16`
  - `backend/app/tests/test_release_smoke_safety.py` sha256 `eda98ddf…bafc`
  - `scripts/Start-E2E.ps1` sha256 `54a647fc…7f6b`
- 方法：只读源码 + 纯模块探针 + 既有离线安全测试；**未连数据库、未建库/迁移、未启动或停止服务、未访问 3000/3001、未读 `.env`/凭据/storage/客户端数据库、未提交/推送**。
- 产品代码、前端、启动脚本、正式文档一字未改（`git status` 仍只有审查前既存的 ` M docs/当前接力.md`）。

## 结论（G3 权限与快照可靠 / G4 演示可复现）

- **G3：通过，但有一处与文档声明不符的守卫缺口（中）**。`validate_run` 在 `exercise` 的第一次 HTTP 请求之前执行（`release_smoke.py:161` < `:203`/`:226`），已覆盖 mock/端口/库名/storage/PID+启动时间，且 `seed_e2e` CLI 的守卫同样在首个 HTTP 与首次数据库连接之前（`seed_e2e.py:915-932`）。既有 22 个离线守卫用例本轮全部通过。缺口见 B1：只识别符号链接，不识别 Windows 目录联接。
- **G4：可复现性机制成立，但“撤回后拒绝旧授权/新重投”的断言不完整（中）**。撤回后的 4 条企业路由与通知目标 404 断言真实有效，冻结快照跨再查看相等也真实有效；但新重投应用的快照/授权没有任何断言，见 B2。
- 起点卡 `6c1b784` 的旧证据仍可绑定当前字节：`docs/evidence/20261012-release-gate/source-verification.json` 记录的 `release_smoke.py` 与安全测试哈希与当前**逐字节相同**；`seed_e2e.py`、`Start-E2E.ps1` 在 `6c1b784..HEAD` 无差异，可传递覆盖。

## 缺陷与反例

### B1（中，已复现）链接守卫只挡符号链接，不挡目录联接（junction）

- 位置：`release_smoke.py:81-82`（`validate_run`：`file.is_symlink() or any(p.is_symlink() …)` ⇒ `ValueError("Linked E2E state is refused")`）、`release_smoke.py:123-124`（`smoke_account` 同一写法）。
- 反例（`guard-edge-probe.raw.out` PROBE 5/6，Python 3.12.14）：
  - `os.symlink` 在本机不可用（`OSError`），但普通用户即可创建**目录联接**：`_winapi.CreateJunction` 成功，`Path.is_symlink() == False`、`Path.is_junction() == True`（`Path.is_junction` 在 3.12 已存在但代码未使用）。
  - `smoke_account(root, "probe")` **未拒绝**：它把明文口令写到了联接目标 `…\junction-smoke\outside\probe.credentials.json`（仓库根之外），`password_len=32`，与返回账号口令一致。
  - `validate_run(root, "probe", process_probe=…)` **未拒绝**：`.tmp/e2e`、`.tmp/e2e-run` 均为联接时，两份状态文件被跨链接读取并**通过校验**（返回成功，未抛 “Linked E2E state is refused”）。
- 影响：`seed_e2e.py:686-687` 无任何链接检查，直接把夹具账号明文口令写入 `.tmp/e2e/<run>.json`；`release_smoke.py:162-166` 的运行状态写入同样无链接检查。把 `backend/.tmp/e2e`、`.tmp/release-smoke` 预先做成联接，即可让口令落到任意本地目录（例如被同步的目录，或 `Start-E2E.ps1:83-85` 明确拒绝作为 E2E storage 的 `backend/storage`）。守卫声明（`release_smoke.py:1-7`“Linked E2E state is refused”）与实际实现不符。
- 影响面限制：利用前提是攻击者已能在 `backend/.tmp` 下建目录/联接；因此定级中，而非高。
- 建议：把两处改为 `os.path.isjunction(p) or p.is_symlink()`（并对 `path.parents` 同样判断）；`seed_e2e.py` 在写 `state_path` 前补同一检查；或对 `.tmp/e2e`、`.tmp/e2e-run`、`.tmp/release-smoke` 用 `os.lstat().st_reparse_tag` 统一拒绝任何重解析点。

### B2（中，静态可证）撤回后“旧授权/新重投”断言不完整

- 位置：`release_smoke.py:479-498`；对照 `seed_e2e.py:783-802`（夹具层确实做了企业看板与非撤回投递集合比对）。
- 已有的真实覆盖（有效，应保留）：撤回后企业侧 `GET /applications/{id}`、`POST /view`、`POST /resume-download`、`POST /reply` 全部 404（`:480-490`），历史通知目标 404（`:482-483`），企业重复 `view` 得到完全相同的冻结快照（`:467-468`），重投返回新 `id` 且无 `replyText`（`:491-498`）。
- 未被断言的部分：
  1. **新重投应用的冻结快照无任何断言**。`snapshot_hashes` 在 `:500` 取到 `final`（含新应用），但 `:501` 只遍历 `original` 的键，因此新应用的 `report_snapshot` 不与任何值比较。
  2. **新重投应用的企业授权未被验证**（撤回后是否必须在 `shareConsent`/重新查看后才可读）。
  3. **本 run 自己岗位的企业看板未复查**（撤回后不得再列出该投递）；该语义只在夹具岗位被 `seed_e2e.py:783-802` 覆盖。
  4. **新重投路径的幂等性未验证**（`:339-346` 只证明了首个应用的重复提交幂等）。
- 反例（能通过现有全部断言的变异实现）：撤回后 `POST /applications` 若返回新行，但把撤回应用的 `report_snapshot` 一起复制进新应用（`replyText` 除外），或直接把旧应用的企业读权限/冻结快照授权转给新应用，则 `:479-498` 与 `:501` 全部通过。
- 建议：对 `renewed` 断言 `status == "submitted"`、`report_id/reportSnapshot` 来自 `comparison["targetId"]`、企业在其上未重新授权前 404，并在撤回后复查本 run 岗位看板集合。

### B3（低，已复现）数据库 URL 的端口不受限，与 API 端口策略不对称

- 位置：`seed_e2e.py:120-133`（`guard_database_url` 无端口校验）与 `seed_e2e.py:159-162`（`guard_base_url` 强制 8001）；`scripts/Start-E2E.ps1:64-69` 同样接受任意端口。
- 反例（PROBE 1）：`postgresql+asyncpg://u:p@127.0.0.1:6543/cp_e2e_probe` 与 `…@localhost/cp_e2e_probe` 均被接受（仍受 `cp_e2e_<run>` 库名约束，故未越出隔离命名空间）。建议显式要求期望端口或与 `E2E_DATABASE_URL` 来源一致。

### B4（低，已复现）seed CLI 不校验 `backendTarget`/`syntheticVerification`

- 位置：`seed_e2e.py:284-293` 只比对 `runId/databaseName/backendPort/aiExternalEnabled/aiProvider`（+storage/PID）；这两项只有 `release_smoke.py:93-94` 检查。
- 反例（PROBE 4）：`backendTarget="app.main:app"`、`syntheticVerification=False` 的清单**通过** `verify_startup_manifest`，即未经 `-SyntheticVerification` 启动的后端（`Start-E2E.ps1:40`）也能播种夹具；数据库仍隔离、AI 仍为 mock，故定级低，但与“seeder 只对合成校验入口运行”的表述不一致。

### B5（低，静态）失败证据非原子，且与“拒绝重跑”叠加后不可恢复

- 位置：`release_smoke.py:162-166`（`open("x")` 拒绝重复运行）与 `:176`（`persist()` 用 `write_text` 就地截断重写）。
- 反例：在 `persist()` 中途崩溃/断电 → `.tmp/release-smoke/<run>.json` 变成截断 JSON；因 `:165` 永远拒绝同一 run id，文档承诺的“失败保留部分进度”不可恢复。建议写临时文件后 `os.replace`。

### B6（信息）链接守卫分支没有任何测试覆盖

- `backend/app/tests/test_release_smoke_safety.py` 的 22 个用例（本轮全绿）无一创建符号链接/联接，`release_smoke.py:81-82`、`:123-124` 的拒绝分支在测试中从未执行；B1 因此长期未被发现。建议为该分支补一条联接用例（本目录 `guard-edge-probe.py` PROBE 5/6 可直接改写入用例）。

### B7（信息）`withdrawnRestored: False` 是硬编码常量

- 位置：`seed_e2e.py:818`。它不反映本次验证结果（撤回清单在 `:952-962` 另行打印），不应作为证据字段解读。

## 逐项核对（任务卡关注点）

| 关注点 | 结论 | 依据 |
| --- | --- | --- |
| 隔离守卫先于 HTTP 写入 | 成立 | `release_smoke.py:161`（守卫）先于 `:203`（只读快照/库名校验）与 `:226`（首个 HTTP）；`seed_e2e.py:915-917、925-932` 先于引擎与 HTTP |
| 重复运行拒绝 | 成立（失败即保留，不重试写入） | `release_smoke.py:165` `open("x")` → `FileExistsError` 由 `:530-532` 转为退出码 1；`Start-E2E.ps1:92` 拒绝已存在 run 记录 |
| prepare 安全 | 成立 | `release_smoke.py:41-49` 校验 run/venv/stage 与本地 PG，`:50-53` 只改子进程环境副本，`test_prepare_uses_child_env_and_existing_launcher` 断言父环境不变 |
| SkipSeed 恢复 | 只读核对通过，未执行 | `Start-E2E.ps1:247-253` → `seed_e2e --verify-only`；`seed_fixture` 状态存在即 `_verify_fixture`（`:833-839`），缺状态时报错（`:840-841`）；`_verify_fixture` 断言账号 id、`/applications/mine` 集合、快照哈希、每单恰一条 submitted 事件与企业通知（`:721-775`），且从不恢复撤回（`:818`、`:952-962`） |
| 账号环境与所有权 | 成立 | 冒烟写入使用独立新学生（`release_smoke.py:118-134`、`:232-238`），企业/studentA2 用夹具账号登录（`:224-231`），日志与结果不含口令（`:185-188`、`:508-510`）；口令仅落 gitignore 的 `backend/.tmp*`（`backend/.gitignore:11` 已核对） |
| 撤回后拒绝旧授权 | 部分覆盖 | 见 B2 第 1–3 点（4 条企业路由与通知目标 404 有效） |
| 新重投 | 部分覆盖 | 见 B2 第 1、2、4 点（新 id、无 replyText 有效） |
| 生成/比较断言 | 真实覆盖 | `:317`（3 项）、`:446-454`（`baseId`/`targetId`/`contextChanges` 含 materials 不含 requirements/`addedEvidence`）、`:467-468`（冻结快照不变） |
| 日志泄露 | 未发现 | 错误只记录 `errorType`（`:509`），HTTP 失败不落响应体（`:185-188`），`<run>.credentials.json` 不打印 |

## 未验证项（本轮明确未做）

1. `release_smoke.exercise` 的完整 HTTP 链未执行（任务卡禁止启停服务/操作 3000/3001/数据库），因此上传解析、匹配、成长对比、撤回重投的**运行时**结果本轮无新证据；可引用的仍是 `docs/evidence/20261012-release-gate/`（其源码哈希与本轮逐字节相同）。
2. 未执行 `prepare_run` → `Start-E2E.ps1`（涉及建库、迁移、启服务），Docker/PG 状态未核对。
3. `-SkipSeed` 的实际恢复执行未跑；仅静态核对。
4. 浏览器/3001 页面验收、真实模型质量、前端构建未涉及（按卡标未验证）。
5. 未复跑旧证据目录中的 HTTP 链原始日志，只做哈希绑定比对。
6. pytest 本轮因 DSH 工作区沙箱拒绝在仓库内创建临时目录，改用工作区外临时根（`D:\jbcode\__dsh_review_tmp`，已删除）以一次性提权运行；对被测代码无影响。

## 环境附注（不影响产品结论）

写入任务卡指定证据目录时被 Windows 文件权限拒绝：`D:\jbcode\web ai\jianli\docs\evidence` 所有者为其他 SID（`…-1007`）且当前用户缺少“更改权限/取得所有权”，自动修复脚本按策略拒绝（未改动任何权限，无需回滚）。报告：`D:\jbcode\dsh-acl-recovery-20261013\acl-report-*.jsonl`；本目录文件改由 Harness 侧写入完成。

## 证据清单（本目录）

| 文件 | 内容 |
| --- | --- |
| `review.md` | 本报告 |
| `source-hashes.json` | 源码 blob/sha256、HEAD 漂移与旧证据绑定关系 |
| `module-safety-tests.raw.out` | `pytest app/tests/test_release_smoke_safety.py -p no:cacheprovider -q -rA` 原始输出：22 passed，退出码 0 |
| `guard-edge-probe.raw.out` | 纯模块探针原始输出（PROBE 1–6，含 B1/B3/B4 复现） |
| `guard-edge-probe.py` | 探针源码；不连数据库、不发 HTTP、不启服务 |
