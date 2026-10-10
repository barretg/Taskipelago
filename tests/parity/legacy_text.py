"""Help text parity (UNIFY 5.3 tooltips, 5.7 tutorial).

Extracts, from legacy_client/client.py:
  - STEPS in TaskipelagoApp._open_tutorial
  - every `_<name>_tip = "..."` string and `Tooltip(_<name>, "...")` text in build_ui
and writes web-client/js/generator/legacy_text.js, so the web generator shows
the legacy text byte for byte:

    python tests/parity/legacy_text.py

tests/python/test_legacy_text.py fails when the JS file is out of date.
Web-only text lives in the modules that use it, not in the generated file.
"""
from __future__ import annotations

import ast
import json
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
CLIENT = ROOT / "legacy_client" / "client.py"
OUT = ROOT / "custom_worlds" / "taskipelago" / "web-client" / "js" / "generator" / "legacy_text.js"


def _method(tree: ast.AST, name: str) -> ast.FunctionDef:
    for node in ast.walk(tree):
        if isinstance(node, ast.FunctionDef) and node.name == name:
            return node
    raise RuntimeError(f"{name} not found")


def legacy_steps(tree: ast.AST) -> list:
    for stmt in ast.walk(_method(tree, "_open_tutorial")):
        if isinstance(stmt, ast.Assign) and any(getattr(t, "id", None) == "STEPS" for t in stmt.targets):
            return [list(step) for step in ast.literal_eval(stmt.value)]
    raise RuntimeError("STEPS not found in _open_tutorial")


def legacy_tips(tree: ast.AST) -> dict:
    tips = {}
    for stmt in ast.walk(_method(tree, "build_ui")):
        if (isinstance(stmt, ast.Assign) and len(stmt.targets) == 1
                and isinstance(stmt.targets[0], ast.Name) and stmt.targets[0].id.endswith("_tip")):
            tips[stmt.targets[0].id.strip("_")[:-len("_tip")]] = ast.literal_eval(stmt.value)
        elif (isinstance(stmt, ast.Call) and getattr(stmt.func, "id", None) == "Tooltip"
                and isinstance(stmt.args[0], ast.Name)):
            tips[stmt.args[0].id.strip("_")] = ast.literal_eval(stmt.args[1])
    return tips


NAME_RULE = ("must start with a letter or underscore and must not contain digits, spaces,\n"
             "quotes, parentheses, commas, && or ||.")
