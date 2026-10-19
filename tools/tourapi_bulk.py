"""TourAPI bulk enrichment: one region list per content type, matched locally (few calls).

    python tools/tourapi_bulk.py --data data/incheon [--max-calls 120] [--offline]
    python tools/tourapi_bulk.py --data data/incheon --add-new --details --events --max-calls 900
    python tools/tourapi_bulk.py --data data/incheon --districts 연수구,강화군 --add-new   # some 구·군 only

1. ldongCode2 -> the region's lDongRegnCd and its 시군구 codes (site.json region_full: '인천광역시' or '<도> <시>').
   A 광역시 (site.json tourapi.scope 'sido') takes every 구·군 TourAPI lists under it — a name its site.json does not
   list in districts / districts_former is reported (the owner updates site.json); a 시 takes the one 시군구 named
   locality. Each list item keeps the 구·군 it was listed under (`_signgu_name` → the place's `district`).
2. areaBasedList2 for content types 12·14·28·38·32·39 (all pages) -> contentid, title, address, mapx/mapy,
   firstimage + cpyrhtDivCd.
3. Local matching against places.json (duplicates skipped): same normalised name, or a near-identical name
   at the same road address. Anything less certain stays unmatched (listed in the report).
4. Fills tourapi.contentid, geo (TourAPI), images (cpyrhtDivCd Type1/Type3 only, https, credit 한국관광공사),
   with --gallery also detailImage2 photos named after the place, then straight-line nearby places
   (attraction/stay/food, within 2 km) computed from those coordinates.
5. --events (searchFestival2) runs before --details/--add-new, so the time-sensitive festival list is refreshed
   first when the per-run call cap is reached.
Fields named in an entity's "locks" are not touched. Values are copied as given; nothing is guessed.
checked_at is the date the TourAPI response was fetched (a cached response keeps its own date), so a
cache-first re-run does not bump 확인일 or sitemap lastmod (aeo_geo_spec P0-4). --refresh ignores the cache
(used by tools/refresh.py --fresh) and the values it re-fetches get today's date.
"""
from __future__ import annotations

import argparse
import json
import os
import re
import sys
import time
from difflib import SequenceMatcher
from pathlib import Path

if __package__ in (None, ""):
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from pipeline.enrich import haversine_m, load_dotenv
from pipeline.schema import TOURAPI_LICENSE_MAP, license_allowed
from pipeline.textutil import normalize_name
from pipeline.tourapi import KIND_BY_TYPE, TourAPIError, TourAPIStopError, from_site_config

LIST_TYPES = ("12", "14", "28", "38", "32", "39")
ROAD = re.compile(r"([가-힣0-9]+(?:로|길))\s*([0-9]+(?:-[0-9]+)?)")
GENERIC = re.compile(r"게스트하우스|게하|모텔|호텔|펜션|민박|하우스")
BRANCH = re.compile(r"(\d+)\s*호점")
NEARBY_RADIUS_M = 2000
NEARBY_PER_KIND = 3


def road_key(address: str | None) -> str:
    """'X시 Y4길 14(Z동)' -> 'Y4길14'; '' when the address has no road + number."""
    m = ROAD.search(re.sub(r"\s+", " ", address or ""))
    return f"{m.group(1)}{m.group(2)}" if m else ""


def name_key(name: str | None, region: str) -> str:
    return normalize_name(name).removeprefix(normalize_name(region))


def retry(fn, *args, **kwargs):
    """Connection resets through the proxy are transient; provider errors are not retried."""
    for attempt in range(6):
        try:
            return fn(*args, **kwargs)
        except TourAPIError as err:
            if "네트워크 오류" not in str(err) or attempt == 5:
                raise
            time.sleep(min(30, 2 ** (attempt + 1)))


def fetch_region(api, regn: str, signgu: str, rows: int = 200, name: str = "") -> list[dict]:
    """Every list item of the content types in one 시군구 (all pages); each keeps the 구·군 name it was listed under."""
    items: list[dict] = []
    for ctype in LIST_TYPES:
        page = 1
        while True:
            got = retry(api.area_based, regn, signgu, ctype, rows=rows, page=page)
            items += [{**it, "_signgu_name": name} if name else it for it in got]
            if len(got) < rows:
                break
            page += 1
    return items


