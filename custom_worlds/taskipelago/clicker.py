"""
Tasclickpelago (clicker mode) option parsing and validation.

The apworld runs no clicker simulation and consumes no extra randomness. Every
function here is pure: it parses the new option lists, validates them with the
usual `raise Exception("Taskipelago: ...")` style, and produces the resolved
values that fill_slot_data forwards to the client, which does all the accrual.

Numeric fields use the shared sub-grammar in prereq_parser.py, so the Python
parser stays the single source of truth for syntax errors: the client receives
an already-parsed AST (or a folded number) and never re-parses authored text.
"""
from __future__ import annotations

import re as _re
from typing import Any, Dict, List, Tuple

from .prereq_parser import (
    LIVE_NUM_CONSTANTS, eval_num_expr, fold_num_expr, num_expr_constants,
    num_expr_is_static, num_expr_to_int, parse_num_expr,
)

#: Target kinds a production/offline spec can carry.
KIND_TASK = "task"
KIND_REGION = "region"
KIND_ALL = "all"

# A target, followed by '-' and the value expression. The target syntax matches
# the rest of Taskipelago: a quoted "Task Name", a bare Region name, a 1-based
# task index, or '*' for every task.
_TARGET_RE = _re.compile(
    r'^\s*(?:"([^"]*)"|(\d+)|(\*)|([^-]+?))\s*-\s*(.+)$', _re.DOTALL)


# ---------------------------------------------------------------------------
# Numeric helpers
# ---------------------------------------------------------------------------

def _bindings(n_tasks: int, unlocked: int, completed: int) -> Dict[str, int]:
    return {
        "N_TASKS": n_tasks,
        "N_TASKS_UNLOCKED": unlocked,
        "N_TASKS_LOCKED": n_tasks - unlocked,
        "N_TASKS_COMPLETED": completed,
        # CPS is the live click value, which depends on which click items have
        # been received. Validation checks the base value of one click.
        "CPS": 1,
    }


