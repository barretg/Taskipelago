import random
from typing import List, Tuple

from BaseClasses import Item, ItemClassification

GAME_NAME = "Taskipelago"

# Flavor text for reward items the player left unnamed.
FILLER_ITEMS: List[str] = [
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

# IDs use formula: BASE + (player - 1) * MAX_TASKS + task_index
# Bases are spaced 1_000_000 apart to support up to 1000 players * 1000 tasks each.
BASE_ITEM_ID = 911_000_000
BASE_TOKEN_ID = 912_000_000
MAX_TASKS = 1000

CLASSIFICATION_MAP = {
    "trap": ItemClassification.trap,
    "useful": ItemClassification.useful,
    "progression": ItemClassification.progression,
    "junk": ItemClassification.filler,
}


class TaskipelagoItem(Item):
    game = GAME_NAME


# Pre-registered stable ID maps (covers all possible tasks up to MAX_TASKS).
# The world narrows these down at generation time.
reward_item_name_to_id: dict[str, int] = {
    f"Reward {i}": BASE_ITEM_ID + (i - 1) for i in range(1, MAX_TASKS + 1)
}
token_item_name_to_id: dict[str, int] = {
    f"Task Complete {i}": BASE_TOKEN_ID + (i - 1) for i in range(1, MAX_TASKS + 1)
}

ITEM_NAME_TO_ID: dict[str, int] = {**reward_item_name_to_id, **token_item_name_to_id}


def get_item_classification(reward_type: str, forced_progression: bool) -> ItemClassification:
    if forced_progression:
        return ItemClassification.progression
    return CLASSIFICATION_MAP.get(reward_type.lower(), ItemClassification.filler)


def _parse_positive_int(s: str) -> int:
    try:
        return max(1, int(s)) if s else 1
    except ValueError:
        return 1


def build_item_editor_rows(
    items_raw_input: List[str],
    item_types_raw: List[str],
    item_consumable_raw: List[str],
    item_count_raw: List[str],
) -> Tuple[List[str], List[str], List[bool], List[int]]:
    """
    Build per-editor-row item state (text/type/consumable/count). Item rows are an
    independent list from task rows (their own count each); only the summed totals
    need to match. Blank item text is replaced with random filler flavor text.
    """
    allowed_types = {"trap", "junk", "useful", "progression"}
    n = len(items_raw_input)

    items_raw_editor = [x if x else random.choice(FILLER_ITEMS) for x in items_raw_input]

    item_types_editor = [
        (item_types_raw[i].strip().lower() if i < len(item_types_raw) else "junk")
        for i in range(n)
    ]
    item_types_editor = [rt if rt in allowed_types else "junk" for rt in item_types_editor]

    item_consumable_editor = [
        (i < len(item_consumable_raw) and item_consumable_raw[i].strip().lower() == "true")
        for i in range(n)
    ]

    item_counts_editor = [
        _parse_positive_int(item_count_raw[i] if i < len(item_count_raw) else "")
        for i in range(n)
    ]

    return items_raw_editor, item_types_editor, item_consumable_editor, item_counts_editor


def expand_rows(rows: List, counts: List[int]) -> List:
    """Repeat each row by its parallel count, preserving order."""
    out = []
    for row, count in zip(rows, counts):
        out.extend([row] * count)
    return out


def pad_or_trim_names(names: List[str], n: int) -> List[str]:
    """Pad with random filler flavor text (or trim) to exactly n entries."""
    if len(names) < n:
        names = names + [random.choice(FILLER_ITEMS) for _ in range(n - len(names))]
    return names[:n]