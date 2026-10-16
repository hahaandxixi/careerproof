# 传智杯56 终态报告：岗位页已有投递提示（2026-10-16）

基线 main/a45b345（git 根 D:\jbcode\web ai\jianli，git status 起始即有大量并行未跟踪 evidence 与 M docs/当前接功.md，均非本人所写、未触碰）。唯一实现写入者 ZCode；本卡交付后停止。

## 交付内容
- 新 `jianli/src/lib/job-application-status.ts`：
  - `resolveJobApplicationStatus(records, jobId)` 纯解析：仅当记录具备非空 `id`/`status` 且 `jobId` 精确匹配时才可证明状态；任何未撤回状态（含服务端未来新字面量）都算"进行中"并在同组内取 `createdAt` 最新（相同取数组靠后）；撤回与进行中并存时 active 优先；无可证明记录 → `unknown`（绝不等于"未投递"）。
  - `createJobApplicationStatusSession({api:{myApplications,errorMessage},publish})`：沿用 application-list-session 的代次票据模式——`refresh(jobId)` 同步先发布 `loading`（岗位切换立即清空上一岗位数据），仅最后一次 refresh 的响应可发布；`dispose()` 后到达的响应静默丢弃（response-after-unmount）；未 `activate()` 的会话不读不发。依赖面结构上只有只读 `myApplications`，不可能触发写/模型动作。
- `jianli/src/components/JobDetailView.tsx`（唯一修改的既有文件）：
  - 新导出无状态 `JobApplicationStatusNotice`：loading（role=status）/error（role=alert，含 message 与"重试读取"，明示"这不影响生成报告"）/unknown（渲染 null，不做任何结论）/active（复用 application-display 的 `applicationStatusText`+`applicationNextAction`，说明"生成新报告不会替换该投递"，链接 `/applications#application-<encodeURIComponent(id)>`）/withdrawn（复用"已撤回授权"文案，明示"当前没有进行中的分享"，仅留查看记录链接，无重投按钮、无授权勾选）。slate/indigo 紧凑样式。
  - MatchForm 内新增独立投递状态读取：独立 state + 独立 session + 两个 effect（activate/dispose 生命周期；`job.id` 变化即重读），与材料加载 effect/错误/重试完全解耦；提示行置于表单错误之前。身份切换沿用既有 `<MatchForm key={user?.id}>` 重挂载兜底。授权/材料选择/模型同意（externalAiConsent、usePreviousReport 默认 false）与 selected-version/query 行为零改动；既有通用 `/applications` 链接保留。
- 新测试 `jianli/tests/job-application-status.test.mjs`（11 例，真实控制器）与 `jianli/tests/job-application-status-notice.test.mjs`（7 例，sucrase+react-dom/server 渲染真实 JobDetailView.tsx 导出组件）。后者 load hook 增加 `.json` 短路（ProjectVersionPicker/ResumeVersionPicker 传递导入 demo/samples.json，Node ESM 需 import attribute；组件源码不动）。

## 测试（先红后绿）
- 红（实现前）：`red-controller.log` = ERR_MODULE_NOT_FOUND（lib 不存在，11 例未实现）；`red-notice.log` = 断言"JobDetailView 必须导出无状态通知组件 JobApplicationStatusNotice"失败。各失败单独留档。
- 绿（实现后）：目标测试 controller 11/11（green-controller.log）、notice 7/7（green-notice.log）；全量前端 303/303（frontend-full.log，含既有 37 文件全部）；`tsc --noEmit` 0 错（typecheck.log，空输出）。
- 覆盖任务卡要求场景：同岗位 vs 其他岗位、active vs withdrawn（withdrawn-only 不当 active、mixed 取 active、多条 active 取最新）、读取失败（显式 error 绝非"未投递"，重试仅新增一次只读调用）、乱序响应丢弃、岗位切换（先清 loading、旧岗位迟到响应丢弃）、卸载后响应不发布、未激活不读取、残缺记录（缺 id/status/空 status/非对象）一律 unknown、重试只读（calls 全部为 myApplications，结构上无写/模型入口）、unknown 渲染空（无"未投递"字样）、error 不含 form/不禁用、active/withdrawn 均无 button 与 checkbox。
- 材料保留由代码层证明：MatchForm 材料 effect/`resolveInitialMaterialSelection`/提交链零改动（`git diff HEAD` 仅 JobDetailView.tsx 一文件）。

## 运行环境与约束
- Node v22.23.1。依赖运行时：按卡先把 `backend/.tmp/refresh-ui-20261015` 完整复制为自有 `backend/.tmp/z56-ui-20261016`（robocopy 10906 文件 466MB），再用当前 HEAD+本卡改动的 `jianli/src`、`jianli/tests` 覆盖镜像进该暂存区后执行（暂存区原 src 有 3 文件落后于 HEAD：globals.css/ApplicationBoard/HeatmapDemo，已用当前版对齐；diff -rq 校验 src/tests 两目录与工作区逐字节一致）。未触碰 Codex 的 refresh-ui-20261015 与 live dep-frontend-20261010。
- 命令（均在 z56-ui-20261016 内）：`node --experimental-strip-types --test tests/job-application-status.test.mjs`、`... job-application-status-notice.test.mjs`、`... tests/*.test.mjs`、`./node_modules/.bin/tsc --noEmit`。
- 未安装依赖、未构建、未启停服务、未触 DB/.env/credentials/storage/client DB/真实模型调用/外部消息/P2/Git 提交推送/清理或其他源。

## 未运行（须注明）
- 真实浏览器/Next 运行时验收未运行（卡禁止真实构建与服务）；按卡由 Codex 激活后安排。
- MatchForm 整树含 useEffect 的挂载链在 react-dom/server 下不可执行（effects 不运行），沿用仓库既有"真实会话控制器 + 真实无状态组件"测试形态（44/48 同例）；MatchForm 接线为 5 行 house pattern（useMemo 会话 + activate/dispose + job.id 重读）。
- 未加 visibilitychange 返回刷新（卡允许"if appropriate"）：避免扩大事件面，返回页面刷新已由 /applications 列表页承担；本页提供显式重试与岗位变化重读，无轮询。

## 自查
- 撤回史呈现为"已撤回授权 + 当前没有进行中的分享"，无任何重投 CTA/勾选；同意默认值未动。
- 状态读取失败只影响提示行：独立 state、独立重试，不进 fieldset、不禁用提交按钮、不触碰材料 state。
- 服务端保持权威：全部为只读 GET 展示，提交拦截逻辑仍在服务端。
- 已知词面限制：`applicationStatusText` 对未知状态字面量原样回显（共享库既有行为，未扩大）。

文件 sha256 见 hashes.txt。变更清单：M jianli/src/components/JobDetailView.tsx；新增 jianli/src/lib/job-application-status.ts、jianli/tests/job-application-status.test.mjs、jianli/tests/job-application-status-notice.test.mjs、docs/evidence/20261016-Z56-job-application-awareness/。
