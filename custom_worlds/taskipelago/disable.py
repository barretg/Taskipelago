"""
Disabled regions and item groups (region_disabled / group_disabled).

A disabled region or item group stays in the YAML but is left out of the seed:
its tasks or items are dropped, and every reference to it, or to one of its
tasks or items, is treated as already satisfied. This runs before anything else
in generate_early and rewrites the raw option lists into the YAML the player
would have written without the disabled content, so the rest of generation
never sees it:

  - task / item rows in a disabled region / group are removed from every
    parallel list, and the remaining rows are renumbered in every expression;
  - a reference to a removed task or item, or to a disabled region or group,
    becomes true and is folded away (prereqs have no negation, so this never
    makes anything harder);
  - 'prev' pointing at a removed row becomes 'sequential' (the same thing for
    every copy after the first) or nothing at all for a single-copy row;
  - a disabled parent region disables its subregions too;
  - clicker production targets aimed only at removed content are dropped;
  - death_link_pool entries naming a removed task are dropped.

Pure function, no randomness: the result depends only on the option lists.
"""
from __future__ import annotations

from typing import Callable, Dict, List, Optional, Tuple

from .clicker import _split_top, _strip_parens, _target_value, _top_level
from .prereq_parser import _COST_SUFFIX_CHARS, split_name_suffix

# Parallel lists, by what they are aligned with.
TASK_LISTS = (
    "task_count", "task_prereqs", "item_prereqs", "task_priority", "task_description",
    "task_region", "task_cost", "task_activations", "task_manual", "task_auto_complete",
)
ITEM_LISTS = (
    "items", "item_types", "item_fillers", "item_consumable", "item_count", "item_early",
    "item_progressive_group", "item_production", "item_click_power", "item_production_mult",
    "item_click_mult", "item_offline_mult",
)
ITEM_SPEC_LISTS = (
    "item_production", "item_click_power", "item_production_mult", "item_click_mult",
    "item_offline_mult",
)
REGION_LISTS = (
    "regions", "region_default_pcts", "region_colors", "region_prereqs", "region_parent",
    "region_random_pick", "region_random_order", "region_manual",
    "region_distributed_production", "region_offline_rate", "region_disabled",
)
GROUP_LISTS = (
    "progressive_groups", "progressive_group_colors", "group_types", "group_random_pick",
    "group_early", "group_default_pcts", "group_disabled",
)
#: Every option list this module reads or rewrites.
OPTION_LISTS = ("tasks", "goal_tasks", "death_link_pool", "death_link_weights") + TASK_LISTS \
    + ITEM_LISTS + REGION_LISTS + GROUP_LISTS

TRUE = None  # a rewritten atom that is always satisfied


def _is_true(text: str) -> bool:
    return text.strip().lower() == "true"


def _pick(values: List[str], rows: List[int]) -> List[str]:
    """Keep the entries at `rows` (ascending); missing trailing entries stay missing."""
    return [values[r] for r in rows if r < len(values)]


def _count(text: str) -> int:
    try:
        return max(1, int(text)) if text else 1
    except ValueError:
        return 1


# ---------------------------------------------------------------------------
# Expression rewriting
# ---------------------------------------------------------------------------

def _tokenize(text: str) -> Optional[list]:
    """Tokens for a prereq or cost expression: ('op', s), ('scope', 'task'|'item'), ('atom', s).
    None when the text holds something this reader does not know (left for the real parser)."""
    toks: list = []
    i, n = 0, len(text)
    while i < n:
        c = text[i]
        if c.isspace():
            i += 1
        elif text.startswith(("&&", "||"), i):
            toks.append(("op", text[i:i + 2]))
            i += 2
        elif c in "(),":
            toks.append(("op", c))
            i += 1
        elif c == '"' or c.isdigit():
            if c == '"':
                j = text.find('"', i + 1)
                if j < 0:
                    return None
                j += 1
            else:
                j = i
                while j < n and text[j].isdigit():
                    j += 1
            # Optional '*Y' copy / spend count, read the way the cost tokenizer
            # reads it (digits, or an N_TASKS expression).
            if j < n and text[j] == "*":
                k = j + 1
                while k < n and text[k].isdigit():
                    k += 1
                e = j + 1
                while e < n and text[e] in _COST_SUFFIX_CHARS:
                    e += 1
                if e > k and "N" in text[j + 1:e]:
                    j = e
                elif k > j + 1:
                    j = k
            toks.append(("atom", text[i:j]))
            i = j
        elif c.isalpha() or c == "_":
            j = i
            while j < n and not text[j].isspace() and text[j] not in "()," \
                    and not text.startswith(("&&", "||"), j):
                j += 1
            word = text[i:j]
            p = j
            while p < n and text[p].isspace():
                p += 1
            if word in ("task", "item") and p < n and text[p] == "(":
                toks.append(("scope", word))
            else:
                toks.append(("atom", word))
            i = j
        else:
            return None
    return toks


