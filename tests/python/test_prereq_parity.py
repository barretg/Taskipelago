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

    def test_f8_suffix_on_names_with_non_letters(self):
        golden = json.loads(prereq_parity.GOLDEN.read_text(encoding="utf-8"))
        f8 = {c["text"]: c["result"] for c in golden["cases"] if c.get("f8")}
        self.assertEqual(f8["weapons+*3"], {"ast": ["group_count", "weapons+", 3]})
        self.assertEqual(f8["weapons+-2"], {"ast": ["group_ref", "weapons+", 2]})
        self.assertEqual(f8["weap-*2"], {"ast": ["group_count", "weap-", 2]})
        self.assertEqual(f8["side-quests!*2"], {"ast": ["group_count", "side-quests!", 2]})
        self.assertEqual(f8["x--3"], {"ast": ["region_ref", "x-", 3]})
        self.assertEqual(f8["my-group-3"], {"ast": ["group_ref", "my-group", 3]})


if __name__ == "__main__":
    unittest.main()
