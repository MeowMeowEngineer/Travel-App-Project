"""Phase: match entities to TourAPI and fill facts / geo / nearby / images (and events).

    python -m pipeline.enrich --data data/gunsan                 # all entities
    python -m pipeline.enrich --data data/gunsan --tier full     # full tier first (quota)
    python -m pipeline.enrich --data data/gunsan --limit 3       # smoke test
    python -m pipeline.enrich --data data/gunsan --events        # also collect events nearby
    python -m pipeline.enrich --data data/gunsan --offline       # cache only, no network
    python -m pipeline.enrich --data data/gunsan --refresh       # ignore cache (weekly re-check)

Rules
- Values come from TourAPI as-is (HTML stripped). Nothing is guessed.
- Fields listed in an entity's "locks" (e.g. ["facts", "geo"]) are never overwritten.
- A backup of places.json is written before saving.
- Outputs: places.json (updated), unmatched.csv, reports/enrich_report.md
"""
from __future__ import annotations

import argparse
from copy import deepcopy
import csv
import datetime as dt
import json
import math
import os
import re
import shutil
import sys
from difflib import SequenceMatcher
from pathlib import Path

from .schema import TOURAPI_LICENSE_MAP, license_allowed
from .textutil import extract_url, normalize_name, strip_html
from .tourapi import (CONTENT_TYPES, DEFAULT_MAX_CALLS, INTRO_FIELDS, KIND_BY_TYPE, TourAPI, TourAPIError,
                      TourAPIStopError, from_site_config)

MATCH_THRESHOLD = 0.75


