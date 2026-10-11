# 传智杯32：启动脚本可靠性只读审查（audit）

2026-10-11。审计基线：HEAD `1f62131e4f70fe48241eb97da312e55f77144ec4`。任务卡写 ff0c170、调度记录写 3d76a5b，两者均为 HEAD 祖先；`git diff ff0c170..HEAD` 对全部审计对象为空（[git-baseline-ff0c170.txt](git-baseline-ff0c170.txt)，0 行差异），三个提交上脚本内容一致，审计不受基线漂移影响。

方法：源码走查 + 纯 PowerShell 解析（AST、合成数据离线模拟）+ node 只跑自有 3 行合成脚本。未启动/停止任何真实进程、容器、服务、数据库；未读 .env/密钥；未触碰真实锁、processes.json、local-run 日志。原始输出：[offline-probes.raw.out](offline-probes.raw.out)；文件指纹：[hashes.txt](hashes.txt)。20261010 已实跑验证项（reuse、BuildOnly、锁互斥、PID 三重验证、stderr 退出码、CMD 透传）不重做，见 20261010-startup-launcher/README.md:15-21。

## 发现（按优先级）

### F1【高】processes.json 写入非原子 + 解析失败无路径：损坏后启动与停止双双失效

- 触发：启动中途（掉电、被杀、磁盘满）使 `Start-Local.ps1:137` 或 `:141` 的 `Set-Content` 写 processes.json 中断，留下截断 JSON。
- 期望：Start/Stop 至少其一给出含文件路径的明确错误，可恢复。
- 实际：`Start-Local.ps1:95` 与 `Stop-Local.ps1:14` 都在 `ConvertFrom-Json` 裸抛；探针 1 证实异常文本不含文件路径（"传入了未终止的字符串。(56)"）。Stop-Local 无法停止也无法清理（manifest 删除在 `Stop-Local.ps1:40`，永远到不了），每次 Start/Stop 都在同一处失败，只能靠用户猜到并手删文件。
- 伴随：manifest 合法但只有 1 条（backend 已写入、frontend 写入前中断）时，reuse 分支 `Start-Local.ps1:101` 以 `$existing.processes[1]`（$null）调 `Wait-LocalService` → `local-runtime.ps1:83` `Get-Process -Id $null`；探针 2 证实即使 `-ErrorAction SilentlyContinue` 也抛参数绑定异常，报错难懂（行为仍安全：catch→Stop-Local 停掉 live 的那条）。
- 最小修复：① 写 manifest 改为临时文件+`Move-Item -Force`（与 `local-build-cache.mjs:39-41` 的 record 同法），建议在 `scripts/local-runtime.ps1` 加 `Save-LocalRunManifest`/`Read-LocalRunManifest` 一对 helper 供两脚本共用并可在 local-runtime.test.ps1 加断言；② 两处解析 catch 后带 `-LiteralPath` 路径 rethrow"run record unreadable, move it aside after confirming no live run"（不自动删除——损坏≠无运行，守住不误删）；③ `Wait-LocalService` 入口对 `$null -eq $Record` 报"run record incomplete"。
- 反例（现状）：截断 JSON → Stop-Local -CheckOnly 抛无路径 JSON 异常。正例（修复后）：同一输入得到含 backend\.tmp\local-run\processes.json 路径的中文可操作错误；中途断电写入后旧 manifest 完整保留。

### F2【高】reuse 分支"healthy"判定不含 PostgreSQL

- 触发：backend/frontend 进程存活但 postgres 停止——`docker compose stop postgres`、容器崩溃、或 Docker Desktop 重启（`backend/docker-compose.yml` 无 restart 策略，默认 no，容器不会被拉起）。
- 期望：启动器检测到 DB 缺失并恢复或明确报错。
- 实际：manifest live → 一致性检查全过 → `Start-Local.ps1:100-103` 仅依赖 `/api/v1/health`；`backend/app/api/v1/health.py:11-13` 只返回静态 ok，不查 DB → 输出 "Existing owned CareerProof services are healthy; reused without migration or rebuild."，实际业务全 500。
- 最小修复：reuse 分支 Wait 通过后追加一次 DB 存活检查，未运行时执行与 `Start-Local.ps1:131` 同款幂等 `docker compose up -d --wait postgres`（与全新启动路径对称，非构建、无副作用），失败再 throw。备选（行为更保守）：只检测 `docker compose ps --status running postgres` 并报错指引。
- 反例：stop postgres 后重跑 Start-Local 误报 healthy。正例：同场景自动补起 DB（或明确报"PostgreSQL not running"）后才放行。

