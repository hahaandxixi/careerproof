# 企业读取失败、重试焦点与主站切换（2026-11-01）

**后续返回链路已修复：** 功能源码 `74223d9`、3140构建 `FSXaKigUvzs4b--RMdRwm`，见文末“离页返回补验”。下文 `d7d6303` / `L17gYOSAOlA952SMhk8cl`及名单重置描述是上一阶段实测快照，不是当前待恢复设计；原生200%和真实标签隐藏仍未验。

## 接受源码与范围

- 分支 `codex/read-recovery-main-20261101`；功能提交 `fd7c247`、`d7d6303`，基于此前回复回执修复 `cb255a1`。
- 仅修改 `ApplicationBoard.tsx`、`application-board-session.ts`，新增局部 `read-retry-focus.ts` 及相关前后端测试。后端生产代码、雷达、热力图、指数方案、评分和授权规则均未改。
- 不调用模型、不写真实回复/查看/投递/通知，不改演示数据；未推送、合并。本轮有副作用的交互只在纯内存合成接口8163验证。

## 修复与实际表现

1. 列表失败显示“投递列表加载失败 / 重新加载投递列表”；固定报告读取失败使用独立名称。错误保留具体原因与请求编号，不再叠加无关全局提示。
2. 回复已确认后，分别显示“回复已发送，投递列表刷新失败”或“回复已发送，最新状态刷新失败”。只读恢复不重发回复、不调用产生查看事件的POST。
3. 重试按钮加载时保留键盘焦点并阻止重复操作；再次失败焦点不丢失。成功后原按钮消失，焦点转入相邻“读取结果”，不滚动定位。用户已点击其他输入、Tab/Esc或离窗则不抢回焦点；旧身份/岗位回调失效。
4. 初次列表失败且未打开任何报告时，不再额外提示“授权未确认，已清除报告和对照”。只有确实存在待恢复报告时才提示清除事实。

## 定向检查

Windows；Node `v22.23.1`；现有Python虚拟环境，不重复安装依赖。

| 检查 | 实际结果 |
| --- | --- |
| `node --experimental-strip-types --test tests/application-reply-result.test.mjs tests/application-board-session.test.mjs tests/failure-reply-draft.test.mjs tests/read-retry-focus.test.mjs`（jianli目录） | 退出0；79通过、0失败、0跳过 |
| 三个生产文件目标ESLint | 退出0 |
| `pytest app/tests/test_applications_api.py::test_download_reply_and_withdraw_revoke_every_enterprise_path app/tests/test_applications_api.py::test_reply_links_only_to_its_frozen_requirement_and_citations app/tests/test_validation_errors.py -q --basetemp <本轮唯一目录> --junitxml=../output/ui-review/20261101-read-recovery/backend-contract.xml`（backend目录） | 退出0；8通过、0失败、0跳过，5个现有第三方弃用警告 |
| 最终合成验收生产构建、真实8140生产构建（各自独立dist） | 均退出0，包含类型检查；现有VisualEvidencePanel图片lint警告保留 |

后端测试强制Mock/外部AI关闭、SQLite临时fixture，不连接真实业务库。首次默认pytest临时目录权限错误导致2个fixture失败，日志保留；改用工作树内唯一basetemp后通过，未修改ACL或削弱断言。

真实API测试保留4015、4049、4098、4220/4224契约；403为真实FastAPI通用AppError处理器与客户端契约检查，**不声称回复路由自然返回403**。网络/超时/5xx未知结果语义保留。

本地日志入口：`output/ui-review/20261101-read-recovery/`，含 `targeted.log`、`lint.log`、`backend-contract.log`、`backend-contract-first.log`、`backend-contract.xml`、`qa-final-build.log`、`main-build.log`。

## 实际桌面浏览器验收

最终源码 `d7d6303`，隔离3144 →8163，构建 `-SBEMEmE-BZX6hZnvGbf6`。合成接口不访问数据库、不转发8140、不调用模型。16张最终截图、视口/图片实际尺寸及页面地址见本地 `SCREENSHOT_INDEX.md`、`screenshots.json`、`截图总览.html`；`final-`以外图片属于前期原型。

