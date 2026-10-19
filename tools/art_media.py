"""AVIF/WebP renditions of the AI art (owner decision 2026-10-13, CLAUDE.md 4; pipeline/art.py).

    python tools/art_media.py              # encode what is missing for every picture in data/incheon/art.json
    python tools/art_media.py --dry-run    # list what would be made, change nothing
    python tools/art_media.py --force      # re-encode every picture whose original is on this computer

Originals: incoming/ai-images/<file> (git-ignored — the operator saves the ChatGPT output there under its ID).
A picture whose original is not on this computer keeps its committed renditions as they are.
Output: templates/assets/art/<ID>-<width>.avif|webp (og-*: <ID>-1200.jpg) and manifest.json {ID: {"w", "h" (the
rendition's frame, after a crop), "avif": [[name, width, bytes], …], "webp": […] | "jpg": […], qualities}}.
pipeline/art.py reads it; the build publishes only the files a page uses. Renditions of a picture that left art.json
(held, removed) are deleted.
Crops (by ID prefix): bands 1536:640 from the centre — head-* list header bands, theme-* theme pages, vtopic-* video
topic pages, course-* course pages, area-* the map's 권역 (their subject sits in the middle band of the drawing);
og-* link previews (og-ko, og-en, og-ja …) 1200:630 cut 37% of the way down (their titles sit high: the frame keeps
them inside the middle 70% a messenger preview shows safely), one 1200×630 JPEG.
Widths: landscape 640·1280·1920, square 400·800 — never wider than the original (a 1536 px original gives
640·1280·1536). Pictures a phone shows at its width — the bands above (in the first screen but area-*), camp-* and
en-camp-* guide cards, about-* the about head — get 400·800·1280·1920 instead, so a phone downloads a file the size
of its screen (a 358 px band: 400w at 1x, 800w at 2x) and a first-screen picture takes as little as possible of the
bandwidth the first paint needs on a slow connection. Budget: the 1280w AVIF of a hero-* picture (the home's first screen) is at most 150,000 bytes; its
AVIF quality steps down from 60 until it fits, and every AVIF width of that picture uses the same quality.
Deterministic: the picture is flattened to RGB (ChatGPT's resized squares carry a 1px semi-transparent edge), no
metadata is written, the AVIF encoder runs single-threaded with fixed settings — the same original gives the same
bytes. Needs Pillow >= 11.3 with AVIF (pip install "pillow>=11.3"); the build itself does not.
"""
from __future__ import annotations

import argparse
import io
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from pipeline import art  # noqa: E402

SRC_DIR = ROOT / "incoming" / "ai-images"
WIDTHS = {"landscape": (640, 1280, 1920), "square": (400, 800)}
BANDS = ("head-", "theme-", "vtopic-", "course-", "area-")   # ID prefixes of the 2.4:1 bands
# ID prefixes a phone shows at its width (most in its first screen), and their widths
SMALL_FIRST = ((*BANDS, "camp-", "en-camp-", "about-"), (400, 800, 1280, 1920))
AVIF_QUALITY, AVIF_MIN_QUALITY, AVIF_STEP, AVIF_SPEED = 60, 32, 4, 4
WEBP_QUALITY = 78
HERO_BUDGET = ("hero-", 1280, 150_000)   # ID prefix, width, bytes: the AVIF a first screen loads
CROPS = {p: (1536, 640) for p in BANDS}  # ID prefix -> frame (aspect) cut from the centre before resizing
OG = ("og-", 1200, 630, 82, 0.37)        # ID prefix, width, height, JPEG quality, vertical anchor: link previews
FORMATS = ("avif", "webp", "jpg")


def entry_files(entry: dict) -> list[str]:
    return [name for fmt in FORMATS for name, _, _ in entry.get(fmt) or []]


def centre_crop(im, w: int, h: int, y_anchor: float = 0.5):
    """The largest w:h frame of the picture, centred across; down the picture at y_anchor (0 top, .5 centre)."""
    if im.width * h > im.height * w:                    # wider than w:h: trim the sides
        cw = round(im.height * w / h)
        x = (im.width - cw) // 2
        return im.crop((x, 0, x + cw, im.height))
    ch = round(im.width * h / w)                         # taller: trim top and bottom
    y = round((im.height - ch) * y_anchor)
    return im.crop((0, y, im.width, y + ch))


def widths_for(w: int, h: int, art_id: str = "") -> list[int]:
    """The rendition widths of a w×h original: the wanted ones that fit, plus the original width when a wanted
    width is wider than the original (nothing is upscaled)."""
    prefixes, small_first = SMALL_FIRST
    wanted = small_first if art_id.startswith(prefixes) else WIDTHS["square" if w == h else "landscape"]
    out = [x for x in wanted if x <= w]
    if any(x > w for x in wanted) and w not in out:
        out.append(w)
    return out


def encode(im, width: int, fmt: str, quality: int) -> bytes:
    from PIL import Image
    frame = im if width == im.width else im.resize((width, round(im.height * width / im.width)), Image.LANCZOS)
    buf = io.BytesIO()
    if fmt == "avif":
        frame.save(buf, "AVIF", quality=quality, speed=AVIF_SPEED, subsampling="4:2:0", max_threads=1)
    else:
        frame.save(buf, "WEBP", quality=quality, method=6)
    return buf.getvalue()


