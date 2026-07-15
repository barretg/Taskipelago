# Taskipelago/Taskipelabingo Version 1.0.0 Pre-release 1
This is the first pre-release build of 1.0! From this point forward I'll be releasing changes as 1.0 pre-release. There may be some instability with these features as I workshop and test them. I will do my best to keep things stable, but likely don't bring this to a long async. Please report any bugs you find.

## New Features
* "Priority" option added for tasks to be in priority locations
* Added "prev" and "sequential" keywords to task pre-reqs. "prev" will establish a requirement on the previous task in sequence. "sequential" can be used in tasks where count > 1 in order to make each task in the duplicates sequential dependent (i.e. second task in duplicate depends on completing the first, third on second, fourth on third, etc.)

## Bug Fixes
* Fixed a bug with the way goal state is detected
* 