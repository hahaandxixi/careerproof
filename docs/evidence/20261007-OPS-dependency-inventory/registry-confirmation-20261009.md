# 官方包仓库补证

2026-10-09通过只读web工具读取官方PyPI版本JSON：

- [Mako1.4.2](https://pypi.org/pypi/Mako/1.4.2/json)：info.version=1.4.2，requires_python>=3.10，yanked=false；wheel上传2026-09-22T20:40:56.423830Z。GitHub Release未找到不代表未发布。
- [pip26.2](https://pypi.org/pypi/pip/26.2.0/json)：请求26.2.0规范化返回info.version=26.2，requires_python>=3.10，yanked=false；wheel上传2026-07-29T21:57:54.763549Z。应按PyPI规范版本写26.2，不宣称GitHub26.2.0 Release存在。

候选源码FastAPI0.143.0要求starlette>=0.46.0、pydantic>=2.9.0、typing-extensions>=4.8.0、typing-inspection>=0.4.2、annotated-doc>=0.0.2、opentelemetry-api>=1.44.0。相比当前FastAPI0.116.1，联合升级会引入/提高依赖；声明相容不等于回归已通过。

当前前端lock父依赖核查：Next锁定其postcss8.4.31，root另有dev postcss^8.4.49；升级root postcss不能自动移除Next内嵌旧版本。postcss-selector-parser来自tailwindcss/postcss-nested的6.x约束，不能直接强行跨7.x。sharp来自Next optional ^0.34.3||^0.35.4；source-map-js来自两个postcss；braces来自chokidar/micromatch，公告未给补丁版本。

本地默认Node/Python运行支持范围仍须在升级实施卡核对。没有安装候选包或跑升级后回归。所有升级排序应明确分批和失败退回方式，不能运行npm audit fix --force或强改传递major版本。
