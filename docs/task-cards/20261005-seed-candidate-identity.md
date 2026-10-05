# SEED-02：合成报告身份与正式分析一致

2026-10-05；Git根 `D:\jbcode\web ai\jianli`。Codex核查当前seed以profile.id写candidate_ref，正式AnalysisService以user.id写candidateId，实际学生GET比较409。旧closure/audit数据、报告和投递快照必须保持原样。

ZCode负责简单夹具修复、回归与证据，Codex独立审查和提交。允许修改仅 `backend/evals/seed_e2e.py`、`backend/app/tests/test_e2e_fixture_safety.py`，新证据目录 `docs/evidence/20261005-seed-candidate-identity/`。其他产品/runner/文档只读；个人GLM任务另持有student runner，不要触碰。

先在现有临时SQLite/ASGI seed回归中真实复现：A/B/A2报告及其投递冻结candidateId必须等于对应账号User.id，profile.id应为不同身份且不可被当作候选人用户身份。保留红输出，再最小修正seed的新报告身份；不放宽compare_views或授权。保持profile存在校验及原材料/通知/幂等行为。

运行整个test_e2e_fixture_safety.py以及适用Ruff，保存命令/完整脱敏输出/退出码，自审diff并限一屏回报。不得改运行数据库、重跑现有seed、建库、迁移、重启服务、浏览器操作、真实模型、外部发送、Git提交/推送或P2stash。旧错误fixture不倒写；未来新run待Codex验收后启动。
