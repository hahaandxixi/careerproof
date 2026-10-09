# 维护方公告核对第一批

2026-10-09，本地安装快照HEAD dc40951：`local-inventory-20261009.json`，108项Python分发元数据及前端lock/安装版本。只读GitHub官方CLI抓取8个维护方仓库152条公开公告，完整API原文见`official-advisories-20261009.json`。所有8次请求成功；采集器Ruff通过。没有安装、升级、业务数据库或部署操作。

这不是所有依赖的最终安全审计。版本区间、补丁字段与正文可能不一致，不能只按严重程度或粗略区间自动推荐版本；尚须全量依赖匹配与候选发布/兼容性核对。

## 有代码证据的初步排序

| 顺序 | 当前依赖与证据 | 下一动作与边界 |
| --- | --- | --- |
| 优先 | python-multipart 0.0.20；FastAPI portfolio上传路由使用File/Form/UploadFile，真实解析路径存在。维护方[不受限part header](https://github.com/Kludex/python-multipart/security/advisories/GHSA-pp6c-gr5w-3c5g)范围<0.0.27；[大preamble/epilogue](https://github.com/Kludex/python-multipart/security/advisories/GHSA-mj87-hwqh-73pj)范围<0.0.26 | 不能只凭应用上传后大小校验排除解析阶段风险。先核对全部9条公告，再选择同时修复相关问题的已发布候选；0.0.27只修复其中一项，不代表最新安全目标。需multipart拒绝/上传/限流回归。 |
| 优先 | Pillow 11.3.0；visual_evidence.safe_png用Image.open(BytesIO(raw))且未限制formats；外层只校验用户文件扩展名。[PSD加载越界写公告](https://github.com/python-pillow/Pillow/security/advisories/GHSA-cfh3-3jmp-rvhc)说明>=10.3.0受影响，并建议formats白名单 | 扩展名和像素检查在Image.open之后，不能证明未加载伪装PSD。升级候选须合并20条公告及实际发布核对；格式白名单防护可以单独列修复卡，不在本轮暗中改生产源码。 |
| 联动评估 | Starlette 0.47.3落在[FileResponse Range DoS](https://github.com/Kludex/starlette/security/advisories/GHSA-7f5h-v6xp-fcq8)的>=0.39.0,<=0.49.0区间，补丁0.49.1；全backend/app源码搜索无FileResponse/StaticFiles/HTTPEndpoint直接调用 | 此项当前直接可达性未确认，不能称已被利用或全站可触发。其它新公告仍须逐条看form/URL路径。FastAPI 0.116.1元数据要求starlette>=0.40.0,<0.48.0；不可单独强装0.49.1或1.x来制造依赖冲突，需框架联合升级与契约回归。 |
| 联动评估 | PyJWT 2.10.1；security.py固定单算法列表及settings.jwt_secret，默认HS256；源码未找到PyJWK/PyJWKClient/verify_signature=False直接路径 | 23条公告中混合算法/JWK特定前提不得当作现有认证可伪造。继续核对未知crit、异常头/撤销语义、候选版本；认证过期/撤销/角色/MCP授权回归不可省略。 |
| 待区间核对 | Next15.5.25、React19.0.0、MCP1.30.0、FastAPI0.116.1的维护方原始记录已取 | 有些Next公告使用15.5.?占位补丁或宽泛范围；必须看正文与已发布修复分支，不能机械判断全部15.x漏洞命中，或因已修旧RCE就声称全部安全。 |

## 接续要求

继续全量本地直接/传递依赖公告匹配，明确已覆盖/未覆盖清单；确认每个升级候选实际发布、Python/React/FastAPI约束与回归范围，形成最终排序。部署镜像安装版本未验证。当前预算PG及两链真实硬停门槛仍因Docker不可用未完成，依赖前置核对不替代这些要求。agent-reach check-update实测v1.5.0最新，无工具升级。
