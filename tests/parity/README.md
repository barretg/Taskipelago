# Parity corpora

Python stays the authority for generation. The web client ports must match it.

## Prereq / cost parser (UNIFY 5.4)

- `prereq_corpus.json`: expressions plus parser arguments (`defaults` merged into each case).
- `prereq_golden.json`: Python output for every case (`{"ast": ...}` or `{"error": "..."}`).
- `prereq_parity.py`: loads `custom_worlds/taskipelago/prereq_parser.py` and writes the golden file.

Checks (both run by `python tests/run_tests.py`):
- `tests/python/test_prereq_parity.py`: golden still matches the Python parser.
- `tests/js/shared/prereq_parser.test.mjs`: `shared/prereq_parser.js` matches the golden file.

Changing the parser: change both files, add corpus cases, run
`python tests/parity/prereq_parity.py`, review the golden diff, run the suite.
Cases marked `"f8": true` record the pre-F8 behavior (v1.1_PLAN Phase A).

## YAML Generator and Taskipelabingo (UNIFY 5.3, 5.5)

- `legacy_generator.py`: loads `legacy_client/client.py` with tkinter/CommonClient/network modules stubbed
  and runs its real `export_yaml`, `_populate_from_taskipelago_doc` and bingo methods headlessly.
- `yaml_corpus/`: `era_*.yaml` (one per legacy export shape, v0.1 to v1.0.2, written by
  `make_yaml_corpus.py`) and hand-written `hand_*.yaml` edge cases (YAML 1.1 scalars, odd types,
  Python exceptions, load errors).
- `generator_parity.py`: writes `generator_golden.json` from the legacy code: every corpus import,
  the export cases in the script, a re-export of every imported model, and the bingo exports,
  settings files, counter labels and loads. Random filler names become `<random filler>`; bingo
  randomness uses `FixedRandom`.

Checks: `tests/python/test_generator_parity.py` (golden still matches legacy),
`tests/js/generator/yaml_parity.test.mjs` and `bingo_parity.test.mjs` (JS matches golden; JS export
text is read back with PyYAML via `$PYTHON`), `tests/js/generator/generator_ui.test.mjs` (jsdom UI).

Adding a case: add a YAML to `yaml_corpus/` or a case to `generator_parity.py`, run
`python tests/parity/generator_parity.py`, review the golden diff, run the suite. A JS mismatch
means the port is wrong, not the golden file (the legacy client is the reference until v1.1 ships).

## Help text (UNIFY 5.3 tooltips, 5.7 tutorial)

`legacy_text.py` extracts the tutorial steps and every `build_ui` tooltip from the legacy client
into `web-client/js/generator/legacy_text.js`. `tests/python/test_legacy_text.py` fails when it is
stale. Web-only text (the hosted-vs-launcher tutorial step) lives in `generator/tutorial.js`.

## Intentional v1.1 changes (plan rule 3)

The harnesses still run the v1.0.2 code, then apply one named step per feature:
- F8 (`generator_parity.py` `apply_v11_changes`): region and group names follow `validateRefName`
  at export. Names legacy rejected but F8 accepts are exported under letter-only aliases and
  mapped back. The prereq golden needs no override (it regenerates from `prereq_parser.py`).
- F8 (`legacy_text.py` `V11_TIP_CHANGES`): region and group hint tooltips describe the new rule.
- F9 (`apply_v11_bingo_export`, `apply_v11_bingo_counts`): the free space is filler instead of
  `Bingo r,c Unlock`, and the rewards label reports unused rewards. `v102_yaml_from:*` loads keep
  a v1.0.2 bingo export covered.
