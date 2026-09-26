"""task(...) / item(...) scopes in task prereqs, item prereqs and goal_tasks."""
from __future__ import annotations

import contextlib
import io
import unittest

from ap_harness import generate, load_world


def _quiet(**kw):
    with contextlib.redirect_stderr(io.StringIO()):
        return generate(**kw)


BASE = dict(
    tasks=["A", "B", "C", "D"],
    items=["Key", "Map", "Lamp", "Rope"],
    item_types=["progression"] * 4,
)


def world(**extra):
    return _quiet(**{**BASE, **extra})


class _State:
    def __init__(self, have):
        self.have = set(have)

    def has(self, name, player):
        return name in self.have

    def has_from_list(self, names, player, count):
        return sum(1 for n in names if n in self.have) >= count


def _eval(w, ast, have):
    pp = load_world().prereq_parser
    sn = {"task": w._token_item_names, "item": w._reward_display_names}
    return pp.eval_node(ast, _State(have), 1, sn["task"], w._group_item_display_names,
                        w._region_token_names, sn)


class TaskPrereqItemScopeTest(unittest.TestCase):
    def test_item_or_task(self):
        w = world(task_prereqs=["", "", "item(1) || 2", ""])
        ast = w._parsed_prereqs[2]
        self.assertEqual(ast, ("or", [("scoped_item", [0]), 1]))
        self.assertEqual(w._raw_prereqs[2], "item(1) || 2")
        key, tok_b = w._reward_display_names[0], w._token_item_names[1]
        self.assertTrue(_eval(w, ast, {key}))
        self.assertTrue(_eval(w, ast, {tok_b}))
        self.assertFalse(_eval(w, ast, set()))
        self.assertIn(0, w._forced_progression_rewards)

    def test_quoted_item_name(self):
        w = world(task_prereqs=["", "", 'item("Lamp") || "B"', ""])
        self.assertEqual(w._raw_prereqs[2], "item(3) || 2")

    def test_editor_copies_translate_per_domain(self):
        w = world(task_count=[2, 1, 1, 1], item_count=[1, 3, 1, 1],
                  items=["Key", "Map", "Lamp", "Rope"],
                  task_prereqs=["", "", "", "item(2) || 1"])
        # task row 1 has two copies (AND), item row 2 has three copies (OR)
        self.assertEqual(w._raw_prereqs[4], "item((2 || 3 || 4)) || (1 && 2)")

    def test_ordering_mode_group_rejected(self):
        with self.assertRaisesRegex(Exception, "ordering mode"):
            world(progressive_groups=["Gear"], item_progressive_group=["Gear", "Gear", "", ""],
                  task_prereqs=["", "", "item(Gear) || 2", ""])

    def test_count_mode_group(self):
        w = world(progressive_groups=["Gear"], item_progressive_group=["Gear", "Gear", "", ""],
                  task_prereqs=["", "", "item(Gear*2) || 2", ""])
        self.assertEqual(w._parsed_prereqs[2], ("or", [("scoped_item", [("group_count", "Gear", 2)]), 1]))


class ItemPrereqTaskScopeTest(unittest.TestCase):
    def test_task_or_item(self):
        w = world(item_prereqs=["", "", "1 || task(2)", ""])
        ast = w._parsed_reward_prereqs[2]
        self.assertEqual(ast, ("or", [0, ("scoped_task", [1])]))
        self.assertTrue(_eval_reward(w, ast, {w._token_item_names[1]}))
        self.assertTrue(_eval_reward(w, ast, {w._reward_display_names[0]}))
        self.assertFalse(_eval_reward(w, ast, set()))
        # Task 2 is not forced progression because of the task(...) leaf
        self.assertNotIn(1, _item_leaves(w, 2))

    def test_task_scope_cycle_detected(self):
        with self.assertRaisesRegex(Exception, "cycle"):
            world(task_prereqs=["2", "", "", ""], item_prereqs=["", "task(1)", "", ""])

    def test_task_scope_region_ref_resolves(self):
        w = world(regions=["Yard"], task_region=["Yard", "Yard", "", ""],
                  item_prereqs=["", "", "1 || task(Yard-50)", ""])
        self.assertEqual(w._raw_reward_prereqs[2], "1 || task(Yard-50)")
        self.assertEqual(w._task_region_reqs[2], [])

    def test_task_prereq_region_ref_ships_inline(self):
        w = world(regions=["Yard", "Shed"], task_region=["Yard", "Yard", "Shed", ""],
                  region_prereqs=["", "Yard*1"], region_default_pcts=["50", "100"],
                  task_prereqs=["", "", "", "item(1) || Yard"])
        self.assertEqual(w._raw_prereqs[3], "item(1) || Yard-50")
        self.assertEqual(w._task_inherited_region_reqs[3], [])
        # Old clients still AND the full list.
        self.assertEqual(w._task_region_reqs[3], [{"region": "Yard", "pct": 50}])
        # Tasks in Shed inherit its gate separately from their own prereq.
        self.assertEqual(w._task_inherited_region_reqs[2], [{"region": "Yard", "abs_count": 1}])

    def test_goal_region_ref_ships_inline(self):
        w = world(regions=["Yard"], task_region=["Yard", "Yard", "", ""],
                  goal_tasks=["item(1) || Yard*2"])
        self.assertEqual(w._raw_goal, "item(1) || Yard*2")
        self.assertEqual(w._goal_region_reqs, [{"region": "Yard", "abs_count": 2}])


