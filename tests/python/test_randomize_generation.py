"""Randomized regions, item group types, and renumbering (generate_early via AP stubs)."""
from __future__ import annotations

import contextlib
import io
import unittest

from ap_harness import generate, load_world

load_world()
from _taskipelago_gen_test.prereq_parser import collect_leaves  # noqa: E402


def _quiet(**kw):
    with contextlib.redirect_stderr(io.StringIO()) as err:
        w = generate(**kw)
    return w, err.getvalue()


def _region_world(pick, seed=1, goal=None, **extra):
    # Task 1 is free and outside the region; tasks 2-7 are in "pool".
    opts = dict(
        tasks=["Free", "P1", "P2", "P3", "P4", "P5", "P6", "After"],
        items=[f"I{i}" for i in range(8)],
        regions=["pool"], region_random_pick=[pick],
        task_region=["", "pool", "pool", "pool", "pool", "pool", "pool", ""],
    )
    if goal is not None:
        opts["goal_tasks"] = goal
    opts.update(extra)
    return _quiet(seed=seed, **opts)[0]


def _assert_refs_valid(tc, w):
    n = len(w._tasks)
    for ast in w._parsed_prereqs + w._parsed_reward_prereqs:
        for leaf in collect_leaves(ast):
            tc.assertTrue(0 <= leaf < n)
    for leaf in w._goal_indices:
        tc.assertTrue(0 <= leaf < n)


class RegionSelectionTest(unittest.TestCase):
    def test_keeps_n_and_renumbers(self):
        w = _region_world("3")
        self.assertEqual(len(w._tasks), 5)
        self.assertEqual(w._tasks[0], "Free")
        self.assertEqual(w._tasks[-1], "After")
        self.assertEqual(w._task_region, ["", "pool", "pool", "pool", ""])
        self.assertEqual(len(w._rewards), 5)
        self.assertEqual(w._reward_location_names[1].split(": ", 1)[1], w._tasks[1])
        _assert_refs_valid(self, w)

    def test_percent_rounds_up(self):
        self.assertEqual(len(_region_world("40%")._tasks), 2 + 3)  # ceil(6 * 0.4) = 3
        self.assertEqual(len(_region_world("1%")._tasks), 2 + 1)

    def test_selection_varies_by_seed(self):
        picks = {tuple(_region_world("3", seed=s)._tasks[1:4]) for s in range(30)}
        self.assertGreater(len(picks), 5)

    def test_order_is_kept_by_default(self):
        for seed in range(20):
            kept = _region_world("3", seed=seed)._tasks[1:4]
            self.assertEqual(kept, sorted(kept))

    def test_random_order_shuffles_kept_tasks(self):
        picks = {
            tuple(_region_world("3", seed=s, region_random_order=["true"])._tasks[1:4])
            for s in range(30)
        }
        self.assertTrue(any(list(p) != sorted(p) for p in picks))

    def test_equal_count_warns_and_keeps_all(self):
        w, err = _quiet(
            tasks=["A", "B", "C"], items=["x", "y", "z"], regions=["r"], region_random_pick=["2"],
            task_region=["", "r", "r"],
        )
        self.assertEqual(len(w._tasks), 3)
        self.assertIn("keeps all", err)

    def test_invalid_picks(self):
        for bad in ("7", "0", "0%", "101%", "abc", "-1", "2.5"):
            with self.subTest(bad=bad), self.assertRaises(Exception):
                _region_world(bad)

    def test_duplicates_are_separate_candidates(self):
        w, _ = _quiet(
            tasks=["Free", "Dup"], items=["a", "b"], item_count=["1", "4"], task_count=["1", "4"],
            regions=["r"], region_random_pick=["2"], task_region=["", "r"],
        )
        self.assertEqual(w._tasks, ["Free", "Dup", "Dup"])

    def test_empty_pick_means_not_randomized(self):
        w = _region_world("")
        self.assertEqual(len(w._tasks), 8)

    def test_region_refs_count_kept_tasks(self):
        w = _region_world("2", task_prereqs=["", "", "", "", "", "", "", "pool*2"])
        self.assertEqual(w._task_region_reqs[-1], [{"region": "pool", "abs_count": 2}])
        with self.assertRaises(Exception):
            _region_world("2", task_prereqs=["", "", "", "", "", "", "", "pool*3"])

    def test_dependencies_on_normal_regions_allowed(self):
        w = _region_world("2", task_prereqs=["", "1", "1", "1", "1", "1", "1", "pool"])
        _assert_refs_valid(self, w)
        self.assertEqual([collect_leaves(a) for a in w._parsed_prereqs[1:3]], [[0], [0]])


