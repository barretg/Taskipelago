import tkinter as tk
from tkinter import ttk, messagebox, filedialog
import yaml
import asyncio
import threading
import logging
import urllib.parse

import Utils
from NetUtils import Endpoint, decode
import CommonClient

import random
import time

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
    accent = "#3b82f6"

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
    style.configure("TNotebook", background=bg)
    style.configure("TNotebook.Tab", background=panel, foreground=fg, padding=(12, 6))
    style.map("TNotebook.Tab", background=[("selected", "#2f2f2f")])

    style.configure(
        "TNotebook",
        background="#2b2b2b",
        borderwidth=0
    )

    style.configure(
        "TNotebook.Tab",
        padding=(14, 6),
        background="#3a3a3a",
        foreground="#dddddd",
        borderwidth=0
    )

    style.map(
        "TNotebook.Tab",
        background=[("selected", "#4a4a4a")],
        foreground=[("selected", "#ffffff")]
    )

    style.configure(
        "Task.TLabel",
        font=("Segoe UI", 11),
    )

    style.configure(
        "TaskDone.TLabel",
        font=("Segoe UI", 11),
        foreground="#9a9a9a"
    )

    style.configure(
        "Reward.TLabel",
        font=("Segoe UI", 10),
        foreground="#4ade80"  # green
    )

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

        self.window_id = self.canvas.create_window((0, 0), window=self.inner, anchor="nw")

        self.canvas.configure(yscrollcommand=self._on_scroll)

        self.canvas.grid(row=0, column=0, sticky="nsew")
        self.vsb.grid(row=0, column=1, sticky="ns")
        self.vsb.grid_remove()  # hidden by default

        self.grid_rowconfigure(0, weight=1)
        self.grid_columnconfigure(0, weight=1)

        self.inner.bind("<Configure>", self._on_frame_configure)
        self.canvas.bind("<Configure>", self._on_canvas_configure)

        # Activate this scroll area when mouse enters it
        self.canvas.bind("<Enter>", lambda _e: self._set_active(True))
        self.canvas.bind("<Leave>", lambda _e: self._set_active(False))
        self.inner.bind("<Enter>", lambda _e: self._set_active(True))
        self.inner.bind("<Leave>", lambda _e: self._set_active(False))

        # Linux wheel support
        self.canvas.bind("<Button-4>", lambda e: self._on_mousewheel_linux(-1))
        self.canvas.bind("<Button-5>", lambda e: self._on_mousewheel_linux(1))
        self.inner.bind("<Button-4>", lambda e: self._on_mousewheel_linux(-1))
        self.inner.bind("<Button-5>", lambda e: self._on_mousewheel_linux(1))


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

    def _on_mousewheel(self, event):
        self.canvas.yview_scroll(int(-1 * (event.delta / 120)), "units")
    
        _active_scroll = None  # class-level pointer

    def _set_active(self, active: bool):
        if active:
            ScrollableFrame._active_scroll = self
        elif ScrollableFrame._active_scroll is self:
            ScrollableFrame._active_scroll = None

    @classmethod
    def bind_mousewheel_to_root(cls, root: tk.Misc):
        # Windows / macOS
        root.bind_all("<MouseWheel>", cls._dispatch_mousewheel, add=True)

    @classmethod
    def _dispatch_mousewheel(cls, event):
        if cls._active_scroll is None:
            return
        cls._active_scroll._on_mousewheel(event)

    def _on_mousewheel(self, event):
        # Windows wheel delta is 120 per notch; macOS varies but sign is correct
        delta = int(-1 * (event.delta / 120)) if event.delta else 0
        if delta:
            self.canvas.yview_scroll(delta, "units")

    def _on_mousewheel_linux(self, direction: int):
        # direction: -1 up, +1 down
        self.canvas.yview_scroll(direction, "units")


