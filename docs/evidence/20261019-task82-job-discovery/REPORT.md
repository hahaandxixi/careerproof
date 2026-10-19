# 传智杯82 · 岗位发现收敛与三套场景接入 — 交棒

HEAD `10b5553`（本轮未提交、未推送）。**先看第 7 节：本轮发生一次边界违规，需要 Codex 决定如何处置。**

## 1. 设计（两个显式标记，不用标题猜测）

| 字段 | 含义 | 默认 |
| --- | --- | --- |
| `jobs.is_demo` | 该岗位是精选体验样例，不是真实招聘 | `false`（企业岗位） |
| `jobs.discovery_visible` | 是否允许出现在**岗位发现**与**推荐候选** | `true` |

两者独立：可发现但非样例（正常企业岗位）、样例且可发现（三套精选）、样例且收起（旧批量合成岗位）。
`discovery_visible=false` 只影响发现/推荐，**不改 status**，原 ID、报告、投递、成长任务访问规则不变。

## 2. 修改文件与 hash（前 16 位）

| 文件 | hash | 改动 |
| --- | --- | --- |
| `backend/app/models/recruitment.py` | `cafb696729f9bb7d` | Job 新增两列（含 `server_default`） |
| `backend/alembic/versions/0021_job_discovery_flags.py`（新） | `792b69af84376c64` | **仅加列/加索引**，无数据改写 |
| `backend/app/repositories/jobs.py` | `9792c1392a074c7e` | 发现列表加 `discovery_visible` 谓词（计数与切片共用）；新增 `recommendation_candidates()` |
| `backend/app/schemas/jobs.py` | `593eeb55e84cb8d4` | `JobSummary/JobView` 增加 `isDemo`/`discoveryVisible` |
| `backend/app/services/jobs.py` | `9289de2af4ad3a57` | 透传两个字段 |
| `backend/app/services/recommendations.py` | `3e16d6aace1d60ea` | 推荐候选改用同一谓词 |
| `backend/evals/seed_demo.py` | `d5c3d5438dcd244e` | 删除"把旧样例重新置为 published"的分支；批量目录改为**显式 opt-in**（`SEED_LEGACY_DEMO_JOBS=1`） |
| `backend/scripts/import_market_scenarios.py`（新） | `1a569f458727e04b` | 默认只读计划；`--apply --confirm` 才写入；幂等 |
| `backend/app/tests/test_job_discovery_curation.py`（新） | `d433619fc9c96f1d` | 7 条反例测试 |
| `jianli/src/components/JobList.tsx` | `4c867205eadce56e` | 样例卡片轻量标注「体验样例 · 虚构企业」 |
| `jianli/src/components/JobDetailView.tsx` | `082df1603655b4a3` | 样例页集中说明（虚构、不向真实企业投递） |
| `jianli/src/lib/api/domain.ts` | `33bb62432f78fe36` | `JobSummary` 增 `isDemo?`/`discoveryVisible?` |

## 3. 红 → 绿

| 场景 | 结果 |
| --- | --- |
| 临时移除发现谓词（`repositories/jobs.py`） | **FAILED** `test_hidden_sample_is_not_counted_or_paged_while_enterprise_jobs_stay`（1 failed / 6 passed） |
| 恢复谓词 | **7 passed** |
| 与既有 `test_jobs_api.py` 合并 | **12 passed**，exit 0 |
| Ruff（9 个后端文件） | **All checks passed** |
| 前端相关测试（job 相关 3 个套件） | **42 passed** |
| 前端 `tsc --noEmit` | **exit 0** |
| 目标 lint（JobList/JobDetailView/domain） | **0 错 0 警** |

覆盖：隐藏项不计入 total、分页不漏合法企业岗位、隐藏项仍可按原 ID 读取、旧 ID 仍在企业自己的管理列表、
其他企业不能管理且已关闭岗位对非管理员 404、推荐候选不复活隐藏样例、导入计划列证据、应用幂等（第二次
`created=[]`、`hidden=[]`、总数 4 不重复）、未确认企业拒绝写入、seed 不再复活旧样例。

