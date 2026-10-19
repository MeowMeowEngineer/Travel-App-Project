"""사이트 정보 품질 리포트 — '정보가 실제로 들어갔는가'를 매 라운드 같은 기준으로 잰다.

    python tools/quality_report.py --data data/incheon --out public
    python tools/quality_report.py --data data/incheon --out dist-preview --json   # 에이전트용
    python tools/quality_report.py --data data/incheon --out public --md docs/handover/quality_after.md

- 표준 라이브러리만 쓴다. 데이터와 빌드 결과(--out)만 읽고 아무것도 고치지 않는다.
- '화면에 나간 장소' = --out/places/<slug>/index.html 이 있는 장소. 데이터 전체가 아니라 사람이 보는 범위를 잰다.
- 판정 기준은 아래 상수에 모아 두었다. 기준을 바꾸면 전/후 비교가 깨지므로, 바꿀 때는 보고서에 적는다.
"""
from __future__ import annotations

import argparse
import datetime as dt
import json
import re
import sys
from collections import Counter, defaultdict
from pathlib import Path

if __package__ in (None, ""):
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from pipeline import city  # noqa: E402
from pipeline.schema import taut_pattern  # noqa: E402

# 실용 정보로 치는 facts 키(출처별 이름이 달라 묶어서 본다)
GROUPS = {
    "hours": ("usetime", "usetime_restdate", "opentime", "opentimefood", "usetimeculture", "usetimeleports"),
    "restdate": ("restdate", "usetime_restdate", "restdatefood", "restdateculture", "restdateleports"),
    "fee": ("usefee", "fee", "usefeeleports", "parkingfee"),
    "parking": ("parking", "parking_seats", "parkingfood", "parkinglodging", "parkingculture", "parkingleports", "accessible_parking"),
    "phone": ("tel", "infocenter", "infocenterfood", "infocenterlodging", "infocenterculture", "infocenterleports", "phone"),
    "homepage": ("homepage", "reservationurl"),
    "checkin": ("checkin", "checkintime"),
    "menu": ("menu", "firstmenu", "treatmenu"),
}
KIND_GROUPS = {  # 유형별로 '있어야 하는' 정보 — 빈칸률을 이 기준으로 본다
    "attraction": ("hours", "restdate", "fee", "parking", "phone"),
    "food": ("hours", "menu", "parking", "phone"),
    "stay": ("checkin", "parking", "phone", "homepage"),
}
CARD_FIELDS = ("usetime", "restdate", "usetime_restdate", "parking", "parking_seats", "menu")
CARD_MAX = 24            # 목록 카드 칩에서 잘리기 쉬운 길이(글자)
NON_PLACE = re.compile(r"(\s코스$|코스$|기본지식|탐방\s|안내서$)")
TAUT = taut_pattern   # the index rule's own pattern for the active city (pipeline/schema.py)
BANMAL = re.compile(r"(어|야|해|돼|래|까|니|지|줘|나)\?*$")
JONDAE = re.compile(r"(나요|까요|습니까|가요|인가요|세요|되나요|있나요|하나요)\?$")


def load(path: Path):
    return json.loads(path.read_text("utf-8")) if path.exists() else []


def sentences(text: str) -> list[str]:
    return [s for s in re.split(r"(?<=[.!?])\s+", (text or "").strip()) if s]


def has(facts: dict, group: str) -> bool:
    return any(str(facts.get(k) or "").strip() for k in GROUPS[group])


def allowed_photo(place: dict, allowed: set[str]) -> bool:
    return any(i.get("license") in allowed for i in place.get("images") or [])


def built_slugs(out: Path, section: str) -> set[str]:
    base = out / section
    return {d.name for d in base.iterdir() if d.is_dir() and (d / "index.html").exists()} if base.exists() else set()


def pct(a: int, b: int) -> str:
    return f"{a}/{b} ({round(100 * a / b)}%)" if b else "0/0"


