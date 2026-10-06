# 当前隔离进程身份复核

2026-10-06 Codex实际CIM/监听端口只读核对：

- manifest backend PID57440仍在，路径backend/.venv/Scripts/python.exe，创建时间21:31:38本地（13:31:38Z），命令uvicorn app.main:app --host127.0.0.1 --port8001。
- 8001监听PID55380的ParentProcessId=57440，创建时间同21:31:38；这是venv启动的实际Python子进程，命令同uvicorn/8001。父子关系与开始时间均已实测，不是无关服务。
- 3001监听PID53292与manifest一致，项目内next start -H127.0.0.1 -p3001，创建21:31:41。
- manifest runId closure-20261005，数据库cp_e2e_closure-20261005，AI_PROVIDER mock，AI_EXTERNAL_ENABLED false；未重新启动或改变环境。
- 独立只读实际库基线page-before-invariants.raw.json为0015，3原投递/9事件/12通知/0用量，三固定增长任务hash已捕获。页面runner仍须通过合成API归属验证实际服务的数据身份。

父manifest PID与实际监听PID不同本身不是阻断。后续停止仍须同时核对父子关系、创建时间和命令，仅处理本轮自有进程；本记录不是允许杀无关进程的依据。