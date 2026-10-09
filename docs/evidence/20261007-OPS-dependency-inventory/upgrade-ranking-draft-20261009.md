# 依赖升级排序草稿（传智杯21）

2026-10-09，BigModel 个人 Flash 起草，供 Codex 独立终审。这是草稿不是实施卡：本文只排序与列边界，不安装、不升级、不启动任何服务，不改生产源码。

## 0. 证据基础与快照说明

- 输入证据（同目录）：`local-inventory-20261009.json`（HEAD dc40951，108 项 Python 安装分发 + 137 条前端 lock）、`reviewed-version-matches-20261009.json`（244 包/版本逐包查询，244 成功 0 失败，13 包命中 51 条公告）、`official-advisories-20261009.json`（8 个维护方仓库 152 条公告原文）、`candidate-releases-20261009.json`（13 项候选发布核对）、`registry-confirmation-20261009.md`（PyPI 补证）、`coverage-20261009.md`、`advisory-checkpoint-20261009.md`。
- 代码/lock 定点复核（本文新增，只读）：`backend/pyproject.toml`、`jianli/package-lock.json`（按包索引读取）、`app/api/v1/portfolio.py`、`app/services/visual_evidence.py`、`app/agents/vision_provider.py`、`app/tools/ocr.py`、`app/core/security.py`、`jianli/next.config.mjs`、`jianli/postcss.config.mjs`。
- 快照差异：inventory 采集于 dc40951；当前 main HEAD 12501ba（比任务卡所写 2a105b5 多一个仅改 `docs/当前接力.md` 的 docs 提交），无代码差异。工作区另有未提交的 `docs/当前接力.md` 改动，与依赖无关。
- 运行时：venv Python 3.12.14（pyproject 钉 `>=3.12,<3.13`），Node v22.23.1。

## 1. 13 命中包清单

51 条 reviewed 命中公告，不是 51 个独立可利用漏洞；同一问题可重复记录。官方仓库公告数与 reviewed 命中数的差额（如 python-multipart 9→7、PyJWT 23→8、starlette 10→5）是"维护方全量公告中其余条目的版本区间不匹配本地版本"，不是遗漏。

| # | 包 | 本地版本 | 用途/归属 | 命中公告 | 修复候选 | 候选发布证据 |
|---|---|---|---|---|---|---|
| 1 | python-multipart | 0.0.20 | 生产上传解析；pyproject 直接 pin，另被 fastapi standard extra（>=0.0.18）与 mcp（>=0.0.9）引用 | 7（high×3） | 0.0.31 | GitHub release 2026-06-04，confirmed |
| 2 | Pillow | 11.3.0 | 生产图像处理；pyproject 直接 pin | 13（high×10） | 12.3.0 | GitHub release 2026-07-01，confirmed |
| 3 | PyJWT | 2.10.1 | 生产认证；pyproject 直接 pin，另被 mcp `pyjwt[crypto]>=2.10.1` 引用 | 8（critical×1, high×2） | 2.15.0 | GitHub release 2026-09-23，confirmed |
| 4 | starlette | 0.47.3 | 生产框架；mcp extra 直接 pin + fastapi 传递约束 | 5（high×3） | 1.3.1 | GitHub release 2026-06-12，confirmed |
| 5 | next | 15.5.25 | 前端框架；直接依赖 ^15.5.25 | 2（medium×2） | 15.5.27 | GitHub release 2026-09-30，confirmed（原维护方 API 的 15.5.? 占位已由此落实） |
| 6 | sharp | 0.35.4 | next optionalDependencies `^0.34.3 \|\| ^0.35.4` 的传递依赖 | 1（high） | 0.35.5 | GitHub release 2026-09-27，confirmed |
| 7 | postcss（next 内嵌） | 8.4.31 | 构建工具链；next 自身钉死 8.4.31（`node_modules/next/node_modules/postcss`） | 4（high×2） | 8.5.23 | GitHub release 2026-07-24，confirmed |
| 8 | postcss-selector-parser | 6.1.4 | 构建工具链；tailwindcss 锁 `^6.1.2`、postcss-nested 锁 `^6.1.1` 的 6.x 传递 | 1（medium） | 7.1.6（跨 major） | GitHub release 2026-09-03，confirmed |
| 9 | source-map-js | 1.2.1 | 构建工具链；root postcss（^1.2.1）与 next 内嵌 postcss（^1.0.2）共同传递 | 1（high） | 1.2.2 | GitHub release 2026-09-30，confirmed |
| 10 | braces | 3.0.3 | 开发工具链；chokidar 与 micromatch（dev，tailwind JIT/watcher 链）传递 | 1（high） | **无已知补丁字段，不得编造版本** | 无候选 |
| 11 | pip | 25.0.1 | venv 安装工具本身 | 6（medium×5, low×1） | 26.2（PyPI 规范化版本名） | PyPI wheel 2026-07-29，yanked=false；GitHub 26.2.0 release 未确认，不宣称存在 |
| 12 | pytest | 8.4.2 | dev extra 测试工具；pyproject 直接 pin | 1（medium） | 9.0.3（跨 major） | GitHub release 2026-04-07，confirmed |
| 13 | Mako | 1.4.1 | alembic 1.16.5 传递依赖（迁移模板引擎，venv dist-info `Requires-Dist: Mako`） | 1（medium） | 1.4.2 | PyPI wheel 2026-09-22，yanked=false，requires_python>=3.10；GitHub release 未找到，不等于未发布 |

