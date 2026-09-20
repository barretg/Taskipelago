"""Prereq/cost parser parity corpus (UNIFY 5.4).

prereq_corpus.json holds the expressions. Running this file regenerates
prereq_golden.json from the Python parser (custom_worlds/taskipelago/prereq_parser.py):

    python tests/parity/prereq_parity.py

tests/python/test_prereq_parity.py checks the golden file still matches Python,
and tests/js/shared/prereq_parser.test.mjs checks the JS port against it. Only
regenerate after a deliberate parser change that lands in both implementations.
"""
from __future__ import annotations

import importlib.util
import json
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
CORPUS = HERE / "prereq_corpus.json"
GOLDEN = HERE / "prereq_golden.json"
PARSER = ROOT / "custom_worlds" / "taskipelago" / "prereq_parser.py"


def load_parser():
    spec = importlib.util.spec_from_file_location("taskipelago_prereq_parser", PARSER)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def expand_cases(corpus: dict) -> list:
    cases = []
    for case in corpus["cases"]:
        merged = dict(corpus["defaults"][case["kind"]])
        merged.update(case)
        cases.append(merged)
    return cases


def run_case(parser, case: dict) -> dict:
    try:
        if case["kind"] == "prereq":
            groups = case.get("groups")
            regions = case.get("regions")
            ast = parser.parse_prereq(
                case["text"], case["n"], case["task_index"], case["label"],
                known_groups=set(groups) if groups is not None else None,
                known_regions=set(regions) if regions is not None else None,
                location_label=case.get("location_label"),
            )
        else:
            ast = parser.parse_cost_expr(case["text"], set(case["consumables"]), case.get("items"), case.get("n_tasks", 0))
        return {"ast": json.loads(json.dumps(ast))}
    except Exception as e:  # the message text is part of the contract
        return {"error": str(e)}


def build_golden() -> dict:
    parser = load_parser()
    corpus = json.loads(CORPUS.read_text(encoding="utf-8"))
    cases = expand_cases(corpus)
    return {"cases": [dict(case, result=run_case(parser, case)) for case in cases]}


def dump(golden: dict) -> str:
    return json.dumps(golden, ensure_ascii=False, indent=1) + "\n"


if __name__ == "__main__":
    GOLDEN.write_text(dump(build_golden()), encoding="utf-8")
    print(f"wrote {GOLDEN}")
