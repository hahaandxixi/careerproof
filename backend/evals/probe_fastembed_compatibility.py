"""Offline real ONNX compatibility probe with synthetic inputs and pinned weights."""

from __future__ import annotations

import argparse
import hashlib
import importlib.metadata
import json
from pathlib import Path

import numpy as np

from app.tools.semantic_retrieval import load_local_model, model_directory

TEXTS = [
    "数据库事务提交失败后回滚，防止重复入账。",
    "Python 数据处理脚本与单元测试。",
    "An image upload validates dimensions before decoding.",
    "事务",
    "数据库事务回滚与幂等账目。" * 100,
    "",
]
# Same pinned quantized model, runtime and CPU provider; batch shape can introduce
# rounding differences, so compare numerically rather than requiring byte identity.
BATCH_ABSOLUTE_TOLERANCE = 1e-5


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--cache", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    if args.output.exists():
        raise FileExistsError("Refusing to overwrite earlier probe evidence")
    model = load_local_model(args.cache)
    batch = np.asarray(list(model.embed(TEXTS, batch_size=len(TEXTS))))
    single = np.asarray([next(iter(model.embed([text]))) for text in TEXTS])
    assert batch.shape == single.shape == (len(TEXTS), 384)
    assert np.isfinite(batch).all() and np.isfinite(single).all()
    norms = np.linalg.norm(batch, axis=1)
    # This configured model returns unnormalized mean-pooled vectors. Production
    # semantic_retrieval._cosine normalizes explicitly; require nonzero norms.
    assert (norms > 0).all()
    delta = float(np.max(np.abs(batch - single)))
    query = np.asarray(next(iter(model.embed(["事务回滚防止重复入账"]))))
    scores = (batch @ query) / (norms * np.linalg.norm(query))
    location = model_directory(args.cache)
    hashes = {
        name: hashlib.sha256((location / name).read_bytes()).hexdigest()
        for name in (
            "model_optimized.onnx", "tokenizer.json", "tokenizer_config.json",
            "config.json", "special_tokens_map.json",
        )
    }
    result = {
        "scope": "synthetic offline actual CPU ONNX; no external model calls",
        "fastembed": importlib.metadata.version("fastembed"),
        "onnxruntime": importlib.metadata.version("onnxruntime"),
        "pillow": importlib.metadata.version("Pillow"),
        "weightHashes": hashes,
        "shape": list(batch.shape),
        "finite": True,
        "norms": norms.tolist(),
        "batchAbsoluteTolerance": BATCH_ABSOLUTE_TOLERANCE,
        "batchVsSingleMaxAbsoluteDifference": delta,
        "batchVsSingleWithinTolerance": delta <= BATCH_ABSOLUTE_TOLERANCE,
        "queryScores": scores.tolist(),
        "queryRanking": np.argsort(-scores).tolist(),
        "vectors": batch.tolist(),
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    print(json.dumps({key: value for key, value in result.items() if key != "vectors"}))


if __name__ == "__main__":
    main()
