# E2E-01 Codex 首轮隔离审查：待修正，尚未签收

本文件由Codex持有，2026-10-04只读检查现有seed_e2e.py取得。ZCode当前仍实施E2E-01；无需停止写入，但补强后再交棒。仍禁止实际建库、迁移或启动。

1. **HTTP目标错位**：guard_base_url只检查loopback，CLI仍可向8000业务后端注册/建岗位，再向cp_e2e库插入报告。生产CLI必须拒绝非8001、非`/api/v1`以及userinfo/query/fragment目标。端口白名单仍不足以证明该服务连接隔离库：实际seed前应核对独立启动清单的自有PID/启动时间/运行ID、目标数据库与存储、强制Mock配置；未取得清单证明即拒绝。测试可使用ASGI注入，但不得弱化实际CLI守卫。
2. **数据库URL覆盖**：URL query/fragment可能改变连接参数，守卫应拒绝；同时seeding也要求数据库名与`cp_e2e_<run-id>`一致，而不是只有create_database核对。口令允许安全编码，不输出连接串。
3. **引用准确性**：RESUME_TEXT技能声明在第3行，_evidence_snapshot目前写第1行。校正并用实际文件内容验证引用范围与snippet一致，不能只测试存在citationId。
4. **后续夹具范围补全**：允许扩展现有seed/测试，创建不同学生A2投同一岗位A，保留另一个岗位B，用于筛选、撤回A后A2/B保持。不扩大产品代码文件。verify需按各自身份和授权核对，不假设每岗位永远一条投递；账号凭据仍只写ignored状态。
5. **执行证据**：日志应保存完整脱敏输出与原始pytest退出码。`pytest | tail`取得的管道退出码不能证明pytest成功；检查PowerShell中$LASTEXITCODE并在日志记录。禁止日志口令。

6. **启动脚本补强**：后端Start-Process后必须等待自有进程健康并验证进程未退出，再seed，目前立即seed存在启动竞态。数据库迁移前就强制Mock并覆盖正确DATABASE_URL，保留/恢复父进程环境；实际3001浏览器请求需配置对应FRONTEND_ORIGINS。Stop-E2E应先验证run ID再拼路径，自有进程匹配失败不得删除记录。记录测试、数据库、storage与distDir的运行清单供CLI校验。
7. **构建产物**：Next build可能改tracked的next-env.d.ts，检查独立build是否影响产品类型文件/tsconfig；运行前后留diff证据，避免与产品构建同时写入。独立distDir及测试存储必须位于ignored范围或明确不入提交；拒绝用户传入业务storage或仓库外可疑目录，不以隔离数据库代替存储隔离。

范围补充：允许最小修改`jianli/.gitignore`只忽略具体独立构建目录，以及`next.config.mjs`里限定独立distDir；不改变常规产品构建目录。若需临时备份/恢复Next生成的tracked类型文件，应记录原始字节并在finally恢复，保留运行前用户改动，不能git checkout覆盖。

第二版代码观察（仍待交棒）：Windows ctypes进程探测需为OpenProcess/GetProcessTimes/CloseHandle明确argtypes/restype，64位HANDLE不可使用默认c_int；PID存活还需检查退出状态。PowerShell5的Set-Content -Encoding utf8写BOM，Python读取运行清单应支持utf-8-sig或写无BOM。guard_base_url接受IPv6时重建URL须保留方括号，不能返回http://::1:8001。上述应按实际实现复核，避免真正启动才暴露。

2026-10-05接续复核：当前PS清单backend字段为`Id/Started/Needle`，Python校验却读取`id/startedAt`，实际清单会拒绝；需统一契约并做真正PS序列化→Python读取校验的回归。后端启动后直到health通过才写state，若health失败，catch调用Stop-E2E找不到记录而遗留自有进程；需启动后立即记录自有PID与时间，或catch安全验证后清理自有进程，不能猜测端口杀进程。进程/端口监听归属也需核对，health200本身不能证明是新进程。

新增拒绝回归应证明拒绝发生在首次HTTP/数据库写入之前。Codex将在交棒后独立复跑最高风险拒绝与撤回/幂等断言；本审查不是最终签收。

## Codex已取得基线（补强前）

命令：在backend执行 `.venv/Scripts/python.exe -m pytest app/tests/test_e2e_fixture_safety.py -q -p no:cacheprovider --basetemp .tmp/pytest-codex-e2e-audit-01`。退出码0，8 passed、5 warnings，耗时3.83s。仅证明当前ASGI/SQLite夹具测试通过，未覆盖上述目标错位及实际启动，不能签收隔离环境。警告来自既有Swig类型弃用信息。

2026-10-05 第二次审查补充：Next build 会自动追加自定义 distDir 类型目录到 tsconfig.json；与 next-env.d.ts 一样，应在 finally 保留并恢复原字节（不存在时只移除本轮生成文件），不能覆盖已有用户改动。后端/前端 health 200 还应核对 Get-NetTCPConnection OwningProcess 属于本轮自有 PID 或经过创建时间核对的子进程，播种前再复核，避免端口竞占误连。新增回归和实跑证据需明确这些边界，不能用静态字符串断言冒充真实拒绝。

2026-10-05 第三次独立审查：create_database finally 使用 asyncpg.Connection.aclose()，本机 asyncpg.Connection 仅有 close() 无 aclose()；实际建库或已存在分支都会在退出失败。改为 await connection.close()，补模拟 asyncpg.connect 的 created/already exists/execute exception 三条分支，验证都关闭连接且异常保留；不连接真实数据库。证据日志 PS5 Tee-Object UTF16 与 Add-Content 混写导致 NUL，请统一输出编码并保留完整命令/退出码，不只截取tail。
