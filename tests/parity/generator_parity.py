"""YAML Generator import/export parity corpus (UNIFY 5.3, M4 gate).

Runs the legacy Tk generator logic (legacy_generator.py) over:
  - imports: every tests/parity/yaml_corpus/*.yaml, loaded with yaml.safe_load
  - exports: EXPORT_CASES below, plus every model the imports produced
and writes generator_golden.json:

    python tests/parity/generator_parity.py

tests/python/test_generator_parity.py checks the golden file still matches the
legacy code; tests/js/generator/yaml_parity.test.mjs checks the JS generator
(generator/yaml_import.js, yaml_export.js) against it, loading the JS export
text back with PyYAML. Random filler names are FILLER_PLACEHOLDER on both sides.
"""
from __future__ import annotations

import copy
import json
from pathlib import Path

import yaml

import legacy_generator as lg

HERE = Path(__file__).resolve().parent
CORPUS_DIR = HERE / "yaml_corpus"
GOLDEN = HERE / "generator_golden.json"
F = lg.FILLER_PLACEHOLDER


def task(name, **kw):
    t = {"name": name, "prereq": "", "itemPrereq": "", "cost": "", "region": "",
         "priority": False, "count": 1, "desc": ""}
    t.update(kw)
    return t


def item(name, **kw):
    it = {"name": name, "filler": False, "type": "useful", "progGroup": "", "consumable": False, "count": 1}
    it.update(kw)
    return it


def filler(count=1):
    return item(F, filler=True, type="junk", count=count)


def region(name, pct=100, color="", prereq=""):
    return {"name": name, "pct": pct, "color": color, "prereq": prereq}


def model(**kw):
    m = {
        "playerName": "Player", "progressionBalancing": 50, "accessibility": "full",
        "deathLinkEnabled": False, "deathLinkAmnesty": 0, "lockPrereqs": True,
        "hideUnreachable": True, "taskRewardPreviews": 0, "goalTasks": "",
        "progGroups": [], "regions": [], "nextColorIdx": 0,
        "tasks": [task("A"), task("B")], "items": [item("X"), item("Y")], "deathLink": [],
    }
    m.update(kw)
    return m


EXPORT_CASES = [
    ("no_player_name", model(playerName="   ")),
    ("no_tasks", model(tasks=[task(""), task("  ")])),
    ("duplicate_tasks", model(tasks=[task("A"), task("B"), task(" A "), task("B"), task("C")],
                              items=[item("X", count=5)])),
    ("duplicate_items", model(items=[item("X"), item("X ")])),
    ("filler_names_may_repeat", model(items=[filler(), filler()])),
    ("bad_region_names", model(regions=[region("ok"), region("bad1"), region("-x"), region("a-"),
                                        region("has space"), region("a\n")])),
    # F8: names legacy rejected (or never checked) that the unified rule accepts, and bad group names.
    ("f8_names_accepted", model(progGroups=["weapons+", "side-quests!"], regions=[region("chores-"), region("caf\u00e9")],
                                tasks=[task("A", itemPrereq="weapons+*1"), task("B", prereq="chores--50")],
                                items=[item("X", progGroup="weapons+"), item("Y")])),
    ("f8_bad_group_names", model(progGroups=["ok", "two words", "x(y", "a||b"])),
    ("reserved_region", model(regions=[region("Prev")])),
    ("reserved_group", model(progGroups=["keys", "sequential"])),
    ("unbalanced_declined", model(items=[item("X")]), False),
    ("unbalanced_accepted", model(items=[item("X")]), True),
    ("quote_in_names", model(tasks=[task('Say "hi"'), task("B")], items=[item("X"), item('Y"')])),
    ("unresolved_names", model(tasks=[task("A", prereq='"Nope" || "B"'), task("B", itemPrereq='"Z"')])),
    ("deathlink_empty_pool", model(deathLinkEnabled=True, deathLink=[{"text": "  ", "weight": "3"}])),
    ("invalid_expressions", model(
        progGroups=["keys"], regions=[region("chores", prereq="fun-50"), region("fun")],
        tasks=[task("A", prereq="3"), task("B", itemPrereq="keys*x", cost='"X"*2'), task("C", cost="9*1")],
        items=[item("X", count=2), item("Y", consumable=True, type="progression")],
        goalTasks='"Missing"')),
    ("goal_parse_error", model(goalTasks="1 &&")),
    ("full_document", model(
        playerName="  Barret  ", progressionBalancing="30", accessibility="minimal",
        deathLinkEnabled=True, deathLinkAmnesty="2", lockPrereqs=False, hideUnreachable=False,
        taskRewardPreviews=2, goalTasks=' "Walk" || chores-50 ',
        progGroups=["keys"],
        regions=[region("chores", 75, "#e05c5c"), region("fun", "100", "", "chores-50")],
        tasks=[
            task(" Walk ", region="chores", priority=True, count="2", desc="  " + "d" * 120 + "  "),
            task("Cook", prereq='"Walk"', itemPrereq="keys-1 || 2", cost='1*2', region="fun"),
            task("yes", prereq="prev", count=" 3 "),
            task("017", prereq="sequential", itemPrereq='"Key"', cost='"Gold"'),
            task("", prereq="ignored row"),
        ],
        items=[
            item("Gold", consumable=True, type="progression", count="2"),
            filler(3),
            item("Key", progGroup="keys", type="progression", count=2),
            item(" Sword ", type=" Trap "),
            item("", count=1),
            item("on", type=""),
        ],
        deathLink=[{"text": "Pushups", "weight": ""}, {"text": "", "weight": "9"}, {"text": " Plank ", "weight": " 4 "}])),
    ("counts_fall_back_to_one", model(
        tasks=[task("A", count="abc"), task("B", count="0"), task("C", count="2.5"), task("D", count=-4)],
        items=[item("X", count=""), item("Y", count="1_0"), item("Z", count="+2")]), True),
    ("filler_expansion_remaps_refs", model(
        progGroups=["keys"],
        tasks=[task("A", itemPrereq="3 && (1 || 4)", cost="1*1"), task("B", itemPrereq="5", cost='"Gold"*2 || 1'),
               task("C", itemPrereq="2"), task("D"), task("E")],
        items=[item("Gold", consumable=True, type="progression"), filler(2), item("Key", progGroup="keys", type="progression"),
               filler(1), item("Sword")]), True),
    ("filler_named_item_in_cost", model(
        tasks=[task("A", cost="2"), task("B")], items=[item("Gold", consumable=True, type="progression"), filler()])),
    ("duplicate_region_entries", model(regions=[region("chores", 10, "#111111"), region("fun"), region("chores", 20, "", "fun")])),
    ("unicode_and_yaml11_strings", model(
        playerName="José",
        tasks=[task("掃除"), task("1:30"), task("0x1F"), task("~"), task("null"), task("Yes"),
               task("1e5"), task("2.50"), task("=")],
        items=[item("off", count=4), item("NO"), item("12:30:45"), item("2001-12-14"), item("<<", count=2)])),
]


