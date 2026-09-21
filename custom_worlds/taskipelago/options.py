from dataclasses import dataclass
from typing import List

from Options import PerGameCommonOptions, OptionList, Toggle, Range, Choice
from Options import DeathLink as APDeathLink

MAX_TASK_DESCRIPTION_LEN = 100

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
    Two reserved keywords are also available here (not in item_prereqs or goal_tasks):
    'prev' resolves to the task immediately before this one. 'sequential', combined
    with a task's count field, makes every duplicate copy after the first depend on
    the copy before it (e.g. 'sequential && "Chore"' with count 4 leaves the first
    copy depending only on "Chore", while the rest also require the prior copy).
    'prev' and 'sequential' cannot be used as region or progressive group names.
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


class DeathLink(APDeathLink):
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


class DeathLinkLockTasks(Toggle):
    """
    When enabled, the client locks every other task (completions, purchases and consumable
    adjustments) while a DeathLink task card is pending, until all DeathLink cards are completed.
    DeathLink task cards appear whenever DeathLink is enabled; this only adds the lock.
    """
    display_name = "Lock Tasks Until DeathLink Tasks Are Done"


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
    List of progressive group name strings (no digits, whitespace, quotes, parentheses, commas, && or ||).
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
    List of region name strings (no digits, whitespace, quotes, parentheses, commas, && or ||).
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


class ProgressiveGroupColors(OptionList):
    """
    NOTE: The Taskipelago client application contains a YAML builder that is the recommended way to configure this. Editing YAML manually is error-prone.
    Parallel list aligned with progressive_groups.
    Each entry is a hex color string (e.g. '#e05c5c') used to color code that group in the client's Items tab.
    Missing or empty entries will be treated as no color.
    """
    display_name = "Progressive Group Colors"
    default: List[str] = []


class StyleColors(OptionList):
    """
    NOTE: The Taskipelago client application contains a YAML builder that is the recommended way to configure this. Editing YAML manually is error-prone.
    Client color scheme for this slot. Each entry is "key:#rrggbb", for example
    'bg:#1e1e1e'. The client applies these colors while it is connected to this
    slot and returns to its default color scheme on disconnect.
    Recognized keys: bg, panel, field, fg, muted, desc, border, tab-bg,
    tab-active, btn-bg, btn-hover, warning, bingo-line, bingo-done.
    Unknown keys and malformed entries are ignored.
    """
    display_name = "Style Colors"
    default: List[str] = []


class RegionPrereqs(OptionList):
    """
    NOTE: The Taskipelago client application contains a YAML builder that is the recommended way to configure this. Editing YAML manually is error-prone.
    Parallel list aligned with regions.
    Each entry is a boolean expression, using the same syntax as Task Prereqs' region
    references, that gates an entire region on OTHER regions being completed:
        otherregion       -> that region's default percentage of tasks must be completed
        otherregion-75    -> exactly 75% of that region's tasks must be completed
        otherregion*5     -> exactly 5 tasks in that region must be completed
    Combine with &&, ||, and ().
    A specific task or item can also gate the region by wrapping it in task( ... )
    or item( ... ):
        task(3)           -> task 3 must be completed
        task("Do dishes") -> that task must be completed (quoted name)
        task(1 || 2)      -> task 1 or task 2 must be completed
        task(caves-50)    -> 50% of the caves region must be completed
        item(4)           -> item 4 must have been received
        item("Blue Key")  -> that item must have been received (quoted name)
        item(keys*3)      -> 3 items from progressive group "keys" (count mode only;
                             the ordering form "keys" on its own is not allowed here)
    Inside task( ... ) any task prereq expression is valid except 'prev' and
    'sequential'; inside item( ... ) any item prereq expression is valid except item
    copy counts. task( ... ) may not reference a task in the region it gates, may not
    reference a task in a randomized region, and item( ... ) may not name an
    individual item inside a random-choice progressive group or a consumable
    currency item (a currency is spent on task costs, so it cannot gate a region).
    A region cannot depend on itself, and dependency cycles between regions are not
    allowed. Missing or empty entries mean the region has no additional requirement
    of its own.
    """
    display_name = "Region Prereqs"
    default: List[str] = []


