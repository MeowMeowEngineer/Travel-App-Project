"""The site's mascot as small WebP/AVIF files with transparency (owner decision 2026-10-13: a small yellow chick with
a blue scarf, the knot on its left chest, and a brown backpack, in a soft 3D clay look — only on this site; it shows up
only in guide spots: the assistant, empty states, 404, help).

    python tools/mascot_media.py              # make what is missing from incoming/mascot/ (the originals)
    python tools/mascot_media.py --force      # make every file again
    python tools/mascot_media.py --dry-run    # list what would be made, change nothing

Originals: incoming/mascot/mascot-<pose>.png — the owner's final pictures, transparent 1254×1254 PNGs. The folder is
git-ignored like incoming/ai-images/ (only its README is committed); the files made from them are committed.

Every picture is cleaned and cut the same way:
  - alpha below ALPHA_FLOOR (8) becomes 0: the generator leaves faint specks and a fringe around the figure that show
    as dots on a dark page; alpha from ALPHA_FULL (248) becomes 255: the body is stored at 252–254, so a page behind
    it would show through;
  - the picture is cut to what is left, with an even margin (MARGIN: 4% of its longer side) on every side, and
    centred on a square, so every file of a pose is N×N and a page gives it width = height;
  - it is resized with premultiplied alpha (no dark halo at the edges), Lanczos.
Sizes (SIZES: the pages show them at the first number, the second is for 2× screens):
  icon    64 · 128   the face — the launcher button (mascot-icon-3d), a panel head later (mascot-icon-flat)
  small   96 · 192   a spot beside a box or a message — hello, point, think, sorry, search
  medium  200 · 400  an empty state — 404, empty
Output: templates/assets/mascot/<name>-<px>.avif|webp and manifest.json
{name: {"size": "icon", "px": [64, 128], "avif": [[file, px, bytes], …], "webp": [[file, px, bytes], …]}}.
The build copies the folder with the other assets (pipeline/build.py); templates/_mascot.html.j2 writes the <picture>.
Budget: an icon file is at most ICON_BUDGET bytes (8 KB); tests/test_mascot.py checks the files against the manifest.
Deterministic: no metadata, the AVIF encoder single-threaded with fixed settings — the same original gives the same
bytes. Needs Pillow >= 11.3 with AVIF (the build itself does not). Files of a pose no longer listed are deleted.
"""
from __future__ import annotations

import argparse
import io
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SRC_DIR = ROOT / "incoming" / "mascot"
OUT_DIR = ROOT / "templates" / "assets" / "mascot"
URL_PREFIX = "/assets/mascot/"
SIZES = {"icon": (64, 128), "small": (96, 192), "medium": (200, 400)}
POSES = {
    "mascot-icon-3d": "icon", "mascot-icon-flat": "icon",
    "mascot-hello": "small", "mascot-point": "small", "mascot-think": "small", "mascot-sorry": "small",
    "mascot-search": "small",
    "mascot-404": "medium", "mascot-empty": "medium",
    # the AI course planner (/plan/, 2026-10-17): at work and with the plan done (the page's first picture), and the
    # rain-edit spot beside the edit box
    "mascot-plan": "medium", "mascot-plan-done": "medium", "mascot-plan-rain": "small",
}
ALPHA_FLOOR, ALPHA_FULL, MARGIN = 8, 248, 0.04
AVIF_QUALITY, AVIF_SPEED, WEBP_QUALITY, WEBP_ALPHA_QUALITY = 68, 4, 82, 90
ICON_BUDGET = 8 * 1024
FORMATS = ("avif", "webp")


