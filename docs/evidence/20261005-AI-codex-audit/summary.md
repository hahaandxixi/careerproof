# Codex独立AI离线审计：四个契约缺口

日期：2026-10-05，HEAD 70aafb0 + ZCode尚未签收的离线改动。无真实模型、网络或数据库调用。此审计不占用ZCode的离线证据目录。

独立执行新覆盖测试：backend目录`.venv/Scripts/python.exe -m pytest app/tests/test_task_plan_quality_coverage.py -q -p no:cacheprovider`，退出0，8通过。其含义是运行器、统计、来源与已登记红灯得到回归覆盖，不是语义质量全部通过。

独立执行[诊断脚本](check-current-probes.py)，完整机器输出见[independent-probes.json](independent-probes.json)。退出1：14个合成样例、23探针，19符合契约期望，4个预期拒绝草稿实际被接受。核查前后运行器/样例/契约SHA256一致，来源无中途变化；13个有来源样例核对准确，1个无来源单列，没有计为sourceExact通过。真实输出回放0、人工语义复核0、语义通过率null。

| 场景 | 未被拒绝的草稿 | 当前缺口 |
| --- | --- | --- |
| python-cache-partial | partial-as-complete | 仅读路径不足以说明完整缓存读写/过期实现，计划跳过补全直接验收 |
| group-project-boundary | group-artifact-as-personal | 小组报告直接作为个人负责模块的证明 |
| conflicting-export-materials | silent-pick-one-side | 未核实“已实现/尚未实现”冲突便采信一侧 |
| reference-only-sql | reference-as-personal-practice | 第三方SQL参考作为本人实践/能力证明 |

这些是合成负例的契约拒绝缺口，尚不证明真实模型一定会产生这些错误。不得将预期拒绝改成预期通过，不得以8个测试绿色代替23个契约探针全部通过。产品最小修复与失败降级需另定边界，避免用宽泛文本匹配误拒合法的未来补证计划或已明确拒绝采纳的材料声明。

独立审查纠正：`matching_materials.py`向matcher传reference_snapshots，并向enrich传全量snapshots，产品参考链路并非调查报告所称“必然断裂”。运行器合并来源修正与产品语义约束是两种工作，不能混同。

## 产品修复进展（尚待工作流降级回归签收）

AI原任务完成交棒后，Codex新增纯文本task_boundaries并接入contracts：来源替代归属、预设完整功能验收而未核对实现范围、同一具名功能“已实现/尚未实现”冲突。原样例和预期不改；[修复后机器输出](after-boundaries.json)记录14个正例接受、23/23探针匹配、退出0。此输出对应文件哈希，后续归属匹配进一步收窄到小组报告/成果等产物和第三方/参考材料，不拦“小组项目中本人具名提交记录”或“参考本人旧日志”这类个人来源；最终哈希与全部测试由新回归任务补证。

新增边界回归初跑14通过1失败：已明确拒绝采纳的声明被逗号拆句误拒，修复后15边界+42既有工作流=57通过。Ruff通过。独立额外四项归属检查（两项合法个人记录、两项群体/参考代替证明）均符合预期。新建Start Plan免费Flash任务独占回归/新证据目录，补真实工作流修复失败后的降级及完整原始日志后再签收提交。不是通用自然语言矛盾检测，不代表真实模型质量或独立人工语义通过。