def bingo(**kw):
    m = {"playerName": "Bingo Player", "x": 5, "y": 5, "bingoal": 3, "progressionBalancing": 50,
         "accessibility": "full", "deathLinkEnabled": False, "deathLinkAmnesty": 0,
         "spaces": "", "rewards": "", "deathLinkPool": ""}
    m.update(kw)
    return m


def lines(prefix, n, extra=""):
    return "\n".join(f"{prefix} {i}" for i in range(1, n + 1)) + extra


BINGO_EXPORT_CASES = [
    ("bingo_5x5", bingo(spaces=lines("Space", 28, "\nSpace 3\n  Space 5  \n\n"), rewards="Cookie\nNap\nCookie\n\n",
                        deathLinkEnabled=True, deathLinkPool="Pushups\n\n Plank ", deathLinkAmnesty="2")),
    ("bingo_7x5_all_rewards", bingo(x=7, y=5, bingoal=99, spaces=lines("Cell", 40),
                                    rewards=lines("Prize", 20, "\nPrize 1\nPrize 2\nBingo Bonus\n" + "\n".join(["Extra"] * 5)))),
    ("bingo_3x3_pairs", bingo(x=3, y=3, bingoal="2", progressionBalancing="abc", accessibility="minimal",
                              spaces="a\r\nb\u2028c\x85d\x0be\x0cf\x1cg\rh\ni", rewards="only one")),
    ("bingo_1x1", bingo(x=1, y=1, bingoal=0, spaces="Only")),
    ("bingo_4x2", bingo(x=4, y=2, bingoal=5, spaces=lines("S", 8), playerName="  Rect Player  ")),
    ("bingo_bad_numbers", bingo(x="abc", y="2.5", bingoal="", spaces=lines("S", 25), deathLinkAmnesty="x")),
    ("bingo_not_enough_spaces", bingo(spaces=lines("S", 24))),
    ("bingo_no_player", bingo(playerName=" ", spaces=lines("S", 25))),
    ("bingo_deathlink_empty", bingo(spaces=lines("S", 25), deathLinkEnabled=True, deathLinkPool=" \n ")),
]

BINGO_COUNT_CASES = [
    bingo(),
    bingo(spaces=lines("S", 25), rewards=lines("R", 13)),
    bingo(x=7, y=5, spaces=lines("S", 40), rewards=lines("R", 3)),
    bingo(x="bad", y=0, spaces="a\nb", rewards=lines("R", 30)),
    bingo(x=-2, y=3),
]

