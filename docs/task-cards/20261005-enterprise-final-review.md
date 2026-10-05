# E2E-02：运行器与企业证据复核（只读）

HEAD76dfd59，当前学生个人任务独占closure浏览器/E2E数据；PG免费任务独占其证据目录和随机测试schema。本任务不碰浏览器、数据库、服务或任何执行测试。

1. 只读`scripts/e2e/enterprise-browser-runner.mjs`、`runner-input.mjs`及测试，审参数/路径拒绝顺序、凭据脱敏、动态Chrome调试/进程自有清理、超时和fail/blocked真实退出码、通知撤回无法证明不能pass。
2. 核对旧`docs/evidence/20261004-E2E-enterprise/`与新`20261005-E2E-enterprise-retest/`的原始steps/results/JSON事件及下载哈希。新回复修复已签收76dfd59，不要求重做；旧撤回证据和当前旧审计分别列，不把旧失败记成新版通过。
3. 同页迟到响应主证据必须continued+responseObserved而非already-cancelled；notification-filter定位必须含列表/目标关系，不靠时间猜。报告结论绑定文件hash，记录明确证据路径和疑点。
4. 仅写新`docs/evidence/20261005-enterprise-final-review/`，产品/运行器/所有既有证据/正式文档不修改。不得打印ignored凭据，不读.env或真实材料；不调用模型API/外网、不安装、不Git提交/推送或改stash。
5. 可用已安装review-agent先读技能，但不新增代理写权限。按缺陷优先回报可复现问题、风险及未验项；没发现也如实报告，不能自称Codex签收。一屏回报，完整审查草稿进新目录。
