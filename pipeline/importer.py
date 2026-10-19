"""CSV -> data/<region>/places.json : the contract between collectors and the rest of the pipeline.

Any collector (the Gunsan site crawler, a converter for the v0 export, a hand-made sheet)
only has to produce a CSV with these columns (UTF-8, header row):

  id, name, kind, category, themes, tier, status,
  source_url, original_text, original_license, collected_at,
  image_url, image_license, image_credit,
  lat, lng, naver_place_id, google_place_id

- id            : stable unique id, e.g. gunsan-0001 (never reuse or change)
- kind          : attraction | stay | food
- themes        : theme slugs separated by ';'
- tier          : full | basic          (default basic)
- status        : draft | reviewed | published   (default draft)
- original_text : the source text exactly as published (never edited)
- original_license / image_license : KOGL-1 | KOGL-2 | KOGL-3 | KOGL-4 | NONE | UNKNOWN
- collected_at  : YYYY-MM-DD

    python -m pipeline.importer --csv data/raw/gunsan_places.csv --data data/gunsan

Existing records with the same id keep their enrichment (facts, nearby, summary, faq ...);
only the source-side fields are updated. A changed original text is reported (its hash changes).
"""
from __future__ import annotations

import argparse
import csv
import json
import sys
from pathlib import Path

from .schema import check_entity
from .textutil import sha256_text, slugify

COLUMNS = ["id", "name", "kind", "category", "themes", "tier", "status", "source_url", "original_text",
           "original_license", "collected_at", "image_url", "image_license", "image_credit",
           "lat", "lng", "naver_place_id", "google_place_id"]


def _f(v: str) -> float | None:
    try:
        return float(v)
    except (TypeError, ValueError):
        return None


def row_to_entity(row: dict, source_name: str) -> dict:
    text = row.get("original_text") or ""
    e = {
        "id": row["id"].strip(),
        "name": row["name"].strip(),
        "slug": slugify(row["name"]),
        "kind": (row.get("kind") or "attraction").strip(),
        "category": (row.get("category") or "").strip(),
        "themes": [t.strip() for t in (row.get("themes") or "").split(";") if t.strip()],
        "tier": (row.get("tier") or "basic").strip(),
        "status": (row.get("status") or "draft").strip(),
        "official": {"source_url": (row.get("source_url") or "").strip()},
        "original": {
            "text": text,
            "source_name": source_name,
            "source_url": (row.get("source_url") or "").strip(),
            "license": (row.get("original_license") or "UNKNOWN").strip(),
            "collected_at": (row.get("collected_at") or "").strip(),
            "sha256": sha256_text(text),
        },
        "map_ids": {"naver_place_id": (row.get("naver_place_id") or "").strip(),
                    "google_place_id": (row.get("google_place_id") or "").strip()},
    }
    lat, lng = _f(row.get("lat")), _f(row.get("lng"))
    if lat is not None and lng is not None:
        e["geo"] = {"lat": lat, "lng": lng, "source": "원문"}
    if (row.get("image_url") or "").strip():
        e["images"] = [{"url": row["image_url"].strip(), "alt": e["name"],
                        "credit": (row.get("image_credit") or source_name).strip(),
                        "license": (row.get("image_license") or "UNKNOWN").strip(),
                        "source": "원문"}]
    return e


SOURCE_FIELDS = ("name", "kind", "category", "themes", "tier", "original", "map_ids")


def merge(existing: list[dict], incoming: list[dict]) -> tuple[list[dict], list[str]]:
    by_id = {e["id"]: e for e in existing}
    used_slugs = {e.get("slug") for e in existing if e.get("slug")}
    notes = []
    for new in incoming:
        old = by_id.get(new["id"])
        if not old:
            # Slugs become URLs: make them unique once, at import time, and never change them.
            base, n = new["slug"], 2
            while new["slug"] in used_slugs:
                new["slug"] = f"{base}-{n}"
                n += 1
            used_slugs.add(new["slug"])
            by_id[new["id"]] = new
            continue
        if old.get("original", {}).get("sha256") != new["original"]["sha256"]:
            notes.append(f"원문 변경 감지: {new['id']} {new['name']} — 요약·FAQ 재검수 필요")
        for k in SOURCE_FIELDS:
            # map_ids: the CSV's naver/google IDs replace ours; an ID the CSV has no column for (kakao_place_id,
            # tools/kakao_places.py) stays
            old[k] = {**(old.get(k) or {}), **new[k]} if k == "map_ids" else new[k]
        old.setdefault("official", {})["source_url"] = new["official"]["source_url"]
        if "geo" in new and "geo" not in (old.get("locks") or []) and not old.get("geo"):
            old["geo"] = new["geo"]
        if new.get("images"):
            keep = [i for i in old.get("images") or [] if i.get("source") != "원문"]
            old["images"] = keep + new["images"]
    return list(by_id.values()), notes


def run(csv_path: Path, data_dir: Path) -> int:
    site = json.loads((data_dir / "site.json").read_text("utf-8"))
    source_name = (site.get("source") or {}).get("name", "")
    with open(csv_path, newline="", encoding="utf-8-sig") as f:
        reader = csv.DictReader(f)
        missing = [c for c in ("id", "name", "original_text") if c not in (reader.fieldnames or [])]
        if missing:
            print(f"CSV 필수 열 누락: {missing}", file=sys.stderr)
            return 2
        incoming = [row_to_entity(r, source_name) for r in reader if (r.get("id") or "").strip()]
    problems = [(e["id"], p) for e in incoming for p in check_entity(e)]
    for pid, p in problems:
        print(f"[{pid}] {p}", file=sys.stderr)
    path = data_dir / "places.json"
    existing = json.loads(path.read_text("utf-8")) if path.exists() else []
    merged, notes = merge(existing, incoming)
    path.write_text(json.dumps(merged, ensure_ascii=False, indent=2), "utf-8")
    for n in notes:
        print(n)
    print(json.dumps({"incoming": len(incoming), "total": len(merged), "problems": len(problems),
                      "changed_originals": len(notes)}, ensure_ascii=False))
    return 1 if problems else 0


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--csv", required=True, type=Path)
    ap.add_argument("--data", required=True, type=Path)
    a = ap.parse_args(argv)
    return run(a.csv, a.data)


if __name__ == "__main__":
    sys.exit(main())
