import asyncio
from dataclasses import dataclass
from datetime import datetime
from itertools import combinations
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

import copy
import CommonClient
from NetUtils import Endpoint, decode

FILLER_ITEMS = [
    "Several pats on the back",
    "A big thumbs up",
    "Free dopamine",
    "One (1) sense of accomplishment",
    "Mildly increased self-esteem",
    "A crisp high five",
    "A firm handshake",
    "A tiny mental victory parade",
    "Temporary immunity to self-criticism",
    "An imaginary star sticker",
    "A nod of respect",
]
FILLER_ITEMS_SET = set(FILLER_ITEMS)
LEGACY_FILLER_TOKEN = "nothing here, get pranked nerd"
REWARD_TYPE_VALUES = ("junk", "useful", "progression", "trap")
DEFAULT_REWARD_TYPE = "useful"


def _is_filler(s: str) -> bool:
    return s == LEGACY_FILLER_TOKEN or s in FILLER_ITEMS_SET


def _random_filler() -> str:
    return random.choice(FILLER_ITEMS)


def _bingo_lines(X: int, Y: int) -> list:
    """Return list of lists of 0-based space indices for each bingo line (rows, cols, diagonals).

    For rectangular boards, all full-length diagonals of length min(X, Y) are included.
    A square 5x5 board has 2 diagonals; a rectangular 7x5 board has 6 (3 down-right + 3 down-left).
    """
    lines = []
    for r in range(Y):
        lines.append([r * X + c for c in range(X)])
    for c in range(X):
        lines.append([r * X + c for r in range(Y)])
    d = min(X, Y)
    # All full-length down-right diagonals
    for r0 in range(Y - d + 1):
        for c0 in range(X - d + 1):
            lines.append([(r0 + i) * X + (c0 + i) for i in range(d)])
    # All full-length down-left (anti) diagonals
    for r0 in range(Y - d + 1):
        for c0 in range(d - 1, X):
            lines.append([(r0 + i) * X + (c0 - i) for i in range(d)])
    return lines


def _gen_bingoal_expr(n_spaces: int, n_lines: int, bingoal: int) -> str:
    """Generate a goal prereq expression requiring any bingoal of the n_lines bingo line tasks."""
    if n_lines == 0 or bingoal <= 0:
        return ""
    bingoal = min(bingoal, n_lines)
    line_1based = list(range(n_spaces + 1, n_spaces + n_lines + 1))
    if bingoal == n_lines:
        return ", ".join(str(i) for i in line_1based)
    terms = [
        "(" + " && ".join(str(i) for i in combo) + ")"
        for combo in combinations(line_1based, bingoal)
    ]
    return " || ".join(terms)


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
    style.configure("Warning.TLabel", background=bg, foreground="#e07070")

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
        # Disable mousewheel on comboboxes entirely so scrolling never changes a selected value
        for seq in ("<MouseWheel>", "<Button-4>", "<Button-5>"):
            root.bind_class("TCombobox", seq, lambda e: "break")
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
        # Skip if cursor is over a combobox or its open dropdown listbox
        w = root.winfo_containing(event.x_root, event.y_root)
        if w is not None and w.winfo_class() in ("TCombobox", "Listbox"):
            return
        owner = cls._find_scroll_owner_under_pointer(root, event.x_root, event.y_root)
        if owner is None:
            return
        delta = int(-1 * (event.delta / 120)) if getattr(event, "delta", 0) else 0
        if delta:
            owner.canvas.yview_scroll(delta, "units")

    @classmethod
    def _dispatch_mousewheel_linux(cls, event, root: tk.Misc, direction: int):
        w = root.winfo_containing(event.x_root, event.y_root)
        if w is not None and w.winfo_class() in ("TCombobox", "Listbox"):
            return
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
# ----------------------------
# Collapsible section for the editor tab
# ----------------------------
class CollapsibleSection:
    """A grid-managed panel with a clickable header that shows/hides its body."""
    def __init__(self, parent, title: str, row: int, expanded: bool = True,
                 min_height: int = 150, colors: dict = None):
        self._parent = parent
        self._row = row
        self._expanded = expanded
        self._min_height = min_height
        colors = colors or {}
        _bg = colors.get("panel", "#252526")
        _fg = colors.get("fg", "#e6e6e6")

        self.outer = ttk.Frame(parent)
        self.outer.grid_columnconfigure(0, weight=1)
        self.outer.grid_rowconfigure(0, weight=0)
        self.outer.grid_rowconfigure(1, weight=1)

        parent.grid_rowconfigure(row, weight=(1 if expanded else 0),
                                 minsize=(min_height if expanded else 0))

        hdr = tk.Frame(self.outer, bg=_bg, cursor="hand2")
        hdr.grid(row=0, column=0, sticky="ew")

        self._arrow = tk.StringVar(value="[-]" if expanded else "[+]")
        arrow_lbl = tk.Label(hdr, textvariable=self._arrow, bg=_bg, fg=_fg,
                             font=("Courier", 9), cursor="hand2")
        arrow_lbl.pack(side="left", padx=(6, 2), pady=3)
        title_lbl = tk.Label(hdr, text=title, bg=_bg, fg=_fg,
                             font=("TkDefaultFont", 9, "bold"), cursor="hand2")
        title_lbl.pack(side="left", pady=3)

        for w in (hdr, arrow_lbl, title_lbl):
            w.bind("<Button-1>", self._toggle)

        self.body = ttk.Frame(self.outer)
        self.body.grid(row=1, column=0, sticky="nsew")
        if not expanded:
            self.body.grid_remove()

    def _toggle(self, event=None):
        if self._expanded:
            self.body.grid_remove()
            self._arrow.set("[+]")
            self._expanded = False
            self._parent.grid_rowconfigure(self._row, weight=0, minsize=0)
        else:
            self.body.grid()
            self._arrow.set("[-]")
            self._expanded = True
            self._parent.grid_rowconfigure(self._row, weight=1, minsize=self._min_height)


# Rows (YAML Generator)
# ----------------------------
class TaskRow:
    def __init__(self, parent, index: int, on_remove, regions=None):
        self.parent = parent
        self.index = index
        self._on_remove = on_remove

        self.task_var = tk.StringVar()
        self.prereq_var = tk.StringVar()
        self.item_prereq_var = tk.StringVar()
        self.cost_var = tk.StringVar()
        self.region_var = tk.StringVar(value="")
        self.count_var = tk.IntVar(value=1)

        self.num_label = ttk.Label(parent, text=str(index), width=3)
        self.task_entry = ttk.Entry(parent, textvariable=self.task_var)
        self.prereq_entry = ttk.Entry(parent, textvariable=self.prereq_var)
        self.item_prereq_entry = ttk.Entry(parent, textvariable=self.item_prereq_var)
        self.cost_entry = ttk.Entry(parent, textvariable=self.cost_var)
        self.region_cb = ttk.Combobox(
            parent, textvariable=self.region_var,
            values=[""] + list(regions or []),
            state="readonly", width=12,
        )
        self.count_spinbox = ttk.Spinbox(parent, from_=1, to=999, textvariable=self.count_var, width=5)
        self.remove_btn = ttk.Button(parent, text="Remove", width=8, command=self.remove)

        self._grid()

    def _grid(self):
        r = self.index + 1  # header is row 0, hint row is 1, tasks start at row 2
        self.num_label.grid(row=r, column=0, padx=(0, 8), sticky="w", pady=4)
        self.task_entry.grid(row=r, column=1, padx=(0, 8), sticky="ew", pady=4)
        self.prereq_entry.grid(row=r, column=2, sticky="ew", padx=(0, 8), pady=4)
        self.item_prereq_entry.grid(row=r, column=3, sticky="ew", padx=(0, 8), pady=4)
        self.cost_entry.grid(row=r, column=4, sticky="ew", padx=(0, 8), pady=4)
        self.region_cb.grid(row=r, column=5, sticky="w", padx=(0, 8), pady=4)
        self.count_spinbox.grid(row=r, column=6, sticky="w", padx=(0, 8), pady=4)
        self.remove_btn.grid(row=r, column=7, padx=(0, 0), pady=4)

    def remove(self):
        for w in (self.num_label, self.task_entry, self.prereq_entry,
                  self.item_prereq_entry, self.cost_entry, self.region_cb,
                  self.count_spinbox, self.remove_btn):
            try:
                w.destroy()
            except Exception:
                pass
        self._on_remove(self)

    def update_regions(self, regions):
        current = self.region_var.get()
        new_values = [""] + list(regions)
        self.region_cb.configure(values=new_values)
        if current not in new_values:
            self.region_var.set("")

    def get_data(self):
        try:
            count = max(1, int(self.count_var.get()))
        except (ValueError, tk.TclError):
            count = 1
        return (
            self.task_var.get().strip(),
            self.prereq_var.get().strip(),
            self.item_prereq_var.get().strip(),
            self.cost_var.get().strip(),
            self.region_var.get().strip(),
            count,
        )