def _parse(toks: list, home: Optional[str]):
    """Generic AND/OR tree over the tokens: ('and'|'or', [kids]), ('scope', dom, kid),
    ('atom', text, dom). None when the brackets do not balance."""
    pos = [0]

    def peek():
        return toks[pos[0]] if pos[0] < len(toks) else None

    def p_or(dom):
        kids = [p_and(dom)]
        while peek() == ("op", "||"):
            pos[0] += 1
            kids.append(p_and(dom))
        return kids[0] if len(kids) == 1 else ("or", kids)

    def p_and(dom):
        kids = [p_atom(dom)]
        while peek() in (("op", "&&"), ("op", ",")):
            pos[0] += 1
            kids.append(p_atom(dom))
        return kids[0] if len(kids) == 1 else ("and", kids)

    def p_atom(dom):
        tok = peek()
        if tok is None:
            raise ValueError
        pos[0] += 1
        if tok == ("op", "("):
            node = p_or(dom)
            if peek() != ("op", ")"):
                raise ValueError
            pos[0] += 1
            return node
        if tok[0] == "scope":
            if peek() != ("op", "("):
                raise ValueError
            pos[0] += 1
            node = p_or(tok[1])
            if peek() != ("op", ")"):
                raise ValueError
            pos[0] += 1
            return ("scope", tok[1], node)
        if tok[0] == "atom":
            return ("atom", tok[1], dom)
        raise ValueError

    try:
        tree = p_or(home)
    except ValueError:
        return None
    return tree if pos[0] == len(toks) else None


def _emit(node, atom_fn) -> Tuple[str, str, bool]:
    """(kind, text, changed); kind 'true' means the node is always satisfied."""
    tag = node[0]
    if tag == "atom":
        new = atom_fn(node[1], node[2])
        if new is TRUE:
            return "true", "", True
        return "atom", new, new != node[1]
    if tag == "scope":
        kind, text, changed = _emit(node[2], atom_fn)
        if kind == "true":
            return "true", "", True
        return "atom", f"{node[1]}({text})", changed
    parts = [_emit(k, atom_fn) for k in node[1]]
    changed = any(p[2] for p in parts)
    if tag == "or":
        if any(p[0] == "true" for p in parts):
            return "true", "", True
        return "or", " || ".join(p[1] for p in parts), changed
    parts = [p for p in parts if p[0] != "true"]
    if not parts:
        return "true", "", True
    if len(parts) == 1:
        return parts[0][0], parts[0][1], True
    return "and", " && ".join(f"({t})" if k == "or" else t for k, t, _ in parts), changed


def rewrite_expr(text: str, home: Optional[str], atom_fn: Callable) -> str:
    """Rewrite one expression. atom_fn(atom, domain) returns the new atom text or TRUE.
    Text that does not read as an expression is returned unchanged."""
    if not text or not text.strip():
        return text
    toks = _tokenize(text)
    tree = _parse(toks, home) if toks else None
    if tree is None:
        return text
    kind, out, changed = _emit(tree, atom_fn)
    if not changed:
        return text
    return "" if kind == "true" else out


# ---------------------------------------------------------------------------
# Main entry point
# ---------------------------------------------------------------------------

