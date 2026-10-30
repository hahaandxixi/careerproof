# 10/30 四批简化实施结果

## 接受版本与实际运行

- 工作树：`D:/jbcode/web ai/careerproof-v1`；分支：`codex/simplicity-batches-20261030`。
- 接受源码：`ea02903ccb97d82b880977460b650615903aa350`；基线：`25d817be3d69beab604dce1bbc451409730839cc`。本记录之后的纯文档提交不改变运行源码。
- 3140：构建 `RLcZoyknK6MTku2FRKv3Z`，目录 `jianli/.next-simplicity-batches-close-20261030`，PID 165804。首页 HTTP 200；实际返回的 13 个 JS/CSS 资源与该目录逐字节相同。
- 8140：本工作树 `backend`；Python 启动器 PID 150588、实际服务 PID 150684；健康检查 200。统一库仍为 `127.0.0.1:55447/careerproof_v1`，文件根仍为 `D:/jbcode/web ai/jianli/backend/storage-v1`。
- Windows，Python 3.12.14、Node v22.23.1、Next.js 15.5.27。新服务沿用已核对的原配置：DeepSeek Flash 启用；本轮真实模型请求为零。
- 配置、进程及资源核对见 [runtime.json](runtime.json)。这证明服务与构建绑定，不等于浏览器视觉验收。

## 四批完成范围

| 批次 | 主要变化 | 本地提交 |
| --- | --- | --- |
| 1 逻辑 | 保留具体缺口和建议，未发送来源另列；区分测试代码与执行记录；正文引用与结构化引用共同验证；同文件多路由保留有界候选；岗位要求比较区分相同、变化与未知；生成失败/旧请求不清空或覆盖草稿，默认追加、替换须确认 | `d1c31ea`，后续边界补充 `5d6e70b`、`6909816` |
| 2 材料 | 我的材料→材料内历史→当前表单；按稳定身份归组；先选类型，新版只开对应项目上传区；保留个人作品/参考资料归属；归档统一为更多操作中的“移出材料库” | `68a75b6`，补充 `5d6e70b`、`ea02903` |
| 3 报告 | 我的报告先展示岗位、材料版本与时间；有效引用转为文件名/行号入口，原文及完整身份可查；解释与直接来源保持主要阅读位置；比较先交代两份报告及材料，再显示状态、引用变化与剩余缺口 | `f24a971` |
| 4 企业 | 岗位名称与紧凑筛选；候选人、双人对照、固定报告分视图；同要求双列证据优先，雷达辅助；分数/用量移入详情；已保存核验只读与生成动作分开；回复明确收件人并保留发送保护 | `5e20f27`，比较依据补充 `01a94b7` |

历史快照没有“是否必需”等必要比较字段时，显示依据不足，保留逐人固定报告与双列证据，不强行叠加同轴雷达。只对今后按正常流程创建的投递保存已有固定要求依据；未回填或改写任何历史快照。未知/跨要求正文引用不再当作可采用解释，原始文字仍可追溯。来源在范围外、暂不可读、局部原文、历史核验信息不足分别表达，不统一称为候选人缺材料。

## 实际检查

以下是独立运行，不能相加成全量通过；所有列示运行退出码为 0。

| 运行 | 结果 | 本机日志（相对 backend/.tmp/simplicity-audit-20261030/） |
| --- | --- | --- |
| 第一批后端相关 5 模块 | 113 通过、0 失败、5 跳过 | `batch1-backend-final.log`、`batch1-final.junit.xml` |
| 企业固定报告/核验及本批逻辑 3 模块 | 56 通过、0 失败、6 跳过 | `batch4-backend-final.log`、`batch4-final.junit.xml` |
| 最终缺口与选证 3 模块（6909816） | 33 通过、0 失败、0 跳过 | `final-scope.log`、`final-scope.junit.xml` |
| 整合后的相关前端 17 个文件（5d6e70b，之后仅后端及空项目按钮变化） | 159 通过、0 失败、0 跳过 | `accepted-frontend.log` |
| 最后空项目归档文案/位置补丁（ea02903） | 材料相关 16 通过、0 失败、0 跳过；目标 ESLint 通过 | `materials-closeout.log` |
| 最终生产构建（ea02903） | 编译、类型检查、Lint、静态生成通过；保留既有 VisualEvidencePanel 图片提示 | `materials-closeout-build.log` |

