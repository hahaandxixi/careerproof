# PRODUCT-01前端与页面验收准备（尚未下发）

本卡只在后端任务终态交棒、Codex完成授权/引用/并发审查后下发。当前后端是单写入者；前端不并行改API/types，不改学生runner或运行服务。

## 用户操作

本人补证任务增加“私人回答草稿”：编辑文字、从服务端可选引用选择证据、明确保存。显示保存时间/版本/是否有未保存修改；不把草稿称为企业回复或通过结论。没有草稿也能选原要求引用；参考证据标“第三方参考”，跨岗位目标没有原要求则解释为何不能用其新要求回答原问题。

保存与分析互不覆盖，各有请求代际和busy状态。失败保留文字/选择，不自动重试；409保留本人编辑，提示新版本已存在并允许读取服务器版本作对照，不能悄悄替换或通过重读取得新版revision后自动覆盖。用户明确选择以本人编辑重新保存时才使用新revision。清空内容也需明确保存，空白编辑本身不删除服务端记录。

刷新重读已保存内容；未保存内容的刷新/离开提示按现有页面约定实现，不承诺浏览器崩溃恢复。账号切换、隐藏或卸载清除私有状态并废弃迟到回执，重新可见时读取本人数据，不能把旧身份草稿带给新身份。

预览展示原要求、本人文字、服务端验证引用与参考标记。用户先查看再主动确认“复制草稿”，仅写本机剪贴板，提示没有发送给企业；未保存编辑应明确标识或要求先保存，失效引用提示且不得作为有效来源复制。没有发送接口、外发调用、自动通知或评级修改。

## 必须验证

- 前端有意义的异步回归：保存后编辑与迟到回执、409保留编辑/显式重读对照、网络失败、身份/隐藏丢弃回执、重复点击/复制失败、跨岗位与参考引用。
- 隔离Mock真实页面：缺口任务编辑→选真实引用→保存→刷新读取；清空再保存；双页面同版本冲突不覆盖；错误引用/他人账号访问拒绝；预览与人工确认复制；390px标题/控件真实可见且无横向溢出。
- Codex重新核对三个旧投递hash/企业回复与通知数未因草稿改变；新草稿不创建分析任务或用量账目。不撤回、不SQL制造结果，不重做前阶段全部浏览器链。
- 后端最终协议字段确定后，任务卡另列允许的组件/helper/client/domain/tests及证据目录；服务0015迁移/生产重建须由Codex验证独立目标后执行，ZCode不自行迁移运行库。

交付：前端/受影响回归、类型与生产构建（构建目录顺序使用）、原始页面步骤/截图/结果与未验项。Codex审查私有状态与复制边界、独立抽验后提交，不以单元测试替代页面。

## 已核对API契约与拟定文件所有权（2026-10-06）

后端已交棒，Codex独立SQLite两项通过、Ruff通过；PG独立复跑暂因Docker未运行失败，仍待恢复，不是完整签收。本卡仍未下发。

后端：GET answer-draft返回data=null或{taskId,requirementId,text,references,revision,updatedAt,boundary}；references每项包含reportId/requirementId/citationId/available/snippet/filePath/lineStart/lineEnd/provenance。GET answer-draft/references返回data数组，除三重引用ID外含reportKind(base|target)/filePath/lineStart/lineEnd/provenance，不含snippet。PUT完整替换{text,references:[三重ID],expectedRevision}，首建0，409(code4240)冲突、422(code4241)来源不可用；最多6000字符/20引用，禁止额外字段。不存在草稿按revision0初始化。预览只展示保存响应的可用snippet，不伪造可选列表原文。

允许新建jianli/src/components/PrivateAnswerDraft.tsx、jianli/src/lib/private-answer-workflow.ts、jianli/tests/private-answer-workflow.test.mjs；只在jianli/src/components/GrowthWorkspace.tsx接入独立组件，jianli/src/lib/api/client.ts增加三调用，jianli/src/lib/api/domain.ts增加新类型；新证据docs/evidence/20261006-PRODUCT-01-frontend/。不重写growth guard/分析/材料/岗位协议，不改后端、runner、认证、通知、企业回复、旧测试预期或正式清单。前端实装阶段不自行生产构建/重启/迁移共享环境；类型与测试可跑，生产构建和页面运行等Codex安排独占目录时再执行。

设计提示：GrowthWorkspace身份key已有user.id:id重建，但分析轮询setTask不能不断重建草稿。私有组件使用独立读写代际+编辑序号，保存期间允许继续编辑，旧回执只更新已存基线且不覆盖后来文字。隐藏时按本项目约定清私有状态，明确告知未保存内容会丢弃；恢复可见重新读取。冲突时读取服务端对照不等于授权覆盖，用户另点击明确保存才用新revision。引用key为reportId+requirementId+citationId，避免两个报告同citationId误合并。
