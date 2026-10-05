# E2E-01 隔离环境：2026-10-05 第二、三轮修复证据

执行组别：**免费 GLM-5.3 体验套餐**（以界面实际额度组为准；旧任务卡标题中的"个人GLM-5.3"不是额度依据）。
范围：按 [接续卡](../../task-cards/20261004-E2E-personal-glm53-handoff.md) 与 [隔离审查卡](../../task-cards/20261004-E2E-isolation-review.md)（含 2026-10-05 第二、三次审查补充）继续修复，不重写已正确部分。未实际建库、迁移或启动服务；未触碰 .env、业务库、演示投递、Git 提交与 P2 stash。

## 本轮修复（对应审查条目）

1. **ctypes HANDLE 位宽与存活检测**（第二版观察）：`_windows_process_started_at` 为 OpenProcess/GetProcessTimes/CloseHandle 显式声明 argtypes/restype（HANDLE=c_void_p），并在 GetProcessTimes 的 exit time 非零时判定进程已退出——僵尸 PID（句柄仍保留、OpenProcess 仍成功）不再被当作存活后端。
2. **UTF-8 BOM**：`load_startup_manifest` 改用 `utf-8-sig`，兼容 Windows PowerShell 5 `Set-Content -Encoding utf8` 的 BOM 与无 BOM 两种写法；非 JSON/非对象清单现在抛 `IsolationError` 而非裸 traceback。
3. **.NET `o` 时间戳**：新增 `parse_utc_timestamp`（去 `Z`、截断 7 位小数秒），`verify_startup_manifest` 用它解析 `StartTime.ToUniversalTime().ToString('o')` 的真实格式。
4. **IPv6 方括号**：`guard_base_url` 重建 URL 时为 `::1` 补回方括号，不再产生非法的 `http://::1:8001`；非 loopback IPv6（如 `fe80::1`）仍拒绝。
5. **启动清单字段契约统一**（2026-10-05 复核）：Start-E2E.ps1 全部清单字段（含 `backend` 与 `processes` 条目）改为 Python 侧读取的 camelCase `id/startedAt/needle`；Stop-E2E.ps1 同步对齐（PS 属性访问本就不区分大小写）。
6. **失败清理窗口**：后端 `Start-Process` 后立即写运行清单（原先是 health 通过才写，health 失败时 Stop-E2E 找不到记录而遗留自有进程）；catch 兜底：清单文件存在则走 Stop-E2E，连清单写入都失败时按 PID+开始时间核验后直接停自有根进程（不猜端口杀进程）。
7. **构建产物 tsconfig.json**（第二次审查）：与 next-env.d.ts 一并做原字节备份/finally 恢复，运行前已存在的文件绝不删除或覆盖，本轮不存在而被 build 生成的才移除。
8. **端口归属核对**（第二次审查）：新增 `Test-PortIsOwned`——health 200 后核对 `Get-NetTCPConnection -State Listen` 的 OwningProcess 属于本轮自有 PID，或属于命令行含本轮二进制目录、创建时间不早于记录启动时间（-2s 容差）的子进程；播种前（后端 health 后）与前端就绪后各核对一次。

## 第三轮修复（对应第三次独立审查）

1. **asyncpg 连接关闭**：`create_database` finally 由 `asyncpg.Connection.aclose()`（本机 asyncpg 无此属性，任何分支退出都会失败）改为 `await connection.close()`；新增回归 `test_create_database_closes_on_every_branch_and_keeps_exceptions` 以 monkeypatch 假 `asyncpg.connect` 覆盖 created / already-exists / execute-exception 三条分支，断言均关闭连接且异常原样保留，不连真实数据库。
2. **统一证据日志编码**：审查指出 PS5 `Tee-Object`（UTF-16）与 `Add-Content`（ANSI）混写产生 NUL；统一入口脚本改为全部 `Set-Content/Add-Content -Encoding utf8`，完整保留命令输出（不截 tail），退出码取自 `$LASTEXITCODE`。另增 `utf8-logs` 检查：四份日志以 `utf-8-sig` 解码且逐字节断言无 NUL。
3. **汇总脚本捕获修复（本轮复跑发现）**：`Invoke-Logged` 原用 `Write-Output` 回显命令输出，输出行与退出码混成一个 Object[] 存入 `$results`，导致任何运行都误报 `CHECKS FAILED`（2026-10-05 11:32 版本遗留，summary 曾按旧版本输出记录）。改为 `Write-Host` 回显后复跑，下方汇总结论为真实退出码；Start/Stop-E2E 与 Codex 审计脚本未改动。

