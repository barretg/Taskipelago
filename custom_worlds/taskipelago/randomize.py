"""
Generation-time helpers for randomized regions and random-choice item groups.

Pick syntax (region_random_pick / group_random_pick): 'N' keeps N candidates,
'N%' keeps N percent of them (rounded up, minimum 1). Candidates are counted
after count-field duplication.
"""
from __future__ import annotations

import math as _math
import re as _re
from typing import Dict, FrozenSet, List, Tuple

from .prereq_parser import Node

GROUP_TYPES = ("progressive", "random-choice", "aesthetic")

_PICK_RE = _re.compile(r'^(\d+)(%?)$')

# Upper bound on minimal goal sets considered; guards against DNF blowup.
MAX_GOAL_SETS = 4096


def parse_pick(text: str, label: str) -> Tuple[int, bool] | None:
    """Parse a pick value into (value, is_percent). Empty means off (None)."""
    text = (text or "").strip()
    if not text:
        return None
    m = _PICK_RE.match(text)
    if not m:
        raise Exception(
            f"Taskipelago: {label} pick '{text}' is invalid. Use a positive whole number N or N%."
        )
    value, is_pct = int(m.group(1)), bool(m.group(2))
    if value < 1:
        raise Exception(f"Taskipelago: {label} pick '{text}' must be at least 1.")
    if is_pct and value > 100:
        raise Exception(f"Taskipelago: {label} pick '{text}' must be at most 100%.")
    return value, is_pct


def resolve_pick(pick: Tuple[int, bool], count: int, label: str) -> int:
    """Resolve a parsed pick against a candidate count. Raises when it exceeds the count."""
    value, is_pct = pick
    n = max(1, _math.ceil(count * value / 100)) if is_pct else value
    if n > count:
        raise Exception(
            f"Taskipelago: {label} keeps {n} but only has {count} candidate(s)."
        )
    return n


def normalize_group_type(text: str) -> str:
    t = (text or "").strip().lower()
    return t if t in GROUP_TYPES else "progressive"


def goal_minimal_sets(node: Node | None) -> List[FrozenSet[int]]:
    """Minimal satisfying sets of task leaves (DNF). Region refs pin nothing."""
    sets = _dnf(node)
    uniq = sorted(set(sets), key=lambda s: (len(s), sorted(s)))
    minimal: List[FrozenSet[int]] = []
    for s in uniq:
        if not any(m <= s for m in minimal):
            minimal.append(s)
    return minimal


def _dnf(node: Node | None) -> List[FrozenSet[int]]:
    if node is None:
        return [frozenset()]
    if isinstance(node, int):
        return [frozenset([node])]
    op = node[0]
    if op == "or":
        out: List[FrozenSet[int]] = []
        for c in node[1]:
            out.extend(_dnf(c))
        return _cap(list(set(out)))
    if op == "and":
        acc: List[FrozenSet[int]] = [frozenset()]
        for c in node[1]:
            child = _dnf(c)
            acc = _cap(list({a | b for a in acc for b in child}))
        return acc
    # region_ref / region_abs / group refs / seq_flag: no individual task pinned
    return [frozenset()]


def _cap(sets: List[FrozenSet[int]]) -> List[FrozenSet[int]]:
    if len(sets) > MAX_GOAL_SETS:
        raise Exception(
            "Taskipelago: goal_tasks expression is too complex to guarantee with randomized "
            "regions. Simplify the goal expression."
        )
    return sets


def remap_int_tokens(text: str, mapping: Dict[int, int], prev_old: int | None = None) -> str:
    """
    Rewrite 1-based integer tokens in a prereq string through mapping (old 0-based ->
    new 0-based). Name tokens are left untouched, except a bare 'prev' which becomes
    the remapped prev_old (0-based) when given. Quoted names are left untouched.
    Unmapped integers raise, since every reference must survive selection.
    """
    if not text:
        return text
    out: List[str] = []
    i = 0
    while i < len(text):
        c = text[i]
        if c == '"':
            j = text.find('"', i + 1)
            j = len(text) if j < 0 else j + 1
            out.append(text[i:j])
            i = j
            continue
        if c.isdigit():
            j = i
            while j < len(text) and text[j].isdigit():
                j += 1
            old = int(text[i:j]) - 1
            if old not in mapping:
                raise Exception(
                    f"Taskipelago: reference '{old + 1}' points at an entry removed by randomization."
                )
            out.append(str(mapping[old] + 1))
            i = j
            continue
        if c.isalpha() or c == '_':
            j = i
            while j < len(text):
                ch = text[j]
                if ch.isspace() or ch in ("(", ")", ","):
                    break
                if text[j:j + 2] in ("&&", "||"):
                    break
                j += 1
            tok = text[i:j]
            if tok == "prev" and prev_old is not None:
                if prev_old not in mapping:
                    raise Exception(
                        "Taskipelago: 'prev' points at a task removed by randomization."
                    )
                tok = str(mapping[prev_old] + 1)
            out.append(tok)
            i = j
            continue
        out.append(c)
        i += 1
    return "".join(out)


_FALSE = ("false",)


def remap_goal_ast(node: Node | None, mapping: Dict[int, int]) -> Node | None:
    """Remap goal leaves; dropped leaves become false and are pruned. None if all true."""
    out = _remap_goal(node, mapping)
    if out is _FALSE:
        raise Exception("Taskipelago: goal_tasks cannot be satisfied after randomization.")
    return out


def _remap_goal(node, mapping):
    if node is None:
        return None
    if isinstance(node, int):
        return mapping[node] if node in mapping else _FALSE
    op = node[0]
    if op in ("and", "or"):
        kids = [_remap_goal(c, mapping) for c in node[1]]
        if op == "and":
            if any(k is _FALSE for k in kids):
                return _FALSE
            kids = [k for k in kids if k is not None]
            if not kids:
                return None
        else:
            if any(k is None for k in kids):
                return None
            kids = [k for k in kids if k is not _FALSE]
            if not kids:
                return _FALSE
        return kids[0] if len(kids) == 1 else (op, kids)
    return node


def cost_indices_to_names(text: str, names: List[str]) -> str:
    """Rewrite numeric item indices in a cost expression to quoted names, so the cost
    keeps its meaning after items are renumbered. Out-of-range indices are left as-is."""
    if not text:
        return text
    out: List[str] = []
    i = 0
    while i < len(text):
        c = text[i]
        if c == '"':
            j = text.find('"', i + 1)
            j = len(text) if j < 0 else j + 1
            out.append(text[i:j])
            i = j
        elif c == '*':
            j = i + 1
            while j < len(text) and text[j].isdigit():
                j += 1
            out.append(text[i:j])
            i = j
        elif c.isdigit():
            j = i
            while j < len(text) and text[j].isdigit():
                j += 1
            idx = int(text[i:j])
            out.append(f'"{names[idx - 1]}"' if 1 <= idx <= len(names) else text[i:j])
            i = j
        else:
            out.append(c)
            i += 1
    return "".join(out)
