# CareerProof Backend

当前目标 Provider 为 DeepSeek 官方 API：`AI_PROVIDER=deepseek`，Key 使用 `DEEPSEEK_API_KEY`，成本保护只允许 `deepseek-flash`。详见 [DeepSeek 官方 API 接入](../docs/guides/AI与数据边界.md) 与 [AI 用量和隐私控制](../docs/guides/AI与数据边界.md)。普通自动测试使用合成响应，不消耗 API 额度。

「职证 CareerProof」的 FastAPI 后端。当前完成真实岗位、学生材料上传与版本历史、
私有匹配报告、失败重试和岗位分类筛选。正常产品环境配置DeepSeek；规则负责检索候选证据和限制评级边界。
学生未同意向外部AI发送材料时，仍可生成本地规则报告，不调用外部模型；明确同意后，
DeepSeek逐项解释候选证据、返回引用和材料缺口，调用或校验失败时自动保留本地兜底报告。

## 架构边界

```text
API -> Services -> Repositories -> PostgreSQL
               -> Agent -> Tools / AIProvider
```

- API 只负责 HTTP 输入输出。
- Service 负责权限、事务与业务流程。
- Repository 封装常用数据库查询；目前部分服务内仍有显式查询和事务。
- Agent 不直接操作数据库。
- Tools 不执行上传的用户代码。
- 当前评分由确定性规则计算；`aiConfidence` 只表示模型解释置信度，不能替代证据校验。

## DeepSeek 证据分析

API Key仅写入本地 `.env`。`.env.example` 不包含Key；完成连通测试后，本地产品启动必须设置：

```dotenv
AI_PROVIDER=deepseek
AI_EXTERNAL_ENABLED=true
DEEPSEEK_API_KEY=仅在本机填写
DEEPSEEK_BASE_URL=https://api.deepseek.com
DEEPSEEK_MODEL=deepseek-flash
AI_PER_REPORT_OUTPUT_TOKEN_LIMIT=4000
AI_DAILY_REPORT_LIMIT=20
AI_LOCAL_FALLBACK_ENABLED=true
```

可选的模型连通检查如下：它会向官方API发送合成材料并可能收费，须另行获得对应授权；不是安装或启动的必经步骤。

```powershell
.\.venv\Scripts\python.exe -m app.scripts.check_deepseek
```

脚本使用合成的岗位要求和证据片段，只输出模型名、要求数、引用数、token 与延迟，不打印
Key 或模型正文。正式分析发送岗位要求、规则判定、相关简历声明（最多 500 字）与每项最多三条候选证据片段。
片段保留完整函数上下文，每条最多 40 行、4000 字符；不单独发送账户身份字段或文件哈希。
材料解析会遮盖常见联系方式，但任意源代码或声明仍可能含个人信息，脱敏并非完备保证，演示仅使用合成材料。
模型返回要求编号、解释、引用编号、
信息缺口、建议和置信度；后端拒绝跨要求引用、不存在的引用和越过规则边界的输出。

## 本地启动

要求 Python 3.12 与 Docker。以下是开发者手动启动方式，命令在 PowerShell 的 `backend` 目录执行；日常双击启动按[使用与启动](../docs/guides/使用与启动.md)，不要同时运行两套服务。
已有 `.env` 时不要覆盖；只需检查新增配置，未填写的任务配置使用默认值。新机器复制模板后，先按上面的配置节填写本机Key并核对DATABASE_URL，再执行连接数据库/迁移和启动命令；模板不是可直接外发的凭据。

```powershell
if (!(Test-Path .env)) { Copy-Item .env.example .env }
docker compose up -d --wait postgres
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -e ".[dev]"
.\.venv\Scripts\alembic.exe upgrade head
.\.venv\Scripts\uvicorn.exe app.main:app --reload --port 8000
```

接口文档：<http://127.0.0.1:8000/docs>

健康检查：<http://127.0.0.1:8000/api/v1/health>

## 验证

在后端目录运行。下例使用已经通过锁定版本核验的升级环境；新机器请先按上面的安装步骤
建立环境，并用所选环境的Python运行 `-m evals.verify_dependency_environment`，不要使用未同步依赖的旧 `.venv`。
启动器会依次校验候选环境并跳过不匹配者；手动测试也必须使用通过校验的环境。
若系统临时目录受限，可给pytest加 `--basetemp=.tmp-pytest-local`，只使用本轮专属且可重建的目录；
涉及子进程读取TEMP的检查，还需将TMP/TEMP指向仓库内另一个专属临时目录。环境错误仍需记录并修复后复跑，不计作通过。

