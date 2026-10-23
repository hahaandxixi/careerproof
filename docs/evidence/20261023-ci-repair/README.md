# 10/23 CI修复与运行版本核对

修复基线5a6b9c8，接受源码60f4839254c2ac1db3d01e87587e4c26bed666ad。原失败run39877034041的前端成功、SQLite13失败、PG主集141通过而hard-stop8失败，不能以旧本地全绿替代。完整原始日志保留在根backend/.tmp/ci-39877034041-{unit,pg}.raw.log；完整nodeid摘录见integration/original-*-failures.txt。

## 修复与保护条件

A：evidence_policy.md和input_budget.py的离线哈希来自CRLF，但Git提交为LF。为两个路径明确text eol=lf，仅刷新当前offlineOnly夹具两个哈希；八份源码内容、生产字节校验、历史授权/claim不改。真实内容变更仍拒绝。KeyError guard是前置校验失败导致finally引用未建guard的连带结果，不是服务端降级。红13失败/12通过，绿27通过；autocrlf true/false八份文件16/16匹配。

B：Linux直接worker与Popen PID相同，父进程应为pytest；Windows启动器模式worker的父进程才是Popen PID。保留nonce、task/schema、创建时间、HTTP计数、精确进程kill/wait、数据库账本和恢复断言。新增拒绝无关/兄弟进程及退出启动器测试，未新增skip/xfail。红2失败/6通过，Windows身份/资源35通过，真实停止8通过。

## 集成验证

同一接受工作树backend/.tmp/ci-integration-20261023：
- SQLite整体：{'total': 1681, 'failed': 0, 'skipped': 91, 'passed': 1590}。
- 严格PG：{'total': 141, 'failed': 0, 'skipped': 0, 'passed': 141}；真实hard-stop：{'total': 8, 'failed': 0, 'skipped': 0, 'passed': 8}；JUnit门禁exit0。
- Ruff、独立空库完整迁移与模型对齐exit0，生产前端build exit0。
- 精确命令、退出码及JUnit见integration/unit-commands.json、pg-commands.json、*.xml；迁移日志另列。跳过原因在unit.xml，不与旧结果相加。
- Windows3.12.14、Node22.23.1，复用现有依赖；外部AI关闭。Linux最终结果须以[main实际CI](https://github.com/hahaandxixi/careerproof/actions?query=branch%3Amain)对应提交为准，不能把Windows通过写为Linux通过。

## 实际预览

[运行记录](integration/runtime.json)：3136前端/8114API从接受工作树启动，55445/cp_product_polish_20261022专属合成PG，独立storage。此次补丁只改测试、离线夹具和Git属性，生产前后端与5a6b9c8逐文件相同，构建可复用。实际浏览器打开了原任务3b9ba85b…，正确林舟账号HTTP200、另一学生404；未重建任务/改权限。页面截图及DOM、实际进程、运行文件SHA在integration。这里只核对已有任务，不声称新增补证链路或真实离窗验收。

原3132等端口未运行，不能代表最终版；本轮未修改正常站、正常库、模型、历史claim或P2。48份原已跟踪修改的既有内容保留；接力仅增加本轮状态说明；未跟踪成果未清理。源码包/PDF/视频、真人语义及首次使用、真实离窗/缩放/系统减少动效仍是后续事项。
