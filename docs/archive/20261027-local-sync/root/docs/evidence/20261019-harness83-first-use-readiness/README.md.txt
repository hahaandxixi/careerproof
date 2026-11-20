# 传智杯83 · 首次使用"无材料死路"最小修复

## 1. 本轮解决的真实障碍

新学生（账号下没有 `completed` 简历版本）打开任一岗位详情时，`MatchForm` 只渲染出空的版本选择器和一个
`disabled={busy || !resumeVersionId}` 的灰按钮「生成我的匹配报告」：**不说明缺什么，也不给上传入口**。
用户无法从当前页知道下一步，只能自己猜去顶部菜单找"个人材料"。属于方向1（首次用户不知道下一步）。

修复前源码：`JobDetailView.tsx:137` 的按钮禁用条件；页面无任何 empty-state 文案（已核对 141 行全文）。

## 2. 参考项目与借鉴点（只读 README，未下载运行）

| 项目 | 文件 | 借鉴内容（思路，非代码/文案） |
| --- | --- | --- |
| A. MadsLorentzen/ai-job-search | [README.md@master](https://github.com/MadsLorentzen/ai-job-search/blob/master/README.md) | `/setup` 会**先探测用户已有什么材料**（documents 目录 / 粘贴 CV / 访谈三选一）再决定引导路径 —— 对应"按真实已保存状态给下一步，而不是给一个不能点的按钮" |
| B. kyle-kw/ai-job-app | [README.md@main](https://github.com/kyle-kw/ai-job-app/blob/main/README.md) | 初始化完成前是向导、完成后首页切换为工作台；并要求"缺材料/配置失败时引导恢复" —— 对应"缺材料要指名缺什么 + 给已有入口" |
| C. ququyixiaozei/aijobs | [README.md@master](https://github.com/ququyixiaozei/aijobs/blob/master/README.md) | 只借鉴"无依据的信息明确缺失、不猜测填充"的原则（其 freshness/archive 机制与本轮无关） |

获取方式：`raw.githubusercontent.com` 只读抓取，各 README 均为 MIT（A、B）／未声明（C，仅读思路）。
未复制任何代码、图标或文案；评分权重、淘汰规则一律未采用。

## 3. 基准与改动

基准 HEAD：`dac9650`（分支 `main`）。正常站在跑：3000/8000（进程 345092 / 321084）。

| 文件 | hash（前16） | 改动 |
| --- | --- | --- |
| `jianli/src/lib/match-readiness.ts`（新） | `1ee76970a1be25d3` | 纯函数：`loading` / `missing-resume` / `ready` 三态；缺简历时给出中文说明 + `/portfolio` 入口 |
| `jianli/src/components/JobDetailView.tsx` | `3a31ccbef20dad07` | 零可用简历时用说明面板替代表单（含"不自动投递、不代表已分享"提示）；其余路径完全不变 |
| `jianli/tests/match-readiness.test.mjs`（新） | `db2fcbc141853647` | 4 条回归：加载中不催上传；零简历给出入口；有简历为 ready；解析中不算可用 |

未改后端、评分、等级、报告快照、投递授权、数据库；未新增依赖。

## 4. 验证

| 命令 | 环境 | 结果 |
| --- | --- | --- |
| `node --experimental-strip-types --test tests/match-readiness.test.mjs` | `jianli/`，node v22.23.1 | **4 passed / 0 failed** |
| 同一测试在把 `=== 0` 改为 `< 0` 后 | 同上 | **2 passed / 2 failed**（`not ok 2` 零简历、`not ok 4` 解析中），恢复后 4/4 |
| `node node_modules/typescript/bin/tsc --noEmit` | `jianli/` | **exit 0** |
| eslint（复用 `backend/.tmp/task62-lint` 依赖，junction 已删除） | `backend/.tmp/task83-lint` | `JobDetailView.tsx` 0/0，`match-readiness.ts` 0/0 |
| `tests/job-application-status.test.mjs`（相邻既有套件） | `jianli/` | 13 passed（未受影响） |

红→绿说明：这是新增纯函数，红测用"把零简历判成 ready"的变异，能准确抓到原问题；不是新写的镜像实现。

## 5. 是否已加载正常站

**未加载。** 正常站运行的是既有构建，本轮未重建、未重启、未部署；3000 上仍是旧页面。
按边界要求（服务所有权与构建目录归 Codex），"说明面板已出现在 3000"**未验证**。
已验范围：源码 + 类型 + lint + 纯逻辑回归；未验范围：桌面/390px 实际渲染、键盘焦点顺序、
`role="status"` 在真实 AT 下的播报、以及"零简历学生"在真实账号下的完整观感。

## 6. 失败记录与剩余风险

- 首次红测用 `Set-Content` 改写导致整文件加载失败（BOM/编码），已改用 edit 工具重做，得到断言级红测；
  第一次的失败输出不作证据使用。
- 残留风险：若学生只有"解析中"的简历，页面会显示缺简历面板；文案已写"等待解析完成"，但**解析失败的
  简历仍会落入该分支**，不会提示"上次解析失败"。这是已知的下一步改进点，超出本轮最小范围。
- 有简历但无项目材料的学生不受影响（项目为可选）。

## 7. Codex 下一步（可直接执行）

1. 审阅 `git diff -- jianli/src/components/JobDetailView.tsx` 与两个新文件；
2. 按现有构建流程重建前端并加载正常站，用一个**零已完成简历**的合成学生账号打开任一岗位详情，
   确认说明面板出现、`去个人材料上传简历` 可达 `/portfolio`、桌面与 390px 均不溢出；
3. 若认可，随本轮改动一并提交（本轮未 commit/push）。