# ----------------------------
# Rows
# ----------------------------
class TaskRow:
    def __init__(self, parent, filler_token: str, on_remove):
        self.frame = ttk.Frame(parent)
        self.filler_token = filler_token
        self._on_remove = on_remove

        self.task_var = tk.StringVar()
        self.reward_var = tk.StringVar()
        self.filler_var = tk.BooleanVar()

        # Save user's last non-filler reward so unchecking restores it
        self._saved_reward = ""

        ttk.Entry(self.frame, textvariable=self.task_var).grid(row=0, column=0, padx=(0, 8), sticky="ew")
        ttk.Entry(self.frame, textvariable=self.reward_var).grid(row=0, column=1, padx=(0, 8), sticky="ew")

        ttk.Checkbutton(
            self.frame,
            text="Filler",
            variable=self.filler_var,
            command=self.on_filler_toggle,
        ).grid(row=0, column=2, padx=(0, 8), sticky="w")

        ttk.Button(self.frame, text="Remove", width=8, command=self.remove).grid(row=0, column=3, sticky="e")

        self.frame.grid_columnconfigure(0, weight=3)
        self.frame.grid_columnconfigure(1, weight=3)

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
        return self.task_var.get().strip(), self.reward_var.get().strip(), self.filler_var.get()


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
# Networking shenanigans
# ----------------------------
class TaskipelagoContext(CommonClient.CommonContext):
    game = "Taskipelago"
    items_handling = 0b111  # receive all items

    def __init__(self, server_address=None, password=None):
        super().__init__(server_address, password)
        self.slot_data = {}
        self.tasks = []
        self.rewards = []
        self.base_location_id = None
        self.death_link_pool = []
        self.death_link_enabled = False
        self.checked_locations_set = set()
        self.on_disconnected = None

        self.on_deathlink = None
        self._deathlink_tag_enabled = False

        self.on_item_received = None
        self._last_item_index = 0

        # UI callback
        self.on_state_changed = None

    def apply_slot_data(self, slot_data: dict):
        self.slot_data = slot_data or {}
        self.tasks = list(self.slot_data.get("tasks", []))
        self.rewards = list(self.slot_data.get("rewards", []))
        self.base_location_id = self.slot_data.get("base_location_id")
        self.death_link_pool = list(self.slot_data.get("death_link_pool", []))
        self.death_link_enabled = bool(self.slot_data.get("death_link_enabled", False))

        if callable(self.on_state_changed):
            self.on_state_changed()

    def on_package(self, cmd: str, args: dict):
        super().on_package(cmd, args)

        # Merge any server-provided checked locations (can be full or partial)
        if "checked_locations" in args and isinstance(args["checked_locations"], (list, set, tuple)):
            self.checked_locations_set.update(args["checked_locations"])

        # Merge whatever the base context currently knows (cumulative if present)
        base_checked = getattr(self, "locations_checked", None)
        if isinstance(base_checked, set):
            self.checked_locations_set.update(base_checked)

        if cmd == "Connected":
            self.apply_slot_data(args.get("slot_data", {}))

            # If your world says DeathLink is enabled, opt-in by adding the tag.
            if self.slot_data.get("death_link_enabled"):
                asyncio.create_task(self.enable_deathlink_tag())

            async def _double_sync():
                # First sync immediately
                await self.send_msgs([{"cmd": "Sync"}])
                # Second sync shortly after (covers timing quirks)
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
            # notify for new items only
            if len(items) > self._last_item_index:
                new_items = items[self._last_item_index:]
                self._last_item_index = len(items)
                if callable(self.on_item_received):
                    self.on_item_received(new_items)


    async def enable_deathlink_tag(self):
        # Adds the DeathLink tag so the server will route DeathLink bounces to us. :contentReference[oaicite:1]{index=1}
        if self._deathlink_tag_enabled:
            return
        self._deathlink_tag_enabled = True
        await self.send_msgs([{"cmd": "ConnectUpdate", "tags": ["DeathLink"]}])



