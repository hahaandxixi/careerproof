# 首页与证据联动体验完善

2026-10-13，基线 main/f781a5b。推进 G1 角色入口与 G2 证据查看体验，不签收全部网站或未完成的 CI/授权页面链。

## 分工与最终改变

- ZCode 无额度，本轮未继续调用。DeepSeek Harness 在北京时间22:30非高峰、jbcode新会话“传智杯50首页体验视觉完善”使用 Flash High，22:33交棒；唯一业务写入首页。其原始静态自审在 [VERIFICATION.md](../20261013-harness50-home/VERIFICATION.md)，不是最终版本或浏览器证据。
- Codex独立核对路由、再精简首页：学生/企业入口、三步流程、原版靛蓝首屏、显式合成预览；预览使用现有合成夹具，不编造用户数据、来源或模型成功。取消直接写“注册企业账号”的入口，因为当前注册页默认选学生，避免暗示企业角色已预选。
- 雷达：独立图例、上方要求按钮、清楚的选中态与详情层级；评分说明、引用默认折叠。维持100坐标、原值与缺材料不绘点、不填面积、历史兼容、键盘选择和按要求ID关联引用。
- 真实热力图过去用75分阈值显示绿色，而当前单项规则上限65；改为按固定报告的证据状态配色，与合成示例共用。颜色不重新评级、不按深浅推断录用顺序。历史高分自述仍为琥珀虚线，未知/无效值为灰色。

## 验证与失败记录

| 检查 | 实际结果 / 原始文件 |
| --- | --- |
| 雷达与原尺度相关 | 13通过，radar-target.raw.out |
| 前端最终全量 | 251通过，frontend-final-fixed.raw.out；含真实/合成同口径、65分证据状态和历史自述反例 |
| 类型检查 | 升级目录 tsc --noEmit 返回0，frontend-typecheck.raw.out；最终构建也包含类型检查 |
| 生产构建 | Next15.5.27、独立 .next-ux-20261013 通过，frontend-build-final.raw.out；不覆盖原 .next/.next-e2e |
| 源码/运行环境 | verify-frontend-runtime.mjs 与116源码文件核对，frontend-runtime-signoff.raw.out |

首轮构建因 `.ts` 值导入未启用 allowImportingTsExtensions 失败，保留 frontend-build.raw.out；改为带JSDoc的普通JS纯展示模块后构建通过。随后旧渲染测试的别名加载不支持无扩展名JS，frontend-final.raw.out保留243通过/1失败；明确 `.js` 导入后最终251通过，未删除或跳过用例。

调用命令：`jianli` 下 `npm test`；升级目录 `node node_modules/typescript/bin/tsc --noEmit`、`NEXT_DIST_DIR=.next-ux-20261013 node node_modules/next/dist/bin/next build`；根目录 `node scripts/dependencies/verify-frontend-runtime.mjs --project-root backend/.tmp/dep-frontend-20261010 --expected-root jianli`。失败和成功各留独立日志，不覆盖失败证据。

## 可审查产物与未验证项

[首页静态预览](home-preview.html)、[新雷达静态预览](radar-preview.html)、[改前雷达静态预览](previous-radar-preview.html)来自对应真实生产构建的HTML和内联CSS，移除脚本，明确标注静态预览。筛选、点击雷达切换、投递和API不在这些文件中运行；不能当成生产页面测试。

浏览器安全策略拒绝 file:// 页面（仅允许HTTP/HTTPS），没有换浏览器/其他通道绕过。此前额外3088预览服务启动也被自动审批拒绝，本轮没有重启服务。因此实际390px/缩放/颜色呈现/交互仍待在正常网站补验，不声称这些已经通过。一条只涉及误建空目录的清理命令也被自动审批拒绝，空目录保留，不参与提交。

没有改后端业务代码、数据库、投递快照、公式、已发回复或通知逻辑；没有网站真实模型调用、推送或部署。Harness客户端调用与网站模型验收是不同结论。CI49草案和原有guard/launcher修改继续独立待签收。
