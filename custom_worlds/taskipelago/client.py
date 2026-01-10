import asyncio
import logging
import random
import threading
import time
import urllib.parse
from tkinter import filedialog, messagebox
import tkinter as tk
from tkinter import ttk

import yaml

import CommonClient
import Utils
from NetUtils import Endpoint, decode

RANDOM_TOKEN = "nothing here, get pranked nerd"


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

    # Prevent white hover flash on checkbuttons
    style.configure("TCheckbutton", background=bg, foreground=fg)
    style.map(
        "TCheckbutton",
        background=[("active", bg), ("pressed", bg), ("focus", bg), ("selected", bg)],
        foreground=[("active", fg), ("pressed", fg), ("focus", fg), ("selected", fg)],
    )

    # Notebook styling
    style.configure("TNotebook", background="#2b2b2b", borderwidth=0)
    style.configure("TNotebook.Tab", padding=(14, 6), background="#3a3a3a", foreground="#dddddd", borderwidth=0)
    style.map("TNotebook.Tab", background=[("selected", "#4a4a4a")], foreground=[("selected", "#ffffff")])

    return {"bg": bg, "panel": panel, "border": border, "fg": fg, "muted": muted}


# ----------------------------
# Scrollable container (auto-hide scrollbar)
# ----------------------------
class ScrollableFrame(ttk.Frame):
    _active_scroll = None  # class pointer for wheel routing

    def __init__(self, parent, colors=None):
        super().__init__(parent)
        self.colors = colors or {"bg": "#1e1e1e"}

        self.canvas = tk.Canvas(self, highlightthickness=0, bg=self.colors["bg"])
        self.vsb = ttk.Scrollbar(self, orient="vertical", command=self.canvas.yview)
        self.inner = ttk.Frame(self.canvas)

        self.window_id = self.canvas.create_window((0, 0), window=self.inner, anchor="nw")
        self.canvas.configure(yscrollcommand=self._on_scroll)

        self.canvas.grid(row=0, column=0, sticky="nsew")
        self.vsb.grid(row=0, column=1, sticky="ns")
        self.vsb.grid_remove()

        self.grid_rowconfigure(0, weight=1)
        self.grid_columnconfigure(0, weight=1)

        self.inner.bind("<Configure>", self._on_frame_configure)
        self.canvas.bind("<Configure>", self._on_canvas_configure)

        # Activate wheel when mouse is over this scroll region
        for w in (self.canvas, self.inner):
            w.bind("<Enter>", lambda _e, self=self: self._set_active(True))
            w.bind("<Leave>", lambda _e, self=self: self._set_active(False))

        # Linux wheel
        for w in (self.canvas, self.inner):
            w.bind("<Button-4>", lambda e, self=self: self._on_mousewheel_linux(-1))
            w.bind("<Button-5>", lambda e, self=self: self._on_mousewheel_linux(1))

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

    def _set_active(self, active: bool):
        if active:
            ScrollableFrame._active_scroll = self
        elif ScrollableFrame._active_scroll is self:
            ScrollableFrame._active_scroll = None

    @classmethod
    def bind_mousewheel_to_root(cls, root: tk.Misc):
        root.bind_all("<MouseWheel>", cls._dispatch_mousewheel, add=True)

    @classmethod
    def _dispatch_mousewheel(cls, event):
        if cls._active_scroll is None:
            return
        cls._active_scroll._on_mousewheel(event)

    def _on_mousewheel(self, event):
        delta = int(-1 * (event.delta / 120)) if event.delta else 0
        if delta:
            self.canvas.yview_scroll(delta, "units")

    def _on_mousewheel_linux(self, direction: int):
        self.canvas.yview_scroll(direction, "units")


# ----------------------------
# Rows (YAML Generator)
# ----------------------------
class TaskRow:
    def __init__(self, parent, filler_token: str, on_remove):
        self.frame = ttk.Frame(parent)
        self.filler_token = filler_token
        self._on_remove = on_remove

        self.task_var = tk.StringVar()
        self.reward_var = tk.StringVar()
        self.prereq_var = tk.StringVar()
        self.filler_var = tk.BooleanVar()

        self._saved_reward = ""

        ttk.Entry(self.frame, textvariable=self.task_var).grid(row=0, column=0, padx=(0, 8), sticky="ew")
        ttk.Entry(self.frame, textvariable=self.reward_var).grid(row=0, column=1, padx=(0, 8), sticky="ew")
        ttk.Entry(self.frame, textvariable=self.prereq_var).grid(row=0, column=2, padx=(0, 8), sticky="ew")

        ttk.Checkbutton(
            self.frame,
            text="Filler",
            variable=self.filler_var,
            command=self.on_filler_toggle,
        ).grid(row=0, column=3, padx=(0, 8), sticky="w")

        ttk.Button(self.frame, text="Remove", width=8, command=self.remove).grid(row=0, column=4, sticky="e")

        self.frame.grid_columnconfigure(0, weight=3)
        self.frame.grid_columnconfigure(1, weight=3)
        self.frame.grid_columnconfigure(2, weight=2)

    def remove(self):
        self.frame.destroy()
        self._on_remove(self)

    def on_filler_toggle(self):
        if self.filler_var.get():
            current = self.reward_var.get().strip()
            if current and current != self.filler_token:
                self._saved_reward = current
            self.reward_var.set(self.filler_token)
        else:
            self.reward_var.set(self._saved_reward)

    def get_data(self):
        return (
            self.task_var.get().strip(),
            self.reward_var.get().strip(),
            self.prereq_var.get().strip(),
            self.filler_var.get()
        )


