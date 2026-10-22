# 视觉模型排队超时测试边界

## 实际问题与范围

总控本次完整接受副本检查1576通过、1失败、88跳过。失败是原视觉用例把整个HTTP请求包在1秒watchdog中；堆栈停于ASGI接收流，不能据此定位超时发生于认证、原图检查/线程调度、预算SQL、模型队列或最终持久化中的哪一步。因此没有认定视觉生产逻辑失效，也没有修改业务源码。

原完整失败文本提取保留在`original-full-failure.txt`，对应元数据见`baseline.json`。同一原用例仅单跑一次通过（`original-single.raw.out`），没有循环重跑来挑选成功。

## 改动与增强后的验收

仅改`backend/app/tests/test_visual_evidence.py::test_visual_workflow_timeout_includes_global_model_queue`，并逐字节同步总控接受副本。现在分别观察请求到达模型队列与最终返回，5秒watchdog只防测试死锁，不作为模型预算断言。真实预算仍为0.05秒，未调整生产或测试配置。

测试通过模块局部asyncio命名空间调用真正的asyncio.timeout，记录公开Timeout对象；不修改全局asyncio、不伪造到期。零容量真实Semaphore被持有，实际acquire因取消退出，退出时Timeout.expired()必须为真，且返回后仍为真。模型工厂仍必须从未被创建；返回workflow_timeout、FAILED任务、零AiUsageLog、原图原始字节不变的关键断言全部保留。

这不是简单把1秒放宽到5秒：若取消源只是watchdog、生产预算被删除或移到队列之后，真实Timeout记录/队列取消到期断言无法满足。

## 结果及反证

- 接受副本整个视觉模块：48 passed，0失败/跳过，exit0，10.42s。`module-green.raw.out`、`module-green.xml`。
- 独立临时源码副本删除生产timeout：1 failed，exit1；`mutation.raw.out`、`mutation.xml`、`remove-timeout.diff`。
- 同一独立副本把timeout移到已获取队列之后：1 failed，exit1；`move-mutation.raw.out`、`move-timeout-after-queue.diff`。
- 两个突变均因队列进入后没有创建所需真实Timeout（0 != 1）失败，并非等5秒watchdog冒充预算失败。突变仅在`backend/.tmp/visual-timeout-mutation-20261022`，未改共享业务源码。
- 目标Ruff通过，见`ruff.raw.out`。测试与未改生产文件哈希、接受副本一致性见`final-identity.json`。

命令均使用既有`backend/.venv-dependency23/Scripts/python.exe`，cwd为总控接受副本backend或上述独立突变目录，PYTHONPATH明确指向对应backend；APP_ENV=test，AI_PROVIDER=mock，AI_EXTERNAL_ENABLED=false，CAREERPROOF_TEST_DATABASE_URL为空。pytest使用各自独占的根.tmp basetemp/cache，ASGI+临时SQLite和MockTransport，无正常库、服务、真实模型或网络请求。

本次没有重跑全量，最终整体验收由总控执行；48项不能当作候选全量通过。原失败的精确慢阶段仍未确定，本修复使排队预算检查不再以整个HTTP耗时替代。
