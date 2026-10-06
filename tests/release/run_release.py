"""Release suite: full Archipelago generation of the packaged apworld.

Run through tests/run_tests.py --release, which picks the interpreter and
checks that the apworld matches the sources. Runs directly as:

    <ap python> tests/release/run_release.py --ap PATH --apworld PATH [--seeds N]

Each directory under tests/release/cases/ is one multiworld (every *.yaml in it
is a player), plus EXTRA_CASES below for YAMLs that live elsewhere. Every case
is generated with full output (spoiler and multidata zip) for each seed, using
a temporary user folder so the Archipelago checkout is never modified.

Checks per generation:
  - generation finishes and writes exactly one output zip
  - no "early" warnings from Fill.distribute_early_items
  - every item flagged early (item_early / group_early) is registered in
    multiworld.early_items and was placed in sphere 1
  - an optional expect.json in the case directory:
        {"early": {"<player name>": [1-based pool indices flagged early]}}
"""
from __future__ import annotations

import argparse
import json
import logging
import os
import shutil
import sys
import tempfile
import traceback
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
CASES = HERE / "cases"
GAME = "Taskipelago"

# Cases whose YAMLs are shared with other suites.
EXTRA_CASES = {
    "task_adventure": [ROOT / "tests" / "python" / "fixtures" / "task_adventure.yaml"],
}


class _Collect(logging.Handler):
    def __init__(self):
        super().__init__(logging.WARNING)
        self.messages: list[str] = []

    def emit(self, record):
        self.messages.append(record.getMessage())


def discover_cases() -> dict[str, list[Path]]:
    cases = {name: list(paths) for name, paths in EXTRA_CASES.items()}
    for d in sorted(p for p in CASES.iterdir() if p.is_dir()):
        cases[d.name] = sorted(d.glob("*.yaml"))
    return cases


def check_world(mw, expect: dict) -> list[str]:
    """Return failure messages for one generated multiworld."""
    errors = []
    spheres = mw.get_spheres()
    sphere1 = next(spheres, set())
    placed = {(loc.item.name, loc.item.player): loc for loc in mw.get_filled_locations()}
    expected_early = expect.get("early", {})
    for p in mw.player_ids:
        if mw.game[p] != GAME:
            continue
        w = mw.worlds[p]
        pname = mw.player_name[p]
        flagged = [i for i, f in enumerate(w._item_early) if f]
        if pname in expected_early and [i + 1 for i in flagged] != expected_early[pname]:
            errors.append(f"{pname}: early pool indices {[i + 1 for i in flagged]}, "
                          f"expected {expected_early[pname]}")
        names = [w._reward_item_names[i] for i in flagged]
        registered = dict(mw.early_items[p])
        if registered != {n: 1 for n in names}:
            errors.append(f"{pname}: multiworld.early_items is {registered}, expected {names}")
        for n in names:
            loc = placed.get((n, p))
            if loc is None:
                errors.append(f"{pname}: early item {n!r} was not placed")
            elif loc not in sphere1:
                errors.append(f"{pname}: early item {n!r} is at {loc.name} "
                              f"({mw.player_name[loc.player]}), not in sphere 1")
    return errors


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description="Taskipelago release generation suite")
    parser.add_argument("--ap", required=True, help="Archipelago source checkout")
    parser.add_argument("--apworld", required=True, help="packaged taskipelago.apworld")
    parser.add_argument("--seeds", type=int, default=5, help="seeds per case (default 5)")
    parser.add_argument("--keep", action="store_true", help="keep the temp folder and print its path")
    args = parser.parse_args(argv)

    ap = Path(args.ap).resolve()
    apworld = Path(args.apworld).resolve()
    cases = discover_cases()

    tmp = Path(tempfile.mkdtemp(prefix="taskipelago_release_"))
    (tmp / "worlds").mkdir()
    shutil.copy2(apworld, tmp / "worlds" / apworld.name)

    # Archipelago reads host.yaml and custom worlds from user_path; pointing it at the
    # temp folder (before worlds is imported) keeps the checkout untouched.
    sys.path.insert(0, str(ap))
    os.chdir(tmp)
    import Utils
    Utils.user_path.cached_path = str(tmp)
    import settings
    host = settings.get_settings()
    host._filename = None
    host.generator.players = 0
    host.generator.race = 0
    import Generate
    import Main

    logging.basicConfig(level=logging.WARNING, format="    %(levelname)s %(message)s")
    collect = _Collect()
    logging.getLogger().addHandler(collect)

    failures = 0
    runs = 0
    for name, paths in cases.items():
        players = tmp / "cases" / name
        players.mkdir(parents=True)
        for path in paths:
            shutil.copy2(path, players / path.name)
        expect_file = CASES / name / "expect.json"
        expect = json.loads(expect_file.read_text(encoding="utf-8")) if expect_file.is_file() else {}
        for seed in range(1, args.seeds + 1):
            runs += 1
            out = tmp / "output" / f"{name}_{seed}"
            collect.messages.clear()
            try:
                gen_args = Generate.mystery_argparse([
                    "--seed", str(seed), "--player_files_path", str(players), "--outputpath", str(out),
                ])
                mw = Main.main(*Generate.main(gen_args))
                errors = check_world(mw, expect)
                zips = list(out.glob("*.zip"))
                if len(zips) != 1:
                    errors.append(f"expected one output zip, found {len(zips)}")
                errors += [f"log: {m}" for m in collect.messages if "early" in m.lower()]
            except Exception:
                errors = [traceback.format_exc()]
            if errors:
                failures += 1
                print(f"FAIL {name} seed {seed}")
                for e in errors:
                    print(f"    {e}")
            else:
                print(f"ok   {name} seed {seed}")

    if args.keep:
        print(f"kept {tmp}")
    else:
        shutil.rmtree(tmp, ignore_errors=True)
    print(f"release: {runs - failures}/{runs} generations passed")
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
