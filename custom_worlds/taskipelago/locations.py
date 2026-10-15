from BaseClasses import Location

GAME_NAME = "Taskipelago"

# IDs use formula: BASE + (player - 1) * MAX_TASKS + task_index
# Same-namespace bases are spaced 20_000_000 apart: up to 4000 players * 5000 tasks each.
# Seeds generated before 5000-task support used 912M/913M bases and a 1000 stride;
# the client reads the bases from slot_data, so those seeds still run.
BASE_REWARD_LOC_ID = 910_000_000
BASE_COMPLETE_LOC_ID = 930_000_000
MAX_TASKS = 5000


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