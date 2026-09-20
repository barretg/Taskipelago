import json
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "parity"))
import num_expr_parity  # noqa: E402


class NumExprGoldenTest(unittest.TestCase):
    def test_golden_matches_python_parser(self):
        expected = num_expr_parity.build_golden()
        actual = json.loads(num_expr_parity.GOLDEN.read_text(encoding="utf-8"))
        self.assertEqual(len(expected["cases"]), len(actual["cases"]),
                         "corpus changed: run python tests/parity/num_expr_parity.py")
        mismatches = [
            (e["text"], a["result"], e["result"])
            for e, a in zip(expected["cases"], actual["cases"]) if e != a
        ]
        self.assertEqual(mismatches, [],
                         "golden is stale (golden, python): run python tests/parity/num_expr_parity.py")

    def test_integer_fields_round_up_with_a_floor_of_one(self):
        golden = json.loads(num_expr_parity.GOLDEN.read_text(encoding="utf-8"))
        by_text = {c["text"]: c["result"] for c in golden["cases"]}
        self.assertEqual(by_text["1.5"]["values"][0]["i"], 2)
        self.assertEqual(by_text["0"]["values"][0]["i"], 1)
        self.assertEqual(by_text["7 / 2"]["values"][0]["i"], 4)

    def test_live_constants_are_rejected_when_disallowed(self):
        golden = json.loads(num_expr_parity.GOLDEN.read_text(encoding="utf-8"))
        live = [c for c in golden["cases"]
                if c.get("allow_live") is False and c["text"] != "N_TASKS"]
        self.assertEqual(len(live), 3)
        for case in live:
            self.assertIn("changes during play", case["result"]["error"])


if __name__ == "__main__":
    unittest.main()
