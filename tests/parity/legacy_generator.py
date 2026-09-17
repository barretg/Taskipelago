"""Run the legacy (v1.0.2) Tk YAML Generator logic headlessly.

legacy_client/client.py is loaded with tkinter, CommonClient, NetUtils,
websockets and certifi replaced by small stubs, so its export_yaml and
_populate_from_taskipelago_doc run unchanged against fake Tk variables. The
parity corpus (UNIFY 5.3, M4 gate) records their results as the reference for
web-client/js/generator/yaml_export.js and yaml_import.js.

Model shape shared with the JS generator (generator/model.js):
    playerName, progressionBalancing, accessibility, deathLinkEnabled,
    deathLinkAmnesty, lockPrereqs, hideUnreachable, taskRewardPreviews (index),
    goalTasks, progGroups [name], regions [{name, pct, color, prereq}],
    nextColorIdx, tasks [{name, prereq, itemPrereq, cost, region, priority,
    count, desc}], items [{name, filler, type, progGroup, consumable, count}],
    deathLink [{text, weight}]
Random filler names are replaced with FILLER_PLACEHOLDER on both sides.
"""
from __future__ import annotations

import importlib.util
import inspect
import os
import sys
import tempfile
import types
from pathlib import Path

import yaml

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
CLIENT = ROOT / "legacy_client" / "client.py"
PARSER = ROOT / "custom_worlds" / "taskipelago" / "prereq_parser.py"
PKG = "taskipelago_legacy"
FILLER_PLACEHOLDER = "<random filler>"


# ---------------------------------------------------------------------------
# Tk stand-ins
# ---------------------------------------------------------------------------
class TclError(Exception):
    pass


class _Var:
    default = ""

    def __init__(self, master=None, value=None, name=None):
        self._value = self.default if value is None else value
        self._traces = []

    def set(self, value):
        self._value = value
        for callback in list(self._traces):
            callback(None, "", "write")

    def trace_add(self, mode, callback):
        self._traces.append(callback)
        return f"trace{len(self._traces)}"

    def get(self):
        return self._value


class StringVar(_Var):
    default = ""

    def get(self):
        return self._value if isinstance(self._value, str) else str(self._value)


class IntVar(_Var):
    default = 0

    def get(self):
        try:
            return int(self._value)
        except (TypeError, ValueError) as e:
            raise TclError(str(e))


class BooleanVar(_Var):
    default = False

    def get(self):
        return bool(self._value)


class _Widget:
    def __init__(self, *args, **kwargs):
        pass

    def __getattr__(self, name):
        if name.startswith("__"):
            raise AttributeError(name)
        return lambda *args, **kwargs: None


def _stub_modules() -> dict:
    tk = types.ModuleType("tkinter")
    for n in ("Tk", "Toplevel", "Frame", "Label", "Canvas", "Text", "Entry", "Button",
              "Widget", "Misc", "Scrollbar"):
        setattr(tk, n, type(n, (_Widget,), {}))
    tk.StringVar, tk.IntVar, tk.BooleanVar, tk.TclError = StringVar, IntVar, BooleanVar, TclError
    ttk = types.ModuleType("tkinter.ttk")
    for n in ("Frame", "Label", "Entry", "Button", "Checkbutton", "Combobox", "Spinbox",
              "Scrollbar", "Notebook", "Separator", "LabelFrame", "Style"):
        setattr(ttk, n, type(n, (_Widget,), {}))
    messagebox = types.ModuleType("tkinter.messagebox")
    filedialog = types.ModuleType("tkinter.filedialog")
    tk.ttk, tk.messagebox, tk.filedialog = ttk, messagebox, filedialog
    common = types.ModuleType("CommonClient")
    common.ClientCommandProcessor = type("ClientCommandProcessor", (), {})
    common.CommonContext = type("CommonContext", (), {})
    net = types.ModuleType("NetUtils")
    net.Endpoint = object
    net.decode = lambda s: s
    certifi = types.ModuleType("certifi")
    certifi.where = lambda: ""
    return {
        "tkinter": tk, "tkinter.ttk": ttk, "tkinter.messagebox": messagebox,
        "tkinter.filedialog": filedialog, "CommonClient": common, "NetUtils": net,
        "websockets": types.ModuleType("websockets"), "certifi": certifi,
    }


_client = None


