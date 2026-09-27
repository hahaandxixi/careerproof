> 历史归档：记录当时状态，不作为当前配置或待办入口。当前使用 [文档导航](../../README.md) 与 [DeepSeek 能力矩阵](../../DeepSeek统一路线与能力验收.md)。

# CareerProof 三模型 API 申请与接入操作流程

更新日期：2026-09-12。执行顺序为百炼主模型、Groq 备用、OpenRouter 应急。
免费额度、模型名称和控制台界面可能调整，以账号控制台当天显示为准。

## 0. 开始前

准备三个可登录的账号，并确认可以接收验证邮件或短信：

- 阿里云账号，用于阿里云百炼；
- GroqCloud 账号；
- OpenRouter 账号，可选。

安全规则：

- API Key 只保存在 `backend/.env`，不要发送到聊天、截图或群聊；
- 不要把 Key 写入前端目录或任何 `NEXT_PUBLIC_*` 变量；
- `backend/.env` 已被 Git 忽略，`backend/.env.example` 只能放空模板；
- 创建后先用合成演示材料测试，不上传真实个人简历；
- 在真实 Provider 接通前保留 `AI_PROVIDER=mock`，现有规则链路继续可用。

## 1. 创建百炼主模型 Key

1. 打开 [百炼北京地域 API Key 页面](https://bailian.console.aliyun.com/cn-beijing/model/settings/api-key) 并登录。
2. 确认页面地域是 **华北 2（北京）**。人在深圳或广州不影响使用北京地域。
3. 如果首次进入，阅读并同意服务协议，完成百炼开通。
4. 点击“创建 API Key”。
5. 归属业务空间选择“默认业务空间”。
6. 描述填写 `careerproof-dev`。
7. 开发阶段可选择全部模型权限；比赛部署前可改成自定义权限，只开放实际使用的 Qwen 模型。
8. 创建后立即保存两项内容：
   - API Key；
   - 弹窗显示的 API Host。
9. 新版 Key 的完整明文可能只展示一次。丢失时应重置或新建，不要尝试从日志找回。

地域的 Key、API Host 和模型列表不能交叉使用。优先使用创建 Key 时返回的业务空间专属 API Host；
不要自行把北京 Key 配到新加坡或其他地域地址。旧版兼容地址是
`https://dashscope.aliyuncs.com/compatible-mode/v1`，但项目接入时以弹窗中的 API Host 为准。

### 开启免费额度保护

1. 在百炼控制台进入“免费额度”页面。
2. 搜索准备使用的 Qwen Plus 或 Flash 模型。
3. 确认它在北京地域显示剩余免费额度和有效期。
4. 打开“免费额度用完即停”。
5. 最稳妥的方式是点击“批量设置 → 一键开启所有模型”。
6. 开启后等待片刻再测试。额度耗尽时接口会返回 HTTP 403，错误码为
   `AllocationQuota.FreeTierOnly`，不会继续按量扣费。

已实名认证账号通常需要手动开启该保护；未实名认证账号可能被系统强制开启。只有北京地域参与
新人模型免费额度，且不是所有模型都有免费额度。

### 百炼模型选择

在模型广场确认当前可用且支持结构化输出的型号。CareerProof 的初始选择顺序：

1. 当前支持 JSON Schema 的 Qwen Plus 型号；
2. 当前支持 JSON Schema 的 Qwen Flash 型号；
3. 如果别名可用，先使用稳定别名 `qwen-plus`，再记录实际返回的模型版本。

不要一开始使用 Max。简历摘要、岗位要求提取和证据解释更适合 Plus/Flash，免费额度消耗也更容易控制。

## 2. 创建 Groq 备用 Key

1. 打开 [GroqCloud API Keys](https://console.groq.com/keys) 并登录。
2. 创建或选择项目 `CareerProof`。Groq 的 Key、用量和限流按项目管理。
3. 点击“Create API Key”。
4. 名称填写 `careerproof-dev`。
5. 立即复制并保存 Key。
6. 打开账号的 Limits 页面，确认 Free Plan 当前限制。
7. 初始模型使用 `openai/gpt-oss-20b`。

Groq 的 OpenAI 兼容地址固定为：

```text
https://api.groq.com/openai/v1
```

当前官方 Free Plan 对 `openai/gpt-oss-20b` 列出的限制是 30 RPM、1000 RPD、
8000 TPM 和 200000 TPD。账号实际限制以 Limits 页面为准。Groq 在项目中只接管百炼超时、
429、5xx 或 JSON 校验失败的请求。

## 3. 创建 OpenRouter 应急 Key

此步骤可最后完成，不影响主链路开发。

1. 打开 [OpenRouter API Keys](https://openrouter.ai/settings/keys) 并登录。
2. 点击创建 Key，名称填写 `careerproof-emergency`。
3. 如果页面提供额度上限，设置一个较小的硬限制。
4. 立即复制并保存 Key。
5. 在模型列表中确认当天可用的免费模型。

OpenRouter 的 OpenAI 兼容地址是：

```text
https://openrouter.ai/api/v1
```

未购买至少 10 美元额度时，免费模型通常合计限制为每天 50 次请求。`openrouter/free` 适合连通测试，
但会自动选择模型，因此不能用于固定评测。正式应急配置应锁定一个当天可用的 `:free` 模型，并要求
Provider 支持结构化参数。

## 4. 写入 CareerProof 本地配置

打开本机文件：

```text
D:\jbcode\web ai\jianli\backend\.env
```

在文件末尾加入以下配置，并在本机编辑器中替换 Key。不要把替换后的内容复制到聊天：

```dotenv
# 保持 mock，等代码接入和三项检查完成后再改为 bailian
AI_PROVIDER=mock
AI_EXTERNAL_ENABLED=false

# 百炼主模型
DASHSCOPE_API_KEY=在本机填写
BAILIAN_BASE_URL=填写创建Key时弹窗显示的API Host
BAILIAN_MODEL=qwen-plus
BAILIAN_TIMEOUT_SECONDS=30

# Groq 备用
GROQ_API_KEY=在本机填写
GROQ_BASE_URL=https://api.groq.com/openai/v1
GROQ_MODEL=openai/gpt-oss-20b
GROQ_TIMEOUT_SECONDS=20

# OpenRouter 手动应急
OPENROUTER_API_KEY=在本机填写
OPENROUTER_BASE_URL=https://openrouter.ai/api/v1
OPENROUTER_MODEL=openrouter/free
OPENROUTER_TIMEOUT_SECONDS=30

# 无论外部模型是否可用，都允许规则引擎完成报告
AI_LOCAL_FALLBACK_ENABLED=true
```

如果暂时只申请了百炼，只填写百炼三项，其他 Key 保持空白。不要把占位文字当成真实 Key 启动。

## 5. 接入代码前检查

逐项确认：

- 百炼页面显示北京地域、剩余额度和“用完即停已开启”；
- 已保存百炼 API Key 和与它配套的 API Host；
- Groq Key 属于 `CareerProof` 项目，Limits 页面可以打开；
- OpenRouter Key 已设置较小额度上限，或暂时不创建；
- 所有 Key 只存在于 `backend/.env`；
- `git status` 不显示 `backend/.env`；
- `AI_PROVIDER` 仍为 `mock`，`AI_EXTERNAL_ENABLED` 仍为 `false`。

完成后只需告诉开发人员“百炼已配置”“Groq 已配置”或“OpenRouter 已配置”，不要提供 Key 内容。

## 6. 代码接入顺序

申请和本地配置完成后，按以下顺序实现：

1. 在后端 Settings 中声明三组 Provider 配置，并拒绝占位 Key。
2. 实现统一 OpenAI 兼容 HTTP 客户端，API Key 只在后端使用。
3. 百炼采用低温度、非流式、严格 JSON Schema 请求。
4. 校验模型结果，禁止模型修改本地证据行号、文件哈希和规则判定。
5. 遇到超时、429、5xx、空响应或 Schema 错误时切换 Groq。
6. Groq 仍失败时回退本地 `evidence-v3`，任务状态仍标记为成功，但记录降级原因。
7. OpenRouter 只通过管理员配置手动启用，不参加默认自动路由。
8. SSE 展示“本地检索 → 百炼解释 → 备用模型 → 规则降级 → 报告完成”等应用阶段，
   不直接流式输出未校验的模型内容。

目标调用链：

```text
本地材料解析和检索
  -> 百炼 Qwen
  -> 失败时 Groq GPT-OSS-20B
  -> 仍失败时 evidence-v3 本地规则
  -> 证据校验、人工复核、报告保存
```

## 7. 连通与验收流程

代码接入后按以下顺序验收，每一步成功后再进行下一步：

1. **配置检查**：只输出 Provider 名称、模型名和 Key 是否存在，绝不输出 Key。
2. **百炼连通测试**：用一句合成岗位要求请求严格 JSON，确认 HTTP 200 和 Schema 合法。
3. **Groq 连通测试**：发送相同请求，确认 HTTP 200，并记录限流响应头。
4. **OpenRouter 连通测试**：仅用合成文本测试；记录实际命中的模型与 Provider。
5. **固定评测集**：运行现有 7 条 evidence-v3 基线，比较字段完整率、引用准确率和失败率。
6. **降级测试**：分别使用错误 Key、超短超时和模拟 429，确认链路能切换且不会卡死任务。
7. **浏览器主链路**：上传合成材料、发起分析、观察 SSE、查看引用、人工复核并刷新找回报告。
8. **断网演示**：关闭外部 Provider，确认本地规则仍能生成可展示报告。

正式切换条件：

```dotenv
AI_PROVIDER=bailian
AI_EXTERNAL_ENABLED=true
```

切换后必须重启 FastAPI 进程，使 `.env` 重新加载。

## 8. 比赛前检查

- 百炼和 Groq 分别完成至少 3 次连续合成请求；
- 固定评测集保存模型名、日期、成功率、延迟和 Token 用量；
- OpenRouter 未使用自动免费路由生成评分基线；
- 报告明确区分规则证据、模型解释和人工复核；
- 所有外部请求只携带完成当前判断所需的最小文本片段；
- 删除日志中的简历原文、Authorization Header 和异常请求体；
- 演示前检查百炼剩余额度与 Groq 当日剩余请求；
- 准备本地规则降级开关，现场网络异常时仍可完成演示。

## 官方入口

- [百炼 API Key 获取与地域规则](https://help.aliyun.com/zh/model-studio/get-api-key)
- [百炼地域与 API Host](https://help.aliyun.com/zh/model-studio/regions/)
- [百炼免费额度与用完即停](https://help.aliyun.com/zh/model-studio/new-free-quota)
- [百炼模型价格与免费额度](https://help.aliyun.com/zh/model-studio/model-pricing)
- [Groq API Keys](https://console.groq.com/keys)
- [Groq OpenAI 兼容接口](https://console.groq.com/docs/openai)
- [Groq Free Plan 限流](https://console.groq.com/docs/rate-limits)
- [OpenRouter API Keys](https://openrouter.ai/settings/keys)
- [OpenRouter Quickstart](https://openrouter.ai/docs/quickstart)
- [OpenRouter 免费模型限制](https://openrouter.ai/docs/faq)
