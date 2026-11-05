# 材料工作台与补证版本确认（2026-10-22）

基线：`01232d27e8768121592b6c05300e0b5ba5170a55`。只接受本任务 11 个文件的增量，验证源码为 `backend/.tmp/product-polish-20261022/source/`。完整文件清单、起始工作区与接受源码哈希见 `accepted-files.json`。未提交、未启动服务、未写数据库、未安装依赖、未调用模型。

## 真实障碍与结果

- 原有输入框和后端接受图片，但简历/项目提交处理器的独立白名单拒绝 PNG/JPG/JPEG/WEBP/BMP。真实组件处理器在 `证明.PNG` 上复现拒绝（`upload-before.raw.out`）；修复后同一测试确实进入离线 API 替身。后端未修改。
- 共享格式/大小校验：简历 PDF/DOCX/TXT/PNG/JPG/JPEG/WEBP/BMP，作品再加 ZIP；扩展名不区分大小写。文档与图片 10MiB、项目 ZIP 30MiB，与当前后端默认限制一致。服务端仍解析实际内容，浏览器 MIME 仅作元信息。
- 文件选择与拖放使用同一校验；单文件、格式、大小错误给出明确原因。原生文件输入保留键盘入口，选中后显示名称、大小、类型、上传目标和限制。选择文件不会立即上传。
- 已有材料优先展示各自最新上传，旧版进入按需展开的历史列表，处理中最新版不会被误标为已完成。第一次使用展开上传准备区。重试继续复用既有项目/请求键，恢复参考材料重试时同步恢复其归属。
- 从材料页返回补证任务携带本次已保存版本的提示；任务页先用当前账号材料列表核实，再提示版本/解析状态。项目版本高亮并显示“尚未选择”，不自动打勾、保存或分析。新版本排序靠前，“最新可用”只认完整列表中的最新完成版本，不因搜索旧版而误标。
- 当前选择与服务端已保存材料分区显示；改选后明确提示尚未保存，生成报告仍使用服务端已保存版本。保存/分析接口、权限、快照及草稿离窗保护没有改动。

## 接受范围与原有改动

本轮：材料页、MaterialFileDropzone、GrowthUploadReturn、GrowthWorkspace、ProjectVersionPicker、material-upload、material-picker（仅排序）及 4 个直接测试文件。具体路径见清单。

起始工作区的 ProjectVersionPicker 同名材料标签、material-picker 的 duplicateProjectNames/projectNameLabel 以及相关原有测试原样保留在工作区；它们不属于本轮，接受目录通过 before→working 的三方合并排除了这些修改。两处相邻冲突只保留本轮高亮逻辑和 HEAD 原标签，不整文件复制脏工作区。PrivateAnswerDraft 未修改。

## 离线验证

运行目录：`backend/.tmp/product-polish-20261022/source/jianli`。Node：`C:/Users/江博/AppData/Local/hermes/node/node.exe`（22.23.1）。只读复用既有依赖，不进行安装。

- `node --experimental-strip-types --test tests/material-upload.test.mjs tests/material-workspace.test.mjs tests/portfolio-upload.test.mjs tests/material-picker.test.mjs tests/growth-material-entry.test.mjs tests/growth-workflow.test.mjs tests/growth-job-selection.test.mjs tests/career-retry.test.mjs`：58 passed，exit 0（`focused-tests.raw.out`）。
- `node node_modules/typescript/bin/tsc --noEmit`：exit 0（`typecheck.raw.out`）。
- 既有 task62-lint stage 的 eslint/config，显式检查 7 个修改源码与 4 个直接测试文件：exit 0，0 error/0 warning（`lint.raw.out`）。

真实组件表单处理器、下拉/返回版本 JSX、输入/拖放 handler 均用真实模块和受控 hooks/离线 API 执行；不把这类模拟事件/SSR 检查称为浏览器原生文件选择或完整键盘验收。未重复全量测试。

## 待父任务实际页面验收

- 桌面及 390px：材料最新/历史分区、长文件名/目标折行、原生文件输入不造成横向溢出。
- 原生键盘选择与实际拖放，取消/多文件/不支持格式；提交前核对元数据与目标，上传错误后保留重试上下文。
- 补证任务→上传→返回，处理中不可选择、完成后突出新版本；明确勾选、保存前后提示和实际请求分别正确，未触发自动分析。
- 同账号日常离窗草稿保护复用既有核心验收，不以本轮 SSR 结果替代实际浏览器复验。

本任务没有运行正常站，也没有产生新的业务材料记录或真实 AI 效果结论。

## 后续真实 API 验收

同日新增明确隔离 API 的图片上传/OCR预览与新规则报告已通过，见 [API-FLOW.md](API-FLOW.md) 与 `api-flow.json`。本节是上述离线交棒之后的独立执行，不把浏览器待验或首次独立用户状态改成通过。

## 页面复验后补齐真实时间与处理状态

父任务页面验收指出选择行与返回提示缺少上传时间。本轮仅在 ProjectVersionPicker 的可选行、已选摘要及 GrowthMaterialReview 提示中使用 API 原有 createdAt 展示上传时间；已完成解析的选项明确标“已解析”。缺失或非法历史时间保持不显示，不使用当前时间补齐。原字段和选择/保存行为不变。

- 新渲染断言修改前 6 passed / 2 failed（`time-before.raw.out`）；修复后 4 个相关模块 21 passed（`time-final-tests.raw.out`）。覆盖返回提示、选项、已选摘要实际时间及无效时间省略。
- 最终 typecheck exit 0、4 个本次文件目标 lint exit 0（`time-final-typecheck.raw.out`、`time-final-lint.raw.out`）。
- 工作区与接受副本均仅更新 material-upload.ts、ProjectVersionPicker.tsx、GrowthUploadReturn.tsx、material-upload.test.mjs；原有同名标签差异仍留在原位置，未整文件覆盖。最终哈希已刷新到清单。
- 本次没有 HTTP 或数据库操作；时间样式与窄屏折行需父任务最后构建后复验。
