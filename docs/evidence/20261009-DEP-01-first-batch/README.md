# 传智杯23 DEP-01 首批依赖升级证据包

2026-10-09。Git 根 `D:\jbcode\web ai\jianli`，HEAD b947171/main（未提交未推送），生产基线 4c78ba7，P2 stash 未动。

## 环境与方法

- 独立 venv：`backend/.venv-dependency23/`，解释器与原 venv 同 base（codex-primary-runtime CPython 3.12.14），pip 25.0.1（未升级）。见 `final-interpreter-versions.txt`。
- 基线复刻：按 `baseline-pinned.txt`（107 项，排除 editable）安装 + `pip install -e . --no-deps` → `pip check` 干净（`pip-check-baseline.log`）。
- 升级前目标基线：portfolio+visual_evidence+document_ocr+auth = 78 passed（`pytest-baseline-targets.log`）；新增回归在旧版本下 = 17 passed（`pytest-baseline-newregression.log`）。
- 测试统一 `--basetemp=.tmp/dep23-basetemp`（系统 `Temp\pytest-of-江博` WinError 5 拒绝访问，与新 venv 无关，首次基线运行失败记录见 `pytest-baseline-targets.log` 覆盖前的同名文件已丢失，仅此说明）。

## 逐项结果

| 项 | 版本 | pip check | 回归 |
|---|---|---|---|
| ① python-multipart | 0.0.20→0.0.31 | 干净 | portfolio+新回归 25 passed（`pytest-01-multipart.log`） |
| ② Pillow | 11.3.0→12.3.0 | **fastembed 0.7.4 声明 pillow<12.0** | visual+ocr+新回归 70 passed；embedding/local_retrieval 16 passed（`pytest-02-*.log`） |
| ③ PyJWT | 2.10.1→2.15.0 | 同上仅剩 fastembed 项 | auth+新回归 34 passed；role_materials 6 passed（`pytest-03-*.log`） |

最终全套 8 文件 117 passed（`pytest-final-all-targets.log`）。venv 与基线 diff 仅三目标包（`venv-diff-baseline-to-final.txt`、`final-dependency23-freeze.txt`）。

## 唯一遗留冲突（交棒 Codex 决策）

`fastembed 0.7.4 requires pillow<12.0,>=10.3.0`（`pip-check-final.log`）。运行时证据：`from fastembed import TextEmbedding` 与本项目唯一使用点 `app/tools/semantic_retrieval.py` import 正常；fastembed 文本 embedding 不走 Pillow 图像路径；全部图像回归通过。onnx 模型懒加载未执行（需下载模型，超出本卡授权）。选项：升级 fastembed（另卡）、受控豁免或回退 Pillow——未决，不冒称兼容。

## 新增回归测试

`app/tests/test_dependency_upgrade_regression.py`（17 用例，真实行为不 mock 库）：multipart 坏 boundary/截断 body/文件名穿越中性化；safe_png 损坏图 4024/像素上限 4026；vision 预检 2MB/非PNG/1281px；OCR 未启用 4025/损坏 4024/像素 4026；PyJWT 7 种畸形 token 4010 + legacy 2.10.1 签发 token（合成 secret，exp 2099）在 2.15.0 下正常解码且 role/jti 保持。Ruff 最终 `All checks passed!`（修复前记录 `ruff-final.log`，参数 noqa: F811 与 test_visual_evidence.py:114 仓库惯例一致，修复后 `ruff-final-after-fix.log`）。

## 写入清单与未验证项

写入：`backend/pyproject.toml` 三处 pin、`backend/.gitignore` 一行 `.venv-dependency23/`、`backend/.venv-dependency23/`、新增回归测试、本目录证据。原 venv/生产源码/已有测试/.env/服务/业务库/前端/正式文档/P2 stash 未动。

未验证：后端全量测试套件（约 90 文件）未跑——按卡交棒 Codex 定范围；fastembed onnx 模型真实加载；PG 集成路径未触（本轮无 PG 测试参与）；批次3 FastAPI/Starlette、批次4 前端、pytest/pip 等均未动，不代表完成。
