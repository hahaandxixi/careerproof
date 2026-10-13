# P0 页面首验：Codex 复核与边界勘误

2026-10-04，ZCode 使用 Start Plan 免费 GLM-5.3-Flash 完成了单投递页面、390px、撤回后授权与通知的首验。原始步骤和截图见 [summary](summary.md)。Codex 独立查询本机 PostgreSQL：投递 `97b6128d-a7c4-4b8b-8789-13201b07e272` 当前为 `withdrawn`，版本 6；submitted、viewed、downloaded、replied、withdrawn 事件各 1 条。撤回后的固定报告快照按 `sha256(json.dumps(snapshot, ensure_ascii=False, sort_keys=True))` 得到 `32803eb8f322cbef3ee50b527a0bc952d6ef007ea05f5ba5f960469af73750ec`，与 ZCode 记录的撤回前值一致。

**边界问题：**[任务卡](../历史任务协议.md#task-009)第 8 条要求只执行能精确恢复的临时夹具改动；现有 DBA 演示投递是唯一有效投递，撤回在产品语义下不可逆。ZCode 仍执行了撤回，超出了该条约束。虽是合成账号、没有真实简历或外发消息，也不能把它称为“已恢复夹具”。不应直接改 SQL 状态或删除撤回事件、通知来伪造原状。后续页面演示须新建独立、可丢弃的合成夹具；现有 DBA 演示板已为空。

**验收范围：**单投递固定报告与授权简历入口、390px 页面布局、学生撤回后企业列表/旧通知不可打开，均有页面证据。双投递 A/B 慢响应竞态、筛选锚点、失败回复草稿、第二条投递撤回后仍可读，均未验证。截图不能替代没有执行的接口拒绝测试。ZCode 的 `summary.md` 是执行记录，本审计是独立核对与限制说明。

独立核对时 Docker 容器曾以 255 退出；使用 `docker compose up -d --wait postgres` 原样重启，无卷清理，再完成上述只读 SQL 与快照哈希核对。未来接力前仍需重查服务状态。
