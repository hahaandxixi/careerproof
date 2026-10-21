# Python 业务选证修复与真实规则报告复验

状态：**AI 辅助代码审查与离线/隔离验证，不是真人评审或独立用户验收。**

## 根因

冻结的 `campus_signup/service.py` 中，`RegistrationError.__init__` 在第 5—7 行，
`RegistrationService.register` / `cancel` 在第 25—54 / 56—77 行。

旧实现：

- `backend/app/tools/code_analyzer.py:_python_implementation_line` 只返回第一个有行为函数；
- `find_evidence` 按 `(文件, evidence_type)` 去重，同一文件只能留下一个 `python_code`；
- 规则候选因此只留下异常构造函数，后续业务方法没有进入 `evidenceList`。

知识检索索引能返回报名/取消片段，但规则报告不使用该检索结果作为最终引用；不能把“知识库能搜到”写成“已接入报告选证”。

## 修复

- `_python_implementation_anchors` 保留每个文件最多 4 个顶层函数/直接类方法；
- 按公开方法、SQL 写入/事务操作和函数体行为做有界排序，不使用项目名、固定函数名或报告 ID；
- Python 证据去重键改为 `(文件, evidence_type, 行号)`；
- `matcher.py` 把岗位要求标题传给 `find_evidence`；
- 单函数源码窗口最多 80 行，`find_evidence` 每文件最多 4 条；上下文仍受既有 40 行/4000 字符限制。

源码 SHA256：

- `backend/app/tools/code_analyzer.py`：`a353c2961474f04caf0cbf9aeb2c20f4e485f5ff3df9ab0f551f9264c8f57186`
- `backend/app/tools/matcher.py`：`8ca77bd966b79822fea1882ca5e8e164fd0aa6ca6e8b5f34992f44b6c6b3647d`
- `backend/app/tests/test_business_method_selection.py`：`1d112706202e157e25cda854f59a8bb93abe86040895a7919ad4d381f1533f45`

## 红绿回归

红测（修复前）：

```text
FAILED app/tests/test_business_method_selection.py
AssertionError: assert 'def register' in 'def __init__(self, message: str):'
1 failed in 0.07s
```

见 `red-before-fix.raw.out`。

修复后：

```powershell
Set-Location 'D:\jbcode\web ai\jianli\backend'
.\.venv-dependency23\Scripts\python.exe -m pytest app/tests/test_business_method_selection.py -q --no-header --tb=short -p no:cacheprovider --basetemp=.tmp/business-selection-general2
```

结果：**3 passed**。见 `test-selection-green.raw.out`。

受影响的匹配、证据质量、引用上下文测试：**67 passed**，见 `affected-tests.raw.out`。
等级/预算/覆盖相关目标测试：**61 passed, 1 skipped**，见 `level-budget-tests.raw.out`。

Python 单要求的实际上下文（修复后）为 3 条：`service.py:25-54`、`service.py:56-77`、`service.py:14-23`；三条片段合计约 3.1k 字符，使用真实 provider 输入估算器得到的 Python 单要求上界为 **11,434**。这只说明单要求未越界，不表示完整五项要求仍在现有 12k 输入门禁内；完整五项仍按既有证据保留为待处理预算问题，规则报告不使用该预算。

新增测试使用合成源码和临时目录，不访问数据库、不调用模型；断言业务方法被保留、候选有界、最终两/三条上下文仍覆盖关键方法，不断言分数、等级或唯一排序。

## 隔离规则报告复验

在既有隔离 PG/存储上，使用隔离源码的临时副本（不改动 8108/3108，不改正常库）生成新规则报告：

- 旧报告：`c97cdfa6-b87e-4143-9551-f780012648aa`
- 新报告：`516cc695-5044-481f-ab9b-5ffa5e59f1a5`
- 旧比较基准报告：`5960cf5d-0f6a-4564-b7ca-037e17d743e3`
- `analysisMode=rules`，无真实模型请求，旧报告读取前后相同。

Python 项引用前后：

| 报告 | 引用 | 文件/行号 |
| --- | --- | --- |
| 修复前 `5960...` | R3-E1 | `api.py:22-56`（create_app） |
| 修复前 | R3-E2 | `__main__.py:9-14`（main） |
| 修复前 | R3-E3 | `service.py:5-7`（RegistrationError.__init__） |
| 新 `516cc...` | R3-E1 | `storage.py:21-30`（BEGIN/commit/rollback） |
| 新 | R3-E2 | `service.py:25-54`（register） |
| 新 | R3-E3 | `service.py:56-77`（cancel） |

新报告仍为 `supported` / `level=3` / “任务实现”。等级未变；本轮**不**声称应升/降级，只确认引用现在包含报名、取消和事务回滚实现。

仍存在：

- `evidenceLevelGap` 仍是“仍需可核对的运行结果与验证记录，不能确认本人贡献”的通用措辞；
- 规则说明仍是“存在Python函数实现”的泛化文案，未逐项解释满额/重复/取消；
- 选证排序使用公开方法、SQL/事务行为作为结构化信号，不是完整的跨文件语义理解；无关的 SQL 写入方法仍可能竞争候选；
- 真实 Agent/模型、页面、真人语义和独立用户验收未执行。

## 文件

- `report-after.json`：新规则报告
- `comparison.json`：旧基准与新报告比较
- `result.json`：隔离运行和源码指纹
- `red-before-fix.raw.out` / `test-selection-green.raw.out`
- `affected-tests.raw.out` / `level-budget-tests.raw.out`
- `api.raw.out` / `readback.raw.out`：隔离 API 日志（不含凭据）

## 边界

- 未修改历史模型输出、评分公式或正常库；
- 未新增真实 AI 请求；
- 未启动/停止 8108/3108，正常 3000/8000 未操作；
- 未推送、未部署。
