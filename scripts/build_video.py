#!/usr/bin/env python3
"""Render the THPT Quang Trung 30th-anniversary slideshow (1920x1080, 30fps).

Expected inputs:
  source/photos.zip (three folders: Phần I, Phần II, Phần III)
  music/*.mp3 (the three source songs)
Output: output/thpt-quang-trung-30-nam.mp4
"""
from __future__ import annotations
import os, re, shutil, subprocess, zipfile
from pathlib import Path
from PIL import Image, ImageDraw, ImageFont, ImageOps
import numpy as np
import librosa
from moviepy import ImageClip, VideoClip, AudioFileClip, concatenate_videoclips, CompositeAudioClip

ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "source"
MUSIC = ROOT / "music"
WORK = ROOT / "build" / "render"
OUT = ROOT / "output" / "thpt-quang-trung-30-nam.mp4"
W, H, FPS = 1920, 1080, 30
DURATION = 480
PARTS = [(0, 180, "I"), (180, 330, "II"), (330, 480, "III")]
TEXTS = [
    (4, 12, "Có một thời, chúng ta đã cùng nhau lớn lên…"),
    (35, 43, "Một mái trường. Những người bạn. Một thời thanh xuân."),
    (82, 91, "Ngày ấy, chúng ta đâu biết những điều bình dị sẽ trở thành ký ức quý giá đến nhường nào."),
    (190, 199, "Vậy mà, gặp lại nhau… cứ ngỡ như ngày hôm qua."),
    (240, 249, "Mỗi người một hành trình. Nhưng vẫn chung một miền ký ức."),
    (300, 309, "30 năm – một chặng đường, biết bao điều còn đọng lại."),
    (337, 346, "Cảm ơn vì đã từng cùng nhau đi qua những năm tháng ấy."),
    (458, 480, "THPT QUANG TRUNG · 30 NĂM KẾT NỐI · MÃI MỘT THANH XUÂN"),
]

def run(cmd):
    subprocess.run(cmd, check=True)

def find_music(patterns):
    files = list(MUSIC.glob("*.mp3"))
    for pattern in patterns:
        for f in files:
            if pattern.casefold() in f.stem.casefold():
                return f
    raise FileNotFoundError(f"Missing music matching {patterns}. Found: {[p.name for p in files]}")

def extract_photos():
    archive = SOURCE / "photos.zip"
    if archive.exists():
        target = WORK / "photos"
        target.mkdir(parents=True, exist_ok=True)
        with zipfile.ZipFile(archive) as z:
            z.extractall(target)
        return target
    # GitHub upload may contain the extracted images directly in source/ rather than a ZIP.
    image_files = [p for p in SOURCE.iterdir() if p.is_file() and p.suffix.lower() in {".jpg", ".jpeg", ".png", ".webp"}]
    if image_files:
        return SOURCE
    for candidate in (ROOT / "photos", SOURCE / "photos", ROOT / "Ảnh"):
        if candidate.exists():
            return candidate
    raise FileNotFoundError("No photo ZIP or image files found in source/.")

def natural(p):
    return [int(x) if x.isdigit() else x.casefold() for x in re.split(r"(\d+)", p.name)]

def part_photos(root, part):
    keys = [f"phần {part}", f"phan {part}", f"part {part}"]
    files = [p for p in root.rglob("*") if p.is_file() and p.suffix.lower() in {".jpg",".jpeg",".png",".webp"}]
    def score(p):
        s = str(p).casefold().replace("_"," ").replace("-"," ")
        return any(k in s for k in keys)
    result = [p for p in files if score(p)]
    # Support the common GitHub upload pattern where all images are placed flat in source/.
    if not result and root.resolve() == SOURCE.resolve():
        return sorted(files, key=natural)
    if not result:
        # Common zip folder names may be nested under a wrapper directory.
        for p in root.rglob("*"):
            if p.is_dir() and p.name.casefold().replace("_"," ").startswith(("phần "+part, "phan "+part)):
                result.extend(x for x in p.iterdir() if x.suffix.lower() in {".jpg",".jpeg",".png",".webp"})
    # Keep stable human-friendly order, including names such as 1.5.7.jpg.
    return sorted(set(result), key=natural)

def font(size):
    candidates = [
        "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
        "/usr/share/fonts/truetype/liberation2/LiberationSans-Regular.ttf",
    ]
    for p in candidates:
        if Path(p).exists():
            return ImageFont.truetype(p, size)
    return ImageFont.load_default()

