# 传智杯24：Pillow / fastembed 联动兼容性

实际 Git 根：D:\jbcode\web ai\jianli，main。首批三 pin 尚未签收；当前 fastembed 0.7.4 要求 Pillow<12，与已选 Pillow12.3.0 冲突。不能以 import 或 mock 测试通过豁免 pip check。

## 文件所有权与授权

ZCode 唯一写入 backend/pyproject.toml 的 fastembed pin、backend/.venv-dependency23、一个新的 backend/evals/probe_fastembed_compatibility.py、新兼容性测试，以及 docs/evidence/20261010-DEP-fastembed-compatibility/。保留已有 multipart/Pillow/PyJWT pin 与回归文件，不改原 backend/.venv、生产检索源码、其他依赖、既有测试、正式接力文档、服务、数据库、.env、P2 stash。Codex只读审查，任务终态后独立复验和提交。

用户已授权本轮项目依赖下载安装；可下载公开模型权重到专属缓存，禁止真实简历/真实模型API/外发消息/业务重索引/Git提交推送。原缓存只读，任何复制到新缓存均保留原文件。需要额外依赖或生产改动时交失败证据给Codex，不扩大修改范围。

## 实施与验收

1. 核对 status/HEAD 和现有 diff，直接读 app/tools/semantic_retrieval.py、相关测试和本卡；不重新研究全仓。0.8.1 官方 PyPI 元数据见 docs/evidence/20261009-DEP-fastembed-compatibility/official-pypi-metadata.json。选择0.8.1是最小0.8补丁路径：Python3.12允许Pillow<13，且修复0.8.0的混合长度padding回归。0.9暂不引入额外功能。来源 https://pypi.org/pypi/fastembed/0.8.1/json 和 https://github.com/qdrant/fastembed/releases/tag/v0.8.1 。
2. 使用旧venv 0.7.4 与新venv 0.8.1，对同一配置模型 sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2、同一权重文件hash和合成文本跑真实CPU ONNX嵌入。调用实际 load_local_model，不 monkeypatch TextEmbedding；记录两解释器版本、权重hash、向量维数/有限性/范数、向量最大绝对差与余弦、查询排序。含中文/英文、空串处理、混合长短批次与单条结果一致性。容差须事先写明依据，不通过后放宽凑绿。
3. 新缓存位于 backend/.tmp/dep24-models；旧缓存只读。若现有权重缺失可下载公开项目配置权重，不提交大二进制。默认模型上游cache命名变化不等于本项目配置变化；记录本项目实际路径、pooling/normalization及缓存/索引兼容结论。不能把测试替身的16通过冒称实际嵌入通过。
4. 新环境安装 fastembed==0.8.1，保留每次失败原始日志和exit code，pip check必须清洁。冻结清单与首批baseline对比，预期仅multipart/Pillow/PyJWT/fastembed四包改变；额外变更交棒裁决。不回退已修补Pillow、不关闭依赖约束。
5. 运行真实嵌入探针和有关semantic/embedding/hybrid回归，再跑首批受影响8文件117项及Ruff。pytest使用独立 basetemp 并 -p no:cacheprovider，避免重用导致证据丢失。无需本批PG或服务启动。原有 golden legacyJWT 的合成短密钥警告需如实记录，不能伪造为生产弱密钥结论。
6. 日志用各自 .raw.out/.raw.err 保存（仓库忽略.log）；证据README包含原始命令、exit code、计数、失败与修正、自审、未验证范围、实际diff/hash。一屏回报后停止写入。首批兼容通过不等于框架、前端、升级后页面、AI语义评测全部完成。

个人 BigModel GLM-5.3/最高。现场核对额度，周余额至少30%；耗尽保留文件和具体未完成点，不反复重试扣额。
