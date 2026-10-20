# Provider接线与来源校验：限定收尾

完成本轮指定收尾，未扩展功能，未暂存/提交/推送；没有真实请求、启停服务、数据库或依赖操作。

## 精确修改

- `backend/evals/bounded_evidence_smoke.py:184`：Agent回执checkpoint抛异常时先锁定stopped、记录receipt_checkpoint_failed与receipt_persistence_failed，再抛出停止异常；合法usage不能替代持久化成功。
- 同文件`:420`：在本批执行器的规划/分析包装层捕获HTTPStatusError，记录provider_http_400/401等停止原因及状态码。生产provider.py和生产降级策略未改。
- 同文件`:518`：最终任一保存目标失败，抛明确SmokeStopped，CLI非零退出且不打印成功摘要，不返回伪装已保存的报告。
- 新增`backend/app/tests/test_agent_smoke_hard_stop.py`：真实DeepSeekProvider＋真实workflow＋MockTransport的执行器回归，不用伪workflow替代。
- 两份人工说明改为先统一rubric、再独立核对输入/引用/模型原文；隐藏参考答案、实现方判断、助手初查及其他评审结果。同步直接链接的next-human-and-live-plan.md及当前授权说明中的同一句顺序。
- 当前agent-live-preflight-20261020.json升为v2，刷新原6个源码哈希；当前授权MD同步包哈希/源码/新增测试哈希和停止条件。原v1 JSON与授权MD原始字节保存在historical-package/，未修改10/18旧授权包或claim。

`closeout-only.diff`由本轮修改逆向重建的原文件与开始时SHA256精确核对后生成，只展示本轮补丁，不将此前接线改动冒充本轮新增。

## 红→绿与实际模拟POST

首次新增6例全部失败，`red.raw.out`/exit1保留；随后仅跑4个直接相关离线套件，**51 passed，exit0**（green.raw.out）。

| 场景 | 修复后POST数 | 结果 |
| --- | ---: | --- |
| 第一例合法usage后回执写失败 | 1 | 批次stopped、首例hard_stop/accepted=false，不运行AG-02/03 |
| 最终日志持续写失败 | 1 | 独立子进程非零退出、明确final report persistence failed，无成功摘要；旧文件仍started，未声称新结果已保存 |
| HTTP400/401，规划阶段 | 各1 | provider_http_400/401；不运行后续案例，不记普通降级或结构通过 |
| HTTP400/401，分析阶段 | 各2（先一次正常规划） | 同上；不运行后续案例 |

回执失败的首轮红测为执行器级；最终日志失败后来加强为真实子进程退出校验。全部POST由MockTransport拦截，**真实外部请求0**。

命令：

```text
python -m pytest app/tests/test_agent_smoke_hard_stop.py app/tests/test_agent_evidence_smoke.py app/tests/test_bounded_evidence_smoke.py app/tests/test_durable_provider_hooks.py -q --basetemp=.tmp/agent-closeout-green-20261020 -p no:cacheprovider
python -m ruff check evals/bounded_evidence_smoke.py app/tests/test_agent_smoke_hard_stop.py app/tests/test_agent_evidence_smoke.py app/tests/test_bounded_evidence_smoke.py app/agents/evidence_workflow.py
python -m evals.bounded_evidence_smoke --agent --packet ../docs/evidence/20261019-agent-boundary/agent-live-preflight-20261020.json
```

环境：backend/.venv-dependency23；以上均在backend工作目录。Ruff与离线包校验exit0（各有原始日志/exit）。首次Ruff一行超长已修；一次日志包装命令因工作目录错误未启动pytest，纠正后才得到51通过。不运行全仓测试。

## 保留与未验证

- 三例输入JSON与v1完全相同；人工表自M01起全部正文与HEAD一致，15处待填写未动；**人工0/3、humanReview仍null**。未改真实模型原文。
- 与开始时相比，已有evidence_workflow.py、test_bounded_evidence_smoke.py、test_agent_evidence_smoke.py字节保留；provider.py及其余生产源码与v1包哈希一致。
- 未做真实HTTP400/401、真实磁盘满/断电/进程强杀，不证明两份日志写入原子性或崩溃恢复；本轮证明的是注入持久化异常后的批次停机和退出行为。
- 未发Agent真实批次，未申请新授权或刷新价格；当前包仍待授权。旧10/18三次授权未复用。

## 未提交文件

本轮：执行器、新增hard-stop测试、两份人工说明、next-human-and-live-plan.md、当前授权JSON/MD及本证据目录均未提交。既有evidence_workflow.py、test_bounded_evidence_smoke.py、agent-boundary/README.md、使用与启动.md、当前接力.md、JobDetailView.tsx及未跟踪的旧Agent测试等成果保持；不替其提交。完整状态见status-after.txt，开始时状态及哈希见baseline.json/status-before.txt。