class RegionParent(OptionList):
    """
    NOTE: The Taskipelago client application contains a YAML builder that is the recommended way to configure this. Editing YAML manually is error-prone.
    Parallel list aligned with regions.
    Each entry names another region that this region is a subregion of, or is empty
    (the default) for a top-level region. A subregion behaves exactly like any other
    region for tasks, prereqs, randomization and colors; the only difference is that
    the client's region progress list hides it until its parent row is expanded, and
    the parent's bar also counts its subregions' tasks.
    A subregion always depends on its parent implicitly: the parent's bare region
    reference (its default percentage of tasks) is added to the subregion's own
    region_prereqs entry, so none of the subregion's tasks unlock until the parent
    is that far along. A parent with no tasks of its own has nothing to complete, so
    its subregions inherit the parent's region_prereqs entry instead.
    Nesting is one level deep: a region named here as a parent may not itself have a
    parent. A randomized region (region_random_pick) may not be a parent, but a
    subregion may be randomized.
    """
    display_name = "Region Parent"
    default: List[str] = []


class RegionRandomPick(OptionList):
    """
    NOTE: The Taskipelago client application contains a YAML builder that is the recommended way to configure this. Editing YAML manually is error-prone.
    Parallel list aligned with regions.
    Empty means the region is not randomized. 'N' keeps N of the region's tasks per seed;
    'N%' keeps N percent (rounded up, minimum 1). Duplicated tasks (count field) count as
    separate candidates. Unkept tasks are removed from the seed entirely.
    Individual tasks inside a randomized region cannot be referenced by task or region
    prereqs (by index, quoted name, prev, or sequential); refer to the region as a whole.
    goal_tasks may name individual tasks; one way to satisfy the goal is always kept.
    Missing or empty entries mean not randomized.
    """
    display_name = "Region Random Pick"
    default: List[str] = []


class RegionRandomOrder(OptionList):
    """
    NOTE: The Taskipelago client application contains a YAML builder that is the recommended way to configure this. Editing YAML manually is error-prone.
    Parallel list aligned with regions. "true" shuffles the order of the tasks kept from
    that randomized region; anything else (including missing or empty entries) keeps them
    in their original YAML order. Only used by regions that have a region_random_pick.
    """
    display_name = "Region Random Order"
    default: List[str] = []


class GroupTypes(OptionList):
    """
    NOTE: The Taskipelago client application contains a YAML builder that is the recommended way to configure this. Editing YAML manually is error-prone.
    Parallel list aligned with progressive_groups (item groups). Each entry is one of:
        "progressive"   -> interchangeable progression counter (default, legacy behavior)
        "random-choice" -> keep only group_random_pick items per seed; kept items are distinct
        "aesthetic"     -> color and inventory grouping only; items are distinct
    Missing or invalid entries are treated as "progressive".
    """
    display_name = "Group Types"
    default: List[str] = []


class GroupRandomPick(OptionList):
    """
    NOTE: The Taskipelago client application contains a YAML builder that is the recommended way to configure this. Editing YAML manually is error-prone.
    Parallel list aligned with progressive_groups. Only used by random-choice groups.
    'N' keeps N of the group's items per seed; 'N%' keeps N percent (rounded up, minimum 1).
    Individual items in a random-choice group cannot be referenced by item prereqs.
    """
    display_name = "Group Random Pick"
    default: List[str] = []


class GroupDefaultPcts(OptionList):
    """
    NOTE: The Taskipelago client application contains a YAML builder that is the recommended way to configure this. Editing YAML manually is error-prone.
    Parallel list aligned with progressive_groups.
    Each entry is the percentage (0-100) required when an item prereq references the group
    by bare name. Blank keeps the legacy progressive behavior (next unused position) for
    progressive groups and means 100 for random-choice and aesthetic groups.
    """
    display_name = "Group Default Percentages"
    default: List[str] = []


class TaskDescriptions(OptionList):
    """
    NOTE: The Taskipelago client application contains a YAML builder that is the recommended way to configure this. Editing YAML manually is error-prone.
    Parallel list aligned with tasks. Each entry is an optional flavor-text description
    (max 100 characters) shown under the task name in the client. Leave empty for none.
    """
    display_name = "Task Descriptions"
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


