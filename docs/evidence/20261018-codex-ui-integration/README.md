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

随后建立`backend/.tmp/dep-frontend-20261018`，复制已安装依赖为实体目录（无安装/升级），原共享目录联接保留不动。源码/锁文件/运行依赖守卫通过，125个源码文件digest为`28252a148bb59acf62265361469ee0c570c8a46d60d0677e8af9e9d65728fdc5`；该实体目录生产构建也通过，见`runtime-physical.raw.out`与`build-physical.raw.out`。尚未启动正常服务，启动缓存应由正式入口核实后记录，不能手工伪造。

## 真实组件浏览器检查

独占3106验证台挂载真实MaterialPreview/TaskView，组件API由合成数据和受控Promise替代；EventSource也是模拟类。这证明真实渲染和组件时序，不证明真实HTTP/SSE/后台全链。模拟页源码保留`fixture/page.tsx`，原文件曾使用null图片观察值导致图片URL尝试访问未运行的8000并失败，没有读写业务数据；不将图片作为本批验收对象。验证台已停止。

1. 材料A文件请求挂起→切换B→B列表成功：修复后不残留加载指示；选择B后释放迟到A，仍显示NEW-B-CONTENT，无OLD-A-CONTENT。临时副本仅撤销setFileLoading重置，同样操作重新出现残留“正在加载文件”，截图`material-regression.png`；实际源码未被回退。修复截图`material-fixed.png`。
2. 任务进行态→模拟onerror显示中断/定时刷新→轮询重开流onopen，回到实时更新。真实业务终态没有因连接中断而改失败。
3. 规则/模型降级/失败合成状态分列；verification.unavailable无完成勾，终态无脉冲点；details通过真实浏览器Enter键展开。模型跳过/降级步骤不显示成功勾，显示原因；普通完成记录保留靛蓝勾，新增真实TSX渲染回归。
4. 桌面1280与移动390设定（有效内容宽375），document scrollWidth==clientWidth，无整页横向溢出。任务页原生progress在Chromium默认显示绿色，补局部跨浏览器进度样式为靛蓝；不改评分/进度值。

截图：`task-fallback-desktop.png`是最终靛蓝进度样式；`task-failed-390.png`是局部进度颜色修正前的移动布局/失败状态。`task-fallback-390.png`在视口调整尚未稳定时采集，存在整体缩放异常，不作为最终视觉证据。移动最终配色截图仍待正常页面验收，不把旧图当现状。浏览器视口已恢复，临时标签已关闭。

## 尚未完成

reduced-motion仅确认CSS规则，未在真实系统偏好下驱动；通知离窗完整竞态未在本轮完成。尚未正常网站加载本批构建、未真人首次使用、未做真实AI语义评估、未完成补证视频和最终材料。78/79、许可/签署/评审访问仍有后续工作，不宣布比赛版本完成。

## 同日后续：正常通知页手机触控

上节“尚未”是此前集成时点；正常启动恢复及补证视频的后续证据分别在20261018-launcher-recovery和20261018-growth-completion。本次只修通知页文字操作的触控高度，不变更异步、已读、授权或分页逻辑。

- 实际3000合成学生会话，390px设定/375px有效宽：修前刷新、全部标已读及卡片文字按钮24px高；修后均44px高。既有翻页按钮约41.6px，非本次修改范围。scrollWidth与clientWidth均375。`notification-mobile.json`和`notification-mobile.png`为新构建实际页面证据。
- 只读筛选：全部9条→未读4条→全部9条；每页20→50后仍9条、未读4条，未点击标已读或打开投递。没有执行真实模型请求。
- 目标ESLint、tsc、生产构建退出0；构建保留已有VisualEvidencePanel图片警告。`node --test jianli/tests/notification-session.test.mjs`4通过，仅证明目的地规则，不证明离窗行为。
- 首次在源码目录运行ESLint失败：配置无法解析@eslint/eslintrc。改在实体依赖stage执行，无安装或关闭规则。停止脚本成功后，外层误以未设置的LASTEXITCODE判失败，命令提前中断；未再次停止，继续同步文件/构建/恢复成功。正常服务3000/8000现已运行。
- 离窗仍未验：新建隐藏对照标签后，原通知document.visibilityState实际仍为visible、9条仍在；未发生hidden转移，不能据此判通过或缺陷。没有覆盖visibilityState、派发伪造离窗事件或继续环境绕行。真实hidden清空/回窗恢复和在途竞态仍待。

本次视口已恢复；未重跑数据库摘要，不将读取未读数量未变扩大为全库无变化结论。
