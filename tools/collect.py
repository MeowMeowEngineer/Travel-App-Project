"""TourAPI 수집 한 번에 — 키 확인 → 연결·지역 코드 진단 → 목록·좌표·사진 → 행사 → 상세 → TourAPI에만 있는 장소
→ 결과 요약과 다음 명령.

    python tools/collect.py --data data/incheon                        # 실행당 호출 상한 900
    python tools/collect.py --data data/incheon --max-calls 400
    python tools/collect.py --data data/incheon --districts 연수구,강화군   # 광역시에서 일부 구·군만
    python tools/collect.py --data data/incheon --offline               # 키·네트워크 없이 캐시로만 다시 만든다

1. 키: 환경 변수 TOURAPI_KEY, 없으면 지금 폴더(저장소 루트)의 .env. 없으면 곧바로 멈추고 어디에 넣는지 알려 준다.
   키 값은 어디에도 출력하지 않는다(모든 출력에서 원문·인코딩 형태를 가림). 공급자 오류 메시지는 키만 가리고 그대로 보인다.
2. 진단(tools/tourapi_doctor.py): 키·네트워크·서비스, 그리고 site.json region_full의 법정동 시도 코드와 그 아래
   시군구(구·군) 코드를 TourAPI(ldongCode2)에서 받아 보여 준다. 실패하면 수집하지 않는다.
3. 수집(tools/tourapi_bulk.py --details --add-new --events): 구·군마다 지역 목록(areaBasedList2: 관광지·문화시설·
   레포츠·쇼핑·숙박·음식점, 모든 쪽) → 기존 장소 매칭·좌표·사진(공공누리 제1·3유형만, '출처: 한국관광공사') → 행사
   (searchFestival2, 오늘부터) → 상세(detailCommon2·detailIntro2, 관광지·레포츠는 detailInfo2도: 전화·이용시간·
   쉬는 날·요금·주차·체크인, 필드마다 출처·확인일) → TourAPI에만 있는 장소(draft). overview는 사실 확인용으로만
   tourapi.overview에 두고 화면에 내지 않는다.
   쓰는 파일: <data>/places.json, <data>/events.json, data/cache/tourapi/(응답 캐시, 커밋 안 함),
   reports/tourapi_bulk.md·.json, reports/collect.md·.json.
4. 요약(장소·구·군·좌표·사진·방문 판단 정보 채움·행사·남은 호출)과 다음 명령(빌드·검증·공개 승인)을 출력한다.

호출 상한(--max-calls, 기본 900 — 공공데이터포털 개발계정 일일 한도 안)은 진단 호출을 포함한 이번 실행 전체의 실호출
수다. 상한에 걸리면 받은 데까지 쓰고 멈춘다. 같은 명령을 다시 실행하면 캐시에 있는 응답은 호출 없이 쓰고 나머지를
이어 받는다(다음 날 다시 — 일일 한도).

종료 코드: 0 끝까지 받음 · 3 호출 상한·공급자 한도로 멈춤(같은 명령을 다시 실행) · 2 키 없음 · 1 진단·수집 오류
"""
from __future__ import annotations

import argparse
import datetime as dt
import json
import os
import re
import sys
from pathlib import Path

if __package__ in (None, ""):
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from pipeline.enrich import load_dotenv
from pipeline.tourapi import TourAPIError, TourAPIStopError, normalize_key, redact
from tools import tourapi_bulk as bulk
from tools import tourapi_doctor as doctor

DEFAULT_MAX_CALLS = 900
NO_KEY = ("TOURAPI_KEY가 없습니다. 공공데이터포털 '한국관광공사_국문 관광정보 서비스_GW' 일반 인증키(Encoding·Decoding "
          "어느 쪽이든)를 다음 중 한 곳에 넣고 다시 실행하세요.\n"
          "  ① 환경 변수: export TOURAPI_KEY=발급받은키   (Windows PowerShell: $env:TOURAPI_KEY=\"발급받은키\")\n"
          "  ② 저장소 루트의 .env 파일: cp .env.example .env 한 뒤 TOURAPI_KEY= 뒤에 키를 붙여 넣기 "
          "(.env는 .gitignore에 있어 커밋되지 않습니다)\n"
          "키 값은 코드·문서·커밋 메시지에 쓰지 않습니다. 키 없이 캐시로만 다시 만들려면 --offline.")
