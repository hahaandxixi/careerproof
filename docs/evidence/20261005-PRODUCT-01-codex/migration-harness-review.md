# 完整迁移链首次隔离检查

2026-10-06。随机schema验收仍未通过，不执行closure升级。

传智杯13首轮 `run.raw.out` 显示从0013直接升0014，随后stage读到0013。独立代码复核发现两处：search_path含public且空测试schema未限定version_table_schema，版本查询可能解析到public；GuardedEngine预检SELECT开启事务后没有结束，影响Alembic自有事务与提交。

已要求暂停原脚本、保留失败并修护栏。新护栏须让版本表始终属于本schema，完整链必须实际从base开始；所有迁移业务表不能回落public；预检事务应结束后再交给Alembic。仅current_schema相等不足以证明隔离。

独立 `check-public-migration-readonly.py` 已在READ ONLY事务执行EXIT0，原始 `public-after-chain-harness.raw.out`：public仍0013，target_job_id列不存在，私人草稿表不存在，首次随机schema已清除，writes=0。0014源迁移只新增该列/FK，无其他DML；这些结果支持首次尝试未提交该迁移，不能扩大为完整迁移链通过或所有数据库内容审计。

任务13正在原限定范围修复测试脚本，不得写public补偿或修改源env.py。主会话未执行数据库修复/回退。
