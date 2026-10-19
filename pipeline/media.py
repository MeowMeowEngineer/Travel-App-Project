"""Same-origin AVIF/WebP derivatives of KOGL-1 photos, and the photo slots that use them (CLAUDE.md 3.4, 7).

KOGL-1 (공공누리 제1유형) photos may be resized and re-encoded as long as the credit stays ("출처: 한국관광공사").
KOGL-3 (제3유형, 변경금지) photos never are: a page always shows the provider's own file, whole.

Derivatives exist only for KOGL-1 photos that a page crops, zooms or shows full-bleed:
  - the home's photo slots the city's configuration picks (site.json city.home.photos: hero slides, the full-bleed
    cover, the gallery cards; city.home.story[].photo: the story chapters) — slots whose treatment needs KOGL-1 go
    through pick_photo(..., need_k1=True);
  - every place whose lead photo is KOGL-1 (the full-bleed place opening; it is that page's LCP image).
tools/kogl1_media.py writes them to templates/assets/media/ with manifest.json; the build copies the folder with
the other assets and present.prepare() calls attach(), so every photo dict carries:

  ph.avif, ph.webp   srcset strings ("/assets/media/3414700-480.avif 480w, /assets/media/3414700-940.avif 940w"),
                     '' when the photo has no derivative (always '' for KOGL-3)
  ph.w, ph.h         the source's intrinsic size (the manifest fills it when image_sizes.json has none)
  ph.url             the provider original — the <img src> fallback inside <picture>
  ph.type            1 or 3

templates/_media.html.j2 turns that into <picture>/srcset with width/height, and a <link rel=preload>.
"""
from __future__ import annotations

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
MEDIA_DIR = ROOT / "templates" / "assets" / "media"
MANIFEST = MEDIA_DIR / "manifest.json"
URL_PREFIX = "/assets/media/"

# Home photo slots (Apple direction, approved 2026-10-08): [place slug or name, index into that place's licensed TourAPI
# photos], picked per city in site.json (city.home.photos {hero, cover, gallery}; city.home.story[].photo). The opening
# slides are cropped 3:2 and pushed in with the scroll, the cover fills the screen behind the H1: KOGL-1 only. The
# story chapters take either licence — a KOGL-1 photo may settle 1.08 → 1 in the stage, a KOGL-3 one is shown whole.
# The gallery cards crop KOGL-1 and show KOGL-3 whole. Without picks (a new city before the owner chooses) the slots
# are empty and the home leaves them out.


def _picks(key: str) -> list[tuple[str, int]]:
    from . import city
    raw = (city.current().home("photos", {}) or {}).get(key) or []
    if key == "cover":
        raw = [raw] if raw else []
    return [(str(x[0]), int(x[1]) if len(x) > 1 else 0) for x in raw if x]


def _story_picks() -> dict[str, tuple[str, int]]:
    from . import city
    return {c["id"]: (str(c["photo"][0]), int(c["photo"][1]) if len(c["photo"]) > 1 else 0)
            for c in city.current().home("story", []) or [] if c.get("id") and c.get("photo")}


def load_manifest(path: Path = MANIFEST) -> dict:
    """{provider url: {"w", "h", "avif": [[path, width, bytes], …], "webp": [...]}}; {} when absent or unreadable."""
    try:
        return json.loads(Path(path).read_text("utf-8")) if Path(path).exists() else {}
    except (OSError, ValueError):
        return {}


def srcset(files: list) -> str:
    return ", ".join(f"{p} {w}w" for p, w, *_ in files)


def smallest(ph: dict) -> tuple[str, int, int] | None:
    """(url, width, height) of the smallest same-origin WebP derivative of a KOGL-1 photo, or None. List rows and
    cards (present.thumb) use it when the provider has no small copy of its own, so a 69-98 px row never downloads
    a 1280 px original (the TourAPI photo gallery has no small copies)."""
    if ph.get("type") != 1 or not ph.get("webp") or not (ph.get("w") and ph.get("h")):
        return None
    files = [p.rsplit(" ", 1) for p in ph["webp"].split(", ")]
    url, w = min(((u, int(d[:-1])) for u, d in files if d.endswith("w") and d[:-1].isdigit()), key=lambda x: x[1])
    return url, w, round(w * ph["h"] / ph["w"])


