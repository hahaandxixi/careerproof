# 10/23 布局与交互收尾验收

接受源码提交：`48520616ec479a50052588919f499a6d4ed6d901`。基线：`4f5ad6ff1cb84c06f3ea5ff97f5ee7e25fb28070`。本轮只涉及17个前端源码/测试文件；精确文件与LF内容哈希见 [接受文件](accepted-files.json)。未改后端、权限、固定快照、评分或调用预算。

## 用户可见变化

- 补证任务先呈现岗位要求、真实阶段和一个下一步；比较结果前移，完整历史与UUID/哈希按需展开。导航入口仍进入原保存、确认、分析流程，不自动执行。
- 报告顶部保留模式、真实材料类型数量、一次摘要和优先入口；完整材料仍可定位展开。当前要求按判断、来源、待核对、操作阅读；长补证清单折叠。
- 手机显示第X/Y项、上下项与全部要求；所有面板继续挂载。修复实际单击跳过一项的问题：拦截识别到的本页锚点，以点击时捕获的目标更新hash，避免捕获阶段更新按钮后原生跳转读到另一个href。
- 修复基线已有的编辑重复阅读区：ReportRequirementReader与McpAccessPanel曾共享报告ID作为同级React key；阅读区现在使用独立前缀。旧版编辑后10个article/两个阅读区，修复后5个article/一个阅读区，切换要求仍保留未提交核对说明。
- 企业雷达/证据约35:65；手机证据优先、图表显式展开，要求按钮不随图表隐藏。下载降为辅助；当前候选人、固定报告及回复区域保留。雷达与学生报告仅采用validated且报告未降级的AI解释。
- 材料顶部添加入口与项目上传新版入口展开原表单并定位焦点，完成卡片精简进度；不自动上传或加入报告。
- 私人草稿显式保存紧邻编辑框；私人范围/实际保存状态保持可见，候选引用折叠，失效引用、冲突和丢失提示保留。未改变会话或请求防护。

## 构建与环境

