"""Filler Scout / Filler Hint: each filler item reveals one task chosen at generation."""
from __future__ import annotations

import contextlib
import io
import unittest

from ap_harness import generate


def world(previews, seed=1, **extra):
    opts = dict(
        tasks=[f"T{i}" for i in range(6)],
        items=["Key", "", "", "Map", "", ""],
        item_types=["progression", "junk", "junk", "progression", "junk", "junk"],
        task_reward_previews=previews,
    )
    opts.update(extra)
    with contextlib.redirect_stderr(io.StringIO()):
        return generate(seed=seed, **opts)


class FillerPreviewTargetsTest(unittest.TestCase):
    def test_each_filler_gets_a_distinct_task(self):
        w = world(3)
        targets = w._filler_preview_targets
        self.assertEqual(len(targets), 6)
        fillers = [i for i, f in enumerate(w._item_fillers) if f]
        self.assertEqual(fillers, [1, 2, 4, 5])
        for i, t in enumerate(targets):
            if i in fillers:
                self.assertTrue(0 <= t < 6)
            else:
                self.assertEqual(t, -1)
        picked = [targets[i] for i in fillers]
        self.assertEqual(len(set(picked)), len(picked))

    def test_more_fillers_than_tasks_reuses_tasks(self):
        w = world(4, tasks=["A", "B"], items=["", ""], item_types=["junk", "junk"])
        self.assertEqual(sorted(w._filler_preview_targets), [0, 1])

    def test_deterministic_per_seed(self):
        self.assertEqual(world(3, seed=5)._filler_preview_targets, world(3, seed=5)._filler_preview_targets)

    def test_purchasable_only_limits_targets_to_costed_tasks(self):
        w = world(3, items=["Coin", "", "", "", ""], item_count=["2", "1", "1", "1", "1"],
                  item_consumable=["true", "", "", "", ""],
                  item_types=["progression"] + ["junk"] * 4,
                  task_cost=["", "", '"Coin"*1', "", "", ""],
                  task_reward_previews_purchasable_only=True)
        picked = {t for t in w._filler_preview_targets if t >= 0}
        self.assertEqual(picked, {2})

    def test_other_modes_assign_nothing(self):
        for mode in (0, 1, 2):
            self.assertEqual(world(mode)._filler_preview_targets, [])


if __name__ == "__main__":
    unittest.main()
