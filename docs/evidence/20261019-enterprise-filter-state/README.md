# 2026-10-19 企业端筛选/已打开报告一致性

状态：已提交 `3024f2adb823ff674ed3de4dc9ce23901fd74c53`，正常站已加载并通过只读空结果/清除/390px 检查。四文件通过锁定依赖环境验证；隔离页面与真实组件交互通过。无真实外部模型、无 SMTP、无正常库写入、无消息发送。

## 一、审查与所有权

- Git 根：`D:\jbcode\web ai\jianli`；分支 `main`；基准 HEAD：`dac9650fef91dfce7357fddd3792613d5d172f8e`。
- 本轮四文件：
  - `jianli/src/components/ApplicationBoard.tsx`
  - `jianli/src/lib/application-comparison.ts`
  - `jianli/tests/application-comparison.test.mjs`
  - `jianli/tests/failure-reply-draft.test.mjs`
- 未覆盖：`docs/当前接力.md`、`docs/guides/使用与启动.md`、`jianli/src/components/JobDetailView.tsx` 及上一轮 backend Agent 三文件。
- 3000/8000 仍在运行既有正常站；3001/8001 由本轮在空闲端口启动，使用克隆库，不是受保护的既有 3001 环境。
- 本轮新增“当前收件人”行：隔离库中两位授权候选人显示名相同（均为 `E2E 合成学生`），发送区原有“这位投递学生”存在实际歧义。现显示姓名 + 投递编号前 8 位，仍只用既有投递对象。

## 二、锁定依赖环境

`backend/.tmp/dep-frontend-20261019-enterprise-filter`：

- `next 15.5.27`、`eslint 9.39.5`、Node v22.23.1。
- `package-lock.json` SHA256：`B95BF8852E451FCC81087EFB22CF0752E66583B3AD3CEBA804AC27AEE37CBB7C`，与仓库锁文件一致。
- 依赖目录来自既有完整 `dep-frontend-20261019-picker` 的只读 junction；未安装、升级或覆盖任何运行中依赖。
- 四文件在 staging 与仓库的 SHA256 完全一致。

## 三、验证结果

### 1. 目标测试 / 类型 / lint / 构建

```powershell
node --experimental-strip-types --test tests/application-comparison.test.mjs tests/candidate-selection.test.mjs tests/failure-reply-draft.test.mjs tests/application-anchor.test.mjs tests/skill-radar-render.test.mjs
# 28 passed, 0 failed

npm run typecheck
# exit 0

node_modules/.bin/eslint src/components/ApplicationBoard.tsx src/lib/application-comparison.ts tests/application-comparison.test.mjs tests/failure-reply-draft.test.mjs
# exit 0, 0 errors / 0 warnings

npm run build
# exit 0, Next 15.5.27; 19 pages; only既有 VisualEvidencePanel <img> warning
```

原始记录：[targeted-tests.raw.out](targeted-tests.raw.out)、[typecheck.raw.out](typecheck.raw.out)、[eslint-target.raw.json](eslint-target.raw.json)、[build.raw.out](build.raw.out)、[exit-codes.txt](exit-codes.txt)、[locked-environment.txt](locked-environment.txt)。

### 2. 真实组件交互回归（真实 ApplicationBoard，隔离 mock API）

隔离 staging 页面 `enterprise-filter-harness` 加载真实 `ApplicationBoard`；Chrome CDP 用 mock API 提供两位名称不同的合成候选人。结果：[component-interaction-result.json](component-interaction-result.json)。

- 打开 A，写入草稿。
- 关键词筛到只剩 B：A 报告仍保留，提示“A 不在筛选结果中；报告与未发送草稿不会被清空”，草稿原文仍在。
- 三项筛选同时非空后输入无匹配关键词：不渲染空表，保留打开报告与草稿。
- 点击“清除全部筛选”：关键词、岗位要求、证据状态三项全部重置，列表恢复两位候选人，草稿保留。
- 明确切换到 B：A 草稿为空，页面不残留 A 草稿文本，选中态转到 B，收件人变为 B。

该页面和 mock 仅用于组件交互回归，**不是产品路由，也不证明真实授权链**。

### 3. 隔离真实页面（两位已授权合成候选人）

- 克隆 `cp_e2e_release-core-20261012` 为 `cp_e2e_enterprise-filter-20261019`，从 0018 升级到 0021；源库未修改、未重播种。
- 岗位 `b176166e-75e3-4a89-965c-6c845652f9cd` 有两条 `submitted` 授权投递：
  - `0582cc18-3dda-4230-a468-e56ec93f0196`
  - `7e6d80dc-796f-41c7-92dd-d0463407e37c`
- 两位显示名相同，均 `E2E 合成学生`；这正好暴露了收件人歧义。
- 3001/8001 为本轮自有进程；Chrome headless 独立 profile。未操作 3000/8000，未发送回复。

