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
from moviepy import ImageClip, AudioFileClip, concatenate_videoclips, CompositeAudioClip

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
    for candidate in (ROOT / "photos", SOURCE / "photos", ROOT / "Ảnh"):
        if candidate.exists():
            return candidate
    raise FileNotFoundError("Upload the original photo ZIP to source/photos.zip first.")

def part_photos(root, part):
    keys = [f"phần {part}", f"phan {part}", f"part {part}"]
    files = [p for p in root.rglob("*") if p.is_file() and p.suffix.lower() in {".jpg",".jpeg",".png",".webp"}]
    def score(p):
        s = str(p).casefold().replace("_"," ").replace("-"," ")
        return any(k in s for k in keys)
    result = [p for p in files if score(p)]
    if not result:
        # Common zip folder names may be nested under a wrapper directory.
        for p in root.rglob("*"):
            if p.is_dir() and p.name.casefold().replace("_"," ").startswith(("phần "+part, "phan "+part)):
                result.extend(x for x in p.iterdir() if x.suffix.lower() in {".jpg",".jpeg",".png",".webp"})
    # Keep stable human-friendly order, including names such as 1.5.7.jpg.
    def natural(p):
        return [int(x) if x.isdigit() else x.casefold() for x in re.split(r"(\d+)", p.name)]
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
    end_images = [p for p in p3 if p.stem.casefold() == "end"]
    portraits = [p for p in p3 if p.stem.casefold() != "end"]
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
        per_photo = (end-start)/len(photos)
        for i, photo in enumerate(photos):
            t = start + i*per_photo
            overlay = next((txt for a,b,txt in TEXTS if a <= t < b), None)
            card_path = WORK / "cards" / f"{part_index+1:02d}-{i:03d}.jpg"
            make_card(photo, card_path, overlay=overlay, final=(part_index==2 and photo in end_images))
            clip = ImageClip(str(card_path)).with_duration(per_photo)
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