def sample_bindings(n_tasks: int) -> List[Dict[str, int]]:
    """
    Constant bindings a validator checks a live expression against: both ends of
    the range plus a few interior points, which covers this grammar's monotonic
    forms and catches the non-monotonic ones in practice.
    """
    points = sorted({0, n_tasks, n_tasks // 4, n_tasks // 2, (3 * n_tasks) // 4})
    out: List[Dict[str, int]] = []
    for unlocked in points:
        for completed in sorted({0, unlocked}):
            out.append(_bindings(n_tasks, unlocked, completed))
    return out


def parse_value_expr(text: str, label: str, loc: str, n_tasks: int, *,
                     minimum: float | None = None, strictly_positive: bool = False,
                     allow_live: bool = True, allow_cps: bool = True,
                     round_2dp: bool = False) -> Any:
    """
    Parse one clicker numeric field and check it stays in range over every
    reachable constant binding. Returns a plain number when the expression is
    static (folded at generation) or the AST when it depends on live constants.
    """
    ast = parse_num_expr(text, label, loc, allow_live=allow_live)
    # CPS is the click value itself, so a click field defined in terms of it
    # would be self-referential.
    if not allow_cps and "CPS" in num_expr_constants(ast):
        raise Exception(
            f"Taskipelago: 'CPS' is the click value and cannot be used in {label} on {loc}."
        )
    for binding in sample_bindings(n_tasks):
        value = eval_num_expr(ast, binding, label, loc)
        if strictly_positive and value <= 0:
            raise Exception(
                f"Taskipelago: {label} on {loc} evaluates to {value:g} with "
                f"N_TASKS_UNLOCKED={binding['N_TASKS_UNLOCKED']}; it must be greater than 0."
            )
        if minimum is not None and value < minimum:
            raise Exception(
                f"Taskipelago: {label} on {loc} evaluates to {value:g} with "
                f"N_TASKS_UNLOCKED={binding['N_TASKS_UNLOCKED']}; it must be at least {minimum:g}."
            )
    if num_expr_is_static(ast):
        value = fold_num_expr(ast, n_tasks, label, loc)
        return round(value, 2) if round_2dp else value
    return ast


def live_constants_used(text: str) -> List[str]:
    """Live constant names in an expression, or [] if it does not even parse."""
    try:
        ast = parse_num_expr(text, allow_live=True)
    except Exception:
        return []
    return sorted(num_expr_constants(ast) & set(LIVE_NUM_CONSTANTS))


# ---------------------------------------------------------------------------
# task_activations
# ---------------------------------------------------------------------------

def parse_task_activations(raw: List[str], n_rows: int, n_tasks: int,
                           row_label: str = "task") -> List[int]:
    """One positive integer per row; blank means 1. N_TASKS only."""
    out: List[int] = []
    for i in range(n_rows):
        text = raw[i].strip() if i < len(raw) else ""
        if not text:
            out.append(1)
            continue
        loc = f"{row_label} {i + 1}"
        ast = parse_num_expr(text, "task_activations", loc, allow_live=False)
        value = fold_num_expr(ast, n_tasks, "task_activations", loc)
        if value < 1:
            raise Exception(
                f"Taskipelago: task_activations on {loc} evaluates to {value:g}; "
                f"it must be at least 1."
            )
        out.append(num_expr_to_int(value))
    return out


def parse_task_flags(raw: List[str], n_rows: int, label: str,
                     row_label: str = "task") -> List[bool]:
    """'true'/'false'/blank per row; blank is False. Used by task_manual and task_auto_complete."""
    out: List[bool] = []
    for i in range(n_rows):
        text = (raw[i].strip().lower() if i < len(raw) else "")
        if text in ("", "false"):
            out.append(False)
        elif text == "true":
            out.append(True)
        else:
            raise Exception(
                f"Taskipelago: {label} on {row_label} {i + 1} is '{raw[i]}'; "
                f"expected 'true', 'false' or blank."
            )
    return out


# ---------------------------------------------------------------------------
# Targeted specs (every grant kind: production, click power, the
# multipliers and the offline multiplier)
# ---------------------------------------------------------------------------

def parse_target_specs(text: str, label: str, loc: str, *, task_names: List[str],
                       region_names: "set[str]", n_tasks: int,
                       strictly_positive: bool = True, minimum: float | None = None,
                       allow_cps: bool = True, round_2dp: bool = False,
                       bare_ok: bool = False) -> List[dict]:
    """
    Parse '<target>-<value>' pairs joined with '&&' into resolved specs:
        {"kind": "task"|"region"|"all", "ref": idx | region name | None, "rate": number|AST}
    Task targets resolve to 0-based indices in the expanded task list.

    With `bare_ok`, a part that carries no readable target is taken as a value
    aimed at '*'. That is what keeps the untargeted fields written by older
    YAMLs ('item_click_power: ["2"]') meaning exactly what they meant before.
    """
    text = (text or "").strip()
    if not text:
        return []
    if minimum is None and not strictly_positive:
        minimum = 0.0

    def _value(value_text: str) -> Any:
        return parse_value_expr(
            value_text, label, loc, n_tasks, strictly_positive=strictly_positive,
            minimum=minimum, allow_cps=allow_cps, round_2dp=round_2dp,
        )

    def _is_value(value_text: str) -> bool:
        """Does this read as a numeric expression on its own?"""
        try:
            parse_num_expr(value_text, label, loc, allow_live=True)
            return True
        except Exception:
            return False

    specs: List[dict] = []
    for part in text.split("&&"):
        part = part.strip()
        if not part:
            continue
        m = _TARGET_RE.match(part)
        if not m:
            # No '<target>-' at all. An untargeted field says so by omission;
            # a targeted one has simply been written wrong.
            if bare_ok:
                specs.append({"kind": KIND_ALL, "ref": None, "rate": _value(part)})
                continue
            raise Exception(
                f"Taskipelago: could not read '{part}' in {label} on {loc}. "
                f"Expected '<target>-<value>', for example '\"Bake Bread\"-1.5', "
                f"'Kitchen-0.5' or '*-0.1'."
            )
        quoted, index, star, bare, value_text = m.groups()
        if star:
            specs.append({"kind": KIND_ALL, "ref": None, "rate": _value(value_text)})
        elif bare is not None:
            bare = bare.strip()
            if bare not in region_names:
                # 'N_TASKS - 1' is a value, not a region called 'N_TASKS'.
                if bare_ok and _is_value(part):
                    specs.append({"kind": KIND_ALL, "ref": None, "rate": _value(part)})
                    continue
                raise Exception(
                    f"Taskipelago: {label} on {loc} targets unknown region '{bare}'. "
                    f"Quote the name to target a task instead."
                )
            specs.append({"kind": KIND_REGION, "ref": bare, "rate": _value(value_text)})
        elif quoted is not None:
            try:
                idx = task_names.index(quoted)
            except ValueError:
                raise Exception(
                    f"Taskipelago: {label} on {loc} targets unknown task '{quoted}'."
                )
            specs.append({"kind": KIND_TASK, "ref": idx, "rate": _value(value_text)})
        else:
            idx_1 = int(index)
            if idx_1 < 1 or idx_1 > len(task_names):
                raise Exception(
                    f"Taskipelago: {label} on {loc} targets task index {idx_1}, "
                    f"which is out of range (1..{len(task_names)})."
                )
            specs.append({"kind": KIND_TASK, "ref": idx_1 - 1, "rate": _value(value_text)})
    return specs


def drop_manual_targets(specs: List[dict], manual: List[bool]) -> Tuple[List[dict], List[int]]:
    """
    Remove specs aimed straight at a manual task, which is an ordinary
    Taskipelago task and reads no clicker grant. Returns the kept specs and the
    1-based numbers of the tasks that were dropped, for the warning.

    Region and '*' specs are left alone: the client skips the manual tasks
    inside them, exactly as it skips locked ones.
    """
    kept: List[dict] = []
    dropped: List[int] = []
    for spec in specs:
        if spec["kind"] == KIND_TASK and 0 <= spec["ref"] < len(manual) and manual[spec["ref"]]:
            dropped.append(spec["ref"] + 1)
            continue
        kept.append(spec)
    return kept, dropped


def remap_spec_tasks(specs: List[dict], task_map: Dict[int, int]) -> List[dict]:
    """Renumber task targets after randomized selection; dropped tasks fall away."""
    out: List[dict] = []
    for spec in specs:
        if spec["kind"] != KIND_TASK:
            out.append(spec)
            continue
        new = task_map.get(spec["ref"])
        if new is not None:
            out.append({**spec, "ref": new})
    return out


# ---------------------------------------------------------------------------
# Region-parallel lists
# ---------------------------------------------------------------------------

def parse_region_flags(raw: List[str], regions: List[str], label: str,
                       warn) -> Dict[str, bool]:
    """'true'/'false'/blank per region; entries beyond `regions` warn and are ignored."""
    if len(raw) > len(regions):
        warn(f"[Taskipelago] WARNING: {label} has {len(raw)} entries but there are "
             f"{len(regions)} region(s); the extra entries are ignored.")
    out: Dict[str, bool] = {}
    for i, rname in enumerate(regions):
        text = (raw[i].strip().lower() if i < len(raw) else "")
        if text in ("", "false"):
            out[rname] = False
        elif text == "true":
            out[rname] = True
        else:
            raise Exception(
                f"Taskipelago: {label} for region '{rname}' is '{raw[i]}'; "
                f"expected 'true', 'false' or blank."
            )
    return out


def parse_region_rates(raw: List[str], regions: List[str], label: str, n_tasks: int,
                       warn) -> Dict[str, Any]:
    """A numeric expression per region; blank inherits (and is left out of the dict)."""
    if len(raw) > len(regions):
        warn(f"[Taskipelago] WARNING: {label} has {len(raw)} entries but there are "
             f"{len(regions)} region(s); the extra entries are ignored.")
    out: Dict[str, Any] = {}
    for i, rname in enumerate(regions):
        text = (raw[i].strip() if i < len(raw) else "")
        if not text:
            continue
        out[rname] = parse_value_expr(
            text, label, f"region '{rname}'", n_tasks, minimum=0.0)
    return out
