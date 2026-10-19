"""Resized AVIF/WebP derivatives of KOGL-1 photos — only those a page crops, zooms or shows full-bleed.

    python tools/kogl1_media.py --data data/incheon              # download what is missing, encode, write manifest
    python tools/kogl1_media.py --data data/incheon --dry-run    # list what would be made, change nothing

Which photos (pipeline/media.py wanted()): the home opening slides, the story chapters, the KOGL-1 island gallery
cards, and every place whose lead photo is KOGL-1 (the full-bleed place opening). KOGL-3 (공공누리 제3유형,
변경금지) photos are never touched — each photo is checked against its stored licence before it is encoded.

Why: the opening photo is the mobile LCP element. The provider original is an 80–230KB JPEG on a third-party
origin (DNS + TLS on a slow link); a same-origin AVIF at 480/940w is 14–60KB. KOGL-1 allows change with
attribution, and the credit under every photo stays "출처: 한국관광공사". Nothing is upscaled: the widest file is
the source width. The opening slides get a lighter encode (the home's LCP image, a 3:2 product shot).

Output: templates/assets/media/<contentid>-<width>[h].<avif|webp> and manifest.json
{provider url: {"w", "h", "slot", "avif": [[path, width, bytes], …], "webp": [...]}}. The build copies the folder
with the other assets; pipeline/media.attach() adds the srcsets to the photo dicts.
Originals are cached in data/cache/kogl1-src/ (git-ignored); existing derivatives are kept (--force re-encodes).
--max-downloads caps the requests of one run. Outbound HTTPS uses HTTPS_PROXY / SSL_CERT_FILE from the
environment. Re-run after tools/tourapi_bulk.py or tools/tourapi_details.py changes photos.
"""
from __future__ import annotations

import argparse
import io
import json
import sys
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from pipeline import media  # noqa: E402

WIDTHS = {"cover": (480, 940, 1280), "hero": (480, 940), "k1": (480, 940)}   # cover: the full-bleed home photo
QUALITY = {"cover": {"avif": 60, "webp": 78}, "hero": {"avif": 44, "webp": 66}, "k1": {"avif": 56, "webp": 74}}
UA = "Mozilla/5.0 (compatible; webforai-kogl1-media)"


def stem_of(url: str) -> str:
    name = url.rsplit("/", 1)[-1].lower()
    return name.rsplit(".", 1)[0].replace("_image2_1", "")


def licence_of(S, url: str) -> str:
    """The stored licence of a photo URL (any place that shows it); '' when not found."""
    for e in S.entities:
        for im in e.get("_images") or []:
            if im.get("url") == url and im.get("source") == "TourAPI":
                return im.get("license") or ""
    return ""


def fetch(url: str, cache: Path, budget: list[int]) -> Path | None:
    raw = cache / url.rsplit("/", 1)[-1].lower()
    if raw.exists() and raw.stat().st_size:
        return raw
    if budget[0] <= 0:
        return None
    budget[0] -= 1
    req = urllib.request.Request(url.replace("http://", "https://", 1), headers={"User-Agent": UA})
    with urllib.request.urlopen(req, timeout=60) as r:
        body = r.read()
    cache.mkdir(parents=True, exist_ok=True)
    raw.write_bytes(body)
    return raw


def encode(raw: Path, url: str, slot: str, out: Path, force: bool) -> dict:
    from PIL import Image  # Pillow with AVIF (pillow>=11.3 ships libavif)

    im = Image.open(raw).convert("RGB")
    W, H = im.size
    stem, mark = stem_of(url), "h" if slot == "hero" else ""
    entry = {"w": W, "h": H, "slot": slot, "avif": [], "webp": []}
    for target in WIDTHS[slot]:
        w = min(target, W)
        h = round(H * w / W)
        frame = im if w == W else im.resize((w, h), Image.LANCZOS)
        for fmt in ("avif", "webp"):
            path = out / f"{stem}-{w}{mark}.{fmt}"
            if force or not path.exists():
                buf = io.BytesIO()
                opts = {"quality": QUALITY[slot][fmt], "speed": 4} if fmt == "avif" else \
                    {"quality": QUALITY[slot][fmt], "method": 6}
                frame.save(buf, fmt.upper(), **opts)
                path.write_bytes(buf.getvalue())
            entry[fmt].append([media.URL_PREFIX + path.name, w, path.stat().st_size])
        if w == W:
            break
    return entry


def run(data_dir: Path, out: Path = media.MEDIA_DIR, cache: Path = ROOT / "data" / "cache" / "kogl1-src",
        max_downloads: int = 200, dry_run: bool = False, force: bool = False, prune: bool = True) -> dict:
    from pipeline.build import State

    S = State(Path(data_dir), "preview")
    want = media.wanted(S)
    for url in want:  # KOGL-1 only, by construction — and checked against the stored licence again here
        lic = licence_of(S, url)
        if lic != "KOGL-1":
            raise SystemExit(f"공공누리 제1유형이 아닌 사진은 변환하지 않습니다: {url} ({lic or '라이선스 없음'})")
    if dry_run:
        for url, slot in want.items():
            print(f"{slot}\t{url}")
        print(f"제1유형 사진 {len(want)}장 (변환 안 함, --dry-run)")
        return {"photos": len(want), "dry_run": True}
    out.mkdir(parents=True, exist_ok=True)
    budget, man, skipped = [max_downloads], {}, []
    for url, slot in sorted(want.items()):
        try:
            raw = fetch(url, cache, budget)
        except OSError as exc:  # the provider's own error text, as is
            skipped.append(f"{url}: {exc}")
            continue
        if raw is None:
            skipped.append(f"{url}: 실행당 내려받기 상한(--max-downloads {max_downloads}) 도달")
            continue
        man[url] = encode(raw, url, slot, out, force)
    keep = {Path(p).name for v in man.values() for fmt in ("avif", "webp") for p, *_ in v[fmt]}
    removed = 0
    if prune:
        for f in out.iterdir():
            if f.suffix in (".avif", ".webp") and f.name not in keep:
                f.unlink()
                removed += 1
    (out / "manifest.json").write_text(json.dumps(man, ensure_ascii=False, indent=1, sort_keys=True) + "\n", "utf-8")
    files = sum(len(v["avif"]) + len(v["webp"]) for v in man.values())
    total = sum(b for v in man.values() for fmt in ("avif", "webp") for _, _, b in v[fmt])
    report = {"photos": len(man), "files": files, "kb": round(total / 1024), "removed": removed,
              "skipped": skipped, "hero": sum(1 for v in man.values() if v["slot"] == "hero")}
    print(json.dumps(report, ensure_ascii=False))
    return report


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--data", type=Path, default=ROOT / "data" / "incheon")
    ap.add_argument("--out", type=Path, default=media.MEDIA_DIR)
    ap.add_argument("--cache", type=Path, default=ROOT / "data" / "cache" / "kogl1-src")
    ap.add_argument("--max-downloads", type=int, default=200)
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--force", action="store_true", help="re-encode derivatives that already exist")
    ap.add_argument("--keep-stale", action="store_true", help="do not delete derivatives no longer wanted")
    a = ap.parse_args(argv)
    report = run(a.data, a.out, a.cache, a.max_downloads, a.dry_run, a.force, not a.keep_stale)
    return 1 if report.get("skipped") else 0


if __name__ == "__main__":
    sys.exit(main())
