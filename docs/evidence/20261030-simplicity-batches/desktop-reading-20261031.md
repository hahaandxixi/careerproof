# 10/31 限定电脑端阅读优化

按 frontend-engineer-agent 技能实施。基线 `579987e`，分支 `codex/desktop-readability-20261031`；接受源码 `e9f3d091c682ca513342ce57e36e135b9e68f01c`。没有移动端专项、后端修改、模型调用或业务写入；未推送、合并。

## 现场与问题分类

- 当前仍存在（代码确认）：空列表显示无效分页；源码没有换行/展开控制；单人雷达在较窄电脑窗口默认隐藏；热力图缺少要求与候选人组合的单元格选中态；双人图例未直接标识线型。
- 已修正、页面待验：历史补证菜单、筛选按钮文案、材料刷新工具栏、报告空白过程卡等已在基线修复，不重复改造。账户菜单展开区已有完整名称。
- 未复现/未验证：旧截图中的具体遮挡、短/长解释和多来源两栏空白、200%实际缩放。旧截图只代表各自旧构建；本轮没有将其标为新效果。
- 开工3140/8140没有监听，原容器8ca4c569（careerproof-home-discovery-20261027）已退出。核对原55447映射后启动原容器，没有重建卷、迁移或播种。只读确认259个完成、6个失败任务，无待运行任务后，沿用原配置启动服务，未停止其他任务进程。

## 分批修改与验证

1. `99c0c28`：空列表首页不显示分页；越界空页保留返回上一页能力。没有重做已清理的文案或账号菜单。
2. `4a4c26f`：EvidenceSnippet 增加换行、展开阅读、收起返回及复制原文；保持缩进、物理行号和原始文本。横向滚动不标成数据截断。报告两栏比例未改、未增加sticky，因为要求的真实四类页面实测尚不可执行。
3. `e9f3d09`：单人雷达在电脑窄窗口也直接显示；保留原刻度、绘点、颜色和比较条件。热力图仍是要求×候选人矩阵，改善字号/列宽/要求换行及选中格反馈，表头首列sticky和横向滚动保留。双人图例增加文字线型说明，轴标签保留完整悬停标题；单人/双人源码复用相同行号阅读控件。

实际定向命令（jianli目录），退出码均0：

```powershell
node --experimental-strip-types --test tests/desktop-reading.test.mjs tests/list-pagination.test.mjs tests/report-reader.test.mjs tests/source-identity-render.test.mjs
# 37通过、0失败/跳过：reading-tests-final.log
node --experimental-strip-types --test tests/skill-radar.test.mjs tests/skill-radar-render.test.mjs tests/history-enterprise.test.mjs tests/application-board-visibility.test.mjs tests/application-comparison.test.mjs tests/desktop-reading.test.mjs
# 40通过、0失败/跳过：charts-tests-final.log
node node_modules/eslint/bin/eslint.js src/components/ListPagination.tsx src/components/EvidenceSnippet.tsx src/components/SkillRadar.tsx src/components/CandidatePairComparison.tsx src/components/ApplicationBoard.tsx
$env:NEXT_DIST_DIR='.next-desktop-reading-20261031'
$env:BACKEND_ORIGIN='http://127.0.0.1:8140'
node node_modules/next/dist/bin/next build
```

日志在本机 `backend/.tmp/desktop-readability-20261031/`。最终编译、类型、lint、静态生成通过，仅既有VisualEvidencePanel图片警告。两组测试不相加成全量；没有重复无关后端全套。

## 尺度核对与待选方案

- 单人SkillRadar用于企业固定报告及合成展示；学生真实报告页没有直接挂载该雷达。双人图在CandidatePairComparison，两者都按原始分值/100绘点，刻度25/50/75/100。
- radarPointKind区分材料支持、仅声明及不绘点；gap即使保存0也不绘点，unsupported/null不当作能力零分。真正有材料支持的数值0与gap状态不混用。仅相邻有材料支持的点连线。
- 双人严格叠加受comparisonBasis、固定要求完整性、岗位ID、要求ID/内容/技能/权重和规则版本一致性限制；条件不足维持既有不可比较处理，本轮未放宽条件。
- 只读统计379项历史记录：evidence-v2/v3/v4及synthetic-ui并存；支持项观察值65，partial为15–40，声明为10，gap为0或历史null，unsupported为null。观察范围不是对所有历史/未来规则上限的证明，未将全部记录统一归一化。
- 用户明确暂不改变尺度。A保留0–100原始坐标；B仅在确认规则上限65且比较尺度一致时用0–65原始坐标，原值65绘到外圈但仍标65，不转成100%。历史其他尺度单独保留，不能静默裁剪或混比。
- 本地 `output/ui-review/20261031/radar-scale-preview.html` 使用同一保存报告8b12bdc5-d298-4e62-b4e5-947aee1bd820生成独立A/B静态方案；旁有原始值表和radar-scale-data.json。它不是产品截图或新模型结果，尚非真实浏览器A/B实拍；生产尺度完全未改。

