# 传智杯34 /goal：私人草稿清除提示与恢复闭环

Git根D:\jbcode\web ai\jianli，免费Weekend Build Flash/最高。依据31的P1-1与probe1实际函数复现；P2-2跨角色mock结论已由Codex否定，不实现其建议。

唯一写jianli/src/lib/private-answer-workflow.ts、jianli/src/components/PrivateAnswerDraft.tsx、新增jianli/tests/private-answer-recovery-notice.test.mjs、docs/evidence/20261011-GLM-goal34/。33写后端AI，35写启动器；所有其他源码/测试和原审查证据只读。

持续完成红测试→实现→目标/受影响测试→自审修正→证据交付：

1. 常驻提示告诉学生离开窗口会清除未保存编辑，先保存；说明私人草稿没有发给企业。
2. hidden时依然立即清除文字/引用/预览、使旧DOM操作和在途回执失效；恢复同一会话activate+load后，实际发生未保存编辑丢弃的非敏感提示必须在读取中、成功和失败后可见，不能被同步notice清空。没有未保存编辑时不要声称丢弃了编辑。不要恢复旧文字、存localStorage、自动保存或发给企业。
3. 清除提示只携带布尔/固定提示，不残留旧身份数据；切换账号/任务时新的session不承接旧会话通知。再次编辑/显式操作后的提示生命周期明确；load/save/compare/copy各自并发票据、来源重验失败门禁、版本不降级行为保留。

用真实createPrivateAnswerSession而非照抄实现的模型测试：未保存文字/引用选择、无编辑、成功与失败恢复、再次操作、dispose/新身份、旧回执和旧DOM不能复活、来源失效仍拒复制。先保存基线红输出，保留31原探针；新测试证明修复后的可见提示。跑目标与所有受影响私人草稿/引用/失败回复会话测试、前端完整Node测试；不共享运行类型检查/构建或改stage，Codex集成后做生产页面/390px验收。

自审迭代范围内失败直至通过，证据包含原始命令输出（失败独立保存）、通过/失败/跳过数、源hash、diff、未验证页面项。一屏交棒，Codex复核和提交。禁改AuthProvider/API/其他页面/原断言；如必须扩范围先解释。禁止DB/服务/浏览器/外发/真实模型/安装/联网/Git提交推送/P2/个人计划、reset/clean。
