# 10/18 Codex独立PG集成检查

基线HEAD：33ba713；实际测试对象是当前未提交工作区，不是干净候选提交。检索源码包含61号修复及69号版本语义纠正。80号解析器/材料预览修复不在本轮写入范围。

## 实际结果

- `test_retrieval_filtered_recall.py` 4项通过：大量更近的无关片段下，自有片段仍按精确距离返回top-k；自有不足一页、250个来源/500片段、大量干扰以及空索引边界。使用hash向量，不证明MiniLM真实语义质量。
- 新增 `test_project_upload_concurrency_postgres.py` 3项通过：两独立会话在真实锁查询前屏障同步，同项目同键同字节只创建1版本/1任务并重放；同键不同字节恰好1成功/1个4092；不同键创建版本1和2，互不覆盖。
- 合计 `7 passed`，零跳过、零失败；13.57秒。5条PyMuPDF SWIG弃用警告保留。目标新文件Ruff通过。
- 并发用例直接调用真实PortfolioService/Repository与PG，不经过HTTP、后台扫描或真实网络；HTTP顺序重试已有其他批次证据，不混称本轮浏览器/HTTP并发通过。并发起点屏障确保两个独立事务同时进入锁查询，不声称覆盖所有调度次序。

## 隔离与命令

用户从桌面启动Docker后，Codex新建一次性 `cp-verify-20261018` 容器，镜像本机已有 `pgvector/pgvector:pg17`，仅绑定127.0.0.1:55435。使用独立合成数据库和合成口令，启用vector；不读取正常连接配置、不使用5432业务库。

从backend使用明确解释器 `.venv-dependency23/Scripts/python.exe`：

```text
python -m pytest app/tests/test_retrieval_filtered_recall.py app/tests/test_project_upload_concurrency_postgres.py -q -p no:cacheprovider --basetemp=.tmp/codex-pg-20261018 --junitxml=../docs/evidence/20261018-codex-pg-integration/results.xml
python -m ruff check app/tests/test_project_upload_concurrency_postgres.py
```

CAREERPROOF_TEST_DATABASE_URL仅在本轮子进程设置到上述专属容器。两个夹具各自创建/删除随机cp_test_* schema。退出后查询遗留schema为0；容器已停止并因--rm删除，不保留测试数据。未启动/停止正常网站。

原始输出：`pg-first.raw.out`；JUnit：`results.xml`。没有修改测试断言以获得通过，无失败首跑需要修正。

测试时SHA256：retrieval.py `456130a4028dd2fc246638f8aa76ecdbedb151e78efcf42f781882c387bbac00`；61号原测试 `bac255b73aa62576a163860f3dbaa8084b0cf16cf5f7eafffdf7643577e75f6b`；新增上传并发测试 `6011aadb0cb8b258e880d171e219230370ddbe9289815a36456bb0eaf3bcb57d`。61号源码与测试尚待集成，不随本批独立测试提交冒充已入库。

## 仍未完成

这是必要的PG代表性验证，不是候选版全量门禁：未做真实语义向量、性能基准、Alembic全链、HTTP并发、真实页面、真实AI质量或最终源码包验收。61号物化自有候选的开销仍需按实际材料规模评估；本批不作性能提升承诺。

整体目标继续进行；下一步接收80号修复，统一前端运行环境与页面验收，再决定可提交的集成批次。
