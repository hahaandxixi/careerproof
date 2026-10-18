"""Run only previously skipped PG nodes without touching the business database."""

import hashlib
import json
import os
import re
import subprocess
import sys
import xml.etree.ElementTree as ET
from pathlib import Path
from uuid import uuid4

ROOT = Path(__file__).resolve().parents[3]
BACKEND = ROOT / "backend"
OUT = Path(__file__).resolve().parent
PREVIOUS = ROOT / "docs/evidence/20261019-backend-integrated-regression/junit.xml"
ALREADY_VERIFIED = {
    "test_retrieval_filtered_recall":
        "bac255b73aa62576a163860f3dbaa8084b0cf16cf5f7eafffdf7643577e75f6b",
    "test_project_upload_concurrency_postgres":
        "6011aadb0cb8b258e880d171e219230370ddbe9289815a36456bb0eaf3bcb57d",
}


def source_hashes():
    paths = {BACKEND / "pyproject.toml"}
    for directory in ("app", "alembic", "scripts", "evals"):
        paths.update((BACKEND / directory).rglob("*.py"))
    return {
        str(path.relative_to(ROOT)).replace("\\", "/"):
            hashlib.sha256(path.read_bytes()).hexdigest()
        for path in sorted(paths) if "__pycache__" not in path.parts
    }


def save(name, value):
    with (OUT / name).open("x", encoding="utf-8") as handle:
        json.dump(value, handle, ensure_ascii=False, indent=2)


for module, expected in ALREADY_VERIFIED.items():
    path = BACKEND / "app/tests" / f"{module}.py"
    assert hashlib.sha256(path.read_bytes()).hexdigest() == expected

groups = {"regular": [], "hardstop": []}
covered = []
for case in ET.parse(PREVIOUS).getroot().findall(".//testcase"):
    if case.find("skipped") is None:
        continue
    match = re.fullmatch(r"app\.tests\.(test_\w+)", case.attrib["classname"])
    assert match, case.attrib["classname"]
    module = match[1]
    node = f"app/tests/{module}.py::{case.attrib['name']}"
    if module in ALREADY_VERIFIED:
        covered.append(node)
        continue
    group = "hardstop" if module == "test_attempt_hard_stop" else "regular"
    groups[group].append(node)
assert len(covered) == 7 and len(groups["regular"]) == 59 and len(groups["hardstop"]) == 8
save("selected-nodes.json", {"priorUnchangedPG": covered, **groups})
before = source_hashes()
save("source-hashes-before.json", before)
head = subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=ROOT, text=True).strip()
results = {"sourceHead": head, "selected": 67, "excludedPriorVerified": 7, "groups": {}}
for name, nodes in groups.items():
    temp = BACKEND / f".tmp-pg-skips-20261019-{name}-{uuid4().hex}"
    temp.mkdir()
    env = os.environ.copy()
    database = "careerproof" if name == "hardstop" else "cp_ci"
    env.update({
        "APP_ENV": "test", "DEBUG": "false", "AI_PROVIDER": "mock",
        "AI_EXTERNAL_ENABLED": "false", "PYTHONIOENCODING": "utf-8",
        "DEEPSEEK_API_KEY": "", "ZHIPU_API_KEY": "",
        "DATABASE_URL": f"sqlite+aiosqlite:///{temp.as_posix()}/unbound.db",
        "STORAGE_BASE_DIR": str(temp / "storage"),
        "CAREERPROOF_TEST_DATABASE_URL":
            f"postgresql+asyncpg://ci:ci@127.0.0.1:55436/{database}",
    })
    command = [sys.executable, "-m", "pytest", *nodes, "-p", "no:cacheprovider",
               f"--basetemp={temp / 'pytest'}", f"--junitxml={OUT / (name + '.xml')}"]
    save(f"{name}-command.json", command)
    print(f"Running {name}: {len(nodes)} previously skipped nodes", flush=True)
    with (OUT / f"{name}.raw.out").open("xb") as handle:
        process = subprocess.run(command, cwd=BACKEND, env=env, stdout=handle,
                                 stderr=subprocess.STDOUT, check=False)
    results["groups"][name] = {"selected": len(nodes), "exitCode": process.returncode}
    print(f"{name} exit={process.returncode}", flush=True)
after = source_hashes()
save("source-hashes-after.json", after)
results["sourceUnchangedDuringRun"] = before == after
save("run-results.json", results)
sys.exit(0 if before == after and all(
    group["exitCode"] == 0 for group in results["groups"].values()
) else 1)
