# PRODUCT-01 来源代际修复 · 个人GLM-5.3交棒（2026-10-06）

## 结论：三项来源交错已修复，全部门禁通过

最小协议（来源代际）：`sourceRun` 在每次 `refreshReferences` 发起时递增并记录落账重验的
optionKeys。GET/PUT 回执发起于更近一次重验之前（`capturedSourceRun !== sourceRun`）时：
① 不得把 `sourceCheck` 改回 current（pending/failed 门禁由较新重验决定）；
② `saved.references` 经 `referencesUnderNewerValidation` 合并——被较新重验否决的引用不得借回执
复活 available，`selected` 同步用合并后引用重建；③ revision 前进、saving/reading 复位、编辑保护
（editSeq）、clear/dispose 失活护栏全部不变。来源新旧按发起顺序，与草稿 revision 无关。
发起晚于失败重验的读取/保存仍可重新建立 current（与既有"保存回执恢复可信"测试兼容）。

改动仅两处：`jianli/src/lib/private-answer-workflow.ts`（+代际计数/合并助手/条件写，含注释更新）、
`jianli/tests/private-answer-workflow.test.mjs`（+4项回归）。Flash轮前端改动原样保留，未动后端/
数据库/.env/runner/通知/企业/构建/Git/P2。

## 顺序检查记录（原始输出+EXIT见本目录，hash见hashes.txt）

| 步骤 | 命令 | 结果 | 证据文件 |
|---|---|---|---|
| 红回归 | node --experimental-strip-types --test tests/private-answer-workflow.test.mjs | 36过/4红（新增项） | regression-red.raw.out |
| 绿回归（修复后） | 同上 | 40过/0败 EXIT=0 | regression-green.raw.out |
| Codex新3探针 | PRIVATE_ANSWER_SOURCE_FILE=当前helper node --experimental-strip-types --test …/independent-source-ordering.test.mjs | 3过/0败 EXIT=0 | independent-source-ordering-green.raw.out |
| Codex旧两组8探针 | 同方式 --test …/independent-races.test.mjs …/independent-binding.test.mjs | 8过/0败 EXIT=0 | independent-old8-green.raw.out |
| 全套 | npm test | 193过/0败 EXIT=0（原189+新4） | npm-test.raw.out |
| 类型 | npm run typecheck | EXIT=0 无输出 | typecheck.raw.out |

探针与红证据（independent-source-ordering.test.mjs / source-ordering-red.raw.out / 两组旧探针）
本人未改动，hash已记录。

## 自审发现

1. 新测试32首轮红为 TypeError：漏覆写 getDraft（初始 saved 引用为空），断言越界，未踩到目标
   断言；立即补 `getDraft: savedView({references:[savedReference()]})` 后绿。该PUT场景的权威红
   证据是 Codex 探针红输出（其测试2），故未重造红。
2. 合并只在 `appliedValidation.run > capturedSourceRun` 时生效：若回执晚于重验"发起"但该重验
   尚未落账，回执可用度照常写入，由该重验落账时按当时 saved 再判——探针3即此路径（copy 在
   pending 期间被拒）。
3. 载荷/接口未变：PUT 仍只带 text/references/expectedRevision，无新增对外请求；预览仍只来自
   已保存回执 snippet。待Codex复核项：生产构建与页面验收（本任务未启动服务）。
