"""TourAPI bulk enrichment: one region list per content type, matched locally (few calls).

    python tools/tourapi_bulk.py --data data/incheon [--max-calls 120] [--offline]
    python tools/tourapi_bulk.py --data data/incheon --add-new --details --events --max-calls 900
    python tools/tourapi_bulk.py --data data/incheon --districts 연수구,강화군 --add-new   # some 구·군 only
    python tools/tourapi_bulk.py --data data/incheon --lists-only    # no call: listed places from the cached lists

1. ldongCode2 -> the region's lDongRegnCd and its 시군구 codes (site.json region_full: '인천광역시' or '<도> <시>').
   A 광역시 (site.json tourapi.scope 'sido') takes every 구·군 TourAPI lists under it — a name its site.json does not
   list in districts / districts_former is reported (the owner updates site.json); a 시 takes the one 시군구 named
   locality. Each list item keeps the 구·군 it was listed under (`_signgu_name` → the place's `district`).
2. areaBasedList2 for content types 12·14·28·38·32·39 (all pages) -> contentid, title, address, mapx/mapy,
   firstimage + cpyrhtDivCd.
3. Local matching against places.json (duplicates skipped): same normalised name, or a near-identical name
   at the same road address. Anything less certain stays unmatched (listed in the report).
4. Fills tourapi.contentid, geo (TourAPI; a point from another source — the city's official tourism site, a
   facility's homepage — stays, the report lists how far TourAPI's is), images (cpyrhtDivCd Type1/Type3 only, https,
   credit 한국관광공사), with --gallery also detailImage2 photos named after the place, then straight-line nearby
   places (each kind, within 2 km) computed from those coordinates; nearby_source names every provider of
   the points used ('한국관광공사 TourAPI·<another provider> 좌표').
   Every place TourAPI lists keeps the item's classification codes (tourapi.lclsSystm1·2·3, cat1·2·3) and its kind
   follows them (pipeline.tourapi.kind_of: lclsSystm3 FD05… or FD030100 — cat3 A05020900 without the new
   classification — is 'cafe', 카페·디저트; type 38 is 'shopping'), unless "kind" is in its locks (reclassify).
5. --events (searchFestival2, all pages) asks for the festivals from today (--events-from YYYYMMDD for an earlier
   day) and runs before --details/--add-new, so the time-sensitive festival list is refreshed first when the
   per-run call cap is reached. A 광역시 asks once for the whole 시도.
6. --lists-only (no call, cache only, no key): every listed place of the place types not in places.json yet is added
   from its list item alone (tools/tourapi_details.list_place): name, address, the 구·군 it was listed under,
   coordinates, phone when the list has one, the list photo (Type1/Type3 only, credit 한국관광공사), classification
   codes and the kind they give — each value with provider and check date (the day the list page was fetched), as a
   draft with tourapi.details_pending. The daily --details run then fetches those places like any place with a
   contentid and completes them (complete_listed: classification from detailCommon2, homepage, missing point or photo;
   the mark goes); --add-new does not add them again (their contentid is in places.json). Overrides and duplicate
   holds apply as for --add-new.
7. The report ends with the live calls the collection still needs (responses not in the cache yet): details of
   the matched places, TourAPI-only places still to add and festival details — `remaining_calls` (cache-first runs).
Fields named in an entity's "locks" are not touched. Values are copied as given; nothing is guessed.
checked_at is the date the TourAPI response was fetched (a cached response keeps its own date), so a
cache-first re-run does not bump 확인일 or sitemap lastmod (aeo_geo_spec P0-4). --refresh ignores the cache
(used by tools/refresh.py --fresh) and the values it re-fetches get today's date.

    python tools/tourapi_bulk.py --data data/incheon --barrier-free --max-calls 600
    python tools/tourapi_bulk.py --data data/incheon --nearby-only     # nearby again from stored coordinates, no calls

--barrier-free runs alone: 한국관광공사 무장애 여행 정보 (KorWithService2, its own data.go.kr 활용신청) for every
published place with a TourAPI contentid — detailWithTour2, and for an answer with values detailCommon2 of the same
service to check the title is our place's TourAPI title. Wheelchair, accessible parking/toilet/route and stroller
rental merge with provider '한국관광공사 무장애 여행 정보(TourAPI)' (tools/tourapi_details.merge_facts): a new value is
added with its source, the same value confirms, a different one is kept beside ours (both shown + 방문 전 전화 확인).
Its own client, cache folder (data/cache/tourapi/barrier_free) and --max-calls; report in
reports/tourapi_barrier_free.md for a person to read before the guides that cite these values are rewritten.
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
from pipeline.relations import raw_family
from pipeline.schema import (KIND_LABELS, KINDS, TOURAPI_LICENSE_MAP, base_kind, geo_providers, license_allowed,
                             nearby_provider)
from pipeline.textutil import first_line, normalize_name
from pipeline.tourapi import CONTENT_TYPES, TourAPIError, TourAPIStopError, from_site_config, kind_of, lcls3

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
    """Every list item of the content types in one 시군구 (all pages); each keeps the 구·군 name it was listed under
    (`_signgu_name`) and the day its list page was fetched (`_listed_on`: a cached page keeps its own date)."""
    items: list[dict] = []
    for ctype in LIST_TYPES:
        page = 1
        while True:
            got = retry(api.area_based, regn, signgu, ctype, rows=rows, page=page)
            day = (getattr(api, "fetched_dates", None) or [""])[-1]
            extra = {**({"_signgu_name": name} if name else {}), **({"_listed_on": day} if day else {})}
            items += [{**it, **extra} if extra else it for it in got]
            total = getattr(api, "last_total", None)
            if len(got) < rows or (total is not None and page * rows >= total):
                break
            page += 1
    return items


def fetch_festivals(api, start: str, regn: str, signgu: str | None, rows: int = 100) -> list[dict]:
    """searchFestival2 from `start` (YYYYMMDD), every page."""
    items: list[dict] = []
    page = 1
    while True:
        got = retry(api.search_festival, start, regn, signgu, rows=rows, page=page)
        items += got
        total = getattr(api, "last_total", None)
        if len(got) < rows or (total is not None and page * rows >= total):
            return items
        page += 1


def pending_detail_calls(api, cid: str, ctype: str) -> int:
    """Live calls _details(cid, ctype) would still make (its responses not in the cache); 0 for a client that keeps
    no cache."""
    cached = getattr(api, "cached", None)
    if cached is None:
        return 0
    n = 0 if cached("detailCommon", contentId=cid, **(getattr(api, "detail_common_params", None) or {})) else 1
    if ctype:
        n += not cached("detailIntro", contentId=cid, contentTypeId=ctype)
    if ctype in ("12", "28"):
        n += not cached("detailInfo", contentId=cid, contentTypeId=ctype)
    return n


def remaining_calls(api, places: list[dict], items: list[dict], fest: list[dict] | None, skip: set, same: dict,
                    gallery: bool) -> dict:
    """Live calls a cache-first collection still needs: details of every place with a TourAPI contentid, the
    TourAPI-only list items not added yet (each as if added — a held duplicate candidate makes this an upper
    bound), festival details (`fest` None: the festival list itself is not fetched yet) and, with --gallery,
    detailImage2 per matched place."""
    from tools.tourapi_details import NEW_PLACE_TYPES
    cached = getattr(api, "cached", None)
    out = {"details": 0, "new_places": 0, "events": 0, "gallery": 0}
    have = set()
    for p in places:
        t = p.get("tourapi") or {}
        if p.get("duplicate_of") or not t.get("contentid"):
            continue
        have.add(str(t["contentid"]))
        out["details"] += pending_detail_calls(api, str(t["contentid"]), str(t.get("contenttypeid") or ""))
        if gallery and cached is not None and not cached("detailImage", contentId=str(t["contentid"]), imageYN="Y",
                                                         numOfRows=20, pageNo=1):
            out["gallery"] += 1
    for it in items:
        cid = str(it.get("contentid"))
        if str(it.get("contenttypeid")) in NEW_PLACE_TYPES and cid not in have and cid not in skip and cid not in same:
            out["new_places"] += pending_detail_calls(api, cid, str(it.get("contenttypeid")))
            have.add(cid)
    if fest is None:
        out["events"] = None
    elif cached is not None:
        out["events"] = sum((not cached("detailIntro", contentId=str(f["contentid"]), contentTypeId="15"))
                            + (not cached("detailCommon", contentId=str(f["contentid"]),
                                          **(getattr(api, "detail_common_params", None) or {})))
                            for f in fest)
    out["total"] = sum(v for v in out.values() if v)
    return out


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


def same_kind(item: dict, kind: str | None) -> bool:
    """A TourAPI item can be a place of this kind: the same kind read alike (schema.base_kind) — a café TourAPI
    files under 음식점 is our food record's twin, a type-38 shop our attraction record's — so a record matches before
    its kind follows TourAPI's classification (reclassify)."""
    return bool(kind) and base_kind(kind_of(item)) == base_kind(kind)


