# DeepSeek 官方 API 接入

更新日期：2026-09-26。

CareerProof 所有产品外部生成调用统一使用 DeepSeek 官方 API，包括学生报告、职业规划、企业岗位拆解和截图内容观察，共用同一份本地 Key、官方地址与 `deepseek-flash`。不使用网页 Cookie、浏览器转接或第三方反向代理。适配器复用既有的证据白名单、结构化输出校验、最多两轮受控补检索、有限重试和规则降级。

## 固定配置

```env
AI_PROVIDER=deepseek
AI_EXTERNAL_ENABLED=true
DEEPSEEK_API_KEY=只在本机填写
DEEPSEEK_BASE_URL=https://api.deepseek.com
DEEPSEEK_MODEL=deepseek-flash
DEEPSEEK_TIMEOUT_SECONDS=90
DEEPSEEK_MAX_ATTEMPTS=2
```

- 适配器只接受官方 `https://api.deepseek.com`，避免把 Key 发送到第三方地址。
- 只允许 `deepseek-flash`，阻止误选成本更高的型号。
- 请求显式使用非思考模式，减少延迟和不可见推理输出。
- Key 只保存于被 Git 忽略的 `backend/.env`，不能写入前端、聊天、日志或仓库。
- 本地产品启动要求 `AI_EXTERNAL_ENABLED=true`；如果Key或Provider配置缺失，启动脚本会明确失败，不会主动切换到规则模式。
- 产品工厂拒绝百炼、千问和智谱选择；旧适配器仅用于历史离线回归，旧连通诊断已停用。历史报告不删除、不改写模型来源。
- 本地 OCR、ONNX 检索、哈希索引与被动规则保护不属于外部生成调用，继续在本机运行；不为了统一供应商额外发送原文件或替换成本地部署 DeepSeek 权重。

## 截图理解

图片使用同一个 DeepSeek Key，无需再配置智谱。本人先检查图片并单独同意外发原图像素，才调用官方视觉输入；去除图片元数据不等于像素脱敏。模型只描述可见内容和估计区域，不参与实践评级。失败保留原图和本地 OCR。

2026-09-26 合成截图真实成功：输入554、输出365 Tokens，API记录模型耗时1926ms；重复请求复用保存结果，本人核对状态刷新保持，企业读取/复核均404。没有核对实际账单，不能宣称免费。详见[视觉验收](视觉证据验收-20260926.md)。

## 验证命令

只检查本地配置，不发送请求：

```powershell
cd backend
.\.venv\Scripts\python.exe -m app.scripts.check_deepseek
```

显式发送一次合成请求：

```powershell
.\.venv\Scripts\python.exe -m app.scripts.check_deepseek --live
```

脚本只保存 Provider、模型、Token、耗时和错误类型，不保存 Key、请求头或真实材料。每次运行生成新的 `backend/evals/deepseek-connectivity-*.json`，不覆盖历史。

## 首次真实结果

2026-09-18 的合成连通测试成功：`deepseek-flash` 返回合法 JSON，输入 106 Tokens、输出 50 Tokens、模型耗时 1,372 ms，总耗时 1,374 ms。该记录证明接口、模型名和 JSON 协议可用，不证明完整证据报告质量，也没有独立核验账单。

原始记录：`backend/evals/deepseek-connectivity-20260918-085150.json`。

## 官方资料

- API 文档：https://api-docs.deepseek.com/
- Chat Completions：https://api-docs.deepseek.com/api/create-chat-completion/
- JSON Output：https://api-docs.deepseek.com/guides/json_mode/
- 模型与价格：https://api-docs.deepseek.com/quick_start/pricing/
- 视觉输入：[官方视觉指南](https://api-docs.deepseek.com/zh-cn/guides/vision/)。

DeepSeek官方API按Token计费，不应描述为永久免费服务。比赛演示始终使用AI链路；余额、网络、限流、超时或输出校验异常时，由服务端自动保存本地兜底报告。
