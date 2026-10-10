# 传智杯30：AI补证建议来源一致性与可执行性诊断

Git根D:\jbcode\web ai\jianli，基线ff0c170；Weekend Build免费Flash/最高，禁止个人套餐。读新GOAL与本卡，不重复全仓研究。唯一写docs/evidence/20261011-AI-plan-consistency-audit/；生产、测试、既有评分/样例与正式文档只读。

将backend/evals/quality-blind-plan-review-input.json的8例草稿和docs/evidence/20261010-AI-blind-plan-review/review.json、codex-review.md逐个送入或映射当前contracts.py/证据上下文，比较结构接受与独立模型失分，不调用provider、不运行样例源码。只读相关provider.py提示词和evidence_workflow.py修正/降级流程；判断哪些失分可以由可靠结构/来源规则处理、哪些只能提示人工核对，不能关键词匹配冒充语义证明。

交付：每例“生产契约是否接受/为什么、来源状态、失分、误判风险”表；最重要3处可复现差异及精确file:line；下一有界实现的允许文件、正反例、保守拒绝/修正/fallback方案、会影响的既有行为。尤其共用账号归属不能筛出本人署名、已有源码不能等于部署/稳定运行、lru_cache写失效机制未定义、Redis键设计遗漏；不要把独立评分当生产真实输出。

允许运行自有纯离线探针，通过真实现行contract/上下文，完整命令/结果/源hash保存；禁止改任何源码/测试/旧标签/评分、数据库/服务/浏览器/联网/安装/真实模型/推送/P2。分析完写audit.md、manifest.json、必要raw.out，一屏交棒。避免笼统建议或仅重复已知盲评分数，必须给当前生产路径与可复现证据。
