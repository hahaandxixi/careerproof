# AI技术证据索引

预审B1；产品`e95504feed306e5cf5ee013a6e546976013639c0`；文档基线`f6bf1ed9c20fe0629976cd9505f2f1258146cedb`。最终提交待任务A完成后同步。

本索引不打主观分数。源码存在、运行发生、质量改善和人工判断分别核查。证据编号及SHA见[机器索引](evidence/verified-index.json)。

|评分项|已实现及用户可见作用|源码入口|真实记录/截图|版本及模型性质|限制|PDF/视频|
|---|---|---|---|---|---|---|
|LLM 8%|DeepSeek适配、结构化解释、降级模式|backend/app/agents/provider.py；contracts.py|E03/E04；agent-real-stop|历史五项真实DeepSeek；当前v30为后续实现|历史输出不能证明当前提示词效果；语义未全验|9-10页；V04/V07|
|Agent/工作流 8%|模型选补检索/本人历史/停止，展示实际动作与原文|backend/app/agents/evidence_workflow.py；jianli/src/components/ReportAgentEvidence.tsx|E03/E05/E06/E08；历史停止截图|五项停止与单要求成功是不同批次|不称通用自主Agent；新完整项目成功补取待验|11-12页；V04|
|RAG 6%|受限候选、同空间检索与可定位引用|backend/app/tools/semantic_retrieval.py；backend/app/services/retrieval.py；backend/app/tools/code_analyzer.py|E07；report-citation|规则/离线链路；当前语义权重未由本轮确认|非全量上下文；无独立同条件生成增益统计|13页；V04/V07|
|多模态 5%|图片上传、本地OCR、另行授权的图像观察|backend/app/tools/ocr.py；backend/app/services/portfolio.py|E02真实PNG/OCR；材料截图|实际PNG及本地OCR；非当前真实视觉模型效果|文档格式不计模态；OCR非通用视觉理解|8/14页；V03/V07|
|安全可控 4%|来源/判据校验、预算硬停、授权固定快照|backend/app/agents/contracts.py；backend/evals/bounded_evidence_smoke.py；backend/app/services/applications.py|E01/E08；enterprise-desktop|真实PG/强停与Mock分开|校验通过非语义全对；已下载副本不可追回|7/15-16页；V06/V07|
|MCP/工具 4%|Function Calling与只读MCP工具实现|backend/app/agents/provider.py；backend/app/mcp_server.py|E05/E06为真实函数调用；MCP看接入指南/测试|真实FC有一单要求用例；MCP未新增客户端实录|不能把FC实测当作MCP客户端运行证明|11-12页；V04/V07|

## 原始证据及保真副本

