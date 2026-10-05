# E2E-02 企业运行器及证据终审（只读审查草稿）

日期：2026-10-05。Git HEAD `76dfd59`（`fix(applications): preserve editable reply drafts across request failures`）。任务卡 `docs/task-cards/20261005-enterprise-final-review.md`。

审查者身份：本会话只读审查（review-agent 只读流程 + 本卡补充核对）。**本报告不构成也不自称任何 Codex 或其他代理的签收**；旧审计明确"尚未签收"（见下文），本报告仅按缺陷优先回报可复现问题、风险与未验项。唯一写入位置为本目录；未运行运行器/自动测试/浏览器/数据库/服务，未读 .env 或凭据内容，未调用模型 API/外网，未 Git 提交/推送/改 stash。

## 0. 读取快照（SHA256，行动前必须重算）

| 文件 | SHA256 | 说明 |
| --- | --- | --- |
| scripts/e2e/enterprise-browser-runner.mjs | `410d73d4225876e01acbf1aa5c03a7c26fd3e348ff370cd79f80dbaaab0a504f` | 1370 行，本报告全部运行器发现所绑定的快照 |
| scripts/e2e/runner-input.mjs | `e7c34a10da2f696ba6d464dfce7ec0ceaddd1c398fe5b65aa42f712e629f989c` | 42 行 |
| scripts/e2e/runner-input.test.mjs | `01db8b4e763c4721e8533ff82b8cf6e939142565547d5fbe07a31f533e646b59` | 65 行，静态 15 个 test 用例（未执行） |
| docs/evidence/20261005-E2E-enterprise-retest/RETEST-SUMMARY.md | `d5df8d51da76a6aca40c87c026164a7c1b13a90307637d15d5313964162814f8` | 新版复测总结 |
| docs/evidence/20261004-E2E-enterprise/SCENARIO-SUMMARY.md | `1a3b9754b11e8307259824a656b6603ed8ae9e6a330c4bab90ada3be06d93522` | 旧版场景总结 |
| docs/evidence/20261004-E2E-enterprise/codex-audit.md | `b382f595d4121586589a2e5dd0d2d4a57473575a82d9363d18a8a4e1ff509ddb` | 旧独立审计（基线 9e87fec，明确"尚未签收"） |

与前次审查 `docs/evidence/20261005-E2E-runner-review/report.md` 的快照（runner `68bcc83d…` 1291 行）相比，runner 与 runner-input.mjs 均已再次修订（本快照 1370 行）：EVIDENCE_DIR 固化为 `20261005-E2E-enterprise-retest`（L32）、引入 `withdrawnNotificationStatus` 映射（L20,1183）等。**本报告发现全部绑定 `410d73d4…` 快照；引用前次报告结论处逐项对当前快照重核，未沿用行号。**

## 1. 发现（review-agent 分级；无 P0/P1）

**[P2] record() 控制台路径输出未脱敏原文，绕过 scrub 管线 — scripts/e2e/enterprise-browser-runner.mjs:60 @410d73d4**
`record()` 把 `entry.detail` 经 `scrub()` 清洗后写入 results.json（L55-59），但紧随其后的 console 行模板使用的是**原始** `step.detail`（L60），而非已清洗的 `entry.detail`。文件头不变量（L6-7）声称"Secrets … never logged … even inside unexpected exception text"，scrub 管线（L48-53）正是为异常文本兜底而建；`main().catch` 把异常 stack 送入 record（L1367-1370）——该路径在 results.json 中被清洗、在控制台上原样输出，恰恰绕过兜底目的。当前未演示出实际泄漏路径（登录失败只报长度 L450、password 字段值永不读取 L361-363、新旧证据 JSON 敏感串扫描 0 命中，见 §3.2），属纵深防御缺口而非现行泄漏，故 P2。最小修复：L60 改用 `entry.detail`。

