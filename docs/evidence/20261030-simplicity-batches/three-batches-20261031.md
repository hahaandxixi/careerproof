# 2026-10-31 三批定向修复

接受源码 `4a64279c85fe6cc833e76a9cd0d1ef5f7de2f61a`，分支 `codex/action-clarity-20261031`。前端生产构建 `VMs6SX8nWr7xIN5Pl5PwX`，目录 `jianli/.next-three-batches-20261031`。本页是本轮证据，不恢复历史任务。

## 三批结果

| 批次 | 实际修改 | 已执行验证 | 现场边界 |
| --- | --- | --- | --- |
| 1 逻辑与错误 | 报告加载/单项错误隔离，写入与随后GET串行，未知提交与已保存读失败仅重读；账号/角色/报告key与请求代际隔离；矩阵缺项显示“本报告无此项”且不可打开别项；新任务no_evidence说明限定为模型上下文 | 最终相关前端41通过、0失败/跳过；后端3通过、0失败/跳过；目标lint与Ruff通过 | 未在真实数据上提交核对；无实际浏览器故障注入 |
| 2 身份与回复 | 授权投递返回candidateId=所属User.id，类型与消费者同步；示例映射只按4个已核实User.id，不再按5个投递ID。新投递沿用同一身份；学生/企业共用回复类型、真实replied事件时间和原文，旧记录缺失不补造 | 前端49通过、0失败/跳过；后端授权/幂等/固定快照/只读身份集成1通过、0失败/跳过 | 示例映射不是全体数据的覆盖率；小江/未知账号保持；不迁移历史姓名/报告/投递 |
| 3 清理与电脑验收 | 删除ReportOverview早返回后不可达的workbench分支，简化恒真条件；补齐静态热力图夹具candidateId。/growth继续只读GrowthHistory，不恢复GrowthWorkspace/旧任务主流程 | 相关离线76通过、0失败/跳过；静态热力图4通过；生产构建和类型通过 | 真实1920×1080、较窄电脑窗口、200%缩放、键盘、控件展开/滚动/返回未验；无新实拍 |

### 关键事实与保护

- 核对采用单个完整写→读周期，不是“最后点击获胜”。同步前禁用其他核对提交，局部笔记保持；权限失效则清除报告。网络/超时/5xx或成功响应无法解析时不宣称未写入，先核对状态；PATCH已成功而GET失败则明确已保存，不重发PATCH。原已保存笔记在未编辑时沿用。
- 缺项不再回退到unsupported；真正unsupported、支持状态与数值零仍保留各自语义，图表尺度/公式/颜色含义不变。
- no_evidence前置检查先调用build_evidence_contexts的默认3条上限；配置ai_context_evidence_limit=2在之后才用。测试保存了原材料存在、上下文为空、provider未构建与0请求的事实。只更正新步骤文案，不重写历史步骤。
- 新candidateId来自已授权投递所属StudentProfile关联User.id，不冒用旧报告candidate_ref，不扩张企业访问范围，不添加邮箱或其他个人字段。身份映射仍是明确登记的示例白名单，未知身份不凭姓名猜测。
- 回复时间只取有效replied事件；没有事件时显示“回复时间未记录”，不用投递createdAt代替。缺类型显示“回复类型未记录”；原文及不可覆盖规则不变。
- 所有写入/并发/错误验证使用mock或临时SQLite夹具；测试autouse禁止外部AI，受控工作流测试以假provider/替代workflow拒绝外部请求。本轮0真实模型调用、0真实投递/回复/通知/核对写入。

## 实际命令与日志

前端在项目根使用现有Node执行 `--experimental-strip-types --test`：

- `jianli/tests/report-review-session.test.mjs jianli/tests/report-review-render.test.mjs jianli/tests/application-board-visibility.test.mjs jianli/tests/report-reader.test.mjs` → 41通过，退出0；`backend/.tmp/three-batches-20261031/batch1-accepted-source.log`。
- `jianli/tests/demo-display-identity.test.mjs jianli/tests/history-enterprise.test.mjs jianli/tests/account-menu.test.mjs jianli/tests/application-list.test.mjs jianli/tests/application-display.test.mjs jianli/tests/application-board-visibility.test.mjs jianli/tests/report-review-render.test.mjs` → 49通过，退出0；`batch2-frontend-final.log`。
- `jianli/tests/report-reader.test.mjs jianli/tests/history-enterprise.test.mjs jianli/tests/simplicity-flow.test.mjs jianli/tests/job-discovery.test.mjs jianli/tests/account-menu.test.mjs jianli/tests/report-review-session.test.mjs jianli/tests/report-review-render.test.mjs` → 76通过，退出0；`batch3-offline-final.log`。
- `jianli/tests/heatmap-demo.test.mjs` → 4通过，退出0；`demo-contract.log`。各组有重叠，不合计为全量测试数。

后端在backend目录使用既有venv：

