"""
settings_panel.py — Collapsible settings panel for the main window.

Contains:
  • Resolution selector
  • Output file path + browse
  • Output format selector (mp4 / mkv)
  • Fade transitions toggle
  • Background music path + volume slider
  • Detected encoder info label
"""

import tkinter as tk
from tkinter import filedialog

import customtkinter as ctk

from ..config import RESOLUTIONS, AppSettings


class SettingsPanel(ctk.CTkFrame):
    """
    Settings panel that reads/writes an AppSettings instance.
    Call `apply()` to push UI values back into the settings object.
    """

    def __init__(self, master, settings: AppSettings, encoder_label: str = "", **kwargs):
        super().__init__(master, **kwargs)
        self.settings = settings

        # ── Row 1: Resolution, Output Format, Encoder badge ──
        r1 = ctk.CTkFrame(self, fg_color="transparent")
        r1.pack(fill=tk.X, padx=12, pady=(10, 4))

        ctk.CTkLabel(r1, text="Resolution", font=("Segoe UI", 12, "bold"),
                      text_color="#cdd6f4").pack(side=tk.LEFT, padx=(0, 6))
        self.res_var = ctk.StringVar(value=settings.resolution)
        ctk.CTkOptionMenu(
            r1, variable=self.res_var,
            values=list(RESOLUTIONS.keys()), width=100,
            fg_color="#45475a", button_color="#585b70",
            dropdown_fg_color="#313244",
        ).pack(side=tk.LEFT, padx=4)

        ctk.CTkLabel(r1, text="Format", font=("Segoe UI", 12, "bold"),
                      text_color="#cdd6f4").pack(side=tk.LEFT, padx=(20, 6))
        self.fmt_var = ctk.StringVar(value=settings.output_format)
        ctk.CTkOptionMenu(
            r1, variable=self.fmt_var,
            values=["mp4", "mkv"], width=80,
            fg_color="#45475a", button_color="#585b70",
            dropdown_fg_color="#313244",
        ).pack(side=tk.LEFT, padx=4)

        if encoder_label:
            badge_color = "#a6e3a1" if "GPU" in encoder_label else "#f9e2af"
            ctk.CTkLabel(
                r1, text=f"⚡ {encoder_label}",
                font=("Segoe UI", 11, "bold"),
                text_color=badge_color,
            ).pack(side=tk.RIGHT, padx=8)

        # ── Row 2: Output file path ──────────────────────────
        r2 = ctk.CTkFrame(self, fg_color="transparent")
        r2.pack(fill=tk.X, padx=12, pady=4)

        ctk.CTkLabel(r2, text="Output File", font=("Segoe UI", 12, "bold"),
                      text_color="#cdd6f4").pack(side=tk.LEFT, padx=(0, 6))
        self.out_var = ctk.StringVar(value=settings.output_path)
        ctk.CTkEntry(r2, textvariable=self.out_var, height=32).pack(
            side=tk.LEFT, fill=tk.X, expand=True, padx=4
        )
        ctk.CTkButton(
            r2, text="Browse", width=80, height=32,
            fg_color="#45475a", hover_color="#585b70",
            command=self._browse_output,
        ).pack(side=tk.RIGHT, padx=4)

        # ── Row 3: Transitions + Music ───────────────────────
        r3 = ctk.CTkFrame(self, fg_color="transparent")
        r3.pack(fill=tk.X, padx=12, pady=(4, 10))

        self.fade_var = ctk.BooleanVar(value=settings.enable_transitions)
        ctk.CTkSwitch(
            r3, text="Fade Transitions (slower)", variable=self.fade_var,
            font=("Segoe UI", 11), text_color="#cdd6f4",
            progress_color="#cba6f7",
        ).pack(side=tk.LEFT, padx=(0, 20))

        ctk.CTkLabel(r3, text="Music", font=("Segoe UI", 12, "bold"),
                      text_color="#cdd6f4").pack(side=tk.LEFT, padx=(0, 6))
        self.music_var = ctk.StringVar(value=settings.background_music)
        ctk.CTkEntry(
            r3, textvariable=self.music_var, height=32, width=200,
            placeholder_text="optional bg music…",
        ).pack(side=tk.LEFT, padx=4)
        ctk.CTkButton(
            r3, text="Browse", width=80, height=32,
            fg_color="#45475a", hover_color="#585b70",
            command=self._browse_music,
        ).pack(side=tk.LEFT, padx=4)

        ctk.CTkLabel(r3, text="Vol", text_color="#a6adc8").pack(side=tk.LEFT, padx=(12, 4))
        self.vol_var = ctk.DoubleVar(value=settings.music_volume)
        ctk.CTkSlider(
            r3, from_=0, to=1, variable=self.vol_var, width=100,
            progress_color="#cba6f7", fg_color="#313244",
        ).pack(side=tk.LEFT, padx=4)

    # ── Helpers ──────────────────────────────────────────────

    def _browse_output(self):
        fmt = self.fmt_var.get()
        fp = filedialog.asksaveasfilename(
            defaultextension=f".{fmt}",
            filetypes=[(fmt.upper(), f"*.{fmt}")],
        )
        if fp:
            self.out_var.set(fp)

    def _browse_music(self):
        fp = filedialog.askopenfilename(
            filetypes=[("Audio Files", "*.mp3 *.wav *.aac *.ogg *.flac")],
        )
        if fp:
            self.music_var.set(fp)

    def apply(self) -> AppSettings:
        """Push current UI values back into self.settings and return it."""
        self.settings.resolution = self.res_var.get()
        self.settings.output_format = self.fmt_var.get()
        self.settings.enable_transitions = self.fade_var.get()
        self.settings.background_music = self.music_var.get().strip()
        self.settings.music_volume = self.vol_var.get()

        out = self.out_var.get().strip()
        if out:
            # Ensure extension matches format
            fmt = self.settings.output_format
            if not out.lower().endswith(f".{fmt}"):
                out = out.rsplit(".", 1)[0] + f".{fmt}" if "." in out else out + f".{fmt}"
            self.settings.output_path = out

        return self.settings
