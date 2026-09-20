"""Tasclickpelago option validation and slot_data shape (generate_early via AP stubs)."""
from __future__ import annotations

import contextlib
import io
import unittest

from ap_harness import generate


def _quiet(**kw):
    with contextlib.redirect_stderr(io.StringIO()) as err:
        w = generate(**kw)
    return w, err.getvalue()


BASE = dict(
    tasks=["Bake Bread", "Knead", "Sweep"],
    items=["Oven", "Mixer", "Broom"],
    item_types=["progression", "progression", "junk"],
    regions=["Kitchen"],
    task_region=["Kitchen", "Kitchen", ""],
)


def world(**extra):
    return _quiet(**{**BASE, "clicker_mode": True, **extra})[0]


class TaskActivationsTest(unittest.TestCase):
    def test_blank_defaults_to_one_click(self):
        w = world()
        self.assertEqual(w._clicker_activations, [1, 1, 1])

    def test_literals_and_n_tasks_expressions(self):
        w = world(task_activations=["100", "10 * N_TASKS", ""])
        self.assertEqual(w._clicker_activations, [100, 30, 1])

    def test_rounds_up(self):
        w = world(task_activations=["2.5", "1.1", "4"])
        self.assertEqual(w._clicker_activations, [3, 2, 4])

    def test_below_one_is_rejected(self):
        with self.assertRaises(Exception) as cm:
            world(task_activations=["0.2"])
        self.assertIn("must be at least 1", str(cm.exception))

    def test_live_constants_are_rejected(self):
        with self.assertRaises(Exception) as cm:
            world(task_activations=["N_TASKS_UNLOCKED"])
        self.assertIn("changes during play", str(cm.exception))
        self.assertIn("task_activations", str(cm.exception))

    def test_garbage_is_rejected(self):
        with self.assertRaises(Exception) as cm:
            world(task_activations=["lots"])
        self.assertIn("unknown name 'lots'", str(cm.exception))

    def test_expands_by_task_count(self):
        w = _quiet(**{**BASE, "clicker_mode": True,
                      "task_count": ["2", "1", "1"],
                      "task_activations": ["5", "7", "9"]})[0]
        self.assertEqual(w._clicker_activations, [5, 5, 7, 9])


class ItemProductionTest(unittest.TestCase):
    def test_targets_resolve(self):
        w = world(item_production=['"Bake Bread"-1.5', 'Kitchen-0.5', '*-0.1'])
        self.assertEqual(w._clicker_production[0], [{"kind": "task", "ref": 0, "rate": 1.5}])
        self.assertEqual(w._clicker_production[1], [{"kind": "region", "ref": "Kitchen", "rate": 0.5}])
        self.assertEqual(w._clicker_production[2], [{"kind": "all", "ref": None, "rate": 0.1}])

    def test_index_targets_and_multiple_targets(self):
        w = world(item_production=['2-1 && Kitchen-0.25', "", ""])
        self.assertEqual(w._clicker_production[0], [
            {"kind": "task", "ref": 1, "rate": 1},
            {"kind": "region", "ref": "Kitchen", "rate": 0.25},
        ])

    def test_live_rate_ships_as_an_ast(self):
        w = world(item_production=["*-0.1 * (1 + N_TASKS_UNLOCKED)"])
        self.assertEqual(w._clicker_production[0][0]["rate"], {
            "op": "*", "l": {"num": 0.1},
            "r": {"op": "+", "l": {"num": 1}, "r": {"const": "N_TASKS_UNLOCKED"}},
        })

    def test_n_tasks_rate_is_folded(self):
        w = world(item_production=["*-0.1 * N_TASKS"])
        self.assertAlmostEqual(w._clicker_production[0][0]["rate"], 0.3)

    def test_unknown_task_target(self):
        with self.assertRaises(Exception) as cm:
            world(item_production=['"Nope"-1'])
        self.assertIn("unknown task 'Nope'", str(cm.exception))

    def test_unknown_region_target(self):
        with self.assertRaises(Exception) as cm:
            world(item_production=['Garage-1'])
        self.assertIn("unknown region 'Garage'", str(cm.exception))

    def test_index_out_of_range(self):
        with self.assertRaises(Exception) as cm:
            world(item_production=["9-1"])
        self.assertIn("out of range", str(cm.exception))

    def test_malformed_pair(self):
        with self.assertRaises(Exception) as cm:
            world(item_production=["1.5"])
        self.assertIn("Expected '<target>-<value>'", str(cm.exception))

    def test_non_positive_rate_is_rejected(self):
        with self.assertRaises(Exception) as cm:
            world(item_production=["*-0"])
        self.assertIn("greater than 0", str(cm.exception))

    def test_a_rate_that_dips_to_zero_across_the_range_is_rejected(self):
        # 0.1 * N_TASKS_UNLOCKED is 0 before anything is unlocked.
        with self.assertRaises(Exception) as cm:
            world(item_production=["*-0.1 * N_TASKS_UNLOCKED"])
        self.assertIn("greater than 0", str(cm.exception))

    def test_expands_by_item_count(self):
        w = _quiet(**{**BASE, "clicker_mode": True,
                      "item_count": ["2", "1", "1"],
                      "item_production": ["*-1", "*-2", "*-3"]})[0]
        rates = [specs[0]["rate"] for specs in w._clicker_production]
        self.assertEqual(rates, [1, 1, 2])  # trimmed to the 3 tasks