class ItemFillers(OptionList):
    """
    NOTE: The Taskipelago client application contains a YAML builder that is the recommended way to configure this. Editing YAML manually is error-prone.
    Parallel list aligned with items.
    Each entry is 'true' or 'false' (default 'false').
    Items marked as filler are exempt from the duplicate item name check, since filler
    flavor text is expected to repeat across items.
    """
    display_name = "Item Fillers"
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
    Format: '"ItemName"*N' requires spending N of the consumable item named ItemName.
    A bare '"ItemName"' with no suffix costs 1.
    Use && for AND (all costs required), || for OR (player picks one branch), () for grouping.
    Item indices (1-based) may also be used in place of quoted names ('4*3').
    Example: '"Gold"*3 && "Silver"*2'  costs 3 Gold and 2 Silver.
    Example: '"Gold"*5 || "Silver"*10'  player chooses which currency to spend.
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


# ---------------------------------------------------------------------------
# Tasclickpelago (clicker mode)
# ---------------------------------------------------------------------------
# Every option below is optional and defaults to today's behavior. The apworld
# runs no clicker simulation and draws no extra randomness: it validates these
# lists and forwards them in slot_data, and the client does all the accrual.
#
# Numeric fields accept a small arithmetic expression (integers, decimals,
# + - * /, parentheses) over five constants:
#     N_TASKS             total tasks in the slot (fixed for the seed)
#     N_TASKS_UNLOCKED    tasks currently unlocked, including completed ones
#     N_TASKS_LOCKED      N_TASKS - N_TASKS_UNLOCKED
#     N_TASKS_COMPLETED   tasks completed so far
#     CPS                 the current click value, after click power and the
#                         click multiplier
# The last four change during play and are therefore legal only in the clicker
# fields, never in prereq, goal or cost expressions. CPS is additionally
# rejected in item_click_power and item_click_mult, which are what define it.
# In a production rate, CPS binds to the click value of the task that rate is
# aimed at, since click power is itself per target.
#
# Every grant but "unlock only" takes a target: item_production,
# item_click_power, item_production_mult, item_click_mult and item_offline_mult
# all use the '<target>-<value>' grammar described under item_production. The
# three that were slot-wide before still accept a bare value, which means '*'.


class ClickerMode(Toggle):
    """
    If enabled, this slot is treated as an idle/clicker game by the client
    (Tasclickpelago). Each task needs a number of activations instead of one
    "Complete" press; activations come from clicking and from production
    granted by items received from the multiworld.
    Cannot be combined with bingo_mode.
    """
    display_name = "Clicker Mode"
    default = 0


class TaskActivations(OptionList):
    """
    NOTE: The Taskipelago client application contains a YAML builder that is the recommended way to configure this. Editing YAML manually is error-prone.
    Parallel list aligned with tasks. Number of activations required to complete
    each task in clicker mode. Blank, missing or '1' means a single click.
    May be an arithmetic expression over N_TASKS only (the requirement has to be
    stable for the whole seed); the result is rounded up with a minimum of 1.
    Example: '100', '10 * N_TASKS'.
    """
    display_name = "Task Activations"
    default: List[str] = []


class TaskManual(OptionList):
    """
    NOTE: The Taskipelago client application contains a YAML builder that is the recommended way to configure this. Editing YAML manually is error-prone.
    Parallel list aligned with tasks. 'true' marks a task as a normal (manual)
    task even in clicker mode: it is never clickable, never receives production,
    and the client shows it as an ordinary task row with a Complete button below
    the clicker cards. 'false' or blank (the default) leaves it a clicker task.
    A task is also manual when its region is marked in region_manual.
    """
    display_name = "Task Manual"
    default: List[str] = []


class TaskAutoComplete(OptionList):
    """
    NOTE: The Taskipelago client application contains a YAML builder that is the recommended way to configure this. Editing YAML manually is error-prone.
    Parallel list aligned with tasks. 'true' makes a clicker task complete itself
    the moment it reaches its activations. 'false' or blank (the default) leaves
    it waiting at full progress until the player presses its Complete button.
    Ignored for manual tasks.
    """
    display_name = "Task Auto Complete"
    default: List[str] = []


class RegionManual(OptionList):
    """
    NOTE: The Taskipelago client application contains a YAML builder that is the recommended way to configure this. Editing YAML manually is error-prone.
    Parallel list aligned with regions. 'true' makes every task in that region a
    manual (non-clicker) task, as if each were marked in task_manual. 'false' or
    blank (the default) leaves the region's tasks clickable.
    """
    display_name = "Region Manual"
    default: List[str] = []


