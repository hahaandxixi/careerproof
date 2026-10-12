# 撤回后重新投递修复验收

2026-10-12。Codex 执行本次有界修复；未声称委派 ZCode。原实现同时通过服务规则和 `(job_id, student_id)` 全历史唯一约束禁止再次投递；现在明确授权后新建投递，保留旧编号、快照、回复、授权时间和事件，不恢复旧企业权限。

## 实现

- 0018 将全历史唯一约束替换为非 withdrawn 记录的部分唯一索引；同岗位同时只有一份有效投递。创建只查询有效记录，同报告重复提交复用有效编号；另一份报告必须先撤回。所有重新投递仍计入24小时20次限制。
- 学生列表提供“重新确认授权并投递”链接，定位报告页授权区；授权勾选默认关闭。可分享同报告或新版报告，新投递从 submitted 开始，不继承旧企业回复。
- 迁移不改数据行。已存在重复历史记录时降级明确拒绝，不删除记录以迎合旧约束。SQLite foreign_keys 开启时拒绝 batch 重建，避免连带删除事件；正常迁移连接使用默认关闭设置，运行时外键保持原配置。

## 自动验证

升级解释器 `backend/.venv-dependency23/Scripts/python.exe`，后端 cwd 为 backend。

```text
python -m pytest app/tests/test_application_resubmission.py -q -p no:cacheprovider --basetemp=.tmp-resubmit-red-20261012
python -m pytest app/tests/test_application_resubmission.py app/tests/test_application_reconsent_migration.py app/tests/test_applications_api.py app/tests/test_notifications.py -q -p no:cacheprovider --basetemp=.tmp-resubmit-sqlite2-20261012
python -m pytest app/tests/test_application_resubmission.py app/tests/test_application_reconsent_migration.py app/tests/test_applications_api.py app/tests/test_notifications.py app/tests/test_application_verification.py app/tests/test_evidence_growth.py -q -p no:cacheprovider --basetemp=.tmp-resubmit-pg-20261012
npm test  (cwd jianli)
```

- 原代码红测2失败/1 PG跳过，确实复现同报告及新版报告再次投递返回409；首轮默认临时目录权限错误另留日志，修正为自有 .tmp-* 后再复现。
- SQLite18通过/4 PG跳过；PG74通过/0跳过。PG用现有 loopback 连接参数，但只在各夹具随机自有 cp_test schema 建表、改表和清理，不触及 public 数据。自动禁用外部模型。
- 覆盖同/新报告重新投递、明确同意、旧快照/回复/授权时间/版本不变、旧通知/报告/下载/回复失效、重复旧撤回不影响新编号、四路并发仅一条有效记录、关闭岗位与次数限制、SQLite/PG迁移往返和拒绝破坏性降级。
- 现行前端215通过/0跳过；stage旧测试另193通过，后者不冒充现行215。Ruff通过。Start-Local实际生产构建含类型检查通过。

## 生产页面与实际服务

新合成 run `resubmit-20261012`，数据库 `cp_e2e_resubmit-20261012`、独立 storage、3001/8001、mock/外发关闭、升级stage `.next-e2e`。未改旧 question-chain 等运行。

学生在真实生产页面完成：个人投递 → 撤回A → 新入口 → 报告授权区（默认按钮禁用）→ 勾选同意 → 确认投递 → 列表同时显示新A已投递、旧A已撤回。390×844实测无横向溢出，保留入口。DOM和桌面/390截图存本目录。

独立只读SQL确认该学生岗位A恰好新旧两条，三份原种子快照哈希不变；实际企业登录接口确认旧编号404、旧通知目标404、列表只包含新A和另一学生的有效投递。核对结果见 independent-checks.json。验收后按自有进程清单停止新E2E服务，库/storage保留；演示学生的普通本地会话已恢复。

普通服务3000/8000已用 Start-Local 重建恢复，迁移0017→0018；applications/application_events/notifications迁移前后每行完整哈希及数量相同（daily-before.json、daily-after.json）。没有替用户重新授权任何历史投递，没有真实DeepSeek、邮件或远端推送。