```powershell
.\.venv-dependency23\Scripts\ruff.exe check .
.\.venv-dependency23\Scripts\python.exe -m pytest -p no:cacheprovider
.\.venv-dependency23\Scripts\alembic.exe check
```

`alembic check` 会连接当前配置数据库，仅在明确选定的本地库执行。
隔离验证必须在该命令的子进程环境中显式设置 `DATABASE_URL`，并先核对目标主机、端口和库名。
本项目不支持 `-x dburl=...` 等自定义选择参数；提供 `-x` 会在创建数据库引擎前报错，不能把它当作隔离方式。
生产环境必须设置
`APP_ENV=production` 和至少32字符的私有随机 `JWT_SECRET`，默认值和示例占位符会被拒绝。
生产模式强制关闭 Debug，`/docs`、`/redoc`、`/openapi.json` 不开放；开发与测试模式仍可用。

## 主要接口

```text
POST /api/v1/auth/register
POST /api/v1/auth/login
POST /api/v1/auth/refresh
POST /api/v1/auth/logout
GET  /api/v1/users/me

GET  /api/v1/enterprises/me
POST /api/v1/enterprises
GET  /api/v1/jobs
GET  /api/v1/jobs/options
GET  /api/v1/jobs/mine
POST /api/v1/jobs
GET  /api/v1/jobs/{job_id}
PATCH /api/v1/jobs/{job_id}

POST /api/v1/resumes
GET  /api/v1/resumes
GET  /api/v1/resumes/{resume_id}/versions
POST /api/v1/projects
GET  /api/v1/projects
GET  /api/v1/projects/{project_id}/versions
POST /api/v1/projects/{project_id}/versions
GET  /api/v1/resume-versions/{version_id}/preview
GET  /api/v1/project-versions/{version_id}/files
GET  /api/v1/project-files/{file_id}
GET  /api/v1/knowledge/search?q=FastAPI

POST /api/v1/matches
GET  /api/v1/analysis-tasks/{task_id}
GET  /api/v1/analysis-tasks/{task_id}/events
POST /api/v1/analysis-tasks/{task_id}/retry
GET  /api/v1/match-reports
GET  /api/v1/match-reports/{report_id}
PATCH /api/v1/match-reports/{report_id}/items/{requirement_id}/review
```

`POST /matches` 返回 `202 Accepted` 与 `taskId`。前端可以轮询任务状态，或使用
SSE 接收任务事件。

请求只提交 `jobId`、`resumeVersionId`、`projectVersionIds`，身份取自登录用户，
文件内容从服务端已上传版本读取；不能再使用前端模拟的简历正文或项目快照创建报告。
简历必选，项目最多 10 个版本，必须属于本人且解析完成。

`GET /applications/mine`、`GET /jobs/{job_id}/applications`、`GET /growth-tasks`、`GET /match-reports` 的 `data` 均为 `{items,total,page,pageSize}`，不再返回裸数组。`page>=1`、`pageSize=1..100`（默认20），越界页回退到末页、空集为第1页，按创建时间和ID降序。学生投递列表可用 `jobId` 在本人归属内先过滤再分页；补证任务另含本页 `unavailableCount`，总数仍包含不可读的已保存记录。通知使用 `pageSize`（默认20、上限50），兼容旧 `page_size`，两者冲突返回422。更新调用脚本时同步读取 `data.items`，不要用当前页条数推断总数。

岗位支持方向、城市、工作类型、关键词与分页。公开列表只展示已发布岗位；企业负责人/HR
管理所属组织的岗位。已产生匹配历史的岗位不能直接替换能力要求，应新建岗位。

报告保存当次岗位要求与材料版本快照。证据关联 `project_files → evidence_sources →
skill_evidence → match_items`，包含文件哈希、版本与行号。后续上传新版本不覆盖旧报告。
学生只看到自己的材料、任务与报告。企业不能自动读取学生私有报告；学生逐份明确投递后，企业仅通过本岗位授权入口读取投递时固定报告与引用，下载该版本简历。撤回后拒绝后续访问，已下载副本无法追回。

## 评分范围与限制