class GoalGuaranteeTest(unittest.TestCase):
    def test_single_goal_task_is_pinned(self):
        for seed in range(15):
            w = _region_world("1", seed=seed, goal=['"P4"'])
            self.assertIn("P4", w._tasks)
            self.assertEqual([w._tasks[i] for i in w._goal_indices], ["P4"])

    def test_or_goal_keeps_at_least_one(self):
        seen = set()
        for seed in range(25):
            w = _region_world("1", seed=seed, goal=["3 || 6"])
            kept = [t for t in ("P2", "P5") if t in w._tasks]
            self.assertTrue(kept)
            seen.add(kept[0])
            self.assertTrue(w._goal_indices)
        self.assertEqual(seen, {"P2", "P5"})

    def test_infeasible_goal_errors(self):
        with self.assertRaises(Exception):
            _region_world("1", goal=["2 && 3"])

    def test_goal_of_normal_tasks_pins_nothing(self):
        w = _region_world("1", goal=["1 || 2"])
        self.assertEqual(len(w._tasks), 3)
        self.assertEqual(w._goal_ast, 0)

    def test_goal_of_task_one_has_index(self):
        w = _region_world("1", goal=["1"])
        self.assertEqual(w._goal_indices, [0])
        w = _region_world("")
        self.assertIsNone(w._goal_ast)
        self.assertEqual(w._goal_indices, [])

    def test_region_goal_ref(self):
        w = _region_world("2", goal=["pool"])
        self.assertEqual(w._goal_region_reqs, [{"region": "pool", "pct": 100}])


class ForbiddenRefsTest(unittest.TestCase):
    def test_individual_task_in_random_region(self):
        with self.assertRaises(Exception):
            _region_world("2", task_prereqs=["", "", "", "", "", "", "", "3"])

    def test_sibling_and_prev(self):
        with self.assertRaises(Exception):
            _region_world("2", task_prereqs=["", "", "2"])
        with self.assertRaises(Exception):
            _region_world("2", task_prereqs=["", "", "", "", "", "", "", "prev"])

    def test_sequential_in_random_region(self):
        with self.assertRaises(Exception):
            _region_world("2", task_prereqs=["", "", "sequential"])

    def test_self_region_ref(self):
        with self.assertRaises(Exception):
            _region_world("2", task_prereqs=["", "", "pool-50"])

    def test_prev_outside_random_region_is_resolved(self):
        w = _region_world("2", task_prereqs=["", "", "", "", "", "", "", ""],
                          tasks=["Free", "P1", "P2", "P3", "P4", "P5", "P6", "After"])
        self.assertEqual(len(w._tasks), 4)
        w2, _ = _quiet(
            tasks=["A", "B", "C", "D"], items=["a", "b", "c", "d"], regions=["r"],
            region_random_pick=["1"], task_region=["r", "r", "", ""], task_prereqs=["", "", "", "prev"],
        )
        self.assertEqual(w2._tasks[1:], ["C", "D"])
        self.assertEqual(w2._raw_prereqs[2], "2")
        self.assertEqual(collect_leaves(w2._parsed_prereqs[2]), [1])


def _group_world(gtype, pick="", dpct="", item_prereqs=None, seed=1, **extra):
    opts = dict(
        tasks=[f"T{i}" for i in range(6)],
        items=["G1", "G2", "G3", "G4", "x", "y"],
        progressive_groups=["gem"], group_types=[gtype], group_random_pick=[pick],
        group_default_pcts=[dpct], item_progressive_group=["gem", "gem", "gem", "gem", "", ""],
        item_prereqs=item_prereqs or [""] * 6,
    )
    opts.update(extra)
    return _quiet(seed=seed, **opts)[0]