- 1920×1080及1280×900电脑视口：列表失败/重试/再次失败/成功、来源、双人对照与矩阵滚动可读；表格内横纵滚动时导航命中仍为header，无页面横向溢出。
- 键盘Enter重试，加载与再次失败保留原焦点；成功后转读取结果。重试期间转到搜索框后，完成不抢走输入焦点。菜单Enter/Tab/Esc可用。
- 回复成功后读取失败、响应中断结果未知、只读恢复、GET授权拒绝均实测；一次恢复日志 `newReply=0, newView=0, readRequests=3`。
- 在途旧回复未返回前，实际退出并登录另一合成企业（09:36:28Z），旧响应09:36:33Z才返回；新身份无旧报告/草稿。延迟读取时切到第二岗位，旧报告不回填。
- 学生合成报告12来源：E2/E12引用跳转、浏览器前进/后退、手动选择后再次点击相同hash、展开后返回焦点均通过；同名文件不同版本可区分，只显示所选一份来源。
- 未知规则的FastAPI原始38.27保持38.27、不换算；缺材料条目即使有历史数值也不绘点。兼容双人FastAPI指数100/61.5与各自独立来源联动。跨第1/2页选择三人保留名单，再选两人深入对照正常。

**明确边界：** 离开岗位页面再浏览器返回会创建新页面会话，页码和对照名单重置（已观察page2→1、名单3→0）；这不等于页面内跨分页选择失败，本轮未增加跨路由持久化。内置浏览器两个标签都报告visible，不能当作真实隐藏/返回通过。原生Edge窗口最小化，工具要求先恢复窗口，未盲发快捷键，缩放未改变；原生200%与真实标签隐藏仍待验。

最小人工补验：恢复Edge打开3144验收页，通过浏览器菜单确认200%，核对重试、来源、双人对照与表格滚动后恢复原缩放；实际切到另一标签再返回，确认重新核对授权后报告/选中项恢复。不要触发真实发送。

## 3140真实后端构建已生效

| 项目 | 实际绑定 |
| --- | --- |
| 前端 | `http://127.0.0.1:3140`；PID314120；目录本统一工作树jianli |
| 前端功能源码 | `d7d63030a906330af0a2fdb2ef27c7420eda4ec1` |
| 构建 | `L17gYOSAOlA952SMhk8cl` / `.next-read-recovery-main-20261101` |
| 编译后的代理目标 | `/backend/:path*` → `http://127.0.0.1:8140/:path*`，不是8163/8162 |
| 后端 | 原8140进程未重启，启动器58272；生产源码摘要与原清单一致 |
| 数据库/文件 | 原 `127.0.0.1:55447/careerproof_v1`、`D:\jbcode\web ai\jianli\backend\storage-v1` |

切换前验证原进程身份、端口归属、配置哈希、后端摘要、构建代理及无pending/running任务，才停止旧3140前端；未停止其他预览。切换后首页、构建清单、代理真实API健康均200，13个实际JS/CSS与磁盘构建逐字节一致。`runtime.json`、`main-build.json`、`main-verification.json`保留实际来源。

12张业务表的数量**与内容指纹全部不变**：投递19、事件49、通知55、报告103、报告条目379、项目54、项目版本75、项目文件338、简历版本56、分析任务265、用量64、请求attempt11。前后原始指纹位于 `backend/.tmp/simplicity-audit-20261030/data-read-recovery-{before,after}-main.json`。这是限定表检查，不冒充全库证明或真实业务端到端验收。

3140本轮为只读健康/资源绑定核验，完整故障注入与点击使用同源码的隔离3144，不将合成图称为主站真实业务截图。原`next-env.d.ts`、`tsconfig.json`未提交改动按开工字节保留。

需要回退前端时执行本地 `output/ui-review/20261101-read-recovery/Activate-Main.ps1 -Action Rollback`：同样先检查身份/任务队列，只恢复旧构建 `ayj9grXn757U2gqBdLjto`，不回退Git、数据库或文件。旧dist、原运行清单 `main-before.json` 和所有旧截图保留。

## 离页返回补验与限定修复

- 分支 `codex/board-history-return-20261101`，功能提交 `74223d9cef3a2c4547add8c179d4b45ac3911381`。原重置来自Workspace销毁后默认page1/空名单，没有发现已批准“返回时重置”的产品依据。
- 生产修改只有 `ApplicationBoard.tsx` 与新增 `application-board-history.ts`；另更新组件测试并新增历史元数据测试。不改后端、AuthProvider、图表或指数方案。
- 利用当前浏览器历史条目记录筛选、页码及最多4个对照ID，绑定当前账号ID和岗位ID，保留Next路由内部字段；不使用localStorage/sessionStorage，不记录报告正文、源码、候选人姓名或回复草稿。不同账号/岗位的历史块不采用。
- 挂载/历史返回先恢复查询参数，再复用原 `session.resume`，通过授权列表及页外只读详情确认候选人。核对前不展示旧候选人；失效项移出并更新历史条目。服务端已会校正越界页，本轮直接保存返回的实际页码，不另建分页算法。
- 跨路由报告正文不缓存；返回只恢复名单和查询。继续查看具体报告仍使用原来的明确打开操作，不自动产生view或reply POST。已挂载页面的离窗恢复与回复回执逻辑保持原样。

