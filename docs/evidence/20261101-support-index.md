# 材料支持度指数展示（2026-11-01）

## 本次实际启动

用户随后明确要求启动项目并切换最新构建。2026-11-01启动现有Docker Desktop和原 `careerproof-home-discovery-20261027` 容器（55447及原卷保持），未重建容器/卷、未迁移或播种。核实无端口占用、源码与接受版本一致、构建ID/配置指纹/数据库/存储相符、无待执行分析后，通过本地无停止能力的 `backend/.tmp/support-index-activation-20261101/Start-Ready.ps1` 启动API8140和前端3140。

运行源码 `e2e043d9c5063ebcabe177abe8b7a56b8c9418bd`，构建 `ayj9grXn757U2gqBdLjto`；前端PID57620，API启动器58272/监听58192。首页、API健康、对应构建清单和 `/demo/heatmap` 均200，首页13个实际JS/CSS字节与新构建一致。12张业务表数量/内容指纹启动前后不变，AI usage/attempt条数未增加。本机记录 `output/ui-review/20261101-support-index/activation.json`。本次启动命令正常获准执行，不代表此前被拒的命令曾执行。

可访问主入口 `http://127.0.0.1:3140`；单人静态示例 `http://127.0.0.1:3140/demo/heatmap`；企业Python岗位候选人入口 `/jobs/e4625d75-14b3-4e60-9687-5fd82a28c745/applications`（需所属企业登录）。助手没有打开真实企业view POST、发送回复或调用模型。用户可自行打开单人固定报告与双人对照查看；真实浏览器/200%/键盘验收和新截图仍待验。以下未启动及手动预览段落保留为本次启动前记录，不要再按旧步骤重复启动另一端口。

## 接受范围与依据

用户明确选择展示归一化：65→100；不是将原始评分或历史记录改为100。接续 `66db64e` / `bab8922` 的电脑端成果，分支 `codex/support-index-20261101`。共享换算提交 `f1451e7`，接入及组件验证提交 `e2e043d`。不推送、不合并，不调用模型或写业务记录。

- `backend/app/tools/matcher.py` 当前 `STRENGTH_SCORE` 为0.65/0.4/0.15，单项 `final_score=round(rule_score*100,2)`，全局上限65。`c458812` 的父版本为evidence-v3；该提交升至v4且明确评分权重不变，差异没有改变计分。这是v3/v4上限依据，不是从历史最大值猜测。
- 展示指数=`raw/cap*100`，半径=`raw/cap`，几何不使用舍入后的文字。文字至多一位小数，无百分号：65→100，40→61.5，10→15.4，0→0。100表示全局规则上限；复杂要求可能另外封顶30，不表示每条要求都能达到100，更不是能力或录用结论。
- 整图一次解析。v3/v4共享65上限，可以采用同一展示口径，但双人仍逐项严格核对岗位、固定依据完整性、要求集合、标题、技能、权重、formulaVersion和evidenceLevelVersion。未修改这些可比性条件。
- v2、缺版本、`v3`短标签、synthetic-only/synthetic-ui及其他未知版本不自动换算；单图保留原始0–100坐标和“未换算”标识。两人无法确认统一上限时不强行叠加，逐项固定证据继续可查。已知/未知混合整图保留原口径，不逐轴混用分母。
- 公开热力示例通过显式 `DEMO_SUPPORT_SCALE` 元数据采用独立示例上限65；仅synthetic标签或synthetic布尔值不能让已保存报告获得这份上限。
- 缺材料、规则不可评、缺项不绘为零；仅声明保留空心点，真实可评零仍绘点。null、不有限、负值、超出已确认上限均保留原始值并说明，异常轴不绘点，不clamp成100。原值/版本/换算依据在现有计量详情可查。

## 实际修改入口

1. `support-index.js` 统一整图尺度、数值格式、换算与异常；`skill-radar.ts` 沿用原始值语义，绘点/连接前使用同一守卫。
2. `SkillRadar.tsx` 单人刻度、点位、轴标签、可访问名称、提示和当前要求计量统一采用指数；缺材料标签修复和来源/要求联动保持。
3. `CandidatePairComparison.tsx` 双人共用整图口径，同轴图例、节点提示和两列当前要求计量一致；保留身份颜色、实/虚线及大小圆点，不填面积、不排名。未知尺度保留固定证据查看。
4. `ApplicationBoard.tsx` 完整固定要求计量同步，`SupportMeasureDetails.tsx` 复用原始记录追溯；公开 `HeatmapDemo.tsx` 显式传示例尺度。
5. 热力矩阵保持按verdict着色和原选择/分页/权限，不显示或恢复候选人总分；计数、权重、证据等级、预算未换算。学生报告当前没有挂载单人雷达；没有为了本轮添加图表或改写已保存AI解释、报告正文、快照。

## 已执行验证

