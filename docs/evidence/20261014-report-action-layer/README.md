# 报告动作层收敛（2026-10-14）

推进G1/G2：落实Harness51建议第一、二项，第三项“推荐结论为主”未实施。后端、评分、存储、授权协议与数据均未修改；未启动或重启服务。

- 四个状态按钮切换/收起一组要求，默认展开待补材料。分组、计数、列表均来自完整report.items，排序为权重降序、证据等级升序、原顺序；不受actionPlan默认3条限制。
- 已保存actionPlan仅按requirementId附加。相同文字只显示一次；真实来源保留，无建议不造建议/来源；引用限制为本要求已有引用。保留所有逐项证据与原锚点。
- 顶部一句话只概括四组已保存状态和排序第一的缺口，不生成职业推荐、能力或投递适宜性结论。非学生保留ActionPlan；学生投递入口及授权步骤不变。

## 实测

命令在jianli目录执行。初次新测试因缺少待实现导出而失败（工具输出保留在会话，不伪称已有原始日志）。实现后目标/相关18通过。

| 检查 | 实际结果 / 原始输出 |
| --- | --- |
| Node22.23.1 `node --experimental-strip-types --test tests/*.test.mjs` | 262通过，0失败/跳过；[最终日志](frontend-node22-final.raw.out) |
| Node24.19.0同命令，初轮 | 262通过，0失败/跳过；[日志](frontend.raw.out) |
| 本地TypeScript5.7.3 `node node_modules/typescript/bin/tsc --noEmit --incremental false` | 退出0，无输出；[日志](typecheck.raw.out)。本地Next15.5.25，不冒充升级生产构建 |
| 独立升级目录同命令，最终Node22.23.1 / TS5.9.3 / Next15.5.27 | 退出0，无输出；[日志](typecheck-upgraded-node22-final.raw.out)；四个源码与工作树[哈希](source-hashes.json)一致 |
| 独立升级目录 `node node_modules/next/dist/bin/next build` | Node22.23.1 / Next15.5.27，退出0；[生产构建](production-build.raw.out)。113个前端源码与工作树[完整哈希](build-source-hashes.json)一致，输出为独立`.next-report-actions-20261014`，未覆盖原运行目录 |

新增测试覆盖六缺口/三建议、零建议、同句去重、独立AI文字/引用、管理员兜底、学生仅一份计划、空组及无关建议拒绝。组件检查使用真实TSX转译后React服务端渲染；它证明默认输出，**不证明点击/键盘/窄屏交互**。未为展示层去重改写后端返回或历史报告。

## 尚未验证

生产构建已补验，未渲染真实页面、未实测分组切换/收起/锚点/390px，也未让同一同学比较前后结果。当前运行站点不因此自动更新。下一步在用户结束现场测试后启用本地构建，核对全部分组数量、来源、默认折叠、管理员及投递入口，再询问“这页如果只能留一句话，你会留哪句？”。不预写同学回答或体验改进结论。
