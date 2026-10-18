# task70 · AI 质量人工复核包 — 交棒

## 10/18最新：首批真实三例已执行，人工语义待核

用户明确授权后，从7197f35工作树、backend/.venv-dependency23运行d31e01d执行器；实际3次POST、无自动重试/修复外发，生产结构及grounding校验3通过，状态structural_checks_complete_human_review_pending。Prompt为v29，响应model字段均为deepseek-flash；官网公布的具体版本名不是响应明确给出的版本标识。

跨日核对：三个供应商created时间换算北京分别为2026-10-18 23:57:55、23:57:57、23:58:00，结果文件23:58:01写完；因此本批确在10/18周末执行。10/19只整理证据，未新增请求；不能复用10/18价格快照发起新批次。

完整原响应、模型输出、收据在live-smoke-20261018-a.json；CLI原始输出live-smoke-20261018-a.raw.out，摘要与SHA256在live-smoke-summary-20261018.json。供应商回执输入9496、输出1315 tokens，其中缓存命中4864、未命中4632。按当日官方周末价估算0.00998928元（约1分钱），非账户扣费发票或余额核对；0.1488元是保守预算预留，不是实际支出。批次claim保留于backend/.tmp/ai-smoke，额度已用满，不再运行或删claim续跑。

助手初查（不计人工成绩）：健康接口输出限定静态返回、明确运行和贡献未知；空接口指出pass并先补实现；固定返回0案例识别与求和声明不一致，没有声称程序已运行或推断造假动机。建议包含交付物及核验点，但实际可执行性和等级边界仍需独立人员判断。这不是3/3语义合格率，也不满足12例/6类覆盖。

[首批三例人工核对表](current-three-human-review.md)含完整合成输入、实际发送引用映射、模型原输出及空白评审栏，不附预期rubric或助手初查；人工评审数仍0、语义通过率null。复核者应先独立阅读该表，不先读本段。仅证明生产provider/提示词/净化/grounding阶段的独立合成评测；没有业务库持久账、SSE/浏览器或整站真实AI报告链验收。

精确执行命令（backend目录）：`python -m evals.bounded_evidence_smoke --live --packet ../docs/evidence/20261017-task70-semantic-review-packet/current-smoke-preflight-20261018.json --prices ../docs/evidence/20261017-task70-semantic-review-packet/deepseek-prices-20261018.json --output ../docs/evidence/20261017-task70-semantic-review-packet/live-smoke-20261018-a.json`，退出0。未扩大授权、未读真实简历或操作正常库/服务。

## 10/18补充：当前生产提示词的三例待评测输入

在7f7802b源码上运行`prepare_current_smoke.py --output current-smoke-preflight-20261018.json`（命令从仓库根用backend/.venv-dependency23解释器，文件参数写本目录完整相对路径）。新增预演不覆盖下方10/17历史包或旧模型输出。

- 使用既有合成route-body、empty-route、contradictory-return，分别检查可见实现、空实现、声明与实现矛盾；不是12例/6类完整评测。
- 真实DeepSeekProvider.analyze_evidence、生产上下文（最多2条证据）、净化及预算预检，MockTransport在HTTP客户端发送边界截获JSON后主动抛出专用异常；底层仅1次尝试，无外部网络。3次本地截获≠3次真实调用。
- 生产promptVersion为evidence-trust-v29-implementation-first-plan，thinking disabled；每例输出上限1200，保守输入字符上界分别7427/7358/6848（不是供应商账单token）。原合成输入、实际请求正文及来源文件SHA256均在JSON，不保存headers或凭据。
- Ruff退出0；独立检查三例请求、thinking/model/output上限、模型输出/人工评分仍为空、无凭据；再次指定原输出路径退出非0且原包SHA256不变。没有运行真实AI或填写语义支持率。
- 后续拟议授权范围：官方DeepSeek deepseek-flash，最多3次物理请求（含重试/修复），每次输入保守上界20000、输出1200，总费用上限1元。**此范围尚未获授权、当日价格未核验、发送前共享计数与失效停止执行器未实现，因此liveExecutionReady=false，不应直接将本包交给旧runner外发。**
- 旧run_evidence_trust仅按返回usage事后检查累计门槛，底层可能重试；这不满足本批物理请求硬上限。补执行器及离线边界测试、核价之后，再就确切输入申请网站外发授权。开发客户端额度许可不能替代。

### 10/18执行器补验（尚无真实调用授权）

后续授权更新：用户在本聊天明确回复“授权，仅这3例和上述上限”。仅覆盖已固定的健康接口、pass空接口、固定返回0/求和声明三例及生产提示词，官方DeepSeek deepseek-flash，最多3次物理请求（含重试/修复）、每次输入预算上界20000/输出1200、总费用上限1元；不包含真实个人材料、业务数据库或后续扩大批次。授权后再次取回当日官方价格页，仍按保守高峰未命中2元输入/8元输出每百万tokens预留。执行前离线核包通过、北京时间2026-10-18、实际批次尚未claim；以下“尚无授权”是先前检查时点。

接续预演新增`backend/evals/bounded_evidence_smoke.py`，没有另起评测框架或修改生产提示词。复用生产DeepSeekProvider和grounding校验，固定三例及请求正文哈希；默认CLI仅核包，不构造provider。Live必须显式传价格及新输出，不能把该参数当用户授权。

