"""Run TaskipelagoWorld.generate_early headlessly with minimal Archipelago stubs."""
from __future__ import annotations

import enum
import importlib.util
import os
import random
import sys
import types

from helpers import WORLD

_PKG = "_taskipelago_gen_test"


def _install_stubs() -> None:
    if "BaseClasses" in sys.modules and getattr(sys.modules["BaseClasses"], "_tp_stub", False):
        return

    base = types.ModuleType("BaseClasses")
    base._tp_stub = True

    class ItemClassification(enum.IntFlag):
        filler = 0
        progression = 1
        useful = 2
        trap = 4

    class Item:
        def __init__(self, name, classification, code, player):
            self.name, self.classification, self.code, self.player = name, classification, code, player

    class Location:
        def __init__(self, player, name, address, parent):
            self.player, self.name, self.address, self.parent_region = player, name, address, parent

    class Region:
        def __init__(self, name, player, multiworld):
            self.name, self.player, self.multiworld, self.locations = name, player, multiworld, []

    base.Item, base.Location, base.Region, base.ItemClassification = Item, Location, Region, ItemClassification
    sys.modules["BaseClasses"] = base

    opts = types.ModuleType("Options")
    for name in ("PerGameCommonOptions", "OptionList", "Toggle", "Range", "Choice", "DeathLink"):
        setattr(opts, name, type(name, (), {}))
    sys.modules["Options"] = opts

    worlds = types.ModuleType("worlds")
    worlds.__path__ = []
    worlds.network_data_package = {"games": {}}
    auto = types.ModuleType("worlds.AutoWorld")
    auto.World = type("World", (), {"get_data_package_data": classmethod(lambda cls: {})})
    auto.WebWorld = type("WebWorld", (), {})
    launcher = types.ModuleType("worlds.LauncherComponents")
    launcher.Component = lambda *a, **k: None
    launcher.Type = types.SimpleNamespace(CLIENT=0)
    launcher.components = []
    launcher.launch_subprocess = lambda *a, **k: None
    sys.modules.update({"worlds": worlds, "worlds.AutoWorld": auto, "worlds.LauncherComponents": launcher})


def load_world():
    _install_stubs()
    if _PKG in sys.modules:
        return sys.modules[_PKG]
    spec = importlib.util.spec_from_file_location(
        _PKG, os.path.join(WORLD, "__init__.py"), submodule_search_locations=[WORLD]
    )
    module = importlib.util.module_from_spec(spec)
    sys.modules[_PKG] = module
    spec.loader.exec_module(module)
    return module


class _Opt:
    def __init__(self, value):
        self.value = value

    def __bool__(self):
        return bool(self.value)

    def __int__(self):
        return int(self.value)


_DEFAULTS = {
    "tasks": [], "items": [], "item_types": [], "item_fillers": [], "item_consumable": [],
    "item_count": [], "task_count": [], "task_cost": [], "task_prereqs": [],
    "task_description": [], "item_prereqs": [], "lock_prereqs": False, "task_priority": [],
    "goal_tasks": [], "hide_unreachable_tasks": False, "death_link": False,
    "death_link_pool": [], "death_link_weights": [], "death_link_amnesty": 0,
    "death_link_lock_tasks": False, "progressive_groups": [], "item_progressive_group": [],
    "progressive_group_colors": [], "group_types": [], "group_random_pick": [],
    "group_default_pcts": [], "regions": [], "region_default_pcts": [], "region_colors": [],
    "region_prereqs": [], "region_random_pick": [], "region_random_order": [], "task_region": [], "bingo_mode": False,
    "bingo_dimension_x": 5, "bingo_dimension_y": 5, "bingoal": 1, "task_reward_previews": 0,
    "style_colors": [],
    # Tasclickpelago
    "clicker_mode": False, "task_activations": [], "item_production": [],
    "item_click_power": [], "item_production_mult": [], "item_click_mult": [],
    "item_offline_mult": [], "region_distributed_production": [],
    "clicker_distribute_global": False, "clicker_offline_progress": True,
    "clicker_offline_rate": [], "region_offline_rate": [], "clicker_offline_cap_hours": 8,
}


class _MultiWorld:
    def __init__(self):
        self.worlds = []
        self.player_name = {1: "P1"}

    def get_game_worlds(self, game):
        return list(self.worlds)


def generate(seed: int = 1, **options):
    """Return a world after generate_early. Unknown option keys raise."""
    mod = load_world()
    unknown = set(options) - set(_DEFAULTS)
    if unknown:
        raise KeyError(f"unknown options: {sorted(unknown)}")
    world = mod.TaskipelagoWorld.__new__(mod.TaskipelagoWorld)
    values = {**_DEFAULTS, **options}
    world.options = types.SimpleNamespace(**{k: _Opt(v) for k, v in values.items()})
    world.options.priority_locations = _Opt(set())
    world.random = random.Random(seed)
    world.player = 1
    world.multiworld = _MultiWorld()
    world.multiworld.worlds.append(world)
    random.seed(seed)
    world.generate_early()
    return world