# Intentional v1.1 text changes applied on top of the legacy text: {key: [(old, new)]}.
V11_TIP_CHANGES = {
    # F8: unified region / progressive group name rule.
    "pg_hint": [("may only contain letters, underscores, and hyphens - no digits.", NAME_RULE),
                ("'Prog. Group' column", "'Item Group' column")],
    "rg_hint": [
        ("may only contain letters, underscores, and hyphens - no digits.", NAME_RULE),
        ("A task cannot depend on its own region.\nRegions",
         "A task cannot depend on its own region in any form.\n\n"
         "Check Randomize on a region row to keep only N (or N%) of its tasks per seed.\n"
         "Tasks may only reference a randomized region as a whole, never its individual tasks.\n\n"
         "Regions"),
    ],
    # Randomized regions and item group types.
    "region_col": [("A task cannot depend on its own region.",
                    "A task cannot depend on its own region in any form (myregion, myregion-75,\n"
                    "myregion*5).\n\n"
                    "Tasks in a randomized region cannot be referenced individually (number,\n"
                    "quoted name, 'prev' or 'sequential'). Reference the region as a whole.")],
    "task_prereq": [("A task cannot depend on its own region.\n",
                     "A task cannot depend on its own region.\n"
                     "Tasks in a randomized region can only be referenced through the region.\n"),
                    ("cannot be used as region or progressive group names.",
                     "cannot be used as region or progressive group names.\n\n"
                     "item( ... ) wraps an item prereq, so items can stand in for tasks:\n"
                     "  item(4) || 2          ->  item 4 received OR task 2 completed\n"
                     "  item(\"Blue Key\") || \"Pick the lock\"\n"
                     "  item(keys*3) || 7     ->  3 items from group 'keys' OR task 7\n"
                     "Inside item( ... ) a progressive group uses count mode only (keys*3).")],
    "goal_tasks": [("The 'prev' and 'sequential' keywords",
                    "Goal Tasks may name tasks in a randomized region. Generation keeps enough of\n"
                    "them to satisfy at least one way to meet the goal (5 || 8 keeps 5 or 8).\n\n"
                    "The 'prev' and 'sequential' keywords"),
                   ("(Task prereqs only).",
                    "(Task prereqs only).\n\n"
                    "item( ... ) wraps an item prereq, so the goal can accept items too:\n"
                    "  item(\"Crown\") || 10  ->  the Crown received OR task 10 completed\n"
                    "  item(keys*3)          ->  3 items from group 'keys' (count mode only)")],
    "item_prereq": [
        ("Progressive group refs:", "Item group refs (progressive groups):"),
        ("Count mode: multiple tasks can share the same threshold.",
         "Count mode: multiple tasks can share the same threshold.\n\n"
         "Random-choice and aesthetic groups:\n"
         "  mygroup     ->  the group's default % of its items\n"
         "  mygroup-50  ->  any 50% of the group's items\n"
         "  mygroup*2   ->  any 2 items from the group\n"
         "For random-choice groups these count only the kept items, and items inside\n"
         "the group cannot be referenced individually.\n\n"
         "task( ... ) wraps a task prereq, so tasks can stand in for items:\n"
         "  1 || task(3)          ->  item 1 received OR task 3 completed\n"
         "  2 && task(caves-50)   ->  item 2 AND half of region caves\n"
         "Inside task( ... ) use task numbers, quoted task names and region refs\n"
         "('prev' and 'sequential' are not allowed there)."),
    ],
    "prog_group": [
        ("Assign this item to a progressive group.", "Assign this item to an item group."),
        ("Group items are interchangeable", "Progressive group items are interchangeable"),
        ("Items in a group are always forced to 'progression' classification.",
         "Items in a progressive group are always forced to 'progression' classification.\n"
         "Items in random-choice and aesthetic groups are forced to 'progression' only\n"
         "when an item prereq references them or their group."),
        ("Groups are defined in the Progressive Groups panel above.",
         "Groups and their types are defined in the Item Groups panel above."),
    ],
    "reward_preview": [("(equivalent to typing !hint).",
                        "(equivalent to typing !hint).\n"
                        "Filler Scout: no automatic previews. At generation each filler item in the\n"
                        "pool is assigned one random task; receiving that filler item reveals the\n"
                        "task's reward preview, whether or not the task is available yet.\n"
                        "Filler Hint: same as Filler Scout, but receiving the filler item also sends\n"
                        "a real Archipelago hint for that task's reward location.")],
    "type": [("Items in a progressive group are always forced to 'progression'.",
              "Items in a progressive group are always forced to 'progression'.\n"
              "Items in random-choice and aesthetic groups are forced to 'progression'\n"
              "only when an item prereq references them or their group.")],
}

