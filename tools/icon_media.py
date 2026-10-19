"""The site's 3D clay pictures (owner 2026-10-14) as small WebP/AVIF files with transparency.

    python tools/icon_media.py              # make what is missing from incoming/icons/ (the originals)
    python tools/icon_media.py --force      # make every file again
    python tools/icon_media.py --dry-run    # list what would be made, change nothing

Originals: incoming/icons/<ID>.png — 1024×1024 PNGs from ChatGPT, named by the fixed IDs of
the first city site's prompt list (data/incheon/icons.json lists them). Git-ignored like
incoming/mascot/; the files made from them are committed. A PNG without transparency (a pure white background, the
prompt's fallback) has its near-white pixels (all channels >= WHITE_CUT) made transparent first.
Cleaning and cutting are tools/mascot_media.py's (alpha snapped, cut to the figure with an even margin, centred on a
square, resized with premultiplied alpha). Sizes: SIZES px (the pages draw them at 32–120px; the srcset picks one).
Output: templates/assets/icons/<ID>-<px>.avif|webp and manifest.json {id: {"px": [...], "avif": [[file, px], …],
"webp": [[file, px], …]}}; pipeline/icons.py reads it, templates/_pic.html.j2 draws it. An unknown ID is refused.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(Path(__file__).resolve().parent))
import mascot_media as mm  # noqa: E402  (clean, resize, encode)

SRC_DIR = ROOT / "incoming" / "icons"
OUT_DIR = ROOT / "templates" / "assets" / "icons"
REGISTRY = ROOT / "data" / "incheon" / "icons.json"   # TODO(다음 단계): pipeline.icons와 함께 --data를 따르게
SIZES = (64, 128, 240)
WHITE_CUT = 248
FORMATS = ("avif", "webp")


def known_ids(registry: Path = REGISTRY) -> set[str]:
    return set(json.loads(registry.read_text("utf-8"))["icons"])


def knock_white(im):
    """A picture with no transparency: its near-white pixels become transparent."""
    im = im.convert("RGBA")
    if im.getchannel("A").getextrema() != (255, 255):
        return im
    px = im.load()
    w, h = im.size
    for y in range(h):
        for x in range(w):
            r, g, b, a = px[x, y]
            if r >= WHITE_CUT and g >= WHITE_CUT and b >= WHITE_CUT:
                px[x, y] = (r, g, b, 0)
    return im


def make(src_dir: Path = SRC_DIR, out_dir: Path = OUT_DIR, registry: Path = REGISTRY, force: bool = False,
         dry: bool = False, formats=FORMATS) -> dict:
    from PIL import Image
    ids = known_ids(registry)
    out_dir.mkdir(parents=True, exist_ok=True)
    mf = out_dir / "manifest.json"
    manifest = json.loads(mf.read_text("utf-8")) if mf.is_file() else {}
    made = []
    for src in sorted(src_dir.glob("*.png")):
        pid = src.stem
        if pid not in ids:
            print(f"알 수 없는 ID(건너뜀): {pid}", file=sys.stderr)
            continue
        names = {fmt: [[f"{pid}-{px}.{fmt}", px] for px in SIZES] for fmt in formats}
        if not force and pid in manifest and all((out_dir / n).is_file() for fmt in formats for n, _ in names[fmt]):
            continue
        made.append(pid)
        if dry:
            continue
        sq = mm.clean(knock_white(Image.open(src)))
        for px in SIZES:
            frame = mm.resize(sq, px)
            for fmt in formats:
                (out_dir / f"{pid}-{px}.{fmt}").write_bytes(mm.encode(frame, fmt))
        manifest[pid] = {"px": list(SIZES), **names}
    if not dry:
        mf.write_text(json.dumps(dict(sorted(manifest.items())), ensure_ascii=False, indent=1) + "\n", "utf-8")
    return {"made": made, "n": len(manifest)}


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--force", action="store_true")
    ap.add_argument("--dry-run", action="store_true")
    a = ap.parse_args(argv)
    print(json.dumps(make(force=a.force, dry=a.dry_run), ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
