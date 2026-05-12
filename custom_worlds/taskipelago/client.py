import asyncio
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
import random
import re
import threading
import time
from tkinter import filedialog, messagebox
import tkinter as tk
from tkinter import ttk

import json
import yaml

import certifi
import ssl
import traceback
import websockets

import CommonClient
from NetUtils import Endpoint, decode

FILLER_TOKEN = "nothing here, get pranked nerd"
REWARD_TYPE_VALUES = ("junk", "useful", "progression", "trap")
DEFAULT_REWARD_TYPE = "useful"

# parsing help
def _eval_prereq_expr(text: str, leaf_fn) -> bool:
    """
    Evaluate a boolean prereq expression string client-side.
    leaf_fn(idx_1based) -> bool
    Supports: integers, &&, ||, ',', parentheses.
    """
    text = text.strip()
    if not text:
        return True

    # Tokenize
    tokens = []
    i = 0
    while i < len(text):
        c = text[i]
        if c.isspace():
            i += 1
        elif c.isdigit():
            j = i
            while j < len(text) and text[j].isdigit():
                j += 1
            tokens.append(int(text[i:j]))
            i = j
        elif text[i:i+2] in ("&&", "||"):
            tokens.append(text[i:i+2])
            i += 2
        elif c in ("(", ")", ","):
            tokens.append(c)
            i += 1
        else:
            raise ValueError(f"Unexpected char: {c}")

    pos = [0]

    def peek():
        return tokens[pos[0]] if pos[0] < len(tokens) else None

    def consume():
        t = tokens[pos[0]]; pos[0] += 1; return t

    def parse_or():
        left = parse_and()
        results = [left]
        while peek() == "||":
            consume()
            results.append(parse_and())
        return any(results)

    def parse_and():
        left = parse_atom()
        results = [left]
        while peek() in ("&&", ","):
            consume()
            results.append(parse_atom())
        return all(results)

    def parse_atom():
        tok = peek()
        if tok == "(":
            consume()
            val = parse_or()
            consume()  # ")"
            return val
        if isinstance(tok, int):
            consume()
            return leaf_fn(tok)
        raise ValueError(f"Unexpected token: {tok}")

    return parse_or()

# ----------------------------
# Dark theme helpers (ttk)
# ----------------------------
def apply_dark_theme(root: tk.Tk):
    style = ttk.Style(root)
    style.theme_use("clam")

    bg = "#1e1e1e"
    panel = "#252526"
    field = "#2d2d30"
    fg = "#e6e6e6"
    muted = "#bdbdbd"
    border = "#3a3a3a"

    root.configure(bg=bg)

    style.configure(".", background=bg, foreground=fg, fieldbackground=field)
    style.configure("TFrame", background=bg)
    style.configure("TLabelframe", background=bg, foreground=fg, bordercolor=border)
    style.configure("TLabelframe.Label", background=bg, foreground=fg)
    style.configure("TLabel", background=bg, foreground=fg)
    style.configure("Muted.TLabel", background=bg, foreground=muted)

    style.configure("TButton", background=panel, foreground=fg, bordercolor=border)
    style.map("TButton", background=[("active", "#303030")])

    style.configure("TEntry", fieldbackground=field, background=field, foreground=fg, insertcolor=fg)
    style.configure("TSpinbox", fieldbackground=field, background=field, foreground=fg, insertcolor=fg)

    style.configure(
        "TCombobox",
        fieldbackground=field,
        background=field,
        foreground=fg,
        arrowcolor=fg,
    )
    style.map(
        "TCombobox",
        fieldbackground=[("readonly", field)],
        background=[("readonly", field)],
        foreground=[("readonly", fg)],
    )

    style.configure("TCheckbutton", background=bg, foreground=fg)
    style.map(
        "TCheckbutton",
        background=[("active", bg), ("pressed", bg), ("focus", bg), ("selected", bg)],
        foreground=[("active", fg), ("pressed", fg), ("focus", fg), ("selected", fg)],
    )

    style.configure("TNotebook", background="#2b2b2b", borderwidth=0)
    style.configure("TNotebook.Tab", padding=(14, 6), background="#3a3a3a", foreground="#dddddd", borderwidth=0)
    style.map("TNotebook.Tab", background=[("selected", "#4a4a4a")], foreground=[("selected", "#ffffff")])

    return {"bg": bg, "panel": panel, "border": border, "fg": fg, "muted": muted}


# ----------------------------
# Scrollable container (auto-hide scrollbar)
# ----------------------------
class ScrollableFrame(ttk.Frame):
    def __init__(self, parent, colors=None):
        super().__init__(parent)
        self.colors = colors or {"bg": "#1e1e1e"}

        self.canvas = tk.Canvas(self, highlightthickness=0, bg=self.colors["bg"])
        self.vsb = ttk.Scrollbar(self, orient="vertical", command=self.canvas.yview)
        self.inner = ttk.Frame(self.canvas)

        # Mark ownership so we can find the right ScrollableFrame from any child widget
        self.canvas._scroll_owner = self
        self.inner._scroll_owner = self

        self.window_id = self.canvas.create_window((0, 0), window=self.inner, anchor="nw")
        self.canvas.configure(yscrollcommand=self._on_scroll)

        self.canvas.grid(row=0, column=0, sticky="nsew")
        self.vsb.grid(row=0, column=1, sticky="ns")
        self.vsb.grid_remove()

        self.grid_rowconfigure(0, weight=1)
        self.grid_columnconfigure(0, weight=1)

        self.inner.bind("<Configure>", self._on_frame_configure)
        self.canvas.bind("<Configure>", self._on_canvas_configure)

    def _on_scroll(self, first, last):
        self.vsb.set(first, last)
        if float(first) <= 0.0 and float(last) >= 1.0:
            self.vsb.grid_remove()
        else:
            self.vsb.grid()

    def _on_frame_configure(self, _event=None):
        self.canvas.configure(scrollregion=self.canvas.bbox("all"))
        self._update_scrollbar_visibility()

    def _on_canvas_configure(self, event):
        self.canvas.itemconfig(self.window_id, width=event.width)
        self._update_scrollbar_visibility()

    def _update_scrollbar_visibility(self):
        region = self.canvas.bbox("all")
        if not region:
            self.vsb.grid_remove()
            return
        content_height = region[3] - region[1]
        canvas_height = self.canvas.winfo_height()
        if content_height > canvas_height:
            self.vsb.grid()
        else:
            self.vsb.grid_remove()

    # ---------- Mousewheel plumbing ----------
    @classmethod
    def bind_mousewheel_to_root(cls, root: tk.Misc):
        # Windows/macOS
        root.bind_all("<MouseWheel>", lambda e, r=root: cls._dispatch_mousewheel(e, r), add=True)
        # Linux
        root.bind_all("<Button-4>", lambda e, r=root: cls._dispatch_mousewheel_linux(e, r, -1), add=True)
        root.bind_all("<Button-5>", lambda e, r=root: cls._dispatch_mousewheel_linux(e, r, 1), add=True)

    @classmethod
    def _find_scroll_owner_under_pointer(cls, root: tk.Misc, x_root: int, y_root: int):
        w = root.winfo_containing(x_root, y_root)
        while w is not None:
            if hasattr(w, "_scroll_owner"):
                return getattr(w, "_scroll_owner")
            w = getattr(w, "master", None)
        return None

    @classmethod
    def _dispatch_mousewheel(cls, event, root: tk.Misc):
        owner = cls._find_scroll_owner_under_pointer(root, event.x_root, event.y_root)
        if owner is None:
            return

        delta = int(-1 * (event.delta / 120)) if getattr(event, "delta", 0) else 0
        if delta:
            owner.canvas.yview_scroll(delta, "units")

    @classmethod
    def _dispatch_mousewheel_linux(cls, event, root: tk.Misc, direction: int):
        owner = cls._find_scroll_owner_under_pointer(root, event.x_root, event.y_root)
        if owner is None:
            return
        owner.canvas.yview_scroll(direction, "units")


# ----------------------------
# Tooltip helper
# ----------------------------
class Tooltip:
    """Show a tooltip popup after a short hover delay."""

    _DELAY = 600
    _WRAP  = 360

    def __init__(self, widget: tk.Widget, text: str):
        self._widget = widget
        self._text   = text
        self._job    = None
        self._tip    = None
        widget.bind("<Enter>",  self._on_enter, add=True)
        widget.bind("<Leave>",  self._on_leave, add=True)
        widget.bind("<Button>", self._on_leave, add=True)

    def _on_enter(self, _=None):
        self._job = self._widget.after(self._DELAY, self._show)

    def _on_leave(self, _=None):
        if self._job:
            self._widget.after_cancel(self._job)
            self._job = None
        self._hide()

    def _show(self):
        if self._tip:
            return
        x = self._widget.winfo_rootx() + 10
        y = self._widget.winfo_rooty() + self._widget.winfo_height() + 4
        self._tip = tk.Toplevel(self._widget)
        self._tip.wm_overrideredirect(True)
        self._tip.wm_geometry(f"+{x}+{y}")
        tk.Label(
            self._tip, text=self._text, justify="left", relief="solid",
            borderwidth=1, wraplength=self._WRAP,
            bg="#2d2d30", fg="#e6e6e6", padx=6, pady=4, font=("Segoe UI", 9),
        ).pack()

    def _hide(self):
        if self._tip:
            self._tip.destroy()
            self._tip = None


def _make_tip_header(parent: tk.Widget, text: str, tip_text: str) -> ttk.Frame:
    """Return a frame with a header label and a hoverable ? tooltip icon."""
    frame = ttk.Frame(parent)
    ttk.Label(frame, text=text).pack(side="left")
    q = ttk.Label(frame, text=" ?", style="Muted.TLabel", cursor="question_arrow")
    q.pack(side="left")
    Tooltip(q, tip_text)
    return frame


