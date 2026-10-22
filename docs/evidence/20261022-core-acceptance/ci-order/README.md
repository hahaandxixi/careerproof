# 单次全量SQLite失败：解析worker诊断

本组只读生产源码，诊断总控接受stage全量结果中的一个失败，没有修改或放宽原测试。原完整输出由总控保留为`unit-before-repeat-cancel.raw.out/xml`（1568 passed / 1 failed / 88 skipped）。

失败点是`test_job_recommendations_rank_owned_material_evidence`调用`upload_materials`时project_scan worker异常退出，尚未执行推荐或排名断言。错误为4025，约0.4秒结束，原worker stderr被DEVNULL丢弃，不能从这次历史输出断言更具体原因。

- 单独原测试：1 passed，`target.raw.out`。
- 首次诊断Popen改成函数导致asyncio在收集前无法继承该类；这是诊断器自身错误，保留`target-repeat.raw.out`，没有执行产品测试。更正为原Popen子类后单例通过，`target-repeat-2.raw.out`。重复同一node参数被pytest去重，未冒充12次通过。
- 采用额外autouse参数化fixture真正执行12例、保留原断言，并仅记录私有worker stderr/退出码。结果**11 passed / 1 failed**，`target-repeat12.raw.out`。
- 35次真实worker启动中，第5次迭代的resume_parse进程退出码1、stdout0。其完整stderr明确为`worker_identity.py:96`读取`worker.ack`时`PermissionError: [Errno 13] Permission denied`，尚未反序列化或解析材料。其余worker正常返回。见`worker-repeat12.jsonl`。

因此这不是预算、推荐排序或测试顺序导致的业务断言失败；已重现私有Windows身份握手文件读取失败。文件读取受拒的底层原因（例如短暂sharing/扫描）尚未独立证明，不能据此改ACL。建议在既有启动期限内窄重试PermissionError/FileNotFoundError；不放行不匹配/坏nonce或损坏JSON，不延长期限、绕过确认或重发模型。

源文件修复归总控。本目录的`capture_worker_case.py`是可重跑诊断器，必须从接受stage/backend运行，明确关闭外部AI、独立basetemp和日志。它只进行过程内Popen替换，不修改共享工作区或已保存材料。读取原失败时间±15秒的Windows Python应用崩溃记录无相关记录，不据此宣称发生或排除native crash。

## 最终接受源码复验

总控完成窄范围读取重试修复并通知stage复制后，以相同诊断器及原API测试断言实际运行12次：**12 passed，exit0，30.43秒**。恰好36个私有worker物理启动全部退出码0、stderr为空，12个迭代均实际执行，见`target-final12.raw.out`、`worker-final12.jsonl`与`final-repeat-summary.json`。这不是把重复node参数被去重的单次通过乘以12。

运行开始记录的`task_runner.py`、`worker_identity.py`、`isolated_worker.py`三份SHA256与总控`accepted-source.json`、stage当前字节逐项一致（值见summary）；没有诊断端源码修改或stage拷贝。修复前11通过/1失败及读取PermissionError原文保留，不改成“从未失败”。该有限复验支持已复现握手读取问题得到修复，不替代总控的完整SQLite、PG、hard-stop或真实用户验收。
