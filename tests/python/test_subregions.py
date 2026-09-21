"""Subregions: region_parent validation, inherited parent gates and parent task rollup."""
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


class InheritedParentRequirementsTest(unittest.TestCase):
    def test_subregion_does_not_require_parent_completion(self):
        w = world()
        self.assertEqual(w._task_region_reqs, [[], [], [], []])

    def test_subregion_inherits_the_parent_gate(self):
        w = _quiet(**{
            **BASE,
            "regions": ["Hall", "Kitchen", "Yard"],
            "task_region": ["Hall", "Yard", "Kitchen", "Kitchen"],
            "region_parent": ["", "Hall", ""],
            "region_prereqs": ["Yard*1", "", ""],
        })
        for i in (0, 2, 3):
            self.assertEqual(w._task_region_reqs[i], [{"region": "Yard", "abs_count": 1}])

    def test_inherited_gate_ands_with_an_explicit_one(self):
        w = _quiet(**{
            **BASE,
            "tasks": BASE["tasks"] + ["Rake"],
            "items": BASE["items"] + ["Rake"],
            "item_types": ["progression"] * 5,
            "regions": ["Hall", "Kitchen", "Yard", "Shed"],
            "task_region": ["Hall", "Yard", "Kitchen", "Kitchen", "Shed"],
            "region_parent": ["", "Hall", "", ""],
            "region_prereqs": ["Yard*1", "Shed*1", "", ""],
        })
        self.assertEqual(
            w._task_region_reqs[2],
            [{"region": "Yard", "abs_count": 1}, {"region": "Shed", "abs_count": 1}],
        )

    def test_task_less_parent_passes_its_own_gate_down(self):
        w = _quiet(**{
            **BASE,
            "regions": ["Hall", "Kitchen", "Yard"],
            "task_region": ["Yard", "Yard", "Kitchen", "Kitchen"],
            "region_parent": ["", "Hall", ""],
            "region_prereqs": ["Yard*2", "", ""],
        })
        self.assertEqual(w._task_region_reqs[2], [{"region": "Yard", "abs_count": 2}])

    def test_parent_counts_subregion_tasks(self):
        w = world()
        self.assertEqual(w._region_to_task_indices["Hall"], [0, 1, 2, 3])
        self.assertEqual(w._region_to_task_indices["Kitchen"], [2, 3])
        self.assertEqual(len(w._region_token_names["Hall"]), 4)

    def test_task_less_parent_can_be_referenced(self):
        w = _quiet(**{
            **BASE,
            "task_region": ["", "", "Kitchen", "Kitchen"],
            "goal_tasks": ["Hall"],
        })
        self.assertEqual(w._region_to_task_indices["Hall"], [2, 3])

    def test_a_randomized_subregion_counts_toward_its_parent(self):
        w = _quiet(**{**BASE, "region_random_pick": ["", "1"]})
        kitchen = [i for i, r in enumerate(w._task_region) if r == "Kitchen"]
        self.assertEqual(w._region_to_task_indices["Hall"], sorted([0, 1] + kitchen))

    def test_subregion_task_may_reference_parent_when_satisfiable(self):
        w = world(task_prereqs=["", "", "Hall*2", ""])
        self.assertEqual(w._task_region_reqs[2], [{"region": "Hall", "abs_count": 2}])

    def test_slot_data_carries_the_parent_map(self):
        w = world()
        sd = w.fill_slot_data()
        self.assertEqual(sd["region_parent"], {"Kitchen": "Hall"})
        self.assertTrue(sd["region_rollup"])


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

    def test_subregion_task_needing_its_own_tasks_via_parent(self):
        msg = self._err(task_prereqs=["", "", "Hall", ""])
        self.assertIn("would have to unlock itself", msg)

    def test_subregion_gate_needing_its_own_tasks_via_parent(self):
        msg = self._err(region_prereqs=["", "Hall*3"])
        self.assertIn("would have to unlock itself", msg)

    def test_parent_depending_on_its_own_subregion_is_a_cycle(self):
        msg = self._err(region_prereqs=["Kitchen*1", ""])
        self.assertIn("cycle", msg.lower())


if __name__ == "__main__":
    unittest.main()
