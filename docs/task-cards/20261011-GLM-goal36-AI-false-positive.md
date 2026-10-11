# 传智杯36：AI守卫误拒修复与独立边界用例

Git根 D:\jbcode\web ai\jianli，HEAD ef29532。继承33现有未提交成果，不覆盖不重做。Codex已独立复现：plan_deployment_outcome_error 对「源码存在说明文件已经上传，实际运行仍待核验」和「源码存在证明材料可定位，部署结果需要另行核验」返回source-presence-proves-runtime错误。第一正则分支未限定运行结果，存在真实误拒。

唯一写入：backend/app/agents/contracts.py、backend/app/tests/test_weekend_plan_boundaries.py、docs/evidence/20261011-GLM-goal36/。其他33/34/35文件冻结，Codex不同时写这些文件。
先保留原18用例，新增最小红测试，修复到必须存在明确源码存在与部署/运行结论因果，合法材料定位/上传、否定、条件、等待核验应放行；真正因果错误仍拒。检查否定范围不能让另一独立错误断言逃逸。继续有界变体测试与自审，不把词面守卫当语义保证。
运行目标及相关合同/任务边界测试，原始命令输出、失败各轮、最终源码hash、diff、自审与未验证项落本证据目录。一屏回报交棒。
不改provider、task_boundaries、检索/评分/盲评标签/P2/预算/快照；不真实模型、联网、数据库、服务、安装、.env、Git提交/推送。达到可审查结果后结束本goal，不无限堆测试消耗额度。