def attach(S, manifest: dict | None = None) -> None:
    """Add avif/webp srcsets (and a missing intrinsic size) to every photo of every place. KOGL-1 only: a manifest
    entry for any other photo is ignored, so a mistaken derivative can never reach a page."""
    man = load_manifest() if manifest is None else manifest
    for e in S.entities:
        for ph in e.get("_photos") or []:
            entry = man.get(ph["url"]) if ph.get("type") == 1 else None
            ph["avif"] = srcset(entry["avif"]) if entry and entry.get("avif") else ""
            ph["webp"] = srcset(entry["webp"]) if entry and entry.get("webp") else ""
            if entry and not (ph.get("w") and ph.get("h")):
                ph["w"], ph["h"] = entry["w"], entry["h"]
                ph["ar"] = f"{entry['w']}/{entry['h']}"


def _pick(S, slug: str, n: int, need_k1: bool) -> tuple[dict | None, str]:
    from .present import find_place
    e = find_place(S, slug)
    photos = (e or {}).get("_photos") or []
    if not photos:
        return None, f"사진 자리: {slug}에 쓸 수 있는 사진 없음 — 그 자리 생략"
    ph = photos[min(n, len(photos) - 1)]
    if need_k1 and ph.get("type") != 1:
        return None, f"사진 자리: {slug} #{n}은 공공누리 제{ph.get('type')}유형 — 자르거나 확대하는 자리에 쓰지 않음"
    return {**ph, "place": e["name"], "path": e["_path"], "slug": e.get("slug", slug), "kind": e.get("kind", "")}, ""


def pick_photo(S, slug: str, n: int = 0, need_k1: bool = True) -> dict | None:
    """Photo n of a place (the last one when it has fewer) with its place name, path and slug. A slot that crops
    or zooms passes need_k1=True: a KOGL-3 photo is then refused with a warning (never cropped or zoomed)."""
    ph, why = _pick(S, slug, n, need_k1)
    if why and getattr(S, "warnings", None) is not None:
        S.warnings.append(why)
    return ph


def slot_photos(S) -> dict:
    """The home's photo slots: hero (KOGL-1 only), cover (the full-bleed opening photo, KOGL-1 only), story ({chapter
    id: photo}, either licence, None for a missing one) and gallery (either licence; templates crop KOGL-1 cards and
    show KOGL-3 cards whole). Empty when the city's configuration picks none."""
    cover = _picks("cover")
    return {"hero": [x for x in (pick_photo(S, s, n, True) for s, n in _picks("hero")) if x],
            "cover": pick_photo(S, *cover[0], True) if cover else None,
            "story": {cid: pick_photo(S, s, n, False) for cid, (s, n) in _story_picks().items()},
            "gallery": [x for x in (pick_photo(S, s, n, False) for s, n in _picks("gallery")) if x]}


def wanted(S) -> dict:
    """{url: slot} for every KOGL-1 photo that gets derivatives; slot 'cover' (the full-bleed home opening: up to
    1280w, a fuller encode — it fills a wide screen), 'hero' (the opening product shots: a lighter encode, small on
    phones) or 'k1'. Used by tools/kogl1_media.py."""
    out: dict[str, str] = {}
    for slot, n_slot in (("cover", _picks("cover")), ("hero", _picks("hero")),
                         ("k1", list(_story_picks().values()) + _picks("gallery"))):
        for s, n in n_slot:
            ph, _ = _pick(S, s, n, True)
            if ph:
                out.setdefault(ph["url"], slot)
    for e in S.entities:
        photos = e.get("_photos") or []
        if photos and photos[0].get("type") == 1:
            out.setdefault(photos[0]["url"], "k1")
    return out


def preload(ph: dict | None, sizes: str = "100vw") -> dict | None:
    """<link rel=preload> fields for a page's first-screen KOGL-1 photo; None when it has no AVIF derivative."""
    if not ph or ph.get("type") != 1 or not ph.get("avif"):
        return None
    return {"srcset": ph["avif"], "type": "image/avif", "sizes": sizes}
