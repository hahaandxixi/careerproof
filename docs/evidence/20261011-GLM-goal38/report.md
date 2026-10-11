# 传智杯38：私人草稿恢复提示独立审查与回归（交付）

- 日期：2026-10-11。Git根D:\jbcode\web ai\jianli。基线=34号工作区成果（未提交）：`src/lib/private-answer-workflow.ts` sha256 `36048005…`、`src/components/PrivateAnswerDraft.tsx` sha256 `c6f04275…`，与34号manifest逐字节一致；HEAD `ef29532`。审查方法：review-agent技能（缺陷优先、只读、逐条给出真实可达路径，不可达则排除）。

## 审查结论：发现1个缺陷（已红绿修复），其余核实项全部通过

### [P1] 第二次clear抹去仍然存活的丢弃提示 — src/lib/private-answer-workflow.ts:482（34版）

34号 `clear()` 无条件写 `lossNotice: hadUnsaved ? DISCARD : ""`。当丢弃提示已发布（lossNotice=DISCARD）且状态已被首次clear清干净后，任何一次"无新丢弃"的第二次clear都会把它覆盖为 `""`——违背该字段自身文档化生命周期（"仅再次编辑或显式保存/对照/复制时结束"，clear 不在其列）。组件中 clear() 仅由 visibilitychange hidden 分支调用，以下三条路径全部真实可达（页面上恢复读取启动与再次隐藏之间无需用户交互，网络慢或读取失败时窗口很大）：

1. **恢复读取进行中再次hidden**：hidden①（丢弃提示发布）→ visible①（activate+load启动）→ GET未返回时hidden② → clear() 看到已干净状态 → lossNotice="" → visible② 恢复成功后，被丢弃的编辑无任何解释（P1-1症状经第二路径复发）。
2. **读取失败后重复隐藏**：恢复读取失败（error+丢弃提示可见）→ 用户再次隐藏窗口 → clear() → lossNotice="" → 再返回后丢弃提示永久消失。
3. **成功恢复后再次hidden（无新编辑）**：同样抹去，违背文档化生命周期。

### 修复（最小，仅 clear() 8行内）

- 无新丢弃时保留既有提示：`lossNotice: hadUnsaved ? DISCARD : carriedLossNotice`（`carriedLossNotice = state.lossNotice` 在重置前捕获）；同步更新两处生命周期注释。notice 字段语义不变（该字段在 hidden 期间渲染、页面不可见，visible 后即被 load 清空，用户不可见窗口无影响）。

### 核实通过项（如实记录，未发现缺陷）

- **无编辑与未保存编辑差异**：`privateAnswerIsDirty` 布尔驱动两套固定文案；引用选中后取消等回退场景正确判净。
- **load期间编辑**：编辑序号保护不变；UI 侧 textarea/fieldset 在 reading 时 disabled，会话级编辑保护为程序化兜底；编辑开始即按生命周期结束提示（测试守护，防修复把提示永久化）。
- **明确操作失败丢失告知**：显式保存/对照/复制**发起时**即清空 lossNotice（即使随后失败）——34号既定设计：用户主动操作意味着面板在场已见提示，且失败路径另有 error/notice 替代呈现；copy 各拒绝分支也都即时给出 notice。判为有意行为，不作缺陷。
- **账号/任务切换**：身份切换由父组件 key 重挂载、taskId 切换重建会话，新会话状态零承接（既有测试守护）。
- **失效来源/迟到回执/旧DOM门禁**：copy 的 sourceCheck pending/failed/无保存/dirty 四道门禁、clear 失活拒绝、迟到保存回执不落账、读取不降级基线、来源代际门禁全部未放宽（diff 仅增加 lossNotice 清空点）。
- 本审查未虚构浏览器多发 visibility 事件等不可达场景。

## 测试（原始输出见本目录）

| 运行 | 命令（jianli/ 下） | 结果 |
|---|---|---|
| 红基线 | `node --test tests/private-answer-recovery-notice.test.mjs` | **17 tests / 14 pass / 3 fail**（恰为3个新用例，失败点均为"第二次clear不得抹去丢弃提示"，actual=''）→ red-target.raw.out |
| 绿目标 | 同上 | **17/17 pass** → green-target.raw.out |
| 受影响 | `node --test tests/private-answer-workflow.test.mjs tests/private-answer-recovery-notice.test.mjs tests/failure-reply-draft.test.mjs tests/verification-reply-draft.test.mjs` | **73/73 pass**（34原断言零修改）→ green-affected.raw.out |
| 完整Node | `node --test tests/*.test.mjs` | **210/210 pass** / 0 fail / 0 skip（34的207+新增3）→ green-full.raw.out |
| 类型检查 | `npm run typecheck`（tsc --noEmit） | exit 0 → typecheck.raw.out |

新增3用例（追加于34号测试文件末尾，34原断言零改动；34基线重建核对：截断至"传智杯38"标记处 sha256=`dd9af75b…` 与34号manifest一致）：复刻组件 visibilitychange 真实序列（hidden→clear；visible→activate+load），覆盖上述三条路径，并守护"编辑仍按生命周期结束提示"防过度修复。

## 范围与禁区核对

- 38号实际改动仅：`src/lib/private-answer-workflow.ts`（clear()+两处注释）、`tests/private-answer-recovery-notice.test.mjs`（末尾追加3用例）。`PrivateAnswerDraft.tsx` 本轮零改动（hash与34号manifest一致）；diff.patch 为相对34工作区基线的增量（行尾已归一核对），仅含上述两个文件。
- 未改其他源码/旧测试断言；未动36（后端AI）/37（启动器）文件（工作区中 Start-Local.ps1、backend/* 等既有改动为他人/其他任务改动，未触碰）。
- 本轮仅执行：Node 测试 + `npm run typecheck`（本任务独占）；未运行 next 构建、未启动服务/浏览器/DB、未联网/安装/真实模型/.env、未改活跃stage/P2、未Git提交推送、未reset/clean。

## 未验证项（如实标注）

- 生产页面与 390px、集成验收：按卡由 Codex 另行操作。
- 面板渲染行为由既有 SSR 测试守护（lossNotice 渲染逻辑本轮未改动，无需新面板用例）。

## Manifest

- 源hash与证据hash：manifest.sha256；diff：diff.patch（相对34基线，70行变更，仅上述两个文件）。
- 交棒：请 Codex 复核 diff.patch 与红绿输出后提交；生产页面/390px 验收后关闭本卡。