def load_client():
    """Import legacy_client/client.py with stubbed GUI/network modules (cached)."""
    global _client
    if _client is not None:
        return _client
    stubs = _stub_modules()
    saved = {k: sys.modules.get(k) for k in stubs}
    sys.modules.update(stubs)
    try:
        pkg = types.ModuleType(PKG)
        pkg.__path__ = []
        sys.modules[PKG] = pkg
        pspec = importlib.util.spec_from_file_location(f"{PKG}.prereq_parser", PARSER)
        parser = importlib.util.module_from_spec(pspec)
        sys.modules[pspec.name] = parser
        pspec.loader.exec_module(parser)
        spec = importlib.util.spec_from_file_location(f"{PKG}.client", CLIENT)
        client = importlib.util.module_from_spec(spec)
        sys.modules[spec.name] = client
        spec.loader.exec_module(client)
    finally:
        for k, v in saved.items():
            if v is None:
                sys.modules.pop(k, None)
            else:
                sys.modules[k] = v
    _client = client
    return client


class _App:
    """Holds the generator state TaskipelagoApp's methods read; methods resolve to the real class."""

    def __init__(self, client):
        self._client = client
        self.messages = []

    def __getattr__(self, name):
        app_cls = self.__dict__["_client"].TaskipelagoApp
        attr = inspect.getattr_static(app_cls, name)  # AttributeError when missing
        if isinstance(attr, staticmethod):
            return attr.__func__
        if callable(attr):
            return types.MethodType(attr, self)
        return attr


def new_app():
    """Generator state as TaskipelagoApp.__init__ + build_ui leave it."""
    client = load_client()
    app = _App(client)
    app.colors = {}
    app.task_rows, app.item_rows, app.deathlink_rows = [], [], []
    app.prog_groups, app.regions = [], []
    app.region_default_pcts, app.region_colors, app.region_prereqs = {}, {}, {}
    app._next_color_idx = 0
    app.player_name_var = StringVar()
    client._limit_var_length(app.player_name_var, client.MAX_PLAYER_NAME_LEN)
    app.lock_prereqs_var = BooleanVar(value=True)
    app.hide_unreachable_tasks = BooleanVar(value=True)
    app.task_reward_previews_var = StringVar(value=client.TASK_REWARD_PREVIEW_LABELS[0])
    app.goal_tasks_var = StringVar()
    app.progression_var = IntVar(value=50)
    app.accessibility_var = StringVar(value="full")
    app.deathlink_enabled = BooleanVar(value=False)
    app.deathlink_amnesty_var = IntVar(value=0)
    app.tasks_scroll = types.SimpleNamespace(inner=_Widget())
    app.items_scroll = types.SimpleNamespace(inner=_Widget())
    app.dl_scroll = types.SimpleNamespace(inner=_Widget())
    app.add_task_row()
    return app


def _bind_dialogs(app, confirm=True, save_path=""):
    client = app._client
    mb = client.messagebox
    mb.showerror = lambda title, message, **_: app.messages.append(["error", title, message])
    mb.showwarning = lambda title, message, **_: app.messages.append(["warning", title, message])
    mb.showinfo = lambda title, message, **_: app.messages.append(["info", title, message])

    def askyesno(title, message, **_):
        app.messages.append(["confirm", title, message])
        return confirm

    mb.askyesno = askyesno
    client.filedialog.asksaveasfilename = lambda **_: save_path


def _raw(var):
    return var._value


def harvest(app) -> dict:
    """Editor state as the model dict (raw widget values, like the JS model)."""
    labels = app._client.TASK_REWARD_PREVIEW_LABELS
    return {
        "playerName": app.player_name_var.get(),
        "progressionBalancing": _raw(app.progression_var),
        "accessibility": app.accessibility_var.get(),
        "deathLinkEnabled": app.deathlink_enabled.get(),
        "deathLinkAmnesty": _raw(app.deathlink_amnesty_var),
        "lockPrereqs": app.lock_prereqs_var.get(),
        "hideUnreachable": app.hide_unreachable_tasks.get(),
        "taskRewardPreviews": labels.index(app.task_reward_previews_var.get()),
        "goalTasks": app.goal_tasks_var.get(),
        "progGroups": list(app.prog_groups),
        "regions": [
            {"name": r, "pct": app.region_default_pcts.get(r, 100),
             "color": app.region_colors.get(r, ""), "prereq": app.region_prereqs.get(r, "")}
            for r in app.regions
        ],
        "nextColorIdx": app._next_color_idx,
        "tasks": [
            {"name": r.task_var.get(), "prereq": r.prereq_var.get(), "itemPrereq": r.item_prereq_var.get(),
             "cost": r.cost_var.get(), "region": r.region_var.get(), "priority": r.priority_var.get(),
             "count": _raw(r.count_var), "desc": r.desc_var.get()}
            for r in app.task_rows
        ],
        "items": [
            {"name": FILLER_PLACEHOLDER if r.filler_var.get() else r.item_var.get(),
             "filler": r.filler_var.get(), "type": r.reward_type_var.get(),
             "progGroup": r.prog_group_var.get(), "consumable": r.consumable_var.get(),
             "count": _raw(r.count_var)}
            for r in app.item_rows
        ],
        "deathLink": [{"text": r.text_var.get(), "weight": r.weight_var.get()} for r in app.deathlink_rows],
    }


