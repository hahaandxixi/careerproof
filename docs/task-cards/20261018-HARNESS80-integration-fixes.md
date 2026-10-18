# 传智杯80：候选集成前最小修复

状态：待执行。执行端 DeepSeek Harness；Flash／高，首轮完成即停止。实际Git根 `D:/jbcode/web ai/jianli`，准备时HEAD为33ba713，执行时重新核对。用户手动转发本卡。

## 前置与所有权

只读本卡、docs/协作规则.md及本轮必要源码/测试。62、67、71、77已交棒，本指令允许在其现有未提交成果上作明确范围的增量修复；不要求先提交或全量集成，不以未列入派发表阻塞。先记录目标文件hash；保留他人修改，不整文件回退。若发现新的活跃写入者才停止冲突文件，其他独立部分继续。

唯一可写：backend/app/tools/document_parser.py、backend/app/tests/test_document_parser_unreadable.py、backend/app/tests/test_document_ocr.py、jianli/src/components/MaterialPreview.tsx、TaskView.tsx、jianli/src/lib/process-trace.ts、对应直接相关测试（可新增material-preview回归）。globals.css仅在本卡真实展示缺陷确需时作局部修正。证据在 docs/evidence/20261018-task80-integration-fixes/；临时验证只用独占 backend/.tmp/task80-*。不改retrieval.py、检索测试、锁文件、依赖声明、启动脚本和正式文档。

## 1. 解析异常边界（必须先复现再修）

当前PDF整段try会将文本提取乃至OCR抛出的普通ValueError都转换为文件损坏。Codex已用真实parse_document+替身page.get_text抛内部ValueError复现，外层得到AppError(4024)。DOCX整段捕获KeyError/ValueError也须检查同类问题。

- 明确输入损坏、空文件、加密拒绝等已知库行为；尽量采用显式加密检查和局限于已知库调用的窄捕获。
- 普通内部ValueError/KeyError、OCR错误及未知程序错误不能因处在整段解析中就被当成输入损坏；不要只删异常类型导致已知坏文件重新变成未知500。
- 保留原4024/4026等已有业务错误、from error诊断原因、上下文资源退出；不改任务进程协议或字符上限行为。
- 回归同时覆盖已知损坏/加密输入仍明确拒绝、内部读取/OCR未知异常传播、现有像素预检保留。更新旧测试中把任意ValueError模拟成损坏的过度假设；替身清理测试验证真实退出控制流，不依赖GC。

## 2. 材料预览加载状态（先确认路径）

核对62重构后：文件请求挂起时切换材料/重试，外层effect清空fileRequest，旧请求finally因current=false不清fileLoading；若新材料没有initialFileId，旧加载指示可能残留。

- 用真实组件构造A文件挂起→切换材料B→B文件列表成功→A迟到返回，检查旧内容与旧加载提示均不恢复。
- 若复现，最小修复上下文切换时的加载/错误/选择重置；保留同文件重复点击可重载、迟到响应隔离。
- 已满足就零改动交棒，不能仅凭代码行认定已修。

## 3. 77展示快速核对（不重做设计）

- 复用已确认的后端事件语义，检查tool.completed配skippedReason/fallbackUsed时勾选及邻近文字是否会误称AI成功；必要时将其表述为“处理结束/未调用模型/已降级”，不改后端事件。
- 检查onerror→onopen恢复后提示回到实时更新，终态不继续动效；缺证据不编造完成记录、耗时或失败原因。
- 有现成可用浏览器/stage则补桌面与390px、reduced-motion、details键盘；没有则直接标页面未验，不安装浏览器工具、不反复环境绕行。

## 环境和检查

后端优先明确使用 backend/.venv-dependency23/Scripts/python.exe，先输出sys.executable与PyJWT版本；Codex10/17在此环境实测为2.15.0，与声明相符。不要使用裸python把其他环境的2.10.1当生产漂移，不安装/降级任何包。

前端用已安装Node22及带eslint的已交付依赖stage；先说明源码目录/依赖目录/执行器。不要在服务目录安装或构建。只运行本次目标测试、相关受影响模块、typecheck、目标lint及修改Python文件Ruff。首次失败保留；本轮不再全量测试，不将跨环境/跨版本结果合并为全绿。

## 边界与交棒

不连接任何正常数据库，不启停3000/3001，不读.env/凭据/真实材料，不修改ACL，不调用网站模型、不提交推送、不部署、不操作P2。数据库/PG验证留给后续统一专属环境批次，本卡不自行创建容器或借用现有业务库。

一个有界批次完成即停止，不继续78/79/74—76。一屏交棒：实际HEAD、目标文件hash、两处疑点是否复现及红→绿结果、77核对结果、环境与实际命令/退出码、页面和PG未验范围。没有浏览器不阻塞代码修复交棒；不得自行签收整个候选版。
