# 传智杯32：启动脚本失败恢复与所有权审查

Git根D:\jbcode\web ai\jianli，ff0c170；Weekend Build免费Flash/最高，禁止个人套餐。唯一写docs/evidence/20261011-launcher-reliability-audit/和自有临时探针，所有启动脚本/测试/正式清单只读；不启停任何真实进程/容器/服务，不调用数据库。

读Start-Demo.cmd/ps1、Start-Local.ps1、Stop-Demo.cmd、Stop-Local.ps1及scripts所引用必要辅助；结合20261010-startup-launcher/README.md和相关现行测试。检查依赖自动选取、源/lock变化后的缓存、BuildOnly/Rebuild、持久锁与失败释放、PID复用/开始时间/子进程所有权、路径空格/中文/reparse、失败退出码传播、运行记录不完整/日志可定位。

只报告实际可复现代码问题，现行已验证不重做；可做PowerShell语法/自有离线模拟（不能启动helper/service，不能碰真实锁、.tmp运行清单、用户资料），保留精确命令和未验证项。拒绝为过测试放宽守卫，不建议杀端口/广泛清理或总是重构建。

交付audit.md：具体触发/期望/实际、file:line、风险、最小修复文件及正反例；manifest源hash与原始输出，一屏交棒。禁止源码/测试修改、Git操作/推送、联网/安装/模型、文件清理和P2。允许读取本地脚本与合成证据，这是客户端协作范围。
