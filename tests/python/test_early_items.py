"""item_early / group_early: flagged items are registered with multiworld.early_items."""
from __future__ import annotations

import contextlib
import io
import unittest

from ap_harness import generate


def world(**extra):
    opts = dict(
        tasks=[f"T{i}" for i in range(5)],
        items=["Key", "Map", "Gem", "Coin"],
        item_count=["1", "2", "1", "1"],
        progressive_groups=["gems"],
        item_progressive_group=["", "", "gems", ""],
    )
    opts.update(extra)
    with contextlib.redirect_stderr(io.StringIO()):
        return generate(**opts)


class EarlyItemsTest(unittest.TestCase):
    def test_default_none_early(self):
        self.assertEqual(world()._item_early, [False] * 5)

    def test_item_flag_expands_with_count(self):
        w = world(item_early=["false", "true"])
        self.assertEqual(w._item_early, [False, True, True, False, False])

    def test_group_flag(self):
        w = world(group_early=["true"])
        self.assertEqual(w._item_early, [False, False, False, True, False])

    def test_create_items_registers_early_items(self):
        w = world(item_early=["true"], group_early=["true"])
        w.multiworld.itempool = []
        w.multiworld.early_items = {w.player: {}}
        names = w._reward_item_names
        w.item_name_to_id = {n: k for k, n in enumerate(names)}
        w.create_items()
        self.assertEqual(w.multiworld.early_items[w.player], {names[0]: 1, names[3]: 1})


if __name__ == "__main__":
    unittest.main()
