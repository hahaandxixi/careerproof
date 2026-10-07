# OPS依赖版本盘点（公告审计前置）

2026-10-07。采集时HEAD `8659b90`。这一目录只保存本地声明、lock和安装元数据；OPS主匹配、共用日预留与跨午夜仍须继续完成，再做当前权威公告核对和升级排序。未调用网站模型、网络、数据库、包安装或部署。

在项目Git根执行：

```powershell
& './backend/.venv/Scripts/python.exe' 'docs/evidence/20261007-OPS-dependency-inventory/collect_inventory.py'
& './backend/.venv/Scripts/ruff.exe' check 'docs/evidence/20261007-OPS-dependency-inventory/collect_inventory.py'
```

首次两个命令退出码0；采集108项Python安装分发元数据，Ruff通过。完整内容见[local-inventory.json](local-inventory.json)。采集器随后补入拒绝覆盖保护；已有快照时指定`--output local-inventory-下一批次.json`另存，默认文件存在会拒绝，不把不同HEAD的结果混成同一现场。采集器只读取三份manifest和安装包元数据，不导入被检查依赖，不读取.env、存储业务文件或数据库。

| 本地依赖 | 安装版本 | 结论范围 |
| --- | --- | --- |
| FastAPI / Starlette | 0.116.1 / 0.47.3 | 仅本地venv元数据 |
| PyJWT / python-multipart | 2.10.1 / 0.0.20 | 仅本地venv元数据 |
| Pillow | 11.3.0 | 仅本地venv元数据 |
| MCP / sse-starlette | 1.30.0 / 3.0.3 | 本地已安装，不等于部署启用所有可选功能 |
| Next.js | 15.5.25 | package-lock与本地node_modules一致，声明为^15.5.25 |
| React / React DOM | 19.0.0 / 19.0.0 | 声明、lock与本地安装一致 |

仍未验证：官方当前公告与实际受影响区间、Docker/部署镜像安装版本、升级候选兼容性及升级后回归。历史Bug清单中的“应升级”不能代替新公告核对；声明版本、lock版本、venv版本和实际部署版本分别记录。最终审计须链接维护者公告/发布说明，区分已修复与仍受影响、直接与传递依赖、适用功能及验证方法，再决定升级次序。当前没有“依赖全部安全”或“升级已完成”的结论。
