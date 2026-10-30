# 10/30 后续四批：入口、材料、报告与企业筛选

用户在上一轮之后追加的限定实施。基线 `2a1022e`；分支 `codex/simplicity-flow-closeout-20261030`；接受源码 `17800f4b577418d3eb02554481988f4dda904780`。本轮未改后端、模型提示、评分、权限或数据库结构；没有真实模型调用和业务写入，未推送或合并。

## 分批结果

| 批次 | 实际变化 | 定向验证（各次独立，不相加） | 本地提交 |
| --- | --- | --- | --- |
| 1 旧补证入口与筛选 | 账户菜单移除历史补证；旧 URL 转为只读历史，保留原任务/API/私人草稿与报告比较；补充材料链接保留报告/要求并可携带项目版本，接收端核对活动项目归属，已有未完成上传不被覆盖；投递状态选择后立即生效，关键词由“搜索”提交；去掉重复“当前位置” | 31通过、0失败/跳过；类型检查与目标lint通过 | `567e18b` |
| 2 材料与公共操作 | 刷新并入标题工具栏；已有材料时示例下载收进帮助；历史版本在所属材料下显示数量；归档为紧凑、默认收起入口，恢复需明确点击；次要链接/按钮/展开样式统一；输入框保留焦点ring，去掉叠加全局outline | 31通过、0失败/跳过；目标lint通过 | `458679a` |
| 3 报告层级 | 删除重复通用段落；没有工具记录不显示填充卡片，有记录默认收起；内部预算规划等保留在分析详情；AI正文与来源仍默认可读；材料判据去掉考试类比及未开放层级，历史等级保留，不改成能力认证 | 84通过、0失败/跳过；类型检查与目标lint通过 | `9d67120` |
| 4 企业对照 | 状态与证据使用分段按钮，要求选择立即筛选，关键词点搜索；服务端筛选条件及分页保留，筛选不清空跨页名单；热力图优先状态，原始计量仍可在固定报告详情查询；双列保留具体缺口，无记录时不填通用缺口；读取已保存建议不再误称生成，生成仍需明确外发同意 | 91通过、0失败/跳过；目标lint通过 | `17800f4` |

上述是组件事件、离线样例与既有会话回归，不冒充真实浏览器或真实账号验收。新增测试核对状态筛选参数、页码重置、名单保留、只读历史、私人内容离窗清除、上传目标归属及草稿保护、归档恢复、读取/生成状态。原取消、失败、重复请求、来源锚点、授权撤回和回复确认断言保留。

原测试中仍假定两种上传表单同时挂载、删除按钮名为“删除项目”，与上一轮已提交实现不符。本轮改为验证选择类型后仅挂载对应表单、实际归档调用与版本移除；没有跳过测试或改动权限断言。迭代失败日志保留。

## 构建与运行

- 最终 `next build` 退出0，编译、类型检查、lint、静态生成成功；唯一既有提示为 `VisualEvidencePanel.tsx` 的图片优化警告。
- 3140 新构建 `SkBhzD4xLUh2sDXZ1r31g`，目录 `jianli/.next-simplicity-flow-20261030`，PID 266896。先验证受管进程身份后只切换该前端，旧构建仍保留。
- API8140 PID 150684未重启；统一库 `127.0.0.1:55447/careerproof_v1`、存储 `D:/jbcode/web ai/jianli/backend/storage-v1`、原AI配置均未变。没有迁移、播种、上传、归档或回复演示记录。
- 六个路由的HTTP页面壳为200，21个资源与磁盘构建逐字节一致。这不证明受保护页面已登录加载或实际操作通过。详见 [flow-runtime.json](flow-runtime.json)。
- 12张表的开工/结束内容指纹一致，包含103份报告、19份投递、49条事件、55条通知、75个项目版本、64条AI用量和11条请求尝试；不是只比数量。
- 原有 `next-env.d.ts`、`tsconfig.json` 修改在构建后按字节恢复；output与旧构建目录保留，未加入本轮提交。

## 命令与日志

日志位于本机 `backend/.tmp/simplicity-flow-20261030/`，本轮未重新执行无关全量或后端测试。以下分别在 jianli 中执行，所列最终命令退出码均为0：

```powershell
node --experimental-strip-types --test tests/simplicity-flow.test.mjs tests/account-menu.test.mjs tests/flow-steps.test.mjs tests/report-follow-up-actions.test.mjs tests/application-list.test.mjs tests/application-list-session.test.mjs
node --experimental-strip-types --test tests/portfolio-upload.test.mjs tests/material-upload.test.mjs tests/material-workspace.test.mjs tests/project-removal.test.mjs tests/simplicity-flow.test.mjs
node --experimental-strip-types --test tests/report-reader.test.mjs tests/report-action-layer.test.mjs tests/agent-evidence-render.test.mjs tests/report-comparison-display.test.mjs tests/report-follow-up-actions.test.mjs tests/report-display.test.mjs tests/source-coverage.test.mjs tests/analysis-status.test.mjs
node --experimental-strip-types --test tests/application-board-visibility.test.mjs tests/application-board-session.test.mjs tests/application-comparison.test.mjs tests/history-enterprise.test.mjs tests/application-verification-session.test.mjs tests/verification-reply-draft.test.mjs tests/failure-reply-draft.test.mjs tests/skill-radar-render.test.mjs tests/simplicity-flow.test.mjs
node node_modules/typescript/bin/tsc --noEmit
# 每批实际修改的组件执行目标 ESLint；最终构建再次检查类型与Lint
$env:NEXT_DIST_DIR='.next-simplicity-flow-20261030'
$env:BACKEND_ORIGIN='http://127.0.0.1:8140'
node node_modules/next/dist/bin/next build
```

对应日志：`batch1-tests-final.log`、`batch2-tests-accepted.log`、`batch3-tests-final.log`、`batch4-tests-final.log`、`batch1-typecheck.log`、`batch3-typecheck.log`、`build.log`。第一批的31项是当时测试文件版本，后续新增用例不反算到旧运行。

## 待验与边界

- **无本轮真实1920×1080截图，未签收视觉效果。** 已读取当前Computer Use规则；此前浏览器URL无法可靠识别的安全停止仍无有效恢复依据，没有反复尝试或通过其他接口绕过。旧截图没有改名当成新构建。
- 待真实页面验证：菜单展开/关闭，投递状态选中与结果；材料工具栏、历史数量与表单定位；报告要求切换、来源展开/返回、版本比较；企业筛选与双列来源；1920×1080、较窄桌面及键盘焦点。需要写入的流程继续使用隔离数据，不制造演示事件。
- 历史快照的要求字段不足时仍不能确认严格同轴比较，双列固定证据可用；本轮未回填。规则将某些完整上下文实现片段标为“任务实现”，仍不能证明完整业务执行、测试通过或本人贡献；底层逻辑未改，如需改变判据须另行评审，不能用展示文字掩盖。
- 本轮UI源码和定向验证已收口；真实页面及截图待验，不继续扩展其他模块。
