## I am bad at organization but that's why I made this in the first place
so yeah i'm dumping todos here in a big sloppy mess
what are you gonna do about it?
take that Jira.

## Next major release features
* Hints tab (next to text client, shows hints- mirrors the existing text client's hints tab)
* Deathlink Alert/Sound (Change notification color)
* Deathlink forced task locking others
* Changing group name (region or prog) in YAML Generator updates references to it (prompt user whether they want to or not)
* Integrate find and replace functionality into YAML Generator
* Progressive group color coding same as regions (colors and groups items in inventory tab)
* Add filters to item: each type of item and each progressive group can be selected in a dropdown checkbox list to be shown or hidden (always displays +X Hidden Items at the bottom showing X where X is the number of items hidden by filtering- default is show all so all boxes are checked).
* Diagnose issues with naming- "weapons+*3" doesn't work if "weapons+" is a progressive group.
* Ensure that Auto-fill filler happens on bingo generator to fill slots that are undefined by user
* Small Up/down carrots on left side of tasks/items to move them up/down in the ordering. This should adjust references to them (leave an option to disable this so that moving does not update references)

### High Prio:
* Unify codebase (launch js client under a python wrapper?)

### Medium Prio:
* Taskmaster style ui

### Low Prio:
* Tasklock integration to force all task locks to be in the taskipelago world (generate tasklock yaml with plando logic included, warn user to enable plando items in host.yaml)
* Multi-completion tasks
* Pomodoro-sanity