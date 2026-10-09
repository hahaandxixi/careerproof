# 首批依赖与实际嵌入兼容性签收

2026-10-10。传智杯23交付三包回归117通过，但fastembed0.7.4要求Pillow<12，不能仅凭import签收。Codex独立34通过，收紧截断multipart必须400/422，禁止202算成功。

传智杯24确已在jbcode新建，个人GLM-5.3/最高，session sess_844d70fa-5fe8-47e0-9c24-70102d2acef2。实际首调用rate_limited/0输出/无工具，UI明确02:01:07恢复；25%面板不等于能调用。没有重复扣额，Codex接管本批所有写入。后续恢复此任务时须先读最新diff，不重做。

## 环境及证据

仅新backend/.venv-dependency23安装fastembed0.8.1，旧venv未升级。先安装触发项目editable元数据仍固定0.7.4的pip check失败，原文codex-pip-check-081.raw.out保留；同步manifest并pip install -e . --no-deps后codex-pip-check-refreshed.raw.out为No broken requirements found。三项首批pin加fastembed合计四包升级；冻结差异须与baseline逐包核对。

实际CPU ONNX探针命令（backend目录）：

```text
.venv/Scripts/python.exe -m evals.probe_fastembed_compatibility --cache .tmp/models --output ../docs/evidence/20261009-DEP-fastembed-compatibility/codex-baseline-074.json
.venv-dependency23/Scripts/python.exe -m evals.probe_fastembed_compatibility --cache .tmp/models --output ../docs/evidence/20261009-DEP-fastembed-compatibility/codex-candidate-081.json
```

均通过真实生产load_local_model、local_files_only、同固定revision/hash的现有权重只读，无下载/网络模型/业务重索引。6组中文/英文/混合长短/空串，6x384、全部有限、范数非零；两版本batch/单条差0，跨版本向量最大差0、查询余弦排序相同。JSON含全部向量及五文件hash；比较codex-comparison.json。预置batch绝对容差1e-5未放宽。

首次探针错误假设单位向量，baseline断言失败原文codex-baseline-074.raw.out保留。实际模型为未归一化mean pooling，生产_cosine显式归一化；修正探针为非零范数和余弦比较。旧0.7.4已有mean-pooling提示，0.8.1无该提示，结果完全相同；不是本批引入pooling切换。本配置使用specific_model_path固定小写qdrant目录，不使用上游默认BAAI模型cache命名，因此没有据此重建旧索引。

## 回归与限制

新venv pytest：首批8文件加semantic/hybrid共10文件，127通过、0跳过、exit0，-p no:cacheprovider及独立basetemp=.tmp/dep24-codex-target-20261010；见codex-affected-tests.raw.out。Ruff probe和新回归All checks passed。黄金旧JWT使用合成23字节key的警告如实保留，不代表生产密钥状态。

本结论为首批依赖兼容性签收：未做后端全量/PG/框架联动/前端升级、升级环境网站迁移页面链路或AI语义评测；不宣称全部漏洞消除。原有测试替身通过和这次实际嵌入证据分开。真实DeepSeek、外发、部署、推送均未执行。P2 stash保持暂停。