def apply_disabled(opts: Dict[str, List[str]]) -> Optional[Dict[str, List[str]]]:
    """
    opts maps each name in OPTION_LISTS to its raw list of strings. Returns the
    rewritten lists, or None when nothing is disabled (generation is then
    untouched).
    """
    get = lambda k: [str(x) for x in (opts.get(k) or [])]

    regions_all = get("regions")
    region_rows = [i for i, r in enumerate(regions_all) if r.strip()]
    region_names = [regions_all[i].strip() for i in region_rows]
    groups_all = get("progressive_groups")
    group_rows = [i for i, g in enumerate(groups_all) if g.strip()]
    group_names = [groups_all[i].strip() for i in group_rows]

    # Region / group parallel lists are aligned with the blank-free name lists.
    r_flags = get("region_disabled")
    g_flags = get("group_disabled")
    dis_regions = {r for i, r in enumerate(region_names) if i < len(r_flags) and _is_true(r_flags[i])}
    dis_groups = {g for i, g in enumerate(group_names) if i < len(g_flags) and _is_true(g_flags[i])}
    if not dis_regions and not dis_groups:
        return None
    # A disabled parent takes its subregions with it.
    parents = get("region_parent")
    dis_regions |= {
        r for i, r in enumerate(region_names)
        if i < len(parents) and parents[i].strip() in dis_regions
    }

    # Task rows (blank names are skipped by the generator, and the parallel
    # lists line up with the blank-free list).
    task_names = [t.strip() for t in get("tasks") if t.strip()]
    task_region = [x.strip() for x in get("task_region")]
    t_dropped = {i for i in range(len(task_names)) if i < len(task_region) and task_region[i] in dis_regions}
    t_kept = [i for i in range(len(task_names)) if i not in t_dropped]
    t_map = {old: new for new, old in enumerate(t_kept)}
    kept_task_names = {task_names[i] for i in t_kept}
    gone_task_names = {task_names[i] for i in t_dropped} - kept_task_names
    t_counts_raw = [x.strip() for x in get("task_count")]
    t_counts = [_count(t_counts_raw[i] if i < len(t_counts_raw) else "") for i in range(len(task_names))]
    # Expanded (per-copy) task indices, which clicker targets use.
    y_map: Dict[int, int] = {}
    y_old = y_new = 0
    for i, c in enumerate(t_counts):
        for _ in range(c):
            if i not in t_dropped:
                y_map[y_old] = y_new
                y_new += 1
            y_old += 1

    # Item rows (blank names are filler rows and stay in place).
    items = get("items")
    item_group = [x.strip() for x in get("item_progressive_group")]
    i_dropped = {k for k in range(len(items)) if k < len(item_group) and item_group[k] in dis_groups}
    i_kept = [k for k in range(len(items)) if k not in i_dropped]
    i_map = {old: new for new, old in enumerate(i_kept)}
    kept_item_names = {items[k].strip() for k in i_kept}
    gone_item_names = {items[k].strip() for k in i_dropped} - kept_item_names

    all_names = set(region_names) | set(group_names)

    def _index(atom: str, mapping: Dict[int, int], dropped: set):
        head, star, tail = atom.partition("*")
        old = int(head) - 1
        if old in dropped:
            return TRUE
        if old not in mapping:
            return atom  # out of range: left for the generator to report
        return f"{mapping[old] + 1}{star}{tail}"

    def _quoted(atom: str, gone: set):
        name = atom[1:atom.index('"', 1)] if atom.count('"') >= 2 else ""
        return TRUE if name in gone else atom

    def make_atom_fn(row: Optional[int] = None):
        def fn(atom: str, dom: Optional[str]):
            if atom[0].isdigit():
                if dom == "task":
                    return _index(atom, t_map, t_dropped)
                if dom in ("item", "cost"):
                    return _index(atom, i_map, i_dropped)
                return atom
            if atom[0] == '"':
                if dom in ("item", "cost"):
                    return _quoted(atom, gone_item_names)
                return _quoted(atom, gone_task_names)
            if atom == "prev":
                if row is None or row - 1 not in t_dropped:
                    return atom
                # The previous row is gone: copy 0 has nothing before it, later
                # copies still wait on the copy before them.
                return "sequential" if t_counts[row] > 1 else TRUE
            if atom == "sequential":
                return atom
            base = split_name_suffix(atom, all_names)[0]
            if dom in ("item", "cost"):
                return TRUE if base in dis_groups else atom
            return TRUE if base in dis_regions else atom
        return fn

    out: Dict[str, List[str]] = {}

    # --- task-aligned lists ---
    out["tasks"] = [task_names[i] for i in t_kept]
    for key in TASK_LISTS:
        out[key] = _pick(get(key), t_kept)
    out["task_prereqs"] = [
        rewrite_expr(txt, "task", make_atom_fn(t_kept[j])) for j, txt in enumerate(out["task_prereqs"])
    ]
    out["item_prereqs"] = [rewrite_expr(txt, "item", make_atom_fn()) for txt in out["item_prereqs"]]
    out["task_cost"] = [rewrite_expr(txt, "cost", make_atom_fn()) for txt in out["task_cost"]]

    # --- item-aligned lists ---
    for key in ITEM_LISTS:
        out[key] = _pick(get(key), i_kept)

    y_dropped = {o for o in range(y_old) if o not in y_map}

    def _spec_atom(atom: str):
        if atom == "*":
            return atom
        if atom.startswith('"'):
            return _quoted(atom, gone_task_names)
        if atom.isdigit():
            return _index(atom, y_map, y_dropped)
        return TRUE if atom in dis_regions else atom

    def _rewrite_specs(text: str) -> str:
        parts_out: List[str] = []
        changed = False
        for part in _split_top(text, "&&"):
            p = part.strip()
            if not p:
                continue
            if p.startswith("(") and not _top_level(p, "-"):
                inner = _strip_parens(p)
                if inner != p:
                    new = _rewrite_specs(inner)
                    changed |= new != inner
                    if new:
                        parts_out.append(p if new == inner else new)
                    continue
            split = _target_value(p, set(region_names))
            if split is None:
                parts_out.append(p)
                continue
            targets, value = split
            new_targets = [t for t in (_spec_atom(t) for t in targets) if t is not TRUE]
            if new_targets == targets:
                parts_out.append(p)
                continue
            changed = True
            if not new_targets:
                continue
            target = new_targets[0] if len(new_targets) == 1 else "(" + " && ".join(new_targets) + ")"
            parts_out.append(f"{target}-{value}")
        return " && ".join(parts_out) if changed else text

    for key in ITEM_SPEC_LISTS:
        out[key] = [_rewrite_specs(txt) if txt.strip() else txt for txt in out[key]]

    # --- region-aligned lists ---
    r_kept = [i for i, r in enumerate(region_names) if r not in dis_regions]
    for key in REGION_LISTS:
        vals = get(key)
        if key == "regions":
            vals = region_names
        out[key] = _pick(vals, r_kept)
    out["region_disabled"] = []
    out["region_prereqs"] = [rewrite_expr(txt, None, make_atom_fn()) for txt in out["region_prereqs"]]

    # --- group-aligned lists ---
    g_kept = [i for i, g in enumerate(group_names) if g not in dis_groups]
    for key in GROUP_LISTS:
        vals = get(key)
        if key == "progressive_groups":
            vals = group_names
        out[key] = _pick(vals, g_kept)
    out["group_disabled"] = []

    # --- goal ---
    goal = ", ".join(x.strip() for x in get("goal_tasks") if x.strip())
    if goal:
        new_goal = rewrite_expr(goal, "task", make_atom_fn())
        if not new_goal:
            raise Exception(
                "Taskipelago: goal_tasks only references disabled regions, item groups or their "
                "tasks and items, so nothing would be left to win with. Change the goal or "
                "re-enable one of them."
            )
        out["goal_tasks"] = [new_goal] if new_goal != goal else get("goal_tasks")
    else:
        out["goal_tasks"] = get("goal_tasks")

    # --- DeathLink pool (task names) ---
    pool = get("death_link_pool")
    weights = get("death_link_weights")
    keep_pool = [i for i, name in enumerate(pool) if name.strip() not in gone_task_names]
    out["death_link_pool"] = [pool[i] for i in keep_pool]
    out["death_link_weights"] = _pick(weights, keep_pool)

    return out
