"""The 3D picture registry (owner 2026-10-14: '사이트 전수점검해서 모든 부분을 GPT 생성 이미지로 마스코트도 고려해서
아기자기하게'). One data-driven mapping from a picture ID (docs/handover/gpt_image_prompts_3d_2026-10-14.md, the audit
docs/handover/specs/icon_audit.md) to its derived files, its label and its interim glyph:

  data/<region>/icons.json        {"icons": {id: {"glyph", "label", "group"}}} — which pictures exist as slots
  templates/assets/icons/         <id>-<px>.avif|webp + manifest.json, made by tools/icon_media.py from the
                                  git-ignored originals incoming/icons/<id>.png

templates/_pic.html.j2 pic(id, glyph, size, alt) asks lookup(id): the derived files when the manifest has them, else
None and the macro draws the interim look (the line glyph on a pale tinted circle). Templates never name files.
ASSETS can be pointed at another folder (tests drop a generated PNG into a tmp copy).

The mascot (templates/assets/mascot/, tools/mascot_media.py) is optional: a site whose owner has not chosen one has no
files there, and mascot(name) is False, so templates/_mascot.html.j2 draws its fallback (a line glyph or nothing) and no
page names a file that is not there. MASCOT can be pointed at another folder like ASSETS."""
from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
ASSETS = ROOT / "templates" / "assets" / "icons"
REGISTRY = ROOT / "data" / "incheon" / "icons.json"   # TODO(다음 단계): --data의 icons.json을 따르게 바꾼다
MASCOT = ROOT / "templates" / "assets" / "mascot"
URL = "/assets/icons/"


@lru_cache(maxsize=8)
def _manifest(folder: str) -> dict:
    f = Path(folder) / "manifest.json"
    if not f.is_file():
        return {}
    try:
        return json.loads(f.read_text("utf-8"))
    except (OSError, ValueError):
        return {}


@lru_cache(maxsize=4)
def _registry(path: str) -> dict:
    f = Path(path)
    return json.loads(f.read_text("utf-8")).get("icons", {}) if f.is_file() else {}


def registry() -> dict:
    return _registry(str(REGISTRY))


def reset() -> None:
    _manifest.cache_clear()
    _registry.cache_clear()


def lookup(pid: str) -> dict | None:
    """{id, label, glyph, avif: [(url, px)], webp: [(url, px)], px} when every listed file of the picture exists,
    else None (the interim look)."""
    m = _manifest(str(ASSETS)).get(pid)
    if not m:
        return None
    folder = Path(ASSETS)
    out = {"id": pid, "px": m.get("px", []), "label": (registry().get(pid) or {}).get("label", "")}
    for fmt in ("avif", "webp"):
        files = m.get(fmt) or []
        if not files or not all((folder / name).is_file() for name, _px in files):
            return None
        out[fmt] = [(URL + name, px) for name, px in files]
    return out


def glyph(pid: str, default: str = "pin") -> str:
    return (registry().get(pid) or {}).get("glyph") or default


def mascot(name: str) -> bool:
    """True when templates/assets/mascot/manifest.json lists the pose and every file it lists for AVIF and WebP is on
    disk (tools/mascot_media.py writes both); False for a site without a mascot."""
    m = _manifest(str(MASCOT)).get(name)
    if not m:
        return False
    folder = Path(MASCOT)
    for fmt in ("avif", "webp"):
        files = m.get(fmt) or []
        if not files or not all((folder / f[0]).is_file() for f in files):
            return False
    return True