def clean(im):
    """The original with its alpha snapped (specks out, body opaque), cut to the figure plus an even margin and
    centred on a transparent square."""
    from PIL import Image
    im = im.convert("RGBA")
    alpha = im.getchannel("A").point(lambda a: 0 if a < ALPHA_FLOOR else 255 if a >= ALPHA_FULL else a)
    im.putalpha(alpha)
    box = alpha.getbbox()
    if not box:
        raise SystemExit("그림에 보이는 부분이 없습니다")
    fig = im.crop(box)
    side = max(fig.size)
    pad = round(side * MARGIN)
    canvas = side + 2 * pad
    sq = Image.new("RGBA", (canvas, canvas), (0, 0, 0, 0))
    sq.paste(fig, ((canvas - fig.width) // 2, (canvas - fig.height) // 2))
    return sq


def resize(sq, px: int):
    from PIL import Image
    return sq.convert("RGBa").resize((px, px), Image.LANCZOS).convert("RGBA")


def encode(frame, fmt: str) -> bytes:
    buf = io.BytesIO()
    if fmt == "avif":
        frame.save(buf, "AVIF", quality=AVIF_QUALITY, speed=AVIF_SPEED, max_threads=1)
    else:
        frame.save(buf, "WEBP", quality=WEBP_QUALITY, alpha_quality=WEBP_ALPHA_QUALITY, method=6)
    return buf.getvalue()


def renditions(name: str, path: Path) -> tuple[dict, dict]:
    """(manifest entry, {file name: bytes}) for one original."""
    from PIL import Image
    with Image.open(path) as src:
        sq = clean(src)
    kind = POSES[name]
    entry, files = {"size": kind, "px": list(SIZES[kind]), "avif": [], "webp": []}, {}
    for px in SIZES[kind]:
        frame = resize(sq, px)
        for fmt in FORMATS:
            data = encode(frame, fmt)
            fname = f"{name}-{px}.{fmt}"
            files[fname] = data
            entry[fmt].append([fname, px, len(data)])
    return entry, files


def load_manifest(out: Path = OUT_DIR) -> dict:
    try:
        return json.loads((Path(out) / "manifest.json").read_text("utf-8"))
    except FileNotFoundError:
        return {}


def entry_files(entry: dict) -> list[str]:
    return [f for fmt in FORMATS for f, _, _ in entry.get(fmt) or []]


def over_budget(entry: dict) -> list[str]:
    """The icon files over ICON_BUDGET bytes."""
    if entry.get("size") != "icon":
        return []
    return [f for fmt in FORMATS for f, _, size in entry.get(fmt) or [] if size > ICON_BUDGET]


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--src", type=Path, default=SRC_DIR, help="where the originals are (git-ignored)")
    ap.add_argument("--out", type=Path, default=OUT_DIR)
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--force", action="store_true", help="make the files again even when they exist")
    a = ap.parse_args(argv)

    old = load_manifest(a.out)
    manifest, rows, missing = {}, [], []
    for name in POSES:
        prev = old.get(name)
        complete = bool(prev) and prev.get("size") == POSES[name] and \
            all((a.out / f).is_file() for f in entry_files(prev))
        if complete and not a.force:
            manifest[name] = prev
            rows.append((name, "그대로", prev))
            continue
        src = a.src / f"{name}.png"
        if not src.is_file():
            if prev:
                manifest[name] = prev
            missing.append(name)
            continue
        if a.dry_run:
            rows.append((name, "만들 예정", prev or {"size": POSES[name]}))
            if prev:
                manifest[name] = prev
            continue
        entry, files = renditions(name, src)
        a.out.mkdir(parents=True, exist_ok=True)
        for fname, blob in files.items():
            (a.out / fname).write_bytes(blob)
        manifest[name] = entry
        rows.append((name, "만듦", entry))

    keep = {f for e in manifest.values() for f in entry_files(e)}
    stale = sorted(f for f in a.out.glob("*") if f.suffix in (".avif", ".webp") and f.name not in keep) \
        if a.out.is_dir() else []
    if not a.dry_run:
        for f in stale:
            f.unlink()
        if manifest:
            a.out.mkdir(parents=True, exist_ok=True)
            (a.out / "manifest.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=1) + "\n", "utf-8")

    print("그림 | 상태 | 크기 | AVIF 폭:바이트 | WebP 폭:바이트")
    for name, state, e in rows:
        files = lambda fmt: ", ".join(f"{px}:{b:,}" for _, px, b in e.get(fmt) or [])   # noqa: E731
        print(f"{name} | {state} | {e.get('size')} | {files('avif')} | {files('webp')}")
    for f in stale:
        print(f"{'지울 예정' if a.dry_run else '지움'}: {f.name} (목록에 없는 그림)")
    for name in missing:
        print(f"원본 없음: {a.src / (name + '.png')}{' — 커밋된 파일은 그대로 둠' if name in manifest else ''}")
    heavy = [f for e in manifest.values() for f in over_budget(e)]
    for f in heavy:
        print(f"예산 초과: {f} > {ICON_BUDGET:,}바이트")
    return 1 if heavy or (not a.dry_run and any(n not in manifest for n in POSES)) else 0


if __name__ == "__main__":
    sys.exit(main())
