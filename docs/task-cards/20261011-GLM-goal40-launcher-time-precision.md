# 传智杯40：真实Windows时间精度与临时清理所有权
Git根D:\jbcode\web ai\jianli，当前6410915。37已交付或收敛到交棒，先核对其终态/源hash，继承35+37成果，不重做全仓研究。

Codex独立只读实测本轮PowerShell进程102808：CIM CreationDate UTC ticks=639273191745370010；Get-Process StartTime UTC ticks=639273191745370012，相差-2（0.2微秒）。37声称内核时间微秒对齐不成立；Stop-ValidatedLocalProcesses逐tick比较CIM和GetProcess/manifest将误拒合法进程。不要用2秒/任意容忍隐藏风险：只将CIM比较规范化到其微秒表达精度；manifest与GetProcess高精度根身份、采样与停止前高精度身份仍需严格相同。注意不能用double除法精度损失；整数余数/DivRem，精确处理64bit大ticks。相差1微秒及真正PID复用仍拒，所有根预检先于任何停止。若发现跨接口舍入并非一致截断，先报告实际观察再定规则。

第二项：Save-LocalRunManifest使用CreateNew但catch仍无条件Remove-Item随机临时路径；若CreateNew失败，未拥有临时文件就不应清理外来对象。添加只在排他创建成功后才获得清理权的明确状态，不删除未知对象。新旧记录保存失败保护不放宽。

唯一写scripts/local-runtime.ps1、scripts/local-launcher-recovery.test.ps1、可新增scripts/local-launcher-real-identity.test.ps1及docs/evidence/20261011-GLM-goal40/；37同文件只有确认其结束才接手。不改Start/Stop消费者、36/39 AI或前端源码。

先红测试钉住真实ticks例与CreateNew失败无清理，再最小修复，mock覆盖1微秒变化/多根全预检/采样后高精度变化。补真实非业务进程只读CheckOnly/ValidateOnly验证（可对当前自身进程，用其命令精确标识，绝不Stop当前进程或任何业务服务；若必须启动短命子进程，仅独立nonce、自有进程且隐藏窗口，记录所有权，不能枚举批量杀进程）。真实停止专项由Codex实施，不扩大授权。
纯PowerShell/自有scratch，禁止DB/模型/联网/安装/.env/业务服务/容器/P2/Git提交推送；原始红绿/真实精度/源hash/diff、自审、未验证项一屏交棒，勿以mock绿冒充真实停止通过。
