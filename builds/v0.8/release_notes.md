# Taskipelago Version 0.8
### Now with 100% more progressive items!
This release is fully backwards compatible with v0.7 multiworlds.

## Features, Improvements, and Changes
* Added the abillity to define "progressive groups" which denote progressive items. These can be listed in the reward pre-reqs.
* Added option to hide inaccessible tasks (I think it was missed last release because I forgot to rebuild the apworld after merging it, lol). Thanks again to [@Dinknumberone](https://www.github.com/Dinknumberone).
* Added some tooltips to YAML generator.
* Added toggle to enforce progression locally after connecting even when "In logic only" (lock_prereqs in YAML) is marked as false
* Added toggle to show hidden tasks, spoiler free (Displays as just "Locked Task")

## Looking forward: Planned features for v1.0
As we are approaching the point where I feel comfortable moving out of beta and calling it a stable 1.0 build, I want to include my future plans here, partially for my own organization, but also with the intent of receiving feedback on the ideas and suggestions for things not listed. Please provide feedback in the discussion for this release, or in the Taskipelago thread in the Archipelago discord server's future-game-design forum. Feel free to @xlander36 on that to ensure I see it in a timely manner. More information on these can be found in the TODO.md file.

* Region-based logic: the user should have the ability to define regions for their locations and items and factor those regions into the game's logic (as in X% of this region required as pre-req for next region). This was suggested [here](https://discord.com/channels/731205301247803413/1459523644693676160/1493368125142470717) and will be my primary focus for v0.9.
* Full tutorial/setup guide for first-time users
* Notification history tab
* Import from csv/xls option
* Separate sections for tasks and rewards in the YAML generator
* Text client tab or expandable drawer
* Pomodoro-sanity mode where all tasks are given a pomodoro rating, and pomodoro completions become locations. This will include a built-in pomodoro timer.
* Lower prio: facelift on some of the UI to make it look cleaner