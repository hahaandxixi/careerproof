# 补验SQLite套件中的PG专属跳过项（2026-10-19）

实际测试源码dece154，Python 3.12.14/.venv-dependency23；前后源码哈希一致，未改业务代码、依赖、权限或正常服务。不是冻结候选、全量PG套件或远端CI通过。

## 选择依据与结果

从10/19完整SQLite JUnit的74条PG跳过记录提取真实node ID。检索4条和上传并发3条已有10/18独立PG结果，测试文件hash完全相同；retrieval.py亦与原PG记录hash一致，portfolio service/repository相对原基线33ba713无diff，因此本轮不重复7条。其余67条分组运行：

- cp_ci：59通过，0失败/错误/跳过，62.68秒。
- 硬停专属careerproof：8通过，0失败/错误/跳过，26.61秒；匹配/企业核验两链各四个真实子进程硬停窗口。只终止夹具创建的子进程。
- 各组5条既有SWIG/依赖弃用警告保留；目标runner Ruff通过。

覆盖预算生产入口并发、AI请求/共享预算迁移、投递重授权与重投、企业核验、授权访问、数据完整性、durable尝试/匹配、成长回答/目标、知识索引、登录限流迁移与锁、MCP隔离、通知、分页、刷新原子性与图像并发。精确模块/用例在selected-nodes.json与两份JUnit，不扩大为未运行的同模块全部用例。

原1404 SQLite通过和这67 PG通过是不同环境/不同进程，不拼成同一候选一次全量通过；此前7 PG亦独立标注来源。

## 隔离与恢复

专属容器cp-skips-20261019，镜像本机已有pgvector/pgvector:pg17，使用--pull=never；固定镜像ID与容器身份/标签、端口保存在container-identity.txt。仅绑定127.0.0.1:55436，不用5432业务库，无宿主数据目录挂载。ci/ci仅为该一次性合成实例的临时测试凭据。两座测试库均启用vector，夹具独占cp_test_*命名空间。

APP_ENV=test、AI_PROVIDER=mock、AI_EXTERNAL_ENABLED=false；默认DATABASE_URL指向本轮独占SQLite文件以防误用全局引擎。只有CAREERPROOF_TEST_DATABASE_URL连接专属55436。硬停临时材料位于backend/.tmp-pg-skips-*，符合既有子进程守卫；未为测试放宽路径或数据库校验。所有模型传输为测试模拟，不消耗已用满的真实三例批次。

初次pg_isready返回no response，是新容器尚在初始化；同一容器随后accepting，不因探测未就绪重建。全部测试后两库cp_test_*残留均0；核对容器完整ID和所有权标签后停止，--rm删除专属容器。正常backend-postgres-1保持运行；只读前后39张公共表的行数/内容digest及0020版本完全相同。

## 运行与证据

backend目录运行 `.venv-dependency23/Scripts/python.exe ../docs/evidence/20261019-postgres-skipped-coverage/run_remaining.py`。runner只读取旧JUnit选择上述节点，使用明确解释器、子进程环境和列表参数；命令、完整日志、JUnit、退出码和源码前后hash分别落盘。不是调用网站或使用真实材料。runner不可在原证据路径覆盖重跑；若将来源码变化需要新run与新的授权隔离环境。

仍未验：候选冻结后的完整适用检查/新装复现、真实AI语义与首次独立用户、hidden/reduced-motion、82号岗位发现接入、最终材料/许可/评审访问。PG通过不代这些门槛。