class ItemGroupTypesTest(unittest.TestCase):
    def test_random_choice_keeps_pick_and_pads(self):
        w = _group_world("random-choice", pick="2")
        self.assertEqual(sum(1 for g in w._reward_to_group if g == "gem"), 2)
        self.assertEqual(len(w._rewards), 6)
        self.assertEqual(w._group_types, ["random-choice"])
        kept = [r for r in w._rewards if r.startswith("G")]
        self.assertEqual(kept, sorted(kept))

    def test_random_choice_refs_count_kept_items(self):
        w = _group_world("random-choice", pick="2", item_prereqs=["", "gem", "gem-50", "gem*1", "", ""])
        self.assertEqual(w._raw_reward_prereqs[1:4], ["gem*2", "gem*1", "gem*1"])
        with self.assertRaises(Exception):
            _group_world("random-choice", pick="2", item_prereqs=["", "gem*3", "", "", "", ""])

    def test_random_choice_individual_item_ref_forbidden(self):
        with self.assertRaises(Exception):
            _group_world("random-choice", pick="2", item_prereqs=["", "1", "", "", "", ""])
        with self.assertRaises(Exception):
            _group_world("random-choice", item_prereqs=["", '"G2"', "", "", "", ""])

    def test_aesthetic_semantics(self):
        w = _group_world("aesthetic", dpct="50", item_prereqs=["", "gem", "gem-100", "gem*3", "1", ""])
        self.assertEqual(w._raw_reward_prereqs[1:5], ["gem*2", "gem*4", "gem*3", "1"])
        self.assertEqual(w._group_default_pcts, [50])

    def test_default_pct_defaults(self):
        self.assertEqual(_group_world("aesthetic")._group_default_pcts, [100])
        self.assertEqual(_group_world("progressive")._group_default_pcts, [None])
        self.assertEqual(_group_world("bogus")._group_types, ["progressive"])

    def test_progressive_legacy_and_default_pct(self):
        w = _group_world("progressive", item_prereqs=["", "gem", "gem", "", "", ""])
        self.assertEqual(w._raw_reward_prereqs[1:3], ["gem", "gem"])
        self.assertEqual(w._task_progressive_reqs[1:3], [[("gem", 1)], [("gem", 2)]])
        w = _group_world("progressive", dpct="50", item_prereqs=["", "gem", "gem", "", "", ""])
        self.assertEqual(w._raw_reward_prereqs[1:3], ["gem*2", "gem*2"])
        with self.assertRaises(Exception):
            _group_world("progressive", dpct="50", item_prereqs=["", "gem", "gem-2", "", "", ""])

    def test_zero_percent_is_always_true(self):
        w = _group_world("aesthetic", dpct="0", item_prereqs=["", "gem", "", "", "", ""])
        self.assertEqual(w._raw_reward_prereqs[1], "")

    def test_forced_progression_by_type(self):
        w = _group_world("aesthetic")
        self.assertFalse({0, 1, 2, 3} & w._forced_progression_rewards)
        w = _group_world("aesthetic", item_prereqs=["", "gem*1", "", "", "", ""])
        self.assertTrue({0, 1, 2, 3} <= w._forced_progression_rewards)
        w = _group_world("progressive")
        self.assertTrue({0, 1, 2, 3} <= w._forced_progression_rewards)

    def test_regions_and_groups_together(self):
        w, _ = _quiet(
            tasks=["Free", "P1", "P2", "P3", "Last"], items=["G1", "G2", "G3", "Gold", "z"],
            item_consumable=["", "", "", "true", ""], task_cost=["", "", "", "", "4"],
            regions=["pool"], region_random_pick=["2"], task_region=["", "pool", "pool", "pool", ""],
            progressive_groups=["gem"], group_types=["random-choice"], group_random_pick=["1"],
            item_progressive_group=["gem", "gem", "gem", "", ""], item_prereqs=["", "", "", "", "gem"],
        )
        self.assertEqual(len(w._tasks), 4)
        self.assertEqual(w._raw_costs[-1], '"Gold"')
        self.assertEqual(w._raw_reward_prereqs[-1], "gem*1")
        self.assertIn("Gold", w._rewards)
        _assert_refs_valid(self, w)


if __name__ == "__main__":
    unittest.main()
