# 传智杯40：真实Windows时间精度与临时清理所有权（GLM，2026-10-11）

Git根D:\jbcode\web ai\jianli，起点6410915（工作区=37终态），继承35+37成果。两处修复均先红后修，全部证据在本目录。

## 真实精度观察（只读，4个独立样本，方向一致=截断）

| 来源 | CIM UTC ticks | .NET UTC ticks | 差(.NET−CIM) |
|---|---|---|---|
| Codex实测 PS 102808（卡面） | 639273191745370010 | 639273191745370012 | +2 |
| 本会话首次探测自有 PS 110244 | 639273199924065320 | 639273199924065322 | +2 |
| real-identity 自身进程 116576 | 639273208101130540 | 639273208101130547 | +7 |
| real-identity nonce子进程 58752 | 639273208112670850 | 639273208112670851 | +1 |

所有样本：CIM值 mod10=0（微秒栅格）、CIM ≤ .NET、差 < 10 ticks（< 1 μs）。**四个样本均与"截断（floor到微秒栅格）"一致，未出现CIM高于.NET的舍入情形**，故按观测采用floor规则；若Codex复验发现反例（CIM > .NET），规则需重议（卡面约定）。

## 修复1：跨API时间比较归一到CIM微秒栅格（整数精确）

`scripts/local-runtime.ps1` 新增 `Get-LocalCimMicrosecondTicks`：`[Math]::DivRem($Ticks,10)` 取余做整数地板，**无double除法**（double在>2^53即6.39e17的ticks上必丢精度，实测PS `%` 与DivRem在 639273191745370012 上均精确）。应用于全部 CIM↔.NET 比较点：

- Stop-ValidatedLocalProcesses 根绑定（快照CIM vs manifest）与采样交叉校验（快照CIM vs 采样.Get-Process）：双侧floor到栅格后比较；
- Stop 与 Test-LocalPortOwner 的后代遍历 `-ge`（CIM子创建时间 vs .NET根启动时间）：双侧floor后比较，修复"子进程与根同微秒内创建被误排除出停止家族"；
- **保持严格不变**：manifest(.NET 'o' 字符串) vs Get-Process 根身份（Get-ValidatedLocalProcesses）、采样 identities（存原始.NET ticks）vs 停止前 Get-Process——任何 .NET↔.NET 差异（含1 tick）仍拒绝；相差整整1微秒（10 ticks）及CIM高于.NET（负差）仍拒绝；多根全部预检先于任何 Stop-Process 的两阶段结构未动。

## 修复2：Save-LocalRunManifest 清理所有权

排他创建抽取为 `New-LocalExclusiveTempStream`（CreateNew/Write/None，纯重构先行并验证行为不变），`Save-LocalRunManifest` 增加显式 `$ownsTemporary` 状态：**仅当排他创建成功返回后才置真**；catch 中仅 `$ownsTemporary` 为真才 `Remove-Item` 临时路径——CreateNew被拒（未知对象赢得竞态）时绝不删除外来对象。失败消息含路径、"前一条记录原样保留"承诺、Replace/Move/[NullString]::Value 语义均未放宽。

## 红绿与测试（纯mock+自有scratch，先红后修）

1. 纯重构（仅seam抽取）：27/27绿（复跑验证行为不变）。
2. 新增F1–F6（[recovery-test-goal40.diff](recovery-test-goal40.diff)）：红跑 **30/33，exit 1**（[red-local-launcher-recovery.raw.out](red-local-launcher-recovery.raw.out)）——F1 真实ticks例（.010/.012）被误拒（红）、F4 多根真实ticks全预检被误拒（红）、F5 CreateNew被拒后外来对象被删（红，经seam注入"输掉的竞态"：外来对象先占临时路径、排他创建抛IOException）；F2（整1μs拒）、F3（采样后.NET漂移拒）、F6（CIM高于.NET拒）为守卫，红绿两态均绿。
3. 修复后 **33/33 绿 ×2**（[green-…](green-local-launcher-recovery.raw.out)/[green2-…](green2-local-launcher-recovery.raw.out)），两次输出字节级一致（cmp全等）；旧 [local-runtime.test.ps1](../local-runtime.test.ps1) 10/10（[green-local-runtime-test.raw.out](green-local-runtime-test.raw.out)）；6脚本AST 0错（[ast-all-scripts.raw.out](ast-all-scripts.raw.out)）。

