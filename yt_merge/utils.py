"""
utils.py — Shared utility functions.

Covers:
  • Timestamp ↔ seconds conversion
  • Filename sanitization
  • FFmpeg / ffprobe binary discovery
  • FFprobe helpers (duration, audio stream detection)
  • URL validation and text-file line parsing
"""

import json
import logging
import os
import re
import shutil
import subprocess
from typing import Optional, Tuple

from .models import VideoEntry

logger = logging.getLogger(__name__)


# ─── Timestamp Helpers ────────────────────────────────────────

def timestamp_to_seconds(ts: str) -> float:
    """
    Convert a timestamp string to seconds.
    Accepted formats: "90", "1:30", "0:01:30", "01:30.500"
    Returns 0.0 for empty / invalid input.
    """
    if not ts:
        return 0.0
    ts = ts.strip()

    # Direct numeric value
    try:
        return float(ts)
    except ValueError:
        pass

    parts = ts.split(":")
    try:
        if len(parts) == 3:
            return int(parts[0]) * 3600 + int(parts[1]) * 60 + float(parts[2])
        if len(parts) == 2:
            return int(parts[0]) * 60 + float(parts[1])
    except (ValueError, IndexError):
        logger.warning("Could not parse timestamp: %s", ts)
    return 0.0


def seconds_to_timestamp(s: float) -> str:
    """Convert seconds to HH:MM:SS.mmm format."""
    if s <= 0:
        return "00:00:00.000"
    h = int(s // 3600)
    m = int((s % 3600) // 60)
    sec = s % 60
    return f"{h:02d}:{m:02d}:{sec:06.3f}"


# ─── Filename / Path Helpers ─────────────────────────────────

def sanitize_filename(name: str) -> str:
    """Strip illegal characters and clamp length for Windows/Linux FS."""
    cleaned = re.sub(r'[<>:"/\\|?*\x00-\x1f]', '_', name).strip()
    return cleaned[:150] if cleaned else "untitled"


# ─── FFmpeg / FFprobe Discovery ──────────────────────────────

def find_ffmpeg() -> Tuple[str, str]:
    """
    Locate ffmpeg and ffprobe on PATH.
    Raises FileNotFoundError with a user-friendly message if missing.
    """
    ffmpeg = shutil.which("ffmpeg")
    if not ffmpeg:
        raise FileNotFoundError(
            "ffmpeg was not found on your system PATH.\n"
            "Download it from https://ffmpeg.org/download.html and add it to PATH."
        )

    ffprobe = shutil.which("ffprobe")
    if not ffprobe:
        # Try same directory as ffmpeg
        ffmpeg_dir = os.path.dirname(ffmpeg)
        candidate = os.path.join(ffmpeg_dir, "ffprobe.exe" if os.name == "nt" else "ffprobe")
        if os.path.isfile(candidate):
            ffprobe = candidate
        else:
            raise FileNotFoundError(
                "ffprobe was not found. It usually ships alongside ffmpeg.\n"
                "Make sure both are on your PATH."
            )

    logger.info("ffmpeg  : %s", ffmpeg)
    logger.info("ffprobe : %s", ffprobe)
    return ffmpeg, ffprobe


# ─── FFprobe Helpers ─────────────────────────────────────────

def get_video_duration(filepath: str, ffprobe: str = "ffprobe") -> float:
    """Return the duration of a media file in seconds (0.0 on failure)."""
    cmd = [ffprobe, "-v", "quiet", "-print_format", "json", "-show_format", filepath]
    try:
        result = subprocess.run(cmd, capture_output=True, text=True, check=True, timeout=30)
        return float(json.loads(result.stdout)["format"]["duration"])
    except Exception as exc:
        logger.warning("Could not probe duration of %s: %s", filepath, exc)
        return 0.0


def has_audio_stream(filepath: str, ffprobe: str = "ffprobe") -> bool:
    """Check whether the file contains at least one audio stream."""
    cmd = [
        ffprobe, "-v", "quiet",
        "-select_streams", "a:0",
        "-show_entries", "stream=codec_type",
        "-of", "csv=p=0",
        filepath,
    ]
    try:
        result = subprocess.run(cmd, capture_output=True, text=True, check=True, timeout=15)
        return "audio" in result.stdout.lower()
    except Exception:
        return False


# ─── URL Validation & Parsing ────────────────────────────────

_YT_URL_RE = re.compile(
    r"(https?://)?(www\.)?"
    r"(youtube\.com/(watch\?v=|shorts/|embed/)|youtu\.be/)"
    r"[\w-]+"
)


def validate_youtube_url(url: str) -> bool:
    """Basic check that a string looks like a YouTube video URL."""
    return bool(_YT_URL_RE.search(url))


def parse_url_line(line: str) -> Optional[VideoEntry]:
    """
    Parse a single line from a batch text file.

    Supported formats:
      URL
      URL  START
      URL  START  END

    Timestamps can be separated by spaces, tabs, or commas.
    Lines starting with # are treated as comments.
    Returns None for blank / comment lines.
    """
    line = line.strip()
    if not line or line.startswith("#"):
        return None

    # Split on whitespace or commas
    parts = re.split(r"[\s,]+", line, maxsplit=2)
    url = parts[0]

    if not url.startswith("http"):
        return None

    start = parts[1] if len(parts) > 1 else None
    end   = parts[2] if len(parts) > 2 else None

    return VideoEntry(url=url, start_time=start, end_time=end)
