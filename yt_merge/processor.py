"""
processor.py — FFmpeg video processing (trim, scale, normalize).

Handles:
  • Trimming to start/end timestamps
  • Scaling + padding to target resolution (preserves aspect ratio)
  • FPS normalization
  • Silent audio generation for videos without audio
  • Cache-aware: skips if processed file already exists
"""

import logging
import os
import subprocess
from typing import Optional, Callable

from .config import (
    AppSettings, EncoderProfile, TARGET_FPS,
    AUDIO_CODEC, AUDIO_BITRATE, AUDIO_SAMPLE_RATE, AUDIO_CHANNELS,
)
from .models import VideoEntry, VideoStatus
from .utils import timestamp_to_seconds, has_audio_stream

logger = logging.getLogger(__name__)


class VideoProcessor:
    """Process a downloaded video to a standardized format for merging."""

    def __init__(
        self,
        settings: AppSettings,
        encoder: EncoderProfile,
        ffmpeg: str,
        ffprobe: str,
        cache_dir: str,
        on_log: Optional[Callable[[str], None]] = None,
    ):
        self.settings = settings
        self.encoder = encoder
        self.ffmpeg = ffmpeg
        self.ffprobe = ffprobe
        self.cache_dir = cache_dir
        self.on_log = on_log or logger.info
        self._cancelled = False

    def cancel(self) -> None:
        self._cancelled = True

    def process(self, entry: VideoEntry, index: int, total: int) -> bool:
        """
        Normalize a single video for merging.
        Returns True on success.
        """
        if self._cancelled:
            entry.set_status(VideoStatus.CANCELLED)
            return False

        if not entry.downloaded_path or not os.path.isfile(entry.downloaded_path):
            entry.set_status(VideoStatus.ERROR, error="Source file missing")
            return False

        # ── Cache check ──────────────────────────────────────
        res_h = self.settings.resolution_height
        out_path = os.path.join(
            self.cache_dir, f"proc_{entry.video_id}_{res_h}.mp4"
        )
        if os.path.isfile(out_path):
            entry.processed_path = out_path
            entry.set_status(VideoStatus.PROCESSED)
            self.on_log(f"⚡ [{index+1}/{total}] Cache hit: {entry.title}")
            return True

        # ── Build FFmpeg command ─────────────────────────────
        entry.set_status(VideoStatus.PROCESSING)
        entry.set_progress(0.0)
        self.on_log(f"⚙  [{index+1}/{total}] Processing: {entry.title}")

        tw, th = self.settings.resolution_wh
        cmd = self._build_command(entry, tw, th, out_path)

        try:
            result = subprocess.run(
                cmd, capture_output=True, text=True, timeout=600
            )
            if result.returncode != 0:
                stderr_tail = result.stderr[-400:] if result.stderr else "unknown"
                raise RuntimeError(f"FFmpeg exit code {result.returncode}: {stderr_tail}")

            entry.processed_path = out_path
            entry.set_status(VideoStatus.PROCESSED)
            self.on_log(f"  ✔ Processed: {entry.title}")
            return True

        except subprocess.TimeoutExpired:
            entry.set_status(VideoStatus.ERROR, error="Processing timed out (10 min)")
            self.on_log(f"  ✖ Timeout: {entry.title}")
            return False
        except Exception as exc:
            entry.set_status(VideoStatus.ERROR, error=str(exc)[:120])
            self.on_log(f"  ✖ Process failed: {exc}")
            return False

    # ── Command builder ──────────────────────────────────────

    def _build_command(
        self, entry: VideoEntry, tw: int, th: int, out_path: str
    ) -> list:
        cmd = [self.ffmpeg, "-y"]
        cmd += self.encoder.hwaccel_args
        cmd += ["-hide_banner", "-loglevel", "warning"]

        # Seek to start time (before -i for fast seek)
        start_sec = 0.0
        if entry.start_time:
            start_sec = timestamp_to_seconds(entry.start_time)
            cmd += ["-ss", str(start_sec)]

        cmd += ["-i", entry.downloaded_path]

        # Check for audio and add silent audio if missing
        audio_present = has_audio_stream(entry.downloaded_path, self.ffprobe)
        if not audio_present:
            cmd += [
                "-f", "lavfi", "-i",
                f"anullsrc=channel_layout=stereo:sample_rate={AUDIO_SAMPLE_RATE}"
            ]

        # Duration (end_time - start_time)
        if entry.end_time:
            end_sec = timestamp_to_seconds(entry.end_time)
            dur = end_sec - start_sec
            if dur > 0:
                cmd += ["-t", str(dur)]

        # ── Video filters ────────────────────────────────────
        vf = (
            f"scale={tw}:{th}:force_original_aspect_ratio=decrease,"
            f"pad={tw}:{th}:(ow-iw)/2:(oh-ih)/2:black,"
            f"setsar=1,fps={TARGET_FPS}"
        )
        cmd += ["-vf", vf]

        # ── Encoder settings ─────────────────────────────────
        cmd += ["-c:v", self.encoder.codec, "-preset", self.encoder.preset]
        cmd += self.encoder.quality_args

        # ── Audio settings ───────────────────────────────────
        cmd += [
            "-c:a", AUDIO_CODEC,
            "-b:a", AUDIO_BITRATE,
            "-ar",  str(AUDIO_SAMPLE_RATE),
            "-ac",  str(AUDIO_CHANNELS),
        ]

        # ── Stream mapping for silent audio ──────────────────
        if not audio_present:
            cmd += ["-map", "0:v:0", "-map", "1:a:0", "-shortest"]

        cmd += ["-movflags", "+faststart", out_path]
        return cmd
