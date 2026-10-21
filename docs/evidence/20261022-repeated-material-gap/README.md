# 已有材料被重复索要：wire request 复核与措辞修复

状态：**第一段完成；未提交，待 Codex 审查集成。未调用模型。**

## 1. 真实 wire request（重构 + 字节级校验）

原始 HTTP body 没有被持久化；本段用保存的 `report-after.json` 证据、运行提交 `bcbe0e3` 的消息构建器和同一 V2 材料重构请求，并用预算字节数校验：

- 模型：`deepseek-flash`
- `max_tokens`：3,952
- messages：2 条
- wire 估算：**38,846 bytes**
- 该次 analysis attempt 保存的 estimated bytes：**38,846**
- `byteEstimateMatched=true`

因此，这不是凭空推断的消息列表；消息内容和保存的预算事实逐字节口径一致。完整 messages、pytest 发送证据、规则层全集和未发送证据见 `wire-request.json`。

## 2. pytest 实际发送范围

实际发送 3 条 citations：

- `R4-E1` `tests/test_registration.py:29-39`（只是重启恢复函数）
- `R4-E2` `tests/test_registration.py:14-16`（fixture）
- `R4-E3` `requirements.txt:5`（pytest 版本）

规则层 evidenceList 有 6 条，另 3 条未发送：

- `README.md:1-9`
- `README.md:16-18`
- `runtime/pytest-output.txt:1-8`

材料中 `tests/test_registration.py` 有 **10 个测试函数**；只发送了第 1 个测试函数片段。`runtime/pytest-output.txt` 是 **11 passed** 的运行输出，但未送入模型。

## 3. 判定

同时存在两类问题：

1. **候选存在，但受上下文上限裁剪未发送**：规则层已有 `runtime/pytest-output.txt`，但 `max_evidence=3` 只发送前三项；README 与 runtime 输出在全集里，未发送。
2. **检测/选证遗漏**：规则层本身只选到 1 个测试函数（test_registration.py:29-39），没有把同文件其余 9 个测试函数作为候选/覆盖；因此不是单纯上下文裁剪。

模型只看到局部后，对 pytest 项写成“未展示重复、满额、取消、回滚与并发测试，测试执行结果未展示”，属于**把未发送当成缺失**。Redis 项没有实现，gap 判定正确，不在本修复内。

## 4. 修复

新增 `backend/app/agents/evidence_scope.py`：

- 在 AI 分析返回后、验证/保存之前，逐需求比较：
  - 模型实际发送的 citations；
  - 规则层 `evidence_list` 全集中存在但未发送的条目。
- 若 AI gap/suggestion 出现“未展示/未提供/缺少/缺失/没有/请补充/需补充/补充”等绝对缺失表述，且存在未发送规则证据：
  - gap 改为“本次片段未覆盖……；规则层保存了未发送证据：……。材料中可能已包含，请先核对……”
  - suggestion 改为“先核对……；材料中可能已包含，仅对核对后仍未覆盖的场景再补充具体材料。”
- 不改变检索、选证、评分、报告模式、API、数据库或历史结果。
- repair 路径同样应用。

规则层 `rule_narrative.py` 的“已上传文本/JSON材料”清单从 2 条扩展到 3 条，确保 `runtime/pytest-output.txt` 出现在 inventory；它仍不代表运行已验证。

## 5. 改前/改后

pytest `information_gap`：

- 改前：`未展示重复、满额、取消、回滚与并发测试，测试执行结果未展示。`
- 改后：`本次片段未覆盖模型判断所需的部分材料；规则层保存了未发送证据：...README.md:1-9、...README.md:16-18、...runtime/pytest-output.txt:1-8。材料中可能已包含，请先核对这些材料后再判断是否仍需补充。`

pytest `suggestion`：

- 改前：`补充其余场景测试函数与pytest运行输出，并说明本人贡献。`
- 改后：`先核对规则层保存但未发送的材料（...）；材料中可能已包含，仅对核对后仍未覆盖的场景再补充具体材料。`

规则报告投影：

- 改前：`本机可核对的运行结果或验证记录，仍需确认本人贡献。`
- 改后：`...已上传测试命名文件：tests/test_registration.py；已上传文本/JSON材料：runtime/README.txt、runtime/http-observations.json、runtime/pytest-output.txt。已有材料无需重复上传；...`

规则报告已实际重跑：从当前源码启动临时隔离后端 `127.0.0.1:8110`（隔离数据库，未重启 8108/3108），用固定 V2 材料、五项要求、`externalAiConsent=false` 创建规则任务；报告 `186faca9-a656-49a7-87d1-dcc7dbc5bafe`，模式 `rules`，五项齐全，pytest gap 已包含 `runtime/pytest-output.txt`。临时后端随后停止。

`rules-report-after.json` 仍保留为离线规则投影；以 `rules-report-current.json` 作为实际重跑证据。整个过程未调用模型、未读写正常库。

## 6. 验收

- `wire-request.json`：wire/attempt 均 38,846，pytest 发送 3 条、规则 6 条、未发送 3 条、材料内测试函数 10 个、runtime `11 passed`。
- `gap-before-after.json`：AI gap/suggestion 改前改后、规则 narrative gap 改前改后。
- `rules-report-current.json`：当前源码实际生成的五项规则报告（`186faca9...`，`rules`）；pytest gap 已包含 runtime 输出。
- `rules-report-after.json`：规则层 pytest gap 的离线投影，保留作对照。
- 新增回归：`app/tests/test_evidence_scope.py`、`test_rule_narrative.py` 的 runtime inventory 测试。
- 未做真实 AI 重跑；历史 `f918` 报告未改动。

## 7. 未验证 / 后续

- 其余 9 个测试函数仍未进入模型上下文；本段按任务要求只修措辞/回查，不修检索与选证。
- 没有证明模型看到完整 10 个测试后会如何评级。
- 规则报告已实际重跑；临时隔离后端 8110 已停止，8108/3108 未重启。
- AI 措辞修复尚未经新的真实模型输出验证；本段没有调用模型。
- 本段已本地提交，交 Codex 审查第一段。
