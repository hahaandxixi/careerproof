"""Windows target names must identify ordinary files, never aliases or streams."""
import os
import zipfile

import pytest

from app.core.exceptions import AppError
from app.tools.archive_scanner import (
    ArchiveLimits,
    SafeArchiveEntry,
    extract_selected_files,
    inspect_zip,
)


@pytest.mark.skipif(os.name != "nt", reason="actual Windows target namespace")
@pytest.mark.parametrize("unsafe", ["Folder./a.py", "Folder /a.py", "base.py:extra.py"])
@pytest.mark.parametrize("reverse", [False, True])
@pytest.mark.parametrize("direct", [False, True])
def test_windows_alias_or_stream_rejected_before_any_target_write(
    tmp_path, unsafe, reverse, direct
):
    names = ["safe.py", unsafe]
    if reverse:
        names.reverse()
    archive = tmp_path / "synthetic.zip"
    with zipfile.ZipFile(archive, "w") as handle:
        for name in names:
            handle.writestr(name, b"synthetic")
    destination = tmp_path / "output"
    with pytest.raises(AppError, match="Windows"):
        if direct:
            extract_selected_files(archive, destination, [SafeArchiveEntry(n, 9) for n in names])
        else:
            inspect_zip(archive, ArchiveLimits(65536, 65536, 4096, 8))
    assert not destination.exists()
