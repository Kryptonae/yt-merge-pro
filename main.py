#!/usr/bin/env python3
"""
╔══════════════════════════════════════════════════════════════╗
║               YT Merge Pro  — Entry Point                    ║
║       Download, Process & Merge YouTube Videos               ║
║           With NVIDIA NVENC Hardware Acceleration            ║
╚══════════════════════════════════════════════════════════════╝

Usage:
    python main.py          Launch the GUI application
"""

import logging
import sys

# ─── Logging Setup ───────────────────────────────────────────
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  %(levelname)-8s  %(name)s — %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger("yt_merge")


def check_dependencies():
    """Verify required packages are installed and give clear messages if not."""
    missing = []

    try:
        import yt_dlp  # noqa: F401
    except ImportError:
        missing.append("yt-dlp")

    try:
        import customtkinter  # noqa: F401
    except ImportError:
        missing.append("customtkinter")

    if missing:
        print("\n" + "=" * 55)
        print("  MISSING DEPENDENCIES")
        print("=" * 55)
        print(f"\n  Install with:  pip install {' '.join(missing)}\n")
        sys.exit(1)


def main():
    check_dependencies()

    from yt_merge.gui.app import App

    logger.info("Starting YT Merge Pro …")
    app = App()
    app.mainloop()


if __name__ == "__main__":
    main()
