# 材料准入：独立PostgreSQL并发验证

仅新增`backend/app/tests/test_material_admission_postgres.py`，未修改生产实现、CI配置或原有测试。使用总控分配的专属容器`careerproof-core-acceptance-20261022`、loopback55445的`cp_ci`，复用原`matching_db`的随机`cp_test_*` schema创建、检查和finally清理协议。没有连接5432、已有55442演示库、启停服务、调用模型或安装依赖。解析worker未运行；走真实`PortfolioService`及retry/lifecycle服务，以独立session和`asyncio.Barrier(2)`同时发起。

## 实际结果

- 不同项目并发上传、简历与项目并发上传，各以pending槽位/累计原文件+解压预留容量为独立约束：四种组合均恰好一个成功、一个`AppError`（4291或4131），数据库恰好一条新材料版本/任务/active槽位。
- pending和容量都已到上限时，同一上传requestId并发重放：同versionId/taskId、两次都`created=False`，仍只有一个版本/任务/预留。
- 失败项目重试与另一项目新上传竞争最后槽位：恰好一方进入pending，另一方4291，旧原文件及字节未变。
- 失败释放active槽位与解压预留，保留原文件容量：失败后新上传可进入；再重试原任务会因额外解压预留超额被4131拒绝，两个原文件仍存在，失败任务没有被悄悄改为pending。
- 成功项目的7字节解压文件及40字节原件持续计入容量，之后187字节需求在186字节上限下被拒绝；成功文件、数据库行和完成状态保留。

目标测试`8 passed`，pytest exit0；目标Ruff exit0。命令、运行时源码SHA256及原始输出见`commands-and-hashes.json`、`pytest-first.raw.out`、`ruff.raw.out`。

## 测试敏感性

独立进程`mutate-no-owner-lock.py`仅将其内存中的`portfolio.lock_material_owner`替换为无操作，未修改共享工作区源码。四个并发用例全部变红（4 failed / 4 deselected，exit1），原因均是两个请求同时被准入，说明这些用例确实会识别丢失owner串行化的缺陷。该进程退出后替换即消失，不需要回写或恢复生产文件。

以上首批8项未发现配额准入缺陷；随后下述锁顺序复核确实发现并修复了一项并发故障。这里不证明解析进程超时/取消清理、操作系统崩溃后的目录回收或历史投递快照链路；这些由总控其他测试覆盖。本组也不等于完整PG严格集合或候选全绿。CI严格步骤与门禁由总控集成，不由本组修改。

## 锁顺序实际复现与第9项永久回归

在同一专属PG中，用真实`archive_material`和`create_project_version`交错：归档先持有Project行锁，上传持有User FOR UPDATE，再等待Project；归档写审计需User FK KEY SHARE，形成锁环。实测上传抛出`asyncpg.DeadlockDetectedError`（审计1、版本0）。独立进程中仅将owner锁换成SQLAlchemy `with_for_update(key_share=True)`，原两条服务路径均成功（审计1、版本1）。完整原始反例与方案输出保留在`lock-order-probe.raw.out`。

总控随后在生产准入helper采用FOR NO KEY UPDATE：仍与其他准入互斥，兼容审计外键检查。本组按授权只在新增PG模块补上`test_archive_audit_and_upload_do_not_deadlock_on_owner_lock`，观察实际锁的事件屏障、真实服务方法、本session的5秒锁超时，断言两条路径均成功且审计/材料行存在，未修改生产helper。

原8项保持原样，最终整模块**9 passed，exit0**（`pytest-final.raw.out`）；原生PostgreSQL方言编译确认`FOR NO KEY UPDATE`。原8项继续证明改弱锁模式没有丢失跨项目、跨材料类型的owner串行化。最终四文件源码SHA与命令见`commands-and-hashes-final.json`，首批清单保留为当时范围，不覆盖历史红/绿日志。
