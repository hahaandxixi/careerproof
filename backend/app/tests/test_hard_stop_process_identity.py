"""Process relationship checks never require a database or external transport."""

import json
import os
import subprocess
import sys
from types import SimpleNamespace

import pytest

from app.tests.test_attempt_hard_stop import WorkerProcess, assert_spawned_worker


@pytest.mark.parametrize(("worker_pid", "parent_pid", "accepted"), [
    (200, 100, True),   # Direct Linux interpreter: worker is Popen child.
    (201, 200, True),   # Windows venv launcher -> worker interpreter.
    (200, 999, False),  # Reused child pid with unrelated parent.
    (999, 100, False),  # Sibling process, not the launched child.
    (999, 888, False),  # Unrelated process.
])
def test_spawned_worker_identity(worker_pid, parent_pid, accepted):
    worker = SimpleNamespace(pid=worker_pid, parent_pid=parent_pid)
    child = SimpleNamespace(pid=200, poll=lambda: None)
    if accepted:
        assert_spawned_worker(worker, child, spawning_pid=100)
    else:
        with pytest.raises(AssertionError):
            assert_spawned_worker(worker, child, spawning_pid=100)


def test_spawned_worker_rejects_exited_launcher():
    child = SimpleNamespace(pid=200, poll=lambda: 1)
    with pytest.raises(AssertionError, match="already exited"):
        assert_spawned_worker(SimpleNamespace(pid=201, parent_pid=200), child,
                              spawning_pid=100)


@pytest.mark.parametrize("executable", sorted({sys.executable, sys._base_executable}))
def test_actual_interpreter_relationship(executable):
    child = subprocess.Popen([
        executable, "-u", "-c",
        "import json,os,time;print(json.dumps({'pid':os.getpid()}),flush=True);time.sleep(60)",
    ], stdout=subprocess.PIPE, text=True)
    worker = None
    try:
        identity = json.loads(child.stdout.readline())
        worker = WorkerProcess(identity["pid"])
        assert_spawned_worker(worker, child, spawning_pid=os.getpid())
    finally:
        if worker:
            # Both valid process shapes reach actual kill+wait, never just PID validation.
            assert worker.terminate_and_wait(10) != 0
            worker.close()
        elif child.poll() is None:
            child.kill()
        child.wait(timeout=10)
        child.stdout.close()
