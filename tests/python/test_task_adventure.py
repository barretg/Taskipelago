"""Regression: a clicker adventure whose Swamp subregions once locked themselves.

Loot Swamp Bats (in parent Swamp) requires Defeat Swamp Bats (in subregion
Swamp_Combat). When subregions depended on their parent's completion, Swamp
could never finish and every Swamp subregion was unreachable (FillError).
"""
from __future__ import annotations

import contextlib
import io
import unittest
from pathlib import Path

import yaml

from ap_harness import _DEFAULTS, generate

FIXTURE = Path(__file__).resolve().parent / "fixtures" / "task_adventure.yaml"


def load_world():
    opts = yaml.safe_load(FIXTURE.read_text(encoding="utf-8"))["Taskipelago"]
    # Weighted options (death_link) are rolled by AP; take the off branch.
    opts = {k: (False if isinstance(v, dict) else v) for k, v in opts.items() if k in _DEFAULTS}
    with contextlib.redirect_stderr(io.StringIO()):
        return generate(1, **opts)


class TaskAdventureTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.w = load_world()

    def _tasks_in(self, rname):
        return [i for i, r in enumerate(self.w._task_region) if r == rname]

    def test_subregions_do_not_wait_on_parent_completion(self):
        parents = {"Meadow", "Forest", "Mountain", "Swamp"}
        for i, reqs in enumerate(self.w._task_region_reqs):
            for req in reqs:
                self.assertNotIn(req["region"], parents, f"task {i + 1}: {req}")

    def test_swamp_counts_its_subregions(self):
        swamp = self.w._region_to_task_indices["Swamp"]
        for sub in ("Swamp", "Swamp_Trees", "Swamp_Mining", "Swamp_Combat"):
            for i in self._tasks_in(sub):
                self.assertIn(i, swamp)

    def test_every_task_is_reachable_with_all_items(self):
        """Fixed-point sweep with every reward item held: each task must complete."""
        w, n = self.w, len(self.w._task_region)
        rewards = set(w._reward_display_names)
        tokens: set = set()

        class State:
            def has(self, name, player, count=1):
                return name in rewards or name in tokens

            def has_from_list(self, names, player, count):
                return sum(1 for x in names if x in rewards or x in tokens) >= count

        from _taskipelago_gen_test.prereq_parser import eval_node
        state, sn = State(), {"task": w._token_item_names, "item": w._reward_display_names}
        changed = True
        while changed:
            changed = False
            for i in range(n):
                tok = w._token_item_names[i]
                if tok in tokens:
                    continue
                if eval_node(w._parsed_prereqs[i], state, 1, w._token_item_names,
                             w._group_item_display_names, w._region_token_names, sn):
                    tokens.add(tok)
                    changed = True
        stuck = [i + 1 for i in range(n) if w._token_item_names[i] not in tokens]
        self.assertEqual(stuck, [])


if __name__ == "__main__":
    unittest.main()
