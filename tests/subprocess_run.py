"""Bounded subprocess helper for the test suite (db-3jcu).

Every subprocess.run call in tests/ must either import run() from here or
carry an explicit timeout=. The default lives here so raising it means one
edit rather than a grep-and-replace, and TimeoutExpired surfaces as a named
pytest failure instead of a silent hang that blocks the entire suite.
"""
import subprocess
import time

DEFAULT_TIMEOUT = 60  # seconds; enough for any single shell script under test


def run(cmd, *, timeout=DEFAULT_TIMEOUT, **kwargs):
    """subprocess.run with a mandatory timeout.

    TimeoutExpired is re-raised as AssertionError that names the command and
    the elapsed time so pytest records which test hung rather than dying mid-
    progress-bar with no label.
    """
    start = time.monotonic()
    try:
        return subprocess.run(cmd, timeout=timeout, **kwargs)
    except subprocess.TimeoutExpired:
        elapsed = time.monotonic() - start
        cmd_str = " ".join(str(c) for c in cmd) if isinstance(cmd, (list, tuple)) else str(cmd)
        raise AssertionError(
            f"subprocess timed out after {elapsed:.1f}s: {cmd_str}"
        ) from None
