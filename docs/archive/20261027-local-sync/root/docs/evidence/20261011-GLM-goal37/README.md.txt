# 传智杯37：启动记录与停止身份的独立风险修复（修复轮）

2026-10-11。基线 ef29532，继承 35 号未提交实现（不清除重做）；36 号并行工作于 AI 合同文件。本轮只写三处：`scripts/local-runtime.ps1`、`scripts/local-launcher-recovery.test.ps1`、本目录。Start-Local.ps1 / Stop-Local.ps1 / local-runtime.test.ps1 逐字节未动（本轮 hash 与 35 号 `hashes-after.txt` 中 Start/Stop 两值一致，见 [hashes.txt](hashes.txt)）。

## 修复（最小实现，[runtime-goal37.diff](runtime-goal37.diff) / [recovery-test-goal37.diff](recovery-test-goal37.diff)）

**风险1 Save-LocalRunManifest 临时文件覆盖**（原 `"$Path.tmp"` 固定名 + `Set-Content` 原位覆盖 + `Move-Item -Force`）：

- 改同目录唯一自有临时文件 `processes.json.tmp-<guid>`，`[IO.File]::Open(CreateNew, Write, None)` 排他创建：任何已存在条目（遗留临时、被占用文件、reparse point）都使创建失败，永不跟随/覆盖/删除外来对象；失败仅清理本次自有的临时路径。
- 目标替换：已存在走 `[IO.File]::Replace`（同卷 ReplaceFile 元数据替换），首次写走 `[IO.File]::Move`。**两者是可用测试验证的 Windows 替换行为，不构成掉电持久性证明**（卡面要求如实声明）。
- PS 5.1 把裸 `$null` 绑定为空字符串导致 `Replace` 抛"路径的形式不合法"（独立探针证实），改传 `[NullString]::Value`。

**风险2 Stop-ValidatedLocalProcesses PID 复用被采信**（原：CIM 快照选后代后，身份仅与自身后续 `Get-Process` 采样比对，从不与快照 `CreationDate` 交叉校验；且逐记录"预检→停止"交错）：

- 每个后代（含根）采样时强制 `CIM CreationDate == Get-Process StartTime`（tick 全等，无任何时间容忍）；不一致 = 快照与采样之间 PID 复用，在任何 Stop-Process 前整体拒绝。
- 根额外与 manifest 绑定：快照中根的 `CreationDate == record.Started`，闭合"验证通过后、快照前"的复用窗口；根从快照消失时，PID 无进程则安全跳过（等价旧行为），有进程则拒绝。
- 两阶段化：先为**全部**根完成快照/后代遍历/身份采样成计划，再统一执行停止——任一根预检失败时首根未被停（E6）。`-ValidateOnly` 边界、身份映射复检语义、错误消息风格逐字保留。

## 测试（纯 mock 进程 + nonce scratch；无真实启停/DB/容器/联网/安装/模型）

先红后修：E1–E6 六项新断言针对真实 helper（dot-source `local-runtime.ps1`）在**未修复实现**上 6/6 红（[red-...raw.out](red-local-launcher-recovery.raw.out)，21/27，exit 1），修复后 27/27 绿 ×2 次确定性复跑（两次原始输出字节级一致）。

- E1 固定临时名处停放外来哨兵文件：旧实现把它移走（红），新实现绕开且往返成功。
- E2 临时路径硬链接到 scratch 外部文件：旧实现穿透改写（红），新实现外目标不变。
- E3 临时路径停放 junction：旧实现 NRE/保存失败（红），新实现保存成功且 junction 与目标内容原样。
- E4 后代 CIM `CreationDate` 与 `Get-Process` `StartTime` 注入不一致：旧实现接受并停止（红），新实现拒绝、零 Stop-Process。
- E5 根与 manifest 时间在快照中漂移：旧实现采信停止（红），新实现拒绝。
- E6 第二根预检失败：旧实现首根已被停（红），新实现零停止。

**声明一处既有测试修正**（非弱化）：B 组 mock 中 CIM 401 的 `CreationDate` 原注入 `procStart+1s`，与同一 PID 的 `Get-Process StartTime`（procStart）及 manifest 物理矛盾；交叉校验使跨 API 同一性成为不变量后该注入不可能通过，已对齐为 `procStart`。B1 断言意图（合法自有根被停止）与全部断言文本未改；其余 21 项既有断言逐字未动且全绿。`local-runtime.test.ps1`（旧测试，10 项）与本轮文件 hash 记录在案证明未重写。

回归：[green-local-runtime-test.raw.out](green-local-runtime-test.raw.out) exit 0；[green-local-build-cache-test.raw.out](green-local-build-cache-test.raw.out) TAP fail 0；[ast-all-scripts.raw.out](ast-all-scripts.raw.out) 五个相关脚本 0 语法错误。scratch 目录测试后自净（backend/.tmp 无 `local-launcher-recovery-*` 残留）。

## 不能证明的范围（如实声明）

- `File.Replace`/`File.Move` 的替换在测试中验证了成功/失败/加锁语义，但**未做也无法在本环境做掉电/崩溃持久性证明**。
- tick 全等依赖"内核创建时间微秒对齐"这一经验事实（NTP 调频期间理论上可破坏）；方向是失败安全（真实世界误报只会拒绝停止、不会误停），但**真实停止路径行为需 Codex 独立验证**（本卡禁止真实启停）。
- 根从 CIM 快照消失且 PID 仍有进程时选择拒绝（保守）；「安全跳过后代」的替代口径未采用，理由写入代码注释。

## 交棒 Codex（一屏审查要点）

1. [runtime-goal37.diff](runtime-goal37.diff)：Save 排他临时名/CreateNew/[NullString]::Value/Replace-vs-Move 分支是否满足卡面"不跟随 reparse、只清理自有文件、失败旧记录保持"；有无遗漏的覆盖路径。
2. [runtime-goal37.diff](runtime-goal37.diff) 第二块：两阶段计划 + 根绑定 + 采样交叉校验是否闭合"验证后→快照前"与"快照→采样前"两个复用窗口；`$snapshots[[int]]` 哈希键、`continue`/拒绝分支语义。
3. [recovery-test-goal37.diff](recovery-test-goal37.diff)：E1–E6 是否为最小红测试且未弱化任何既有断言；B1 mock 一致性修正（唯一一处既有测试改动，见上声明）是否可接受。
4. [red-...raw.out](red-local-launcher-recovery.raw.out) 6 项 FAIL 与 [green-...raw.out](green-local-launcher-recovery.raw.out) 27/27 对照；[hashes.txt](hashes.txt) 与 35 号 hashes-after.txt 交叉核对 Start/Stop 未动。
5. 真实启停验证（按卡面约定）由 Codex 独立接手。
