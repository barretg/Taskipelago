from BaseClasses import Location

GAME_NAME = "Taskipelago"

BASE_REWARD_LOC_ID = 910_000
BASE_COMPLETE_LOC_ID = 920_000
MAX_TASKS = 1000


class TaskipelagoLocation(Location):
    game = GAME_NAME


# Pre-registered stable ID maps
reward_loc_name_to_id: dict[str, int] = {
    f"Task {i} (Reward)": BASE_REWARD_LOC_ID + (i - 1) for i in range(1, MAX_TASKS + 1)
}
complete_loc_name_to_id: dict[str, int] = {
    f"Task {i} (Complete)": BASE_COMPLETE_LOC_ID + (i - 1) for i in range(1, MAX_TASKS + 1)
}

LOCATION_NAME_TO_ID: dict[str, int] = {**reward_loc_name_to_id, **complete_loc_name_to_id}