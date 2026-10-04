# B-16：企业简历下载的 blob URL 生命周期 —— 证据包 summary（v2，含 Codex 审计勘误）

## 基线
- 嵌套仓库 `D:\jbcode\web ai\jianli`，分支 `main`，HEAD `1cdb506`（[origin/main: ahead 1]）。
- 开始时未提交：B-11 两个后端文件（本任务未触碰）、`docs/Bug测试与问题清单-20261002.md`、
  `docs/README.md`；未跟踪：手册、约束、B-11 验收记录、task-cards/、templates/。
  stash@{0} P2 原样在位。结束时新增仅 `docs/evidence/20261004-B16/`。

## 可复现问题
- **合成模式层面：未复现失败**。在 Chromium（本机 Chrome 154.0.8037.93 headless + CDP）中逐字
  复刻 ApplicationBoard.tsx:96 交付模式：A 64KB、B 256MB、C 双击连下两个、D 点击后 300ms 页面
  卸载（撤销定时器不触发）四场景全部 `completed`，**六项落盘大小 + SHA-256 与源哈希全部一致**；
  E 机制验证：撤销 1.5s 后 `fetch(同URL)` → `"Failed to fetch"`（撤销生效，机制存在但 1 秒未咬伤）。
  输出记录：[rerun-success.log](rerun-success.log)（**人工誊录摘录，非完整原始 stdout**：guid 行
  已被过滤命令移除无法补全；六项 match 行与 ALL_DONE 为逐字完整，见该文件头说明）。
- **限制（显著标注）**：① 成功运行复用了此前崩溃尝试遗留的 Chrome 实例（9333 端口冲突，
  新实例退出）；全新单实例重验仅完成场景 A（哈希一致，[rerun-fresh-partial.raw](rerun-fresh-partial.raw)
  + `sha256sum` 独立复核）、B 文件完整写盘但未及比对，随后按限时指示取消并**不再重试**；
  ② 这是合成复现页，**不是真实产品页面验收**；③ 非 Chromium 内核未测。
- 任务卡第 3 条"0 字节或失败尚未复现，先验事实"经实测在 Chromium 内仍未复现。

## 结果
- **未修改任何产品代码**（任务卡第 10 条停止条件成立：无真实产品失败复现，不为改而改）。
  `ApplicationBoard.tsx:96` 保持原样；B-16 维持 **待确认**，风险范围收窄为"非 Chromium 内核 +
  真实产品页面未验"。
- 修正过程中 harness 自身三处确定缺陷（含 Codex 审计指出的 server.mjs MIME 键错误）已修复并
  记录于 [repro-attempt.log](repro-attempt.log) §0/§3 与 [harness/README.md](harness/README.md)。

## 文件
- 变更列表：仅 `docs/evidence/20261004-B16/`（summary.md、tests.log、review.md、
  repro-attempt.log、rerun-success.log、rerun-fresh-partial.raw、3 个基线日志、harness/ 6 件）。
- 越界文件：无。

## 测试
- 前端全量：123 通过 / 0 失败 / 0 跳过（基线，改动前）→ [tests-baseline-full.log](tests-baseline-full.log)
- 类型检查：通过，退出码 0 → [typecheck-baseline.log](typecheck-baseline.log)
- 生产构建：通过，退出码 0 → [build-baseline.log](build-baseline.log)
- 新增回归测试：无（未修改产品代码，无新增被测对象；此为"未运行"而非"通过"）。
- Ruff：不适用（前端任务，未改 Python 文件）。
- 超时记录：`chrome --version` 探测挂起 >5 分钟（GUI 程序不退）；全新实例重验约 8 分钟完成 A、B
  两场景后按限时指示取消。两次均属复现工具过程，不构成产品结论。

## 页面
- **未验证**：真实产品页面的企业下载首验（桌面 + 390px）、下载列表、文件大小/哈希、截图——
  本任务浏览器工具（IAB）无法访问回环地址，CDP harness 只覆盖合成模式。`screenshots/` 未创建，
  无人工替代证据。合成夹具未启动故无需恢复；本次创建的进程/服务器/空白页均已精确清理
  （清理记录：[repro-attempt.log](repro-attempt.log) §6）。

## review-agent
- 已实际调用（技能内只读规程），范围与逐条结论见 [review.md](review.md)：**No findings**；
  残余风险已按复现结果更新（非 Chromium 内核 + 真实页面未验）。

## 结论分层
- 程序级：已验 —— 既有前端 123 用例、类型检查、生产构建全绿（基线证据）。
- 合成模式级：已验（Chromium 154）—— 1 秒撤销不破坏下载；撤销机制生效。
  ⚠️ 附实例限制（复用实例运行 + 全新实例仅验 A）。
- 页面级（真实产品）：**未验** —— 合成 harness 不能替代页面验收。
- 其他浏览器：**未验**（Firefox/Safari）。
- 真实模型：不适用。独立语义复核：**未做/不适用** —— review-agent 是代码缺陷只读审查，
  不构成 AI 语义复核；本项无 AI 生成内容的语义复核环节。Codex 终审待签。

## 下一项建议
- B-16 保持待确认，先补真实产品页面的企业下载验收；下一批优先 **B-08**（模型实际用量与任务租约解耦防重复入账）。可定位证据：本 summary
  结论分层节 + docs/Bug测试与问题清单-20261002.md 第 192 行。

## Codex 终审
- 2026-10-04 审计通过，**仅签收前端基线检查与合成 Chromium 复现范围**。抽查了服务端 MIME
  修正、驱动落盘哈希比较逻辑、六项 match 摘录和首次误归因勘误；证据文件已明确区分誊录摘录与
  原始日志。由于完整运行的 stdout 未保存，且真实产品页面、Firefox/Safari 未验，B-16 保持待确认。
