# Taskipelago/Taskipelabingo Version 1.2.0
*The big region overhaul (and also clicker game mode)*

## What's new
* New types of item grouping definitions. Now progressive, aesthetic, or random-choice
  * aesthetic groups merely group things aesthetically with no effect on progression or not.
  * random-choice groups randomly choose N or N% as you define items from within the group to be included in the world. No tasks may depend on individual items in these groups since they aren't guaranteed to exist, but depending on the randomized group as a whole or by percentage/count is supported.
  * progressive groups function the same as always
* Regions can now also be randomized to include N or N% of tasks within that region. May optionally also shuffle the order in which such tasks appear.
* Subregions can now be defined within regions that aren't randomized (subregions may be randomized).
* Regions may now depend on items and tasks via the syntax item(expr) and task(expr) where expr is any valid task or item dependency expression
* Tasclickpelago toggle on the yaml generator that enables a bunch of features for building out an idle game because the concept was funny and I thought of a way to do it well.
* Style tab added to the YAML generator so you can recolor the entire application at will while connected to the slot in question. Pretty colors are pretty.
* Added syntax `item(...) and task(...)` to reference an item or task from within task prereqs and item prereqs fields respectively. This also works in the goal requirements, so you can now depend on receiving items to goal. The other benefit here is using OR operators on tasks and items together allowing for some interesting new logic.
* Added a setting for filler items to grant a hint/scout for a random item (See the hint/scout dropdown).
* Fix browser choice to use user's default where possible and never prefer Edge otherwise
* Fix OR not working properly with region dependencies

Note: should be fully backwards compatible with worlds generated from 1.0 onwards. Also Universal Tracker is still incompatible.