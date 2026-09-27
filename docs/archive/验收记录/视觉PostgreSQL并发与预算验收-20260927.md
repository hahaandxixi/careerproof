# 视觉 PostgreSQL 并发与预算验收

日期：2026-09-27。范围：真实 PostgreSQL 的账户行锁、锁后缓存复检与每日预算。模型为合成替身，未发送 DeepSeek 请求，不消耗 API；不代表真实供应商并发或浏览器上传链路验收。

## 验收场景

| 场景 | 实际结果 |
| --- | --- |
| 同一学生同时分析同一图片版本 | 第二请求等待第一请求账户锁；两请求均 200，结果 ID 相同；只调用一次合成模型、保存一条观察和一条用量记录 |
| 同一学生同时分析两张不同像素的图片，每日上限为 1 | 第二请求等待账户锁；第一请求 200，第二请求 429；只调用一次合成模型、保存一条观察和一条用量记录 |

不是仅检查请求耗时：测试记录两个真实请求连接的 PostgreSQL PID，第三连接清除统计快照后，通过 `wait_event_type='Lock'` 与 `pg_blocking_pids` 验证第二连接确实被第一连接阻塞。探针不使用可能滞后的 SQL query 文本，也不把无关连接等待算作成功。

合成模型在第一请求持锁期间等待受控事件，探针确认后才释放。预算服务本身仍执行真实账户锁与数据库用量统计；包装器只记录 PID。上限仅在临时测试配置中设为 1，未改变运行中项目的预算。

## 隔离与复现

测试复用 `test_real_matching.matching_db`：默认 SQLite；明确配置 `CAREERPROOF_TEST_DATABASE_URL` 才创建真实 PostgreSQL 的独立 `cp_test_<32位十六进制>` schema。仅清理本次生成且通过正则检查的 schema；测试账号、图片、任务与用量不进入生产表，原图写入临时目录。

从项目根目录进入 backend 后，可用以下 Python 调用（不打印或保存数据库凭据）：

```python
import os, subprocess, sys, tempfile, uuid
from sqlalchemy.engine import make_url
from app.core.config import settings
assert make_url(settings.database_url).host in {'127.0.0.1', 'localhost'}
os.environ['CAREERPROOF_TEST_DATABASE_URL'] = settings.database_url
base = os.path.join(tempfile.gettempdir(), 'cp-visual-pg-' + uuid.uuid4().hex)
raise SystemExit(subprocess.call([
    sys.executable, '-m', 'pytest',
    'app/tests/test_visual_postgres_concurrency.py',
    'app/tests/test_visual_evidence.py', '-q', '-p', 'no:cacheprovider',
    '--basetemp', base,
]))
```

在 backend 的虚拟环境 Python 中执行，并确保本地 PostgreSQL 可连接。未配置真实数据库时，新增两例明确跳过；跳过不能记为验收通过。

## 检查结果

- 真实 PostgreSQL 视觉专项：34 项通过，7.87 秒，5 条第三方警告；包含两例实际锁等待观测与已有 32 项视觉安全检查。
- 默认离线完整后端：451 项通过、2 项跳过，56.24 秒，6 条第三方警告；跳过的是上述需显式 PostgreSQL 配置的两例，已在独立真实数据库专项执行。
- 后端 Ruff 静态检查通过。没有前端改动，本轮未重复前端构建。
- 测试使用合成用量 17 输入 / 13 输出 Tokens，用于核对数据库记录，不是供应商计费数据。

## 尚未证明

真实 DeepSeek 网络请求的并发行为、跨账户压力容量、生产截图完整浏览器点击、估计区域准确度与项目外语义复核仍单列。MCP 的锁等待验收与本次视觉锁验收分别记录；两者不相互替代。