class DeathLinkRow:
    def __init__(self, parent, on_remove):
        self.frame = ttk.Frame(parent)
        self.text_var = tk.StringVar()
        self._on_remove = on_remove

        ttk.Entry(self.frame, textvariable=self.text_var).grid(row=0, column=0, padx=(0, 8), sticky="ew")
        ttk.Button(self.frame, text="Remove", width=8, command=self.remove).grid(row=0, column=1)

        self.frame.grid_columnconfigure(0, weight=1)

    def remove(self):
        self.frame.destroy()
        self._on_remove(self)

    def get_text(self):
        return self.text_var.get().strip()


# ----------------------------
# Networking
# ----------------------------
class TaskipelagoContext(CommonClient.CommonContext):
    game = "Taskipelago"
    items_handling = 0b111  # receive all items

    def __init__(self, server_address=None, password=None):
        super().__init__(server_address, password)
        self.slot_data = {}
        self.tasks = []
        self.rewards = []
        self.task_prereqs = []
        self.lock_prereqs = False

        self.base_location_id = None
        self.base_item_id = None

        self.death_link_pool = []
        self.death_link_enabled = False

        self.checked_locations_set = set()
        self.on_disconnected = None

        self.on_deathlink = None
        self._deathlink_tag_enabled = False

        self.on_item_received = None
        self._last_item_index = 0

        self.on_state_changed = None

    def apply_slot_data(self, slot_data: dict):
        self.slot_data = slot_data or {}
        self.tasks = list(self.slot_data.get("tasks", []))
        self.rewards = list(self.slot_data.get("rewards", []))
        self.task_prereqs = list(self.slot_data.get("task_prereqs", []))
        self.lock_prereqs = bool(self.slot_data.get("lock_prereqs", False))

        self.base_location_id = self.slot_data.get("base_location_id")
        self.base_item_id = self.slot_data.get("base_item_id")

        self.death_link_pool = list(self.slot_data.get("death_link_pool", []))
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
            self.apply_slot_data(args.get("slot_data", {}))

            if self.slot_data.get("death_link_enabled"):
                asyncio.create_task(self.enable_deathlink_tag())

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
            if len(items) > self._last_item_index:
                new_items = items[self._last_item_index:]
                self._last_item_index = len(items)
                if callable(self.on_item_received):
                    self.on_item_received(new_items)

    async def enable_deathlink_tag(self):
        if self._deathlink_tag_enabled:
            return
        self._deathlink_tag_enabled = True
        await self.send_msgs([{"cmd": "ConnectUpdate", "tags": ["DeathLink"]}])


