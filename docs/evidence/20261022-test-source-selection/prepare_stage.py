"""Build an explicit accepted source set, never copy the dirty working tree."""
import hashlib
import io
import json
from pathlib import Path
import subprocess
import zipfile

ROOT = Path(__file__).resolve().parents[3]
OUT = Path(__file__).parent
STAGE = ROOT / "backend/.tmp/test-source-accepted-20261022"
BASE = "7a19e6b872c8df1a9b74c6e912f0488e43fbe203"
FILES = [
    "backend/app/tools/code_analyzer.py",
    "backend/app/tools/evidence_selection.py",
    "backend/app/tools/hybrid_retrieval.py",
    "backend/app/tools/matcher.py",
    "backend/app/agents/evidence_workflow.py",
    "backend/app/tests/test_test_source_selection.py",
    "backend/app/tools/evidence_levels.py",
    "backend/app/tests/test_real_matching.py",
    "jianli/src/components/ListPagination.tsx",
    "jianli/src/lib/list-pagination.js",
    "jianli/src/lib/list-pagination.d.ts",
    "jianli/tests/list-pagination.test.mjs",
]

assert not STAGE.exists(), "Preserve previous validation source"
archive = subprocess.check_output(
    ["git", "archive", "--format=zip", BASE, "backend", "jianli", "demo/evidence-api"],
    cwd=ROOT,
)
with zipfile.ZipFile(io.BytesIO(archive)) as package:
    package.extractall(STAGE)
(STAGE / "backend/.tmp").mkdir()
for name in FILES:
    (STAGE / name).write_bytes((ROOT / name).read_bytes())
# Accept the existing narrative integration, but exclude the paused Agent projection.
service = STAGE / "backend/app/services/analysis.py"
text = (ROOT / "backend/app/services/analysis.py").read_text(encoding="utf-8")
paused = '''            ai_process={
                key: value if isinstance(value, str) else None
                for key in ("planningSkippedReason", "skippedReason", "fallbackReason", "failureStage")
                for value in [(report.analysis_metadata or {}).get(key)]
            },
'''
assert text.count(paused) == 1
service.write_text(text.replace(paused, ""), encoding="utf-8", newline="\n")
FILES.append("backend/app/services/analysis.py")
manifest = {
    "baseCommit": BASE,
    "source": str(STAGE),
    "acceptedFiles": {
        name: hashlib.sha256((STAGE / name).read_bytes()).hexdigest() for name in FILES
    },
    "excluded": "All other working-tree changes, including UUID display and paused Agent display",
}
(OUT / "accepted-source.json").write_text(
    json.dumps(manifest, indent=2) + "\n", encoding="utf-8",
)
print(STAGE)
