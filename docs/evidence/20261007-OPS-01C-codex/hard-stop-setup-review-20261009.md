# 两链硬停准备缺陷修复

2026-10-09，基线2565d80。独立检查发现matching分支调用test_real_matching.upload_materials时误传tmp_path，并误以为返回两项/currentVersionId/id；真实契约为一个位置参数、三项返回、versionId。提取prepare_chain_task供同一真实硬停测试及离线准备回归使用，修正调用和字段，不改变硬停窗口、身份校验、HTTP/收据/预留/恢复断言。

新增test_budget_hard_stop_setup运行实际合成上传/解析与匹配API；断言pending、同学生owner、匹配尚无报告/attempt/预留、唯一后台捕获任务id准确、原投递snapshot摘要不变。材料解析期间暂时恢复原后台runner并关闭外部AI，随后恢复capture，不提前执行匹配。

## 实测与失败留档

- hard-stop-setup-red.raw.out、red2：新增回归自身误读MatchReport字段，两次初始化失败，保留。
- red3：使用原报告关联AnalysisTask取得owner后，真实复现upload_materials多余位置参数TypeError。
- green：修正上传调用/三元返回及versionId后1通过。
- affected：准备回归+worker保护13通过，退出0。
- collection：两链8硬停案例成功收集，退出0；不是PG执行。
- Ruff首次helper形参与导入fixture同名F811；重命名helper参数fixture_case后检查通过，最终回归1通过（final.raw.out）。

仍缺：当前预算PG专项、实际两条生产链同owner最后槽并发与锁探针、两链真实8窗口及独立复验。Docker查询96044仍等待、5432未恢复，不能用SQLite准备回归替代这些证据。生产源码未改变，没有真实模型/外发/业务库迁移/升级/部署。
