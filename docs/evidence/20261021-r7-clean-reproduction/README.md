# r7交付包隔离干净复现（2026-10-21）

结论：r7在Windows专属环境完成全新安装、迁移、生产启动、合成账号/材料、规则报告、浏览器引用核对及停止/重启恢复。离线播种说明不完整已补回仓库README，提交39f49d7，产出r8。仅两份README变化，837份文件中其他运行源码/依赖与本次实际执行r7逐字节一致；未把r8再安装一遍称为第二次干净安装。不是首次独立用户或真实AI质量验收。

## 包和环境

- r7来源：9d43e5a02fbd76cba5dd8370e6956feac90f3d7a；SHA256：5b0169c10daca3b766c1a6085b6a379f614676e715da5663567c19f76df90ea2。输入完整清单见input-manifest.json。
- r8来源：39f49d7d9c79282a62401d0b23c7182bdaaf8e2f；SHA256：1666cf7f5cb6d88dd2ef2c1e9484fed242258967bcf544887106bf5733f845ab。本机文件output/source/CareerProof-source-review-20261021-r8.zip；完整清单r8-manifest.json，837文件哈希及20份保留文档本地导航通过。
- 全新解包：backend/.tmp/r7-clean-20261021/source；全新backend/.venv（Python3.12.14、include-system-site-packages=false），独立jianli/node_modules。允许下载缓存，未借用已安装venv或node_modules；Node22.23.1/npm10.9.8。
- 专属容器careerproof-r7-clean-20261021；127.0.0.1:55441/cp_review_r7_20261021，API8107、前端3107，独立storage。初始端口空闲，原正常站与正常库未启停或写入。Docker起初未就绪，用户启动后继续。

## 各阶段实际结果

| 阶段 | 命令/结果与证据 |
| --- | --- |
| Python安装 | 在新backend执行 .venv/Scripts/python.exe -m pip install -e ".[dev]"，成功安装日志pip-install.raw.out；pip check退出0，无依赖冲突 |
| 前端安装 | 在新jianli执行npm ci，357包安装日志npm-ci.raw.out；未复制旧依赖 |
| 迁移 | 新环境 -m alembic upgrade head退出0，空库逐级到0021_job_discovery_flags；migrate.raw.out、environment.json核实实际数据库 |
| 构建/启动 | BACKEND_ORIGIN=http://127.0.0.1:8107后npm run build退出0；新venv的uvicorn app.main:app监听8107，新安装Next生产监听3107。首轮与重启健康均200 |
| 账号准备 | 首次直接seed因无凭据被拒，保留seed-demo.raw.out；随后成套设置已有三项DEMO环境变量，明确选择8107，用现有seed函数准备账号和3套岗位。精确补充文档命令重放退出0，不复制正常账号 |
| 材料/报告 | 通过3107生产代理登录、上传体验场景简历/项目、解析、生成未同意外发的规则报告；5项要求、3个原文件，12条引用的行号/片段、上传字节哈希和版本一致。HTTP调用见http-calls.json，结果flow.json/report-first.json |
| 浏览器 | 实际IAB登录到材料页，打开新报告，展开引用及定位信息；截图/AX证明路径、行号和原文显示。上传和报告创建由HTTP执行，未冒充全鼠标链路 |
| 停止/恢复 | 核对本轮进程身份后停止前后端，专属数据库stop/start，再用原配置/构建/存储重启。报告SHA完全相同，简历与项目文件可读，浏览器刷新再次显示规则报告及引用；restore.json和browser-restored.png |
| 外发边界 | mock、AI_EXTERNAL_ENABLED=false、无真实Key；报告analysisMode=rules、aiProvider/aiUsage为空、aiToolCalls为空，专属库AI相关表全部0；不改历史claim |

安装工具初次返回被用户中断，但后台安装自然完成；未保留pip install/npm ci的退出码，不能补造。各自成功日志及随后新环境导入、pip check、迁移、生产构建和HTTP/浏览器实际运行构成安装可用证据。没有安装第二套旧环境来替代失败。

## 文档修复及限制

仅backend/README.md与jianli/README.md新增现有离线手动入口的配置、端口/构建和演示账号准备步骤；不改变正常双击入口、PID协议或业务代码。新包保留r7及所有失败记录。核查脚本首轮哈希对象用错的修正见verification-correction.md，不将验证脚本错误当产品缺陷。

仅Windows与本轮端口/专属PG通过；未验证其他操作系统、无缓存网络安装、公网部署、真实AI、新Agent三例、人工语义或首次独立用户，亦非候选全项目测试通过。视频/PDF和评审访问/许可/签署仍单独处理。

## 最终资源

本轮前后端已停止，3107/8107/55441端口关闭；专属容器stopped、数据库匿名卷/存储、全新依赖、解包目录均保留以便复查。Docker Desktop按用户启动状态保留，未停止引擎；临时浏览器页已关闭。正常站、正常库、原工作区5份受保护文件、暂停P2均保留原状；凭据仅本机backend/.tmp/r7-clean-20261021，不入证据或包。详见final-state.json。