class RegionError(RuntimeError):
    """site.json does not name a region TourAPI knows (the message says what to fix)."""


def region_codes(api, site: dict, only: list[str] | None = None) -> tuple[str, list[tuple[str, str]], list[str]]:
    """(lDongRegnCd, [(lDongSignguCd, 시군구 name)], notes) of the site's region, from TourAPI's own code lists.
    The 시도 is the one whose name is in site.json region_full; a 광역시 (tourapi.scope 'sido') takes every 시군구
    TourAPI lists under it (or the `only` names), a 시 the one named locality (or region + '시', region). A 시군구 name
    the site.json does not list (districts, districts_former) is a note: TourAPI may use the new names before the data
    does, or the other way round — both are read (pipeline/city.py district_of)."""
    region_full = str(site.get("region_full") or "").strip()
    if not region_full:
        raise RegionError("site.json에 region_full이 없습니다(예: '인천광역시', '○○도 ○○시').")
    regn = next((str(r["code"]) for r in retry(api.ldong_code) if r.get("name") and r["name"] in region_full), "")
    if not regn:
        raise RegionError(f"TourAPI 법정동 시도 목록에 region_full '{region_full}'에 든 이름이 없습니다.")
    signgus = [(str(r["code"]), str(r.get("name") or "")) for r in retry(api.ldong_code, regn) if r.get("code")]
    notes: list[str] = []
    if (site.get("tourapi") or {}).get("scope") == "sido":
        known = set(site.get("districts") or []) | set(site.get("districts_former") or [])
        notes += [f"site.json districts에 없는 구·군(TourAPI): {n}" for _, n in signgus if known and n not in known]
        chosen = [(c, n) for c, n in signgus if not only or n in only]
        missing = sorted(set(only or []) - {n for _, n in signgus})
        notes += [f"TourAPI 목록에 없는 구·군: {n}" for n in missing]
        return regn, chosen, notes
    region = str(site.get("region") or "")
    names = [x for x in (site.get("locality"), f"{region}시" if region else "", region) if x]
    hit = next(((c, n) for c, n in signgus if n in names), None)
    if not hit:
        raise RegionError(f"TourAPI 법정동 시군구 목록에 locality '{site.get('locality')}'가 없습니다.")
    return regn, [hit], notes


def match(place: dict, by_name: dict, by_road: dict, region: str) -> tuple[dict | None, str]:
    kind = place.get("kind")
    nk = name_key(place.get("name"), region)
    rk = road_key((place.get("facts") or {}).get("address"))
    same_name = [c for c in by_name.get(nk, []) if KIND_BY_TYPE.get(str(c.get("contenttypeid"))) == kind]
    if len(same_name) == 1:
        return same_name[0], "same_name"
    if len(same_name) > 1 and rk:
        hit = [c for c in same_name if road_key(c.get("addr1")) == rk]
        if len(hit) == 1:
            return hit[0], "same_name_address"
    if rk:
        near = [c for c in by_road.get(rk, []) if KIND_BY_TYPE.get(str(c.get("contenttypeid"))) == kind
                and SequenceMatcher(None, nk, name_key(c.get("title"), region)).ratio() >= 0.6]
        if len(near) == 1:
            return near[0], "same_address_similar_name"
    if rk and kind in ("stay", "food"):  # a business at one address: '게스트하우스 소설여행' = '소설여행'
        core = lambda s: GENERIC.sub("", s)
        branches = lambda s: set(BRANCH.findall(s or ""))
        hit = [c for c in by_road.get(rk, []) if KIND_BY_TYPE.get(str(c.get("contenttypeid"))) == kind
               and branches(c.get("title")) == branches(place.get("name"))
               and min(len(core(nk)), len(core(name_key(c.get("title"), region)))) >= 2
               and (core(nk) in core(name_key(c.get("title"), region))
                    or core(name_key(c.get("title"), region)) in core(nk))]
        if len(hit) == 1:
            return hit[0], "same_address_name_contains"
    return None, ""


def photo_title(title: str | None) -> str:
    """What the provider photo shows: 'X사(<city>)' -> 'X사', '[백년가게]Y반점' -> 'Y반점' (tourapi_details.display_name)."""
    from tools.tourapi_details import display_name
    return display_name(title)


def https(url: str) -> str:
    return "https://" + url[len("http://"):] if url.startswith("http://") else url