def rhythm_cut_points(song, audio_start, section_duration, photo_count):
    """Choose photo changes near musical beats, with a gentle 4–7s target cadence."""
    if photo_count <= 1:
        return [0.0, section_duration]
    # Estimate beats only within the selected music segment.
    y, sr = librosa.load(str(song), sr=22050, mono=True, offset=audio_start, duration=section_duration)
    tempo, beat_frames = librosa.beat.beat_track(y=y, sr=sr, units="frames")
    beat_times = librosa.frames_to_time(beat_frames, sr=sr)
    beat_times = [float(t) for t in beat_times if 0.4 <= t < section_duration - 0.4]
    # Aim for a calm, readable cadence, then snap each ideal cut to the nearest beat.
    ideal = [i * section_duration / photo_count for i in range(photo_count + 1)]
    cuts = [0.0]
    for target in ideal[1:-1]:
        nearby = [t for t in beat_times if cuts[-1] + 2.6 <= t <= min(section_duration - 2.6, target + 1.5) and abs(t-target) <= 1.8]
        candidate = min(nearby, key=lambda t: abs(t-target)) if nearby else target
        # Avoid tiny or excessively long holds if the beat tracker is noisy.
        candidate = max(cuts[-1] + 2.6, min(candidate, section_duration - 2.6))
        cuts.append(candidate)
    cuts.append(float(section_duration))
    # Ensure strict ordering even if a sparse beat track repeats a nearby point.
    for i in range(1, len(cuts)-1):
        cuts[i] = max(cuts[i], cuts[i-1] + 2.6)
    for i in range(len(cuts)-2, 0, -1):
        cuts[i] = min(cuts[i], cuts[i+1] - 2.6)
    return cuts

