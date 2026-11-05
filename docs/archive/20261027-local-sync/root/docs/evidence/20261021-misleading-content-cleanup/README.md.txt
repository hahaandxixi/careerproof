# 文档与历史探针清理（2026-10-21）

范围：评审包筛选器、保留指南、演示材料入口，以及三个旧浏览器探针。不是全仓库所有代码和历史记录均已审计的结论。

## 已处理

- `scripts/build_source_package.py` 精确排除 `backend/evals/demo-zhipu-20260916-run1`、`demo-zhipu-v3-run1`、`demo-zhipu-v4-20260916-run1` 的 `.md` 和 `.json` 共六份历史输出；原件保留在仓库，不排除所有 eval Markdown、运行器或冻结夹具。扫描未发现当前 backend/scripts/demo 调用它们的依赖。
- `demo/README.md` 将三套岗位场景设为体验入口，九职业材料明确为专项回归，不再暗示文件存在就意味着已导入。
- `demo/market-scenarios/README.md` 修正“尚未导入/加载正常站”的过时描述，按10月19日已有验收记录说明，并明确新环境仍需初始化；片段材料不代表完整业务实现或运行证据。
- `docs/guides/使用与启动.md` 去除作者本机盘符。原有未提交账号说明原样保留。
- 三个未跟踪的一次性探针从 `scripts/e2e/` 移至忽略目录 `backend/.tmp/retired-probes-20261021/`：`student-debug-jobform.mjs`、`student-keyprobe.mjs`、`student-task-probe.mjs`。原脚本写死旧日期、端口或绝对路径；仅在历史记录中发现名称引用，无当前运行入口引用。未执行脚本。`manifest.json` 保存原路径和SHA256，归档后逐项哈希一致。需要恢复历史调查时可按清单移回；归档副本不作为当前可运行工具。

## 验证

- 当前锁定环境运行 `python -m pytest app/tests/test_source_package.py -q -p no:cacheprovider --basetemp=.tmp/cleanup-package-20261021`：23通过。
- 新增实际临时Git仓库/ZIP回归：六份历史输出不入包，eval说明、运行器和合成JSON仍保留，仓库历史原件不删除。
- 当前工作树中已跟踪文件按新导出规则检查：831文件、20份导航文档，本地文件/目录链接通过；六份旧输出导出数0。不检查外部URL或锚点。

## 保留边界

未修改旧r7/r8 ZIP，未声称它们已获得此次清理；正式包必须从包含本次修改的提交重新生成。此次未提交或推送。

未改Agent页面及后端待集成修改、JobDetailView/match-readiness、完整报名项目、历史模型原文、claim、P2或正常站。没有把未跟踪证据、Mock测试和有意缺陷夹具当垃圾删除。历史任务/验收记录保留，文档清理不改变人工0/3或真实Agent验收状态。
