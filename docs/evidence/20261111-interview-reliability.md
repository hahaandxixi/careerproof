# 模拟面试集中修复验收

## 版本与范围

- 任务与反馈主体到 `1b5dc8b`，历史授权修订及后续记录见同一分支 `codex/records-ui-20261108` 的 [PR #15](https://github.com/hahaandxixi/careerproof/pull/15)。
- Windows 上使用原统一环境，前端 3140、API 8140、PostgreSQL `careerproof_v1`。迁移从 `0022_interview_practice` 到 `0023_interview_tasks`，新关联允许历史记录为空。12 条技术知识按现有播种入口更新。
- 生产构建 `1tftA00LXoa7bqyp-6eXy` 封存于 `.next-candidate-20261111-practice`，前端源码提交 `03f26d4`。后续提交无前端文件差异。Next.js 生成的类型目录引用留在本地。
- 历史 `output/interview-knowledge-20261110` 中，`INDEX.md` 的 `bd3ccaa` 是知识修正提交；同一构建的 `BUILD.txt` 记录的是后续补齐全 NULL 行数边界的 `4d03a36`。两者用途不同，当前构建已另行记录。

## 验证

| 项目 | 结果 |
| --- | --- |
| 知识召回、字段播种、快照 | 三个具体中文主题命中预期卡片，无关查询为空；修改出题或来源字段后更新依据，旧快照保留。实际旧报告的 SQL 题面补有明确召回入口 |
| 两轮总结 | 已明确纠正的条目依据问题 ID 和回答原文移出待补，未回答的条目继续保留。最终补丁去掉相同待补文本的重复 |
| 生成与恢复 | 受控慢响应复现旧实现重复执行。新实现原子保存回答和任务，重复提交返回同一任务；租约失效后保留回答，可重试，旧任务的迟到结果不能写回 |
| 电脑端 | 1920×1080、1280×900。报告雷达切换、技能来源跳回报告、企业矩阵与单人雷达的 Python 引用、双人 Python 要求两份源码均实测。使用既有合成授权案例，打开固定报告会经正常接口记录查看事件 |
| 回答状态 | 浏览器拦截提交，确认未保存时保留草稿；延迟错误在离开原练习后未显示在目标页。另一个会话未读到该草稿 |
| 历史授权 | 旧练习按原确认范围继续。它的后续点评请求只包含当前轮内容和已确认的依据，新练习按用户确认后的范围提供前轮上下文 |
| 本地检查 | 36 项后端定向、8 项前端定向通过，目标 Ruff、ESLint、TypeScript 和生产构建通过 |

后端命令为 `python -m pytest app/tests/test_interview_practice.py app/tests/test_interview_practice_migration.py app/tests/test_material_tasks.py`，使用专用临时目录。前端执行 `node --test tests/interview-practice.test.mjs`、`npm run typecheck`、目标 ESLint 和 `npm run build`。GitHub 状态以 PR 对应提交的 Checks 为准。

## 真实模型结果

- 练习 `29c5c512-c2b6-4da0-8fae-cb757652da60` 绑定原报告与 SQL 要求。知识快照 `tech-sql-aggregate-null` 的 hash 为 `61ae43b677d726fb1c01845f6edc17673724372160d59e3eb11f96397d186348`。
- 三个任务 `7ee305ed-abc1-44f4-bef0-cb498c36c21b`、`5023002c-1ebe-4a30-a60d-834845b1135e`、`66363d46-8e0c-45c2-a3cb-43457f646193` 均完成。对应三条 `deepseek-flash` 用量记录共 3263 输入、1048 输出 tokens。应用账本记为 0 元，未核对服务商账单。
- 刷新后从服务端读回首问、两轮点评和小结。第一轮 COUNT(*) 错误有原文和知识依据，第二轮的纠正进入已解决清单。人工复核发现模型另有归类不一致与重复待补，原结果保留。
- 上述真实练习使用本轮早期提示版本。最终提示与归纳规则经受控回归，未用新增付费请求复验，不能据此声明模型的归类问题已消失。

本地实拍与运行记录在 `output/interview-practice-20261110/20261111-real-final`、`20261111-draft-recovery`、`20261111-preserve-06`、`20261111-enterprise-pair-final`。日志位于 `output/solution-plan-20261111`。截图和账号凭据不进入 Git。

## 名称修复及第二次真实验证

- 真实复验会话 `b71fdf2c-7192-4a70-a984-0c72f6ff25a5` 使用 `interview-practice-v3`，三次 `deepseek-flash` 请求合计 3417 输入、1019 输出 tokens。COUNT(*) 的纠正及原文可读回，最终无待补。第一轮仍同时把 COUNT(*) 判为答错和遗漏，保存的输出保持原样。
- `115ebc4` 的前端构建 `D9E1oNF51izrxiU7ThJhF` 显示「模拟面试」「数据工程实习生」「数据工程方向简历 v1」及「数据清洗工具 v2」。新旧练习读取同一报告、要求及材料快照。未登记的材料和岗位按原名展示。
- 1920×1080、1280×900 实测完成页、重新练习草稿、返回原报告及已保存 Python 源码引用。名称验收未产生模型请求。实拍位于本地 `20261111-practice-names-final` 和 `20261111-practice-names-cited`。
- `interview-practice-v4` 用逐项输出代替独立分类列表，校验拒绝相同问点标签的重复分类，仍可同时记录不同问点的错误与遗漏。改动时的 37 项后端定向测试通过。模型使用不同名称描述同一语义的情况仍需人工核查。

## V4 实际结果与失败诊断

- `c54d713` 的 [CI](https://github.com/hahaandxixi/careerproof/actions/runs/42985666746) 通过。经授权使用练习 `c7a3de7b-4cab-4533-94da-441b2262a58e` 发起三次 `deepseek-flash` 请求，账本记录 3516 输入、1356 输出 tokens。
- 首问和首轮点评保存。COUNT(*) 只归为答错，AVG 非空分母归为已回答，缺失机制及业务解释归为遗漏。第二轮任务 `ffa1d255-edbe-42b8-b012-ca5a9230f525` 有用量记录，但点评未通过校验，第二轮回答仍可读，无小结。该任务没有细分原因或可回读的原始模型输出。
- 后续失败日志关联任务 ID 和阶段。仅由练习校验器定义的原因可写入日志，外部异常只记异常类别。受控验证覆盖超时、提供方错误、重复问点和失败重试，39 项后端定向通过。历史结果与用户可见失败提示保留，本次诊断修订未新增外部请求。
