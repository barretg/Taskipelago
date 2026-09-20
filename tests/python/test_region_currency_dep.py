"""A region dependency may not reference a consumable currency item."""
from __future__ import annotations

import contextlib
import io
import unittest

from ap_harness import generate


def _quiet(**kw):
    with contextlib.redirect_stderr(io.StringIO()):
        return generate(**kw)


BASE = dict(
    tasks=["Sweep", "Mop", "Bake"],
    items=["Broom", "Gold", "Oven"],
    item_types=["progression"] * 3,
    item_consumable=["", "true", ""],
    task_cost=["", "", '"Gold"'],
    regions=["Hall", "Kitchen"],
    task_region=["Hall", "Hall", "Kitchen"],
)


def world(**extra):
    return _quiet(**{**BASE, **extra})


class RegionCurrencyDependencyTest(unittest.TestCase):
    def _err(self, **extra):
        with self.assertRaises(Exception) as cm:
            world(**extra)
        return str(cm.exception)

    def test_currency_by_index_is_rejected(self):
        msg = self._err(region_prereqs=["", "item(2)"])
        self.assertIn("consumable currency", msg)

    def test_currency_by_name_is_rejected(self):
        msg = self._err(region_prereqs=["", 'item("Gold")'])
        self.assertIn("consumable currency", msg)

    def test_currency_inside_a_larger_expression_is_rejected(self):
        msg = self._err(region_prereqs=["", 'item(1 || "Gold")'])
        self.assertIn("consumable currency", msg)

    def test_non_currency_item_is_still_allowed(self):
        w = world(region_prereqs=["", "item(1)"])
        self.assertTrue(w._rewards)


if __name__ == "__main__":
    unittest.main()
