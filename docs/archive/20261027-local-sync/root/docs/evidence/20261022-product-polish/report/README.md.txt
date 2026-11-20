# 报告阅读体验交棒

本记录仅覆盖报告阅读界面。接受基线 `01232d2`，接受副本 `backend/.tmp/product-polish-20261022/source`；准确文件字节见 [accepted-file-hashes.json](accepted-file-hashes.json)。不声称已完成浏览器验收或真实 AI 效果验证。

## 用户看到的变化

- 报告先显示查看身份、岗位/候选人、生成时间、固定材料版本及真实处理模式，再显示摘要和一个优先核对入口。入口直接复用既有 `evidenceWorkspace(...).priorities`，不改变排序、评分或投递条件。
- 桌面为要求列表与当前详情；窄屏为列表在前、详情在后。当前项同时有边框、背景、`aria-current` 和“正在查看”文字。每项详情明确区分当前判断、来源、还需核对和按需补证。
- 所有条目始终只挂载一份，切换只隐藏面板，保留来源锚点、本人核对输入及补证表单状态。原始代码、引用 ID、来源身份与版本映射没有改写。
- `#requirement-*`、`#citation-*`、无模型编号的 `#rule-source-*`、`#growth-*` 和企业回复 query 入口按当前报告保存的映射选择要求，再在 React 提交后展开来源并滚动。重复相同 fragment、浏览器前后退同样处理。
- 本地规则、Mock 和模型降级继续区分；降级提示在摘要区域直接可见。模型名称、token 与耗时移至处理说明，缺失数值不显示为 0。
- 既有补证计划、Agent 分析说明、投递、固定材料、版本比较与本人核对功能仍保留；未增加接口、框架或业务状态。

## 文件与归属

接受文件仅五个：

1. `jianli/src/components/ReportDetail.tsx`
2. `jianli/src/components/ReportOverview.tsx`（新增）
3. `jianli/src/components/ReportRequirementReader.tsx`（新增）
4. `jianli/src/lib/report-reader.ts`（新增）
5. `jianli/tests/report-reader.test.mjs`（新增）

工作树 `ReportDetail.tsx` 原来有三处显示修改。本轮保留它们，不视为已接受：对 HEAD、保存的 before 和本轮 working 三份文件统一临时 LF 后进行三方合并，在接受副本解决一处移动内容冲突。接受文件保持已提交的 SourceIdentity、原始字段和完整材料校验信息；上述旧显示差异仍在工作树单列。没有修改其他旧 UUID helper、EvidenceCard、ReportItemExplanation、Agent 实现、导航、全局 CSS、材料页、后端或数据库。

## 实际检查

执行目录为接受副本中的 `jianli`，Node `C:/Users/江博/AppData/Local/hermes/node/node.exe`（v22.23.1）；依赖为已有只读复用 junction，没有安装。

```text
node --experimental-strip-types --test tests/report-reader.test.mjs tests/report-action-layer.test.mjs tests/source-identity-render.test.mjs tests/source-coverage.test.mjs tests/growth-anchor-entry.test.mjs tests/agent-evidence-render.test.mjs
=> 42 passed / 0 failed, exit 0

node node_modules/typescript/bin/tsc --noEmit
=> exit 0

node node_modules/eslint/bin/eslint.js src/components/ReportDetail.tsx src/components/ReportOverview.tsx src/components/ReportRequirementReader.tsx src/lib/report-reader.ts tests/report-reader.test.mjs
=> exit 0, no reported errors or warnings
```

原始输出：`accepted-tests.raw.out`、`accepted-typecheck.raw.out`、`accepted-lint.raw.out`。八个新增目标测试覆盖既有优先级、同名多版本引用映射、回复入口、真实组件 SSR、降级和固定材料、不卸载隐藏内容、直接锚点/重复 fragment/前后退的选择展开滚动顺序及监听清理。效果驱动测试使用生产组件 + 可控 React effects/commit/frame，属于模拟行为测试，不冒充真实浏览器操作。

工作树类型检查曾遇到其他执行端正在修改的 portfolio `uploaded` prop 不匹配；未改其文件，最终接受副本类型检查通过。未启动服务、写业务数据、调用模型、安装依赖或提交。

## 交给总控的浏览器用例

- 桌面 1280/1440px 和 390px：首屏可识别报告岗位、时间、固定版本与模式；列表和详情可读、整页不横向溢出；长要求名折行。
- 点击第二项，确认只有正确详情可见；输入本人核对草稿后切走再返回，草稿保留。键盘 Tab/Enter 可切换，焦点轮廓清楚。
- 直接打开非默认项 `#citation-*`；确认先选中该项，再打开来源、定位正确行号。收起来源后重复点击同一引用仍可展开；浏览器返回/前进恢复正确要求。
- `#requirement-*`、`#growth-*`、企业通知 `?enterpriseReply=...#requirement-*` 都定位对应要求；已有 GrowthTaskStart 自动展开语义仍适用。未知引用不错误选中其他条目。
- 同名 `service.py` 的不同项目和版本仍使用 SourceIdentity 标签；完整来源、下载、原始代码与行号准确。点击“核对材料”展开固定材料，即便重复同 hash 仍有效。
- 规则/真实 AI/Mock/降级报告模式与处理记录一致；降级提示无需展开可见。确认摘要主入口与既有优先补证顺序一致，投递未被设为补证完成后的闯关动作。
- 企业固定快照使用 ApplicationBoard 自己的组件，不复用新 Reader；本批不宣称企业页面视觉已验。

## 只读交叉审阅

`auth-return.ts` 的内部来源、已知路由、反外部跳转限制合理，API 仍负责权限。发现 enterprise 返回 `/reports`、`/reports/:id`、`/tasks/:id` 时与页面 student/admin AccessGate 不一致，已通知总控并由总控补规则和回归；本执行端没有编辑该文件。该项不是数据越权，而是错误角色可能落入不可用页面。
