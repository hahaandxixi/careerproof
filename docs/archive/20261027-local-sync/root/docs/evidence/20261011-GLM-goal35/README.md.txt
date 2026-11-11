# 传智杯35：启动记录与失败诊断可靠性（修复轮）

2026-10-11。基线：main @ `80d425312db2d33717780ac1d3328bb32be953da`。修复 32 号审查 [20261011-launcher-reliability-audit](../20261011-launcher-reliability-audit/audit.md) 中的 F1、F4、F5；F2（真实DB可用性）、F3（LASTEXITCODE 残值）按任务卡明确不做。只写卡列五个位置：`scripts/local-runtime.ps1`、`Start-Local.ps1`、`Stop-Local.ps1`、新增 `scripts/local-launcher-recovery.test.ps1`、本目录。Start-Demo 与已有 tests 未改。

## 改动（最小实现，[impl.diff](impl.diff)，3 文件 +95/−39）

**F1 manifest 原子保存与坏记录保守诊断**（`scripts/local-runtime.ps1` 新 helper，两个脚本接线）：

- `Save-LocalRunManifest`：同目录临时文件 `processes.json.tmp` 写入后 `Move-Item -Force` 原子替换（与 `local-build-cache.mjs:39-41` record 同法）；任一步失败删除临时文件并抛含路径错误，先前完整记录不动。
- `Read-LocalRunManifest`：坏 JSON / 空文件 / 解析为 null 时抛含完整文件路径的可操作错误（先确认无运行再手工移开；**不自动删除**）；文件不存在返回 `$null`。
- `Assert-LocalStatePath`：manifest 文件与其直接父目录为 reparse point 时拒绝读写（junction 探针证实可行；不遍历全部祖先，避免云同步目录 reparse 误报）。
- `Assert-LocalReusableManifest`：Start 复用分支先守卫 schemaVersion≠2 或记录数<2 的不完整/旧格式 manifest，抛含路径错误并指向 Stop-Local 恢复；防 `$existing.processes[1]` 为 null 的难懂报错（32 号 F1 伴随项）。
- `Start-Local.ps1` 两处 `Set-Content`（原 :137/:141）改走 `Save-LocalRunManifest`；复用分支改走 `Read-LocalRunManifest` + `Assert-LocalReusableManifest`；`Get-ValidatedLocalProcesses` 增加可选 `[string]$StatePath` 参数，四条身份错误消息附 manifest 路径（不传参时消息与原先逐字一致，现有测试不受影响）。
- `Stop-Local.ps1` 裸 `Get-Content|ConvertFrom-Json` 改走 `Read-LocalRunManifest`：损坏时抛含路径错误、**不删除、不停止**，可重跑恢复。