# ----------------------------
# Rows (YAML Generator)
# ----------------------------
class TaskRow:
    def __init__(self, parent, index: int, filler_token: str, on_remove, groups=None):
        self.parent = parent
        self.index = index
        self.filler_token = filler_token
        self._on_remove = on_remove

        self.task_var = tk.StringVar()
        self.reward_var = tk.StringVar()
        self.prereq_var = tk.StringVar()
        self.reward_prereq_var = tk.StringVar(value="")
        self.reward_prereq_entry = ttk.Entry(parent, textvariable=self.reward_prereq_var, width=10)
        self.filler_var = tk.BooleanVar()

        self.reward_type_var = tk.StringVar(value=DEFAULT_REWARD_TYPE)
        self._saved_reward_type = DEFAULT_REWARD_TYPE
        self.reward_type_cb = ttk.Combobox(
            parent,
            textvariable=self.reward_type_var,
            values=REWARD_TYPE_VALUES,
            state="readonly",
            width=12
        )

        self._saved_reward = ""
        self._saved_prog_group = ""

        self.prog_group_var = tk.StringVar(value="")
        self.prog_group_cb = ttk.Combobox(
            parent,
            textvariable=self.prog_group_var,
            values=[""] + list(groups or []),
            state="readonly",
            width=12,
        )
        self.prog_group_var.trace_add("write", self._on_prog_group_change)

        self.num_label = ttk.Label(parent, text=str(index), width=3)
        self.task_entry = ttk.Entry(parent, textvariable=self.task_var)
        self.reward_entry = ttk.Entry(parent, textvariable=self.reward_var)
        self.prereq_entry = ttk.Entry(parent, textvariable=self.prereq_var)
        self.filler_cb = ttk.Checkbutton(parent, text="Filler", variable=self.filler_var, command=self.on_filler_toggle)
        self.remove_btn = ttk.Button(parent, text="Remove", width=8, command=self.remove)

        self._grid()

    def _grid(self):
        r = self.index + 1  # header is row 0, hint row is 1, tasks start at row 2
        self.num_label.grid(row=r, column=0, padx=(0, 8), sticky="w", pady=4)
        self.task_entry.grid(row=r, column=1, padx=(0, 8), sticky="ew", pady=4)
        self.reward_entry.grid(row=r, column=2, padx=(0, 8), sticky="ew", pady=4)
        self.prereq_entry.grid(row=r, column=3, sticky="ew", padx=(0, 8), pady=4)
        self.reward_prereq_entry.grid(row=r, column=4, sticky="ew", padx=(0, 8), pady=4)
        self.reward_type_cb.grid(row=r, column=5, sticky="w", padx=(0, 8), pady=4)
        self.filler_cb.grid(row=r, column=6, padx=(0, 8), sticky="w", pady=4)
        self.prog_group_cb.grid(row=r, column=7, sticky="w", padx=(0, 8), pady=4)
        self.remove_btn.grid(row=r, column=8, padx=(0, 0), pady=4)

    def remove(self):
        for w in (
            self.num_label,
            self.task_entry,
            self.reward_entry,
            self.prereq_entry,
            self.reward_prereq_entry,
            self.reward_type_cb,
            self.filler_cb,
            self.prog_group_cb,
            self.remove_btn,
        ):
            try:
                w.destroy()
            except Exception:
                pass
        self._on_remove(self)

    def on_filler_toggle(self):
        if self.filler_var.get():
            current = self.reward_var.get().strip()
            if current and current != self.filler_token:
                self._saved_reward = current
            current_type = self.reward_type_var.get().strip().lower()
            if current_type:
                self._saved_reward_type = current_type
            self._saved_prog_group = self.prog_group_var.get()
            self.prog_group_var.set("")
            self.prog_group_cb.state(["disabled"])
            self.reward_var.set(self.filler_token)
            self.reward_entry.state(["disabled"])
            self.reward_type_var.set("junk")
            self.reward_type_cb.state(["disabled"])
        else:
            self.reward_entry.state(["!disabled"])
            self.reward_var.set(self._saved_reward)
            self.prog_group_cb.state(["!disabled"])
            self.prog_group_var.set(self._saved_prog_group)
            # _on_prog_group_change fires from the trace and restores type / disables as needed

    def _on_prog_group_change(self, *_):
        if self.prog_group_var.get():
            # Group selected: force progression type, lock type dropdown and filler.
            if not self.filler_var.get():
                current_type = self.reward_type_var.get().strip().lower()
                if current_type != "progression":
                    self._saved_reward_type = current_type
            self.reward_type_var.set("progression")
            self.reward_type_cb.state(["disabled"])
            self.filler_cb.state(["disabled"])
        else:
            # Group cleared: restore type and re-enable controls.
            self.reward_type_cb.state(["!disabled"])
            self.reward_type_var.set(self._saved_reward_type or DEFAULT_REWARD_TYPE)
            if not self.filler_var.get():
                self.filler_cb.state(["!disabled"])

    def update_groups(self, groups):
        """Refresh the prog-group combobox values, keeping current selection if still valid."""
        current = self.prog_group_var.get()
        new_values = [""] + list(groups)
        self.prog_group_cb.configure(values=new_values)
        if current not in new_values:
            self.prog_group_var.set("")

    def get_data(self):
        return (
            self.task_var.get().strip(),
            self.reward_var.get().strip(),
            self.prereq_var.get().strip(),
            self.reward_prereq_var.get().strip(),
            self.filler_var.get(),
            self.reward_type_var.get().strip().lower() or "useful",
            self.prog_group_var.get().strip(),
        )


class DeathLinkRow:
    def __init__(self, parent, index: int, on_remove):
        self.parent = parent
        self.index = index
        self._on_remove = on_remove

        self.text_var = tk.StringVar()
        self.weight_var = tk.StringVar(value="1")

        self.task_entry = ttk.Entry(parent, textvariable=self.text_var)
        self.weight_entry = ttk.Entry(parent, textvariable=self.weight_var, width=6)
        self.remove_btn = ttk.Button(parent, text="Remove", width=8, command=self.remove)

        self._grid()

    def _grid(self):
        r = self.index  # header is row 0
        self.task_entry.grid(row=r, column=0, padx=(0, 8), pady=4, sticky="ew")
        self.weight_entry.grid(row=r, column=1, padx=(0, 8), pady=4, sticky="w")
        self.remove_btn.grid(row=r, column=2, pady=4, sticky="e")

    def remove(self):
        for w in (self.task_entry, self.weight_entry, self.remove_btn):
            w.destroy()
        self._on_remove(self)

    def get_data(self):
        return (self.text_var.get().strip(), self.weight_var.get().strip())



# ----------------------------
# Networking
# ----------------------------
class TaskipelagoContext(CommonClient.CommonContext):
    game = "Taskipelago"
    items_handling = 0b111

    def __init__(self, server_address=None, password=None):
        super().__init__(server_address, password)
        self.slot_data = {}

        self.tasks = []
        self.rewards = []
        self.task_prereqs = []
        self.reward_prereqs = []
        self.lock_prereqs = False
        self.hide_unreachable_tasks = True
        self.goal_indices = []
        self.goal_expression = ""

        self.base_reward_location_id = None
        self.base_complete_location_id = None
        self.base_item_id = None

        self.death_link_pool = []
        self.death_link_enabled = False

        self.checked_locations_set = set()

        self.on_disconnected = None
        self.on_state_changed = None

        self.on_deathlink = None
        self._deathlink_tag_enabled = False
        self.death_link_weights = []
        self.death_link_amnesty = 0
        self._deathlink_amnesty_left = 0

        self.on_item_received = None
        self._last_item_index = 0

        self.seed_name = ""
        self.sent_item_names = []
        self.sent_player_names = []

        self.progressive_groups = []
        self.reward_progressive_group = []
        self.task_progressive_reqs = []

        # persist received notification state
        self._notify_state_path = Path.cwd() / "taskipelago_notify_state.json"
        self._notify_key = None
        self._loaded_notify_index = False
        self._pending_notify_index = None  # type: int | None

    def apply_slot_data(self, slot_data: dict):
        self.slot_data = slot_data or {}
        self.tasks = list(self.slot_data.get("tasks", []))
        self.rewards = list(self.slot_data.get("rewards", []))
        self.task_prereqs = list(self.slot_data.get("task_prereqs", []))
        self.reward_prereqs = list(self.slot_data.get("reward_prereqs", []))
        self.lock_prereqs = bool(self.slot_data.get("lock_prereqs", False))
        self.hide_unreachable_tasks = bool(self.slot_data.get("hide_unreachable_tasks", True))
        self.goal_indices = list(self.slot_data.get("goal_indices", []) or [])
        self.goal_expression = str(self.slot_data.get("goal_expression", "") or "")

        self.base_reward_location_id = self.slot_data.get("base_reward_location_id")
        self.base_complete_location_id = self.slot_data.get("base_complete_location_id")
        self.base_item_id = self.slot_data.get("base_item_id")

        self.death_link_pool = list(self.slot_data.get("death_link_pool", []))
        self.death_link_weights = list(self.slot_data.get("death_link_weights", []))
        self.death_link_amnesty = int(self.slot_data.get("death_link_amnesty", 0) or 0)
        self.death_link_enabled = bool(self.slot_data.get("death_link_enabled", False))

        self.seed_name = str(self.slot_data.get("seed_name", "") or "")

        self.sent_item_names = list(self.slot_data.get("sent_item_names", []))
        self.sent_player_names = list(self.slot_data.get("sent_player_names", []))

        self.progressive_groups = list(self.slot_data.get("progressive_groups", []) or [])
        self.reward_progressive_group = list(self.slot_data.get("reward_progressive_group", []) or [])
        self.task_progressive_reqs = list(self.slot_data.get("task_progressive_reqs", []) or [])

        if callable(self.on_state_changed):
            self.on_state_changed()

    def on_package(self, cmd: str, args: dict):
        super().on_package(cmd, args)

        if "checked_locations" in args and isinstance(args["checked_locations"], (list, set, tuple)):
            self.checked_locations_set.update(args["checked_locations"])

        base_checked = getattr(self, "locations_checked", None)
        if isinstance(base_checked, set):
            self.checked_locations_set.update(base_checked)

        if cmd == "Connected":
            # Apply slot data on connection
            self.apply_slot_data(args.get("slot_data", {}))
            if self.slot_data.get("death_link_enabled"):
                asyncio.create_task(self.enable_deathlink_tag())

            # Load persisted "already notified" index for this server+slot.
            # Apply it when we see the first ReceivedItems after connect.
            self._loaded_notify_index = False
            self._pending_notify_index = self.load_last_notified_index()

            async def _double_sync():
                await self.send_msgs([{"cmd": "Sync"}])
                await asyncio.sleep(0.25)
                await self.send_msgs([{"cmd": "Sync"}])

            asyncio.create_task(_double_sync())

        if cmd in ("Connected", "RoomUpdate", "Sync", "ReceivedItems"):
            if callable(self.on_state_changed):
                self.on_state_changed()

        if cmd == "Bounced":
            tags = args.get("tags") or []
            if "DeathLink" in tags:
                data = args.get("data") or {}
                if callable(self.on_deathlink):
                    self.on_deathlink(data)

        if cmd == "ReceivedItems":
            # Archipelago sends deltas as: {"index": <start>, "items": [ ... ]}
            try:
                packet_index = int(args.get("index", 0) or 0)
            except Exception:
                packet_index = 0

            packet_items = list(args.get("items") or [])
            packet_end = packet_index + len(packet_items)

            # First ReceivedItems after connect: establish baseline using absolute server index.
            if not self._loaded_notify_index:
                self._loaded_notify_index = True

                if isinstance(self._pending_notify_index, int):
                    # Resume from previously-notified absolute index
                    self._last_item_index = max(0, int(self._pending_notify_index))
                else:
                    # First time on this machine: skip ALL history by setting baseline to end of this packet.
                    self._last_item_index = packet_end

                # Persist immediately so reconnect/crash doesn't replay history
                self.save_last_notified_index(self._last_item_index)

            # Detect server restart
            if packet_end < self._last_item_index:
                # reset local cursor to the start of this packet so we process it
                self._last_item_index = packet_index
                self.save_last_notified_index(self._last_item_index, force=True)

            # If this packet ends at/before what we've already shown, nothing new
            if packet_end <= self._last_item_index:
                return

            # Compute overlap: how many items in this packet have we already notified?
            # If _last_item_index is inside this packet range, skip up to that point.
            already_notified_in_packet = max(0, self._last_item_index - packet_index)

            new_items = packet_items[already_notified_in_packet:]

            # Advance last notified absolute index to end of packet
            self._last_item_index = packet_end
            self.save_last_notified_index(self._last_item_index)

            if callable(self.on_item_received) and new_items:
                self.on_item_received(new_items)


    async def enable_deathlink_tag(self):
        # If we aren't connected to a server endpoint yet, bail.
        if not getattr(self, "server", None):
            return

        # Always try at least once per connection; guard only prevents spamming.
        if self._deathlink_tag_enabled:
            return

        self._deathlink_tag_enabled = True
        await self.send_msgs([{"cmd": "ConnectUpdate", "tags": ["DeathLink"]}])

    def _make_notify_key(self) -> str:
        # Slot name is stored in ctx.auth by your connect flow
        server = (self.server_address or "").strip().lower()
        slot = (getattr(self, "auth", None) or "").strip()
        seed = (getattr(self, "seed_name", None) or "").strip()
        return f"v3::{server}::{slot}::{seed}"

    def _load_notify_state(self) -> dict:
        try:
            if self._notify_state_path.exists():
                return json.loads(self._notify_state_path.read_text(encoding="utf-8") or "{}")
        except Exception:
            pass
        return {}

    def _save_notify_state(self, data: dict) -> None:
        try:
            self._notify_state_path.parent.mkdir(parents=True, exist_ok=True)
            self._notify_state_path.write_text(json.dumps(data, indent=2), encoding="utf-8")
        except Exception:
            # Don't crash the client for a persistence failure
            pass

    def load_last_notified_index(self) -> int | None:
        self._notify_key = self._make_notify_key()
        if not self._notify_key.strip(":"):
            return None
        data = self._load_notify_state()
        val = data.get(self._notify_key)
        if isinstance(val, int) and val >= 0:
            return val
        return None

    def save_last_notified_index(self, idx: int, *, force: bool = False) -> None:
        if idx is None:
            return
        if self._notify_key is None:
            self._notify_key = self._make_notify_key()
        if not self._notify_key.strip(":"):
            return

        data = self._load_notify_state()
        prev = data.get(self._notify_key)

        # Only move forward unless forced (used for server reset)
        if not force and isinstance(prev, int) and prev > idx:
            return

        data[self._notify_key] = int(idx)
        self._save_notify_state(data)

    async def disconnect(self):
        # Snapshot current endpoint so it can't be nulled out under us
        endpoint = getattr(self, "server", None)
        if not endpoint:
            return

        # Best-effort tell server we're disconnecting
        try:
            await self.send_msgs([{"cmd": "Disconnect"}])
        except Exception:
            pass

        # Hard close the websocket so server_loop's "async for data in socket" exits
        try:
            sock = getattr(endpoint, "socket", None)
            if sock is not None:
                await sock.close()
        except Exception:
            pass

        # Now clear local endpoint
        self.server = None
        self._deathlink_tag_enabled = False




