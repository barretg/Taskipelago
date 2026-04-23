from __future__ import annotations

from typing import Any, Dict, List

from BaseClasses import Item, ItemClassification, Region
from worlds.AutoWorld import WebWorld, World
from worlds.LauncherComponents import Component, Type, components, launch_subprocess

from .items import (
    ITEM_NAME_TO_ID,
    MAX_TASKS,
    BASE_ITEM_ID,
    BASE_TOKEN_ID,
    TaskipelagoItem,
    get_item_classification,
)
from .locations import (
    LOCATION_NAME_TO_ID,
    BASE_COMPLETE_LOC_ID,
    BASE_REWARD_LOC_ID,
    TaskipelagoLocation,
)
from .options import TaskipelagoOptions
from .prereq_parser import collect_leaves, parse_prereq, Node
from .rules import set_rules as _set_rules


class TaskipelagoWeb(WebWorld):
    game = "Taskipelago"


class TaskipelagoWorld(World):
    """
    Taskipelago: a manual-task multiworld game where players complete real-world
    tasks to send items to their multiworld allies.
    """

    game = "Taskipelago"
    web = TaskipelagoWeb()
    options_dataclass = TaskipelagoOptions

    item_name_to_id: Dict[str, int] = ITEM_NAME_TO_ID
    location_name_to_id: Dict[str, int] = LOCATION_NAME_TO_ID

    # --- Per-generation state (set in generate_early) ---
    _tasks: List[str]
    _rewards: List[str]
    _reward_types: List[str]
    _raw_prereqs: List[str]
    _parsed_prereqs: List[Node | None]
    _raw_reward_prereqs: List[str]
    _parsed_reward_prereqs: List[Node | None]
    _forced_progression_rewards: set
    _lock_prereqs: bool
    _reward_location_names: List[str]
    _complete_location_names: List[str]
    _reward_item_names: List[str]
    _token_item_names: List[str]
    _death_link_pool: List[str]
    _death_link_weights: List[float]
    _death_link_amnesty: int
    _hide_unreachable_tasks: bool

    def generate_early(self) -> None:
        tasks = [str(t).strip() for t in self.options.tasks.value if str(t).strip()]
        rewards = [str(r).strip() for r in self.options.rewards.value if str(r).strip()]

        reward_types_raw = list(self.options.reward_types.value)
        reward_types = [str(x).strip().lower() for x in reward_types_raw if str(x).strip()]

        if not tasks:
            raise Exception("Taskipelago: tasks list is empty.")
        if len(tasks) != len(rewards):
            raise Exception(
                f"Taskipelago: tasks ({len(tasks)}) and rewards ({len(rewards)}) must be the same length."
            )

        n = len(tasks)
        if n > MAX_TASKS:
            raise Exception(f"Taskipelago: too many tasks ({n}). Max is {MAX_TASKS}.")

        # Normalize reward_types to task count, defaulting to "junk".
        allowed_types = {"trap", "junk", "useful", "progression"}
        if len(reward_types) < n:
            reward_types += ["junk"] * (n - len(reward_types))
        reward_types = [rt if rt in allowed_types else "junk" for rt in reward_types[:n]]

        self._tasks = tasks
        self._rewards = rewards
        self._reward_types = reward_types

        # --- DeathLink validation ---
        if bool(self.options.death_link):
            dl_pool = [str(x).strip() for x in self.options.death_link_pool.value if str(x).strip()]
            if not dl_pool:
                raise Exception(
                    "Taskipelago: death_link is enabled but death_link_pool is empty."
                )

            raw_w = [str(x).strip() for x in self.options.death_link_weights.value or []]
            if len(raw_w) < len(dl_pool):
                raw_w += ["1"] * (len(dl_pool) - len(raw_w))
            raw_w = raw_w[:len(dl_pool)]

            parsed_w: List[float] = []
            for idx, txt in enumerate(raw_w):
                try:
                    parsed_w.append(max(0.0, float(txt) if txt else 1.0))
                except ValueError:
                    raise Exception(
                        f"Taskipelago: invalid death_link_weights[{idx}]={txt!r}. Must be a number."
                    )

            self._death_link_pool = dl_pool
            self._death_link_weights = parsed_w
        else:
            self._death_link_pool = []
            self._death_link_weights = []

        self._death_link_amnesty = int(self.options.death_link_amnesty.value or 0)

        # --- set hiding of unreachable tasks ---
        self._hide_unreachable_tasks = bool(self.options.hide_unreachable_tasks.value)
        
        # --- Parse task prereqs ---
        raw_prereqs = [str(x).strip() for x in list(self.options.task_prereqs.value or [])]
        if len(raw_prereqs) < n:
            raw_prereqs += [""] * (n - len(raw_prereqs))
        raw_prereqs = raw_prereqs[:n]

        parsed_prereqs = []
        for i, txt in enumerate(raw_prereqs):
            ast = parse_prereq(txt, n, i, "task prereq")
            if ast is not None and i in collect_leaves(ast):
                raise Exception(f"Taskipelago: task {i + 1} cannot require itself.")
            parsed_prereqs.append(ast)

        # Cycle detection via DFS.
        _assert_no_cycles(parsed_prereqs, n)

        # --- Parse reward prereqs ---
        raw_reward_prereqs = [str(x).strip() for x in list(self.options.reward_prereqs.value or [])]
        if len(raw_reward_prereqs) < n:
            raw_reward_prereqs += [""] * (n - len(raw_reward_prereqs))
        raw_reward_prereqs = raw_reward_prereqs[:n]

        parsed_reward_prereqs = []
        for i, txt in enumerate(raw_reward_prereqs):
            parsed_reward_prereqs.append(parse_prereq(txt, n, i, "reward prereq"))

        # --- Parse goal tasks ---
        raw_goal_parts = [str(x).strip() for x in list(self.options.goal_tasks.value or []) if str(x).strip()]
        raw_goal = ", ".join(raw_goal_parts)  # rejoin into single expression
        goal_ast = parse_prereq(raw_goal, n, 0, "goal_tasks") if raw_goal else None
        self._raw_goal = raw_goal
        self._goal_ast = goal_ast

        # 0-based indices of all tasks referenced in goal (for slot data)
        self._goal_indices = sorted(set(collect_leaves(goal_ast))) if goal_ast else []

        # Any reward referenced as a prereq must be progression so logic can rely on it.
        forced_prog: set = set()
        for ast in parsed_prereqs:
            forced_prog.update(collect_leaves(ast))
        for ast in parsed_reward_prereqs:
            forced_prog.update(collect_leaves(ast))

        self._raw_prereqs = raw_prereqs
        self._parsed_prereqs = parsed_prereqs       # List[Node | None]
        self._raw_reward_prereqs = raw_reward_prereqs
        self._parsed_reward_prereqs = parsed_reward_prereqs  # List[Node | None]
        self._forced_progression_rewards = forced_prog
        self._lock_prereqs = bool(self.options.lock_prereqs)

        # Stable names for this generation.
        self._reward_location_names = [f"Task {i + 1} (Reward)" for i in range(n)]
        self._complete_location_names = [f"Task {i + 1} (Complete)" for i in range(n)]
        self._reward_item_names = [f"Reward {i + 1}" for i in range(n)]
        self._reward_display_names = [
            f"Reward {i + 1}: {r}" if r.strip() else f"Reward {i + 1}"
            for i, r in enumerate(rewards)
        ]
        self._token_item_names = [f"Task Complete {i + 1}" for i in range(n)]

    def create_regions(self) -> None:
        menu = Region("Menu", self.player, self.multiworld)
        tasks_region = Region("Tasks", self.player, self.multiworld)

        for i in range(len(self._tasks)):
            rname = self._reward_location_names[i]
            cname = self._complete_location_names[i]
            rid = LOCATION_NAME_TO_ID[rname]
            cid = LOCATION_NAME_TO_ID[cname]

            tasks_region.locations.append(
                TaskipelagoLocation(self.player, rname, rid, tasks_region)
            )
            tasks_region.locations.append(
                TaskipelagoLocation(self.player, cname, cid, tasks_region)
            )

        self.multiworld.regions += [menu, tasks_region]
        menu.connect(tasks_region)

    def create_items(self) -> None:
        """
        Add N reward items to the item pool.
        Complete locations hold N locked event tokens (not in the pool).
        Total locations: 2N. Pool items from this world: N. Balance maintained.
        """
        for i, name in enumerate(self._reward_item_names):
            rt = self._reward_types[i] if i < len(self._reward_types) else "junk"
            forced = i in self._forced_progression_rewards
            cls = get_item_classification(rt, forced)

            display_name = self._reward_display_names[i]
            self.multiworld.itempool.append(
                TaskipelagoItem(
                    display_name,
                    cls,
                    ITEM_NAME_TO_ID[name],  # stable ID keyed off "Reward {i+1}"
                    self.player,
                )
            )

    def set_rules(self) -> None:
        _set_rules(self)

    def generate_basic(self) -> None:
        # Place locked completion tokens on Complete locations.
        for i, cname in enumerate(self._complete_location_names):
            token_name = self._token_item_names[i]
            complete_loc = self.multiworld.get_location(cname, self.player)
            complete_loc.place_locked_item(
                TaskipelagoItem(
                    token_name,
                    ItemClassification.progression,
                    ITEM_NAME_TO_ID[token_name],
                    self.player,
                )
            )

        # Goal condition: either specific goal tasks, or all tasks by default.
        if self._goal_ast is not None:
            from .prereq_parser import eval_node
            complete_names = self._complete_location_names
            # Goal: the boolean expression over complete locations
            complete_locs = {
                i: self.multiworld.get_location(complete_names[i], self.player)
                for i in collect_leaves(self._goal_ast)
            }
            def goal_condition(state, ast=self._goal_ast, locs=complete_locs):
                # Reuse eval_node but over locations_checked instead of items
                def loc_checked(node):
                    if isinstance(node, int):
                        return locs[node] in state.locations_checked
                    op, children = node
                    if op == "and":
                        return all(loc_checked(c) for c in children)
                    return any(loc_checked(c) for c in children)
                return loc_checked(ast)
            self.multiworld.completion_condition[self.player] = goal_condition
        else:
            reward_locs = [
                self.multiworld.get_location(name, self.player)
                for name in self._reward_location_names
            ]
            self.multiworld.completion_condition[self.player] = lambda state: all(
                loc in state.locations_checked for loc in reward_locs
            )

    def fill_slot_data(self) -> Dict[str, Any]:
        sent_item_names: List[str] = []
        sent_player_names: List[str] = []

        for loc_name in self._reward_location_names:
            item_name = ""
            player_name = "Unknown"
            try:
                loc = self.multiworld.get_location(loc_name, self.player)
                item = getattr(loc, "item", None)
                if item is not None:
                    item_name = str(getattr(item, "name", "") or "").strip()
                    recipient = getattr(item, "player", None)
                    if recipient is not None:
                        player_name = self.multiworld.player_name.get(
                            recipient, f"Player {recipient}"
                        )
            except Exception:
                pass

            sent_item_names.append(item_name)
            sent_player_names.append(player_name)

        return {
            "tasks": list(self._tasks),
            "rewards": list(self._rewards),
            "reward_types": list(self._reward_types),
            "task_prereqs": list(self._raw_prereqs),
            "reward_prereqs": list(self._raw_reward_prereqs),
            "lock_prereqs": bool(self._lock_prereqs),
            "hide_unreachable_tasks": bool(self._hide_unreachable_tasks),
            "death_link_pool": [
                str(x).strip()
                for x in self.options.death_link_pool.value
                if str(x).strip()
            ],
            "death_link_weights": list(self._death_link_weights),
            "death_link_amnesty": int(self._death_link_amnesty),
            "death_link_enabled": bool(self.options.death_link),
            "base_reward_location_id": BASE_REWARD_LOC_ID,
            "base_complete_location_id": BASE_COMPLETE_LOC_ID,
            "base_item_id": BASE_ITEM_ID,
            "sent_item_names": sent_item_names,
            "sent_player_names": sent_player_names,
            "goal_indices": sorted(self._goal_indices),
            "goal_expression": self._raw_goal,
        }


