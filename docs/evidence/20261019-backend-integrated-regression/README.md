# 当前集成后端完整SQLite回归（2026-10-19）

源码：26a64b9；执行前后backend无跟踪差异。未改业务源码、依赖或锁文件，不是10/26冻结候选。上次全量8项调用者失败的修复及后续解析器/检索/幂等/AI执行器改动，现经同一进程完整套件验证。

## 实际结果

- Python 3.12.14，backend/.venv-dependency23；28项生产/可选/开发精确pin均匹配，见environment.json。复用安装环境，不是全新安装。
- pytest app/tests：1404通过、0失败、0错误、74跳过；1478项，328.24秒，退出码0。JUnit与完整原始日志保留。
- 74项全部要求明确分配的隔离PostgreSQL环境，含真实行锁、跨进程硬停等；逐条原因与计数见summary.json。本轮不证明这些PG性质。10/18的PG7项仍只证明其对应范围，不拼成完整PG验收。
- Ruff app evals：退出码0，All checks passed。
- 9条warning保留：PyMuPDF SWIG元数据、Starlette/httpx/anyio弃用、旧JWT兼容测试的短密钥。未升级依赖或关闭警告以求干净。

## 隔离与命令

工作目录backend。APP_ENV=test、DEBUG=false、AI_PROVIDER=mock、AI_EXTERNAL_ENABLED=false；CAREERPROOF_TEST_DATABASE_URL为空，DATABASE_URL指向本轮独占backend/.tmp/integrated-20261019-*/unbound-app.db，STORAGE_BASE_DIR也位于该独占目录。未使用正常业务库，未启停正常服务，未实际网站模型调用。应用测试夹具继续使用各自临时数据库。命令参数原文见arguments.txt：

```text
.venv-dependency23/Scripts/python.exe -m pytest app/tests --basetemp=<独占目录>/pytest -p no:cacheprovider --junitxml=<本证据目录>/junit.xml
.venv-dependency23/Scripts/python.exe -m ruff check app evals
```

第一次PowerShell内联构造--basetemp参数有误，pytest收集前退出4；未执行测试。原始失败pytest-01-argument-failure.raw.out与退出码保留。改用显式参数数组后才执行上述完整一次，不是先失败后边改业务代码边拼接结果。

## 未覆盖

本轮不运行前端、真实浏览器、真实模型、PG、远端CI或安装验证；不替代首次独立用户、AI人工语义核对、许可、评审访问、视频人工听审与冻结交付。正常站前端仍为已有生产构建，不能将测试环境解释成重新加载网站。
