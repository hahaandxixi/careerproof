> 历史归档：记录当时状态，不作为当前配置或待办入口。当前使用 [文档导航](../../README.md) 与 [DeepSeek 能力矩阵](../../guides/AI与数据边界.md)。

# 免费模型 API 候选与接入顺序

更新日期：2026-09-10。免费额度、模型名单和区域限制会变化；接入前仍以控制台显示为准。

## 推荐组合

### 1. 阿里云百炼：国内主选

- 适合：中文岗位要求、简历解释和结构化输出。
- 免费方式：部分模型有新人免费额度，官方价格页说明通常在开通、模型发布或申请通过后 90 天内有效，具体模型和区域以百炼控制台为准。
- 风险：免费额度不是所有模型都有；不要把 Token Plan 专属 Key 当作通用免费 API Key 使用。
- 适配方向：OpenAI 兼容客户端，配置百炼 compatible-mode 地址。

### 2. Groq：高速英文/代码备选

- 适合：短文本摘要、代码解释、快速演示。
- 免费方式：官方 Free Plan 按模型提供 RPM、RPD、TPM 等限制；例如官方页面列出了部分开源模型的免费日请求和 token 上限。
- 风险：免费额度是速率限制，不是固定美元余额；模型名单和限额会动态调整。
- 适配方向：OpenAI 兼容 API，优先选择控制台当前仍在 Free Plan 表中的开源模型。

### 3. OpenRouter：统一备用网关

- 适合：需要快速切换多个免费模型和 Provider。
- 免费方式：使用 `openrouter/free` 或模型的 `:free` 变体；官方当前说明免费账号通常为每天 50 次免费模型请求，购买至少 10 美元额度后可提高到每天 1000 次。
- 风险：免费模型可用性、延迟和上下文限制不稳定；不同 Provider 的数据策略要分别核对。
- 适配方向：OpenAI 兼容 API，最适合放在项目的 fallback provider。

### 4. SiliconFlow：国内模型备选

- 适合：中文模型、Qwen/GLM 等开源模型的低成本测试。
- 免费方式：官方文档说明有多个免费模型，并提供固定的免费模型速率限制；具体模型和当前限额以账号控制台为准。
- 风险：免费模型不等于永久免费，模型上下线和额度策略可能变化。
- 适配方向：OpenAI 兼容 API，适合作为百炼不可用时的国内 fallback。

### 5. Google Gemini API：多模态实验备选

- 适合：后续需要 PDF、图片或长文本理解时做对照实验。
- 免费方式：官方定价页提供 Free tier，部分模型输入输出免费，但免费层的使用内容可能用于改进 Google 产品。
- 风险：地区、账号、网络和配额可用性需要现场确认；真实简历不应直接放入免费层。
- 适配方向：先用合成材料做模型评测，再决定是否保留。

### 6. Hugging Face Inference Providers：极小额度测试

- 适合：验证某个开源模型是否能调用。
- 免费方式：官方当前说明 Free 用户每月有 0.10 美元实验额度。
- 风险：额度很小，不适合比赛演示主链路。

## CareerProof 建议顺序

```text
百炼（中文主选）
  -> Groq（高速代码摘要）
  -> OpenRouter（统一免费路由）
  -> SiliconFlow（国内开源模型备用）
  -> Gemini（多模态实验）
```

项目已保留 `MockAIProvider` 和规则基线，并接入可选的百炼千问证据分析层。模型逐项解释
后端给出的候选片段、返回白名单引用、信息缺口和建议，不能覆盖规则判定、文件行号、哈希
和人工复核结果；调用或校验失败时自动生成规则报告。

## 本地配置约定

不要把 Key 写入仓库、截图或聊天。每次只启用一个 Provider：

```dotenv
AI_PROVIDER=mock
AI_BASE_URL=
AI_API_KEY=
AI_MODEL=
AI_EXTERNAL_ENABLED=false
```

接入验证顺序：健康检查 → 单条合成请求 → 固定评测集 → 失败降级到规则基线 → 再接入浏览器演示。真实个人简历在供应商数据保留和训练政策确认前不发送。

## 官方参考

- Google Gemini：[定价与 Free tier](https://ai.google.dev/gemini-api/docs/pricing)
- Groq：[Free Plan 限制](https://console.groq.com/docs/rate-limits)
- OpenRouter：[免费模型限制](https://openrouter.ai/docs/faq) 与 [免费模型变体](https://openrouter.ai/docs/guides/routing/model-variants/free)
- SiliconFlow：[速率限制](https://docs.siliconflow.cn/docs/userguide/rate-limits/rate-limit-and-upgradation)
- 阿里云百炼：[新人免费额度](https://help.aliyun.com/zh/model-studio/new-free-quota) 与 [模型价格/免费额度](https://help.aliyun.com/zh/model-studio/model-pricing)
- Hugging Face：[Inference Providers 定价](https://huggingface.co/docs/inference-providers/pricing)
