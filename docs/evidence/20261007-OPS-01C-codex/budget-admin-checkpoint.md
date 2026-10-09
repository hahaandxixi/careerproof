# 2026-10-09 预算请求与管理员审计检查点（PG待恢复）

本批Codex唯一写attempt接入、预算服务及新增两个测试文件。没有向传智杯20发送指令。原36通过/3PG跳过的SQLite检查覆盖管理员8、实际provider/observer5、容量服务14、attempt内核12；其中8+5+14+12=39，3真实PG锁测试跳过。原始budget-admin-final-sqlite.raw.out。此前管理员6项验证后新增可信旧收据接续/无效收据拒绝两项；最终Ruff四文件通过。PG未复验，不称阶段签收。

请求通路已经实际MockTransport抓包：初次请求批准300，可信503消费7输出后重试批准293，总可信24/14、恢复2/0；无usage的503占用原300上界，第二次准入拒绝，无第二HTTP。prepare和intent跨午夜足额时持久日转移且wire仍300；新日已有报告槽时not_sent关闭、旧日released、0HTTP。六个并发book只一份账目；SQLite验证不替代PG并发锁。

管理员能力是内部事务服务，尚无公开操作入口或业务启用动作。每次检查新鲜ADMIN且active，理由/操作id/实际整数非负校验；unknown容量调整只追加审计，不产生receipt或ledger；幂等重放不覆盖原审计，改参数拒绝，停用管理员无法重放。可信迟到收据经实际AttemptService.receive/book结清12/7，原20/30政策调整审计保持，不重复退款。

activate先管理员短锁和持久闸门锁，排空外部活run，严格接续现代attempt，并按源receipt/原日/身份/上界核对容量。旧外部终态run无物理来源仍拒绝，不因FAILED/COMPLETED或旧聚合有部分费用就归零。未能审计的旧未知保持闸门关闭，不伪造旧attempt。初次激活写实际清单摘要和操作者/时间/理由，已启用重放不覆盖首份证据。只在自有夹具模拟激活，业务/closure不切换。

## Docker真实阻碍

PG初始化错误来自Docker Linux engine pipe不存在。随后启动已有Docker Desktop，CLI79334仍等待；ps89484、status66687也仍等待，没有重复启动或重置。只读当前日志确认2026-10-09 09:01:21后端崩溃，原因是初始化Inference manager时无法访问Docker/run/dockerInference AF_UNIX临时对象，日志随后显示all local engines stopped。不能把这些CLI还活着等同于引擎正在成功启动。

原对象0字节、Archive/ReparsePoint，创建2026-10-06；fsutil只读查询Error1920。尝试严格同目录改名保留到dockerInference.stale-20261009，系统拒绝“无法访问此文件”；未删除任何对象、卷或数据库，未禁用安全设置。已请用户恢复Docker至Engine running，后台继续离线开发。系统拒绝改名不是自动审批拒绝，不虚构审批理由。

下一步：Docker恢复后先复核原CLI句柄/引擎健康、以新日志重跑专属PG和最高风险；两条外部workflow构造器仍须接入SharedBudgetService并补预算端到端夹具；剩余跨链真实HTTP并发、收据/账目commit故障、管理员PG并发、两链真实进程四窗口和最后依赖权威公告审计。当前为本地有界检查点，完整OPS未完成，未推送、安装、升级、部署或真实模型调用。