def renditions(art_id: str, path: Path) -> tuple[dict, dict]:
    """(manifest entry, {file name: bytes}) for one original."""
    from PIL import Image
    with Image.open(path) as src:
        im = src.convert("RGB")
    prefix, ow, oh, oq, anchor = OG
    if art_id.startswith(prefix):
        frame = centre_crop(im, ow, oh, anchor).resize((ow, oh), Image.LANCZOS)
        buf = io.BytesIO()
        frame.save(buf, "JPEG", quality=oq, optimize=True, progressive=True)
        name = f"{art_id}-{ow}.jpg"
        return {"w": ow, "h": oh, "jpg_quality": oq, "jpg": [[name, ow, len(buf.getvalue())]]}, {name: buf.getvalue()}
    for crop_prefix, (cw, ch) in CROPS.items():
        if art_id.startswith(crop_prefix):
            im = centre_crop(im, cw, ch)
    widths = widths_for(im.width, im.height, art_id)
    quality, cache = AVIF_QUALITY, {}
    prefix, budget_w, budget = HERO_BUDGET
    if art_id.startswith(prefix) and budget_w in widths:
        while True:
            cache[(budget_w, quality)] = encode(im, budget_w, "avif", quality)
            if len(cache[(budget_w, quality)]) <= budget or quality - AVIF_STEP < AVIF_MIN_QUALITY:
                break
            quality -= AVIF_STEP
    entry = {"w": im.width, "h": im.height, "avif_quality": quality, "webp_quality": WEBP_QUALITY,
             "avif": [], "webp": []}
    files = {}
    for fmt, q in (("avif", quality), ("webp", WEBP_QUALITY)):
        for w in widths:
            data = cache.get((w, q)) if fmt == "avif" else None
            data = data or encode(im, w, fmt, q)
            name = f"{art_id}-{w}.{fmt}"
            files[name] = data
            entry[fmt].append([name, w, len(data)])
    return entry, files


def over_budget(art_id: str, entry: dict) -> int | None:
    prefix, budget_w, budget = HERO_BUDGET
    if not art_id.startswith(prefix):
        return None
    size = next((b for _, w, b in entry.get("avif") or [] if w == budget_w), None)
    return size if size is not None and size > budget else None


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--data", type=Path, default=ROOT / "data" / "incheon")
    ap.add_argument("--src", type=Path, default=SRC_DIR, help="where the originals are (git-ignored)")
    ap.add_argument("--out", type=Path, default=art.ART_DIR)
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--force", action="store_true", help="re-encode renditions that already exist")
    a = ap.parse_args(argv)

    pictures = art.load(a.data)["images"]
    old = art.load_manifest(a.out)
    manifest, rows, missing = {}, [], []
    for art_id, meta in pictures.items():
        src = a.src / Path(str(meta.get("file") or f"{art_id}.png")).name
        prev = old.get(art_id)
        complete = bool(prev) and all((a.out / n).is_file() for n in entry_files(prev))
        if complete and not a.force:
            manifest[art_id] = prev
            rows.append((art_id, "그대로", prev))
            continue
        if not src.is_file():
            if prev:
                manifest[art_id] = prev
            missing.append(art_id)
            continue
        if a.dry_run:
            rows.append((art_id, "만들 예정", prev or {}))
            if prev:
                manifest[art_id] = prev
            continue
        entry, files = renditions(art_id, src)
        a.out.mkdir(parents=True, exist_ok=True)
        for name, blob in files.items():
            (a.out / name).write_bytes(blob)
        manifest[art_id] = entry
        rows.append((art_id, "만듦", entry))

    keep = {n for e in manifest.values() for n in entry_files(e)}
    stale = sorted(f for f in a.out.glob("*") if f.suffix in (".avif", ".webp", ".jpg") and f.name not in keep) \
        if a.out.is_dir() else []
    if not a.dry_run:
        for f in stale:
            f.unlink()
        if manifest or (a.out / "manifest.json").exists():
            a.out.mkdir(parents=True, exist_ok=True)
            (a.out / "manifest.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=1) + "\n", "utf-8")

    print("ID | 상태 | 틀 | AVIF 폭:바이트 (품질) | WebP 폭:바이트 (품질) | JPEG")
    for art_id, state, e in rows:
        fmt_files = lambda fmt: ", ".join(f"{w}:{b:,}" for _, w, b in e.get(fmt) or [])
        print(f"{art_id} | {state} | {e.get('w', '?')}×{e.get('h', '?')} | {fmt_files('avif')} ({e.get('avif_quality', '-')})"
              f" | {fmt_files('webp')} ({e.get('webp_quality', '-')}) | {fmt_files('jpg') or '-'}")
    for f in stale:
        print(f"{'지울 예정' if a.dry_run else '지움'}: {f.name} (art.json에 없는 그림)")
    for art_id in missing:
        print(f"원본 없음: {a.src / (pictures[art_id].get('file') or art_id + '.png')}"
              f"{' — 커밋된 파생본은 그대로 둠' if art_id in manifest else ' — 파생본도 없음'}")
    bad = {art_id: over_budget(art_id, e) for art_id, e in manifest.items() if over_budget(art_id, e)}
    for art_id, size in bad.items():
        print(f"예산 초과: {art_id} {HERO_BUDGET[1]}w AVIF {size:,}바이트 > {HERO_BUDGET[2]:,}")
    incomplete = not a.dry_run and any(art_id not in manifest for art_id in pictures)
    return 1 if bad or incomplete else 0


if __name__ == "__main__":
    sys.exit(main())