## 真实验证（只读；未停止任何进程、零文件写入）

[scripts/local-launcher-real-identity.test.ps1](../../scripts/local-launcher-real-identity.test.ps1)（新文件）内置 Stop-Process 陷阱（任何停止尝试即失败），全程仅读：
- R1/R2 自身进程：按真实StartTime('o')与自身命令行精确标识建记录，`-ValidateOnly` 判活成功；真实ticks对落栅格（gap=7）。
- R4/R5 独立nonce短命子进程（隐藏窗口、命令行含唯一nonce、4秒自退出、`Wait-Process` 自然等待，绝不Stop；所有权已记录 pid=58752）：ValidateOnly 判活成功；ticks对落栅格（gap=1）。
- R3/R6/R7 真实拒绝路径：命令行不匹配、+1小时、+10 ticks(1μs) 的记录均被拒。

结果 **7/7，exit 0**（[real-identity.raw.out](real-identity.raw.out)）。

## 自审要点（已核对）

- [runtime-goal40.diff](runtime-goal40.diff) 由37终态快照生成，快照hash同时匹配 git blob SHA1（b32c49b9/3296d2a8）与37 hashes.txt 记录值（00886574/087dff6f）——diff精确、无夹带。
- Start-Local.ps1 / Stop-Local.ps1 / local-runtime.test.ps1 当前hash与37冻结记录逐字相同（[hashes.txt](hashes.txt)），36/39后端、前端未触碰；唯一改动即卡面授权的 scripts/local-runtime.ps1、scripts/local-launcher-recovery.test.ps1、新增 scripts/local-launcher-real-identity.test.ps1 与本目录。
- identities 映射仍存原始 .NET ticks，停止前比较保持严格相等（F3守卫钉住）；栅格归一只作用于跨API比较。

## 未验证/风险（如实声明）

- **真实停止路径（非ValidateOnly的实际 Stop-Process）未实跑**——卡面禁止，归Codex独立实施；本卡证据不含任何真实停止，勿以mock绿推定。
- floor规则基于4个真实样本的截断方向；理论上若WMI在别处/别时采用四舍五入（CIM > .NET），F6口径会拒绝合法进程——方向是失败安全（误拒不停，绝不误停），但需Codex复验；若复现反例，按卡面约定先报告再定规则。
- CIM mod10=0 依赖 WMI DMTF 微秒表达；未验证更早系统/极端时钟调频下的行为（37号风险1同类声明）。
- 子进程样本量小（1个nonce子进程+2个自身进程+Codex的1个）；未做批量统计。

## 交棒Codex（一屏审查要点）

1. [runtime-goal40.diff](runtime-goal40.diff)：三处比较点的floor规则是否恰好放宽到微秒栅格、未放宽1μs以上；identities原始.NET ticks与停止前严格比较是否保留。
2. [runtime-goal40.diff](runtime-goal40.diff) 修复2：`$ownsTemporary` 是否在且仅在排他创建成功后置真；ConvertTo-Json失败/写失败/Replace失败/创建被拒四条路径的清理行为。
3. [recovery-test-goal40.diff](recovery-test-goal40.diff)：F1–F6是否为最小红测试且未弱化A–E任何既有断言（33=27+6）。
4. [real-identity.raw.out](real-identity.raw.out)：4样本ticks与栅格结论复核；真实停止专项按约定由Codex实施。
