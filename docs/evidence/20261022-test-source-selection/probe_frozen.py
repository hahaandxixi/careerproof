"""Inspect production selection and the serialized prompt; never call a provider."""
import ast
from dataclasses import asdict
import hashlib
import json
from pathlib import Path
import sys
from uuid import UUID
import zipfile

sys.path.insert(0, str(Path.cwd()))

from app.agents.evidence_workflow import build_evidence_contexts
from app.agents.provider import evidence_analysis_messages
from app.tools.code_analyzer import ProjectFileSnapshot
from app.tools.evidence_context import enrich_evidence
from app.tools.matcher import RequirementInput, match_candidate
from app.tools.resume_parser import parse_resume

assert Path(__import__("app.tools.matcher", fromlist=["__file__"]).__file__).is_relative_to(
    Path.cwd()
), "Probe imported a different source tree"

ROOT = Path(__file__).resolve().parents[3]
OUT = Path(__file__).parent
package = ROOT / "output/demo/CareerProof-campus-signup-v2-runtime.zip"
package_sha = hashlib.sha256(package.read_bytes()).hexdigest()
assert package_sha == "58b3ced4e093d346b7f466d5cc36243639357590d8ab692445d6de9202fb1518"
prefix = "6db170c9-ea2b-4036-84d1-47260c687014/"
with zipfile.ZipFile(package) as archive:
    files = [ProjectFileSnapshot(prefix + name, archive.read(name).decode("utf-8"))
             for name in archive.namelist() if not name.endswith("/")]
previous = json.loads((OUT.parent / (
    "20261021-complete-project-validation/rule-narrative-fix/report-after.json"
)).read_text(encoding="utf-8"))
requirements = [RequirementInput(UUID(item["requirementId"]), item["requirementTitle"],
                                item["skill"], item["weight"]) for item in previous["items"]]
manifest = json.loads((OUT.parent / (
    "20261021-complete-project-validation/material-manifest.json"
)).read_text(encoding="utf-8"))
claims = parse_resume(Path(manifest["resume"]).read_text(encoding="utf-8"))
raw = match_candidate(requirements, claims, files)
expanded = enrich_evidence(raw, files)
contexts = build_evidence_contexts(expanded)
rows = []
for initial, full, context in zip(raw.items, expanded.items, contexts, strict=True):
    for e in context.evidence:
        content = next(f.content for f in files if f.path == e.file_path)
        assert e.snippet == "\n".join(content.splitlines()[e.line_start - 1:e.line_end])
    rows.append({
        "skill": initial.skill, "verdict": initial.verdict,
        "ruleScore": initial.rule_base_score, "formulaVersion": initial.formula_version,
        "candidates": [asdict(e) for e in initial.evidence_list],
        "expanded": [asdict(e) for e in full.evidence_list],
        "sentContext": context.model_dump(mode="json"),
    })
test_file = next(f for f in files if f.path.endswith("tests/test_registration.py"))
test_functions = [n.name for n in ast.walk(ast.parse(test_file.content))
                  if isinstance(n, ast.FunctionDef) and n.name.startswith("test_")]
record = {
    "materialSha256": package_sha, "moduleSource": __import__(
        "app.tools.matcher", fromlist=["__file__"]).__file__,
    "projectVersionId": prefix[:-1], "testFunctionsInFile": test_functions,
    "requirements": rows,
    "preparedMessages": evidence_analysis_messages(contexts),
    "externalRequests": 0,
    "meaning": "Actual production prompt serialization, not a sent request or model response",
}
target = OUT / sys.argv[1]
assert not target.exists(), "Preserve previous probe output"
target.write_text(json.dumps(record, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
print(json.dumps({"out": target.name, "rows": len(rows), "externalRequests": 0}))
