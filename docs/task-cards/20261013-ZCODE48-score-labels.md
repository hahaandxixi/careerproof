# 传智杯48：报告尺度与证据等级文案

基线：main / 71a2fd3；实际 Git 根 D:\jbcode\web ai\jianli。整改来源是仓库外 CareerProof-整改清单.md 的 P0-1.1/P0-1.2，逐条核实后采用保守展示修复。唯一实现写入者 ZCode；Codex 同时仅修改后端生产配置和正式文档。

## 可观察交付

- 当前 evidence-v3 规则单项材料支持度为 0/10/15/30/40/65，总分是加权平均。65 是规则上限，不能叫能力满分或录用概率。
- 企业对照/详情不再把 65 呈现为未达 100 的成绩；显示原报告数值，并解释“当前规则上限65，分数仅表示材料支持度”。不改后端公式、API、历史报告、雷达坐标尺度或历史数值，不把所有历史结果限制到65。
- 证据等级优先使用已有 evidenceLevelLabel（基础线索、局部操作、任务实现），对缺少标签的维度/成长对照可用单一纯函数格式化 1/2/3 的名称；未知历史等级保留原等级数字，不能改为不存在的 /3 比例。去除实践证据 /5 的误导，岗位权重 /5 保留。
- 调整本批受影响的正常测试数据为真实规则可达值；专门测试历史/异常80或100的兼容用例保留并注明。补实际组件渲染回归，验证标签、65文案、权重仍 /5、未评级、历史未知等级仍可显示。不要仅以源码正则测试代替可观察输出。

## 唯一文件所有权

允许 jianli/src/components/{ApplicationBoard,ReportDetail,SkillRadar,GrowthComparison,ReportComparisonPanel,ActionPlan}.tsx，必要注释 jianli/src/lib/types.ts，新纯格式模块 jianli/src/lib/evidence-display.ts，以及直接相关 jianli/tests/*.test.mjs；不要批量重写无关测试。唯一证据目录 docs/evidence/20261013-z48-score-labels/ 与自有 backend/.tmp/z48-score-labels/。

## 验证与停止

先最小红测试，再修复；目标测试→受影响/全量前端测试→类型检查。只使用已安装依赖；升级运行目录 backend/.tmp/dep-frontend-20261010 的工具若被使用须核对实际版本并明确源码来源，不安装依赖或重建共享 Next 目录，不启动/停止服务。完整原始日志（失败单独保留）+最终 diff/hash+一屏报告落盘后停止交棒。页面验收由 Codex 后续安排，未运行须注明。

禁止修改 backend业务代码/.env/launcher/DB/原投递快照/旧guard/P2 stash；禁止真实网站模型调用、外发私有数据、Git提交或推送。不能用文案整改宣称 CI、安全配置、许可证、视频和部署已完成。