- 共享RequestGuard在POST前计数、按每次20000输入/1200输出的高峰价预留，最多3次/总上限1元；关闭此批provider重试。额外用真实provider+MockTransport证明，即便改成3次重试，503/超时后也不会发生第二次HTTP。缺失/非法/超量usage、费用不足、记录写入失败或请求哈希变化均停止，不填补为成功。
- 首版仅单实例上限，复核发现不同输出文件可启动另一个实例。已加固定批次`current-smoke-20261018-three-cases`的持久独占claim，位于backend/.tmp/ai-smoke；不同输出、重启、崩溃都不重置。两独立Python进程争抢同一claim恰好一胜一拒，8个并发准入最多3个通过。不得自行删除claim恢复额度；新一轮须重新明确授权和评测范围。
- 当前生产输入JSON仅本地截获，输出/人工评分为空；`deepseek-prices-20261018.json`记录当日官方页及按高峰未命中2元输入/8元输出每百万tokens的保守价。固定三次最大预留0.1488元，网页费率不等于实际账户账单。价格日期按北京时间核对，过期拒绝执行。
- 环境backend/.venv-dependency23，Ruff通过；`app/tests/test_bounded_evidence_smoke.py`最终21通过，原始输出`bounded-guard-tests-final.raw.out`，包括可信收据不会退还请求次数。第二轮20通过保留在round2日志。第一次默认系统tmp_path有2项权限错误，其余16项通过；改用backend/.tmp下全新独占basetemp、禁缓存，不改ACL。首轮格式7项、格式化后剩1项长路径，最终修正。无正常库、服务启停或真实模型调用。
- 复跑：在backend目录，`python -m evals.bounded_evidence_smoke --packet ../docs/evidence/20261017-task70-semantic-review-packet/current-smoke-preflight-20261018.json`，退出0、OFFLINE。实际`--live`仍等待用户对确切三例/官方DeepSeek/最多3次/1元上限的确认；本次尚未创建真实批次claim、未执行真实网络/语义评测、未代人工签字。

下方仍是10/17历史交棒：

HEAD `33ba7136bd5f516360e5d2d59bacfb4c4e4f39ce`。**未改任何产品源码/评测输入/提示词**；只在本目录产出材料。

## 产出

| 文件 | 内容 |
| --- | --- |
| `sample-table.md` | 12 例**匿名**样本表：材料 + 生产输出原文 + 空白人工判断栏 + 汇总签署；**不含类别与预期结论** |
| `reference-criteria.md` | 与样本**分离**的参考判据：每例的设计类别、冻结 rubric、检验意图、来源/模型/日期 |
| `build_packet.py` | 生成脚本（只读冻结产物，复用既有 run 结果，未另造评测框架） |
| `input-hashes.txt` | 4 个冻結输入文件的 SHA256 |
| `build.raw.out` | 生成原始输出（exit 0） |

## 案例构成（12 例，6 类设计）

- 支持 2（C01 route-body、C02 test-assertion）
- 部分支持 2（C03 sql-query、C04 truncated-body）
- 缺证据 3（C05 no-evidence、C06 dependency-only、C11 unsupported）
- 归属冲突 2（C07 forged-claim、C08 contradictory-return）
- 注入 2（C09 prompt-injection、C10 empty-route）
- **建议不可执行 1（C12 controlled-function-calling-report，且无本轮新输出）**

来源构成：模型正文 8 例、规则跳过 3 例、无输出 1 例。

## 必须如实说明的缺口

1. **6 类各 2 例的完整覆盖未达成**：冻结产物在「建议不可执行」只有 1 例，且本卡禁止外发、
   不允许重跑模型，故 C12 留空。已在该文件内显式声明，**没有用凑数案例补齐**。
2. **输出不是今日模型**：11 个冻结用例的模型正文来自 `2026-09-18T01:37:15Z` 保存结果
   （provider=deepseek、suite=evidence-trust-v2、promptVersion=evidence-trust-v6-consistency）。
   不得据此声称当前模型质量或当前配置表现。
3. **人工判断全部留空**：机器评分、模型自评、本脚本均未填写任何「结论支持度/是否过度推断」，
   不代签。包内保留「评审前未见 assistant-review 文件」的独立性声明栏。
4. 真实模型小批评测**未执行**：`sample-table.md` 内已列「待批字段」（用例集、提示词版本、
   每例请求数上限 1、合计 11、输入/输出上限、预算上限、模型版本、停止条件、授权状态=未获授权）。

## 命令与结果

- `python docs/evidence/20261017-task70-semantic-review-packet/build_packet.py`
  → exit 0，`cases=12 models=8 rules=3 no_output=1`

## 未验证项

1. 未做任何真实模型请求，未产生新的模型质量证据。
2. 未邀请真实评审者填写，故本包**不含任何人工语义结论**。
3. 未核验 `trust-deepseek-v6-assistant-review-20260918.json` 的内容（独立性要求：评审前不应查看）；
   本脚本也未读取它。

## 证据

本目录全部文件；输入 hash 见 `input-hashes.txt`。
