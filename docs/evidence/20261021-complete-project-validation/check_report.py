"""Compare persisted report sources with frozen bytes, without editing either."""
import hashlib
import json
from pathlib import Path
import zipfile

ROOT = Path(__file__).resolve().parents[3]
EVIDENCE = Path(__file__).parent
manifest = json.loads((EVIDENCE / "material-manifest.json").read_text(encoding="utf-8"))
report = json.loads((EVIDENCE / "report.json").read_text(encoding="utf-8"))
files = json.loads((EVIDENCE / "project-files.json").read_text(encoding="utf-8"))
previews = json.loads((EVIDENCE / "project-previews.json").read_text(encoding="utf-8"))
plan = json.loads((EVIDENCE / "evaluation-plan.json").read_text(encoding="utf-8"))
sha = lambda data: hashlib.sha256(data).hexdigest()
assert sha(Path(manifest["zip"]).read_bytes()) == manifest["zipSha256"]
with zipfile.ZipFile(manifest["zip"]) as archive:
    frozen = {name: archive.read(name) for name in archive.namelist()}
assert {name: sha(body) for name, body in frozen.items()} == manifest["files"]
assert {row["relativePath"] for row in files} == set(frozen)
file_by_id = {row["id"]: row for row in files}
for preview in previews:
    assert preview["projectVersionId"] == report["materials"][1]["id"]
    # Preview drops the final newline; line contents, not binary file identity,
    # are the preview contract. Raw upload hashes are checked separately below.
    assert preview["content"].splitlines() == frozen[preview["relativePath"]].decode("utf-8").splitlines()
citations = []
coverage = []
for item, criterion in zip(report["items"], plan["requirements"], strict=True):
    assert item["requirementTitle"] == criterion["requirement"]
    selected = []
    for evidence in item["evidenceList"]:
        path = evidence["filePath"]
        suffixes = [name for name in frozen if path == name or path.endswith("/" + name)]
        assert len(suffixes) == 1, path
        source = suffixes[0]
        lines = frozen[source].decode("utf-8").splitlines()
        start, end = evidence["lineStart"], evidence["lineEnd"]
        assert 1 <= start <= end <= len(lines)
        assert evidence["snippet"] == "\n".join(lines[start - 1:end]), (path, start, end)
        assert evidence["contentHash"] == sha(frozen[source]), (path, "hash")
        assert evidence["projectVersionId"] == report["materials"][1]["id"]
        assert evidence["projectFileId"] in file_by_id
        row = {"requirement": criterion["key"], "citationId": evidence.get("citationId"),
               "file": source, "start": start, "end": end, "type": evidence["evidenceType"],
               "snippetExact": True, "hashExact": True, "versionExact": True}
        citations.append(row)
        selected.append(row)
    coverage.append({"key": criterion["key"], "skill": item["skill"], "verdict": item["verdict"],
                     "level": item["evidenceLevel"], "levelLabel": item["evidenceLevelLabel"],
                     "explanation": item["explanation"], "gap": item["evidenceLevelGap"],
                     "expectedSourceFiles": criterion["source"],
                     "actualSourceFiles": sorted({row["file"] for row in selected}),
                     "modelCitations": [row for row in selected if row["citationId"]],
                     "candidateOnly": [row for row in selected if not row["citationId"]]})
assert report["analysisMode"] == "rules" and report["aiProvider"] is None
assert all(item["aiStatus"] == "not_used" for item in report["items"])
result = {"reportId": report["id"], "filesAccepted": len(files), "frozenFiles": len(frozen),
          "everyPreviewMatchesFrozenLines": True, "previewNormalizesFinalNewline": True,
          "evidenceEntries": len(citations),
          "allEvidenceExact": True, "allEvidenceSameSelectedVersion": True,
          "actualRulePipelineNotMock": True, "requirements": coverage,
          "citationChecks": citations, "semanticCompletenessNotProvenBySourceExactness": True}
(EVIDENCE / "source-verification.json").write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
print(f"PASS: {len(files)} uploaded files; {len(citations)} evidence entries match exact source, lines, SHA and selected version.")
for row in coverage:
    print(row["key"], row["verdict"], row["levelLabel"],
          [(citation["file"], citation["start"], citation["end"]) for citation in row["modelCitations"]])
