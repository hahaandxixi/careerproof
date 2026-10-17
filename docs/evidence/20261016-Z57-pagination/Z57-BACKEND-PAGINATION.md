# Z57 · 真实列表分页后端修复 · 证据

- Git root: `D:/jbcode/web ai/jianli`
- Baseline: `89d8bed`；卡片提交 `e94be9b`（仅新增任务卡）
- 范围：仅后端分页（`backend/app/**`）；前端与最终集成为 Codex
- 原始失败日志：`backend/.tmp/z57-pytest-20261016-2350/red-01-z57-pagination.txt`
  （8 failed，保留未覆盖）

## 已实现的契约

| 端点 | 返回 | 默认 pageSize | 上限 | 排序 |
| --- | --- | --- | --- | --- |
| `GET /applications/mine` | `{items,total,page,pageSize}` | 20 | 100 | `created_at DESC, id DESC` |
| `GET /jobs/{job_id}/applications` | 同上 | 20 | 100 | 同上 |
| `GET /growth-tasks` | `GrowthTaskPage` = 上述字段 + `unavailableCount` | 20 | 100 | 同上 |
| `GET /match-reports` | `{items,total,page,pageSize}` | 20（原 50） | 100 | 同上 |
| `GET /notifications` | 原字段不变 | 20 | 50 | 原有 |

- `page >= 1` 由 Query 校验；服务层把 `page` 夹到最后一页，空集始终 `page=1`。
- 计数与数据切片使用**同一个**归属/授权/同意谓词（同一 `conditions` 列表）。
- `/applications/mine` 新增可选 `jobId`（UUID）。过滤在当前学生的查询内、计数与分页之前完成；
  无跨学生/跨企业可见性。
- `/growth-tasks`：total = 该学生 owned 保存行总数；只做有界数据库分页；
  当前页被既有窄口径漂移异常跳过的行计入 `unavailableCount`，不被静默丢弃、也不扫描历史补页。
  catch 集合未扩大（仍是 `AppError/ValidationError/KeyError`），其他异常继续抛错。
- `/notifications`：新增规范参数 `pageSize`，保留旧 `page_size`，两者都传且**不相等**时返回 422；
  相等则接受；默认 20、上限 50 不变；已读/未读归属行为未改。
- 未引入隐藏的“返回全量列表”HTTP 模式；服务方法 `mine/candidates/list/list_reports` 现在直接返回分页对象，
  没有保留 list 包装器，也没有默认值的隐式变化（除 `/match-reports` 默认 50→20，符合卡片契约）。
- 未改动任何迁移、未产生写副作用；授权/撤回/快照校验逻辑未动。

## 新增/修改文件与内容哈希（`git hash-object`）

| 文件 | blob |
| --- | --- |
| `backend/app/schemas/pagination.py`（新） | `d68419efa7d6687d2d44419f215f7c0af6c04db4` |
| `backend/app/services/applications.py` | `d5c9b1694a44819bb7d9229060c91575ef346c4e` |
| `backend/app/services/analysis.py` | `adefea3de4557e1784d8c269757ecbd1b746db6d` |
| `backend/app/services/evidence_growth.py` | `4be250f10435dd282ca9402a701c0a563a101e84` |
| `backend/app/api/v1/applications.py` | `17f9c55bcdb00aba2fc9944a42d32e5168c4b1ae` |
| `backend/app/api/v1/analysis.py` | `ba9ec5dda3fa065f1ba71012869a4ba929542d94` |
| `backend/app/api/v1/evidence_growth.py` | `d3727c537d927b58b4534cd11e4300edd065b1dc` |
| `backend/app/api/v1/notifications.py` | `83fcba9bc36c4598335de265cebec09f40fd6be3` |
| `backend/app/tests/test_z57_pagination.py`（新） | `3f643086dcccd1acf4316caf6a6728748055ac46` |
| `backend/app/tests/test_applications_api.py` | `5e1e9d077458115885aec7bb28dab78a0a049d25` |
| `backend/app/tests/test_application_resubmission.py` | `52cfd7d9c1a98904c9e3d20e8e5f723e7d09b11d` |
| `backend/app/tests/test_evidence_growth.py` | `4c65bbda90a737f3c500a3d2782e227a7cbd1ba0` |
| `backend/app/tests/test_real_matching.py` | `b4397051868138a81985c8d50acf2736bbdf0575` |

既有测试的改动仅为适配新信封（`["data"]` → `["data"]["items"]`）与
`/growth-tasks` 的 `total`/`unavailableCount` 断言；无行为放宽。

## 命令与退出码

| # | 命令（在 `backend/` 下，均使用 `.venv\Scripts\python.exe`） | 结果 |
| --- | --- | --- |
| 1 | `pytest app/tests/test_z57_pagination.py --basetemp=.tmp/z57-pytest-20261016-2350/basetemp-red -o cache_dir=.../pytest-cache-red -q` | `8 failed` / exit 1（原始失败，已保留）|
| 2 | 同上，`basetemp-green1`（实现后） | `8 passed` / exit 0 |
| 3 | `ruff check` 13 个改动文件 | 首轮 `8 errors`（F811 夹具导入），修正后 `All checks passed!` / exit 0 |
| 4 | `pytest test_z57_pagination + test_applications_api + test_application_resubmission + test_notifications + test_evidence_growth + test_real_matching` | `51 passed, 4 skipped` / exit 0 |
| 5 | `pytest test_jobs_api + test_validation_errors + test_report_history + test_growth_answer + test_growth_target_job` | `32 passed` / exit 0 |

原始输出：
`red-01-z57-pagination.txt`、`green-01-z57-pagination.txt`、`ruff-01-changed.txt`、
`ruff-02-changed.txt`、`green-02-affected.txt`、`green-03-adjacent.txt`
（均在 `backend/.tmp/z57-pytest-20261016-2350/`）。

4 个 skip 全部是需要显式隔离 PostgreSQL 的既有用例（本任务规定不连普通数据库）。

## 未验证 / 遗留

- 未做浏览器验证，未接 PostgreSQL：契约按卡片要求只在本仓库既有的隔离 SQLite 夹具上验证。
- 前端展示（`unavailableCount` 文案、`total` 导航、`jobId` 提示）由 Codex 负责；本次未改任何前端文件。
- 未提交、未推送。
- 环境说明：本会话最初为 workspace-write，PowerShell 沙箱无法在仓库内写入（`backend` 目录属主为另一 SID，
  权限修复脚本被拒绝），因此 pytest/ruff 的运行目录在获得放宽权限后创建；当前会话为 danger-full-access。
