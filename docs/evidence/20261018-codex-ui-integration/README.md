# 10/18 Codex集成复核：解析、材料预览与处理进度

检查起点5714f55，测试实际未提交工作区，不是冻结候选版。未操作正常数据库、未启动3000/3001，不做真实模型请求。78号启动脚本/使用与启动指南由Harness另行写入，本批不签收这些文件。

## 后端

- 在明确的`.venv-dependency23`执行解析器/OCR：31通过；异常捕获限打开文件，加密显式拒绝，读页/OCR/自有DOCX遍历的未知异常继续传播。保持像素分配前预检。
- 将旧证据中的确定性上下文替身测试纳入正式`test_document_parser_release.py`，并纠正80号后仍期待内部ValueError被转换的旧断言：现在验证ValueError传播且必经__exit__，不依赖__del__/GC。
- 上述释放3项＋版本范围7项＋上传端点9项，合计19通过。Ruff初跑发现新增正式替身文件带引号注解，修正后全部相关文件通过；原失败`ruff-first.raw.out`保留。
- 另一次独立PG7项结果见[PG记录](../20261018-codex-pg-integration/README.md)，不能与这些测试拼成一次全量后端运行。

## 前端自动检查

独立stage `backend/.tmp/codex-ui-20261018`，Node22.23.1，最初只读联接已安装Z58依赖，无安装或升级。全部335项通过，目标处理进度11项通过，typecheck与生产Next构建退出0。构建前已删除本卡独占模拟页面并恢复正式layout；构建覆盖实际产品源码，不包括验证台。

最终lint为0错误、1条既有VisualEvidencePanel图片警告。首跑新增测试变量名module触发Next规则，改名loaded后通过，原失败`lint-first.raw.out`保留。没有关规则或改依赖。

正式运行守卫拒绝该stage依赖联接（`runtime.raw.out`），所以它只作为组件/构建检查环境，不宣称已获正常运行资格。后续使用独立实体依赖目录核验，不放宽守卫。

## 真实组件浏览器检查

独占3106验证台挂载真实MaterialPreview/TaskView，组件API由合成数据和受控Promise替代；EventSource也是模拟类。这证明真实渲染和组件时序，不证明真实HTTP/SSE/后台全链。模拟页源码保留`fixture/page.tsx`，原文件曾使用null图片观察值导致图片URL尝试访问未运行的8000并失败，没有读写业务数据；不将图片作为本批验收对象。验证台已停止。

1. 材料A文件请求挂起→切换B→B列表成功：修复后不残留加载指示；选择B后释放迟到A，仍显示NEW-B-CONTENT，无OLD-A-CONTENT。临时副本仅撤销setFileLoading重置，同样操作重新出现残留“正在加载文件”，截图`material-regression.png`；实际源码未被回退。修复截图`material-fixed.png`。
2. 任务进行态→模拟onerror显示中断/定时刷新→轮询重开流onopen，回到实时更新。真实业务终态没有因连接中断而改失败。
3. 规则/模型降级/失败合成状态分列；verification.unavailable无完成勾，终态无脉冲点；details通过真实浏览器Enter键展开。模型跳过/降级步骤不显示成功勾，显示原因；普通完成记录保留靛蓝勾，新增真实TSX渲染回归。
4. 桌面1280与移动390设定（有效内容宽375），document scrollWidth==clientWidth，无整页横向溢出。任务页原生progress在Chromium默认显示绿色，补局部跨浏览器进度样式为靛蓝；不改评分/进度值。

截图：`task-fallback-desktop.png`是最终靛蓝进度样式；`task-failed-390.png`是局部进度颜色修正前的移动布局/失败状态。`task-fallback-390.png`在视口调整尚未稳定时采集，存在整体缩放异常，不作为最终视觉证据。移动最终配色截图仍待正常页面验收，不把旧图当现状。浏览器视口已恢复，临时标签已关闭。

## 尚未完成

reduced-motion仅确认CSS规则，未在真实系统偏好下驱动；通知离窗完整竞态未在本轮完成。尚未正常网站加载本批构建、未真人首次使用、未做真实AI语义评估、未完成补证视频和最终材料。78/79、许可/签署/评审访问仍有后续工作，不宣布比赛版本完成。