**[P2] withdraw-verify 的 open-card 检查可空泛通过（无落地证据仍记 pass）— scripts/e2e/enterprise-browser-runner.mjs:1303-1305 @410d73d4**
verdict 仅要求 `inaccessible.length>=2 && withdrawalEventCard && olderInaccessible.length>=1 && !aLeak`；当所有可打开卡的点击均未落地时 `openAnchors` 全为 `no-landing:…`，`aLeak` 恒为 false，verdict 仍为 **pass**（未落地仅产生 warn 子步骤 L1295）。这违反"无法证明不能 pass"原则：open-card 枚举（可打开卡永不指向 A）是本场景的核心阳性证明之一，无任何真实落地即通过属空泛通过。**历史证据已实际发生 4 次**：旧目录 withdraw-verify `10-01-22-716Z`（openCardAnchors=[""]）、`10-02-47-389Z`、`10-04-55-671Z`、`10-07-02-808Z`（均 no-landing）四个运行的 old-notification-A 步骤全部记 status=pass；唯有最终版 `10-09-19-774Z` 有真实落地锚点（`#application-8032fdb1…`（A2）与 `#application-d9c6411…`（B)）。最小修复：`openCount>0 且 openAnchors 无任何以 #application- 开头的真实落地` 时记 blocked（或至少不判 pass）。

**[P3] withdraw-verify verdict 无 blocked 取值，不可证明一律塌缩为 fail — scripts/e2e/enterprise-browser-runner.mjs:1304 @410d73d4**
与 download-withdraw 场景的 `withdrawnNotificationStatus`（runner-input.mjs:38-42：unavailable-notice→pass / REPORT-STILL-READABLE→fail / 其余→blocked）不同，withdraw-verify 的三类条件不满足时（如凭据缺夹具、撤回事件卡不可识别）只能记 fail。fail 是保守方向（不会造成假通过），但与同文件"缺证据→blocked"的既有语义不一致，会混淆"产品缺陷"与"夹具/依赖不可证"。修 P2 时可一并引入 blocked。

**[P3] withdraw-verify 的 withdrewAt 取自 EVIDENCE_DIR 中排序首个 download-withdraw-* 目录 — scripts/e2e/enterprise-browser-runner.mjs:1250-1256 @410d73d4**
若复测目录内同时存在多个 run-id 的 download-withdraw 证据（当前没有——retest 目录本轮未运行撤回，只有旧目录 20261004 有），时间关联可能取到别的运行的撤回时刻；影响仅限撤回事件卡的"时间戳关联识别"，aLeak 主证明不受影响，且取错时结果为 fail（保守）。当前休眠。另注：该时间关联本身只识别"哪张不可访问卡对应撤回事件"，非 API 对象级关联——旧审计第 3 条已声明不把其当完整关联证据，本审查沿用该保留意见（notification-filter 场景的定位不使用时间，见 §3.4，不违反任务卡"不靠时间猜"）。

**[P3] 凭据路径前缀守卫不含尾分隔符且未锁 e2e 子目录 — scripts/e2e/enterprise-browser-runner.mjs:601 @410d73d4**
`file.startsWith(path.join(ROOT,"backend",".tmp"))` 理论上放行 `backend\.tmp-evil\…` 前缀；但 RUN_ID 已被 `^[a-z0-9][a-z0-9-]{0,31}$`（runner-input.mjs:19）与凭据互锁 `raw.runId !== RUN_ID`（L603）双重锁死，该守卫不可达触发。纵深防御写法瑕疵。

**[P3] reply-failure 的窄视口 info 步骤在 about:blank 阶段测量且标签误导 — scripts/e2e/enterprise-browser-runner.mjs:757-761 @410d73d4**
`390-viewport` detail 写"(device metrics after first load)"，实际在 login/goto 之前测量（新证据 reply-failure…10-47-15 步骤[19]如实记录 viewport=980）；该场景的 390 证明实际依赖截图宽度（@2x 780px）与 viewport390 场景加载后的实测门槛（L1326-1327，status 随 w===390 通过/失败）。信息性步骤不影响判定，仅标签与时机不一致。

