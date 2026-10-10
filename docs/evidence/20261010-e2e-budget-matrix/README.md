# 升级运行的核验预算状态矩阵

2026-10-10。成功运行为 budget-matrix2-20261010，专属cp_e2e同名库、0017、升级Python/Next、8001/3001、严格MockTransport。预算通过真实inventory审计启用后才播种；没有真实DeepSeek调用、业务库迁移或邮件发送。

## 实际页面与数据库

成功浏览器证据：budget-state-matrix-2026-10-10T03-10-34-617Z/results.json、截图、budget-state-views.json及browser-fresh-run.raw.out。

- A：15秒响应延迟期间页面预留4013/3000；完成后已知100/80，预留清零。刷新保留结算值。
- B：返回有效合成建议但缺usage，页面已知仍100/80、预留4013/3000、待核实1条，并明确收据不完整。复用与刷新无新增物理调用。
- A2：HTTP503页面明确失败、没有自动重试或旧建议；两次缺收据累计预留8026/6000、待核实2条；刷新后不归零。
- 八次页面状态采集均实际innerWidth=scrollWidth=390，非仅设置Chrome窗口宽度。失败截图已独立查看预算与错误文案。
- audit-final.json使用SET TRANSACTION READ ONLY独立读取专属PG：恰好3条attempt（1booked、2usage_unknown）、3条reservation（1settled100/80、2held各4013/3000）、核验任务2completed+1failed；三份原投递快照hash与播种清单相同。

audit-fresh-inflight.json的文件名来自启动探针时的预期阶段，实际采集已到B缺收据完成；仅作为中间账目证据，不冒充A在途SQL。A在途证据来自页面与真实15秒MockTransport响应；最终SQL核对保留的预留上界与收据。

## 保留的失败与修复

第一次：CDP固定15秒总等待短于页面30秒等待，尚无核验任务/attempt，见audit-before-send.json。修复使Runtime.evaluate客户端等待与其有界页面等待一致。

第二次：390px横向表格存在相同姓名，旧鼠标定位未可靠打开目标列；改为以投递ID定位DOM按钮、横向滚入视口后真实鼠标点击，保留失败DOM/截图/网络。

第三次：首个生成请求已成功发送，但held断言的JS正则斜杠转义错误导致漏判，失败DOM实际显示4013/3000。该请求最终结算，保留旧budget-matrix-20261010库/storage和audit-during-browser-third.json，不撤销、不重seed。另建上述成功run重验；未修改缓存结果或旧收据。

节点输入回归19通过、JS语法与审计模块Ruff通过。当前成功run保留可复查；旧upgrade-budget及首次matrix运行只停已核对身份的自有服务，数据库/storage全部保留。

本批闭合核验预算known/held/unknown/失败页面。关联企业问题的学生补证及真实生成建议/新版解释语义仍待验收；不能据此声称全目标完成。
