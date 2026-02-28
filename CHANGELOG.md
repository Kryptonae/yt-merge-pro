# Changelog

All notable changes to this project will be documented in this file.

## [1.0.0] — 2025-02-28

### 🎉 Initial Release

**YT Merge Pro** — a desktop application for downloading, trimming, and merging YouTube videos with GPU acceleration.

#### Features
- Download multiple YouTube videos in parallel (3 concurrent workers)
- Trim clips with start/end timestamps
- Merge videos via fast concat (no re-encode) or crossfade transitions
- NVIDIA NVENC auto-detection with CPU fallback
- Playlist import with keyword filtering and shift-click selection
- Batch import from `.txt` files
- Background music overlay with volume control
- Smart caching — skips re-downloading/re-processing identical videos
- Auto retry on failed downloads (3 attempts, exponential backoff)
- Per-video download speed display
- Modern dark UI (CustomTkinter, Catppuccin Mocha theme)
- Output format selection (MP4 / MKV)
- Resolution presets (480p, 720p, 1080p, 1440p)
- Clean modular architecture (12 modules, 4 packages)

#### Tech Stack
- Python 3.9+
- yt-dlp for downloading
- FFmpeg for processing and merging
- CustomTkinter for the GUI
- NVIDIA NVENC for hardware-accelerated encoding
