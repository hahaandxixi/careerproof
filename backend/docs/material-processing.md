# 材料处理与任务恢复

项目上传接口继续使用 `POST /api/v1/projects/{id}/versions`，支持 ZIP 源码（30 MB）及 PDF、DOCX、TXT 作品文档（10 MB）。文档作品转成 `document.txt`，PDF 保留页码标签。DOCX 按顺序抽取段落和表格；空白或纯扫描 PDF 明确提示先做 OCR，不会保存为成功的空简历。当前不内置 OCR 模型。

所有预览接口均校验当前用户是否拥有材料，越权或不存在统一返回 404：

- `GET /api/v1/resume-versions/{id}/preview`：解析状态和带页码的简历分段。
- `GET /api/v1/project-versions/{id}/files`：文件 ID、相对路径、语言、大小、行数。
- `GET /api/v1/project-files/{id}`：文件正文及所属项目版本 ID。

阻塞的 PDF/DOCX 解析、ZIP 检查解压和文本处理在独立 Python 子进程中执行，不执行上传代码。调用方使用 `run_isolated`；内部 IPC 仅接收服务端生成的参数。Windows `uvicorn --reload` 使用 SelectorEventLoop，所以通过 `Popen` 和线程等待进程，兼容 Windows/Linux。超时或请求任务取消会终止并回收子进程，避免只把数据库状态改成超时、解析却继续消耗资源。

数据库任务使用 `PENDING → RUNNING → COMPLETED/FAILED` 状态流转。`claim_task` 原子抢占并生成新的 `run_token`，重复执行同一任务不会重复入库；完成时先以运行令牌更新终态，再在同一事务写入业务结果。迟到的旧令牌不能覆盖重试结果。材料重试继续使用原文件、原版本和原任务 ID；既有上传幂等键仍返回同一版本。

`retry_material_task(session, task_id, current_user)` 校验任务所有者、失败状态和原文件，提交排队状态后返回 `(TaskAccepted, callback, args)`，由路由交给 `FastAPIBackgroundTaskRunner`。通用 `reset_failed_task` 不提交事务，其他任务类型可在验证持久化输入后使用。

可通过环境变量调整：

- `TASK_CONCURRENCY=2`：每个 API 进程同时处理的后台任务数。
- `TASK_TIMEOUT_SECONDS=90`：每次隔离处理的硬超时秒数。
- `TASK_LEASE_SECONDS=120`：RUNNING 心跳过期秒数，默认每 10 秒续约。
- `TASK_PENDING_TIMEOUT_SECONDS=600`：遗留排队任务的过期秒数。
- `TASK_DISPATCH_INTERVAL_SECONDS=2`：数据库 pending 任务扫描间隔。
- `MAX_DOCUMENT_CHARACTERS=500000`：文档提取文字上限。

应用启动及后续扫描会接手数据库中仍为 pending 的简历解析、项目扫描和岗位匹配任务。原子 `run_token` 保证 HTTP BackgroundTasks 与扫描器并发提交时只有一个执行者。扫描器同时回收超过租期的 running 任务，把状态设为失败并提供可重试说明；不会终止其他进程仍正常续约的任务。数据库临时不可用时记录警告并在下一轮继续恢复。

当前为单机比赛规模设计：并发限额按 API 进程计算，不是分布式队列；推荐使用一个 API worker。失败解析的隔离输出目录可能保留，未被关联为成功材料；部署维护时可对未被 ProjectFile 引用的旧输出做保留期清理。