## 2. 单列约束（任务卡点名）

### 2.1 Next 内嵌 postcss

- lock 中存在两份 postcss：root dev `8.5.26`（installed 8.5.28，**未被本批公告命中**）与 next 内嵌 `8.4.31`（**命中 4 条，修复需 8.5.23**）。
- next 15.5.25 在 lock 中把 postcss 钉为字面量 `8.4.31`；升级 root postcss 不能移除嵌套副本。唯一随批次移动它的途径是 next 自身升级；**next 15.5.27 是否调整内嵌 postcss 版本，当前证据未包含，列为实施卡核对项**，不得预设"升 next 即修复 postcss"。
- 入口条件：postcss 管道只处理本地受信源码（`postcss.config.mjs` = tailwindcss + autoprefixer）；sourceMappingURL 自动加载类攻击需攻击者可控 CSS/源映射，现有构建未提供该入口。防御性升级，非已证实可达。

### 2.2 postcss-selector-parser 6.x

- tailwindcss `^6.1.2` 与 postcss-nested `^6.1.1` 均约束 6.x；候选 7.1.6 是跨 major，直接强装会制造依赖冲突。正确路径是等待/推动上游（tailwind 3.4.x 线）放宽，或单独评估 tailwind 大版本升级（超出本卡范围）。
- 入口条件：选择器解析只吃本地样式源码，CPU 复杂度攻击需非可信选择器输入，现有构建未提供。

### 2.3 FastAPI 联合升级新增依赖

fastapi 0.143.0（tag 源码 pyproject，sha 1b018d2）相对当前 0.116.1：

- 运行时新增 3 项：`typing-inspection>=0.4.2`、`annotated-doc>=0.0.2`、`opentelemetry-api>=1.44.0`（当前仅 starlette/pydantic/typing-extensions 三项）。
- starlette 上界消失：0.116.1 钉 `starlette>=0.40.0,<0.48.0`；0.143.0 声明 `starlette>=0.46.0` 无上界，starlette 1.3.1 的声明相容由此成立——**声明相容不等于回归通过**。
- standard extra 新增/抬升：`fastar>=0.9.0`、`fastapi-cli>=0.0.32`、`pydantic-extra-types>=2.0.0`、`opentelemetry-sdk/exporter-otlp-proto-http>=1.44.0`（本项目经 uvicorn 直接起服，standard extra 是否在用须在实施卡核对 requirements/安装方式）。
- 联动 pin：`backend/pyproject.toml` 的 mcp extra 显式钉 `starlette==0.47.3`，联合升级须同步改；mcp 1.30.0 自身要求 `starlette>=0.27`（python_version<3.14 分支，本项目 3.12 生效）与 `pyjwt[crypto]>=2.10.1`，对 starlette 1.3.1 / PyJWT 2.15.0 均放行。