BINGO_LOAD_DOCS = [
    ("settings_odd_values", {"spaces": "ab", "bingo_x": "7", "bingo_y": None, "bingoal": "x",
                             "progression_balancing": 20, "player_name": "  A Very Long Player Name ",
                             "death_link_enabled": "no", "death_link_pool": [1, None, " p "], "rewards": None,
                             "accessibility": " ", "death_link_amnesty": "3"}),
    ("settings_not_a_list_x", {"spaces": [], "bingo_x": [1], "bingo_y": 4}),
    ("yaml_player_entry", {"Entry Player": {"game": "Taskipelago", "Taskipelago": {
        "bingo_mode": 1, "bingo_dimension_x": 2, "bingo_dimension_y": "2", "tasks": ["a", " b ", None, "d", "e"],
        "rewards": ["Bingo 1,1 Unlock", "Treat", "A nod of respect", "nothing here, get pranked nerd", " Snack "],
        "item_count": "3", "death_link": True, "death_link_pool": "xy", "accessibility": "items"}}}),
    ("yaml_counts_list", {"name": "Counts", "Taskipelago": {
        "bingo_mode": True, "tasks": ["t"] * 30, "items": ["Treat", "Nap", "Bingo 1,2 Unlock"],
        "item_count": ["2", "bad", 3], "death_link": {"true": "10", "false": 10}, "bingoal": 0}}),
    ("yaml_no_bingo_mode", {"name": "Plain", "Taskipelago": {"tasks": ["a"]}}),
    ("yaml_no_block", ["not", "a", "mapping"]),
    ("yaml_bad_dimension", {"name": "Bad", "Taskipelago": {"bingo_mode": True, "bingo_dimension_x": "abc"}}),
]


# ---------------------------------------------------------------------------
# Intentional v1.1 changes applied to the legacy results (plan rule 3).
# ---------------------------------------------------------------------------

LEGACY_PRE_REGION_ERRORS = {"Error", "Duplicate Task Names", "Duplicate Item Names"}


def f8_name_reason(name: str):
    """Mirror of validateRefName (web-client/js/shared/prereq_parser.js)."""
    import re
    if not name:
        return "must not be empty"
    if re.search(r"\d", name):
        return "must not contain digits"
    if any(c.isspace() for c in name):
        return "must not contain spaces"
    if not (name[0].isalpha() or name[0] == "_"):
        return "must start with a letter or underscore"
    if any(c in name for c in '"(),'):
        return "must not contain quotes, parentheses or commas"
    if "&&" in name or "||" in name:
        return "must not contain && or ||"
    if name.lower() in ("prev", "sequential"):
        return "is a reserved word"
    return None


def lg_region_rejected(name: str) -> bool:
    import re
    return not re.match(r'^[a-zA-Z_][a-zA-Z_-]*$', name) or bool(re.search(r'\d', name)) or name.endswith('-')


def _swap(text: str, mapping: dict) -> str:
    for old, new in mapping.items():
        text = text.replace(json.dumps(old)[1:-1], new if new.isascii() else json.dumps(new)[1:-1])
    return text


def apply_v11_changes(m: dict, result: dict) -> dict:
    # F8: unified region / progressive group name rule at export. It replaces the legacy
    # region regex check and adds a group check; reserved words keep their legacy message.
    errors = [msg for msg in result["messages"] if msg[0] == "error"]
    if not (errors and errors[0][1] in LEGACY_PRE_REGION_ERRORS):
        def bad(names):
            return [f"{n} ({f8_name_reason(n)})" for n in names
                    if n.lower() not in ("prev", "sequential") and f8_name_reason(n)]
        regions = [r["name"] for r in m["regions"]]
        if bad(regions):
            return {"data": None, "messages": [["error", "Invalid Region Names",
                    "The following region names are invalid and cannot be exported:\n\n" + "\n".join(bad(regions))]]}
        if errors and errors[0][1] == "Invalid Region Names" and "reserved" not in errors[0][2]:
            # Legacy stopped at a name F8 accepts: export with letter-only aliases, then map back.
            aliases = {r: f"fEightAlias{chr(65 + i)}" for i, r in enumerate(sorted(
                {r for r in regions if lg_region_rejected(r)}, key=len, reverse=True))}
            result = json.loads(_swap(json.dumps(lg.legacy_export(json.loads(_swap(json.dumps(m), aliases)), True)),
                                      {v: k for k, v in aliases.items()}))
            errors = [msg for msg in result["messages"] if msg[0] == "error"]
        reserved_region = errors and errors[0][1] == "Invalid Region Names" and "reserved" in errors[0][2]
        if bad(m["progGroups"]) and not reserved_region:
            return {"data": None, "messages": [["error", "Invalid Progressive Group Names",
                    "The following progressive group names are invalid and cannot be exported:\n\n"
                    + "\n".join(bad(m["progGroups"]))]]}
    return result


