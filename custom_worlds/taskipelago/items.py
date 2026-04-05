from BaseClasses import Item, ItemClassification

GAME_NAME = "Taskipelago"

BASE_ITEM_ID = 911_000
BASE_TOKEN_ID = 912_000
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