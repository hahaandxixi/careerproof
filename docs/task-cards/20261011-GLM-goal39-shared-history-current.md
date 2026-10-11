# 传智杯39：当前共用账号历史归因漏拒
Git根D:\jbcode\web ai\jianli，HEAD6618f90。Codex直接实测shared_history_attribution_impossible(["项目当前共用账号，历史记录无法区分作者"])为False；同源task_boundary_error对本人提交清单/从提交历史筛出本人署名/具名提交清单作为个人证据返回None；换成「项目当前共用账号，提交未区分作者」则True且拒绝。原因是历史记录词全行豁免把当前不可归属误判成历史已解决。

唯一写backend/app/tools/task_boundaries.py、新backend/app/tests/test_shared_history_current_boundary.py、docs/evidence/20261011-GLM-goal39/。36唯一写contracts和weekend测试，provider冻结；其他前端/启动器/旧样例/盲评分数/P2全部不动。
先落最小红测试，再窄修区分「当前仍无法归属的提交历史」与「以前状态且已经解决」。不要把所有历史词删除后 blanket 拒绝旧描述；不改33原18测试断言。保留独立具名分工证明/明确待核验的合法新证据路径，不把来源不可见当已解决，不声称任意语义保证。否定、条件、旧事实与当前事实同句混合须检查范围，只有旧描述且无当前不可归属不得误拒。
运行本模块目标及task_boundaries受影响，纯函数/mock不DB/模型/服务/安装/联网/.env/Git提交推送，不改其他任务源码。原始失败每轮保存、最终diff/hash、自审和未验证项一屏交棒。红绿之后收敛结束本goal，不为烧额度任意长文。
