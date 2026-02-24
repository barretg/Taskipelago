from dataclasses import dataclass
from typing import List

from Options import PerGameCommonOptions, DeathLink, OptionList, Toggle, Range

class Tasks(OptionList):
    display_name = "Tasks"
    default: List[str] = []


class Rewards(OptionList):
    display_name = "Rewards"
    default: List[str] = []


class RewardTypes(OptionList):
    """
    Parallel list aligned with rewards/tasks. Each entry  is one of:
        "trap" | "junk" | "useful" | "progression"
    Missing/invalid entries will be treated as "junk".
    """
    display_name = "Reward Types"
    default: List[str] = []


class TaskPrereqs(OptionList):
    """
    NOTE: The application contains a YAML generator that makes it easier to populate this!
    List to show task preqreqs, entries formatted:
    ""
    "1"             requires 1
    "1, 2, 5"       requires 1, 2, 5
    """
    display_name = "Task Prereqs"
    default: List[str] = []

class RewardPrereqs(OptionList):
    """
    NOTE: The application contains a YAML generator that makes it easier to populate this!
    Parallel list aligned with tasks.
    Each entry is a comma-separated list of task indices whose *Reward {n}* items are required.
    Examples:
      ""            -> no reward prereqs
      "1"           -> requires Reward 1
      "1, 2, 5"     -> requires Reward 1, Reward 2, Reward 5
    """
    display_name = "Reward Prereqs"
    default: List[str] = []

class LockPreqreqs(Toggle):
    display_name = "Lock Tasks Behind Prereqs"
    default = 1

class DeathLink(Toggle):
    """
    If enabled, receiving certain rewards can trigger DeathLink.
    """
    display_name = "DeathLink"
    default = 0

class DeathLinkPool(OptionList):
    display_name = "DeathLink Task Pool"
    default: List[str] = []


class DeathLinkWeights(OptionList):
    """
    Parallel list aligned with death_link_pool, each entry is a number as text.
    Missing entries default to 1.
    """
    display_name = "DeathLink Task Weights"
    default: List[str] = []


class DeathLinkAmnesty(Range):
    display_name = "DeathLink Amnesty (ignore X before triggering 1)"
    range_start = 0
    range_end = 999
    default = 0


@dataclass
class TaskipelagoOptions(PerGameCommonOptions):
    tasks: Tasks
    rewards: Rewards
    reward_types: RewardTypes
    task_prereqs: TaskPrereqs
    reward_prereqs: RewardPrereqs
    lock_prereqs: LockPreqreqs
    death_link: DeathLink
    death_link_pool: DeathLinkPool
    death_link_weights: DeathLinkWeights
    death_link_amnesty: DeathLinkAmnesty