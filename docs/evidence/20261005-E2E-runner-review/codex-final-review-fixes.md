# 企业运行器最终审查修正

2026-10-05。只读终审发现两处P2，Codex在企业任务交棒后修复；学生独占浏览器/closure数据，本轮仅离线检查企业运行器，无数据库或页面操作。

- 所有证据detail先清洗，由同一prepareEvidenceRecord生成JSON对象和控制台文本；异常携带秘密值也不会通过原始step.detail旁路输出。测试注入假秘密串，验证两端均脱敏且原输入不变。
- withdraw-verify须每张可打开通知实际落到合法投递锚点且无撤回目标，才允许pass。全部/部分未落地、数量缺失、无事件关联、零可打开卡记blocked；撤回目标出现记fail。blocked随现有聚合退出非零。不能靠“没有看到A”空泛通过。
- 原历史JSON未改：旧四次no-landing记录虽写pass，本签收不采用；仅最终有真实A2/B落地的10-09-19证据可供审查。新closure仍禁止撤回，本次未实际重跑撤回页。

回归先缺少新导出红灯EXIT1，见codex-final-review-red.raw.out；修复后17测试通过、EXIT0，见codex-final-review-green.raw.out。node --check enterprise-browser-runner.mjs通过。此处是离线护栏修复验收，整个企业闭环仍需独立签收。
