from dataclasses import dataclass
from typing import List

from Options import PerGameCommonOptions, DeathLink, OptionList, Toggle, Range

class Tasks(OptionList):
    """
    NOTE: The Taskipelago client application contains a YAML builder that is the recommended way to configure this. Editing YAML manually is error-prone.
    List of task names. Each entry is a string.
    """
    display_name = "Tasks"
    default: List[str] = []


class Items(OptionList):
    """
    NOTE: The Taskipelago client application contains a YAML builder that is the recommended way to configure this. Editing YAML manually is error-prone.
    Parallel list aligned with tasks. Each entry is the name of the reward item for that task.
    """
    display_name = "Items"
    default: List[str] = []


class ItemTypes(OptionList):
    """
    NOTE: The Taskipelago client application contains a YAML builder that is the recommended way to configure this. Editing YAML manually is error-prone.
    Parallel list aligned with items/tasks. Each entry is one of:
        "trap" | "junk" | "useful" | "progression"
    Missing/invalid entries will be treated as "junk".
    """
    display_name = "Item Types"
    default: List[str] = []


class TaskPrereqs(OptionList):
    """
    NOTE: The Taskipelago client application contains a YAML builder that is the recommended way to configure this. Editing YAML manually is error-prone.
    Parallel list aligned with tasks. Each entry is a boolean expression of 1-based task
    indices that must be completed before this task is accessible.
    Supports &&, ||, (), quoted task names (e.g. "My Task"), and region references
    (e.g. 'chores' for the region's default percentage, 'chores-75' for exactly 75%,
    'chores*5' for an absolute count of 5 tasks).
    Example: '1 && (2 || 3)' requires task 1 and either task 2 or task 3.
    """
    display_name = "Task Prereqs"
    default: List[str] = []


class ItemPrereqs(OptionList):
    """
    NOTE: The Taskipelago client application contains a YAML builder that is the recommended way to configure this. Editing YAML manually is error-prone.
    Parallel list aligned with tasks. Each entry is a boolean expression of 1-based item
    indices (or progressive group names) that must be received before this task is accessible.
    Supports &&, ||, (), and quoted item names (e.g. "My Item").
    Example: '1 && (2 || 3)' requires item 1 and either item 2 or item 3.
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
    """
    NOTE: The Taskipelago client application contains a YAML builder that is the recommended way to configure this. Editing YAML manually is error-prone.
    List of task name strings. When a DeathLink is received, a task is randomly chosen from this pool.
    """
    display_name = "DeathLink Task Pool"
    default: List[str] = []


class DeathLinkWeights(OptionList):
    """
    NOTE: The Taskipelago client application contains a YAML builder that is the recommended way to configure this. Editing YAML manually is error-prone.
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


class TaskPriority(OptionList):
    """
    NOTE: The Taskipelago client application contains a YAML builder that is the recommended way to configure this. Editing YAML manually is error-prone.
    Parallel list aligned with tasks. Each entry is 'true' or 'false' (default 'false').
    Tasks marked 'true' have their reward location added to Archipelago's built-in
    priority_locations, making it more likely to receive a progression or otherwise
    important item instead of junk/filler.
    """
    display_name = "Task Priority"
    default: List[str] = []


class GoalTasks(OptionList):
    """
    NOTE: The Taskipelago client application contains a YAML builder that is the recommended way to configure this. Editing YAML manually is error-prone.
    Boolean expression of 1-based task indices whose completion triggers game completion.
    Uses the same syntax as task_prereqs: &&, ||, (), quoted task names (e.g. "My Task"),
    and region references (e.g. 'chores', 'chores-75', 'chores*5').
    If empty, all tasks must be completed (default behaviour).
    """
    display_name = "Goal Tasks"
    default: List[str] = []


class ProgressiveGroups(OptionList):
    """
    NOTE: The Taskipelago client application contains a YAML builder that is the recommended way to configure this. Editing YAML manually is error-prone.
    List of progressive group name strings (letters, underscores, and hyphens only - no digits).
    Each name defines a set of interchangeable item entries that are treated as a progression counter.
    """
    display_name = "Progressive Groups"
    default: List[str] = []


class ItemProgressiveGroup(OptionList):
    """
    NOTE: The Taskipelago client application contains a YAML builder that is the recommended way to configure this. Editing YAML manually is error-prone.
    Parallel list aligned with items/tasks.
    Each entry is a progressive group name (from progressive_groups) or empty string.
    Items assigned to a group are interchangeable and always forced to progression classification.
    """
    display_name = "Item Progressive Group"
    default: List[str] = []