def load_dotenv(path: Path) -> None:
    """Tiny .env loader (KEY=VALUE lines) so no extra dependency is needed."""
    if not path.exists():
        return
    for line in path.read_text("utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        k, v = line.split("=", 1)
        os.environ.setdefault(k.strip(), v.strip().strip('"').strip("'"))


def haversine_m(lat1: float, lng1: float, lat2: float, lng2: float) -> float:
    r = 6371000.0
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dp, dl = math.radians(lat2 - lat1), math.radians(lng2 - lng1)
    a = math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return 2 * r * math.asin(math.sqrt(a))


def _num(v) -> float | None:
    try:
        return float(v)
    except (TypeError, ValueError):
        return None


def score_candidate(name: str, cand: dict, region_kw: str = "", geo: dict | None = None) -> float:
    a, b = normalize_name(name), normalize_name(cand.get("title", ""))
    rk = normalize_name(region_kw)
    if rk:
        a, b = a.removeprefix(rk), b.removeprefix(rk)
    if not a or not b:
        return 0.0
    if a == b:
        s = 1.0
    elif a in b or b in a:
        s = 0.85
    else:
        s = SequenceMatcher(None, a, b).ratio() * 0.9
    if region_kw and region_kw not in (cand.get("addr1") or ""):
        s -= 0.5  # outside the region: almost certainly a different place
    if geo and geo.get("lat") is not None and _num(cand.get("mapy")) is not None:
        d = haversine_m(geo["lat"], geo["lng"], _num(cand["mapy"]), _num(cand["mapx"]))
        if d < 300:
            s += 0.1
        elif d > 5000:
            s -= 0.3
    return round(s, 3)


def _rank(name: str, cands: list[dict], region_kw: str, geo: dict | None) -> list[tuple[float, dict]]:
    return sorted(((score_candidate(name, c, region_kw, geo), c) for c in cands), key=lambda x: x[0], reverse=True)


def match_entity(api: TourAPI, e: dict, region_kw: str) -> tuple[dict | None, float, list[tuple[float, dict]]]:
    cands = api.search_keyword(e["name"])
    scored = _rank(e["name"], cands, region_kw, e.get("geo"))
    # Second query with the region prefix only when the first one is not good enough (saves quota).
    if (not scored or scored[0][0] < MATCH_THRESHOLD) and region_kw and region_kw not in e["name"]:
        more = [c for c in api.search_keyword(f"{region_kw} {e['name']}") if c not in cands]
        scored = _rank(e["name"], cands + more, region_kw, e.get("geo"))
    if scored and scored[0][0] >= MATCH_THRESHOLD:
        return scored[0][1], scored[0][0], scored
    return None, (scored[0][0] if scored else 0.0), scored


def _intro_facts(intro: dict, ctype: str) -> dict:
    facts = {}
    for key, by_type in INTRO_FIELDS.items():
        field = by_type.get(ctype)
        if field and intro.get(field):
            val = strip_html(intro[field])
            if val:
                facts[key] = val
    return facts


def _fee_from_info(rows: list[dict]) -> str:
    for r in rows:
        name = re.sub(r"\s", "", r.get("infoname") or "")
        if re.search(r"요금|입장료|관람료", name):
            return strip_html(r.get("infotext"))
    return ""


def fill_entity(api: TourAPI, e: dict, site: dict, by_contentid: dict, today: str) -> None:
    locks = set(e.get("locks") or [])
    t = e.setdefault("tourapi", {})
    cid, ctype = str(t["contentid"]), str(t.get("contenttypeid") or "")
    common = api.detail_common(cid)
    if not ctype:
        ctype = str(common.get("contenttypeid") or "")
        t["contenttypeid"] = ctype
    t["title"] = common.get("title", t.get("title", ""))
    t["overview"] = strip_html(common.get("overview"))  # reference for writing summaries; not displayed
    t["modifiedtime"] = common.get("modifiedtime", "")

    lat, lng = _num(common.get("mapy")), _num(common.get("mapx"))
    if "geo" not in locks and lat is not None and lng is not None:
        e["geo"] = {"lat": lat, "lng": lng, "source": "TourAPI"}

    facts = {}
    addr = " ".join(x for x in (strip_html(common.get("addr1")), strip_html(common.get("addr2"))) if x)
    if addr:
        facts["address"] = addr
    homepage = extract_url(common.get("homepage"))
    if homepage:
        facts["homepage"] = homepage
        e.setdefault("official", {}).setdefault("homepage", homepage)
    facts.update(_intro_facts(api.detail_intro(cid, ctype), ctype) if ctype else {})
    if ctype == "12" and "usefee" not in facts:
        fee = _fee_from_info(api.detail_info(cid, ctype))
        if fee:
            facts["usefee"] = fee
    if "infocenter" not in facts and common.get("tel"):
        facts["infocenter"] = strip_html(common["tel"])
    if "facts" not in locks:
        merged = dict(e.get("facts") or {})
        merged.update(facts)
        e["facts"] = merged
        e["facts_source"] = {"provider": "한국관광공사 TourAPI", "contentid": cid, "checked_at": today}

    # Image: only licence types allowed by site.json (default KOGL-1/KOGL-3)
    allowed = site.get("publish_rules", {}).get("allowed_image_licenses")
    code = TOURAPI_LICENSE_MAP.get(str(common.get("cpyrhtDivCd") or ""), "UNKNOWN")
    if "images" not in locks and common.get("firstimage"):
        others = [i for i in (e.get("images") or []) if i.get("source") != "TourAPI"]
        tour_img = []
        if license_allowed(code, allowed):
            tour_img = [{"url": common["firstimage"], "alt": e["name"], "credit": "한국관광공사",
                         "license": code, "source": "TourAPI"}]
        e["images"] = others + tour_img

    # Nearby (one call, grouped by kind). Straight-line distance from TourAPI coordinates.
    if "nearby" not in locks and e.get("geo"):
        tconf = site.get("tourapi") or {}
        radius = int(tconf.get("nearby_radius_m", 2000))
        per_kind = int(tconf.get("nearby_per_kind", 3))
        items = api.location_based(e["geo"]["lat"], e["geo"]["lng"], radius=radius)
        groups: dict[str, list] = {"attraction": [], "stay": [], "food": []}
        self_name = normalize_name(e["name"])
        for it in items:
            icid, ict = str(it.get("contentid")), str(it.get("contenttypeid"))
            kind = KIND_BY_TYPE.get(ict)
            if not kind or icid == cid or normalize_name(it.get("title")) == self_name:
                continue
            if len(groups[kind]) >= per_kind:
                continue
            target = by_contentid.get(icid)
            groups[kind].append({
                "name": it.get("title", ""),
                "kind": kind,
                "type_label": CONTENT_TYPES.get(ict, ""),
                "distance_m": int(_num(it.get("dist")) or 0),
                "contentid": icid,
                "internal_slug": target.get("slug", "") if target else "",
                "address": strip_html(it.get("addr1")),
            })
        e["nearby"] = groups["attraction"] + groups["stay"] + groups["food"]
        e["nearby_source"] = {"provider": "한국관광공사 TourAPI 위치기반", "radius_m": radius,
                              "distance_basis": "직선거리", "checked_at": today}


def collect_events(api: TourAPI, site: dict, existing: list[dict], today: str) -> list[dict]:
    center = site.get("center") or {}
    if center.get("lat") is None:
        raise TourAPIError("site.json의 center(lat,lng)가 비어 있어 행사 수집을 할 수 없습니다")
    items = api.location_based(center["lat"], center["lng"], radius=20000, content_type_id="15", rows=100)
    by_cid = {str(ev.get("contentid")): ev for ev in existing if ev.get("contentid")}
    out = list(existing)
    for it in items:
        cid = str(it.get("contentid"))
        if cid in by_cid:
            continue
        intro = api.detail_intro(cid, "15")
        start, end = intro.get("eventstartdate", ""), intro.get("eventenddate", "")
        if not start:
            continue
        iso = lambda d: f"{d[:4]}-{d[4:6]}-{d[6:8]}" if len(d) == 8 else d
        out.append({
            "id": f"event-{cid}", "contentid": cid, "status": "draft",
            "name": it.get("title", ""), "start_date": iso(start), "end_date": iso(end),
            "place_name": strip_html(intro.get("eventplace")), "address": strip_html(it.get("addr1")),
            "geo": {"lat": _num(it.get("mapy")), "lng": _num(it.get("mapx")), "source": "TourAPI"},
            "summary": "", "source_name": "한국관광공사 TourAPI", "source_url": "",
            "checked_at": today,
        })
    return out


def run(data_dir: Path, tier: str | None = None, limit: int | None = None, offline: bool = False,
        events: bool = False, rematch: bool = False, refresh: bool = False,
        max_calls: int = DEFAULT_MAX_CALLS) -> dict:
    load_dotenv(Path(".env"))
    site = json.loads((data_dir / "site.json").read_text("utf-8"))
    places_path = data_dir / "places.json"
    entities = json.loads(places_path.read_text("utf-8"))
    api = from_site_config(site, os.environ.get("TOURAPI_KEY", ""), data_dir.parent / "cache" / "tourapi",
                           offline, refresh, max_calls=max_calls)
    region_kw = (site.get("tourapi") or {}).get("region_keyword") or site.get("region", "")
    today = dt.date.today().isoformat()

    todo = [e for e in entities if (tier is None or e.get("tier") == tier)]
    if limit:
        todo = todo[:limit]
    matched, unmatched, failed = [], [], []
    stopped = False
    stop_reason = ""
    for e in todo:  # pass 1: matching
        t = e.setdefault("tourapi", {})
        if t.get("contentid") and not rematch:
            matched.append(e)
            continue
        try:
            best, score, scored = match_entity(api, e, region_kw)
        except TourAPIStopError as err:
            failed.append((e, str(err)))
            stopped, stop_reason = True, str(err)
            break
        except TourAPIError as err:
            failed.append((e, str(err)))
            continue
        if best:
            t.update({"contentid": str(best["contentid"]), "contenttypeid": str(best.get("contenttypeid", "")),
                      "title": best.get("title", ""), "match_score": score})
            matched.append(e)
        else:
            t["match_score"] = score
            unmatched.append((e, scored[:3]))

    by_contentid = {str(x["tourapi"]["contentid"]): x for x in entities if (x.get("tourapi") or {}).get("contentid")}
    for e in ([] if stopped else matched):  # pass 2: details
        before = deepcopy(e)
        try:
            fill_entity(api, e, site, by_contentid, today)
        except TourAPIStopError as err:
            # An interrupted fill must not leave half-refreshed facts/images.
            e.clear()
            e.update(before)
            failed.append((e, str(err)))
            stopped, stop_reason = True, str(err)
            break
        except TourAPIError as err:
            failed.append((e, str(err)))

    if events and not stopped:
        ev_path = data_dir / "events.json"
        existing = json.loads(ev_path.read_text("utf-8")) if ev_path.exists() else []
        try:
            collected = collect_events(api, site, existing, today)
        except TourAPIStopError as err:
            failed.append(({"name": "행사 수집"}, str(err)))
            stopped, stop_reason = True, str(err)
        except TourAPIError as err:
            failed.append(({"name": "행사 수집"}, str(err)))
        else:
            ev_path.write_text(json.dumps(collected, ensure_ascii=False, indent=2), "utf-8")

    shutil.copy2(places_path, places_path.with_suffix(".json.bak"))
    places_path.write_text(json.dumps(entities, ensure_ascii=False, indent=2), "utf-8")

    with open(data_dir / "unmatched.csv", "w", newline="", encoding="utf-8-sig") as f:
        w = csv.writer(f)
        w.writerow(["id", "name", "best_score", "cand1", "cand1_addr", "cand1_contentid", "cand2", "cand2_addr", "cand2_contentid"])
        for e, scored in unmatched:
            row = [e.get("id"), e.get("name"), e["tourapi"].get("match_score")]
            for s, c in scored[:2]:
                row += [f"{c.get('title')} ({s})", c.get("addr1", ""), c.get("contentid", "")]
            w.writerow(row)

    report = Path("reports")
    report.mkdir(exist_ok=True)
    lines = [f"# TourAPI 보강 리포트 ({today})", "",
             f"- 대상 {len(todo)} / 매칭 {len(matched)} / 미매칭 {len(unmatched)} / 오류 {len(failed)}",
             f"- 실호출 {api.live_calls}건 / 캐시 {api.cache_hits}건", "",
             "## 미매칭 (unmatched.csv에서 contentid를 직접 지정 후 재실행)"]
    lines += [f"- {e.get('name')} (최고 점수 {e['tourapi'].get('match_score')})" for e, _ in unmatched] or ["- 없음"]
    lines += ["", "## 오류"] + ([f"- {e.get('name')}: {msg}" for e, msg in failed] or ["- 없음"])
    if stopped:
        lines += ["", f"- 호출 중단: {stop_reason}"]
    (report / "enrich_report.md").write_text("\n".join(lines) + "\n", "utf-8")
    summary = {"targets": len(todo), "matched": len(matched), "unmatched": len(unmatched),
               "failed": len(failed), "live_calls": api.live_calls, "cache_hits": api.cache_hits,
               "stopped": stopped, "stop_reason": stop_reason}
    print(json.dumps(summary, ensure_ascii=False))
    return summary


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--data", required=True, type=Path)
    ap.add_argument("--tier", choices=["full", "basic"])
    ap.add_argument("--limit", type=int)
    ap.add_argument("--offline", action="store_true")
    ap.add_argument("--events", action="store_true")
    ap.add_argument("--rematch", action="store_true", help="이미 매칭된 contentid도 다시 검색")
    ap.add_argument("--refresh", action="store_true", help="캐시를 무시하고 다시 조회(주간 정보 확인일 갱신)")
    ap.add_argument("--max-calls", type=int, default=DEFAULT_MAX_CALLS, help="이번 실행의 실호출 상한")
    a = ap.parse_args(argv)
    s = run(a.data, a.tier, a.limit, a.offline, a.events, a.rematch, a.refresh, a.max_calls)
    return 1 if s["failed"] else 0


if __name__ == "__main__":
    sys.exit(main())