class MultiplierTest(unittest.TestCase):
    def test_click_power_and_multipliers(self):
        w = world(item_click_power=["5", "", "2.5"],
                  item_production_mult=["1.15", "", ""],
                  item_click_mult=["", "2", ""])
        self.assertEqual(w._clicker_click_power, [5, 0, 2.5])
        self.assertEqual(w._clicker_production_mult, [1.15, None, None])
        self.assertEqual(w._clicker_click_mult, [None, 2, None])

    def test_multipliers_round_to_two_places(self):
        w = world(item_production_mult=["1.15555"])
        self.assertEqual(w._clicker_production_mult[0], 1.16)

    def test_a_multiplier_below_one_is_legal(self):
        w = world(item_production_mult=["0.75"])
        self.assertEqual(w._clicker_production_mult[0], 0.75)

    def test_zero_multiplier_is_rejected(self):
        with self.assertRaises(Exception) as cm:
            world(item_production_mult=["0"])
        self.assertIn("greater than 0", str(cm.exception))

    def test_negative_click_power_is_rejected(self):
        with self.assertRaises(Exception) as cm:
            world(item_click_power=["-1"])
        self.assertIn("at least 0", str(cm.exception))

    def test_offline_multiplier_takes_every_target_kind(self):
        w = world(item_offline_mult=['"Sweep"-2', 'Kitchen-1.5', "*-3"])
        self.assertEqual(w._clicker_offline_mult[0], [{"kind": "task", "ref": 2, "rate": 2}])
        self.assertEqual(w._clicker_offline_mult[1], [{"kind": "region", "ref": "Kitchen", "rate": 1.5}])
        self.assertEqual(w._clicker_offline_mult[2], [{"kind": "all", "ref": None, "rate": 3}])


