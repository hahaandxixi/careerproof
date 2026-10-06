# PRODUCT-01：个人GLM-5.3复杂并发接续

Git根D:\jbcode\web ai\jianli。当前后端与迁移已签收d760726；前端未提交改动全部保留。Start Plan免费Flash边界修复任务已由Codex确认“已停止”，其后续队列暂停；旧免费GLM-5.3任务已有额度错误，也不得恢复。切换原因是并发协议复杂而非认定免费Flash额度耗尽；用户已授权复杂问题提前使用个人GLM-5.3，必须新开任务并核对BigModel个人组。

## 接续目标

读取当前helper/component/tests和已有前端摘要，不重做已绿的31项/184全套。Codex新增独立探针 `docs/evidence/20261005-PRODUCT-01-codex/race-snapshot-binding-20261006/independent-binding.test.mjs` 对冻结helper8021e5a8为0过4失败：

1. 合法目标绑定变化后的来源重验成功：失效引用身份仍保留，但旧snippet不能作为有效来源预览/复制。
2. 重验pending：旧预览确认不得写剪贴板；保留未保存文字/选择。
3. 重验失败：不能继续相信旧来源；明确错误/可恢复路径，不悄悄移除历史引用。
4. PUT2已落库但响应延迟，另一窗口保存3，本窗口GET3先到，PUT2后到：保存基线不能3→2，busy正常结束，读取开始后的新编辑保留。

先补有意义回归再最小修复。`load/persist/refresh/compare/copy`应有各自票据/字段责任，clear/dispose失活护栏不放宽；最新来源重验和GET/PUT交错不能恢复旧来源。预览是已保存的文字及服务端验证引用；可选列表无snippet，不伪造原文。分享仍需预览后手动确认，不新增对外发送接口。旧红探针不要改；独立绿复跑通过设置PRIVATE_ANSWER_SOURCE_FILE为当前helper绝对路径，绿输出保存自己的证据目录。

## 文件所有权与门禁

只允许：jianli/src/components/PrivateAnswerDraft.tsx、jianli/src/lib/private-answer-workflow.ts、jianli/tests/private-answer-workflow.test.mjs；GrowthWorkspace/API client/domain仅必要兼容接入。新证据独占 docs/evidence/20261006-PRODUCT-01-personal-concurrency/。Codex持有正式清单与原独立探针。

禁止：后端/迁移/运行库/.env/runner/分析/通知/企业协议/真实模型/真实材料/外发/安装/Git提交推送/P2 stash。不得恢复旧任务队列或覆盖其已有成果。此任务只做本地前端实现/检查，不启动服务/生产构建/页面。

目标检查：新增回归红绿、原受影响前端检查、独立两组探针、npm test、类型检查顺序运行。原始命令/输出/EXIT/hash与自审发现落盘；限一屏交棒。遇协议歧义只提出具体问题，避免重写正确部分或循环全仓调研。完成后由Codex复核、生产构建与页面验收。
