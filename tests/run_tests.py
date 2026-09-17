#!/usr/bin/env python3
"""
Taskipelago regression suite. Run after any major change:

    python tests/run_tests.py            # everything
    python tests/run_tests.py python     # Python tests only
    python tests/run_tests.py js         # Node tests only

Python tests use only the stdlib plus PyYAML. JS tests need Node 20+; jsdom is
installed into tests/node_modules on first run.
"""
from __future__ import annotations

import os
import shutil
import subprocess
import sys

TESTS = os.path.dirname(os.path.abspath(__file__))


def run_python() -> int:
    print("== Python tests", flush=True)
    return subprocess.run([
        sys.executable, "-m", "unittest", "discover",
        "-s", os.path.join(TESTS, "python"), "-t", os.path.join(TESTS, "python"),
        "-p", "test_*.py",
    ]).returncode


def run_js() -> int:
    print("== JS tests", flush=True)
    node = shutil.which("node")
    if not node:
        print("node not found; skipping JS tests (install Node 20+)")
        return 1
    if not os.path.isdir(os.path.join(TESTS, "node_modules", "jsdom")):
        npm = shutil.which("npm")
        if not npm:
            print("npm not found; cannot install jsdom for the JS tests")
            return 1
        print("installing test dependencies into tests/node_modules", flush=True)
        rc = subprocess.run([npm, "install", "--no-audit", "--no-fund"], cwd=TESTS).returncode
        if rc:
            return rc
    files = []
    for root, _dirs, names in os.walk(os.path.join(TESTS, "js")):
        files += [os.path.join(root, n) for n in names if n.endswith(".test.mjs")]
    # --test-force-exit: the app's heartbeat timers and jsdom keep test processes alive.
    # PYTHON: the generator parity test reads JS export text back with PyYAML.
    env = {**os.environ, "PYTHON": sys.executable}
    return subprocess.run([node, "--test", "--test-force-exit", *sorted(files)], cwd=TESTS, env=env).returncode


def main(argv: list) -> int:
    which = argv[1] if len(argv) > 1 else "all"
    rc = 0
    if which in ("all", "python"):
        rc |= run_python()
    if which in ("all", "js"):
        rc |= run_js()
    print("ALL PASSED" if rc == 0 else "FAILURES")
    return rc


if __name__ == "__main__":
    sys.exit(main(sys.argv))
