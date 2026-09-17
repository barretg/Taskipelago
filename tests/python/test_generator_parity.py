import json
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "parity"))
import generator_parity  # noqa: E402


class GeneratorGoldenTest(unittest.TestCase):
    def test_golden_matches_legacy_generator(self):
        expected = generator_parity.build_golden()
        actual = json.loads(generator_parity.GOLDEN.read_text(encoding="utf-8"))
        self.assertEqual([i["file"] for i in expected["imports"]], [i["file"] for i in actual["imports"]],
                         "corpus changed: run python tests/parity/generator_parity.py")
        self.assertEqual([e["name"] for e in expected["exports"]], [e["name"] for e in actual["exports"]],
                         "export cases changed: run python tests/parity/generator_parity.py")
        stale = [e.get("file") or e.get("name") for e, a in
                 zip(expected["imports"] + expected["exports"], actual["imports"] + actual["exports"]) if e != a]
        self.assertEqual(stale, [], "golden is stale: run python tests/parity/generator_parity.py")
        self.assertEqual(expected["bingo"], actual["bingo"], "bingo golden is stale: run python tests/parity/generator_parity.py")

    def test_every_era_imports_and_reexports(self):
        golden = json.loads(generator_parity.GOLDEN.read_text(encoding="utf-8"))
        eras = [i for i in golden["imports"] if i["file"].startswith("era_")]
        self.assertGreaterEqual(len(eras), 13)
        for entry in eras:
            self.assertTrue(entry["result"]["ok"], entry["file"])
        reexports = {e["name"]: e["result"] for e in golden["exports"] if e["name"].startswith("reexport:era_")}
        for name, result in reexports.items():
            self.assertIsNotNone(result["data"], name)


if __name__ == "__main__":
    unittest.main()
