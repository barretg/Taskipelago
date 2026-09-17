import json
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "parity"))
import prereq_parity  # noqa: E402


class PrereqGoldenTest(unittest.TestCase):
    def test_golden_matches_python_parser(self):
        expected = prereq_parity.build_golden()
        actual = json.loads(prereq_parity.GOLDEN.read_text(encoding="utf-8"))
        mismatches = [
            (e["kind"], e["text"], a["result"], e["result"])
            for e, a in zip(expected["cases"], actual["cases"])
            if e != a
        ]
        self.assertEqual(len(expected["cases"]), len(actual["cases"]),
                         "corpus changed: run python tests/parity/prereq_parity.py")
        self.assertEqual(mismatches, [],
                         "golden is stale (golden, python): run python tests/parity/prereq_parity.py")

    def test_f8_cases_record_current_behavior(self):
        golden = json.loads(prereq_parity.GOLDEN.read_text(encoding="utf-8"))
        f8 = {c["text"]: c["result"] for c in golden["cases"] if c.get("f8")}
        # Until Phase A (F8) these names cannot carry a -N / *N suffix.
        self.assertEqual(f8["weapons+*3"], {"error": "Taskipelago: unknown name 'weapons+*3' in task prereq on task 5."})
        self.assertEqual(f8["weapons+-2"], {"error": "Taskipelago: unknown name 'weapons+-2' in task prereq on task 5."})
        self.assertEqual(f8["weap-*2"], {"error": "Taskipelago: unknown name 'weap-*2' in task prereq on task 5."})
        self.assertEqual(f8["my-group-3"], {"ast": ["group_ref", "my-group", 3]})


if __name__ == "__main__":
    unittest.main()
