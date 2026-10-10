# 启动脚本实际优化与验证

2026-10-10。用户指出前轮只加强预检、不足以改善启停体验，本批补齐实际行为。

## 现在的入口

- Start-Demo.cmd仍可双击，并透传CheckOnly/Rebuild/NoBrowser等PowerShell参数；正常完成退出，失败保留窗口供查看。Stop-Demo.cmd默认只停网站，显式-Database才停止共用PostgreSQL。
- Start-Local是唯一服务启动实现；Demo不再用HTTP200直接认领别的运行，而是委托它的运行时、配置、代码、PID/开始时间/命令、端口归属和健康检查。
- 默认auto先检查常规venv/node_modules，失败后检查本地已存在且通过当前生产版本/源码验证的升级环境；明确显示最终选择，不自动安装、换套餐或改.env。显式参数不回退到其他环境。
- 源码/public/锁文件/配置、BUILD_ID与关键产物均一致时自动复用生产构建；Rebuild强制重建，SkipBuild只接受可信一致缓存；BuildOnly只准备构建，不访问Docker/迁移/服务/模型。
- 两次并发启停有文件独占锁；演示初始化另有锁。同一运行初始化成功可复用，Reseed重跑幂等播种；修改凭据不会自动轮换既有数据库密码。
- 已运行服务只有在后端生产源码、实际环境配置、依赖路径、前端构建均一致时才复用。配置记录仅保存摘要，不写Key/连接串。停止先验证所有根进程，再核对子PID创建时间；兼容旧数组进程记录。
- 修复NEXT_DIST_DIR=.next与Next配置守卫冲突：普通模式清除隔离覆盖，使用默认.next，并在结束恢复调用者环境。Windows PowerShell5.1按原生命令退出码判定Docker/Alembic结果，正常stderr进度不再被当成失败。

## 验证证据

- local-build-cache.test.mjs：3通过，覆盖缺失/部分构建、源文件/public/锁/配置变化、BUILD_ID变化、产物删除与损坏记录。
- local-runtime.test.ps1：10个断言通过，覆盖旧/新记录、第二个根身份错误、空身份、venv重定向子进程、外来/混合监听者、stderr成功与失败退出码、实际环境配置变化；无真实进程停止。
- 实际生产构建成功，第二次BuildOnly明确复用而不重建。首次真实构建暴露.next显式覆盖错误，失败保留，修复后通过。CheckOnly自动选择.venv-dependency23与dep-frontend-20261010；两个CMD入口透传预检通过。
- 实际生命周期使用专属cp_e2e_startup-smoke-20261010库、隔离storage、环境强制mock/外发关闭。普通8000/3000启动、重复启动同PID与创建时间、Demo入口NoBrowser/SkipSeed复用、默认停止释放两端口均通过；原8001/3001健康保留。专属库/storage保留，业务库/.env/旧依赖未改。
- 失败记录：探针WindowsPS5.1的内联Python引号失败；Docker正常stderr曾使原入口失败，已修；嵌套powershell捕获输出等待后台子进程导致探针停滞，实测服务已健康，由已验证清单停止后改成与Demo一致的同宿主调用完成全生命周期。未仅因观察超时重启。

本次实跑没有播种、打开浏览器或真实模型调用，不声称验证了真实DeepSeek输出。新状态矩阵与AI评测仍按当前接力继续；本批不包含ZCode25未交棒成果。
