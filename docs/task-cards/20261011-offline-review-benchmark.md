# 传智杯28：离线三维评测与独立盲评的可重复联合报告

2026-10-11。Git根D:\jbcode\web ai\jianli，main。模型Start Plan Weekend Build免费Flash/最高；不用个人套餐。27只写自己的审计证据，本任务唯一写backend/evals/run_quality_review_benchmark.py、backend/app/tests/test_quality_review_benchmark.py、docs/evidence/20261011-AI-review-benchmark/。既有runner、fixture、review及生产逻辑只读。

## 缺口与目标

三维runner已有引用契约/来源与变化比较指标，但建议可执行性是作者覆盖率，真实生成可执行性必须null。独立8例盲评分数在单独JSON；尚无一键命令把它作为可审计的离线草稿基线，区分结构通过与独立模型判定。补一个组合CLI，调用既有evals.run_quality_dimensions.evaluate/load_cases，不复制生产逻辑；附独立盲评回放，保留两类结论和全部失败分母。

只读：docs/evidence/20261010-AI-codex-holdout/README.md、docs/evidence/20261010-AI-blind-plan-review/codex-review.md、review.json；backend/evals/quality-blind-plan-review-input.json、run_quality_dimensions.py及所需测试。不要全仓重读。

## 指标协议

- 默认输入冻结8例input与原review.json；参数支持指定新路径，但显式拒绝覆盖输出。metadata保留reviewer/model/plan/reviewedAt/humanReview=false、输入与review SHA256、现行生产/runner/fixture哈希。严格校验review.inputSha256匹配原始输入字节；病例ID非空唯一且集合完整相等；评分仅整数0/1/2或null，bool/字符串/NaN非法。四维必须全部存在；每个非null评分需要非空文本理由，缺失理由不得算成功。
- 结果称reviewedAuthoredDrafts，不称网站真实生成。8个总样例全部纳入分母；null独立计unscored，不能剔掉再报高成功率。四维分别计0/1/2/null和样例数。严格通过需四维都为2且均有理由；来源0/1/null直接不通过或未评分，其他高分不能抵消。保留每例分数、理由、需补充点。
- 作者覆盖与独立review严格通过分列，不能把6份作者声明齐全等于实际可执行；真实网站模型样本数0、humanReview=false、generatedPlanOperabilityRate/semanticQualityPassRate继续null。明确这是已有独立模型评分的确定性回放，不是每次重新模型评分或人工证明。
- 新报告包含原三维结构报告及上述独立盲评基线；结构/契约指标过线与草稿质量不通过分列。命令退出码：合法且完整回放成功可以0（基线存在劣质草稿是预期数据）；结构suite失败或输入/评分证据非法必须非0，不能通过未评分掩盖。

## 测试/交付

先写能复现上述缺口/错误采信的最小测试，再实现；必要测试覆盖输入hash篡改、丢病例/重复ID、bool评分、null分母、无理由、来源矛盾不被总分抵消、原样本3/8严格通过且2例来源0、拒绝覆盖。可注入小fixture替身验证schema，但至少一次原8例与现行三维真实生产路径组合运行。

升级Python .venv-dependency23，只跑本新测试与原quality_dimensions/holdout受影响离线测试，Ruff。两次CLI报告除时间应一致，留原命令/完整输出/重复比对/源hash及自审、一屏交棒；生成样例代码只扫描不执行。报告失败保留，不改原标签/评分凑成功。

禁止数据库/页面/服务/真实DeepSeek/外发/联网/安装、编辑正式清单或27证据、Git暂存提交推送、清理/P2。Codex负责独立高风险反例与最终本地提交。
