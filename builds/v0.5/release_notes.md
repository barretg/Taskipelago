# Version 0.5
New apworld version with some QOL stuff and new features added. Thanks for all the support and encouragement on this project!

## Features, Improvements, and Changes
* Added support for tasks having items as prerequisites
* Added support for marking rewards as junk, useful, progression, or trap (Note: any prerequisite rewards will be forced to "progression" during generation)
* Added a notification for which reward was sent upon completing tasks, and to whom
* Last connected server info is now stored and auto-filled when launching
* Added a reset button to the yaml generator
* Server connection info (other than password) now stored between launches, with archipelago.gg as the new default server address
* DeathLink now defaults to off
* Blocking by progression now defaults to on

## Bug Fixes
* Notifications now properly display slot names instead of "Player #"
* Application state storage now properly prefixed with "taskipelago_"
* Fixed DeathLink enabled/disable not showing up in the template YAML