from dataclasses import dataclass
from typing import List

from Options import PerGameCommonOptions, DeathLink, OptionList, Toggle

class Tasks(OptionList):
    display_name = "Tasks"
    default: List[str] = []


class Rewards(OptionList):
    display_name = "Rewards"
    default: List[str] = []


class TaskPrereqs(OptionList):
    """
    List to show task preqreqs, entries formatted:
    ""
    "1"             requires 1
    "1, 2, 5"       requires 1, 2, 5
    """
    display_name = "Task Prereqs"
    default: List[str] = []


class LockPreqreqs(Toggle):
    display_name = "Lock Tasks Behind Prereqs"
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
    death_link: DeathLink
    tasks: Tasks
    rewards: Rewards
    task_prereqs: TaskPrereqs
    lock_prereqs: LockPreqreqs
    death_link_pool: DeathLinkPool
    death_link_weights: DeathLinkWeights
    death_link_amnesty: DeathLinkAmnesty