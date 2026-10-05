# 学生主动选择目标岗位：后端实现与验证

2026-10-05，Codex实现。下文保留实现过程的历史检查点；当前已完成最终全量、生产页面与独立签收，见[codex-stage-signoff](codex-stage-signoff.md)。

## 行为

- 补证任务保存可空目标岗位。历史NULL沿用基准岗位；省略targetJobId亦选择基准岗位。
- 保存本人材料时验证目标已发布，并在同一事务保存材料与目标。材料相同且岗位相同仍409；明确新岗位允许只比较要求变化。
- 分析不接受临时目标覆盖，复用现行匹配分析的发布状态、要求、并发与材料校验；分析输入冻结目标，重读核对持久目标与分析及报告的jobId一致。
- 只有已保存的补证新目标可打开跨岗位比较；默认报告比较继续409，同一candidate限制始终保留。不同requirementId独立展示新增/移除，不按技能名称合并。
- 比较增加原/目标岗位身份、标题和job背景；原企业投递不更新。
- 0014仅新增可空FK，SQLite真实升级/回退保存旧任务JSON，拒绝不存在目标与删除被引用岗位。

## 原始证据

全部命令cwd为backend，使用.venv/Scripts/python.exe、隔离pytest临时数据库/材料、无外部模型。

| 文件 | 命令与结果 |
| --- | --- |
| red.raw.out | pytest app/tests/test_growth_target_job.py -q -p no:cacheprovider --basetemp=D:/jbcode/tmp/pytest-growth-target-red-recorded：4失败，EXIT=1，真实缺少targetJobId及请求422 |
| green.raw.out | 初次实现后目标/原补证/比较组合：8失败、29通过、1跳过，EXIT=1。实现错误把公开AnalysisTaskView当持久AnalysisTask访问input_snapshot；已改为先授权读取，再读取持久对象。失败证据保留 |
| green2.raw.out | 加入SQLite迁移回归、修正持久对象读取：38通过、1跳过，EXIT=0；该轮尚不包含后续新增候选人边界测试 |
| boundaries.raw.out | pytest app/tests/test_growth_target_job.py app/tests/test_growth_target_migration.py app/tests/test_evidence_growth.py app/tests/test_report_comparison.py -q -p no:cacheprovider --basetemp=D:/jbcode/tmp/pytest-growth-target-boundaries：39通过、1跳过，EXIT=0 |
| ruff.raw.out | Ruff检查8个本次后端文件，全部通过，EXIT=0 |
| retry-bypass-red.raw.out | 通用retry绕过补证重新保存：新增真实API负例失败，实际202而期望409，EXIT=1 |
| retry-bypass-green.raw.out | 拒绝通用retry并保留失败来源后，组合40通过、1跳过，EXIT=0；旧失败脱离当前growth绑定后仍拒绝通用重试，人工保存可创建新分析 |
| postgres.raw.out | 显式本机compose PostgreSQL，matching_db每例生成独立cp_test随机schema：新迁移/并发、目标变化/授权、原补证合计18通过，EXIT=0；仅删除各例自己生成schema，不触public |
| ordinary-retry-pg.raw.out | 原普通匹配失败的owner-only/原子重试回归1通过，17取消选择，EXIT=0；补证限制不阻断普通匹配重试 |

后续边界包括：同材料且省略/原目标拒绝；不存在/未发布目标拒绝且原选择不变；另一学生无法保存；目标保存后下架时分析拒绝且没有创建分析任务；分析完成后禁止换目标；重复analyze复用任务；持久目标被篡改时重读409；显式跨岗位许可不放宽candidate边界。

三种变化测试均经真实上传解析/API创建报告：只换材料、只换岗位、两者一起；断言企业旧快照完全相等。隔离测试数据库的篡改只用于负例，不用于制造报告，也不接触运行中的E2E数据。

## 当时尚未验证（历史检查点，现状见签收）

1. 阶段全量PG尚未跑；定向PG18通过不替代全量。
2. 独立协议审查已产报告，指出retry旁路并已由Codex真实复现修复；前端第二轮153通过并交棒，Codex34组合与类型检查通过，尚待新页面签收。
3. closure-20261005尚未应用0014或重新构建/重启；当前运行的旧页面不证明新岗位选择通过。
4. 学生真实页面三条路径、桌面/390px、原E2E投递哈希再核对仍待完成。
5. 真实模型调用/人工语义复核未验证。阶段验收前不提交为完成。

## 独立审查处理

- 通用retry旁路是实际缺陷：新补证分析在固定输入中增加仅服务端生成的growthRequiresReselect来源标记，不修改job/materials；通用重试先核对本人所有权、与growth一致的用户锁，再拒绝标记或当前绑定任务。旧失败解除绑定后标记保留；失败记录不会重置。历史未标记且已解除绑定任务无法可靠还原来源，不倒写历史输入。
- 材料内容与版本身份采用不同键有明确用途：attach以内容与角色拒绝空补证；比较保留实际版本身份变化，前端标签为“材料版本变化”，并不声称内容变化或能力提升。相同内容新版本跨岗位比较仍可如实显示版本变化，不改为忽略版本。
- 0014 FK命名已与model一致，真实PG upgrade/downgrade保存旧行JSON与时间字段；SQLite开启foreign_keys真实拒绝失效目标和删除被引用目标。
- 原/目标要求不映射，默认跨岗位与同candidate门独立探针10/10通过。报告标注的HEAD bfe2e65不是本检查点实际HEAD，当前现场以git命令为准。
- 仍需页面核对要求变化、更新基准后的链式任务、缓存复用说明，以及分析途中岗位下架后的固定输入语义；不把内存探针当页面完成。
