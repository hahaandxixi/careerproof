# 开发工具及迁移模板升级签收

2026-10-10。Codex唯一环境/源码写入者，ZCode五小时窗口现场0%、个人周60%，25审查卡仅准备、未发送。本次安装仅独立backend/.venv-dependency23，旧venv/服务/业务数据保持。

pytest8.4.2→9.0.3、pytest-asyncio1.1→1.4.0联动；官方1.4.0要求pytest>=8.4,<10。pip25.0.1→26.2.1（规范化PyPI发行名，较排序26.2多一个补丁）；Mako1.4.1→1.4.2。registry.json保留Python>=3.10、依赖与非yanked文件hash。dev extra固定pytest/asyncio/pip；生产依赖明确固定Mako，避免Alembic无上界传递重新选旧版本。resolver-plan/install/editable-refresh/pip-check原输出全部保留。

python -m pip install --dry-run -e '.[dev,mcp]'解析通过，仅计划重装项目自身，无其它新包，combined-extras-plan.json/raw.out。当前4候选的GitHub reviewed公开查询均0匹配，reviewed-candidate-advisories.json；这不代表未审阅公告或所有安全风险不存在。

## 验证

- 完整新runner离线 pytest -q -ra -p no:cacheprovider --basetemp=.tmp/dep-toolchain-full-20261010：1094通过/46跳过，299.44秒。full-sqlite.raw.out列出每类PG跳过理由，不能计作成功。
- 之后新增真实Mako模板生成回归：Alembic command.revision在临时脚本目录渲染项目script.py.mako，特意没有env.py/DB URL，生成AST有效、revision/down_revision正确，未执行上传代码或连接业务库。模板/既有增长迁移/环境guard共7通过（template-target.raw.out）；该新模板测试在完整套件收集后加入，未冒称包含在1094中。
- 新pytest/asyncio下专属PG迁移/服务/生产入口及授权79通过/0跳过（pg-risk.raw.out）：test_ai_request_attempt_migration、test_ai_shared_budget_migration、test_ai_shared_budget_service、test_ai_budget_production_race、test_application_verification、test_mcp_postgres_isolation。真实0016/0017升级往返、旧账目hash/严格拒绝有数据回退、最后槽、撤回锁与MCP授权均在该范围；随机cp_test schema预检/自身清理保持，不对业务库运行Alembic。
- pip check清洁，全部生产pin验证通过(runtime-pins.json)，新测试Ruff通过。保留TestClient/httpx/anyio和合成legacyJWT短key等警告，未随升级关闭断言。

本批不等于升级后的生产页面或AI质量验收，原两链硬停程序本次未重跑；后续独立环境实际迁移/页面门槛仍必要。没有真实模型调用/外发/部署/推送，P2 stash暂停。