class OfflineAndRegionTest(unittest.TestCase):
    def test_defaults(self):
        w = world()
        self.assertEqual(w._clicker_distributed, {"Kitchen": False})
        self.assertEqual(w._clicker_region_offline_rate, {})
        self.assertEqual(w._clicker_offline_rate, 1)
        self.assertTrue(w._clicker_offline_progress)
        self.assertEqual(w._clicker_offline_cap_hours, 8)

    def test_distributed_flag(self):
        w = world(region_distributed_production=["true"])
        self.assertEqual(w._clicker_distributed, {"Kitchen": True})

    def test_bad_distributed_flag(self):
        with self.assertRaises(Exception) as cm:
            world(region_distributed_production=["maybe"])
        self.assertIn("expected 'true', 'false' or blank", str(cm.exception))

    def test_extra_region_entries_warn_but_pass(self):
        _w, err = _quiet(**{**BASE, "clicker_mode": True,
                            "region_distributed_production": ["true", "false"]})
        self.assertIn("region_distributed_production has 2 entries", err)

    def test_region_and_global_offline_rates(self):
        w = world(clicker_offline_rate=["0.25"], region_offline_rate=["0"])
        self.assertEqual(w._clicker_offline_rate, 0.25)
        self.assertEqual(w._clicker_region_offline_rate, {"Kitchen": 0})

    def test_negative_offline_rate_is_rejected(self):
        with self.assertRaises(Exception) as cm:
            world(clicker_offline_rate=["-1"])
        self.assertIn("at least 0", str(cm.exception))

    def test_warns_when_offline_is_off_but_configured(self):
        _w, err = _quiet(**{**BASE, "clicker_mode": True,
                            "clicker_offline_progress": False,
                            "clicker_offline_rate": ["0.5"]})
        self.assertIn("clicker_offline_progress is off", err)

    def test_warns_when_nothing_grants_production(self):
        _w, err = _quiet(**{**BASE, "clicker_mode": True})
        self.assertIn("no item grants production", err)

    def test_no_warning_when_an_item_grants_production(self):
        _w, err = _quiet(**{**BASE, "clicker_mode": True, "item_production": ["*-1"]})
        self.assertNotIn("no item grants production", err)


class ConflictAndCompatTest(unittest.TestCase):
    def test_bingo_and_clicker_conflict(self):
        with self.assertRaises(Exception) as cm:
            world(bingo_mode=True)
        self.assertIn("cannot both be enabled", str(cm.exception))

    def test_constants_are_reserved_names(self):
        for opts in (dict(regions=["N_TASKS"], task_region=["", "", ""]),
                     dict(progressive_groups=["N_TASKS_LOCKED"]),
                     dict(items=["N_TASKS", "b", "c"])):
            with self.assertRaises(Exception) as cm:
                _quiet(**{**BASE, **opts})
            self.assertIn("reserved word", str(cm.exception))

    def test_a_seed_with_no_clicker_options_is_unchanged(self):
        plain = _quiet(**BASE)[0]
        self.assertFalse(plain._clicker_mode)
        self.assertEqual(plain._clicker_activations, [1, 1, 1])
        self.assertEqual(plain._clicker_production, [[], [], []])
        self.assertEqual(plain._clicker_click_power, [0, 0, 0])
        self.assertEqual(plain._clicker_production_mult, [None, None, None])


class SlotDataTest(unittest.TestCase):
    def test_slot_data_shape(self):
        import json

        w = world(task_activations=["10", "20", "30"],
                  item_production=["*-0.5 * (1 + N_TASKS_UNLOCKED)", 'Kitchen-2', ""],
                  item_click_power=["3", "", ""],
                  item_production_mult=["1.5", "", ""],
                  item_click_mult=["", "2", ""],
                  item_offline_mult=["*-2", "", ""],
                  region_distributed_production=["true"],
                  clicker_distribute_global=True,
                  clicker_offline_rate=["0.25"],
                  region_offline_rate=["0.5"],
                  clicker_offline_cap_hours=12)
        w._goal_indices = set()
        w._raw_goal = ""
        w._goal_region_reqs = []
        sd = w.fill_slot_data()
        json.dumps(sd)  # slot_data must be JSON-serializable
        self.assertTrue(sd["clicker_mode"])
        self.assertEqual(sd["task_activations"], [10, 20, 30])
        self.assertEqual(len(sd["item_production"]), 3)
        self.assertEqual(sd["item_click_power"], [3, 0, 0])
        self.assertEqual(sd["item_production_mult"], [1.5, None, None])
        self.assertEqual(sd["item_click_mult"], [None, 2, None])
        self.assertEqual(sd["item_offline_mult"][0], [{"kind": "all", "ref": None, "rate": 2}])
        self.assertEqual(sd["region_distributed_production"], {"Kitchen": True})
        self.assertTrue(sd["clicker_distribute_global"])
        self.assertTrue(sd["clicker_offline_progress"])
        self.assertEqual(sd["clicker_offline_rate"], 0.25)
        self.assertEqual(sd["region_offline_rate"], {"Kitchen": 0.5})
        self.assertEqual(sd["clicker_offline_cap_hours"], 12)


if __name__ == "__main__":
    unittest.main()
