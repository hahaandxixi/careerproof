# OPS-01C 主匹配独立检查点（尚非阶段签收）

2026-10-07。传智杯19已按固定session `sess_fb819292-30a7-4d2b-b3ab-3b8941a9aa64`确认completed，最后模型finish=stop，交棒文件声明停止写入；见z19-terminal.json。自动标题从冒号前缀改为“传智杯19 OPS-01C 主匹配持久账目接入”，此前前缀查无结果不是任务失踪；观察器增加空格前缀与显式session-id，仍只读/query_only。

## 交付与独立修复

ZCode三个源码及两处必要旧测试的实际hash与其summary.md一致；新测试后来由Codex扩展namespace guard，独立记录修改，不冒称最终hash仍相同。其全量PG1028零跳过/SQLite991+37跳过只证明交棒源码快照，不能代替Codex修改后的全量检查。原始失败、绿灯日志和ZCode声明均保留不追改。

- Codex实际触发规划503无usage、分析429可信usage、分析成功但引用冲突、repair成功，共5个物理HTTP；序号1未知无账目，2..5准确记(100/10、30/5、200/80、150/60)。可信部分480/155，整体usageKnown=false、usageBooked=false。ZCode summary中“unknown但usageBooked=true”的描述没有被其原用例实际证明，是叙述错误；原内核语义保留，不能为此改弱。
- 独立红灯：HTTP期间停用owner、简历解析状态failed、项目解析状态failed，原代码仍COMPLETED并保存报告。review-red-sqlite.raw.out **3失败/1通过**。没有把这些故障藏在业务401断言后面，直接查自有task/report/ledger。
- 修复：新鲜授权共用User→Task→材料短锁顺序，发送前和AI结果发布前复查owner/角色、claim、固定岗位/材料/选择/历史来源/同意；材料必须仍completed、仍属本人且版本/hash一致。报告授权失败不回滚已独立book的消费；Task失败且不发布新报告。规则/Mock旧路径仍按既有兼容分支，不写伪attempt。
- 取消出口先rollback借用事务，再独立bounded/shield结清；结清失败留可恢复事实并保留原CancelledError。**这条取消改动尚待独立故障测试，不能从一般异常用例推导已验证。**
- 自有PG fixture在seed前检查所有创建的表namespace（排除未使用knowledge_chunks），create_all(checkfirst=False)，只清理自有随机schema；仍不触碰closure、业务行或P2。

## 独立命令与结果

backend下实际运行新增review文件：`python -u -m pytest app/tests/test_durable_matching_review.py -q --tb=short -p no:cacheprovider --basetemp=.tmp-ops01c-codex-review-{red,green}`。原红退出1，修复后review-green-sqlite.raw.out **4通过/退出0**。

新增+受影响：test_durable_matching、test_durable_matching_review、test_real_matching、test_ai_evidence_workflow、test_report_input_budget、test_report_history。SQLite `affected-sqlite.raw.out` **91通过/1 PG跳过，退出0**；PG `affected-pg.raw.out` **92通过/零跳过，退出0**，主匹配fixture使用本机careerproof随机专属schema；纯逻辑/历史helper测试按各自原fixture运行。包括实际历史HTTP期间无schema关系锁探针。Ruff目标文件和源码diff检查通过。

全部网站HTTP均合成MockTransport，无真实模型；未升级业务库、closure、依赖或部署/推送。仅本地可验证批次Git提交。

## 未闭合的验收

主链取消/旧租约失效/真实报告commit失败需要独立补验；固定选择字段、材料completed在首次发送前失效也应有定向探针。阶段签收前整理最终source hash与适用回归，不用ZCode自报代替。随后才共用日预留/跨午夜实施及最后当前公告审计/升级排序，完整OPS仍未完成。