# Tooltips that only exist in v1.1.
V11_NEW_TIPS = {
    "rg_random": (
        "Randomize this region: each seed keeps only some of its tasks.\n\n"
        "Keep:\n"
        "  3      ->  keep 3 tasks, chosen at random per seed\n"
        "  40%    ->  keep 40% of the tasks, rounded up (at least 1)\n\n"
        "Duplicated tasks (Count > 1) count separately. Keeping every task only warns;\n"
        "keeping more than the region has is an error.\n\n"
        "Other tasks may only reference this region as a whole (myregion, myregion-75,\n"
        "myregion*5), which counts only the kept tasks."
    ),
    "rg_order": (
        "Shuffle the order of this region's tasks.\n\n"
        "Off (default): the tasks stay in their original list order.\n"
        "On: their order is shuffled per seed.\n\n"
        "Works with or without Randomize. With Randomize, only the kept tasks are\n"
        "shuffled. Without it, every task is kept and shuffled, and its tasks can still\n"
        "be referenced individually ('prev' and 'sequential' keep their original targets).\n"
        "A shuffle-only region may also be a parent.\n\n"
        "A subregion inherits this from its parent: when the parent shuffles, the\n"
        "subregion's box is shown on and locked, and each subregion's tasks are\n"
        "shuffled among themselves."
    ),
    "rg_prereq": (
        "Gate every task in this region behind other regions, tasks or items.\n\n"
        "The expression here is added to each of this region's tasks, on top of that\n"
        "task's own prereqs, so none of them unlock until it is satisfied:\n"
        "  otherregion     ->  that region's default % of its tasks completed\n"
        "  otherregion-75  ->  75% of that region's tasks completed\n"
        "  otherregion*5   ->  5 tasks in that region completed\n"
        "Combine with && , || and parentheses: intro && (caves || cliffs)\n\n"
        "task( ... ) and item( ... ) target a specific task or item. Inside the\n"
        "parentheses write any ordinary task prereq or item prereq expression:\n"
        "  task(3)                ->  task 3 completed\n"
        "  task(\"Do the dishes\")  ->  that named task completed\n"
        "  task(1 || 2)           ->  task 1 or task 2 completed\n"
        "  task(caves-50)         ->  region refs work inside task( ... ) too\n"
        "  item(4)                ->  item 4 received\n"
        "  item(\"Blue Key\")       ->  that named item received\n"
        "  item(keys*3)           ->  3 items from progressive group 'keys'\n"
        "Mix them freely: task(3) && (item(\"Blue Key\") || caves-50)\n\n"
        "Inside task( ... ) use task numbers, quoted task names and region refs;\n"
        "inside item( ... ) use item numbers, quoted item names and group counts\n"
        "(group*N). A progressive group must use count mode here, never ordering mode\n"
        "(group or group-N), since an ordering position belongs to a single task.\n"
        "'prev' and 'sequential' are never allowed.\n\n"
        "A region cannot depend on itself or on a task inside itself, the region named\n"
        "must have at least one task, and dependency cycles between regions are an\n"
        "error. Tasks and items inside a randomized region or random-choice group can\n"
        "only be referenced through the region or group as a whole.\n\n"
        "Blank (the default) means the region's tasks are gated only by their own prereqs."
    ),
    "rg_parent": (
        "Make this region a subregion of another region.\n\n"
        "Blank (the default) leaves it as a top-level region.\n\n"
        "A subregion behaves exactly like any other region: tasks are assigned to it,\n"
        "prereqs reference it by name, it can be randomized, and it has its own color.\n"
        "Display: the play client's region progress list hides subregions until you\n"
        "click their parent's row to expand it, and the parent's bar counts its own\n"
        "tasks plus every task in its subregions.\n\n"
        "A subregion inherits its parent's requirements: the parent's 'Depends on'\n"
        "expression is added to the subregion's automatically, so the subregion unlocks\n"
        "whenever the parent does. A subregion's tasks count toward its parent, so a\n"
        "reference to the parent region (parent, parent-50, parent*5) counts them too.\n\n"
        "Nesting is one level deep, so a region that already has subregions cannot be\n"
        "given a parent of its own. A randomized region cannot be a parent, but a\n"
        "subregion may be randomized."
    ),
    "rg_disabled": (
        "Leave this region out of the seed without deleting it.\n\n"
        "None of its tasks are generated, and every reference to the region or to one\n"
        "of its tasks (prereqs, Depends on, goal, clicker targets, DeathLink pool)\n"
        "counts as already satisfied. Disabling a parent also disables its subregions\n"
        "(their Disabled box is shown on and locked).\n"
        "Disabled takes priority over Randomize: its tasks are never randomized in.\n"
        "A goal that only references disabled content falls back to every task.\n\n"
        "Its tasks stay editable but are greyed out. Problems in them are warnings at\n"
        "export, not errors."
    ),
    "group_type": (
        "How the group behaves:\n\n"
        "  progressive    ->  items are interchangeable; grp-N is the Nth position,\n"
        "                     grp*N is any N items (the original behavior)\n"
        "  random-choice  ->  each seed keeps only Keep items from the group; the rest\n"
        "                     are removed. Kept items are normal, distinct items\n"
        "  aesthetic      ->  color and inventory grouping only; items are normal,\n"
        "                     distinct items\n\n"
        "For random-choice and aesthetic, grp-N means any N% of the items and grp*N\n"
        "means any N items."
    ),
    "group_early": (
        "Place every item in this group early (see the Early item column).\n\n"
        "A subgroup inherits this from its parent: when the parent is Early, the\n"
        "subgroup's box is shown on and locked."
    ),
    "group_disabled": (
        "Leave this group's items out of the seed without deleting them.\n\n"
        "None of its items are generated, and every reference to the group or to one\n"
        "of its items (prereqs, Depends on, goal) counts as already satisfied.\n"
        "Disabled takes priority over random-choice: its items are never drawn.\n\n"
        "Its currency is unavailable: a task cost branch paid in it cannot be used, and\n"
        "a cost with no other branch is dropped (with a warning at export).\n\n"
        "Its items stay editable but are greyed out. Problems in them are warnings at\n"
        "export, not errors."
    ),
    "group_parent": (
        "Make this group a subgroup of another item group.\n\n"
        "Blank (the default) leaves it as a top-level group.\n\n"
        "A subgroup behaves exactly like any other group: items are assigned to it,\n"
        "prereqs reference it by name, it has its own type and color.\n"
        "A subgroup's items count toward its parent, so a reference to the parent\n"
        "group (Parent, Parent-50, Parent*5) counts them too. The client's Items tab\n"
        "lists subgroups under their parent.\n\n"
        "A subgroup inherits its parent's Early and Disabled: when the parent has one\n"
        "on, the subgroup's box is shown on and locked. When the parent has it off,\n"
        "the subgroup can still turn it on for itself.\n\n"
        "Nesting is one level deep, so a group that already has subgroups cannot be\n"
        "given a parent. A random-choice group cannot be a parent, but a subgroup may\n"
        "be random-choice."
    ),
    "item_early": (
        "Place this item early.\n\n"
        "Uses Archipelago's early_items: at generation the item is placed in a\n"
        "sphere 1 location (one reachable with no items, in any world) before\n"
        "the main fill. Each copy (Count) is placed early.\n\n"
        "If there are not enough sphere 1 locations, the rest are placed\n"
        "normally and a warning is logged."
    ),
    "group_pick": (
        "Random-choice groups only: how many items to keep per seed.\n\n"
        "  2      ->  keep 2 items, chosen at random\n"
        "  50%    ->  keep 50% of the items, rounded up (at least 1)\n\n"
        "Blank keeps every item. Duplicated items (Count > 1) count separately."
    ),
    "group_pct": (
        "Percentage of the group's items required by a bare group reference (mygroup).\n\n"
        "Blank on a progressive group keeps the original behavior (fills the lowest\n"
        "unused position). Blank on other types means 100%.\n"
        "Setting a value on a progressive group makes bare refs use count mode."
    ),
}


