from __future__ import annotations

from pathlib import Path
from typing import Protocol


class Storage(Protocol):
    def save(self, object_key: str, content: bytes) -> str: ...

    def resolve(self, object_key: str) -> Path: ...


class LocalStorage:
    def __init__(self, base_dir: Path) -> None:
        self.base_dir = base_dir.resolve()
        self.base_dir.mkdir(parents=True, exist_ok=True)

    def resolve(self, object_key: str) -> Path:
        target = (self.base_dir / object_key).resolve()
        if target != self.base_dir and self.base_dir not in target.parents:
            raise ValueError("object key escapes storage base directory")
        return target

    def save(self, object_key: str, content: bytes) -> str:
        target = self.resolve(object_key)
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(content)
        return object_key
