# PRODUCT-01生产接入前预检

2026-10-06。前端尚由个人GLM-5.3独占修改，此文件不证明生产启动或页面通过。

- 再次Get-Process核对原manifest PID188716/192980均不存在，先复制原清单为prior-closure-processes.json。
- 按原已审查Stop-E2E执行，未发现需终止的自有进程，仅清除过期运行记录；数据库、存储、数据卷保留。原始closure-stale-manifest-stop.raw.out。
- 强制E2E_DATABASE_URL为回环cp_e2e_closure-20261005，执行Start-E2E -CheckOnly，EXIT0；8001/3001空闲，隔离存储在backend/.tmp，未创建/迁移/构建/启动。原始closure-start-preflight.raw.out。
- closure实际数据库已0015，迁移阶段证据已提交d760726；新接入仍需前端最终哈希/独立探针与类型门禁通过。不能使用旧.next-e2e构建冒充新功能页面。

下一步：ZCode交棒后Codex检查最终源码及11项独立探针，再顺序生产构建与Start-E2E -SkipSeed（验证现有合成夹具，保留旧投递）；真实页面按既有矩阵执行。
