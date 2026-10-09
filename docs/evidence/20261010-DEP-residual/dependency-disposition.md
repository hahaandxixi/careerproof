# 13项升级排序处置与构建残余

2026-10-10，Codex终审。本表落实原排序每一项；已升级项表示本地隔离环境和版本化清单已验证，不表示旧运行服务已更新。证据分别在DEP-01-first-batch、DEP-fastembed-compatibility、DEP-framework、DEP-frontend、DEP-toolchain目录。

| 原排序项 | 当前处置 | 证据/限制 |
|---|---|---|
| python-multipart | 升0.0.31 | 真实上传/畸形请求回归；不是完整DoS容量测试 |
| Pillow | 升12.3.0 | 图像/OCR预检，联动fastembed0.8.1实际嵌入兼容 |
| PyJWT | 升2.15.0 | 旧token、畸形token、角色授权回归 |
| Starlette | 升1.3.1并联动FastAPI0.143.0 | 全套/真实PG与MCP、SSE/生命周期/OpenAPI |
| Next | 升15.5.27 | 独立node环境193/类型/生产构建 |
| sharp | 升0.35.5 | 真实合成SVG→PNG、记录Windows原生库 |
| Next内嵌PostCSS | next专属override8.5.28 | 声明仍8.4.31，实际锁/解析/CSS source map/build验证 |
| selector-parser | 保留6.1.4，明确未修 | 修复7.1.6超出Tailwind3/postcss-nested6范围 |
| source-map-js | 升1.2.2 | 两份PostCSS消费者解析与map相容 |
| braces | 保留3.0.3，明确未修 | 维护方first_patched_version=null，不能编造补丁 |
| pip | 升26.2.1 | dev pin/安装解析/pip check；旧venv未升 |
| pytest | 升9.0.3并联动asyncio1.4.0 | 完整1094+PG79，不关闭失败 |
| Mako | 升1.4.2 | 直接pin、真实模板渲染和迁移回归 |

## 两项残余的具体裁决

GitHub原公告braces-advisory.json/selector-advisory.json，与官方npm审计一致；7个受影响包是两个直接公告经父依赖传播，不是7个独立漏洞。braces公开registry仍3.0.3；selector-parser6线仍截至6.1.4。postcss-nested8.0.1允许^7.1.4，但只换nested仍不能移除Tailwind3自身^6.1.2或braces链。npm提示父Tailwind4.3.3属于移除旧依赖链候选，不是braces发布了补丁。

本轮裁决：暂缓Tailwind4跨major迁移，保留两项明确已知风险，先完成升级后网站行为和样式基线；不全局强装selector-parser7，不运行audit fix --force。不把可安装或audit建议当兼容证明。4.x涉及PostCSS插件改为@tailwindcss/postcss、CSS入口/源码发现、Preflight/边框/ring/shadow默认行为，须单独验收panel/field/button、中文与390px焦点/布局，不能用本轮CSS五例替代这项大迁移。

缓解与实证：当前Next CSS唯一源码入口layout.tsx静态import globals.css；Tailwind content只src/app和src/components，模板/样式来自受信版本化代码。本轮build使用Git跟踪源码隔离副本，不把学生上传材料放入npm/Tailwind源码或glob构建，不执行其包管理脚本。上传材料在backend独立存储/分析工作进程，网页展示片段；全src静态搜索未发现style标签/动态注入或dangerouslySetInnerHTML。只证明当前源码入口边界，其他部署/未来新入口未验证，不能声称远程不可达或风险为零。

跟踪责任：Codex阶段签收时重新核对两条公告/registry与lock；后续ZCode有界批次可在独立前端副本验证Tailwind4候选并起草迁移证据，Codex审样式/输入边界及代表页面。若出现接收不可信CSS/glob的新入口、6.x补丁或父依赖兼容更新，重新排序，不沿用本暂缓结论。残余必须进入下一接力，不算漏洞清零。

依赖处置阶段已覆盖13项的升级或明确残余裁决；整个用户目标仍缺升级环境真实迁移/双端页面和AI可重复质量评测，不能据此完成目标。
