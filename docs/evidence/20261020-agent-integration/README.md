# Agent执行器集成本地验收（2026-10-20）

本轮在b756d323起点核对真实工作流的provider_override接线、同实例物理请求/预算/留痕、要求/引用/路径/行号/片段及历史来源校验。发送前、usage、回执与最终落盘失败、HTTP错误均在执行器边界停止；fallback不允许把hard_stop记为结构成功或进入后续案例。生产默认降级未改。

恢复旧执行器同输出/同claim拒绝与假密钥不落盘断言。六份受授权哈希校验源码统一LF（通过.gitattributes固定），使Git对象、解包文件和工作区身份相同；无语义改写。当前包升v3并更新输入指纹、全部源码及测试哈希；历史v1/v2原始字节保留。

## 实际检查

- backend/.venv-dependency23/Scripts/python.exe -m pytest backend/app/tests/test_agent_smoke_hard_stop.py backend/app/tests/test_agent_evidence_smoke.py backend/app/tests/test_bounded_evidence_smoke.py backend/app/tests/test_durable_provider_hooks.py -q --basetemp=backend/.tmp/agent-integration-final-20261020 -p no:cacheprovider → 51 passed，3.52s，exit 0。
- 同解释器 -m ruff check 五份本阶段源码/测试 → All checks passed，exit 0。
- 测试使用MockTransport/替身，未调用真实模型；硬停执行器测试涵盖回执失败、最终日志无法保存的子进程非零退出、规划/分析HTTP400和401。
- package-binding.json记录当前输入指纹及六份源码SHA；提交后另从Git对象验证，不能仅以工作区检查替代提交验收。

## 边界

仅离线执行器集成通过，不代表新Agent真实模型三例已执行、语义合格或页面已加载。本轮不发请求，不核销旧授权、不重置claim；执行日价格与明确授权仍需重新确认。人工三例保持0/3。

runtime-before.json是只读现场：清单保留现有构建和进程来源，但本次3000/8000只读HTTP检查均无法连接；不把旧清单当活服务证明。本轮不启停服务、不写业务库。历史closeout目录的未提交状态描述保留为当时事实；实际本轮提交由后续集成记录给出。
