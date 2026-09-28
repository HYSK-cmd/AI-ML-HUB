"""Render a Korean news-style briefing video for one day.

Usage:
  pip install edge-tts pillow imageio-ffmpeg gTTS
  python make_video.py data/2026-09-28.json   # -> videos/2026-09-28.mp4 (+ .jpg poster), sets "video" in the JSON
  python make_video.py --validate data/2026-09-28.json   # schema + corpus check only, exit 2 if invalid
  python make_video.py --check                # offline self-check of text helpers

Each narration sentence becomes one slide + one TTS clip (subtitle = the sentence being spoken).
Slides show the item's og:image as supporting material when the page has one.
"""
import asyncio
import io
import json
import re
import shutil
import subprocess
import sys
import tempfile
import urllib.request
from datetime import date
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

ROOT = Path(__file__).parent
W, H = 1280, 720
NAVY, NAVY2, WHITE, INK, GREY, ACCENT = "#0d1a2e", "#15294a", "#f7f7f5", "#0d1a2e", "#9aa7bd", "#e8590c"
LEVELS = ("beginner", "intermediate", "advanced")  # data values; display names come from the locale
LEVEL_COLOR = {"beginner": "#2f9e44", "intermediate": "#1971c2", "advanced": "#c2255c"}
VOICE = "ko-KR-SunHiNeural"
FONT_URL = "https://cdn.jsdelivr.net/npm/pretendard@1.3.9/dist/public/static/Pretendard-{}.otf"
UA = {"User-Agent": "Mozilla/5.0 (hub-video; +https://github.com/HYSK-cmd/hub)"}
LOCALE = json.loads((ROOT / "locales" / "ko.json").read_text(encoding="utf-8"))  # every on-screen/spoken string
V, LEVEL_NAME = LOCALE["video"], LOCALE["levels"]


def font(weight, size, _cache={}):
    path = ROOT / ".cache" / f"Pretendard-{weight}.otf"
    if not path.exists():
        path.parent.mkdir(exist_ok=True)
        path.write_bytes(urllib.request.urlopen(urllib.request.Request(FONT_URL.format(weight), headers=UA), timeout=60).read())
    if (weight, size) not in _cache:
        _cache[weight, size] = ImageFont.truetype(str(path), size)
    return _cache[weight, size]


def sentences(text):
    return [s.strip() for s in re.split(r"(?<=[.!?。])\s+", text or "") if s.strip()]


def wrap(draw, text, fnt, width, max_lines):
    lines, cur = [], ""
    for word in text.split():
        trial = f"{cur} {word}".strip()
        if draw.textlength(trial, font=fnt) <= width:
            cur = trial
            continue
        if cur:
            lines.append(cur)
        cur = word
        while draw.textlength(cur, font=fnt) > width:  # a single over-long token: hard-break it
            i = len(cur)
            while i > 1 and draw.textlength(cur[:i], font=fnt) > width:
                i -= 1
            lines.append(cur[:i])
            cur = cur[i:]
    if cur:
        lines.append(cur)
    if len(lines) > max_lines:
        lines = lines[:max_lines]
        while lines[-1] and draw.textlength(lines[-1] + "…", font=fnt) > width:
            lines[-1] = lines[-1][:-1]
        lines[-1] += "…"
    return lines


def og_image(url):
    """The page's og:image as a PIL image, or None. Skips logos and tiny images."""
    try:
        page = urllib.request.urlopen(urllib.request.Request(url, headers=UA), timeout=20).read(400_000).decode("utf-8", "replace")
        m = (re.search(r'<meta[^>]+property=["\']og:image["\'][^>]+content=["\']([^"\']+)', page)
             or re.search(r'<meta[^>]+content=["\']([^"\']+)["\'][^>]+property=["\']og:image["\']', page))
        if not m or "arxiv-logo" in m.group(1):
            return None
        img = Image.open(io.BytesIO(urllib.request.urlopen(urllib.request.Request(m.group(1).replace("&amp;", "&"), headers=UA), timeout=20).read()))
        return img.convert("RGB") if img.width >= 400 else None
    except Exception as e:  # material is optional; the slide works without it
        print(f"  og:image skip ({url}): {e}", file=sys.stderr)
        return None


def base(day_label):
    img = Image.new("RGB", (W, H), NAVY)
    d = ImageDraw.Draw(img)
    for y in range(H):  # vertical gradient
        t = y / H
        c = tuple(int(int(NAVY[i:i + 2], 16) * (1 - t) + int(NAVY2[i:i + 2], 16) * t) for i in (1, 3, 5))
        d.line([(0, y), (W, y)], fill=c)
    d.rectangle([0, 0, W, 56], fill="#0a1424")
    d.rectangle([32, 12, 208, 44], fill=ACCENT)
    d.text((120, 28), V["channel"], font=font("Bold", 20), fill=WHITE, anchor="mm")
    d.text((W - 32, 28), day_label, font=font("Medium", 18), fill=GREY, anchor="rm")
    return img, d