### F3【中】Start-Local 成功退出码寄生于 $LASTEXITCODE 残值

- 触发：`Start-Demo.ps1:90` 以 `$LASTEXITCODE -ne 0` 判定 Start-Local 结果，但 Start-Local.ps1 无 `exit 0`；当前恰好每条成功路径都以成功的 native 命令结尾（`Start-Local.ps1:72` inspect 必跑且为最后 native），残值=0。
- 实际（探针 3）：子脚本无 native 时 `$LASTEXITCODE` 为 $null，`$null -ne 0` 为 true → Start-Demo 误抛 "Local services did not start successfully."。属隐性耦合：任何未来调整让某成功出口不以成功 native 结尾即复燃。
- 最小修复：`Start-Local.ps1` 四个出口（`:68` CheckOnly、`:103` reuse、`:128` BuildOnly、`:144` 末尾）由 return/自然结束改为显式 `exit 0`（finally 仍会执行）。
- 反例：native-less 成功出口 → Start-Demo 误判失败。正例：`powershell -File Start-Local.ps1 -CheckOnly` 后 `$LASTEXITCODE` 恒 0；候选全失败时仍非 0。

### F4【中】Get-LocalBackendDigest 不覆盖 alembic 迁移：迁移变更被 reuse 吞掉

- 触发：开发期新增/修改 `backend/alembic/versions/*.py` 后重跑 Start-Local（服务仍在运行）。
- 期望：迁移属后端生产源码，变更应使 reuse 失效，走 Stop→Start 并执行 `alembic upgrade head`（`Start-Local.ps1:132`）。
- 实际（探针 4）：`local-runtime.ps1:24-25` 文件集只有 `app/**/*.py`（去 tests）+ pyproject.toml，迁移文件变更 digest 不变 → `Start-Local.ps1:99` 判定一致 → reuse 报 "without migration"，DB schema 与代码漂移。README（20261010:12）"后端生产源码……一致时才复用"的承诺与实现有偏差。
- 最小修复：`local-runtime.ps1:24` 后追加 alembic 迁移目录到文件集（`Get-ChildItem -LiteralPath (Join-Path $Root 'alembic') -Recurse -File -Filter '*.py'`，同款排序+哈希），一行级改动。docker-compose.yml 变更同样不入 digest，但影响仅限容器参数、重启即可矫正，不单列。
- 反例：改迁移 → Start-Local reuse 跳过 upgrade head。正例：改迁移 → "Existing run differs... Stop-Local.ps1, then start again."，重启后 upgrade head 生效。

### F5【中低】catch 内清理失败会掩盖原始异常

- 触发：启动失败进入 `Start-Local.ps1:145-148` catch 后，若 `Stop-Local.ps1` 自身抛错（锁竞争、身份验证 throw 等），新异常替换原异常向上传播，根因丢失。
- 最小修复：catch 内先保存 `$_`，清理包 try/catch 只 `Write-Warning` 清理失败原因，最后 `throw $original`。清理调用成功路径不变。
- 验收以代码审查+模拟注入为主（真实注入需并发窗口）。

### F6【低，观察不修】两项机制性弱点（当前路径未触发，探针已证机制）

- probe 输出解析对 stderr 噪音脆弱：`Start-Local.ps1:32-34/46-48` 以 `2>&1` 合并后仅在验证成功时 `$metadata | ConvertFrom-Json`；当前 `verify_dependency_environment.py:40` 与 `verify-frontend-runtime.mjs:75-79` 输出为单行纯 JSON（stderr 仅失败时使用，已读源码确认），但探针 5 证实一旦未来 node/python 在成功路径打任何 stderr（如 ExperimentalWarning），ConvertFrom-Json 即 throw。修复方向：解析前过滤到非空行或捕获后带上下文 rethrow；换 Node/Python 版本时回归此项。
- 后代链断裂泄漏：`Stop-Local.ps1:22-25` 的 BFS 依赖父子进程链存活，中间 redirector/worker（如 venv launcher 与其 base python 子进程、next 与其 server 子进程）若中途死亡，其后代遍历不到；停止后也无端口释放确认，泄漏要到下次 Start 的 `Start-Local.ps1:108` "Port N belongs to another run" 才暴露。符合约束的改进（不杀端口）：删除 manifest 后对 8000/3000 各做一次 `Get-NetTCPConnection -State Listen` 只读检查，仍有监听则 `Write-Warning` 指明 PID。
- 已知残余（不修）：`Stop-Local.ps1:28-37` 身份 Ticks 复核与 `Stop-Process` 之间存在毫秒级 TOCTOU 窗口，PowerShell 层无原子句柄原语可消除，复现需竞态注入，维持现状。

