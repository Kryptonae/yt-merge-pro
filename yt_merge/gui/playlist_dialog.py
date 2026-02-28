"""
playlist_dialog.py — YouTube playlist import dialog.

Features:
  • Fetch playlist metadata via yt-dlp (flat extraction)
  • Display video titles with duration in a dark-themed Treeview
  • Select All / None / individual toggle / Shift-click range selection
  • Filter by keyword (title search box)
  • Import selected videos into main queue
"""

import threading
import tkinter as tk
from tkinter import ttk
from typing import Callable, Dict, List

import customtkinter as ctk
import yt_dlp

from ..utils import seconds_to_timestamp
from .components import apply_dark_treeview_style


class PlaylistDialog(ctk.CTkToplevel):
    """Modal dialog for importing videos from a YouTube playlist."""

    def __init__(self, parent, on_import: Callable[[List[str]], None]):
        super().__init__(parent)
        self.title("Import YouTube Playlist")
        self.geometry("800x580")
        self.minsize(640, 400)
        self.on_import = on_import
        self.videos: List[Dict] = []       # raw metadata dicts
        self._last_clicked: int = -1       # for shift-click range select
        self.transient(parent)
        self.grab_set()

        self._build_ui()

    # ── UI Construction ──────────────────────────────────────

    def _build_ui(self):
        # ── Top: URL input ───────────────────────────────────
        top = ctk.CTkFrame(self)
        top.pack(fill=tk.X, padx=16, pady=(16, 8))

        ctk.CTkLabel(top, text="Playlist URL:", font=("Segoe UI", 13, "bold")).pack(
            side=tk.LEFT, padx=(8, 4)
        )
        self.url_entry = ctk.CTkEntry(
            top, placeholder_text="Paste playlist link here …", height=36
        )
        self.url_entry.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=8)
        self.fetch_btn = ctk.CTkButton(
            top, text="⬇ Fetch", width=100, height=36, command=self._fetch_threaded,
        )
        self.fetch_btn.pack(side=tk.RIGHT, padx=8)

        # ── Filter bar ───────────────────────────────────────
        filt = ctk.CTkFrame(self, fg_color="transparent")
        filt.pack(fill=tk.X, padx=16, pady=4)
        ctk.CTkLabel(filt, text="Filter:", font=("Segoe UI", 11)).pack(side=tk.LEFT, padx=4)
        self.filter_entry = ctk.CTkEntry(
            filt, placeholder_text="type to filter by title …", height=30
        )
        self.filter_entry.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=4)
        self.filter_entry.bind("<KeyRelease>", lambda _: self._apply_filter())

        # ── Treeview ─────────────────────────────────────────
        apply_dark_treeview_style()
        tree_frame = ctk.CTkFrame(self)
        tree_frame.pack(fill=tk.BOTH, expand=True, padx=16, pady=4)

        self.tree = ttk.Treeview(
            tree_frame, columns=("sel", "title", "dur"),
            show="headings", height=14, style="Dark.Treeview",
        )
        self.tree.heading("sel",   text="☑")
        self.tree.heading("title", text="Video Title")
        self.tree.heading("dur",   text="Duration")
        self.tree.column("sel",   width=45,  anchor="center", stretch=False)
        self.tree.column("title", width=530, anchor="w")
        self.tree.column("dur",   width=100, anchor="center", stretch=False)
        self.tree.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)

        sb = ttk.Scrollbar(tree_frame, orient=tk.VERTICAL, command=self.tree.yview)
        self.tree.configure(yscrollcommand=sb.set)
        sb.pack(side=tk.RIGHT, fill=tk.Y)

        self.tree.bind("<Button-1>", self._on_click)
        self.tree.bind("<Shift-Button-1>", self._on_shift_click)

        # ── Bottom buttons ───────────────────────────────────
        bottom = ctk.CTkFrame(self, fg_color="transparent")
        bottom.pack(fill=tk.X, padx=16, pady=(8, 16))

        ctk.CTkButton(
            bottom, text="Select All", width=100,
            fg_color="#45475a", hover_color="#585b70",
            command=lambda: self._set_all("☑"),
        ).pack(side=tk.LEFT, padx=4)

        ctk.CTkButton(
            bottom, text="Select None", width=100,
            fg_color="#45475a", hover_color="#585b70",
            command=lambda: self._set_all("☐"),
        ).pack(side=tk.LEFT, padx=4)

        self.status_lbl = ctk.CTkLabel(bottom, text="Ready.", text_color="#a6adc8")
        self.status_lbl.pack(side=tk.LEFT, padx=16)

        self.import_btn = ctk.CTkButton(
            bottom, text="Import Selected", width=140,
            fg_color="#a6e3a1", hover_color="#94e2d5",
            text_color="#1e1e2e", font=("Segoe UI", 12, "bold"),
            state="disabled", command=self._import_selected,
        )
        self.import_btn.pack(side=tk.RIGHT, padx=4)

    # ── Fetch Logic ──────────────────────────────────────────

    def _fetch_threaded(self):
        url = self.url_entry.get().strip()
        if not url:
            return
        self.fetch_btn.configure(state="disabled")
        self.status_lbl.configure(text="Fetching metadata …")
        self.tree.delete(*self.tree.get_children())
        threading.Thread(target=self._fetch, args=(url,), daemon=True).start()

    def _fetch(self, url: str):
        opts = {"extract_flat": True, "quiet": True, "no_warnings": True}
        try:
            with yt_dlp.YoutubeDL(opts) as ydl:
                info = ydl.extract_info(url, download=False)
                entries = info.get("entries", [info])

            self.videos = []
            for e in (entries or []):
                if not e:
                    continue
                v_url = e.get("url", "")
                if not v_url.startswith("http"):
                    vid = e.get("id", "")
                    if vid:
                        v_url = f"https://www.youtube.com/watch?v={vid}"
                    else:
                        continue
                title = e.get("title", "Unknown Title")
                dur_s = e.get("duration")
                dur = seconds_to_timestamp(dur_s) if dur_s else "Unknown"
                self.videos.append({"url": v_url, "title": title, "dur": dur})

            self.after(0, self._populate)
        except Exception as exc:
            self.after(
                0,
                lambda: [
                    self.status_lbl.configure(text=f"Error: {str(exc)[:60]}"),
                    self.fetch_btn.configure(state="normal"),
                ],
            )

    def _populate(self):
        self.tree.delete(*self.tree.get_children())
        for i, v in enumerate(self.videos):
            self.tree.insert("", tk.END, iid=str(i), values=("☐", v["title"], v["dur"]))
        self.status_lbl.configure(text=f"Found {len(self.videos)} video(s).")
        self.fetch_btn.configure(state="normal")
        if self.videos:
            self.import_btn.configure(state="normal")

    # ── Filter ───────────────────────────────────────────────

    def _apply_filter(self):
        query = self.filter_entry.get().strip().lower()
        self.tree.delete(*self.tree.get_children())
        for i, v in enumerate(self.videos):
            if query and query not in v["title"].lower():
                continue
            self.tree.insert("", tk.END, iid=str(i), values=("☐", v["title"], v["dur"]))

    # ── Selection Handling ───────────────────────────────────

    def _on_click(self, event):
        item = self.tree.identify_row(event.y)
        col = self.tree.identify_column(event.x)
        if item and col == "#1":
            self._last_clicked = int(item)
            vals = list(self.tree.item(item, "values"))
            vals[0] = "☐" if vals[0] == "☑" else "☑"
            self.tree.item(item, values=vals)

    def _on_shift_click(self, event):
        item = self.tree.identify_row(event.y)
        col = self.tree.identify_column(event.x)
        if not item or col != "#1":
            return
        curr = int(item)
        if self._last_clicked >= 0:
            lo, hi = sorted((self._last_clicked, curr))
            target = self.tree.item(str(self._last_clicked), "values")[0]
            for i in range(lo, hi + 1):
                iid = str(i)
                if self.tree.exists(iid):
                    vals = list(self.tree.item(iid, "values"))
                    vals[0] = target
                    self.tree.item(iid, values=vals)
        self._last_clicked = curr

    def _set_all(self, state: str):
        for item in self.tree.get_children():
            vals = list(self.tree.item(item, "values"))
            vals[0] = state
            self.tree.item(item, values=vals)

    # ── Import ───────────────────────────────────────────────

    def _import_selected(self):
        selected = []
        for item in self.tree.get_children():
            if self.tree.item(item, "values")[0] == "☑":
                idx = int(item)
                if 0 <= idx < len(self.videos):
                    selected.append(self.videos[idx]["url"])
        if selected:
            self.on_import(selected)
        self.destroy()
