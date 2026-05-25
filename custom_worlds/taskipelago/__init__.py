from __future__ import annotations

import re as _re
from typing import Any, Dict, List, Tuple

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
from .prereq_parser import (
    collect_leaves, collect_group_refs, collect_region_refs,
    eval_node, parse_prereq, resolve_ast_refs, Node,
)
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

    # Static fallbacks used before any generation (e.g. server startup, data package requests).
    # stage_generate_early replaces these with actual reward names and player-specific IDs.
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
    _progressive_groups: List[str]
    _reward_to_group: List[str]
    _group_to_reward_indices: Dict[str, List[int]]
    _task_progressive_reqs: List[List[Tuple[str, int]]]
    _group_item_display_names: Dict[str, List[str]]
    _regions: List[str]
    _region_default_pcts: Dict[str, int]
    _task_region: List[str]
    _task_region_reqs: List[List[Tuple[str, int]]]
    _region_to_task_indices: Dict[str, List[int]]
    _region_token_names: Dict[str, List[str]]

    def generate_early(self) -> None:
        import random as _random
        import sys as _sys

        _FILLER_ITEMS = [
            "Several pats on the back",
            "A big thumbs up",
            "Free dopamine",
            "One (1) sense of accomplishment",
            "Mildly increased self-esteem",
            "A crisp high five",
            "A firm handshake",
            "A tiny mental victory parade",
            "Temporary immunity to self-criticism",
            "An imaginary star sticker",
            "A nod of respect",
        ]

        tasks = [str(t).strip() for t in self.options.tasks.value if str(t).strip()]
        items_raw = [str(r).strip() for r in self.options.items.value]

        item_types_raw = list(self.options.item_types.value)
        item_types = [str(x).strip().lower() for x in item_types_raw if str(x).strip()]

        if not tasks:
            raise Exception("Taskipelago: tasks list is empty.")

        n = len(tasks)
        if n > MAX_TASKS:
            raise Exception(f"Taskipelago: too many tasks ({n}). Max is {MAX_TASKS}.")

        # Pad or truncate items to match task count, warning if unbalanced.
        n_items = len([x for x in items_raw if x])
        if n_items != n:
            print(
                f"[Taskipelago] WARNING: Unbalanced item and task counts can lead to generation failures. "
                f"Tasks: {n}, Items: {n_items}.",
                file=_sys.stderr,
            )
        if len(items_raw) < n:
            items_raw += [_random.choice(_FILLER_ITEMS) for _ in range(n - len(items_raw))]
        items_raw = items_raw[:n]
        rewards = [x if x else _random.choice(_FILLER_ITEMS) for x in items_raw]

        # Normalize item_types to task count, defaulting to "junk".
        allowed_types = {"trap", "junk", "useful", "progression"}
        if len(item_types) < n:
            item_types += ["junk"] * (n - len(item_types))
        item_types = [rt if rt in allowed_types else "junk" for rt in item_types[:n]]

        self._tasks = tasks
        self._rewards = rewards
        self._reward_types = item_types

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
        
        # --- Parse regions ---
        raw_regions = [
            str(g).strip() for g in (self.options.regions.value or [])
            if str(g).strip()
        ]
        for rname in raw_regions:
            if _re.search(r'\d', rname):
                raise Exception(
                    f"Taskipelago: region name '{rname}' must not contain digits."
                )
        if len(raw_regions) != len(set(raw_regions)):
            raise Exception("Taskipelago: duplicate region names.")
        region_set = set(raw_regions)

        raw_rdp = [str(x).strip() for x in (self.options.region_default_pcts.value or [])]
        if len(raw_rdp) < len(raw_regions):
            raw_rdp += ["100"] * (len(raw_regions) - len(raw_rdp))
        raw_rdp = raw_rdp[:len(raw_regions)]
        region_default_pcts: Dict[str, int] = {}
        for rname, pct_str in zip(raw_regions, raw_rdp):
            try:
                pct = int(pct_str) if pct_str else 100
            except ValueError:
                raise Exception(
                    f"Taskipelago: invalid default percentage '{pct_str}' for region '{rname}'."
                )
            if pct < 0 or pct > 100:
                raise Exception(
                    f"Taskipelago: region '{rname}' default percentage {pct} must be 0-100."
                )
            region_default_pcts[rname] = pct

        raw_task_region = [str(x).strip() for x in (self.options.task_region.value or [])]
        if len(raw_task_region) < n:
            raw_task_region += [""] * (n - len(raw_task_region))
        raw_task_region = raw_task_region[:n]
        for i, rname in enumerate(raw_task_region):
            if rname and rname not in region_set:
                raise Exception(
                    f"Taskipelago: task {i + 1} references unknown region '{rname}'."
                )
        task_region = raw_task_region

        region_to_task_indices: Dict[str, List[int]] = {r: [] for r in raw_regions}
        for i, rname in enumerate(task_region):
            if rname:
                region_to_task_indices[rname].append(i)

        # --- Parse progressive groups ---
        raw_prog_groups = [
            str(g).strip() for g in (self.options.progressive_groups.value or [])
            if str(g).strip()
        ]
        for gname in raw_prog_groups:
            if _re.search(r'\d', gname):
                raise Exception(
                    f"Taskipelago: progressive group name '{gname}' must not contain digits."
                )
        if len(raw_prog_groups) != len(set(raw_prog_groups)):
            raise Exception("Taskipelago: duplicate progressive group names.")
        prog_group_set = set(raw_prog_groups)

        # --- Map each item to its group ---
        raw_rpg = [str(x).strip() for x in (self.options.item_progressive_group.value or [])]
        if len(raw_rpg) < n:
            raw_rpg += [""] * (n - len(raw_rpg))
        raw_rpg = raw_rpg[:n]

        group_to_reward_indices: Dict[str, List[int]] = {g: [] for g in raw_prog_groups}
        reward_to_group: List[str] = []
        for i, gname in enumerate(raw_rpg):
            if gname:
                if gname not in prog_group_set:
                    raise Exception(
                        f"Taskipelago: reward {i + 1} references unknown progressive group '{gname}'."
                    )
                group_to_reward_indices[gname].append(i)
            reward_to_group.append(gname)

        # --- Parse item prereqs ---
        raw_reward_prereqs_input = [str(x).strip() for x in list(self.options.item_prereqs.value or [])]
        if len(raw_reward_prereqs_input) < n:
            raw_reward_prereqs_input += [""] * (n - len(raw_reward_prereqs_input))
        raw_reward_prereqs_input = raw_reward_prereqs_input[:n]

        # Resolve quoted item names to 1-based indices.
        for _j, _txt in enumerate(raw_reward_prereqs_input):
            _resolved, _errs = _resolve_quoted_names(_txt, items_raw)
            if _errs:
                raise Exception(
                    f"Taskipelago: item prereq for task {_j + 1} references unknown item name(s): "
                    + "; ".join(_errs)
                )
            raw_reward_prereqs_input[_j] = _resolved

        # Parse reward prereqs; group refs become group_ref AST nodes.
        parsed_reward_prereqs_unresolved = []
        for i, txt in enumerate(raw_reward_prereqs_input):
            parsed_reward_prereqs_unresolved.append(
                parse_prereq(txt, n, i, "reward prereq", known_groups=prog_group_set)
            )

        # Collect group refs from ASTs.
        task_group_refs: List[List[Tuple[str, int | None]]] = [
            collect_group_refs(ast) for ast in parsed_reward_prereqs_unresolved
        ]

        # Validate group refs.
        for i, refs in enumerate(task_group_refs):
            for gname, n_val in refs:
                group_size = len(group_to_reward_indices.get(gname, []))
                if group_size == 0:
                    raise Exception(
                        f"Taskipelago: task {i + 1} references progressive group '{gname}' "
                        f"which has no rewards assigned to it."
                    )
                if n_val is not None:
                    if n_val < 1 or n_val > group_size:
                        raise Exception(
                            f"Taskipelago: task {i + 1} uses '{gname}-{n_val}' but group "
                            f"'{gname}' only has {group_size} reward(s). "
                            f"Required count must be between 1 and {group_size}."
                        )

        # Resolve progressive unlock thresholds per group.
        # prog-N means "require at least N items from the group"; multiple tasks may share N.
        # Tasks referencing the group without a number are assigned the lowest unused thresholds.
        task_progressive_reqs: List[List[Tuple[str, int]]] = [[] for _ in range(n)]
        for gname in raw_prog_groups:
            task_refs: List[Tuple[int, int | None]] = []
            for i, refs in enumerate(task_group_refs):
                for ref_group, ref_n in refs:
                    if ref_group == gname:
                        task_refs.append((i, ref_n))

            if not task_refs:
                continue

            group_size = len(group_to_reward_indices[gname])

            # Split into explicit-threshold tasks and implicit tasks.
            explicit_threshold_tasks: Dict[int, List[int]] = {}  # threshold -> [task indices]
            implicit_tasks: List[int] = []
            for ti, n_val in task_refs:
                if n_val is not None:
                    explicit_threshold_tasks.setdefault(n_val, []).append(ti)
                else:
                    implicit_tasks.append(ti)
            implicit_tasks.sort()  # lower task index = lower threshold

            # Each unique explicit threshold plus each implicit task occupies one unlock step.
            num_steps = len(explicit_threshold_tasks) + len(implicit_tasks)
            if num_steps > group_size:
                raise Exception(
                    f"Taskipelago: progressive group '{gname}' has {group_size} reward(s) but "
                    f"requires {num_steps} distinct unlock steps "
                    f"({len(explicit_threshold_tasks)} unique explicit threshold(s) + "
                    f"{len(implicit_tasks)} implicit task(s)). "
                    f"Add more rewards to the group or reduce the number of tasks depending on it."
                )

            # Free thresholds are positions 1..group_size not taken by any explicit ref.
            free_thresholds = [p for p in range(1, group_size + 1) if p not in explicit_threshold_tasks]

            for threshold, task_list in explicit_threshold_tasks.items():
                for ti in task_list:
                    task_progressive_reqs[ti].append((gname, threshold))
            for ti, threshold in zip(implicit_tasks, free_thresholds):
                task_progressive_reqs[ti].append((gname, threshold))

        # Resolve group_ref nodes to group nodes using computed thresholds.
        parsed_reward_prereqs = []
        for i, ast in enumerate(parsed_reward_prereqs_unresolved):
            group_thresh = {gname: count for gname, count in task_progressive_reqs[i]}
            parsed_reward_prereqs.append(resolve_ast_refs(ast, group_thresh, {}))

        # --- Parse task prereqs ---
        raw_prereqs_input = [str(x).strip() for x in list(self.options.task_prereqs.value or [])]
        if len(raw_prereqs_input) < n:
            raw_prereqs_input += [""] * (n - len(raw_prereqs_input))
        raw_prereqs_input = raw_prereqs_input[:n]

        # Resolve quoted task names to 1-based indices.
        for _j, _txt in enumerate(raw_prereqs_input):
            _resolved, _errs = _resolve_quoted_names(_txt, tasks)
            if _errs:
                raise Exception(
                    f"Taskipelago: task prereq for task {_j + 1} references unknown task name(s): "
                    + "; ".join(_errs)
                )
            raw_prereqs_input[_j] = _resolved

        # Parse task prereqs; region refs become region_ref AST nodes.
        parsed_prereqs_unresolved = []
        for i, txt in enumerate(raw_prereqs_input):
            parsed_prereqs_unresolved.append(
                parse_prereq(txt, n, i, "task prereq", known_regions=region_set)
            )

        # Collect region refs from ASTs and resolve percentages.
        task_region_reqs: List[List[Tuple[str, int]]] = []
        for i, ast in enumerate(parsed_prereqs_unresolved):
            refs = collect_region_refs(ast)
            reqs: List[Tuple[str, int]] = []
            for rname, pct_val in refs:
                if task_region[i] == rname:
                    raise Exception(
                        f"Taskipelago: task {i + 1} cannot depend on its own region '{rname}'."
                    )
                pct = pct_val if pct_val is not None else region_default_pcts.get(rname, 100)
                if pct < 0 or pct > 100:
                    raise Exception(
                        f"Taskipelago: task {i + 1} region prereq '{rname}' percentage {pct} must be 0-100."
                    )
                if not region_to_task_indices.get(rname):
                    raise Exception(
                        f"Taskipelago: task {i + 1} references region '{rname}' which has no tasks assigned."
                    )
                reqs.append((rname, pct))
            task_region_reqs.append(reqs)

        # Resolve region_ref nodes to region nodes using computed percentages.
        parsed_prereqs = []
        for i, ast in enumerate(parsed_prereqs_unresolved):
            region_pct = {rname: pct for rname, pct in task_region_reqs[i]}
            ast = resolve_ast_refs(ast, {}, region_pct)
            if ast is not None and i in collect_leaves(ast):
                raise Exception(f"Taskipelago: task {i + 1} cannot require itself.")
            parsed_prereqs.append(ast)
        _assert_no_cycles(parsed_prereqs, n)

        # --- Parse goal tasks ---
        raw_goal_parts = [str(x).strip() for x in list(self.options.goal_tasks.value or []) if str(x).strip()]
        raw_goal = ", ".join(raw_goal_parts)  # rejoin into single expression
        goal_ast = parse_prereq(raw_goal, n, 0, "goal_tasks") if raw_goal else None
        self._raw_goal = raw_goal
        self._goal_ast = goal_ast

        # 0-based indices of all tasks referenced in goal (for slot data)
        self._goal_indices = sorted(set(collect_leaves(goal_ast))) if goal_ast else []

        # Rewards that other tasks require to be *received* must be progression so AP
        # places them early enough. Task-completion prereqs gate via completion tokens
        # (always progression themselves), so they do NOT force reward items to progression.
        # Progressive group members are also always forced to progression.
        forced_prog: set = set()
        for ast in parsed_reward_prereqs:
            forced_prog.update(collect_leaves(ast))
        for indices in group_to_reward_indices.values():
            forced_prog.update(indices)

        self._raw_prereqs = raw_prereqs_input
        self._parsed_prereqs = parsed_prereqs       # List[Node | None]
        self._raw_reward_prereqs = raw_reward_prereqs_input
        self._parsed_reward_prereqs = parsed_reward_prereqs  # List[Node | None]
        self._forced_progression_rewards = forced_prog
        self._lock_prereqs = bool(self.options.lock_prereqs)

        self._progressive_groups = raw_prog_groups
        self._reward_to_group = reward_to_group
        self._group_to_reward_indices = group_to_reward_indices
        self._task_progressive_reqs = task_progressive_reqs
        self._regions = raw_regions
        self._region_default_pcts = region_default_pcts
        self._task_region = task_region
        self._task_region_reqs = task_region_reqs
        self._region_to_task_indices = region_to_task_indices

        # Stable names for this generation.
        # stage_generate_early runs before this and sets the class-level dicts;
        # we reproduce the same naming formula here so instance methods use matching names.
        multi_slot = len(list(self.multiworld.get_game_worlds(self.game))) > 1
        _pname = self.multiworld.player_name[self.player]
        prefix = f"[{_pname}] " if multi_slot else ""

        self._reward_location_names = [f"{prefix}Task {i + 1} (Reward)" for i in range(n)]
        self._complete_location_names = [f"{prefix}Task {i + 1} (Complete)" for i in range(n)]
        self._reward_item_names = [
            f"{prefix}Item {i + 1}: {rewards[i]}" if rewards[i].strip() else f"{prefix}Item {i + 1}"
            for i in range(n)
        ]
        self._reward_display_names = list(self._reward_item_names)
        self._token_item_names = [f"{prefix}Task {i + 1} Complete" for i in range(n)]
        self._group_item_display_names: Dict[str, List[str]] = {
            gname: [self._reward_item_names[idx] for idx in indices]
            for gname, indices in group_to_reward_indices.items()
        }
        self._region_token_names: Dict[str, List[str]] = {
            rname: [self._token_item_names[idx] for idx in indices]
            for rname, indices in region_to_task_indices.items()
        }

    @classmethod
    def stage_generate_early(cls, multiworld) -> None:
        import worlds as _worlds

        task_worlds = list(multiworld.get_game_worlds(cls.game))
        multi_slot = len(task_worlds) > 1

        item_name_to_id: Dict[str, int] = {}
        location_name_to_id: Dict[str, int] = {}

        for world in task_worlds:
            p = world.player
            player_name = multiworld.player_name[p]
            prefix = f"[{player_name}] " if multi_slot else ""

            tasks = [str(t).strip() for t in world.options.tasks.value if str(t).strip()]
            items_raw = [str(r).strip() for r in world.options.items.value]
            n = min(len(tasks), MAX_TASKS)

            for i in range(n):
                reward_text = items_raw[i] if i < len(items_raw) else ""
                item_name = (
                    f"{prefix}Item {i + 1}: {reward_text}"
                    if reward_text
                    else f"{prefix}Item {i + 1}"
                )
                token_name = f"{prefix}Task {i + 1} Complete"
                reward_loc_name = f"{prefix}Task {i + 1} (Reward)"
                complete_loc_name = f"{prefix}Task {i + 1} (Complete)"

                item_name_to_id[item_name] = BASE_ITEM_ID + (p - 1) * MAX_TASKS + i
                item_name_to_id[token_name] = BASE_TOKEN_ID + (p - 1) * MAX_TASKS + i
                location_name_to_id[reward_loc_name] = BASE_REWARD_LOC_ID + (p - 1) * MAX_TASKS + i
                location_name_to_id[complete_loc_name] = BASE_COMPLETE_LOC_ID + (p - 1) * MAX_TASKS + i

        cls.item_name_to_id = item_name_to_id
        cls.location_name_to_id = location_name_to_id
        _worlds.network_data_package["games"][cls.game] = cls.get_data_package_data()

    def create_regions(self) -> None:
        menu = Region("Menu", self.player, self.multiworld)
        fallback = Region("Tasks", self.player, self.multiworld)

        ap_region_map: Dict[str, Region] = {
            rname: Region(rname, self.player, self.multiworld)
            for rname in self._regions
        }

        for i in range(len(self._tasks)):
            rlocname = self._reward_location_names[i]
            clocname = self._complete_location_names[i]
            target = ap_region_map.get(self._task_region[i], fallback)
            target.locations.append(
                TaskipelagoLocation(self.player, rlocname, self.location_name_to_id[rlocname], target)
            )
            target.locations.append(
                TaskipelagoLocation(self.player, clocname, self.location_name_to_id[clocname], target)
            )

        all_regions = [menu, fallback] + list(ap_region_map.values())
        self.multiworld.regions += all_regions
        for region in [fallback] + list(ap_region_map.values()):
            menu.connect(region)

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

            self.multiworld.itempool.append(
                TaskipelagoItem(
                    name,
                    cls,
                    self.item_name_to_id[name],
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
                    self.item_name_to_id[token_name],
                    self.player,
                )
            )

        # Goal condition: either specific goal tasks, or all tasks by default.
        if self._goal_ast is not None:
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
            "items": list(self._rewards),
            "item_types": list(self._reward_types),
            "task_prereqs": list(self._raw_prereqs),
            "item_prereqs": list(self._raw_reward_prereqs),
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
            "base_reward_location_id": BASE_REWARD_LOC_ID + (self.player - 1) * MAX_TASKS,
            "base_complete_location_id": BASE_COMPLETE_LOC_ID + (self.player - 1) * MAX_TASKS,
            "base_item_id": BASE_ITEM_ID + (self.player - 1) * MAX_TASKS,
            "base_token_id": BASE_TOKEN_ID + (self.player - 1) * MAX_TASKS,
            "sent_item_names": sent_item_names,
            "sent_player_names": sent_player_names,
            "goal_indices": sorted(self._goal_indices),
            "goal_expression": self._raw_goal,
            "progressive_groups": list(self._progressive_groups),
            "item_progressive_group": list(self._reward_to_group),
            "task_progressive_reqs": [
                [{"group": g, "count": c} for g, c in reqs]
                for reqs in self._task_progressive_reqs
            ],
            "regions": list(self._regions),
            "region_default_pcts": dict(self._region_default_pcts),
            "task_region": list(self._task_region),
            "task_region_reqs": [
                [{"region": r, "pct": p} for r, p in reqs]
                for reqs in self._task_region_reqs
            ],
            "bingo_mode": bool(self.options.bingo_mode),
            "bingo_dimension_x": int(self.options.bingo_dimension_x),
            "bingo_dimension_y": int(self.options.bingo_dimension_y),
            "bingoal": int(self.options.bingoal),
        }


# --- Helpers ---

def _resolve_quoted_names(text: str, names: list) -> Tuple[str, List[str]]:
    """Replace "Quoted Name" tokens with the 1-based index of the first matching entry."""
    errors: List[str] = []
    def _replacer(m: "_re.Match") -> str:
        name = m.group(1)
        for i, n in enumerate(names):
            if n == name:
                return str(i + 1)
        errors.append(f'No entry found named "{name}"')
        return m.group(0)
    result = _re.sub(r'"([^"]*)"', _replacer, text)
    return result, errors




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