# 新升级环境实际启动检查点

2026-10-10，依赖58b728b，启动guard a873097。实际执行Start-E2E -RunId upgrade-20261010 -BackendVenv .venv-dependency23 -FrontendStage dep-frontend-20261010。E2E_DATABASE_URL由现有loopback配置替换成专属cp_e2e_upgrade-20261010，不打印连接凭据，不改.env。

startup.raw.out保存真实建库、Alembic base→0017、合成seed、独立Next .next-e2e生产构建和服务启动原文；生成next-env/tsconfig改变恢复为stage原字节。旧数据库/旧投递与原node_modules未写入。本轮创建的新库/存储/进程属于该RunId，继续用于后续页面测试，不重复seed或重启。

actual-startup-baseline.json核对：backend PID存活且创建时间匹配manifest，专属数据库head=0017_ai_shared_budget；后端/api/v1/health与新前端/login均200；真实runtime包括FastAPI0.143/Starlette1.3.1/Mako1.4.2及Next15.5.27/内嵌PostCSS8.5.28/105源文件摘要。初始3份Application.report_snapshot canonical SHA256保存，后续新报告/撤回/通知前后逐项比对，不用仅页面文字声称固定快照不变。

运行：8001/3001、backend/.tmp/e2e-storage/upgrade-20261010、强制aiProvider=mock/aiExternalEnabled=false/Next遥测关闭，凭据只在忽略的backend/.tmp/e2e/upgrade-20261010.json。停止只用此RunId的Stop-E2E，经PID/创建时间检查，不终止其他服务。

尚未验收：学生新版补证/生成新报告/三种变化归因、企业核验/撤回/通知、390px和预算显示。现核验服务生产_runtime要求DeepSeek+外发启用，Mock服务下核验生成受保护；后续需明确合成MockTransport测试适配方案，不能为页面验收打开真实外发或冒称实际模型调用。不要复用旧runner硬编码历史evidence/state.json，否则会覆盖旧证据；新run须独立证据和状态。

AI质量评测仍只有旧14例基线及协议，三维实现/holdout复核与P2决策未完成。整个目标保持进行中。
