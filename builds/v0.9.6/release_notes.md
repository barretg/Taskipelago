# Taskipelago/Taskipelabingo Version 0.9.6
*The "wow I should probably fix that" update*

## New Features
* "Priority" option added for tasks to be in priority locations
* Added "prev" and "sequential" keywords to task pre-reqs. "prev" will establish a requirement on the previous task in sequence. "sequential" can be used in tasks where count > 1 in order to make each task in the duplicates sequential dependent (i.e. second task in duplicate depends on completing the first, third on second, fourth on third, etc.)

## Bug Fixes
* Fixed a bug with the way goal state is detected
* Added a check to prevent yaml generation when the yaml would have no location available at multiworld start to prevent location starvation
* General clean-up