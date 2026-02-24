from __future__ import annotations

from typing import Dict, List, Any

from BaseClasses import Item, ItemClassification, Location, Region
from worlds.AutoWorld import World, WebWorld
from worlds.LauncherComponents import Component, Type, components, launch_subprocess

from .options import TaskipelagoOptions

print("Loading Taskipelago world module...")

# Reward locations: these contain real multiworld items and MUST be checked to send items.
BASE_REWARD_LOC_ID = 910_000

# Completion locations: these contain event items (tokens) for prereq logic.
BASE_COMPLETE_LOC_ID = 920_000

# Taskipelago contributes N reward items to keep item/location counts balanced.
# (Those reward items will be placed somewhere in the multiworld.)
BASE_ITEM_ID = 911_000
BASE_TOKEN_ID = 912_000

MAX_TASKS = 1000


class TaskipelagoWeb(WebWorld):
    game = "Taskipelago"


class TaskipelagoItem(Item):
    game = "Taskipelago"


class TaskipelagoLocation(Location):
    game = "Taskipelago"


class TaskipelagoWorld(World):
    game = "Taskipelago"
    web = TaskipelagoWeb()
    options_dataclass = TaskipelagoOptions

    # Stable ID maps for server/name resolution
    item_name_to_id: Dict[str, int] = {}
    location_name_to_id: Dict[str, int] = {}

    # Pre-register stable IDs for max tasks
    location_name_to_id = {}
    location_name_to_id.update({f"Task {i} (Reward)": BASE_REWARD_LOC_ID + (i - 1) for i in range(1, MAX_TASKS + 1)})
    location_name_to_id.update({f"Task {i} (Complete)": BASE_COMPLETE_LOC_ID + (i - 1) for i in range(1, MAX_TASKS + 1)})

    item_name_to_id.update(
        {f"Reward {i}": int(BASE_ITEM_ID + (i - 1)) for i in range(1, MAX_TASKS + 1)}
    )
    item_name_to_id.update(
        {f"Task Complete {i}": int(BASE_TOKEN_ID + (i - 1)) for i in range(1, MAX_TASKS + 1)}
    )

    def generate_early(self) -> None:
        tasks = [str(t).strip() for t in self.options.tasks.value if str(t).strip()]
        rewards = [str(r).strip() for r in self.options.rewards.value if str(r).strip()]

        reward_types_raw = list(getattr(self.options, "reward_types", None).value) if hasattr(self.options,  "reward_types") else []
        reward_types = [str(x).strip().lower() for x in reward_types_raw if str(x).strip()]

        if not tasks:
            raise Exception("Taskipelago: tasks list is empty.")
        if len(tasks) != len(rewards):
            raise Exception(f"Taskipelago: tasks ({len(tasks)}) and rewards ({len(rewards)}) must be same length.")
        
        # Normalize reward_types to tasks length; default "junk"
        if len(reward_types) < len(tasks):
            reward_types += ["junk"] * (len(tasks) - len(reward_types))
        reward_types = reward_types[:len(tasks)]

        allowed = {"trap", "junk", "useful", "progression"}
        reward_types = [rt if rt in allowed else "junk" for rt in reward_types]

        self._tasks = tasks
        self._rewards = rewards
        self._reward_types = reward_types

        # DeathLink pool validation (only if death_link ends up enabled)
        if bool(self.options.death_link):
            dl_pool = [str(x).strip() for x in self.options.death_link_pool.value if str(x).strip()]
            if not dl_pool:
                raise Exception("Taskipelago: death_link is enabled but death_link_pool is empty.")
            
            raw_w = [str(x).strip() for x in getattr(self.options, "death_link_weights").value or []]

            # pad/truncate to pool length, defaulting to "1"
            if len(raw_w) < len(dl_pool):
                raw_w += ["1"] * (len(dl_pool) - len(raw_w))
            raw_w = raw_w[:len(dl_pool)]

            # parse to floats; bad/empty => 1
            parsed_w = []
            for i, txt in enumerate(raw_w):
                if not txt:
                    parsed_w.append(1.0)
                    continue
                try:
                    w = float(txt)
                except ValueError:
                    raise Exception(
                        f"Taskipelago: invalid death_link_weights[{i}]={txt!r}. Must be a number."
                    )
                # allow 0 to mean "never pick", but prevent negatives
                parsed_w.append(max(0.0, w))

            self._death_link_pool = dl_pool
            self._death_link_weights = parsed_w

            self._death_link_amnesty = int(getattr(self.options, "death_link_amnesty").value or 0)
        else:
            self._death_link_pool = []
            self._death_link_weights = []
            self._death_link_amnest = int(getattr(self.options, "death_link_amnesty").value or 0)

        n = len(tasks)
        if n > MAX_TASKS:
            raise Exception(f"Taskipelago: too many tasks ({n}). Max supported is {MAX_TASKS}.")

        # --- task prereqs parse/normalize ---
        raw_prereqs = list(getattr(self.options, "task_prereqs").value or [])
        if len(raw_prereqs) < n:
            raw_prereqs += [""] * (n - len(raw_prereqs))
        raw_prereqs = raw_prereqs[:n]
        raw_prereqs = [str(x).strip() for x in raw_prereqs]

        parsed_prereqs: List[List[int]] = []
        for i, txt in enumerate(raw_prereqs):
            if not txt:
                parsed_prereqs.append([])
                continue
            parts = [p.strip() for p in txt.split(",") if p.strip()]
            reqs: List[int] = []
            for p in parts:
                try:
                    idx_1 = int(p)
                except ValueError:
                    raise Exception(
                        f"Taskipelago: invalid prereq '{p}' on task {i+1}. "
                        f"Use comma-separated integers like '1,2'."
                    )
                if idx_1 < 1 or idx_1 > n:
                    raise Exception(f"Taskipelago: prereq '{idx_1}' on task {i+1} is out of range (1..{n}).")
                if idx_1 == (i + 1):
                    raise Exception(f"Taskipelago: task {i+1} cannot require itself.")
                reqs.append(idx_1 - 1)

            # de-dupe while preserving order
            seen = set()
            reqs = [x for x in reqs if not (x in seen or seen.add(x))]
            parsed_prereqs.append(reqs)

        # --- reward prereqs parse/normalize ---
        raw_reward_prereqs = list(getattr(self.options, "reward_prereqs").value or [])
        if len(raw_reward_prereqs) < n:
            raw_reward_prereqs += [""] * (n - len(raw_reward_prereqs))
        raw_reward_prereqs = raw_reward_prereqs[:n]
        raw_reward_prereqs = [str(x).strip() for x in raw_reward_prereqs]

        parsed_reward_prereqs: List[List[int]] = []
        for i, txt in enumerate(raw_reward_prereqs):
            if not txt:
                parsed_reward_prereqs.append([])
                continue
            parts = [p.strip() for p in txt.split(",") if p.strip()]
            reqs: List[int] = []
            for p in parts:
                try:
                    idx_1 = int(p)
                except ValueError:
                    raise Exception(
                        f"Taskipelago: invalid reward prereq '{p}' on task {i+1}. "
                        f"Use comma-separated integers like '1,2'."
                    )
                if idx_1 < 1 or idx_1 > n:
                    raise Exception(
                        f"Taskipelago: reward prereq '{idx_1}' on task {i+1} is out of range (1..{n})."
                    )
                reqs.append(idx_1 - 1)  # store 0-based like task_prereqs
            parsed_reward_prereqs.append(reqs)

        self._raw_reward_prereqs = raw_reward_prereqs
        self._parsed_reward_prereqs = parsed_reward_prereqs

        # Any reward that is referenced as a prereq (either completion prereq or reward prereq)
        # must be progression so logic can rely on it.
        forced_prog = set()
        for reqs in parsed_prereqs:
            forced_prog.update(reqs)
        for reqs in parsed_reward_prereqs:
            forced_prog.update(reqs)
        self._forced_progression_rewards = forced_prog

        lock = bool(getattr(self.options, "lock_prereqs"))
        if lock:
            # cycle detect in prereq graph
            visiting = set()
            visited = set()

            def dfs(v: int):
                if v in visiting:
                    raise Exception("Taskipelago: prereq graph contains a cycle. Fix your prereqs.")
                if v in visited:
                    return
                visiting.add(v)
                for u in parsed_prereqs[v]:
                    dfs(u)
                visiting.remove(v)
                visited.add(v)

            for i in range(n):
                dfs(i)

        # store
        self._tasks = tasks
        self._rewards = rewards
        self._raw_prereqs = raw_prereqs
        self._parsed_prereqs = parsed_prereqs
        self._lock_prereqs = lock

        # stable names for this generation
        self._reward_location_names = [f"Task {i+1} (Reward)" for i in range(n)]
        self._complete_location_names = [f"Task {i+1} (Complete)" for i in range(n)]
        self._reward_item_names = [f"Reward {i+1}" for i in range(n)]
        self._token_item_names = [f"Task Complete {i+1}" for i in range(n)]

        # update id maps for this generation
        self.location_name_to_id = {}
        self.location_name_to_id.update(
            {name: int(BASE_REWARD_LOC_ID + i) for i, name in enumerate(self._reward_location_names)}
        )
        self.location_name_to_id.update(
            {name: int(BASE_COMPLETE_LOC_ID + i) for i, name in enumerate(self._complete_location_names)}
        )

        self.item_name_to_id = {f"Reward {i+1}": int(BASE_ITEM_ID + i) for i in range(n)}
        self.item_name_to_id.update({f"Task Complete {i+1}": int(BASE_TOKEN_ID + i) for i in range(n)})

        # Hard-sanitize IDs to real ints and validate
        for name, lid in list(self.location_name_to_id.items()):
            try:
                self.location_name_to_id[name] = int(lid)
            except Exception as e:
                raise Exception(f"Taskipelago: location id for '{name}' is not an int: {lid!r} ({type(lid)})") from e
            
            # Hard-sanitize IDs to real ints and validate
        for name, lid in list(self.item_name_to_id.items()):
            try:
                self.location_name_to_id[name] = int(lid)
            except Exception as e:
                raise Exception(f"Taskipelago: location id for '{name}' is not an int: {lid!r} ({type(lid)})") from e


    def create_regions(self) -> None:
        menu = Region("Menu", self.player, self.multiworld)
        tasks_region = Region("Tasks", self.player, self.multiworld)

        n = len(self._tasks)
        for i in range(n):
            rname = self._reward_location_names[i]
            cname = self._complete_location_names[i]
            rid = self.location_name_to_id.get(rname)
            cid = self.location_name_to_id.get(cname)

            if not isinstance(rid, int):
                raise Exception(f"Bad reward location id: {rname} -> {rid!r} ({type(rid)})")
            if not isinstance(cid, int):
                raise Exception(f"Bad complete location id: {cname} -> {cid!r} ({type(cid)})")

            tasks_region.locations.append(
                TaskipelagoLocation(self.player, rname, rid, tasks_region)
            )
            tasks_region.locations.append(
                TaskipelagoLocation(self.player, cname, cid, tasks_region)
            )



        self.multiworld.regions += [menu, tasks_region]
        menu.connect(tasks_region)

    def create_items(self) -> None:
        """
        We add N reward items to keep world totals balanced:
          - total locations: 2N (Reward + Complete)
          - complete locations get N locked EVENT items (not in itempool)
          - remaining items needed in itempool: N
        These Reward {i} items will be distributed somewhere in the multiworld.
        """
        # Reward items: classification comes from reward_types
        for i, name in enumerate(self._reward_item_names):
            rt = "junk"
            try:
                if hasattr(self, "_reward_types") and i < len(self._reward_types):
                    rt = (self._reward_types[i] or "junk").lower()
            except Exception:
                rt = "junk"

            cls = ItemClassification.filler
            if rt == "trap":
                cls = ItemClassification.trap
            elif rt == "useful":
                cls = ItemClassification.useful
            elif rt == "progression":
                cls = ItemClassification.progression
            else:
                cls = ItemClassification.filler  # junk -> filler

            # If this reward is used as a prereq anywhere, force it to progression.
            if hasattr(self, "_forced_progression_rewards") and i in self._forced_progression_rewards:
                cls = ItemClassification.progression

            self.multiworld.itempool.append(
                TaskipelagoItem(
                    name,
                    cls,
                    self.item_name_to_id[name],
                    self.player,
                )
            )

        # Completion tokens → progression, lock-placed later
        self._token_items = []
        for name in self._token_item_names:
            self._token_items.append(
                TaskipelagoItem(
                    name,
                    ItemClassification.progression,
                    self.item_name_to_id[name],
                    self.player,
                )
            )

    def set_rules(self) -> None:
        if not self._lock_prereqs:
            return

        n = len(self._tasks)

        for i in range(n):
            token_req_indices = self._parsed_prereqs[i] if i < len(self._parsed_prereqs) else []
            reward_req_indices = (
                self._parsed_reward_prereqs[i]
                if hasattr(self, "_parsed_reward_prereqs") and i < len(self._parsed_reward_prereqs)
                else []
            )

            # ----------------------------
            # A) Lock completing the task
            # ----------------------------
            if token_req_indices or reward_req_indices:
                complete_loc = self.multiworld.get_location(self._complete_location_names[i], self.player)

                required_token_names = tuple(f"Task Complete {j+1}" for j in token_req_indices)
                required_reward_names = tuple(f"Reward {j+1}" for j in reward_req_indices)

                def complete_rule(state, req_tokens=required_token_names, req_rewards=required_reward_names, player=self.player):
                    return all(state.has(name, player) for name in req_tokens) and all(state.has(name, player) for name in req_rewards)

                complete_loc.access_rule = complete_rule

            # ---------------------------------------
            # B) Lock getting the reward behind:
            #    - completing this same task, AND
            #    - (optionally) any prereqs as well
            # ---------------------------------------
            reward_loc = self.multiworld.get_location(self._reward_location_names[i], self.player)
            my_complete_token = f"Task Complete {i+1}"

            required_token_names = tuple(f"Task Complete {j+1}" for j in token_req_indices)
            required_reward_names = tuple(f"Reward {j+1}" for j in reward_req_indices)

            def reward_rule(
                state,
                my_token=my_complete_token,
                req_tokens=required_token_names,
                req_rewards=required_reward_names,
                player=self.player,
            ):
                return (
                    state.has(my_token, player)
                    and all(state.has(name, player) for name in req_tokens)
                    and all(state.has(name, player) for name in req_rewards)
                )

            reward_loc.access_rule = reward_rule

    def generate_basic(self) -> None:
        # Place locked EVENT items on completion locations (code=None => not a network item id).
        n = len(self._tasks)
        for i in range(n):
            complete_loc = self.multiworld.get_location(self._complete_location_names[i], self.player)
            token_name = self._token_item_names[i]  # "Task Complete {i+1}"
            token_item = TaskipelagoItem(
                name=token_name,
                classification=ItemClassification.progression,
                code=self.item_name_to_id[token_name],  # integer
                player=self.player
            )
            complete_loc.place_locked_item(token_item)

        # Completion condition: all REWARD locations checked (meaning all multiworld items were triggered)
        my_reward_locs = [self.multiworld.get_location(name, self.player) for name in self._reward_location_names]
        self.multiworld.completion_condition[self.player] = lambda state: all(
            loc in state.locations_checked for loc in my_reward_locs
        )

    def fill_slot_data(self) -> Dict[str, Any]:
        return {
            "tasks": list(self._tasks),
            "rewards": list(self._rewards),
            "reward_types": list(getattr(self, "_reward_types", [])),

            "task_prereqs": list(self._raw_prereqs),
            "reward_prereqs": list(getattr(self, "_raw_reward_prereqs", [])),
            "lock_prereqs": bool(self._lock_prereqs),

            "death_link_pool": [str(x).strip() for x in self.options.death_link_pool.value if str(x).strip()],
            "death_link_weights": list(getattr(self, "_death_link_weights", [])),
            "death_link_amnesty": int(getattr(self, "_death_link_amnesty", 0)),
            "death_link_enabled": bool(self.options.death_link),

            "base_reward_location_id": BASE_REWARD_LOC_ID,
            "base_complete_location_id": BASE_COMPLETE_LOC_ID,
            "base_item_id": BASE_ITEM_ID,
        }


def launch_client(*args):
    from .client import launch
    launch_subprocess(launch, name="TaskipelagoClient", args=args)


components.append(
    Component(
        "Taskipelago Client",
        func=launch_client,
        component_type=Type.CLIENT,
    )
)
