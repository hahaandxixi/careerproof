"""Read-only-source diagnostic: real synthetic API case, worker stderr capture.

Run from the accepted backend directory with external AI disabled. The extra
autouse fixture repeats only this case; original assertions remain unchanged.
"""

import argparse
import hashlib
import json
import subprocess
import sys
import threading
from pathlib import Path

import pytest

sys.path.insert(0, str(Path.cwd()))
parser = argparse.ArgumentParser()
parser.add_argument("--repeats", type=int, default=12)
parser.add_argument("--log", type=Path, required=True)
parser.add_argument("--basetemp", required=True)
options = parser.parse_args()
original_popen = subprocess.Popen
write_lock = threading.Lock()
current = {"iteration": None}


class CapturingPopen(original_popen):
    def __init__(self, *args, **kwargs):
        command = kwargs.get("args", args[0] if args else [])
        self.diagnostic_worker = (
            isinstance(command, (tuple, list)) and "app.services.isolated_worker" in command
        )
        self.diagnostic_iteration = current["iteration"]
        if self.diagnostic_worker:
            kwargs["stderr"] = subprocess.PIPE
        super().__init__(*args, **kwargs)

    def communicate(self, *args, **kwargs):
        if not self.diagnostic_worker:
            return super().communicate(*args, **kwargs)
        try:
            stdout, stderr = super().communicate(*args, **kwargs)
        except BaseException as error:
            self.record({"exception": type(error).__name__, "detail": str(error)})
            raise
        self.record({
            "stdoutBytes": len(stdout or b""),
            "stderr": (stderr or b"").decode("utf-8", errors="replace"),
        })
        return stdout, stderr

    def record(self, extra):
        record = {
            "iteration": self.diagnostic_iteration,
            "pid": self.pid,
            "returncode": self.returncode,
            **extra,
        }
        with write_lock, options.log.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(record, ensure_ascii=True) + "\n")


class Repetition:
    @pytest.fixture(autouse=True, params=range(options.repeats))
    def diagnostic_iteration(self, request):
        current["iteration"] = request.param
        yield
        current["iteration"] = None


hashes = {
    str(path): hashlib.sha256(path.read_bytes()).hexdigest()
    for path in (
        Path("app/services/task_runner.py"),
        Path("app/services/worker_identity.py"),
        Path("app/services/isolated_worker.py"),
    )
}
print(json.dumps({"cwd": str(Path.cwd()), "sourceSha256": hashes}), flush=True)
subprocess.Popen = CapturingPopen
raise SystemExit(pytest.main([
    "app/tests/test_real_matching.py::test_job_recommendations_rank_owned_material_evidence",
    "-q", "-p", "no:cacheprovider", "--basetemp=" + options.basetemp,
], plugins=[Repetition()]))
