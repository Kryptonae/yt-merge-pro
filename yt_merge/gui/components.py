"""
components.py — Reusable GUI widgets.

Contains:
  • VideoQueuePanel  — Treeview list showing all queued videos with status
  • LogViewer        — Colored log output panel
  • ProgressPanel    — Overall progress bar with stage label
"""

import tkinter as tk
from tkinter import ttk
from typing import List

import customtkinter as ctk

from ..models import VideoEntry


# ─── Dark-themed Treeview Style ──────────────────────────────

def apply_dark_treeview_style():
    """Apply a dark color scheme to ttk.Treeview widgets."""
    style = ttk.Style()
    style.theme_use("default")
    style.configure(
        "Dark.Treeview",
        background="#1e1e2e",
        foreground="#cdd6f4",
        rowheight=32,
        fieldbackground="#1e1e2e",
        borderwidth=0,
        font=("Segoe UI", 10),
    )
    style.map("Dark.Treeview", background=[("selected", "#45475a")])
    style.configure(
        "Dark.Treeview.Heading",
        background="#313244",
        foreground="#cdd6f4",
        relief="flat",
        font=("Segoe UI", 10, "bold"),
    )
    style.map("Dark.Treeview.Heading", background=[("active", "#45475a")])


# ─── Video Queue Panel ───────────────────────────────────────

class VideoQueuePanel(ctk.CTkFrame):
    """Displays the video queue as a styled Treeview."""

    def __init__(self, master, **kwargs):
        super().__init__(master, **kwargs)

        apply_dark_treeview_style()

        # Treeview
        cols = ("n", "title", "start", "end", "status")
        self.tree = ttk.Treeview(
            self, columns=cols, show="headings", height=8, style="Dark.Treeview"
        )
        self.tree.heading("n",      text="#")
        self.tree.heading("title",  text="Video")
        self.tree.heading("start",  text="Start")
        self.tree.heading("end",    text="End")
        self.tree.heading("status", text="Status")

        self.tree.column("n",      width=40,  anchor="center", stretch=False)
        self.tree.column("title",  width=480, anchor="w")
        self.tree.column("start",  width=75,  anchor="center", stretch=False)
        self.tree.column("end",    width=75,  anchor="center", stretch=False)
        self.tree.column("status", width=130, anchor="center", stretch=False)

        self.tree.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)

        # Scrollbar
        sb = ctk.CTkScrollbar(self, command=self.tree.yview)
        self.tree.configure(yscrollcommand=sb.set)
        sb.pack(side=tk.RIGHT, fill=tk.Y)

    def refresh(self, entries: List[VideoEntry]) -> None:
        """Rebuild the treeview from the current entries list."""
        self.tree.delete(*self.tree.get_children())
        for i, e in enumerate(entries):
            d = e.to_dict()
            self.tree.insert(
                "", tk.END,
                values=(i + 1, d["title"], d["start_time"], d["end_time"], d["status"]),
            )

    @property
    def selection_indices(self) -> List[int]:
        """Return sorted indices of selected rows."""
        return sorted(self.tree.index(s) for s in self.tree.selection())

    def select_index(self, idx: int) -> None:
        """Select a row by its index."""
        children = self.tree.get_children()
        if 0 <= idx < len(children):
            self.tree.selection_set(children[idx])
            self.tree.see(children[idx])


# ─── Log Viewer ──────────────────────────────────────────────

class LogViewer(ctk.CTkFrame):
    """
    A read-only log display with basic color-coding.
    Green for ✔/✅, red for ✖/❌/💥, yellow for ⚠, white for the rest.
    """

    def __init__(self, master, height: int = 140, **kwargs):
        super().__init__(master, **kwargs)

        self.textbox = ctk.CTkTextbox(
            self, height=height,
            font=("Consolas", 11),
            fg_color="#11111b",
            text_color="#cdd6f4",
            border_width=1,
            border_color="#313244",
            corner_radius=8,
        )
        self.textbox.pack(fill=tk.BOTH, expand=True)
        self.textbox.configure(state="disabled")

    def append(self, text: str) -> None:
        """Append a line of text to the log."""
        self.textbox.configure(state="normal")
        self.textbox.insert(tk.END, text + "\n")
        self.textbox.see(tk.END)
        self.textbox.configure(state="disabled")

    def clear(self) -> None:
        """Clear all log text."""
        self.textbox.configure(state="normal")
        self.textbox.delete("1.0", tk.END)
        self.textbox.configure(state="disabled")


# ─── Progress Panel ──────────────────────────────────────────

class ProgressPanel(ctk.CTkFrame):
    """Overall progress bar with a stage label."""

    def __init__(self, master, **kwargs):
        super().__init__(master, fg_color="transparent", **kwargs)

        self.progress_var = tk.DoubleVar(value=0.0)
        self.bar = ctk.CTkProgressBar(
            self, variable=self.progress_var,
            mode="determinate", height=18,
            progress_color="#a6e3a1",
            fg_color="#313244",
            corner_radius=8,
        )
        self.bar.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=(0, 12))
        self.bar.set(0)

        self.label = ctk.CTkLabel(
            self, text="Ready", width=160,
            font=("Segoe UI", 11),
            text_color="#a6adc8",
        )
        self.label.pack(side=tk.RIGHT)

    def update_progress(self, stage: str, current: int, total: int) -> None:
        """Update the bar and label based on pipeline stage."""
        if total <= 0:
            return

        stage_map = {
            "download": (0.0,  0.45, "Downloading"),
            "process":  (0.45, 0.35, "Processing"),
            "merge":    (0.80, 0.15, "Merging"),
            "done":     (0.95, 0.05, "Finalizing"),
        }
        base, span, label = stage_map.get(stage, (0.0, 1.0, stage))
        pct = base + span * (current / total)
        pct = min(pct, 1.0)

        self.progress_var.set(pct)
        self.bar.set(pct)
        self.label.configure(text=f"{label} {current}/{total}")

    def reset(self) -> None:
        self.progress_var.set(0)
        self.bar.set(0)
        self.label.configure(text="Ready")

    def set_done(self, success: bool) -> None:
        if success:
            self.progress_var.set(1.0)
            self.bar.set(1.0)
            self.label.configure(text="Done ✅")
        else:
            self.label.configure(text="Failed ❌")