结果：[real-page-result.json](real-page-result.json)。

- 桌面 1280×800：打开 A、写入草稿、切到 B；B 收件人显示 `投递编号 7e6d80dc`；A 草稿为空；选中态只落在 B。
- 输入无匹配关键词：表格隐藏，提示空结果；打开报告与草稿仍保留；点“清除全部筛选”后恢复两位候选人，关键词与两个筛选下拉均为空。
- 390×844：页面 `scrollWidth=390`，无整页横向溢出；表格自身横向滚动（448px）；空结果提示、清除按钮、收件人行均可见。
- 键盘：聚焦“清除全部筛选”，用真实 Enter 键清空关键词和两个筛选下拉，列表恢复。
- **没有在真实隔离页复验“筛选只剩 B”**：两位候选人名称、要求、分数、状态完全相同，现有筛选无法只留 B；该场景由上一节 mock 真实组件回归覆盖。

截图：[desktop-empty-filter.png](desktop-empty-filter.png)、[mobile-390-empty-filter.png](mobile-390-empty-filter.png)、[mobile-390-table.png](mobile-390-table.png)、[mobile-390-recipient.png](mobile-390-recipient.png)。

### 4. 既有闭环只读核对

正常站只读检查（非本轮页面验收）：21 个企业岗位，只有 2 个有授权投递，每岗位 1 人；两份投递的已保存 AI 核验建议均为 `null`。学生回复通知目标指向正确投递。详见 [normal-enterprise-inventory.json](normal-enterprise-inventory.json)、[normal-readonly-checks.json](normal-readonly-checks.json)。

## 四、代码改动

- `applicationFilterView`：统一输出 `visible`、`empty`、`selectedOutside`。
- `CandidateFilterNotice`：空结果与“报告在筛选外”共用；只提示/清理筛选，不清空报告或草稿。
- 空结果不再渲染空表。
- 发送区增加“当前收件人：姓名 · 投递编号前 8 位（仅发送给该投递对应学生）”。
- 新增状态/组件回归。
- 未改分页协议、后端、数据库、授权/快照、AI 提示词/模型、邮件、历史报告。

### 5. 正常站加载与验证

- 已提交 `3024f2a`；从未提交前即已通过锁定依赖验证的同一源码构建 `.next-prod`（`BACKEND_ORIGIN=http://127.0.0.1:8000`）。
- 旧 3000 进程（`dep-frontend-20261019-task82`）先记录 PID/命令行，再停止；旧构建目录保留用于回滚。新 3000 PID 404752，路径为 `backend/.tmp/dep-frontend-20261019-enterprise-filter`，dist `.next-prod`。
- 3000 返回 200；8000 `/api/v1/health` 返回 200；没有重启或改动 8000。
- 正常站只读操作：企业登录 → 有 1 条授权投递的岗位 → 输入无匹配关键词 → 空结果提示、无空表 → 点“清除全部筛选” → 关键词/两个筛选下拉重置、1 位候选人恢复；390px 页面无横向溢出。**未打开候选人报告**，避免写入正常站 viewed 事件。
- 正常站只有 1 位授权候选人，无法验证“打开 A → 筛选只剩 B”和“报告在筛选外”的真实页面状态；这两项由隔离页面与组件交互分别覆盖。

结果：[normal-page-result.json](normal-page-result.json)、[normal-3000-empty-filter.png](normal-3000-empty-filter.png)、[normal-activation.txt](normal-activation.txt)、[normal-rollback.txt](normal-rollback.txt)。

## 五、未验证 / 边界

- 正常站已加载，但因只有 1 位授权候选人，未在正常站验证多人筛选/报告切换；正常站未打开报告，未写 viewed 事件。
- 未实际发送回复；重复点击、发送失败、成功后通知、撤回后旧通知等沿用既有代码/历史证据，本轮未重跑。
- 未生成/调用 AI 核验建议；正常站两份投递无已保存建议。
- 未验证商业邮件通道；没有新增 SMTP、邮箱提取或自动外发。
- 未在正常库新增/撤回/重投任何记录；隔离克隆上的 viewed 事件属于测试。
- 组件 mock 页面不是产品路由；不能替代真实授权页面。
- 本轮不是首次独立用户验收，也不是冻结候选验收。

## 六、提交与回滚

- 代码/证据提交：`3024f2a`；仅四文件 + 本证据目录。
- 正常站旧进程与回滚路径见 [normal-rollback.txt](normal-rollback.txt)；旧构建 `backend/.tmp/dep-frontend-20261019-task82` 未删除。
- 正常站后续如出现异常，按 `normal-rollback.txt` 中的旧命令重启旧构建即可；不要清理本 staging 或旧构建目录。
- 3001/8001 隔离环境、克隆库与 Chrome profile 仍为本轮测试资源；是否保留由 Codex 按后续隔离验收需要决定，不得影响 3000/8000。