async def server_loop(ctx: TaskipelagoContext, address: str):
    raw = (address or "").strip()

    # If user didn't provide scheme, try sensible defaults:
    candidates = []
    if "://" in raw:
        candidates.append(raw)
    else:
        host = raw
        # archipelago.gg is typically behind TLS; try wss first
        if "archipelago.gg" in host.lower():
            candidates.append(f"wss://{host}")
        candidates.append(f"ws://{host}")

    last_err = None

    for url in candidates:
        try:
            ssl_ctx = ssl.create_default_context(cafile=certifi.where()) if url.startswith("wss://") else None

            socket = await websockets.connect(
                url,
                ssl=ssl_ctx,
                ping_timeout=None,
                ping_interval=None,
                close_timeout=2,
            )

            ctx.server = Endpoint(socket)

            # ensure every connection will send deathlink tag over
            ctx._deathlink_tag_enabled = False

            await ctx.send_connect()

            async for data in socket:
                for msg in decode(data):
                    await CommonClient.process_server_cmd(ctx, msg)

            # If the server loop exits cleanly, break
            return

        except Exception as e:
            last_err = e
            print(f"[Taskipelago] Connection failed for {url}: {e!r}")
            traceback.print_exc()

    # If we tried all candidates and failed, stash a human-readable reason for UI
    try:
        ctx._last_disconnect_reason = f"{type(last_err).__name__}: {last_err}" if last_err else "Unknown error"
    except Exception:
        pass
    finally:
        if hasattr(ctx, "on_disconnected") and callable(ctx.on_disconnected):
            ctx.on_disconnected()

@dataclass
class Notification:
    kind: str # "reward" | "deathlink" | "sent"
    title: str
    body: str
    created_at: float # time.time()