## 4. schema / API 影响

- 迁移 `0021`：`jobs` 加 `is_demo`(NOT NULL, default false)、`discovery_visible`(NOT NULL, default true)，
  加两个索引，无 UPDATE/DELETE。
- API：`GET /jobs`、`GET /jobs/mine`、`GET /jobs/{id}` 的 `data` 增 `isDemo`、`discoveryVisible` 两个字段
  （只增不改，旧客户端忽略即可）。发现列表语义变化：`status=published AND discovery_visible`。
- 未改：投递/报告/成长/权限协议；`JobCreate/JobUpdate` 不接受这两个字段（防企业自封"样例"）。

## 5. 导入计划与幂等结论

工具：`python -m scripts.import_market_scenarios`（**默认只读**）。
- 计划列：目标企业（须与 `demo/market-scenarios.json` 的 `companyName` 完全一致才允许写）、三个场景的
  create/update、拟收起旧岗位的 **ID + 归属依据**（"`demo/jobs.json` 目录标题精确匹配 **且** 属于目标演示企业"，
  无该证据的记录一律保留），以及所有歧义项。
- 本轮**未连正常库**（见第 7 节例外），未产出真实 ID 清单；`import-plan-no-db.json` 为无库模式输出。
- 幂等：第二次 `--apply` → `created=[]`、`updated=3`、`hidden=[]`，岗位总数不增；已有场景的 requirements 保留
  （避免解锁已被匹配历史锁定的要求）；旧岗位只 `discovery_visible=False`，`status` 保持 `published`。

## 6. 页面与 PG 未验

- **页面未验**：无浏览器驱动，未做桌面/390px 渲染；样例标注仅为组件级改动 + typecheck/lint。
  未验证：标注在窄屏不挤压标题、详情页说明不与投递入口冲突。
- **PostgreSQL 未验**（且被第 7 节污染）：迁移只在 SQLite 上验证语法；`is_demo/discovery_visible` 的
  PG 索引行为、并发下唯一性未测。

## 7. ⚠️ 边界违规（必须处置）

**发生了什么**：我用 `python -m alembic -x dburl="sqlite+aiosqlite:///…" upgrade head` 想验证迁移语法，
但 `backend/alembic/env.py:15` **忽略 `-x dburl`**，直接用 `settings.database_url`。
结果该命令**连接并升级了正常业务库** `127.0.0.1:5432/careerproof`。

**只读核查结果**（已执行，仅 SELECT）：
- `alembic_version = 0021_job_discovery_flags`（原本应为 `0020_login_limits`）；
- `jobs` 已存在 `is_demo`(bool, default false, NOT NULL)、`discovery_visible`(bool, default true, NOT NULL)；
- `jobs` 共 **36 行，`is_demo=1` 0 行、`discovery_visible=false` 0 行** —— **没有改写任何业务行**，
  发现页行为因此**未改变**（全部仍是可发现的企业岗位）。

**影响评估**：纯增列 + 默认值 + 两个索引，向后兼容；但由于代码尚未提交，库现在**领先于已提交代码**一个 revision。
若 Codex 最终采纳本迁移，无需额外操作；若不采纳，需在专属环境执行回滚。

**建议的处置（我未执行，避免第二次未授权写入）**：
```powershell
# 回滚到 0020（会删除两个索引与两列；不touch任何业务行）
.\backend\.venv-dependency23\Scripts\python.exe -m alembic downgrade 0020_login_limits
```
由 Codex 决定「保留」还是「回滚」。**这是我的操作失误**：我本应先用 `-x dburl` 是否被 env.py 采信做静态核对，
或干脆只对迁移文件做语法导入检查。

## 8. 证据

`docs/evidence/20261019-task82-job-discovery/import-plan-no-db.json`（无库模式计划输出）、本 REPORT。
测试与 lint 原始输出见本轮命令记录；未写其他文档与总账。
