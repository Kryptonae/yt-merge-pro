"""
models.py — Data models for the application.

Defines:
  • VideoStatus enum for tracking each video's state
  • VideoEntry dataclass representing a single video in the queue
"""

import threading
from dataclasses import dataclass, field
from enum import Enum, auto
from typing import Optional


class VideoStatus(Enum):
    """Lifecycle states of a video in the processing pipeline."""
    PENDING      = auto()
    DOWNLOADING  = auto()
    DOWNLOADED   = auto()
    PROCESSING   = auto()
    PROCESSED    = auto()
    MERGING      = auto()
    DONE         = auto()
    ERROR        = auto()
    CANCELLED    = auto()

    @property
    def display(self) -> str:
        """Human-readable status label for the UI."""
        _labels = {
            VideoStatus.PENDING:     "Pending",
            VideoStatus.DOWNLOADING: "Downloading...",
            VideoStatus.DOWNLOADED:  "Downloaded",
            VideoStatus.PROCESSING:  "Processing...",
            VideoStatus.PROCESSED:   "Processed",
            VideoStatus.MERGING:     "Merging...",
            VideoStatus.DONE:        "Done",
            VideoStatus.ERROR:       "ERROR",
            VideoStatus.CANCELLED:   "Cancelled",
        }
        return _labels.get(self, self.name)


@dataclass
class VideoEntry:
    """
    Represents a single video in the download/merge queue.

    Thread-safety: status and progress are updated from worker threads.
    A reentrant lock guards concurrent mutations, and the GUI reads
    snapshot copies via `to_dict()`.
    """
    url: str
    start_time: Optional[str] = None
    end_time:   Optional[str] = None

    # Populated after metadata fetch / download
    title:      str   = ""
    video_id:   str   = ""
    duration:   float = 0.0
    thumbnail_url: str = ""

    # File paths through the pipeline
    downloaded_path: str = ""
    processed_path:  str = ""

    # State tracking
    status:   VideoStatus = VideoStatus.PENDING
    progress: float = 0.0        # 0.0 – 1.0 within current stage
    error_msg: str  = ""

    # Internal lock for thread-safe updates
    _lock: threading.Lock = field(default_factory=threading.Lock, repr=False)

    def set_status(self, status: VideoStatus, error: str = "") -> None:
        """Thread-safe status update."""
        with self._lock:
            self.status = status
            if error:
                self.error_msg = error
            if status in (VideoStatus.DOWNLOADED, VideoStatus.PROCESSED, VideoStatus.DONE):
                self.progress = 1.0

    def set_progress(self, value: float) -> None:
        """Thread-safe progress update (clamped to 0–1)."""
        with self._lock:
            self.progress = max(0.0, min(1.0, value))

    def to_dict(self) -> dict:
        """Return a snapshot of display-relevant fields (safe to read from GUI thread)."""
        with self._lock:
            return {
                "url": self.url,
                "title": self.title or self.url,
                "start_time": self.start_time or "–",
                "end_time": self.end_time or "–",
                "status": self.status.display,
                "progress": self.progress,
                "error_msg": self.error_msg,
            }
