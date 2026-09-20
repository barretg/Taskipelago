"""Subregions: region_parent validation and the implicit parent dependency."""
from __future__ import annotations

import contextlib
import io
import unittest

from ap_harness import generate


def _quiet(**kw):
    with contextlib.redirect_stderr(io.StringIO()):
        return generate(**kw)


# Hall is the parent, Kitchen its subregion; task 3 is unassigned.
BASE = dict(
    tasks=["Sweep Hall", "Mop Hall", "Bake Bread", "Knead"],
    items=["Broom", "Mop", "Oven", "Mixer"],
    item_types=["progression"] * 4,
    regions=["Hall", "Kitchen"],
    task_region=["Hall", "Hall", "Kitchen", "Kitchen"],
    region_parent=["", "Hall"],
)


def world(**extra):
    return _quiet(**{**BASE, **extra})


class ImplicitParentDependencyTest(unittest.TestCase):
    def test_subregion_tasks_require_the_parent(self):
        w = world()
        # Tasks 3 and 4 are in Kitchen, whose parent is Hall (default 100%).
        for i in (2, 3):
            self.assertEqual(w._task_region_reqs[i], [{"region": "Hall", "pct": 100}])
        # The parent's own tasks gain nothing.
        for i in (0, 1):
            self.assertEqual(w._task_region_reqs[i], [])

    def test_parent_default_pct_is_used(self):
        w = world(region_default_pcts=["50", "100"])
        self.assertEqual(w._task_region_reqs[2], [{"region": "Hall", "pct": 50}])

    def test_implicit_dependency_ands_with_an_explicit_one(self):
        w = _quiet(**{
            **BASE,
            "regions": ["Hall", "Kitchen", "Yard"],
            "task_region": ["Hall", "Yard", "Kitchen", "Kitchen"],
            "region_parent": ["", "Hall", ""],
            "region_prereqs": ["", "Yard*1", ""],
        })
        self.assertEqual(
            w._task_region_reqs[2],
            [{"region": "Hall", "pct": 100}, {"region": "Yard", "abs_count": 1}],
        )

    def test_top_level_regions_are_untouched(self):
        w = _quiet(**{**BASE, "region_parent": []})
        self.assertEqual(w._task_region_reqs, [[], [], [], []])

    def test_task_less_parent_passes_its_own_gate_down(self):
        """A grouping-only parent has nothing to complete, so its gate is inherited."""
        w = _quiet(**{
            **BASE,
            "regions": ["Hall", "Kitchen", "Yard"],
            "task_region": ["Yard", "Yard", "Kitchen", "Kitchen"],
            "region_parent": ["", "Hall", ""],
            "region_prereqs": ["Yard*2", "", ""],
        })
        self.assertEqual(w._task_region_reqs[2], [{"region": "Yard", "abs_count": 2}])

    def test_task_less_parent_without_a_gate_adds_nothing(self):
        w = _quiet(**{
            **BASE,
            "regions": ["Hall", "Kitchen"],
            "task_region": ["", "", "Kitchen", "Kitchen"],
            "region_parent": ["", "Hall"],
        })
        self.assertEqual(w._task_region_reqs[2], [])

    def test_a_randomized_subregion_still_requires_its_parent(self):
        w = _quiet(**{**BASE, "region_random_pick": ["", "1"]})
        kitchen = [i for i, r in enumerate(w._task_region) if r == "Kitchen"]
        self.assertTrue(kitchen)
        for i in kitchen:
            self.assertEqual(w._task_region_reqs[i], [{"region": "Hall", "pct": 100}])

    def test_slot_data_carries_the_parent_map(self):
        w = world()
        self.assertEqual(w.fill_slot_data()["region_parent"], {"Kitchen": "Hall"})


class ParentValidationTest(unittest.TestCase):
    def _err(self, **extra):
        with self.assertRaises(Exception) as cm:
            world(**extra)
        return str(cm.exception)

    def test_unknown_parent(self):
        self.assertIn("unknown parent region", self._err(region_parent=["", "Attic"]))

    def test_self_parent(self):
        self.assertIn("cannot be its own parent", self._err(region_parent=["", "Kitchen"]))

    def test_two_levels_of_nesting(self):
        msg = self._err(
            regions=["Hall", "Kitchen", "Pantry"],
            task_region=["Hall", "Hall", "Kitchen", "Pantry"],
            region_parent=["", "Hall", "Kitchen"],
        )
        self.assertIn("only one level deep", msg)

    def test_randomized_region_cannot_be_a_parent(self):
        msg = self._err(region_random_pick=["1", ""])
        self.assertIn("cannot be a parent region", msg)

    def test_parent_depending_on_its_own_subregion_is_a_cycle(self):
        msg = self._err(region_prereqs=["Kitchen*1", ""])
        self.assertIn("cycle", msg.lower())


if __name__ == "__main__":
    unittest.main()
