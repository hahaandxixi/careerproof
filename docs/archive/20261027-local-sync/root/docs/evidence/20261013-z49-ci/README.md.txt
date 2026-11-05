# 传智杯49 证据：可复现CI与PostgreSQL必跑门禁（本地门禁实现）

日期：2026-10-13。基线 main/f781a5b。本目录仅含本地可验证证据；
真实 PG 服务、容器启动、远端 Actions 运行按卡由 Codex 独立执行。

## 写入清单（全部在卡片授权范围内）

| 文件 | 状态 |
| --- | --- |
| `.github/workflows/ci.yml` | 新增，三 job |
| `backend/scripts/check_ci_junit.py` | 新增，JUnit 门脚本 |
| `backend/app/tests/test_ci_junit_gate.py` | 新增，门禁反例测试（先红后绿） |
| `jianli/package.json` / `package-lock.json` | 各 +1 行：devDependency 声明 `sucrase@3.35.1`（精确 pin） |

hash 见 `hashes.txt`。

## 协议执行记录

1. **先红**：`test_ci_junit_gate.py`（18 例）在脚本未实现时运行 →
   18 failed（`red-run.log.txt`，pytest exit=1）。
2. **后绿**：实现 `check_ci_junit.py` 后同一命令 → 18 passed
   （`green-run.log.txt`，pytest exit=0）。命令均为
   `pytest app/tests/test_ci_junit_gate.py --basetemp .tmp-z49-*`。
3. **Ruff**：两个新文件与全仓 `ruff check .` 均通过（`ruff-full.log.txt`）。
4. **YAML 结构自审**（`yaml-selfcheck.log.txt`）：解析 ci.yml 并断言——
   三 job；触发 pull_request/push main/workflow_dispatch；
   permissions contents:read；concurrency cancel-in-progress；四个 action
   均为卡片指定 SHA 且 checkout persist-credentials:false；upload 均
   if:always + retention-days:7 + 路径仅 .tmp-ci 下 junit/log；PG 镜像为
   卡片 digest；strict 11 文件 env URL=cp_ci、mock 四变量、
   --basetemp=.tmp-ci-pg；hard-stop 文件 URL=/careerproof、
   --basetemp=.tmp-ci-pg-hardstop；unit CAREERPROOF_TEST_DATABASE_URL=""
   且 --junitxml；前端 npm ci→test→typecheck→build 顺序、node 22.23.1。
   （注：PyYAML 将裸 `on` 键读为布尔 True，属 YAML1.1 语义，
   GitHub Actions 解析不受影响。）
5. **锁差异**（`lock-diff.log.txt`）：`npm install --package-lock-only
   --ignore-scripts --no-audit --no-fund` 后 git diff 仅各 +1 行
   （根包 devDependencies 增加 sucrase "3.35.1"）。无其他包版本变动；
   sucrase 原传递父包为 tailwindcss（`^3.35.0`），其条目未动；
   node_modules/sucrase 既有条目版本 3.35.1 未动；未安装根 node_modules。

## JUnit 门退出码分档（check_ci_junit.py）

| 退出码 | 分档 |
| --- | --- |
| 0 | 12 模块齐、全过、hard-stop 8/8 窗口实际通过 |
| 2 | JUnit 文件缺失 |
| 3 | 格式错误（不可解析/根元素非 testsuite(s)/testcase 缺 name） |
| 4 | 空 XML（零 testcase） |
| 5 | 必跑模块无用例 |
| 6 | hard-stop 两链四窗口缺失（含用单个扁平用例冒充矩阵） |
| 7 | 存在 failure/error/skipped（skipped 的窗口也算未实际通过） |

## ⚠ 唯一偏离点（需 Codex 裁决）

卡片要求 PG 显式 URL `postgresql+asyncpg://ci:ci@127.0.0.1:5432/cp_ci`，
但 `backend/app/tests/ops_hard_stop_worker.py` 的 `validate_config`
（HEAD f781a5b）硬性要求传给子进程的 URL **数据库名字面等于
`careerproof`**，否则子进程拒绝启动、8 个 hard-stop 窗口必红。该文件
不在本卡可写范围（测试夹具）。处理：同一一次性 CI 服务容器内除 cp_ci
外另建 `careerproof` 库（ci:ci 凭据，随 job 销毁，绝非业务库），strict
集拆两次 pytest 调用：11 文件跑 cp_ci、test_attempt_hard_stop 跑
CI 内部 careerproof 库，两份 JUnit 一起喂给门脚本（多文件合并已在
反例测试 test_split_junit_files_still_exits_zero 覆盖）。

## 本地未验证（按卡留给 Codex）

- 未真实创建数据库/启动容器/服务/真实硬停；未跑 12 文件真实 PG 集。
- 未真实 npm ci / npm test / typecheck / build（frontend node_modules
  非本机新装；干净快照由 Codex 验证）。
- 未提交/推送；远端 Actions 未运行——**本地门禁实现 ≠ 远端 Actions
  已成功，也 ≠ 已设置强制合并保护**。
