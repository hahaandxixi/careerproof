# 模拟面试集中修复验收

## 版本与范围

- 产品源码 `1b5dc8b`，分支 `codex/records-ui-20261108`，已推送至 [PR #15](https://github.com/hahaandxixi/careerproof/pull/15)。
- Windows 上使用原统一环境，前端 3140、API 8140、PostgreSQL `careerproof_v1`。迁移从 `0022_interview_practice` 到 `0023_interview_tasks`，新关联允许历史记录为空。12 条技术知识按现有播种入口更新。
- 生产构建 `1tftA00LXoa7bqyp-6eXy` 封存于 `.next-candidate-20261111-practice`，前端源码提交 `03f26d4`。与 `1b5dc8b` 的提交差异无前端文件。Next.js 生成的类型目录引用留在本地。
- 历史 `output/interview-knowledge-20261110` 中，`INDEX.md` 的 `bd3ccaa` 是知识修正提交；同一构建的 `BUILD.txt` 记录的是后续补齐全 NULL 行数边界的 `4d03a36`。两者用途不同，当前构建已另行记录。

## 验证

| 项目 | 结果 |
| --- | --- |
| 知识召回、字段播种、快照 | 三个具体中文主题命中预期卡片，无关查询为空；修改出题或来源字段后更新依据，旧快照保留。实际旧报告的 SQL 题面补有明确召回入口 |
| 两轮总结 | 已明确纠正的条目依据问题 ID 和回答原文移出待补，未回答的条目继续保留。最终补丁去掉相同待补文本的重复 |
| 生成与恢复 | 受控慢响应复现旧实现重复执行。新实现原子保存回答和任务，重复提交返回同一任务；租约失效后保留回答，可重试，旧任务的迟到结果不能写回 |
| 电脑端 | 1920×1080、1280×900。报告雷达切换、技能来源跳回报告、企业矩阵与单人雷达的 Python 引用、双人 Python 要求两份源码均实测。使用既有合成授权案例，打开固定报告会经正常接口记录查看事件 |
| 回答状态 | 浏览器拦截提交，确认未保存时保留草稿；延迟错误在离开原练习后未显示在目标页。另一个会话未读到该草稿 |
| 本地检查 | 35 项后端定向、8 项前端定向通过，目标 Ruff、ESLint、TypeScript 和生产构建通过 |

后端命令为 `python -m pytest app/tests/test_interview_practice.py app/tests/test_interview_practice_migration.py app/tests/test_material_tasks.py`，使用专用临时目录。前端执行 `node --test tests/interview-practice.test.mjs`、`npm run typecheck`、目标 ESLint 和 `npm run build`。GitHub 状态以 PR 对应提交的 Checks 为准。

## 真实模型结果

- 练习 `29c5c512-c2b6-4da0-8fae-cb757652da60` 绑定原报告与 SQL 要求。知识快照 `tech-sql-aggregate-null` 的 hash 为 `61ae43b677d726fb1c01845f6edc17673724372160d59e3eb11f96397d186348`。
- 三个任务 `7ee305ed-abc1-44f4-bef0-cb498c36c21b`、`5023002c-1ebe-4a30-a60d-834845b1135e`、`66363d46-8e0c-45c2-a3cb-43457f646193` 均完成。对应三条 `deepseek-flash` 用量记录共 3263 输入、1048 输出 tokens。应用账本记为 0 元，未核对服务商账单。
- 刷新后从服务端读回首问、两轮点评和小结。第一轮 COUNT(*) 错误有原文和知识依据，第二轮的纠正进入已解决清单。人工复核发现模型另有归类不一致与重复待补，原结果保留。
- 上述真实练习使用本轮早期提示版本。最终提示与归纳规则经受控回归，未用新增付费请求复验，不能据此声明模型的归类问题已消失。

本地实拍与运行记录在 `output/interview-practice-20261110/20261111-real-final`、`20261111-draft-recovery`、`20261111-preserve-06`、`20261111-enterprise-pair-final`。日志位于 `output/solution-plan-20261111`。截图和账号凭据不进入 Git。
