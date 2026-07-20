# Taskipelago/Taskipelabingo Version 0.9.6

## New Features
* "Priority" option added for tasks to be in priority locations
* Added "prev" and "sequential" keywords to task pre-reqs. "prev" will establish a requirement on the previous task in sequence. "sequential" can be used in tasks where count > 1 in order to make each task in the duplicates sequential dependent (i.e. second task in duplicate depends on completing the first, third on second, fourth on third, etc.)
* Task location names now display in non-taskipelago clients

## Bug Fixes
* Fixed a bug with the way goal state is detected
* Added a check to prevent yaml generation when the yaml would have no location available at multiworld start to prevent location starvation
* Fixed another filler generation bug
* General clean-up

## Known Issues
* Universal Tracker is unhappy with the structure of the datapackage because of the dynamic nature of Taskipelago's location names. This is aimed to be resolved in a future patch.