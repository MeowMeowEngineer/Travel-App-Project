"""검수 시트(CSV) 만들기 — 사람이 판정(OK/수정)과 메모를 적고, tools/apply_review.py가 그 표시만 반영한다.

    python tools/make_review_sheet.py --data data/incheon --out docs/handover/review_round3.csv
    python tools/make_review_sheet.py --data data/incheon --base https://preview.example   # 기본: site.json site_url

- 대상(한 줄에 하나): full 장소(tier=full, duplicate_of 없음) · 가이드 전부 · 코스 전부 · 행사 전부.
- 열: 구분, ID, 이름, 미리보기 URL, 핵심 사실, 출처 링크, 현재 상태, 판정(빈칸), 메모(빈칸).
- 데이터를 읽기만 한다. 상태·검수일을 바꾸거나 공개를 결정하지 않는다(CLAUDE.md 3절 7항).
- 파일은 UTF-8 BOM(엑셀에서 한글이 깨지지 않음)이고, 같은 데이터면 같은 파일이 나온다(날짜·시각을 넣지 않음).
- slug가 없는 레코드는 pipeline.build와 같은 규칙(이름 → slugify, 겹치면 -2, -3)으로 만든다.
"""
from __future__ import annotations

import argparse
import csv
import json
import sys
from pathlib import Path
from urllib.parse import quote, urlsplit

if __package__ in (None, ""):
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from pipeline.build import _unique_slugs, guide_has_content
from pipeline.schema import FACT_ALIASES, FACT_LABELS, KEY_FACTS
from pipeline.textutil import first_sentence, squash_ws

DEFAULT_BASE = ""   # the region's site.json site_url (site_base)


def site_base(data: Path) -> str:
    """The address the sheet's page links start with: the region's site.json site_url."""
    try:
        return str(json.loads((Path(data) / "site.json").read_text("utf-8")).get("site_url") or "")
    except (OSError, ValueError):
        return ""
HEADERS = ("구분", "ID", "이름", "미리보기 URL", "핵심 사실", "출처 링크", "현재 상태", "판정", "메모")
# 구분 -> (데이터 파일, 이름 키). apply_review.py도 이 표로 레코드를 찾는다.
KINDS = {"장소": ("places.json", "name"), "가이드": ("guides.json", "title"),
         "코스": ("courses.json", "name"), "행사": ("events.json", "name")}
# 장소의 '핵심 사실'로 보여 줄 facts 키(있는 것만, 이 순서로)
SHEET_FACTS = ("address", "usetime", "restdate", "usetime_restdate", "usefee", "menu", "treatmenu",
               "checkin", "checkout", "roomcount", "parking", "parking_seats", "parkingfee", "infocenter", "homepage")
EXTRA_LABELS = {"treatmenu": "취급 메뉴", "roomcount": "객실 수"}
KIND_ORDER = {"attraction": 0, "food": 1, "stay": 2}


def load(data: Path, name: str) -> list[dict]:
    path = data / name
    return json.loads(path.read_text("utf-8")) if path.exists() else []


def _lines(*parts) -> str:
    out = []
    for part in parts:
        if part and part not in out:
            out.append(part)
    return "\n".join(out)


def _summary_line(item: dict) -> str:
    return first_sentence(item.get("summary"), limit=400) or "요약 없음"


def _status(item: dict) -> str:
    reviewed = item.get("reviewed_at") or "없음"
    return f"{item.get('status') or '상태 없음'} (reviewed_at {reviewed})"


def _provider(place: dict, key: str) -> str:
    src = (place.get("fact_sources") or {}).get(key) or {}
    provider = src.get("provider") or (place.get("facts_source") or {}).get("provider") or "출처 미기록"
    return f"{provider}; 일치 확인 {src['confirmed_by']}" if src.get("confirmed_by") else provider


def place_facts(place: dict) -> str:
    facts = place.get("facts") or {}
    alts = place.get("fact_alternatives") or {}
    rows = [_summary_line(place)]
    for key in SHEET_FACTS:
        value = squash_ws(str(facts.get(key) or ""))
        if not value:
            continue
        label = FACT_LABELS.get(key) or EXTRA_LABELS.get(key) or key
        rows.append(f"{label}: {value} ({_provider(place, key)})")
        for alt in alts.get(key) or []:
            rows.append(f"  └ 다른 출처 값: {squash_ws(str(alt.get('value') or ''))} ({alt.get('provider') or '출처 미기록'})")
    wanted = dict.fromkeys(KEY_FACTS.get(place.get("kind"), ()) + ("infocenter",))
    missing = [key for key in wanted if not facts.get(key) and not any(facts.get(a) for a in FACT_ALIASES.get(key, ()))]
    if missing:
        rows.append("데이터 없음: " + "·".join(FACT_LABELS[k] for k in missing))
    return "\n".join(rows)


def place_sources(place: dict) -> str:
    original, official = place.get("original") or {}, place.get("official") or {}
    urls = [original.get("source_url"), official.get("source_url"), official.get("visitkorea_url"), official.get("homepage")]
    urls += [src.get("url") for src in (place.get("fact_sources") or {}).values() if isinstance(src, dict)]
    cid = (place.get("tourapi") or {}).get("contentid")
    return _lines(*urls, f"TourAPI contentid {cid}" if cid else "")


