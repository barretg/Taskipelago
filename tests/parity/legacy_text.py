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
                     "Tasks in a randomized region can only be referenced through the region.\n")],
    "goal_tasks": [("The 'prev' and 'sequential' keywords",
                    "Goal Tasks may name tasks in a randomized region. Generation keeps enough of\n"
                    "them to satisfy at least one way to meet the goal (5 || 8 keeps 5 or 8).\n\n"
                    "The 'prev' and 'sequential' keywords")],
    "item_prereq": [
        ("Progressive group refs:", "Item group refs (progressive groups):"),
        ("Count mode: multiple tasks can share the same threshold.",
         "Count mode: multiple tasks can share the same threshold.\n\n"
         "Random-choice and aesthetic groups:\n"
         "  mygroup     ->  the group's default % of its items\n"
         "  mygroup-50  ->  any 50% of the group's items\n"
         "  mygroup*2   ->  any 2 items from the group\n"
         "For random-choice groups these count only the kept items, and items inside\n"
         "the group cannot be referenced individually."),
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
        "Shuffle the order of the tasks kept from this randomized region.\n\n"
        "Off (default): the kept tasks stay in their original list order.\n"
        "On: their order is shuffled per seed.\n\n"
        "Only applies when Randomize is checked for this region."
    ),
    "rg_prereq": (
        "Gate every task in this region behind other regions.\n\n"
        "The expression here is added to each of this region's tasks, on top of that\n"
        "task's own prereqs, so none of them unlock until it is satisfied:\n"
        "  otherregion     ->  that region's default % of its tasks completed\n"
        "  otherregion-75  ->  75% of that region's tasks completed\n"
        "  otherregion*5   ->  5 tasks in that region completed\n"
        "Combine with && , || and parentheses: intro && (caves || cliffs)\n\n"
        "Only whole regions may be named here, never individual tasks, items or\n"
        "'prev'/'sequential'. A region cannot depend on itself, the region named must\n"
        "have at least one task, and dependency cycles between regions are an error.\n\n"
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
        "A subregion always depends on its parent. The parent's default % of tasks is\n"
        "added to the subregion's 'Depends on' expression automatically, so none of the\n"
        "subregion's tasks unlock until the parent is that far along. A parent holding\n"
        "no tasks of its own passes its own 'Depends on' gate down instead.\n\n"
        "Nesting is one level deep, so a region that already has subregions cannot be\n"
        "given a parent of its own. A randomized region cannot be a parent, but a\n"
        "subregion may be randomized."
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
         "A subregion always depends on its parent: the parent's default % of its tasks is added to "
         "the subregion's 'Depends on' expression for you, so the parent must be that far along "
         "before any of the subregion's tasks unlock. A parent with no tasks of its own passes its "
         "own 'Depends on' gate down instead. Nesting is one level deep, and a randomized region "
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