### 实际检查与截图

`output/ui-review/20261101-board-history/` 保留日志、10张真实1920×1080视口截图（实际图片像素另列）、`SCREENSHOT_INDEX.md`、`screenshots.json`、`截图总览.html`。

| 检查 | 实际结果 |
| --- | --- |
| `node --experimental-strip-types --test tests/application-board-history.test.mjs tests/application-board-visibility.test.mjs tests/application-board-session.test.mjs tests/application-reply-result.test.mjs tests/failure-reply-draft.test.mjs tests/read-retry-focus.test.mjs` | 退出0，93通过、0失败、0跳过；`targeted.log` |
| `node node_modules/eslint/bin/eslint.js src/components/ApplicationBoard.tsx src/lib/application-board-history.ts` | 退出0；`lint.log` |
| 独立QA与真实8140两次生产构建（各自dist，包含类型检查） | 均退出0；`qa-build.log` / `main-build.log`；保留既有图片lint警告 |
| 第二页选三人、关键词Python → 岗位管理 → 后退 → 前进离页 → 再后退 | 实际恢复第二页、原关键词及三人名单；同视口离页前/返回后截图保留 |
| 组合筛选后离页返回 | Python、已查看未回复、FastAPI、有证据或部分支持及两人名单均恢复 |
| 换岗位、换账号、授权失效 | 第二岗位为空名单；另一合成企业实际后退原历史条目时无旧筛选/名单，API拒绝；撤回项核对后从3人减到2人 |
| 授权读取延迟与页码回退 | 等待期间无候选人正文；服务器总数缩至一页后正确回到第一页 |
| 图表与读取副作用 | 明确打开两份合成固定报告后，FastAPI双列来源及100/61.5雷达联动保留；恢复阶段view/reply均为0 |

验收为纯内存3145→8164，构建 `yiW5DsTCQfIKkFfcpqwry`，不连接真实数据库、不转发真实API、不调用模型。`read-return-before.json`/`read-return-after.json`记录28→34个请求、view=0、reply=0；之后仅明确点击“打开两份授权报告”产生2个合成view，回复仍为0。原生200%与真实标签隐藏沿用准确未验状态，不重复盲试。

首轮93项中3项失败是组件测试文本助手漏渲染数字，修正为与React一致后相同断言全部通过，保留 `targeted-first.log`；未删除或放宽断言。浏览器中一次等待超过工具默认3秒，实际4个串行800ms授权读取随后完成，已检查最终清理状态，没有重发写入。工程资源核验首次因本地路径未解码`%5Bid%5D`失败，解码后完成字节核对，不将诊断脚本错误当作产品失败。

### 最新主站绑定与回退

- 3140前端PID361068，构建 `FSXaKigUvzs4b--RMdRwm` / `.next-board-history-main-20261101`，源码 `74223d9`；独立编译代理仍为真实8140。原8140进程58272及库/存储不变。
- 停前进程身份、配置摘要、后端生产源码摘要、代理及空任务队列检查通过，仅切换3140前端；其他预览未停止。首页与候选人页面HTML、构建清单和真实API健康均200，15个实际JS/CSS（含候选人页面块）与接受构建逐字节一致。
- 12张业务表数量和内容指纹均不变，记录见 `main-verification.json`；前后指纹为 `backend/.tmp/simplicity-audit-20261030/data-board-history-{before,after}-main.json`。配置原有两文件字节保持，未做真实业务写入、模型请求或后端全量测试。
- 本次回退入口：本地 `output/ui-review/20261101-board-history/Activate-Main.ps1 -Action Rollback`，恢复上一接受前端 `L17gYOSAOlA952SMhk8cl`，仍先检查身份和任务队列，不回退Git或数据。上一阶段的回退脚本仅作历史记录，不用于撤销本次更新。
- 未推送、未合并。主站本轮只读绑定检查与隔离页面真实交互分别记录，不把合成截图冒充真实企业业务验收。