def subtitle(img, d, text):
    lines = wrap(d, text, font("SemiBold", 28), W - 200, 2)
    h = 20 + 42 * len(lines)
    overlay = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    ImageDraw.Draw(overlay).rounded_rectangle([80, H - 24 - h, W - 80, H - 24], 10, fill=(0, 0, 0, 170))
    img.paste(Image.alpha_composite(img.convert("RGBA"), overlay).convert("RGB"))
    for i, line in enumerate(lines):
        d.text((W // 2, H - 24 - h + 10 + 42 * i + 21), line, font=font("SemiBold", 28), fill=WHITE, anchor="mm")


def intro_slide(day, day_label, text):
    img, d = base(day_label)
    d.text((80, 120), V["intro_title"], font=font("Bold", 56), fill=WHITE)
    d.text((80, 196), day_label, font=font("Medium", 24), fill=GREY)
    for i, it in enumerate(day["items"]):
        y = 270 + i * 86
        lvl = it.get("level", "")
        d.rounded_rectangle([80, y, 160, y + 44], 6, fill=LEVEL_COLOR.get(lvl, ACCENT))
        d.text((120, y + 22), LEVEL_NAME.get(lvl, lvl), font=font("Bold", 22), fill=WHITE, anchor="mm")
        line = wrap(d, it.get("headline_ko") or it["title"], font("Bold", 30), W - 280, 1)[0]
        d.text((184, y + 22), line, font=font("Bold", 30), fill=WHITE, anchor="lm")
    subtitle(img, d, text)
    return img


def item_slide(it, day_label, text, material):
    img, d = base(day_label)
    lvl = it.get("level", "")
    top, box_w, box_h = 84, 620, 349  # material area, 16:9
    if material:
        m = material.copy()
        m.thumbnail((box_w, box_h))
        x0 = 64 + (box_w - m.width) // 2
        y0 = top + (box_h - m.height) // 2
        d.rounded_rectangle([60, top - 4, 64 + box_w + 4, top + box_h + 4], 8, fill="#223a63")
        img.paste(m, (x0, y0))
        tx = 64 + box_w + 44
    else:
        tx = 80
    tw = W - tx - 64
    d.text((tx, top), f"{it.get('source', '')}", font=font("Medium", 20), fill=GREY)
    y = top + 40
    for line in wrap(d, it["title"], font("SemiBold", 26), tw, 4):
        d.text((tx, y), line, font=font("SemiBold", 26), fill=WHITE)
        y += 36
    y += 18
    d.text((tx, y), V["keywords"], font=font("Bold", 20), fill=ACCENT)
    y += 34
    for kw in (it.get("keywords") or [])[:4]:
        d.text((tx, y), f"· {kw}", font=font("Medium", 22), fill="#d7deea")
        y += 32
    # lower third: level tab + Korean headline bar
    ly = 452
    d.rectangle([60, ly, 164, ly + 64], fill=LEVEL_COLOR.get(lvl, ACCENT))
    d.text((112, ly + 32), LEVEL_NAME.get(lvl, lvl), font=font("Bold", 28), fill=WHITE, anchor="mm")
    d.rectangle([164, ly, W - 60, ly + 64], fill=WHITE)
    head = wrap(d, it.get("headline_ko") or it["title"], font("Bold", 32), W - 60 - 164 - 40, 1)[0]
    d.text((188, ly + 32), head, font=font("Bold", 32), fill=INK, anchor="lm")
    d.rectangle([60, ly + 64, W - 60, ly + 70], fill=ACCENT)
    subtitle(img, d, text)
    return img


async def edge(text, path):
    import edge_tts
    await edge_tts.Communicate(text, VOICE, rate="+8%").save(str(path))


def tts(text, path):
    try:
        asyncio.run(edge(text, path))
    except Exception as e:  # edge-tts is an unofficial endpoint; fall back rather than lose the video
        print(f"  edge-tts failed ({e}), using gTTS", file=sys.stderr)
        from gtts import gTTS
        gTTS(text, lang="ko").save(str(path))


def ffmpeg_bin():
    found = shutil.which("ffmpeg")
    if found:
        return found
    import imageio_ffmpeg
    return imageio_ffmpeg.get_ffmpeg_exe()


def duration(ff, path):
    err = subprocess.run([ff, "-i", str(path)], capture_output=True, text=True).stderr
    h, m, s = re.search(r"Duration: (\d+):(\d+):([\d.]+)", err).groups()
    return int(h) * 3600 + int(m) * 60 + float(s)


CATS = {"LLM", "Agents", "Multimodal & Vision", "Robotics & Embodied", "RL", "ML Systems & Infra",
        "Research Fundamentals", "Open Source & Tools", "Industry & Policy"}
FIELDS = ("title", "url", "source", "categories", "summary", "why", "level", "keywords", "headline_ko", "narration")


def validate(day_path):
    """Problems with a day file, [] if it is publishable."""
    from collect import corpus, keys
    day = json.loads(Path(day_path).read_text(encoding="utf-8"))
    errs = []
    items = day.get("items", [])
    if not day.get("date") or not day.get("headline"):
        errs.append("missing date/headline")
    if [i.get("level") for i in items] != list(LEVELS):
        errs.append(f"need exactly 3 items ordered {', '.join(LEVELS)}; got {[i.get('level') for i in items]}")
    openers = {o.format(level=name) for o in V["item_openers"] for name in LEVEL_NAME.values()}
    for n, it in enumerate(items):
        if sentences(it.get("narration"))[:1] and sentences(it.get("narration"))[0] in openers:
            errs.append(f"item {n}: narration starts with the item opener; drop it, the video adds it")
    published = corpus(exclude=day_path)
    for n, it in enumerate(items):
        errs += [f"item {n}: missing {f}" for f in FIELDS if not it.get(f)]
        if not str(it.get("url", "")).startswith("http"):
            errs.append(f"item {n}: url must be http(s)")
        if bad := set(it.get("categories", [])) - CATS:
            errs.append(f"item {n}: unknown categories {bad}")
        if keys(it.get("url"), it.get("title")) & published:
            errs.append(f"item {n}: already published before ({it.get('url')})")
    if "—" in json.dumps(day, ensure_ascii=False):
        errs.append("contains an em-dash; rewrite with a period, comma or colon")
    return errs


def render(day_path):
    day_path = Path(day_path)
    if errs := validate(day_path):
        sys.exit("invalid day file:\n  " + "\n  ".join(errs))
    day = json.loads(day_path.read_text(encoding="utf-8"))
    dt = date.fromisoformat(day["date"])
    day_label = f"{dt.year}.{dt.month:02d}.{dt.day:02d} ({V['weekdays'][dt.weekday()]})"
    spoken_date = V["spoken_date"].format(month=dt.month, day=dt.day)
    ff = ffmpeg_bin()

    slides = [(intro_slide, (day, day_label), V["intro"].format(date=spoken_date, headline=day.get("headline", "")))]
    for n, it in enumerate(day["items"]):
        material = og_image(it["url"])
        opener = V["item_openers"][n].format(level=LEVEL_NAME.get(it["level"], it["level"]))
        for s in [opener] + sentences(it.get("narration") or it.get("summary")):
            slides.append((item_slide, (it, day_label), s, material))
    slides.append((intro_slide, (day, day_label), V["outro"]))

    out = ROOT / "videos" / f"{day['date']}.mp4"
    out.parent.mkdir(exist_ok=True)
    with tempfile.TemporaryDirectory() as tmp:
        tmp = Path(tmp)
        segs = []
        for n, (fn, args, text, *rest) in enumerate(slides):
            frame = fn(*args, text, *rest)
            if n == 0:
                frame.save(out.with_suffix(".jpg"), quality=85)  # poster for the <video> tag
            frame.save(tmp / f"{n}.png")
            tts(text, tmp / f"{n}.mp3")
            dur = duration(ff, tmp / f"{n}.mp3") + 0.35
            seg = tmp / f"{n}.mp4"
            subprocess.run([ff, "-y", "-loglevel", "error", "-loop", "1", "-framerate", "10", "-i", str(tmp / f"{n}.png"),
                            "-i", str(tmp / f"{n}.mp3"), "-af", "apad", "-t", f"{dur:.2f}",
                            "-c:v", "libx264", "-preset", "veryfast", "-tune", "stillimage", "-pix_fmt", "yuv420p", "-r", "10",
                            "-c:a", "aac", "-b:a", "96k", "-ar", "44100", "-ac", "1", str(seg)], check=True)
            segs.append(seg)
            print(f"  slide {n + 1}/{len(slides)} {dur:.1f}s", file=sys.stderr)
        (tmp / "list.txt").write_text("".join(f"file '{s.as_posix()}'\n" for s in segs), encoding="utf-8")
        subprocess.run([ff, "-y", "-loglevel", "error", "-f", "concat", "-safe", "0", "-i", str(tmp / "list.txt"),
                        "-c", "copy", "-movflags", "+faststart", str(out)], check=True)

    day["video"] = f"videos/{day['date']}.mp4"
    day_path.write_text(json.dumps(day, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    print(f"OK {out} ({out.stat().st_size / 1e6:.1f} MB, {duration(ff, out):.0f}s)", file=sys.stderr)


def check():
    assert sentences("First one. Second! Third?") == ["First one.", "Second!", "Third?"]
    assert all(k in LEVEL_NAME for k in LEVELS) and len(V["item_openers"]) == len(LEVELS)
    d = ImageDraw.Draw(Image.new("RGB", (10, 10)))
    f = ImageFont.load_default()
    lines = wrap(d, "a " * 200 + "x" * 300, f, 200, 3)
    assert len(lines) == 3 and lines[-1].endswith("…") and all(d.textlength(l, font=f) <= 200 + d.textlength("…", font=f) for l in lines)
    print("OK", file=sys.stderr)


if __name__ == "__main__":
    if sys.argv[1:] == ["--check"]:
        check()
    elif sys.argv[1] == "--validate":
        errs = validate(sys.argv[2])
        print("\n".join(errs) or "OK", file=sys.stderr)
        sys.exit(2 if errs else 0)
    else:
        render(sys.argv[1])