def fill(place: dict, cand: dict, basis: str, allowed: list | None) -> dict:
    locks = set(place.get("locks") or [])
    changed = {"geo": False, "image": ""}
    if cand.get("_signgu_name") and not place.get("district"):   # the 구·군 TourAPI lists it under (a 광역시)
        place["district"] = cand["_signgu_name"]
    place["tourapi"] = {**(place.get("tourapi") or {}), "contentid": str(cand["contentid"]),
                        "contenttypeid": str(cand.get("contenttypeid", "")), "title": cand.get("title", ""),
                        "match_basis": basis, "modifiedtime": cand.get("modifiedtime", "")}
    try:
        lat, lng = float(cand.get("mapy")), float(cand.get("mapx"))
    except (TypeError, ValueError):
        lat = lng = None
    if "geo" not in locks and lat and lng:
        place["geo"] = {"lat": lat, "lng": lng, "source": "TourAPI"}
        changed["geo"] = True
    code = TOURAPI_LICENSE_MAP.get(str(cand.get("cpyrhtDivCd") or ""), "UNKNOWN")
    if "images" not in locks and cand.get("firstimage"):
        others = [i for i in (place.get("images") or []) if i.get("source") != "TourAPI"]
        first = https(cand["firstimage"])
        # keep gallery photos added earlier (detailImage2); the list photo stays first
        gallery = [i for i in (place.get("images") or []) if i.get("source") == "TourAPI" and i.get("url") != first]
        tour = []
        if license_allowed(code, allowed):
            tour = [{"url": first, "alt": photo_title(cand.get("title")) or place["name"],
                     "credit": "한국관광공사", "license": code, "source": "TourAPI"}]
            changed["image"] = code
        place["images"] = others + tour + gallery
    return changed


def add_gallery(api, place: dict, allowed: list | None, limit: int = 6) -> int:
    """detailImage2 photos whose name mentions the place (provider lists sometimes carry other places'
    photos), allowed licence types only, after the list photo."""
    if "images" in set(place.get("locks") or []):
        return 0
    title = photo_title((place.get("tourapi") or {}).get("title"))
    key = normalize_name(title)[:6]
    have = {i["url"] for i in place.get("images") or []}
    added = 0
    for im in retry(api.detail_image, place["tourapi"]["contentid"]):
        code = TOURAPI_LICENSE_MAP.get(str(im.get("cpyrhtDivCd") or ""), "UNKNOWN")
        url = https(im.get("originimgurl") or "")
        if (not url or url in have or not license_allowed(code, allowed)
                or len(key) < 2 or key not in normalize_name(im.get("imgname"))):
            continue
        place.setdefault("images", []).append({"url": url, "alt": title or place["name"], "credit": "한국관광공사",
                                               "license": code, "source": "TourAPI"})
        have.add(url)
        added += 1
        if len([i for i in place["images"] if i.get("source") == "TourAPI"]) >= limit:
            break
    return added


# Shops listed as "nearby": markets, local-produce halls and bookstores only (TourAPI lclsSystm3), not marts or malls
NEARBY_SHOP_LCLS = ("SH05", "SH06", "SH07")


def compute_nearby(places: list[dict], today: str) -> int:
    live = [p for p in places if not p.get("duplicate_of") and (p.get("geo") or {}).get("lat") is not None]
    listable = lambda q: not q.get("exclude") and (q.get("category") != "쇼핑" or
                                                     (q.get("tourapi") or {}).get("lcls", "").startswith(NEARBY_SHOP_LCLS))
    n = 0
    for p in live:
        if "nearby" in set(p.get("locks") or []):
            continue
        dists = sorted(((haversine_m(p["geo"]["lat"], p["geo"]["lng"], q["geo"]["lat"], q["geo"]["lng"]), q)
                        for q in live if q is not p and listable(q)), key=lambda x: x[0])
        groups = {"attraction": [], "stay": [], "food": []}
        for d, q in dists:
            if d > NEARBY_RADIUS_M:
                break
            g = groups.get(q.get("kind"))
            if g is not None and len(g) < NEARBY_PER_KIND:
                g.append({"name": q["name"], "kind": q["kind"], "type_label": q.get("category") or "",
                          "distance_m": int(round(d)), "internal_slug": q["slug"],
                          "contentid": (q.get("tourapi") or {}).get("contentid", "")})
        nearby = groups["attraction"] + groups["stay"] + groups["food"]
        kept = (p.get("nearby_source") or {}).get("checked_at") if nearby == p.get("nearby") else ""
        p["nearby"] = nearby
        p["nearby_source"] = {"provider": "한국관광공사 TourAPI 좌표", "radius_m": NEARBY_RADIUS_M,
                              "distance_basis": "직선거리", "checked_at": kept or today}
        n += bool(p["nearby"])
    return n


