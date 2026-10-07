# 传智杯15：页面首验中断接续

2026-10-07。Git根 `D:\jbcode\web ai\jianli`，当前main/4dd43ea（后续Codex证据提交可能递进）。旧传智杯14已界面确认额度错误终态，无正在运行的private-answer runner；不要恢复旧队列。保留所有未提交脚本与失败证据，先核对局部diff，不从零调研。

## 现场和边界

- Codex已恢复closure服务：8001/3001、0015、.next-e2e、Mock且外发false，SkipSeed/SkipBuild保留既有数据。无需构建、迁移或启动服务。
- 唯一写入者：你负责 `scripts/e2e/private-answer*.mjs` 和新证据 `docs/evidence/20261007-PRODUCT-01-pages/`；为延续已有runner可读取20261006证据，修改默认输出目录到本日。Codex只读库和正式文档，不同时写你的文件或夹具。
- 必读旧卡 `20261006-PRODUCT-01-page-acceptance.md` 及 `docs/evidence/20261005-PRODUCT-01-codex/page-review-findings.md`。禁止产品源码、正式清单、共用runner、.env、Git提交/推送、P2、真实模型、外发、权限设置、安装。
- 新Mock分析仅S9专用任务/合成材料允许。三原增长绑定、四固定报告、A/B/A2回复/投递/通知不得修改。凭据仅程序化读ignored文件，不进入证据或消息。
- 现场BigModel个人五小时100%、每周37%（10月9日重置）；最多再用约7个百分点至30%底线。套餐当前Start Plan暂无可用体验套餐。模型菜单核对BigModel个人GLM-5.3；不要把历史错误当当前额度。到30%停止个人调用、保留成果交棒。

## 顺序小队列

1. S8：已有真实COMPLETED材料重选409/4099、冻结绑定不变及GET网络降级注入有效；失败是runner错误期待“移除”按钮。引用身份仍在选项中时，明确取消该checkbox再保存即可。当前源在鼠标点击取消后 `if (!checked)` 又按Space重新勾选，条件反了；只在仍checked时补按，且断言目标reportId/requirementId/citationId取消、其他引用和正文保留。不要降为计数校验，也不要SQL改来源。修正陈旧orphan/remove断言；失效原文从预览和模拟剪贴板排除。原始服务端和注入回执分别落盘。
2. S9：合法上传已标记reference的合成材料并生成Mock报告（材料角色参考，不得仅写“第三方”字样）；从真实报告及要求创建新任务/选引用，编辑保存、刷新、预览/人工复制保留第三方身份、不计评级、不变本人贡献。复用现有student runner已读方法，优先最小专用流程；新材料/分析/报告ID写入自己的state，普通草稿不产生分析/usage另核对。
3. S6b补强：已跑同浏览器退出并登录A2后释放旧GET，结果为interception-invalid-after-context-destroyed，不能称旧回执已送达新组件。保留此事实，新增当前浏览器真实/auth/me userId核对为A2（两个账号显示名相同，不以显示名作身份证明），对旧marker/预览无泄漏断言；隐藏晚响应另证。若能在合法SPA跳转中保留可释放回执，则另补真实送达竞态，不绕过身份或产品保护。
4. S5/S10补验已在14:43/14:42绿，不重复完整全量：确认精确三元引用身份保持、页面注入clipboard调用次数0→显式点击1、失败保留后恢复再人工成功及390确认按钮。明确模拟剪贴板不声称系统剪贴板；不得再使用Browser.grantPermissions。

最后自审runner（尤其选择器、故障命中、未实施分支、口径）、node --check、每个新场景实际运行并保留全部失败原文。交付一屏：脚本hash、最终有效run、真实/注入/未验证区别、未完成项、无活动runner及数据库写入已交棒；长日志在证据。不要把12个标签pass当签收，也不要重跑193全套或重建未改产品。
