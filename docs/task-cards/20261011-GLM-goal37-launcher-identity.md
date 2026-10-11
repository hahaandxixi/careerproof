# 传智杯37：启动记录与停止身份的独立风险修复
Git根 D:\jbcode\web ai\jianli，基线ef29532，继承35已有未提交实现，禁止清除重做。36唯一写AI合同；本任务唯一写scripts/local-runtime.ps1、scripts/local-launcher-recovery.test.ps1、本任务docs/evidence/20261011-GLM-goal37/。Start/Stop-Local若必须改先报告，本轮冻结。

优先复现两项Codex审查：
1. Save-LocalRunManifest先查目标/父目录，但固定 processes.json.tmp 不查reparse且Set-Content覆盖现有对象；scratch内做临时路径junction/符号链接/占用文件对照，证明不改链接外目标。改用同目录唯一自有临时文件、CreateNew或等价排他创建、只清理自有文件；目标原子替换使用可验证File.Replace/Move等Windows行为，不把Move-Item结果正常当掉电原子证明。不跟随reparse路径，失败旧记录保持；不要扩大到删除未知临时文件。
2. Stop-ValidatedLocalProcesses从CIM列出后代再用Get-Process采集当前startTime：期间PID复用可能被采信。mock注入CIM快照CreationDate与Get-Process当前StartTime不一致，应在任何Stop-Process前拒绝或安全跳过该非自有身份；根也须与manifest绑定。保留旧身份/CheckOnly边界，不能用模糊时间容忍放宽。所有根/后代做完整预检后才停止，失败不误停首根。

先新增真实helper最小红测试再最小修复，跑新旧PowerShell测试/build-cache/AST，自审原始输出hash与diff一屏交棒；不得重写现有测试使问题通过。纯mock进程和nonce scratch测试，不启动或停止真实服务/容器，不操作业务库/storage/.env、不安装/联网/真实模型/提交推送/P2。涉及真实停止由Codex独立接手。证据声明能证明的范围，无法证明原子保证要说明。