# Intentional v1.1 tutorial changes: {step title: [(old, new)]}.
V11_STEP_CHANGES = {
    # F8: unified region / progressive group name rule. F4: renames update references.
    "Regions": [
        ("Names can only use letters, underscores, and hyphens -- no spaces or digits.",
         "Names must start with a letter or underscore and cannot contain digits, spaces, quotes,\n"
         "parentheses, commas, && or ||."),
        ("Press Enter or click away to confirm changes.",
         "Press Enter or click away to confirm changes. If other expressions reference the old name,\n"
         "you are asked whether to update them."),
        ("Regions also appear as Archipelago regions for location hinting.",
         "A task cannot reference its own region in any form (chores, chores-75 or chores*5).\n\n"
         "Randomizing a region:\n"
         "Check Randomize on a region row and enter how many of its tasks to keep:\n"
         "  3      keep 3 tasks\n"
         "  40%    keep 40% of the tasks, rounded up (at least 1)\n"
         "The tasks are chosen when the seed is generated, so every seed can differ. The YAML keeps "
         "every task. Duplicated tasks (Count > 1) count separately. Keeping every task only warns; "
         "keeping more tasks than the region has is an error.\n\n"
         "Subregions:\n"
         "Set a region's Parent to file it under another region. A subregion works exactly like "
         "any other region - tasks, prereqs, randomizing and colors all behave the same - but the "
         "client's region progress list hides it until you click its parent's row to expand it, and "
         "the parent's bar counts its subregions' tasks too.\n\n"
         "A subregion inherits its parent's requirements: the parent's 'Depends on' expression is "
         "added to the subregion's for you, so the subregion unlocks whenever the parent does. A "
         "subregion's tasks count toward its parent, so any reference to the parent region counts "
         "them too. Nesting is one level deep, and a randomized region "
         "cannot be a parent (though a subregion may be randomized).\n\n"
         "Regions also appear as Archipelago regions for location hinting."),
    ],
    # Item group types.
    "Progressive Groups": [
        ("Progressive groups link several items together",
         "Item groups collect related items under one name and color. Each group has a Type: "
         "progressive, random-choice or aesthetic (see the next steps). Progressive groups link "
         "several items together"),
        ("1. In the Progressive Groups panel,", "1. In the Item Groups panel,"),
        ('the "Prog. Group" dropdown', 'the "Item Group" dropdown'),
        ("All group items are automatically classified as Progression.",
         "Progressive group items are automatically classified as Progression."),
    ],
    "Item Types": [
        ("Items in a progressive group and consumable items are automatically forced to "
         "Progression, regardless of what you set here.",
         "Items in a progressive group and consumable items are automatically forced to "
         "Progression, regardless of what you set here. Items in random-choice and aesthetic "
         "groups are forced to Progression only when an Item Prereq references them or their group."),
    ],
}

