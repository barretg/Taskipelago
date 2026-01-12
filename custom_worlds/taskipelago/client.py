import asyncio
from pathlib import Path
import random
import threading
import time
from tkinter import filedialog, messagebox
import tkinter as tk
from tkinter import ttk

import json
import yaml

import CommonClient
from NetUtils import Endpoint, decode

FILLER_TOKEN = "nothing here, get pranked nerd"


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
# Rows (YAML Generator)
# ----------------------------
class TaskRow:
    def __init__(self, parent, index: int, filler_token: str, on_remove):
        self.parent = parent
        self.index = index
        self.filler_token = filler_token
        self._on_remove = on_remove

        self.task_var = tk.StringVar()
        self.reward_var = tk.StringVar()
        self.prereq_var = tk.StringVar()
        self.filler_var = tk.BooleanVar()

        self._saved_reward = ""

        self.num_label = ttk.Label(parent, text=str(index), width=3)
        self.task_entry = ttk.Entry(parent, textvariable=self.task_var)
        self.reward_entry = ttk.Entry(parent, textvariable=self.reward_var)
        self.prereq_entry = ttk.Entry(parent, textvariable=self.prereq_var)
        self.filler_cb = ttk.Checkbutton(parent, text="Filler", variable=self.filler_var, command=self.on_filler_toggle)
        self.remove_btn = ttk.Button(parent, text="Remove", width=8, command=self.remove)

        self._grid()

    def _grid(self):
        r = self.index  # NOTE: header is row 0, so tasks start at row 1
        self.num_label.grid(row=r, column=0, padx=(0, 8), sticky="w", pady=4)
        self.task_entry.grid(row=r, column=1, padx=(0, 8), sticky="ew", pady=4)
        self.reward_entry.grid(row=r, column=2, padx=(0, 8), sticky="ew", pady=4)
        self.prereq_entry.grid(row=r, column=3, padx=(0, 8), sticky="ew", pady=4)
        self.filler_cb.grid(row=r, column=4, padx=(0, 8), sticky="w", pady=4)
        self.remove_btn.grid(row=r, column=5, sticky="e", pady=4)

    def remove(self):
        for w in (self.num_label, self.task_entry, self.reward_entry, self.prereq_entry, self.filler_cb, self.remove_btn):
            w.destroy()
        self._on_remove(self)

    def on_filler_toggle(self):
        if self.filler_var.get():
            current = self.reward_var.get().strip()
            if current and current != self.filler_token:
                self._saved_reward = current
            self.reward_var.set(self.filler_token)
            self.reward_entry.state(["disabled"])
        else:
            self.reward_entry.state(["!disabled"])
            self.reward_var.set(self._saved_reward)

    def get_data(self):
        return (
            self.task_var.get().strip(),
            self.reward_var.get().strip(),
            self.prereq_var.get().strip(),
            self.filler_var.get()
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
        self.lock_prereqs = False

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

        # persist received notification state
        self._notify_state_path = Path.cwd() / "notify_state.json"
        self._notify_key = None
        self._loaded_notify_index = False
        self._pending_notify_index = None  # type: int | None

    def apply_slot_data(self, slot_data: dict):
        self.slot_data = slot_data or {}
        self.tasks = list(self.slot_data.get("tasks", []))
        self.rewards = list(self.slot_data.get("rewards", []))
        self.task_prereqs = list(self.slot_data.get("task_prereqs", []))
        self.lock_prereqs = bool(self.slot_data.get("lock_prereqs", False))

        self.base_reward_location_id = self.slot_data.get("base_reward_location_id")
        self.base_complete_location_id = self.slot_data.get("base_complete_location_id")
        self.base_item_id = self.slot_data.get("base_item_id")

        self.death_link_pool = list(self.slot_data.get("death_link_pool", []))
        self.death_link_weights = list(self.slot_data.get("death_link_weights", []))
        self.death_link_amnesty = int(self.slot_data.get("death_link_amnesty", 0) or 0)
        self.death_link_enabled = bool(self.slot_data.get("death_link_enabled", False))

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
            items = list(getattr(self, "items_received", []) or [])

            # If this is the first ReceivedItems after connect, establish baseline.
            if not self._loaded_notify_index:
                self._loaded_notify_index = True

                if isinstance(self._pending_notify_index, int):
                    # We've notified up through this index in the past; resume from there.
                    self._last_item_index = min(self._pending_notify_index, len(items))
                else:
                    # First time on this machine: treat existing history as already-seen,
                    # so we only popup for future rewards.
                    self._last_item_index = len(items)

                # Persist baseline so a crash right after connect doesn't replay history next time.
                self.save_last_notified_index(self._last_item_index)

            if len(items) >= self._last_item_index:
                new_items = items[self._last_item_index:]
                self._last_item_index = len(items)

                # Persist that we've now notified through this index.
                self.save_last_notified_index(self._last_item_index)

                if callable(self.on_item_received):
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
        return f"{server}::{slot}"

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

    def save_last_notified_index(self, idx: int) -> None:
        if idx is None:
            return
        if self._notify_key is None:
            self._notify_key = self._make_notify_key()
        if not self._notify_key.strip(":"):
            return
        data = self._load_notify_state()
        prev = data.get(self._notify_key)
        # Only move forward
        if isinstance(prev, int) and prev > idx:
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
    import websockets
    import ssl
    import traceback

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
            ssl_ctx = ssl.create_default_context() if url.startswith("wss://") else None

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


# ----------------------------
# Main app
# ----------------------------
class TaskipelagoApp(tk.Tk):
    def __init__(self):
        super().__init__()

        self.title("Taskipelago")
        self.geometry("980x740")
        self.minsize(850, 640)

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

        # YAML generator state
        self.task_rows = []
        self.deathlink_rows = []

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
        self.editor_tab.grid_rowconfigure(0, weight=0)
        self.editor_tab.grid_rowconfigure(1, weight=1, minsize=220)
        self.editor_tab.grid_rowconfigure(2, weight=1, minsize=160)
        self.editor_tab.grid_rowconfigure(3, weight=0, minsize=52)

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

        self.deathlink_enabled = tk.BooleanVar(value=True)
        ttk.Checkbutton(meta_row2, text="Enable DeathLink", variable=self.deathlink_enabled).grid(row=0, column=0, sticky="w")

        ttk.Label(meta_row2, text="DeathLink amnesty:").grid(row=0, column=1, sticky="w", padx=(16, 0))
        self.deathlink_amnesty_var = tk.IntVar(value=0)
        ttk.Spinbox(meta_row2, from_=0, to=999, textvariable=self.deathlink_amnesty_var, width=5).grid(
            row=0, column=2, sticky="w", padx=(6, 0)
        )

        self.lock_prereqs_var = tk.BooleanVar(value=False)
        ttk.Checkbutton(meta_row2, text="Lock tasks behind prereqs", variable=self.lock_prereqs_var).grid(row=0, column=3, sticky="w", padx=(16, 0))

        tasks = ttk.LabelFrame(self.editor_tab, text="Tasks")
        tasks.grid(row=1, column=0, sticky="nsew", pady=(0, 10))
        tasks.grid_columnconfigure(0, weight=1)
        tasks.grid_rowconfigure(0, weight=0, minsize=28)
        tasks.grid_rowconfigure(1, weight=1)
        tasks.grid_rowconfigure(2, weight=0, minsize=44)
        
        self.tasks_scroll = ScrollableFrame(tasks, colors=self.colors)
        self.tasks_scroll.grid(row=1, column=0, sticky="nsew", padx=10, pady=0)

        tbl = self.tasks_scroll.inner

        for col, weight in [(1, 3), (2, 3), (3, 2)]:
            tbl.grid_columnconfigure(col, weight=weight)

        ttk.Label(tbl, text="#").grid(row=0, column=0, sticky="w", padx=(0, 8))
        ttk.Label(tbl, text="Task").grid(row=0, column=1, sticky="w", padx=(0, 8))
        ttk.Label(tbl, text="Reward / Challenge").grid(row=0, column=2, sticky="w", padx=(0, 8))
        ttk.Label(tbl, text="Prereqs (1-based, e.g. 1,2)").grid(row=0, column=3, sticky="w", padx=(0, 8))
        ttk.Label(tbl, text="").grid(row=0, column=4, sticky="w")  # filler column placeholder
        ttk.Label(tbl, text="").grid(row=0, column=5, sticky="w")  # remove column placeholder

        btn_row = ttk.Frame(tasks)
        btn_row.grid(row=2, column=0, sticky="ew", padx=10, pady=(0, 10))
        ttk.Button(btn_row, text="Add Task", command=self.add_task_row).pack(side="left")

        dl = ttk.LabelFrame(self.editor_tab, text="DeathLink Task Pool")
        dl.grid(row=2, column=0, sticky="nsew")
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
        bottom.grid(row=3, column=0, sticky="ew", pady=(10, 0))
        bottom.grid_columnconfigure(0, weight=1)
        ttk.Button(bottom, text="Import YAML", command=self.import_yaml).grid(row=0, column=0, sticky="e", padx=(10, 0))
        ttk.Button(bottom, text="Export YAML", command=self.export_yaml).grid(row=0, column=1, sticky="e", padx=(0, 10))

        self.add_task_row()

        # Play tab
        play_root = ttk.Frame(self.play_tab)
        play_root.pack(fill="both", expand=True, padx=10, pady=10)

        conn_frame = ttk.LabelFrame(play_root, text="Connection")
        conn_frame.pack(fill="x", pady=(0, 10))

        ttk.Label(conn_frame, text="Server (host:port):").grid(row=0, column=0, sticky="w", padx=5, pady=5)
        self.server_var = tk.StringVar(value="localhost:38281")
        ttk.Entry(conn_frame, textvariable=self.server_var, width=30).grid(row=0, column=1, padx=5)

        ttk.Label(conn_frame, text="Slot Name:").grid(row=1, column=0, sticky="w", padx=5, pady=5)
        self.slot_var = tk.StringVar()
        ttk.Entry(conn_frame, textvariable=self.slot_var, width=30).grid(row=1, column=1, padx=5)

        ttk.Label(conn_frame, text="Password:").grid(row=2, column=0, sticky="w", padx=5, pady=5)
        self.pass_var = tk.StringVar()
        ttk.Entry(conn_frame, textvariable=self.pass_var, width=30, show="*").grid(row=2, column=1, padx=5)

        btns = ttk.Frame(conn_frame)
        btns.grid(row=3, column=0, columnspan=2, sticky="w", padx=5, pady=(8, 0))

        self.connect_button = ttk.Button(btns, text="Connect", command=self.on_connect_toggle)
        self.connect_button.pack(side="left")

        self.connect_status = tk.StringVar(value="Not connected.")
        ttk.Label(play_root, textvariable=self.connect_status).pack(anchor="w")

        tasks_frame = ttk.LabelFrame(play_root, text="Tasks")
        tasks_frame.pack(fill="both", expand=True, pady=(10, 0))

        self.play_tasks_scroll = ScrollableFrame(tasks_frame, colors=self.colors)
        self.play_tasks_scroll.pack(fill="both", expand=True, padx=10, pady=10)

    # ---------------- YAML generator actions ----------------
    def add_task_row(self):
        # rows start at 1 because header is row 0
        row = TaskRow(self.tasks_scroll.inner, len(self.task_rows) + 1, FILLER_TOKEN, self._remove_task_row)
        self.task_rows.append(row)

    def _remove_task_row(self, row):
        if row in self.task_rows:
            self.task_rows.remove(row)

        for i, r in enumerate(self.task_rows, start=1):
            r.index = i
            r.num_label.config(text=str(i))
            r._grid()  # re-place widgets on the correct grid row
    
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

        tasks, rewards, prereqs = [], [], []
        for r in self.task_rows:
            t, rw, pr, filler = r.get_data()
            if not t:
                continue
            if not rw:
                messagebox.showerror("Error", "Each task must have a reward or be marked Filler.")
                return
            tasks.append(t)
            rewards.append(FILLER_TOKEN if filler else rw)
            prereqs.append(pr or "")

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

        data = {
            "name": player_name,
            "game": "Taskipelago",
            "description": "YAML template for Taskipelago",
            "Taskipelago": {
                "progression_balancing": int(self.progression_var.get()),
                "accessibility": self.accessibility_var.get(),
                "death_link": {"true": on_w, "false": off_w},

                "tasks": tasks,
                "rewards": rewards,
                "task_prereqs": prereqs,
                "lock_prereqs": bool(self.lock_prereqs_var.get()),

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

        # --------- Populate Tasks table ---------
        tasks = list(block.get("tasks", []) or [])
        rewards = list(block.get("rewards", []) or [])
        prereqs = list(block.get("task_prereqs", []) or [])

        # Normalize lengths
        n = max(len(tasks), len(rewards), len(prereqs))
        tasks += [""] * (n - len(tasks))
        rewards += [""] * (n - len(rewards))
        prereqs += [""] * (n - len(prereqs))

        # Wipe existing UI rows then rebuild
        self._clear_task_rows()

        for i in range(n):
            t = str(tasks[i]).strip() if tasks[i] is not None else ""
            rw = str(rewards[i]).strip() if rewards[i] is not None else ""
            pr = str(prereqs[i]).strip() if prereqs[i] is not None else ""

            # Skip completely empty rows
            if not t and not rw and not pr:
                continue

            row = TaskRow(self.tasks_scroll.inner, len(self.task_rows) + 1, FILLER_TOKEN, self._remove_task_row)
            self.task_rows.append(row)

            row.task_var.set(t)
            row.prereq_var.set(pr)

            # Filler handling
            if rw == FILLER_TOKEN:
                row.filler_var.set(True)
                # on_filler_toggle sets reward to token + disables entry
                row.on_filler_toggle()
            else:
                row.filler_var.set(False)
                row.reward_entry.state(["!disabled"])
                row.reward_var.set(rw)

        # Ensure at least 1 row exists for UX
        if not self.task_rows:
            self.add_task_row()

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
        self.refresh_play_tab()

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
        lock_prereqs = bool(getattr(self.ctx, "lock_prereqs", False))

        for i, task_name in enumerate(self.ctx.tasks):
            reward_loc_id = self.ctx.base_reward_location_id + i
            complete_loc_id = self.ctx.base_complete_location_id + i

            # Consider "completed" when reward location is checked (the one that sends items)
            completed = (reward_loc_id in checked) or (reward_loc_id in self.pending_reward_locations)

            # prereqs satisfied based on COMPLETE locations (completion tokens)
            prereq_ok = True
            prereq_text = ""
            if i < len(prereq_list) and prereq_list[i]:
                prereq_text = prereq_list[i]
                prereq_ok = self._prereqs_satisfied(prereq_text, checked)

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
                if lock_prereqs and not prereq_ok:
                    can_complete = False

                btn = ttk.Button(top, text="Complete", command=lambda idx=i: self.complete_task(idx))
                if not can_complete:
                    btn.state(["disabled"])
                btn.pack(side="right", padx=(10, 0))

            if (not completed) and lock_prereqs and prereq_text and not prereq_ok:
                hint = tk.Label(
                    card,
                    text=f"Locked until prereqs complete: {prereq_text}",
                    bg=panel,
                    fg=muted,
                    font=("Segoe UI", 10),
                    anchor="w",
                    justify="left",
                    wraplength=740
                )
                hint.pack(fill="x", padx=28, pady=(0, 8))
            else:
                spacer = tk.Frame(card, bg=panel, height=6)
                spacer.pack(fill="x")

    def _prereqs_satisfied(self, prereq_text: str, checked_locations: set) -> bool:
        """
        prereq_text: "1,2,5" meaning tasks 1/2/5 must be completed first.
        Completion is represented by COMPLETE locations being checked.
        """
        if not prereq_text or self.ctx.base_complete_location_id is None:
            return True
        parts = [p.strip() for p in prereq_text.split(",") if p.strip()]
        for p in parts:
            try:
                idx_1based = int(p)
            except ValueError:
                continue
            loc = self.ctx.base_complete_location_id + (idx_1based - 1)
            if loc not in checked_locations:
                return False
        return True

    def complete_task(self, task_index: int):
        if not getattr(self, "ctx", None):
            return
        if self.ctx.base_reward_location_id is None or self.ctx.base_complete_location_id is None:
            return

        reward_loc_id = self.ctx.base_reward_location_id + task_index
        complete_loc_id = self.ctx.base_complete_location_id + task_index

        checked = getattr(self.ctx, "checked_locations_set", set()) or set()
        if reward_loc_id in checked or reward_loc_id in self.pending_reward_locations:
            return

        # UI optimism on reward location
        self.pending_reward_locations.add(reward_loc_id)
        self.refresh_play_tab()

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
        if not self.ctx.tasks or self.ctx.base_reward_location_id is None:
            return

        checked = getattr(self.ctx, "checked_locations_set", set()) or set()

        for i in range(len(self.ctx.tasks)):
            if (self.ctx.base_reward_location_id + i) not in checked:
                return

        self.sent_goal = True

        async def _send_goal():
            await self.ctx.send_msgs([{"cmd": "StatusUpdate", "status": 30}])  # CLIENT_GOAL

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

        win = tk.Toplevel(self)
        win.title("DEATHLINK!")
        win.configure(bg=self.colors["bg"])
        win.geometry("520x260")
        win.transient(self)
        win.grab_set()

        title = tk.Label(win, text="DEATHLINK!", bg=self.colors["bg"], fg="#ff6b6b", font=("Segoe UI", 20, "bold"))
        title.pack(pady=(18, 10))

        detail_text = f"From: {source}"
        if cause:
            detail_text += f"\n{cause}"

        details = tk.Label(
            win,
            text=detail_text,
            bg=self.colors["bg"],
            fg=self.colors["muted"],
            font=("Segoe UI", 10),
            justify="center",
            wraplength=480
        )
        details.pack(pady=(0, 10))

        task_label = tk.Label(
            win,
            text=task,
            bg=self.colors["bg"],
            fg=self.colors["fg"],
            font=("Segoe UI", 14),
            justify="center",
            wraplength=480
        )
        task_label.pack(pady=(0, 18))

        ttk.Button(win, text="Dismiss", command=win.destroy).pack()

    # ---------------- Reward popup ----------------
    def on_items_received(self, new_items):
        self.after(0, lambda: self._show_reward_popups(new_items))

    def _show_reward_popups(self, new_items):
        for it in new_items:
            item_id = getattr(it, "item", None)
            sender = getattr(it, "player", None)
            loc = getattr(it, "location", None)

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

            # show popup
            self._show_reward_popup(
                f"{resolved_name}\n\n(from player {sender})" if sender is not None else resolved_name
            )


    def _show_reward_popup(self, reward_text: str):
        win = tk.Toplevel(self)
        win.title("Reward Received!")
        win.configure(bg=self.colors["bg"])
        win.geometry("520x260")
        win.transient(self)
        win.grab_set()

        title = tk.Label(win, text="REWARD RECEIVED!", bg=self.colors["bg"], fg="#4ade80", font=("Segoe UI", 20, "bold"))
        title.pack(pady=(18, 12))

        body = tk.Label(
            win,
            text=reward_text,
            bg=self.colors["bg"],
            fg=self.colors["fg"],
            font=("Segoe UI", 13),
            justify="center",
            wraplength=480
        )
        body.pack(pady=(0, 18))

        ttk.Button(win, text="Nice", command=win.destroy).pack()


if __name__ == "__main__":
    TaskipelagoApp().mainloop()


def launch(*args):
    app = TaskipelagoApp()
    app.mainloop()
