# Version 0.6
Major version update refactoring the apworld to use the new Rule Builder for cleaner code and maintainability, as well as some feature additions. Requires Archipelago version 0.6.7+ for generation.

## Features, Improvements, and Changes
* Goal task can now be selected
* Refactor apworld to use new Rule Builder API
* Refactor apworld into several files to conform to standard practice better
* QOL: empty rewards now automatically populate as filler items on YAML export
* QOL: Item names actually reflect the reward names in the multiworld

## Bug fixes
* Checklist no longer marks tasks completed just because their reward has been collected by the multiworld.