def _eval_reward(w, ast, have):
    pp = load_world().prereq_parser
    sn = {"task": w._token_item_names, "item": w._reward_display_names}
    return pp.eval_node(ast, _State(have), 1, sn["item"], w._group_item_display_names,
                        w._region_token_names, sn)


def _item_leaves(w, i):
    pp = load_world().prereq_parser
    return pp.collect_leaves(w._parsed_reward_prereqs[i], "item", "item")


class GoalScopeTest(unittest.TestCase):
    def test_goal_item_or_task(self):
        w = world(goal_tasks=["item(4) || 3"])
        self.assertEqual(w._goal_ast, ("or", [("scoped_item", [3]), 2]))
        self.assertEqual(w._goal_indices, [2])
        self.assertTrue(_eval(w, w._goal_ast, {w._reward_display_names[3]}))
        self.assertIn(3, w._forced_progression_rewards)

    def test_goal_quoted_item(self):
        w = world(goal_tasks=['item("Rope") || "C"'])
        self.assertEqual(w._raw_goal, "item(4) || 3")


class RandomizedScopeTest(unittest.TestCase):
    def _world(self, seed, **extra):
        opts = dict(
            tasks=["Free", "P1", "P2", "P3", "After"],
            items=["Key", "Gem1", "Gem2", "Rope", "Lamp"],
            item_types=["progression"] * 5,
            progressive_groups=["Gems"], group_types=["random-choice"], group_random_pick=["1"],
            item_progressive_group=["", "Gems", "Gems", "", ""],
            regions=["pool"], region_random_pick=["2"],
            task_region=["", "pool", "pool", "pool", ""],
        )
        opts.update(extra)
        return _quiet(seed=seed, **opts)

    def test_scoped_refs_follow_renumbering(self):
        for seed in range(10):
            w = self._world(seed, task_prereqs=["", "", "", "", 'item("Rope") || 1'],
                            item_prereqs=["", "", "", "", ""],
                            goal_tasks=['item("Lamp") || "After"'])
            n = len(w._tasks)
            rope = w._rewards.index("Rope")
            lamp = w._rewards.index("Lamp")
            self.assertEqual(w._raw_prereqs[n - 1], f"item({rope + 1}) || 1")
            self.assertEqual(w._goal_ast, ("or", [("scoped_item", [lamp]), n - 1]))

    def test_random_choice_item_in_scope_rejected(self):
        with self.assertRaisesRegex(Exception, "random-choice"):
            self._world(1, task_prereqs=["", "", "", "", "item(2)"])

    def test_randomized_region_task_in_item_prereq_rejected(self):
        with self.assertRaisesRegex(Exception, "randomized"):
            self._world(1, item_prereqs=["", "", "", "", "task(2)"])


class BackwardCompatTest(unittest.TestCase):
    def test_plain_prereqs_unchanged(self):
        w = world(task_prereqs=["", "1", "1 && 2", ""], item_prereqs=["", "", "1 || 2", ""],
                  goal_tasks=["3", "4"])
        self.assertEqual(w._raw_prereqs[2], "1 && 2")
        self.assertEqual(w._raw_reward_prereqs[2], "1 || 2")
        self.assertEqual(w._raw_goal, "3, 4")


if __name__ == "__main__":
    unittest.main()