def match(place: dict, by_name: dict, by_road: dict, region: str) -> tuple[dict | None, str]:
    kind = place.get("kind")
    nk = name_key(place.get("name"), region)
    rk = road_key((place.get("facts") or {}).get("address"))
    same_name = [c for c in by_name.get(nk, []) if same_kind(c, kind)]
    if len(same_name) == 1:
        return same_name[0], "same_name"
    if len(same_name) > 1 and rk:
        hit = [c for c in same_name if road_key(c.get("addr1")) == rk]
        if len(hit) == 1:
            return hit[0], "same_name_address"
    if rk:
        near = [c for c in by_road.get(rk, []) if same_kind(c, kind)
                and SequenceMatcher(None, nk, name_key(c.get("title"), region)).ratio() >= 0.6]
        if len(near) == 1:
            return near[0], "same_address_similar_name"
    if rk and kind in ("stay", "food", "cafe"):  # a business at one address: '게스트하우스 소설여행' = '소설여행'
        core = lambda s: GENERIC.sub("", s)
        branches = lambda s: set(BRANCH.findall(s or ""))
        hit = [c for c in by_road.get(rk, []) if same_kind(c, kind)
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


def keep_classification(place: dict, item: dict) -> None:
    """The place's `tourapi` block takes the item's classification codes (lclsSystm1·2·3, cat1·2·3 as TourAPI gives
    them); the older single `lcls` field (lclsSystm3, records collected before 2026-10-19) goes once lclsSystm3 is
    there."""
    from tools.tourapi_details import classification
    t = place.setdefault("tourapi", {})
    t.update(classification(item))
    if t.get("lclsSystm3"):
        t.pop("lcls", None)


def reclassify(places: list[dict], by_cid: dict) -> list[str]:
    """Every place with a TourAPI contentid in this run's lists keeps TourAPI's classification codes
    (keep_classification) and its kind follows them (pipeline.tourapi.kind_of: a café or bakery TourAPI files under
    음식점 is 'cafe' — 카페·디저트, operator 2026-10-19; type 38 is 'shopping') when the two kinds read alike
    (food ↔ cafe, attraction ↔ shopping: schema.base_kind) and "kind" is not in the place's locks. The category of a
    TourAPI-only place follows its kind. No calls (the list items are this run's). Returns 'name: old → new' lines."""
    out = []
    for p in places:
        cid = str((p.get("tourapi") or {}).get("contentid") or "")
        item = by_cid.get(cid)
        if p.get("duplicate_of") or not item:
            continue
        keep_classification(p, item)
        new, old = kind_of({"contenttypeid": item.get("contenttypeid"), **p["tourapi"]}), p.get("kind")
        if not new or new == old or base_kind(new) != base_kind(old) or "kind" in set(p.get("locks") or []):
            continue
        p["kind"] = new
        if str(p.get("id", "")).startswith("tourapi-"):
            p["category"] = KIND_LABELS["cafe"] if new == "cafe" else CONTENT_TYPES.get(str(item.get("contenttypeid")), "")
        out.append(f"{p['name']}: {KIND_LABELS.get(old, old)} → {KIND_LABELS.get(new, new)}")
    return out


def fill(place: dict, cand: dict, basis: str, allowed: list | None) -> dict:
    locks = set(place.get("locks") or [])
    changed = {"geo": False, "image": ""}
    if cand.get("_signgu_name") and not place.get("district"):   # the 구·군 TourAPI lists it under (a 광역시)
        place["district"] = cand["_signgu_name"]
    place["tourapi"] = {**(place.get("tourapi") or {}), "contentid": str(cand["contentid"]),
                        "contenttypeid": str(cand.get("contenttypeid", "")), "title": cand.get("title", ""),
                        "match_basis": basis, "modifiedtime": cand.get("modifiedtime", "")}
    keep_classification(place, cand)
    try:
        lat, lng = float(cand.get("mapy")), float(cand.get("mapx"))
    except (TypeError, ValueError):
        lat = lng = None
    have = place.get("geo") or {}
    if "geo" not in locks and lat and lng:
        if have.get("lat") is None or have.get("source") in (None, "", "TourAPI"):
            place["geo"] = {"lat": lat, "lng": lng, "source": "TourAPI"}
            changed["geo"] = True
        else:  # a point from another source (the city's tourism site, a homepage) stays; how far TourAPI's is goes in the stats
            changed["geo_kept"] = int(round(haversine_m(float(have["lat"]), float(have["lng"]), lat, lng)))
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
    """Up to NEARBY_PER_KIND places of each kind within NEARBY_RADIUS_M (straight line between the two places' coordinates).
    A place's own family (pipeline/relations.py: its parent, parts and same-building partners — they have their own
    lines on the page) is never its nearby place, and a same-building alias is skipped while its parent is listable
    (one building, one row); the next places fill the slots. Network-free: also run alone with --nearby-only."""
    live = [p for p in places if not p.get("duplicate_of") and (p.get("geo") or {}).get("lat") is not None]
    listable = lambda q: not q.get("exclude") and ((q.get("kind") != "shopping" and q.get("category") != "쇼핑")
                                                   or lcls3(q).startswith(NEARBY_SHOP_LCLS))
    family, alias = raw_family(places)
    shown = {q["id"] for q in live if listable(q)}
    n = 0
    for p in live:
        if "nearby" in set(p.get("locks") or []):
            continue
        fam = family.get(p["id"]) or set()
        dists = sorted(((haversine_m(p["geo"]["lat"], p["geo"]["lng"], q["geo"]["lat"], q["geo"]["lng"]), q)
                        for q in live if q is not p and listable(q) and q["id"] not in fam
                        and alias.get(q["id"]) not in shown), key=lambda x: x[0])
        groups = {k: [] for k in KINDS}
        geos = [p["geo"]]
        for d, q in dists:
            if d > NEARBY_RADIUS_M:
                break
            g = groups.get(q.get("kind"))
            if g is not None and len(g) < NEARBY_PER_KIND:
                g.append({"name": q["name"], "kind": q["kind"], "type_label": q.get("category") or "",
                          "distance_m": int(round(d)), "internal_slug": q["slug"],
                          "contentid": (q.get("tourapi") or {}).get("contentid", "")})
                geos.append(q["geo"])
        nearby = [n for k in KINDS for n in groups[k]]
        kept = (p.get("nearby_source") or {}).get("checked_at") if nearby == p.get("nearby") else ""
        p["nearby"] = nearby
        # whose coordinates the distances come from: this place's point and every listed place's, TourAPI first
        # ('한국관광공사 TourAPI 좌표' when all are TourAPI's, '한국관광공사 TourAPI·<another provider> 좌표' when mixed)
        providers = geo_providers(geos)
        p["nearby_source"] = {"provider": nearby_provider(providers), "providers": providers,
                              "radius_m": NEARBY_RADIUS_M, "distance_basis": "직선거리", "checked_at": kept or today}
        n += bool(p["nearby"])
    return n


def run_nearby_only(data_dir: Path, today: str | None = None) -> dict:
    """--nearby-only: recompute every place's nearby list from the coordinates already in places.json (compute_nearby)
    and write it back. No TourAPI client is created and nothing is fetched; locks are kept."""
    import datetime as dt
    path = data_dir / "places.json"
    places = json.loads(path.read_text("utf-8"))
    before = {p["id"]: p.get("nearby") for p in places}
    n = compute_nearby(places, today or dt.date.today().isoformat())
    path.write_text(json.dumps(places, ensure_ascii=False, indent=2) + "\n", "utf-8")
    changed = sum(1 for p in places if p.get("nearby") != before.get(p["id"]))
    return {"nearby_pages": n, "changed": changed}


def _priority(p: dict) -> tuple:
    """Detail calls go to the pages people read first: full tier, question places, attractions, the rest, shops last
    (owner decision 2026-10-19: most are brand stores in outlets and department stores) — markets, local-produce halls
    and bookstores (NEARBY_SHOP_LCLS) first among the shops."""
    shop = p.get("kind") == "shopping"
    lcls = str((p.get("tourapi") or {}).get("lclsSystm3") or "")
    return (p.get("tier") != "full", not p.get("question_ids"), shop, shop and not lcls.startswith(NEARBY_SHOP_LCLS),
            p.get("kind") != "attraction", p.get("name", ""))


def fetched_on(api, start: int, today: str) -> str:
    """Oldest fetch date of the responses the client answered since `start` (len(api.fetched_dates) before the
    calls): a cached response keeps the date it was fetched, so re-running from cache changes no 확인일."""
    dates = (getattr(api, "fetched_dates", None) or [])[start:]
    return min(dates) if dates else today


def unlisted(items: list[dict], places: list[dict], n: dict, region: str, overrides: dict, same: dict, skip: set,
             hold: set, different: set):
    """The list items of the place types (NEW_PLACE_TYPES) whose contentid is not in places.json yet, attractions
    first, shops (38) last. A contentid the overrides skip, hold or tie to a record of ours (same) is not given; one that may be a record
    of ours (duplicate_candidates — unless the overrides say different) is held for a person. Skips and holds are
    counted in `n` (skipped, held_duplicate_candidates). A generator: a place added while it runs is a candidate for the
    items after it."""
    from tools.tourapi_details import NEW_PLACE_TYPES, duplicate_candidates
    have = {str((p.get("tourapi") or {}).get("contentid")) for p in places if (p.get("tourapi") or {}).get("contentid")}
    todo = sorted((it for it in items if str(it.get("contenttypeid")) in NEW_PLACE_TYPES
                   and str(it["contentid"]) not in have and str(it["contentid"]) not in same),
                  key=lambda it: (str(it.get("contenttypeid")) not in ("12", "14", "28"), str(it.get("contenttypeid")) == "38",
                                  it.get("title", "")))
    for it in todo:
        cid = str(it["contentid"])
        if cid in skip:
            n["skipped"] += 1
            continue
        if cid in hold:
            n["held_duplicate_candidates"].append({"contentid": cid, "title": it.get("title", ""),
                                                   "addr": it.get("addr1", ""), "candidates": [],
                                                   "note": (overrides.get("hold") or {})[cid]})
            continue
        cands = duplicate_candidates(it, places, region)
        if cands and cid not in different:
            n["held_duplicate_candidates"].append({"contentid": cid, "title": it.get("title", ""),
                                                   "addr": it.get("addr1", ""), "candidates": cands})
            continue
        yield it


def _details(api, cid: str, ctype: str) -> tuple[dict, dict, list]:
    common = retry(api.detail_common, cid)
    intro = retry(api.detail_intro, cid, ctype) if ctype else {}
    info = retry(api.detail_info, cid, ctype) if ctype in ("12", "28") else []
    return common, intro, info


def run(data_dir: Path, max_calls: int, offline: bool, gallery: bool = False, details: bool = False,
        add_new: bool = False, events: bool = False, refresh: bool = False, districts: list[str] | None = None,
        events_from: str | None = None, echo: bool = True, lists_only: bool = False) -> dict:
    """lists_only (--lists-only, cache only — the caller passes offline): after the lists, matching and reclassify,
    every listed place not in places.json yet is added from its list item alone (tourapi_details.list_place, draft,
    tourapi.details_pending) — no detail call; a later --details run fills those places like any other."""
    import datetime as dt

    from pipeline import city
    from tools.tourapi_details import (alternate_name, clean, complete_listed, event_key, festival_event, list_place,
                                       merge_facts, new_place, tourapi_facts)
    if lists_only and (details or add_new or events or gallery or refresh):
        raise ValueError("lists_only runs without details, add_new, events, gallery and refresh")
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
    sizes: dict[str, dict[str, int]] = {}
    for it in items:   # list sizes per 구·군 and content type: the numbers the call budget is made of
        where = sizes.setdefault(it.get("_signgu_name") or region, {})
        ctype = str(it.get("contenttypeid") or "")
        where[ctype] = where.get(ctype, 0) + 1
    stats = {"list_items": len(items), "districts": [n for _, n in signgus], "region_codes": {
                 "lDongRegnCd": regn, "signgu": [{"code": c, "name": n} for c, n in signgus]},
             "list_sizes": sizes, "region_notes": region_notes,
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
        if "geo_kept" in ch:
            stats.setdefault("geo_kept", []).append(f"{p['name']}: {p['geo'].get('source')} 좌표 유지 "
                                                    f"(TourAPI 좌표와 {ch['geo_kept']}m)")
        if ch["image"]:
            stats["images"][ch["image"]] += 1
        elif cand.get("firstimage"):
            stats["image_other_type"] += 1
    # every place TourAPI lists keeps its classification codes, and its kind follows them (카페·디저트, 쇼핑)
    stats["reclassified"] = reclassify(places, by_cid)
    if gallery:
        stats["gallery_added"] = sum(add_gallery(api, p, allowed) for p in places
                                     if not p.get("duplicate_of") and (p.get("tourapi") or {}).get("match_basis"))
    detail_log: list[str] = []
    fest: list[dict] | None = None
    try:
        if events:
            ev_path = data_dir / "events.json"
            existing = json.loads(ev_path.read_text("utf-8")) if ev_path.exists() else []
            e = stats["events"] = {"festival_items": 0, "added": [], "updated": [], "errors": []}
            mark = len(getattr(api, "fetched_dates", []))
            # a 광역시: one list for the whole 시도 (each item's address names its 구·군); a 시: its 시군구.
            # From today: the home shows the festivals still to come (--events-from for an earlier day).
            start_day = events_from or today.replace("-", "")
            e["from"] = start_day
            fest = fetch_festivals(api, start_day, regn, None if sido else signgus[0][0])
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
                                    "listed_completed": 0, "errors": []}
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
                checked = fetched_on(api, start, today)
                old_home = (p.get("facts") or {}).get("homepage")
                res = merge_facts(p, tourapi_facts(common, intro, info, ctype), checked, cid)
                new_home = (p.get("facts") or {}).get("homepage")
                off = p.get("official") or {}
                # the official link a TourAPI homepage gave follows that value when it is read again (QA 2026-10-19 QA-21)
                if (old_home and new_home and new_home != old_home and off.get("homepage") == old_home
                        and "official" not in (p.get("locks") or [])):
                    off["homepage"] = first_line(new_home)
                if t.get("details_pending"):   # a place added from its list item (--lists-only): now complete
                    complete_listed(p, common, checked, allowed)
                    d["listed_completed"] += 1
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
            taken = {p["slug"] for p in places}
            for it in unlisted(items, places, n, region, overrides, same, skip, hold, different):
                cid = str(it["contentid"])
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
                if place["images"]:
                    lic = place["images"][0]["license"]
                    stats["images"][lic] = stats["images"].get(lic, 0) + 1
                elif common.get("firstimage") or it.get("firstimage"):   # Type2·4 or no type: not taken
                    stats["image_other_type"] += 1
        if lists_only:   # no call: each listed place not in places.json yet, from its list item (details pending)
            n = stats["list_only"] = {"added": [], "held_duplicate_candidates": [], "skipped": 0}
            taken = {p["slug"] for p in places}
            for it in unlisted(items, places, n, region, overrides, same, skip, hold, different):
                place = list_place(it, it.get("_listed_on") or today, allowed, taken)
                places.append(place)
                n["added"].append(f"{place['kind']}:{place['name']}")
                if place["images"]:
                    lic = place["images"][0]["license"]
                    stats["images"][lic] = stats["images"].get(lic, 0) + 1
                elif it.get("firstimage"):   # Type2·4 or no type: not taken
                    stats["image_other_type"] += 1
    except TourAPIStopError as err:
        stats["stopped"] = str(err)
    stats["nearby_pages"] = compute_nearby(places, today)
    stats["live_calls"] = api.live_calls
    stats["cache_hits"] = api.cache_hits
    stats["remaining_calls"] = remaining_calls(api, places, items, fest if events else [], skip, same, gallery)
    places_path.write_text(json.dumps(places, ensure_ascii=False, indent=2) + "\n", "utf-8")
    report = Path("reports")
    report.mkdir(exist_ok=True)
    lines = [f"# TourAPI 일괄 보강 ({today})", "", f"- 시군구 {', '.join(stats['districts'])}",
             *[f"- 확인: {x}" for x in region_notes],
             f"- 목록 항목 {len(items)} · 실호출 {api.live_calls} · 캐시 {api.cache_hits}",
             f"- 대상 {stats['targets']} · 매칭 {stats['matched']} · 좌표 {stats['geo']}",
             f"- 허용 사진 Type1 {stats['images']['KOGL-1']} · Type3 {stats['images']['KOGL-3']}"
             f" · 사진은 있으나 허용 외 유형 {stats['image_other_type']}",
             f"- 직선거리 주변이 생긴 장소 {stats['nearby_pages']}",
             f"- 남은 호출(캐시에 없는 응답, 캐시 우선 기준): {stats['remaining_calls']}"]
    lines += [f"- 다른 출처 좌표 유지: {x}" for x in stats.get("geo_kept") or []]
    lines += [f"- 종류 변경(TourAPI 분류): {x}" for x in stats.get("reclassified") or []]
    if stats.get("stopped"):
        lines.append(f"- 중단: {stats['stopped']}")
    if "details" in stats:   # not when the run stopped before the details (the call cap during the festivals)
        d = stats["details"]
        lines += ["", "## 상세(detailCommon2·detailIntro2·detailInfo2)", "",
                  f"- 처리 {d['done']}곳 · 새로 채운 항목 {d['added']} · 기존 값과 일치 {d['confirmed']}",
                  f"- 값이 달라 둘 다 표시 {len(d['conflicts'])}건 · 다른 이름 {d['alternate_names']}곳 · 오류 {len(d['errors'])}"
                  + (f" · 목록만으로 추가했던 곳 상세 완료 {d['listed_completed']}곳" if d["listed_completed"] else "")]
        lines += detail_log + [f"- 오류: {x}" for x in d["errors"]]
    for part, head in (("new_places", "TourAPI에만 있는 장소"),
                       ("list_only", "목록만으로 추가한 장소(--lists-only, 호출 없음 — 상세는 다음 수집)")):
        n = stats.get(part)
        if not n:
            continue
        lines += ["", f"## {head}", "", f"- 추가 {len(n['added'])} · 중복 의심 보류 "
                  f"{len(n['held_duplicate_candidates'])} · 제외 {n['skipped']}"
                  + (f" · 오류 {len(n['errors'])}" if "errors" in n else "")]
        lines += [f"- 추가: {x}" for x in n["added"]]
        for h in n["held_duplicate_candidates"]:
            lines.append(f"- 보류 {h['contentid']} {h['title']} ({h['addr']}) ↔ "
                         + ", ".join(f"{c['name']}[{c['slug']}] {c['address']}" for c in h["candidates"]))
    if events:
        e = stats["events"]
        lines += ["", "## 행사(searchFestival2)", "", f"- {e.get('from', '')}부터 · 응답 {e['festival_items']} · "
                  f"추가 {len(e['added'])} · 갱신 {len(e['updated'])}"]
        lines += [f"- 추가: {x}" for x in e["added"]] + [f"- 갱신: {x}" for x in e["updated"]]
    lines += ["", "## 미매칭"] + [f"- {x}" for x in stats["unmatched"]]
    (report / "tourapi_bulk.md").write_text("\n".join(lines) + "\n", "utf-8")
    (report / "tourapi_bulk.json").write_text(json.dumps(stats, ensure_ascii=False, indent=1) + "\n", "utf-8")
    out = {k: v for k, v in stats.items()
           if k not in ("unmatched", "details", "new_places", "list_only", "events", "geo_kept")}
    out["unmatched"] = len(stats["unmatched"])
    out["geo_kept"] = len(stats.get("geo_kept") or [])
    if "details" in stats:
        out["details"] = {k: (len(v) if isinstance(v, list) else v) for k, v in stats["details"].items()}
    for part in ("new_places", "list_only"):
        if part in stats:
            out[part] = {k: (len(v) if isinstance(v, list) else v) for k, v in stats[part].items()}
    if events:
        out["events"] = {k: (len(v) if isinstance(v, list) else v) for k, v in stats["events"].items()}
    if echo:
        print(json.dumps(out, ensure_ascii=False))
    return stats


def squash(value: str) -> str:
    return re.sub(r"\s+", " ", value or "").strip()[:80]


def run_barrier_free(data_dir: Path, max_calls: int, offline: bool = False, refresh: bool = False,
                     report_dir: Path = Path("reports")) -> dict:
    """--barrier-free: KorWithService2 detailWithTour2 for the published places with a contentid (see the module
    docstring). Writes places.json and reports/tourapi_barrier_free.{md,json}."""
    import datetime as dt
    from pipeline.tourapi import barrier_free_client
    from tools.tourapi_details import BARRIER_FREE, display_name, merge_facts, with_facts
    load_dotenv(Path(".env"))
    site = json.loads((data_dir / "site.json").read_text("utf-8"))
    places_path = data_dir / "places.json"
    places = json.loads(places_path.read_text("utf-8"))
    api = barrier_free_client(site, os.environ.get("TOURAPI_KEY", ""), data_dir.parent / "cache" / "tourapi",
                              offline=offline, refresh=refresh, max_calls=max_calls)
    today = dt.date.today().isoformat()
    targets = sorted((p for p in places if p.get("status") == "published" and not p.get("duplicate_of")
                      and (p.get("tourapi") or {}).get("contentid")), key=_priority)
    s = {"service": api.base_url, "targets": len(targets), "done": 0, "with_data": 0, "no_data": [],
         "title_mismatch": [], "added": {}, "confirmed": {}, "also": {}, "conflicts": [], "errors": []}
    log: list[str] = []
    try:
        for p in targets:
            cid = str(p["tourapi"]["contentid"])
            start = len(api.fetched_dates)
            try:
                facts = with_facts(retry(api.detail_with_tour, cid))
                if not facts:
                    s["done"] += 1
                    s["no_data"].append(p["name"])
                    continue
                title = (retry(api.detail_common, cid) or {}).get("title")
            except TourAPIStopError:
                raise
            except TourAPIError as err:
                s["errors"].append(f"{p['name']}: {err}")
                continue
            s["done"] += 1
            ours = (p.get("tourapi") or {}).get("title") or p["name"]
            if normalize_name(display_name(title)) != normalize_name(display_name(ours)):
                s["title_mismatch"].append(f"{p['name']} ({cid}): 무장애 '{title or '없음'}' ≠ TourAPI '{ours}'")
                continue
            s["with_data"] += 1
            before = {k: (p.get("facts") or {}).get(k, "") for k in facts}
            res = merge_facts(p, facts, fetched_on(api, start, today), cid, provider=BARRIER_FREE)
            for part in ("added", "confirmed", "also"):
                for k in res[part]:
                    s[part][k] = s[part].get(k, 0) + 1
            for part, word in (("added", "추가"), ("confirmed", "일치"), ("also", "함께 표시"), ("conflicts", "값이 다름")):
                for k in res[part]:
                    old = f"기존 '{squash(before[k])}' / " if before[k] else ""
                    log.append(f"- {p['name']} · {k} · {word}: {old}무장애 '{squash(facts[k])}'")
            s["conflicts"] += [f"{p['name']}·{k}" for k in res["conflicts"]]
    except TourAPIStopError as err:
        s["stopped"] = str(err)
    s["live_calls"], s["cache_hits"] = api.live_calls, api.cache_hits
    places_path.write_text(json.dumps(places, ensure_ascii=False, indent=2) + "\n", "utf-8")
    report_dir.mkdir(parents=True, exist_ok=True)
    lines = [f"# TourAPI 무장애 여행 정보 ({today})", "",
             f"- 서비스 {s['service']} · 실호출 {s['live_calls']} · 캐시 {s['cache_hits']}",
             f"- 대상(공개·contentid) {s['targets']} · 처리 {s['done']} · 값 있음 {s['with_data']} · 값 없음 {len(s['no_data'])}"
             f" · 제목 불일치 {len(s['title_mismatch'])} · 오류 {len(s['errors'])}",
             f"- 추가 {s['added']} · 일치 {s['confirmed']} · 함께 표시 {s['also']} · 값이 달라 둘 다 표시 {len(s['conflicts'])}"]
    if s.get("stopped"):
        lines.append(f"- 중단: {s['stopped']} (다시 실행하면 캐시로 이어 갑니다)")
    lines += ["", "## 장소별", ""] + (log or ["- 없음"])
    lines += ["", "## 제목 불일치(병합하지 않음)", ""] + [f"- {x}" for x in s["title_mismatch"]]
    lines += ["", "## 오류", ""] + [f"- {x}" for x in s["errors"]]
    lines += ["", "다음: 값이 달라진 장소의 요약·FAQ·가이드 문장(예: guide-29·guide-02의 휠체어 대수)을 두 출처로 고쳐 쓰고,"
              " 바뀐 장소·가이드를 8개 언어로 다시 번역한다(tools/en_content.py)."]
    (report_dir / "tourapi_barrier_free.md").write_text("\n".join(lines) + "\n", "utf-8")
    (report_dir / "tourapi_barrier_free.json").write_text(json.dumps(s, ensure_ascii=False, indent=1) + "\n", "utf-8")
    print(json.dumps({k: (len(v) if isinstance(v, list) else v) for k, v in s.items()}, ensure_ascii=False))
    return s


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
                    help="TourAPI에만 있는 장소(유형 12·14·28·32·38·39)를 draft/basic으로 추가(중복 의심은 보류)")
    ap.add_argument("--events", action="store_true", help="searchFestival2(오늘부터, 모든 쪽)로 행사 갱신")
    ap.add_argument("--events-from", default="", help="행사를 이 날짜(YYYYMMDD)부터 받는다(기본: 오늘)")
    ap.add_argument("--districts", default="", help="광역시에서 이 구·군만(쉼표로, 예: 연수구,강화군) — 호출 한도 안에서 나눠 받을 때")
    ap.add_argument("--barrier-free", action="store_true",
                    help="무장애 여행 정보(KorWithService2 detailWithTour2)를 공개 장소에 병합 — 이 옵션만 따로 실행")
    ap.add_argument("--nearby-only", action="store_true",
                    help="places.json의 좌표로 주변 장소(nearby)만 다시 계산 — TourAPI 호출 없음, 이 옵션만 따로 실행")
    ap.add_argument("--lists-only", action="store_true",
                    help="캐시의 목록 응답만으로 아직 없는 장소를 draft로 추가(상세 대기 표시) — TourAPI 호출 없음(캐시만, "
                         "키 없이), 상세는 다음 --details 수집이 채운다. --districts만 함께 쓴다")
    a = ap.parse_args(argv)
    if a.nearby_only:
        if a.gallery or a.details or a.add_new or a.events or a.barrier_free or a.refresh:
            ap.error("--nearby-only는 다른 옵션 없이 따로 실행합니다")
        print(json.dumps(run_nearby_only(a.data), ensure_ascii=False))
        return 0
    only = [x.strip() for x in a.districts.split(",") if x.strip()] or None
    if a.events_from and not re.fullmatch(r"\d{8}", a.events_from):
        ap.error("--events-from은 YYYYMMDD")
    if a.lists_only and (a.gallery or a.details or a.add_new or a.events or a.barrier_free or a.refresh):
        ap.error("--lists-only는 --districts 말고 다른 옵션 없이 따로 실행합니다(호출 없음)")
    try:
        if a.lists_only:
            run(a.data, a.max_calls, True, districts=only, lists_only=True)
            return 0
        if a.barrier_free:
            if a.gallery or a.details or a.add_new or a.events:
                ap.error("--barrier-free는 다른 보강 옵션 없이 따로 실행합니다")
            run_barrier_free(a.data, a.max_calls, a.offline, a.refresh)
            return 0
        run(a.data, a.max_calls, a.offline, a.gallery, a.details, a.add_new, a.events, a.refresh, only,
            a.events_from or None)
    except RegionError as err:
        print(f"중단: {err}", file=sys.stderr)
        return 1
    except TourAPIError as err:   # a provider error before any data was written (masked key, provider message as-is)
        print(f"중단: {err} — python tools/tourapi_doctor.py --data {a.data} 로 키·네트워크를 확인하세요.", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