**F4 复用 digest 覆盖迁移与 alembic 配置**：`Get-LocalBackendDigest` 文件集在 app/\*\*/\*.py（去 tests）+ pyproject.toml 之后追加 `alembic.ini` 与 `alembic\` 递归下 `*.py`/`*.mako`（实际目录名 `alembic`、`alembic.ini`、`alembic\env.py`、`alembic\versions\`，非猜测），排除 `__pycache__`，各段 `Sort-Object FullName` 顺序稳定。新增/修改/删除迁移或改 alembic.ini、env.py 均使 reuse 失效；字节码与无关 scratch 不影响。未执行任何迁移。

**F5 清理失败不掩盖原错误**：新 `Invoke-LocalCleanupSafely`（try/catch + Write-Warning，不 exit）；`Start-Local.ps1` catch 保存 `$originalError`，锁照旧先释放，清理经 helper 包裹，最后 `throw $originalError`。清理范围不变（仍调 Stop-Local，其验证/后代/身份边界逐字未动）、损坏清单不由清理删除、锁互斥与 finally 环境恢复语义不变。

**停止路径抽取**：Stop-Local 的「validate 全部根→后代 BFS→身份快照→停止」循环原样移入 `local-runtime.ps1` 的 `Stop-ValidatedLocalProcesses`（`-ValidateOnly` 供 -CheckOnly），行为逐字不变，作为任务卡要求的真实测试缝；Started/命令/后代边界未弱化。

## 证据（本目录，全部原始输出未加工）

| 文件 | 内容 |
| --- | --- |
| [red-local-launcher-recovery.raw.out](red-local-launcher-recovery.raw.out) | 修复前红测试：5/21 通过、16 失败（helper 缺失、digest 不含迁移、AST 检出 Set-Content），exit 1 |
| [green-local-launcher-recovery.raw.out](green-local-launcher-recovery.raw.out) | 修复后 21/21 通过，exit 0 |
| [green2-rerun.raw.out](green2-rerun.raw.out) | 确定性复跑：21/21，exit 0 |
| [green-local-runtime-test.raw.out](green-local-runtime-test.raw.out) | 现有 `local-runtime.test.ps1`：10 项断言通过（签名向后兼容验证） |
| [green-local-build-cache-test.raw.out](green-local-build-cache-test.raw.out) | 现有 `local-build-cache.test.mjs`：TAP 3/3 通过 |
| [impl.diff](impl.diff)、[hashes-before.txt](hashes-before.txt)、[hashes-after.txt](hashes-after.txt) | 完整 diff 与前后 SHA256 |

原始命令：`powershell -NoProfile -ExecutionPolicy Bypass -File scripts/local-launcher-recovery.test.ps1`、`powershell -NoProfile -ExecutionPolicy Bypass -File scripts/local-runtime.test.ps1`、`node scripts/local-build-cache.test.mjs`。测试方法：全 mock 进程（Get-Process/Get-CimInstance/Stop-Process 哨兵）+ 自有 `backend\.tmp\local-launcher-recovery-<guid>` scratch（finally 清理并核实无残留）+ 写入失败用 FileStream 独占锁确定性注入（探针证实 Move-Item 被阻断）+ junction reparse（免管理员）+ AST 解析 8 个 launcher/消费方脚本 0 错误。B2/B3 证明缺字段/命令变更不触发任何 Stop-Process 且首根不被先行停止；A3 证明写入失败旧记录逐字节保留且无临时文件残留；A5/A6 证明坏记录报错含路径且文件不被删除修改。

## 自审

- 全程未启动/停止任何真实进程、服务、容器、端口；未触碰现有锁、真实 processes.json、local-run 日志、backend\.env、数据库；未联网、未安装、未 Git 提交。写入仅卡列五处。
- 函数级探针确认：junction 可免管理员创建、FileStream 独占锁确定性阻断 `Move-Item -Force`、`ConvertFrom-Json` 错误可 try/catch、`Move-Item -Force` 原子替换且临时文件消失。
- 兼容性核查：`local-runtime.ps1` 消费方仅 Start-Local/Stop-Local/Start-Demo/现有测试（grep 证实）；Start-Demo 只用 `Get-LocalEnvValue`/`Invoke-LocalNative`（未变），其自读 processes.json 仅发生在 Start-Local 成功退出后（原子保存保证完整），无冲突。错误消息无外部断言依赖（grep 证实）。
- 中途返修两项（均为新测试自身问题，非实现问题）：Stop-Process mock 的 `-Force` 需 `[switch]`；PS5.1 `Remove-Item` 对 junction 抛 NullReferenceException（已知 bug），测试 finally 改用 `[System.IO.Directory]::Delete($junction, $false)` 先删链接。该 bug 造成的首个绿跑中断遗留 scratch 已清理并核实为 0 残留。
- F3 按卡未修：Start-Local 成功出口仍无显式 `exit 0`，`$LASTEXITCODE` 残值耦合保持原状；本轮改动未新增/移除任何 native 调用，未改变该现状。

## 未验证项（交 Codex）

1. 真实启停全生命周期（含迁移变更→"Existing run differs"、损坏 manifest→含路径报错、写入失败→旧记录保留的实际进程场景）——按卡由 Codex 实跑。
2. `-ValidateOnly`/`-CheckOnly` 在真实 Stop-Local 下的组合行为（仅 AST+helper 级验证）。
3. digest 对真实 backend 全量文件的数值稳定性（仅合成根验证；`alembic/` 下杂散 `.py` 会保守性失效 reuse，属预期）。
4. `Save-LocalRunManifest` 未 fsync（与 local-build-cache.mjs record 同口径）：掉电可残留 `.tmp` 但目标文件完整，下次成功保存覆盖 `.tmp`。
5. `Move-Item -Destination` 参数非 literal：真实路径无通配符字符；含 `[]` 的安装路径理论上有影响（与现有脚本同级限制）。
6. Start-Demo F3 残值耦合未动（按卡 F3 不做）。

## 交棒

Codex 独立复验本目录证据与 diff，按 32 号验收协议实跑回归（真实启停允许）；Git 提交由 Codex 执行。
