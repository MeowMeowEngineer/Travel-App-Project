"""Record the intrinsic size and byte length of every licensed photo the site shows.

    python tools/image_sizes.py --data data/gunsan                 # probe photos not yet in the file
    python tools/image_sizes.py --data data/gunsan --refresh       # probe every photo again

Writes data/<region>/image_sizes.json: {url: [width, height, bytes]}. pipeline/present.py reads it so every
<img> can carry width/height/aspect-ratio (no layout shift) and never be drawn above its native width.

Photos: images[] with source TourAPI and a licence the site may show (site.json publish_rules
allowed_image_licenses, default KOGL-1/KOGL-3), plus the provider's own small rendition of each
('…_image3_1.*', TourAPI smallimageurl) for thumbnails. A rendition is recorded only when it answers with a
decodable image; otherwise the page falls back to the original.

How: a ranged GET of the first 32KB (the JPEG/PNG/GIF/WebP header holds the size), widened to 256KB and then
the whole file when the header is further in. The byte length comes from Content-Range (or the body).
Outbound HTTPS uses the environment's proxy and CA settings (HTTPS_PROXY, SSL_CERT_FILE). Already recorded
URLs are not fetched again (the file is the cache); --limit caps the requests of one run. Re-run after
tools/tourapi_bulk.py or tools/tourapi_details.py adds photos.
"""
from __future__ import annotations

import argparse
import json
import struct
import sys
import urllib.request
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

DEFAULT_LICENSES = ("KOGL-1", "KOGL-3")
STEPS = (32768, 262144, None)  # bytes per attempt; None = the whole file
UA = "Mozilla/5.0 (compatible; gunsan-image-size-probe)"


def image_size(data: bytes) -> tuple[int, int] | None:
    """(width, height) from the first bytes of a JPEG, PNG, GIF or WebP file; None when not found (yet)."""
    if data[:8] == b"\x89PNG\r\n\x1a\n" and len(data) >= 24 and data[12:16] == b"IHDR":
        return struct.unpack(">II", data[16:24])
    if data[:6] in (b"GIF87a", b"GIF89a") and len(data) >= 10:
        return struct.unpack("<HH", data[6:10])
    if data[:4] == b"RIFF" and data[8:12] == b"WEBP" and len(data) >= 30:
        chunk = data[12:16]
        if chunk == b"VP8 ":
            w, h = struct.unpack("<HH", data[26:30])
            return w & 0x3FFF, h & 0x3FFF
        if chunk == b"VP8L":
            b = data[21:25]
            w = 1 + (((b[1] & 0x3F) << 8) | b[0])
            h = 1 + (((b[3] & 0xF) << 10) | (b[2] << 2) | ((b[1] & 0xC0) >> 6))
            return w, h
        if chunk == b"VP8X":
            return 1 + int.from_bytes(data[24:27], "little"), 1 + int.from_bytes(data[27:30], "little")
        return None
    if data[:2] != b"\xff\xd8":
        return None
    i = 2
    while i + 4 <= len(data):
        if data[i] != 0xFF:
            i += 1
            continue
        marker = data[i + 1]
        if marker in (0xD8, 0x01) or 0xD0 <= marker <= 0xD7 or marker == 0xFF:
            i += 2 if marker != 0xFF else 1
            continue
        if marker in (0xD9, 0xDA):  # end of image / start of scan: no frame header before it
            return None
        length = struct.unpack(">H", data[i + 2:i + 4])[0]
        if 0xC0 <= marker <= 0xCF and marker not in (0xC4, 0xC8, 0xCC):
            if i + 9 > len(data):
                return None
            h, w = struct.unpack(">HH", data[i + 5:i + 9])
            return w, h
        i += 2 + length
    return None


