# E2E-03 三变化真实页面验收报告（409审查后接续）

2026-10-05，个人GLM-5.3学生任务。运行环境：既有closure-20261005（8001/3001，aiProvider=mock、aiExternalEnabled=false，运行记录与进程父子链已核验），未重启/迁移/建库。基准为真实UI生成 `baseReportId=1c421762-226c-4895-8949-2752c1482b17`（candidate_ref=user.id 口径，未触发旧seed 409）。未重跑setup-job/baseline/chain-reply；旧seed企业问题任务维持失败留档，未标已回答。

## 结果：5场景全部 exit 0

| 场景 | 任务ID | 新报告 | 关键判定（全部纳入pass/fail） |
|---|---|---|---|
| variant-materials | 225fa32f | R1=d65c7585 | 背景=仅材料版本变化；引用确指向R1；补证重点项新增展示6条；刷新重读第2版存活；PUT体含目标=岗位B |
| variant-job | 5d91c362 | R2=1ce37c54 | 背景=目标岗位变化（无材料变化）；跨岗位banner；removed=1/added=2；Python移除1条+新增1条分列；刷新重读岗位C存活 |
| variant-both | 15c7f81f | R3=835e6897 | 背景同时含材料版本+目标岗位变化；banner C→B；3项全部有任务基准/目标报告两栏解释+等级行；重读=第1版+岗位B |
| viewport390 | — | — | 三页无横向溢出；标题真实滚动至sticky header下(top=129>117)且elementFromPoint命中自身；截图在滚动后拍摄 |
| enterprise-recheck | — | — | A/B/A2三投递快照哈希与状态不变；jobA/B行与要求不变；固定报告均含分数+引用 |

证据：各场景`docs/evidence/20261005-E2E-student/<scenario>-<时间戳>/`（results.json含逐步状态、comparison JSON、PUT体、截图）。state.json含全部任务/报告ID。

## 断言补强（先于运行完成，静态测试12/12钉住）

- citations/新增移除条数/Python分列/两栏解释/R1-R3解析全部进入判定；缺证记fail（如`v-*-new-report-missing`），不再只打印布尔值。
- 任务ID在UI创建返回后立即`saveState`（首步即`v-*-task-saved`）；失败复用：state已有任务则`openGrowthTask`直开，不重复创建（variant-job实跑验证：5d91c362复用两次，未建新任务）；已compared任务跳过重复分析，只重验证据。
- 重读验证在compared复用态也执行（只读）；`rereadSavedSelection`只信重载后DOM。

## 实跑暴露并修复的3个runner缺陷（均为学生helpers范围）

1. `pickTargetJob`开picker的locator设`details.open=true`却从不设`__e2eClickEl`，clickStored点空→13-22-22运行崩溃。改为纯evalJs程序化开（真点summary会把details又toggle关）。
2. `v-job-refresh-reread`断言硬编码"≠"，而section1渲染"与任务原岗位不同"→13-23-17误判fail（业务行为正确：目标存活）。改为接受任一跨岗位标记。
3. viewport390读取了`overflowCheck`不存在的`ok`字段恒undefined→13-25-36误判fail；job-picker的clickStored同缺陷1，被catch吞成warn。均已修。

失败运行目录（13-22-22、13-23-17、13-25-36）留档不删，作修复前证据。

## 边界遵守

未改产品源码/seed/企业runner/正式清单；未撤回A/B/A2、未SQL修数据、未调真实模型、未外发、未Git提交/推送、未动P2stash。工作区存在他人未提交的growth-target-job产品改动（含alembic 0014），未触碰。运行中服务为11:31签署构建，不含这些未提交改动。
