# 升级环境前端与解释器绑定检查

2026-10-10，Codex。依赖阶段58b728b；本次Start-E2E支持-BackendVenv .venv-dependency23以及-FrontendStage dep-frontend-20261010。Stage只允许backend/.tmp下本地目录名，拒绝路径穿越/reparse点，默认仍正式jianli。

前端验证器在任何数据库创建/迁移/起服务前核对：实际Next、Next-resolved PostCSS、sharp、source-map-js与该stage lock一致；stage package/lock与正式jianli一致；src全部文件和Next/PostCSS/Tailwind配置与正式源码一致（文本只规范化CRLF，不以构建生成的tsconfig/next-env差异误判源代码）。105个源/config文件hash摘要写入启动manifest，固定8001/3001、原PID/时间/存储guard保持。Next遥测明确关闭并恢复父进程原环境。

实际负例：正式主node_modules的旧Next拒绝；自身stage临时加入合成source-drift标记拒绝。只修改自身stage layout.tsx测试副本，finally恢复原字节，再正例通过；guard-summary.json/原始拒绝日志保存。未修改业务前端src或用户文件。

组合CheckOnly：新venv+新frontend stage通过，合成未连接的cp_e2e URL只用于解析，不创建数据库或启动服务。此预检不等于实际迁移、网页或企业核验通过。实际后续运行须使用新RunId/new cp_e2e库/独立存储；强制Mock/外发关闭、旧投递不改、P2暂停。

已核对源码guard和Startup参数传递、manifest、独立Next构建/恢复及自有PID检查。本有界启动准备签收后可按用户目标实际建立隔离新环境；其页面链路另记结果。ZCode当前个人五小时0%、每周60%、02:01:07恢复，未发送25，不等待配额而停止本地推进。