def probe(url: str, timeout: int = 60) -> tuple[str, list | None, str]:
    """(url, [width, height, bytes] or None, error text). Provider errors are reported as they come."""
    for size in STEPS:
        headers = {"User-Agent": UA}
        if size:
            headers["Range"] = f"bytes=0-{size - 1}"
        try:
            with urllib.request.urlopen(urllib.request.Request(url, headers=headers), timeout=timeout) as r:
                data = r.read()
                total = len(data)
                content_range = r.headers.get("Content-Range") or ""
                if "/" in content_range and content_range.rsplit("/", 1)[1].isdigit():
                    total = int(content_range.rsplit("/", 1)[1])
                elif r.headers.get("Content-Length", "").isdigit() and not size:
                    total = int(r.headers["Content-Length"])
        except Exception as exc:  # noqa: BLE001 — every failure is reported with its own message
            return url, None, f"{type(exc).__name__}: {exc}"
        wh = image_size(data)
        if wh and wh[0] and wh[1]:
            return url, [wh[0], wh[1], total], ""
        if size and len(data) < size:  # the whole file came back and has no readable header
            break
    return url, None, "이미지 크기를 읽지 못함"


def photo_urls(data_dir: Path) -> list[str]:
    places = json.loads((data_dir / "places.json").read_text("utf-8"))
    site_path = data_dir / "site.json"
    site = json.loads(site_path.read_text("utf-8")) if site_path.exists() else {}
    allowed = tuple((site.get("publish_rules") or {}).get("allowed_image_licenses") or DEFAULT_LICENSES)
    originals = sorted({i["url"] for p in places for i in p.get("images") or []
                        if i.get("source") == "TourAPI" and i.get("license") in allowed and i.get("url")})
    small = [u.replace("_image2_1", "_image3_1") for u in originals if "_image2_1" in u]
    return originals + small


def write(path: Path, sizes: dict) -> None:
    rows = [f"{json.dumps(k, ensure_ascii=False)}: {json.dumps(v)}" for k, v in sorted(sizes.items())]
    path.write_text("{\n" + ",\n".join(rows) + "\n}\n", "utf-8")


def run(data_dir: Path, out: Path | None = None, refresh: bool = False, limit: int = 2000, workers: int = 8,
        prober=probe) -> dict:
    out = out or data_dir / "image_sizes.json"
    cache = json.loads(out.read_text("utf-8")) if out.exists() else {}
    urls = photo_urls(data_dir)
    todo = [u for u in urls if refresh or u not in cache][:limit]
    failed = []
    with ThreadPoolExecutor(max(1, workers)) as ex:
        for url, size, err in ex.map(prober, todo):
            if size:
                cache[url] = size
            else:
                if refresh:  # a re-probe that fails drops the old record rather than keep a stale size
                    cache.pop(url, None)
                failed.append((url, err))
    keep = set(urls)
    sizes = {u: v for u, v in cache.items() if u in keep}
    write(out, sizes)
    originals = [u for u in urls if "_image3_1" not in u]
    return {"photos": len(originals), "renditions_probed": len(urls) - len(originals), "requests": len(todo),
            "recorded": len(sizes), "originals_recorded": sum(1 for u in originals if u in sizes),
            "renditions_recorded": sum(1 for u in sizes if "_image3_1" in u), "failed": failed, "out": str(out)}


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--data", type=Path, default=Path("data/gunsan"))
    ap.add_argument("--out", type=Path, default=None)
    ap.add_argument("--refresh", action="store_true", help="probe recorded photos again")
    ap.add_argument("--limit", type=int, default=2000, help="most requests in one run")
    ap.add_argument("--workers", type=int, default=8)
    a = ap.parse_args(argv)
    report = run(a.data, a.out, a.refresh, a.limit, a.workers)
    for url, err in report["failed"]:
        print("FAIL", url, err)
    print(json.dumps({k: v for k, v in report.items() if k != "failed"} | {"failed": len(report["failed"])},
                     ensure_ascii=False))
    originals_missing = report["photos"] - report["originals_recorded"]
    return 1 if originals_missing else 0


if __name__ == "__main__":
    sys.exit(main())