- `python -m pytest app/tests/test_ai_evidence_workflow.py::test_no_evidence_skips_external_provider app/tests/test_ai_evidence_workflow.py::test_empty_model_context_does_not_mean_uploaded_source_is_absent app/tests/test_real_matching.py::test_no_model_context_preserves_uploaded_evidence_and_accurate_step -q --basetemp=.tmp/three-batches-20261031/pytest-batch1 --junitxml=.tmp/three-batches-20261031/batch1-backend.xml` → 3通过，退出0。
- `python -m pytest app/tests/test_applications_api.py::test_explicit_consent_owner_scope_idempotency_and_snapshot -q --basetemp=.tmp/three-batches-20261031/pytest-batch2-verified --junitxml=.tmp/three-batches-20261031/batch2-backend-verified.xml` → 1通过，退出0。
- 修改文件Ruff通过；前端修改文件ESLint通过。`NEXT_DIST_DIR=.next-three-batches-20261031 BACKEND_ORIGIN=http://127.0.0.1:8140 next build` → 退出0，包含类型检查；`build.log`。原img优化及Python Swig弃用warning保留。
- 初次构建因静态合成热力图缺少新增candidateId失败，已补真实夹具身份字段后通过，未用类型断言绕过。初次后端新增断言误用了未挂载auth/me的测试应用，改为独立读取夹具User验证，原授权/快照断言全部保留。失败日志均留存。

## 运行切换与工具限制

截至本记录核对，3140/8140仍运行上一版：运行记录653f83a，前端构建XoleNUsVu1E69wlUwOKs3，前端PID109508，API启动器53592/监听53632。不能将本轮新构建写成已加载。数据库127.0.0.1:55447/careerproof_v1、storage-v1及配置保持；切换前只读检查259 COMPLETED/6 FAILED，无PENDING/RUNNING任务。

自动审批拒绝了包含重启逻辑的命令，理由仅为“blocked by policy”；该命令未执行。没有换接口绕过。已准备语法检查通过的本机文件 `backend/.tmp/three-batches-20261031/Start-Ready.ps1`，它不会停止服务：只在原进程/端口已退出、配置/数据库/存储匹配、任务队列无未完成项时启动既有前后端。无迁移、播种或AI请求。

### 手动切换入口（已替换先停服务的旧步骤）

请勿继续使用此前先调用停止函数的五行命令。新增本机只读预检文件 `backend/.tmp/three-batches-20261031/Test-BeforeStop.ps1`：在停服务前检查原进程及端口归属、接受构建和源码、配置指纹、数据库身份/可连接性、存储、运行依赖及无PENDING/RUNNING任务，失败直接抛出错误，不改变服务。返回的原运行记录用于后续身份校验，不重新猜测要停止的进程。

以下命令必须作为**一个完整脚本块**执行。`$ErrorActionPreference='Stop'` 与预检结果/记录指纹检查保证失败时不进入停止步骤；不要拆成先停止再检查。切换期间请暂停其他分析操作及其他执行端对这套服务的使用；预检证明的是检查时状态。启动前原有检查继续保留。

```powershell
& {
    $ErrorActionPreference = 'Stop'
    $cpRoot = 'D:\jbcode\web ai\careerproof-v1'
    . (Join-Path $cpRoot 'scripts\local-runtime.ps1')
    $cpReady = & (Join-Path $cpRoot 'backend\.tmp\three-batches-20261031\Test-BeforeStop.ps1')
    if (!$cpReady.Passed) { throw '预检未通过，不停止服务。' }
    if ((Get-FileHash -LiteralPath $cpReady.RecordPath).Hash -ne $cpReady.ManifestHash) {
        throw '运行记录已变化，不停止服务。'
    }
    Stop-ValidatedLocalProcesses $cpReady.Manifest $cpReady.RecordPath
    & (Join-Path $cpRoot 'backend\.tmp\three-batches-20261031\Start-Ready.ps1')
}
```

本轮仅运行只读预检及故意传入错误构建ID的失败路径：正常预检通过，错误构建被拒绝，3140/8140监听PID前后不变；两个文件语法检查通过。没有执行上面的停止/启动脚本块，没有重启服务。只读检查日志与本机文件都在 `backend/.tmp/three-batches-20261031/`，不进入公共启动器或提交凭据。

此前Computer Use无法可靠识别当前浏览器URL而安全停止，尚无有效恢复依据；本轮读了技能后未重复尝试或改走另一接口。无新截图，不以HTTP壳/SSR/模拟事件代替真实页面验收。

## 最小人工电脑验收

切换确认后，在3140正常缩放及1920×1080打开已有记录：

1. 学生报告切换要求、展开来源/返回，编辑核对笔记但不提交；菜单及首页核对“示例”名称。浏览器前进/后退后仍对应同一报告。
2. 企业候选人页展开要求下拉、键盘选择/关闭；应用/清除搜索及状态筛选，核对页码归1；从已打开且仍授权的快照核对热力格、要求和两列证据。不发送回复/投递或新核验。
3. 浏览器菜单设200%，检查报告和企业页按钮/正文不遮挡、可纵向滚动、Tab焦点可见，再恢复100%；较窄电脑窗口重复关键入口。截图注明构建、视口、缩放和默认/展开/选中状态。
4. 保存失败、保存后读失败及权限失效使用隔离数据或本轮mock测试，不在演示记录上注入故障。上述真实操作和截图完成前，第三批保持待验。

未推送、未合并；原配置修改、旧构建、素材和中断日志保留。本轮不改比赛包或视频。