## 3. 升级批次排序（按发布确定性 × 入口可达性 × 风险）

### 批次1：生产上传/图像链，单包直接升级（先行）

| 项 | 内容 |
|---|---|
| 顺序 | ① python-multipart 0.0.20→0.0.31；② Pillow 11.3.0→12.3.0 |
| 已发布证据 | 两者 GitHub release 均 confirmed；0.0.31 同时覆盖全部 7 条（0.0.22/26/27/30/31 各项），12.3.0 覆盖全部 13 条。**0.0.27 与 Pillow 12.1.1 只是旧的单项修复，不得当完整候选**。 |
| 实际入口条件 | multipart：`app/api/v1/portfolio.py` 两处 `UploadFile = File()` + `Form(...)`，真实解析路径存在；应用层大小校验在上传后，不能排除解析阶段 DoS（part header/preamble 类）。Pillow：`safe_png`（visual_evidence.py:67）、`vision_provider.py:49`、`ocr.py:33` 三处 `Image.open(BytesIO(...))` 均无 formats 白名单，像素/尺寸检查在 open 之后；PSD/FITS/BDF 等伪装格式可在检查前进入解码器。 |
| 兼容性风险 | Pillow 11→12 跨 major（API/常量弃用面）；0.0.31 为 0.x 小版本，行为面小。fastapi 0.116.1（>=0.0.18）与 mcp 1.30.0（>=0.0.9）的约束均放行 0.0.31，可先于批次3 单独落地。 |
| 回归清单 | multipart 拒绝/正常上传/限流/坏 boundary；图像上传→visual_evidence 归一化、OCR（启用/未启用两态）、vision 预检 2MB/1280px、像素上限 4026/4024 错误路径。 |
| 回退 | pyproject 双 pin 改回 `==0.0.20`/`==11.3.0` 重装 venv；无数据迁移，回退无残留。 |

### 批次2：认证防御升级（单包，前提部分不成立）

| 项 | 内容 |
|---|---|
| 顺序 | ③ PyJWT 2.10.1→2.15.0 |
| 已发布证据 | GitHub release 2026-09-23 confirmed；2.15.0 覆盖全部 8 条（含 2.12.0/2.13.0/2.14.0 的累积项）。 |
| 实际入口条件 | `security.py:57` 单算法 `algorithms=[settings.jwt_algorithm]`（默认 HS256）+ 固定 secret；源码无 PyJWK/PyJWKClient/verify_signature=False。**mixed-alg、JWK x/d 混淆、JWKS 重定向 SSRF、raw-token 撤销绕过等公告前提在本项目当前不成立**，不得按"现有认证可伪造"表述；unknown `crit` 头等与算法无关项仍须逐条核对正文。mcp 的 `pyjwt[crypto]` 引用会引入 crypto extra，实施卡核对安装面变化。 |
| 回归清单 | 签发/校验、过期、jti 查库撤销、角色鉴权、MCP 授权链、异常/畸形 JWT 拒绝路径全量回归。 |
| 回退 | pin 改回 `==2.10.1` 重装；已签发 HS256 token 算法不变，无迁移。 |

### 批次3：FastAPI/Starlette 联合升级（最大 scope，独立批次）