## 执行证据（原始输出与退出码）

统一入口：`docs/evidence/20261004-E2E-environment/scripts/run-glm53-fixround-checks.ps1`（本机 Windows 10 x64，Windows PowerShell 5.1.26100.9444，backend venv Python 3.12.14）。汇总结论输出：

```
pytest exit=0
ruff exit=0
ps-parse exit=0
manifest-compat exit=0
utf8-logs exit=0
ALL CHECKS PASSED
```

powershell.exe 进程退出码 0（2026-10-05 复跑实测，bash `$?` 直取）。本机 Windows 10 x64，Windows PowerShell 5.1.26100.9444，backend venv Python 3.12.14。

- [tests.log](tests.log)：`pytest app/tests/test_e2e_fixture_safety.py -q -p no:cacheprovider --basetemp .tmp/pytest-glm53-e2e-a`，**17 passed, 5 warnings in 4.85s**（既有 Swig 弃用警告），`$LASTEXITCODE=0` 直接取自 python.exe，无管道代取。
- [ruff.log](ruff.log)：`ruff check evals/seed_e2e.py app/tests/test_e2e_fixture_safety.py`，退出码 0。
- [ps-parse.log](ps-parse.log)：Start-E2E.ps1 / Stop-E2E.ps1 在 PowerShell 5.1 下 Parser::ParseFile 语法均 OK。
- [ps-python-manifest-compat.log](ps-python-manifest-compat.log)：真实 PS5.1 `Set-Content -Encoding utf8` 写出的清单（首字节 `ef bb bf` BOM、camelCase 键、`o` 格式时间戳）由 Python `load_startup_manifest`+`parse_utc_timestamp` 成功读回（`manifest read back OK: backend.id=… startedAt parsed as …+00:00`）。
- [log-encoding.log](log-encoding.log)：上述四份日志经 `utf-8-sig` 解码且无 NUL 字节（另经独立逐字节复核确认）。
- 新增回归（test_e2e_fixture_safety.py）：BOM/无 BOM/坏 JSON/JSON 数组清单；.NET `o` 时间戳接受与垃圾拒绝；IPv6 括号重建与非 loopback IPv6 拒绝；**真实 Windows ctypes 探测**（本机 64 位：存活 PID 返回 UTC 创建时间；已退出未收割子进程返回 None）；**CLI 拒绝顺序**（业务库名/8000 端口/缺清单三种拒绝均在 create_async_engine 与 httpx.AsyncClient 被 monkeypatch 成禁区的情况下先抛 IsolationError，即先于任何引擎/HTTP 构造）；**create_database 三分支关闭**（created / already-exists / execute-exception 均关闭连接且异常原样保留，假 asyncpg.connect 注入，不连真实数据库）。

## 边界实测

- 本机实测 `Get-CimInstance Win32_Process.CreationDate`（UTC+8）：值为本地墙钟、Kind=Local，`.ToUniversalTime()` 与 `[DateTime]::UtcNow` 一致——`Test-PortIsOwned` 的子进程创建时间比较方向正确。

## 已验 / 未验

已验：上述 17 项回归、Ruff、PS5.1 解析、PS5.1→Python 清单序列化兼容、CIM 时间语义、真实 ctypes 存活/退出探测（本机）、证据日志统一 UTF-8 无 NUL（脚本内检查+独立字节复核）。
未验（留 Codex 签收后实跑）：实际 CREATE DATABASE/Alembic/服务启动全程、`Test-PortIsOwned` 对真实监听的判定、Next 真实 build 对 tsconfig.json 的改写与恢复、非 Windows 行为（探测函数在非 nt 仅测试跳过）。已知残留：catch 兜底（清单写失败窗口）只停自有根进程不停其子进程，主路径 Stop-E2E 仍含子进程树清理。

## 交棒

请 Codex 按审查卡声明复跑最高风险拒绝与撤回/幂等断言，并实跑 Start/Stop-E2E 验证启动、端口归属、tsconfig/next-env 恢复后再签收。
