from dataclasses import dataclass
from typing import List

from Options import PerGameCommonOptions, DeathLink, OptionList, Toggle, Range

class Tasks(OptionList):
    display_name = "Tasks"
    default: List[str] = []


class Items(OptionList):
    display_name = "Items"
    default: List[str] = []


class ItemTypes(OptionList):
    """
    Parallel list aligned with items/tasks. Each entry is one of:
        "trap" | "junk" | "useful" | "progression"
    Missing/invalid entries will be treated as "junk".
    """
    display_name = "Item Types"
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

class ItemPrereqs(OptionList):
    """
    NOTE: The application contains a YAML generator that makes it easier to populate this!
    Parallel list aligned with tasks.
    Each entry is a comma-separated list of task indices whose *Item {n}* items are required.
    Examples:
      ""            -> no item prereqs
      "1"           -> requires Item 1
      "1, 2, 5"     -> requires Item 1, Item 2, Item 5
    """
    display_name = "Item Prereqs"
    default: List[str] = []

class LockPreqreqs(Toggle):
    """
    If set to off, the client is able to mark off checks that would normally be out-of-logic. This otherwise does not affect multiworld logic.
    """
    display_name = "Lock Tasks Behind Prereqs"
    default = 1

class HideUnreachableTasks(Toggle):
    """
    If enabled, the client will hide tasks that are currently unreachable due to unsatisfied prereqs.
    """
    display_name = "Hide Unreachable Tasks"
    default = 1

class DeathLink(Toggle):
    """
    If enabled, receiving deathlinks trigger a weighted random deathlink task from the user supplied deathlink task pool.
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

class GoalTasks(OptionList):
    """
    Comma-separated 1-based indices of tasks whose completion triggers game completion.
    If empty, all tasks must be completed (default behaviour).
    """
    display_name = "Goal Tasks"
    default: List[str] = []

class ProgressiveGroups(OptionList):
    """
    List of progressive group name strings (letters, underscores, and hyphens only - no digits).
    Each name defines a set of interchangeable item entries that are treated as a progression counter.
    """
    display_name = "Progressive Groups"
    default: List[str] = []

class ItemProgressiveGroup(OptionList):
    """
    Parallel list aligned with items/tasks.
    Each entry is a progressive group name (from progressive_groups) or empty string.
    Items assigned to a group are interchangeable and always forced to progression classification.
    """
    display_name = "Item Progressive Group"
    default: List[str] = []

class Regions(OptionList):
    """
    List of region name strings (letters, underscores, and hyphens only - no digits).
    Each name defines a set of tasks that can be used as percentage-based completion prerequisites.
    """
    display_name = "Regions"
    default: List[str] = []

class RegionDefaultPcts(OptionList):
    """
    Parallel list aligned with regions.
    Each entry is the default completion percentage (0-100) required when a task prereq
    references the region by name without an explicit percentage.
    Missing or invalid entries default to 100.
    """
    display_name = "Region Default Percentages"
    default: List[str] = []

class TaskRegion(OptionList):
    """
    Parallel list aligned with tasks.
    Each entry is a region name (from regions) or empty string.
    Tasks assigned to a region can be used as region-based completion prerequisites.
    A task cannot depend on its own region.
    """
    display_name = "Task Region"
    default: List[str] = []


class BingoMode(Toggle):
    """If enabled, this slot is treated as a bingo board by the client."""
    display_name = "Bingo Mode"
    default = 0

class BingoDimensionX(Range):
    """Number of columns in the bingo board (only used when bingo_mode is on)."""
    display_name = "Bingo Dimension X (Columns)"
    range_start = 1
    range_end = 20
    default = 5

class BingoDimensionY(Range):
    """Number of rows in the bingo board (only used when bingo_mode is on)."""
    display_name = "Bingo Dimension Y (Rows)"
    range_start = 1
    range_end = 20
    default = 5

class Bingoal(Range):
    """Number of bingos required to complete the goal."""
    display_name = "Bingoal (bingos required)"
    range_start = 1
    range_end = 100
    default = 3


@dataclass
class TaskipelagoOptions(PerGameCommonOptions):
    tasks: Tasks
    items: Items
    item_types: ItemTypes
    task_prereqs: TaskPrereqs
    item_prereqs: ItemPrereqs
    lock_prereqs: LockPreqreqs
    goal_tasks: GoalTasks
    hide_unreachable_tasks: HideUnreachableTasks
    death_link: DeathLink
    death_link_pool: DeathLinkPool
    death_link_weights: DeathLinkWeights
    death_link_amnesty: DeathLinkAmnesty
    progressive_groups: ProgressiveGroups
    item_progressive_group: ItemProgressiveGroup
    regions: Regions
    region_default_pcts: RegionDefaultPcts
    task_region: TaskRegion
    bingo_mode: BingoMode
    bingo_dimension_x: BingoDimensionX
    bingo_dimension_y: BingoDimensionY
    bingoal: Bingoal