async def server_loop(ctx: TaskipelagoContext, address: str):
    import websockets  # lazy import

    address = f"ws://{address}" if "://" not in address else address

    try:
        socket = await websockets.connect(address, ping_timeout=None, ping_interval=None)
        ctx.server = Endpoint(socket)

        await ctx.send_connect()

        async for data in socket:
            for msg in decode(data):
                await CommonClient.process_server_cmd(ctx, msg)

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
        self.connection_state = "disconnected"  # disconnected | connecting | connected
        self.sent_goal = False
        self.total_task_count = 0
        self.pending_locations = set()

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

        # Context init inside loop
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
        # ---------------- YAML tab ----------------
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

        self.lock_prereqs_var = tk.BooleanVar(value=False)
        ttk.Checkbutton(meta_row2, text="Lock tasks behind prereqs", variable=self.lock_prereqs_var).grid(row=0, column=1, sticky="w", padx=(16, 0))

        tasks = ttk.LabelFrame(self.editor_tab, text="Tasks")
        tasks.grid(row=1, column=0, sticky="nsew", pady=(0, 10))
        tasks.grid_columnconfigure(0, weight=1)
        tasks.grid_rowconfigure(0, weight=0, minsize =28)
        tasks.grid_rowconfigure(1, weight=1)
        tasks.grid_rowconfigure(2, weight=0, minsize =44)

        # Header row inside tasks box
        header = ttk.Frame(tasks)
        header.grid(row=0, column=0, sticky="ew", padx=10, pady=(10, 0))
        header.grid_columnconfigure(0, weight=3)
        header.grid_columnconfigure(1, weight=3)
        header.grid_columnconfigure(2, weight=2)

        ttk.Label(header, text="Task").grid(row=0, column=0, sticky="w")
        ttk.Label(header, text="Reward / Challenge").grid(row=0, column=1, sticky="w")
        ttk.Label(header, text="Prereqs (1-based, e.g. 1,2)").grid(row=0, column=2, sticky="w")

        self.tasks_scroll = ScrollableFrame(tasks, colors=self.colors)
        self.tasks_scroll.grid(row=1, column=0, sticky="nsew", padx=10, pady=0)

        btn_row = ttk.Frame(tasks)
        btn_row.grid(row=2, column=0, sticky="ew", padx=10, pady=(0, 10))
        ttk.Button(btn_row, text="Add Task", command=self.add_task_row).pack(side="left")

        dl = ttk.LabelFrame(self.editor_tab, text="DeathLink Task Pool")
        dl.grid(row=2, column=0, sticky="nsew")
        dl.grid_columnconfigure(0, weight=1)
        dl.grid_rowconfigure(0, weight=1)
        dl.grid_rowconfigure(1, weight=0)

        self.dl_scroll = ScrollableFrame(dl, colors=self.colors)
        self.dl_scroll.grid(row=0, column=0, sticky="nsew", padx=10, pady=10)

        ttk.Button(dl, text="Add DeathLink Task", command=self.add_deathlink_row).grid(row=1, column=0, sticky="w", padx=10, pady=(0, 10))

        bottom = ttk.Frame(self.editor_tab)
        bottom.grid(row=3, column=0, sticky="ew", pady=(10, 0))
        bottom.grid_columnconfigure(0, weight=1)
        ttk.Button(bottom, text="Export YAML", command=self.export_yaml).grid(row=0, column=0, sticky="e")

        self.add_task_row()  # start with one

        # ---------------- Play tab ----------------
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
        row = TaskRow(self.tasks_scroll.inner, RANDOM_TOKEN, self._remove_task_row)
        row.frame.pack(fill="x", pady=4)
        self.task_rows.append(row)

    def _remove_task_row(self, row):
        if row in self.task_rows:
            self.task_rows.remove(row)

    def add_deathlink_row(self):
        row = DeathLinkRow(self.dl_scroll.inner, self._remove_deathlink_row)
        row.frame.pack(fill="x", pady=4)
        self.deathlink_rows.append(row)

    def _remove_deathlink_row(self, row):
        if row in self.deathlink_rows:
            self.deathlink_rows.remove(row)

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
            rewards.append(RANDOM_TOKEN if filler else rw)
            prereqs.append(pr or "")

        if not tasks:
            messagebox.showerror("Error", "No tasks defined.")
            return

        deathlink_pool = [r.get_text() for r in self.deathlink_rows if r.get_text()]

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
            }
        }

        path = filedialog.asksaveasfilename(defaultextension=".yaml", filetypes=[("YAML Files", "*.yaml")])
        if not path:
            return

        with open(path, "w", encoding="utf-8") as f:
            yaml.dump(data, f, sort_keys=False, allow_unicode=True)

        messagebox.showinfo("Success", f"YAML exported to:\n{path}")

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

        self.after(0, self._clear_play_state)

    def _clear_play_state(self):
        self.pending_locations = set()
        if getattr(self, "ctx", None):
            self.ctx.tasks = []
            self.ctx.rewards = []
            self.ctx.task_prereqs = []
            self.ctx.lock_prereqs = False
            self.ctx.base_location_id = None
            self.ctx.base_item_id = None
            self.ctx.death_link_pool = []
            self.ctx.death_link_enabled = False
            self.ctx.checked_locations_set = set()
            self.ctx._last_item_index = 0
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

        checked = getattr(self.ctx, "checked_locations_set", set())
        self.pending_locations.difference_update(checked)

        self._maybe_send_goal_complete()
        self.after(0, self.refresh_play_tab)

    def refresh_play_tab(self):
        for child in self.play_tasks_scroll.inner.winfo_children():
            child.destroy()

        if not getattr(self, "ctx", None) or not self.ctx.tasks or self.ctx.base_location_id is None:
            return

        self.total_task_count = len(self.ctx.tasks)

        panel = self.colors.get("panel", "#252526")
        border = self.colors.get("border", "#3a3a3a")
        fg = self.colors.get("fg", "#e6e6e6")
        muted = self.colors.get("muted", "#bdbdbd")

        checked = set(getattr(self.ctx, "checked_locations_set", set()) or set())

        # prereqs aligned list; if missing, treat as none
        prereq_list = list(getattr(self.ctx, "task_prereqs", []) or [])
        lock_prereqs = bool(getattr(self.ctx, "lock_prereqs", False))

        for i, task_name in enumerate(self.ctx.tasks):
            loc_id = self.ctx.base_location_id + i
            completed = (loc_id in checked) or (loc_id in self.pending_locations)

            # Determine prereq completion
            prereq_ok = True
            prereq_text = ""
            if i < len(prereq_list) and prereq_list[i]:
                prereq_text = prereq_list[i]
                prereq_ok = self._prereqs_satisfied(prereq_text, checked)

            card = tk.Frame(self.play_tasks_scroll.inner, bg=panel, highlightbackground=border, highlightthickness=1)
            card.pack(fill="x", pady=6, padx=4)

            top = tk.Frame(card, bg=panel)
            top.pack(fill="x", padx=10, pady=(8, 2))

            display_text = task_name
            task_color = fg
            if completed:
                display_text = "✔ " + task_name
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
                # if lock is on and prereqs not met, disable completion
                can_complete = True
                if lock_prereqs and not prereq_ok:
                    can_complete = False

                btn = ttk.Button(top, text="Complete", command=lambda lid=loc_id: self.complete_task(lid))
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
        prereq_text: "1,2,5" meaning tasks 1/2/5 must be checked first (1-based task numbering)
        """
        if not prereq_text or self.ctx.base_location_id is None:
            return True
        parts = [p.strip() for p in prereq_text.split(",") if p.strip()]
        for p in parts:
            try:
                idx_1based = int(p)
            except ValueError:
                # ignore junk tokens; you could choose to treat as invalid instead
                continue
            loc = self.ctx.base_location_id + (idx_1based - 1)
            if loc not in checked_locations:
                return False
        return True

    def complete_task(self, location_id: int):
        if location_id in self.pending_locations or location_id in getattr(self.ctx, "checked_locations_set", set()):
            return

        self.pending_locations.add(location_id)
        self.refresh_play_tab()

        async def _send():
            await self.ctx.send_msgs([{"cmd": "LocationChecks", "locations": [location_id]}])

        self.loop.call_soon_threadsafe(lambda: asyncio.create_task(_send()))

    def _maybe_send_goal_complete(self):
        if self.sent_goal:
            return
        if not getattr(self, "ctx", None):
            return
        if not self.ctx.tasks or self.ctx.base_location_id is None:
            return

        checked = getattr(self.ctx, "checked_locations_set", set())
        for i in range(len(self.ctx.tasks)):
            if (self.ctx.base_location_id + i) not in checked:
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
        key = (data.get("time"), data.get("source"), data.get("cause"))
        now = time.time()
        if key == self._last_deathlink_key and (now - self._last_deathlink_seen_at) < 2.0:
            return
        self._last_deathlink_key = key
        self._last_deathlink_seen_at = now

        pool = list(getattr(self.ctx, "death_link_pool", []) or [])
        task = random.choice(pool) if pool else "DeathLink received! (No pool entries configured.)"

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

            # Resolve to YAML reward text if it's within our Taskipelago item range
            name = getattr(it, "item_name", None)
            if not name:
                try:
                    name = Utils.get_item_name_from_id(item_id, self.ctx.game)
                except Exception:
                    name = None

            if not name:
                base = getattr(self.ctx, "base_item_id", None)
                rewards = getattr(self.ctx, "rewards", []) or []
                resolved = None
                if isinstance(base, int) and isinstance(item_id, int):
                    idx = item_id - base
                    if 0 <= idx < len(rewards):
                        resolved = rewards[idx]
                name = resolved or f"Item ID {item_id}"

            key = (item_id, sender, loc)
            now = time.time()
            if key == self._last_reward_key and (now - self._last_reward_seen_at) < 1.5:
                continue
            self._last_reward_key = key
            self._last_reward_seen_at = now

            self._show_reward_popup(name)

    def _show_reward_popup(self, reward_text: str):
        win = tk.Toplevel(self)
        win.title("Reward Received!")
        win.configure(bg=self.colors["bg"])
        win.geometry("520x240")
        win.transient(self)
        win.grab_set()

        title = tk.Label(win, text="REWARD RECEIVED!", bg=self.colors["bg"], fg="#4ade80", font=("Segoe UI", 20, "bold"))
        title.pack(pady=(18, 12))

        body = tk.Label(
            win,
            text=reward_text,
            bg=self.colors["bg"],
            fg=self.colors["fg"],
            font=("Segoe UI", 14),
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
