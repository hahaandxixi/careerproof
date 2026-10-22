# Windows解析子进程：实际退出后再回收

## 已复现问题

只验证`Popen.poll()/wait()`不足以证明实际解析器退出。Windows虚拟环境`python.exe`可启动另一个解释器；旧接受副本的Popen PID320364已退出，但真实解析器PID340204仍未成为signaled。保留的native HANDLE创建时间为134371385211254891，进入`cleanup_attempt(worker_exited=True)`时`WaitForSingleObject(handle,0)`返回WAIT_TIMEOUT、partial目录已存在，见`cancellation-red-native-observation.json`与`cancellation-observed.raw.out`。测试在删除前主动断言失败，未让其删除仍可能写入的目标。

首次探针另有两个自身问题，均留档：目录外pytest未选项目asyncio配置；将venv启动器PID等同实际worker PID。修正了探针，不把这些自身错误当业务缺陷。之后的真实native退出断言仍失败，因此才修改生产代码。

## 最小修复与边界

- `task_runner.py`：Windows为本次子进程创建独占临时身份目录；启动器仅传本机路径和随机nonce。父进程拿到实际PID/创建时间后，打开并验证对应内核进程对象，持有句柄后才原子写ack。停止时kill/wait启动器，再terminate/wait这个实际进程句柄，确认退出后返回，finally清理控制文件。
- `isolated_worker.py`：身份发布与父进程ack均发生在pickle反序列化/解析函数之前；发布失败、ack错误或超时都不能进入解析。stdin/stdout私有pickle协议保持原样，不执行上传源码。
- 新`worker_identity.py`：只用标准库和Win32 API；验证nonce、PID和native创建时间，持有process HANDLE避免PID重用。不是查找或杀死同名进程，不用CIM、外部依赖、ACL修改或全局进程清理。
- 开始时被取消且尚未ack，子进程不能解析材料；启动等待有界。已有ack后，父进程必持有实际句柄，因此取消/超时不会只回收启动器。POSIX使用原命令及原有协议，不使用Windows身份机制。
- 总控另将业务回收改为本次尝试+实际marker PID保护；这不是本子任务修改，避免缺少确认时盲信`worker_exited=True`。

## 接受副本实际验证

源码：`backend/.tmp/core-acceptance-20261022/source/backend`。来源与hash见`worker-identity-source-hashes.json`；最终portfolio SHA256 `8e14f951c3d7e6468b348a4fee37f633fb91a3061587f7b077c2546ecaad7886`。

`test_cancel_cleanup.py`放在证据目录，不在常规CI测试收集范围；它显式复用已存在的`app.tests.test_portfolio_api`临时SQLite fixture。走实际上传HTTP路由/仓储、实际`execute_project_scan_task`、实际Popen隔离worker和实际cleanup；仅把可信解析函数换成在子进程中写partial并阻塞的测试函数，构造可靠中断时点，不伪造进程退出。

- 取消：保留真实worker HANDLE+创建时间，确认进入cleanup之前该对象已退出；随后只删除该尝试目录，`CancelledError`透传。
- 超时：同样先确认实际worker退出再删除；任务记录failed，错误包含“超时”。
- 两种情况的原始ZIP保留，另一个已成功版本的真实ProjectFile记录与文件哈希仍一致；不只是保留一个伪造成功目录。
- 原先一次失败的`test_orphan_recovery_protects_live_workers_and_saved_sources`在最终接受副本精确重跑通过；其早先失败原因未得到进一步证实，不把mtime假设当已知根因，也未据此改回收规则。

命令（工作目录为上述接受backend，PYTHONPATH同接受backend与该resources目录）：

```text
python -m pytest -c <accepted-backend>/pyproject.toml <resources>/test_cancel_cleanup.py app/tests/test_material_resources.py::test_orphan_recovery_protects_live_workers_and_saved_sources -q -s --showlocals -o cache_dir=<owned-tmp> --basetemp=<owned-tmp>
```

结果 **3 passed，exit0**，5个既有SWIG弃用警告，见`cancellation-green.raw.out`。逐案例实际PID、native创建时间、退出码、回收结果、原始及成功材料保留见`cancellation-result.json`和`timeout-result.json`。

常规相关测试另为 **28 passed，exit0**：`test_worker_identity.py test_material_tasks.py test_document_ocr.py`；覆盖正常结束、无ack/身份发布失败、nonce与创建时间拒绝、POSIX分支命令、真实超时及OCR边界。运行机器是Windows；“POSIX分支”通过模块级平台替身验证，并不冒充Linux机器实测。所有4个源码/测试文件Ruff通过。后续整体CI以总控最终接受副本结果为准，不累加批次数量。

本轮外部AI关闭、provider mock、JWT为固定合成测试值，数据库为fixture专属临时SQLite；无正常站/数据库、依赖安装、网络请求、Git提交或权限变更。子进程全部退出、native句柄关闭、临时控制目录清理；测试数据目录保留作证据。不以本探针替代所有崩溃、机器断电或公网运行验收。

## 复核追加：重复取消不能截断teardown

独立复核发现，原finally中`await process.wait`仍可被第二次`task.cancel()`打断，跳过实际worker join、句柄关闭及身份目录清理。业务侧marker保护避免误删，但不能以此声称无残留。新增确定性内存控制流测试在启动器wait闸门阻塞时发出两次取消，原实现红（`second cancellation interrupted teardown`），见`second-cancel-red.raw.out`。

修复仅涉及`task_runner.py`：整个teardown放入独立asyncio任务，通过shield循环等待，重复取消只延期，不传递给清理任务；清理完成后保留原始第一次CancelledError。正常结果、原异常及timeout cause不因清理变成成功。新测试在第二次取消后确认调用仍未结束，释放wait闸门后断言实际worker join→handle close→identity cleanup顺序完成，最终仍抛出第一次取消的原文。该测试是内存控制流证明，不冒充native进程实测。

`test_worker_identity.py test_material_tasks.py`最终**18 passed，exit0**（`second-cancel-green.raw.out`），目标Ruff通过。先前native取消/timeout证据对应第一次进程身份修复；重复取消修复后的接受副本及整体CI由总控更新并复验，不能把旧源码证明直接当成最终完整范围。

## 复核追加：私有身份/ack文件短暂读拒绝

另一执行端实际重复12次捕获一次失败：子进程在`await_parent_admission`读取本次独占的`worker.ack`时抛出`PermissionError(Errno13)`，导致解析尚未开始便异常退出；该诊断不证明业务材料损坏。

最小修复新增共享`read_identity_record`：仅将`PermissionError`或`FileNotFoundError`视为“暂未读到”，父进程身份等待与子进程ack等待继续在各自原有deadline内重试；不扩大deadline，不改ACL，不把异常当作已获准。读出的损坏JSON、非对象、错误nonce/身份仍立即拒绝，不将这些错误纳入可重试范围。

新增确定性红例四项失败，见`private-read-red.raw.out`；修复后`test_worker_identity.py test_material_tasks.py test_document_ocr.py` **36 passed，exit0**，见`private-read-green.raw.out`。父进程两类瞬时读异常通过真实控制流内存测试恢复；子进程两次瞬时失败后第三次恢复，永久拒绝不超过原10秒虚拟时钟deadline，损坏JSON及旧ack继续失败。三文件Ruff通过。该结果不是12次真实进程诊断的重复统计；最终接受副本与整体CI仍由总控更新、绑定版本后核对。
