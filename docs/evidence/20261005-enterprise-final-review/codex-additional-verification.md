# Codex 独立补验：通知身份、下载与390px可见报告

日期2026-10-05；本记录仅签收下列补验，不冒充学生闭环或整个GOAL完成。

## 旧通知与固定快照

`codex-notification-object-check.py` 在严格限定的本机 `cp_e2e_audit-20261005` 库中执行 `SET TRANSACTION READ ONLY`，从通知关联事件取得真实投递ID，再调用只读目标服务。没有标已读、撤回、回复或SQL更新，最后回滚。

原始输出 `codex-notification-object-check.raw.out`：EXIT=0、writes=0；A保持withdrawn，A/B/A2快照哈希均与原清单一致。精确关联A的submitted与withdrawn通知均返回404；B和A2的submitted通知返回200且目标ID一致。此项是服务/数据库核查，不声称新做了HTTP或页面点击。此前脚本路径错误输出单独保留，不计通过。

## 实际下载文件

`codex-download-hash.raw.out` 为Codex重算已落盘授权合成简历：203字节，SHA256 `a0149d5a113b3432d86c5cf235e26aa8283b37b6ac2550ba704432a75c1c6b6b`，与closure合成清单一致；不是仅采信下载提示。

## 390px报告可见性

运行器原断言仅检测DOM标题存在；现在滚动实际标题到视口中部，检查标题不被header遮挡，并要求页面无横向溢出，同时保存视口截图。没有修改产品页面。

命令：`node scripts/e2e/enterprise-browser-runner.mjs --run closure-20261005 --scenario viewport390`。沙箱Chrome异常退出证据保留；获准本地运行的最终原始输出 `codex-viewport390-visible.raw.out` EXIT=0。对应 `../20261005-E2E-enterprise-retest/viewport390-2026-10-05T12-56-16-532Z/results.json`，真实390×844、reportVisible=true、pageWidth=390。Codex实际查看 `08-report-390-visible-viewport.png`，标题、合成A2固定报告与下载入口可读，无遮挡。第一次获准截图仍有header遮挡，不作为最终可见性证据，原始运行保留。

只登录并查看closure A2，未撤回、未发回复、未调用模型。运行器护栏独立重跑17项通过，输出 `codex-viewport-guards.raw.out`；这些参数护栏不替代真实页面验收。

剩余工作：学生409夹具身份不一致需处理并完成真实三变化路径；企业整体签收应整合既有迟到响应、回复失败、通知定位及历史撤回页面证据。真实模型质量未验证。