class Regions(OptionList):
    """
    NOTE: The Taskipelago client application contains a YAML builder that is the recommended way to configure this. Editing YAML manually is error-prone.
    List of region name strings (letters, underscores, and hyphens only - no digits).
    Each name defines a set of tasks that can be used as percentage-based completion prerequisites.
    """
    display_name = "Regions"
    default: List[str] = []


class RegionDefaultPcts(OptionList):
    """
    NOTE: The Taskipelago client application contains a YAML builder that is the recommended way to configure this. Editing YAML manually is error-prone.
    Parallel list aligned with regions.
    Each entry is the default completion percentage (0-100) required when a task prereq
    references the region by name without an explicit percentage.
    Missing or invalid entries default to 100.
    """
    display_name = "Region Default Percentages"
    default: List[str] = []


class RegionColors(OptionList):
    """
    NOTE: The Taskipelago client application contains a YAML builder that is the recommended way to configure this. Editing YAML manually is error-prone.
    Parallel list aligned with regions.
    Each entry is a hex color string (e.g. '#e05c5c') for that region's color coding.
    Missing or empty entries will be treated as no color.
    """
    display_name = "Region Colors"
    default: List[str] = []


class TaskRegion(OptionList):
    """
    NOTE: The Taskipelago client application contains a YAML builder that is the recommended way to configure this. Editing YAML manually is error-prone.
    Parallel list aligned with tasks.
    Each entry is a region name (from regions) or empty string.
    Tasks assigned to a region can be used as region-based completion prerequisites.
    A task cannot depend on its own region.
    """
    display_name = "Task Region"
    default: List[str] = []


class ItemConsumable(OptionList):
    """
    NOTE: The Taskipelago client application contains a YAML builder that is the recommended way to configure this. Editing YAML manually is error-prone.
    Parallel list aligned with items.
    Each entry is 'true' or 'false' (default 'false').
    Consumable items can be spent as currency to purchase (unlock) tasks that have a task_cost.
    All copies of a consumable item with the same name are interchangeable as currency.
    """
    display_name = "Item Consumable"
    default: List[str] = []


class ItemCount(OptionList):
    """
    NOTE: The Taskipelago client application contains a YAML builder that is the recommended way to configure this. Editing YAML manually is error-prone.
    Parallel list aligned with items.
    Each entry is a positive integer (default 1).
    The item will be duplicated that many times in the final output as separate pool entries.
    On YAML import, consecutive duplicate item rows are crunched back into a single row with a higher count.
    """
    display_name = "Item Count"
    default: List[str] = []


class TaskCount(OptionList):
    """
    NOTE: The Taskipelago client application contains a YAML builder that is the recommended way to configure this. Editing YAML manually is error-prone.
    Parallel list aligned with tasks.
    Each entry is a positive integer (default 1).
    The task will be duplicated that many times in the final output with identical configuration.
    A prereq referencing a task with count > 1 requires ALL copies to be completed.
    On YAML import, consecutive duplicate task rows are crunched back into a single row with a higher count.
    """
    display_name = "Task Count"
    default: List[str] = []


class TaskCost(OptionList):
    """
    NOTE: The Taskipelago client application contains a YAML builder that is the recommended way to configure this. Editing YAML manually is error-prone.
    Parallel list aligned with tasks.
    Each entry is a cost expression. The player must spend the specified consumable items
    (from item_consumable) before being allowed to complete this task.
    Format: '"ItemName"-N' requires spending N of the consumable item named ItemName.
    Use && for AND (all costs required), || for OR (player picks one branch), () for grouping.
    Item indices (1-based) may also be used in place of quoted names.
    Example: '"Gold"-3 && "Silver"-2'  costs 3 Gold and 2 Silver.
    Example: '"Gold"-5 || "Silver"-10'  player chooses which currency to spend.
    Leave empty for no cost.
    An error is raised at generation time if total consumable supply is insufficient to
    cover all task costs.
    """
    display_name = "Task Cost"
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
    item_consumable: ItemConsumable
    item_count: ItemCount
    task_count: TaskCount
    task_cost: TaskCost
    task_prereqs: TaskPrereqs
    item_prereqs: ItemPrereqs
    lock_prereqs: LockPreqreqs
    task_priority: TaskPriority
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
    region_colors: RegionColors
    task_region: TaskRegion
    bingo_mode: BingoMode
    bingo_dimension_x: BingoDimensionX
    bingo_dimension_y: BingoDimensionY
    bingoal: Bingoal