**[P3] Chrome spawn 失败时无 child error 监听 — scripts/e2e/enterprise-browser-runner.mjs:120-134 @410d73d4**
`spawn(CHROME,…)` 未挂 `error` 监听；chrome.exe 不存在等 spawn 失败会以 Node 未处理 'error' 事件崩溃，finally 清理与 results.json 均不落盘（此情形下 Chrome 未启动，无进程可清理，但证据中断无记录）。CHROME 路径硬编码（L23），属环境边缘情形。

**[P3] 文档精度：两份总结存在与原始 JSON 不完全一致的表述**
(a) RETEST-SUMMARY.md 表格引用 late-response 通过证据为 `late-response-…10-49-31`，但磁盘上最终通过运行是 `late-response-…11-22-15-479Z`（总结成文后又有 `11-21-36-586Z` 中止运行与 `11-22-15-479Z` 重跑，两者未被总结收录；11-22 运行绑定 `codex-late-response-approved.raw.out` EXIT=0）。结论本身仍成立（10-49-31 与 11-22-15 两次均真实通过），属文档未随重跑更新。
(b) RETEST-SUMMARY.md 称"护栏13项测试"；runner-input.test.mjs 静态计数为 **15 个 test 用例**（1 默认值 + 11 组危险参数循环 + 1 CLI 拒绝 + 1 凭据 + 1 撤回映射）。本卡禁止执行测试，计数未经运行验证，仅静态核对存在出入。
(c) SCENARIO-SUMMARY.md（旧）称"10-0x三次no-landing抖动"；实际 no-landing/空锚点运行有 **4 个**且其 results.json 中 old-notification-A 记录的是 **pass**（非"标fail"）——与 §1 第二条 P2 直接相关，历史表述低估了空泛通过的数量与性质。

## 2. 前次运行器审查（20261005-E2E-runner-review）发现的当前状态（逐项对本快照重核）

| 前次发现 | 当前快照状态 |
| --- | --- |
| [P2] `--scenario` 越界写（STAGE_DIR 拼接） | **已修复**：runner-input.mjs 在任何 mkdir 前白名单校验（ENTERPRISE_SCENARIOS 冻结，L2-5），失败 exit 2 "no files were written"（runner L28-29）；测试绑定证据目录不变式（runner-input.test.mjs:30-45） |
| [P2] RUN_ID 正则与 ps1 不一致、参数吞噬 | **已修复**：与 ps1 同一 `^[a-z0-9][a-z0-9-]{0,31}$`（runner-input.mjs:19），成对解析拒绝重复键/`--`开头值/缺值（L10-17） |
| [P2] 聚合退出码把 no-notice-no-report（warn）当成功 | **已修复**：withdrawnNotificationStatus 映射缺失证据→blocked（runner-input.mjs:41），blocked 计入 notPassed→exit 1（runner L1358-1361）；download-withdraw old-notification-A 步骤改用该映射（runner L1183） |
| [P3] JSON.parse 错误原文进日志 | **已修复**：parseCredentialDocument 统一抛固定消息、不带 cause（runner-input.mjs:28-36），测试断言无源片段回显（runner-input.test.mjs:47-57） |
| [P3] Stop-E2E 子孙 PID 复用窗口 | 不在本卡范围（卡指定审查 runner/runner-input/测试；ps1 归前次卡），未重查 |

## 3. 任务卡要求逐项核对结果（全部通过项均绑定证据 hash）

### 3.1 参数/路径拒绝顺序 ✅
parseRunnerArgs 在任何文件系统 I/O 之前执行（runner L27-30 在 L34-35 mkdir 之前）；拒绝顺序为：未知键/重复键/缺值/`--`开头值 → runId 正则 → 场景白名单（runner-input.mjs:7-24）。无效参数 exit 2 且不建目录；测试以真实进程断言 runtime 目录不存在、既有证据目录列表不变（runner-input.test.mjs:30-45）。凭据路径守卫在读取前执行（L601），runId 正则使遍历不可达。

