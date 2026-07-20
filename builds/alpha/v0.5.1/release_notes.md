# Version 0.5.1
Hotfix for critical bugs in version 0.5

## Features, Improvements, and Changes
* Added instruction text for clarity in yaml generator

## Bug Fixes
* Notification state now hashed by seed to avoid collision when creating more than one apworld with the same slotname and server.
* Fixed (silly) bug in item sent notifications so it now actually works and doesn't fall back to the local cache ever because that doesn't make sense...
* Fix remove row in yaml generator