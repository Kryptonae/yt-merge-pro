"""
app.py — Main application window for YT Merge Pro.

Coordinates all GUI panels and drives the MergeEngine on a background thread.
All engine callbacks are relayed to the main thread via `self.after()`.
"""

import logging
import threading
import tkinter as tk
from tkinter import filedialog, messagebox
from typing import List, Optional

import customtkinter as ctk

from ..config import AppSettings, detect_encoder
from ..engine import MergeEngine
from ..models import VideoEntry, VideoStatus
from ..utils import parse_url_line
from .components import LogViewer, ProgressPanel, VideoQueuePanel
from .playlist_dialog import PlaylistDialog
from .settings_panel import SettingsPanel

logger = logging.getLogger(__name__)

# ─── Theme ───────────────────────────────────────────────────
ctk.set_appearance_mode("Dark")
ctk.set_default_color_theme("blue")


class App(ctk.CTk):
    """Main application window."""

    TITLE = "YT Merge Pro"
    MIN_W, MIN_H = 960, 720

    def __init__(self):
        super().__init__()
        self.title(self.TITLE)
        self.geometry("1120x820")
        self.minsize(self.MIN_W, self.MIN_H)
        self.configure(fg_color="#1e1e2e")

        # State
        self.settings = AppSettings()
        self.encoder = detect_encoder()
        self.entries: List[VideoEntry] = []
        self.engine: Optional[MergeEngine] = None
        self.is_running = False
        self._poll_id = None

        self._build_ui()

    # ═════════════════════════════════════════════════════════
    #  UI Construction
    # ═════════════════════════════════════════════════════════

    def _build_ui(self):
        # ── Header ───────────────────────────────────────────
        header_frame = ctk.CTkFrame(self, fg_color="#181825", corner_radius=0, height=56)
        header_frame.pack(fill=tk.X)
        header_frame.pack_propagate(False)

        ctk.CTkLabel(
            header_frame, text="🎬  YT Merge Pro",
            font=("Segoe UI", 22, "bold"), text_color="#cdd6f4",
        ).pack(side=tk.LEFT, padx=20)

        ctk.CTkLabel(
            header_frame, text=f"⚡ {self.encoder.label}",
            font=("Segoe UI", 12),
            text_color="#a6e3a1" if self.encoder.is_gpu else "#f9e2af",
        ).pack(side=tk.RIGHT, padx=20)

        # ── Main scrollable area ─────────────────────────────
        body = ctk.CTkFrame(self, fg_color="transparent")
        body.pack(fill=tk.BOTH, expand=True, padx=16, pady=8)

        # — Input row —
        inp = ctk.CTkFrame(body, fg_color="#181825", corner_radius=12)
        inp.pack(fill=tk.X, pady=(0, 8))

        row1 = ctk.CTkFrame(inp, fg_color="transparent")
        row1.pack(fill=tk.X, padx=12, pady=(10, 4))

        ctk.CTkLabel(row1, text="URL", font=("Segoe UI", 12, "bold"),
                      text_color="#cdd6f4").pack(side=tk.LEFT, padx=(0, 6))

        self.url_entry = ctk.CTkEntry(
            row1, placeholder_text="Paste a YouTube video URL …", height=36,
        )
        self.url_entry.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=4)
        self.url_entry.bind("<Return>", lambda _: self._add_url())

        ctk.CTkLabel(row1, text="Start", text_color="#a6adc8").pack(side=tk.LEFT, padx=(8, 2))
        self.ts_start = ctk.CTkEntry(row1, width=72, height=36, placeholder_text="0:00")
        self.ts_start.pack(side=tk.LEFT, padx=2)

        ctk.CTkLabel(row1, text="End", text_color="#a6adc8").pack(side=tk.LEFT, padx=(8, 2))
        self.ts_end = ctk.CTkEntry(row1, width=72, height=36, placeholder_text="0:00")
        self.ts_end.pack(side=tk.LEFT, padx=2)

        ctk.CTkButton(
            row1, text="➕  Add", width=90, height=36,
            fg_color="#a6e3a1", hover_color="#94e2d5",
            text_color="#1e1e2e", font=("Segoe UI", 12, "bold"),
            command=self._add_url,
        ).pack(side=tk.LEFT, padx=(8, 0))

        # — Toolbar row —
        row2 = ctk.CTkFrame(inp, fg_color="transparent")
        row2.pack(fill=tk.X, padx=12, pady=(0, 10))

        toolbar_btns = [
            ("📋  Playlist", "#cba6f7", "#b4befe", self._open_playlist),
            ("📂  Load .txt", "#89b4fa", "#74c7ec", self._load_txt),
            ("⬆", "#45475a", "#585b70", self._move_up),
            ("⬇", "#45475a", "#585b70", self._move_down),
            ("🗑  Remove", "#f38ba8", "#eba0ac", self._remove_selected),
            ("🗑  Clear All", "#45475a", "#585b70", self._clear_all),
        ]
        for text, fg, hover, cmd in toolbar_btns:
            ctk.CTkButton(
                row2, text=text, width=90 if len(text) > 3 else 50,
                height=32, fg_color=fg, hover_color=hover,
                text_color="#1e1e2e", font=("Segoe UI", 11),
                command=cmd,
            ).pack(side=tk.LEFT, padx=3)

        # — Video queue —
        self.queue_panel = VideoQueuePanel(body, fg_color="#181825", corner_radius=12)
        self.queue_panel.pack(fill=tk.BOTH, expand=True, pady=4)

        # — Settings panel —
        self.settings_panel = SettingsPanel(
            body, settings=self.settings,
            encoder_label=self.encoder.label,
            fg_color="#181825", corner_radius=12,
        )
        self.settings_panel.pack(fill=tk.X, pady=4)

        # — Action buttons —
        actions = ctk.CTkFrame(body, fg_color="transparent")
        actions.pack(fill=tk.X, pady=4)

        self.start_btn = ctk.CTkButton(
            actions, text="🚀  START PROCESSING", height=48,
            font=("Segoe UI", 16, "bold"),
            fg_color="#a6e3a1", hover_color="#94e2d5", text_color="#1e1e2e",
            command=self._start,
        )
        self.start_btn.pack(side=tk.LEFT, expand=True, fill=tk.X, padx=(0, 6))

        self.cancel_btn = ctk.CTkButton(
            actions, text="⛔  Cancel", height=48,
            font=("Segoe UI", 14, "bold"),
            fg_color="#f38ba8", hover_color="#eba0ac", text_color="#1e1e2e",
            state="disabled", command=self._cancel,
        )
        self.cancel_btn.pack(side=tk.RIGHT, padx=(6, 0), ipadx=10)

        # — Progress —
        self.progress_panel = ProgressPanel(body)
        self.progress_panel.pack(fill=tk.X, pady=4)

        # — Log viewer —
        self.log_viewer = LogViewer(body, height=130, fg_color="transparent")
        self.log_viewer.pack(fill=tk.BOTH, expand=False, pady=(4, 0))

    # ═════════════════════════════════════════════════════════
    #  Queue Management
    # ═════════════════════════════════════════════════════════

    def _add_url(self):
        url = self.url_entry.get().strip()
        if not url:
            return
        entry = VideoEntry(
            url=url,
            start_time=self.ts_start.get().strip() or None,
            end_time=self.ts_end.get().strip() or None,
        )
        self.entries.append(entry)
        self.url_entry.delete(0, tk.END)
        self.ts_start.delete(0, tk.END)
        self.ts_end.delete(0, tk.END)
        self._refresh_queue()
        self.url_entry.focus()

    def _open_playlist(self):
        PlaylistDialog(self, self._on_playlist_import)

    def _on_playlist_import(self, urls: List[str]):
        for u in urls:
            self.entries.append(VideoEntry(url=u))
        self._refresh_queue()
        self._log(f"📋 Imported {len(urls)} video(s) from playlist.")

    def _load_txt(self):
        fp = filedialog.askopenfilename(filetypes=[("Text Files", "*.txt")])
        if not fp:
            return
        count = 0
        with open(fp, encoding="utf-8") as fh:
            for line in fh:
                entry = parse_url_line(line)
                if entry:
                    self.entries.append(entry)
                    count += 1
        self._refresh_queue()
        self._log(f"📂 Loaded {count} video(s) from file.")

    def _remove_selected(self):
        indices = self.queue_panel.selection_indices
        for i in reversed(indices):
            if 0 <= i < len(self.entries):
                self.entries.pop(i)
        self._refresh_queue()

    def _move_up(self):
        indices = self.queue_panel.selection_indices
        if indices and indices[0] > 0:
            i = indices[0]
            self.entries[i], self.entries[i - 1] = self.entries[i - 1], self.entries[i]
            self._refresh_queue()
            self.queue_panel.select_index(i - 1)

    def _move_down(self):
        indices = self.queue_panel.selection_indices
        if indices and indices[0] < len(self.entries) - 1:
            i = indices[0]
            self.entries[i], self.entries[i + 1] = self.entries[i + 1], self.entries[i]
            self._refresh_queue()
            self.queue_panel.select_index(i + 1)

    def _clear_all(self):
        if self.entries and messagebox.askyesno("Confirm", "Remove all videos from queue?"):
            self.entries.clear()
            self._refresh_queue()

    def _refresh_queue(self):
        self.queue_panel.refresh(self.entries)

    # ═════════════════════════════════════════════════════════
    #  Engine Control
    # ═════════════════════════════════════════════════════════

    def _start(self):
        if not self.entries:
            messagebox.showwarning("Empty Queue", "Add at least one video URL first.")
            return
        if self.is_running:
            return

        # Apply settings from the panel
        self.settings = self.settings_panel.apply()

        # Reset entries for a fresh run
        for e in self.entries:
            e.set_status(VideoStatus.PENDING)
            e.set_progress(0.0)

        self.is_running = True
        self.start_btn.configure(state="disabled")
        self.cancel_btn.configure(state="normal")
        self.progress_panel.reset()
        self.log_viewer.clear()

        try:
            self.engine = MergeEngine(
                settings=self.settings,
                on_progress=self._on_progress,
                on_log=self._log,
            )
            self.engine.videos = self.entries
        except Exception as exc:
            messagebox.showerror("Startup Error", str(exc))
            self._on_done(False)
            return

        threading.Thread(target=self._run_engine, daemon=True).start()
        # Start polling for queue refreshes
        self._poll_queue()

    def _run_engine(self):
        ok = False
        try:
            ok = self.engine.run()
        except Exception as exc:
            self._log(f"💥 {exc}")
        self.after(0, self._on_done, ok)

    def _on_done(self, success: bool):
        self.is_running = False
        self.start_btn.configure(state="normal")
        self.cancel_btn.configure(state="disabled")
        self.progress_panel.set_done(success)
        self._refresh_queue()
        if self._poll_id:
            self.after_cancel(self._poll_id)
            self._poll_id = None
        if success:
            messagebox.showinfo("Success", f"Saved to:\n{self.settings.output_path}")

    def _cancel(self):
        if self.engine:
            self.engine.cancel()
            self._log("⛔ Cancellation requested …")

    # ── Callbacks (called from engine threads) ───────────────

    def _log(self, msg: str):
        """Thread-safe log append."""
        self.after(0, self.log_viewer.append, msg)

    def _on_progress(self, stage: str, current: int, total: int):
        """Thread-safe progress update."""
        self.after(0, self.progress_panel.update_progress, stage, current, total)

    def _poll_queue(self):
        """Periodically refresh the queue view to show live status updates."""
        if self.is_running:
            self._refresh_queue()
            self._poll_id = self.after(500, self._poll_queue)