工作目录 `D:\jbcode\web ai\careerproof-v1\jianli`，Windows / Node以本机日志记录为准。

| 检查 | 命令/结果 |
| --- | --- |
| 共享换算首批 | `node --test tests/support-index.test.mjs`，4通过，0失败/跳过，退出0 |
| 最终相关回归 | `node --experimental-strip-types --test tests/support-index.test.mjs tests/skill-radar.test.mjs tests/skill-radar-render.test.mjs tests/history-enterprise.test.mjs tests/evidence-display.test.mjs tests/application-comparison.test.mjs tests/application-board-visibility.test.mjs tests/heatmap-demo.test.mjs`，56通过，0失败/跳过，退出0 |
| 目标lint | `node node_modules/eslint/bin/eslint.js src/lib/support-index.js src/lib/skill-radar.ts src/lib/evidence-display.ts src/components/SupportMeasureDetails.tsx src/components/SkillRadar.tsx src/components/CandidatePairComparison.tsx src/components/ApplicationBoard.tsx src/components/HeatmapDemo.tsx`，退出0 |
| 独立生产构建/类型 | `NEXT_DIST_DIR=.next-support-index-20261101 BACKEND_ORIGIN=http://127.0.0.1:8140 node node_modules/next/dist/bin/next build`，退出0；构建 `ayj9grXn757U2gqBdLjto`，对应源码 `e2e043d` |

相关回归包含实际组件渲染与真实onClick/Enter处理器、切换要求后点坐标稳定、两人来源ID隔离、要求/权重/版本不匹配、未知/混合版本、缺项/null/缺材料/声明/零/越界及原数据不变。程序验证不是浏览器验收。

日志位于 `output/ui-review/20261101-support-index/`。首次37项回归中3项失败来自旧“不换算”断言和不完整v3测试标签；已按明确新契约更新等价验证。扩大回归时6项未能加载新导入，补齐测试模块映射后全部执行通过，失败日志保留。没有删断言/跳过用例。构建保留原 `VisualEvidencePanel.tsx` 的img优化warning。原先已修改的next-env.d.ts和tsconfig.json均在构建后按原字节恢复，未暂存；旧构建/截图/材料全部保留。

## 运行与真实验收边界

开工和结束核对3140、8140、3141、3142、8161均无监听。`processes.json`仍记录历史 `4a64279` / `VMs6SX8nWr7xIN5Pl5PwX`，不能视为当前在线或本轮构建已生效。新构建已生成但未启动，未执行此前被拒的生产预览启动/重启，未更改统一数据库或存储配置。先前Computer Use无法可靠识别浏览器URL的限制没有解除依据；未重试或换接口绕过。

**未验：** 新构建真实1920×1080、较窄电脑窗口、200%原生缩放、Tab/Enter实际浏览器行为、默认/选中/展开/滚动截图、同数据改前改后、企业mock页面全链路。没有新真实截图，不把组件测试或构建替代实拍。旧截图及已完成视频未修改或重包。

## 最小人工预览与后续验收

需要人工启动新预览时，可在单独PowerShell窗口运行下列命令（不停止现有服务，不写业务数据，不启动API）。端口3141若被占用应停止执行并核实归属，不自行结束占用进程：

```powershell
& {
    $ErrorActionPreference = 'Stop'
    $cpRoot = 'D:\jbcode\web ai\careerproof-v1'
    if (Get-NetTCPConnection -State Listen -LocalPort 3141 -ErrorAction SilentlyContinue) { throw '3141已占用，请先核实。' }
    $cpBuild = (Get-Content -LiteralPath (Join-Path $cpRoot 'jianli\.next-support-index-20261101\BUILD_ID') -Raw).Trim()
    if ($cpBuild -ne 'ayj9grXn757U2gqBdLjto') { throw '构建不匹配。' }
    Set-Location -LiteralPath (Join-Path $cpRoot 'jianli')
    $env:NEXT_DIST_DIR = '.next-support-index-20261101'
    $env:BACKEND_ORIGIN = 'http://127.0.0.1:8140'
    node node_modules/next/dist/bin/next start -H 127.0.0.1 -p 3141
}
```

先打开 `http://127.0.0.1:3141/demo/heatmap` 查看静态示例（不依赖业务API），选择候选人/要求，确认100/61.5/15.4、缺材料无零点；1920、较窄电脑窗口及浏览器菜单200%核对后恢复原缩放。单人真实固定报告及双人证据仍需后续获准隔离mock验收；当前8140离线，不能声称此手动前端入口已打通业务页。不要为截图打开真实企业view POST，或启动模型/投递/回复。真实恢复后的运行地址、构建清单和截图尺寸必须另行记录。

需要后续同步但本轮未改：视频、比赛PDF、源码包、旧截图中若展示原始65，应说明原始口径；待用户确认新页面后再更新交付材料，不自动重录。
