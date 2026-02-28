"""
engine.py — Pipeline orchestrator for download → process → merge.

Coordinates:
  • Parallel downloads via ThreadPoolExecutor
  • Sequential processing (GPU can only do one encode at a time)
  • Smart merge: fast concat (copy) or xfade (re-encode)
  • Background music overlay
  • Cancellation at every stage
  • Aggregated progress reporting
"""

import logging
import os
import shutil
import subprocess
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Callable, List, Optional

from .config import (
    AppSettings, EncoderProfile, detect_encoder, get_cache_dir,
    AUDIO_CODEC,
)
from .downloader import DownloadManager
from .models import VideoEntry, VideoStatus
from .processor import VideoProcessor
from .utils import find_ffmpeg, get_video_duration

logger = logging.getLogger(__name__)

# Callback types
LogCallback = Callable[[str], None]
ProgressCallback = Callable[[str, int, int], None]  # (stage, current, total)


class MergeEngine:
    """
    Orchestrates the full pipeline:
      1. Download all videos (parallel)
      2. Normalize each video (sequential — GPU bound)
      3. Merge into final output
      4. Optionally overlay background music
    """

    def __init__(
        self,
        settings: AppSettings,
        on_progress: Optional[ProgressCallback] = None,
        on_log: Optional[LogCallback] = None,
    ):
        self.settings = settings
        self.on_progress = on_progress or (lambda *_: None)
        self.on_log = on_log or logger.info

        # Lazy init — may raise if ffmpeg missing
        self.ffmpeg, self.ffprobe = find_ffmpeg()
        self.encoder: EncoderProfile = detect_encoder()
        self.cache_dir = get_cache_dir()

        self.videos: List[VideoEntry] = []
        self._cancelled = False

        # Sub-components
        self._downloader: Optional[DownloadManager] = None
        self._processor: Optional[VideoProcessor] = None

    # ── Public API ───────────────────────────────────────────

    def cancel(self) -> None:
        """Signal all stages to stop ASAP."""
        self._cancelled = True
        if self._downloader:
            self._downloader.cancel()
        if self._processor:
            self._processor.cancel()

    def run(self) -> bool:
        """
        Execute the full pipeline.  Returns True on success.
        Safe to call from a background thread.
        """
        self._cancelled = False
        total = len(self.videos)
        if total == 0:
            self.on_log("⚠ No videos in queue.")
            return False

        self.on_log(f"🚀 Engine: {self.encoder.label} | {total} video(s)")
        self.on_log(f"   Resolution: {self.settings.resolution}")
        self.on_log(f"   Cache: {self.cache_dir}\n")

        try:
            # ── Stage 1: Download ────────────────────────────
            if not self._stage_download():
                return False

            # ── Stage 2: Process ─────────────────────────────
            if not self._stage_process():
                return False

            # ── Stage 3: Merge ───────────────────────────────
            if not self._stage_merge():
                return False

            # ── Stage 4: Music overlay (optional) ────────────
            self._stage_music()

            self.on_log(f"\n✅ SUCCESS → {self.settings.output_path}")
            self.on_progress("done", total, total)
            return True

        except Exception as exc:
            self.on_log(f"\n💥 Pipeline error: {exc}")
            logger.exception("Pipeline failed")
            return False

    # ── Stage 1: Parallel Downloads ──────────────────────────

    def _stage_download(self) -> bool:
        self.on_log("━" * 50)
        self.on_log("STAGE 1 / 3 — Downloading")
        self.on_log("━" * 50)

        self._downloader = DownloadManager(
            settings=self.settings,
            cache_dir=self.cache_dir,
            on_progress=self._dl_progress_relay,
            on_log=self.on_log,
        )

        total = len(self.videos)
        completed = 0

        with ThreadPoolExecutor(max_workers=self.settings.max_concurrent_downloads) as pool:
            futures = {
                pool.submit(self._downloader.download, v, i, total): i
                for i, v in enumerate(self.videos)
            }
            for future in as_completed(futures):
                if self._cancelled:
                    return False
                completed += 1
                self.on_progress("download", completed, total)

        # Check how many succeeded
        ok = sum(1 for v in self.videos if v.status == VideoStatus.DOWNLOADED)
        if ok == 0:
            self.on_log("✖ All downloads failed.")
            return False
        if ok < total:
            self.on_log(f"⚠ {total - ok} download(s) failed — continuing with {ok}.")
        return True

    def _dl_progress_relay(self, entry: VideoEntry, speed_str: str) -> None:
        """Relay per-video speed info (called from download threads)."""
        # This just updates the entry; GUI polls via to_dict()
        pass

    # ── Stage 2: Sequential Processing ───────────────────────

    def _stage_process(self) -> bool:
        self.on_log("\n" + "━" * 50)
        self.on_log("STAGE 2 / 3 — Processing & Normalizing")
        self.on_log("━" * 50)

        self._processor = VideoProcessor(
            settings=self.settings,
            encoder=self.encoder,
            ffmpeg=self.ffmpeg,
            ffprobe=self.ffprobe,
            cache_dir=self.cache_dir,
            on_log=self.on_log,
        )

        total = len(self.videos)
        for i, v in enumerate(self.videos):
            if self._cancelled:
                return False
            if v.status == VideoStatus.DOWNLOADED:
                self._processor.process(v, i, total)
            self.on_progress("process", i + 1, total)

        ok = sum(1 for v in self.videos if v.status == VideoStatus.PROCESSED)
        if ok == 0:
            self.on_log("✖ No videos were processed successfully.")
            return False
        return True

    # ── Stage 3: Merge ───────────────────────────────────────

    def _stage_merge(self) -> bool:
        self.on_log("\n" + "━" * 50)
        self.on_log("STAGE 3 / 3 — Merging")
        self.on_log("━" * 50)

        ready = [
            v.processed_path for v in self.videos
            if v.processed_path and os.path.isfile(v.processed_path)
        ]
        if not ready:
            self.on_log("✖ No processed files available to merge.")
            return False

        output = os.path.abspath(self.settings.output_path)
        os.makedirs(os.path.dirname(output) or ".", exist_ok=True)

        if self.settings.enable_transitions:
            ok = self._merge_xfade(ready, output)
        else:
            ok = self._merge_concat(ready, output)

        self.on_progress("merge", 1, 1)
        return ok

    def _merge_concat(self, files: List[str], output: str) -> bool:
        """Fast merge via FFmpeg concat demuxer (no re-encoding)."""
        if len(files) == 1:
            shutil.copy2(files[0], output)
            self.on_log("  → Single file copied to output.")
            return True

        self.on_log("  🔗 Fast concat (no re-encode) …")
        list_file = os.path.join(self.cache_dir, "concat_list.txt")
        with open(list_file, "w", encoding="utf-8") as fh:
            for f in files:
                safe = f.replace("\\", "/").replace("'", "'\\''")
                fh.write(f"file '{safe}'\n")

        cmd = [
            self.ffmpeg, "-y", "-hide_banner", "-loglevel", "warning",
            "-f", "concat", "-safe", "0", "-i", list_file,
            "-c", "copy", "-movflags", "+faststart", output,
        ]
        result = subprocess.run(cmd, capture_output=True, text=True)
        if result.returncode != 0:
            self.on_log(f"  ✖ Concat failed: {result.stderr[-200:]}")
            return False
        return True

    def _merge_xfade(self, files: List[str], output: str) -> bool:
        """Merge with crossfade transitions (requires re-encoding)."""
        n = len(files)
        if n == 1:
            shutil.copy2(files[0], output)
            return True

        self.on_log(f"  🔗 Crossfade merge ({n} files, re-encoding) …")
        fade = self.settings.fade_duration
        durations = [get_video_duration(f, self.ffprobe) for f in files]

        # Build xfade / acrossfade filter chains
        vfilters, afilters = [], []
        # Running offset tracks the timeline position accounting for overlaps
        running_offset = durations[0] if durations[0] > 0 else 5.0

        for i in range(1, n):
            v_in1 = f"[{i-1}:v]" if i == 1 else f"[vf{i-1}]"
            v_out  = f"[vf{i}]"  if i < n - 1 else "[vout]"
            a_in1 = f"[{i-1}:a]" if i == 1 else f"[af{i-1}]"
            a_out  = f"[af{i}]"  if i < n - 1 else "[aout]"

            offset = max(running_offset - fade, 0)
            vfilters.append(
                f"{v_in1}[{i}:v]xfade=transition=fade:"
                f"duration={fade}:offset={offset:.3f}{v_out}"
            )
            afilters.append(
                f"{a_in1}[{i}:a]acrossfade=d={fade}:c1=tri:c2=tri{a_out}"
            )
            # Next offset = current offset + next clip duration - fade overlap
            next_dur = durations[i] if i < len(durations) and durations[i] > 0 else 5.0
            running_offset = offset + next_dur

        cmd = [self.ffmpeg, "-y"]
        cmd += self.encoder.hwaccel_args
        cmd += ["-hide_banner", "-loglevel", "warning"]
        for f in files:
            cmd += ["-i", f]
        cmd += [
            "-filter_complex", ";".join(vfilters + afilters),
            "-map", "[vout]", "-map", "[aout]",
            "-c:v", self.encoder.codec, "-preset", self.encoder.preset,
        ]
        cmd += self.encoder.quality_args
        cmd += ["-c:a", AUDIO_CODEC, "-movflags", "+faststart", output]

        result = subprocess.run(cmd, capture_output=True, text=True)
        if result.returncode != 0:
            self.on_log(f"  ⚠ Crossfade failed, falling back to fast concat.")
            self.on_log(f"    {result.stderr[-200:]}")
            return self._merge_concat(files, output)
        return True

    # ── Stage 4: Background Music Overlay ────────────────────

    def _stage_music(self) -> None:
        music = self.settings.background_music
        if not music or not os.path.isfile(music):
            return

        output = os.path.abspath(self.settings.output_path)
        self.on_log("\n🎵 Overlaying background music …")
        tmp = os.path.join(self.cache_dir, "with_music.mp4")
        vol = self.settings.music_volume

        fc = (
            f"[1:a]aloop=loop=-1:size=2e+09,volume={vol}[bg];"
            f"[0:a][bg]amix=inputs=2:duration=first:dropout_transition=3[aout]"
        )
        cmd = [
            self.ffmpeg, "-y", "-hide_banner", "-loglevel", "warning",
            "-i", output, "-i", music,
            "-filter_complex", fc,
            "-map", "0:v", "-map", "[aout]",
            "-c:v", "copy", "-c:a", AUDIO_CODEC,
            "-shortest", tmp,
        ]
        result = subprocess.run(cmd, capture_output=True, text=True)
        if result.returncode == 0:
            shutil.move(tmp, output)
            self.on_log("  ✔ Music overlay applied.")
        else:
            self.on_log(f"  ⚠ Music overlay failed: {result.stderr[-150:]}")
