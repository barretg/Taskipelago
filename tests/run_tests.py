#!/usr/bin/env python3
"""
Taskipelago regression suite. Run after any major change:

    python tests/run_tests.py            # everything
    python tests/run_tests.py python     # Python tests only
    python tests/run_tests.py js         # Node tests only

Before a release, add --release to also run the full-generation suite
(tests/release/run_release.py) against an Archipelago source checkout:

    python tests/run_tests.py --release [--ap PATH] [--apworld PATH] [--seeds N]

--ap defaults to $TASKIPELAGO_AP_SRC, else ../MoreProjects/Archipelago-src next to
this repo; its .venv interpreter is used when present. --apworld defaults to
out/taskipelago.apworld and must match the current sources (repackage with
python build_apworld.py if it does not).

Python tests use only the stdlib plus PyYAML. JS tests need Node 20+; jsdom is
installed into tests/node_modules on first run.
"""
from __future__ import annotations

import argparse
import os
import shutil
import subprocess
import sys
import zipfile

TESTS = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(TESTS)
DEFAULT_AP = os.environ.get("TASKIPELAGO_AP_SRC") or os.path.join(
    os.path.dirname(ROOT), "MoreProjects", "Archipelago-src")
DEFAULT_APWORLD = os.path.join(ROOT, "out", "taskipelago.apworld")


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


def stale_apworld_files(apworld: str) -> list:
    """Paths that differ between the packaged apworld and build_apworld.py's file list."""
    sys.path.insert(0, ROOT)
    import build_apworld
    expected = {f"{build_apworld.WORLD.name}/{rel.as_posix()}": path for path, rel in build_apworld.world_files()}
    with zipfile.ZipFile(apworld) as zf:
        packaged = set(zf.namelist())
        diff = sorted(packaged ^ set(expected))
        diff += sorted(n for n in packaged & set(expected) if zf.read(n) != expected[n].read_bytes())
    return diff


def ap_python(ap: str) -> str:
    for rel in (os.path.join(".venv", "bin", "python"), os.path.join(".venv", "Scripts", "python.exe")):
        if os.path.isfile(os.path.join(ap, rel)):
            return os.path.join(ap, rel)
    return sys.executable


def run_release(ap: str, apworld: str, seeds: int) -> int:
    print("== Release generation tests", flush=True)
    if not os.path.isfile(os.path.join(ap, "Generate.py")):
        print(f"no Archipelago checkout at {ap}; pass --ap PATH or set TASKIPELAGO_AP_SRC")
        return 1
    if not os.path.isfile(apworld):
        print(f"{apworld} not found; package it with python build_apworld.py")
        return 1
    stale = stale_apworld_files(apworld)
    if stale:
        print(f"{apworld} does not match the sources; repackage with python build_apworld.py")
        for n in stale[:20]:
            print(f"    {n}")
        return 1
    return subprocess.run([
        ap_python(ap), os.path.join(TESTS, "release", "run_release.py"),
        "--ap", ap, "--apworld", apworld, "--seeds", str(seeds),
    ]).returncode


def main(argv: list) -> int:
    parser = argparse.ArgumentParser(description="Taskipelago regression suite")
    parser.add_argument("which", nargs="?", default="all", choices=("all", "python", "js"))
    parser.add_argument("--release", action="store_true",
                        help="also run full Archipelago generation (release prep only)")
    parser.add_argument("--ap", default=DEFAULT_AP, help=f"Archipelago source checkout (default {DEFAULT_AP})")
    parser.add_argument("--apworld", default=DEFAULT_APWORLD, help="packaged apworld to test")
    parser.add_argument("--seeds", type=int, default=5, help="seeds per release case (default 5)")
    args = parser.parse_args(argv[1:])
    rc = 0
    if args.which in ("all", "python"):
        rc |= run_python()
    if args.which in ("all", "js"):
        rc |= run_js()
    if args.release:
        rc |= run_release(os.path.abspath(args.ap), os.path.abspath(args.apworld), args.seeds)
    print("ALL PASSED" if rc == 0 else "FAILURES")
    return rc


if __name__ == "__main__":
    sys.exit(main(sys.argv))