| 项 | 内容 |
|---|---|
| 顺序 | ④ fastapi 0.116.1→0.143.0 + starlette 0.47.3→1.3.1（+ 2.3 节新增依赖） |
| 已发布证据 | fastapi 0.143.0（2026-10-08）、starlette 1.3.1（2026-06-12）均 GitHub confirmed；starlette 1.3.1 覆盖其 5 条（0.49.1/1.0.1/1.1.0/1.3.1 累积）。 |
| 为何必须联合 | 当前 fastapi 钉 `starlette<0.48.0`，0.47.3 的任何补丁版本（最低 0.49.1）都装不上——**starlette 无可独立落地的补丁**，这是唯一的修复路径。 |
| 实际入口条件 | Range DoS（FileResponse）、UNC SSRF（StaticFiles）、getattr 任意方法（HTTPEndpoint）在 backend/app 无直接调用点（全源码搜索无 FileResponse/StaticFiles/HTTPEndpoint），当前直接可达性未证实；form limits 广播缺失（GHSA-82w8）与上传路径同链，与批次1 互补。 |
| 兼容性风险 | pydantic 2.11.7 满足 >=2.9.0；Python 3.12.14 满足 >=3.10。新增 3 个运行时依赖 + extra 变化（见 2.3）。starlette 0.47→1.3 跨三个 minor 线，中间行为变更面最大的一批。 |
| 回归清单 | 全 API 契约回归（重点表单/上传/鉴权依赖注入/异常处理）、MCP SSE（sse-starlette 3.0.3 与 starlette 1.3 的相容须实测）、OpenAPI 文档生成、启动/关闭生命周期。 |
| 回退 | pyproject 改回原 pin 整体重装；先在分支/临时 venv 验证，不动现有 venv。 |

### 批次4：前端 lock 级补丁（生产条件未证实，防御性）

| 项 | 内容 |
|---|---|
| 顺序 | ⑤ next 15.5.25→15.5.27；⑥ sharp 0.35.4→0.35.5；⑦ source-map-js 1.2.1→1.2.2；⑧ 内嵌 postcss 8.4.31（随⑤） |
| 已发布证据 | 三者 GitHub confirmed（2026-09-30/09-27/09-30）；15.5.27 落实了原 API 的 15.5.? 占位。 |
| 实际入口条件 | next 两条 medium 均为自托管 SSG/ISR 缓存投毒，前提是 Pages Router SSG/ISR 或根 catch-all；本项目 App Router（src/app）静态核查**无** generateStaticParams、`export const revalidate`、`[...slug]` catch-all，前提未证实。sharp 的 librsvg 缺陷需 SVG 栅格入口：src 中无 `next/image`/`<Image` 使用，next.config.mjs 无 images 配置，未证实可达。source-map-js 是构建期本地输入。 |
| 兼容性风险 | sharp 0.35.5 在 next optional 范围 `^0.34.3 \|\| ^0.35.4` 内，lock bump 即可；next 同 minor 补丁；source-map-js 1.2.2 满足两处 `^1.x` 范围。内嵌 postcss 是否随 15.5.27 移动未知（见 2.1），实施后以 lock 复核。 |
| 回归清单 | `next build`、登录后核心页面冒烟、rewrites `/backend` 代理、E2E 脚本（NEXT_DIST_DIR 隔离路径不受影响）。 |
| 回退 | package-lock 还原（git checkout lock + 重装 node_modules）；无数据面。 |

### 批次5：开发/构建工具链（跟踪类，不阻塞生产）

