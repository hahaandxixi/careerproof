# 传智杯35 /goal：启动记录与失败诊断可靠性

Git根D:\jbcode\web ai\jianli，免费Weekend Build Flash/最高；依据32审查。F3是未来耦合，不能写成当前已复现失败；不要用exit终止调用者。F2真实DB可用性与启停页验收由Codex另定范围，此目标不自动启停DB。

唯一写scripts/local-runtime.ps1、Start-Local.ps1、Stop-Local.ps1、新增scripts/local-launcher-recovery.test.ps1、docs/evidence/20261011-GLM-goal35/。Start-Demo与已有tests只读。33后端AI、34私人草稿不重叠。源码变化需先读实际HEAD并记录hash。

持续完成复现→修复→目标/受影响测试→自审修正→原始证据：

1. 自有processes.json持久写改为同目录临时文件原子替换，失败保留先前完整记录；拒绝非预期路径/reparse，读损坏或不完整记录明确显示文件位置、不得把损坏当作无运行自动删除。读后validate所有根身份再停止任何进程，不弱化Started/命令/后代边界。用全mock进程与自有无敏感scratch证明首次写、替换、写入失败旧记录保留、坏JSON/缺字段均不触发Stop-Process。
2. 后端复用digest覆盖现行迁移目录和alembic配置（按实际目录名，不猜路径），文件顺序稳定；内容变更失效，测试/无关scratch不影响。缺失与新增迁移也要可判断。不要执行迁移或修改DB。
3. 启动catch中的清理失败不能掩盖原始错误；保留原错误并附清理警告。不得为清理扩大kill范围或删损坏清单；释放/重取锁逻辑不削弱。用实际helper/脚本抽取安全测试缝注入，不照抄业务逻辑当测试。保持外层错误退出语义和finally恢复环境。

允许纯PowerShell AST/自有offline文件与全mock进程探针；现有local-runtime.test脚本的短命自有Node子进程可运行，但禁止任何真实网站helper/服务/容器/端口进程/现有锁/现有manifest、密钥/业务库操作。先原始红测试后最小修复；跑新测试、现有local-runtime.test.ps1与local-build-cache.test.mjs、AST和diff检查。原失败输出单独保留。

完整原始命令/输出、源码hash、自审/未验证项、一屏交棒。Codex独立复验、真实启停与Git提交。禁止联网/安装/.env/真实模型/外发/全量清理/kill端口/P2/Git提交推送/个人套餐；越界文件先说明，不自行改。