- `evidence-v3` 计算材料支持度：强证据 65、中等 40、仅依赖/配置 15、仅简历声明 10；当前补充 FastAPI、PostgreSQL 和 pytest 的可追溯规则。
- README、TODO、注释不是已实现的功能证据；高级能力要求另有限制，代码片段不证明熟练度。
- 未支持的技能返回 `unsupported` 和空分数，不参与分母；不等于用户缺少该能力。
- 非计算机方向先支持「活动策划、用户调研、内容运营」文档结构核查，不能证明执行效果或原创性。
- 分数不是能力认证、录用概率或自动淘汰依据。规则尚有漏检/误检，需要人工核验。

## 材料历史与幂等提交

历史查询使用迁移 `0002_portfolio_history`；`0003_real_matching` 包含岗位筛选、任务租期和
报告快照，`0004_ai_evidence_analysis` 保存报告级模型、降级和用量元数据。升级使用
`alembic upgrade head`，保留原有材料；
原来没有保存的文件名和任务关联保持为空，不按时间猜测或重新关联。

材料列表只返回当前学生自己的记录，列表内包含全部版本和关联任务状态。
访问他人的版本列表或向他人项目上传返回404，企业账号访问个人材料接口返回403。

`POST /projects` 的JSON可携带UUID类型的 `requestId`。同一学生重复提交相同编号和内容时
返回同一个项目；编号相同但内容不同返回409。唯一约束负责处理并发请求，不限制合法的同名项目。

`POST /projects/{id}/versions` 的表单可携带UUID类型的 `requestId`。同一项目重复上传相同编号
和文件内容时返回原版本及任务，不重复扫描；更换内容返回409。创建新版本需新的请求编号。
PostgreSQL对项目行加锁来串行分配版本号。旧客户端不传编号仍可调用，但不享有重复请求保护。

相同匹配输入只在任务排队/运行时合并；已完成后重新提交会生成新的报告，不是永久幂等键。

测试：安装 `.[dev]` 后运行 `pytest`。默认在临时 SQLite 中测试，不接触开发材料。
`test_real_matching.py` 另支持 `CAREERPROOF_TEST_DATABASE_URL`（asyncpg URL）：在随机命名的
`cp_test_*` schema 中创建测试表并清理该 schema，不改 `public` 业务表。不要使用生产库测试，
也不要在日志、公开仓库或命令截图中暴露数据库密码。

本地检索在材料解析时按可追溯行号切块，优先用本地 MiniLM ONNX 模型生成384维向量；
模型不可用时回退为 `local-hash-v1-384`，并保存实际嵌入引擎。它不调用外部API。
`GET /knowledge/search` 只检索当前登录学生自己的材料。已有材料可用
`python -m app.scripts.reindex_knowledge` 重建派生索引；0012迁移改变向量维度并清空旧派生索引，
从旧版本升级后需显式重建并核对本人材料的查询结果，不能把迁移成功当成检索就绪。

真实报告另有可选的本地 ONNX 语义检索，它只给项目文档补充低强度候选，和上述
上述知识库索引是两条不同路径。新环境需显式运行
`python -m app.scripts.download_semantic_model` 安装约 235 MB 的固定版本权重；
未安装或推理失败时自动保留词法检索与规则报告。运行
`python -m app.scripts.evaluate_semantic_retrieval` 可复核四个固定小例。
详见 本地语义文档检索验收（历史记录保留在开发仓库）。

固定规则评测：`python evals/run_rule_baseline.py --output evals/baseline-evidence-v3.json`。

固定64例合成检索对照：`python -m evals.run_offline_retrieval_comparison --semantic --output evals/retrieval-new-run.json`。不调用外部API、不自动下载权重、不覆盖输出；独立人工标注尚待完成。结果区分文档范围、宏/微Recall@2和无目标时返回候选，召回不表示实现成立。详见评测边界与复现（历史记录保留在开发仓库）。原`run_retrieval_comparison`是真实DeepSeek三组对照入口，需要显式`--live`并产生API费用。

固定 AI 评测：启用合成数据可用的真实 Provider 后，运行
`python -m evals.run_ai_evidence_baseline --output evals/baseline-ai-evidence-deepseek-YYYY-MM-DD.json`。
自动化测试由 `app/tests/conftest.py` 强制隔离真实 Provider，不消耗模型额度。

## 当前限制