## 运行与真实验收边界

- 前端3140构建 `mooOW7bI-CNs0o20RcjTj`，目录 `.next-desktop-reading-20261031`，PID44068；API8140实际PID71896（启动器44452）。原careerproof_v1及storage-v1保留。详见[运行绑定](desktop-runtime.json)。
- 六个HTTP路由壳与21个实际资源匹配新构建；这不等于登录后页面点击或视觉验收。启动记录一次前端提交字段生成失败已修正；服务启动成功，未以错误字段宣称版本绑定。
- 12张业务表开工/结束内容指纹一致，包括103报告、19投递、49事件、55通知、265任务、64用量和11请求尝试；没有模型或业务记录新增。
- 无真实新截图。Computer Use此前URL安全识别停止没有新恢复依据；已阅读更新后的技能规则，未绕过。1920×1080默认/选中/展开/滚动，较窄电脑窗口，真实200%缩放、键盘和浮层遮挡均待验；不声称视觉验收通过。
- 原next-env.d.ts/tsconfig.json修改以及output/旧构建保留，不纳入提交。不恢复旧待办或新增其他页面改版。

## 控件、接口与操作接续核对

补充有界回归25项通过、0失败/跳过，退出0（`actions-tests.log`）：`node --experimental-strip-types --test tests/application-submit.test.mjs tests/application-submit-session.test.mjs tests/report-follow-up-actions.test.mjs tests/account-menu.test.mjs tests/simplicity-flow.test.mjs`。均为离线接口/组件测试，无真实发送。

| 类别／入口 | 动作或请求 | 目标与反馈 | 证据与边界 |
| --- | --- | --- | --- |
| UI简化／空列表分页 | 首页total=0不显示按钮；越界保留上一页 | 可返回有记录页 | 本轮真实组件事件回归；页面空态待浏览器验 |
| 逻辑／报告→上传新版 | 链接携带原报告、要求、项目版本；GET核对归属 | 只打开正确上传表单，不自动上传/分析；未完成上传不覆盖 | 已有操作接续回归通过；拒绝/缺失/晚回执保护保留 |
| 控件适配／学生投递状态 | 选择立即提交视图与关键词，页码归1；重置清空条件 | 选中态和服务端条件一致 | 本轮复用组件事件回归通过；真实展开/点击待验 |
| 控件适配／企业要求选择与状态 | 原生要求select及分段按钮→服务端筛选；保留已选候选人 | 分页一致、跨页名单保留，撤回后不能恢复 | 本轮图表会话回归通过；原生下拉打开/键盘/关闭未实测 |
| 逻辑／报告投递 | 固定reportId→POST createApplication；明确授权后才启用确认 | 忙碌禁用、防重；成功入口、真实失败与重试 | 25项中的投递组件/会话验证通过；没有真实POST |
| 控件适配／报告与来源切换 | 要求锚点、来源定位、历史返回 | 维持要求与引用对应，不代换材料版本 | 37项来源/阅读回归通过；浏览器返回与滚动待验 |
| UI与逻辑／企业雷达及热力格子 | 单元格明确候选人+要求；切回矩阵标明选中格 | 仍联动对应固定报告，不发送回复 | 40项相关回归通过；实际桌面遮挡待验 |
| 控件适配／企业核验 | GET读取保存建议；生成必须显式同意 | 读取不伪装生成，失败原因仍可见 | 本轮25项中的离线操作验证通过；无AI请求 |

以上没有发现需要继续扩大修改的已复现接口缺口。未验证项不是已确认无问题，也不因构建通过变成真实页面验收通过。
