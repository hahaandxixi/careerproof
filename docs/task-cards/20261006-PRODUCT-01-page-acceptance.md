# PRODUCT-01私人草稿生产页面首验

Git根D:\jbcode\web ai\jianli；前端实现027069d已阶段签收：193全套/类型/Codex独立11探针通过。0015迁移与旧行hash已签收。Docker由用户恢复，原backend-postgres-1已healthy；Codex已实际Start-E2E closure-20261005 -SkipSeed -SkipBuild成功，独立生产.next-e2e、8001/3001、Mock且外发关闭。不能用自动测试代替页面通过。

## 本任务用户结果与证据

读docs/evidence/20261005-PRODUCT-01-codex/page-acceptance-matrix.md并逐项实际测试十二场景：保存/刷新、清空显式保存、保存中继续编辑、双窗口409、网络失败不自动重发、身份/隐藏与迟到回执、原要求/跨岗位、合法引用失效、第三方参考标识、先预览后人工确认复制及复制失败、真390px、旧状态不变。每项记录操作/请求顺序/结果/截图/可复跑脚本；未验明确写未验，不用mocked component当真实页面。故障应延迟/失败真实请求或clipboard实现，不手改组件内部状态。

实际页面仅http://127.0.0.1:3001；后端仅8001。先核对健康、运行manifest中的Mock/false/closure与真实进程身份。合成fixture账户来自ignored backend/.tmp/e2e/closure-20261005.json，必须程序化读取，不把密码/token/cookie/认证header打印、写证据、发聊天或复制到模型上下文。可读既有scripts/e2e学生runner/夹具方法，优先复用已安装浏览器插件/MCP/技能，先读其说明；没有工具不安装，具体报告。

## 所有权与不变量

只允许新scripts/e2e/private-answer*.mjs、docs/evidence/20261006-PRODUCT-01-pages/与自己的ignored测试输出；测试数据写入限定closure合成账号，通过真实产品UI/API。不得改产品源码/正式清单/.env/runner共用模块/服务/构建/Git/P2，不调用真实DeepSeek或外发，不访问真实材料。

Codex在此轮持有正式文档/运行环境，ZCode为页面测试与合成数据唯一写入者；Codex可只读复核，不同时改夹具。现有A/B/A2严禁撤回、回复、下载次数变更或重投递；其原状态/hash必须保持。原baseline/R1/R2/R3和三个增长任务绑定不得重选或覆盖；普通草稿保存可用已存在本人任务但不改变其计划/材料/分析/目标岗位。引用失效与第三方参考场景用新合成材料/报告/专用补证任务，通过真实合法流程创建；不能SQL造成功状态/报告或回滚撤回。

需要新报告的场景，先保存新专用任务的分析/用量基线；普通草稿操作不新建分析/通知/用量，前后核对。新报告生成明确分开记录，Mock合法不代表真实模型质量。页面第三方来源必须真实来源provenance=reference，不仅编造草稿文字。

遇阻断缺陷：先留真实复现与证据，不擅自改产品源码或改断言掩盖；交棒Codex决定修复，再继续互不依赖的场景。完整日志进文件，一屏回报12项通过/失败/未验、证据路径、工具/限制、下一项。不提交/推送、不停止服务。
