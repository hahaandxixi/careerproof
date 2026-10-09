# Docker恢复复查

2026-10-09 Asia/Shanghai。旧start79334/ps89484句柄均已Unknown process id；系统Get-Process也未发现Docker Desktop/backend进程。确认旧启动已停止后，按用户既有授权仅尝试一次Start-Process Docker Desktop.exe（Hidden），启动PID459068/17:55:53。

新ps首次退出1（LinuxEngine命名管道不存在），随后新观察CLI句柄96044等待无输出。此等待不代表引擎健康；5432此前TCP探测timeout。

17:56:44本地backend日志GET /error再次确认：initializing Inference manager，dockerInference临时对象无法被系统访问，listener路径语法错误。界面异常操作只有Quit/Reset to factory defaults；没有点击任何恢复出厂操作，没有删除临时对象、数据或容器。新backend447696/458012与Desktop459320等存在，但后台已报告启动异常，不能把进程存在当作PG就绪。

当前阻碍仍是同一Docker临时对象系统访问故障。需用户恢复Engine running后，再实际验证docker ps/5432和专属PG；保留数据库和容器。旧句柄移除不等于旧日志被修复。不再次循环启动，不把当前预算PG/8项硬停或独立复跑标为通过。