## 已核查无问题（对应任务卡关注点）

- 环境自动选取：候选过滤+正则守卫（`Start-Local.ps1:19-27/37-49`）、显式参数不回退、8.3 短名对 `.venv-*`/`dep-frontend-*` 前缀过滤不构成误匹配；候选目录名不进通配上下文（全 LiteralPath）。
- 缓存失效：fingerprint 覆盖 9 类输入+产物完整性+BUILD_ID+stamp.root（`local-build-cache.mjs:6-30`）；`jianli/` 现无 `.env*`（仅 .env.example，Next 不读），src 无任何 `NEXT_PUBLIC_*` 引用（grep 证据），"指纹不含构建期环境"当前无实际影响。
- BuildOnly：跳过 env/端口/docker/manifest（`Start-Local.ps1:76/108/110/128`），与 live run 冲突时明确拒绝（`:98`）。
- 路径：中文/空格全链 LiteralPath；`Start-Demo.cmd:3/5` 引号包裹；`Start-Local.ps1:139` 对含空格 nextPath 手工加引号（PS5.1 -ArgumentList 不自动引号）；probe 4 证实 digest 以传入前缀一致截断。
- reparse：venv/前端目录三处拒绝 ReparsePoint（`Start-Local.ps1:27/44/56`）、buildFingerprint 对 symlink lstat 拒绝（`local-build-cache.mjs:12`）、verify-frontend 拒绝源码 symlink（`verify-frontend-runtime.mjs:54`）。
- 退出码：两个 CMD 入口 `if errorlevel 1` 正确承接 powershell -File 的 throw→1。
- PID/所有权：PID+StartTime Ticks+CommandLine needle 三重验证（`local-runtime.ps1:52-56`）；后代筛选的 `CreationDate >= record.Started` 正确防 PID 复用误伤（`Stop-Local.ps1:24`）； descendant 中途复用会 throw 且重跑 Stop 可恢复（manifest 未删）。
- 锁：launcher.lock 双向互斥（Start-Local:90 / Stop-Local:8），Start-Local catch 先释放再调 Stop-Local 避免自锁（`:146`）；demo-launcher.lock 覆盖初始化全程（Start-Demo.ps1:84）；句柄随进程死亡由 OS 释放，无泄漏。
- 失败清理：Wait 失败→catch→Stop-Local 停 live 记录+删 manifest，路径闭合（backend 单条、双条、frontend 先死各态走查通过）；日志固定在 backend\.tmp\local-run\*.log，失败文案均指向该目录（`local-runtime.ps1:83/90`）。
- 语法：5 个 ps1 AST 解析 0 错误（probe 7）。

## 验收协议（修复轮执行；本审计未实跑）

1. F1：隔离 `.tmp` 环境写入截断 manifest → `Stop-Local.ps1 -CheckOnly` 输出含 processes.json 路径与可操作指引；正常启动→停止→重启循环 3 次无残留；local-runtime.test.ps1 新增损坏 JSON/单条 manifest 断言。
2. F2：真实生命周期中 `docker compose stop postgres` 后重跑 Start-Local → 自动补起或明确报错，不得输出 "healthy; reused"。
3. F3：`powershell -File Start-Local.ps1 -CheckOnly` 后退出码为 0；让所有 venv 候选验证失败时非 0。
4. F4：运行中服务 + 新增空迁移文件 → Start-Local throw "Existing run differs"；Stop 后重启完成 upgrade head。
5. F5：代码审查确认原异常保留；可选 mock 注入验证。

## 自审

- 全程只读仓库；写入仅本目录与 TEMP 无数据 scratch（probes.ps1 及合成件）。探针含 dot-source `local-runtime.ps1`（文件头声明无副作用）与对 TEMP 合成目录的纯读函数调用；node 仅执行自有 3 行合成脚本。
- 未触碰：真实锁/manifest/local-run 日志/进程/Docker/DB/backend\.env。未安装、未联网、未 Git 提交。
- 结论分级依据：F1/F3/F4 有探针机制证据；F2/F5 有源码级必然性走查；F6 明确标注"当前未触发"。未声称任何实跑验证。
- 范围区分：本批不含传智杯30（AI）/31（页面）内容；未重复 20261010 已验证项。

## 交棒

交 Codex 审查本 audit 与证据；修复范围建议限定为 F1-F5（F6 观察不修），其中 F1、F2 优先。修复后按验收协议实跑回归（修复轮允许真实启停）。