后端跳过项均要求显式配置独立 PostgreSQL schema：慢读取/撤回竞争、账户锁等待、已保存结果读取与撤回串行化等。本轮未新增跳过，未声称 PostgreSQL 专属检查或远端 CI 通过。第三方 SWIG 弃用提示保留。

可复查命令（分别在 backend、jianli 执行；使用现有 Python/Node，不重新安装）：

```powershell
# backend；前两组使用独立 --basetemp=.tmp/<唯一目录> 和 --junitxml=<上述路径>
python -m pytest app/tests/test_evidence_scope.py app/tests/test_simplicity_logic.py app/tests/test_test_source_selection.py app/tests/test_ai_evidence_workflow.py app/tests/test_application_verification.py -q --tb=short
python -m pytest app/tests/test_simplicity_logic.py app/tests/test_applications_api.py app/tests/test_application_verification.py -q --tb=short
python -m pytest app/tests/test_evidence_scope.py app/tests/test_simplicity_logic.py app/tests/test_test_source_selection.py -q --tb=short --junitxml=.tmp/simplicity-audit-20261030/final-scope.junit.xml
# jianli；159 项来自以下一次有界运行
node --experimental-strip-types --test tests/simplicity-logic.test.mjs tests/portfolio-upload.test.mjs tests/material-upload.test.mjs tests/report-reader.test.mjs tests/report-comparison-display.test.mjs tests/report-display.test.mjs tests/report-follow-up-actions.test.mjs tests/source-label.test.mjs tests/application-board-session.test.mjs tests/application-board-visibility.test.mjs tests/application-comparison.test.mjs tests/application-verification-session.test.mjs tests/history-enterprise.test.mjs tests/skill-radar-render.test.mjs tests/skill-radar.test.mjs tests/verification-reply-draft.test.mjs tests/failure-reply-draft.test.mjs
node --experimental-strip-types --test tests/portfolio-upload.test.mjs tests/material-upload.test.mjs
node node_modules/eslint/bin/eslint.js src/app/portfolio/page.tsx
$env:NEXT_DIST_DIR='.next-simplicity-batches-close-20261030'
$env:BACKEND_ORIGIN='http://127.0.0.1:8140'
node node_modules/next/dist/bin/next build
```

最初临时目录权限错误、迭代中断言失败和切换脚本参数错误日志均未删除：临时目录改为本工作树独占目录；业务断言保留；切换脚本补齐清单 schemaVersion 后成功，首次失败未停止服务。最终构建没有覆盖正在运行的旧构建目录，原有 next-env.d.ts/tsconfig.json 修改按构建前字节恢复并保留。

## 数据、截图与剩余边界

- 未迁移、播种、归档或写入演示业务数据；无新报告、投递、回复、通知或模型请求。对 12 张表在本轮前/后做只读内容指纹核对，均一致：103 报告、379 明细、19 投递、49 事件、55 通知、54 项目、75 项目版本、338 项目文件、56 简历版本、265 分析任务、64 用量记录、11 请求尝试。不是只比较行数。
- 先核实受管进程、启动时间、命令、端口、原配置及库/存储后切换本任务服务；最后空项目补丁仅重启 3140，8140 不再重启。未操作其他任务进程。
- 真实前后截图未完成。Computer Use 上轮因不能可靠识别当前浏览器 URL 而停止；本轮无有效恢复依据，未重试、未使用其他接口绕过。现存 `output/screenshots/CareerProof-Simplicity-Audit-20261030/` 仅为改前部分素材（含非 1920×1080 原图），不能冒充本轮新构建效果。
- 待真实页面核对：1920×1080/较窄桌面、放大阅读、键盘焦点；要求切换、来源定位/返回、比较筛选；材料类型/上传目标/失败恢复；企业跨页选择、离窗恢复、同要求双列来源和回复收件人。不得为核对制造演示查看事件、上传、回复或新 AI 调用；有副作用场景继续用隔离数据。
- 新规则未做真实 AI 语义复验；词法范围保护不等同于全面语义判断。未执行无关全量测试，未推送、合并或触发本分支远端 CI。
- 原有 `jianli/next-env.d.ts`、`jianli/tsconfig.json` 跟踪修改以及 output、旧构建目录均保留，未混入本轮提交。本轮到四批为止，不追加整站改版。
