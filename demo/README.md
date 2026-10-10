# CareerProof 合成演示材料

先看 [演示测试指南](../docs/guides/使用与启动.md)。网页入口：http://127.0.0.1:3000/demo ，包含演示账号、样例下载与操作步骤。

本目录只包含虚构数据，用于本地开发、浏览器主链路验收和后续规则/AI 对照评测。
姓名、邮箱、项目和经历均为合成内容，不对应真实个人或组织。

当前基础样例：

普通网站测试优先使用 [九职业配对案例清单](role-cases.json)。CP01—CP09 各有对应简历、项目/作品和人工步骤，文件名带职业与 v1；`/demo` 按卡片下载。演示初始化会把这九套材料导入本地演示学生账号，同编号配对选择，不混入其他职业。已有材料直接复用；亲自重新上传时，在名称末尾加本轮日期。

修改源材料后运行 `backend/.venv/Scripts/python.exe demo/build_role_packs.py`，生成 `jianli/public/demo-assets/cases/` 下的具名文件与网页清单。过程不联网、不执行项目代码。运行 `backend` 中的 `.venv/Scripts/python.exe -m evals.seed_role_materials --apply` 可导入/复用九套材料，不生成 AI 报告。详见 [演示测试指南](../docs/guides/使用与启动.md)。

以下旧路径保留给已有引用与专项脚本，不再作为所有职业共用的上传案例：

- `student-resume.txt`：声明 Python、FastAPI、PostgreSQL 和测试经验。
- `evidence-api/`：可静态核验的 FastAPI、PostgreSQL 与 pytest 项目片段。
- `evidence-function-call/`：受控补检索专项材料，初始候选不包含完整任务，索引内另有可由模型补取的 `create_item`。
- `software-backend-job.md`：演示岗位及预期证据关系。

生成上传用 ZIP：

```powershell
Compress-Archive -Path evidence-api\* -DestinationPath evidence-api.zip -Force
Compress-Archive -Path evidence-function-call\* -DestinationPath evidence-function-call.zip -Force
```

Function Calling 专项会消耗真实模型额度，优先复用已保存报告；需要重跑时按
[演示测试指南](../docs/guides/使用与启动.md)执行。
