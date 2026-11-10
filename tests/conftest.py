"""Test-wide setup. The listener writes .browser/listener.log through a module-level file handle;
tests that mock faults (RuntimeError("disk full")) used to append those lines to the LIVE log
and made a real "disk full" look likely (2026-11-10, decision 104). Every test session points
that handle at a temporary file instead."""
import os
import tempfile

import pytest


@pytest.fixture(autouse=True, scope="session")
def _listener_log_to_temp():
    try:
        import listener
    except Exception:  # noqa: BLE001 — a test run without the listener still runs
        yield
        return
    fd, path = tempfile.mkstemp(prefix="listener-test-", suffix=".log")
    os.close(fd)
    old = listener._log_f
    listener._log_f = open(path, "a", encoding="utf-8")  # noqa: SIM115 — closed below
    yield
    listener._log_f.close()
    listener._log_f = old
    os.remove(path)