class ItemProduction(OptionList):
    """
    NOTE: The Taskipelago client application contains a YAML builder that is the recommended way to configure this. Editing YAML manually is error-prone.
    Parallel list aligned with items. Production granted by each item, in
    activations per second, as '<target>-<rate>' pairs joined with '&&'.
    Targets:
        "Bake Bread"-1.5    a single task, by quoted name
        3-1.5               a single task, by 1-based task index
        Kitchen-0.5         every task in a region, by bare name
        *-0.1               every clicker task
    Every received copy of the item adds its rate, so a progressive group stacks
    naturally. Rates are positive numeric expressions and may use all four
    task-count constants. Leave blank for an item that grants no production.
    Example: '"Bake Bread"-1 && Kitchen-0.25'.
    """
    display_name = "Item Production"
    default: List[str] = []


class ItemClickPower(OptionList):
    """
    NOTE: The Taskipelago client application contains a YAML builder that is the recommended way to configure this. Editing YAML manually is error-prone.
    Parallel list aligned with items. Activations added to the value of one click
    per received copy of the item, for the targeted tasks. Uses the same
    '<target>-<value>' grammar as item_production ("Bake Bread"-2, 3-2,
    Kitchen-2, *-2, joined with &&), so click power is adjustable per target.
    A bare value with no target (the pre-targeting spelling) means '*'.
    Values are non-negative numeric expressions; blank is 0.
    A task's click value is (1 + sum of the click power aimed at it)
    * product of the click multipliers aimed at it.
    """
    display_name = "Item Click Power"
    default: List[str] = []


class ItemProductionMult(OptionList):
    """
    NOTE: The Taskipelago client application contains a YAML builder that is the recommended way to configure this. Editing YAML manually is error-prone.
    Parallel list aligned with items. Each received copy multiplies the production
    of the targeted tasks (never click power); copies stack multiplicatively.
    Uses the same '<target>-<value>' grammar as item_production; a bare value
    with no target (the pre-targeting spelling) means '*', i.e. all production.
    Values are positive numeric expressions, rounded to 2 decimal places when
    plain numbers. Values below 1 are legal (a "curse" item); 0 and negatives
    are an error. Blank means the item is not a production multiplier.
    """
    display_name = "Item Production Multiplier"
    default: List[str] = []


class ItemClickMult(OptionList):
    """
    NOTE: The Taskipelago client application contains a YAML builder that is the recommended way to configure this. Editing YAML manually is error-prone.
    Parallel list aligned with items. Each received copy multiplies the click
    value of the targeted tasks only (never production); copies stack
    multiplicatively. Same '<target>-<value>' grammar and rules as
    item_production_mult, so the multiplier can be aimed at one task, a region
    or '*'.
    """
    display_name = "Item Click Multiplier"
    default: List[str] = []


class ItemOfflineMult(OptionList):
    """
    NOTE: The Taskipelago client application contains a YAML builder that is the recommended way to configure this. Editing YAML manually is error-prone.
    Parallel list aligned with items. Multiplies the offline (away from keyboard)
    rate for the targeted tasks. Uses the same '<target>-<value>' grammar as
    item_production, including single tasks, bare region names and *. Each copy
    multiplies, so copies stack. Blank means no offline multiplier.
    """
    display_name = "Item Offline Multiplier"
    default: List[str] = []


class RegionDistributedProduction(OptionList):
    """
    NOTE: The Taskipelago client application contains a YAML builder that is the recommended way to configure this. Editing YAML manually is error-prone.
    Parallel list aligned with regions. 'true' splits a region-targeted production
    rate evenly among that region's eligible (unlocked, incomplete) tasks, keeping
    the region's total throughput constant. 'false' (the default) applies the rate
    in full to each eligible task.
    """
    display_name = "Region Distributed Production"
    default: List[str] = []


class ClickerDistributeGlobal(Toggle):
    """
    The same choice as region_distributed_production, for production aimed at '*'
    (every clicker task), which belongs to no region.
    """
    display_name = "Clicker Distribute Global Production"
    default = 0


class ClickerOfflineProgress(Toggle):
    """
    If disabled, no production accrues while the client is closed: no catch-up, no
    timestamp accrual, and the client hides the offline row. This is the hard off
    switch; the other offline options are then unused.
    """
    display_name = "Clicker Offline Progress"
    default = 1


class ClickerOfflineRate(OptionList):
    """
    NOTE: The Taskipelago client application contains a YAML builder that is the recommended way to configure this. Editing YAML manually is error-prone.
    A single entry: the fraction of live production that accrues while away.
    '1' (the default) is parity with being at the keyboard, '0.25' is a quarter
    rate, '0' is live-only, and values above 1 are legal. May be a numeric
    expression using all four task-count constants.
    """
    display_name = "Clicker Offline Rate"
    default: List[str] = []


