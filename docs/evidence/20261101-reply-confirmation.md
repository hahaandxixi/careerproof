# 企业回复回执与读取恢复（2026-11-01）

## 接受范围

- 基线：`01cd7054fd68649728f5e9e1407c1ff2f565f49d`，PR #10已合并main；当前本轮分支 `codex/reply-confirmation-20261101`。
- 功能源码：`cb255a1`。仅两个生产文件 `jianli/src/lib/application-board-session.ts`、`jianli/src/components/ApplicationBoard.tsx` 与三个相关测试文件。
- 不改评分、图表、授权接口、快照或历史数据；无模型调用、真实回复/查看/投递/通知写入；不推送、合并或部署。

## 修复前后

固定基线的真实会话与 `replySendOutcome` 在纯内存模拟中复现：回复API成功，随后open或list失败时，`writeConfirmed=true`、会话返回false、页面结果`mark-unconfirmed`；各场景一次mock reply、零网络请求。原始结果在本地 `output/ui-review/20261101-reply-confirmation/baseline-simulation.json`。

现在写入与读取分别返回结果：

| 实际结果 | 页面与后续操作 |
| --- | --- |
| 写入确认，读取成功 | 回复已发送，清除已提交草稿 |
| 写入确认，GET详情或列表失败 | 回复已发送，最新状态刷新失败；只提供刷新回复状态，不重发 |
| 接口明确拒绝 | 显示本次发送被拒绝，保留可编辑草稿；先读取当前状态。409及已有回复不能冒充本次成功 |
| 网络、超时、5xx或无法确认的响应 | 发送结果未知；先读取核对，不自动重发 |
| 授权失效或固定报告不一致 | 清除报告、缓存和草稿；已确认提交的非敏感事实不改写成未知 |

恢复只使用 `GET /applications/{id}` 和授权列表，复用此前明确打开的不可变报告，且必须重新核对身份。`POST /applications/{id}/view` 是产生查看事件的操作，不是只读GET；本轮不再把它用作发送后的刷新。

单在途、未知结果先核对、账号/岗位key、草稿代际与迟到回调保护保留。切换投递、离窗、销毁或权限变化后的旧响应不能恢复旧正文、报告或修改新草稿。

## 工程验证

Windows / Node.js（实际版本见本地runtime记录），执行目录为本工作树 `jianli`。

| 命令 | 结果 |
| --- | --- |
| `node --experimental-strip-types --test tests/application-reply-result.test.mjs tests/application-board-session.test.mjs tests/failure-reply-draft.test.mjs tests/history-enterprise.test.mjs tests/verification-reply-draft.test.mjs` | exit0，82通过，0失败/取消/跳过 |
| `npx eslint src/lib/application-board-session.ts src/components/ApplicationBoard.tsx` | exit0 |
| `NEXT_DIST_DIR=.next-reply-confirmation-20261101 BACKEND_ORIGIN=http://127.0.0.1:8162 npm run build`（PowerShell环境变量） | exit0，生产编译、类型检查通过；保留既有VisualEvidencePanel图片lint警告 |

构建ID：`Wc2_iJ9Z7-_eLA1pI7Tfn`，包含最终原值精度补丁。启动前工程检查与后续手动启动/实拍分开记录，见下节。构建后原有 `next-env.d.ts`、`tsconfig.json` 的未提交内容已逐字节保留。

日志位于本地 `output/ui-review/20261101-reply-confirmation/`：`reply-regression.log`、`lint.log`、`build.log`、`runtime.json`。早期针对新契约的失败与测试夹具修正不是独立的生产缺陷数量；最终数字仅来自最后一次完整定向运行。不运行后端全套或全前端测试。

## 启动前浏览器与运行边界（历史，后续已部分完成）

- 只检测到内置浏览器，没有连接的原生Edge/Chrome；不把窄窗口当原生200%。
- 已在旧合成3142、1920×1080实际打开报告和回复确认：旧页把模拟接口拒绝也显示为发送未确认。仅内存模拟接口，未发送真实回复。截图 `output/ui-review/20261101-reply-confirmation/before-rejected-as-unknown.jpg`，对应 `fb34cba` / `taa37JHNyx5_K6Qgg9QFe`，**不是本轮修复后的截图**。
- 新3143前端与8162内存API的启动在执行前被自动审批拒绝，原因为 `blocked by policy`；随后准备仅供人工启动的脚本命令也被拒绝，未生成该脚本。没有改用另一接口绕过；已准备的模拟API文件仍在本地。
- 再次只读确认3143/8162无监听。3140、3141、3142各自构建清单与磁盘匹配，仍是 `ayj9grXn757U2gqBdLjto` / `fzu-WABM9r2QL-KGbfD4J` / `taa37JHNyx5_K6Qgg9QFe`，没有切换。
- 因此新页面发送反馈、只读恢复、1920/1280、原生200%、Tab/Enter/Esc、来源返回、筛选返回、双人同要求证据与38.27精度实拍均保持待验。相关代码及原有自动测试通过不替代这些项目。

## 最小人工补验