def analyse(data: Path, out: Path, today: str) -> dict:
    site = load(data / "site.json") or {}
    city.activate(site)
    allowed = set((site.get("publish_rules") or {}).get("allowed_image_licenses") or ["KOGL-1", "KOGL-3"])
    places = [p for p in load(data / "places.json") if not p.get("duplicate_of")]
    shown = built_slugs(out, "places")
    live = [p for p in places if p.get("slug") in shown]
    rep: dict = {"today": today, "data_places": len(places), "shown_places": len(live), "kinds": {}}

    faq_q = defaultdict(list)
    hygiene = Counter()
    samples = defaultdict(list)
    for kind in sorted({p.get("kind") for p in live}):
        rows = [p for p in live if p.get("kind") == kind]
        c = Counter()
        for p in rows:
            f = p.get("facts") or {}
            c["geo"] += bool(p.get("geo"))
            c["photo"] += allowed_photo(p, allowed)
            c["tourapi"] += bool(p.get("tourapi"))
            for g in GROUPS:
                c[g] += has(f, g)
            ss = sentences(p.get("summary") or "")
            taut = bool(ss) and bool(re.match(TAUT(p.get("name", "")), ss[0]))
            c["summary_tautology_first"] += taut
            practical = any(has(f, g) for g in KIND_GROUPS.get(kind, ()))
            thin = (not practical) or (taut and len(ss) <= 1)
            c["thin"] += thin
            if thin and len(samples[f"thin_{kind}"]) < 5:
                samples[f"thin_{kind}"].append(p.get("name"))
            for q in p.get("faq") or []:
                faq_q[re.sub(r"\s+", " ", q.get("q", "")).strip()].append(p.get("slug"))
            addr = f.get("address") or ""
            if re.search(r"\s{2,}", addr):
                hygiene["address_multiple_spaces"] += 1
            if re.search(r"\b(\d+)\s+\1\b", addr):
                hygiene["address_repeated_number"] += 1
                samples["address_repeated_number"].append(addr.strip())
            ut, rd = str(f.get("usetime") or "").strip(), str(f.get("restdate") or "").strip()
            if ut and not re.search(r"\d", ut):
                hygiene["hours_without_digits"] += 1
                samples["hours_without_digits"].append(f"{p.get('name')}: {ut}")
            if ut and ut == rd:
                hygiene["hours_equals_restdate"] += 1
            for k in CARD_FIELDS:
                if len(str(f.get(k) or "")) > CARD_MAX:
                    hygiene["card_value_too_long"] += 1
            if NON_PLACE.search(p.get("name", "")):
                hygiene["suspected_non_place"] += 1
                samples["suspected_non_place"].append(p.get("name"))
            if p.get("fact_conflicts"):
                hygiene["fact_conflicts"] += 1
                samples["fact_conflicts"].append(p.get("name"))
        n = len(rows)
        rep["kinds"][kind] = {"n": n, **{k: c[k] for k in sorted(c)},
                              "need": {g: pct(c[g], n) for g in KIND_GROUPS.get(kind, ())}}

    qs = [q for q in faq_q for _ in faq_q[q]]
    style = Counter("존댓말" if JONDAE.search(q) else ("반말" if BANMAL.search(q) else "기타") for q in qs)
    dups = {q: s for q, s in faq_q.items() if len(set(s)) > 1}
    rep["faq"] = {"total": len(qs), "pages_with_faq": len({s for v in faq_q.values() for s in v}),
                  "style": dict(style), "duplicate_questions": len(dups),
                  "duplicate_examples": [f"{q} ×{len(set(s))}" for q, s in list(dups.items())[:5]]}

    courses = [c for c in load(data / "courses.json")]
    shown_courses = built_slugs(out, "courses")
    stops = linked = 0
    for c in courses:
        if c.get("slug") not in shown_courses:
            continue
        for s in c.get("stops") or []:
            stops += 1
            linked += bool(s.get("place_slug")) and s.get("place_slug") in shown
            if re.search(r"\s{2,}|[\r\n]", s.get("name") or ""):
                hygiene["course_stop_name_whitespace"] += 1
    rep["courses"] = {"shown": len(shown_courses), "stops": stops, "stops_linked_to_shown_page": pct(linked, stops)}

    events = load(data / "events.json")
    ev = Counter()
    for e in events:
        end, start = e.get("end_date") or "", e.get("start_date") or ""
        if not end and re.fullmatch(r"\d{4}-\d{2}", e.get("end_month") or ""):  # source says only '~10월'
            y, m = int(e["end_month"][:4]), int(e["end_month"][5:])
            end = (dt.date(y + m // 12, m % 12 + 1, 1) - dt.timedelta(days=1)).isoformat()
        if not start:
            ev["undated"] += 1
        elif (end or start) < today:
            ev["past"] += 1
        else:
            ev["upcoming"] += 1
    rep["events"] = {"total": len(events), **dict(ev)}
    guides = load(data / "guides.json")
    rep["guides"] = {"total": len(guides), "shown": len(built_slugs(out, "guides")),
                     "items": sum(len(g.get("items") or []) for g in guides)}
    rep["hygiene"] = dict(hygiene)
    rep["samples"] = {k: v[:5] for k, v in samples.items()}
    rep["status"] = dict(Counter(p.get("status") for p in places))
    return rep


def to_md(rep: dict) -> str:
    L = [f"# 정보 품질 리포트 ({rep['today']})", "",
         f"- 데이터 장소 {rep['data_places']}곳(중복 제외) · 화면에 나간 장소 {rep['shown_places']}곳 · 상태 {rep['status']}", ""]
    L += ["## 유형별 채움률(화면에 나간 장소 기준)", "", "| 유형 | 수 | 좌표 | 허용 사진 | 필수 정보 채움 | 얇은 페이지 | 요약 첫 문장이 '○○은 ○○시 ○○에 있는 ○○입니다' |", "|---|---|---|---|---|---|---|"]
    for k, v in rep["kinds"].items():
        need = " · ".join(f"{g} {s}" for g, s in v["need"].items())
        L.append(f"| {k} | {v['n']} | {pct(v.get('geo', 0), v['n'])} | {pct(v.get('photo', 0), v['n'])} | {need} | "
                 f"{pct(v.get('thin', 0), v['n'])} | {pct(v.get('summary_tautology_first', 0), v['n'])} |")
    f = rep["faq"]
    L += ["", "## FAQ", "", f"- 질문 {f['total']}개(페이지 {f['pages_with_faq']}곳) · 문체 {f['style']} · 여러 페이지에 같은 질문 {f['duplicate_questions']}건 {f['duplicate_examples']}"]
    L += ["", "## 코스·행사·가이드", "", f"- 코스 {rep['courses']}", f"- 행사 {rep['events']}", f"- 가이드 {rep['guides']}"]
    L += ["", "## 데이터 정리 필요", "", f"- {rep['hygiene']}"]
    for k, v in rep["samples"].items():
        L.append(f"  - {k}: {v}")
    return "\n".join(L) + "\n"


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--data", type=Path, default=Path("data/incheon"))
    ap.add_argument("--out", type=Path, default=Path("public"))
    ap.add_argument("--today", default=dt.date.today().isoformat())
    ap.add_argument("--json", action="store_true")
    ap.add_argument("--md", type=Path)
    a = ap.parse_args(argv)
    rep = analyse(a.data, a.out, a.today)
    if a.md:
        a.md.parent.mkdir(parents=True, exist_ok=True)
        a.md.write_text(to_md(rep), "utf-8")
    print(json.dumps(rep, ensure_ascii=False, indent=1) if a.json else to_md(rep))
    return 0


if __name__ == "__main__":
    sys.exit(main())
