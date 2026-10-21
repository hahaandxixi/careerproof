# 2026-10-22 页面结果接收、显式提交与真实 200% 验收

状态：接收文件准备本地提交；未推送、未部署；不调用模型。3108/8108 未重启。

## 1. 本轮接收清单（18 个未提交文件）

| # | 文件 | 归类 | 处理理由 |
|---|---|---|---|
| 1 | `backend/app/schemas/analysis.py` | 暂停的展示改动 | 后端展示 schema，未在本批页面验收范围；保持原样 |
| 2 | `backend/app/services/analysis.py` | 暂停的展示改动 | 后端展示组装，未在本批页面验收范围；保持原样 |
| 3 | `backend/app/tests/test_real_matching.py` | 其他 | 非本批页面文件；不夹带提交 |
| 4 | `backend/app/tools/evidence_levels.py` | 其他 | 非本批页面文件；不夹带提交 |
| 5 | `demo/README.md` | 其他 | demo 说明，不是本批指南/页面；保持未提交 |
| 6 | `demo/market-scenarios/README.md` | 其他 | demo 场景说明，不是本批指南/页面；保持未提交 |
| 7 | `docs/guides/使用与启动.md` | **本批接收** | 启动指南新增 8 行；出包前必须进入提交，否则包内仍是旧指南 |
| 8 | `docs/guides/功能演示.md` | **本批接收** | 与报告页/步骤条直接相关，已按当前页面同步 |
| 9 | `docs/guides/比赛交付.md` | **本批接收** | 视频归档说明 1 行；出包前必须进入提交 |
| 10 | `docs/当前接力.md` | 其他 | 交接记录不属于页面结果；本批不改写 |
| 11 | `jianli/src/components/FlowSteps.tsx` | **本批接收** | 已验证移动端步骤提示；构建中实际加载 |
| 12 | `jianli/src/components/JobDetailView.tsx` | 暂停的展示改动 | 岗位选择展示未在本批验收；保持原样 |
| 13 | `jianli/src/components/ReportDetail.tsx` | 暂停的展示改动 | 报告详情仍有未完成的展示改动；不夹带提交 |
| 14 | `jianli/src/components/ReportEvidenceWorkspace.tsx` | **本批接收** | 已验证固定材料版本/下一步；构建中实际加载 |
| 15 | `jianli/src/lib/api/domain.ts` | 暂停的展示改动 | 展示类型改动未在本批验收；保持原样 |
| 16 | `jianli/src/lib/report-display.ts` | 暂停的展示改动 | 展示辅助改动未在本批验收；保持原样 |
| 17 | `jianli/tests/flow-steps.test.mjs` | **本批接收** | 对应 FlowSteps 的回归测试 |
| 18 | `jianli/tests/report-action-layer.test.mjs` | **本批接收** | 对应报告工作区的回归测试 |

不是 `git add -A`：只对“本批接收”文件及本记录证据显式暂存。

另有 2026-10-22 的 UUID 显示修复批次（新增 helper、多个组件和测试）仍在工作树，不在上述 18 文件内，**未纳入本批提交**；不能把它算作本批 18 文件之一。

## 2. 文档修正

- 旧 UI 验收 README 的 `sm:hidden` 表述从“390px 以下”改为 **视口 <640px**。
- 旧说明“review-only 不写成可直接投递”已与当前实现不符；当前实现是：存在待补/部分支持/需复核时提示可核对，但**不阻止直接投递当前报告**。验收记录已同步。
- 旧截图和 21 项结论是 2026-10-21 旧 source 的历史结果，已作废，不再作为本批通过依据。

## 3. 构建与 3130 预览

- 接受文件集在独立工作树 `backend/.tmp/ui-accepted-worktree` 构建，工作树基线 `8e344aa`；不包含暂停展示改动。
- 构建命令：`NEXT_DIST_DIR=.next-accepted BACKEND_ORIGIN=http://127.0.0.1:8108 node node_modules/next/dist/bin/next build`
- 结果：exit 0，19 页面生成；BUILD_ID `_MAQzEIqP5DEgV9hioxr_`。Next 提示构建环境未安装 ESLint（不是 lint 通过声明）。
- 独立 3130 预览：`next start` 已启动并实际访问；测试完成后停止。
- **3108 当前仍是**旧构建 `WDMAX7DoSVpEqnsSppkxf`，不能代表本批；未重启、未替换 3108。

## 4. 真实浏览器 200% 缩放

方法不是 CDP `pageScale`：

1. 启动独立的 **GUI Chrome**（非 headless），1280×900；
2. 前台窗口经 `WScript.Shell.AppActivate` 激活；
3. 用系统键盘事件发送 **Ctrl+Shift+=**（浏览器“放大”快捷键）；
4. 用 CDP 读取布局，不作为缩放手段。

结果：

- 缩放前：`innerWidth=1280`、`dpr≈1`；
- 缩放后：`innerWidth=640`、`dpr≈2`、`clientWidth=scrollWidth=632`，即视口约 640 CSS px，页面无横向文档溢出；
- `visualViewport.scale` 仍为 1，说明不是 CDP 页面缩放；
- 截图：[after-1280-browser-zoom200.png](after-1280-browser-zoom200.png)
- 原始数据：[browser-zoom-check.json](browser-zoom-check.json)

200% 下步骤条自身仍有横向滚动，这是 <640px 布局的预期行为；不是整页横向溢出。

## 5. 测试与版本

- 接受文件集前端测试：`node --test tests/flow-steps.test.mjs tests/report-action-layer.test.mjs` → **16 passed**。
- 旧记录里的 **21 passed** 属于旧 source，已作废；本批不沿用。
- 未调用模型，未重跑规则报告，未读写正常库，未重启 3108/8108。
- 本记录对应接受提交：`<待提交>`。

## 6. 未验证 / 边界

- 没有把新构建部署到 3108；3108 仍是旧页面。
- 暂停的 6 个展示改动、demo README、当前接力、后端其他未提交文件均未纳入。
- UUID 显示修复批次是另一批未提交工作，未纳入本次提交。
- 本轮只验证页面可加载、关键文案、真实 200% 和前端目标测试；未重复全量后端/全部页面验收。