- **E01 同版本工程检查**：[原始副本](evidence/originals/E01-ci-f6bf1ed.json)；原仓库路径 `docs/submission/evidence/ci-f6bf1ed.json`；版本：f6bf1ed9c20fe0629976cd9505f2f1258146cedb。CI39947184769三任务成功；前端442、SQLite1586/94跳过、严格PG141、强停8。数量来自该版本记录，不与历史累加。 SHA256 `042b788a87273cb674842d356632cab9c10b431c4dd8c81d85dbd6ae294f024e`。
- **E02 接受页面与固定版本**：[原始副本](evidence/originals/E02-candidate.json)；原仓库路径 `docs/evidence/20261023-page-final/candidate.json`；版本：e95504feed306e5cf5ee013a6e546976013639c0。桌面1280/手机390、明确保存刷新及身份拒绝已验；真实200%缩放、标签隐藏/最小化仍待人工。 SHA256 `a3352bd4dab643dd3a8ee0f5af6c49b00f5d73122d57dce00a64d7b6e999978d`。
- **E03 完整五项真实DeepSeek报告**：[原始副本](evidence/originals/E03-claims.md.txt)；原仓库路径 `docs/evidence/20261021-agent-verification/claims.md`；版本：bcbe0e3及其等价运行副本，见E04。五项、14条引用、2请求、输入11137/输出1679；历史估算0.035706元。模型选择停止，无成功补检索，非当前v30效果。 SHA256 `006b681e64818bce551ce071844bd6515c1b51b7bbace78d65afe9c355dc3081`。
- **E04 历史运行源码等价链**：[原始副本](evidence/originals/E04-source-equivalence.json)；原仓库路径 `docs/evidence/20261021-source-equivalence/source-equivalence.json`；版本：历史逐文件清单。运行副本、产品提交与去诊断差异分别记录；不能把当前源码写成历史请求源码。 SHA256 `33697960f446a51ee901f95491ff7ac25eae903a3d2d24e07e73f46ee7c9f58a`。
- **E05 单要求工具真实作用**：[原始副本](evidence/originals/E05-live-result.json)；原仓库路径 `docs/evidence/20261021-tool-choice/live-result.json`；版本：20261021独立固定工具批次。2物理请求补取cancel片段R1-E3；0.015898元为历史估算。原fail保留，修正的是包含判据，无第二次请求。非站内五项报告。 SHA256 `5e184cfbdffe18490cde995ec62c0cdb01a8df5e2587dfd6fdbad69df62ca37f`。
- **E06 真实工具批次判据更正**：[原始副本](evidence/originals/E06-live-acceptance.json)；原仓库路径 `docs/evidence/20261021-tool-choice/live-acceptance.json`；版本：与E05同次请求。可证明目标引用包含新增片段；不新增模型请求、不替代语义评审。 SHA256 `6a34631be62784b6a2b45aa27da2309914fd1cbe1ac21f98aa3459a963af840f`。
- **E07 受限候选到最终引用**：[原始副本](evidence/originals/E07-README.md.txt)；原仓库路径 `docs/evidence/20261022-test-source-selection/README.md`；版本：4ba1ccd。10个测试中候选1变6；最终上下文仅两个测试加一份上传输出。没有模型读全量或独立运行的结论。 SHA256 `d4fcc6a5ad4aa8fdf62e05a998eb79a30681d6480a423783fc3dee05b9134c55`。
- **E08 Agent页面与真人收件**：[原始副本](evidence/originals/E08-README.md.txt)；原仓库路径 `docs/evidence/20261022-agent-result-integration/README.md`；版本：da728dc、ba0c970。真实五项停止与Mock补检索分开。一位独立评审者三例已收，两处理由待澄清，不报告通过率。 SHA256 `9c35cb83e0120e385758a7be4de06e54fc214b88c75a097d5675b4c75f8e6355`。
- **E09 源码包干净复现**：[原始副本](evidence/originals/E09-README.md.txt)；原仓库路径 `docs/evidence/20261021-r7-clean-reproduction/README.md`；版本：r7；39f49d7仅补文档。全新依赖、专属PG、规则报告与停止恢复已验。只证明r7对应版本；B1未重做安装。 SHA256 `40e8f4a3f2277c1a71a8ae7b76dd3be11227c57a4d33c5e4c22d8cf7319202bc`。
- **E10 内容核对与来源身份**：[原始副本](evidence/originals/E10-README.md.txt)；原仓库路径 `docs/evidence/20261022-content-warnings/README.md`；版本：44d57ae、0c27a9c。本地四类风险提示，不自动拦截；未命中不等于安全；源码/测试/合法引用可由用户核对。 SHA256 `30ef5da8c628e355fb30b497dee619058984b1d59842bd78797008187c5304cb`。

## 截图使用

[素材清单](evidence/assets.json)列出6张原始截图的哈希、实际格式和像素。扩展名为png的历史文件部分实际为JPEG，按真实格式记录，不重编码冒充原图。最新页面对应e95504f及构建HNdt9SK706tuGRbc0NPbL；历史Agent图另属da728dc构建，PDF中标注历史。

源码入口清单由本专项校验存在性；具体源码仍由任务A负责。当前发现的证据缺口只登记，不改产品或历史结果。
