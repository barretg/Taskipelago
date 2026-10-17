"""Renewable clicker tasks: option parsing, cost logic and slot_data shape."""
from __future__ import annotations

import contextlib
import io
import unittest

from ap_harness import generate, load_world


def _quiet(**kw):
    with contextlib.redirect_stderr(io.StringIO()) as err:
        w = generate(**kw)
    return w, err.getvalue()


# Two Gold items, one Mixer. Task 1 is free, task 2 is the Gold producer
# (costs 1 Gold), tasks 3 and 4 each cost 2 Gold, more than the supply allows
# cumulatively.
BASE = dict(
    tasks=["Start", "Mine", "Buy A", "Buy B"],
    items=["Gold", "Mixer", "Broom"],
    item_count=["2", "1", "1"],
    item_types=["progression", "progression", "junk"],
    item_consumable=["true", "false", "false"],
    task_cost=["", '"Gold"', '"Gold"*2', '"Gold"*2'],
    clicker_mode=True,
)


def world(**extra):
    return _quiet(**{**BASE, **extra})[0]


class _State:
    def __init__(self, items):
        self.items = items

    def has_any(self, names, player):
        return any(self.items.get(n, 0) for n in names)

    def has_from_list(self, names, player, count):
        return sum(self.items.get(n, 0) for n in names) >= count


class RenewableTest(unittest.TestCase):
    def test_without_renewable_the_cumulative_barrier_fails(self):
        with self.assertRaisesRegex(Exception, "cumulative AP logic|not enough consumable"):
            _quiet(**BASE)

    def test_renewable_lifts_the_barrier(self):
        w = world(task_renewable=["", '"Gold"*3', "", ""])
        self.assertEqual(w._clicker_renewable, [None, ("Gold", 3), None, None])
        # The producer pays its own cost from items; buyers need the producer.
        self.assertEqual(w._task_cost_reqs[1], [[("Gold", 1, [])]])
        self.assertEqual(w._task_cost_reqs[2], [[("Gold", None, [1])]])
        sd = w.fill_slot_data()
        self.assertEqual(sd["task_renewable"], [None, ["Gold", 3], None, None])
        self.assertEqual(sd["task_cost_reqs"][2],
                         [[{"consumable": "Gold", "threshold": None, "producers": [1]}]])

    def test_amount_defaults_to_one(self):
        w = world(task_renewable=["", '"Gold"', "", ""])
        self.assertEqual(w._clicker_renewable[1], ("Gold", 1))

    def test_rule_shape(self):
        rules = load_world().rules
        w = world(task_renewable=["", '"Gold"', "", ""])
        tokens = w._token_item_names
        cd = w._consumable_group_display_names
        gold = cd["Gold"]
        buy = w._task_cost_reqs[2][0][0]
        self.assertFalse(rules._cost_req_met(_State({gold[0]: 2}), 1, buy, cd, tokens))
        self.assertTrue(rules._cost_req_met(_State({tokens[1]: 1}), 1, buy, cd, tokens))
        mine = w._task_cost_reqs[1][0][0]
        self.assertTrue(rules._cost_req_met(_State({gold[0]: 1}), 1, mine, cd, tokens))

    def test_off_outside_clicker_mode(self):
        with self.assertRaises(Exception):
            _quiet(**{**BASE, "clicker_mode": False, "task_renewable": ["", '"Gold"', "", ""]})

    def test_unknown_currency(self):
        with self.assertRaisesRegex(Exception, "not a consumable"):
            world(task_renewable=["", '"Mixer"', "", ""])

    def test_bad_syntax(self):
        with self.assertRaisesRegex(Exception, "task_renewable"):
            world(task_renewable=["", "Gold*0", "", ""])

    def test_manual_task_cannot_renew(self):
        with self.assertRaisesRegex(Exception, "manual task"):
            world(task_renewable=["", '"Gold"', "", ""], task_manual=["", "true", "", ""])

    def test_unaffordable_producer(self):
        with self.assertRaisesRegex(Exception, "renewable task for 'Gold'"):
            world(task_renewable=["", '"Gold"', "", ""], task_cost=["", '"Gold"*3', "", ""])

    def test_expands_with_task_count(self):
        w = world(tasks=["Start", "Mine", "Buy"], task_count=["1", "2", "1"],
                  task_cost=["", '"Gold"', '"Gold"*2'], task_renewable=["", '"Gold"*2', ""])
        self.assertEqual(w._clicker_renewable, [None, ("Gold", 2), ("Gold", 2), None])
        # Either producer lets the other skip its own cost.
        self.assertEqual(w._task_cost_reqs[1], [[("Gold", 1, [2])]])
        self.assertEqual(w._task_cost_reqs[3], [[("Gold", None, [1, 2])]])


if __name__ == "__main__":
    unittest.main()