def make_card(path, out_path, overlay=None, final=False):
    with Image.open(path) as im:
        im = ImageOps.exif_transpose(im).convert("RGB")
        # Cover canvas without distorting faces; crop only excess edges.
        im = ImageOps.fit(im, (W,H), method=Image.Resampling.LANCZOS, centering=(0.5,0.5))
    draw = ImageDraw.Draw(im, "RGBA")
    if overlay:
        f = font(44 if len(overlay) < 65 else 36)
        max_width = 1540
        words, lines, current = overlay.split(), [], ""
        for word in words:
            test = (current + " " + word).strip()
            if draw.textbbox((0,0), test, font=f)[2] <= max_width:
                current = test
            else:
                if current: lines.append(current)
                current = word
        if current: lines.append(current)
        line_h = 58
        box_h = len(lines)*line_h + 48
        y = H - box_h - 65
        draw.rounded_rectangle((110,y,W-110,H-65), radius=24, fill=(10,18,20,165))
        for i,line in enumerate(lines):
            bbox = draw.textbbox((0,0), line, font=f, stroke_width=0)
            x = (W-(bbox[2]-bbox[0]))//2
            draw.text((x,y+22+i*line_h), line, font=f, fill=(255,250,235,255))
    if final:
        f = font(34)
        label = "1996 — 2026"
        bbox = draw.textbbox((0,0),label,font=f)
        draw.text(((W-(bbox[2]-bbox[0]))//2, 70),label,font=f,fill=(255,250,235,230))
    out_path.parent.mkdir(parents=True, exist_ok=True)
    im.save(out_path, quality=92)


def make_mosaic_board(photos, out_path):
    """Create one high-resolution board containing every individual portrait."""
    if not photos:
        raise RuntimeError("No individual portraits found for the Part III mosaic.")
    board_w, board_h = W * 2, H * 2
    cols = 8
    rows = (len(photos) + cols - 1) // cols
    gap, margin_x, margin_y = 12, 44, 54
    tile_w = (board_w - 2 * margin_x - (cols - 1) * gap) // cols
    tile_h = (board_h - 2 * margin_y - (rows - 1) * gap) // rows
    board = Image.new("RGB", (board_w, board_h), (242, 237, 224))
    draw = ImageDraw.Draw(board)
    label_font = font(22)
    for index, path in enumerate(photos):
        row, col = divmod(index, cols)
        x = margin_x + col * (tile_w + gap)
        y = margin_y + row * (tile_h + gap)
        draw.rounded_rectangle(
            (x, y, x + tile_w, y + tile_h), radius=16,
            fill=(255, 253, 247), outline=(218, 208, 188), width=2
        )
        with Image.open(path) as original:
            portrait = ImageOps.exif_transpose(original).convert("RGB")
            # Contain preserves the whole original portrait and avoids face cropping.
            portrait.thumbnail((tile_w - 28, tile_h - 78), Image.Resampling.LANCZOS)
            px = x + (tile_w - portrait.width) // 2
            py = y + 8 + (tile_h - 70 - portrait.height) // 2
            board.paste(portrait, (px, py))
        label = path.stem
        bounds = draw.textbbox((0, 0), label, font=label_font)
        max_width = tile_w - 20
        if bounds[2] - bounds[0] > max_width:
            while label and draw.textbbox((0, 0), label + "…", font=label_font)[2] > max_width:
                label = label[:-1]
            label = label + "…"
        bounds = draw.textbbox((0, 0), label, font=label_font)
        label_w = bounds[2] - bounds[0]
        draw.text((x + (tile_w - label_w) // 2, y + tile_h - 56),
                  label, font=label_font, fill=(54, 67, 61))
    out_path.parent.mkdir(parents=True, exist_ok=True)
    board.save(out_path, quality=94)
    return out_path


def mosaic_frame_function(board_path, duration):
    """Return a MoviePy frame callback that gently explores, then reveals the full board."""
    board = Image.open(board_path).convert("RGB")
    board_w, board_h = board.size
    # Begin wide, explore several areas with a restrained zoom, then pull back and hold.
    keyframes = [
        (0.0, 1.0, 0.50, 0.50),
        (12.0, 1.48, 0.36, 0.34),
        (40.0, 1.48, 0.64, 0.36),
        (68.0, 1.48, 0.64, 0.64),
        (94.0, 1.48, 0.36, 0.64),
        (112.0, 1.0, 0.50, 0.50),
        (duration, 1.0, 0.50, 0.50),
    ]

    def frame(t):
        t = max(0.0, min(float(t), duration))
        for idx in range(len(keyframes) - 1):
            a, b = keyframes[idx], keyframes[idx + 1]
            if a[0] <= t <= b[0]:
                progress = (t - a[0]) / max(b[0] - a[0], 1e-6)
                progress = progress * progress * (3 - 2 * progress)
                scale = a[1] + (b[1] - a[1]) * progress
                cx = a[2] + (b[2] - a[2]) * progress
                cy = a[3] + (b[3] - a[3]) * progress
                break
        else:
            _, scale, cx, cy = keyframes[-1]
        view_w = max(1, int(board_w / scale))
        view_h = max(1, int(board_h / scale))
        center_x = min(max(cx * board_w, view_w / 2), board_w - view_w / 2)
        center_y = min(max(cy * board_h, view_h / 2), board_h - view_h / 2)
        left = int(center_x - view_w / 2)
        top = int(center_y - view_h / 2)
        shot = board.crop((left, top, left + view_w, top + view_h))
        shot = shot.resize((W, H), Image.Resampling.LANCZOS)
        absolute_t = 330 + t
        caption = next((txt for start, end, txt in TEXTS if start <= absolute_t < end), None)
        if caption:
            draw = ImageDraw.Draw(shot, "RGBA")
            f = font(44 if len(caption) < 65 else 36)
            box = draw.textbbox((0, 0), caption, font=f)
            text_w = box[2] - box[0]
            x = (W - text_w) // 2
            y = H - 150
            draw.rounded_rectangle((x - 32, y - 18, x + text_w + 32, y + 62),
                                   radius=18, fill=(10, 18, 20, 165))
            draw.text((x, y), caption, font=f, fill=(255, 250, 235, 255))
        return np.asarray(shot)

    return frame

def main():
    WORK.mkdir(parents=True, exist_ok=True)
    photo_root = extract_photos()
    p1, p2, p3 = (part_photos(photo_root, p) for p in ("I","II","III"))
    if not p1 or not p2 or not p3:
        raise RuntimeError(f"Could not identify all three photo folders: I={len(p1)}, II={len(p2)}, III={len(p3)}. Check the ZIP folder names.")
    # Curated selections: use only chosen school-day and reunion photos.
    # Part III deliberately keeps the commemorative portrait set and End image.
    def choose(folder, names, label):
        by_name = {p.name.casefold(): p for p in folder}
        selected = []
        missing = []
        for name in names:
            match = by_name.get(name.casefold())
            if match:
                selected.append(match)
            else:
                missing.append(name)
        if missing:
            raise RuntimeError(f"Curated {label} photos not found: {missing}. Check original archive filenames.")
        return selected

    selected_p1 = choose(p1, [
        "60.jpg", "61.jpg", "37.jpg", "1.5.7.jpg", "1.5.1.jpg",
        "1.7.1.jpg", "1.9.jpg", "1.3.jpg", "38.jpg", "22.jpg",
        "14.jpg", "42.jpg", "47.jpg",
    ], "Part I")
    selected_p2 = choose(p2, [
        "2.50.jpg", "2.47.jpg", "2.49.jpg", "2.48.jpg",
        "2.28.jpg", "2.45.jpg", "2.21.jpg", "2.20.jpg",
        "2.46.jpg", "2.6.jpg", "2.5.jpg",
    ], "Part II")

    # Use the curated sequence first, then the remaining archive photos to avoid
    # long holds. In flat GitHub uploads, infer the original folders from filenames.
    image_exts = {".jpg", ".jpeg", ".png", ".webp"}
    if photo_root.resolve() == SOURCE.resolve():
        part1_extra = [
            p for p in p1
            if p.suffix.lower() in image_exts
            and re.match(r"^(?:\d+|1(?:\.\d+)+)$", p.stem)
            and not p.stem.startswith("2.")
            and p not in selected_p1
        ]
        part2_extra = [
            p for p in p2
            if p.suffix.lower() in image_exts
            and re.match(r"^2\.\d+(?:\.\d+)*$", p.stem)
            and p not in selected_p2
        ]
    else:
        part1_extra = [p for p in p1 if p not in selected_p1]
        part2_extra = [p for p in p2 if p not in selected_p2]
    selected_p1 = selected_p1 + sorted(part1_extra, key=natural)
    selected_p2 = selected_p2 + sorted(part2_extra, key=natural)

    end_images = [p for p in p3 if p.stem.casefold() == "end"]
    # In a flat upload, named portrait files belong to Part III; numbered files belong to Parts I/II.
    portraits = [p for p in p3 if p.stem.casefold() != "end" and not re.match(r"^\d+(?:\.\d+)*$", p.stem)]
    song1 = find_music(["mong ước", "mong uoc", "mong-ước", "mong-uoc", "mong"])
    song2 = find_music(["như ngày hôm qua", "nhu ngay hom qua", "như-ngày", "nhu-ngay"])
    song3 = find_music(["phép màu", "phep mau"])
    pools = [selected_p1, selected_p2, portraits + end_images]
    section_specs = [
        (0, 180, song1, pools[0], 0, 180),
        (180, 330, song2, pools[1], 0, 150),
        # The intended chorus start can be overridden with PHEP_MAU_START.
        (330, 480, song3, pools[2], float(os.getenv("PHEP_MAU_START","100")), 150),
    ]
    clips, audio_clips = [], []
    for part_index, (start, end, song, photos, audio_start, span) in enumerate(section_specs):
        if not photos:
            raise RuntimeError(f"No photos found for part {part_index+1}")
        if part_index == 2:
            # Part III: one simultaneous portrait mosaic, camera exploration, then
            # a full-board pullback. Keep End.png as the final 22-second closing card.
            board_path = make_mosaic_board(portraits, WORK / "cards" / "03-portrait-mosaic.jpg")
            board_duration = (end - start) - 22
            clips.append(VideoClip(
                frame_function=mosaic_frame_function(board_path, board_duration),
                duration=board_duration,
            ).with_duration(board_duration))
            if not end_images:
                raise RuntimeError("Part III requires the original End.png closing image.")
            closing_start = start + board_duration
            closing_caption = next((txt for a, b, txt in TEXTS if a <= closing_start < b), None)
            closing_path = WORK / "cards" / "03-closing-card.jpg"
            make_card(end_images[0], closing_path, overlay=closing_caption, final=True)
            clips.append(ImageClip(str(closing_path)).with_duration(22))
        else:
            cut_points = rhythm_cut_points(song, audio_start, end-start, len(photos))
            for i, photo in enumerate(photos):
                photo_duration = cut_points[i+1] - cut_points[i]
                t = start + cut_points[i]
                overlay = next((txt for a,b,txt in TEXTS if a <= t < b), None)
                card_path = WORK / "cards" / f"{part_index+1:02d}-{i:03d}.jpg"
                make_card(photo, card_path, overlay=overlay)
                clip = ImageClip(str(card_path))
                # A restrained Ken Burns move on every third photo adds life without
                # making the whole montage feel restless. Crop back to the 16:9 canvas.
                if i % 3 == 1:
                    clip = clip.resized(
                        lambda t, d=photo_duration: 1.0 + 0.025 * min(t / max(d, 0.1), 1.0)
                    ).cropped(width=W, height=H)
                clip = clip.with_duration(photo_duration)
                clips.append(clip)
        source_audio = AudioFileClip(str(song))
        audio_end = min(audio_start + span, source_audio.duration)
        if audio_end <= audio_start:
            raise RuntimeError(f"Audio start {audio_start}s is beyond the end of {song.name}")
        audio_clips.append(source_audio.subclipped(audio_start, audio_end).with_start(start))
    video = concatenate_videoclips(clips, method="compose")
    # Normalize audio durations to the exact 8-minute timeline; keep the music order.
    audio = CompositeAudioClip(audio_clips).with_duration(DURATION)
    video = video.with_duration(DURATION).with_audio(audio)
    OUT.parent.mkdir(parents=True, exist_ok=True)
    video.write_videofile(str(OUT), fps=FPS, codec="libx264", audio_codec="aac", bitrate="8000k", preset="medium", threads=4)
    video.close()
    audio.close()
    for audio_clip in audio_clips:
        audio_clip.close()
    print(f"Rendered: {OUT} ({DURATION}s, {W}x{H}, {FPS}fps)")

if __name__ == "__main__":
    main()