### 3.2 凭据脱敏 ✅（含一处 P2 纵深缺口，见 §1）
SCRUB 在凭据加载时填充、早于任何 record（L604-606 → main L1351）；record 清洗 entry.detail（L58）；fillText 失配只报 label+长度（L450）；FINDER 对 password 输入框不读取任何值（L361-363）；登录截图先于输入（L617）。**本审查对 `20261005-E2E-enterprise-retest/` 与 `20261004-E2E-enterprise/` 全部 JSON 做 password/token/cookie/secret 大小写不敏感扫描：0 命中**；证据中出现的均为合成具名正文与相对路径。未读取凭据文件内容本身；凭据文件路径字符串已在旧证据 codex-closure-startup-approved.txt 出现（仅路径非内容，本报告不复述）。控制台旁路见 P2 第 1 条。

### 3.3 动态 Chrome 调试与进程自有清理 ✅（强制击杀路径无实跑证据，见 §5）
`--remote-debugging-port=0` 动态端口 + 每 profile 独立目录（L120-134）；启动前删除残留 DevToolsActivePort（L118-119）防死端口锁定；端口等待 20s（L135-143）。stop() 顺序：Browser.close → 3s 退出等待 → 仍存活时 `pidStillOurs()` 以 Win32_Process CommandLine 含本实例自有 `--user-data-dir` 为准 → 核验通过才 `taskkill /T /F`，不核验通过记 warn 放弃（L231-248）。防误杀为 fail-safe（探针失败/超时/进程消失一律不杀）。新证据各场景 chrome-stopped 均 exitCode=0（优雅退出），force-kill 路径未被任何保留证据实跑过（前次审查 v3 探针已离线核验含空格路径下 includes 判定有效）。

### 3.4 超时与 fail/blocked 真实退出码 ✅
所有 CDP send 15s（L195-198）、goto 30s、waitFor 有界、下载 30s（L1030）、hold 竞速 15s（L895/965/1007）。main() 聚合 fail+blocked→exitCode 1（L1358-1364），异常中止→1（L1367-1370），参数无效→2（L29）。证据链：失败运行 `late-response-…10-48-51` scenario-complete fail（`d6ecfb17…`，草稿断言 bug）；中止运行 `11-21-36-586Z`（`52ed44bc…`，Chrome exitCode=2147483651 + cdp closed，`codex-late-response.raw.out` EXIT=1，`daeee064…`）；最终通过 `11-22-15-479Z`（EXIT=0，`7f4ce67b…`）。

### 3.5 旧撤回通知证明（历史与新证分开列，不把旧失败记成新版通过）✅
- **旧 download-withdraw `04-41-28-116Z`（`23247bae…`）**：撤回已发生（不可逆）。步骤[5] download-A sha256=`a0149d5a113b3432d86c5cf235e26aa8283b37b6ac2550ba704432a75c1c6b6b` matchesAuthorizedFile=true；步骤[13] board-A-unreadable **fail**（脚本错页 bug，当时 tab 在 jobB 板误查 jobA 列）；步骤[15] old-notification-A **warn outcome=null**（该运行未证明撤回通知）；步骤[21] scenario-complete 仍记 pass——旧聚合缺陷的历史记录，其 exit 0 不可追认（旧审计"审计修订"第 1 条已声明）。
- **旧 withdraw-verify 链**：`04-44-03-901Z` probe **fail**（`23089d45…`）→ 4 个 no-landing 空泛 pass（§1 P2 第 2 条）→ **最终版 `10-09-19-774Z`（`e47051e5…`）为绑定证据**：inaccessibleCards=2、撤回事件卡 2026/10/5 12:41:37 与 download-withdraw 步骤[11] 04:41:37.324Z 对齐、openCardAnchors 落 A2/B 不落 A。
- **当前旧审计** `codex-audit.md`（`b382f595…`）：基线 9e87fec，标题即"尚未签收"，4 项未闭合（新版页面未验、late-response 不能称证明实际迟到响应被忽略、通知卡关联保留意见、运行器独立审查未闭合）——这是历史审计状态，本审查不替其签收，其中第 4 项即本卡，第 1/2 项已由 76dfd59 新证据部分闭合（见 §3.6/§4）。
- **新版**：本轮按指令未撤回、未运行 download-withdraw/withdraw-verify（RETEST-SUMMARY 未验项第 3 条与之一致），故撤回链新版无新证，沿用旧证并如实标注。

