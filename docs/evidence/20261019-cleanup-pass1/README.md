# 临时文件第一批清理（2026-10-19）

用户直接授权清理无用临时文件和历史遗留。本批只删除可再生成内容，不执行历史79号卡的文档/任务卡删除部分。

- 删除255个目录、25,330个文件，按文件大小合计4,849,138,096字节（4.516 GiB）。逐路径清单见cleanup.json、deletion-results.json及verification.json。
- 范围：pytest专属basetemp（根目录布局为test_*编号目录/.lock）、旧前端的Next编译cache、可读取的Ruff缓存。旧完整构建成品、源码、锁文件、node_modules均保留。
- 保留当前dep-frontend-20261019-picker及.venv-dependency23；未启停网站、数据库或Docker，未调用模型、安装依赖、改ACL、操作P2。
- 保留全部正式文档/任务卡/历史证据、未提交源码与测试、账号与上传材料、预算占用标记、备份、模型文件、演示视频原素材、PDF及源码包；D:/jbcode其他项目未改动。
- 60处无法读取的历史目录在扫描阶段跳过；backend/.pytest_cache因不可读取跳过。未提权或修改权限。全部255个通过检查的候选最终成功删除，无部分失败。

删除前验证绝对路径位于当前仓库；检查目标及所有祖先/后代无重解析点、Git无跟踪文件、无活跃node/python进程引用、不与当前启动目录重叠；发现活跃pytest时会保留所有basetemp。PowerShell仅使用同一shell和LiteralPath删除，不跟随目录联接。脚本有一次性执行标记，不能误重复执行旧清单。

删除后1626个既有未提交/未跟踪且非忽略文件的SHA256均与删除前一致，P2 stash提交哈希未变；之后只追加本批状态说明，不覆盖用户在当前接力中的单空白行。没有将未跟踪文件当作垃圾清除。

正常站/jobs与/api/v1/health均200，列表仍为4条/3套新样例；当前BUILD_ID仍为XaZKbZz9Z7rYI8ltVzuUO。Start-Local.cmd -CheckOnly退出0，当前依赖/源码匹配；不重复运行全量测试。

验证程序首轮将健康地址写成/health，得到404而岗位API已200；纠正为启动器实际使用的/api/v1/health后通过。首次结果保留在verification-wrong-health-path.json，不是网站故障，也未为此重启服务。

这不是全部历史内容已清空的声明。未签收的任务卡、仍用于复验的测试台、共享依赖与历史失败原始日志继续保留。
