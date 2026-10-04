# P0 企业双投递页面首验证据包（2026-10-04）

执行者：ZCode（Start Plan 免费 GLM-5.3-Flash）。任务卡：`docs/task-cards/20261004-P0-enterprise-double-application-page.md`。
浏览器：ZCode 内置浏览器（IAB，Chromium 内核）。视口：桌面 1280×800、移动 390×844。
生产构建：`http://127.0.0.1:3000`（HTTP 200）；后端 `http://127.0.0.1:8000/api/v1/health`（HTTP 200）。服务由 Codex 预先启动，本包未重启任何服务。

## 1. 现场核对（只读）

- Git：`main@1cdb506`，领先 `origin/main` 1 个提交；B-08/B-11 等未提交与未跟踪改动全部保留，`stash@{0}`（P2 RRF）未动。测试过程零代码修改、零提交、零推送。
- 服务健康：backend 200、frontend 200（curl 实测）。
- 凭据：`backend/.tmp/demo-credentials.json`（合成演示企业/学生账号）。凭据值只由脚本读入浏览器表单，未写入本包任何文件、截图或命令输出。

## 2. 合成夹具与测试前状态（只读 SQL 查询）

| 夹具 | ID | 测试前状态 |
| --- | --- | --- |
| 演示企业（OWNER） | `12eca85a-1315-479f-9a49-9cf0f7b2d080`，企业 `4a074a4f-f0eb-40b2-a6a3-c69f3662438f` | 名下 18 个岗位、2 条投递、通知 0 条 |
| 演示学生 | `8a722516-c73e-4eec-b00c-7e586d2a5851` | 唯一有效投递：DBA |
| 投递 A（DBA） | 应用 `97b6128d-a7c4-4b8b-8789-13201b07e272`，岗位 `9c2afb19-a3ec-40c6-9229-bdd3d9c333cc`，报告 `f0e36d67-d028-4bcb-ba3f-64f71a52b1c6` | status=replied（已回复，回复文本为合成演示文案）；固定快照 SHA256（规范化 JSON，sort_keys）：`32803eb8f322cbef3ee50b527a0bc952d6ef007ea05f5ba5f960469af73750ec` |
| 投递 B | **不存在** | 演示企业名下另一条投递 `a816e859…`（Python 后端岗）测试前已是 withdrawn，企业板不可见 |
| 企业通知 | 无 | DBA 的 submitted/viewed/downloaded/replied 事件发生在通知功能上线前，“历史事件不补发”，故两账号通知数均为 0 |

快照哈希方法：`sha256(json.dumps(report_snapshot, ensure_ascii=False, sort_keys=True))`，对 `applications.report_snapshot` 列只读计算。

## 3. 夹具不足的判定（测试前）

1. 任务卡要求“同一企业账号下两个不同岗位的合成投递 A/B”。现场仅 1 条有效投递，第二条已 withdrawn。
2. 补造第二条投递需要为学生生成新报告 → 后端当前配置 `ai_external_enabled=True, ai_provider=deepseek`（只读评估，未打印密钥），会触发真实 DeepSeek 调用，任务卡明令禁止。Demo 导入只放材料不生成报告。
3. 因此 T1 无法执行；T3 的“B 保持可读”、T2 的“锚点指向被筛掉但可访问的投递”两个子项缺少第二夹具。

## 4. 页面实测结果

### T3 撤回授权（执行并验证，页面 + DB 双证）

1. 撤回前企业页：投递板显示“演示学生 42.27 · 已回复”，5×1 矩阵、固定报告面板（摘要/雷达/五项引用/待核验）、“下载本次授权简历”按钮可点，页面提示“已收到授权简历文件…”。截图 `t0-board-desktop-initial.png`、`t0-report-panel-desktop-scroll1/2.png`、`t3-before-withdraw-download-click.png`。
2. 企业 AI 核验建议区：DeepSeek 外发同意框**未勾选**，未触发任何模型调用；“读取已保存建议”（页面标注不新增模型调用）正常返回“尚无已保存的核验建议”。
3. 学生端撤回：我的投递 → 撤回投递授权 → 确认页警告“撤回后企业不能继续访问本份报告或下载…” → 确认后状态变“已撤回授权”，事件流新增“学生撤回授权；企业后续访问被拒绝，已下载副本无法追回”。截图 `t3-student-*.png`。
4. DB 复核：status=withdrawn；快照 SHA256 与撤回前**完全一致**（同上哈希）；新增 withdrawn 事件，并向学生、企业各生成 1 条撤回通知。
5. 企业端撤回后：投递板变空（“暂无已授权投递…平台不会从学生库导出未经授权的简历”），固定报告面板与下载按钮随之消失，页面无任何可发起下载的入口；企业通知中心该通知标题为“投递授权已撤回或当前已无访问权限”，正文“当前投递不可访问，不能从旧通知查看报告或材料”，**只有“标为已读”、无打开按钮**。截图 `t3-enterprise-board-after-withdraw.png`、`t3-enterprise-notifications-withdrawn.png`。
6. 学生端锚点（唯一可产生的活跃通知锚点）：学生通知“核对授权并打开投递” → `/applications#application-97b6128d…`，本人已撤回投递卡片正确定位展示，通知自动已读。截图 `t3-student-anchor-reveal-withdrawn.png`。
7. 副作用声明：撤回按产品语义不可逆（本期不能重新投递同岗位）。该投递为合成演示夹具（回复文本明示“合成演示，请勿实际赴约”），与既有先例（Python 后端岗投递早已 withdrawn）一致；未删除任何业务表行。

