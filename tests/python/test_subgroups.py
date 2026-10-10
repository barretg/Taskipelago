"""Subgroups: group_parent validation, parent item rollup and the disable cascade."""
from __future__ import annotations

import contextlib
import io
import unittest

from ap_harness import generate


def _quiet(**kw):
    with contextlib.redirect_stderr(io.StringIO()):
        return generate(**kw)


# Tools is the parent, Cleaning its subgroup; item 4 is ungrouped.
BASE = dict(
    tasks=["Sweep", "Mop", "Bake", "Knead"],
    items=["Hammer", "Broom", "Mop", "Oven"],
    item_types=["progression"] * 4,
    progressive_groups=["Tools", "Cleaning"],
    item_progressive_group=["Tools", "Cleaning", "Cleaning", ""],
    group_types=["aesthetic", "aesthetic"],
    group_parent=["", "Tools"],
)


def world(**extra):
    return _quiet(**{**BASE, **extra})


class RollupTest(unittest.TestCase):
    def test_parent_counts_subgroup_items(self):
        w = world()
        self.assertEqual(w._group_to_reward_indices["Tools"], [0, 1, 2])
        self.assertEqual(w._group_to_reward_indices["Cleaning"], [1, 2])
        # Each item keeps its own group for display.
        self.assertEqual(w._reward_to_group, ["Tools", "Cleaning", "Cleaning", ""])

    def test_parent_count_ref_beyond_own_items(self):
        w = world(item_prereqs=["", "", "", "Tools*3"])
        self.assertEqual(w._parsed_reward_prereqs[3], ("group_count", "Tools", 3))

    def test_parent_bare_ref_uses_rollup_size(self):
        # Aesthetic default is 100% of the parent's 3 items.
        w = world(item_prereqs=["", "", "", "Tools"])
        self.assertEqual(w._parsed_reward_prereqs[3], ("group_count", "Tools", 3))

    def test_slot_data(self):
        sd = world().fill_slot_data()
        self.assertEqual(sd["group_parent"], {"Cleaning": "Tools"})
        self.assertTrue(sd["group_rollup"])

    def test_disabled_parent_disables_subgroups(self):
        w = world(group_disabled=["true", ""], item_prereqs=["", "", "", "Cleaning*2"])
        self.assertEqual(w._rewards[:1], ["Oven"])
        self.assertIsNone(w._parsed_reward_prereqs[0])

    def test_subgroup_inherits_parent_early(self):
        w = world(group_early=["true", "false"])
        self.assertEqual(w._item_early, [True, True, True, False])

    def test_subgroup_may_be_early_alone(self):
        w = world(group_early=["false", "true"])
        self.assertEqual(w._item_early, [False, True, True, False])


class ParentValidationTest(unittest.TestCase):
    def _err(self, **extra):
        with self.assertRaises(Exception) as cm:
            world(**extra)
        return str(cm.exception)

    def test_unknown_parent(self):
        self.assertIn("unknown parent group", self._err(group_parent=["", "Gear"]))

    def test_self_parent(self):
        self.assertIn("cannot be its own parent", self._err(group_parent=["", "Cleaning"]))

    def test_two_levels_of_nesting(self):
        msg = self._err(
            progressive_groups=["Tools", "Cleaning", "Mops"],
            item_progressive_group=["Tools", "Cleaning", "Mops", ""],
            group_types=["aesthetic"] * 3,
            group_parent=["", "Tools", "Cleaning"],
        )
        self.assertIn("only one level deep", msg)

    def test_random_choice_group_cannot_be_a_parent(self):
        msg = self._err(group_types=["random-choice", "aesthetic"], group_random_pick=["1", ""])
        self.assertIn("cannot be a parent group", msg)

    def test_random_choice_subgroup_is_allowed(self):
        w = world(group_types=["aesthetic", "random-choice"], group_random_pick=["", "1"])
        self.assertEqual(len(w._group_to_reward_indices["Cleaning"]), 1)
        self.assertEqual(len(w._group_to_reward_indices["Tools"]), 2)


if __name__ == "__main__":
    unittest.main()
