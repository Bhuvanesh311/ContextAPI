"""Which parser sandboxes are orphans: their worker process is gone."""

import os
import socket
import subprocess
import sys
import time

from app.knowledge.parsing.sandbox.pool import _owner_alive


def _worker_id(pid: int) -> str:
    return f"sandbox-{socket.gethostname()}-{pid}-1"


def test_running_owner_is_alive():
    assert _owner_alive(_worker_id(os.getpid()), client=None)


def test_killed_owner_not_yet_reaped_is_dead():
    # A stop request kills the worker process; until its parent reaps it,
    # it is a zombie that still answers kill(pid, 0).
    child = subprocess.Popen([sys.executable, "-c", "pass"])
    try:
        for _ in range(50):
            with open(f"/proc/{child.pid}/status") as status:
                if "\nState:\tZ" in status.read():
                    break
            time.sleep(0.05)
        assert not _owner_alive(_worker_id(child.pid), client=None)
    finally:
        child.wait()


def test_vanished_owner_is_dead():
    child = subprocess.Popen([sys.executable, "-c", "pass"])
    child.wait()
    assert not _owner_alive(_worker_id(child.pid), client=None)
