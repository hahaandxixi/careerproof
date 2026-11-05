# 学生报告页：步骤与补证入口可理解性（2026-10-21）

状态：**有界 UI 修改完成，未提交，交 Codex 审查集成。** 未调用真实模型，未在正常库/正常站写业务记录。

## 实际环境

- 3108 实际监听 PID 224728；口径来自 `backend/.tmp/agent-display-20261021/frontend-process.json`：
  - cwd `backend/.tmp/agent-display-20261021/source/jianli`
  - `next start --port 3108`
- 3108 HTML 的 BUILD_ID `WDMAX7DoSVpEqnsSppkxf` 与上述 source `.next/BUILD_ID` 一致；**不是当前工作树源码直接加载**。
- 3108 合成报告：`ac09d831-073b-4d9e-8799-3b4971716562`；provider `mock-ui`，State `realModelRequests=0`。页面明确标“Mock 界面验证 · 非真实模型报告”。
- 修改预览：从当前工作树构建，独立端口 3130，`BACKEND_ORIGIN=http://127.0.0.1:8108`；预览进程已停止，3108/8108 用户进程未重启。

## 实际发现

1. **390px 学生步骤条只露出第 1–3 步**（before 截图）；父容器可横向滚动，但页面没有可见提示，第 4/5 步容易被认为不存在。
2. **报告页“下一步补证计划”没有在附近说明这一份报告绑定的材料版本**；用户要向下滚动才能看到“本次使用的材料版本”，不容易确认“哪一版报告”。
3. 当前全支持的 Mock 报告虽然默认展开“有证据支持”，但“下一步”文案只写成补证计划，没有明确说明“当前没有待补项时可以直接核对引用后投递”。
4. 加载状态显示“正在确认登录状态…”，网络失败时显示“无法连接服务，请确认网络和后端运行状态后重试。”及“重新加载”；实际点击后恢复报告。报告页不存在“空报告”路由，空结果不属于本页状态。
5. 企业候选页当前 `/jobs/b3b6.../applications` 返回空列表，未观察到候选/回复有效状态；本轮不修改企业页。

## 修改

| 文件 | 归属 | 变化 |
|---|---|---|
| `jianli/src/components/FlowSteps.tsx` | 页面公共步骤组件，修改前无未提交改动 | 外层包一层；保留原有全部步骤与链接；`sm:hidden` 在视口 **<640px** 时显示“左右滑动查看全部 5 步”。 |
| `jianli/src/components/ReportEvidenceWorkspace.tsx` | 学生报告补证工作区，修改前无未提交改动 | 在“下一步补证计划”显示固定材料版本（例：简历 v1 · 项目 v1）；根据 gaps/partial/other 给出不夸大、可执行的下一步；全支持时明确可核对引用后投递。 |
| `jianli/tests/flow-steps.test.mjs` | 对应回归 | 断言移动端提示存在。 |
| `jianli/tests/report-action-layer.test.mjs` | 对应回归 | 断言固定材料版本；全支持可直接投递；存在待补/部分支持/需复核时提示可核对，但**仍不阻止直接投递当前报告**。 |
| `docs/guides/功能演示.md` | 与报告页直接相关的现有指南；修改前无未提交改动 | 说明手机步骤条会提示横向滑动；演示二增加固定材料版本与“全支持可直接投递/补证不是前置条件”的操作步骤。 |

未修改：评分、报告模式判定、API 协议、数据库、预算守卫、历史结果、`ReportDetail.tsx`、`JobDetailView.tsx`、`schemas/analysis.py`、`analysis.py`、`report-display.ts`、`domain.ts`。

## 验证结果

- 目标测试：`node --experimental-strip-types --test tests/flow-steps.test.mjs tests/report-action-layer.test.mjs tests/evidence-workspace.test.mjs`
  - **21 passed**
- TypeScript：`node node_modules/typescript/bin/tsc --noEmit` exit 0。
- 目标 lint：当前 `jianli/node_modules` 缺 ESLint；用隔离 source 的 ESLint 9.39.5 在临时项目（junction node_modules）跑两份组件，exit 0、0 error；临时项目无 `pages` 目录产生一条配置 warning，不是代码错误。
- 生产构建：`NEXT_DIST_DIR=.next-ui-audit-build2 next build` exit 0，19 页面生成；Next 提示构建内 ESLint 未安装（不会把它写成 lint 通过）。构建自动改写的 `tsconfig.json` / `next-env.d.ts` 已恢复，未混入改动。
- 浏览器：
  - 1280×900：before/after 截图，after 显示材料版本与下一步；
  - 390×844：after 显示滑动提示；将 `.student-flow` 滚到末端后第 4/5 步可见；
  - 1280 + CDP pageScale 2：`document.scrollWidth=clientWidth=1265`，无横向文档溢出；这是 CDP 缩放检查，不等同于系统 Ctrl+ 缩放实测，仍标 UNVERIFIED；
  - 390×844 200% 页面缩放：after 仍可纵向使用；该宽度低于 320 CSS 等效宽度，横向滚动属于预期；
  - 键盘 Tab 12 次：顺序覆盖跳过入口、品牌、三个主菜单、账户菜单、步骤 1/2/4/5（当前第 3 步是文本，不可聚焦）、返回报告、实际处理记录；无不可见焦点陷阱；
  - 加载/失败/恢复：延迟网络显示“正在确认登录状态…”；阻断报告 API 显示错误与“重新加载”；解除阻断后实际点击“重新加载”，报告恢复（`state-check.json`）。
- 实际页面行为，不是仅截图：3108 旧构建 before 与 3130 当前源码 after 均通过 CDP 实际导航和 DOM 检查；预览服务已停止。
- 用户指南：`docs/guides/功能演示.md` 的步骤已同步，未新增重复文档；本轮没有改 `使用与启动.md` 或 `比赛交付.md` 这两个已有他人未提交改动的指南。

## 未完成 / 未验证

- 空结果：报告详情路由以报告 ID 为入口，没有“空报告”状态；本轮不改报告列表空态。
- 企业候选列表/回复区：当前合成岗位无投递，未验证。
- 1280 桌面真实浏览器 200% 未用系统 Ctrl+ 缩放复跑；仅 CDP pageScale 检查（无横向文档溢出），标 UNVERIFIED。
- 当前工作树仍有他人 11+ 个未提交文件（含暂停展示、`test_real_matching.py`、`evidence_levels.py` 等），本轮未纳入、未修改其内容。
- 本轮未提交、未暂存、未推送；交 Codex 审查后集成。

## 证据

- `before-student-report-1280.png` / `before-student-report-390.png`
- `after-student-report-1280.png` / `after-student-report-390.png`
- `after-student-report-390-steps-end.png`
- `after-student-report-1280-200pct.png`
- `state-loading.png` / `state-failure.png` / `state-recovered.png`
- `interaction-check.json` / `state-check.json`