class RegionOfflineRate(OptionList):
    """
    NOTE: The Taskipelago client application contains a YAML builder that is the recommended way to configure this. Editing YAML manually is error-prone.
    Parallel list aligned with regions. Overrides clicker_offline_rate for that
    region; blank inherits the global rate.
    """
    display_name = "Region Offline Rate"
    default: List[str] = []


class ClickerOfflineCapHours(Range):
    """
    Maximum number of elapsed hours a single offline catch-up may claim. 0 disables
    catch-up while leaving the rest of the offline configuration in place.
    """
    display_name = "Clicker Offline Cap (hours)"
    range_start = 0
    range_end = 168
    default = 8


class TaskRewardPreviews(Choice):
    """
    Controls whether the client shows a preview of a task's reward (item name and recipient
    player) once that task becomes available to complete (prereqs satisfied and, if it has a
    cost, the cost already paid).

    'No Previews' (default) shows nothing and makes no network calls - fully backwards compatible.
    'Scout Previews' shows the reward using data already resolved locally at generation time,
    with no additional network traffic.
    'Hint Previews' does the same, but also sends a real Archipelago hint for that task's reward
    location the first time it becomes available each session (equivalent to typing !hint).
    This is a real hint subject to the server's hint point economy and is visible to other players.
    """
    display_name = "Task Reward Previews"
    option_no_previews = 0
    option_scout_previews = 1
    option_hint_previews = 2
    default = 0


class TaskRewardPreviewsPurchasableOnly(Toggle):
    """
    When on, Task Reward Previews (scout or hint) only apply to tasks that have a cost.
    A purchasable task shows its preview once its purchase is in logic.
    """
    display_name = "Task Reward Previews Purchasable Only"


@dataclass
class TaskipelagoOptions(PerGameCommonOptions):
    tasks: Tasks
    items: Items
    item_types: ItemTypes
    item_fillers: ItemFillers
    item_consumable: ItemConsumable
    item_count: ItemCount
    task_count: TaskCount
    task_cost: TaskCost
    task_prereqs: TaskPrereqs
    task_description: TaskDescriptions
    item_prereqs: ItemPrereqs
    lock_prereqs: LockPreqreqs
    task_priority: TaskPriority
    goal_tasks: GoalTasks
    hide_unreachable_tasks: HideUnreachableTasks
    death_link: DeathLink
    death_link_pool: DeathLinkPool
    death_link_weights: DeathLinkWeights
    death_link_amnesty: DeathLinkAmnesty
    death_link_lock_tasks: DeathLinkLockTasks
    progressive_groups: ProgressiveGroups
    item_progressive_group: ItemProgressiveGroup
    progressive_group_colors: ProgressiveGroupColors
    group_types: GroupTypes
    group_random_pick: GroupRandomPick
    group_default_pcts: GroupDefaultPcts
    regions: Regions
    region_default_pcts: RegionDefaultPcts
    region_colors: RegionColors
    region_prereqs: RegionPrereqs
    region_parent: RegionParent
    region_random_pick: RegionRandomPick
    region_random_order: RegionRandomOrder
    task_region: TaskRegion
    bingo_mode: BingoMode
    bingo_dimension_x: BingoDimensionX
    bingo_dimension_y: BingoDimensionY
    bingoal: Bingoal
    clicker_mode: ClickerMode
    task_activations: TaskActivations
    task_manual: TaskManual
    task_auto_complete: TaskAutoComplete
    region_manual: RegionManual
    item_production: ItemProduction
    item_click_power: ItemClickPower
    item_production_mult: ItemProductionMult
    item_click_mult: ItemClickMult
    item_offline_mult: ItemOfflineMult
    region_distributed_production: RegionDistributedProduction
    clicker_distribute_global: ClickerDistributeGlobal
    clicker_offline_progress: ClickerOfflineProgress
    clicker_offline_rate: ClickerOfflineRate
    region_offline_rate: RegionOfflineRate
    clicker_offline_cap_hours: ClickerOfflineCapHours
    task_reward_previews: TaskRewardPreviews
    task_reward_previews_purchasable_only: TaskRewardPreviewsPurchasableOnly
    style_colors: StyleColors
