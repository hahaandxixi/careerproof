# 默认AI请求预算：有界修复

基线：`ba0c970`。只处理默认请求被本地预算拒绝；无真实模型请求、正常数据库访问、依赖安装、服务启停或Git提交。

## 复现与修复

当前完整请求序列化采用JSON UTF-8字节数加1024字节余量。它不是供应商计费token；旧默认12000在没有任何证据时已不足（13924）。最小有效材料原先16122，冻结完整校园报名项目五项要求原先39348，因此默认路径根本到不了HTTP transport。

`provider.py`中只删除已由原样追加的`evidence_policy.md`覆盖的重复事实/建议/来源覆盖说明，保留JSON合约、引用白名单、本人/第三方边界、历史隔离、评级上限、占位识别和定向修正要求。没有改评分公式或裁剪材料原文。提示词版本升为`evidence-trust-v30-budget-deduplication`，历史授权包/原始输出不覆盖。

相同context与相同完整wire形态对照：

| 输入 | 修复前预检上界 | 去重后预检上界 |
| --- | ---: | ---: |
| 无证据，仅固定开销 | 13924 | 12322 |
| 最小有效要求 | 16122 | 14520 |
| 五项最小形态（非完整业务评测） | 24918 | 23316 |
| 八项最小形态 | 31515 | 29913 |
| 冻结完整项目五项、多文件实现/测试/运行输出 | 39348 | 37746 |

完整项目数据来自既有`20261022-test-source-selection/frozen-after.json`的`sentContext`，单独复制为测试夹具，不改历史文件；材料SHA256为`58b3ced4e093d346b7f466d5cc36243639357590d8ab692445d6de9202fb1518`。

据完整项目37746上界（其中已含1024余量），默认`AI_PER_REPORT_INPUT_TOKEN_LIMIT`调整为40000，保留2254额外空间；不是凭最小案例推断32000足够。旧环境中显式设置12000仍会阻断，需由使用者按指南调整，代码不绕过显式更低限额。

此历史配置名继续同时限制完整请求的保守字节准入及供应商可信实计input-token累计；两者单位不同，不能把37746写成实际token或费用。累计报告/每日预算、200000每日输入、4000单报告输出、物理重试数均未增加。完整项目可能因最终请求预留而跳过规划，不把这种程序跳过标为模型主动停止，不强制调用工具。更大输入仍可被阻断并保留规则降级。

## 实际验证

- 新增最小/五项形态默认请求到达真实`httpx.MockTransport`测试，旧12000下红：2 failed，见`default-red.raw.out`。红阶段提示词已去重但仍超过旧默认；原提示词字节另由Git基线测量。红日志为初次去重版本，最终恢复显式等级提示后的字节以`request-measurements.json`与最后158项日志为准。
- 当前默认最小、五项形态和完整项目均到达Mock HTTP；最终分析继续消耗供应商回执的80input/40output，不将字节估算写入实际用量。
- 默认工作流通过一次规划停止响应再完成最终分析；保留当前工具选择、合并可信用量与最终预留。
- 相关最终命令：`python -m pytest app/tests/test_report_input_budget.py app/tests/test_input_budget_ledger.py app/tests/test_deepseek_provider.py app/tests/test_zhipu_provider.py app/tests/test_bailian_provider.py app/tests/test_ai_evidence_workflow.py app/tests/test_durable_provider_hooks.py app/tests/test_ai_budget_attempt_integration.py app/tests/test_ai_budget_fault_recovery.py -q -s -o cache_dir=.tmp/budget-pytest-cache --basetemp=.tmp/budget-acceptance-final` → **122 passed，exit0**，5个既有PyMuPDF/SWIG弃用警告；该次在最终恢复一句显式“不自动提高”等级提示之前，日志保留其当时字节测量。
- 覆盖超限发送前拒绝、工具schema/历史增长、修正剩余预算、显式零/负限额、每次物理重试回执、回执失败不重发、可信错误用量累计、未知503用量保持预留而非归零；均Mock或夹具专属临时SQLite。
- 为核对旧CI全部预算失败模块，再运行`test_actionable_evidence_gaps.py test_career_change_attribution.py test_directed_retrieval.py test_external_credential_privacy.py test_function_coverage.py test_report_history.py`：首轮141通过/1失败，失败是去重后缺少原有显式“不自动提高”提示，未改断言，恢复原提示及不输出内部字段要求。最终这些六模块加`test_report_input_budget.py`为**158 passed，exit0**（`prior-failure-modules-final.raw.out`），涵盖所有31个先前预算失败；不与前批数量相加作为整体数。
- 目标Ruff三个文件通过（`ruff-final.raw.out`）；首轮两条长度错误已仅换行修复，原失败保留。
- 原沙箱async等待无结果已中断本人的两个执行句柄；同样离线检查经审批在可运行权限下完成，未改ACL。日志扫描未发现JWT/数据库URL/Key字段泄露。

## 文件归属与边界

- `backend/app/core/config.py`：只接受AI预算字段及解释注释；同文件材料资源配额字段由总控另行实现，勿把其归为本子任务。
- `backend/app/agents/provider.py`：重复规则去重、提示词版本与准确的字节准入报错文案。
- `backend/app/tests/test_report_input_budget.py`：四个新增测试实例（最小/五项参数化、实际工作流、完整项目）。
- `backend/app/tests/fixtures/complete-project-budget-contexts.json`：上述冻结项目context，不含参考答案。

`input_budget.py`、`evidence_policy.md`和`evidence_workflow.py`无需重写，原有统一wire估算/规划预留/修正/重试持久化守卫测试复用。未运行全项目、真实模型语义评估或公网部署；预算准入通过不等于真实AI效果通过。总控负责同步环境模板/用户说明、生成新的当前冻结输入包、整体CI及本地提交。
