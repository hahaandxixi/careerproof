"""Display-only removal of the internal material UUID from file paths and text."""
from __future__ import annotations

import re

_UUID_PREFIX = re.compile(
    r"^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}/"
)
_UUID_PREFIX_ANYWHERE = re.compile(
    r"[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}/"
)


def display_file_path(file_path: str) -> str:
    """Strip exactly one leading material-version UUID segment."""
    return _UUID_PREFIX.sub("", file_path, count=1)


def display_path_text(text: str) -> str:
    """Strip UUID prefixes embedded in saved text without changing the stored value."""
    return _UUID_PREFIX_ANYWHERE.sub("", text)
