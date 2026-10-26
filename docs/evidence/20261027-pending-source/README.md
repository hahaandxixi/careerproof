# 本地待集成源码快照（2026-10-27）

本分支仅保存主工作区尚未上传的 42 个源码、测试、工具和安全模板文件；基线为 `8ca91cc`。原工作区文件逐字保留，未切换其分支、未写业务库、未启动服务或真实模型请求。不能将本分支当作最终候选或直接合并。

## 范围与边界

- UUID 短路径 helper、规则文字、企业固定材料摘要、回复摘要、材料选择器、报告入口准备提示、触控尺寸，以及配套测试。
- 既有 UUID helper 会通过正则剥离文本内 UUID 前缀，尚未证明合法 UUID 文件名、同名多版本显示都安全；保存实现不表示接受其语义。
- `ReportDetail.tsx` 与 [PR #1](https://github.com/hahaandxixi/careerproof/pull/1) 同路径有差异。禁止通过覆盖文件整合；该 PR 的直接上传新版流程仍以其独立分支为准。
- 两个 JSON/BOM 工具和私人草稿浏览器 runner 是历史工具；本轮只跑离线测试，未执行其访问服务或材料操作。
- 不包含 PDF、人工评审原件、凭据、数据库和临时依赖。

## 本轮实际检查

独立 worktree：`backend/.tmp/github-source-20261027`。Python 3.12 的既有验证环境，Node 22.23.1；前端依赖只读复用同版本目录，不借此声称干净安装。检查针对这 42 个快照文件与基线，非 PR #1 源码。

| 检查 | 命令 | 结果 |
| --- | --- | --- |
| 后端定向 | `python -m pytest app/tests/test_display_path.py app/tests/test_rule_narrative.py app/tests/test_evidence_scope.py -q` | 19 通过，0 失败 |
| 后端静态 | `python -m ruff check` 本轮 7 个 Python 文件 | 通过 |
| 前端整体 | `npm test` | 476 通过、1 失败、0 跳过 |
| 前端 lint | `npm run lint` | 0 错误，既有鉴权图片警告 1 条 |
| 类型检查 | `npm run typecheck` | 通过 |
| 生产构建 | `npm run build` | 通过；未启动该构建 |
| 历史 runner | `node --test scripts/e2e/private-recovery-notice.test.mjs` | 9 通过、1 失败 |

失败保留：

1. `tests/keyboard-focus.test.mjs` 的“每处 outline-none 都必须同行配回焦点样式”，定位 `ReportDetail.tsx:67`。尚未判断是产品焦点缺口还是跨行检查假设；未删断言或改样式掩盖。
2. 历史 runner 的 `fixed notice copy is bound byte-for-byte to the product source`，旧 `DISCARD_NOTICE` 与当前 `private-answer-workflow.ts` 不一致。未重写历史工具。

完整原始日志、全工作树文件分类及排除原因放在 `codex/careerproof-pending-evidence` 分支的 `docs/evidence/20261027-github-sync/`。远端 CI 以该分支 Draft PR 的实际结果为准；本记录不预写通过。

## 合并前仍需处理

逐项与 PR #1 选择可接受差异，复核 UUID 身份与路径语义、两项失败，再做受影响浏览器验收。当前只确认源码可安全远端保存，不确认整批可合并。
