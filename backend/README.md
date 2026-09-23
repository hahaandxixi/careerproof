# CareerProof Backend

当前目标 Provider 为 DeepSeek 官方 API：`AI_PROVIDER=deepseek`，Key 使用 `DEEPSEEK_API_KEY`，成本保护只允许 `deepseek-flash`。详见 [DeepSeek 官方 API 接入](../docs/DeepSeek官方API接入.md) 与 [AI 用量和隐私控制](../docs/AI用量与隐私控制.md)。普通自动测试使用合成响应，不消耗 API 额度。

「职证 CareerProof」的 FastAPI 后端。当前完成真实岗位、学生材料上传与版本历史、
私有匹配报告、失败重试和岗位分类筛选。产品运行时必须启用DeepSeek；规则负责检索候选证据和限制评级边界，
DeepSeek逐项解释候选证据、返回引用和材料缺口，调用或校验失败时才自动保留本地兜底报告。

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

用不含真实个人信息的合成请求检查连接：

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

要求 Python 3.12 与 Docker。以下命令在 PowerShell 的 `backend` 目录执行。
已有 `.env` 时不要覆盖；只需检查新增配置，未填写的任务配置使用默认值。

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

```powershell
.\.venv\Scripts\ruff.exe check .
.\.venv\Scripts\pytest.exe
.\.venv\Scripts\alembic.exe check
```

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

岗位支持方向、城市、工作类型、关键词与分页。公开列表只展示已发布岗位；企业负责人/HR
管理所属组织的岗位。已产生匹配历史的岗位不能直接替换能力要求，应新建岗位。

报告保存当次岗位要求与材料版本快照。证据关联 `project_files → evidence_sources →
skill_evidence → match_items`，包含文件哈希、版本与行号。后续上传新版本不覆盖旧报告。
学生只看到自己的材料、任务与报告；企业不能自动读取学生报告，投递授权流程尚未开放。

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

本地检索在材料解析时按可追溯行号切块，使用 `local-hash-v1` 生成 1024 维确定性向量并写入
pgvector；它不调用外部模型。`GET /knowledge/search` 只检索当前登录学生自己的材料。
已有材料可用 `python -m app.scripts.reindex_knowledge` 重建派生索引。

真实报告另有可选的本地 ONNX 语义检索，它只给项目文档补充低强度候选，和上述
`local-hash-v1` 数据库索引是两条不同路径。新环境需显式运行
`python -m app.scripts.download_semantic_model` 安装约 235 MB 的固定版本权重；
未安装或推理失败时自动保留词法检索与规则报告。运行
`python -m app.scripts.evaluate_semantic_retrieval` 可复核四个固定小例。
详见 [本地语义文档检索验收](../docs/本地语义文档检索验收-20260923.md)。

固定规则评测：`python evals/run_rule_baseline.py --output evals/baseline-evidence-v3.json`。

固定 AI 评测：启用合成数据可用的真实 Provider 后，运行
`python -m evals.run_ai_evidence_baseline --output evals/baseline-ai-evidence-qwen-plus-YYYY-MM-DD.json`。
自动化测试由 `app/tests/conftest.py` 强制隔离真实 Provider，不消耗模型额度。

## 当前限制

- HTTP 请求仍使用 `BackgroundTasks` 快速提交；数据库扫描器会在进程恢复后接手 pending 任务。
  解析在独立子进程进行，有限并发、硬超时、运行令牌和心跳；已失去租期的 running 任务
  会安全转为失败并由用户重试，不会接受迟到结果。
  详见 [材料任务说明](docs/material-processing.md)。
- ZIP 上限 30 MB，PDF/DOCX/TXT 上限 10 MB；扫描 PDF 和常见图片可使用本地 RapidOCR，低置信度文字仍需人工核对。
- 规则覆盖有限，分类入口不代表每个专业都具备完整评价器。
- 当前是规则、词法与可选本地语义文档候选组成的受控生成闭环，不宣称通用向量 RAG；语音
  面试、多模态理解及企业投递授权尚未实现。

## 安全策略

- 密码使用 Argon2 摘要。
- Access Token 与 Refresh Token 使用 HttpOnly Cookie。
- Refresh Token 轮换并在数据库保存 JTI 摘要。
- 压缩包扫描限制大小、文件数量、路径穿越和符号链接。
- 默认只做静态文本分析，不执行任何上传代码。
- 数据库只保存相对 `storage_key`，不保存本机绝对路径。