### 自动刷新不夺回视口（T2 家族的部分验证，通过）

企业投递板打开固定报告面板 → 滚动至 y≈2600（已发送回复区）→ 通过浏览器面板隐藏/显示触发页面可见性变化 → 页面自动刷新（已打开报告按页面说明收起，列表重取）→ 无任何锚点滚动/视口跳转到列表顶部以外的强制定位（场景中无锚点）。截图 `t2-after-auto-refresh-viewport.png`。带锚点的“刷新不重新滚到锚点”子项未验证（见下）。

### 桌面与 390px 页面检查（通过）

- 桌面：岗位管理列表、岗位详情、投递板+矩阵、固定报告面板、通知中心（空态/1 条撤回通知）均正常渲染，无错位遮挡。
- 390×844：投递板标题/筛选纵向堆叠正常；矩阵表格走容器内横向滚动（overflow-x-auto 合法模式），页面级 `scrollWidth==clientWidth`（375/375，无水平溢出）；雷达图、报告面板、通知中心空态正常。截图 `t5-*.png`。
- 390px 企业投递板撤回后空态未单独截图（撤回在 390px 取证之后执行），已记录为缺口。

### 全页截图工具伪影说明

`t0-report-panel-desktop-full.png` 为 fullPage 拼接截图，sticky 头部在拼接中重复出现；DOM 快照确认页面 banner 仅 1 个，视口分段截图（scroll1/scroll2）无重复，判定为截图工具伪影、非页面缺陷。

## 5. 未验证项与阻碍（不猜测结论）

| 项 | 阻碍 |
| --- | --- |
| T1 双投递筛选→快速切换 A→B、A 慢响应不覆盖 B（含跨岗位页面切换） | 仅 1 条有效合成投递；补造需真实模型调用（禁止）。IAB 亦无网络延迟注入能力 |
| T2 通知锚点指向“被筛选排除但仍可访问”的投递：提示可见、清除筛选只定位一次、带锚点刷新不夺回视口 | 演示企业 0 条企业通知（历史事件不补发），现场无法从页面产生该场景；唯一可新生成的事件是撤回，而撤回后通知即无导航目标 |
| T4 回复发送失败注入（拦截/断网下草稿保留、无“已发送”提示） | IAB 无请求拦截/断网注入能力；且该投递状态为已回复，页面本就不显示回复表单。绝不真实发送 |
| T3 的“B 保持可读” | 无 B 夹具 |
| 撤回后下载接口 4xx 的页面级复现 | 撤回后页面已无下载入口，无法从页面发起；接口层拒绝由既有后端专项覆盖，不以此替代页面证据 |

## 6. 测试产生的状态变化清单

1. DBA 投递 `97b6128d…`：replied → withdrawn（产品语义内、不可逆，快照哈希不变）。
2. 新增：withdrawn 事件 1 条；通知 2 条（学生、企业各 1，学生侧已读）。
3. 企业查看/下载事件为既有事件（唯一约束去重），本次页面点击未新增事件行。
4. 未修改任何产品代码、配置、正式文档；未删除任何表行；未调用 DeepSeek；未发送站内回复或外部消息。

## 7. 截图清单（本目录 screenshots/）

t0-board-desktop-initial.png、t0-report-panel-desktop-full.png（含工具伪影说明）、t0-report-panel-desktop-scroll1.png、t0-report-panel-desktop-scroll2.png、t2-after-auto-refresh-viewport.png、t3-before-withdraw-download-click.png、t3-student-applications-before-withdraw.png、t3-student-withdraw-confirm-ui.png、t3-student-after-withdraw.png、t3-student-anchor-reveal-withdrawn.png、t3-enterprise-board-after-withdraw.png、t3-enterprise-notifications-withdrawn.png、t5-board-390px-top.png、t5-board-390px-matrix.png、t5-board-390px-table.png、t5-board-390px-matrix-table.png、t5-notifications-390px-empty.png

## 8. 下一项建议

为 T1/T2 补夹具的最小路径：由维护者决定是否授权一次“规则模式”报告生成（如临时以 mock provider 启动后端）或直接注入两条不同岗位的合成投递+submitted 事件（产生企业通知），再做双投递竞态与筛选锚点页面首验；建议由 Codex 定边界后执行。