- HTTP 请求仍使用 `BackgroundTasks` 快速提交；数据库扫描器会在进程恢复后接手 pending 任务。
  解析在独立子进程进行，有限并发、硬超时、运行令牌和心跳；已失去租期的 running 任务
  会安全转为失败并由用户重试，不会接受迟到结果。
  详见 [材料任务说明](docs/material-processing.md)。
- ZIP 上限 30 MB，PDF/DOCX/TXT 上限 10 MB；扫描 PDF 和常见图片可使用本地 RapidOCR，低置信度文字仍需人工核对。
- PDF 的 OCR 另有独立预算：默认最多对10个未提取到文字的页面尝试 OCR，并非只扫描 PDF 的前10页；达到预算后的无文字页不再识别，文字页仍正常提取。`OCR_MAX_PAGES` 可设置为1–50，使用较长扫描件时须核对实际解析范围。
- 单页 OCR 渲染像素默认上限20,000,000（20MP），`OCR_MAX_IMAGE_PIXELS` 可设置为1,000,000–50,000,000。超限在分配位图前返回错误码4026，渲染后仍保留复核。此限制不等于10MB文件限制；应缩小超大页面尺寸或提供文字版 PDF，单纯压缩文件大小未必有效。扫描图片的限制以对应图片解析路径为准，不将 PDF 单页预算套用于所有格式。
- 规则覆盖有限，分类入口不代表每个专业都具备完整评价器。
- 当前是规则、词法与可选本地语义文档候选组成的受控生成闭环，不宣称通用向量 RAG；语音
  企业投递授权、候选人对照、站内回复和通知中心已接线；在线面试和SMTP邮件尚未实现。截图观察已使用同一DeepSeek Key完成一次合成图片真实验收，区域定位及语义准确性仍待独立人工核验。

## 安全策略

- 密码使用 Argon2 摘要。
- Access Token 与 Refresh Token 使用 HttpOnly Cookie。
- Refresh Token 轮换并在数据库保存 JTI 摘要。
- 压缩包扫描限制大小、文件数量、路径穿越和符号链接。
- 默认只做静态文本分析，不执行任何上传代码。
- 数据库只保存相对 `storage_key`，不保存本机绝对路径。

## 本机只读 MCP

可选依赖：`python -m pip install -e ".[mcp]"`。官方SDK stdio服务的启动入口是 `python -m app.mcp_server`。学生报告页可显式授权当前报告及上一份同岗位报告，签发十分钟专用令牌；只放入本机子进程环境变量 `CAREERPROOF_MCP_TOKEN`，不要提交或分享。支持三个只读工具，作用域、40次上限、独立审计与撤销在后端再次校验。没有模型消费，不是远程OAuth服务。详见[受控MCP使用与验收](../docs/guides/工具与接入.md)。

## 登录尝试限制（0020）

升级到 `0020_login_limits` 后，公开 `POST /auth/login` 在密码校验前通过数据库原子准入。默认同一邮箱与来源5次/300秒，同一来源120次/60秒；成功登录与会话签发同事务清除组合计数，总来源计数保留。失败、进程退出及服务重启不会回滚已提交的准入，窗口到期自动恢复；不豁免演示账号，也不写 `users.is_active`。触发时返回429、业务码4293和 `Retry-After` 秒数，限流数据库故障返回503而不绕过。合法请求计数，不是仅在密码错误后计数；已经触发限制时正确密码也须等待短时窗口。

可通过 `LOGIN_PAIR_LIMIT`、`LOGIN_PAIR_WINDOW_SECONDS`、`LOGIN_SOURCE_LIMIT`、`LOGIN_SOURCE_WINDOW_SECONDS` 在配置校验范围内调整。表仅保存作用域、HMAC键、计数和到期秒数；到期记录在后续准入时分批清理。HMAC以服务的JWT密钥派生，密钥轮换会改变桶身份。IPv4按单地址，IPv6归并/64，缺失或非法来源进入共享unknown桶。不基于邮箱全局封锁，分布式换来源攻击、注册接口和整个站点的容量保护仍需另外评估。

应用不自行解析XFF；项目Local/E2E/Docker入口显式使用 `--no-proxy-headers`，独立启动也应使用该参数。将来接反向代理时须重新核对明确的可信代理范围与实际客户端来源；不能直接信任任意转发头。共享NAT/反代仍可能共享来源总额，不把本地演示配置当公网部署配置。
