"""Package custom_worlds/taskipelago into out/taskipelago.apworld.

Usage: python build_apworld.py [--list] [--out DIR]
  --list  print the files that would be packaged and exit without writing
  --out   output directory (default: out/)
"""
import argparse
import json
import sys
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent
WORLD = ROOT / "custom_worlds" / "taskipelago"
SKIP_DIRS = {"__pycache__", "node_modules", ".git"}
SKIP_SUFFIXES = {".pyc", ".pyo"}


def world_files():
    for path in sorted(WORLD.rglob("*")):
        rel = path.relative_to(WORLD)
        if not path.is_file():
            continue
        if any(part in SKIP_DIRS or part.startswith(".") for part in rel.parts):
            continue
        if path.suffix in SKIP_SUFFIXES:
            continue
        yield path, rel


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--list", action="store_true")
    parser.add_argument("--out", type=Path, default=ROOT / "out")
    args = parser.parse_args()

    files = list(world_files())
    names = {rel.as_posix() for _, rel in files}
    for required in ("__init__.py", "archipelago.json", "webhost.py", "web-client/index.html"):
        if required not in names:
            sys.exit(f"missing required file: {required}")
    manifest = json.loads((WORLD / "archipelago.json").read_text(encoding="utf-8"))

    if args.list:
        for _, rel in files:
            print(f"{WORLD.name}/{rel.as_posix()}")
        print(f"{len(files)} files, world_version {manifest.get('world_version')}")
        return

    args.out.mkdir(parents=True, exist_ok=True)
    target = args.out / f"{WORLD.name}.apworld"
    with zipfile.ZipFile(target, "w", zipfile.ZIP_DEFLATED) as zf:
        for path, rel in files:
            zf.write(path, f"{WORLD.name}/{rel.as_posix()}")
    print(f"wrote {target} ({len(files)} files, world_version {manifest.get('world_version')})")


if __name__ == "__main__":
    main()
