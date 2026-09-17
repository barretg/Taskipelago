# **Taskipelago**: an apworld for arbitrary to-do lists!

## How it works:

### 'Tasks' and 'Items'

* In the client's YAML generator, you'll be able to input 'Tasks' and 'Items'

* Tasks are the checks (locations) you'll need to mark complete on the client's to-do list

* Items are the items that are shuffled into the multi-world to match those spots

* Tasks can be prerequisite on the completion of other tasks or items. It is advised to set up a hierarchy with this, as otherwise all checks will be in sphere 1

### DeathLink:

* If DeathLink is enabled, the user can provide a list of random tasks or punishments that go off whenever the client receives a death link

* As an example things like "10 pushups" or "Tidy one thing in your room" or "Read 2 pages of a book" or "1 minute plank" make for good DeathLink tasks

* Each triggered DeathLink task shows up as a red card at the top of your task list until you complete it. Optionally, pending DeathLink cards can lock all other tasks until they are done

### Taskipelabingo

* Taskipelabingo mode allows you to provide a list of tasks to be selected at random and shuffled into a bingo board. For more information, see the Taskipelabingo tab in the client

## Setup:

* Download taskipelago.apworld from the releases page

* Place taskipelago.apworld in the custom_worlds folder of your archipelago install

* Launch the client from archipelago and use it to build a yaml to place in your host's Players folder. Follow the in-client tutorial for more information.

* Once the server is up, you can join from the client through your archipelago launcher, or via the [web client](https://barretg.github.io/Taskipelago/web-client/)

* Congrats, your setup is complete!

### Launcher client vs hosted web client

* They are the same app. The launcher serves it locally and opens it in an app window, preferring a Chromium-based browser (Chrome, Edge, Chromium) and falling back to your default browser.

* The hosted web client can only connect to secure (`wss://`) servers such as archipelago.gg. For a local or LAN server (`ws://`), use the client from the launcher.

* Per-seed progress (notification history, purchases, manual consumable use) is stored on the Archipelago server, so it follows you between the two clients and across devices. Generator drafts and UI preferences stay on the device that made them.

## Community YAML Submission
[Submit your YAML Here!](https://script.google.com/macros/s/AKfycbxDgukz7NG9emJOODU2-HOMCHPJJyoIH_kSHHnpJwSEHvBSjWewhHWAG1Cd4qhH9YsuUg/exec)

## Development

* Run the regression suite after any major change: `python tests/run_tests.py` (or `python tests/run_tests.py python` / `js`). It needs Python with PyYAML and Node 20+; jsdom installs into `tests/node_modules` on first run.

* The web client's prereq parser, YAML import/export, Taskipelabingo generator and help text are checked against the legacy Python client. See `tests/parity/README.md`.
