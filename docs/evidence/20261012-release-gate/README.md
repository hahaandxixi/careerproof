# 首版交付线检查（进行中）

2026-10-12；起点HEAD `6c1b784`，范围为当前工作树。门槛与开放问题只在[任务清单](../../任务清单.md)维护。本批推进G1用户定位、G3权限与快照、G4可重复演示、G5问题分级；不签收整个网站。

## 可审计证据

- `core-risk-tests.raw.out`：升级解释器46专项通过、5个警告。投递、重投、通知、成长与历史专项；PG用独立cp_test schema，岗位夹具使用临时SQLite，不能称全量PG。
- `http-chain-first.json`、`http-chain-repeat.json`、`http-chain-one-command.json`：三次新隔离run通过真实HTTP、真实解析与持久化闭环。同意/幂等、跨角色、具名问题、通知/下载、新版三项对比、原投递不变、撤回后旧链接拒绝、新投递不继承回复；A/B/A2原三个快照不变。
- `one-command-demo.raw.out`：既有Start-E2E入口、生产构建及HTTP链通过。`http-smoke-first.raw.out`保留apiBaseUrl格式假设错误的预检失败，未重复业务写入。
- `smoke-safety-prepare.raw.out`：此前20安全测试；`smoke-safety-owner.raw.out`：独立学生与凭据不覆盖边界加入后22通过；最新Ruff现场通过。
- `runtime-resume.raw.out`：PG退出导致恢复失败；Docker Engine29.2.0正常，原容器Exited255。恢复原容器后 `runtime-resume-after-pg.raw.out`暴露第二个缺口：原夹具学生新增投递导致严格夹具核对拒绝。没有绕过守卫、重新播种或删除业务记录。
- `owner-chain.raw.out`：改用独立合成学生后的第四次新run HTTP链通过。停止后恢复能力以追加检查点为准，不能由首次启动推断。

## 改动与边界

`backend/evals/release_smoke.py`把上传、报告、补证、新报告、企业查看、撤回重投变为一次性新run。强制8001/3001、同名cp_e2e库、专属storage、Mock/外发关闭，核对真实PID与开始时间。已有结果用CreateNew拒绝覆盖，失败保留进度，凭据仅存gitignored本机目录。

恢复实验发现的缺陷已修：新注册独立合成学生承载HTTP链；企业和越权探针复用种子角色，种子学生原投递集合不新增、不改写。前三次链只证明旧实现的HTTP范围；`release-owner-20261012`证明新实现，分别留档。`owner-stop.raw.out`与 `owner-resume.raw.out`证明实际停止/SkipSeed恢复成功；`owner-recovery-integrity.json`只读再确认A/B/A2三快照不变。

`student-ui-chain.json`记录实际390px学生页面操作：从SQL缺口创建任务，上传具名第3版、解析、明确保存选中版本，未勾选外发授权，Enter发起本地规则新报告，三项变化可解释，刷新后内容一致。SQL从未评级到2/5并保留运行/贡献待核验；Python/pytest等级不变，展示引用变化。截图见 `student-sql-comparison-390.jpg`；`student-applications-after-ui.md`显示原有效投递仍指向第2版报告、第1版已撤回。基准先由HTTP准备，不冒充从全新账号开始的完整UI首验。

最新企业页面复验、首次用户独立走查和真实AI语义仍未完成。2026-10-13核对系统已在09:41重启，当前验收服务与Docker离线；这是本次离线的直接现场事实，不能反推前一次服务退出根因。

## 独立审查与状态

[ZCode45原调查](../20261012-release-usability-audit/audit.md)列5项，标题误写4项；仅静态调查。Codex取舍：F1是首次Demo报告准备负担，文档已声明前提，不升级为确认P1矛盾；F2已改为当前用户交付目标；F3有效投递徽标为P2；F4永久加载尚未复现；F5摘要replace目前匹配，保留维护建议。没有发现P0不能证明所有安全问题均不存在。

2026-10-13用户把Trae换为DeepSeek Harness；已核对桌面快捷方式和运行中的Harness、Flash High模型，用户添加工作区。46号只读审查卡待空闲时段发送，09:48处于用户指定高峰，不发模型请求。ZCode使用智谱，周用量授权改为90%；两执行端与网站AI调用分别记录，最终集成由Codex验收。

既有未提交guard/launcher与用户空白行保留，不随本批暂存。无远端推送、部署或邮件发送。