# The visit-decision facts a place page leads with (CLAUDE.md 1절), as fact keys -> labels
VISIT_FACTS = (("infocenter", "전화"), ("usetime", "이용시간"), ("restdate", "쉬는 날"), ("usefee", "요금"),
               ("parking", "주차"), ("checkin", "체크인"))
KIND_LABELS = {"attraction": "관광지", "food": "음식점", "stay": "숙소"}


def key_forms(raw: str) -> list[str]:
    """Every form of the key the output must not show (raw, decoded; redact() adds the URL-encoded ones)."""
    raw = (raw or "").strip().strip('"').strip("'")
    return [k for k in dict.fromkeys((raw, normalize_key(raw))) if k]


def masker(raw: str):
    secrets = key_forms(raw)

    def mask(text) -> str:
        out = str(text if text is not None else "")
        for key in secrets:
            out = redact(out, key)
        return out
    return mask


def _load(path: Path) -> list:
    try:
        value = json.loads(path.read_text("utf-8"))
    except (OSError, ValueError):
        return []
    return value if isinstance(value, list) else []


def data_summary(data: Path, today: str) -> dict:
    """What the collection wrote: places by kind and 구·군, coordinates, photos by licence, visit facts that carry
    their own source, festivals still to come."""
    from pipeline import city
    places = [p for p in _load(data / "places.json") if not p.get("duplicate_of") and not p.get("exclude")]
    C = city.current()
    events = _load(data / "events.json")
    images = {"KOGL-1": 0, "KOGL-3": 0}
    with_photo = 0
    for p in places:
        tour = [i for i in p.get("images") or [] if i.get("source") == "TourAPI"]
        with_photo += bool(tour)
        for i in tour[:1]:
            images[i.get("license")] = images.get(i.get("license"), 0) + 1
    facts = {}
    for key, label in VISIT_FACTS:
        have = [p for p in places if (p.get("facts") or {}).get(key)]
        sourced = [p for p in have if ((p.get("fact_sources") or {}).get(key) or {}).get("checked_at")]
        facts[label] = {"places": len(have), "with_source": len(sourced)}
    districts: dict[str, int] = {}
    for p in places:
        d = C.district_of((p.get("facts") or {}).get("address"), p.get("district", "")) or "구·군 미상"
        districts[d] = districts.get(d, 0) + 1
    kinds: dict[str, int] = {}
    for p in places:
        kinds[p.get("kind", "")] = kinds.get(p.get("kind", ""), 0) + 1
    upcoming = [e for e in events if (e.get("end_date") or e.get("start_date") or "") >= today]
    return {"places": len(places), "kinds": kinds, "districts": districts,
            "geo": sum(1 for p in places if (p.get("geo") or {}).get("lat") is not None),
            "with_photo": with_photo, "first_photo_license": images, "visit_facts": facts,
            "drafts": sum(1 for p in places if p.get("status") == "draft"),
            "events": len(events), "events_upcoming": len(upcoming)}


def next_commands(data: str, today: str, stopped: bool, max_calls: int, extra: str) -> list[str]:
    again = f"python tools/collect.py --data {data} --max-calls {max_calls}{extra}"
    lines = []
    if stopped:
        lines.append(f"0. 이어 받기: {again}   ← 캐시에 있는 응답은 호출 없이 쓰고 나머지를 받는다"
                     "(일일 한도가 남았으면 바로, 다 썼으면 다음 날)")
    lines += [
        f"1. 미리보기 빌드·검증: python -m pipeline.build --data {data} --out dist-preview --mode preview && "
        f"python -m pipeline.validate --data {data} --out dist-preview --mode preview",
        "   열어 보기: python -m http.server -d dist-preview 8000   (draft까지 보이고 전부 noindex)",
        "2. 요약 쓰기(CLAUDE.md 3절 5항): 새 장소는 요약이 비어 있다 — 요약이 생겨야 공개 선별·색인 대상이 된다.",
        f"3. 공개 선별 미리보기: python tools/build_review.py --data {data} --out dist-review --report-dir reports",
        f"4. 운영자 공개 승인(사람): python tools/approve_publication.py --data {data} --date {today}   "
        "← 미리 보기, 운영자가 정하면 --apply",
        f"5. 공개 빌드·검증: python tools/build_public.py --data {data} --out public   "
        "(site_url이 자리표시인 동안은 검증이 막는다 — 도메인은 운영자가 정한다)",
    ]
    return lines


