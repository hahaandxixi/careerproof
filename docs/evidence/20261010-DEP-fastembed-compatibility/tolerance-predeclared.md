# 预立容差（探针运行前声明）

本文件在任何探针/比较运行之前写入。依据与阈值如下，运行后不放宽；不通过即记录失败原文并停止。

## 比较对象

- 旧解释器：`backend/.venv`，fastembed 0.7.4 / Pillow 11.3.0
- 新解释器：`backend/.venv-dependency23`，fastembed 0.8.1 / Pillow 12.3.0
- 其余嵌入栈实测完全一致：Python 3.12.14、onnxruntime 1.30.0、tokenizers 0.23.2、huggingface-hub 1.32.0、numpy 2.5.2
- 权重：`backend/.tmp/dep24-models`（从旧缓存 `.tmp/models` 复制，5 个必需文件 sha256 已逐字节核对一致；`model_optimized.onnx` 与生产 `MODEL_SHA256` 一致）
- 输入：探针内置 6 条合成文本（中文/英文/混合长短/空串），无真实简历

## 阈值与依据

1. 批次 vs 单条（同一解释器内）：最大绝对差 ≤ **1e-5**。
   依据：float32 CPU 上不同批次形状可改变归约顺序，epsilon≈1.19e-7，累加长度~128 token 的最坏舍入噪声量级在 1e-5 内；该阈值已固化在已提交探针 `BATCH_ABSOLUTE_TOLERANCE`，本轮不改。
2. 跨版本（0.7.4 vs 0.8.1 同权重同输入）：最大绝对差 ≤ **1e-5**。
   依据：ONNX 图、tokenizer 文件、onnxruntime、numpy 完全相同，唯一变量是 fastembed 库版本；若 0.8.x 的 padding/池化实现等价，输出应数值一致，仅允许浮点归约顺序差异。1e-5 对量级 O(0.1) 的分量约 100 ULP，宽于舍入噪声但远低于任何语义可分辨差异。
3. 跨版本同位置向量余弦：≥ **1 - 1e-9**（等价计算必须保持方向）。
4. 查询排序：`argsort(-scores)` 逐元素完全一致，无容差。
5. 维数/有限性/范数：两版本均为 (6, 384)、全有限、范数 > 0，无容差。

不满足任一条 → 保留原始输出为失败证据，不调整阈值重跑。
