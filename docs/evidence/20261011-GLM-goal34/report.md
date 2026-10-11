# 传智杯34：私人草稿清除提示与恢复闭环（交付）

- 日期：2026-10-11。Git根D:\jbcode\web ai\jianli。任务卡基线 80d4253；实际工作起点 HEAD `ef29532`（其间的 ef29532 为 docs-only 提交，两个源码文件 blob 与 80d4253 完全一致 `346d9d7`，代码基线相同）。
- 依据：31号审查 P1-1（docs/evidence/20261011-page-recovery-audit/audit.md）：hidden 清除后 clear() 的"未保存修改已丢弃"声明被恢复 load 首段同步 notice 清空，用户永远看不到；面板事前无常驻警告。P2-2 建议未实现（已被 Codex 否定）。

## 改动（仅卡列文件）
1. `jianli/src/lib/private-answer-workflow.ts`：新增 `lossNotice` 状态字段与两个导出固定常量（丢弃/无编辑文案，只携带"是否有未保存编辑"布尔事实，不含草稿内容/身份数据）；`clear()` 按 `privateAnswerIsDirty(清除前状态)` 布尔选择文案，notice 仍同步携带丢弃声明（31原测试断言不动），丢弃事实同时写入 lossNotice；**load 全程不触碰 lossNotice**（读取中/成功/失败都可见）；再次编辑（setText/toggleReference/removeSelection）与显式保存/对照/复制结束时清空。并发票据/来源重验门禁/版本不降级逻辑零改动。
2. `jianli/src/components/PrivateAnswerDraft.tsx`：面板顶部新增常驻警告"离开或最小化窗口会清除未保存的编辑：请先点击保存草稿再离开窗口。私人草稿只保存在你的账号下，没有发送给企业"；渲染 lossNotice（role="alert"，与 notice 同文时去重不重复渲染）。hidden 仍立即 clear+关预览；恢复仍 activate+load 立即读取。
3. 新增 `jianli/tests/private-answer-recovery-notice.test.mjs`：14 项，全部用真实 `createPrivateAnswerSession` 与真实面板 SSR（sucrase 转译），未复制实现模型。

## 测试（原始输出见本目录）
| 运行 | 结果 |
|---|---|
| 红基线 `node --test tests/private-answer-recovery-notice.test.mjs`（修复前） | 14 tests / 12 fail / 2 pass（绿者为既有行为回归锚点）/ 0 skip → red-target.raw.out |
| 绿目标（修复后同命令） | 14/14 pass / 0 fail → green-target.raw.out |
| 受影响 `private-answer-workflow + failure-reply-draft + verification-reply-draft` | 56/56 pass（31原断言零修改全绿）→ green-affected.raw.out |
| 前端完整 `node --test tests/*.test.mjs` | **207/207 pass** / 0 fail / 0 skip（193基线+14新增）→ green-full.raw.out |

- 红基线注：首次红跑因新测试自身脚手架缺陷（gate 同时挡住首读）出现 8 项 cancelled，修正脚手架后重跑，上表红基线为最终版；实现红原因均为 lossNotice 未定义/常驻警告缺失，符合预期。
- probe1 对照：复跑 31 号探针（probe1-postfix-contrast.raw.out）仍 PASS——探针把"用户可见"近似为 notice 字段单值，而修复把持续丢弃事实移至独立 lossNotice 字段（探针不读取）；其断言的"load 首段同步清 notice"在设计上仍然成立（notice 生命周期未变）。用户真实可见性由新测试的面板 SSR 断言证明（读取中/成功后/失败后均渲染丢弃声明）。31 号探针文件与证据零改动。

## 关键行为证明（新测试覆盖）
未保存文字/引用选择丢弃→恢复读取中+成功+失败丢弃提示均可见；无编辑不声称丢弃；固定文案不携带旧正文（SECRET 标记断言）；再次编辑/显式保存/复制结束提示；新会话不承接旧会话通知；dispose 后迟到保存回执不复活；clear 后旧 save/copy/setText 全拒绝直到显式 activate+load；恢复后来源重验失败仍拒复制；恢复读取期间的编辑保护行为不变。不恢复旧文字、无 localStorage、无自动保存、无任何发送入口。

## 未验证项（如实标注）
- 生产页面与 390px 实测：按卡由 Codex 集成后执行（本卡禁止浏览器/服务操作）。
- scripts/e2e/private-answer-page-runner.mjs 未跑（需真实前后端+Chrome）；其文本断言仅涉及复制成功提示，与本改动无冲突。
- 未运行类型检查/构建（卡列禁止共享构建）；`docs/当前接口.md` 的工作区改动为他人既有改动，未触碰。

## Manifest
- 源hash与证据hash：manifest.sha256；diff：diff.patch（163行，仅上述两个源文件）。
- 禁区核对：未改 AuthProvider/API/其他页面/原测试断言；未动 33（后端AI）35（启动器）；无 DB/服务/浏览器/安装/联网/外发/Git 提交推送/reset/clean；未改 stage。
- 交棒：请 Codex 复核 diff.patch 与 31 原测试兼容性后提交；生产页面/390px 验收后关闭本卡。
