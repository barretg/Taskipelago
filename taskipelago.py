import tkinter as tk
from tkinter import ttk, messagebox, filedialog
import yaml

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
# Main app
# ----------------------------
class TaskipelagoApp(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("Taskipelago")
        self.geometry("980x740")
        self.minsize(850, 640)

        self.colors = apply_dark_theme(self)

        self.task_rows = []
        self.deathlink_rows = []

        self.build_ui()

    def build_ui(self):
        notebook = ttk.Notebook(self)
        notebook.pack(fill="both", expand=True, padx=10, pady=10)

        editor = ttk.Frame(notebook)
        notebook.add(editor, text="YAML Generator")

        # Meta (fixed), Tasks (3), DeathLink (2), Export (fixed)
        editor.grid_columnconfigure(0, weight=1)
        editor.grid_rowconfigure(0, weight=0)
        editor.grid_rowconfigure(1, weight=3)
        editor.grid_rowconfigure(2, weight=2)
        editor.grid_rowconfigure(3, weight=0)

        # Meta
        meta = ttk.LabelFrame(editor, text="Player / Global Settings")
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

        # Weighted DeathLink controls
        # Default "on" being 50, and off being 0
        weights = ttk.Frame(meta)
        weights.grid(row=1, column=0, columnspan=6, sticky="ew", padx=10, pady=(0, 10))
        weights.grid_columnconfigure(7, weight=1)

        ttk.Label(weights, text="DeathLink (weighted):", style="Muted.TLabel").grid(row=0, column=0, sticky="w", padx=(0, 10))

        ttk.Label(weights, text="On weight").grid(row=0, column=1, sticky="w")
        self.deathlink_on_weight = tk.IntVar(value=50)
        ttk.Spinbox(weights, from_=0, to=999, textvariable=self.deathlink_on_weight, width=6).grid(row=0, column=2, padx=(6, 14))

        ttk.Label(weights, text="Off weight").grid(row=0, column=3, sticky="w")
        self.deathlink_off_weight = tk.IntVar(value=0)
        ttk.Spinbox(weights, from_=0, to=999, textvariable=self.deathlink_off_weight, width=6).grid(row=0, column=4, padx=(6, 14))

        ttk.Button(weights, text="Always On", command=lambda: self._set_deathlink_weights(on_=50, off_=0)).grid(row=0, column=5, padx=(0, 8))
        ttk.Button(weights, text="Always Off", command=lambda: self._set_deathlink_weights(on_=0, off_=50)).grid(row=0, column=6, padx=(0, 8))

        # Tasks section
        tasks = ttk.LabelFrame(editor, text="Tasks")
        tasks.grid(row=1, column=0, sticky="nsew", pady=(0, 10))
        tasks.grid_columnconfigure(0, weight=1)
        tasks.grid_rowconfigure(0, weight=1)

        self.tasks_scroll = ScrollableFrame(tasks, colors=self.colors)
        self.tasks_scroll.grid(row=0, column=0, sticky="nsew", padx=10, pady=10)

        ttk.Button(tasks, text="Add Task", command=self.add_task_row).grid(row=1, column=0, sticky="w", padx=10, pady=(0, 10))

        # DeathLink pool section
        dl = ttk.LabelFrame(editor, text="DeathLink Task Pool")
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
        bottom = ttk.Frame(editor)
        bottom.grid(row=3, column=0, sticky="ew", pady=(10, 0))
        bottom.grid_columnconfigure(0, weight=1)

        ttk.Button(bottom, text="Export YAML", command=self.export_yaml).grid(row=0, column=0, sticky="e")

        # Start with one task row; DL pool can be empty
        self.add_task_row()

    def _set_deathlink_weights(self, on_: int, off_: int):
        self.deathlink_on_weight.set(int(on_))
        self.deathlink_off_weight.set(int(off_))

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

        on_w = int(self.deathlink_on_weight.get())
        off_w = int(self.deathlink_off_weight.get())

        if on_w < 0 or off_w < 0:
            messagebox.showerror("Error", "DeathLink weights cannot be negative.")
            return
        if on_w == 0 and off_w == 0:
            messagebox.showerror("Error", "DeathLink weights cannot both be 0.")
            return

        # If there's any chance DL is on, require pool to be non-empty
        if on_w > 0 and not deathlink_pool:
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


if __name__ == "__main__":
    TaskipelagoApp().mainloop()
