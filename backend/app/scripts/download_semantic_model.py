"""Install the pinned, Apache-2.0 ONNX embedding model before first use."""

from __future__ import annotations

from huggingface_hub import snapshot_download

from app.core.config import settings
from app.tools.semantic_retrieval import (
    MODEL_REPOSITORY,
    MODEL_REVISION,
    load_local_model,
    model_directory,
)


def main() -> None:
    cache = settings.semantic_model_cache_dir
    try:
        snapshot_download(
            repo_id=MODEL_REPOSITORY,
            revision=MODEL_REVISION,
            cache_dir=str(cache),
            allow_patterns=[
                "model_optimized.onnx",
                "tokenizer.json",
                "tokenizer_config.json",
                "config.json",
                "special_tokens_map.json",
            ],
            local_files_only=True,
        )
    except Exception:
        snapshot_download(
            repo_id=MODEL_REPOSITORY,
            revision=MODEL_REVISION,
            cache_dir=str(cache),
            allow_patterns=[
                "model_optimized.onnx",
                "tokenizer.json",
                "tokenizer_config.json",
                "config.json",
                "special_tokens_map.json",
            ],
        )
    model = load_local_model(cache)
    dimensions = len(next(iter(model.embed(["数据库事务回滚"]))))
    if dimensions != 384:
        raise ValueError("Unexpected semantic model dimensions")
    print(f"Local semantic model ready: {model_directory(cache)} (384 dimensions)")


if __name__ == "__main__":
    main()
