# 全链路批次 AI 离线契约基线

执行者：Codex，2026-10-04；代码基线 main@b3611fa。命令（backend目录）：`.venv/Scripts/python.exe evals/run_task_plan_quality.py --output .tmp/task-plan-quality-20261004-e2e-baseline.json`，退出码0。

原始标准输出：`{"caseCount": 9, "sourceExactCount": 9, "referenceContractAccepted": 9, "contractExpectationMatches": 13, "contractProbeCount": 13, "replayedModelOutputs": 0, "independentSemanticReviews": 0, "semanticQualityPassRate": null}`。

9/9来源精确、13/13契约期望匹配。样例是作者编写的合成契约探针；0真实模型调用、0已保存模型回放、0独立语义复核，语义质量通过率未知。详细JSON在本地ignored输出路径，不能把此基线称作AI建议有用性通过。后续由ZCode执行失败样例整理，Codex审核事实和引用边界，再安排独立人工语义评价。
