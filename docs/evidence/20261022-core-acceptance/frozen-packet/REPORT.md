# 当前源码离线Agent回归包与执行器预算单位

基线全量离线日志`unit-baseline.raw.out`：1500通过、43失败、75跳过。12处由测试继续读取10月20日历史授权包而其源码已漂移导致；另31处为默认输入预算/规划预留相关，交预算执行端复验。分类完整列表见`unit-failure-triage.json`。没有删除失败、增加skip或重写历史哈希。

新建测试夹具`backend/app/tests/fixtures/current-20261022/agent-offline-input.json`，只供MockTransport回归，明确offlineOnly、非真实调用授权或claim。三例合成输入、历史上下文、原限制和旧包文件按字节/结构对照保留；promptVersion为当前v30，8份源码哈希绑定总控接受副本，非整个脏工作树。测试新增当前包来源验证和旧包拒绝验证；旧包/旧报告/claim未改。新包identity见`packet-identity.json`。

首次来源通过后，目标回归18通过/6失败（`target-approved.raw.out`）：暴露真实预算单位问题：执行器把单次物理请求20,000的输入边界当成整份报告累计上限，覆盖了当前40,000默认配置，规划被程序跳过，分析错误场景只有1次POST，无法覆盖预期规划→分析硬停。经总控追加授权，执行器改为累计上限min(生产设置,4×单次上限)，仍保持每次POST完整JSON+1024字节≤20,000，输出/费用/请求数/预留/硬停不变。

未放宽原5次物理请求的完整工作流、1次规划错误/2次分析错误及回执失败断言；新增工具schema超限发送前零预留测试，并断言运行内累计40,000及运行后恢复设置。总控接受副本8份源码哈希逐一吻合，新夹具也逐字节复制；不是整个脏工作树。

无真实网络/模型/业务数据库，所有执行器请求均由httpx.MockTransport承接，临时claim目录每测独占。只修改执行器、直接测试和新测试夹具。首次沙箱无输出执行仅中断自有会话，随后目标测试走已批准权限；没有ACL或依赖变动。

## 最终接受副本验证

工作目录：`backend/.tmp/core-acceptance-20261022/source/backend`；PYTHONPATH明确设为该目录，解释器仍为根`backend/.venv-dependency23/Scripts/python.exe`（复用已安装环境，无安装）。APP_ENV=test、DEBUG=false、AI_PROVIDER=mock、AI_EXTERNAL_ENABLED=false、CAREERPROOF_TEST_DATABASE_URL空。命令：

```
python -m pytest app/tests/test_agent_evidence_smoke.py app/tests/test_agent_smoke_hard_stop.py --basetemp=D:/jbcode/web ai/jianli/backend/.tmp/core-frozen-stage-tests -o cache_dir=D:/jbcode/web ai/jianli/backend/.tmp/core-frozen-stage-cache --junitxml=<evidence>/junit-stage-green.xml -q
```

实际25 passed，0failed/skip，exit0（1.90s）。`stage-green.raw.out`和`junit-stage-green.xml`保存原始结果。完整三例5次Mock POST、模型停止与程序跳过分列、400/401规划1次/分析2次、回执写入失败1次及最终日志落盘失败退出均按原关键断言通过；没有真实请求。工具schema超限在发送前零预留，累计上限与每次物理请求边界分别守住，未知usage停止不被降级吞掉。

首次接受副本运行使用不存在父目录的嵌套basetemp，得到13通过/12fixture准备错误（`stage-target.raw.out`、`junit-stage.xml`）；没有修改源码或fixture，把basetemp/cache改为独占、父目录已存在的根.tmp路径后复跑同一组通过。首次沙箱无输出和第一次新包暴露预算单位错误的失败记录亦保留。

目标Ruff（执行器及直接测试）exit0，All checks passed。总控另行执行完整CI，不能把本目标25项写成全量验收通过。本批未触碰正常数据库、服务、真实模型、历史claim/包，也未提交Git。

## 全量遗留单失败：日志配置的测试顺序污染

总控首轮接受副本全量为1559通过、1失败、87跳过。仅`test_ai_budget_database_fault_surfaces_instead_of_faking_rule_fallback`日志数量断言失败；SQLAlchemy异常实际已抛出，未改生产降级。

最小反例：该用例单跑通过，`career_planning.logger.disabled=False`；先运行`test_alembic_environment.py::test_no_x_option_still_reaches_existing_engine_boundary`再运行该用例，得到1通过/1失败且logger.disabled=True。原因是前者runpy执行真实env.py中的fileConfig，默认禁用已由pytest收集导入的应用logger，测试结束未恢复。原始对照日志`career-fault-alone.raw.out`、`career-fault-after-alembic.raw.out`保留。

修复只在测试边界：Alembic入口测试记录fileConfig参数而不改pytest进程全局日志，仍断言实际到达engine边界以及logging配置调用路径；不改生产env.py或career逻辑。职业规划故障测试另加“故障预算函数恰好进入一次”及exception.statement精确匹配故障SELECT，原单条安全warning、阶段、异常分类、隐私和SQLAlchemyError外抛断言全部保留，没有为了通过而删日志断言。

两个测试模块逐字节复制到接受副本后，原顺序两项已通过（`career-order-green.raw.out`）；完整受影响两个模块45通过、0失败/跳过，exit0（25.84s），见`career-module-green.raw.out`/XML。生产源码与8份当前包绑定源码均未变，不需重做包hash或模型测试。各文件哈希及stage一致性见`career-order-fix-identity.json`。
