from __future__ import annotations

import re as _re
from typing import Any, Dict, List, Tuple

import logging

from BaseClasses import Item, ItemClassification, Region
from worlds.AutoWorld import WebWorld, World

logger = logging.getLogger("Taskipelago")
from worlds.LauncherComponents import Component, Type, components, launch_subprocess

from .items import (
    ITEM_NAME_TO_ID,
    MAX_TASKS,
    BASE_ITEM_ID,
    BASE_TOKEN_ID,
    TaskipelagoItem,
    get_item_classification,
    build_item_editor_rows,
    expand_rows,
    pad_or_trim_names,
)
from .locations import (
    LOCATION_NAME_TO_ID,
    BASE_COMPLETE_LOC_ID,
    BASE_REWARD_LOC_ID,
    TaskipelagoLocation,
)
from .options import TaskipelagoOptions
from .prereq_parser import (
    collect_leaves, collect_group_refs, collect_group_count_refs,
    collect_region_refs, collect_region_abs_refs,
    collect_cost_groups, collect_cost_groups_per_branch,
    eval_node, parse_prereq, parse_cost_expr, resolve_ast_refs, Node,
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
    item_name_to_id: Dict[str, int] = ITEM_NAME_TO_ID
    location_name_to_id: Dict[str, int] = LOCATION_NAME_TO_ID

    # --- Per-generation state (set in generate_early) ---
    _tasks: List[str]
    _rewards: List[str]
    _reward_types: List[str]
    _item_consumable: List[bool]
    _raw_prereqs: List[str]
    _parsed_prereqs: List[Node | None]
    _raw_reward_prereqs: List[str]
    _parsed_reward_prereqs: List[Node | None]
    _raw_costs: List[str]
    _parsed_costs: List[Node | None]
    _task_cost_reqs: List[List[List[Tuple[str, int]]]]  # per-task cost branches (OR of ANDs)
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
    _task_region_reqs: List[List[dict]]
    _region_to_task_indices: Dict[str, List[int]]
    _region_token_names: Dict[str, List[str]]
    _consumable_groups: Dict[str, List[int]]   # name -> [0-based item indices]

    def generate_early(self) -> None:
        import sys as _sys

        # ------------------------------------------------------------------ #
        # 1. Read raw option lists (pre-expansion, editor-indexed)            #
        # ------------------------------------------------------------------ #
        tasks_raw = [str(t).strip() for t in self.options.tasks.value if str(t).strip()]
        items_raw_input = [str(r).strip() for r in self.options.items.value]

        item_types_raw = [str(x).strip() for x in self.options.item_types.value]
        item_consumable_raw = [str(x).strip() for x in (self.options.item_consumable.value or [])]
        item_count_raw = [str(x).strip() for x in (self.options.item_count.value or [])]
        task_count_raw = [str(x).strip() for x in (self.options.task_count.value or [])]
        task_cost_raw = [str(x).strip() for x in (self.options.task_cost.value or [])]

        if not tasks_raw:
            raise Exception("Taskipelago: tasks list is empty.")

        # Duplicate name validation
        _task_name_seen: set = set()
        _task_name_dups: set = set()
        for _tn in tasks_raw:
            if _tn in _task_name_seen:
                _task_name_dups.add(_tn)
            _task_name_seen.add(_tn)
        if _task_name_dups:
            raise Exception(
                "Taskipelago: duplicate task names found (use the count field for multiple copies): "
                + ", ".join(repr(n) for n in sorted(_task_name_dups))
            )

        _item_name_seen: set = set()
        _item_name_dups: set = set()
        for _in in items_raw_input:
            if _in and _in in _item_name_seen:
                _item_name_dups.add(_in)
            elif _in:
                _item_name_seen.add(_in)
        if _item_name_dups:
            raise Exception(
                "Taskipelago: duplicate item names found (use the count field for multiple copies): "
                + ", ".join(repr(n) for n in sorted(_item_name_dups))
            )

        n_editor_tasks = len(tasks_raw)
        n_editor_items = len(items_raw_input)

        if n_editor_tasks > MAX_TASKS:
            raise Exception(
                f"Taskipelago: too many tasks ({n_editor_tasks}). Max is {MAX_TASKS}."
            )

        def _parse_count(s: str) -> int:
            try:
                return max(1, int(s)) if s else 1
            except ValueError:
                return 1

        # Parse per-editor-row counts
        task_counts_editor = [
            _parse_count(task_count_raw[i] if i < len(task_count_raw) else "")
            for i in range(n_editor_tasks)
        ]

        _n_yaml_tasks_expected = sum(task_counts_editor)

        # Items are an independent editor list from tasks (their own rows/counts);
        # only the summed totals need to match, so this is built without regard
        # to n_editor_tasks.
        items_raw_editor, item_types_editor, item_consumable_editor, item_counts_editor = (
            build_item_editor_rows(items_raw_input, item_types_raw, item_consumable_raw, item_count_raw)
        )
        _n_defined_expanded = sum(item_counts_editor)

        # Warn using expanded counts, not editor slot counts
        if _n_defined_expanded != _n_yaml_tasks_expected:
            print(
                f"[Taskipelago] WARNING: Unbalanced item and task counts can lead to generation failures. "
                f"Tasks: {_n_yaml_tasks_expected}, Items: {_n_defined_expanded}.",
                file=_sys.stderr,
            )

        # ------------------------------------------------------------------ #
        # 2. Build editor -> YAML index mappings                              #
        # ------------------------------------------------------------------ #
        # editor_to_yaml_task[i] = list of 0-based YAML indices for editor task i
        editor_to_yaml_task: List[List[int]] = []
        for i, count in enumerate(task_counts_editor):
            start = sum(task_counts_editor[:i])
            editor_to_yaml_task.append(list(range(start, start + count)))

        # editor_to_yaml_item[i] = list of 0-based YAML indices for editor item i
        editor_to_yaml_item: List[List[int]] = []
        for i, count in enumerate(item_counts_editor):
            start = sum(item_counts_editor[:i])
            editor_to_yaml_item.append(list(range(start, start + count)))

        n_yaml_tasks = sum(task_counts_editor)
        n_yaml_items = sum(item_counts_editor)

        if n_yaml_tasks > MAX_TASKS:
            raise Exception(
                f"Taskipelago: expanded task count ({n_yaml_tasks}) exceeds maximum ({MAX_TASKS}). "
                f"Reduce task counts."
            )

        # ------------------------------------------------------------------ #
        # 3. Expand all parallel lists to YAML size                          #
        # ------------------------------------------------------------------ #
        tasks: List[str] = expand_rows(tasks_raw, task_counts_editor)

        items_raw = expand_rows(items_raw_editor, item_counts_editor)
        item_types = expand_rows(item_types_editor, item_counts_editor)
        item_consumable = expand_rows(item_consumable_editor, item_counts_editor)

        # Pad/trim items to n_yaml_tasks
        items_raw = pad_or_trim_names(items_raw, n_yaml_tasks)
        if len(item_types) < n_yaml_tasks:
            item_types += ["junk"] * (n_yaml_tasks - len(item_types))
        item_types = item_types[:n_yaml_tasks]
        if len(item_consumable) < n_yaml_tasks:
            item_consumable += [False] * (n_yaml_tasks - len(item_consumable))
        item_consumable = item_consumable[:n_yaml_tasks]
        rewards = list(items_raw)

        n = n_yaml_tasks

        # ------------------------------------------------------------------ #
        # 4. Translate editor-indexed prereq/cost strings to YAML indices    #
        # ------------------------------------------------------------------ #
        raw_task_prereqs_editor = [
            str(x).strip() for x in list(self.options.task_prereqs.value or [])
        ]
        if len(raw_task_prereqs_editor) < n_editor_tasks:
            raw_task_prereqs_editor += [""] * (n_editor_tasks - len(raw_task_prereqs_editor))
        raw_task_prereqs_editor = raw_task_prereqs_editor[:n_editor_tasks]

        raw_item_prereqs_editor = [
            str(x).strip() for x in list(self.options.item_prereqs.value or [])
        ]
        if len(raw_item_prereqs_editor) < n_editor_tasks:
            raw_item_prereqs_editor += [""] * (n_editor_tasks - len(raw_item_prereqs_editor))
        raw_item_prereqs_editor = raw_item_prereqs_editor[:n_editor_tasks]

        task_region_editor = [
            str(x).strip() for x in (self.options.task_region.value or [])
        ]
        if len(task_region_editor) < n_editor_tasks:
            task_region_editor += [""] * (n_editor_tasks - len(task_region_editor))
        task_region_editor = task_region_editor[:n_editor_tasks]

        task_cost_editor = [
            str(x).strip() for x in task_cost_raw
        ]
        if len(task_cost_editor) < n_editor_tasks:
            task_cost_editor += [""] * (n_editor_tasks - len(task_cost_editor))
        task_cost_editor = task_cost_editor[:n_editor_tasks]

        # Expand parallel task lists by count, translating indices in prereq strings
        raw_prereqs_input: List[str] = []
        raw_reward_prereqs_input: List[str] = []
        raw_task_region: List[str] = []
        raw_costs_input: List[str] = []

        for i in range(n_editor_tasks):
            count = task_counts_editor[i]
            # Translate prereq indices from editor space to YAML space
            translated_tp = _translate_prereq_indices(
                raw_task_prereqs_editor[i], editor_to_yaml_task, and_multi=True
            )
            translated_ip = _translate_prereq_indices(
                raw_item_prereqs_editor[i], editor_to_yaml_item, and_multi=False
            )
            for _ in range(count):
                raw_prereqs_input.append(translated_tp)
                raw_reward_prereqs_input.append(translated_ip)
                raw_task_region.append(task_region_editor[i])
                raw_costs_input.append(task_cost_editor[i])

        # ------------------------------------------------------------------ #
        # 5. Resolve quoted names in task/item prereqs                       #
        # ------------------------------------------------------------------ #
        # Quoted task name references in task prereqs
        for _j, _txt in enumerate(raw_prereqs_input):
            _resolved, _errs = _resolve_quoted_names(_txt, tasks)
            if _errs:
                raise Exception(
                    f"Taskipelago: task prereq for task {_j + 1} references unknown task name(s): "
                    + "; ".join(_errs)
                )
            raw_prereqs_input[_j] = _resolved

        # Quoted item name references in item prereqs
        for _j, _txt in enumerate(raw_reward_prereqs_input):
            _resolved, _errs = _resolve_quoted_names(_txt, items_raw)
            if _errs:
                raise Exception(
                    f"Taskipelago: item prereq for task {_j + 1} references unknown item name(s): "
                    + "; ".join(_errs)
                )
            raw_reward_prereqs_input[_j] = _resolved

        # ------------------------------------------------------------------ #
        # 6. DeathLink validation                                             #
        # ------------------------------------------------------------------ #
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

        # ------------------------------------------------------------------ #
        # 7. Parse regions                                                    #
        # ------------------------------------------------------------------ #
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

        raw_rcolors = [str(x).strip() for x in (self.options.region_colors.value or [])]
        if len(raw_rcolors) < len(raw_regions):
            raw_rcolors += [""] * (len(raw_regions) - len(raw_rcolors))
        region_colors = raw_rcolors[:len(raw_regions)]

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

        # ------------------------------------------------------------------ #
        # 8. Parse progressive groups                                         #
        # ------------------------------------------------------------------ #
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

        # Expand item progressive groups in parallel with items (own row count,
        # decoupled from task rows, same as items/item_types/item_consumable).
        raw_ipg_editor = [str(x).strip() for x in (self.options.item_progressive_group.value or [])]
        if len(raw_ipg_editor) < n_editor_items:
            raw_ipg_editor += [""] * (n_editor_items - len(raw_ipg_editor))
        raw_ipg_editor = raw_ipg_editor[:n_editor_items]

        raw_rpg: List[str] = expand_rows(raw_ipg_editor, item_counts_editor)
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

        # ------------------------------------------------------------------ #
        # 9. Parse item prereqs (reward prereqs)                             #
        # ------------------------------------------------------------------ #
        parsed_reward_prereqs_unresolved = []
        for i, txt in enumerate(raw_reward_prereqs_input):
            parsed_reward_prereqs_unresolved.append(
                parse_prereq(txt, n, i, "reward prereq", known_groups=prog_group_set)
            )

        # Collect ordering refs (group_ref: - notation or bare) and count refs (group_count: * notation)
        task_group_refs: List[List[Tuple[str, int | None]]] = [
            collect_group_refs(ast) for ast in parsed_reward_prereqs_unresolved
        ]
        task_group_count_refs: List[List[Tuple[str, int]]] = [
            collect_group_count_refs(ast) for ast in parsed_reward_prereqs_unresolved
        ]

        # Validate all referenced groups exist and have rewards
        for i, refs in enumerate(task_group_refs):
            for gname, n_val in refs:
                group_size = len(group_to_reward_indices.get(gname, []))
                if group_size == 0:
                    raise Exception(
                        f"Taskipelago: task {i + 1} references progressive group '{gname}' "
                        f"which has no rewards assigned to it."
                    )
                if n_val is not None and (n_val < 1 or n_val > group_size):
                    raise Exception(
                        f"Taskipelago: task {i + 1} uses '{gname}-{n_val}' but group "
                        f"'{gname}' only has {group_size} reward(s)."
                    )
        for i, refs in enumerate(task_group_count_refs):
            for gname, cnt in refs:
                group_size = len(group_to_reward_indices.get(gname, []))
                if group_size == 0:
                    raise Exception(
                        f"Taskipelago: task {i + 1} references progressive group '{gname}' "
                        f"which has no rewards assigned to it."
                    )
                if cnt < 1 or cnt > group_size:
                    raise Exception(
                        f"Taskipelago: task {i + 1} uses '{gname}*{cnt}' but group "
                        f"'{gname}' only has {group_size} reward(s)."
                    )

        task_progressive_reqs: List[List[Tuple[str, int]]] = [[] for _ in range(n)]
        for gname in raw_prog_groups:
            # Ordering refs for this group (from group_ref nodes, - or bare)
            order_refs: List[Tuple[int, int | None]] = [
                (i, ref_n)
                for i, refs in enumerate(task_group_refs)
                for ref_name, ref_n in refs
                if ref_name == gname
            ]
            # Count refs for this group (from group_count nodes, *)
            count_refs: List[Tuple[int, int]] = [
                (i, cnt)
                for i, refs in enumerate(task_group_count_refs)
                for ref_name, cnt in refs
                if ref_name == gname
            ]

            if not order_refs and not count_refs:
                continue

            has_explicit_dash = any(n_val is not None for _, n_val in order_refs)
            has_explicit_star = bool(count_refs)

            if has_explicit_dash and has_explicit_star:
                raise Exception(
                    f"Taskipelago: progressive group '{gname}' cannot mix * (count mode) "
                    f"and - (ordering mode) notation."
                )

            group_size = len(group_to_reward_indices[gname])

            if has_explicit_star or (not has_explicit_dash and count_refs):
                # COUNT MODE: each task gets the explicit count (or 1 for bare refs)
                for ti, cnt in count_refs:
                    task_progressive_reqs[ti].append((gname, cnt))
                for ti, _ in order_refs:  # bare refs in count mode -> require 1
                    task_progressive_reqs[ti].append((gname, 1))
            else:
                # ORDERING MODE: each task gets a unique positional threshold
                explicit_pos: Dict[int, int] = {}  # position -> task_idx (one per position)
                implicit_tasks: List[int] = []
                for ti, n_val in order_refs:
                    if n_val is not None:
                        if n_val in explicit_pos:
                            raise Exception(
                                f"Taskipelago: progressive group '{gname}' has two tasks both "
                                f"requiring ordering position {n_val}. Use count mode ({gname}*N) "
                                f"if multiple tasks should unlock at the same threshold."
                            )
                        explicit_pos[n_val] = ti
                    else:
                        implicit_tasks.append(ti)
                implicit_tasks.sort()

                num_steps = len(explicit_pos) + len(implicit_tasks)
                if num_steps > group_size:
                    raise Exception(
                        f"Taskipelago: progressive group '{gname}' has {group_size} reward(s) but "
                        f"requires {num_steps} distinct ordering positions."
                    )

                free_thresholds = [p for p in range(1, group_size + 1) if p not in explicit_pos]
                for threshold, ti in explicit_pos.items():
                    task_progressive_reqs[ti].append((gname, threshold))
                for ti, threshold in zip(implicit_tasks, free_thresholds):
                    task_progressive_reqs[ti].append((gname, threshold))

        parsed_reward_prereqs = []
        for i, ast in enumerate(parsed_reward_prereqs_unresolved):
            # group_ref nodes need resolution; group_count nodes pass through
            group_thresh = {gname: count for gname, count in task_progressive_reqs[i]}
            parsed_reward_prereqs.append(resolve_ast_refs(ast, group_thresh, {}))

        # ------------------------------------------------------------------ #
        # 10. Parse task prereqs                                              #
        # ------------------------------------------------------------------ #
        parsed_prereqs_unresolved = []
        for i, txt in enumerate(raw_prereqs_input):
            parsed_prereqs_unresolved.append(
                parse_prereq(txt, n, i, "task prereq", known_regions=region_set)
            )

        task_region_reqs: List[List[dict]] = []
        for i, ast in enumerate(parsed_prereqs_unresolved):
            pct_refs = collect_region_refs(ast)
            abs_refs = collect_region_abs_refs(ast)
            reqs: List[dict] = []
            for rname, pct_val in pct_refs:
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
                reqs.append({"region": rname, "pct": pct})
            for rname, abs_n in abs_refs:
                if task_region[i] == rname:
                    raise Exception(
                        f"Taskipelago: task {i + 1} cannot depend on its own region '{rname}'."
                    )
                region_size = len(region_to_task_indices.get(rname, []))
                if region_size == 0:
                    raise Exception(
                        f"Taskipelago: task {i + 1} references region '{rname}' which has no tasks assigned."
                    )
                if abs_n < 1 or abs_n > region_size:
                    raise Exception(
                        f"Taskipelago: task {i + 1} uses '{rname}*{abs_n}' but region "
                        f"'{rname}' only has {region_size} task(s)."
                    )
                reqs.append({"region": rname, "abs_count": abs_n})
            task_region_reqs.append(reqs)

        parsed_prereqs = []
        for i, ast in enumerate(parsed_prereqs_unresolved):
            region_pct = {
                req["region"]: req["pct"]
                for req in task_region_reqs[i]
                if "pct" in req
            }
            ast = resolve_ast_refs(ast, {}, region_pct)
            if ast is not None and i in collect_leaves(ast):
                raise Exception(f"Taskipelago: task {i + 1} cannot require itself.")
            parsed_prereqs.append(ast)
        _assert_no_cycles(parsed_prereqs, n)

        # ------------------------------------------------------------------ #
        # 11. Parse and validate cost expressions                             #
        # ------------------------------------------------------------------ #
        # Build consumable groups: name -> list of 0-based item indices
        consumable_groups: Dict[str, List[int]] = {}
        for idx, (name, is_consumable) in enumerate(zip(rewards, item_consumable)):
            if is_consumable:
                consumable_groups.setdefault(name, []).append(idx)

        consumable_names: set = set(consumable_groups.keys())

        parsed_costs: List[Node | None] = []
        for i, cost_text in enumerate(raw_costs_input):
            if not cost_text:
                parsed_costs.append(None)
                continue
            try:
                ast = parse_cost_expr(
                    cost_text,
                    consumable_names,
                    item_names_ordered=rewards,
                )
                parsed_costs.append(ast)
            except Exception as e:
                raise Exception(
                    f"Taskipelago: cost expression for task {i + 1} is invalid: {e}"
                )

        # Validate total consumable supply covers minimum possible task costs.
        # Uses min-cost (cheapest branch per currency per task) to check that the
        # world is theoretically beatable with optimal play. The Stage 12 threshold
        # model uses worst-case (max branch) costs to prevent drought regardless of
        # player choices; those thresholds are validated separately against supply.
        consumable_supply: Dict[str, int] = {name: len(idxs) for name, idxs in consumable_groups.items()}
        consumable_demand: Dict[str, int] = {}
        for cost_ast in parsed_costs:
            if cost_ast is None:
                continue
            branches = collect_cost_groups_per_branch(cost_ast)
            currencies_in_any_branch: set = set()
            for branch in branches:
                for name, _ in branch:
                    currencies_in_any_branch.add(name)
            for cname in currencies_in_any_branch:
                min_cost = min(
                    (sum(cnt for n, cnt in branch if n == cname) for branch in branches),
                    default=0,
                )
                consumable_demand[cname] = consumable_demand.get(cname, 0) + min_cost

        for cname, demand in consumable_demand.items():
            supply = consumable_supply.get(cname, 0)
            if demand > supply:
                raise Exception(
                    f"Taskipelago: not enough consumable '{cname}' items to cover all task costs. "
                    f"Required: {demand}, available: {supply}."
                )

        # ------------------------------------------------------------------ #
        # 12. Compute cumulative cost thresholds for AP logic                #
        # ------------------------------------------------------------------ #
        # Every task that can spend currency C (AND or OR) advances the
        # per-currency cumulative by its worst-case (max branch) cost.
        # OR tasks' gold-branch threshold = cumulative_before + branch_gold_cost,
        # ensuring AP places enough currency even if the player never uses Make Change.
        # AP rule shape: at least one branch's thresholds all satisfied (OR of ANDs).

        topo_depth = _compute_topo_depths(parsed_prereqs, n)

        # per_currency_cb[cname][task_idx] = cumulative collected *before* this task
        per_currency_cb: Dict[str, Dict[int, int]] = {}

        for cname in consumable_names:
            tasks_with_max_cost: List[Tuple[int, int]] = []  # (task_idx, max_cost)
            for i, cost_ast in enumerate(parsed_costs):
                if cost_ast is None:
                    continue
                branches = collect_cost_groups_per_branch(cost_ast)
                max_c = max(
                    (sum(cnt for nm, cnt in b if nm == cname) for b in branches),
                    default=0,
                )
                if max_c > 0:
                    tasks_with_max_cost.append((i, max_c))

            if not tasks_with_max_cost:
                continue

            tasks_with_max_cost.sort(key=lambda x: (topo_depth[x[0]], x[0]))

            cb: Dict[int, int] = {}
            cumulative = 0
            for task_idx, max_c in tasks_with_max_cost:
                cb[task_idx] = cumulative
                cumulative += max_c

            per_currency_cb[cname] = cb

        # task_cost_reqs[i] = list of branches; each branch is [(cname, threshold), ...].
        # AP rule: at least one branch must have all its thresholds satisfied.
        task_cost_reqs: List[List[List[Tuple[str, int]]]] = [[] for _ in range(n)]

        for i, cost_ast in enumerate(parsed_costs):
            if cost_ast is None:
                continue
            branches = collect_cost_groups_per_branch(cost_ast)
            branch_reqs: List[List[Tuple[str, int]]] = []
            for branch in branches:
                req: List[Tuple[str, int]] = []
                for cname in consumable_names:
                    if cname not in per_currency_cb or i not in per_currency_cb[cname]:
                        continue
                    cb_c = per_currency_cb[cname][i]
                    branch_c_cost = sum(cnt for nm, cnt in branch if nm == cname)
                    if branch_c_cost > 0:
                        req.append((cname, cb_c + branch_c_cost))
                branch_reqs.append(req)
            task_cost_reqs[i] = branch_reqs

        # Validate AND tasks (single branch): threshold must not exceed supply.
        # A threshold above supply means the rule can never be satisfied regardless
        # of item placement, making the world unbeatable.
        for i, branches in enumerate(task_cost_reqs):
            if len(branches) != 1:
                continue
            for cname, threshold in branches[0]:
                supply = consumable_supply.get(cname, 0)
                if threshold > supply:
                    raise Exception(
                        f"Taskipelago: task {i + 1} requires {threshold} '{cname}' item(s) "
                        f"in cumulative AP logic (including worst-case OR-task spending before it) "
                        f"but only {supply} exist. Add more '{cname}' items or reduce costs."
                    )

        # ------------------------------------------------------------------ #
        # 13. Parse goal tasks                                                #
        # ------------------------------------------------------------------ #
        raw_goal_parts = [str(x).strip() for x in list(self.options.goal_tasks.value or []) if str(x).strip()]
        raw_goal = ", ".join(raw_goal_parts)

        _goal_resolved, _goal_errs = _resolve_quoted_names(raw_goal, tasks)
        if _goal_errs:
            raise Exception(
                "Taskipelago: goal_tasks references unknown task name(s): " + "; ".join(_goal_errs)
            )
        raw_goal = _goal_resolved

        goal_ast_unresolved = parse_prereq(raw_goal, n, 0, "goal_tasks", known_regions=region_set) if raw_goal else None

        goal_region_reqs: List[dict] = []
        if goal_ast_unresolved is not None:
            for rname, pct_val in collect_region_refs(goal_ast_unresolved):
                pct = pct_val if pct_val is not None else region_default_pcts.get(rname, 100)
                if pct < 0 or pct > 100:
                    raise Exception(
                        f"Taskipelago: goal_tasks region prereq '{rname}' percentage {pct} must be 0-100."
                    )
                if not region_to_task_indices.get(rname):
                    raise Exception(
                        f"Taskipelago: goal_tasks references region '{rname}' which has no tasks assigned."
                    )
                goal_region_reqs.append({"region": rname, "pct": pct})
            for rname, abs_n in collect_region_abs_refs(goal_ast_unresolved):
                region_size = len(region_to_task_indices.get(rname, []))
                if region_size == 0:
                    raise Exception(
                        f"Taskipelago: goal_tasks references region '{rname}' which has no tasks assigned."
                    )
                if abs_n < 1 or abs_n > region_size:
                    raise Exception(
                        f"Taskipelago: goal_tasks uses '{rname}*{abs_n}' but region "
                        f"'{rname}' only has {region_size} task(s)."
                    )
                goal_region_reqs.append({"region": rname, "abs_count": abs_n})

        goal_region_pct = {req["region"]: req["pct"] for req in goal_region_reqs if "pct" in req}
        goal_ast = resolve_ast_refs(goal_ast_unresolved, {}, goal_region_pct)

        self._raw_goal = raw_goal
        self._goal_ast = goal_ast
        self._goal_region_reqs = goal_region_reqs
        self._goal_indices = sorted(set(collect_leaves(goal_ast))) if goal_ast else []

        # ------------------------------------------------------------------ #
        # 14. Determine forced-progression rewards                           #
        # ------------------------------------------------------------------ #
        forced_prog: set = set()
        for ast in parsed_reward_prereqs:
            forced_prog.update(collect_leaves(ast))
        for indices in group_to_reward_indices.values():
            forced_prog.update(indices)
        # Consumable items used in costs must be progression so AP places them accessibly
        for cname, idxs in consumable_groups.items():
            if consumable_demand.get(cname, 0) > 0:
                forced_prog.update(idxs)

        # ------------------------------------------------------------------ #
        # 15. Store all world state                                           #
        # ------------------------------------------------------------------ #
        self._tasks = tasks
        self._rewards = rewards
        self._reward_types = item_types
        self._item_consumable = item_consumable

        self._raw_prereqs = raw_prereqs_input
        self._parsed_prereqs = parsed_prereqs
        self._raw_reward_prereqs = raw_reward_prereqs_input
        self._parsed_reward_prereqs = parsed_reward_prereqs
        self._raw_costs = raw_costs_input
        self._parsed_costs = parsed_costs
        self._task_cost_reqs = task_cost_reqs
        self._forced_progression_rewards = forced_prog
        self._lock_prereqs = bool(self.options.lock_prereqs)

        self._progressive_groups = raw_prog_groups
        self._reward_to_group = reward_to_group
        self._group_to_reward_indices = group_to_reward_indices
        self._task_progressive_reqs = task_progressive_reqs
        self._regions = raw_regions
        self._region_default_pcts = region_default_pcts
        self._region_colors = region_colors
        self._task_region = task_region
        self._task_region_reqs = task_region_reqs
        self._region_to_task_indices = region_to_task_indices
        self._consumable_groups = consumable_groups

        # Stable per-generation names
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
        # Consumable group display names for logic (name -> [reward_item_names])
        self._consumable_group_display_names: Dict[str, List[str]] = {
            cname: [self._reward_item_names[idx] for idx in idxs]
            for cname, idxs in consumable_groups.items()
        }

        # ------------------------------------------------------------------ #
        # DEBUG LOGGING                                                        #
        # ------------------------------------------------------------------ #
        logger.info("=== Taskipelago generate_early ===")
        logger.info("n_yaml_tasks=%d  n_yaml_items=%d", n, n_yaml_items)
        for gname, idxs in group_to_reward_indices.items():
            names = [f"Item {idx+1}: {rewards[idx]}" for idx in idxs]
            logger.info("group '%s' -> indices %s -> %s", gname, idxs, names)
        for ti, reqs in enumerate(task_progressive_reqs):
            if reqs:
                logger.info("Task %d (%s) progressive reqs: %s", ti + 1, tasks[ti], reqs)
        for ti, txt in enumerate(raw_reward_prereqs_input):
            if txt:
                logger.info("Task %d raw item prereq: %r", ti + 1, txt)
        for ti, ast in enumerate(parsed_reward_prereqs):
            if ast is not None:
                logger.info("Task %d (%s) parsed reward prereq AST: %s", ti + 1, tasks[ti], ast)
        logger.info("forced_progression_rewards (0-based): %s", sorted(forced_prog))
        logger.info("=== end generate_early ===")

    @classmethod
    def stage_generate_early(cls, multiworld) -> None:
        import worlds as _worlds

        task_worlds = list(multiworld.get_game_worlds(cls.game))
        multi_slot = len(task_worlds) > 1

        item_name_to_id: Dict[str, int] = {}
        location_name_to_id: Dict[str, int] = {}

        def _pc(s):
            try: return max(1, int(s)) if s else 1
            except ValueError: return 1

        for world in task_worlds:
            p = world.player
            player_name = multiworld.player_name[p]
            prefix = f"[{player_name}] " if multi_slot else ""

            tasks = [str(t).strip() for t in world.options.tasks.value if str(t).strip()]
            items_raw_input = [str(r).strip() for r in world.options.items.value]

            # Compute expanded count to size the ID allocation correctly
            task_count_raw = [str(x).strip() for x in (world.options.task_count.value or [])]
            item_count_raw = [str(x).strip() for x in (world.options.item_count.value or [])]

            task_counts = [_pc(task_count_raw[i] if i < len(task_count_raw) else "") for i in range(len(tasks))]
            n_tasks = min(sum(task_counts), MAX_TASKS)

            # Items are an independent editor list from tasks (their own rows/counts),
            # matching how generate_early expands them.
            items_raw_editor, _, _, item_counts_editor = build_item_editor_rows(
                items_raw_input, [], [], item_count_raw
            )
            expanded_items = expand_rows(items_raw_editor, item_counts_editor)
            expanded_items = pad_or_trim_names(expanded_items, n_tasks)

            for i in range(n_tasks):
                reward_text = expanded_items[i]
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

        if self._goal_ast is not None:
            def goal_condition(state, ast=self._goal_ast, p=self.player,
                                tn=self._token_item_names, gi=self._group_item_display_names,
                                rt=self._region_token_names):
                return eval_node(ast, state, p, tn, gi, rt)
            self.multiworld.completion_condition[self.player] = goal_condition
        else:
            reward_tokens = list(self._token_item_names)
            player = self.player
            self.multiworld.completion_condition[self.player] = lambda state: state.has_all(
                reward_tokens, player
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
            "item_consumable": list(self._item_consumable),
            "task_costs": list(self._raw_costs),
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
            "goal_region_reqs": list(self._goal_region_reqs),
            "progressive_groups": list(self._progressive_groups),
            "item_progressive_group": list(self._reward_to_group),
            "task_progressive_reqs": [
                [{"group": g, "count": c} for g, c in reqs]
                for reqs in self._task_progressive_reqs
            ],
            "task_cost_reqs": [
                [
                    [{"consumable": cname, "threshold": thr} for cname, thr in branch]
                    for branch in branches
                ]
                for branches in self._task_cost_reqs
            ],
            "task_cost_amounts": [
                [
                    [[name, amt] for name, amt in branch]
                    for branch in collect_cost_groups_per_branch(cost_ast)
                ] if cost_ast is not None else []
                for cost_ast in self._parsed_costs
            ],
            "consumable_groups": {
                cname: list(idxs) for cname, idxs in self._consumable_groups.items()
            },
            "regions": list(self._regions),
            "region_default_pcts": dict(self._region_default_pcts),
            "region_colors": list(self._region_colors),
            "task_region": list(self._task_region),
            "task_region_reqs": [list(reqs) for reqs in self._task_region_reqs],
            "bingo_mode": bool(self.options.bingo_mode),
            "bingo_dimension_x": int(self.options.bingo_dimension_x),
            "bingo_dimension_y": int(self.options.bingo_dimension_y),
            "bingoal": int(self.options.bingoal),
        }


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

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


def _translate_prereq_indices(
    text: str,
    editor_to_yaml: List[List[int]],
    and_multi: bool,
) -> str:
    """
    Translate integer indices in a prereq string from editor-space to YAML-space.
    editor_to_yaml[i] = list of 0-based YAML indices for editor row i.
    If and_multi=True, multi-copy tasks become an AND expression (all copies required).
    If and_multi=False, multi-copy items become an OR expression (any copy sufficient).
    Integers in name tokens (e.g. "group-50") are left untouched.
    """
    if not text:
        return text

    result = []
    i = 0
    while i < len(text):
        c = text[i]

        if c.isspace():
            result.append(c)
            i += 1
            continue

        if text[i:i+2] in ("&&", "||"):
            result.append(text[i:i+2])
            i += 2
            continue

        if c in ("(", ")", ","):
            result.append(c)
            i += 1
            continue

        # Name token: consume until whitespace/operator/paren - leave as-is
        if c.isalpha() or c == '_':
            j = i
            while j < len(text):
                ch = text[j]
                if ch.isspace() or ch in ("(", ")", ","):
                    break
                if text[j:j+2] in ("&&", "||"):
                    break
                j += 1
            result.append(text[i:j])
            i = j
            continue

        # Integer: translate to YAML indices
        if c.isdigit():
            j = i
            while j < len(text) and text[j].isdigit():
                j += 1
            editor_idx_1 = int(text[i:j])
            editor_idx_0 = editor_idx_1 - 1
            if 0 <= editor_idx_0 < len(editor_to_yaml):
                yaml_idxs_0 = editor_to_yaml[editor_idx_0]
                yaml_idxs_1 = [k + 1 for k in yaml_idxs_0]
                if len(yaml_idxs_1) == 1:
                    result.append(str(yaml_idxs_1[0]))
                elif and_multi:
                    result.append("(" + " && ".join(str(k) for k in yaml_idxs_1) + ")")
                else:
                    result.append("(" + " || ".join(str(k) for k in yaml_idxs_1) + ")")
            else:
                result.append(text[i:j])
            i = j
            continue

        result.append(c)
        i += 1

    return "".join(result)


def _compute_topo_depths(parsed_prereqs: list, n: int) -> List[int]:
    """Return a list of topological depths for each task (0 = no prereqs)."""
    depths = [-1] * n
    computing = [False] * n

    def depth(v: int) -> int:
        if depths[v] >= 0:
            return depths[v]
        if computing[v]:
            return 0  # cycle; handled elsewhere
        computing[v] = True
        prereq_ast = parsed_prereqs[v] if v < len(parsed_prereqs) else None
        deps = collect_leaves(prereq_ast)
        d = (max(depth(u) for u in deps) + 1) if deps else 0
        computing[v] = False
        depths[v] = d
        return d

    for i in range(n):
        depth(i)
    return depths


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
    """DFS cycle detection on the prereq graph."""
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
