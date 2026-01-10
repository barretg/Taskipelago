from __future__ import annotations

from typing import Dict, List, Any

from BaseClasses import Item, ItemClassification, Location, Region
from worlds.AutoWorld import World, WebWorld
from worlds.LauncherComponents import Component, Type, components, launch_subprocess

from .options import TaskipelagoOptions

print("Loading Taskipelago world module...")

BASE_LOCATION_ID = 910_000
BASE_ITEM_ID = 911_000
MAX_TASKS = 1000

class TaskipelagoWeb(WebWorld):
    game = "Taskipelago"


class TaskipelagoItem(Item):
    game = "Taskipelago"


class TaskipelagoLocation(Location):
    game = "Taskipelago"


class TaskipelagoWorld(World):
    game = "Taskipelago"
    web = TaskipelagoWeb()
    options_dataclass = TaskipelagoOptions

    # These get populated during generate_early() for the current generation run.
    item_name_to_id: Dict[str, int] = {}
    location_name_to_id: Dict[str, int] = {}

    # Pre-register a stable ID->name mapping so the server can resolve names and stuff.
    location_name_to_id = {f"Task {i}": BASE_LOCATION_ID + (i - 1) for i in range(1, MAX_TASKS + 1)}
    item_name_to_id = {f"Reward {i}": BASE_ITEM_ID + (i - 1) for i in range(1, MAX_TASKS + 1)}

    def generate_early(self) -> None:
        tasks = [str(t).strip() for t in self.options.tasks.value if str(t).strip()]
        rewards = [str(r).strip() for r in self.options.rewards.value if str(r).strip()]

        if not tasks:
            raise Exception("Taskipelago: tasks list is empty.")
        if len(tasks) != len(rewards):
            raise Exception(f"Taskipelago: tasks ({len(tasks)}) and rewards ({len(rewards)}) must be same length.")

        # If DeathLink is enabled (after weights resolve), require pool non-empty.
        if bool(self.options.death_link):
            dl_pool = [str(x).strip() for x in self.options.death_link_pool.value if str(x).strip()]
            if not dl_pool:
                raise Exception("Taskipelago: death_link is enabled but death_link_pool is empty.")

        self._tasks = tasks
        self._rewards = rewards
        n = len(tasks)
        if n > MAX_TASKS:
            raise Exception(f"Taskipelago: too many tasks ({n}). Max supported is {MAX_TASKS}.")

        # Stable names that won't collide across different YAML sets.
        self._location_names = [f"Task {i+1}" for i in range(n)]
        self._item_names = [f"Reward {i+1}" for i in range(n)]

        # Build ID maps for this generation
        self.location_name_to_id = {name: BASE_LOCATION_ID + i for i, name in enumerate(self._location_names)}
        self.item_name_to_id = {name: BASE_ITEM_ID + i for i, name in enumerate(self._item_names)}

    def create_regions(self) -> None:
        menu = Region("Menu", self.player, self.multiworld)
        tasks_region = Region("Tasks", self.player, self.multiworld)

        for loc_name in self._location_names:
            loc_id = self.location_name_to_id[loc_name]
            tasks_region.locations.append(TaskipelagoLocation(self.player, loc_name, loc_id, tasks_region))

        self.multiworld.regions += [menu, tasks_region]
        menu.connect(tasks_region)

    def create_items(self) -> None:
        # These are the "rewards" items that will be distributed throughout the multiworld.
        # For v1 treat them as filler so they don't break logic in other games.
        for name in self._item_names:
            self.multiworld.itempool.append(
                TaskipelagoItem(name, ItemClassification.filler, self.item_name_to_id[name], self.player)
            )

    def set_rules(self) -> None:
        # No access rules; tasks are client-checked.
        pass

    def generate_basic(self) -> None:
        my_locations = [self.multiworld.get_location(name, self.player) for name in self._location_names]
        self.multiworld.completion_condition[self.player] = lambda state: all(
            loc in state.locations_checked for loc in my_locations
        )

    def fill_slot_data(self) -> Dict[str, Any]:
        # Client-facing strings so the GUI can show real task/reward text.
        return {
            "tasks": list(self._tasks),
            "rewards": list(self._rewards),
            "death_link_pool": [str(x).strip() for x in self.options.death_link_pool.value if str(x).strip()],
            "death_link_enabled": bool(self.options.death_link),
            "base_location_id": BASE_LOCATION_ID,
            "task_prereqs": [str(x).strip() for x in self.options.task_prereqs.value],
            "lock_prereqs": bool(self.options.lock_prereqs),
            "base_item_id": BASE_ITEM_ID,
        }

def launch_client(*args):
    from .client import launch
    launch_subprocess(launch, name="TaskipelagoClient", args=args)

components.append(
    Component(
        "Taskipelago Client",
        func=launch_client,
        component_type=Type.CLIENT,
    )
)