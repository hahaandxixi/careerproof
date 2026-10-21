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
        assert not saved["git_history_included"]
        assert set(package.AGENT_FIXTURES) <= set(saved["files"])
        assert "完整Git历史须通过原托管仓库" in archive.read("SOURCE_PACKAGE.md").decode()


def test_reproducible_and_existing_output_never_overwritten(repository, tmp_path):
    first, second = tmp_path / "first.zip", tmp_path / "second.zip"
    package.build(repository, first)
    package.build(repository, second)
    assert first.read_bytes() == second.read_bytes()
    original = first.read_bytes()
    with pytest.raises(FileExistsError):
        package.build(repository, first)
    assert first.read_bytes() == original


def test_historical_outputs_excluded_but_eval_sources_retained(repository, tmp_path):
    historical = [
        f"backend/evals/{stem}.{extension}"
        for stem in ("demo-zhipu-20260916-run1", "demo-zhipu-v3-run1",
                     "demo-zhipu-v4-20260916-run1")
        for extension in ("md", "json")
    ]
    retained = ["backend/evals/README.md", "backend/evals/run_quality.py",
                "backend/evals/synthetic-fixture.json"]
    for name in historical + retained:
        path = repository / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("synthetic test content", encoding="utf-8")
    git(repository, "add", ".")
    git(repository, "commit", "-qm", "Add historical outputs and eval resources")
    output = tmp_path / "without-history.zip"
    package.build(repository, output)
    with ZipFile(output) as archive:
        assert not set(historical).intersection(archive.namelist())
        assert set(retained).issubset(archive.namelist())
    assert all((repository / name).exists() for name in historical)


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


@pytest.mark.parametrize("name", [
    "docs/任务清单.md", "docs/协作规则.md", "docs/当前接力.md",
    "docs/task-cards/task.md", "docs/guides/unapproved.md",
    "output/pdf/CareerProof-技术文档-提交候选稿.pdf",
])
def test_internal_documents_and_old_pdf_are_excluded(name):
    assert not package.included(name)


def test_reviewer_guides_and_required_agent_fixtures_are_preserved():
    assert len(package.REVIEW_DOCS) == 8
    for name in package.REVIEW_DOCS | package.AGENT_FIXTURES:
        assert package.included(name)
        assert name in package.REQUIRED


@pytest.mark.parametrize("fixture", sorted(package.AGENT_FIXTURES))
def test_missing_agent_fixture_refuses_package(repository, tmp_path, fixture):
    git(repository, "rm", fixture)
    git(repository, "commit", "-qm", "Remove required Agent fixture")
    output = tmp_path / "missing-agent.zip"
    with pytest.raises(ValueError, match="Missing required source/resources"):
        package.build(repository, output)
    assert not output.exists()


def test_local_links_check_paths_directories_references_images_and_ignore_code():
    contents = {
        "README.md": b'''[guide](<docs/guide one.md>)
[root](/backend/README.md?view=1#setup)
[directory](docs/)
![image](demo/picture.png "title")
[reference][guide]
[guide]: docs/guide%20one.md#heading
[url](https://example.invalid/missing)
[anchor](#not-checked)
`[inline example](missing.txt)`
```markdown
[fenced example](missing.txt)
```
''',
        "docs/guide one.md": b"material",
        "backend/README.md": b"[up](../README.md)",
        "demo/picture.png": b"not rendered",
        "backend/app/tests/fixture.md": b"[not navigation](missing.md)",
    }
    assert package.validate_document_links(contents) == ["README.md", "backend/README.md"]


def test_missing_local_link_refuses_before_creating_zip(repository, tmp_path):
    (repository / "README.md").write_text("[internal](docs/任务清单.md)\n", encoding="utf-8")
    internal = repository / "docs/任务清单.md"
    internal.write_text("Exists in Git but must not be exported", encoding="utf-8")
    git(repository, "add", ".")
    git(repository, "commit", "-qm", "Link to excluded internal document")
    output = tmp_path / "broken-link.zip"
    with pytest.raises(ValueError, match="Missing package document links") as failure:
        package.build(repository, output)
    assert "README.md:1:" in str(failure.value)
    assert "docs/任务清单.md" in str(failure.value)
    assert not output.exists()


def test_navigation_is_checked_from_committed_bytes(repository, tmp_path):
    (repository / "README.md").write_text("[guide](docs/guides/使用与启动.md)", encoding="utf-8")
    git(repository, "add", ".")
    git(repository, "commit", "-qm", "Valid committed navigation")
    (repository / "README.md").write_text("[missing](missing.md)", encoding="utf-8")
    manifest = package.build(repository, tmp_path / "committed-links.zip")
    assert "README.md" in manifest["document_link_check"]["documents"]