def apply_v11_bingo_export(m: dict, result: dict) -> dict:
    # F9: the free space defaults to random filler (junk, filler) instead of a dead
    # "Bingo r,c Unlock" progression item. A user reward there is unchanged.
    data = result["data"]
    if data is None:
        return result
    block = data["Taskipelago"]
    names, types, fillers = [], [], []
    for name, typ, fil, count in zip(block["items"], block["item_types"], block["item_fillers"], block["item_count"]):
        names += [name] * int(count)
        types += [typ] * int(count)
        fillers += [fil] * int(count)
    middle = block["bingo_dimension_x"] * block["bingo_dimension_y"] // 2
    if names[middle].startswith("Bingo ") and types[middle] == "progression":
        names[middle], types[middle], fillers[middle] = lg.load_client().FILLER_ITEMS[0], "junk", True
    order, counts = [], {}
    for key in zip(names, types, fillers):
        if key not in counts:
            order.append(key)
        counts[key] = counts.get(key, 0) + 1
    block["items"] = [k[0] for k in order]
    block["item_types"] = [k[1] for k in order]
    block["item_fillers"] = [k[2] for k in order]
    block["item_count"] = [str(counts[k]) for k in order]
    block["item_progressive_group"] = [""] * len(order)
    return result


def apply_v11_bingo_counts(m: dict, result: dict) -> dict:
    # F9: the rewards label reports rewards beyond the available slots.
    import re
    n = int(re.match(r"Reward slots available: (-?\d+)", result["rewards"]).group(1))
    have = len([line for line in str(m["rewards"]).splitlines() if line.strip()])
    if have > n:
        result["rewards"] += f", {have - n} unused"
    return result


def load_doc(path: Path):
    try:
        return {"doc": yaml.safe_load(path.read_text(encoding="utf-8"))}
    except Exception as e:  # noqa: BLE001
        return {"load_error": type(e).__name__}


def build_golden() -> dict:
    imports = []
    for path in sorted(CORPUS_DIR.glob("*.yaml")):
        loaded = load_doc(path)
        result = {"load_error": loaded["load_error"]} if "load_error" in loaded else lg.legacy_import(loaded["doc"])
        imports.append({"file": path.name, "result": result})

    exports = []
    for case in EXPORT_CASES:
        name, m = case[0], case[1]
        confirm = case[2] if len(case) > 2 else True
        exports.append({"name": name, "confirm": confirm, "model": m,
                        "result": apply_v11_changes(m, lg.legacy_export(copy.deepcopy(m), confirm))})
    for entry in imports:
        m = entry["result"].get("model")
        if m:
            exports.append({"name": f"reexport:{entry['file']}", "confirm": True, "model": m,
                            "result": apply_v11_changes(m, lg.legacy_export(copy.deepcopy(m), True))})
    return {"placeholder": F, "imports": imports, "exports": exports, "bingo": build_bingo()}


def build_bingo() -> dict:
    exports = [{"name": name, "model": m, "result": apply_v11_bingo_export(m, lg.legacy_bingo_export(copy.deepcopy(m)))}
               for name, m in BINGO_EXPORT_CASES]
    settings = [{"name": name, "model": m, "result": lg.legacy_bingo_settings(copy.deepcopy(m))}
                for name, m in BINGO_EXPORT_CASES[:5]]
    counts = [{"model": m, "result": apply_v11_bingo_counts(m, lg.legacy_bingo_counts(copy.deepcopy(m)))}
              for m in BINGO_COUNT_CASES]
    docs = list(BINGO_LOAD_DOCS)
    docs += [(f"settings_from:{e['name']}", e["result"]) for e in settings]
    docs += [(f"yaml_from:{e['name']}", e["result"]["data"]) for e in exports if e["result"]["data"]]
    # F9: a v1.0.2 export (free space is a "Bingo r,c Unlock" item) must still load.
    docs += [(f"v102_yaml_from:{name}", lg.legacy_bingo_export(copy.deepcopy(m))["data"])
             for name, m in BINGO_EXPORT_CASES if name in ("bingo_4x2", "bingo_1x1")]
    loads = [{"name": name, "doc": doc, "result": lg.legacy_bingo_load(copy.deepcopy(doc))} for name, doc in docs]
    return {"exports": exports, "settings": settings, "counts": counts, "loads": loads}


def main() -> None:
    golden = build_golden()
    GOLDEN.write_text(json.dumps(golden, indent=1, ensure_ascii=True) + "\n", encoding="utf-8")
    b = golden["bingo"]
    print(f"wrote {len(golden['imports'])} imports, {len(golden['exports'])} exports, "
          f"{len(b['exports'])} bingo exports, {len(b['loads'])} bingo loads to {GOLDEN.name}")


if __name__ == "__main__":
    main()
