import ast
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "parity"))
import legacy_text  # noqa: E402


class LegacyTextTest(unittest.TestCase):
    def test_generated_text_matches_legacy_client(self):
        self.assertEqual(legacy_text.OUT.read_text(encoding="utf-8"), legacy_text.render(),
                         "run python tests/parity/legacy_text.py")

    def test_expected_entries_present(self):
        tree = ast.parse(legacy_text.CLIENT.read_text(encoding="utf-8"))
        self.assertEqual(len(legacy_text.legacy_steps(tree)), 18)
        self.assertEqual(sorted(legacy_text.legacy_tips(tree)), [
            "consumable", "cost_col", "count_item", "count_task", "filler", "goal_tasks", "item_prereq",
            "pg_hint", "priority_col", "prog_group", "region_col", "reward_preview", "rg_hint",
            "task_prereq", "type",
        ])


if __name__ == "__main__":
    unittest.main()
