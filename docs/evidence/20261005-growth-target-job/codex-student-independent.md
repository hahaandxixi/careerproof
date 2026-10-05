# 学生三变化独立核查（阶段尚待最终签收）

2026-10-05。ZCode个人GLM-5.3三变化任务已从界面确认终态交棒，无停止生成按钮，学生runner/浏览器写入权已释放；另有免费Flash最终全量任务，仅写phase-final证据及独立测试schema。

## 数据不变量与三类变化

Codex执行codex-closure-invariants.py：严格限制本机cp_e2e_closure-20261005，SET TRANSACTION READ ONLY并核对当前库及readonly状态，最后回滚，writes=0。首次原始输出before-variants仅基准存在，明确completeReportChain=false；through-R2保留中间结果；最终带--require-complete的final-chain输出EXIT=0，四份报告均实际存在、归属同一合成User、分析完成。

- baseline→R1：岗位B及requirementId不变，项目第1版换第2版，简历版本不变。
- R1→R2：材料完全一致，岗位改C，要求ID与原岗位严格不同；同名技能不导致身份合并。
- R2→R3：项目换回第1版，岗位换回B，两类变化均实际存在。

三个原投递A/B/A2快照SHA256与初始合成清单全部一致，仍replied/replied/viewed，未撤回或倒写旧快照。旧seed错误报告及企业问题任务保留历史409，本轮从正式UI基准缺口继续，不声称旧企业问题已回答。

## 独立真实页面抽验

Codex实际执行student-browser-runner的variant-job，原始输出codex-student-job-refresh.raw.out EXIT=0，对应student/variant-job-2026-10-05T13-33-00-540Z。复用5d91c362任务及R2，不重复创建/分析；刷新仍保持岗位C，比较明确仅目标岗位/要求变化，原Python要求移除1条、新Python要求新增1条分列，总计移除1、新增2，有基准和目标报告引用。该次只登录、打开、刷新与读取比较，未执行材料PUT或新分析。

已读取ZCode三条最终results：材料变化13-21-50、岗位变化13-24-45、共同变化13-25-06；对应引用、逐项解释及刷新重读均纳入断言。390首次undefined断言误判fail及岗位首次定位/符号错误保持留档，未追认旧失败为成功。最终390 13-26-14三页宽390且标题在固定header下、elementFromPoint命中；Codex查看对应比较/报告截图，没有只以DOM存在当作可见。

## 其他阶段当前性与限制

codex-current-ai-source-audit.json独立重算已签收离线评测的四个源码SHA256，均与probes.json一致；14具名样例、23契约探针的覆盖指标仍对应当前实现。146回归及PG939基线另有已签收证据，不机械重复没有变化的评测。真实模型与任意自然语言语义质量未验证。

ZCode报告末句“运行服务不包含这些未提交改动”与实际0014迁移/生产重建日志、成功跨岗位API及本次数据证据相矛盾，不采信该句；closure构建包含当时已落盘的产品协议，不以是否提交判断运行源码。产品安全diff、最终全量证据、提交范围及正式状态还需收口；本记录不宣称整个GOAL完成。