### 3.6 新迟到响应：continued + responseObserved（非 already-cancelled）✅
主证据 `late-response-2026-10-05T11-22-15-479Z/results.json`（`24f8d966…`）步骤[8] same-page-late-a-race pass：`release=continued responseObserved=true a2ReportStillOpen=true aDataOverwroteA2=false error=false draft=false hashStillA2=true bothColumns=true`。代码要求二者同时成立（L984 `result==="continued"` 且 L986-989 轮询 Network.responseReceived 计数增长，L999 ok 联合判定）。`same-page-race-evidence.json`（`6b29898b…`）：releaseOutcomes[0].result="continued"、injectorLog 记录 response 阶段 200 暂停与 released、hashEvents 页面侧记录 `#application-b4da6fb3…`。跨页变体（辅）如实记 already-cancelled 为浏览器预期（步骤[10]），不冒充主证据。中间失败运行全部保留：10-48-51（draft 断言 bug，fail）、11-21-36（Chrome 崩溃，abort）。
残注：responseObserved 目前以步骤 detail 布尔 + injectorLog 佐证，networkLog 事件列表本身未随 late-response 落盘（旧证据有 late-response-network.json，新版无同名物）——建议后续版本补 dump，属证据完备性小缺口。

### 3.7 notification-filter 定位含列表/目标关系 ✅
定位方式为逐卡真实点击后校验 `location.hash === '#application-<target>'`（L847-872，列表/目标关系），非时间猜测；新证据 `notification-filter-…10-47-55`（`a5076f7d…`）步骤[7] card #0 经真实"核对授权并打开投递"点击落到目标 b4da6fb3，步骤[9] 筛选外提示+目标隐藏+零结果列表，步骤[11] 清除筛选定位一次，步骤[13] 刷新不劫持（scrollEvents=[137,11,0]，telemetry `61c1c459…`）。

### 3.8 下载哈希证据 ✅
新 skeleton `10-47-01`（`625da052…`）步骤[8]：sha256=`a0149d5a113b3432d86c5cf235e26aa8283b37b6ac2550ba704432a75c1c6b6b`、bytes=203、matchesAuthorizedFile=true——与旧 download-withdraw `04-41-28`（`23247bae…`）步骤[5]/[7]/[17] 同一授权材料哈希逐字一致（跨构建一致）。哈希来源为运行时 creds.materials.student.contentHash 与落盘文件重算比对（L729-732），本审查未读取授权材料与凭据，故仅核验证据内部一致性，不独立重算材料哈希。

## 4. 历史失败 vs 新版通过对照（防"旧失败记成新版通过"）

