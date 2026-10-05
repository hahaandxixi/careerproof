# PHASE-PG：当前源码全量回归

HEAD76dfd59；当前未提交岗位选择协议、0014迁移及前端已经落盘。只读产品、测试及其他证据；本任务仅写`docs/evidence/20261005-phase-postgres/`，测试临时文件可写`D:/jbcode/tmp/pytest-phase-pg-20261005`。

1. 先记录HEAD、status和本次测试实际源码文件hash；核对测试夹具强制Mock/禁止外部AI，以及PG只创建自有随机cp_test_* schema。
2. PostgreSQL仅localhost:5432已有Docker服务、careerproof测试入口；子进程设置CAREERPROOF_TEST_DATABASE_URL为postgresql+asyncpg://careerproof:careerproof@127.0.0.1:5432/careerproof，不要改.env。测试夹具隔离schema，不写public/业务表或cp_e2e_closure-20261005。
3. backend/.venv/Scripts/python.exe -m pytest app/tests -q -rs -p no:cacheprovider --basetemp=D:/jbcode/tmp/pytest-phase-pg-20261005；保存完整UTF8输出、真实EXIT和计数/跳过原因。
4. 后端Ruff check app evals；前端npm test全量及tsc --noEmit --incremental false顺序执行。生产构建已由Codex重建通过，不重复构建，不写.next-e2e，不重启服务。类型检查开始前确认无构建在运行。
5. 允许适用只读review-agent自审证据；失败不改产品或测试期望，报告最小定位及受影响项。工具权限错误不计业务失败/通过，不换通道绕过审批。
6. 不访问浏览器或E2E夹具/凭据，不调用真实模型，不外发、不安装、Git只读、不动stash或正式文档。全部结果在本目录README起草，一屏交棒。它与学生浏览器任务并行，但拥有不同数据和文件。