def guide_facts(guide: dict, place_by_slug: dict) -> str:
    names = []
    for item in guide.get("items") or []:
        target = place_by_slug.get(item.get("place_slug"))
        names.append(target["name"] if target else f"{squash_ws(item.get('name') or item.get('place_slug') or '이름 없음')}(연결 없음)")
    places = f"추천 장소 {len(names)}곳" + (": " + ", ".join(names) if names else "")
    return _lines(_summary_line(guide), places, f"본문 {len(guide.get('body') or [])}단락 · FAQ {len(guide.get('faq') or [])}개")


def course_facts(course: dict, place_by_slug: dict) -> str:
    stops = course.get("stops") or []
    linked = [s for s in stops if s.get("place_slug") in place_by_slug]
    unlinked = [squash_ws(s.get("name") or "") for s in stops if s.get("place_slug") not in place_by_slug]
    rows = [_summary_line(course), f"경유지 {len(stops)}곳 · 장소 연결 {len(linked)}곳"]
    if unlinked:
        rows.append("연결 안 된 경유지: " + ", ".join(unlinked))
    return "\n".join(rows)


def event_facts(event: dict) -> str:
    start, end = event.get("start_date") or "", event.get("end_date") or ""
    dates = f"{start} ~ {end}" if start and end and start != end else (start or end)
    period = squash_ws(event.get("period_text") or "")
    when = f"기간: {dates}" if dates else (f"기간: {period} (시작·종료일 없음)" if period else "기간: 없음")
    rows = [when, f"장소: {squash_ws(event.get('place_name') or event.get('address') or '') or '없음'}"]
    if event.get("summary"):
        rows.insert(0, _summary_line(event))
    return "\n".join(rows)


def event_sources(event: dict) -> str:
    cid = event.get("contentid")
    return _lines(event.get("source_url"), f"TourAPI contentid {cid}" if cid else "")


def preview_url(base: str, path: str) -> str:
    return base.rstrip("/") + quote(path, safe="/")


def make_rows(data: Path, base: str = DEFAULT_BASE) -> list[dict]:
    places, guides = load(data, "places.json"), load(data, "guides.json")
    courses, events = load(data, "courses.json"), load(data, "events.json")
    _unique_slugs(places, "name")      # same rule as pipeline.build (in memory only)
    _unique_slugs(guides, "title")
    _unique_slugs(courses, "name")
    place_by_slug = {p["slug"]: p for p in places if not p.get("duplicate_of")}
    rows = []

    def row(kind: str, item: dict, url: str, facts: str, sources: str) -> None:
        rows.append({"구분": kind, "ID": item.get("id") or "", "이름": item.get(KINDS[kind][1]) or "",
                     "미리보기 URL": url, "핵심 사실": facts, "출처 링크": sources,
                     "현재 상태": _status(item), "판정": "", "메모": ""})

    full = [p for p in places if p.get("tier") == "full" and not p.get("duplicate_of")]
    for p in sorted(full, key=lambda p: (KIND_ORDER.get(p.get("kind"), 9), p.get("name") or "", p.get("id") or "")):
        row("장소", p, preview_url(base, f"/places/{p['slug']}/"), place_facts(p), place_sources(p))
    for g in guides:
        url = preview_url(base, f"/guides/{g['slug']}/")
        if not guide_has_content(g):
            url += "\n(본문이 없어 미리보기에 없음)"
        row("가이드", g, url, guide_facts(g, place_by_slug),
            _lines(*[s.get("url") for s in g.get("sources") or [] if isinstance(s, dict)]))
    for c in courses:
        row("코스", c, preview_url(base, f"/courses/{c['slug']}/"), course_facts(c, place_by_slug),
            _lines((c.get("original") or {}).get("source_url")))
    for e in sorted(events, key=lambda e: (e.get("start_date") or "9999", e.get("name") or "", e.get("id") or "")):
        row("행사", e, preview_url(base, "/events/"), event_facts(e), event_sources(e))
    return rows


def write_sheet(rows: list[dict], out: Path) -> None:
    out.parent.mkdir(parents=True, exist_ok=True)
    with out.open("w", encoding="utf-8-sig", newline="") as fh:
        writer = csv.DictWriter(fh, fieldnames=HEADERS)
        writer.writeheader()
        writer.writerows(rows)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--data", default=Path("data/incheon"), type=Path)
    parser.add_argument("--out", default=Path("docs/handover/review_round3.csv"), type=Path)
    parser.add_argument("--base", default=DEFAULT_BASE, help="미리보기 주소(기본: 지역 site.json의 site_url)")
    args = parser.parse_args(argv)
    args.base = args.base or site_base(args.data)
    parsed = urlsplit(args.base)
    if parsed.scheme not in ("http", "https") or not parsed.netloc or parsed.username or parsed.query or parsed.fragment:
        parser.error("--base는 인증정보·쿼리·fragment 없는 http(s) 주소여야 합니다")
    rows = make_rows(args.data, args.base)
    write_sheet(rows, args.out)
    counts = {kind: sum(r["구분"] == kind for r in rows) for kind in KINDS}
    print(f"검수 시트: {args.out} ({len(rows)}행 — " + ", ".join(f"{k} {n}" for k, n in counts.items()) + ")")
    print("판정 칸에 OK 또는 수정, 메모 칸에 고칠 내용을 적은 뒤 "
          f"`python tools/apply_review.py --sheet {args.out}`로 미리 보고 --apply로 반영합니다.")
    print("이 시트는 공개 결정이 아닙니다. OK 행만 status=reviewed가 되고 published는 사람이 따로 정합니다.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
