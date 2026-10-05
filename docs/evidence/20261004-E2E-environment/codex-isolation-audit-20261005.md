# Codex 隔离环境独立审计（进行中）

2026-10-05，起点 main@b3611fa。ZCode当前实际为免费GLM-5.3（体验套餐），旧任务标题仍含个人计划，不能作为额度依据。

## 业务库启动前基线

只读执行（退出码0）：

```powershell
docker compose exec -T postgres psql -U careerproof -d careerproof -At -c "SELECT 'revision',version_num FROM alembic_version; SELECT 'users',count(*)::text FROM users UNION ALL SELECT 'jobs',count(*)::text FROM jobs UNION ALL SELECT 'applications',count(*)::text FROM applications UNION ALL SELECT 'application_events',count(*)::text FROM application_events UNION ALL SELECT 'notifications',count(*)::text FROM notifications UNION ALL SELECT 'match_reports',count(*)::text FROM match_reports;"
```

```text
revision|0013_ai_usage_idempotency
users|20
jobs|36
applications|6
application_events|21
notifications|11
match_reports|60
```

这只证明采样表行数及迁移版本；不证明每行内容不变。后续实际隔离启动后重新核对，不将行数一致表述为全库内容哈希一致。

## 尚待验收

ZCode正在修复Windows HANDLE/存活、UTF8 BOM、IPv6、清单字段和失败清理；已追加tsconfig字节恢复及端口归属审查。实际独立数据库创建、迁移、播种、前端生产构建与双端页面均未完成；不能签收E2E-01。

## 独立定向回归

在backend运行，退出码0：

```powershell
.\.venv\Scripts\python.exe -m pytest app/tests/test_e2e_fixture_safety.py -q --basetemp=.tmp/pytest-codex-e2e-audit-20261005
```

```text
............... [100%]
15 passed, 5 warnings in 4.81s
```

5条为现有Swig类型DeprecationWarning；本轮未改相关依赖。覆盖Windows本机进程探测、BOM及坏JSON、.NET时间戳、IPv6与原夹具安全项。运行时ZCode仅在继续补启动脚本；最终脚本端口归属、构建配置恢复和真实启动仍需另验，15项通过不等于全链路通过。

端口归属：执行 `docs/evidence/20261004-E2E-environment/scripts/codex-port-ownership-check.ps1`，退出码0，7个用例通过。脚本从当前启动脚本AST提取实际函数，以模拟套接字/进程库存覆盖根/子/孙进程、同命令无关进程、错误命令、过早创建及无监听。未实际启动服务，不作为真实监听证明。

依赖与环境预检：从现有Settings内部派生回环独立库URL（未打印连接凭据），运行 `scripts/Start-E2E.ps1 -RunId audit-20261005 -CheckOnly`，退出码0。确认8001/3001空闲、Python/Next/Node依赖可用、存储位于backend/.tmp；未创建数据库或启动服务。

第三次审查发现启动阻断：本机 `asyncpg.Connection` 有 `close`、无 `aclose`（本机Python类属性实查）；现有create_database退出仍调用aclose。已退回ZCode最小修复，并要求created/already-exists/execute异常三分支关闭回归，以及修复PS5混合日志编码；当前不能签收。

## 实际启动、失败修复与重启验收

建库关闭缺陷修复后，Codex独立回归17通过、5条既有Swig警告（4.68s，退出码0）。免费GLM-5.3耗尽后，新任务明确选Start Plan免费Flash接续证据；该任务发现并修复证据脚本Write-Output污染返回码的问题，实际重跑通过，不以旧汇总替代新证据。

首次启动记录有两次失败：Codex日志收集使用相对路径，被脚本Push-Location影响，改绝对路径后恢复；后端健康200但归属校验拒绝播种。后者是本机Windows venv重定向器创建基础Python子进程，子进程路径不包含.venv/Scripts。用自有短命Python探针实查父/子命令确认，未查询其他用户进程材料。

Codex修改Start-E2E：后端子进程校验使用本轮确切uvicorn调用（含主机和端口），同时要求根PID创建时间及命令匹配，保留子进程族和创建时间校验，不放宽为任意占用8001的进程。独立所有权函数8个模拟用例通过（新增根PID复用拒绝）。ZCode此时只整理证据，不改实现文件。

实际执行Start-E2E（URL从本地Settings内部派生为`cp_e2e_audit-20261005`，未输出凭据），创建/迁移独立库至0013，播种A/B/A2；Next15.5.25生产构建含类型检查通过。8001健康与3001首页均200；两个端口的真实监听归属校验通过。[完整启动日志](codex-startup-20261005.log)

构建确实自动追加`.next-e2e/types/**/*.ts`到tsconfig，并改写next-env；finally恢复原字节，`git diff --exit-code -- jianli/next-env.d.ts jianli/tsconfig.json`无差异。

Stop-E2E实跑退出码0，8001/3001均释放，数据库/存储保留。随后Start-E2E同run ID使用SkipBuild/SkipSeed重启成功，模式verified，A/B/A2 ID及快照SHA256与首次创建完全一致，无恢复撤回动作。[完整重启日志](codex-restart-20261005.log)

独立库计数：users3、jobs2、applications3、application_events3、notifications6、match_reports3。业务库再次只读核对：版本及六张采样表行数与前述基线逐项一致。行数校验不代表逐行内容哈希校验；脚本目标与运行日志证明本轮迁移/播种连接独立库，不宣称审计了所有业务表内容。

E2E-01环境可用，当前运行ID`audit-20261005`，前端3001/后端8001，Mock。企业页面竞态/失败回复/下载/撤回与学生补证新版仍需E2E-02/03，AI-01仍待推进；不能据环境启动完成宣布全链路目标完成。
