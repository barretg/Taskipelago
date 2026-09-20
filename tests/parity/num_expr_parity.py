"""Numeric expression parser/evaluator parity corpus (clicker mode).

num_expr_corpus.json holds the expressions. Running this file regenerates
num_expr_golden.json from the Python implementation
(custom_worlds/taskipelago/prereq_parser.py: parse_num_expr / eval_num_expr):

    python tests/parity/num_expr_parity.py

tests/python/test_num_expr_parity.py checks the golden file still matches
Python, and tests/js/shared/num_expr.test.mjs checks the JS port
(web-client/js/shared/num_expr.js) against it.
"""
from __future__ import annotations

import json
from pathlib import Path

from prereq_parity import load_parser  # same directory

HERE = Path(__file__).resolve().parent
CORPUS = HERE / "num_expr_corpus.json"
GOLDEN = HERE / "num_expr_golden.json"


def run_case(parser, case: dict, bindings: list) -> dict:
    try:
        ast = parser.parse_num_expr(
            case["text"], case.get("label", "numeric expression"),
            case.get("location_label"), case.get("allow_live", True),
        )
    except Exception as e:  # the message text is part of the contract
        return {"error": str(e)}
    out = {
        "ast": json.loads(json.dumps(ast)),
        "constants": sorted(parser.num_expr_constants(ast)),
        "static": parser.num_expr_is_static(ast),
        "values": [],
    }
    for b in bindings:
        try:
            v = parser.eval_num_expr(ast, b)
            out["values"].append({"v": round(v, 10), "i": parser.num_expr_to_int(v)})
        except Exception as e:
            out["values"].append({"error": str(e)})
    return out


def build_golden() -> dict:
    parser = load_parser()
    corpus = json.loads(CORPUS.read_text(encoding="utf-8"))
    bindings = corpus["bindings"]
    return {
        "bindings": bindings,
        "cases": [dict(c, result=run_case(parser, c, bindings)) for c in corpus["cases"]],
    }


if __name__ == "__main__":
    GOLDEN.write_text(json.dumps(build_golden(), ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    print(f"wrote {GOLDEN}")