def _priority(p: dict) -> tuple:
    """Detail calls go to the pages people read first: full tier, question places, attractions, the rest."""
    return (p.get("tier") != "full", not p.get("question_ids"), p.get("kind") != "attraction", p.get("name", ""))


def fetched_on(api, start: int, today: str) -> str:
    """Oldest fetch date of the responses the client answered since `start` (len(api.fetched_dates) before the
    calls): a cached response keeps the date it was fetched, so re-running from cache changes no 확인일."""
    dates = (getattr(api, "fetched_dates", None) or [])[start:]
    return min(dates) if dates else today


def _details(api, cid: str, ctype: str) -> tuple[dict, dict, list]:
    common = retry(api.detail_common, cid)
    intro = retry(api.detail_intro, cid, ctype) if ctype else {}
    info = retry(api.detail_info, cid, ctype) if ctype in ("12", "28") else []
    return common, intro, info


def run(data_dir: Path, max_calls: int, offline: bool, gallery: bool = False, details: bool = False,
        add_new: bool = False, events: bool = False, refresh: bool = False, districts: list[str] | None = None) -> dict:
    import datetime as dt

    from pipeline import city
    from tools.tourapi_details import (NEW_PLACE_TYPES, alternate_name, clean, duplicate_candidates, event_key,
                                       festival_event, merge_facts, new_place, tourapi_facts)
    load_dotenv(Path(".env"))
    site = json.loads((data_dir / "site.json").read_text("utf-8"))
    city.activate(site)   # the city's names for name matching and photo titles (pipeline/city.py)
    places_path = data_dir / "places.json"
    # before the first collection there is no places.json: every TourAPI item is new (--add-new)
    places = json.loads(places_path.read_text("utf-8")) if places_path.exists() else []
    overrides_path = data_dir / "tourapi_overrides.json"
    overrides = json.loads(overrides_path.read_text("utf-8")) if overrides_path.exists() else {}
    same = {str(k): ([v] if isinstance(v, str) else list(v))                 # contentid -> our slug(s)
            for k, v in (overrides.get("same") or {}).items()}
    different = {str(x) for x in overrides.get("different") or []}           # contentid: add as its own place
    skip = {str(x) for x in overrides.get("skip") or []}                     # contentid: not a place for this site
    hold = {str(x) for x in overrides.get("hold") or {}}                     # contentid: a person decides first
    api = from_site_config(site, os.environ.get("TOURAPI_KEY", ""), data_dir.parent / "cache" / "tourapi",
                           offline=offline, refresh=refresh, max_calls=max_calls)
    region = str(site.get("region") or "")
    regn, signgus, region_notes = region_codes(api, site, districts)
    sido = (site.get("tourapi") or {}).get("scope") == "sido"
    items = [it for code, name in signgus for it in fetch_region(api, regn, code, name=name if sido else "")]
    by_cid = {str(it["contentid"]): it for it in items}
    by_name: dict[str, list] = {}
    by_road: dict[str, list] = {}
    for it in items:
        by_name.setdefault(name_key(it.get("title"), region), []).append(it)
        rk = road_key(it.get("addr1"))
        if rk:
            by_road.setdefault(rk, []).append(it)
    allowed = (site.get("publish_rules") or {}).get("allowed_image_licenses")
    today = dt.date.today().isoformat()
    stats = {"list_items": len(items), "districts": [n for _, n in signgus], "region_notes": region_notes,
             "live_calls": 0, "targets": 0, "matched": {}, "geo": 0,
             "images": {"KOGL-1": 0, "KOGL-3": 0}, "image_other_type": 0, "unmatched": []}
    forced = {slug: by_cid[cid] for cid, slugs in same.items() if cid in by_cid for slug in slugs}
    for p in places:
        if p.get("duplicate_of") or str(p.get("id", "")).startswith("tourapi-"):
            continue
        stats["targets"] += 1
        if p["slug"] in forced:
            cand, basis = forced[p["slug"]], "reviewed_same_place"
        else:
            cand, basis = match(p, by_name, by_road, region)
        if not cand:
            stats["unmatched"].append(f"{p['kind']}:{p['name']}")
            continue
        stats["matched"][p["kind"]] = stats["matched"].get(p["kind"], 0) + 1
        ch = fill(p, cand, basis, allowed)
        stats["geo"] += ch["geo"]
        if ch["image"]:
            stats["images"][ch["image"]] += 1
        elif cand.get("firstimage"):
            stats["image_other_type"] += 1
    if gallery:
        stats["gallery_added"] = sum(add_gallery(api, p, allowed) for p in places
                                     if not p.get("duplicate_of") and (p.get("tourapi") or {}).get("match_basis"))
    detail_log: list[str] = []
    try:
        if events:
            ev_path = data_dir / "events.json"
            existing = json.loads(ev_path.read_text("utf-8")) if ev_path.exists() else []
            e = stats["events"] = {"festival_items": 0, "added": [], "updated": [], "errors": []}
            mark = len(getattr(api, "fetched_dates", []))
            # a 광역시: one call for the whole 시도 (each item's address names its 구·군); a 시: its 시군구
            fest = retry(api.search_festival, f"{today[:4]}0101", regn, None if sido else signgus[0][0])
            list_date = fetched_on(api, mark, today)
            e["festival_items"] = len(fest)
            have_cid = {str(x.get("contentid")): x for x in existing if x.get("contentid")}
            for it in fest:
                cid = str(it["contentid"])
                start = len(getattr(api, "fetched_dates", []))
                try:
                    intro = retry(api.detail_intro, cid, "15")
                    common = retry(api.detail_common, cid)
                except TourAPIStopError:
                    raise
                except TourAPIError as err:
                    e["errors"].append(f"{it.get('title')}: {err}")
                    continue
                checked = min(list_date, fetched_on(api, start, today))
                ev = festival_event(it, intro, common, checked)
                if cid in have_cid:  # refresh our earlier TourAPI copy
                    have_cid[cid].update({k: v for k, v in ev.items() if k not in ("id", "status", "summary")})
                    e["updated"].append(ev["name"])
                    continue
                key, year = event_key(ev["name"]), ev["start_date"][:4]
                twin = next((x for x in existing if event_key(x.get("name")) == key
                             and (x.get("start_date") or "")[:4] == year and year), None)
                if twin:  # same edition already listed from the city's own source: keep its dates, note TourAPI's next to them
                    twin["tourapi_contentid"] = cid
                    if (twin.get("start_date"), twin.get("end_date")) != (ev["start_date"], ev["end_date"]):
                        twin["date_alternatives"] = [{"start_date": ev["start_date"], "end_date": ev["end_date"],
                                                      "provider": "한국관광공사 TourAPI", "checked_at": checked}]
                    for k in ("address", "geo", "tel", "homepage", "playtime", "fee"):
                        if ev.get(k) and not twin.get(k):
                            twin[k] = ev[k]
                    e["updated"].append(twin["name"])
                    continue
                for x in existing:  # undated '매년 …' record of the same festival: mark it recurring
                    if event_key(x.get("name")) == key and not x.get("start_date"):
                        x["recurring"] = True
                existing.append(ev)
                e["added"].append(f"{ev['name']} ({ev['start_date']}~{ev['end_date']})")
            ev_path.write_text(json.dumps(existing, ensure_ascii=False, indent=2) + "\n", "utf-8")
        if details:
            d = stats["details"] = {"done": 0, "added": {}, "confirmed": {}, "conflicts": [], "alternate_names": 0,
                                    "errors": []}
            matched = sorted((p for p in places if not p.get("duplicate_of") and (p.get("tourapi") or {}).get("contentid")),
                             key=_priority)
            for p in matched:
                t = p["tourapi"]
                cid, ctype = str(t["contentid"]), str(t.get("contenttypeid") or "")
                start = len(getattr(api, "fetched_dates", []))
                try:
                    common, intro, info = _details(api, cid, ctype)
                except TourAPIStopError:
                    raise
                except TourAPIError as err:
                    d["errors"].append(f"{p['name']}: {err}")
                    continue
                res = merge_facts(p, tourapi_facts(common, intro, info, ctype), fetched_on(api, start, today), cid)
                t["modifiedtime"] = common.get("modifiedtime") or t.get("modifiedtime", "")
                t["overview"] = clean(common.get("overview"))  # fact-checking reference only — never rendered
                alt = alternate_name(p, common.get("title") or t.get("title"))
                if alt and alt not in (p.get("alternate_names") or []):
                    p.setdefault("alternate_names", []).append(alt)
                    d["alternate_names"] += 1
                d["done"] += 1
                for k in res["added"]:
                    d["added"][k] = d["added"].get(k, 0) + 1
                for k in res["confirmed"]:
                    d["confirmed"][k] = d["confirmed"].get(k, 0) + 1
                d.setdefault("also", 0)
                d["also"] += len(res["also"])
                for k in res["conflicts"]:
                    d["conflicts"].append(f"{p['name']}·{k}")
                    detail_log.append(f"- {p['name']} · {k}: 기존 '{squash(p['facts'].get(k, ''))}' / TourAPI "
                                      f"'{squash(p['fact_alternatives'][k][-1]['value'])}'")
        if add_new:
            n = stats["new_places"] = {"added": [], "held_duplicate_candidates": [], "skipped": 0, "errors": []}
            have = {str((p.get("tourapi") or {}).get("contentid")) for p in places if (p.get("tourapi") or {}).get("contentid")}
            taken = {p["slug"] for p in places}
            todo = sorted((it for it in items if str(it.get("contenttypeid")) in NEW_PLACE_TYPES
                           and str(it["contentid"]) not in have and str(it["contentid"]) not in same),
                          key=lambda it: (str(it.get("contenttypeid")) not in ("12", "14", "28"), it.get("title", "")))
            for it in todo:
                cid = str(it["contentid"])
                if cid in skip:
                    n["skipped"] += 1
                    continue
                if cid in hold:
                    n["held_duplicate_candidates"].append({"contentid": cid, "title": it.get("title", ""),
                                                           "addr": it.get("addr1", ""), "candidates": [],
                                                           "note": overrides["hold"][cid]})
                    continue
                cands = duplicate_candidates(it, places, region)
                if cands and cid not in different:
                    n["held_duplicate_candidates"].append({"contentid": cid, "title": it.get("title", ""),
                                                           "addr": it.get("addr1", ""), "candidates": cands})
                    continue
                start = len(getattr(api, "fetched_dates", []))
                try:
                    common, intro, info = _details(api, cid, str(it.get("contenttypeid")))
                except TourAPIStopError:
                    raise
                except TourAPIError as err:
                    n["errors"].append(f"{it.get('title')}: {err}")
                    continue
                place = new_place(it, common, intro, info, fetched_on(api, start, today), allowed, taken)
                places.append(place)
                n["added"].append(f"{place['kind']}:{place['name']}")
    except TourAPIStopError as err:
        stats["stopped"] = str(err)
    stats["nearby_pages"] = compute_nearby(places, today)
    stats["live_calls"] = api.live_calls
    stats["cache_hits"] = api.cache_hits
    places_path.write_text(json.dumps(places, ensure_ascii=False, indent=2) + "\n", "utf-8")
    report = Path("reports")
    report.mkdir(exist_ok=True)
    lines = [f"# TourAPI 일괄 보강 ({today})", "", f"- 시군구 {', '.join(stats['districts'])}",
             *[f"- 확인: {x}" for x in region_notes],
             f"- 목록 항목 {len(items)} · 실호출 {api.live_calls} · 캐시 {api.cache_hits}",
             f"- 대상 {stats['targets']} · 매칭 {stats['matched']} · 좌표 {stats['geo']}",
             f"- 허용 사진 Type1 {stats['images']['KOGL-1']} · Type3 {stats['images']['KOGL-3']}"
             f" · 사진은 있으나 허용 외 유형 {stats['image_other_type']}",
             f"- 직선거리 주변이 생긴 장소 {stats['nearby_pages']}"]
    if stats.get("stopped"):
        lines.append(f"- 중단: {stats['stopped']}")
    if details:
        d = stats["details"]
        lines += ["", "## 상세(detailCommon2·detailIntro2·detailInfo2)", "",
                  f"- 처리 {d['done']}곳 · 새로 채운 항목 {d['added']} · 기존 값과 일치 {d['confirmed']}",
                  f"- 값이 달라 둘 다 표시 {len(d['conflicts'])}건 · 다른 이름 {d['alternate_names']}곳 · 오류 {len(d['errors'])}"]
        lines += detail_log + [f"- 오류: {x}" for x in d["errors"]]
    if add_new:
        n = stats["new_places"]
        lines += ["", "## TourAPI에만 있는 장소", "", f"- 추가 {len(n['added'])} · 중복 의심 보류 "
                  f"{len(n['held_duplicate_candidates'])} · 제외 {n['skipped']} · 오류 {len(n['errors'])}"]
        lines += [f"- 추가: {x}" for x in n["added"]]
        for h in n["held_duplicate_candidates"]:
            lines.append(f"- 보류 {h['contentid']} {h['title']} ({h['addr']}) ↔ "
                         + ", ".join(f"{c['name']}[{c['slug']}] {c['address']}" for c in h["candidates"]))
    if events:
        e = stats["events"]
        lines += ["", "## 행사(searchFestival2)", "", f"- 응답 {e['festival_items']} · 추가 {len(e['added'])} · 갱신 {len(e['updated'])}"]
        lines += [f"- 추가: {x}" for x in e["added"]] + [f"- 갱신: {x}" for x in e["updated"]]
    lines += ["", "## 미매칭"] + [f"- {x}" for x in stats["unmatched"]]
    (report / "tourapi_bulk.md").write_text("\n".join(lines) + "\n", "utf-8")
    (report / "tourapi_bulk.json").write_text(json.dumps(stats, ensure_ascii=False, indent=1) + "\n", "utf-8")
    out = {k: v for k, v in stats.items() if k not in ("unmatched", "details", "new_places", "events")}
    out["unmatched"] = len(stats["unmatched"])
    if details:
        out["details"] = {k: (len(v) if isinstance(v, list) else v) for k, v in stats["details"].items()}
    if add_new:
        out["new_places"] = {k: (len(v) if isinstance(v, list) else v) for k, v in stats["new_places"].items()}
    if events:
        out["events"] = {k: (len(v) if isinstance(v, list) else v) for k, v in stats["events"].items()}
    print(json.dumps(out, ensure_ascii=False))
    return stats


