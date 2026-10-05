# 回复失败草稿修复：Codex 有界签收

2026-10-05。签收范围仅ApplicationBoard回复失败草稿与failure-reply-draft回归，不代表整个E2E-02/03目标已完成。

## 结论与依据

1. Codex全文核对草稿生命周期改动：明确unconfirmed状态与正文是否为空解耦；resetReply/verificationUnavailable递增代际；发送前捕获，await后仅本代更新状态，旧成功/失败不得清理或污染新草稿。
2. ZCode三轮红/绿原始证据均保留。本轮Codex实际运行failure-reply-draft、notification-session、growth-job-selection组合34通过；其中回复草稿8、通知4、学生选择22。`node node_modules/typescript/bin/tsc --noEmit --incremental false`退出0。学生选择另有未签收范围，不随本提交合入。
3. 生产页面首验：`../20261005-E2E-enterprise-retest/reply-failure-2026-10-05T10-47-15-502Z/`的4份draft-acceptance及results.json，桌面/390×请求失败/响应丢失均真实输入→删空→重输；草稿可编辑、无发送/确认框/旧报告、各1次POST且无自动重发。请求失败刷新后未送达可重新人工发送；响应丢失已送达不可二发。Codex读取原始JSON并查看390响应丢失截图，符合可编辑提示与授权清理边界。
4. 最高风险独立页面抽验：closure-20261005上实际执行late-response。新证据`late-response-2026-10-05T11-22-15-479Z/`：A /view响应阶段hold→真实hashchange到A2→A2打开→放行A，continued且responseObserved=true、A2仍开、无A回复内容/错误/失败草稿。独立查看截图，Chrome退出0，脚本退出0。首次默认沙箱Chrome退出2147483651/CDP关闭的失败保留，批准通道复跑成功，未掩盖失败。
5. 两run的合成口令精确值与JSON转义值本地扫描相关企业/草稿/审查证据87份文本：0命中；没有输出口令。截图仅空登录页或登录后页面；无真实用户材料、外部模型、对外消息或远端推送。

## 限制

单元行为测试使用真实TSX渲染/回调与代际规则，未完整挂载GrowthContent/React全部effects；生产页面补齐编辑与授权路径。独立迟到响应抽验验证报告会话，旧发送回调归属另由代码全文及代际回归证明，不冒充全部回调场景已逐个页面注入。

运行器输入/退出码补强及其他企业场景还待整体签收；学生新版目标选择、PG/生产集成、整个GOAL仍未完成。本提交不包含它们的代码。
