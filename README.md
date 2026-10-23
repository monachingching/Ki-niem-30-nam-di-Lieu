# THPT Quang Trung — 30 năm kết nối (1996–2026)

This repository contains a reproducible, script-based slideshow renderer. It does not use InVideo or AI-generated replacements of people.

## Required source files

1. The original three-part photo archive at **`source/photos.zip`**. Keep the folder names for Phần I, Phần II and Phần III inside the ZIP.
2. All three original MP3s in `music/`. The renderer locates the songs by their Vietnamese titles:
   - Mong Ước Kỉ Niệm Xưa
   - Như Ngày Hôm Qua
   - Phép Màu

**The photo ZIP is not currently committed to this repository.** Upload it through GitHub: open `source/` (create the folder if needed) → **Add file → Upload files** → upload the ZIP as `photos.zip` → commit. The archive is about 58.5 MB, under GitHub's 100 MB single-file limit. The repository is public, so anyone can access committed photos and music; change repository visibility or use a private repository if needed.

## Render on GitHub

1. Commit `source/photos.zip` and confirm the three MP3s are present under `music/`.
2. Open **Actions → Render THPT Quang Trung anniversary video → Run workflow**.
3. Set the start offset for the selected section of *Phép Màu* if needed (default: 100 seconds).
4. After the workflow succeeds, download the artifact named `thpt-quang-trung-30-nam-mp4`.

Output: 8-minute MP4, 1920×1080, 30 fps, with Vietnamese text overlays and the three music sections in order.

## Local rendering

Requires Python 3.11+, FFmpeg, Pillow and MoviePy:

```bash
python -m pip install pillow moviepy
python scripts/build_video.py
```

The renderer writes `output/thpt-quang-trung-30-nam.mp4`. Source photos and music are not rewritten.

## Story structure

- 00:00–03:00 — *Mong Ước Kỉ Niệm Xưa*
- 03:00–05:30 — *Như Ngày Hôm Qua*
- 05:30–08:00 — *Phép Màu* (intended chorus section; configurable start offset)

Photo timing is distributed across each section. The final section uses the Part III portraits and supplied End image. Review the first render for photo order, text placement, and the exact chorus start before treating it as final.

## Privacy and copyright

Use only photos and audio you have permission to store and distribute. A public repository exposes its contents to everyone. Keep this repository private if any alumni do not consent to public distribution.