def _apply_model(app, model: dict) -> None:
    """Load a model into the editor without firing widget traces."""
    labels = app._client.TASK_REWARD_PREVIEW_LABELS
    app.player_name_var._value = model["playerName"]
    app.progression_var._value = model["progressionBalancing"]
    app.accessibility_var._value = model["accessibility"]
    app.deathlink_enabled._value = model["deathLinkEnabled"]
    app.deathlink_amnesty_var._value = model["deathLinkAmnesty"]
    app.lock_prereqs_var._value = model["lockPrereqs"]
    app.hide_unreachable_tasks._value = model["hideUnreachable"]
    app.task_reward_previews_var._value = labels[model["taskRewardPreviews"]]
    app.goal_tasks_var._value = model["goalTasks"]
    app.prog_groups = list(model["progGroups"])
    app.regions = [r["name"] for r in model["regions"]]
    app.region_default_pcts = {r["name"]: r["pct"] for r in model["regions"]}
    app.region_colors = {r["name"]: r["color"] for r in model["regions"]}
    app.region_prereqs = {r["name"]: r["prereq"] for r in model["regions"]}
    app._next_color_idx = model.get("nextColorIdx", len(app.regions))

    app._clear_task_rows()
    for t in model["tasks"]:
        row = app.add_task_row()
        for var, key in ((row.task_var, "name"), (row.prereq_var, "prereq"), (row.item_prereq_var, "itemPrereq"),
                         (row.cost_var, "cost"), (row.region_var, "region"), (row.priority_var, "priority"),
                         (row.count_var, "count"), (row.desc_var, "desc")):
            var._value = t[key]
    app._clear_item_rows()
    for it in model["items"]:
        row = app.add_item_row()
        for var, key in ((row.item_var, "name"), (row.filler_var, "filler"), (row.reward_type_var, "type"),
                         (row.prog_group_var, "progGroup"), (row.consumable_var, "consumable"),
                         (row.count_var, "count")):
            var._value = it[key]
    app._clear_deathlink_rows()
    for d in model["deathLink"]:
        app.add_deathlink_row()
        row = app.deathlink_rows[-1]
        row.text_var._value = d["text"]
        row.weight_var._value = d["weight"]


def legacy_import(doc) -> dict:
    app = new_app()
    _bind_dialogs(app)
    try:
        ok = bool(app._populate_from_taskipelago_doc(doc))
    except Exception as e:  # the Tk client left partial state behind; not modelled
        return {"ok": False, "exception": type(e).__name__, "model": None, "messages": app.messages}
    return {"ok": ok, "exception": None, "model": harvest(app), "messages": app.messages}


def legacy_export(model: dict, confirm: bool = True) -> dict:
    app = new_app()
    _apply_model(app, model)
    with tempfile.TemporaryDirectory() as d:
        path = os.path.join(d, "export.yaml")
        _bind_dialogs(app, confirm=confirm, save_path=path)
        app.export_yaml()
        text = Path(path).read_text(encoding="utf-8") if os.path.exists(path) else None
    data = yaml.safe_load(text) if text is not None else None
    if data is not None:
        block = data["Taskipelago"]
        for i, filler in enumerate(block["item_fillers"]):
            if filler:
                block["items"][i] = FILLER_PLACEHOLDER
    messages = [m for m in app.messages if not (m[0] == "info" and m[1] == "Success")]
    return {"data": data, "messages": messages}


# ---------------------------------------------------------------------------
# Taskipelabingo generator (UNIFY 5.5)
# ---------------------------------------------------------------------------
# Bingo model shape (bingo_gen/bingo_model.js): playerName, x, y, bingoal,
# progressionBalancing, accessibility, deathLinkEnabled, deathLinkAmnesty and the
# raw text of the spaces, rewards and deathLinkPool boxes.
class _Text:
    def __init__(self):
        self.value = ""

    def get(self, start, end):
        return self.value

    def delete(self, start, end):
        self.value = ""

    def insert(self, index, text):
        self.value += text


class _Label(_Widget):
    def __init__(self):
        self.text = ""

    def config(self, text="", **_):
        self.text = text


class FixedRandom:
    """Deterministic stand-in for the random module: sample takes the pool
    reversed, shuffle reverses in place, choice takes the first entry. The JS
    parity test uses the same rules."""

    @staticmethod
    def sample(pool, n):
        return list(reversed(pool))[:n]

    @staticmethod
    def shuffle(items):
        items.reverse()

    @staticmethod
    def choice(seq):
        return seq[0]


