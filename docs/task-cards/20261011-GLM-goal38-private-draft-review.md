# 传智杯38：私人草稿恢复提示独立审查与回归
Git根 D:\jbcode\web ai\jianli，继承34成果。Codex已独立运行 recovery-notice + workflow，54项通过，未声称生产页通过。唯一写前端PrivateAnswerDraft.tsx、private-answer-workflow.ts、新private-answer-recovery-notice.test.mjs和docs/evidence/20261011-GLM-goal38/。36后端、37启动器互不重叠。禁止改其他源码/旧测试断言。

使用现有review-agent（可用先读其技能）对34变更做缺陷优先独立审查；不是把14新增用例重复当全部证明。重点核实：多次hidden/clear、恢复读取前又hidden、读取失败后重复隐藏、无编辑与未保存编辑差异、load期间编辑、明确操作失败是否应丢失告知、账号/任务切换不承接旧通知、失效来源/迟到回执/旧DOM门禁不能放宽。别虚构浏览器多发visibility事件；给每项缺陷真实可达路径，不可达则如实排除。
如复现缺陷，先新增红测试再最小修复，原34证据不覆盖。自审后跑目标/受影响/完整Node及类型检查，完整原始输出、源码hash、diff、一屏交棒。npm typecheck本任务唯一执行，其他任务不得构建；本轮不运行next生产构建、不启动服务/浏览器/DB/联网/模型/安装、不改变活跃stage/P2/.env、不Git提交推送。页面390px与集成由Codex另行操作。
成果必须有可复核分析/回归证据，不为了花额度编造缺陷或重复已过全量测试。未发现代码缺陷可交只读审查结果，保持源码不变。
