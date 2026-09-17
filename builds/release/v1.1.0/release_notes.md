# Taskipelago/Taskipelabingo Version 1.1.0
*One client everywhere*

## Unified Client
* The apworld now ships the web client and a small local web server; the old Tk client is removed. The same client runs from the Archipelago Launcher and on the hosted web page
* The launcher client opens in a Chromium app window (Chrome, Edge, Chromium or Brave), and falls back to your default browser when none is installed
* The hosted web page can only connect to secure (wss://) servers such as archipelago.gg. Use the launcher client for local or LAN (ws://) servers
* Per-seed state (manual consumable adjustments, purchases, notification progress and DeathLink task cards) now syncs through the Archipelago server, so it follows you across devices and between the hosted page and the launcher client
* Saved state from the previous client is migrated automatically
* The YAML Generator and Taskipelabingo generator are part of the client, with autosaved drafts

## New Features
* **Hints tab**: every hint for your slot with sortable columns, colored like the Archipelago text client. Set Priority, No Priority or Avoid on hints for items you receive
* **DeathLink alerts**: DeathLink notifications are highlighted in red, can play a short sound (toggle in the Notifications tab), flash the window title and switch to the Notifications tab
* **DeathLink task cards**: each DeathLink that gets past amnesty adds a red task card at the top of the task list (or above the bingo board) that you check off when done. Cards are saved locally and shared by every client on your slot
* **DeathLink lock** (optional): with the new "Lock other tasks until DeathLink tasks are done" setting, pending DeathLink cards lock every other task, purchase and consumable adjustment until they are completed
* **Progressive group colors**: groups get a color in the YAML Generator, and the Items tab groups received items under their progressive group in that color
* **Item filters**: filter the Items tab by type (Progression, Useful, Junk, Trap, Filler, Consumable) and by progressive group. A "+X Hidden Items" line shows how many items are hidden
* **Rename updates references**: renaming a region or progressive group in the YAML Generator offers to update every expression that uses it. Removing one that is still referenced asks first
* **Reorder tasks and items**: up/down buttons on every task and item row, with an option to update numbered references automatically
* **Find and Replace** in the YAML Generator (Ctrl+F / Ctrl+H), with match case, whole word and per-field scopes
* Tutorial steps for all of the above

## New YAML Options
* `death_link_lock_tasks` (default off): lock other tasks while DeathLink task cards are pending
* `progressive_group_colors` (default none): colors for progressive groups, parallel to `progressive_groups`

Existing YAMLs generate the same as before, and v1.0.x seeds play in the new client.

## Bug Fixes
* Region and progressive group names containing characters other than letters, underscores and hyphens (for example `weapons+`) can now be referenced with a count or percentage suffix (`weapons+*3`, `weapons+-2`). Region and group names now share one rule: start with a letter or underscore, no digits, spaces, quotes, parentheses, commas, && or ||
* Taskipelabingo no longer gives the free space a useless "Bingo r,c Unlock" item; its reward slot is filler like the line rewards
* Taskipelabingo asks before exporting when more rewards were entered than there are reward slots, instead of silently dropping them

## Known Issues
* Universal Tracker is unhappy with the structure of the datapackage because of the dynamic nature of Taskipelago's location names. This is aimed to be resolved in a future patch. This is an issue specifically with multiple taskipelago worlds in a single multiworld with shared item or location names.