def summary_lines(stats: dict, summary: dict, doctor_calls: int, max_calls: int) -> list[str]:
    s, rc = summary, stats.get("region_codes") or {}
    lines = []
    if rc.get("lDongRegnCd"):
        lines.append(f"- 지역 코드(TourAPI ldongCode2, 실행 때 받음): 시도 {rc['lDongRegnCd']} · 구·군 "
                     + ", ".join(f"{d['code']} {d['name']}" for d in rc.get("signgu") or []))
    for note in stats.get("region_notes") or []:
        lines.append(f"- 확인: {note}")
    sizes = stats.get("list_sizes") or {}
    if sizes:
        names = {"12": "관광지", "14": "문화시설", "28": "레포츠", "38": "쇼핑", "32": "숙박", "39": "음식점"}
        lines.append("- 목록 크기(구·군별): " + " / ".join(
            f"{d} " + "·".join(f"{names.get(t, t)} {n}" for t, n in sorted(v.items())) for d, v in sizes.items()))
    kinds = " · ".join(f"{KIND_LABELS.get(k, k)} {n}" for k, n in sorted(s["kinds"].items()))
    lines.append(f"- 장소 {s['places']}곳({kinds or '없음'}) · draft {s['drafts']} — 구·군: "
                 + (", ".join(f"{d} {n}" for d, n in sorted(s["districts"].items())) or "없음"))
    lines.append(f"- 좌표 {s['geo']}곳 · 사진 {s['with_photo']}곳(대표 사진 제1유형 {s['first_photo_license'].get('KOGL-1', 0)}"
                 f" · 제3유형 {s['first_photo_license'].get('KOGL-3', 0)}; 제2·4유형·유형 없음은 받지 않음 "
                 f"{stats.get('image_other_type', 0)}곳)")
    lines.append("- 방문 판단 정보(필드별 출처·확인일): " + " · ".join(
        f"{label} {v['places']}" + ("" if v["with_source"] == v["places"] else f"(출처 있음 {v['with_source']})")
        for label, v in s["visit_facts"].items()))
    ev = stats.get("events") or {}
    lines.append(f"- 행사 {s['events']}건(오늘 이후 진행 {s['events_upcoming']}건) — searchFestival2 "
                 f"{ev.get('from', '')}부터 응답 {ev.get('festival_items', 0)}건")
    det, new = stats.get("details") or {}, stats.get("new_places") or {}
    errors = len(det.get("errors") or []) + len(new.get("errors") or []) + len(ev.get("errors") or [])
    lines.append(f"- 이번 실행: 실호출 {stats.get('live_calls', 0) + doctor_calls}(진단 {doctor_calls} 포함) · "
                 f"캐시 {stats.get('cache_hits', 0)} · 새 장소 {len(new.get('added') or [])} · 중복 의심 보류 "
                 f"{len(new.get('held_duplicate_candidates') or [])} · 기존 장소 상세 갱신 {det.get('done', 0)}곳 · "
                 f"항목 오류 {errors}")
    rem = stats.get("remaining_calls") or {}
    if rem:
        ev_left = "행사 목록을 아직 못 받음" if rem.get("events") is None else f"행사 {rem.get('events', 0)}"
        lines.append(f"- 남은 호출(캐시에 없는 응답): 약 {rem.get('total', 0)}회 — 상세 {rem.get('details', 0)} · "
                     f"새 장소 {rem.get('new_places', 0)} · {ev_left}" + (f" · 사진 {rem['gallery']}" if rem.get("gallery") else ""))
    if stats.get("stopped"):
        lines.append(f"- 멈춤: {stats['stopped']} (이번 실행 상한 {max_calls}회 = 진단 {doctor_calls} + 수집 "
                     f"{max(1, max_calls - doctor_calls)})")
    return lines


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--data", type=Path, default=Path("data/incheon"))
    ap.add_argument("--max-calls", type=int, default=DEFAULT_MAX_CALLS,
                    help="이번 실행의 실호출 상한(진단 포함, 기본 900)")
    ap.add_argument("--districts", default="", help="광역시에서 이 구·군만(쉼표로, 예: 연수구,강화군)")
    ap.add_argument("--events-from", default="", help="행사를 이 날짜(YYYYMMDD)부터(기본: 오늘)")
    ap.add_argument("--gallery", action="store_true", help="장소마다 detailImage2로 허용 사진 더 받기(장소당 1회)")
    ap.add_argument("--offline", action="store_true", help="네트워크 없이 캐시로만(키 없이)")
    a = ap.parse_args(argv)
    if a.max_calls < 1:
        ap.error("--max-calls는 1 이상")
    if a.events_from and not re.fullmatch(r"\d{8}", a.events_from):
        ap.error("--events-from은 YYYYMMDD")

    load_dotenv(Path(".env"))
    raw = os.environ.get("TOURAPI_KEY", "").strip().strip('"').strip("'")
    mask = masker(raw)

    def say(text: str = "", err: bool = False) -> None:
        print(mask(text), file=sys.stderr if err else sys.stdout, flush=True)

    if not a.offline and not raw:
        say(f"중단: {NO_KEY}", err=True)
        return 2
    site = doctor.load_site(a.data)
    if site is None:
        say(f"중단: {a.data / 'site.json'}을 읽을 수 없습니다 — --data에 지역 데이터 폴더(예: data/incheon)를 주세요.", err=True)
        return 1
    today = dt.date.today().isoformat()
    only = [x.strip() for x in a.districts.split(",") if x.strip()] or None

    region = None
    used = 0
    if not a.offline:
        say("== 1. TourAPI 연결·지역 코드 진단 ==")
        keyword = str((site.get("tourapi") or {}).get("region_keyword") or site.get("region") or "관광")
        rep = doctor.run(keyword, raw, site)
        for line in doctor.report_lines(rep):
            say(line)
        region, used = rep.get("region"), int(rep.get("calls") or 0)
        if not str(rep.get("verdict", "")).startswith("정상"):
            say(f"중단: 진단을 통과하지 못해 수집하지 않습니다 — {rep.get('verdict', '')}", err=True)
            return 1
        if used >= a.max_calls:
            say(f"중단: 호출 상한 {a.max_calls}회를 진단이 다 썼습니다(진단 {used}회). --max-calls를 늘리세요.", err=True)
            return 3

    say("== 2. 수집(목록·좌표·사진 → 행사 → 상세 → TourAPI에만 있는 장소) ==")
    try:
        stats = bulk.run(a.data, max(1, a.max_calls - used), a.offline, gallery=a.gallery, details=True,
                         add_new=True, events=True, districts=only, events_from=a.events_from or None, echo=False)
    except TourAPIStopError as err:   # the cap or the provider's quota during the list phase: nothing to write yet
        say(f"멈춤: {err} — 받은 목록은 캐시에 있습니다. 같은 명령을 다시 실행하면 이어서 받습니다.", err=True)
        return 3
    except bulk.RegionError as err:
        say(f"중단: {err}", err=True)
        return 1
    except TourAPIError as err:   # provider message as given, key masked (the client masks it; say() again)
        say(f"중단: {err}", err=True)
        return 1

    summary = data_summary(a.data, today)
    lines = summary_lines(stats, summary, used, a.max_calls)
    extra = (f" --districts {a.districts}" if only else "") + (" --gallery" if a.gallery else "")
    steps = next_commands(str(a.data).replace(os.sep, "/"), today, bool(stats.get("stopped")), a.max_calls, extra)
    say("== 3. 결과 ==")
    for line in lines:
        say(line)
    say(f"- 쓴 파일: {a.data / 'places.json'}, {a.data / 'events.json'}, reports/tourapi_bulk.md, reports/collect.md")
    say("")
    say("== 다음 명령 ==")
    for line in steps:
        say(line)
    report = Path("reports")
    report.mkdir(exist_ok=True)
    md = [f"# TourAPI 수집 ({today})", "", *lines, "", "## 다음 명령", "", *steps, ""]
    (report / "collect.md").write_text(mask("\n".join(md)), "utf-8")
    (report / "collect.json").write_text(mask(json.dumps(
        {"date": today, "summary": summary, "region": region, "max_calls": a.max_calls, "doctor_calls": used,
         "live_calls": stats.get("live_calls", 0), "cache_hits": stats.get("cache_hits", 0),
         "list_sizes": stats.get("list_sizes"), "region_codes": stats.get("region_codes"),
         "remaining_calls": stats.get("remaining_calls"), "stopped": stats.get("stopped", "")},
        ensure_ascii=False, indent=1)) + "\n", "utf-8")
    return 3 if stats.get("stopped") else 0


if __name__ == "__main__":
    sys.exit(main())