class ItemRow:
    def __init__(self, parent, index: int, on_remove, groups=None):
        self.parent = parent
        self.index = index
        self._on_remove = on_remove

        self.item_var = tk.StringVar()
        self.filler_var = tk.BooleanVar(value=False)
        self.consumable_var = tk.BooleanVar(value=False)
        self.reward_type_var = tk.StringVar(value=DEFAULT_REWARD_TYPE)
        self._saved_reward_type = DEFAULT_REWARD_TYPE
        self._saved_item = ""
        self._saved_prog_group = ""
        self.count_var = tk.IntVar(value=1)

        self.prog_group_var = tk.StringVar(value="")
        self.prog_group_cb = ttk.Combobox(
            parent,
            textvariable=self.prog_group_var,
            values=[""] + list(groups or []),
            state="readonly",
            width=12,
        )
        self.prog_group_var.trace_add("write", self._on_prog_group_change)

        self.reward_type_cb = ttk.Combobox(
            parent,
            textvariable=self.reward_type_var,
            values=REWARD_TYPE_VALUES,
            state="readonly",
            width=12,
        )

        self.num_label = ttk.Label(parent, text=str(index), width=3)
        self.item_entry = ttk.Entry(parent, textvariable=self.item_var)
        self.filler_cb = ttk.Checkbutton(
            parent, text="Filler", variable=self.filler_var, command=self.on_filler_toggle
        )
        self.consumable_cb = ttk.Checkbutton(
            parent, text="Consumable", variable=self.consumable_var,
            command=self.on_consumable_toggle,
        )
        self.count_spinbox = ttk.Spinbox(parent, from_=1, to=999, textvariable=self.count_var, width=5)
        self.remove_btn = ttk.Button(parent, text="Remove", width=8, command=self.remove)

        self._grid()

    def _grid(self):
        r = self.index + 2  # header is row 0, hint row is 1, items start at row 2
        self.num_label.grid(row=r, column=0, padx=(0, 8), sticky="w", pady=4)
        self.item_entry.grid(row=r, column=1, padx=(0, 8), sticky="ew", pady=4)
        self.reward_type_cb.grid(row=r, column=2, sticky="w", padx=(0, 8), pady=4)
        self.filler_cb.grid(row=r, column=3, padx=(0, 8), sticky="w", pady=4)
        self.consumable_cb.grid(row=r, column=4, padx=(0, 8), sticky="w", pady=4)
        self.prog_group_cb.grid(row=r, column=5, sticky="w", padx=(0, 8), pady=4)
        self.count_spinbox.grid(row=r, column=6, sticky="w", padx=(0, 8), pady=4)
        self.remove_btn.grid(row=r, column=7, padx=(0, 0), pady=4)

    def remove(self):
        for w in (
            self.num_label,
            self.item_entry,
            self.reward_type_cb,
            self.filler_cb,
            self.consumable_cb,
            self.prog_group_cb,
            self.count_spinbox,
            self.remove_btn,
        ):
            try:
                w.destroy()
            except Exception:
                pass
        self._on_remove(self)

    def set_remove_visible(self, visible: bool):
        if visible:
            self.remove_btn.grid()
        else:
            self.remove_btn.grid_remove()

    def on_filler_toggle(self):
        if self.filler_var.get():
            current = self.item_var.get().strip()
            if current and not _is_filler(current):
                self._saved_item = current
            current_type = self.reward_type_var.get().strip().lower()
            if current_type:
                self._saved_reward_type = current_type
            self._saved_prog_group = self.prog_group_var.get()
            self.prog_group_var.set("")
            self.prog_group_cb.state(["disabled"])
            self.consumable_var.set(False)
            self.consumable_cb.state(["disabled"])
            self.item_var.set(_random_filler())
            self.item_entry.state(["disabled"])
            self.reward_type_var.set("junk")
            self.reward_type_cb.state(["disabled"])
        else:
            self.item_entry.state(["!disabled"])
            self.item_var.set(self._saved_item)
            self.consumable_cb.state(["!disabled"])
            if self.consumable_var.get():
                # Re-apply consumable constraints (prog group stays locked)
                self.on_consumable_toggle()
            else:
                self.prog_group_cb.state(["!disabled"])
                self.prog_group_var.set(self._saved_prog_group)
                # _on_prog_group_change fires from the trace and restores type / disables as needed

    def on_consumable_toggle(self):
        if self.consumable_var.get():
            # Force progression type and lock dropdown
            current_type = self.reward_type_var.get().strip().lower()
            if current_type != "progression":
                self._saved_reward_type = current_type or DEFAULT_REWARD_TYPE
            self.reward_type_var.set("progression")
            self.reward_type_cb.state(["disabled"])
            # Consumables cannot be in a progressive group
            if not self._saved_prog_group:
                self._saved_prog_group = self.prog_group_var.get()
            self.prog_group_var.set("")
            self.prog_group_cb.state(["disabled"])
        else:
            # Restore type and prog group if not filler
            if not self.filler_var.get():
                self.reward_type_cb.state(["!disabled"])
                self.reward_type_var.set(self._saved_reward_type or DEFAULT_REWARD_TYPE)
                self.prog_group_cb.state(["!disabled"])
                self.prog_group_var.set(self._saved_prog_group)

    def _on_prog_group_change(self, *_):
        if self.prog_group_var.get():
            if not self.filler_var.get():
                current_type = self.reward_type_var.get().strip().lower()
                if current_type != "progression":
                    self._saved_reward_type = current_type
            self.reward_type_var.set("progression")
            self.reward_type_cb.state(["disabled"])
            self.filler_cb.state(["disabled"])
        else:
            self.reward_type_cb.state(["!disabled"])
            self.reward_type_var.set(self._saved_reward_type or DEFAULT_REWARD_TYPE)
            if not self.filler_var.get() and not self.consumable_var.get():
                self.filler_cb.state(["!disabled"])

    def update_groups(self, groups):
        current = self.prog_group_var.get()
        new_values = [""] + list(groups)
        self.prog_group_cb.configure(values=new_values)
        if current not in new_values:
            self.prog_group_var.set("")

    def get_data(self):
        try:
            count = max(1, int(self.count_var.get()))
        except (ValueError, tk.TclError):
            count = 1
        return (
            self.item_var.get().strip(),
            self.filler_var.get(),
            self.reward_type_var.get().strip().lower() or "useful",
            self.prog_group_var.get().strip(),
            self.consumable_var.get(),
            count,
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
class _TaskipelagoCommandProcessor(CommonClient.ClientCommandProcessor):
    console_output_callback = None

    def output(self, text: str):
        if callable(self.console_output_callback):
            self.console_output_callback(text)
        else:
            super().output(text)


class TaskipelagoContext(CommonClient.CommonContext):
    command_processor = _TaskipelagoCommandProcessor
    game = "Taskipelago"
    items_handling = 0b111

    def __init__(self, server_address=None, password=None):
        super().__init__(server_address, password)
        self.slot_data = {}

        self.tasks = []
        self.items = []
        self.task_prereqs = []
        self.item_prereqs = []
        self.lock_prereqs = False
        self.hide_unreachable_tasks = True
        self.goal_indices = []
        self.goal_expression = ""

        self.base_reward_location_id = None
        self.base_complete_location_id = None
        self.base_item_id = None
        self.base_token_id = None

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

        self.regions = []
        self.region_default_pcts = {}
        self.task_region = []
        self.task_region_reqs = []

        self.bingo_mode = False
        self.bingo_dimension_x = 5
        self.bingo_dimension_y = 5
        self.bingoal = 3

        self.on_print_json_callback = None  # type: callable | None

        # persist received notification state
        self._notify_state_path = Path.cwd() / "taskipelago_notify_state.json"
        self._notify_key = None
        self._loaded_notify_index = False
        self._pending_notify_index = None  # type: int | None

    def apply_slot_data(self, slot_data: dict):
        self.slot_data = slot_data or {}
        self.tasks = list(self.slot_data.get("tasks", []))
        # Accept both new "items" key and legacy "rewards" key for backward compatibility
        self.items = list(self.slot_data.get("items", self.slot_data.get("rewards", [])))
        self.task_prereqs = list(self.slot_data.get("task_prereqs", []))
        # Accept both new "item_prereqs" key and legacy "reward_prereqs" key
        self.item_prereqs = list(self.slot_data.get("item_prereqs", self.slot_data.get("reward_prereqs", [])))
        self.lock_prereqs = bool(self.slot_data.get("lock_prereqs", False))
        self.hide_unreachable_tasks = bool(self.slot_data.get("hide_unreachable_tasks", True))
        self.goal_indices = list(self.slot_data.get("goal_indices", []) or [])
        self.goal_expression = str(self.slot_data.get("goal_expression", "") or "")

        self.base_reward_location_id = self.slot_data.get("base_reward_location_id")
        self.base_complete_location_id = self.slot_data.get("base_complete_location_id")
        self.base_item_id = self.slot_data.get("base_item_id")
        self.base_token_id = self.slot_data.get("base_token_id")

        self.death_link_pool = list(self.slot_data.get("death_link_pool", []))
        self.death_link_weights = list(self.slot_data.get("death_link_weights", []))
        self.death_link_amnesty = int(self.slot_data.get("death_link_amnesty", 0) or 0)
        self.death_link_enabled = bool(self.slot_data.get("death_link_enabled", False))

        self.seed_name = str(self.slot_data.get("seed_name", "") or "")

        self.sent_item_names = list(self.slot_data.get("sent_item_names", []))
        self.sent_player_names = list(self.slot_data.get("sent_player_names", []))

        self.progressive_groups = list(self.slot_data.get("progressive_groups", []) or [])
        self.reward_progressive_group = list(
            self.slot_data.get("item_progressive_group", self.slot_data.get("reward_progressive_group", [])) or []
        )
        self.task_progressive_reqs = list(self.slot_data.get("task_progressive_reqs", []) or [])

        self.task_costs = list(self.slot_data.get("task_costs", []) or [])
        self.task_cost_amounts = list(self.slot_data.get("task_cost_amounts", []) or [])
        self.item_consumable = list(self.slot_data.get("item_consumable", []) or [])
        self.consumable_groups = dict(self.slot_data.get("consumable_groups", {}) or {})

        self.regions = list(self.slot_data.get("regions", []) or [])
        self.region_default_pcts = dict(self.slot_data.get("region_default_pcts", {}) or {})
        self.task_region = list(self.slot_data.get("task_region", []) or [])
        self.task_region_reqs = list(self.slot_data.get("task_region_reqs", []) or [])

        self.bingo_mode = bool(self.slot_data.get("bingo_mode", False))
        self.bingo_dimension_x = int(self.slot_data.get("bingo_dimension_x", 5) or 5)
        self.bingo_dimension_y = int(self.slot_data.get("bingo_dimension_y", 5) or 5)
        self.bingoal = int(self.slot_data.get("bingoal", 3) or 3)

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

    def on_print_json(self, args: dict):
        super().on_print_json(args)
        parts = args.get("data", [])
        if not parts:
            return
        try:
            text = self.jsontotextparser(copy.deepcopy(parts))
        except Exception:
            text = "".join(p.get("text", "") for p in parts if isinstance(p, dict))
        if text and callable(self.on_print_json_callback):
            self.on_print_json_callback(text)

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
        self.geometry("1080x840")

        self.colors = apply_dark_theme(self)
        ScrollableFrame.bind_mousewheel_to_root(self)

        # Connection/UI state
        self.connection_state = "disconnected"
        self.sent_goal = False
        self.pending_reward_locations = set()  # only track reward loc pending (UI completion)
        self._task_purchases: dict = {}  # {task_idx: {consumable_name: amount_spent}}

        # Incremental task-card reconciliation state
        self._task_cards: dict = {}          # {task_idx: card_dict}
        self._visible_task_order: list = []  # current ordered list of visible task indices
        self._refresh_after_id: int | None = None

        # Dedupe popups
        self._last_deathlink_key = None
        self._last_deathlink_seen_at = 0.0
        self._last_reward_key = None
        self._last_reward_seen_at = 0.0
        self._last_sent_key = None
        self._last_sent_seen_at = 0.0

        # YAML generator state
        self.task_rows = []
        self.item_rows = []
        self.deathlink_rows = []
        self.prog_groups: list = []
        self.regions: list = []
        self.region_default_pcts: dict = {}

        # Notifications state
        self._notifications: list[Notification] = []
        self._max_notifications = 200  # keep memory bounded

        notebook = ttk.Notebook(self)
        notebook.pack(fill="both", expand=True)

        self.play_tab = ttk.Frame(notebook)
        notebook.add(self.play_tab, text="Connect and Play")

        self.console_tab = ttk.Frame(notebook)
        notebook.add(self.console_tab, text="Text Console")

        self.editor_tab = ttk.Frame(notebook)
        notebook.add(self.editor_tab, text="YAML Generator")

        self.bingo_tab = ttk.Frame(notebook)
        notebook.add(self.bingo_tab, text="Taskipelabingo")

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
            self.ctx.on_print_json_callback = self._on_console_message
            self.ctx._cmd_processor = self.ctx.command_processor(self.ctx)
            self.ctx._cmd_processor.console_output_callback = self._append_console_text

        self.loop.call_soon_threadsafe(_init_ctx)

        self.build_ui()

    # ---------------- UI layout ----------------
    def build_ui(self):
        # YAML tab layout
        self.editor_tab.grid_columnconfigure(0, weight=1)
        self.editor_tab.grid_rowconfigure(0, weight=0)   # player name strip
        # rows 1-3 managed dynamically by CollapsibleSection (tasks, items, deathlink)
        self.editor_tab.grid_rowconfigure(4, weight=0, minsize=52)    # buttons

        # --- Player name strip (row 0) ---
        name_strip = ttk.Frame(self.editor_tab)
        name_strip.grid(row=0, column=0, sticky="ew", padx=10, pady=(8, 4))
        ttk.Button(name_strip, text="Tutorial", command=self._open_tutorial).pack(side="right")
        ttk.Label(name_strip, text="Player Name:").pack(side="left", padx=(0, 6))
        self.player_name_var = tk.StringVar()
        ttk.Entry(name_strip, textvariable=self.player_name_var, width=28).pack(side="left")

        # ======== TASKS section (collapsible, row 1, expanded by default) ========
        _tasks_cs = CollapsibleSection(self.editor_tab, "Tasks", row=1,
                                       expanded=True, min_height=180, colors=self.colors)
        _tasks_cs.outer.grid(row=1, column=0, sticky="nsew", padx=10, pady=(0, 2))
        tasks_lf = _tasks_cs.body
        tasks_lf.grid_columnconfigure(0, weight=1)
        tasks_lf.grid_rowconfigure(0, weight=0)   # settings
        tasks_lf.grid_rowconfigure(1, weight=0)   # regions panel
        tasks_lf.grid_rowconfigure(2, weight=1)   # table
        tasks_lf.grid_rowconfigure(3, weight=0, minsize=40)  # button row

        # Task settings sub-row
        task_settings = ttk.Frame(tasks_lf)
        task_settings.grid(row=0, column=0, sticky="ew", padx=10, pady=(6, 4))

        self.lock_prereqs_var = tk.BooleanVar(value=True)
        ttk.Checkbutton(
            task_settings, text="In logic only (lock task completion behind prereqs)",
            variable=self.lock_prereqs_var,
        ).pack(side="left")

        self.hide_unreachable_tasks = tk.BooleanVar(value=True)
        ttk.Checkbutton(
            task_settings, text="Hide Unreachable Tasks",
            variable=self.hide_unreachable_tasks,
        ).pack(side="left", padx=(16, 0))

        ttk.Label(task_settings, text="Goal task(s):").pack(side="left", padx=(16, 4))
        self.goal_tasks_var = tk.StringVar()
        ttk.Entry(task_settings, textvariable=self.goal_tasks_var, width=16).pack(side="left")
        ttk.Label(task_settings, text="(blank = all)", style="Muted.TLabel").pack(side="left", padx=(4, 0))

        # Regions panel (inside tasks section)
        regions_frame = ttk.LabelFrame(tasks_lf, text="Regions")
        regions_frame.grid(row=1, column=0, sticky="ew", padx=10, pady=(0, 4))
        regions_frame.grid_columnconfigure(0, weight=1)

        self.regions_chips_frame = ttk.Frame(regions_frame)
        self.regions_chips_frame.grid(row=0, column=0, sticky="w", padx=10, pady=(4, 2))

        rg_add_row = ttk.Frame(regions_frame)
        rg_add_row.grid(row=1, column=0, sticky="w", padx=10, pady=(0, 6))
        ttk.Label(rg_add_row, text="New region name:").pack(side="left", padx=(0, 6))
        self.new_region_var = tk.StringVar()
        _nr_entry = ttk.Entry(rg_add_row, textvariable=self.new_region_var, width=18)
        _nr_entry.pack(side="left", padx=(0, 6))
        _nr_entry.bind("<Return>", lambda _: self._add_region())
        ttk.Label(rg_add_row, text="Default %:").pack(side="left", padx=(0, 4))
        self.new_region_pct_var = tk.IntVar(value=100)
        ttk.Spinbox(rg_add_row, from_=0, to=100, textvariable=self.new_region_pct_var, width=5).pack(side="left", padx=(0, 6))
        ttk.Button(rg_add_row, text="Add Region", command=self._add_region).pack(side="left")
        _rg_hint = ttk.Label(
            rg_add_row, text="(letters, underscores, hyphens - no digits)",
            style="Muted.TLabel", cursor="question_arrow",
        )
        _rg_hint.pack(side="left", padx=(8, 0))
        Tooltip(_rg_hint, (
            "Region names may only contain letters, underscores, and hyphens - no digits.\n\n"
            "Assign tasks to a region using the Region column in the task table.\n\n"
            "Reference a region in 'Task prereqs' using the region name:\n"
            "  myregion       ->  region's default % of tasks must be completed\n"
            "  myregion-75    ->  exactly 75% of that region's tasks must be completed\n"
            "  myregion*5     ->  exactly 5 tasks in that region must be completed\n\n"
            "A task cannot depend on its own region.\n"
            "Regions also appear as Archipelago regions for location hinting."
        ))
        self._refresh_regions_panel()

        # Tasks scrollable table
        self.tasks_scroll = ScrollableFrame(tasks_lf, colors=self.colors)
        self.tasks_scroll.grid(row=2, column=0, sticky="nsew", padx=10, pady=0)

        t_tbl = self.tasks_scroll.inner
        t_tbl.grid_columnconfigure(0, weight=0)   # #
        t_tbl.grid_columnconfigure(1, weight=3)   # Task
        t_tbl.grid_columnconfigure(2, weight=2)   # Task prereqs
        t_tbl.grid_columnconfigure(3, weight=2)   # Item prereqs
        t_tbl.grid_columnconfigure(4, weight=2)   # Cost
        t_tbl.grid_columnconfigure(5, weight=1)   # Region
        t_tbl.grid_columnconfigure(6, weight=0)   # Count
        t_tbl.grid_columnconfigure(7, weight=0)   # Remove

        ttk.Label(t_tbl, text="#").grid(row=0, column=0, sticky="w", padx=(0, 8))
        ttk.Label(t_tbl, text="Task").grid(row=0, column=1, sticky="w", padx=(0, 8))
        _task_prereq_tip = (
            "Which tasks must be COMPLETED before this task can be checked off.\n\n"
            "Format: task numbers, quoted task names, boolean logic, or region refs:\n"
            "  1, 2, 5               ->  tasks 1 AND 2 AND 5\n"
            '  "Do the dishes"       ->  task named exactly "Do the dishes"\n'
            '  1 && "Buy groceries"  ->  task 1 AND task named "Buy groceries"\n'
            "  1 || 2               ->  task 1 OR task 2\n"
            "  (1 || 2) && 3        ->  (1 or 2) and also 3\n\n"
            "Region refs:\n"
            "  myregion      ->  region's default % of tasks must be completed\n"
            "  myregion-75   ->  exactly 75% of that region's tasks must be completed\n"
            "  myregion*5    ->  exactly 5 tasks in that region must be completed\n\n"
            "Quoted names resolve to the first matching task number at export.\n"
            "Quotation marks are not allowed in task names.\n"
            "A task cannot depend on its own region."
        )
        _item_prereq_tip = (
            "Which items must be RECEIVED before this task can be checked off.\n\n"
            "Format: item numbers, quoted item names, or boolean logic:\n"
            "  1, 2             ->  items 1 AND 2 required\n"
            '  "Some Item"      ->  item named exactly "Some Item"\n'
            '  1 || "Item two"  ->  item 1 OR item named "Item two"\n\n'
            "Quoted names resolve to the first matching item number at export.\n"
            "Quotation marks are not allowed in item names.\n\n"
            "Progressive group refs:\n"
            "  mygroup     ->  count inferred (fills lowest unused position)\n"
            "  mygroup-2   ->  ordering mode: placed in order as the second unlocked task\n"
            "  mygroup*2   ->  count mode: any 2 items from the group\n\n"
            "Can't mix - and * notation for the same group.\n"
            "Ordering mode: each position can only be held by one task.\n"
            "Count mode: multiple tasks can share the same threshold."
        )
        _region_col_tip = (
            "Assign this task to a named region.\n\n"
            "Tasks in a region can be used as completion prerequisites.\n"
            "Other tasks can require 'myregion', 'myregion-75', or 'myregion*5' in Task prereqs.\n\n"
            "Regions also appear as Archipelago regions, enabling location hinting by region.\n"
            "A task cannot depend on its own region."
        )
        _cost_col_tip = (
            "Consumable items that must be spent to unlock (purchase) this task.\n\n"
            'Format: "ItemName"*N, item index*N, or bare name/index (bare = cost 1):\n'
            '  "Gold"*3              ->  spend 3 Gold\n'
            '  1*3                   ->  spend 3 of item #1 (index form)\n'
            '  "Gold"*3 && "Silver"*2  ->  spend 3 Gold AND 2 Silver\n'
            '  "Gold"*5 || "Silver"*10  ->  player chooses which to spend\n'
            '  "Gold"                ->  spend 1 Gold\n\n'
            "Items used as currency must be marked Consumable in the Items table.\n"
            "Leave blank for no cost.\n"
            "For OR-branch tasks, a Make Change button lets players swap branches after purchase."
        )
        _count_task_tip = (
            "How many times this task is duplicated in the exported YAML.\n\n"
            "All copies are generated with identical configuration.\n"
            "A prereq referencing this task requires ALL copies to be completed.\n"
            "Consecutive duplicate task rows are crunched into one row on import."
        )
        _make_tip_header(t_tbl, "Task prereqs", _task_prereq_tip).grid(row=0, column=2, sticky="w", padx=(0, 8))
        _make_tip_header(t_tbl, "Item prereqs", _item_prereq_tip).grid(row=0, column=3, sticky="w", padx=(0, 8))
        _make_tip_header(t_tbl, "Cost",         _cost_col_tip).grid(row=0, column=4, sticky="w", padx=(0, 8))
        _make_tip_header(t_tbl, "Region",       _region_col_tip).grid(row=0, column=5, sticky="w", padx=(0, 8))
        _make_tip_header(t_tbl, "Count",        _count_task_tip).grid(row=0, column=6, sticky="w", padx=(0, 8))
        ttk.Label(t_tbl, text="").grid(row=0, column=7, sticky="w")

        ttk.Label(t_tbl, text="", style="Muted.TLabel").grid(row=1, column=0, sticky="w", padx=(0, 8))
        ttk.Label(t_tbl, text="Location", style="Muted.TLabel").grid(row=1, column=1, sticky="w", padx=(0, 8))
        ttk.Label(t_tbl, text='1  or  "Task Name"  or  region', style="Muted.TLabel").grid(row=1, column=2, sticky="w", padx=(0, 8))
        ttk.Label(t_tbl, text='1  or  "Item Name"', style="Muted.TLabel").grid(row=1, column=3, sticky="w", padx=(0, 8))
        ttk.Label(t_tbl, text='"ItemName"*N', style="Muted.TLabel").grid(row=1, column=4, sticky="w", padx=(0, 8))
        ttk.Label(t_tbl, text="", style="Muted.TLabel").grid(row=1, column=5, sticky="w", padx=(0, 8))
        ttk.Label(t_tbl, text="", style="Muted.TLabel").grid(row=1, column=6, sticky="w", padx=(0, 8))
        ttk.Label(t_tbl, text="", style="Muted.TLabel").grid(row=1, column=7, sticky="w")

        tasks_btn_row = ttk.Frame(tasks_lf)
        tasks_btn_row.grid(row=3, column=0, sticky="ew", padx=10, pady=(4, 8))
        ttk.Button(tasks_btn_row, text="Add Task", command=self.add_task_row).pack(side="left")

        # ======== ITEMS section (collapsible, row 2, expanded by default) ========
        _items_cs = CollapsibleSection(self.editor_tab, "Items", row=2,
                                       expanded=True, min_height=200, colors=self.colors)
        _items_cs.outer.grid(row=2, column=0, sticky="nsew", padx=10, pady=(0, 2))
        items_lf = _items_cs.body
        items_lf.grid_columnconfigure(0, weight=1)
        items_lf.grid_rowconfigure(0, weight=0)   # settings
        items_lf.grid_rowconfigure(1, weight=0)   # prog groups
        items_lf.grid_rowconfigure(2, weight=1)   # table
        items_lf.grid_rowconfigure(3, weight=0, minsize=40)  # button row

        # Item settings sub-row
        item_settings = ttk.Frame(items_lf)
        item_settings.grid(row=0, column=0, sticky="ew", padx=10, pady=(6, 4))

        ttk.Label(item_settings, text="Progression Balancing (0-99):").pack(side="left", padx=(0, 4))
        self.progression_var = tk.IntVar(value=50)
        ttk.Spinbox(item_settings, from_=0, to=99, textvariable=self.progression_var, width=5).pack(side="left")

        ttk.Label(item_settings, text="Accessibility:").pack(side="left", padx=(16, 4))
        self.accessibility_var = tk.StringVar(value="full")
        ttk.Combobox(
            item_settings,
            textvariable=self.accessibility_var,
            values=["full", "items", "minimal"],
            state="readonly",
            width=10,
        ).pack(side="left")

        self.items_counter_var = tk.StringVar(value="0/0 items")
        self.items_counter_lbl = ttk.Label(item_settings, textvariable=self.items_counter_var, style="Muted.TLabel")
        self.items_counter_lbl.pack(side="left", padx=(10, 0))

        # Progressive Groups panel (inside items section)
        prog_frame = ttk.LabelFrame(items_lf, text="Progressive Groups")
        prog_frame.grid(row=1, column=0, sticky="ew", padx=10, pady=(0, 4))
        prog_frame.grid_columnconfigure(0, weight=1)

        self.prog_chips_frame = ttk.Frame(prog_frame)
        self.prog_chips_frame.grid(row=0, column=0, sticky="w", padx=10, pady=(4, 2))

        pg_add_row = ttk.Frame(prog_frame)
        pg_add_row.grid(row=1, column=0, sticky="w", padx=10, pady=(0, 6))
        ttk.Label(pg_add_row, text="New group name:").pack(side="left", padx=(0, 6))
        self.new_group_var = tk.StringVar()
        _ng_entry = ttk.Entry(pg_add_row, textvariable=self.new_group_var, width=18)
        _ng_entry.pack(side="left", padx=(0, 6))
        _ng_entry.bind("<Return>", lambda _: self._add_prog_group())
        ttk.Button(pg_add_row, text="Add Group", command=self._add_prog_group).pack(side="left")
        _pg_hint = ttk.Label(
            pg_add_row, text="(letters, underscores, hyphens - no digits)",
            style="Muted.TLabel", cursor="question_arrow",
        )
        _pg_hint.pack(side="left", padx=(8, 0))
        Tooltip(_pg_hint, (
            "Group names may only contain letters, underscores, and hyphens - no digits.\n\n"
            "See the 'Prog. Group' column header tooltip for more details."
        ))
        self._refresh_prog_groups_panel()

        # Items scrollable table
        self.items_scroll = ScrollableFrame(items_lf, colors=self.colors)
        self.items_scroll.grid(row=2, column=0, sticky="nsew", padx=10, pady=0)

        i_tbl = self.items_scroll.inner
        i_tbl.grid_columnconfigure(0, weight=0)   # #
        i_tbl.grid_columnconfigure(1, weight=3)   # Item
        i_tbl.grid_columnconfigure(2, weight=1)   # Type
        i_tbl.grid_columnconfigure(3, weight=0)   # Filler
        i_tbl.grid_columnconfigure(4, weight=0)   # Consumable
        i_tbl.grid_columnconfigure(5, weight=1)   # Prog. Group
        i_tbl.grid_columnconfigure(6, weight=0)   # Count
        i_tbl.grid_columnconfigure(7, weight=0)   # Remove

        ttk.Label(i_tbl, text="#").grid(row=0, column=0, sticky="w", padx=(0, 8))
        ttk.Label(i_tbl, text="Item").grid(row=0, column=1, sticky="w", padx=(0, 8))
        _type_tip = (
            "Item classification for the Archipelago multiworld:\n\n"
            "  junk        - low-priority filler item\n"
            "  useful      - helpful but not sphere-gating\n"
            "  progression - placed early; advances sphere logic\n"
            "  trap        - negative-effect item\n\n"
            "Items in a progressive group are always forced to 'progression'.\n"
            "Consumable items are always forced to 'progression'."
        )
        _filler_tip = (
            "Mark this as a filler item.\n\n"
            "Filler items send a randomly selected humorous consolation prize to the\n"
            "multiworld instead of a real item. The task can still be completed and\n"
            "count toward prerequisites.\n\n"
            "Leaving the item name blank also produces a filler item at export time."
        )
        _consumable_tip = (
            "Mark this item as a consumable (currency).\n\n"
            "Consumable items can be spent to purchase (unlock) tasks that have a Cost.\n"
            "All copies with the same name are pooled together as shared currency.\n\n"
            "When a task has a cost and all other prereqs are met, a Purchase button\n"
            "appears. Spending locks the task until the cost is deducted.\n\n"
            "Consumable items are always forced to 'progression' and cannot be assigned\n"
            "to a progressive group.\n"
            "Filler items cannot be consumable."
        )
        _prog_group_tip = (
            "Assign this item to a progressive group.\n\n"
            "Group items are interchangeable - receiving any of them increments the group\n"
            "counter. Tasks reference a group in 'Item prereqs' using two modes:\n\n"
            "Items in a group are always forced to 'progression' classification.\n"
            "Consumable items cannot be assigned to a group.\n"
            "Groups are defined in the Progressive Groups panel above."
        )
        _count_item_tip = (
            "How many times this item is duplicated in the exported YAML.\n\n"
            "All copies are generated as separate pool entries with the same name.\n"
            "Consecutive duplicate item rows are crunched into one row on import."
        )
        _make_tip_header(i_tbl, "Type",        _type_tip).grid(row=0, column=2, sticky="w", padx=(0, 8))
        _make_tip_header(i_tbl, "Filler",      _filler_tip).grid(row=0, column=3, sticky="w", padx=(0, 4))
        _make_tip_header(i_tbl, "Consumable",  _consumable_tip).grid(row=0, column=4, sticky="w", padx=(0, 8))
        _make_tip_header(i_tbl, "Prog. Group", _prog_group_tip).grid(row=0, column=5, sticky="w", padx=(0, 8))
        _make_tip_header(i_tbl, "Count",       _count_item_tip).grid(row=0, column=6, sticky="w", padx=(0, 8))
        ttk.Label(i_tbl, text="").grid(row=0, column=7, sticky="w")

        ttk.Label(i_tbl, text="", style="Muted.TLabel").grid(row=1, column=0, sticky="w", padx=(0, 8))
        ttk.Label(i_tbl, text="Multiworld item name (blank = filler)", style="Muted.TLabel").grid(row=1, column=1, sticky="w", padx=(0, 8))
        ttk.Label(i_tbl, text="", style="Muted.TLabel").grid(row=1, column=2, sticky="w", padx=(0, 8))
        ttk.Label(i_tbl, text="", style="Muted.TLabel").grid(row=1, column=3, sticky="w")
        ttk.Label(i_tbl, text="", style="Muted.TLabel").grid(row=1, column=4, sticky="w")
        ttk.Label(i_tbl, text="", style="Muted.TLabel").grid(row=1, column=5, sticky="w")
        ttk.Label(i_tbl, text="", style="Muted.TLabel").grid(row=1, column=6, sticky="w")
        ttk.Label(i_tbl, text="", style="Muted.TLabel").grid(row=1, column=7, sticky="w")

        items_btn_row = ttk.Frame(items_lf)
        items_btn_row.grid(row=3, column=0, sticky="ew", padx=10, pady=(4, 8))
        self.add_item_btn = ttk.Button(
            items_btn_row, text="Add Item", command=self.add_item_row
        )
        self.add_item_btn.pack(side="left")

        # ======== DEATHLINK section (collapsible, row 3, collapsed by default) ========
        _dl_cs = CollapsibleSection(self.editor_tab, "DeathLink", row=3,
                                    expanded=False, min_height=120, colors=self.colors)
        _dl_cs.outer.grid(row=3, column=0, sticky="nsew", padx=10, pady=(0, 2))
        dl = _dl_cs.body
        dl.grid_columnconfigure(0, weight=1)
        dl.grid_rowconfigure(0, weight=0)   # settings
        dl.grid_rowconfigure(1, weight=1)   # pool table
        dl.grid_rowconfigure(2, weight=0, minsize=44)  # add button

        dl_settings = ttk.Frame(dl)
        dl_settings.grid(row=0, column=0, sticky="ew", padx=10, pady=(6, 4))

        self.deathlink_enabled = tk.BooleanVar(value=False)
        ttk.Checkbutton(dl_settings, text="Enable DeathLink", variable=self.deathlink_enabled).pack(side="left")

        ttk.Label(dl_settings, text="Amnesty:").pack(side="left", padx=(16, 4))
        self.deathlink_amnesty_var = tk.IntVar(value=0)
        ttk.Spinbox(dl_settings, from_=0, to=999, textvariable=self.deathlink_amnesty_var, width=5).pack(side="left")

        self.dl_scroll = ScrollableFrame(dl, colors=self.colors)
        self.dl_scroll.grid(row=1, column=0, sticky="nsew", padx=10, pady=(0, 0))

        dl_tbl = self.dl_scroll.inner
        dl_tbl.grid_columnconfigure(0, weight=1)
        dl_tbl.grid_columnconfigure(1, weight=0)
        dl_tbl.grid_columnconfigure(2, weight=0)

        ttk.Label(dl_tbl, text="DeathLink Task").grid(row=0, column=0, sticky="w", padx=(0, 8))
        ttk.Label(dl_tbl, text="Weight").grid(row=0, column=1, columnspan=2, sticky="w")

        ttk.Button(dl, text="Add DeathLink Task", command=self.add_deathlink_row).grid(
            row=2, column=0, sticky="w", padx=10, pady=(0, 10)
        )

        # ======== Bottom buttons (row 4) ========
        bottom = ttk.Frame(self.editor_tab)
        bottom.grid(row=4, column=0, sticky="ew", pady=(8, 0))
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
        self._server_entry = ttk.Entry(conn_frame, textvariable=self.server_var, width=30)
        self._server_entry.grid(row=0, column=1, padx=5)

        ttk.Label(conn_frame, text="Slot Name:").grid(row=1, column=0, sticky="w", padx=5, pady=5)
        self.slot_var = tk.StringVar(value=slot_default)
        self._slot_entry = ttk.Entry(conn_frame, textvariable=self.slot_var, width=30)
        self._slot_entry.grid(row=1, column=1, padx=5)

        ttk.Label(conn_frame, text="Password:").grid(row=2, column=0, sticky="w", padx=5, pady=5)
        self.pass_var = tk.StringVar()
        self._pass_entry = ttk.Entry(conn_frame, textvariable=self.pass_var, width=30, show="*")
        self._pass_entry.grid(row=2, column=1, padx=5)

        for _e in (self._server_entry, self._slot_entry, self._pass_entry):
            _e.bind("<Return>", lambda e: self.connection_state == "disconnected" and self._start_connect())

        btns = ttk.Frame(conn_frame)
        btns.grid(row=3, column=0, columnspan=2, sticky="w", padx=5, pady=(8, 0))

        self.connect_button = ttk.Button(btns, text="Connect", command=self.on_connect_toggle)
        self.connect_button.pack(side="left")

        self.send_deathlink_btn = ttk.Button(btns, text="Send Deathlink", command=self._send_deathlink)
        # shown only when connected with deathlink enabled

        self.connect_status = tk.StringVar(value="Not connected.")
        # ttk.Label(play_root, textvariable=self.connect_status).pack(anchor="w")
        ttk.Label(play_root, textvariable=self.connect_status).grid(row=1, column=0, sticky="w", padx=(0, 10))

        tasks_frame = ttk.LabelFrame(play_root, text="Tasks")
        tasks_frame.grid(row=2, column=0, sticky="nsew", padx=(0, 10), pady=(10, 0))

        self._local_enforce_var = tk.BooleanVar(value=False)
        self._show_locked_var = tk.BooleanVar(value=False)
        self._hide_completed_var = tk.BooleanVar(value=False)
        self._enforce_header_frame = ttk.Frame(tasks_frame)
        ttk.Label(
            self._enforce_header_frame,
            text="Prereqs are optional in your YAML (lock_prereqs is off).",
        ).pack(side="left", padx=(10, 8), pady=4)
        ttk.Checkbutton(
            self._enforce_header_frame,
            text="Enforce locally",
            variable=self._local_enforce_var,
            command=self._on_enforce_toggle,
        ).pack(side="left", pady=4)
        self._show_locked_frame = ttk.Frame(tasks_frame)
        self._show_locked_checkbox = ttk.Checkbutton(
            self._show_locked_frame,
            text="Show hidden tasks",
            variable=self._show_locked_var,
            command=self.refresh_play_tab,
        )
        self._show_locked_checkbox.pack(side="left", padx=(10, 4), pady=4)
        self._hide_completed_checkbox = ttk.Checkbutton(
            self._show_locked_frame,
            text="Hide completed tasks",
            variable=self._hide_completed_var,
            command=self.refresh_play_tab,
        )
        self._hide_completed_checkbox.pack(side="left", padx=(8, 8), pady=4)

        self.play_tasks_scroll = ScrollableFrame(tasks_frame, colors=self.colors)
        self.play_tasks_scroll.pack(fill="both", expand=True, padx=10, pady=10)

        bg = self.colors.get("bg", "#1e1e1e")
        self.play_bingo_frame = ttk.Frame(tasks_frame)
        self._bingo_counter_label = ttk.Label(self.play_bingo_frame, text="")
        self._bingo_counter_label.pack(side="top", anchor="w", padx=10, pady=(6, 0))
        self.play_bingo_canvas = tk.Canvas(self.play_bingo_frame, bg=bg, highlightthickness=0)
        self.play_bingo_canvas.pack(fill="both", expand=True)
        self.play_bingo_canvas.bind("<Configure>", lambda e: self._render_bingo_board())
        self._bingo_buttons = []
        # play_bingo_frame intentionally not packed here; toggled in refresh_play_tab

        # ---- Notifications panel (right column, tabbed) ----
        notif_outer = ttk.Frame(play_root)
        notif_outer.grid(row=0, column=1, rowspan=3, sticky="nsew")
        notif_outer.grid_rowconfigure(0, weight=1)
        notif_outer.grid_columnconfigure(0, weight=1)

        notif_notebook = ttk.Notebook(notif_outer)
        notif_notebook.grid(row=0, column=0, sticky="nsew")

        # -- Notifications tab --
        notif_tab_frame = ttk.Frame(notif_notebook)
        notif_notebook.add(notif_tab_frame, text="Notifications")
        notif_tab_frame.grid_rowconfigure(1, weight=1)
        notif_tab_frame.grid_columnconfigure(0, weight=1)

        notif_btns = ttk.Frame(notif_tab_frame)
        notif_btns.grid(row=0, column=0, sticky="ew", padx=10, pady=(4, 0))
        ttk.Button(notif_btns, text="Clear", command=self._clear_notifications).pack(side="left")

        self.notif_scroll = ScrollableFrame(notif_tab_frame, colors=self.colors)
        self.notif_scroll.grid(row=1, column=0, sticky="nsew", padx=10, pady=10)

        # -- Items tab --
        items_tab_frame = ttk.Frame(notif_notebook)
        notif_notebook.add(items_tab_frame, text="Items")
        items_tab_frame.grid_rowconfigure(0, weight=1)
        items_tab_frame.grid_columnconfigure(0, weight=1)

        self.items_received_scroll = ScrollableFrame(items_tab_frame, colors=self.colors)
        self.items_received_scroll.grid(row=0, column=0, sticky="nsew", padx=10, pady=10)

        # -- Consumable Items tab --
        consumable_tab_frame = ttk.Frame(notif_notebook)
        notif_notebook.add(consumable_tab_frame, text="Consumable Items")
        consumable_tab_frame.grid_rowconfigure(1, weight=1)
        consumable_tab_frame.grid_columnconfigure(0, weight=1)

        _ctab_hint = ttk.Label(
            consumable_tab_frame,
            text="Remaining balance of each consumable item type available to spend.",
            style="Muted.TLabel",
        )
        _ctab_hint.grid(row=0, column=0, sticky="w", padx=10, pady=(6, 2))

        self.consumable_tab_scroll = ScrollableFrame(consumable_tab_frame, colors=self.colors)
        self.consumable_tab_scroll.grid(row=1, column=0, sticky="nsew", padx=10, pady=(0, 10))

        self._build_bingo_tab()
        self._build_console_tab()

    # ---------------- YAML generator actions ----------------
    def add_task_row(self):
        row = TaskRow(
            self.tasks_scroll.inner,
            len(self.task_rows) + 1,
            self._remove_task_row,
            list(self.regions),
        )
        self.task_rows.append(row)
        row.count_var.trace_add("write", lambda *_: self._update_item_counter())
        self._update_item_counter()
        return row

    def add_item_row(self):
        row = ItemRow(
            self.items_scroll.inner,
            len(self.item_rows) + 1,
            self._remove_item_row,
            list(self.prog_groups),
        )
        self.item_rows.append(row)
        row.count_var.trace_add("write", lambda *_: self._update_item_counter())
        self._refresh_item_remove_visibility()
        self._update_item_counter()
        return row

    def _refresh_item_remove_visibility(self):
        for row in self.item_rows:
            row.set_remove_visible(True)

    def _update_item_counter(self):
        if not hasattr(self, "items_counter_lbl"):
            return
        try:
            n_tasks = sum(max(1, int(r.count_var.get())) for r in self.task_rows)
        except (ValueError, tk.TclError):
            n_tasks = len(self.task_rows)
        try:
            n_items = sum(max(1, int(r.count_var.get())) for r in self.item_rows)
        except (ValueError, tk.TclError):
            n_items = len(self.item_rows)
        self.items_counter_var.set(f"{n_items}/{n_tasks} items")
        self.items_counter_lbl.configure(
            style="Warning.TLabel" if n_items != n_tasks else "Muted.TLabel"
        )

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
        self._update_all_item_row_prog_groups()

    def _remove_prog_group(self, gname: str):
        if gname in self.prog_groups:
            self.prog_groups.remove(gname)
        for row in self.item_rows:
            if row.prog_group_var.get() == gname:
                row.prog_group_var.set("")
        self._refresh_prog_groups_panel()
        self._update_all_item_row_prog_groups()

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
                chip, text="x", width=2,
                command=lambda g=gname: self._remove_prog_group(g),
            ).pack(side="left", padx=(0, 2))

    def _update_all_item_row_prog_groups(self):
        for row in self.item_rows:
            row.update_groups(self.prog_groups)

    # ---------------- Region management ----------------
    def _add_region(self):
        name = self.new_region_var.get().strip()
        if not name:
            messagebox.showerror("Error", "Region name cannot be empty.")
            return
        if re.search(r'\d', name):
            messagebox.showerror("Error", f"Region name '{name}' must not contain digits.")
            return
        if name in self.regions:
            messagebox.showerror("Error", f"Region '{name}' already exists.")
            return
        pct = self.new_region_pct_var.get()
        self.regions.append(name)
        self.region_default_pcts[name] = int(pct)
        self.new_region_var.set("")
        self.new_region_pct_var.set(100)
        self._refresh_regions_panel()
        self._update_all_task_row_regions()

    def _remove_region(self, rname: str):
        if rname in self.regions:
            self.regions.remove(rname)
        self.region_default_pcts.pop(rname, None)
        for row in self.task_rows:
            if row.region_var.get() == rname:
                row.region_var.set("")
        self._refresh_regions_panel()
        self._update_all_task_row_regions()

    def _refresh_regions_panel(self):
        if not hasattr(self, "regions_chips_frame"):
            return
        for w in self.regions_chips_frame.winfo_children():
            w.destroy()
        if not self.regions:
            ttk.Label(self.regions_chips_frame, text="No regions defined.", style="Muted.TLabel").pack(side="left")
            return
        for rname in self.regions:
            pct = self.region_default_pcts.get(rname, 100)
            chip = ttk.Frame(self.regions_chips_frame)
            chip.pack(side="left", padx=(0, 6))
            ttk.Label(chip, text=f"{rname} ({pct}%)").pack(side="left", padx=(0, 2))
            ttk.Button(chip, text="x", width=2,
                       command=lambda r=rname: self._remove_region(r)).pack(side="left")

    def _update_all_task_row_regions(self):
        for row in self.task_rows:
            row.update_regions(self.regions)

    def _remove_task_row(self, row):
        if row in self.task_rows:
            self.task_rows.remove(row)
        for i, r in enumerate(self.task_rows, start=1):
            r.index = i
            r.num_label.config(text=str(i))
            r._grid()
        self._refresh_item_remove_visibility()
        self._update_item_counter()

    def _clear_task_rows(self):
        for r in list(self.task_rows):
            try:
                r.remove()
            except Exception:
                pass
        self.task_rows = []

    def _remove_item_row(self, row):
        if row in self.item_rows:
            self.item_rows.remove(row)
        for i, r in enumerate(self.item_rows, start=1):
            r.index = i
            r.num_label.config(text=str(i))
            r._grid()
        self._refresh_item_remove_visibility()
        self._update_item_counter()

    def _clear_item_rows(self):
        for r in list(self.item_rows):
            try:
                r.remove()
            except Exception:
                pass
        self.item_rows = []

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

    def _resolve_name_refs(self, text: str, names: list) -> tuple:
        """
        Replace "Quoted Name" references in a prereq string with 1-based indices.
        Returns (resolved_text, list_of_error_strings).
        Uses the first matching entry in names (0-indexed).
        """
        errors = []
        def replacer(m):
            name = m.group(1)
            for i, n in enumerate(names):
                if n == name:
                    return str(i + 1)
            errors.append(f'No entry found named "{name}"')
            return m.group(0)
        result = re.sub(r'"([^"]*)"', replacer, text)
        return result, errors

    @staticmethod
    def _convert_cost_idx_to_quote(cost_text: str, item_names: list, item_counts: list) -> str:
        """Replace integer-indexed cost refs with quoted names for items with count > 1."""
        import re as _re
        # Match already-quoted refs (leave alone) or bare idx*N / idx patterns
        pattern = _re.compile(r'"[^"]*"\*?\d*|\b(\d+)(?:\*(\d+))?\b')
        def repl(m):
            if m.group(1) is None:
                return m.group(0)  # already quoted, leave alone
            idx = int(m.group(1))
            n = m.group(2) or "1"
            if 1 <= idx <= len(item_names) and item_counts[idx - 1] > 1:
                return f'"{item_names[idx - 1]}"*{n}'
            return m.group(0)
        return pattern.sub(repl, cost_text)

    def export_yaml(self):
        player_name = self.player_name_var.get().strip()
        if not player_name:
            messagebox.showerror("Error", "Player name is required.")
            return

        tasks, task_prereqs, item_prereqs_raw, task_costs, task_region_list, task_counts = [], [], [], [], [], []
        for r in self.task_rows:
            t, tpr, ipr, cost, treg, count = r.get_data()
            if not t:
                continue
            tasks.append(t)
            task_prereqs.append(tpr or "")
            item_prereqs_raw.append(ipr or "")
            task_costs.append(cost or "")
            task_region_list.append(treg or "")
            task_counts.append(count)

        if not tasks:
            messagebox.showerror("Error", "No tasks defined.")
            return

        # Duplicate task name check
        _seen_tasks = {}
        for t in tasks:
            _seen_tasks[t] = _seen_tasks.get(t, 0) + 1
        _dup_tasks = [n for n, c in _seen_tasks.items() if c > 1]
        if _dup_tasks:
            messagebox.showerror(
                "Duplicate Task Names",
                "Duplicate task names are not allowed - use the Count field for multiple copies:\n"
                + "\n".join(_dup_tasks)
            )
            return

        raw_item_names = []
        items, item_types, item_fillers, item_prog_groups, item_consumables, item_counts = [], [], [], [], [], []
        for r in self.item_rows:
            itm, filler, itype, pgrp, consumable, count = r.get_data()
            raw_item_names.append(itm)
            is_filler_row = filler or not itm
            items.append(_random_filler() if is_filler_row else itm)
            item_types.append("junk" if is_filler_row else (itype or "junk"))
            item_fillers.append(bool(is_filler_row))
            item_prog_groups.append(pgrp if not is_filler_row else "")
            item_consumables.append(consumable if not is_filler_row else False)
            item_counts.append(count)

        # Duplicate item name check (non-filler items only)
        _seen_items = {}
        for itm, filler in zip(items, item_fillers):
            if not filler and itm:
                _seen_items[itm] = _seen_items.get(itm, 0) + 1
        _dup_items = [n for n, c in _seen_items.items() if c > 1]
        if _dup_items:
            messagebox.showerror(
                "Duplicate Item Names",
                "Duplicate item names are not allowed - use the Count field for multiple copies:\n"
                + "\n".join(_dup_items)
            )
            return

        total_task_slots = sum(task_counts)
        total_item_slots = sum(item_counts)

        if total_task_slots != total_item_slots:
            proceed = messagebox.askyesno(
                "Unbalanced Counts",
                f"Warning: Unbalanced item and task slot counts will cause generation failures.\n\n"
                f"Task slots: {total_task_slots}  |  Item slots: {total_item_slots}\n\n"
                "Export anyway?"
            )
            if not proceed:
                return

        # Validate no quotation marks in names
        quote_errors = []
        for i, t in enumerate(tasks):
            if '"' in t:
                quote_errors.append(f'Task {i + 1} name contains a quotation mark.')
        for i, itm in enumerate(raw_item_names):
            if itm and '"' in itm:
                quote_errors.append(f'Item {i + 1} name contains a quotation mark.')
        if quote_errors:
            messagebox.showerror("Invalid Names", "\n".join(quote_errors))
            return

        # Validate quoted name references exist
        name_errors = []
        for i, tpr in enumerate(task_prereqs):
            _, errs = self._resolve_name_refs(tpr, tasks)
            name_errors.extend([f'Task {i + 1} task prereqs: {e}' for e in errs])
        for i, ipr in enumerate(item_prereqs_raw):
            _, errs = self._resolve_name_refs(ipr, raw_item_names)
            name_errors.extend([f'Task {i + 1} item prereqs: {e}' for e in errs])
        if name_errors:
            messagebox.showerror("Unresolved Names", "Unresolved name references:\n\n" + "\n".join(name_errors))
            return

        # Convert cost index refs to quoted names for items with count > 1
        task_costs = [
            self._convert_cost_idx_to_quote(cost, raw_item_names, item_counts)
            for cost in task_costs
        ]

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
                "item_progressive_group": item_prog_groups,

                "regions": list(self.regions),
                "region_default_pcts": [self.region_default_pcts.get(r, 100) for r in self.regions],
                "task_region": task_region_list,

                "tasks": tasks,
                "task_count": [str(c) for c in task_counts],
                "items": items,
                "item_types": item_types,
                "item_fillers": item_fillers,
                "item_consumable": ["true" if c else "false" for c in item_consumables],
                "item_count": [str(c) for c in item_counts],
                "task_prereqs": task_prereqs,
                "item_prereqs": item_prereqs_raw,
                "task_cost": task_costs,
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

        # --------- Progressive groups (must be loaded before rows) ---------
        raw_pg = list(block.get("progressive_groups", []) or [])
        self.prog_groups = [str(g).strip() for g in raw_pg if str(g).strip()]
        self._refresh_prog_groups_panel()

        # --------- Regions (must be loaded before task rows) ---------
        raw_rg = list(block.get("regions", []) or [])
        raw_rdp = list(block.get("region_default_pcts", []) or [])
        self.regions = [str(r).strip() for r in raw_rg if str(r).strip()]
        self.region_default_pcts = {}
        for i, rname in enumerate(self.regions):
            try:
                pct = int(raw_rdp[i]) if i < len(raw_rdp) else 100
            except (ValueError, TypeError):
                pct = 100
            self.region_default_pcts[rname] = pct
        self._refresh_regions_panel()

        # --------- Read tasks ---------
        tasks_raw = list(block.get("tasks", []) or [])
        prereqs_raw = list(block.get("task_prereqs", []) or [])
        task_regions_raw = list(block.get("task_region", []) or [])
        task_costs_raw = list(block.get("task_cost", []) or [])
        item_prereqs_raw = list(block.get("item_prereqs", block.get("reward_prereqs", [])) or [])
        task_count_raw = block.get("task_count", None)

        # --------- Read items (support both new and legacy key names) ---------
        items_raw = list(block.get("items", block.get("rewards", [])) or [])
        item_types_raw = list(block.get("item_types", block.get("reward_types", [])) or [])
        item_fillers_raw = list(block.get("item_fillers", []) or [])
        item_prog_group_raw = list(block.get("item_progressive_group", block.get("reward_progressive_group", [])) or [])
        item_consumable_raw = list(block.get("item_consumable", []) or [])
        item_count_raw = block.get("item_count", None)

        def _str(v, default=""):
            return str(v).strip() if v is not None else default

        # --------- Crunch or parse task counts ---------
        if task_count_raw is not None:
            task_count_list = [task_count_raw] if not isinstance(task_count_raw, list) else list(task_count_raw)
            tasks = [_str(t) for t in tasks_raw]
            task_counts = []
            for i in range(len(tasks)):
                try:
                    c = max(1, int(task_count_list[i])) if i < len(task_count_list) else 1
                except (ValueError, TypeError):
                    c = 1
                task_counts.append(c)
            prereqs = [_str(prereqs_raw[i]) if i < len(prereqs_raw) else "" for i in range(len(tasks))]
            task_regions = [_str(task_regions_raw[i]) if i < len(task_regions_raw) else "" for i in range(len(tasks))]
            task_costs = [_str(task_costs_raw[i]) if i < len(task_costs_raw) else "" for i in range(len(tasks))]
            item_prereqs = [_str(item_prereqs_raw[i]) if i < len(item_prereqs_raw) else "" for i in range(len(tasks))]
        else:
            # Crunch consecutive identical task names into single rows with count
            tasks, prereqs, task_regions, task_costs, item_prereqs, task_counts = [], [], [], [], [], []
            i = 0
            while i < len(tasks_raw):
                name = _str(tasks_raw[i])
                count = 1
                j = i + 1
                while j < len(tasks_raw) and _str(tasks_raw[j]) == name:
                    count += 1
                    j += 1
                tasks.append(name)
                prereqs.append(_str(prereqs_raw[i]) if i < len(prereqs_raw) else "")
                task_regions.append(_str(task_regions_raw[i]) if i < len(task_regions_raw) else "")
                task_costs.append(_str(task_costs_raw[i]) if i < len(task_costs_raw) else "")
                item_prereqs.append(_str(item_prereqs_raw[i]) if i < len(item_prereqs_raw) else "")
                task_counts.append(count)
                i = j

        n_tasks = len(tasks)

        # --------- Crunch or parse item counts ---------
        if item_count_raw is not None:
            item_count_list = [item_count_raw] if not isinstance(item_count_raw, list) else list(item_count_raw)
            items = [_str(t) for t in items_raw]
            item_types = [_str(item_types_raw[i], "useful") if i < len(item_types_raw) else "useful" for i in range(len(items))]
            item_fillers = [item_fillers_raw[i] if i < len(item_fillers_raw) else None for i in range(len(items))]
            item_prog_groups = [_str(item_prog_group_raw[i]) if i < len(item_prog_group_raw) else "" for i in range(len(items))]
            item_consumables = [_str(item_consumable_raw[i]).lower() == "true" if i < len(item_consumable_raw) else False for i in range(len(items))]
            item_counts = []
            for i in range(len(items)):
                try:
                    c = max(1, int(item_count_list[i])) if i < len(item_count_list) else 1
                except (ValueError, TypeError):
                    c = 1
                item_counts.append(c)
        else:
            # Crunch consecutive identical item names
            items, item_types, item_fillers, item_prog_groups, item_consumables, item_counts = [], [], [], [], [], []
            i = 0
            while i < len(items_raw):
                name = _str(items_raw[i])
                count = 1
                j = i + 1
                while j < len(items_raw) and _str(items_raw[j]) == name:
                    count += 1
                    j += 1
                items.append(name)
                item_types.append(_str(item_types_raw[i], "useful") if i < len(item_types_raw) else "useful")
                item_fillers.append(item_fillers_raw[i] if i < len(item_fillers_raw) else None)
                item_prog_groups.append(_str(item_prog_group_raw[i]) if i < len(item_prog_group_raw) else "")
                item_consumables.append(_str(item_consumable_raw[i]).lower() == "true" if i < len(item_consumable_raw) else False)
                item_counts.append(count)
                i = j

        n_items = len(items)

        total_task_slots = sum(task_counts)
        total_item_slots = sum(item_counts)
        if total_task_slots != total_item_slots:
            messagebox.showwarning(
                "Unbalanced Counts",
                f"Unbalanced item and task counts can lead to generation failures.\n\n"
                f"Task slots: {total_task_slots}  |  Item slots: {total_item_slots}"
            )

        # Wipe existing UI rows
        self._clear_task_rows()
        self._clear_item_rows()

        for i in range(n_tasks):
            task_row = TaskRow(
                self.tasks_scroll.inner, len(self.task_rows) + 1,
                self._remove_task_row, list(self.regions),
            )
            self.task_rows.append(task_row)
            task_row.count_var.trace_add("write", lambda *_: self._update_item_counter())
            task_row.task_var.set(tasks[i])
            task_row.prereq_var.set(prereqs[i])
            task_row.item_prereq_var.set(item_prereqs[i])
            task_row.cost_var.set(task_costs[i])
            task_row.count_var.set(task_counts[i])
            if task_regions[i] in self.regions:
                task_row.region_var.set(task_regions[i])

        for i in range(n_items):
            itm = items[i]
            rt = item_types[i]
            pgrp = item_prog_groups[i]
            explicit_filler = item_fillers[i]
            consumable = item_consumables[i]
            count = item_counts[i]

            if isinstance(explicit_filler, bool):
                is_filler = explicit_filler
            else:
                is_filler = _is_filler(itm)

            item_row = ItemRow(
                self.items_scroll.inner, len(self.item_rows) + 1,
                self._remove_item_row, list(self.prog_groups),
            )
            self.item_rows.append(item_row)
            item_row.count_var.trace_add("write", lambda *_: self._update_item_counter())
            item_row.set_remove_visible(True)

            if rt not in ("trap", "junk", "useful", "progression"):
                rt = "useful"
            item_row.reward_type_var.set(rt)
            item_row._saved_reward_type = rt
            item_row.count_var.set(count)

            if is_filler:
                item_row.filler_var.set(True)
                item_row.on_filler_toggle()
            else:
                item_row.item_var.set(itm)
                if consumable:
                    item_row.consumable_var.set(True)
                    item_row.on_consumable_toggle()
                elif pgrp in self.prog_groups:
                    item_row.prog_group_var.set(pgrp)

        self._refresh_item_remove_visibility()

        # --------- Populate DeathLink pool ---------
        deathlink_pool = list(block.get("death_link_pool", []) or [])
        deathlink_weights = list(block.get("death_link_weights", []) or [])
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

        self._update_item_counter()
        messagebox.showinfo("Imported", f"Imported YAML from:\n{path}")

    def reset_yaml_generator(self):
        self.player_name_var.set("")
        self.progression_var.set(50)
        self.accessibility_var.set("full")
        self.deathlink_enabled.set(False)
        self.deathlink_amnesty_var.set(0)
        self.lock_prereqs_var.set(True)
        self.hide_unreachable_tasks.set(True)
        self.goal_tasks_var.set("")

        self.prog_groups = []
        self._refresh_prog_groups_panel()

        self.regions = []
        self.region_default_pcts = {}
        self._refresh_regions_panel()

        self._clear_task_rows()
        self._clear_item_rows()
        self._clear_deathlink_rows()
        self.add_task_row()

    # ---------------- Tutorial ----------------
    def _open_tutorial(self):
        if hasattr(self, "_tutorial_win") and self._tutorial_win.winfo_exists():
            self._tutorial_win.lift()
            return

        STEPS = [
            (
                "Welcome to the YAML Generator",
                "This tutorial walks you through every feature of the YAML Generator.\n\n"
                "Taskipelago turns your real-life to-do list into a multiworld game. Each task you "
                "complete becomes a \"location\" that hides an item for one of your teammates. When "
                "they complete their tasks, they find items for you.\n\n"
                "The YAML Generator is where you design your game: what your tasks are, what items "
                "they reward, how tasks depend on each other, and more.\n\n"
                "Click Next to begin. You can reopen this tutorial at any time with the Tutorial button."
            ),
            (
                "Your Player Name",
                "At the very top of the generator is the Player Name field.\n\n"
                "This name identifies you in the multiworld. Your teammates see it when they receive "
                "items that came from your tasks. Choose something recognizable -- your username, "
                "nickname, or real name.\n\n"
                "You can change it any time before exporting your YAML file."
            ),
            (
                "Tasks -- What They Are",
                "The Tasks section (top portion of the generator) is the heart of your game.\n\n"
                "Each task you add becomes a location in the multiworld -- a place where an item can "
                "be hidden. When you complete that task in real life and check it off in the app, you "
                "\"find\" whatever item was placed there for one of your teammates.\n\n"
                "Think of tasks as your personal to-do list: \"Exercise for 30 minutes\", "
                "\"Read 10 pages\", \"Cook dinner\". Anything you want to track works.\n\n"
                "Click \"Add Task\" at the bottom of the Tasks section to add your first task, then "
                "type its name in the Task column."
            ),
            (
                "Task Settings",
                "Above the task table are three settings that apply to all tasks:\n\n"
                "\"In logic only (lock task completion behind prereqs)\"\n"
                "When checked, the app enforces your task dependencies. You cannot check off a task "
                "until its prerequisites are done. Recommended to leave on.\n\n"
                "\"Hide Unreachable Tasks\"\n"
                "When checked, tasks whose prerequisites are not yet met are hidden from the play "
                "screen, keeping it clean and focused on what is currently available.\n\n"
                "\"Goal task(s)\"\n"
                "The task or tasks that win the game for you when completed. Enter a task number "
                "(e.g. 5), a quoted task name (e.g. \"Finish the project\"), or multiple separated "
                "by commas. Leave blank to require ALL tasks to be completed."
            ),
            (
                "Task Dependencies (Task Prereqs column)",
                "The \"Task prereqs\" column defines which other tasks must be completed before this "
                "one becomes available.\n\n"
                "Examples:\n"
                "  (blank)           task is always available from the start\n"
                "  1                 Task 1 must be done first\n"
                "  1, 2, 3           Tasks 1, 2, AND 3 must all be done first\n"
                "  1 || 2            Either Task 1 OR Task 2 must be done first\n"
                "  (1 || 2) && 3     (Task 1 or 2) AND Task 3 must all be done\n\n"
                "You can also refer to tasks by name in quotes:\n"
                "  \"Do the dishes\"   that specific task must be done first\n\n"
                "Region references (covered later):\n"
                "  chores            region's default percentage of tasks done\n"
                "  chores-75         exactly 75% of that region's tasks done\n"
                "  chores*5          exactly 5 tasks in that region done\n\n"
                "Hover over the \"Task prereqs\" column header for a quick reference."
            ),
            (
                "Item Requirements (Item Prereqs column)",
                "The \"Item prereqs\" column defines which items you must have received from the "
                "multiworld before this task becomes available.\n\n"
                "Examples:\n"
                "  (blank)           task doesn't require any items\n"
                "  1                 Item #1 must be received first\n"
                "  1, 2              Items #1 AND #2 must both be received\n"
                "  1 || 2            Either item #1 OR item #2 must be received\n"
                "  \"Magic Key\"      The item named \"Magic Key\" must be received\n\n"
                "Progressive group references (covered in the Progressive Groups step):\n"
                "  power-2           requires the 2nd item unlocked from group \"power\"\n"
                "  power*2           requires any 2 items from group \"power\" received\n\n"
                "Hover over the \"Item prereqs\" column header for a quick reference."
            ),
            (
                "Task Cost (Spending Currency)",
                "The \"Cost\" column lets you require players to spend consumable items to unlock "
                "a task -- like paying in-game currency before being allowed to check it off.\n\n"
                "Format:\n"
                "  \"Gold\"*3                   spend 3 Gold\n"
                "  \"Gold\"*3 && \"Silver\"*2     spend 3 Gold AND 2 Silver\n"
                "  \"Gold\"*5 || \"Silver\"*10    player chooses which branch to spend\n"
                "  \"Gold\"                     spend 1 Gold (bare name = 1)\n\n"
                "For this to work, the item (Gold, Silver, etc.) must be marked Consumable in "
                "the Items table (covered in the Consumable Items step).\n\n"
                "When a task has a cost and all other prerequisites are met, a Purchase button "
                "appears in the play screen. Clicking it deducts the cost from your balance.\n\n"
                "If the cost has an OR branch (||), a Make Change button appears after purchasing. "
                "This lets you swap which branch you paid, in case you need those items elsewhere."
            ),
            (
                "Regions",
                "Regions let you group related tasks together under a shared label.\n\n"
                "Creating a region:\n"
                "In the Regions panel (inside the Tasks section), type a name in \"New region "
                "name\" and click \"Add Region\". Names can only use letters, underscores, and "
                "hyphens -- no spaces or digits.\n\n"
                "Default %:\n"
                "When another task references this region without a specific number, this is the "
                "percentage of the region's tasks that must be done. Default is 100%.\n\n"
                "Assigning tasks to a region:\n"
                "Use the \"Region\" column in the task table to assign each task to a region.\n\n"
                "Referencing a region in Task Prereqs:\n"
                "  chores            region's default percentage done\n"
                "  chores-75         exactly 75% of chores tasks done\n"
                "  chores*5          exactly 5 tasks in chores done\n\n"
                "Regions also appear as Archipelago regions for location hinting."
            ),
            (
                "Task Count (Duplicating Tasks)",
                "The \"Count\" column in the task table lets you create multiple identical copies "
                "of the same task.\n\n"
                "Setting Count to 5 for \"Exercise session\" adds 5 separate exercise sessions "
                "to the game -- each one is its own location with its own hidden item.\n\n"
                "If another task has this task in its prerequisites, ALL copies must be completed "
                "before that other task unlocks.\n\n"
                "When you import a YAML file, consecutive duplicate task rows are automatically "
                "collapsed back into a single row with the correct count."
            ),
            (
                "Items -- What They Are",
                "The Items section (bottom portion of the generator) defines what items exist in "
                "the multiworld item pool.\n\n"
                "Each item you add can be hidden at any location in any player's game -- including "
                "yours. The multiworld distributes items randomly at the start.\n\n"
                "Think of items as rewards and unlocks: keys that open new tasks, currency that "
                "can be spent, collectibles, or anything meaningful to your group.\n\n"
                "A player \"finds\" one of your items by completing a task in their own game. "
                "That item is then delivered to whoever it was assigned to.\n\n"
                "Click \"Add Item\" to add a new item, then give it a descriptive name."
            ),
            (
                "Item Types",
                "Each item has a classification that tells the multiworld how to prioritize "
                "placing it:\n\n"
                "Progression\n"
                "Required to advance the game. The multiworld places these so they're "
                "accessible when needed. Any item referenced in a task's prerequisites should "
                "be Progression.\n\n"
                "Useful\n"
                "Helpful but not strictly required. Placed with moderate priority.\n\n"
                "Junk\n"
                "Low priority filler. The game functions without it.\n\n"
                "Trap\n"
                "A negative item. Other players may receive these from your locations!\n\n"
                "Items in a progressive group and consumable items are automatically forced "
                "to Progression, regardless of what you set here.\n\n"
                "Progression Balancing (0-99): Controls how aggressively the multiworld "
                "places progression items early. 50 is a good default.\n\n"
                "Accessibility: Controls which locations are guaranteed reachable.\n"
                "  full     All locations guaranteed reachable (recommended)\n"
                "  items    All items reachable, some locations may not be\n"
                "  minimal  Only the goal is guaranteed reachable"
            ),
            (
                "Filler Items",
                "Checking the \"Filler\" checkbox marks an item as a generic placeholder.\n\n"
                "Instead of sending the real item name, the multiworld delivers a randomly "
                "selected humorous consolation message to whoever finds it.\n\n"
                "Filler items are useful when you want locations (task completions) that don't "
                "contribute meaningful rewards to the pool -- they just fill the slot count.\n\n"
                "Tip: Leaving an item's name blank also produces a filler item at export time.\n\n"
                "Filler items cannot be marked as Consumable."
            ),
            (
                "Consumable Items (Currency)",
                "Checking \"Consumable\" marks an item as spendable currency for task costs.\n\n"
                "How the full system works:\n"
                "1. Add an item named \"Gold\" and check Consumable.\n"
                "2. Set Count to how many Gold items should be in the pool (e.g. 10).\n"
                "3. In a task's Cost field, write \"Gold\"*3 to require spending 3 Gold.\n"
                "4. When you receive enough Gold and all other prerequisites are met, a "
                "Purchase button appears in the play screen.\n"
                "5. Clicking Purchase deducts the Gold and unlocks the task for completion.\n\n"
                "All copies of a consumable item with the same name are pooled together. "
                "If you have 10 Gold in the pool and receive 4 of them, your balance is 4.\n\n"
                "Consumable items are always classified as Progression automatically.\n"
                "Consumable items cannot be added to a Progressive Group."
            ),
            (
                "Progressive Groups",
                "Progressive groups link several items together as an ordered or counted "
                "series, letting tasks unlock progressively as you receive more group items.\n\n"
                "Setting up:\n"
                "1. In the Progressive Groups panel, type a name and click \"Add Group\".\n"
                "2. In the Items table, assign items to that group using the \"Prog. Group\" "
                "dropdown.\n\n"
                "Ordering Mode (use - notation in Item Prereqs):\n"
                "  power-1           requires the 1st item from the group received\n"
                "  power-2           requires the 2nd item from the group received\n"
                "  power             fills the lowest unused position automatically\n"
                "One task per position. Good for gated progression.\n\n"
                "Count Mode (use * notation in Item Prereqs):\n"
                "  power*2           requires any 2 items from the group received\n"
                "Multiple tasks can share the same threshold.\n\n"
                "You cannot mix - and * notation for the same group.\n"
                "All group items are automatically classified as Progression."
            ),
            (
                "Item Count and Item Settings",
                "Item Count:\n"
                "The \"Count\" column in the item table puts multiple copies of an item into "
                "the pool. Setting Count to 10 for \"Gold\" adds 10 separate Gold items to "
                "the multiworld -- 10 locations that can each yield one Gold.\n\n"
                "This is essential for consumable currency: more copies means a higher "
                "possible balance and more locations that reward that currency.\n\n"
                "When you import a YAML file, consecutive duplicate item rows are automatically "
                "collapsed into a single row with the correct count.\n\n"
                "Progression Balancing (0-99):\n"
                "Controls how aggressively progression items are placed early. 50 is balanced.\n\n"
                "Accessibility:\n"
                "  full     All locations guaranteed reachable (recommended)\n"
                "  items    All items reachable, some locations may not be\n"
                "  minimal  Only the goal location is guaranteed reachable"
            ),
            (
                "DeathLink (Optional Challenge)",
                "DeathLink is an optional challenge mode for the Archipelago multiworld. "
                "When enabled, \"deaths\" are shared between players.\n\n"
                "In Taskipelago, a \"death\" means a DeathLink task gets triggered -- a task "
                "that fires automatically when another player in the multiworld sends a "
                "DeathLink event.\n\n"
                "Enable DeathLink: Check the box in the DeathLink section to participate.\n\n"
                "Amnesty:\n"
                "A buffer before incoming events affect you. With amnesty set to 3, the "
                "first 3 death events from other players are absorbed before your DeathLink "
                "tasks fire.\n\n"
                "Adding DeathLink Tasks:\n"
                "Click \"Add DeathLink Task\" and type a task description. The Weight column "
                "controls how likely each task is to be chosen when an event fires -- higher "
                "weight means more likely."
            ),
            (
                "Export, Import, and Reset",
                "Once your tasks and items are set up, use the buttons at the bottom:\n\n"
                "Export YAML\n"
                "Saves your game design as a YAML file. This is the file you give to your "
                "Archipelago host or upload to the Archipelago website to generate the "
                "multiworld. Share it once and you're ready to play.\n\n"
                "Import YAML\n"
                "Loads a previously exported YAML file back into the generator so you can "
                "make changes and re-export.\n\n"
                "Reset\n"
                "Clears everything and starts fresh. Export first if you want to keep your "
                "work -- reset cannot be undone.\n\n"
                "------\n\n"
                "You are all set! A good starting point for your first game:\n"
                "  - Add 10 to 20 tasks from your real to-do list\n"
                "  - Add 10 to 20 items with creative names\n"
                "  - Set items referenced in prerequisites to Progression\n"
                "  - Set extras to Useful or Junk\n"
                "  - Export and share the YAML with your multiworld host\n\n"
                "Have fun!"
            ),
        ]

        win = tk.Toplevel(self)
        self._tutorial_win = win
        win.title("YAML Generator Tutorial")
        win.resizable(True, True)
        win.minsize(440, 360)

        self.update_idletasks()
        mx = self.winfo_rootx() + self.winfo_width() + 12
        my = self.winfo_rooty()
        sw = win.winfo_screenwidth()
        if mx + 500 > sw:
            mx = max(0, self.winfo_rootx() - 500 - 12)
        win.geometry(f"500x500+{mx}+{my}")

        step_idx = [0]

        header_frame = ttk.Frame(win)
        header_frame.pack(fill="x", padx=16, pady=(14, 0))
        title_var = tk.StringVar()
        counter_var = tk.StringVar()
        ttk.Label(header_frame, textvariable=title_var, font=("TkDefaultFont", 11, "bold")).pack(anchor="w")
        ttk.Label(header_frame, textvariable=counter_var, style="Muted.TLabel").pack(anchor="w", pady=(2, 0))

        ttk.Separator(win, orient="horizontal").pack(side="top", fill="x", padx=16, pady=(8, 0))

        # Bottom bar packed before text frame so it always claims space first
        btn_row = ttk.Frame(win)
        btn_row.pack(side="bottom", fill="x", padx=16, pady=(8, 14))
        prev_btn = ttk.Button(btn_row, text="< Previous")
        prev_btn.pack(side="left")
        close_btn = ttk.Button(btn_row, text="Close", command=win.destroy)
        close_btn.pack(side="right")
        next_btn = ttk.Button(btn_row, text="Next >")
        next_btn.pack(side="right", padx=(0, 8))

        ttk.Separator(win, orient="horizontal").pack(side="bottom", fill="x", padx=16, pady=(0, 8))

        txt_frame = ttk.Frame(win)
        txt_frame.pack(side="top", fill="both", expand=True, padx=16, pady=(8, 0))
        txt_frame.grid_rowconfigure(0, weight=1)
        txt_frame.grid_columnconfigure(0, weight=1)

        bg = self.colors.get("panel", "#252526")
        fg = self.colors.get("fg", "#e6e6e6")
        txt = tk.Text(
            txt_frame, wrap="word", relief="flat", borderwidth=0,
            background=bg, foreground=fg, font=("TkDefaultFont", 10),
            padx=6, pady=6, state="disabled",
        )
        sb = ttk.Scrollbar(txt_frame, orient="vertical", command=txt.yview)
        txt.configure(yscrollcommand=sb.set)
        txt.grid(row=0, column=0, sticky="nsew")
        sb.grid(row=0, column=1, sticky="ns")

        def show_step(i: int):
            step_idx[0] = i
            title, content = STEPS[i]
            title_var.set(title)
            counter_var.set(f"Step {i + 1} of {len(STEPS)}")
            txt.configure(state="normal")
            txt.delete("1.0", "end")
            txt.insert("1.0", content)
            txt.configure(state="disabled")
            txt.yview_moveto(0.0)
            prev_btn.state(["disabled"] if i == 0 else ["!disabled"])
            if i == len(STEPS) - 1:
                next_btn.configure(text="Finish", command=win.destroy)
            else:
                next_btn.configure(text="Next >", command=lambda: show_step(step_idx[0] + 1))

        prev_btn.configure(command=lambda: show_step(step_idx[0] - 1))
        show_step(0)

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
        self.send_deathlink_btn.pack_forget()
        self.sent_goal = False

        if getattr(self, "ctx", None) and self.ctx.server:
            async def _do_disconnect():
                await self.ctx.disconnect()

            self.loop.call_soon_threadsafe(lambda: asyncio.create_task(_do_disconnect()))

        if getattr(self, "ctx", None):
            self.ctx._deathlink_tag_enabled = False

        self._clear_notifications()
        self._update_console_connection_state(False)
        self.after(0, self._clear_play_state)

    def _clear_play_state(self):
        self.pending_reward_locations = set()
        self._task_purchases = {}
        if hasattr(self, "_local_enforce_var"):
            self._local_enforce_var.set(False)
        if hasattr(self, "_show_locked_var"):
            self._show_locked_var.set(False)
        if hasattr(self, "_hide_completed_var"):
            self._hide_completed_var.set(False)
        if getattr(self, "ctx", None):
            self.ctx.tasks = []
            self.ctx.items = []
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
            self.ctx.regions = []
            self.ctx.region_default_pcts = {}
            self.ctx.task_region = []
            self.ctx.task_region_reqs = []
            self.ctx.bingo_mode = False
            self.ctx.bingo_dimension_x = 5
            self.ctx.bingo_dimension_y = 5
            self.ctx.bingoal = 3
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
    def _schedule_play_refresh(self, delay_ms: int = 50) -> None:
        if self._refresh_after_id is not None:
            self.after_cancel(self._refresh_after_id)
        self._refresh_after_id = self.after(delay_ms, self.refresh_play_tab)

    def _on_enforce_toggle(self):
        if not self._local_enforce_var.get():
            self._show_locked_var.set(False)
        self.refresh_play_tab()

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

        self._recalculate_purchases_from_completed()
        self._maybe_send_goal_complete()
        self._schedule_play_refresh()
        self.after(0, self._render_items_tab)
        self.after(0, self._render_consumable_tab)
        if self.connection_state == "connected":
            self._update_console_connection_state(True)

        dl_enabled = getattr(self.ctx, "death_link_enabled", False) if getattr(self, "ctx", None) else False
        if self.connection_state == "connected" and dl_enabled:
            self.send_deathlink_btn.pack(side="left", padx=(8, 0))
        else:
            self.send_deathlink_btn.pack_forget()

    def _build_task_card(self, parent: tk.Widget, task_idx: int) -> dict:
        panel = self.colors.get("panel", "#252526")
        border = self.colors.get("border", "#3a3a3a")
        fg = self.colors.get("fg", "#e6e6e6")
        muted = self.colors.get("muted", "#bdbdbd")

        card = tk.Frame(parent, bg=panel, highlightbackground=border, highlightthickness=1)

        top = tk.Frame(card, bg=panel)
        top.pack(fill="x", padx=10, pady=(8, 2))

        label = tk.Label(
            top, text="", bg=panel, fg=fg,
            font=("Segoe UI", 12), wraplength=720, justify="left", anchor="w",
        )
        label.pack(side="left", fill="x", expand=True)

        complete_btn = ttk.Button(
            top, text="Complete",
            command=lambda idx=task_idx: self.complete_task(idx),
        )
        purchase_btn = ttk.Button(
            top, text="Purchase",
            command=lambda idx=task_idx: self._attempt_purchase(idx),
        )
        mc_btn = ttk.Button(
            top, text="Make Change",
            command=lambda idx=task_idx: self._attempt_make_change(idx),
        )

        hints = [
            tk.Label(card, text="", bg=panel, fg=muted,
                     font=("Segoe UI", 10), anchor="w", justify="left", wraplength=740)
            for _ in range(4)
        ]
        spacer = tk.Frame(card, bg=panel, height=6)

        return {
            "frame": card,
            "label": label,
            "complete_btn": complete_btn,
            "purchase_btn": purchase_btn,
            "make_change_btn": mc_btn,
            "hints": hints,
            "spacer": spacer,
            "sig": (),
        }

    def _apply_task_card_state(self, card_dict: dict, s: dict) -> None:
        card_dict["label"].config(text=s["label_text"], fg=s["label_color"])

        complete_btn = card_dict["complete_btn"]
        purchase_btn = card_dict["purchase_btn"]
        mc_btn = card_dict["make_change_btn"]

        complete_btn.pack_forget()
        purchase_btn.pack_forget()
        mc_btn.pack_forget()

        if s["completed"]:
            if s["can_make_change"]:
                mc_btn.pack(side="right", padx=(10, 0))
        elif s["show_purchase"]:
            purchase_btn.pack(side="right", padx=(10, 0))
        else:
            if s["can_complete"]:
                complete_btn.state(["!disabled"])
            else:
                complete_btn.state(["disabled"])
            complete_btn.pack(side="right", padx=(10, 0))
            if s["can_make_change"]:
                mc_btn.pack(side="right", padx=(10, 0))

        showed = False
        for j, h in enumerate(card_dict["hints"]):
            text = s["hint_texts"][j] if j < len(s["hint_texts"]) else ""
            if text:
                h.config(text=text)
                h.pack(fill="x", padx=28, pady=(0, 2))
                showed = True
            else:
                h.pack_forget()

        if showed:
            card_dict["spacer"].pack_forget()
        else:
            card_dict["spacer"].pack(fill="x")

        card_dict["sig"] = s["sig"]

    def refresh_play_tab(self):
        self._refresh_after_id = None

        connected = bool(
            getattr(self, "ctx", None)
            and self.ctx.tasks
            and self.ctx.base_reward_location_id is not None
            and self.ctx.base_complete_location_id is not None
        )
        bingo_mode = bool(getattr(self.ctx, "bingo_mode", False)) if getattr(self, "ctx", None) else False
        yaml_lock = bool(getattr(self.ctx, "lock_prereqs", False)) if getattr(self, "ctx", None) else True
        hide_tasks = bool(getattr(self.ctx, "hide_unreachable_tasks", True)) if getattr(self, "ctx", None) else True
        local_enforce = self._local_enforce_var.get()

        if connected and not yaml_lock and not bingo_mode:
            self._enforce_header_frame.pack(side="top", fill="x", before=self.play_tasks_scroll)
        else:
            self._enforce_header_frame.pack_forget()
        effective_lock_for_header = yaml_lock or local_enforce
        if connected and not bingo_mode:
            self._show_locked_frame.pack(side="top", fill="x", before=self.play_tasks_scroll)
            if effective_lock_for_header and hide_tasks:
                self._show_locked_checkbox.pack(side="left", padx=(10, 4), pady=4)
            else:
                self._show_locked_checkbox.pack_forget()
            self._hide_completed_checkbox.pack_forget()
            self._hide_completed_checkbox.pack(side="left", padx=(8, 8), pady=4)
        else:
            self._show_locked_frame.pack_forget()

        def _clear_task_cards():
            for cd in self._task_cards.values():
                try:
                    cd["frame"].destroy()
                except Exception:
                    pass
            self._task_cards.clear()
            self._visible_task_order.clear()

        if not connected:
            _clear_task_cards()
            self.play_bingo_frame.pack_forget()
            self.play_tasks_scroll.pack(fill="both", expand=True, padx=10, pady=10)
            return

        if bingo_mode:
            _clear_task_cards()
            self.play_tasks_scroll.pack_forget()
            self.play_bingo_frame.pack(fill="both", expand=True, padx=10, pady=10)
            self._render_bingo_board()
            return
        else:
            self.play_bingo_frame.pack_forget()
            self.play_tasks_scroll.pack(fill="both", expand=True, padx=10, pady=10)

        fg = self.colors.get("fg", "#e6e6e6")
        muted = self.colors.get("muted", "#bdbdbd")

        checked = set(getattr(self.ctx, "checked_locations_set", set()) or set())
        prereq_list = list(getattr(self.ctx, "task_prereqs", []) or [])
        item_prereq_list = list(getattr(self.ctx, "item_prereqs", []) or [])
        effective_lock = yaml_lock or self._local_enforce_var.get()
        show_locked = self._show_locked_var.get()
        hide_completed = self._hide_completed_var.get()
        cost_amounts = list(getattr(self.ctx, "task_cost_amounts", []) or [])

        new_visible: list = []  # [(task_idx, s_dict), ...]

        for i, task_name in enumerate(self.ctx.tasks):
            complete_loc_id = self.ctx.base_complete_location_id + i
            completed = complete_loc_id in checked

            task_prereq_ok = True
            task_prereq_text = ""
            if i < len(prereq_list):
                raw = prereq_list[i]
                task_prereq_text = ("" if raw is None else str(raw)).strip()
                if task_prereq_text:
                    task_prereq_ok = self._prereqs_satisfied(task_prereq_text, checked)

            item_prereq_ok = True
            item_prereq_text = ""
            if i < len(item_prereq_list):
                raw = item_prereq_list[i]
                item_prereq_text = ("" if raw is None else str(raw)).strip()
                if item_prereq_text:
                    item_prereq_ok = self._reward_prereqs_satisfied(item_prereq_text, checked)

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
                    item_prereq_ok = False
                prog_hint_parts.append(f"group '{g}' (need {c})")

            region_reqs = []
            task_region_reqs_list = list(getattr(self.ctx, "task_region_reqs", []) or [])
            if i < len(task_region_reqs_list):
                raw_rr = task_region_reqs_list[i]
                if isinstance(raw_rr, list):
                    region_reqs = raw_rr
            region_hint_parts = []
            region_prereq_ok = True
            for req in region_reqs:
                if isinstance(req, dict):
                    r = req.get("region", "")
                    abs_count = req.get("abs_count")
                    pct = req.get("pct", 100)
                    if abs_count is not None:
                        if not self._region_req_satisfied_abs(r, abs_count):
                            region_prereq_ok = False
                            region_hint_parts.append(f"region '{r}' (need {abs_count} tasks)")
                    else:
                        if not self._region_req_satisfied(r, pct):
                            region_prereq_ok = False
                            region_hint_parts.append(f"region '{r}' ({pct}% completed)")
                else:
                    r, pct = req[0], req[1]
                    if not self._region_req_satisfied(r, pct):
                        region_prereq_ok = False
                        region_hint_parts.append(f"region '{r}' ({pct}% completed)")

            task_has_cost = i < len(cost_amounts) and bool(cost_amounts[i])
            cost_paid = not task_has_cost or (not effective_lock) or self._task_cost_is_paid(i)

            other_prereqs_ok = task_prereq_ok and item_prereq_ok and region_prereq_ok
            cost_only_locked = other_prereqs_ok and not cost_paid

            would_hide = (not other_prereqs_ok) and hide_tasks and effective_lock
            show_as_locked = would_hide and show_locked
            if would_hide and not show_as_locked:
                continue
            if completed and hide_completed:
                continue

            if show_as_locked:
                label_text = f"{i+1}. Locked Task"
                label_color = muted
            elif completed:
                label_text = f"✔ {i+1}. {task_name}"
                label_color = muted
            else:
                label_text = f"{i+1}. {task_name}"
                label_color = fg

            hint_texts = ["", "", "", ""]
            if not completed:
                if task_prereq_text and not task_prereq_ok:
                    hint_texts[0] = f"Locked behind task(s): {task_prereq_text}"
                if (item_prereq_text or prog_hint_parts) and not item_prereq_ok:
                    parts = []
                    if item_prereq_text:
                        parts.append(self._reward_prereq_display(item_prereq_text))
                    parts.extend(prog_hint_parts)
                    hint_texts[1] = f"Locked behind item(s): {', '.join(parts)}"
                if region_hint_parts and not region_prereq_ok:
                    hint_texts[2] = f"Locked behind region(s): {', '.join(region_hint_parts)}"
                if cost_only_locked and effective_lock:
                    branches = cost_amounts[i] if i < len(cost_amounts) else []
                    if branches:
                        cost_parts = [" && ".join(f"{amt} {name}" for name, amt in branch) for branch in branches]
                        cost_text = " || ".join(f"({p})" if len(branches) > 1 else p for p in cost_parts)
                        hint_texts[3] = f"Requires purchase: {cost_text}"

            task_branches = cost_amounts[i] if i < len(cost_amounts) else []
            can_make_change = len(task_branches) > 1 and i in self._task_purchases
            can_complete = not (effective_lock and (not other_prereqs_ok or not cost_paid))
            show_purchase = cost_only_locked and effective_lock

            sig = (label_text, label_color, can_complete, show_purchase, can_make_change, *hint_texts)
            new_visible.append((i, {
                "label_text": label_text,
                "label_color": label_color,
                "completed": completed,
                "can_complete": can_complete,
                "show_purchase": show_purchase,
                "can_make_change": can_make_change,
                "hint_texts": hint_texts,
                "sig": sig,
            }))

        new_visible_indices = [idx for idx, _ in new_visible]
        new_visible_set = set(new_visible_indices)

        # Destroy cards that are no longer visible
        for old_idx in list(self._task_cards.keys()):
            if old_idx not in new_visible_set:
                try:
                    self._task_cards[old_idx]["frame"].destroy()
                except Exception:
                    pass
                del self._task_cards[old_idx]

        # Create or update each visible task card
        for task_idx, s in new_visible:
            if task_idx not in self._task_cards:
                self._task_cards[task_idx] = self._build_task_card(
                    self.play_tasks_scroll.inner, task_idx
                )
            card_dict = self._task_cards[task_idx]
            if card_dict["sig"] != s["sig"]:
                self._apply_task_card_state(card_dict, s)

        # Re-pack all cards in order when the visible set or order changed
        if new_visible_indices != self._visible_task_order:
            for task_idx in new_visible_indices:
                self._task_cards[task_idx]["frame"].pack_forget()
            prev = None
            for task_idx in new_visible_indices:
                f = self._task_cards[task_idx]["frame"]
                if prev is not None:
                    f.pack(fill="x", pady=6, padx=4, after=prev)
                else:
                    f.pack(fill="x", pady=6, padx=4)
                prev = f
            self._visible_task_order = new_visible_indices

    def _render_bingo_board(self):
        for btn in getattr(self, "_bingo_buttons", []):
            try:
                btn.destroy()
            except Exception:
                pass
        self._bingo_buttons = []

        canvas = self.play_bingo_canvas
        canvas.delete("all")

        if not getattr(self, "ctx", None):
            return

        X = int(getattr(self.ctx, "bingo_dimension_x", 5) or 5)
        Y = int(getattr(self.ctx, "bingo_dimension_y", 5) or 5)
        bingoal = int(getattr(self.ctx, "bingoal", 3) or 3)
        n_spaces = X * Y

        tasks = list(getattr(self.ctx, "tasks", []) or [])
        if len(tasks) < n_spaces:
            return

        checked = set(getattr(self.ctx, "checked_locations_set", set()) or set())
        base_complete = getattr(self.ctx, "base_complete_location_id", None)
        base_reward = getattr(self.ctx, "base_reward_location_id", None)
        base_item = getattr(self.ctx, "base_item_id", None)

        if base_complete is None or base_reward is None or base_item is None:
            return

        received = self._received_item_ids()

        middle = n_spaces // 2
        space_completed = [(base_complete + i) in checked for i in range(n_spaces)]
        space_unlocked = [(base_item + i) in received or i == middle for i in range(n_spaces)]

        lines = _bingo_lines(X, Y)
        L = len(lines)
        line_completed = [all(space_completed[s] for s in line) for line in lines]
        n_bingos = sum(line_completed)

        space_in_bingo = [False] * n_spaces
        for li, line in enumerate(lines):
            if line_completed[li]:
                for s in line:
                    space_in_bingo[s] = True

        self._auto_complete_bingo_lines(lines, space_completed, base_complete, base_reward, checked)

        needed_more = max(0, bingoal - n_bingos)
        self._bingo_counter_label.config(
            text=f"{n_bingos} of {L} bingos complete (need {needed_more} more)"
        )

        w = canvas.winfo_width()
        h = canvas.winfo_height()
        if w <= 1 or h <= 1:
            canvas.after(50, self._render_bingo_board)
            return

        panel = self.colors.get("panel", "#252526")
        border = self.colors.get("border", "#3a3a3a")
        fg = self.colors.get("fg", "#e6e6e6")
        muted = self.colors.get("muted", "#bdbdbd")

        cell_size = max(10, min(w // X, h // Y))
        grid_w = cell_size * X
        grid_h = cell_size * Y
        grid_x = (w - grid_w) // 2
        grid_y = (h - grid_h) // 2

        font_size = max(7, cell_size // 12)
        font = ("Segoe UI", font_size)
        padding = 6

        for i in range(n_spaces):
            row = i // X
            col = i % X
            x0 = grid_x + col * cell_size
            y0 = grid_y + row * cell_size
            x1 = x0 + cell_size
            y1 = y0 + cell_size

            if space_in_bingo[i]:
                cell_bg = "#1a4a1a"
            elif space_completed[i]:
                cell_bg = "#4a3a00"
            else:
                cell_bg = panel

            canvas.create_rectangle(x0, y0, x1, y1, fill=cell_bg, outline=border, width=1)

            if not space_unlocked[i]:
                canvas.create_text(
                    (x0 + x1) // 2, (y0 + y1) // 2,
                    text="Locked", fill=muted, font=font, anchor="center",
                    width=cell_size - 2 * padding,
                )
            elif space_completed[i]:
                canvas.create_text(
                    (x0 + x1) // 2, (y0 + y1) // 2,
                    text=f"✔ {tasks[i]}", fill=muted, font=font, anchor="center",
                    width=cell_size - 2 * padding,
                )
            else:
                btn_h = 22
                text_cy = y0 + padding + (cell_size - btn_h - 2 * padding) // 2
                canvas.create_text(
                    (x0 + x1) // 2, text_cy,
                    text=tasks[i], fill=fg, font=font, anchor="center",
                    width=cell_size - 2 * padding,
                )
                btn = ttk.Button(
                    canvas, text="Complete",
                    command=lambda idx=i: self.complete_task(idx),
                )
                canvas.create_window((x0 + x1) // 2, y1 - padding, window=btn, anchor="s")
                self._bingo_buttons.append(btn)

    def _auto_complete_bingo_lines(
        self, lines: list, space_completed: list,
        base_complete: int, base_reward: int, checked: set,
    ):
        n_spaces = len(space_completed)
        for li, line in enumerate(lines):
            if all(space_completed[s] for s in line):
                line_task_idx = n_spaces + li
                line_complete_id = base_complete + line_task_idx
                line_reward_id = base_reward + line_task_idx
                if (line_complete_id not in checked
                        and line_complete_id not in self.pending_reward_locations):
                    self.pending_reward_locations.add(line_complete_id)

                    async def _send_line(cid=line_complete_id, rid=line_reward_id):
                        await self.ctx.send_msgs([{
                            "cmd": "LocationChecks",
                            "locations": [cid, rid],
                        }])

                    self.loop.call_soon_threadsafe(
                        lambda s=_send_line: asyncio.create_task(s())
                    )

    # ---------------- Text Console tab ----------------
    def _build_console_tab(self):
        bg = self.colors.get("bg", "#1e1e1e")
        fg = self.colors.get("fg", "#e6e6e6")

        tab = self.console_tab
        tab.grid_rowconfigure(0, weight=1)
        tab.grid_rowconfigure(1, weight=0)
        tab.grid_columnconfigure(0, weight=1)

        # Message history - tk.Text in readonly mode
        text_frame = tk.Frame(tab, bg=bg)
        text_frame.grid(row=0, column=0, sticky="nsew", padx=6, pady=(6, 0))
        text_frame.grid_rowconfigure(0, weight=1)
        text_frame.grid_columnconfigure(0, weight=1)

        self.console_text = tk.Text(
            text_frame,
            bg=bg, fg=fg, insertbackground=fg,
            relief="flat", wrap="word",
            font=("Consolas", 10),
            state="disabled",
        )
        self.console_text.grid(row=0, column=0, sticky="nsew")

        sb = ttk.Scrollbar(text_frame, orient="vertical", command=self.console_text.yview)
        sb.grid(row=0, column=1, sticky="ns")
        self.console_text.configure(yscrollcommand=sb.set)

        # Input bar
        input_frame = tk.Frame(tab, bg=bg)
        input_frame.grid(row=1, column=0, sticky="ew", padx=6, pady=6)
        input_frame.grid_columnconfigure(0, weight=1)

        self.console_input_var = tk.StringVar()
        self.console_input_entry = ttk.Entry(input_frame, textvariable=self.console_input_var)
        self.console_input_entry.grid(row=0, column=0, sticky="ew", padx=(0, 6))
        self.console_input_entry.bind("<Return>", self._send_console_message)

        ttk.Button(input_frame, text="Send", command=self._send_console_message).grid(row=0, column=1)

        self._update_console_connection_state(False)

    def _update_console_connection_state(self, connected: bool):
        if not hasattr(self, "console_input_entry"):
            return
        if connected:
            self.console_input_var.set("")
            self.console_input_entry.state(["!disabled"])
            self.console_input_entry.configure(foreground=self.colors.get("fg", "#e6e6e6"))
        else:
            self.console_input_var.set("Must be connected to a multiworld")
            self.console_input_entry.state(["disabled"])

    def _on_console_message(self, text: str):
        self.after(0, lambda t=text: self._append_console_text(t))

    _ANSI_RE = re.compile(r"\x1b\[([0-9;]*)m")
    _ANSI_FG = {
        30: "#555555", 31: "#cc4444", 32: "#55aa55", 33: "#aaaa44",
        34: "#5588cc", 35: "#aa55aa", 36: "#44aaaa", 37: "#cccccc",
        90: "#888888", 91: "#ff6666", 92: "#66cc66", 93: "#cccc66",
        94: "#6699ff", 95: "#cc66cc", 96: "#66cccc", 97: "#ffffff",
    }
    _ANSI_BG = {
        40: "#000000", 41: "#660000", 42: "#006600", 43: "#666600",
        44: "#000066", 45: "#660066", 46: "#006666", 47: "#666666",
        100: "#333333", 101: "#993333", 102: "#339933", 103: "#999933",
        104: "#333399", 105: "#993399", 106: "#339999", 107: "#999999",
    }

    def _get_ansi_tag(self, fg, bg, bold):
        tag = f"ansi_{fg}_{bg}_{bold}"
        if tag not in self.console_text.tag_names():
            kw = {}
            if fg is not None:
                kw["foreground"] = self._ANSI_FG.get(fg, "#cccccc")
            if bg is not None:
                kw["background"] = self._ANSI_BG.get(bg, "#000000")
            if bold:
                kw["font"] = ("Consolas", 10, "bold")
            self.console_text.tag_configure(tag, **kw)
        return tag

    def _append_console_text(self, text: str):
        if not hasattr(self, "console_text"):
            return
        widget = self.console_text
        widget.configure(state="normal")
        fg = None
        bg = None
        bold = False
        pos = 0
        for m in self._ANSI_RE.finditer(text):
            plain = text[pos:m.start()]
            if plain:
                tag = self._get_ansi_tag(fg, bg, bold)
                widget.insert("end", plain, tag)
            pos = m.end()
            codes_str = m.group(1)
            codes = [int(c) for c in codes_str.split(";") if c] if codes_str else [0]
            for code in codes:
                if code == 0:
                    fg = bg = None
                    bold = False
                elif code == 1:
                    bold = True
                elif code == 22:
                    bold = False
                elif 30 <= code <= 37 or 90 <= code <= 97:
                    fg = code
                elif 40 <= code <= 47 or 100 <= code <= 107:
                    bg = code
        plain = text[pos:]
        if plain:
            widget.insert("end", plain, self._get_ansi_tag(fg, bg, bold))
        widget.insert("end", "\n")
        widget.see("end")
        widget.configure(state="disabled")

    def _send_console_message(self, _event=None):
        if not hasattr(self, "console_input_entry"):
            return
        if self.connection_state != "connected":
            return
        msg = self.console_input_var.get().strip()
        if not msg:
            return
        self.console_input_var.set("")
        self._append_console_text(f"> {msg}")
        if msg.startswith("/"):
            proc = getattr(self.ctx, "_cmd_processor", None)
            if proc is not None:
                self.loop.call_soon_threadsafe(lambda m=msg: proc(m))
            return
        self.loop.call_soon_threadsafe(
            lambda: asyncio.create_task(self.ctx.send_msgs([{"cmd": "Say", "text": msg}]))
        )

    # ---------------- Consumable item helpers ----------------

    def _consumable_received_counts(self) -> dict:
        """Count received items per consumable display name."""
        ctx = getattr(self, "ctx", None)
        if not ctx:
            return {}
        base_item = getattr(ctx, "base_item_id", None)
        items_text = list(getattr(ctx, "items", []) or [])
        item_consumable = list(getattr(ctx, "item_consumable", []) or [])
        items_received = list(getattr(ctx, "items_received", []) or [])
        counts: dict = {}
        for it in items_received:
            item_id = getattr(it, "item", None)
            if item_id is None or base_item is None:
                continue
            idx = item_id - base_item
            if 0 <= idx < len(items_text):
                consumable_flag = item_consumable[idx] if idx < len(item_consumable) else False
                if consumable_flag:
                    name = items_text[idx]
                    counts[name] = counts.get(name, 0) + 1
        return counts

    def _consumable_spent_counts(self) -> dict:
        """Sum up all recorded purchase deductions by consumable name."""
        totals: dict = {}
        for deduction in self._task_purchases.values():
            for name, amt in deduction.items():
                totals[name] = totals.get(name, 0) + amt
        return totals

    def _consumable_balance(self) -> dict:
        """Remaining balance per consumable name (received - spent)."""
        received = self._consumable_received_counts()
        spent = self._consumable_spent_counts()
        all_names = set(received) | set(spent)
        return {name: received.get(name, 0) - spent.get(name, 0) for name in all_names}

    def _task_cost_is_paid(self, task_idx: int) -> bool:
        """True if the task has no cost or has been purchased."""
        ctx = getattr(self, "ctx", None)
        if not ctx:
            return True
        cost_amounts = list(getattr(ctx, "task_cost_amounts", []) or [])
        if task_idx >= len(cost_amounts) or not cost_amounts[task_idx]:
            return True
        return task_idx in self._task_purchases

    def _attempt_purchase(self, task_idx: int):
        """Deduct cost for task_idx, prompting for OR branch if needed."""
        ctx = getattr(self, "ctx", None)
        if not ctx:
            return
        cost_amounts = list(getattr(ctx, "task_cost_amounts", []) or [])
        if task_idx >= len(cost_amounts) or not cost_amounts[task_idx]:
            return
        branches = cost_amounts[task_idx]  # list of [[name, amt], ...]
        if not branches:
            return

        balance = self._consumable_balance()

        # Filter to branches the player can afford
        def _can_afford(branch):
            for name, amt in branch:
                if balance.get(name, 0) < amt:
                    return False
            return True

        affordable = [b for b in branches if _can_afford(b)]
        if not affordable:
            messagebox.showerror(
                "Insufficient Funds",
                "You don't have enough consumable items to purchase this task."
            )
            return

        if len(branches) > 1:
            # Show OR branch selection dialog
            branch_labels = []
            for b in affordable:
                parts = ", ".join(f"{amt} {name}" for name, amt in b)
                branch_labels.append(parts)

            chosen_branch = self._choose_cost_branch(branch_labels)
            if chosen_branch is None:
                return
            chosen = affordable[chosen_branch]
        else:
            chosen = affordable[0]

        deduction = {name: amt for name, amt in chosen}
        self._task_purchases[task_idx] = deduction
        self._schedule_play_refresh()
        self.after(0, self._render_consumable_tab)

    def _choose_cost_branch(self, branch_labels: list) -> "int | None":
        """Show a dialog to choose an OR branch. Returns index or None."""
        win = tk.Toplevel(self)
        win.title("Choose Payment")
        win.resizable(False, False)
        win.grab_set()

        ttk.Label(win, text="Choose how to pay for this task:").pack(padx=16, pady=(12, 4))

        result = [None]

        def pick(i):
            result[0] = i
            win.destroy()

        for i, label in enumerate(branch_labels):
            ttk.Button(win, text=label, command=lambda x=i: pick(x)).pack(
                fill="x", padx=16, pady=3
            )

        ttk.Button(win, text="Cancel", command=win.destroy).pack(padx=16, pady=(4, 12))
        self.wait_window(win)
        return result[0]

    def _attempt_make_change(self, task_idx: int):
        """Swap OR branch for a purchased task, refunding old and deducting new."""
        ctx = getattr(self, "ctx", None)
        if not ctx:
            return
        cost_amounts = list(getattr(ctx, "task_cost_amounts", []) or [])
        if task_idx >= len(cost_amounts) or not cost_amounts[task_idx]:
            return
        branches = cost_amounts[task_idx]
        if len(branches) <= 1:
            return

        current_deduction = self._task_purchases.get(task_idx)
        if current_deduction is None:
            return

        # Compute balance assuming current branch is refunded
        base_balance = self._consumable_balance()
        refund_balance = dict(base_balance)
        for name, amt in current_deduction.items():
            refund_balance[name] = refund_balance.get(name, 0) + amt

        current_label = ", ".join(
            f"{amt} {name}" for name, amt in sorted(current_deduction.items())
        )

        def _branch_dict(branch):
            return {name: amt for name, amt in branch}

        def _is_current(branch):
            return _branch_dict(branch) == current_deduction

        def _can_afford(branch):
            for name, amt in branch:
                if refund_balance.get(name, 0) < amt:
                    return False
            return True

        alternatives = [b for b in branches if not _is_current(b) and _can_afford(b)]

        if not alternatives:
            messagebox.showinfo(
                "No Alternatives",
                f"Currently paid: {current_label}\n\n"
                "No alternative payment can be afforded right now.\n"
                "(Other branches require items you don't have yet.)"
            )
            return

        win = tk.Toplevel(self)
        win.title("Make Change")
        win.resizable(False, False)
        win.grab_set()

        ttk.Label(win, text=f"Currently paid: {current_label}").pack(padx=16, pady=(12, 2))
        ttk.Label(win, text="Switch payment to:").pack(padx=16, pady=(0, 6))

        result = [None]

        def pick(branch):
            result[0] = branch
            win.destroy()

        for b in alternatives:
            parts = ", ".join(f"{amt} {name}" for name, amt in b)
            ttk.Button(win, text=parts, command=lambda br=b: pick(br)).pack(
                fill="x", padx=16, pady=3
            )

        ttk.Button(win, text="Cancel", command=win.destroy).pack(padx=16, pady=(4, 12))
        self.wait_window(win)

        if result[0] is not None:
            self._task_purchases[task_idx] = {name: amt for name, amt in result[0]}
            self._schedule_play_refresh()
            self.after(0, self._render_consumable_tab)

    def _recalculate_purchases_from_completed(self):
        """Ensure completed tasks have a recorded purchase deduction.
        Preserves existing entries (user's Make Change choices and in-session purchases)."""
        ctx = getattr(self, "ctx", None)
        if not ctx:
            return
        checked = getattr(ctx, "checked_locations_set", set()) or set()
        base_complete = getattr(ctx, "base_complete_location_id", None)
        cost_amounts = list(getattr(ctx, "task_cost_amounts", []) or [])
        if base_complete is None:
            return
        for i, branches in enumerate(cost_amounts):
            if not branches:
                continue
            if (base_complete + i) not in checked:
                continue
            if i not in self._task_purchases:
                # Assign minimum-cost branch as default for newly-seen completed tasks
                min_branch = min(branches, key=lambda b: sum(amt for _, amt in b))
                self._task_purchases[i] = {name: amt for name, amt in min_branch}

    def _render_consumable_tab(self):
        if not hasattr(self, "consumable_tab_scroll"):
            return
        inner = self.consumable_tab_scroll.inner
        for w in inner.winfo_children():
            w.destroy()

        ctx = getattr(self, "ctx", None)
        cost_amounts = list(getattr(ctx, "task_cost_amounts", []) or []) if ctx else []
        has_any_cost = any(c for c in cost_amounts)
        if not ctx or not has_any_cost:
            ttk.Label(inner, text="No consumable items in this session.", style="Muted.TLabel").pack(
                anchor="w", padx=6, pady=4
            )
            return

        balance = self._consumable_balance()
        received = self._consumable_received_counts()
        spent = self._consumable_spent_counts()
        all_names = sorted(set(received) | set(spent))

        if not all_names:
            ttk.Label(inner, text="No consumable items received yet.", style="Muted.TLabel").pack(
                anchor="w", padx=6, pady=4
            )
            return

        for name in all_names:
            recv = received.get(name, 0)
            sp = spent.get(name, 0)
            bal = balance.get(name, 0)
            color_style = "Warning.TLabel" if bal < 0 else "TLabel"
            ttk.Label(
                inner,
                text=f"{name}:  {bal} remaining  ({recv} received, {sp} spent)",
                style=color_style,
            ).pack(anchor="w", padx=6, pady=2)

    # ---------------- Items received tab ----------------
    def _render_items_tab(self):
        if not hasattr(self, "items_received_scroll"):
            return
        inner = self.items_received_scroll.inner
        for w in inner.winfo_children():
            w.destroy()

        ctx = getattr(self, "ctx", None)
        if not ctx:
            return

        items_received = list(getattr(ctx, "items_received", []) or [])
        base_token = getattr(ctx, "base_token_id", None)
        base_item = getattr(ctx, "base_item_id", None)
        n_tasks = len(getattr(ctx, "tasks", []) or [])
        items_text = list(getattr(ctx, "items", getattr(ctx, "rewards", [])) or [])
        item_consumable = list(getattr(ctx, "item_consumable", []) or [])
        prog_groups = list(getattr(ctx, "progressive_groups", []) or [])
        reward_prog_group = list(getattr(ctx, "reward_progressive_group", []) or [])
        if not reward_prog_group:
            reward_prog_group = list(getattr(ctx, "item_progressive_group", []) or [])

        # --- Group summary section ---
        # Progressive groups
        have = self._received_item_ids()
        prog_rows = []
        for g in prog_groups:
            total = sum(1 for x in reward_prog_group if x == g)
            if isinstance(base_item, int):
                received = sum(1 for i, x in enumerate(reward_prog_group) if x == g and (base_item + i) in have)
            else:
                received = 0
            prog_rows.append((g, received, total))

        # Consumable currencies (in pool order, deduplicated)
        seen_cons: set = set()
        cons_names = []
        for i, name in enumerate(items_text):
            flag = item_consumable[i] if i < len(item_consumable) else False
            if flag and name and name not in seen_cons:
                cons_names.append(name)
                seen_cons.add(name)
        cons_recv = self._consumable_received_counts()

        if prog_rows or cons_names:
            muted = self.colors.get("muted", "#bdbdbd")
            fg = self.colors.get("fg", "#e6e6e6")
            bg = self.colors.get("bg", "#1e1e1e")

            for g, received, total in prog_rows:
                row = tk.Frame(inner, bg=bg)
                row.pack(fill="x", padx=4, pady=1)
                tk.Label(row, text=g, bg=bg, fg=fg, font=("Segoe UI", 10)).pack(side="left")
                tk.Label(row, text=f"{received} / {total}", bg=bg, fg=muted, font=("Segoe UI", 10)).pack(side="right", padx=(0, 6))

            for name in cons_names:
                row = tk.Frame(inner, bg=bg)
                row.pack(fill="x", padx=4, pady=1)
                tk.Label(row, text=f"{name}  (currency)", bg=bg, fg=fg, font=("Segoe UI", 10)).pack(side="left")
                tk.Label(row, text=f"{cons_recv.get(name, 0)} received", bg=bg, fg=muted, font=("Segoe UI", 10)).pack(side="right", padx=(0, 6))

            ttk.Separator(inner, orient="horizontal").pack(fill="x", pady=(4, 2))

        if not items_received:
            ttk.Label(inner, text="No items received yet.", style="Muted.TLabel").pack(anchor="w", padx=6, pady=4)
            return

        for it in items_received:
            item_id = getattr(it, "item", None)
            sender = getattr(it, "player", None)
            if item_id is None:
                continue
            # Skip completion tokens
            if isinstance(base_token, int) and isinstance(item_id, int) and n_tasks:
                if 0 <= (item_id - base_token) < n_tasks:
                    continue

            # Resolve name
            name = None
            try:
                item_names = getattr(ctx, "item_names", None)
                if isinstance(item_names, dict):
                    name = item_names.get(item_id)
                elif hasattr(item_names, "get"):
                    name = item_names.get(item_id)
            except Exception:
                pass
            if isinstance(base_item, int) and isinstance(item_id, int) and items_text:
                idx = item_id - base_item
                if 0 <= idx < len(items_text) and items_text[idx]:
                    name = items_text[idx]
            if not name:
                name = f"Item #{item_id}"

            sender_label = ""
            if sender is not None:
                try:
                    player_names = getattr(ctx, "player_names", None)
                    pname = player_names.get(sender) if isinstance(player_names, dict) else None
                    if pname:
                        sender_label = f"  (from {pname})"
                except Exception:
                    pass

            ttk.Label(inner, text=f"{name}{sender_label}").pack(anchor="w", padx=6, pady=1)

    # ---------------- Bingo generator tab ----------------
    def _build_bingo_tab(self):
        tab = self.bingo_tab
        tab.grid_columnconfigure(0, weight=1)
        tab.grid_rowconfigure(1, weight=1)
        tab.grid_rowconfigure(2, weight=0)
        tab.grid_rowconfigure(3, weight=0)

        meta = ttk.LabelFrame(tab, text="Bingo Settings")
        meta.grid(row=0, column=0, sticky="ew", padx=10, pady=(10, 6))
        meta.grid_columnconfigure(1, weight=1)

        ttk.Label(meta, text="Player Name:").grid(row=0, column=0, padx=10, pady=8, sticky="w")
        self.bingo_player_var = tk.StringVar()
        ttk.Entry(meta, textvariable=self.bingo_player_var).grid(
            row=0, column=1, sticky="ew", padx=(0, 10), pady=8
        )

        settings_row = ttk.Frame(meta)
        settings_row.grid(row=1, column=0, columnspan=2, sticky="w", padx=10, pady=(0, 8))

        ttk.Label(settings_row, text="Columns (X):").grid(row=0, column=0, sticky="w")
        self.bingo_x_var = tk.IntVar(value=5)
        ttk.Spinbox(settings_row, from_=1, to=20, textvariable=self.bingo_x_var, width=4).grid(
            row=0, column=1, padx=(4, 16), sticky="w"
        )
        self.bingo_x_var.trace_add("write", lambda *_: self._update_bingo_counts())

        ttk.Label(settings_row, text="Rows (Y):").grid(row=0, column=2, sticky="w")
        self.bingo_y_var = tk.IntVar(value=5)
        ttk.Spinbox(settings_row, from_=1, to=20, textvariable=self.bingo_y_var, width=4).grid(
            row=0, column=3, padx=(4, 16), sticky="w"
        )
        self.bingo_y_var.trace_add("write", lambda *_: self._update_bingo_counts())

        ttk.Label(settings_row, text="Bingos to goal:").grid(row=0, column=4, sticky="w")
        self.bingo_goal_var = tk.IntVar(value=3)
        ttk.Spinbox(settings_row, from_=1, to=100, textvariable=self.bingo_goal_var, width=4).grid(
            row=0, column=5, padx=(4, 16), sticky="w"
        )

        ttk.Label(settings_row, text="Prog. Balancing:").grid(row=0, column=6, sticky="w")
        self.bingo_prog_var = tk.IntVar(value=50)
        ttk.Spinbox(settings_row, from_=0, to=99, textvariable=self.bingo_prog_var, width=5).grid(
            row=0, column=7, padx=(4, 16), sticky="w"
        )

        ttk.Label(settings_row, text="Accessibility:").grid(row=0, column=8, sticky="w")
        self.bingo_access_var = tk.StringVar(value="full")
        ttk.Combobox(
            settings_row, textvariable=self.bingo_access_var,
            values=["full", "items", "minimal"], state="readonly", width=10,
        ).grid(row=0, column=9, padx=(4, 0))

        field_bg = "#2d2d30"
        text_fg = self.colors.get("fg", "#e6e6e6")

        # Spaces and rewards side by side
        content_frame = ttk.Frame(tab)
        content_frame.grid(row=1, column=0, sticky="nsew", padx=10, pady=(0, 6))
        content_frame.grid_columnconfigure(0, weight=1)
        content_frame.grid_columnconfigure(1, weight=1)
        content_frame.grid_rowconfigure(0, weight=1)

        spaces_frame = ttk.LabelFrame(content_frame, text="Spaces (one per line)")
        spaces_frame.grid(row=0, column=0, sticky="nsew", padx=(0, 3))
        spaces_frame.grid_rowconfigure(1, weight=1)
        spaces_frame.grid_columnconfigure(0, weight=1)

        self._bingo_count_label = ttk.Label(
            spaces_frame,
            text="Enter one space per line (need X*Y, have 0)",
            style="Muted.TLabel",
        )
        self._bingo_count_label.grid(row=0, column=0, sticky="w", padx=10, pady=(6, 2))

        self.bingo_spaces_text = tk.Text(
            spaces_frame,
            bg=field_bg, fg=text_fg, insertbackground=text_fg,
            font=("Segoe UI", 10), relief="flat", padx=6, pady=6,
            undo=True, wrap="word",
        )
        self.bingo_spaces_text.grid(row=1, column=0, sticky="nsew", padx=10, pady=(0, 6))
        self.bingo_spaces_text.bind("<KeyRelease>", lambda _: self._update_bingo_counts())

        rewards_frame = ttk.LabelFrame(content_frame, text="Rewards (one per line, optional)")
        rewards_frame.grid(row=0, column=1, sticky="nsew", padx=(3, 0))
        rewards_frame.grid_rowconfigure(1, weight=1)
        rewards_frame.grid_columnconfigure(0, weight=1)

        self._bingo_rewards_count_label = ttk.Label(
            rewards_frame,
            text="Optional: replace filler reward slots (free space + bingo line tasks)",
            style="Muted.TLabel",
        )
        self._bingo_rewards_count_label.grid(row=0, column=0, sticky="w", padx=10, pady=(6, 2))

        self.bingo_rewards_text = tk.Text(
            rewards_frame,
            bg=field_bg, fg=text_fg, insertbackground=text_fg,
            font=("Segoe UI", 10), relief="flat", padx=6, pady=6,
            undo=True, wrap="word",
        )
        self.bingo_rewards_text.grid(row=1, column=0, sticky="nsew", padx=10, pady=(0, 6))
        self.bingo_rewards_text.bind("<KeyRelease>", lambda _: self._update_bingo_counts())

        # DeathLink section
        dl_frame = ttk.LabelFrame(tab, text="DeathLink")
        dl_frame.grid(row=2, column=0, sticky="ew", padx=10, pady=(0, 6))
        dl_frame.grid_columnconfigure(1, weight=1)

        dl_top = ttk.Frame(dl_frame)
        dl_top.grid(row=0, column=0, columnspan=2, sticky="w", padx=10, pady=(6, 4))

        self.bingo_deathlink_var = tk.BooleanVar(value=False)
        ttk.Checkbutton(dl_top, text="Enable DeathLink", variable=self.bingo_deathlink_var).pack(
            side="left"
        )
        ttk.Label(dl_top, text="Amnesty:").pack(side="left", padx=(20, 4))
        self.bingo_deathlink_amnesty_var = tk.IntVar(value=0)
        ttk.Spinbox(dl_top, from_=0, to=999, textvariable=self.bingo_deathlink_amnesty_var, width=5).pack(
            side="left"
        )

        ttk.Label(dl_frame, text="Pool (one per line):").grid(
            row=1, column=0, sticky="nw", padx=10, pady=(0, 6)
        )
        self.bingo_deathlink_text = tk.Text(
            dl_frame,
            bg=field_bg, fg=text_fg, insertbackground=text_fg,
            font=("Segoe UI", 10), relief="flat", padx=6, pady=4,
            undo=True, wrap="word", height=3,
        )
        self.bingo_deathlink_text.grid(row=1, column=1, sticky="ew", padx=(0, 10), pady=(0, 6))

        btn_frame = ttk.Frame(tab)
        btn_frame.grid(row=3, column=0, sticky="ew", padx=10, pady=(0, 10))
        btn_frame.grid_columnconfigure(0, weight=1)

        ttk.Button(btn_frame, text="Clear", command=self._clear_bingo_tab).grid(
            row=0, column=1, sticky="e", padx=(0, 6)
        )
        ttk.Button(btn_frame, text="Save Settings", command=self._save_bingo_settings).grid(
            row=0, column=2, sticky="e", padx=(0, 6)
        )
        ttk.Button(btn_frame, text="Load", command=self._load_bingo).grid(
            row=0, column=3, sticky="e", padx=(0, 6)
        )
        ttk.Button(btn_frame, text="Export Bingo YAML", command=self._export_bingo_yaml).grid(
            row=0, column=4, sticky="e"
        )

        self._update_bingo_counts()

    def _update_bingo_counts(self, _=None):
        X = self._safe_int(self.bingo_x_var, 5)
        Y = self._safe_int(self.bingo_y_var, 5)
        needed = X * Y
        spaces = self._get_bingo_spaces()
        have = len(spaces)
        if have >= needed:
            suffix = " (enough)" if have == needed else f" ({have - needed} extra)"
        else:
            suffix = f" (need {needed - have} more)"
        self._bingo_count_label.config(
            text=f"Enter one space per line (need {needed}, have {have}{suffix})"
        )

        n_filler = 1 + len(_bingo_lines(X, Y))  # free space + line tasks
        rewards = self._get_bingo_rewards()
        have_rw = len(rewards)
        if have_rw == 0:
            rw_suffix = f"all {n_filler} slots will be filler"
        elif have_rw >= n_filler:
            rw_suffix = f"all {n_filler} slots covered"
        else:
            rw_suffix = f"{have_rw} replaced, {n_filler - have_rw} remain filler"
        self._bingo_rewards_count_label.config(
            text=f"Reward slots available: {n_filler} - {rw_suffix}"
        )

    def _get_bingo_spaces(self) -> list:
        text = self.bingo_spaces_text.get("1.0", "end-1c")
        return [line.strip() for line in text.splitlines() if line.strip()]

    def _get_bingo_rewards(self) -> list:
        text = self.bingo_rewards_text.get("1.0", "end-1c")
        return [line.strip() for line in text.splitlines() if line.strip()]

    def _safe_int(self, var, default: int) -> int:
        try:
            return int(var.get())
        except Exception:
            return default

    def _export_bingo_yaml(self):
        player_name = self.bingo_player_var.get().strip()
        if not player_name:
            messagebox.showerror("Error", "Player name is required.")
            return

        X = self._safe_int(self.bingo_x_var, 5)
        Y = self._safe_int(self.bingo_y_var, 5)
        bingoal = self._safe_int(self.bingo_goal_var, 3)
        n_spaces = X * Y

        spaces_pool = self._get_bingo_spaces()
        if len(spaces_pool) < n_spaces:
            messagebox.showerror(
                "Error",
                f"Need at least {n_spaces} spaces for a {X}x{Y} board, "
                f"but only {len(spaces_pool)} entered.",
            )
            return

        selected = random.sample(spaces_pool, n_spaces)

        tasks, rewards, task_prereqs, reward_prereqs, reward_types = [], [], [], [], []
        middle = n_spaces // 2

        for i in range(n_spaces):
            r, c = divmod(i, X)
            tasks.append(selected[i])
            rewards.append(f"Bingo {r + 1},{c + 1} Unlock")
            task_prereqs.append("")
            reward_prereqs.append("" if i == middle else str(i + 1))
            reward_types.append("progression")

        lines = _bingo_lines(X, Y)
        L = len(lines)
        n_rows, n_cols = Y, X
        d = min(X, Y)
        n_main_diags = (Y - d + 1) * (X - d + 1)
        n_anti_diags = n_main_diags

        for li, line in enumerate(lines):
            if li < n_rows:
                name = f"Row {li + 1} Bingo"
            elif li < n_rows + n_cols:
                name = f"Column {li - n_rows + 1} Bingo"
            elif li < n_rows + n_cols + n_main_diags:
                idx = li - n_rows - n_cols
                name = "Diagonal Bingo (↘)" if n_main_diags == 1 else f"Diagonal Bingo (↘ #{idx + 1})"
            else:
                idx = li - n_rows - n_cols - n_main_diags
                name = "Diagonal Bingo (↙)" if n_anti_diags == 1 else f"Diagonal Bingo (↙ #{idx + 1})"
            tasks.append(name)
            rewards.append(_random_filler())
            task_prereqs.append(", ".join(str(s + 1) for s in line))
            reward_prereqs.append("")
            reward_types.append("junk")

        if self.bingo_deathlink_var.get():
            dl_pool = [
                l.strip() for l in self.bingo_deathlink_text.get("1.0", "end-1c").splitlines()
                if l.strip()
            ]
            if not dl_pool:
                messagebox.showerror(
                    "Error",
                    "DeathLink is enabled but the pool is empty.\n"
                    "Add at least one entry or disable DeathLink."
                )
                return

        # Assign user-provided rewards to filler slots (free space + line tasks)
        reward_pool = self._get_bingo_rewards()
        random.shuffle(reward_pool)
        reward_iter = iter(reward_pool)

        user_rw = next(reward_iter, None)
        if user_rw:
            rewards[middle] = user_rw
            reward_types[middle] = "useful"

        for li in range(L):
            user_rw = next(reward_iter, None)
            if user_rw:
                rewards[n_spaces + li] = user_rw
                reward_types[n_spaces + li] = "useful"

        bingoal = max(1, min(bingoal, L))
        goal_expr = _gen_bingoal_expr(n_spaces, L, bingoal)

        data = {
            "name": player_name,
            "game": "Taskipelago",
            "description": "Taskipelabingo YAML",
            "Taskipelago": {
                "progression_balancing": self._safe_int(self.bingo_prog_var, 50),
                "accessibility": self.bingo_access_var.get(),
                "death_link": {"true": 50, "false": 0} if self.bingo_deathlink_var.get() else {"true": 0, "false": 50},
                "progressive_groups": [],
                "item_progressive_group": [""] * len(tasks),
                "tasks": tasks,
                "items": rewards,
                "item_types": reward_types,
                "item_fillers": [False] * len(tasks),
                "task_prereqs": task_prereqs,
                "item_prereqs": reward_prereqs,
                "lock_prereqs": True,
                "hide_unreachable_tasks": True,
                "goal_tasks": [goal_expr] if goal_expr else [],
                "death_link_pool": [
                    l.strip() for l in self.bingo_deathlink_text.get("1.0", "end-1c").splitlines()
                    if l.strip()
                ],
                "death_link_weights": [],
                "death_link_amnesty": self._safe_int(self.bingo_deathlink_amnesty_var, 0),
                "bingo_mode": True,
                "bingo_dimension_x": X,
                "bingo_dimension_y": Y,
                "bingoal": bingoal,
            },
        }

        path = filedialog.asksaveasfilename(
            defaultextension=".yaml", filetypes=[("YAML Files", "*.yaml")]
        )
        if not path:
            return

        with open(path, "w", encoding="utf-8") as f:
            yaml.dump(data, f, sort_keys=False, allow_unicode=True)

        messagebox.showinfo("Success", f"Bingo YAML exported to:\n{path}")

    def _clear_bingo_tab(self):
        self.bingo_player_var.set("")
        self.bingo_x_var.set(5)
        self.bingo_y_var.set(5)
        self.bingo_goal_var.set(3)
        self.bingo_prog_var.set(50)
        self.bingo_access_var.set("full")
        self.bingo_deathlink_var.set(False)
        self.bingo_deathlink_amnesty_var.set(0)
        self.bingo_spaces_text.delete("1.0", "end")
        self.bingo_rewards_text.delete("1.0", "end")
        self.bingo_deathlink_text.delete("1.0", "end")
        self._update_bingo_counts()

    def _save_bingo_settings(self):
        path = filedialog.asksaveasfilename(
            defaultextension=".bingo",
            filetypes=[("Bingo Settings", "*.bingo"), ("All Files", "*.*")],
        )
        if not path:
            return
        data = {
            "spaces": self._get_bingo_spaces(),
            "rewards": self._get_bingo_rewards(),
            "player_name": self.bingo_player_var.get().strip(),
            "bingo_x": self._safe_int(self.bingo_x_var, 5),
            "bingo_y": self._safe_int(self.bingo_y_var, 5),
            "bingoal": self._safe_int(self.bingo_goal_var, 3),
            "progression_balancing": self._safe_int(self.bingo_prog_var, 50),
            "accessibility": self.bingo_access_var.get(),
            "death_link_enabled": bool(self.bingo_deathlink_var.get()),
            "death_link_amnesty": self._safe_int(self.bingo_deathlink_amnesty_var, 0),
            "death_link_pool": [
                l.strip()
                for l in self.bingo_deathlink_text.get("1.0", "end-1c").splitlines()
                if l.strip()
            ],
        }
        try:
            with open(path, "w", encoding="utf-8") as f:
                yaml.dump(data, f, allow_unicode=True, default_flow_style=False, sort_keys=False)
            messagebox.showinfo("Saved", f"Bingo settings saved to:\n{path}")
        except Exception as e:
            messagebox.showerror("Error", f"Failed to save:\n{e}")

    def _load_bingo(self):
        """Load either a .bingo settings file or an AP bingo YAML."""
        path = filedialog.askopenfilename(
            filetypes=[
                ("Bingo Files", "*.bingo *.yaml *.yml"),
                ("Bingo Settings", "*.bingo"),
                ("YAML Files", "*.yaml *.yml"),
                ("All Files", "*.*"),
            ]
        )
        if not path:
            return
        try:
            with open(path, "r", encoding="utf-8") as f:
                doc = yaml.safe_load(f)
        except Exception as e:
            messagebox.showerror("Error", f"Failed to read file:\n{e}")
            return

        if isinstance(doc, dict) and "spaces" in doc:
            self._load_bingo_settings_doc(doc, path)
        else:
            self._load_bingo_yaml_doc(doc, path)


    def _load_bingo_settings_doc(self, doc: dict, path: str):
        """Populate bingo tab from a .bingo settings file."""
        name = doc.get("player_name", "")
        if isinstance(name, str) and name.strip():
            self.bingo_player_var.set(name.strip())

        try:
            self.bingo_x_var.set(int(doc.get("bingo_x", 5) or 5))
            self.bingo_y_var.set(int(doc.get("bingo_y", 5) or 5))
            self.bingo_goal_var.set(int(doc.get("bingoal", 3) or 3))
            self.bingo_prog_var.set(int(doc.get("progression_balancing", 50) or 50))
        except Exception:
            pass

        acc = doc.get("accessibility", "full")
        if isinstance(acc, str) and acc.strip():
            self.bingo_access_var.set(acc.strip())

        dl_enabled = doc.get("death_link_enabled", False)
        self.bingo_deathlink_var.set(bool(dl_enabled))
        try:
            self.bingo_deathlink_amnesty_var.set(int(doc.get("death_link_amnesty", 0) or 0))
        except Exception:
            pass

        self.bingo_deathlink_text.delete("1.0", "end")
        for entry in list(doc.get("death_link_pool", []) or []):
            s = str(entry).strip()
            if s:
                self.bingo_deathlink_text.insert("end", s + "\n")

        self.bingo_spaces_text.delete("1.0", "end")
        for s in list(doc.get("spaces", []) or []):
            entry = str(s).strip()
            if entry:
                self.bingo_spaces_text.insert("end", entry + "\n")

        self.bingo_rewards_text.delete("1.0", "end")
        for r in list(doc.get("rewards", []) or []):
            entry = str(r).strip()
            if entry:
                self.bingo_rewards_text.insert("end", entry + "\n")

        self._update_bingo_counts()
        messagebox.showinfo("Loaded", f"Bingo settings loaded from:\n{path}")

    def _import_bingo_yaml(self):
        path = filedialog.askopenfilename(
            filetypes=[("YAML Files", "*.yaml *.yml"), ("All Files", "*.*")]
        )
        if not path:
            return
        try:
            with open(path, "r", encoding="utf-8") as f:
                doc = yaml.safe_load(f)
        except Exception as e:
            messagebox.showerror("Error", f"Failed to read YAML:\n{e}")
            return
        self._load_bingo_yaml_doc(doc, path)

    def _load_bingo_yaml_doc(self, doc, path: str):
        player_name, block = self._extract_taskipelago_block(doc)
        if not isinstance(block, dict):
            messagebox.showerror("Error", "Could not find a Taskipelago section in this YAML.")
            return
        if not block.get("bingo_mode"):
            messagebox.showerror("Error", "This YAML does not have bingo_mode enabled.")
            return

        if player_name:
            self.bingo_player_var.set(player_name)

        X = int(block.get("bingo_dimension_x", 5) or 5)
        Y = int(block.get("bingo_dimension_y", 5) or 5)
        try:
            self.bingo_x_var.set(X)
            self.bingo_y_var.set(Y)
            self.bingo_goal_var.set(int(block.get("bingoal", 3) or 3))
            self.bingo_prog_var.set(int(block.get("progression_balancing", 50) or 50))
        except Exception:
            pass

        acc = block.get("accessibility", "full")
        if isinstance(acc, str) and acc.strip():
            self.bingo_access_var.set(acc.strip())

        dl = block.get("death_link")
        if isinstance(dl, dict):
            try:
                t = int(dl.get("true", 0) or 0)
                f = int(dl.get("false", 0) or 0)
                self.bingo_deathlink_var.set((t > 0) and (t >= f))
            except Exception:
                pass
        elif isinstance(dl, (bool, int)):
            self.bingo_deathlink_var.set(bool(dl))

        try:
            self.bingo_deathlink_amnesty_var.set(int(block.get("death_link_amnesty", 0) or 0))
        except Exception:
            pass

        self.bingo_deathlink_text.delete("1.0", "end")
        for entry in list(block.get("death_link_pool", []) or []):
            s = str(entry).strip()
            if s:
                self.bingo_deathlink_text.insert("end", s + "\n")

        n_spaces = X * Y
        tasks = list(block.get("tasks", []) or [])
        self.bingo_spaces_text.delete("1.0", "end")
        for t in tasks[:n_spaces]:
            s = str(t).strip()
            if s:
                self.bingo_spaces_text.insert("end", s + "\n")

        rewards = list(block.get("items", block.get("rewards", [])) or [])
        middle = n_spaces // 2
        n_lines = len(_bingo_lines(X, Y))
        filler_rewards = []
        if middle < len(rewards):
            rw = str(rewards[middle]).strip()
            if rw and not _is_filler(rw) and not rw.startswith("Bingo "):
                filler_rewards.append(rw)
        for li in range(n_lines):
            idx = n_spaces + li
            if idx < len(rewards):
                rw = str(rewards[idx]).strip()
                if rw and not _is_filler(rw):
                    filler_rewards.append(rw)

        self.bingo_rewards_text.delete("1.0", "end")
        for rw in filler_rewards:
            self.bingo_rewards_text.insert("end", rw + "\n")

        self._update_bingo_counts()
        messagebox.showinfo("Imported", f"Imported Bingo YAML from:\n{path}")

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
        # Also try new key name
        if not reward_prog_group:
            reward_prog_group = list(getattr(self.ctx, "item_progressive_group", []) or [])
        base = getattr(self.ctx, "base_item_id", None)
        if not isinstance(base, int):
            return True  # can't evaluate without base id - optimistic
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

    def _region_req_satisfied(self, rname: str, pct: int) -> bool:
        import math
        checked = set(getattr(self.ctx, "checked_locations_set", set()) or set())
        task_region = list(getattr(self.ctx, "task_region", []) or [])
        base_complete = getattr(self.ctx, "base_complete_location_id", None)
        if base_complete is None:
            return True
        region_indices = [i for i, r in enumerate(task_region) if r == rname]
        if not region_indices:
            return True
        required = math.ceil(len(region_indices) * pct / 100)
        completed = sum(1 for i in region_indices if (base_complete + i) in checked)
        return completed >= required

    def _region_req_satisfied_abs(self, rname: str, required_count: int) -> bool:
        checked = set(getattr(self.ctx, "checked_locations_set", set()) or set())
        task_region = list(getattr(self.ctx, "task_region", []) or [])
        base_complete = getattr(self.ctx, "base_complete_location_id", None)
        if base_complete is None:
            return True
        region_indices = [i for i, r in enumerate(task_region) if r == rname]
        completed = sum(1 for i in region_indices if (base_complete + i) in checked)
        return completed >= required_count

    def _reward_prereq_display(self, prereq_text: str) -> str:
        items = list(getattr(self.ctx, "items", getattr(self.ctx, "rewards", [])) or [])
        parts = [p.strip() for p in prereq_text.split(",") if p.strip()]
        names = []

        for p in parts:
            try:
                idx_1based = int(p)
            except ValueError:
                continue
            idx0 = idx_1based - 1
            if 0 <= idx0 < len(items) and str(items[idx0]).strip():
                names.append(str(items[idx0]).strip())
            else:
                names.append(f"Item #{idx_1based}")

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

        # 2) Taskipelago item range -> YAML item text
        try:
            base_reward_item = getattr(ctx, "base_item_id", None)
            items_text = list(getattr(ctx, "items", getattr(ctx, "rewards", [])) or [])
            if isinstance(base_reward_item, int) and isinstance(item_id, int) and items_text:
                idx = item_id - base_reward_item
                if 0 <= idx < len(items_text):
                    resolved = items_text[idx]
        except Exception:
            pass

        # 3) fallback: YAML item text by task index (even if item_id unknown)
        if (not resolved) and task_index is not None:
            try:
                items_text = list(getattr(ctx, "items", getattr(ctx, "rewards", [])) or [])
                if 0 <= task_index < len(items_text):
                    resolved = items_text[task_index]
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
        
        # UI optimism on complete location - cancel any pending debounced refresh first
        self.pending_reward_locations.add(complete_loc_id)
        if self._refresh_after_id is not None:
            self.after_cancel(self._refresh_after_id)
            self._refresh_after_id = None
        self.refresh_play_tab()

        try:
            # Dedupe so doule-clicks or rapid refreshes don't spam
            now = time.time()
            sent_key = ("sent", reward_loc_id)
            if sent_key != self._last_sent_key or (now - self._last_sent_seen_at) > 1.0:
                reward_name, recipient_name = self._get_sent_notification_info(task_index)

                # Skip filler and skip unknown/empty authoritative item names
                if reward_name and reward_name.strip() and not _is_filler(reward_name.strip()):
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
        self.send_deathlink_btn.pack_forget()
        self.sent_goal = False
        self._clear_notifications()
        self._clear_play_state()
        self._update_console_connection_state(False)

    # ---------------- DeathLink ----------------
    def _send_deathlink(self):
        ctx = getattr(self, "ctx", None)
        if not ctx or self.connection_state != "connected":
            return

        async def _do_send():
            await ctx.send_msgs([{
                "cmd": "Bounce",
                "tags": ["DeathLink"],
                "data": {
                    "time": time.time(),
                    "source": ctx.auth or "Taskipelago",
                },
            }])

        self.loop.call_soon_threadsafe(lambda: asyncio.create_task(_do_send()))

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

            # 2b) If this is one of our Taskipelago items, show YAML item text instead
            base_reward_item = getattr(self.ctx, "base_item_id", None)
            items_text = list(getattr(self.ctx, "items", getattr(self.ctx, "rewards", [])) or [])
            if isinstance(base_reward_item, int) and isinstance(item_id, int) and items_text:
                idx = item_id - base_reward_item
                if 0 <= idx < len(items_text):
                    resolved_name = items_text[idx]

            # ---- 3) If we STILL don't have a name, do NOT popup ----
            if not resolved_name or not str(resolved_name).strip():
                continue

            resolved_name = str(resolved_name).strip()

            # If it's a filler string, don't popup
            if _is_filler(resolved_name):
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