| 项 | 内容 |
|---|---|
| ⑨ postcss-selector-parser 6.1.4→7.1.6 | 跨 major 被 tailwindcss/postcss-nested 6.x 约束锁死，**不能强装**；等上游放宽或随 tailwind 大版本评估。入口（本地 CSS）不可达，暂以"已知未修、低可达"挂账。 |
| ⑩ braces 3.0.3 | 公告无 patched 字段，**无已知修复版本，不得编造**；chokidar/micromatch 均为 dev 依赖（tailwind watcher/本地 glob），输入是本地文件路径，非远程攻击面。挂账跟踪上游。 |
| ⑪ pytest 8.4.2→9.0.3 | 跨 major，且 **pytest-asyncio 1.1.0 钉 `pytest<9`，须联动升级 pytest-asyncio**，否则解析冲突；dev 面，回归=测试套件本身。 |
| ⑫ pip 25.0.1→26.2 | 按 PyPI 规范化写 **26.2**（不宣称 GitHub 26.2.0 release 存在）；修复 25.3/26.0/26.1/26.1.2/26.2 累积 6 条。属安装期供应链风险，非 HTTP 运行面；**不在现有 venv 擅自升级**，随实施卡用临时环境验证。 |
| ⑬ Mako 1.4.1→1.4.2 | alembic 传递；Windows 盘符路径遍历前提是 TemplateLookup 接收不可信模板名，alembic 用内置模板，未证实可达。PyPI confirmed，requires_python>=3.10 与 3.12.14 相容（声明面）。随 alembic/迁移实施卡顺带升。 |

## 4. 覆盖边界（约 244 的含义）

- 244 = 108 个 Python 安装分发 + 137 条 npm lock 条目去重后的包/版本对，逐包 `affects=name@version` 查询，244 成功 0 失败。它覆盖**本地声明/lock/venv 安装元数据**这一层。
- 未命中的 231 个包/版本仅表示 reviewed 库该版本无命中：**不等于安全**、不等于无未审阅公告、不等于无平台层 CVE。React 19.0.0、MCP 1.30.0、FastAPI 0.116.1、pydantic 等本次无命中，但维护方原始库（react 8 条、python-sdk 12 条、fastapi 1 条等）与 reviewed 口径的差异仍须在后续复查，不得反推"全部安全"。
- 不在覆盖内：Docker/部署镜像实际安装版本；sharp/librsvg 等原生二进制库；系统级依赖；npm 侧只查 lock 不查运行镜像；`docs/evidence` 之外的其他环境。

## 5. 未验证项（终审/实施卡必读）

1. next 15.5.27 的内嵌 postcss 版本——当前证据不含，决定⑧是否随⑤闭合。
2. braces 上游是否计划发布补丁——公告无 patched 字段，持续跟踪，不设期限承诺。
3. starlette 1.3.1 + fastapi 0.143.0 + sse-starlette 3.0.3 组合的实测相容性——声明相容≠回归通过。
4. fastapi standard extra（fastar/fastapi-cli/pydantic-extra-types/opentelemetry）在本项目的实际安装面。
5. 部署镜像安装版本与部署启用方式（MCP extra 是否在生产启用）。
6. 所有批次的升级后回归均未执行（本文档阶段禁止安装/启动）。
7. Python 3.12 / Node 22 与各候选的运行支持范围在实施卡最后核对。
8. 预算 PG 与两条真实硬停门槛仍未完成（Docker 不可用）——**依赖排序不等于 OPS 全目标完成**，不得冒称。

## 6. 自审记录

- 13 包、51 条公告数与 coverage-20261009.md 完全一致；候选 13 项发布状态逐条取自 candidate-releases JSON，Mako/pip 按 PyPI 补证口径表述（26.2 规范化、GitHub 未确认不宣称）。
- 未编造任何修复版本：braces 明确写"无已知补丁"；selector-parser 7.1.6 标注跨 major 且被 6.x 约束锁死；starlette 标注无可独立落地补丁。
- 版本命中一律未表述为"可利用"：next/sharp/starlette(文件类)/Mako/内嵌 postcss 均写明入口前提与核查结论（当前未证实可达或不可达项分明）；python-multipart/Pillow 写明真实入口存在。
- 未安装、未启动、未联网补搜（未做全网重复搜索）、未改生产源码、未动 venv；本文是本任务唯一写入文件。
- 快照（dc40951）与当前 HEAD（12501ba）差异仅为 docs 提交，已在 §0 说明。
