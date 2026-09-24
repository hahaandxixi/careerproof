# 公开仓库合成测试材料

这里的四份简历都是虚构人物和虚构经历；三个项目 ZIP 是公开仓库的**原样文件选集**，不是参赛作品源码，也不代表简历中的人物曾参与开发。它们用于检验材料解析、跨文件检索、AI 引用、职业建议与“本人贡献未核验”的边界。不要把这些 ZIP 当作参赛作品或真实学生项目提交。

| 项目 | 固定提交 | 许可证 | 对应简历与测试重点 |
| --- | --- | --- | --- |
| [pallets/flask](https://github.com/pallets/flask) | `d73fa1cdcbd8b1465c151db8924ba58b1dd14e35` | BSD-3-Clause | `flask-backend.txt`：路由、数据库示例与个人贡献；`flask-qa.txt`：测试断言不等于运行通过 |
| [prometheus/client_python](https://github.com/prometheus/client_python) | `9cd073cb4dc6ee617eadf02dcdec94e0225eff0a` | Apache-2.0 | `prometheus-ops.txt`：指标暴露与生产告警、部署闭环的区别 |
| [coleifer/peewee](https://github.com/coleifer/peewee) | `fa29ff5d56cc7b597a9309b83c245042ebd94ef1` | MIT | `peewee-dba.txt`：ORM 查询与“索引提速十倍”声明的区别 |

原仓库保存在本机被 Git 忽略的 `backend/.tmp/open-source-cases/sources/`；上传 ZIP 和带哈希的清单保存在 `backend/.tmp/open-source-cases/generated/`。生成器只复制白名单内的原文件、保留原许可证与 NOTICE，并加入 `SOURCE.txt`，不会执行下载项目中的代码。

在仓库根目录运行 `backend/.venv/Scripts/python.exe demo/open-source/build_cases.py` 可核验已下载的固定提交并重新生成这些 ZIP。若换一台机器，先将表中的三个仓库分别克隆到 `backend/.tmp/open-source-cases/sources/flask`、`client_python`、`peewee`，检出表中的确切提交，再运行生成器；脚本会拒绝提交不匹配的源码。已有输出不一致时脚本会报错，不会默默覆盖测试基线。

演示上传步骤：使用 `demo/open-source/resumes/` 中的一份 TXT 上传简历；新建项目，将同名项目 ZIP 上传为项目版本；从岗位列表选择本表对应的合成演示岗位并发起 AI 分析。先查看材料预览，再在报告中核对引用、本人贡献限制、补证建议和人工复核。四个案例的预期边界写在生成的 `manifest.json` 中。

ZIP 与简历的对应关系：

| 简历 | 项目 ZIP | 选择的岗位 |
| --- | --- | --- |
| `flask-backend.txt` | `flask-public-source.zip` | Python 后端开发实习生（合成演示） |
| `flask-qa.txt` | `flask-public-source.zip` | 软件测试工程师（合成演示） |
| `prometheus-ops.txt` | `client_python-public-source.zip` | 自动化运维工程师（合成演示） |
| `peewee-dba.txt` | `peewee-public-source.zip` | 数据库工程师 DBA（合成演示） |

自动回归可在 `backend` 目录执行（只解析文件，不运行下载的代码）：

```powershell
& '.venv/Scripts/python.exe' 'evals/run_open_source_cases.py' --output 'evals/open-source-local-offline.json'
& '.venv/Scripts/python.exe' 'evals/run_open_source_cases.py' --ai --output 'evals/open-source-local-ai.json'
```

第二条命令会调用当前配置的真实模型并可能产生费用；每次请使用新的输出文件名，保留历史结果。完整输出含检索到的开源代码片段，默认仅留本机；提交给老师时先阅读案例说明和验收摘要。评测脚本不把引用编号合法等同于“结论由证据支持”，语义结论仍需人工核查。
