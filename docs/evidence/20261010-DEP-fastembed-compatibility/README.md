# 传智杯24：fastembed 0.8.1 实际嵌入兼容性独立证据（ZCode 轮）

2026-10-10。Git 根 `D:\jbcode\web ai\jianli`，HEAD 80a6e63/main（任务卡所写 2fefa24 为其祖先，后续 f574cb4/58b728b 等批次已推进）。本目录是 ZCode 按 [任务卡](../../task-cards/20261010-DEP-fastembed-compatibility.md) 的专属证据，与 Codex 已有的 [20261009 签收](../20261009-DEP-fastembed-compatibility/codex-review-20261010.md) 相互独立；两轮结论一致。

## 本轮实际做了什么

1. **新缓存**：从旧缓存 `.tmp/models` 只读复制配置模型（qdrant paraphrase-multilingual-MiniLM-L12-v2-onnx-Q，revision faf4aa42）到 `backend/.tmp/dep24-models`，5 个必需文件 sha256 逐字节核对一致，`model_optimized.onnx` 与生产 `MODEL_SHA256`（634d0f66…59a9）一致。旧缓存零写入。见 `cache-copy-verification.raw.out`。
2. **同权重新旧解释器真实嵌入对比**：容差先于运行写入 `tolerance-predeclared.md`（含依据，运行后未放宽）。
   - 基线（旧 `.venv`，fastembed 0.7.4/Pillow 11.3.0）：`probe-baseline-074.raw.out`，exit 0，6×384 全有限、范数非零、批次/单条最大差 0.0。
   - 候选（`.venv-dependency23`，fastembed 0.8.1/Pillow 12.3.0）：`probe-candidate-081.raw.out`，exit 0，同上。
   - 两 venv 嵌入栈其余完全一致：Python 3.12.14、onnxruntime 1.30.0、tokenizers 0.23.2、huggingface-hub 1.32.0、numpy 2.5.2（见 `interpreter-versions-074/081.raw.out`）。
   - 跨版本比较 `comparison.json`（`compare_embeddings.py`，判定逻辑不含阈值常量）：**最大绝对差 0.0（≤1e-5）、同位余弦最小 0.9999999999999998（≥1-1e-9）、查询排序逐元素一致、范数一致、权重 hash 一致**，全部通过，exit 0。
   - 0.7.4 的 mean-pooling UserWarning 在 0.8.1 消失，向量数值不变（与 Codex 结论一致，非 pooling 切换）。
3. **pip check / 冻结对比**：`pip-check-081.raw.out` exit 0 `No broken requirements found.`。本轮未执行任何安装——0.8.1 升级由 Codex 前轮完成（安装与首次失败的原始日志在 20261009 目录 `codex-install-081.raw.out`、`codex-pip-check-081.raw.out`，当时 editable 元数据过期导致一次失败后 refresh 转清洁）。本轮冻结 `freeze-081.txt`（108 项）对首批 baseline（107 项）diff 见 `freeze-diff-first-batch.txt`：超出预期 4 包的变更全部可归因于已提交后续批次——fastapi 0.143.0/starlette 1.3.1 + 新增 annotated-doc、opentelemetry-api（两者经已装元数据反查均为 fastapi 依赖，批次 f574cb4）；pytest 9.0.3/pytest-asyncio 1.4.0/Mako 1.4.2/pip 26.2.1（批次 58b728b）；`pip==25.0.1` 行消失是 pip≥25.1 不再自列的清单现象，非卸载。fastembed 0.7.4→0.8.1 安装时刻的实际变更仅其自身（20261009 目录 `codex-installed-diff.json`）。归因表交棒裁决，无未解释变更。
4. **新兼容性测试** `backend/app/tests/test_fastembed_dependency_compatibility.py`（3 用例，零 mock）：pyproject 四 pin 与实际安装逐一相等；fastembed 全部生效的 Requires-Dist 与已装环境逐条满足（历史 `pillow<12` 冲突的进程内等价门）；权重在场时走生产 `load_local_model` 真实 CPU ONNX 冒烟（本轮实际运行未跳过），缺席则显式 skip，不以替身冒充。
5. **回归**：`pytest-affected-11files.raw.out` exit 0，**130 passed, 0 skipped**（首批 8 文件 117 + semantic/hybrid 10 + 新 3），命令带 `-p no:cacheprovider --basetemp=.tmp/dep24-zcode-basetemp`。golden legacy JWT 的 23 字节合成密钥 InsecureKeyLengthWarning 如实保留在原始输出，不代表生产密钥状态。Ruff：`ruff.raw.out` exit 0 `All checks passed!`（新测试 + 已提交探针）。

## 失败记录

本轮无失败：所有探针、比较、pip check、pytest、Ruff 首次运行即 exit 0。原始 stdout/stderr 均按 `.raw.out/.raw.err` 成对保存。

## 自审

- 未安装/卸载任何包，未改 `backend/pyproject.toml`（pin 已在 HEAD）、生产源码、旧 `.venv`、旧缓存、服务、数据库、`.env`、P2 stash；未提交未推送（`git status` 本轮新增仅本目录与新测试文件，均 untracked；`.tmp/`、`.venv-dependency23/` 被 .gitignore 忽略）。
- 探针走真实 `load_local_model`（SHA256 校验 + `local_files_only` + `specific_model_path`），无 TextEmbedding monkeypatch、无 mock 嵌入、无网络模型调用、无真实简历/业务重索引。
- 预立容差文件时间戳先于两份探针 JSON（探针自身拒绝覆写已存在输出）。
- 新测试的 skip 语义与真实嵌入通过严格区分；测试替身（既有 `MeaningOnlyEmbedder` 用例）与本轮真实嵌入证据分开陈述。

## 交付物 hash（sha256）

| 文件 | hash |
|---|---|
| app/tests/test_fastembed_dependency_compatibility.py | 50ad782025b5bcd9d2cb71415cc1edad3993230231a5e0b172f5ceac0d4fe916 |
| evals/probe_fastembed_compatibility.py（已提交 559fdee，未改） | 385a863aead17dc7f856fd89affc8c63aa57b8058fe5899a6404c148604b6372 |
| compare_embeddings.py | 69084bfe0e64a1f7ba639f0ee640f3bd58ce13fc1d8eed1e5ca84b1cd240b804 |
| probe-baseline-074.json | 4c2ea8f968d9036e3d2249e56034f3fbc1962baef726597829bba823027a76d9 |
| probe-candidate-081.json | 03b27dba9960536168aa0c1461ef2b15e2f047217672c9584a187e40db9ceb10 |
| comparison.json | cdf876e080c395988deb9a1b02c6e39c19babe25a7544821720aad44785a7cd8 |

## 未验证范围

本结论限于 fastembed 0.7.4→0.8.1 同权重嵌入兼容与首批依赖签收补强：未跑后端全量套件、PG/服务启动、框架联动全量、前端、升级环境页面链路、AI 语义评测；`.tmp/dep24-models` 未回填生产 `.tmp/models`（生产缓存路径与索引兼容结论：`specific_model_path` 固定 qdrant 目录 + revision，不受 0.8.x 默认 cache 命名变化影响，无需重建旧索引——与 Codex 轮结论一致）。首批兼容通过不等于整体升级完成。
