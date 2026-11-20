# 传智杯41：私人草稿丢弃提示真实页面验收 — 准备就绪，等待 Codex 服务

Git根 D:/jbcode/web ai/jianli。本目录只含 goal 41 的准备证据。**实际页面验收尚未执行**——按任务卡约定，收到 Codex 服务就绪指令前不执行任何页面/API 请求。

## 交付物（唯一写清单内）

| 文件 | 说明 |
| --- | --- |
| `scripts/e2e/private-recovery-notice-runner.mjs` | 独立页面验收 runner（headed Chrome + raw CDP + 真实窗口最小化隐藏/恢复 + 只读不变量核对） |
| `scripts/e2e/private-recovery-notice.test.mjs` | 参数闭合/静态安全测试 10 项（含对自有 WinForms 探针窗口的真实 ShowWindow 往返） |
| `prep/` | 本准备阶段的全部证据（raw 输出、自审、hash） |

产品前后端、旧 runner、其他任务文件零改动；36/39 后端、40 launcher 冻结未碰。

## 准备阶段验证状态（全部通过）

- 语法：`node --check` runner/test 均通过（prep-syntax-check.raw.out）
- 静态测试：10/10 pass（prep-static-tests.raw.out）——参数闭合（只认 question-chain-20261010，14 组拒绝样例）、服务/DB 固定常量（127.0.0.1:3001/8001、cp_e2e_question-chain-20261010、无 process.env/localhost）、固定文案与产品源逐字节绑定、SQL 仅 SELECT 且包在服务端 READ ONLY、marker 唯一性、导入无副作用、真实 ShowWindow 往返（MINIMIZED→RESTORED→MINIMIZED）
- 坏参数闭合：5 组非法调用全部 exit=3 且零文件写入（prep-args-closure.raw.out）
- 只读 DB 现状（prep-fixture-hash.raw.out）：growth_answer_drafts=0、student 任务=1、applications=3、已发送回复=1、match_reports=5、analysis_tasks=9、ai_usage_logs=1、notifications=10
- 实测发现：seeder 的 `normalized_snapshot_hash` 因 Python 浮点（`overallScore: 55.0`）无法在 JS 字节级复刻（0/3）→ runner 将 fixture 交叉核对降级为信息性记录，硬不变量改为 before/after 原始行文本哈希全等（任何变化必然现形）

## Codex 服务就绪后的续跑方式（同任务续跑）

1. 按既有流程以 `question-chain-20261010` 启动 3001/8001（升级前端 stage 就绪后）。
2. 运行：`node scripts/e2e/private-recovery-notice-runner.mjs --run question-chain-20261010`
   - 只接受该参数；服务/端口/DB 全部固定常量，无 CLI 覆盖。
   - 服务未就绪时健康检查失败 → exit 2（blocked），不执行页面操作。
   - 退出码：0 全过 / 1 fail / 2 blocked / 3 参数非法。
3. 证据落在 `docs/evidence/20261011-GLM-goal41/page-run-<stamp>/`（results.json + 截图 + invariants-*.json + network-log.json）。浏览器 profile 在被忽略的 `backend/.tmp/e2e-browser/question-chain-20261010-private-recovery/`。

## runner 页面流程（对应任务卡“页面步骤”）

0. 预检：前端/后端健康、端口归属、只读 DB 身份核对、before 不变量快照。
1. 前置（因当前库中 0 草稿）：**真实 UI 保存**一条前置已保存文本（非 marker，唯一一次 PUT），之后作为“服务器原草稿”，终态只读核对版本与正文摘要不变。
2. 步骤1 读取已保存草稿（textarea=服务器版本 + 常驻警告在）。
3. 步骤2 未编辑真实隐藏/恢复：中段捕获“已清除+清洁文案、无丢弃声明”，恢复后不谎报丢弃。
4. 步骤3 输入一次性 marker（PRIVREC41-…）→ 真实隐藏（中段：文字已清+固定丢弃文案）→ 真实恢复：文字恢复服务器版本、丢弃提示读取中（尽力捕获，观察不到如实记 info）与成功后保持可见。
5. 步骤4 重复隐藏：中段同时出现清洁 status 文案与被保留的丢弃 alert（38号修复），恢复后提示仍在。
6. 步骤5 再次编辑 → 提示结束；重读恢复服务器版本。
7. 步骤6 读取失败路径：marker 输入→隐藏→浏览器级真断网→恢复→读取失败（错误提示+丢弃提示保持+文字已清）→ 联网重读成功且提示仍在；观察不到则记 blocked=未验，不伪造。
8. 步骤7 严格 390px 关键路径重复（marker→隐藏→恢复→提示在→文字恢复）+ 横向溢出三判据 + DOM/输入值/localStorage/sessionStorage/cookie 全量 marker 泄露扫描（必须 0）。
9. 终态：全程 PUT 计数必须为 1（仅前置种子）；after 不变量比对（草稿行/三投递逐行/原始文本/回复摘要/8 表计数）。

## 红线遵守

- 不启动/停止服务、不迁移/seed、不真实模型、不安装、不外发、不动 .env、不 P2、不 Git 提交推送。
- 准备阶段未执行任何页面/API 请求（仅静态测试与只读 SQL/JSON 复刻）。
- 隐藏=真实 OS 最小化+页面自报 hidden 双验证；不发合成 visibilitychange、不注入组件状态、不伪造事件。
- 合成凭证/cookie 内存脱敏；密码不打印；marker 非机密但终态必须清零。

## 交棒

Runner/测试/证据就绪，一屏交棒：**等待 Codex 恢复服务后再续跑页面验收**（服务就绪指令下达前不运行 runner）。hash 见 `prep/hashes.sha256`，自审与已知局限见 `prep/self-review.md`。
