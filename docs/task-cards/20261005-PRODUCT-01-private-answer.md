# PRODUCT-01：学生私人回答草稿协议与后端任务

2026-10-05。基线b1b2b8d，Git根D:\jbcode\web ai\jianli。先核对status/HEAD/stash，保留所有历史未跟踪证据。读固定约束；本卡覆盖其“真人简历禁止”仅在用户另给具体修改后本地材料时，不扩大外发权限。本卡测试仍用合成数据。

## 用户结果与协议（Codex设计）

学生在本人补证任务中整理私人回答草稿，刷新可重读，关联原要求可溯的报告引用。保存草稿不改变补证进度、分析输入、评级、企业回复、投递、通知或旧快照。草稿没有“通过/企业认可”字段。复制供人工使用需先看预览、主动确认；不新增对企业发送接口、不自动分享、不调用模型。

1. 独立表growth_answer_drafts，一条growth任务至多一条草稿。id/时间沿用项目Mixin，growth_task_id非空唯一FK CASCADE；text非空默认空字符串，references JSON默认空列表，revision整数初始1。迁移0015接0014，真实升级/回退验证旧任务/报告/投递JSON完全不变。
2. GET /growth-tasks/{task_id}/answer-draft，学生本人所有权先检查，不存在草稿返回data=null。PUT同路径，payload={text, references, expectedRevision}，expectedRevision严格非负整数（拒绝bool/float），首建0、更新等于当前revision，否则409，不覆盖新版本；父任务User→growth锁序序列化首建/更新。每次成功保存revision+1，允许text为空用于清空草稿。text严格字符串最多6000字符，原样保留换行，不因本地存储自动脱敏改写用户文字；额外字段拒绝。
3. references最多20条，结构{reportId UUID, requirementId UUID, citationId非空≤100字符}，去重或明确拒绝重复；只允许task.base_report_id与本人task当前完成targetReportId。所有requirementId必须等于task原requirement_id，并实际存在于选定报告；citationId必须属于该要求evidenceList的真实条目，服务端验证来源，不接受仅拼接ID。基准用任务冻结base_snapshot，目标经本人授权报告查询；跨岗位新要求不可冒充原问题证据。原文/文件位置/参考来源从报告读取，客户端不提交snippet、评级或第三方标识。
4. GET与PUT均只允许student本人；别的学生404、企业403，不能通过猜taskId/reportId读写。响应包含taskId、原requirementId、text、references、revision、updatedAt及私人边界文案。历史已保存引用若目标关联变化，GET保留原记录但标明不可用，不悄悄删除；新PUT必须重新验证。不要将草稿加入企业API或投递快照。
5. 并发保存以expectedRevision明确409保护；刷新/账号切换丢弃旧异步回执。前端以后独立草稿guard，不与分析轮询争代际；409保留用户编辑、提示重读对比，网络失败保留编辑，不自动发送或重试。此轮后端交棒后才派前端。
6. GET /growth-tasks/{task_id}/answer-draft/references 单独提供本人可选择的引用列表，草稿尚未建立也可读；复用同一服务端引用解析，基准来自任务冻结快照、目标仅完成且仍为原requirementId。每项包含reportId/requirementId/citationId、reportKind(base|target)、filePath/lineStart/lineEnd/provenance；不返回别的要求或整报告。跨岗位目标没有原要求则不列目标引用，不用同名技能替代。接口同样student本人限制；前端不需手造citationId或猜冻结引用。

## 本任务文件所有权（ZCode后端执行）

允许：新backend/app/models/growth_answer.py、schemas/growth_answer.py、services/growth_answer.py；backend/app/models/__init__.py只注册新模型；backend/app/api/v1/evidence_growth.py只接新GET/PUT路由；backend/alembic/versions/0015_growth_answer_drafts.py；新backend/app/tests/test_growth_answer*.py；docs/evidence/20261005-PRODUCT-01-backend/及专属pytest临时目录。

禁止：改现有growth/report/application协议或放宽比较；前端、浏览器、业务public/cp_e2e、.env、生产建库/迁移/构建/重启、真实模型/真实材料/外部消息、Git写入、P2stash。Codex持有本卡与正式清单。本任务结束前不派前端写入。

## 必须验证与交棒

- 有意义红→绿：创建/更新/清空与刷新读取、首建冲突/旧revision409、其他学生/企业拒绝、伪造报告/要求/引用拒绝、跨岗位同名技能拒绝、第三方来源仍标参考；未知字段/过长/非严格类型拒绝。
- 保存前后原投递完整快照、企业回复、通知/事件数、growth状态/计划/材料/固定基准/analysis输入均不变；保存不创建分析或用量记录。SQLite真实迁移；PG真实并发首建/旧revision只在匹配夹具cp_test随机schema，失败不得改预期。
- 运行目标+原growth/比较受影响测试及Ruff，保存原始命令、脱敏完整输出与EXIT、源码hash、自审发现/处理。长日志进证据，一屏交棒；只实测结论，没跑的标未验证。遇协议歧义/越界需求停相关项询问Codex，继续独立安全项。
