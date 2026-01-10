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

    return {"bg": bg}


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

        # Mouse wheel scrolling
        self._bind_mousewheel(self.canvas)
        self._bind_mousewheel(self.inner)

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

    def _bind_mousewheel(self, widget):
        widget.bind("<Enter>", lambda _e: widget.bind_all("<MouseWheel>", self._on_mousewheel))
        widget.bind("<Leave>", lambda _e: widget.unbind_all("<MouseWheel>"))

    def _on_mousewheel(self, event):
        self.canvas.yview_scroll(int(-1 * (event.delta / 120)), "units")


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
        if cmd == "Connected":
            self.apply_slot_data(args.get("slot_data", {}))

async def server_loop(ctx: TaskipelagoContext, address: str):
    import websockets  # lazy import

    address = f"ws://{address}" if "://" not in address else address

    socket = await websockets.connect(
        address,
        ping_timeout=None,
        ping_interval=None
    )
    ctx.server = Endpoint(socket)

    # Authenticate with server
    await ctx.send_connect()

    async for data in socket:
        for msg in decode(data):
            await CommonClient.process_server_cmd(ctx, msg)



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
        self.task_reward_labels = {}  # location_id -> Label

        self.colors = apply_dark_theme(self)

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

        self.loop.call_soon_threadsafe(_init_ctx)

        # Buiild the UI
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

        self.after(0, self.refresh_play_tab)

    def refresh_play_tab(self):
        for child in self.play_tasks_scroll.inner.winfo_children():
            child.destroy()

        self.task_widgets.clear()
        self.task_reward_labels.clear()

        if not self.ctx.tasks or self.ctx.base_location_id is None:
            return

        for i, task_name in enumerate(self.ctx.tasks):
            loc_id = self.ctx.base_location_id + i
            completed = loc_id in self.ctx.locations_checked

            container = ttk.Frame(self.play_tasks_scroll.inner)
            container.pack(fill="x", pady=6)

            # --- Task text ---
            task_label = ttk.Label(
                container,
                text=task_name,
                style="Task.TLabel",
                wraplength=640
            )
            task_label.pack(anchor="w")

            # --- Reward line (hidden unless completed) ---
            reward_label = ttk.Label(
                container,
                text="",  # filled when item received
                style="Reward.TLabel",
                wraplength=600
            )
            reward_label.pack(anchor="w", padx=(18, 0), pady=(2, 0))
            reward_label.pack_forget()

            self.task_reward_labels[loc_id] = reward_label

            if completed:
                task_label.configure(
                    style="TaskDone.TLabel",
                    text="✔ " + task_name.replace("", "\u0336")[:-1]
                )
                reward_label.pack(anchor="w", padx=(18, 0), pady=(2, 0))
            else:
                btn = ttk.Button(
                    container,
                    text="Complete",
                    command=lambda lid=loc_id: self.complete_task(lid)
                )
                btn.pack(anchor="e", pady=(4, 0))

            self.task_widgets[loc_id] = container


    def complete_task(self, location_id: int):
        if location_id in self.ctx.locations_checked:
            return  # hard lock

        async def _send():
            await self.ctx.send_msgs([
                {
                    "cmd": "LocationChecks",
                    "locations": [location_id]
                }
            ])

        self.loop.call_soon_threadsafe(
            lambda: asyncio.create_task(_send())
        )


    def _start_connect(self):
        if self.connection_state != "disconnected":
            return

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




if __name__ == "__main__":
    TaskipelagoApp().mainloop()

def launch(*args):
    app = TaskipelagoApp()
    app.mainloop()