# 页面补验期间的独立只读核对

2026-10-06。ZCode传智杯14仍是合成夹具唯一写入者；Codex未执行写数据库或页面修改。

实际命令：以限定 `cp_e2e_closure-20261005` 的本机合成连接变量运行 `backend/.venv/Scripts/python.exe docs/evidence/20261005-PRODUCT-01-codex/page-invariants-readonly.py`，输出见 [page-mid-invariants.raw.json](page-mid-invariants.raw.json)。脚本验证事务为READ ONLY并使用REPEATABLE READ。

与首验前 [page-before-invariants.raw.json](page-before-invariants.raw.json) 比较：applications 3、application_events 9、notifications 12、ai_usage_logs 0、analysis_tasks 11、match_reports 8，六表全部完整行内容SHA256相同；三条固定增长绑定的SHA256也相同。因此目前草稿页面测试没有改变原投递的企业回复、引用、通知内容或既有分析输入，结论强于仅比较计数。

脚本追加四个固定报告的报告行、全部match_items、关联analysis_task分别的哈希，供允许创建新Mock报告的S9之后逐项比较旧行。新增报告会改变全表哈希，届时不能把新增报告归因于草稿操作，也不能用全表计数变化掩盖旧行变化。

此项仅证明本次采样时的不变量。S6账号切换竞态、S8失效注入、S9第三方来源、S10复制补验与Codex独立页面抽验仍未签收；不据此宣布PRODUCT-01完成。