# ----------------------------
# Main app
# ----------------------------
class TaskipelagoApp(tk.Tk):
    def __init__(self):
        super().__init__()

        self.title("Taskipelago")
        self.geometry("1080x740")
        self.minsize(950, 640)

        self.colors = apply_dark_theme(self)
        ScrollableFrame.bind_mousewheel_to_root(self)

        # Connection/UI state
        self.connection_state = "disconnected"
        self.sent_goal = False
        self.pending_reward_locations = set()  # only track reward loc pending (UI completion)

        # Dedupe popups
        self._last_deathlink_key = None
        self._last_deathlink_seen_at = 0.0
        self._last_reward_key = None
        self._last_reward_seen_at = 0.0
        self._last_sent_key = None
        self._last_sent_seen_at = 0.0

        # YAML generator state
        self.task_rows = []
        self.deathlink_rows = []
        self.prog_groups: list = []  # defined progressive group names

        # Notifications state
        self._notifications: list[Notification] = []
        self._max_notifications = 200  # keep memory bounded

        notebook = ttk.Notebook(self)
        notebook.pack(fill="both", expand=True)

        self.play_tab = ttk.Frame(notebook)
        notebook.add(self.play_tab, text="Connect and Play")

        self.editor_tab = ttk.Frame(notebook)
        notebook.add(self.editor_tab, text="YAML Generator")

        notebook.select(self.play_tab)

        # Async loop thread
        self.loop = asyncio.new_event_loop()
        t = threading.Thread(target=self._run_async_loop, daemon=True)
        t.start()

        def _init_ctx():
            self.ctx = TaskipelagoContext()
            self.ctx.on_state_changed = self.on_network_update
            self.ctx.on_disconnected = self.on_server_disconnected
            self.ctx.on_deathlink = self.on_deathlink_received
            self.ctx.on_item_received = self.on_items_received

        self.loop.call_soon_threadsafe(_init_ctx)

        self.build_ui()

    # ---------------- UI layout ----------------
    def build_ui(self):
        # YAML tab layout
        self.editor_tab.grid_columnconfigure(0, weight=1)
        self.editor_tab.grid_rowconfigure(0, weight=0)   # meta / global settings
        self.editor_tab.grid_rowconfigure(1, weight=0)   # progressive groups
        self.editor_tab.grid_rowconfigure(2, weight=1, minsize=220)  # tasks
        self.editor_tab.grid_rowconfigure(3, weight=1, minsize=160)  # deathlink
        self.editor_tab.grid_rowconfigure(4, weight=0, minsize=52)   # buttons

        meta = ttk.LabelFrame(self.editor_tab, text="Player / Global Settings")
        meta.grid(row=0, column=0, sticky="ew", pady=(0, 10))
        meta.grid_columnconfigure(1, weight=1)

        ttk.Label(meta, text="Player Name:").grid(row=0, column=0, padx=10, pady=8, sticky="w")
        self.player_name_var = tk.StringVar()
        ttk.Entry(meta, textvariable=self.player_name_var).grid(row=0, column=1, sticky="ew", padx=(0, 10), pady=8)

        ttk.Label(meta, text="Progression Balancing (0–99):").grid(row=0, column=2, padx=(0, 10), pady=8, sticky="w")
        self.progression_var = tk.IntVar(value=50)
        ttk.Spinbox(meta, from_=0, to=99, textvariable=self.progression_var, width=5).grid(row=0, column=3, pady=8)

        ttk.Label(meta, text="Accessibility:").grid(row=0, column=4, padx=(0, 10), pady=8, sticky="w")
        self.accessibility_var = tk.StringVar(value="full")
        ttk.Combobox(
            meta,
            textvariable=self.accessibility_var,
            values=["full", "items", "minimal"],
            state="readonly",
            width=10,
        ).grid(row=0, column=5, pady=8)

        meta_row2 = ttk.Frame(meta)
        meta_row2.grid(row=1, column=0, columnspan=6, sticky="w", padx=10, pady=(0, 10))

        self.deathlink_enabled = tk.BooleanVar(value=False)
        ttk.Checkbutton(meta_row2, text="Enable DeathLink", variable=self.deathlink_enabled).grid(row=0, column=0, sticky="w")

        self.hide_unreachable_tasks = tk.BooleanVar(value=True)
        ttk.Checkbutton(meta_row2, text="Hide Unreachable Tasks", variable=self.hide_unreachable_tasks).grid(row=0, column=1, sticky="w")

        ttk.Label(meta_row2, text="DeathLink amnesty:").grid(row=0, column=2, sticky="w", padx=(16, 0))
        self.deathlink_amnesty_var = tk.IntVar(value=0)
        ttk.Spinbox(meta_row2, from_=0, to=999, textvariable=self.deathlink_amnesty_var, width=5).grid(
            row=0, column=3, sticky="w", padx=(6, 0)
        )

        self.lock_prereqs_var = tk.BooleanVar(value=True)
        ttk.Checkbutton(meta_row2, text="In logic only (lock task completion behind prereqs)", variable=self.lock_prereqs_var).grid(row=0, column=4, sticky="w", padx=(16, 0))

        ttk.Label(meta_row2, text="Goal task(s):").grid(row=0, column=5, sticky="w", padx=(16, 0))
        self.goal_tasks_var = tk.StringVar()
        ttk.Entry(meta_row2, textvariable=self.goal_tasks_var, width=16).grid(
            row=0, column=6, sticky="w", padx=(6, 0)
        )
        ttk.Label(meta_row2, text="(blank = all)", style="Muted.TLabel").grid(
            row=0, column=7, sticky="w", padx=(4, 0)
        )

        # --- Progressive Groups panel (row 1) ---
        prog_frame = ttk.LabelFrame(self.editor_tab, text="Progressive Groups")
        prog_frame.grid(row=1, column=0, sticky="ew", pady=(0, 6))
        prog_frame.grid_columnconfigure(0, weight=1)

        self.prog_chips_frame = ttk.Frame(prog_frame)
        self.prog_chips_frame.grid(row=0, column=0, sticky="w", padx=10, pady=(6, 4))

        add_row = ttk.Frame(prog_frame)
        add_row.grid(row=1, column=0, sticky="w", padx=10, pady=(0, 8))
        ttk.Label(add_row, text="New group name:").pack(side="left", padx=(0, 6))
        self.new_group_var = tk.StringVar()
        new_group_entry = ttk.Entry(add_row, textvariable=self.new_group_var, width=18)
        new_group_entry.pack(side="left", padx=(0, 6))
        new_group_entry.bind("<Return>", lambda _: self._add_prog_group())
        ttk.Button(add_row, text="Add Group", command=self._add_prog_group).pack(side="left")
        _pg_hint = ttk.Label(add_row, text="(letters, underscores, hyphens — no digits)", style="Muted.TLabel", cursor="question_arrow")
        _pg_hint.pack(side="left", padx=(8, 0))
        Tooltip(_pg_hint, (
            "Group names may only contain letters, underscores, and hyphens — no digits.\n\n"
            "Reference a group in the 'Reward prereqs' column using the group name:\n"
            "  mygroup    →  require 1 item from 'mygroup'\n"
            "  mygroup-2  →  require 2 items from 'mygroup'\n\n"
            "Receiving any item assigned to a group counts toward that group's total.\n"
            "All group items are forced to 'progression' classification."
        ))

        self._refresh_prog_groups_panel()

        # --- Tasks table (row 2) ---
        tasks = ttk.LabelFrame(self.editor_tab, text="Tasks")
        tasks.grid(row=2, column=0, sticky="nsew", pady=(0, 10))
        tasks.grid_columnconfigure(0, weight=1)
        tasks.grid_rowconfigure(0, weight=0, minsize=28)
        tasks.grid_rowconfigure(1, weight=1)
        tasks.grid_rowconfigure(2, weight=0, minsize=44)

        self.tasks_scroll = ScrollableFrame(tasks, colors=self.colors)
        self.tasks_scroll.grid(row=1, column=0, sticky="nsew", padx=10, pady=0)

        tbl = self.tasks_scroll.inner

        ttk.Label(tbl, text="#").grid(row=0, column=0, sticky="w", padx=(0, 8))
        ttk.Label(tbl, text="Task").grid(row=0, column=1, sticky="w", padx=(0, 8))
        ttk.Label(tbl, text="Reward / Challenge").grid(row=0, column=2, sticky="w", padx=(0, 8))
        _task_prereq_tip = (
            "Which tasks must be COMPLETED before this task can be checked off.\n\n"
            "Format: comma-separated task numbers, or use boolean logic:\n"
            "  1, 2, 5       →  tasks 1 AND 2 AND 5\n"
            "  1 && 2        →  tasks 1 AND 2\n"
            "  1 || 2        →  task 1 OR task 2\n"
            "  (1 || 2) && 3 →  (1 or 2) and also 3"
        )
        _reward_prereq_tip = (
            "Which task REWARDS must be received before this task can be checked off.\n\n"
            "Supports the same boolean logic as Task prereqs, plus progressive group refs:\n"
            "  1, 2       →  rewards 1 AND 2 required\n"
            "  1 || 2     →  reward 1 OR reward 2\n"
            "  mygroup    →  1 item from 'mygroup' required\n"
            "  mygroup-2  →  2 items from 'mygroup' required"
        )
        _type_tip = (
            "Item classification for the Archipelago multiworld:\n\n"
            "  junk        — low-priority filler item\n"
            "  useful      — helpful but not sphere-gating\n"
            "  progression — placed early; advances sphere logic\n"
            "  trap        — negative-effect item\n\n"
            "Rewards in a progressive group are always forced to 'progression'."
        )
        _filler_tip = (
            "Mark this task as a filler task.\n\n"
            "Filler tasks grant no item to the multiworld. The task can still be "
            "completed and count toward prerequisites, but the reward slot is empty."
        )
        _prog_group_tip = (
            "Assign this reward to a progressive group.\n\n"
            "Group items are interchangeable — receiving any of them increments the group "
            "counter. Other tasks can require N items from the group in 'Reward prereqs':\n"
            "  groupname    →  require 1 item from the group\n"
            "  groupname-2  →  require 2 items from the group\n\n"
            "Items in a group are always forced to 'progression' classification.\n"
            "Groups are defined in the Progressive Groups panel above."
        )
        _make_tip_header(tbl, "Task prereqs",  _task_prereq_tip).grid(row=0, column=3, sticky="w", padx=(0, 8))
        _make_tip_header(tbl, "Reward prereqs", _reward_prereq_tip).grid(row=0, column=4, sticky="w", padx=(0, 8))
        _make_tip_header(tbl, "Type",          _type_tip).grid(row=0, column=5, sticky="w", padx=(0, 8))
        _make_tip_header(tbl, "Filler",        _filler_tip).grid(row=0, column=6, sticky="w", padx=(0, 4))
        _make_tip_header(tbl, "Prog. Group",   _prog_group_tip).grid(row=0, column=7, sticky="w", padx=(0, 8))
        ttk.Label(tbl, text="").grid(row=0, column=8, sticky="w")   # Remove (no header)

        # Muted hint text
        ttk.Label(tbl, text="", style="Muted.TLabel").grid(row=1, column=0, sticky="w", padx=(0, 8))
        ttk.Label(tbl, text="Location", style="Muted.TLabel").grid(row=1, column=1, sticky="w", padx=(0, 8))
        ttk.Label(tbl, text="Item", style="Muted.TLabel").grid(row=1, column=2, sticky="w", padx=(0, 8))
        ttk.Label(tbl, text="1  or  1, 2, 5", style="Muted.TLabel").grid(row=1, column=3, sticky="w", padx=(0, 8))
        ttk.Label(tbl, text="1  or  prog  or  prog-2", style="Muted.TLabel").grid(row=1, column=4, sticky="w", padx=(0, 8))
        ttk.Label(tbl, text="", style="Muted.TLabel").grid(row=1, column=5, sticky="w", padx=(0, 8))
        ttk.Label(tbl, text="", style="Muted.TLabel").grid(row=1, column=6, sticky="w")
        ttk.Label(tbl, text="", style="Muted.TLabel").grid(row=1, column=7, sticky="w")
        ttk.Label(tbl, text="", style="Muted.TLabel").grid(row=1, column=8, sticky="w")

        tbl.grid_columnconfigure(0, weight=0)   # #
        tbl.grid_columnconfigure(1, weight=3)   # Task
        tbl.grid_columnconfigure(2, weight=3)   # Reward
        tbl.grid_columnconfigure(3, weight=2)   # Task prereqs
        tbl.grid_columnconfigure(4, weight=2)   # Reward prereqs
        tbl.grid_columnconfigure(5, weight=1)   # Type
        tbl.grid_columnconfigure(6, weight=0)   # Filler
        tbl.grid_columnconfigure(7, weight=1)   # Prog. Group
        tbl.grid_columnconfigure(8, weight=0)   # Remove button

        btn_row = ttk.Frame(tasks)
        btn_row.grid(row=2, column=0, sticky="ew", padx=10, pady=(0, 10))
        ttk.Button(btn_row, text="Add Task", command=self.add_task_row).pack(side="left")

        dl = ttk.LabelFrame(self.editor_tab, text="DeathLink Task Pool")
        dl.grid(row=3, column=0, sticky="nsew")
        dl.grid_columnconfigure(0, weight=1)
        dl.grid_rowconfigure(0, weight=1)
        dl.grid_rowconfigure(1, weight=0, minsize=44)

        self.dl_scroll = ScrollableFrame(dl, colors=self.colors)
        self.dl_scroll.grid(row=0, column=0, sticky="nsew", padx=10, pady=10)

        dl_tbl = self.dl_scroll.inner
        dl_tbl.grid_columnconfigure(0, weight=1)  # task text expands
        dl_tbl.grid_columnconfigure(1, weight=0)  # weight fixed
        dl_tbl.grid_columnconfigure(2, weight=0)  # remove fixed

        ttk.Label(dl_tbl, text="DeathLink Task").grid(row=0, column=0, sticky="w", padx=(0, 8))
        # Label can extend over Remove column per your request
        ttk.Label(dl_tbl, text="Weight").grid(row=0, column=1, columnspan=2, sticky="w")

        ttk.Button(dl, text="Add DeathLink Task", command=self.add_deathlink_row).grid(row=1, column=0, sticky="w", padx=10, pady=(0, 10))

        bottom = ttk.Frame(self.editor_tab)
        bottom.grid(row=4, column=0, sticky="ew", pady=(10, 0))
        bottom.grid_columnconfigure(0, weight=1)
        ttk.Button(bottom, text="Reset", command=self.reset_yaml_generator).grid(
            row=0, column=0, sticky="w", padx=(10, 0)
        )
        ttk.Button(bottom, text="Import YAML", command=self.import_yaml).grid(
            row=0, column=1, sticky="e", padx=(0, 6)
        )
        ttk.Button(bottom, text="Export YAML", command=self.export_yaml).grid(
            row=0, column=2, sticky="e", padx=(0, 10)
        )

        self.add_task_row()

        # Play tab
        play_root = ttk.Frame(self.play_tab)
        play_root.pack(fill="both", expand=True, padx=10, pady=10)

        # Split: left main + right notifications
        play_root.grid_columnconfigure(0, weight=3)
        play_root.grid_columnconfigure(1, weight=1)
        play_root.grid_rowconfigure(2, weight=1) # tasks row grows

        conn_frame = ttk.LabelFrame(play_root, text="Connection")
        conn_frame.grid(row=0, column=0, sticky="ew", pady=(0, 10), padx=(0, 10))
        # conn_frame.pack(fill="x", pady=(0, 10))

        last = self._load_last_connection()
        server_default = str(last.get("server") or "archipelago.gg")
        slot_default = str(last.get("slot") or "")

        ttk.Label(conn_frame, text="Server (host:port):").grid(row=0, column=0, sticky="w", padx=5, pady=5)
        self.server_var = tk.StringVar(value=server_default)
        ttk.Entry(conn_frame, textvariable=self.server_var, width=30).grid(row=0, column=1, padx=5)

        ttk.Label(conn_frame, text="Slot Name:").grid(row=1, column=0, sticky="w", padx=5, pady=5)
        self.slot_var = tk.StringVar(value=slot_default)
        ttk.Entry(conn_frame, textvariable=self.slot_var, width=30).grid(row=1, column=1, padx=5)

        ttk.Label(conn_frame, text="Password:").grid(row=2, column=0, sticky="w", padx=5, pady=5)
        self.pass_var = tk.StringVar()
        ttk.Entry(conn_frame, textvariable=self.pass_var, width=30, show="*").grid(row=2, column=1, padx=5)

        btns = ttk.Frame(conn_frame)
        btns.grid(row=3, column=0, columnspan=2, sticky="w", padx=5, pady=(8, 0))

        self.connect_button = ttk.Button(btns, text="Connect", command=self.on_connect_toggle)
        self.connect_button.pack(side="left")

        self.connect_status = tk.StringVar(value="Not connected.")
        # ttk.Label(play_root, textvariable=self.connect_status).pack(anchor="w")
        ttk.Label(play_root, textvariable=self.connect_status).grid(row=1, column=0, sticky="w", padx=(0, 10))

        tasks_frame = ttk.LabelFrame(play_root, text="Tasks")
        tasks_frame.grid(row=2, column=0, sticky="nsew", padx=(0, 10), pady=(10, 0))

        self.play_tasks_scroll = ScrollableFrame(tasks_frame, colors=self.colors)
        self.play_tasks_scroll.pack(fill="both", expand=True, padx=10, pady=10)

        # ---- Notifications panel ----
        notif_frame = ttk.LabelFrame(play_root, text="Notifications")
        notif_frame.grid(row=0, column=1, rowspan=3, sticky="nsew")
        notif_frame.grid_rowconfigure(1, weight=1)
        notif_frame.grid_columnconfigure(0, weight=1)

        notif_btns = ttk.Frame(notif_frame)
        notif_btns.grid(row=0, column=0, sticky="ew", padx=10, pady=(0, 0))
        ttk.Button(notif_btns, text="Clear", command=self._clear_notifications).pack(side="left")

        self.notif_scroll = ScrollableFrame(notif_frame, colors=self.colors)
        self.notif_scroll.grid(row=1, column=0, sticky="nsew", padx=10, pady=10)


    # ---------------- YAML generator actions ----------------
    def add_task_row(self):
        row = TaskRow(
            self.tasks_scroll.inner,
            len(self.task_rows) + 1,
            FILLER_TOKEN,
            self._remove_task_row,
            list(self.prog_groups),
        )
        self.task_rows.append(row)
        return row

    # ---------------- Progressive groups management ----------------
    def _add_prog_group(self):
        name = self.new_group_var.get().strip()
        if not name:
            messagebox.showerror("Error", "Group name cannot be empty.")
            return
        if re.search(r'\d', name):
            messagebox.showerror("Error", f"Group name '{name}' must not contain digits.")
            return
        if name in self.prog_groups:
            messagebox.showerror("Error", f"Progressive group '{name}' already exists.")
            return
        self.prog_groups.append(name)
        self.new_group_var.set("")
        self._refresh_prog_groups_panel()
        self._update_all_task_row_prog_groups()

    def _remove_prog_group(self, gname: str):
        if gname in self.prog_groups:
            self.prog_groups.remove(gname)
        for row in self.task_rows:
            if row.prog_group_var.get() == gname:
                row.prog_group_var.set("")
        self._refresh_prog_groups_panel()
        self._update_all_task_row_prog_groups()

    def _refresh_prog_groups_panel(self):
        if not hasattr(self, "prog_chips_frame"):
            return
        for w in self.prog_chips_frame.winfo_children():
            w.destroy()
        if not self.prog_groups:
            ttk.Label(self.prog_chips_frame, text="No groups defined.", style="Muted.TLabel").pack(side="left")
            return
        for gname in self.prog_groups:
            chip = ttk.Frame(self.prog_chips_frame)
            chip.pack(side="left", padx=(0, 6))
            ttk.Label(chip, text=gname).pack(side="left", padx=(6, 2), pady=2)
            ttk.Button(
                chip, text="×", width=2,
                command=lambda g=gname: self._remove_prog_group(g),
            ).pack(side="left", padx=(0, 2))

    def _update_all_task_row_prog_groups(self):
        for row in self.task_rows:
            row.update_groups(self.prog_groups)

    def _remove_task_row(self, row):
        if row in self.task_rows:
            self.task_rows.remove(row)

        for i, r in enumerate(self.task_rows, start=1):
            r.index = i
            r.num_label.config(text=str(i))
            r._grid() # re-place widgets on the correct grid row
    
    def _clear_task_rows(self):
        # Destroy existing widgets for all task rows and forget them
        for r in list(self.task_rows):
            try:
                r.remove()  # calls destroy + _on_remove
            except Exception:
                pass
        self.task_rows = []

    def add_deathlink_row(self):
        # rows start at 1 because header is row 0
        row = DeathLinkRow(self.dl_scroll.inner, len(self.deathlink_rows) + 1, self._remove_deathlink_row)
        self.deathlink_rows.append(row)

    def _remove_deathlink_row(self, row):
        if row in self.deathlink_rows:
            self.deathlink_rows.remove(row)

        for i, r in enumerate(self.deathlink_rows, start=1):
            r.index = i
            r._grid()

    def _clear_deathlink_rows(self):
        for r in list(self.deathlink_rows):
            try:
                r.remove()
            except Exception:
                pass
        self.deathlink_rows = []

    def _extract_taskipelago_block(self, doc: dict):
        """
        Supports:
          A) Your generator format (root has 'name' + 'Taskipelago')
          B) Common AP format-ish (root has a player name key; inside has 'Taskipelago')
        Returns: (player_name: str|None, block: dict|None)
        """
        if not isinstance(doc, dict):
            return None, None

        # A) direct
        if isinstance(doc.get("Taskipelago"), dict):
            player_name = doc.get("name")
            if isinstance(player_name, str):
                player_name = player_name.strip()
            else:
                player_name = None
            return player_name, doc["Taskipelago"]

        # B) nested: find any mapping that contains a Taskipelago dict
        # e.g. { "Barret": { "Taskipelago": {...}} }
        for k, v in doc.items():
            if isinstance(v, dict) and isinstance(v.get("Taskipelago"), dict):
                player_name = k if isinstance(k, str) else None
                return player_name, v["Taskipelago"]

        return None, None

    def export_yaml(self):
        player_name = self.player_name_var.get().strip()
        if not player_name:
            messagebox.showerror("Error", "Player name is required.")
            return

        tasks, rewards, prereqs, reward_prereqs, reward_types, reward_prog_groups = [], [], [], [], [], []
        for r in self.task_rows:
            t, rw, pr, rpr, filler, rtype, pgrp = r.get_data()
            if not t:
                continue
            if not rw:
                filler = True

            tasks.append(t)
            rewards.append(FILLER_TOKEN if filler else rw)
            prereqs.append(pr or "")
            reward_prereqs.append(rpr or "")
            reward_types.append("junk" if filler else (rtype or "junk"))
            reward_prog_groups.append(pgrp if not filler else "")

        if not tasks:
            messagebox.showerror("Error", "No tasks defined.")
            return

        deathlink_pool = []
        deathlink_weights = []
        for r in self.deathlink_rows:
            txt, wtxt = r.get_data()
            if not txt:
                continue
            deathlink_pool.append(txt)
            deathlink_weights.append(wtxt if wtxt else "1")


        if self.deathlink_enabled.get():
            on_w, off_w = 50, 0
        else:
            on_w, off_w = 0, 50

        if self.deathlink_enabled.get() and not deathlink_pool:
            messagebox.showerror(
                "Error",
                "DeathLink is enabled, but the DeathLink Task Pool is empty.\n"
                "Add at least one DeathLink task or disable DeathLink."
            )
            return
        
        goal_tasks_raw = self.goal_tasks_var.get().strip()

        data = {
            "name": player_name,
            "game": "Taskipelago",
            "description": "YAML template for Taskipelago",
            "Taskipelago": {
                "progression_balancing": int(self.progression_var.get()),
                "accessibility": self.accessibility_var.get(),
                "death_link": {"true": on_w, "false": off_w},

                "progressive_groups": list(self.prog_groups),
                "reward_progressive_group": reward_prog_groups,

                "tasks": tasks,
                "rewards": rewards,
                "reward_types": reward_types,
                "task_prereqs": prereqs,
                "reward_prereqs": reward_prereqs,
                "lock_prereqs": bool(self.lock_prereqs_var.get()),
                "hide_unreachable_tasks": bool(self.hide_unreachable_tasks.get()),
                "goal_tasks": [goal_tasks_raw] if goal_tasks_raw else [],

                "death_link_pool": deathlink_pool,
                "death_link_weights": deathlink_weights,
                "death_link_amnesty": int(self.deathlink_amnesty_var.get()),
            }
        }

        path = filedialog.asksaveasfilename(defaultextension=".yaml", filetypes=[("YAML Files", "*.yaml")])
        if not path:
            return

        with open(path, "w", encoding="utf-8") as f:
            yaml.dump(data, f, sort_keys=False, allow_unicode=True)

        messagebox.showinfo("Success", f"YAML exported to:\n{path}")

    def import_yaml(self):
        path = filedialog.askopenfilename(filetypes=[("YAML Files", "*.yaml *.yml"), ("All Files", "*.*")])
        if not path:
            return

        try:
            with open(path, "r", encoding="utf-8") as f:
                doc = yaml.safe_load(f)
        except Exception as e:
            messagebox.showerror("Error", f"Failed to read YAML:\n{e}")
            return

        player_name, block = self._extract_taskipelago_block(doc)
        if not isinstance(block, dict):
            messagebox.showerror(
                "Error",
                "Could not find a 'Taskipelago' section in this YAML.\n"
                "Expected either:\n"
                "  - root: { name: ..., Taskipelago: {...} }\n"
                "  - or a player entry: { <player>: { Taskipelago: {...} } }"
            )
            return

        # --------- Populate global settings ---------
        if player_name:
            self.player_name_var.set(player_name)

        pb = block.get("progression_balancing", self.progression_var.get())
        try:
            self.progression_var.set(int(pb))
        except Exception:
            pass

        acc = block.get("accessibility", self.accessibility_var.get())
        if isinstance(acc, str) and acc.strip():
            self.accessibility_var.set(acc.strip())

        # death_link stored as weights: {"true": X, "false": Y}
        dl = block.get("death_link", None)
        enabled = bool(self.deathlink_enabled.get())
        if isinstance(dl, dict):
            try:
                t = int(dl.get("true", 0) or 0)
                f = int(dl.get("false", 0) or 0)
                enabled = (t > 0) and (t >= f)
            except Exception:
                pass
        elif isinstance(dl, (bool, int)):
            enabled = bool(dl)
        self.deathlink_enabled.set(enabled)

        try:
            self.deathlink_amnesty_var.set(int(block.get("death_link_amnesty", self.deathlink_amnesty_var.get()) or 0))
        except Exception:
            pass

        self.lock_prereqs_var.set(bool(block.get("lock_prereqs", self.lock_prereqs_var.get())))

        self.hide_unreachable_tasks.set(bool(block.get("hide_unreachable_tasks", self.hide_unreachable_tasks.get())))
        
        goal_tasks = list(block.get("goal_tasks", []) or [])
        self.goal_tasks_var.set(", ".join(str(g) for g in goal_tasks))

        # --------- Progressive groups (must be loaded before task rows) ---------
        raw_pg = list(block.get("progressive_groups", []) or [])
        self.prog_groups = [str(g).strip() for g in raw_pg if str(g).strip()]
        self._refresh_prog_groups_panel()

        # --------- Populate Tasks table ---------
        tasks = list(block.get("tasks", []) or [])
        rewards = list(block.get("rewards", []) or [])
        prereqs = list(block.get("task_prereqs", []) or [])
        reward_prereqs = list(block.get("reward_prereqs", []) or [])
        reward_types = list(block.get("reward_types", []) or [])
        reward_prog_group = list(block.get("reward_progressive_group", []) or [])

        # Normalize lengths
        n = max(len(tasks), len(rewards), len(prereqs))
        tasks += [""] * (n - len(tasks))
        rewards += [""] * (n - len(rewards))
        prereqs += [""] * (n - len(prereqs))
        reward_prereqs += [""] * (n - len(reward_prereqs))
        reward_types += ["useful"] * (n - len(reward_types))
        reward_prog_group += [""] * (n - len(reward_prog_group))

        # Wipe existing UI rows then rebuild
        self._clear_task_rows()

        for i in range(n):
            t = str(tasks[i]).strip() if tasks[i] is not None else ""
            rw = str(rewards[i]).strip() if rewards[i] is not None else ""
            pr = str(prereqs[i]).strip() if prereqs[i] is not None else ""
            rpr = str(reward_prereqs[i]).strip() if reward_prereqs[i] is not None else ""
            rt = str(reward_types[i]).strip().lower() if reward_types[i] is not None else "useful"
            pgrp = str(reward_prog_group[i]).strip() if reward_prog_group[i] is not None else ""

            row = self.add_task_row()  # creates row with current self.prog_groups
            row.task_var.set(t)
            row.prereq_var.set(pr)
            row.reward_prereq_var.set(rpr)

            # Clamp reward type
            if rt not in ("trap", "junk", "useful", "progression"):
                rt = "useful"
            row.reward_type_var.set(rt)
            row._saved_reward_type = rt

            # Handle filler token
            if rw == FILLER_TOKEN:
                row.filler_var.set(True)
                row.on_filler_toggle()
            else:
                row.filler_var.set(False)
                row.on_filler_toggle()
                row.reward_var.set(rw)
                if not self.task_rows:
                    self.add_task_row()

            # Set progressive group after filler toggle so _on_prog_group_change fires correctly
            if pgrp in self.prog_groups:
                row.prog_group_var.set(pgrp)

        # --------- Populate DeathLink pool ---------
        deathlink_pool = list(block.get("death_link_pool", []) or [])
        deathlink_weights = list(block.get("death_link_weights", []) or [])

        # Normalize weights to pool length (default "1")
        if len(deathlink_weights) < len(deathlink_pool):
            deathlink_weights += ["1"] * (len(deathlink_pool) - len(deathlink_weights))
        deathlink_weights = deathlink_weights[:len(deathlink_pool)]

        self._clear_deathlink_rows()

        for i, txt in enumerate(deathlink_pool):
            s = str(txt).strip() if txt is not None else ""
            if not s:
                continue
            w = deathlink_weights[i]
            wtxt = str(w).strip() if w is not None else "1"
            if not wtxt:
                wtxt = "1"

            row = DeathLinkRow(self.dl_scroll.inner, len(self.deathlink_rows) + 1, self._remove_deathlink_row)
            self.deathlink_rows.append(row)
            row.text_var.set(s)
            row.weight_var.set(wtxt)

        messagebox.showinfo("Imported", f"Imported YAML from:\n{path}")

    def reset_yaml_generator(self):
        # reset to defaults
        self.player_name_var.set("")
        self.progression_var.set(50)
        self.accessibility_var.set("full")
        self.deathlink_enabled.set(True)
        self.deathlink_amnesty_var.set(0)
        self.lock_prereqs_var.set(False)
        self.hide_unreachable_tasks.set(True)
        self.goal_tasks_var.set("")

        self.prog_groups = []
        self._refresh_prog_groups_panel()

        self._clear_task_rows()
        self._clear_deathlink_rows()
        self.add_task_row()

    # ---------------- Connection actions ----------------
    def on_connect_toggle(self):
        if self.connection_state == "disconnected":
            self._start_connect()
        else:
            self._start_disconnect()

    def _start_connect(self):
        if self.connection_state != "disconnected":
            return

        self.sent_goal = False

        server = self.server_var.get().strip()
        slot = self.slot_var.get().strip()
        password = self.pass_var.get().strip() or None

        if not server or not slot:
            messagebox.showerror("Error", "Server and Slot Name are required.")
            return
        
        # store last connection to restore next load
        self._save_last_connection(server, slot)

        self.connection_state = "connecting"
        self.connect_status.set(f"Connecting to {server} as {slot}...")
        self.connect_button.config(text="Disconnect")

        def _start():
            self.ctx.server_address = server
            self.ctx.auth = slot
            self.ctx.password = password
            asyncio.create_task(server_loop(self.ctx, server))

        self.loop.call_soon_threadsafe(_start)

    def _start_disconnect(self):
        if self.connection_state == "disconnected":
            return

        self.connection_state = "disconnected"
        self.connect_status.set("Disconnected.")
        self.connect_button.config(text="Connect")
        self.sent_goal = False

        if getattr(self, "ctx", None) and self.ctx.server:
            async def _do_disconnect():
                await self.ctx.disconnect()

            self.loop.call_soon_threadsafe(lambda: asyncio.create_task(_do_disconnect()))

        if getattr(self, "ctx", None):
            self.ctx._deathlink_tag_enabled = False

        self.after(0, self._clear_play_state)

    def _clear_play_state(self):
        self.pending_reward_locations = set()
        if getattr(self, "ctx", None):
            self.ctx.tasks = []
            self.ctx.rewards = []
            self.ctx.task_prereqs = []
            self.ctx.lock_prereqs = False
            self.ctx.base_reward_location_id = None
            self.ctx.base_complete_location_id = None
            self.ctx.death_link_pool = []
            self.ctx.death_link_enabled = False
            self.ctx.deathlink_tag_enabled = False
            self.ctx.checked_locations_set = set()
            self.ctx._loaded_notify_index = False
            self.ctx._pending_notify_index = None
            self._deathlink_amnesty_left = 0
            if hasattr(self.ctx, "locations_checked"):
                self.ctx.locations_checked = set()
            self.ctx.progressive_groups = []
            self.ctx.reward_progressive_group = []
            self.ctx.task_progressive_reqs = []
        self.refresh_play_tab()

    # ---------------- Notifications stuff ----------------
    def _clear_notifications(self):
        self._notifications.clear()
        self._render_notifications()

    def _enqueue_notification(self, n: Notification):
        self._notifications.append(n)
        if len(self._notifications) > self._max_notifications:
            self._notifications = self._notifications[-self._max_notifications:]
        self._render_notifications()

    def _dismiss_notification(self, idx: int):
        if 0 <= idx < len(self._notifications):
            self._notifications.pop(idx)
            self._render_notifications()

    def _render_notifications(self):
        if not hasattr(self, "notif_scroll"):
            return

        inner = self.notif_scroll.inner
        for child in inner.winfo_children():
            child.destroy()

        panel = self.colors.get("panel", "#252526")
        border = self.colors.get("border", "#3a3a3a")
        fg = self.colors.get("fg", "#e6e6e6")
        muted = self.colors.get("muted", "#bdbdbd")

        for i, n in enumerate(reversed(self._notifications)):
            # reversed so newest on top
            real_idx = len(self._notifications) - 1 - i

            card = tk.Frame(inner, bg=panel, highlightbackground=border, highlightthickness=1)
            card.pack(fill="x", pady=6, padx=2)

            top = tk.Frame(card, bg=panel)
            top.pack(fill="x", padx=8, pady=(8, 2))

            title = tk.Label(top, text=n.title, bg=panel, fg=fg, font=("Segoe UI", 11, "bold"),
                             anchor="w", justify="left", wraplength=260)
            title.pack(side="left", fill="x", expand=True)

            ttk.Button(top, text="Dismiss", command=lambda ix=real_idx: self._dismiss_notification(ix)).pack(side="right")

            ts = datetime.fromtimestamp(n.created_at).strftime("%H:%M:%S")
            meta = tk.Label(card, text=f"{n.kind.upper()} • {ts}", bg=panel, fg=muted,
                            font=("Segoe UI", 9), anchor="w")
            meta.pack(fill="x", padx=8)

            body = tk.Label(card, text=n.body, bg=panel, fg=fg, font=("Segoe UI", 10),
                            anchor="w", justify="left", wraplength=300)
            body.pack(fill="x", padx=8, pady=(4, 8))
        
    def _last_connection_path(self) -> Path:
        # keep it alongside other per-user state
        return Path.cwd() / "taskipelago_last_connection.json"

    def _load_last_connection(self) -> dict:
        try:
            p = self._last_connection_path()
            if p.exists():
                return json.loads(p.read_text(encoding="utf-8") or "{}") or {}
        except Exception:
            pass
        return {}

    def _save_last_connection(self, server: str, slot: str) -> None:
        try:
            p = self._last_connection_path()
            p.parent.mkdir(parents=True, exist_ok=True)
            p.write_text(json.dumps({"server": server, "slot": slot}, indent=2), encoding="utf-8")
        except Exception:
            # don't crash the client for a persistence failure
            pass

    # ---------------- Async loop plumbing ----------------
    def _run_async_loop(self):
        asyncio.set_event_loop(self.loop)
        self.loop.run_forever()

    # ---------------- Network -> UI updates ----------------
    def on_network_update(self):
        if self.connection_state == "connecting":
            self.connection_state = "connected"
            self.connect_status.set("Connected.")
            self.connect_button.config(text="Disconnect")

        if not getattr(self, "ctx", None):
            return
        
        self._deathlink_amnesty_left = int(getattr(self.ctx, "death_link_amnesty", 0) or 0)

        checked = getattr(self.ctx, "checked_locations_set", set()) or set()
        self.pending_reward_locations.difference_update(checked)

        self._maybe_send_goal_complete()
        self.after(0, self.refresh_play_tab)

    def refresh_play_tab(self):
        for child in self.play_tasks_scroll.inner.winfo_children():
            child.destroy()

        if (
            not getattr(self, "ctx", None)
            or not self.ctx.tasks
            or self.ctx.base_reward_location_id is None
            or self.ctx.base_complete_location_id is None
        ):
            return

        panel = self.colors.get("panel", "#252526")
        border = self.colors.get("border", "#3a3a3a")
        fg = self.colors.get("fg", "#e6e6e6")
        muted = self.colors.get("muted", "#bdbdbd")

        checked = set(getattr(self.ctx, "checked_locations_set", set()) or set())

        prereq_list = list(getattr(self.ctx, "task_prereqs", []) or [])
        reward_prereq_list = list(getattr(self.ctx, "reward_prereqs", []) or [])
        lock_prereqs = bool(getattr(self.ctx, "lock_prereqs", False))

        for i, task_name in enumerate(self.ctx.tasks):
            complete_loc_id = self.ctx.base_complete_location_id + i

            # Consider "completed" when reward location is checked (the one that sends items)
            completed = complete_loc_id in checked

            # task prereqs satisfied based on COMPLETE locations (completion tokens)
            task_prereq_ok = True
            task_prereq_text = ""
            if i < len(prereq_list):
                raw = prereq_list[i]
                task_prereq_text = ("" if raw is None else str(raw)).strip()
                if task_prereq_text:
                    task_prereq_ok = self._prereqs_satisfied(task_prereq_text, checked)

            reward_prereq_list = list(getattr(self.ctx, "reward_prereqs", []) or [])
            reward_prereq_ok = True
            reward_prereq_text = ""
            if i < len(reward_prereq_list):
                raw = reward_prereq_list[i]
                reward_prereq_text = ("" if raw is None else str(raw)).strip()
                if reward_prereq_text:
                    reward_prereq_ok = self._reward_prereqs_satisfied(reward_prereq_text, checked)

            # Progressive group requirement (resolved server-side, delivered via slot_data)
            prog_reqs = []
            task_prog_reqs_list = list(getattr(self.ctx, "task_progressive_reqs", []) or [])
            if i < len(task_prog_reqs_list):
                raw_pr = task_prog_reqs_list[i]
                if isinstance(raw_pr, list):
                    prog_reqs = raw_pr
            prog_hint_parts = []
            for req in prog_reqs:
                if isinstance(req, dict):
                    g, c = req.get("group", ""), req.get("count", 1)
                else:
                    g, c = req[0], req[1]
                if not self._progressive_req_satisfied(g, c):
                    reward_prereq_ok = False
                prog_hint_parts.append(f"group '{g}' (need {c})")

            #Hide tasks that have unfinished prerequisites if enabled
            if (not task_prereq_ok or not reward_prereq_ok) and getattr(self.ctx, "hide_unreachable_tasks", True) and getattr(self.ctx, "lock_prereqs", False):
                continue

            card = tk.Frame(self.play_tasks_scroll.inner, bg=panel, highlightbackground=border, highlightthickness=1)
            card.pack(fill="x", pady=6, padx=4)

            top = tk.Frame(card, bg=panel)
            top.pack(fill="x", padx=10, pady=(8, 2))

            display_text = f"{i+1}. {task_name}"
            task_color = fg
            if completed:
                display_text = "✔ " + display_text
                task_color = muted

            task_label = tk.Label(
                top,
                text=display_text,
                bg=panel,
                fg=task_color,
                font=("Segoe UI", 12),
                wraplength=720,
                justify="left",
                anchor="w",
            )
            task_label.pack(side="left", fill="x", expand=True)

            if not completed:
                can_complete = True
                if lock_prereqs and (not task_prereq_ok or not reward_prereq_ok):
                    can_complete = False

                btn = ttk.Button(
                    top,
                    text="Complete",
                    command=lambda idx=i: self.complete_task(idx)
                )

                if not can_complete:
                    btn.state(["disabled"])

                btn.pack(side="right", padx=(10, 0))

            # Hints: show task line if locked behind tasks; reward line if locked behind rewards
            showed_hint = False

            if (not completed) and lock_prereqs and task_prereq_text and not task_prereq_ok:
                hint = tk.Label(
                    card,
                    text=f"Locked behind task(s): {task_prereq_text}",
                    bg=panel,
                    fg=muted,
                    font=("Segoe UI", 10),
                    anchor="w",
                    justify="left",
                    wraplength=740
                )
                hint.pack(fill="x", padx=28, pady=(0, 2))
                showed_hint = True

            if (not completed) and lock_prereqs and (reward_prereq_text or prog_hint_parts) and not reward_prereq_ok:
                hint_parts = []
                if reward_prereq_text:
                    hint_parts.append(self._reward_prereq_display(reward_prereq_text))
                hint_parts.extend(prog_hint_parts)
                hint2 = tk.Label(
                    card,
                    text=f"Locked behind reward(s): {', '.join(hint_parts)}",
                    bg=panel,
                    fg=muted,
                    font=("Segoe UI", 10),
                    anchor="w",
                    justify="left",
                    wraplength=740
                )
                hint2.pack(fill="x", padx=28, pady=(0, 8))
                showed_hint = True

            if not showed_hint:
                spacer = tk.Frame(card, bg=panel, height=6)
                spacer.pack(fill="x")

    def _prereqs_satisfied(self, prereq_text: str, checked_locations: set) -> bool:
        """Best-effort client-side prereq check for UI lock hints."""
        if not prereq_text or self.ctx.base_complete_location_id is None:
            return True
        try:
            return _eval_prereq_expr(
                prereq_text,
                lambda idx_1: (self.ctx.base_complete_location_id + idx_1 - 1) in checked_locations
            )
        except Exception:
            return True  # if we can't parse, don't lock the UI

    def _reward_prereqs_satisfied(self, prereq_text: str, checked_locations: set) -> bool:
        if not prereq_text:
            return True
        have = self._received_item_ids()
        base = getattr(self.ctx, "base_item_id", None)
        try:
            return _eval_prereq_expr(
                prereq_text,
                lambda idx_1: (isinstance(base, int) and (base + idx_1 - 1) in have)
            )
        except Exception:
            return True

    def _progressive_req_satisfied(self, group: str, required_count: int) -> bool:
        """Return True if the player has received at least required_count items from the given group."""
        reward_prog_group = list(getattr(self.ctx, "reward_progressive_group", []) or [])
        base = getattr(self.ctx, "base_item_id", None)
        if not isinstance(base, int):
            return True  # can't evaluate without base id — optimistic
        have = self._received_item_ids()
        count = sum(
            1 for idx, g in enumerate(reward_prog_group)
            if g == group and (base + idx) in have
        )
        return count >= required_count
    
    def _received_item_ids(self) -> set:
        """
        Best-effort extraction of received item IDs from common AP client context shapes.
        Returns a set of integer item ids.
        """
        ctx = getattr(self, "ctx", None)
        if not ctx:
            return set()

        candidates = None
        for attr in ("items_received", "received_items"):
            v = getattr(ctx, attr, None)
            if isinstance(v, (list, tuple)):
                candidates = v
                break

        if not candidates:
            return set()

        out = set()
        for it in candidates:
            # Many AP clients store items as objects with .item, sometimes tuples.
            item_id = getattr(it, "item", None)
            if isinstance(item_id, int):
                out.add(item_id)
                continue
            if isinstance(it, (tuple, list)) and it:
                # try first element if it looks like an int item id
                if isinstance(it[0], int):
                    out.add(it[0])
        return out

    def _reward_prereq_display(self, prereq_text: str) -> str:
        """
        Convert prereq indices into actual reward names from ctx.rewards.
        """
        rewards = list(getattr(self.ctx, "rewards", []) or [])
        parts = [p.strip() for p in prereq_text.split(",") if p.strip()]
        names = []

        for p in parts:
            try:
                idx_1based = int(p)
            except ValueError:
                continue
            idx0 = idx_1based - 1
            if 0 <= idx0 < len(rewards) and str(rewards[idx0]).strip():
                names.append(str(rewards[idx0]).strip())
            else:
                names.append(f"Reward #{idx_1based}")

        return ", ".join(names)
        
    def _slot_name_from_id(self, slot_id):
        """Best-effort slot-id -> slot name."""
        if slot_id is None:
            return "Unknown"
        try:
            ctx = getattr(self, "ctx", None)
            slot_info = getattr(ctx, "slot_info", None) if ctx else None

            # Archipelago commonly provides slot_info as dict[int, dict-like]
            if isinstance(slot_info, dict) and slot_id in slot_info:
                v = slot_info.get(slot_id)
                if isinstance(v, dict):
                    name = v.get("name") or v.get("slot_name") or v.get("player_name")
                    if isinstance(name, str) and name.strip():
                        return name.strip()
                else:
                    name = getattr(v, "name", None) or getattr(v, "slot_name", None)
                    if isinstance(name, str) and name.strip():
                        return name.strip()
        except Exception:
            pass

        return f"Player {slot_id}"
    
    def _get_sent_notification_info(self, task_index: int):
        ctx = getattr(self, "ctx", None)
        if not ctx:
            return None, "Unknown"

        try:
            sent_item_names = list(getattr(ctx, "sent_item_names", []) or [])
        except Exception:
            sent_item_names = []

        try:
            sent_player_names = list(getattr(ctx, "sent_player_names", []) or [])
        except Exception:
            sent_player_names = []

        item_name = None
        recipient_name = "Unknown"

        if 0 <= task_index < len(sent_item_names):
            item_name = str(sent_item_names[task_index]).strip() or None

        if 0 <= task_index < len(sent_player_names):
            recipient_name = str(sent_player_names[task_index]).strip() or "Unknown"

        return item_name, recipient_name
    
    def _resolve_location_item_and_player(self, location_id: int):
        """
        Resolve (item_id, player_id) for a location using the best available source.

        Order:
        1) existing local/cache-based lookup
        2) authoritative ctx.locations_info mapping if available
        """
        item_id, player_id = self._get_location_item_and_player(location_id)
        if item_id is not None and player_id is not None:
            return item_id, player_id

        ctx = getattr(self, "ctx", None)
        if not ctx:
            return item_id, player_id

        try:
            locations_info = getattr(ctx, "locations_info", None)
            if locations_info is not None:
                li = None

                if isinstance(locations_info, dict):
                    li = locations_info.get(location_id)
                elif hasattr(locations_info, "get"):
                    li = locations_info.get(location_id)

                if li is not None:
                    # tuple/list
                    if isinstance(li, (tuple, list)) and len(li) >= 2:
                        item_id = li[0] if item_id is None else item_id
                        player_id = li[1] if player_id is None else player_id
                        return item_id, player_id

                    # dict
                    if isinstance(li, dict):
                        if item_id is None:
                            item_id = li.get("item")
                        if player_id is None:
                            player_id = li.get("player")
                        return item_id, player_id

                    # object
                    if item_id is None:
                        item_id = getattr(li, "item", None)
                    if player_id is None:
                        player_id = getattr(li, "player", None)
                    return item_id, player_id
        except Exception:
            pass

        return item_id, player_id
    
    def _resolve_player_name(self, player_id) -> str:
        ctx = getattr(self, "ctx", None)
        if ctx is None or player_id is None:
            return "Unknown"

        # 1) direct player_names map
        try:
            player_names = getattr(ctx, "player_names", None)
            if isinstance(player_names, dict):
                name = player_names.get(player_id)
                if name:
                    return str(name)
            elif hasattr(player_names, "get"):
                name = player_names.get(player_id)
                if name:
                    return str(name)
        except Exception:
            pass

        # 2) slot_info map
        try:
            slot_info = getattr(ctx, "slot_info", None)
            if isinstance(slot_info, dict):
                info = slot_info.get(player_id)
            elif hasattr(slot_info, "get"):
                info = slot_info.get(player_id)
            else:
                info = None

            if info is not None:
                name = getattr(info, "name", None)
                if name:
                    return str(name)

                if isinstance(info, dict):
                    name = info.get("name")
                    if name:
                        return str(name)
        except Exception:
            pass

        return "Unknown"

    def _get_location_item_and_player(self, loc_id: int):
        """
        Best-effort read of scouted location info from context.
        Returns: (item_id|None, player_id|None)
        """
        ctx = getattr(self, "ctx", None)
        if not ctx:
            return None, None

        # Different AP clients / versions store this differently.
        candidates = [
            "location_info",
            "locations_info",
            "locations_info_cache",
            "location_infos",
            "scouted_locations",
        ]

        for attr in candidates:
            try:
                m = getattr(ctx, attr, None)
                if isinstance(m, dict) and loc_id in m:
                    li = m.get(loc_id)

                    # tuple/list form: (item, player, flags?) or similar
                    if isinstance(li, (tuple, list)) and len(li) >= 2:
                        return li[0], li[1]

                    # dict form
                    if isinstance(li, dict):
                        return li.get("item"), li.get("player")

                    # object form (NetUtils.LocationInfo-like)
                    item = getattr(li, "item", None)
                    player = getattr(li, "player", None)
                    return item, player
            except Exception:
                continue

        return None, None

    def _resolve_item_name_for_sent(self, item_id, task_index: int):
        """
        Resolve an item name similar to your received-item popup logic:
        - Prefer ctx.item_names map (multiworld items)
        - If it's a Taskipelago Reward item id, use YAML reward text
        - Otherwise fallback to YAML reward text for this task (best-effort)
        """
        ctx = getattr(self, "ctx", None)
        if not ctx:
            return None

        resolved = None

        # 1) global item name map
        try:
            item_names = getattr(ctx, "item_names", None)
            if isinstance(item_names, dict):
                resolved = item_names.get(item_id)
            elif hasattr(item_names, "get"):
                resolved = item_names.get(item_id)
        except Exception:
            resolved = None

        # 2) Taskipelago reward range -> YAML reward text
        try:
            base_reward_item = getattr(ctx, "base_item_id", None)
            rewards_text = list(getattr(ctx, "rewards", []) or [])
            if isinstance(base_reward_item, int) and isinstance(item_id, int) and rewards_text:
                idx = item_id - base_reward_item
                if 0 <= idx < len(rewards_text):
                    resolved = rewards_text[idx]
        except Exception:
            pass

        # 3) fallback: YAML reward text by task index (even if item_id unknown)
        if (not resolved) and task_index is not None:
            try:
                rewards_text = list(getattr(ctx, "rewards", []) or [])
                if 0 <= task_index < len(rewards_text):
                    resolved = rewards_text[task_index]
            except Exception:
                pass

        if resolved is None:
            return None

        resolved = str(resolved).strip()
        if not resolved:
            return None
        return resolved

    def complete_task(self, task_index: int):
        if not getattr(self, "ctx", None):
            return
        if self.ctx.base_reward_location_id is None or self.ctx.base_complete_location_id is None:
            return

        reward_loc_id = self.ctx.base_reward_location_id + task_index
        complete_loc_id = self.ctx.base_complete_location_id + task_index

        checked = getattr(self.ctx, "checked_locations_set", set()) or set()
        if complete_loc_id in checked or complete_loc_id in self.pending_reward_locations:
            return
        
        # UI optimism on complete location
        self.pending_reward_locations.add(complete_loc_id)
        self.refresh_play_tab()

        try:
            # Dedupe so doule-clicks or rapid refreshes don't spam
            now = time.time()
            sent_key = ("sent", reward_loc_id)
            if sent_key != self._last_sent_key or (now - self._last_sent_seen_at) > 1.0:
                reward_name, recipient_name = self._get_sent_notification_info(task_index)

                # Skip filler and skip unknown/empty authoritative item names
                if reward_name and reward_name.strip() and reward_name.strip() != FILLER_TOKEN:
                    task_label = None
                    try:
                        if 0 <= task_index < len(self.ctx.tasks):
                            task_label = self.ctx.tasks[task_index]
                    except Exception:
                        task_label = None

                    body_lines = []
                    if task_label:
                        body_lines.append(f"Task {task_index + 1}: {task_label}")
                        body_lines.append("")
                    body_lines.append(str(reward_name))
                    body_lines.append("")
                    body_lines.append(f"(sent to {recipient_name})")

                    self._enqueue_notification(Notification(
                        kind="sent",
                        title="Reward Sent!",
                        body="\n".join(body_lines),
                        created_at=time.time()
                    ))

                    self._last_sent_key = sent_key
                    self._last_sent_seen_at = now
        except Exception:
            pass

        async def _send():
            # IMPORTANT: send BOTH checks in one click
            await self.ctx.send_msgs([{
                "cmd": "LocationChecks",
                "locations": [complete_loc_id, reward_loc_id]
            }])

        self.loop.call_soon_threadsafe(lambda: asyncio.create_task(_send()))

    def _maybe_send_goal_complete(self):
        if self.sent_goal:
            return
        if not getattr(self, "ctx", None):
            return
        if not self.ctx.tasks or self.ctx.base_reward_location_id is None or self.ctx.base_complete_location_id is None:
            return

        checked = getattr(self.ctx, "checked_locations_set", set()) or set()

        if self.ctx.goal_expression:
            try:
                done = _eval_prereq_expr(
                    self.ctx.goal_expression,
                    lambda idx_1: (self.ctx.base_complete_location_id + idx_1 - 1) in checked
                )
            except Exception:
                done = False
        else:
            done = all(
                (self.ctx.base_complete_location_id + i) in checked
                for i in range(len(self.ctx.tasks))
            )

        if not done:
            return

        self.sent_goal = True

        async def _send_goal():
            await self.ctx.send_msgs([{"cmd": "StatusUpdate", "status": 30}])

        self.loop.call_soon_threadsafe(lambda: asyncio.create_task(_send_goal()))

    def on_server_disconnected(self):
        self.after(0, self._handle_server_disconnected)

    def _handle_server_disconnected(self):
        self.connection_state = "disconnected"
        self.connect_status.set("Disconnected (server closed connection).")
        self.connect_button.config(text="Connect")
        self.sent_goal = False
        self._clear_play_state()

    # ---------------- DeathLink popup ----------------
    def on_deathlink_received(self, data: dict):
        self.after(0, lambda: self._show_deathlink_popup(data))

    def _show_deathlink_popup(self, data: dict):
        # dedupe
        key = (data.get("time"), data.get("source"), data.get("cause"))
        now = time.time()
        if key == self._last_deathlink_key and (now - self._last_deathlink_seen_at) < 2.0:
            return
        self._last_deathlink_key = key
        self._last_deathlink_seen_at = now

        # amnesty- ignores X deathlinks
        amnesty = int(getattr(self.ctx, "death_link_amnesty", 0) or 0) if getattr(self, "ctx", None) else 0

        if self._deathlink_amnesty_left > 0:
            self._deathlink_amnesty_left -= 1
            return # iframed through it babyyy let's go

        self._deathlink_amnesty_left = amnesty # reset if not dodged

        pool = list(getattr(self.ctx, "death_link_pool", []) or [])
        weights_raw = list(getattr(self.ctx, "death_link_weights", []) or [])

        # normalize weights length
        if len(weights_raw) < len(pool):
            weights_raw += [1] * (len(pool) - len(weights_raw))
        weights_raw = weights_raw[:len(pool)]

        weights = []
        for w in weights_raw:
            try:
                wf = float(w)
            except Exception:
                wf = 1.0
            weights.append(max(0.0, wf))

        if pool:
            if sum(weights) > 0:
                task = random.choices(pool, weights=weights, k=1)[0]
            else:
                task = random.choice(pool)
        else:
            task = "No pool entries configured. Make something up, I guess"

        source = data.get("source") or "Unknown"
        cause = data.get("cause") or ""

        detail_text = f"From: {source}"
        if cause:
            detail_text += f"\n{cause}"

        self._enqueue_notification(Notification(
            kind="deathlink",
            title="DEATHLINK!",
            body=f"{detail_text}\n\nTask: {task}",
            created_at=time.time()
        ))

    # ---------------- Reward popup ----------------
    def on_items_received(self, new_items):
        self.after(0, lambda: self._show_reward_popups(new_items))

    def _show_reward_popups(self, new_items):
        for it in new_items:
            item_id = getattr(it, "item", None)
            sender = getattr(it, "player", None)
            loc = getattr(it, "location", None)

            # If we can't even read an item id, enqueue a debug notification
            if item_id is None:
                self._enqueue_notification(Notification(
                    kind="reward",
                    title="Reward Received (unparsed)",
                    body=f"Got a reward event but couldn't parse fields:\n{it!r}",
                    created_at=time.time()
                ))
                continue

            # ---- 1) HARD SKIP: Task Complete token items (912xxx range) ----
            base_token = getattr(self.ctx, "base_token_id", None)
            n_tasks = len(getattr(self.ctx, "tasks", []) or [])
            if isinstance(base_token, int) and isinstance(item_id, int) and n_tasks:
                if 0 <= (item_id - base_token) < n_tasks:
                    continue

            # ---- 2) Resolve a REAL name (no fallback to "Item ID ...") ----
            resolved_name = None

            # 2a) Server-provided global item name map (best for multiworld items)
            try:
                item_names = getattr(self.ctx, "item_names", None)
                if isinstance(item_names, dict):
                    resolved_name = item_names.get(item_id)
                elif hasattr(item_names, "get"):
                    resolved_name = item_names.get(item_id)
            except Exception:
                resolved_name = None

            # 2b) If this is one of our Taskipelago Reward items, show YAML reward text instead
            base_reward_item = getattr(self.ctx, "base_item_id", None)
            rewards_text = list(getattr(self.ctx, "rewards", []) or [])
            if isinstance(base_reward_item, int) and isinstance(item_id, int) and rewards_text:
                idx = item_id - base_reward_item
                if 0 <= idx < len(rewards_text):
                    resolved_name = rewards_text[idx]

            # ---- 3) If we STILL don't have a name, do NOT popup ----
            if not resolved_name or not str(resolved_name).strip():
                continue

            resolved_name = str(resolved_name).strip()

            # If it's your filler token, don't popup
            if resolved_name == FILLER_TOKEN:
                continue

            # (Extra safety) If server name says Task Complete anyway, skip
            if resolved_name.startswith("Task Complete "):
                continue

            # ---- dedupe the popup ----
            key = (item_id, sender, loc)
            now = time.time()
            if key == self._last_reward_key and (now - self._last_reward_seen_at) < 1.5:
                continue
            self._last_reward_key = key
            self._last_reward_seen_at = now

            sender_label = None
            if sender is not None:
                # Try common AP context mappings first
                try:
                    player_names = getattr(self.ctx, "player_names", None)
                    if isinstance(player_names, dict):
                        sender_label = player_names.get(sender)
                    elif hasattr(player_names, "get"):
                        sender_label = player_names.get(sender)
                except Exception:
                    sender_label = None

                # Fallback: slot_info-style structures (if present)
                if not sender_label:
                    try:
                        slot_info = getattr(self.ctx, "slot_info", None)
                        info = None
                        if isinstance(slot_info, dict):
                            info = slot_info.get(sender)
                        elif hasattr(slot_info, "get"):
                            info = slot_info.get(sender)

                        if isinstance(info, dict):
                            sender_label = info.get("name") or info.get("slot_name")
                        else:
                            sender_label = getattr(info, "name", None) if info is not None else None
                    except Exception:
                        sender_label = None

                if not sender_label:
                    sender_label = f"Player {sender}"

            # show popup
            self._enqueue_notification(Notification(
                kind="reward",
                title="Reward Received!",
                body=(f"{resolved_name}\n\n(from player {sender_label})" if sender is not None else resolved_name),
                created_at=time.time()
            ))


if __name__ == "__main__":
    TaskipelagoApp().mainloop()


def launch(*args):
    app = TaskipelagoApp()
    app.mainloop()
