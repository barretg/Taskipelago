"""Write the era YAML corpus (tests/parity/yaml_corpus/era_*.yaml).

builds/ holds released apworlds, not YAMLs, so this synthesizes one YAML per
distinct legacy export shape (key sets taken from export_yaml in each
builds/<ver>/client.py), dumped with PyYAML the way the Tk client wrote them.
hand_*.yaml files in the same folder are hand-written edge cases and are not
touched here.

    python tests/parity/make_yaml_corpus.py
"""
from __future__ import annotations

from pathlib import Path

import yaml

OUT = Path(__file__).resolve().parent / "yaml_corpus"
FILLER = "nothing here, get pranked nerd"


def doc(block: dict, name: str = "Barret") -> dict:
    return {"name": name, "game": "Taskipelago", "description": "YAML template for Taskipelago", "Taskipelago": block}


def head(dl_on: bool = False) -> dict:
    return {
        "progression_balancing": 50,
        "accessibility": "full",
        "death_link": {"true": 50 if dl_on else 0, "false": 0 if dl_on else 50},
    }


V01 = {**head(), "tasks": ["Wash dishes", "Cook dinner", "Read 10 pages"],
       "rewards": ["Cookie", FILLER, "Nap"], "death_link_pool": []}

V02 = {**head(True), "tasks": V01["tasks"], "rewards": V01["rewards"],
       "task_prereqs": ["", "1", "1, 2"], "lock_prereqs": True, "death_link_pool": ["Pushups"]}

V03 = {**head(True), "tasks": V01["tasks"], "rewards": V01["rewards"],
       "task_prereqs": ["", "1", "1, 2"], "lock_prereqs": False,
       "death_link_pool": ["Pushups", "Plank"], "death_link_weights": ["3"], "death_link_amnesty": 2}

V05 = {**head(), "tasks": V01["tasks"], "rewards": ["Cookie", FILLER, "Nap"],
       "reward_types": ["useful", "junk", "trap"], "task_prereqs": ["", "1", "2"],
       "reward_prereqs": ["", "", "1"], "lock_prereqs": True,
       "death_link_pool": [], "death_link_weights": [], "death_link_amnesty": 0}

# v0.6 added goal_tasks (a string), v0.7 made it a list; both sit after lock_prereqs.
V06 = {k: V05[k] for k in list(V05)[:9]} | {"goal_tasks": "3"} | {k: V05[k] for k in list(V05)[9:]}
V07 = {k: V05[k] for k in list(V05)[:9]} | {"goal_tasks": ["2 || 3"]} | {k: V05[k] for k in list(V05)[9:]}

V08 = {**head(),
       "progressive_groups": ["keys"],
       "reward_progressive_group": ["keys", "keys", "", ""],
       "tasks": ["Walk", "Walk", "Cook", "Read"],
       "rewards": ["Key", "Key", "Snack", "Book"],
       "reward_types": ["progression", "progression", "junk", "useful"],
       "task_prereqs": ["", "", "1", "3"],
       "reward_prereqs": ["", "", "keys-1", "keys*2"],
       "lock_prereqs": True, "hide_unreachable_tasks": False, "goal_tasks": [],
       "death_link_pool": [], "death_link_weights": [], "death_link_amnesty": 0}


def v09_block(colors=False, priority=False, v100=False) -> dict:
    b = {**head(True),
         "progressive_groups": ["tickets"],
         "item_progressive_group": ["", "", "", "tickets"],
         "regions": ["chores", "fun"],
         "region_default_pcts": [75, 100]}
    if colors:
        b["region_colors"] = ["#e05c5c", ""]
    if v100:
        b["region_prereqs"] = ["", "chores-50"]
    b["task_region"] = ["chores", "chores", "fun"]
    if priority:
        b["task_priority"] = ["true", "false", "false"]
    b["tasks"] = ["Laundry", "Vacuum", "Game night"]
    b["task_count"] = ["2", "1", "1"]
    if v100:
        b["task_description"] = ["Sort by color", "", "Board games"]
    b.update({
        "items": ["Gold", "A big thumbs up", "Free dopamine", "Ticket"],
        "item_types": ["progression", "junk", "junk", "progression"],
        "item_fillers": [False, True, True, False],
        "item_consumable": ["true", "false", "false", "false"],
        "item_count": ["1", "1", "1", "1"],
        "task_prereqs": ["", "chores-50", "chores && 1"],
        "item_prereqs": ["", "4", "tickets*1 || 1"],
        "task_cost": ["", '"Gold"*1', "1*1"],
        "lock_prereqs": True, "hide_unreachable_tasks": True,
    })
    if v100:
        b["task_reward_previews"] = 2
    b.update({"goal_tasks": ["3"],
              "death_link_pool": ["Pushups", "Plank"], "death_link_weights": ["1", "2"], "death_link_amnesty": 1})
    return b


V102 = v09_block(colors=True, priority=True, v100=True)
V102.update({
    "tasks": ["Laundry", "Vacuum", "Game night"],
    "task_count": ["2", "1", "2"],
    "task_prereqs": ["sequential", "prev", "1 || 2"],
    "items": ["Gold", "A big thumbs up", "Free dopamine", "Ticket", "Nap"],
    "item_types": ["progression", "junk", "junk", "progression", "useful"],
    "item_fillers": [False, True, True, False, False],
    "item_consumable": ["true", "false", "false", "false", "true"],
    "item_count": ["1", "1", "1", "1", "1"],
    "item_progressive_group": ["", "", "", "tickets", ""],
    "item_prereqs": ["5", "4 || 2", "(3 || 4) && 1"],
    "task_cost": ["", '"Gold"*2', "1 || 5"],
})

ERAS = {
    "era_v0.1.yaml": doc(V01),
    "era_v0.2.yaml": doc(V02),
    "era_v0.3-v0.4.yaml": doc(V03),
    "era_v0.5.yaml": doc(V05),
    "era_v0.6.yaml": doc(V06),
    "era_v0.7.yaml": doc(V07),
    "era_v0.8.yaml": doc(V08),
    "era_v0.9-v0.9.4.yaml": doc(v09_block()),
    "era_v0.9.5.yaml": doc(v09_block(colors=True)),
    "era_v0.9.6.yaml": doc(v09_block(colors=True, priority=True)),
    "era_v1.0.0-v1.0.1.yaml": doc(v09_block(colors=True, priority=True, v100=True)),
    "era_v1.0.2.yaml": doc(V102),
    "era_player_entry.yaml": {"Barret": {"game": "Taskipelago", "Taskipelago": v09_block(colors=True, v100=True)}},
}


def main() -> None:
    OUT.mkdir(exist_ok=True)
    for name, data in ERAS.items():
        (OUT / name).write_text(yaml.dump(data, sort_keys=False, allow_unicode=True), encoding="utf-8")
    print(f"wrote {len(ERAS)} files to {OUT}")


if __name__ == "__main__":
    main()
