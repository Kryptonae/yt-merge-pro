"""
config.py — Application constants, hardware detection, and user settings.

Handles:
  • Resolution presets and codec defaults
  • Lazy NVIDIA GPU (NVENC) detection with CPU fallback
  • Central AppSettings dataclass for all user-configurable options
  • Cache directory management
"""

import os
import shutil
import subprocess
import logging
from dataclasses import dataclass, field
from typing import Tuple, List

logger = logging.getLogger(__name__)

# ─── Resolution Presets ───────────────────────────────────────
RESOLUTIONS = {
    "480p":  (854, 480),
    "720p":  (1280, 720),
    "1080p": (1920, 1080),
    "1440p": (2560, 1440),
}

# ─── Audio / Video Defaults ──────────────────────────────────
TARGET_FPS         = 30
AUDIO_CODEC        = "aac"
AUDIO_BITRATE      = "192k"
AUDIO_SAMPLE_RATE  = 44100
AUDIO_CHANNELS     = 2
FADE_DURATION      = 0.5

# ─── Download Defaults ────────────────────────────────────────
MAX_CONCURRENT_DOWNLOADS = 3
MAX_RETRIES              = 3
CONCURRENT_FRAGMENTS     = 8


# ─── Encoder Detection ───────────────────────────────────────

@dataclass
class EncoderProfile:
    """Holds the detected (or fallback) encoder settings."""
    codec: str = "libx264"
    hwaccel_args: List[str] = field(default_factory=list)
    quality_args: List[str] = field(default_factory=lambda: ["-crf", "23"])
    preset: str = "ultrafast"
    is_gpu: bool = False

    @property
    def label(self) -> str:
        return f"{self.codec} ({'GPU' if self.is_gpu else 'CPU'})"


def detect_encoder() -> EncoderProfile:
    """
    Auto-detect NVIDIA GPU via nvidia-smi.
    Returns an NVENC profile if available, otherwise falls back to libx264.
    """
    if not shutil.which("nvidia-smi"):
        logger.info("nvidia-smi not found — using CPU encoder (libx264)")
        return EncoderProfile()

    try:
        result = subprocess.run(
            ["nvidia-smi"], stdout=subprocess.PIPE, stderr=subprocess.PIPE,
            timeout=5, check=True,
        )
        logger.info("NVIDIA GPU detected — using h264_nvenc")
        return EncoderProfile(
            codec="h264_nvenc",
            hwaccel_args=["-hwaccel", "cuda"],
            quality_args=["-cq", "23", "-spatial_aq", "1"],
            preset="p4",
            is_gpu=True,
        )
    except (subprocess.SubprocessError, FileNotFoundError, OSError) as exc:
        logger.warning("GPU detection failed (%s) — falling back to CPU", exc)
        return EncoderProfile()


# ─── Cache Directory ──────────────────────────────────────────

def get_cache_dir() -> str:
    """Return a stable cache directory path (survives CWD changes)."""
    base = os.environ.get("LOCALAPPDATA") or os.path.expanduser("~")
    cache = os.path.join(base, "YTMergePro", "cache")
    os.makedirs(cache, exist_ok=True)
    return cache


# ─── Application Settings ────────────────────────────────────

@dataclass
class AppSettings:
    """All user-configurable settings in one place."""
    resolution: str = "1080p"
    output_path: str = "output.mp4"
    output_format: str = "mp4"          # mp4 or mkv
    enable_transitions: bool = False
    fade_duration: float = FADE_DURATION
    background_music: str = ""
    music_volume: float = 0.15
    max_concurrent_downloads: int = MAX_CONCURRENT_DOWNLOADS

    @property
    def resolution_wh(self) -> Tuple[int, int]:
        return RESOLUTIONS.get(self.resolution, (1920, 1080))

    @property
    def resolution_height(self) -> int:
        return self.resolution_wh[1]
