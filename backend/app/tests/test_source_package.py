"""Exercise exported Git content, exclusions and refusal without touching this repo."""

import importlib.util
import json
import subprocess
from pathlib import Path
from zipfile import ZipFile

import pytest

MODULE_PATH = Path(__file__).resolve().parents[3] / "scripts/build_source_package.py"
SPEC = importlib.util.spec_from_file_location("source_package", MODULE_PATH)
package = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(package)


def git(root, *args):
    return subprocess.check_output(["git", *args], cwd=root)


@pytest.fixture
def repository(tmp_path):
    root = tmp_path / "repo"
    root.mkdir()
    git(root, "init", "-q")
    git(root, "config", "user.name", "Synthetic test")
    git(root, "config", "user.email", "test@example.com")
    git(root, "config", "core.autocrlf", "false")
    for name in package.REQUIRED:
        path = root / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(b"synthetic committed content\n")
    for name in ("backend/.env", "backend/Storage/private.txt", "backend/.TMP/password.txt",
                 "backend/demo-credentials.json", "backend/secret.key"):
        path = root / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(b"private excluded value")
    git(root, "add", ".")
    git(root, "commit", "-qm", "Synthetic baseline")
    return root


def test_committed_snapshot_excludes_private_and_worktree_content(repository, tmp_path):
    (repository / "README.md").write_bytes(b"uncommitted replacement")
    (repository / "backend/untracked.py").write_bytes(b"untracked")
    before = git(repository, "status", "--porcelain")
    output = tmp_path / "source.zip"
    manifest = package.build(repository, output)
    assert git(repository, "status", "--porcelain") == before
    with ZipFile(output) as archive:
        assert archive.read("README.md") == b"synthetic committed content\n"
        assert "backend/untracked.py" not in archive.namelist()
        assert "backend/.env.example" in archive.namelist()
        assert package.REVIEW_FIXTURE in archive.namelist()
        for name in ("backend/.env", "backend/Storage/private.txt", "backend/.TMP/password.txt",
                     "backend/demo-credentials.json", "backend/secret.key"):
            assert name not in archive.namelist()
        saved = json.loads(archive.read("SOURCE_MANIFEST.json"))
        assert saved == manifest
        assert set(saved["files"]) == package.REQUIRED
        assert not saved["worktree_included"]


def test_reproducible_and_existing_output_never_overwritten(repository, tmp_path):
    first, second = tmp_path / "first.zip", tmp_path / "second.zip"
    package.build(repository, first)
    package.build(repository, second)
    assert first.read_bytes() == second.read_bytes()
    original = first.read_bytes()
    with pytest.raises(FileExistsError):
        package.build(repository, first)
    assert first.read_bytes() == original


def test_missing_frozen_review_refuses_incomplete_package(repository, tmp_path):
    git(repository, "rm", package.REVIEW_FIXTURE)
    git(repository, "commit", "-qm", "Remove required resource")
    output = tmp_path / "missing.zip"
    with pytest.raises(ValueError, match="Missing required source/resources"):
        package.build(repository, output)
    assert not output.exists()


def test_possible_provider_secret_refused_without_disclosing_value(repository, tmp_path):
    secret = "sk-" + "A" * 32
    (repository / "backend/settings.txt").write_text(f"DEEPSEEK_API_KEY={secret}")
    git(repository, "add", ".")
    git(repository, "commit", "-qm", "Synthetic secret sentinel")
    with pytest.raises(ValueError, match="Possible provider key") as failure:
        package.build(repository, tmp_path / "refused.zip")
    assert secret not in str(failure.value)


@pytest.mark.parametrize("path", ["/backend/a.py", "backend/../a.py", "backend\\a.py",
                                 "backend/a:stream", "backend/a\n.py"])
def test_unsafe_archive_names_are_excluded(path):
    assert not package.included(path)


def test_ci_workflows_are_exported_but_other_hidden_github_files_are_not():
    assert package.included('.github/workflows/ci.yml')
    assert not package.included('.github/private-credentials.json')
