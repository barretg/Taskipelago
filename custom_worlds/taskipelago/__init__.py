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
from .prereq_parser import collect_leaves, eval_node, parse_prereq, Node
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
    _progressive_groups: List[str]
    _reward_to_group: List[str]
    _group_to_reward_indices: Dict[str, List[int]]
    _task_progressive_reqs: List[List[Tuple[str, int]]]
    _group_item_display_names: Dict[str, List[str]]

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

        # --- Map each reward to its group ---
        raw_rpg = [str(x).strip() for x in (self.options.reward_progressive_group.value or [])]
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

        # --- Parse reward prereqs (extracting group refs first) ---
        raw_reward_prereqs_input = [str(x).strip() for x in list(self.options.reward_prereqs.value or [])]
        if len(raw_reward_prereqs_input) < n:
            raw_reward_prereqs_input += [""] * (n - len(raw_reward_prereqs_input))
        raw_reward_prereqs_input = raw_reward_prereqs_input[:n]

        # Extract group refs from each task's reward prereq string, keeping only integers for the parser.
        task_group_refs: List[List[Tuple[str, int | None]]] = []
        raw_reward_prereqs: List[str] = []
        for txt in raw_reward_prereqs_input:
            refs, cleaned = _extract_group_refs(txt, prog_group_set)
            task_group_refs.append(refs)
            raw_reward_prereqs.append(cleaned)

        # Validate group refs found in reward prereqs.
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
                            f"N must be between 1 and {group_size} (1-indexed)."
                        )

        # Resolve progressive unlock order per group.
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
            if len(task_refs) > group_size:
                raise Exception(
                    f"Taskipelago: progressive group '{gname}' has {group_size} reward(s) but "
                    f"{len(task_refs)} task(s) require it. Add more rewards to the group or "
                    f"reduce the number of tasks depending on it."
                )

            # Separate tasks with explicit positions from those relying on default order.
            explicit_pos: Dict[int, int] = {}   # position (1-based) -> task_index
            implicit_tasks: List[int] = []
            for ti, n_val in task_refs:
                if n_val is not None:
                    if n_val in explicit_pos:
                        raise Exception(
                            f"Taskipelago: progressive group '{gname}' has multiple tasks "
                            f"assigned to position {n_val}."
                        )
                    explicit_pos[n_val] = ti
                else:
                    implicit_tasks.append(ti)
            implicit_tasks.sort()  # lower task index = lower unlock position

            all_positions = set(range(1, len(task_refs) + 1))
            free_positions = sorted(all_positions - set(explicit_pos.keys()))

            for pos, ti in explicit_pos.items():
                task_progressive_reqs[ti].append((gname, pos))
            for ti, pos in zip(implicit_tasks, free_positions):
                task_progressive_reqs[ti].append((gname, pos))

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

        # Rewards that other tasks require to be *received* must be progression so AP
        # places them early enough. Task-completion prereqs gate via completion tokens
        # (always progression themselves), so they do NOT force reward items to progression.
        # Progressive group members are also always forced to progression.
        forced_prog: set = set()
        for ast in parsed_reward_prereqs:
            forced_prog.update(collect_leaves(ast))
        for indices in group_to_reward_indices.values():
            forced_prog.update(indices)

        self._raw_prereqs = raw_prereqs
        self._parsed_prereqs = parsed_prereqs       # List[Node | None]
        self._raw_reward_prereqs = raw_reward_prereqs   # integer-only (group refs stripped)
        self._parsed_reward_prereqs = parsed_reward_prereqs  # List[Node | None]
        self._forced_progression_rewards = forced_prog
        self._lock_prereqs = bool(self.options.lock_prereqs)

        self._progressive_groups = raw_prog_groups
        self._reward_to_group = reward_to_group
        self._group_to_reward_indices = group_to_reward_indices
        self._task_progressive_reqs = task_progressive_reqs

        # Stable names for this generation.
        self._reward_location_names = [f"Task {i + 1} (Reward)" for i in range(n)]
        self._complete_location_names = [f"Task {i + 1} (Complete)" for i in range(n)]
        self._reward_item_names = [f"Reward {i + 1}" for i in range(n)]
        self._reward_display_names = [
            f"Reward {i + 1}: {r}" if r.strip() else f"Reward {i + 1}"
            for i, r in enumerate(rewards)
        ]
        self._token_item_names = [f"Task Complete {i + 1}" for i in range(n)]
        self._group_item_display_names: Dict[str, List[str]] = {
            gname: [self._reward_display_names[idx] for idx in indices]
            for gname, indices in group_to_reward_indices.items()
        }

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
            "progressive_groups": list(self._progressive_groups),
            "reward_progressive_group": list(self._reward_to_group),
            "task_progressive_reqs": [
                [{"group": g, "count": c} for g, c in reqs]
                for reqs in self._task_progressive_reqs
            ],
        }


# --- Helpers ---

def _extract_group_refs(
    text: str, known_groups: set
) -> Tuple[List[Tuple[str, int | None]], str]:
    """
    Scan a reward prereq expression string and pull out any progressive group references.
    A group ref is a token whose base name (letters/underscores/hyphens, no digits) matches
    a known group name, optionally followed by -<N> (the explicit unlock order).

    Returns:
        (group_refs, cleaned_text)
        group_refs  : list of (group_name, explicit_n_or_None)
        cleaned_text: original text with group tokens removed and dangling operators cleaned up
    """
    group_refs: List[Tuple[str, int | None]] = []
    parts: List[str] = []
    i = 0
    length = len(text)

    while i < length:
        c = text[i]

        if c.isspace():
            parts.append(c)
            i += 1

        elif text[i:i+2] in ('&&', '||'):
            parts.append(text[i:i+2])
            i += 2

        elif c in ('(', ')', ','):
            parts.append(c)
            i += 1

        elif c.isdigit():
            j = i
            while j < length and text[j].isdigit():
                j += 1
            parts.append(text[i:j])
            i = j

        elif c.isalpha() or c == '_':
            # Read until a separator (space, paren, comma, or start of && / ||)
            j = i
            while j < length:
                ch = text[j]
                if ch.isspace() or ch in ('(', ')', ','):
                    break
                if text[j:j+2] in ('&&', '||'):
                    break
                j += 1
            token = text[i:j]

            # Try to split off a trailing -<digits> suffix.
            # The base must end in a letter or underscore (guaranteeing no digits in group name).
            suffix_m = _re.match(r'^(.+[a-zA-Z_])-(\d+)$', token)
            if suffix_m:
                base, n_val = suffix_m.group(1), int(suffix_m.group(2))
            else:
                base, n_val = token, None

            if base in known_groups:
                group_refs.append((base, n_val))
                # Remove token from output
            else:
                parts.append(token)
            i = j

        else:
            parts.append(c)
            i += 1

    cleaned = ''.join(parts)
    # Clean up operator residue left by removed tokens.
    cleaned = _re.sub(r'(?:&&|,)\s*(?:&&|,)', '&&', cleaned)
    cleaned = _re.sub(r'^\s*(?:&&|,|\|\|)\s*', '', cleaned)
    cleaned = _re.sub(r'\s*(?:&&|,|\|\|)\s*$', '', cleaned)
    return group_refs, cleaned.strip()


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