async def server_loop(ctx: TaskipelagoContext, address: str):
    import websockets  # lazy import

    address = f"ws://{address}" if "://" not in address else address

    try:
        socket = await websockets.connect(
            address,
            ping_timeout=None,
            ping_interval=None
        )
        ctx.server = Endpoint(socket)

        await ctx.send_connect()

        async for data in socket:
            for msg in decode(data):
                await CommonClient.process_server_cmd(ctx, msg)

    except Exception:
        # fall through to finally
        pass
    finally:
        # Tell UI we are no longer connected
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
        self.task_vars = {} # location_id -> BooleanVar
        self.task_widgets = {}
        self.connection_state = "disconnected"  # disconnected | connecting | connected
        self.sent_goal = False
        self.total_task_count = 0
        self._last_deathlink_key = None
        self._last_deathlink_seen_at = 0.0
        self._last_reward_key = None
        self._last_reward_seen_at = 0.0


        self.colors = apply_dark_theme(self)
        ScrollableFrame.bind_mousewheel_to_root(self)

        self.task_rows = []
        self.deathlink_rows = []

        notebook = ttk.Notebook(self)
        notebook.pack(fill="both", expand=True)

        self.play_tab = ttk.Frame(notebook)
        notebook.add(self.play_tab, text="Connect and Play")

        self.editor_tab = ttk.Frame(notebook)
        notebook.add(self.editor_tab, text="YAML Generator")

        notebook.select(self.play_tab)
        
        # Start the networking loop
        self.loop = asyncio.new_event_loop()

        t = threading.Thread(target=self._run_async_loop, daemon=True)
        t.start()

        # Create context safely inside the event loop
        def _init_ctx():
            self.ctx = TaskipelagoContext()
            self.ctx.on_state_changed = self.on_network_update
            self.ctx.on_disconnected = self.on_server_disconnected
            self.ctx.on_deathlink = self.on_deathlink_received
            self.ctx.on_item_received = self.on_items_received

        self.loop.call_soon_threadsafe(_init_ctx)

        self.pending_locations = set()  # location_ids we've sent checks for, awaiting server confirmation

        # Build the UI
        self.build_ui()

    def build_ui(self):

        # YAML Editor Tab
        # Meta (fixed), Tasks (3), DeathLink (2), Export (fixed)
        self.editor_tab.grid_columnconfigure(0, weight=1)
        self.editor_tab.grid_rowconfigure(0, weight=0)
        self.editor_tab.grid_rowconfigure(1, weight=3)
        self.editor_tab.grid_rowconfigure(2, weight=2)
        self.editor_tab.grid_rowconfigure(3, weight=0)

        # Meta
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

        # DeathLink toggle (UI), still exported as weighted
        dl_toggle = ttk.Frame(meta)
        dl_toggle.grid(row=1, column=0, columnspan=6, sticky="w", padx=10, pady=(0, 10))

        self.deathlink_enabled = tk.BooleanVar(value=True)

        ttk.Checkbutton(
            dl_toggle,
            text="Enable DeathLink",
            variable=self.deathlink_enabled,
        ).grid(row=0, column=0, sticky="w")

        # Tasks section
        tasks = ttk.LabelFrame(self.editor_tab, text="Tasks")
        tasks.grid(row=1, column=0, sticky="nsew", pady=(0, 10))
        tasks.grid_columnconfigure(0, weight=1)
        tasks.grid_rowconfigure(0, weight=1)

        self.tasks_scroll = ScrollableFrame(tasks, colors=self.colors)
        self.tasks_scroll.grid(row=0, column=0, sticky="nsew", padx=10, pady=10)

        ttk.Button(tasks, text="Add Task", command=self.add_task_row).grid(row=1, column=0, sticky="w", padx=10, pady=(0, 10))

        # DeathLink pool section
        dl = ttk.LabelFrame(self.editor_tab, text="DeathLink Task Pool")
        dl.grid(row=2, column=0, sticky="nsew")
        dl.grid_columnconfigure(0, weight=1)
        dl.grid_rowconfigure(0, weight=0)  # hint label
        dl.grid_rowconfigure(1, weight=1)  # scroll area grows/shrinks
        dl.grid_rowconfigure(2, weight=0)  # button row stays visible

        hint = ttk.Label(
            dl,
            text="If DeathLink On weight > 0, this pool must contain at least 1 entry.",
            style="Muted.TLabel",
        )
        hint.grid(row=0, column=0, sticky="w", padx=10, pady=(8, 0))

        self.dl_scroll = ScrollableFrame(dl, colors=self.colors)
        self.dl_scroll.grid(row=1, column=0, sticky="nsew", padx=10, pady=10)

        ttk.Button(dl, text="Add DeathLink Task", command=self.add_deathlink_row).grid(row=2, column=0, sticky="w", padx=10, pady=(0, 10))

        # Export
        bottom = ttk.Frame(self.editor_tab)
        bottom.grid(row=3, column=0, sticky="ew", pady=(10, 0))
        bottom.grid_columnconfigure(0, weight=1)

        ttk.Button(bottom, text="Export YAML", command=self.export_yaml).grid(row=0, column=0, sticky="e")

        # Start with one task row; DL pool can be empty
        self.add_task_row()


        # Connect and Play tab
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

        # ttk.Button(btns, text="Connect", command=self.on_connect).pack(side="left", padx=(0, 8))
        # ttk.Button(btns, text="Disconnect", command=self.on_disconnect).pack(side="left")
        self.connect_button = ttk.Button(
            btns,
            text="Connect",
            command=self.on_connect_toggle
        )
        self.connect_button.pack(side="left")

        self.connect_status = tk.StringVar(value="Not connected.")
        ttk.Label(play_root, textvariable=self.connect_status).pack(anchor="w")

        tasks_frame = ttk.LabelFrame(play_root, text="Tasks")
        tasks_frame.pack(fill="both", expand=True, pady=(10, 0))

        self.play_tasks_scroll = ScrollableFrame(tasks_frame, colors=self.colors)
        self.play_tasks_scroll.pack(fill="both", expand=True, padx=10, pady=10)
        self._bind_mousewheel_to_widget(self.play_tasks_scroll.canvas, self.play_tasks_scroll)
        self._bind_mousewheel_to_widget(self.play_tasks_scroll.inner, self.play_tasks_scroll)

    def _clear_play_state(self):
        # clear local UI/client state
        self.pending_locations = {} if isinstance(getattr(self, "pending_locations", {}), dict) else set()
        if getattr(self, "ctx", None):
            self.ctx.tasks = []
            self.ctx.rewards = []
            self.ctx.base_location_id = None
            self.ctx.death_link_pool = []
            self.ctx.death_link_enabled = False
            self.ctx.checked_locations_set = set()
            self.ctx._last_item_index = 0
            if hasattr(self.ctx, "locations_checked"):
                self.ctx.locations_checked = set()
        self._last_reward_key = None
        self._last_reward_seen_at = 0.0
        self.refresh_play_tab()

    
    def on_connect_toggle(self):
        if self.connection_state == "disconnected":
            self._start_connect()
        elif self.connection_state in ("connecting", "connected"):
            self._start_disconnect()

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

        tasks, rewards = [], []
        for r in self.task_rows:
            t, rw, filler = r.get_data()
            if not t:
                continue
            if not rw:
                messagebox.showerror("Error", "Each task must have a reward or be marked Filler.")
                return
            tasks.append(t)
            rewards.append(RANDOM_TOKEN if filler else rw)

        if not tasks:
            messagebox.showerror("Error", "No tasks defined.")
            return

        deathlink_pool = [r.get_text() for r in self.deathlink_rows if r.get_text()]

        if self.deathlink_enabled.get():
            on_w, off_w = 50, 0
        else:
            on_w, off_w = 0, 50

        # If there's any chance DL is on, require pool to be non-empty
        if self.deathlink_enabled.get() and not deathlink_pool:
            messagebox.showerror(
                "Error",
                "DeathLink On weight is > 0, but the DeathLink Task Pool is empty.\n"
                "Add at least one DeathLink task or set On weight to 0."
            )
            return

        data = {
            "name": player_name,
            "game": "Taskipelago",
            "description": "YAML template for Taskipelago",
            "Taskipelago": {
                "progression_balancing": int(self.progression_var.get()),
                "accessibility": self.accessibility_var.get(),
                "death_link": {
                    "true": on_w,
                    "false": off_w,
                },
                "tasks": tasks,
                "rewards": rewards,
                "death_link_pool": deathlink_pool,
            }
        }

        path = filedialog.asksaveasfilename(defaultextension=".yaml", filetypes=[("YAML Files", "*.yaml")])
        if not path:
            return

        with open(path, "w", encoding="utf-8") as f:
            yaml.dump(data, f, sort_keys=False, allow_unicode=True)

        messagebox.showinfo("Success", f"YAML exported to:\n{path}")
    
    def _run_async_loop(self):
        asyncio.set_event_loop(self.loop)
        self.loop.run_forever()

    def on_network_update(self):
        if self.connection_state == "connecting":
            self.connection_state = "connected"
            self.connect_status.set("Connected.")
            self.connect_button.config(text="Disconnect")

        if not getattr(self, "ctx", None):
            return

        checked = getattr(self.ctx, "checked_locations_set", set())
        if isinstance(getattr(self, "pending_locations", None), set):
            self.pending_locations.difference_update(checked)

        self._maybe_send_goal_complete()
        self.after(0, self.refresh_play_tab)


    def refresh_play_tab(self):
        for child in self.play_tasks_scroll.inner.winfo_children():
            child.destroy()

        # Ensure tasks exist
        if not getattr(self, "ctx", None) or not self.ctx.tasks or self.ctx.base_location_id is None:
            return
        
        self.total_task_count = len(self.ctx.tasks)

        panel = self.colors.get("panel", "#252526")
        border = self.colors.get("border", "#3a3a3a")
        fg = self.colors.get("fg", "#e6e6e6")
        muted = self.colors.get("muted", "#bdbdbd")

        for i, task_name in enumerate(self.ctx.tasks):
            loc_id = self.ctx.base_location_id + i
            completed = (loc_id in self.ctx.checked_locations_set) or (loc_id in self.pending_locations)

            # ---- Box container ----
            card = tk.Frame(
                self.play_tasks_scroll.inner,
                bg=panel,
                highlightbackground=border,
                highlightthickness=1
            )
            card.pack(fill="x", pady=6, padx=4)

            # ---- Row 1: Task text + button ----
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
                font=("Segoe UI", 12),     # bigger
                wraplength=720,
                justify="left",
                anchor="w"
            )
            task_label.pack(side="left", fill="x", expand=True)

            if not completed:
                btn = ttk.Button(
                    top,
                    text="Complete",
                    command=lambda lid=loc_id: self.complete_task(lid)
                )
                btn.pack(side="right", padx=(10, 0))

            self._bind_mousewheel_recursive(card, self.play_tasks_scroll)

            spacer = tk.Frame(card, bg=panel, height=6)
            spacer.pack(fill="x")

    def complete_task(self, location_id: int):
        if location_id in self.pending_locations or location_id in self.ctx.checked_locations_set:
            return

        # Immediate UI feedback
        self.pending_locations.add(location_id)
        self.refresh_play_tab()

        async def _send():
            await self.ctx.send_msgs([
                {"cmd": "LocationChecks", "locations": [location_id]}
            ])

        self.loop.call_soon_threadsafe(lambda: asyncio.create_task(_send()))



    def _start_connect(self):
        if self.connection_state != "disconnected":
            return
        
        # Ensure we don't accidentally early complete
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

        if self.ctx and self.ctx.server:
            async def _do_disconnect():
                await self.ctx.disconnect()

            self.loop.call_soon_threadsafe(
                lambda: asyncio.create_task(_do_disconnect())
            )
        
        self.sent_goal = False
        self.after(0, self._clear_play_state)
    
    def _bind_mousewheel_to_widget(self, widget, scroll: ScrollableFrame):
        # Windows / macOS
        widget.bind("<MouseWheel>", lambda e: scroll.canvas.yview_scroll(int(-e.delta / 120), "units"), add=True)
        # Linux
        widget.bind("<Button-4>", lambda e: scroll.canvas.yview_scroll(-1, "units"), add=True)
        widget.bind("<Button-5>", lambda e: scroll.canvas.yview_scroll(1, "units"), add=True)

    def _bind_mousewheel_recursive(self, root_widget, scroll: ScrollableFrame):
        # bind this widget
        self._bind_mousewheel_to_widget(root_widget, scroll)
        # bind all descendants
        for child in root_widget.winfo_children():
            self._bind_mousewheel_recursive(child, scroll)

    def _maybe_send_goal_complete(self):
        if self.sent_goal:
            return
        if not getattr(self, "ctx", None):
            return
        if not self.ctx.tasks or self.ctx.base_location_id is None:
            return

        checked = getattr(self.ctx, "checked_locations_set", set())
        all_done = True
        for i in range(len(self.ctx.tasks)):
            loc_id = self.ctx.base_location_id + i
            if loc_id not in checked:
                all_done = False
                break

        if not all_done:
            return

        self.sent_goal = True

        async def _send_goal():
            await self.ctx.send_msgs([{"cmd": "StatusUpdate", "status": 30}])  # CLIENT_GOAL = 30 :contentReference[oaicite:1]{index=1}

        self.loop.call_soon_threadsafe(lambda: asyncio.create_task(_send_goal()))

    def on_server_disconnected(self):
        # called from async thread; bounce to Tk thread
        self.after(0, self._handle_server_disconnected)

    def _handle_server_disconnected(self):
        self.connection_state = "disconnected"
        self.connect_status.set("Disconnected (server closed connection).")
        self.connect_button.config(text="Connect")
        self.sent_goal = False
        self._clear_play_state()

    def on_deathlink_received(self, data: dict):
        # Called from async thread -> marshal to Tk thread
        self.after(0, lambda: self._show_deathlink_popup(data))

    def _show_deathlink_popup(self, data: dict):
        key = (data.get("time"), data.get("source"), data.get("cause"))
        now = time.time()

        # Ignore duplicates arriving back-to-back (common with some client handlers)
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
        win.grab_set()  # modal

        title = tk.Label(
            win,
            text="DEATHLINK!",
            bg=self.colors["bg"],
            fg="#ff6b6b",
            font=("Segoe UI", 20, "bold")
        )
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

        btn = ttk.Button(win, text="Dismiss", command=win.destroy)
        btn.pack()
    
    def on_items_received(self, new_items):
        # called from async thread; marshal to Tk thread
        self.after(0, lambda: self._show_reward_popups(new_items))

    def _show_reward_popups(self, new_items):
        for it in new_items:
            item_id = getattr(it, "item", None)
            sender = getattr(it, "player", None)
            loc = getattr(it, "location", None)

            # name lookup best-effort
            name = getattr(it, "item_name", None)
            if not name:
                try:
                    name = Utils.get_item_name_from_id(item_id, self.ctx.game)
                except Exception:
                    name = None
            if not name:
                name = f"Item ID {item_id}"

            # dedupe
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

        title = tk.Label(
            win,
            text="REWARD RECEIVED!",
            bg=self.colors["bg"],
            fg="#4ade80",
            font=("Segoe UI", 20, "bold")
        )
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

        btn = ttk.Button(win, text="Nice", command=win.destroy)
        btn.pack()





if __name__ == "__main__":
    TaskipelagoApp().mainloop()

def launch(*args):
    app = TaskipelagoApp()
    app.mainloop()