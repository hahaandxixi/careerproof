# 传智杯25：离线AI三维评测实现

实际Git根 D:\jbcode\web ai\jianli，起点 fef6e73；Codex在并行修改核验预算显示，互不重叠。只先读20261009-AI-quality-evaluation-protocol.md、现有run_task_plan_quality.py与必要生产契约/比较逻辑，避免全仓重复调研。

你唯一写：backend/evals/run_quality_dimensions.py、backend/evals/quality-dimensions-cases.json、backend/app/tests/test_quality_dimensions.py、docs/evidence/20261010-AI-quality-dimensions/。旧14样例与runner保持原样；生产源码、预算/核验、前端、服务/数据库、依赖/P2/stash、正式接力全部只读。Codex负责独立holdout、边界审查和最终提交。

任务：实现可重复CLI，按协议分别测引用准确/越界拒绝、六类缺口建议的可操作性、八组版本变化归因。先落黄金标签与分类理由，再实现；明确这些是作者编写合成标签，不冒充真实模型或独立人工语义评分。通过生产validate_grounded_analysis、matcher/enrich与compare_views等实际路径，不重写一个永远通过的替代器。保留源hash/fixturehash/正反例/病例ID及失败原因，各维分子分母；无来源单列，不计引用成功。独立语义评价缺席时semanticQualityPassRate=null，规则/结构探针与语义分栏。

至少覆盖：旧/其他要求/其他owner/未来来源越界、第三方参考不能证明本人实践；具名交付物/步骤/核验条件，已有源码不重复索取，不把未来运行/团队贡献当已证明；无变化/仅材料/仅岗位/两者/删除/来源角色/同路径异hash/局部引用ID复用。归因以稳定要求ID/材料hash对比为依据，不用关键字命中冒充语义正确。

只用合成离线数据、不创建provider/不联网/不执行上传源码/不访问DB；运行两遍比较除timestamp完全一致，支持--case筛选。目标测试用 .venv-dependency23 与新项目内basetemp，-p no:cacheprovider；每次失败单独保存原始日志，最后自审/源码fixturehash/一屏回报。发现生产缺陷以最小反例报告，不擅改生产或调整标签掩盖。禁止Git提交/推送/安装/服务重启/真实模型/外发/P2应用。个人GLM5.3最高，当前五小时88%/每周58%，消费保留至少30%周余额；额度不足保留文件停止。
