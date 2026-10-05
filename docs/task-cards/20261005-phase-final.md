# PHASE-FINAL：最终当前源码全量回归

Git根D:\jbcode\web ai\jianli，当前HEAD f96bca2；SEED-02已提交edf4bd5。原phase-postgres939/153基线已审计；新增夹具身份回归后再做阶段全量。本任务只读产品与测试，仅写docs/evidence/20261005-phase-final/及D:/jbcode/tmp/pytest-phase-final-20261005。学生个人GLM任务独占closure浏览器/数据/runner，不能触碰。

采用20261005-phase-postgres.md相同夹具隔离和命令，但换本任务新临时目录和证据目录：backend pytest app/tests全量、Ruff check app evals；前端npm test及tsc顺序执行；另运行node --test scripts/e2e/runner-input.test.mjs（学生runner测试待其交棒，由Codex独立执行，不并发读半成品）。完整脱敏输出、真实退出码、计数/跳过原因落文件。

仅显式本机PG测试入口CAREERPROOF_TEST_DATABASE_URL=postgresql+asyncpg://careerproof:careerproof@127.0.0.1:5432/careerproof；每例自有cp_test随机schema。不写public业务表或cp_e2e库，不清理别人的孤儿schema。强制Mock/外发关闭，不改.env。测试前后记录所有当前产品差异文件及本轮测试的哈希，若测试期间源码变化，说明不采信该次基线，勿擅自修代码。

生产构建closure已通过且前端产品源码未变，本任务不重复构建、不写.next-e2e、不重启服务。类型检查前确认无build。失败只定位、保存证据并交棒，不修改测试期望或产品。无浏览器/凭据、真实模型/外发、安装、Git写入、P2stash或正式文档变更；完成限一屏回报。
