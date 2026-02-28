"""
downloader.py — yt-dlp download manager with per-video progress and retry.

Features:
  • Real per-video progress via yt-dlp progress_hooks
  • Automatic retry with exponential backoff
  • Resume support (continuedl)
  • Cache-aware: skips re-download if file already exists
  • Thread-safe callbacks for GUI updates
"""

import logging
import os
import time
from typing import Callable, Optional

import yt_dlp

from .config import AppSettings, get_cache_dir, MAX_RETRIES, CONCURRENT_FRAGMENTS
from .models import VideoEntry, VideoStatus
from .utils import sanitize_filename

logger = logging.getLogger(__name__)

# Type alias for the progress callback: (entry, stage_label) -> None
ProgressCallback = Callable[[VideoEntry, str], None]


class DownloadManager:
    """
    Wraps yt-dlp to download a single VideoEntry with progress hooks,
    retry logic, and cache awareness.
    """

    def __init__(
        self,
        settings: AppSettings,
        cache_dir: Optional[str] = None,
        on_progress: Optional[ProgressCallback] = None,
        on_log: Optional[Callable[[str], None]] = None,
    ):
        self.settings = settings
        self.cache_dir = cache_dir or get_cache_dir()
        self.on_progress = on_progress or (lambda *_: None)
        self.on_log = on_log or logger.info
        self._cancelled = False

    def cancel(self) -> None:
        self._cancelled = True

    def download(self, entry: VideoEntry, index: int, total: int) -> bool:
        """
        Download a single video.  Returns True on success.

        Retries up to MAX_RETRIES times on failure.
        Skips download entirely if the cached file already exists.
        """
        if self._cancelled:
            entry.set_status(VideoStatus.CANCELLED)
            return False

        res_h = self.settings.resolution_height
        cache_pattern = os.path.join(self.cache_dir, f"%(id)s_{res_h}.%(ext)s")

        for attempt in range(1, MAX_RETRIES + 1):
            if self._cancelled:
                entry.set_status(VideoStatus.CANCELLED)
                return False

            try:
                entry.set_status(VideoStatus.DOWNLOADING)
                entry.set_progress(0.0)
                self.on_log(f"⬇  [{index+1}/{total}] Downloading: {entry.url}"
                            + (f" (attempt {attempt})" if attempt > 1 else ""))

                # ── yt-dlp progress hook (fires per fragment) ──
                def _progress_hook(d, _entry=entry):
                    if d.get("status") == "downloading":
                        total_bytes = d.get("total_bytes") or d.get("total_bytes_estimate") or 0
                        downloaded = d.get("downloaded_bytes", 0)
                        if total_bytes > 0:
                            _entry.set_progress(downloaded / total_bytes)
                        speed = d.get("speed")
                        if speed:
                            speed_str = f"{speed / 1_048_576:.1f} MB/s"
                            self.on_progress(_entry, speed_str)
                    elif d.get("status") == "finished":
                        _entry.set_progress(1.0)

                opts = {
                    "format": (
                        f"bestvideo[height<={res_h}][ext=mp4]+bestaudio[ext=m4a]"
                        f"/bestvideo[height<={res_h}]+bestaudio"
                        f"/best[height<={res_h}]/best"
                    ),
                    "merge_output_format": "mp4",
                    "outtmpl": cache_pattern,
                    "quiet": True,
                    "no_warnings": True,
                    "continuedl": True,
                    "retries": 3,
                    "concurrent_fragment_downloads": CONCURRENT_FRAGMENTS,
                    "progress_hooks": [_progress_hook],
                }

                with yt_dlp.YoutubeDL(opts) as ydl:
                    info = ydl.extract_info(entry.url, download=True)
                    entry.title = sanitize_filename(info.get("title", f"video_{index}"))
                    entry.video_id = info.get("id", str(index))
                    entry.duration = info.get("duration", 0.0) or 0.0
                    entry.thumbnail_url = info.get("thumbnail", "")

                    # Locate the downloaded file
                    prepared = ydl.prepare_filename(info)
                    entry.downloaded_path = self._resolve_file(prepared)

                if not entry.downloaded_path:
                    raise FileNotFoundError("Downloaded file could not be located on disk")

                entry.set_status(VideoStatus.DOWNLOADED)
                self.on_log(f"  ✔ {entry.title}")
                return True

            except Exception as exc:
                wait = 2 ** attempt
                self.on_log(f"  ✖ Attempt {attempt} failed: {str(exc)[:80]}")
                if attempt < MAX_RETRIES:
                    self.on_log(f"  ↻ Retrying in {wait}s …")
                    time.sleep(wait)
                else:
                    entry.set_status(VideoStatus.ERROR, error=str(exc)[:120])
                    self.on_log(f"  ✖ Download failed permanently: {entry.url}")
                    return False

        return False  # unreachable but keeps linters happy

    # ── Internal helpers ─────────────────────────────────────

    @staticmethod
    def _resolve_file(prepared_path: str) -> str:
        """
        yt-dlp's prepare_filename may not match the actual extension
        after muxing (e.g., .webm → .mp4).  Try common variants.
        """
        if os.path.isfile(prepared_path):
            return prepared_path
        base = os.path.splitext(prepared_path)[0]
        for ext in (".mp4", ".mkv", ".webm", ".m4a"):
            candidate = base + ext
            if os.path.isfile(candidate):
                return candidate
        return ""
