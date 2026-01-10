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


@dataclass
class TaskipelagoOptions(PerGameCommonOptions):
    death_link: DeathLink
    tasks: Tasks
    rewards: Rewards
    task_prereqs: TaskPrereqs
    lock_prereqs: LockPreqreqs
    death_link_pool: DeathLinkPool
