# B-16 review-agent 只读缺陷审查（v2，含复现结果后的更新）

- 是否实际运行：是。通过 review-agent 技能执行（2026-10-04，只读模式，无任何文件修改）。
- 审查范围（当前工作树，无本次改动；基线 HEAD 1cdb506）：
  - `jianli/src/components/ApplicationBoard.tsx`（第 96 行 download/deliver 回调、blob URL 1 秒撤销）
  - `jianli/src/lib/application-board-session.ts`（run 的授权复查与 download 方法，第 47-79 行）
  - `jianli/src/lib/api/client.ts`（request 的 `responseKind="file"` 分支 161-198 行、
    `downloadApplicationResume` 240 行）
- 参照规程：review-agent 的 defect-first 规则（仅报告可从代码演示的可行动缺陷，不报告推测性担忧）。

## 审查问题与证据

1. **1 秒 revokeObjectURL 是否构成 0 字节/失败下载缺陷**：交付回调运行时，文件已由
   `request(..., "file")` 分支完整读入内存（client.ts:182 `await response.blob()`），
   `createObjectURL → anchor.click() → setTimeout(revoke,1000)` 与 ApplicationBoard.tsx:96 完全一致。
   浏览器时序失败路径无法从代码演示；合成 harness 实测（Chromium 154，见
   rerun-success.log）四种场景均完整交付、哈希一致，未复现失败。判为残余风险（非 Chromium
   内核），不构成 findings。
2. **页面卸载 / 重复下载的 URL 泄漏**：1 秒内卸载时撤销定时器不触发，但 blob URL 绑定
   Document 生命周期，文档销毁时由浏览器释放；harness 场景 D 实测点击后 300ms 卸载仍完整交付。
   重复下载各自创建 URL、各自在其点击后 1 秒撤销（场景 C 两文件均完整、无交叉中止）。
   未发现可行动缺陷。
3. **文件名解析（client.ts:181）**：`filename*=UTF-8''` 正则 + `decodeURIComponent` + 路径
   分隔符替换，解码失败落入 catch 回退 `resume.txt`；后端上传时已做 basename 截断；
   `quote/decode` 对 `%` 往返正确。未发现可行动缺陷。
4. **download→open 两次请求间的一致性（application-board-session.ts:74-76）**：若期间发生
   撤回，`api.open` 抛 404 → `run()` 进 catch → `deliver` 永不执行，方向为"失败关闭"，
   与固定约束 3 一致；现有用例 tests/application-board-session.test.mjs:104、:160 已覆盖。
   任务卡第 7 条不变量"先经现有授权复查才调用浏览器交付"**已存在**：run() 第 73-74 行
   `stillAuthorized` 列表复查后才调用 `result.deliver?.()`。未发现可行动缺陷。

## 结论

**No findings.**（B-16 审查范围内未发现可从代码演示的可行动缺陷。）

## 残余风险（非缺陷，供 Codex 终审；v2 已按复现结果收窄）

- Chromium 内核：合成 harness 已实测 1 秒撤销无害（64KB–256MB、双击、300ms 卸载；撤销后
  fetch 被拒证明机制生效）。⚠️ 该证据来自复用实例的一次完整运行 + 全新实例仅验场景 A，
  且为合成复现页而非真实产品页面。
- 未验证：Firefox（另存为对话框推迟 blob fetch 的历史行为风险高于 Chrome）与 Safari；
  真实产品页面的企业下载首验。
- Node test 套件无 DOM，撤销时序无法单测覆盖；如未来改动交付实现，应优先补浏览器级证据。
- 勘误记录：初版 review/summary 曾把首次复现失败归因于 CDP 限制，实为 harness server.mjs
  MIME 键错误（详见 repro-attempt.log §0），相关表述已在 v2 各文件中更正。
