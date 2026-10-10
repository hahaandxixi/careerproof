# 隔离运行恢复与当前证据核对

2026-10-11。现场8001/3001无监听、Docker引擎管道不存在；旧运行清单两PID247864/259056均已不存在，不能将昨日验收写成当前服务在线。

按用户约定，通过Computer Use在资源管理器的用户Desktop文件夹双击已存在的Docker Desktop快捷方式启动；Docker Server29.2.0确认。原backend-postgres-1容器处于Exited，先核对pgvector:pg17、Compose项目路径/服务/原5432映射，再启动原容器并确认pg_isready。

第一次恢复发生在PG未启动时，连接拒绝原文保留start.raw.out；数据库没有重建或重播种。清单两原PID消失后，仅清理原自有进程清单，备份previous-process-manifest.json。PG就绪后，Start-E2E复用question-chain-20261010、升级venv与frontend stage，SkipBuild/SkipSeed、强制MockTransport/外发关闭，不重新激活库存闸门、不修改旧记录。start-final.raw.out证明迁移当前head、验证原夹具及两服务就绪。

health.json使用正确/api/v1/health与前端/reports，均200；初探误用/health得到404，不能将其当成健康故障。独立SET TRANSACTION READ ONLY再审计chain-after-resume.json：新报告ID、已发回复SHA、attempt数量与之前一致；三原快照hash不变，岗位要求、材料与账户边界仍一致，见resume-integrity.json。没有新增分析或模型请求。

另核对三维评测基线sourceHashes与现行源文件、传智杯27manifest全部引用证据；current-quality-source-check.json保存逐文件结果。此核对不能替代传智杯28新runner的测试与独立风险验收，完整目标继续进行。