1. 确认3143/8162没有其他服务后，在本工作树用Node启动 `output/ui-review/20261101-reply-confirmation/mock-api.cjs`；另一个终端进入 `jianli`，设置 `NEXT_DIST_DIR=.next-reply-confirmation-20261101` 和 `BACKEND_ORIGIN=http://127.0.0.1:8162`，执行 `npm run start -- -H 127.0.0.1 -p 3143`。不停止3140/8140。模拟接口无数据库或真实API转发。
2. 打开 `http://127.0.0.1:3143/jobs/qa-desktop/applications`，选择陈同学，填写并人工确认一次合成回复。默认故障模式应显示“回复已发送，最新状态刷新失败”。只在本隔离地址操作。
3. 将本地 `control.json` 的mode从`detail-fail`改为`none`，保持revision为1，点击“刷新回复状态”，核对已保存的合成回复。模拟请求日志应仅有一次reply，恢复时没有新增reply或view。
4. 同一页面检查1920及较窄电脑窗口；原生浏览器菜单明确设置200%，检查操作和图表，完成后恢复原缩放。用Tab/Enter/Esc核对按钮、菜单、证据入口；来源选择/返回、双人同要求及筛选返回仍需实际操作，不填写未经观察的通过结果。

本轮停止于本地修复和构建可复查；不为补截图生成真实记录或重新调用模型。

## 用户手动启动后的实际补验

2026-11-01北京时间15:24，用户执行本聊天提供的命令，返回Ready。新前端PID201032、内存API PID200728，创建时间与本机进程一致。构建清单HTTP200并与 `.next-reply-confirmation-20261101` 字节一致；源码仍为 `cb255a1`，未改代码、未重复构建或自动测试。

- 入口：`http://127.0.0.1:3143/jobs/qa-desktop/applications`，只连接8162纯内存合成API，没有数据库或真实API转发。原3140/PID57620与8140/PID58192不变。
- 新构建实际通过：正常发送；写入确认后GET详情失败、再次读取失败与恢复；写入确认后列表失败与恢复；4224明确拒绝；模拟写入后响应中断；写入确认后GET 4049授权拒绝。
- 前五个独立场景各一次模拟reply、一次用户明确打开报告的view；恢复没有新reply/view。正常场景另有用户明确点击双人报告打开产生的view，不混称只读。计数与分段位置见本地 `browser-*.json`、`mock-requests.log`。共6次模拟reply请求，未发送真实回复。
- 未知结果只显示需核对；GET发现已保存回复后不反推本次请求一定成功。明确拒绝后草稿保留，确认勾选清除，发送按钮仍禁用。授权GET拒绝后旧报告/草稿和恢复入口均清除；这是拒绝响应展示检查，**不是实际撤回业务或真实跨账号测试**。
- 双人FastAPI同轴联动：A指数100/B指数61.5，双方分别显示自己的固定来源。雷达实线/虚线及文字图例保留。1920时雷达396px，1280时336px；页面无横向溢出，源码和表格保留自身滚动。
- 来源展开、换行、收起返回实测；返回焦点为“展开阅读”。账号菜单Enter展开、Tab到通知、Esc关闭并返回账号入口通过。最初向非焦点details容器发送Esc的工具定位失败，经实际焦点重新定位后通过，不计为产品错误。
- 关键词筛选出1条时正确只显示数量、不渲染无效分页。清除筛选保留两人名单；第2页加入候选人21，返回第1页名单仍为三人。三人矩阵可见；候选人21仅查元数据，没有自动POST view获取完整报告。
- 热力图实际横向scrollLeft40、纵向scrollTop24.8（最大25）；固定首列仍在容器左侧，导航中心 `elementFromPoint` 命中header，z-index40。
- 保留的非阻断可用性现象：读取失败时刷新按钮禁用/恢复后，键盘焦点曾回到页面，需要再Tab进入；本轮未扩展焦点修整。

### 截图与未验项

本地 `output/ui-review/20261101-reply-confirmation/截图总览.html`、`SCREENSHOT_INDEX.md`、`screenshots.json` 共12张真实图：11张本轮构建，1张旧构建。JPEG原图无裁剪或缩放；设定视口为1920×1080、1280×900，实际图像分别存在1920×1080、1905×1072、1265×889，索引逐张记录，不能把截图像素和视口混写。代码与构建未变，沿用82项检查结果，不再跑全量测试。

仍未验：原生200%（只连接内置浏览器，无原生Edge/Chrome）；完整浏览器前进/后退；学生报告多来源选择在本构建的实拍；真实账号/岗位在途切换与真实离窗；38.27未知规则原值的页面样例。后者代码已包含，但本模拟数据均为已知v4，没有38.27样例。对应自动测试或前轮结果与本轮浏览器结果分开，不宣称全面验收完成。

无需再重启当前3143/8162。补验200%时，由用户在原生Edge打开上述隔离地址，通过浏览器菜单明确设为200%，检查按钮、雷达和源码可达，完成后恢复缩放。不得用1280窗口或CSS缩放代替。

本次只更新本地验收记录，不推送、不合并、不切换3140，不调用模型或操作真实业务数据。