def new_bingo_app():
    client = load_client()
    app = _App(client)
    app.bingo_player_var = StringVar()
    client._limit_var_length(app.bingo_player_var, client.MAX_PLAYER_NAME_LEN)
    app.bingo_x_var = IntVar(value=5)
    app.bingo_y_var = IntVar(value=5)
    app.bingo_goal_var = IntVar(value=3)
    app.bingo_prog_var = IntVar(value=50)
    app.bingo_access_var = StringVar(value="full")
    app.bingo_deathlink_var = BooleanVar(value=False)
    app.bingo_deathlink_amnesty_var = IntVar(value=0)
    app.bingo_spaces_text = _Text()
    app.bingo_rewards_text = _Text()
    app.bingo_deathlink_text = _Text()
    app._bingo_count_label = _Label()
    app._bingo_rewards_count_label = _Label()
    return app


def harvest_bingo(app) -> dict:
    return {
        "playerName": app.bingo_player_var.get(),
        "x": _raw(app.bingo_x_var), "y": _raw(app.bingo_y_var), "bingoal": _raw(app.bingo_goal_var),
        "progressionBalancing": _raw(app.bingo_prog_var), "accessibility": app.bingo_access_var.get(),
        "deathLinkEnabled": app.bingo_deathlink_var.get(), "deathLinkAmnesty": _raw(app.bingo_deathlink_amnesty_var),
        "spaces": app.bingo_spaces_text.value, "rewards": app.bingo_rewards_text.value,
        "deathLinkPool": app.bingo_deathlink_text.value,
    }


def _apply_bingo_model(app, model: dict) -> None:
    app.bingo_player_var._value = model["playerName"]
    app.bingo_x_var._value = model["x"]
    app.bingo_y_var._value = model["y"]
    app.bingo_goal_var._value = model["bingoal"]
    app.bingo_prog_var._value = model["progressionBalancing"]
    app.bingo_access_var._value = model["accessibility"]
    app.bingo_deathlink_var._value = model["deathLinkEnabled"]
    app.bingo_deathlink_amnesty_var._value = model["deathLinkAmnesty"]
    app.bingo_spaces_text.value = model["spaces"]
    app.bingo_rewards_text.value = model["rewards"]
    app.bingo_deathlink_text.value = model["deathLinkPool"]


def _with_fixed_random(app, fn):
    client = app._client
    saved = client.random
    client.random = FixedRandom
    try:
        return fn()
    finally:
        client.random = saved


def _saved_yaml(app, method: str):
    with tempfile.TemporaryDirectory() as d:
        path = os.path.join(d, "out.yaml")
        app._client.filedialog.asksaveasfilename = lambda **_: path
        _with_fixed_random(app, getattr(app, method))
        text = Path(path).read_text(encoding="utf-8") if os.path.exists(path) else None
    return yaml.safe_load(text) if text is not None else None


def legacy_bingo_export(model: dict) -> dict:
    app = new_bingo_app()
    _apply_bingo_model(app, model)
    _bind_dialogs(app)
    data = _saved_yaml(app, "_export_bingo_yaml")
    messages = [m for m in app.messages if m[0] != "info"]
    return {"data": data, "messages": messages}


def legacy_bingo_settings(model: dict) -> dict:
    app = new_bingo_app()
    _apply_bingo_model(app, model)
    _bind_dialogs(app)
    return _saved_yaml(app, "_save_bingo_settings")


def legacy_bingo_counts(model: dict) -> dict:
    app = new_bingo_app()
    _apply_bingo_model(app, model)
    app._update_bingo_counts()
    return {"spaces": app._bingo_count_label.text, "rewards": app._bingo_rewards_count_label.text}


def legacy_bingo_load(doc) -> dict:
    """_load_bingo after the file is read, starting from a fresh tab."""
    app = new_bingo_app()
    _bind_dialogs(app)
    kind = "settings" if isinstance(doc, dict) and "spaces" in doc else "yaml"
    try:
        if kind == "settings":
            app._load_bingo_settings_doc(doc, "file")
        else:
            app._load_bingo_yaml_doc(doc, "file")
    except Exception as e:  # noqa: BLE001
        return {"kind": kind, "exception": type(e).__name__, "model": None, "messages": []}
    ok = not any(m[0] == "error" for m in app.messages)
    messages = [m for m in app.messages if m[0] != "info"]
    return {"kind": kind, "exception": None, "ok": ok, "model": harvest_bingo(app), "messages": messages}