| 项 | 历史记录（audit-20261005，旧构建） | 新版记录（closure-20261005，HEAD 76dfd59 构建） |
| --- | --- | --- |
| reply-failure 草稿 | 步骤[6]/[12] `preserved=true readOnly=true editBlocked=true` 记 **evidence** 状态、scenario-complete 仍 pass、exit 0（`d02c8eca…`）——不可追认为通过 | 4 段验收全 pass：readOnly=false、编辑/删空仍存在/重输全链真输入、发送入口/勾选框/旧报告缺席、各变体恰 1 次 POST 无自动重发、刷新后服务器真相分别正确（`18aaee6a…`） |
| late-response | 仅证明跨页导航取消路径（v1/v2 均 already-cancelled，`7c1a4af5…`/`0fec8540…`）；同页竞态未验 | 主证据 continued+responseObserved（§3.6）；跨页变体如实记 already-cancelled |
| notification-filter | v1 blocked（同名夹具）→ v2 零结果筛选通过（`…04-46-24`） | 新构建重跑通过，定位含列表/目标关系（§3.7） |
| 撤回链 | 撤回已发生且不可逆；通知证明经 withdraw-verify 最终版闭合 | 本轮未撤回（按卡禁令），无新证，沿用旧证并标注 |
| 视口 | 512px 对照目录与 about:blank 早测 fail 保留 | viewport390 `10-48-40`（`9a009ee6…`）加载后实测 390×844 全过；10-48-19 早测失败运行保留 |
| 退出码 | 修复前历史运行曾 exit 0（含缺陷场景），以各自 results.json 步骤为准，不追认 | fail/blocked/blocked 映射齐备；失败与中止运行以真实非零退出码保留（§3.4） |

## 5. 未验项与疑点（如实）

1. **未执行任何东西**（卡禁令）：runner-input.test.mjs 的 15 个用例未运行，"测试通过"声明仅静态采信；运行器在真实 CDP/浏览器下的行为全部来自代码推导 + 既有证据，本审查未复跑任何场景。
2. download-withdraw / withdraw-verify 在新构建上无实跑证据（撤回不可逆 + 卡禁令）；`withdrawnNotificationStatus` 映射与 §1 P2 第 2 条的 verdict 逻辑属"代码审查确认 + 历史证据佐证"，新版未走查。
3. Chrome 强制击杀路径（pidStillOurs→taskkill）无实跑证据；全部 chrome-stopped 均 exitCode=0 优雅退出。
4. responseObserved 的底层 Network.responseReceived 事件列表未随新版 late-response 落盘（§3.6 残注）。
5. reply-failure 场景 390px 证明依赖截图宽度（@2x 780px）与独立 viewport390 场景，本场景内 info 步骤记录的是 980（§1 P3 第 6 条）。
6. 凭据 JSON 内是否含 tokens/cookies 等其他秘密未核（未读凭据）；SCRUB 仅覆盖 accounts.*.password（L604-606），若凭据文档含其他秘密值，其意外进入 detail 的清洗依赖同一 scrub 管线——控制台旁路（P2 第 1 条）同样适用于它们。
7. Start/Stop-E2E.ps1 未在本卡范围重查（前次卡已覆盖，其 P3 发现未重核）。
8. 学生个人任务独占 closure 数据与浏览器、PG 免费任务独占其 schema——本审查全程未触碰浏览器/数据库/服务，与两个并行任务零交集。

## 6. 交棒要点（给下一个接手者）

1. 修复两处 P2 均为单行级改动：runner L60 `step.detail`→`entry.detail`；withdraw-verify verdict 增加"openCount>0 且无真实落地→blocked"（runner L1303-1305）。修前重算快照哈希（§0），运行器属开发任务独占的未跟踪文件，可能再次并行改版。
2. 证据采信顺序：新版 late-response 以 `11-22-15-479Z`（`24f8d966…` + raw.out `7f4ce67b…`）为准；撤回链以旧 `withdraw-verify-10-09-19-774Z`（`e47051e5…`）为准；旧 download-withdraw 的 step13 fail/step15 warn 与旧 reply-failure 的 exit 0 均为历史记录，不得计入新版通过。
3. RETEST-SUMMARY.md 需要一次文档刷新（补 11-21/11-22 两次运行、"13项测试"计数）；SCENARIO-SUMMARY.md 的"三次no-landing"应更正为四次且其中四次记 pass（属历史文档修正，须由证据所有者执行，本审查只读未改）。
4. 本报告无签收效力；闭合"运行器独立审查"这一旧审计第 4 项，还需修复确认 + （如获许可）一次测试实跑回归。
