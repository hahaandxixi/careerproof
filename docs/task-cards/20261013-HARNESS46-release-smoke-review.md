# 传智杯46：DeepSeek Harness 独立检查（避峰）

目标：G3权限与快照可靠、G4演示可复现。实际Git根 `D:\jbcode\web ai\jianli`；起点HEAD `6c1b784`，当前工作树有其他未提交改动。

只读 `backend/evals/release_smoke.py`、`backend/app/tests/test_release_smoke_safety.py`、`backend/evals/seed_e2e.py`、必要的API/配置定义与本轮非敏感证据 `docs/evidence/20261012-release-gate/`。不要全仓遍历，不读 `.env`、凭据、storage、个人资料或本地客户端数据库。

检查：隔离守卫是否先于HTTP写入；run/真实进程所有权；prepare与重复运行拒绝是否安全；生成/比较/撤回/重投断言是否真的覆盖目标；日志是否泄露。优先找能复现的缺陷，不改业务代码。

唯一写入 `docs/evidence/20261013-harness-release-review/`：`review.md`（等级、触发、引用、修复建议、未验证）、`source-hashes.json`。可在该目录准备纯合成反例；只跑不连接数据库/不启动服务的已有安全测试，保存完整原始输出。不得安装、真实网站模型调用、建库、迁移、操作业务库、停止服务、提交/推送、改其他文件或P2 stash。

模型使用Harness界面已选Flash；无需读取API密钥。高峰不发送，开始前核对北京时间和余额，只做一个有界审查，不无限/goal续跑跨入高峰。独立学生修正与原夹具SkipSeed恢复已通过；重点审查新版本真实覆盖及失败路径。完成后一屏回报G3/G4结论及证据路径，未执行的页面/真实模型检查标未验证。Codex终审，不修改你的证据文件。