实际预览 [3137](http://127.0.0.1:3137/reports/2997e468-ca66-401d-a3e2-f6518cad9243)，生产构建 `E_NOkpjgVH-G2jRhfgdvS`，目录 `backend/.tmp/layout-closeout-20261023/jianli`。此目录基于接受基线加17个接受文件，各文件LF内容与源码提交逐项相同，不使用整个脏工作树预览。

API8114仍来自原CI隔离工作树；正常站未启停。专属PG55445 / cp_product_polish_20261022与原合成存储复用；进程和容器身份再次只读核对。[运行记录](runtime.json)。Node22.23.1、Next15.5.27、React19.0.0、Windows11；依赖通过既有stage只读junction复用，未安装升级。

仅本次合成草稿曾明确保存、刷新核对并恢复原文本，另有登录会话写入；没有投递、回复、上传、生成报告或外部模型调用。企业读取沿用既有授权合成数据。

## 实际检查

|命令（在独立前端目录）|结果|日志|
|---|---|---|
|node --test tests/report-reader.test.mjs|9通过，exit0|[定向回归](report-reader-final.log)|
|node --test tests/*.test.mjs|439通过、0失败、0跳过，exit0|[最终全前端](frontend-accepted-final.log)|
|node node_modules/typescript/bin/tsc --noEmit|exit0|[类型检查](typecheck-final.log)|
|node node_modules/eslint/bin/eslint.js .|0错误、1既有img警告，exit0|[完整lint](lint-final.log)|
|node node_modules/eslint/bin/eslint.js src/components/ReportDetail.tsx src/components/ReportRequirementReader.tsx tests/report-reader.test.mjs|0错误0警告，exit0|[最后涉及文件](lint-last-target.log)|
|BACKEND_ORIGIN=http://127.0.0.1:8114 node node_modules/next/dist/bin/next build|exit0，最终逐字接受源码|[最终构建](build-final-exact.log)|
|git diff --cached --check|exit0，提交前无空白错误|源码提交可复核|

最后构建也运行Next自带类型/lint检查；末次完整测试后仅删除一处空白行。完整lint唯一警告仍是既有VisualEvidencePanel.tsx:46的鉴权图片，不关闭规则。保留首轮前端失败日志 [原始测试](frontend-tests.log)：涉及被保留隐私/快照文案与材料摘要布局断言，已恢复必要边界文案并保留等价材料定位验证。没有删除测试或隐藏失败。

另有一次沙箱构建因EPERM无法建立自身.next/types目录失败：[原始输出](build-final.log)。随后在同一独立目录以获准环境完成构建，不改ACL。旧成功日志不作为最终源码结果。

未触及后端，不重复本地SQLite、PG、hard-stop或r7/r8干净安装；不把历史后端数字累加成本轮验收。

## 浏览器实际验收与局限

使用正确林舟合成学生和既有企业账号，1280×900、390×844实际渲染；截图像素宽度含工具滚动条处理，不等于CSS视口宽度。

- 材料添加焦点upload-workspace-title；给原项目上传新版焦点project-upload-title，明确目标Campus Signup，不发文件。
- 已完成补证任务首屏显示待人工核验和查看本次变化；点击后自动展开原SQL比较锚点；UUID/哈希默认折叠。
- 草稿保存按钮距编辑框下边约63px；合成文本明确保存后刷新读回，再恢复原文保存。其他合成学生访问原任务被拒、无草稿编辑框、无私人内容；切回原学生恢复原草稿。
- 报告上下项各切一次，2→3→2；标题焦点H3位于134.6px，固定头部底108.8px；未提交核对说明保持；全部5个article仍挂载。未点击采纳/驳回按钮。
- 引用R2-E2直接链接选择SQL第2项并展开来源，定位约120.2px；刷新可恢复。核对材料入口展开原材料区。Enter键可展开/收起全部要求。
- 企业端SQL选择、固定候选人和收件人保留；手机图表默认收起且可展开/收起，要求选择始终可见。原并排比较逻辑未修改；本轮未重新执行发送回复或下载。
- 上述检查页面无整页横向溢出；代码区自身横滑保留。新布局没有新增动画。

观测摘要见 [browser-checks.json](browser-checks.json)。真实200%缩放仍未验：工具Control_L+plus未改变DPR/视口/visual scale，未用CSS zoom冒充。真实离窗仍未验：第二IAB标签未使原document.visibilityState离开visible，未派发模拟visibility事件冒充。真人首次使用、AI语义质量均不由本轮程序/浏览器测试替代。

## 同状态截图

基线3136与新3137使用同一合成数据；报告均为2997…，补证任务3b9…，材料为同一林舟账户。企业同为林舟固定报告、SQL选中且来源展开。

|页面/视口|修改前|修改后|
|---|---|---|
|补证1280|[前](before-growth-1280.png)|[后](after-growth-1280.png)|
|补证390|[前](before-growth-390.png)|[后](after-growth-390.png)|
|报告1280|[前](before-report-1280.png)|[后](after-report-1280-final.png)|
|报告390|[前](before-report-390-stable.png)|[后](after-report-390-final.png)|
|材料1280|[前](before-materials-1280-stable.png)|[后](after-materials-1280.png)|
|材料390|[前](before-materials-390.png)|[后](after-materials-390.png)|
|企业1280|[前](before-enterprise-1280.png)|[后](after-enterprise-1280-stable.png)|

附：[手机要求与来源定位](after-citation-390.png)、[切换后编辑保留](after-report-navigation-390.png)、[上传新版定位](after-material-upload-390.png)、[草稿保存区域](after-draft-390.png)、[企业手机证据优先](after-enterprise-390-stable.png)。视口刚切换时产生的过渡截图仅留本地独立stage，不列入验收。

## 集成边界与后续

本轮独立接受文件先构建验收，再逐文件以4f5ad6f作共同基线与主工作树合并；暂存的仅为接受文件内容。ApplicationBoard/ReportDetail相邻其他修改人工合并保留但未暂存，globals/PrivateAnswerDraft其他旧改动三方合并保留。原工作树仍有48个已跟踪修改，路径见 [保留清单](remaining-tracked.txt)；既有未跟踪证据/文件也未清理。暂停Agent、其他UUID/选证、指南/PDF等不混入本轮源码提交。

下一项优先补真实浏览器200%与离窗草稿检查，再由独立人员完成首次走查。本轮结论为布局与交互调整完成及以上验证范围，不能据此宣布全项目或比赛交付完成。远端本提交CI以GitHub实际运行结果为准；既有基线run39887022268不替代本轮。
