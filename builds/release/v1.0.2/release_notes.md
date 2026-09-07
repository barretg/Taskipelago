# Taskipelago/Taskipelabingo Version 1.0.2
Quick bug fix patch

## Bug fixes
* Fixed an issue where the offsets for item rows under a filler block were not being offset properly on export
* Fixed pop-up windows on linux 
* Fixed a bug with drawer rendering on linux
Note on linux fixes: I use wayland, need verification from other compositor/window manager users

## Known Issues
* Universal Tracker is unhappy with the structure of the datapackage because of the dynamic nature of Taskipelago's location names. This is aimed to be resolved in a future patch. This is an issue specifically with multiple taskipelago worlds in a single multiworld with shared item or location names.