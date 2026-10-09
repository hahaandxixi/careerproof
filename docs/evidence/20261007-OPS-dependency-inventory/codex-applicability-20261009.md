# Codex独立适用性检查

2026-10-09，HEAD12501ba之后没有修改生产源码/manifest/lock。

- `backend/.venv/Scripts/python.exe -m pip check`实测退出0：No broken requirements found。这是现有venv一致性，不证明升级组合可安装或已通过回归。
- 当前pytest-asyncio1.1.0安装元数据明确要求pytest>=8.2,<9；候选pytest9.0.3不能单独安装，测试工具批次必须同时选择支持9.x的插件或保留受控替代措施。MCP1.30.0在当前Python3.12要求starlette>=0.27、pyjwt[crypto]>=2.10.1；它不消除FastAPI旧版本的<0.48约束。
- `jianli/src`文件清单未找到Pages Router目录、root catch-all（`...`）或middleware文件；源码搜索无next/image、dangerouslyAllowSVG、remotePatterns、ImageResponse调用或自定义配置。当前Next两条SSG/ISR cache公告的必要场景未从应用源码确认。不是对部署额外路由的绝对排除。
- 实际已安装Next image-optimizer.js:1024在SVG且dangerouslyAllowSVG为false时拒绝该类型，next.config.mjs没有开启此选项。sharp的librsvg公告不得直接当作站点当前开放的任意SVG上传漏洞；仍需考虑其它consumer/部署设置，推荐可兼容补丁而非忽略版本命中。
- backend/app静态搜索无TemplateLookup调用。Mako属于Alembic模板工具链，Windows驱动器路径模板URI公告应排迁移/构建级，不称已有生产HTTP入口。
- Next自己的postcss8.4.31与root/dev PostCSS分开；selector-parser来自tailwindcss/postcss-nested的6.x范围；不得把升级root工具链宣称清除所有Next依赖。
- JWT默认HS256单算法+固定secret；refresh使用payload jti_hash撤销，不按原始token字节撤销。JWK/混合算法/raw-token前提未见当前路径；未知crit处理仍需防御回归，不能从局部无前提推导全部PyJWT公告均不适用。
- Pillow Image.open未限定formats，上传外层扩展名不构成实际decoder格式白名单；这一点与维护方PSD公告建议一致，风险级应高于只在受控CSS构建触发的工具问题。

以上为静态调用/当前安装代码与命令证据，不是攻击实测。当前部署镜像、对外代理/限额、运行时额外配置未验证。最终排序应保留这些限定，且不能说已经安装补丁或完成预算PG门槛。
