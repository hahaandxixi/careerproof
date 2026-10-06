# Docker恢复调查（2026-10-06）

范围：本机启动失败阻碍PRODUCT-01独立PG；不删除/重命名运行目录、配置或卷，不发送诊断包。

- 现场error：Inference manager移除dockerInference时系统无法访问，重解析文件Length0。只有实际套接字报错证据，不能据此诊断卷坏。
- 官方Docker文档确认desktop stop有--timeout；本机start --help也确认--timeout。本轮docker desktop stop --timeout 20已实际EXIT0，输出Stopping Docker Desktop；现在start --timeout 30运行，结果待观察。
- 公开docker/desktop-feedback #531/#527有相同AF_UNIX 1920报错及不同用户的恢复提议，但这是问题报告，不能当官方保证。特别是enableDockerAI在官方设置参考中对应Gordon，不能盲信论坛把它当Model Runner开关，不改该字段。

来源：
- https://docs.docker.com/reference/cli/docker/desktop/stop/
- https://docs.docker.com/desktop/settings-and-maintenance/settings/
- https://docs.docker.com/enterprise/security/hardened-desktop/settings-management/settings-reference/
- https://github.com/docker/desktop-feedback/issues/531
- https://github.com/docker/desktop-feedback/issues/527

检索遵循agent-reach/Exa，查询仅通用错误；首个沙箱DNS失败后同查询获得公开结果。没有外发本机用户名、日志、配置或凭据。完整启动成功仍需engine/PG端口及隔离测试，而非只看进程出现。
