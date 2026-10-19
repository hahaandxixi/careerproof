# 82号剩余修复与正常站接入

本批接续502c110的迁移事故处置。不是再次执行81号，不调用网站外部模型。

## 实际结果

- 正常库新增3个原创体验岗位，企业“职证场景实验室（虚构）”，配套6份真实下载文件。
- 从发现及推荐候选中收起9个原目录演示岗位：保留published状态、原ID和全部原要求。不是关闭、删除或撤销投递。
- 原36个岗位均保留，逐字段核对仅允许9条的is_demo/discovery_visible/updated_at变化；其他旧岗位完全一致。
- 正常库仅enterprises、enterprise_memberships、jobs、job_requirements四张表按计划变化；报告、投递、快照、通知及其他表摘要不变。原始对照为normal-before/after.json。
- 第二次导入后全部39张表摘要与岗位记录均不变（normal-replay.json）。首次导入记录及9个旧ID见normal-apply-result.json。
- 默认列表实际4条：3条新样例＋另一企业原有的1条岗位。该岗位不属于已确认旧目录归属，保留，未擅自按“合成”字样全库隐藏。

## 修复范围与判断

1. 导入器分离新企业与旧企业。只接受各企业唯一有效OWNER且用户有效、角色为enterprise/admin；旧新企业须同一确认owner。重复同名、非样例同名、被修改样例均拒绝覆盖。
2. 旧岗位须同时匹配显式企业、owner、公司、原目录标题、分类、完整要求及原描述；未知来源保留。没有模糊标题筛选、全库清扫或status改写。
3. PostgreSQL锁企业行，固定顺序；演示准备另锁owner，防并发创建重复企业。重跑保留已有岗位状态、要求、显隐与时间戳。
4. CLI不读取app默认连接，必须显式指定database-url；无URL只输出无库计划。计划在PG使用SET TRANSACTION READ ONLY、SQLite使用PRAGMA query_only。
5. 显式Start-Demo流程准备3套新场景，不再创建批量旧目录；普通Start-Local不播种。摘要纳入导入器和目录文件，防代码/目录已更新却沿用旧播种标记。
6. 详情只为isDemo且公司与标题精确对应的3个样例显示配套下载；正常企业岗位不混入材料。样例使用“可体验”，集中披露虚构边界；不自动上传、评分或投递。

## 验证

- `pytest app/tests/test_job_discovery_curation.py app/tests/test_jobs_api.py -q --basetemp=.tmp/task82-final-tests -p no:cacheprovider`：18 passed；5条既有PyMuPDF弃用警告。覆盖新旧企业分离、来源拒绝、重复标题、无效owner、计划只读、旧ID、分页/推荐、首次准备及重跑。
- 在独立临时副本加入“重跑重新发布”突变：关闭态回归失败（closed-republish-mutant.raw.out），共享源码未改坏。正常源码同例通过。
- 专属55438 PostgreSQL：完整迁移到head，两次并发首次准备分别创建3/0条，仅1家新企业；关闭/隐藏一条后重跑，状态及时间戳保持。pg_curation_check.py及pg-curation-result.json。验证后核对完整容器ID与owner标签，停止并移除该一次性容器，正常PG保留。
- 前端相关5个测试文件49 passed（frontend-final.raw.out）；生产tsc exit0；7个后端目标文件Ruff通过，前端目标lint0/0。初次新增测试的Next lint module命名错误已修，原失败日志lint.raw.out保留。
- Next最终构建exit0（build-final.raw.out）。初次构建本身成功，外围终端打印构建日志遭GBK编码错误；最终UTF-8构建与日志重新确认。
- 真正日常入口`Start-Local.cmd -CheckOnly`成功；运行目录backend/.tmp/dep-frontend-20261019-task82，物理复用已安装依赖，无安装。最终BUILD_ID=h_rjDP5FogJFaYdhNlMMH，正常3000/8000已恢复。
- 实际IAB正常页面：1280与390列表、390详情无整页横向溢出；材料下载链接与匹配版本选择共存；Tab从简历下载到项目下载。截图与ui-check.json。
- 真实HTTP发现总数4，3条样例，9条隐藏岗位原ID全部200且仍published；6份材料下载200及SHA256匹配（http-check.json）。

## 限制

本轮没有再次上传这3套材料、生成新报告、投递或调用模型，也不是首次独立用户验收。没有把这一批目标检查称为全站/最终候选回归；77的hidden/reduced-motion/断线验收、人工语义评分与交付物冻结仍按原待办。

首次pytest使用系统Temp遇既有ACL拒绝，改用本批独占basetemp及关闭共享cache，不改ACL。另一次时间戳断言因SQLite往返后丢时区失败，测试先refresh统一持久化视图后通过；未改生产时间戳行为。
