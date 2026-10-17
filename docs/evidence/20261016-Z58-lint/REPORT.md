# 传智杯58 · 前端 lint 门禁 · 交棒报告（ZCode GLM，2026-10-16）

基线 e94be9b。Stage：`backend/.tmp/z58-lint-20261016/`（全部安装/运行均在此，未触碰任何 served/Codex stage）。

## 变更文件（全部在任务卡允许范围内，src 零改动）
- `jianli/package.json` — `lint`: `next lint` → `eslint .`；新增 devDeps（精确锁定）：`eslint@9.39.5`、`eslint-config-next@15.5.27`、`@eslint/eslintrc@3.3.7`
- `jianli/package-lock.json` — 纯增量：138→416 条目（+278 全为 eslint 工具链），0 移除、0 既有包版本变更；next 15.5.27 / react 19.0.0 / typescript 5.9.3 不变；lockfileVersion 3→3
- `jianli/eslint.config.mjs`（新）— flat config：`compat.extends("next/core-web-vitals", "next/typescript")`；ignores 仅生成产物（node_modules/.next/.next-e2e/out/next-env.d.ts，与 jianli/.gitignore 对齐）
- `jianli/tests/lint-config.test.mjs`（新）— 6 项工具测试（脚本非交互、版本锁定、presets 激活、无本地 rules 覆盖、ignores 白名单、`--print-config` 运行时加载）
- `.github/workflows/ci.yml` — frontend job 在 npm ci 后新增 `Lint` 步骤（`npm run lint 2>&1 | tee .tmp-ci/npm-lint.log`，与本地一致）+ lint 日志 artifact；test/typecheck/build 门禁未动

## 版本依据
eslint-config-next@15.5.27 与 next 15.5.27 锁步，peer 接受 `eslint ^7.23 || ^8 || ^9`；取 9.x 最新 9.39.5（latest 10.13.0 超出 peer 范围，不取；npm 提示 9.x EOL 属预期，等 Next 16 升级路径）。@eslint/eslintrc 3.3.7 为 create-next-app@15.5 平移 flat config 所需。Node 22.23.1 本地=CI。

## 验证矩阵（日志在本目录）
| 项 | 结果 |
|---|---|
| 原始 `npm run lint`（基线） | exit 1 — next lint 已弃用 + 无配置时进入交互提示，非 TTY 直接失败（00） |
| 合成无效条件 Hook fixture | exit 1 — `react-hooks/rules-of-hooks` error 捕获（01） |
| 合成有效组件 fixture | exit 0（02） |
| 真实项目 `npm run lint` | exit 1 — **1 error / 7 warning**（03），无任何 rules-of-hooks 违规 |
| 真实项目 `npm run typecheck` | exit 0（04） |
| 工具测试 tests/lint-config.test.mjs | 6/6 pass，exit 0（05） |
| lock 完整性 | stage `npm ci` exit 0（+357 包）；diff 摘要（06） |

## 交给 Codex 的现存发现清单（我未改任何源码）
**error（CI Lint 步骤将红，直到修复）**
- `src/app/error.tsx:23:9` — `@next/next/no-html-link-for-pages`（`<a href="/">` 应改 `<Link href="/">`）

**warning（默认严重级，全部保留、可见、不拦截退出码）**
- `src/components/MaterialPreview.tsx:29:49` — `react-hooks/exhaustive-deps`（cleanup 读 `fileRequest.current`）
- `src/components/NotificationCenter.tsx:32:33` — `react-hooks/exhaustive-deps`（cleanup 读 `generation.current`）
- `src/components/NotificationLink.tsx:31:33` — `react-hooks/exhaustive-deps`（cleanup 读 `generation.current`）
- `src/components/PrivateAnswerDraft.tsx:76:6` — `react-hooks/exhaustive-deps`（缺依赖 `props`）
- `src/components/VisualEvidencePanel.tsx:46:7` — `@next/next/no-img-element`
- `tests/application-board-session.test.mjs:124:46` — `@typescript-eslint/no-unused-vars`（`args`）
- `tests/private-answer-workflow.test.mjs:731:7` — `@typescript-eslint/no-unused-vars`（`reads`）

## 严重级决策（按卡要求记录）
invalid Hook 调用保持 error（配置未动该规则，fixture 已证）；exhaustive-deps 等既有发现保留为 warning——这是 `next/core-web-vitals` 预设的默认级，不设 `--max-warnings`、不全局关规则、不加内联抑制，因此每次运行都完整可见；修复它们需要业务语义判断（ref 时序意图），归 Codex。

## 未做 / 留给 Codex
- 未跑全量前端测试、未跑生产 build、未真实验证 CI 运行（yaml 已本地解析校验）；未碰数据库/服务/.env/提交推送。
- 过程坑：eslint-config-next 的 `@rushstack/eslint-patch` 使配置文件无法在 ESLint 之外直接 import（工具测试第 1 轮即此失败，改用 `--print-config` 子进程后 6/6 绿）。
- hash 与状态见 `07-hashes-and-status.txt`。
