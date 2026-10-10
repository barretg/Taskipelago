"""Disabled regions and item groups (region_disabled / group_disabled)."""
from __future__ import annotations

import contextlib
import importlib
import io
import unittest

from ap_harness import _PKG, generate, load_world

load_world()
disable = importlib.import_module(_PKG + ".disable")


def _quiet(**kw):
    with contextlib.redirect_stderr(io.StringIO()):
        return generate(**kw)


# Task 2 (Mop) and task 3 (Dust) are in Attic; items 2 (Key A) and 3 (Key B) are in keys.
BASE = dict(
    tasks=["Sweep", "Mop", "Dust", "Bake", "Knead"],
    task_region=["", "Attic", "Attic", "Kitchen", ""],
    items=["Broom", "Key A", "Key B", "Oven", "Gold"],
    item_types=["progression"] * 5,
    item_consumable=["false", "false", "false", "false", "true"],
    item_progressive_group=["", "keys", "keys", "", ""],
    regions=["Attic", "Kitchen"],
    progressive_groups=["keys"],
)


def prune(**kw):
    return disable.apply_disabled({**BASE, **kw})


class RewriteTest(unittest.TestCase):
    def test_nothing_disabled_is_untouched(self):
        self.assertIsNone(prune())
        self.assertIsNone(prune(region_disabled=["false", ""], group_disabled=["false"]))

    def test_region_tasks_removed_and_renumbered(self):
        out = prune(region_disabled=["true", "false"],
                    task_prereqs=["", "", "", "2 && 1", "4 || 3"])
        self.assertEqual(out["tasks"], ["Sweep", "Bake", "Knead"])
        self.assertEqual(out["task_region"], ["", "Kitchen", ""])
        self.assertEqual(out["task_prereqs"], ["", "1", ""])
        self.assertEqual(out["regions"], ["Kitchen"])

    def test_region_and_name_refs_fold_to_true(self):
        out = prune(region_disabled=["true"],
                    task_prereqs=["", "", "", '(Attic-50 || 1) && "Dust" && Kitchen*1', ""])
        self.assertEqual(out["task_prereqs"][1], "Kitchen*1")

    def test_untouched_expressions_keep_their_text(self):
        out = prune(region_disabled=["true"], task_prereqs=["Kitchen,  \"Sweep\""])
        self.assertEqual(out["task_prereqs"][0], 'Kitchen,  "Sweep"')

    def test_prev_after_removed_row(self):
        out = prune(region_disabled=["true"], task_prereqs=["", "", "", "prev && 1", ""],
                    task_count=["1", "1", "1", "3", "1"])
        self.assertEqual(out["task_prereqs"][1], "sequential && 1")
        out = prune(region_disabled=["true"], task_prereqs=["", "", "", "prev", ""])
        self.assertEqual(out["task_prereqs"][1], "")

    def test_group_items_removed_and_refs_true(self):
        out = prune(group_disabled=["true"],
                    item_prereqs=["2 || 4", "keys*2 && 1", '"Key A"', "item(4)", "5*1"],
                    task_prereqs=["item(3) && 1", "", "", "", ""],
                    task_cost=["", "", "", "5*3", '"Gold"*2'])

        self.assertEqual(out["items"], ["Broom", "Oven", "Gold"])
        self.assertEqual(out["item_prereqs"], ["", "1", "", "item(2)", "3*1"])
        self.assertEqual(out["task_prereqs"][0], "1")
        self.assertEqual(out["task_cost"], ["", "", "", "3*3", '"Gold"*2'])
        self.assertEqual(out["progressive_groups"], [])

    def test_region_prereqs_and_parent_cascade(self):
        out = prune(regions=["Attic", "Kitchen", "Loft"], region_parent=["", "", "Attic"],
                    region_prereqs=["", "Loft && task(2) && item(1)", ""],
                    region_disabled=["true", "", ""])
        self.assertEqual(out["regions"], ["Kitchen"])
        self.assertEqual(out["region_prereqs"], ["item(1)"])

    def test_goal(self):
        out = prune(region_disabled=["true"], goal_tasks=["2", "5"])
        self.assertEqual(out["goal_tasks"], ["3"])
        warnings = []
        out = disable.apply_disabled({**BASE, "region_disabled": ["true"], "goal_tasks": ["Attic || 2"]},
                                     warn=warnings.append)
        self.assertEqual(out["goal_tasks"], [])
        self.assertEqual(len(warnings), 1)

    def test_disabled_currency_is_unavailable(self):
        warnings = []
        out = disable.apply_disabled({
            **BASE, "group_disabled": ["true"],
            "item_consumable": ["false", "true", "false", "false", "true"],
            "task_cost": ['"Key A"*2 || "Gold"*1', '2*1 && "Gold"*1', '"Gold"*3', "", ""],
        }, warn=warnings.append)
        self.assertEqual(out["task_cost"], ['"Gold"*1', "", '"Gold"*3', "", ""])
        self.assertEqual(len(warnings), 1)

    def test_clicker_targets_and_deathlink(self):
        out = prune(region_disabled=["true"],
                    item_production=['"Mop"-1 && Kitchen-2', "(Attic && 4)-1", "2-1", "*-1", "3"],
                    death_link_pool=["Mop", "Bake"], death_link_weights=["2", "5"])
        self.assertEqual(out["item_production"], ["Kitchen-2", "2-1", "", "*-1", "3"])
        self.assertEqual(out["death_link_pool"], ["Bake"])
        self.assertEqual(out["death_link_weights"], ["5"])


class GenerateTest(unittest.TestCase):
    def test_generates_without_disabled_content(self):
        w = _quiet(**BASE, region_disabled=["true", ""], group_disabled=["true"],
                   task_prereqs=["", "", "", "Attic && 1", ""],
                   item_prereqs=["", "", "", "keys", ""])
        self.assertEqual(w._tasks, ["Sweep", "Bake", "Knead"])
        self.assertNotIn("Key A", w._rewards)
        self.assertEqual(w._raw_prereqs[1], "1")
        self.assertEqual(w._raw_reward_prereqs[1], "")

    def test_broken_and_randomized_disabled_content_still_generates(self):
        w = _quiet(**BASE, region_disabled=["true", ""],
                   region_random_pick=["1", ""],
                   task_prereqs=["", "((", "nonsense-region", "", ""],
                   region_prereqs=["also broken ((", ""])
        self.assertEqual(w._tasks, ["Sweep", "Bake", "Knead"])

    def test_goal_falls_back_to_all_tasks(self):
        w = _quiet(**BASE, region_disabled=["true", ""], goal_tasks=["Attic"])
        self.assertIsNone(w._goal_ast)


if __name__ == "__main__":
    unittest.main()
