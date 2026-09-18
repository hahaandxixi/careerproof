# CareerProof 合成演示材料

先看 [演示测试指南](../docs/演示测试指南.md)。网页入口：http://127.0.0.1:3000/demo ，包含演示账号、样例下载与操作步骤。

本目录只包含虚构数据，用于本地开发、浏览器主链路验收和后续规则/AI 对照评测。
姓名、邮箱、项目和经历均为合成内容，不对应真实个人或组织。

当前基础样例：

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
[演示测试指南](../docs/演示测试指南.md)执行。