# Intentional v1.1 tutorial title changes: {legacy title: new title}. Applied after V11_STEP_CHANGES.
V11_TITLE_CHANGES = {
    "Progressive Groups": "Item Groups (Progressive, Random-Choice, Aesthetic)",
}


# The legacy text writes dashes as " -- ". Show a comma where the next word continues
# the sentence, a colon otherwise (titles always get a colon).
COMMA_AFTER_DASH = {"except", "like", "including", "useful", "higher", "no"}


def undash(text: str, title: bool = False) -> str:
    import re
    def sub(m):
        return ", " if not title and m.group(1) in COMMA_AFTER_DASH else ": "
    return re.sub(r" -- (?=(\S+))", sub, text)


def v11_steps(tree: ast.AST) -> list:
    steps = legacy_steps(tree)
    for step in steps:
        for old, new in V11_STEP_CHANGES.get(step[0], []):
            assert old in step[1], (step[0], old)
            step[1] = step[1].replace(old, new)
        step[0] = V11_TITLE_CHANGES.get(step[0], step[0])
    return [[undash(title, title=True), undash(text)] for title, text in steps]


def v11_tips(tree: ast.AST) -> dict:
    tips = legacy_tips(tree)
    for key, changes in V11_TIP_CHANGES.items():
        for old, new in changes:
            assert old in tips[key], (key, old)
            tips[key] = tips[key].replace(old, new)
    for key, text in V11_NEW_TIPS.items():
        assert key not in tips, key
        tips[key] = text
    return {key: undash(text) for key, text in tips.items()}


def render() -> str:
    tree = ast.parse(CLIENT.read_text(encoding="utf-8"))
    dump = lambda s: json.dumps(s, ensure_ascii=True)  # noqa: E731
    lines = [
        "// GENERATED by tests/parity/legacy_text.py from legacy_client/client.py.",
        "// Do not edit: regenerate after changing the legacy text or the V11_* changes.",
        "",
        "// _open_tutorial STEPS: [title, text]",
        "export const LEGACY_STEPS = [",
    ]
    for title, content in v11_steps(tree):
        lines.append(f"  [{dump(title)},")
        lines.append(f"    {dump(content)}],")
    lines += ["];", "", "// build_ui tooltips, keyed by the legacy variable name", "export const TIPS = {"]
    for key, text in sorted(v11_tips(tree).items()):
        lines.append(f"  {key}: {dump(text)},")
    lines.append("};")
    return "\n".join(lines) + "\n"


def main() -> None:
    OUT.write_text(render(), encoding="utf-8")
    print(f"wrote {OUT.relative_to(ROOT)}")


if __name__ == "__main__":
    main()