def squash(value: str) -> str:
    return re.sub(r"\s+", " ", value or "").strip()[:80]


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--data", type=Path, default=Path("data/incheon"))
    ap.add_argument("--max-calls", type=int, default=120)
    mode = ap.add_mutually_exclusive_group()
    mode.add_argument("--offline", action="store_true", help="캐시만 쓴다(네트워크 호출 없음)")
    mode.add_argument("--refresh", action="store_true",
                      help="캐시를 무시하고 새로 받는다(응답은 다시 캐시에 저장, 실행당 상한 --max-calls 적용)")
    ap.add_argument("--gallery", action="store_true", help="매칭된 장소마다 detailImage2로 허용 사진 추가(장소당 1회)")
    ap.add_argument("--details", action="store_true",
                    help="매칭된 장소마다 detailCommon2·detailIntro2(관광지·레포츠는 detailInfo2도) — 필드별 출처로 병합")
    ap.add_argument("--add-new", action="store_true",
                    help="TourAPI에만 있는 장소(유형 12·14·28·32·39)를 draft/basic으로 추가(중복 의심은 보류)")
    ap.add_argument("--events", action="store_true", help="searchFestival2(올해 1월 1일부터)로 행사 갱신")
    ap.add_argument("--districts", default="", help="광역시에서 이 구·군만(쉼표로, 예: 연수구,강화군) — 호출 한도 안에서 나눠 받을 때")
    a = ap.parse_args(argv)
    only = [x.strip() for x in a.districts.split(",") if x.strip()] or None
    try:
        run(a.data, a.max_calls, a.offline, a.gallery, a.details, a.add_new, a.events, a.refresh, only)
    except RegionError as err:
        print(f"중단: {err}", file=sys.stderr)
        return 1
    except TourAPIError as err:   # a provider error before any data was written (masked key, provider message as-is)
        print(f"중단: {err} — python tools/tourapi_doctor.py --data {a.data} 로 키·네트워크를 확인하세요.", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