# --- Helpers ---

def _parse_prereq_list(txt: str, task_index: int, n: int, label: str) -> List[int]:
    """Parse a comma-separated prereq string into a deduplicated list of 0-based indices."""
    if not txt:
        return []
    parts = [p.strip() for p in txt.split(",") if p.strip()]
    reqs: List[int] = []
    seen: set = set()
    for p in parts:
        try:
            idx_1 = int(p)
        except ValueError:
            raise Exception(
                f"Taskipelago: invalid {label} '{p}' on task {task_index + 1}. "
                f"Use comma-separated integers like '1,2'."
            )
        if idx_1 < 1 or idx_1 > n:
            raise Exception(
                f"Taskipelago: {label} '{idx_1}' on task {task_index + 1} is out of range (1..{n})."
            )
        idx_0 = idx_1 - 1
        if idx_0 not in seen:
            seen.add(idx_0)
            reqs.append(idx_0)
    return reqs


def _assert_no_cycles(parsed_prereqs: list, n: int) -> None:
    """DFS Cycle detection on the prereq graph. Raises if a cycle is found, otherwise does nothing."""
    from .prereq_parser import collect_leaves
    visiting: set = set()
    visited: set = set()

    def dfs(v: int) -> None:
        if v in visiting:
            raise Exception("Taskipelago: prereq graph contains a cycle. Fix your prereqs.")
        if v in visited:
            return
        visiting.add(v)
        for u in collect_leaves(parsed_prereqs[v]):
            dfs(u)
        visiting.discard(v)
        visited.add(v)

    for i in range(n):
        dfs(i)


# --- Client launcher registration ---

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