"""TourAPI detail merge for tools/tourapi_bulk.py --details: per-field sources, agreement and conflicts.

Called with the cached/live responses of detailCommon2 · detailIntro2 (· detailInfo2 for types 12/28).
Rules (CLAUDE.md 3절 1·2):
- A value is copied as the provider gives it (HTML stripped); nothing is inferred.
- Every fact key written here records its own source in `fact_sources[key]` (provider, checked_at, contentid).
- When the place already holds a value from another source:
    same meaning  -> keep it and note the agreement (`fact_sources[key].confirmed_by`)
    different     -> keep both: the TourAPI value goes to `fact_alternatives[key]`; the page shows both values
                     with their providers and "방문 전 전화 확인". Neither side is picked.
- `overview` is never copied into page text (kept under tourapi.overview for fact checking only).
"""
from __future__ import annotations

import re
from difflib import SequenceMatcher

from pipeline.schema import TOURAPI_LICENSE_MAP, license_allowed
from pipeline.textutil import extract_url, normalize_name, slugify, squash_ws, strip_html
from pipeline.tourapi import CONTENT_TYPES, INTRO_FIELDS, KIND_BY_TYPE

PROVIDER = "한국관광공사 TourAPI"
NEW_PLACE_TYPES = ("12", "14", "28", "32", "38", "39")
# detailIntro2 fields beyond pipeline.tourapi.INTRO_FIELDS (our fact key -> field per content type)
EXTRA_INTRO = {
    "seat": {"39": "seat"},
    "treatmenu": {"39": "treatmenu"},
    "packing": {"39": "packing"},
    "kidsfacility": {"39": "kidsfacility"},
    "reservation": {"39": "reservationfood", "32": "reservationlodging", "28": "reservation"},
    "reservationurl": {"32": "reservationurl"},
    "roomcount": {"32": "roomcount"},
    "roomtype": {"32": "roomtype"},
    "subfacility": {"32": "subfacility"},
    "cooking": {"32": "chkcooking"},
    "creditcard": {"12": "chkcreditcard", "14": "chkcreditcardculture", "28": "chkcreditcardleports",
                   "38": "chkcreditcardshopping", "39": "chkcreditcardfood"},
    "expguide": {"12": "expguide"},
    "discount": {"14": "discountinfo"},
    "openperiod": {"28": "openperiod"},
    "fairday": {"38": "fairday"},
    "saleitem": {"38": "saleitem"},
    "shopguide": {"38": "shopguide"},
}
FEE_INFO = re.compile(r"입장료|관람료|이용요금|이용료|요금")
FILMING_INFO = re.compile(r"촬영")
EMPTY = {"", "-", "0", "없음 없음", "null", "none"}
GLUED_PHONES = re.compile(r"(0\d{1,3}-\d{3,4}-\d{4})(?=0\d{1,3}-)")
FLAG_FIELDS = {"kidsfacility"}  # provider sends 0/1
# Two different values here do not contradict each other (a second signature dish, another phone line or
# web page): both are shown with their providers, without the "방문 전 전화 확인" warning.
COMPLEMENTARY = {"menu", "treatmenu", "homepage", "reservationurl", "infocenter", "reservation"}
# our keys that already hold the same information under a combined key
COMBINED = {"usetime_restdate": ("usetime", "restdate"), "parking_seats": ("parking", "seat")}


def clean(value) -> str:
    text = strip_html(value if isinstance(value, str) else ("" if value is None else str(value)))
    text = "\n".join(squash_ws(line) for line in text.splitlines() if squash_ws(line))
    return "" if text.strip().lower() in EMPTY else text.strip()


def _ints(value: str) -> set[int]:
    return {int(x) for x in re.findall(r"\d+", value or "")}


def _norm(value: str) -> str:
    s = strip_html(value or "").lower()
    s = s.replace("：", ":").replace("～", "~").replace("〜", "~")
    return re.sub(r"[\s·,.:;()\[\]<>※*~\-–—/|'\"`]", "", s)


def _yesno(value: str) -> bool | None:
    n = _norm(value)
    if not n:
        return None
    if re.search(r"불가|불가능|없음|안됨|미운영|^x$|^무$|^n$", n):
        return False
    if re.search(r"가능|있음|^o$|^유$|^y$|운영", n):
        return True
    return None


ALWAYS = re.compile(r"^(연중(무휴|개방)?|상시(개방)?|24시간(개방)?|항시개방|연중상시개방)$")
FILLER = {"휴관", "휴무", "휴일", "정기휴일", "쉼", "운영", "개방", "가능", "있음"}


def _tokens(value: str) -> list[str]:
    return [t for t in re.split(r"[\s·,.:;()\[\]<>※*~\-–—/|'\"`]+", strip_html(value or "").lower()) if t and t not in FILLER]


def more_detailed(a: str, b: str) -> bool:
    """b repeats everything a says (numbers and words) and adds more."""
    nb = _norm(b)
    return (len(nb) > len(_norm(a)) and _ints(a) <= _ints(b)
            and all(_norm(t) in nb for t in _tokens(a)))


def same_meaning(a: str, b: str) -> bool:
    """True when two provider values say the same thing (one may be more detailed than the other)."""
    na, nb = _norm(a), _norm(b)
    ya, yb = _yesno(a), _yesno(b)
    if ya is not None and yb is not None and ya != yb:  # '가능' is inside '불가능'
        return False
    if not na or not nb or na == nb or na in nb or nb in na:
        return True
    if ALWAYS.match(na) and ALWAYS.match(nb):          # '연중무휴' = '상시 개방'
        return True
    if more_detailed(a, b) or more_detailed(b, a):
        return True
    ia, ib = _ints(a), _ints(b)
    if ia and ib:
        return ia <= ib or ib <= ia
    if ya is not None and yb is not None:
        return ya == yb
    if (ia and yb is True) or (ib and ya is True):  # '7대' vs '가능'
        return True
    return False


def same_phone(a: str, b: str) -> bool:
    pa = {re.sub(r"\D", "", m) for m in re.findall(r"0\d{1,2}[-\s)]?\d{3,4}-?\d{4}|1\d{3}-?\d{4}", a or "")}
    pb = {re.sub(r"\D", "", m) for m in re.findall(r"0\d{1,2}[-\s)]?\d{3,4}-?\d{4}|1\d{3}-?\d{4}", b or "")}
    if pa and pb:
        return bool(pa & pb)
    return same_meaning(a, b)


def same_url(a: str, b: str) -> bool:
    key = lambda u: re.sub(r"^https?://(www\.)?|/+$", "", (u or "").strip().lower())
    return key(a) == key(b) or not key(a) or not key(b)


def tourapi_facts(common: dict, intro: dict, info: list[dict], ctype: str) -> dict:
    """Our fact keys from one place's TourAPI detail responses (values cleaned, empty ones dropped)."""
    facts: dict[str, str] = {}
    for key, by_type in list(INTRO_FIELDS.items()) + list(EXTRA_INTRO.items()):
        field = by_type.get(ctype)
        value = clean(intro.get(field)) if field else ""
        if key in FLAG_FIELDS:
            value = {"1": "있음"}.get(value, "") if value in ("0", "1", "") else value
        if value:
            facts[key] = value
    for key in ("infocenter", "reservation"):  # '063-443-1981063-443-4819': two numbers sent glued together
        if facts.get(key):
            facts[key] = GLUED_PHONES.sub(r"\1, ", facts[key])
    tel = clean(common.get("tel"))
    if "infocenter" not in facts and tel:
        name = clean(common.get("telname"))
        facts["infocenter"] = f"{name} {tel}".strip() if name and name not in tel else tel
    homepage = extract_url(common.get("homepage"))
    if homepage:
        facts["homepage"] = homepage
    addr = " ".join(x for x in (clean(common.get("addr1")), clean(common.get("addr2"))) if x)
    if addr:
        facts["address"] = addr
    for row in info or []:
        name = re.sub(r"\s", "", row.get("infoname") or "")
        text = clean(row.get("infotext"))
        if not text:
            continue
        if "usefee" not in facts and FEE_INFO.search(name) and not re.search(r"주차", name):
            facts["usefee"] = text
        elif "filming" not in facts and FILMING_INFO.search(name):
            facts["filming"] = text
    return facts


def _same(key: str, a: str, b: str) -> bool:
    if key in ("infocenter", "reservation"):
        return same_phone(a, b)
    if key in ("homepage", "reservationurl"):
        return same_url(a, b)
    if key == "address":
        from tools.tourapi_bulk import road_key  # local import: avoid a cycle at module load
        ra, rb = road_key(a), road_key(b)
        if ra and rb:  # '○○로 1685' = '○○로 1685-53': same main number, one adds the sub-number
            return ra.split("-")[0] == rb.split("-")[0]
        return not ra or same_meaning(a, b)  # '해망동 일원' vs a road address in it: the road one is just more exact
    return same_meaning(a, b)


def _prefer_new(key: str, old: str, new: str) -> bool:
    """When both agree, show the more exact value (e.g. a road address, hours with last entry)."""
    if key == "address":
        from tools.tourapi_bulk import road_key
        ro, rn = road_key(old), road_key(new)
        return (not ro and bool(rn)) or (bool(ro) and "-" not in ro and "-" in rn)
    if key in ("homepage", "reservationurl", "infocenter", "reservation"):
        return False
    return more_detailed(old, new)


def merge_facts(place: dict, new: dict, today: str, contentid: str) -> dict:
    """Merge TourAPI facts into place in-place. Returns {'added': [...], 'confirmed': [...], 'conflicts': [...]}."""
    locks = set(place.get("locks") or [])
    out = {"added": [], "confirmed": [], "conflicts": [], "also": []}
    if "facts" in locks:
        return out
    facts = place.setdefault("facts", {})
    sources = place.setdefault("fact_sources", {})
    alts = place.setdefault("fact_alternatives", {})
    base = place.get("facts_source") or {}
    src = {"provider": PROVIDER, "checked_at": today, "contentid": contentid}

    def own_source(key: str) -> dict:
        return sources.get(key) or {k: v for k, v in base.items() if k in ("provider", "checked_at", "url", "contentid")}

    def record_alt(key: str, value: str) -> None:
        cur = [a for a in alts.get(key, []) if a.get("provider") != PROVIDER]
        also = key in COMPLEMENTARY
        alts[key] = cur + [{"value": value, **src, **({"relation": "also"} if also else {})}]
        out["also" if also else "conflicts"].append(key)

    def confirm(key: str) -> None:
        s = dict(own_source(key))
        if s.get("provider") != PROVIDER:
            prev = s.get("confirmed_by") or ""
            if PROVIDER not in prev:  # a re-run keeps the richer note written earlier (e.g. '… · <city tourism site> 본문')
                s["confirmed_by"] = " · ".join(x for x in (prev, f"{PROVIDER} {today}") if x)
            sources[key] = s
            out["confirmed"].append(key)

    handled = set()
    for combined, parts in COMBINED.items():  # e.g. the city site's '영업시간·정기휴일' vs TourAPI 영업시간 + 쉬는 날
        if not facts.get(combined) or not any(new.get(p) for p in parts):
            continue
        joined = " / ".join(new[p] for p in parts if new.get(p))
        if combined == "parking_seats":
            ok = all(same_meaning(facts[combined], new[p]) or (p == "seat" and _ints(new[p]) <= _ints(facts[combined]))
                     for p in parts if new.get(p))
        else:
            ok = same_meaning(facts[combined], joined)
        if ok:
            confirm(combined)
        else:
            record_alt(combined, joined)
        handled.update(p for p in parts if new.get(p))

    for key, value in new.items():
        if key in handled:
            continue
        if not facts.get(key):
            facts[key] = value
            sources[key] = dict(src)
            out["added"].append(key)
            continue
        if own_source(key).get("provider") == PROVIDER:  # our own earlier copy: refresh
            prev = own_source(key)
            # unchanged value: keep what an earlier run recorded about the other source
            keep = {k: prev[k] for k in ("confirmed_by", "note", "raw") if k in prev and facts[key] == value}
            facts[key] = value
            sources[key] = {**src, **keep}
            continue
        if _same(key, facts[key], value):
            if _prefer_new(key, facts[key], value):
                prev = own_source(key)
                sources[key] = {**src, "confirmed_by": f"{prev.get('provider', '')} {prev.get('checked_at', '')}".strip(),
                                "note": f"{prev.get('provider', '다른 출처')} 표기: {squash_ws(facts[key])}"}
                facts[key] = value
                out["confirmed"].append(key)
            else:
                confirm(key)
        else:
            record_alt(key, value)
    for key in [k for k, v in alts.items() if not v]:
        alts.pop(key)
    if not alts:
        place.pop("fact_alternatives", None)
    return out


def display_name(title: str | None) -> str:
    """'X사(<city>)' -> 'X사' (the active city's names in brackets, pipeline/city.py), '[백년가게]Y반점' -> 'Y반점'."""
    from pipeline import city
    names = "|".join(re.escape(n) for n in city.current().names)
    rx = (rf"\s*\((?:{names})\)|" if names else "") + r"\[[^\]]*\]\s*"
    return re.sub(rx, "", title or "").strip()


def alternate_name(place: dict, title: str | None) -> str:
    """TourAPI's own name when it differs from ours in more than spacing/brackets (e.g. '<city>근대역사박물관')."""
    name = display_name(title)
    mine, theirs = normalize_name(place.get("name")), normalize_name(name)
    # 'X사' for our '<city> X사 대웅전' names the whole temple, '궁전' for '궁전갈치찜' is a shortening: not another name
    if not name or theirs == mine or theirs in mine:
        return ""
    return name


def https(url: str) -> str:
    return "https://" + url[len("http://"):] if (url or "").startswith("http://") else (url or "")


def new_place(item: dict, common: dict, intro: dict, info: list[dict], today: str, allowed, taken: set) -> dict:
    """A draft/basic place for a TourAPI item that matches nothing in the region's data. A 광역시's items carry the
    구·군 TourAPI listed them under (tourapi_bulk: '_signgu_name'), kept as `district` (pipeline/city.py district_of
    reads it when the address names none)."""
    cid, ctype = str(item["contentid"]), str(item.get("contenttypeid") or "")
    name = display_name(common.get("title") or item.get("title"))
    slug, n = slugify(name), 2
    while slug in taken:
        slug, n = f"{slugify(name)}-{n}", n + 1
    taken.add(slug)
    facts = tourapi_facts(common, intro, info, ctype)
    place = {
        "id": f"tourapi-{cid}", "name": name, "slug": slug, "kind": KIND_BY_TYPE[ctype],
        "category": CONTENT_TYPES.get(ctype, ""), "themes": [], "tier": "basic", "status": "draft",
        "official": {"homepage": facts["homepage"]} if facts.get("homepage") else {},
        "original": {}, "map_ids": {"naver_place_id": "", "google_place_id": ""}, "images": [],
        "facts": facts,
        "facts_source": {"provider": PROVIDER, "contentid": cid, "checked_at": today},
        "fact_sources": {k: {"provider": PROVIDER, "checked_at": today, "contentid": cid} for k in facts},
        "summary": "",
        "tourapi": {"contentid": cid, "contenttypeid": ctype, "title": common.get("title") or item.get("title", ""),
                    "match_basis": "tourapi_only", "modifiedtime": common.get("modifiedtime") or item.get("modifiedtime", ""),
                    "lcls": common.get("lclsSystm3") or item.get("lclsSystm3", ""),
                    "overview": clean(common.get("overview"))},
    }
    try:
        lat, lng = float(common.get("mapy") or item.get("mapy")), float(common.get("mapx") or item.get("mapx"))
        place["geo"] = {"lat": lat, "lng": lng, "source": "TourAPI"}
    except (TypeError, ValueError):
        pass
    if item.get("_signgu_name"):
        place["district"] = item["_signgu_name"]
    first = common.get("firstimage") or item.get("firstimage")
    code = TOURAPI_LICENSE_MAP.get(str(common.get("cpyrhtDivCd") or item.get("cpyrhtDivCd") or ""), "UNKNOWN")
    if first and license_allowed(code, allowed):
        place["images"] = [{"url": https(first), "alt": name, "credit": "한국관광공사", "license": code, "source": "TourAPI"}]
    return place


def duplicate_candidates(item: dict, places: list[dict], region: str) -> list[dict]:
    """The region's records that may be the same place as an unmatched TourAPI item (for a person or reviewer)."""
    from tools.tourapi_bulk import GENERIC, name_key, road_key
    kind = KIND_BY_TYPE.get(str(item.get("contenttypeid")))
    nk = name_key(display_name(item.get("title")), region)
    rk = road_key(item.get("addr1"))
    core = lambda s: GENERIC.sub("", s)
    out = []
    for p in places:
        if p.get("duplicate_of") or (p.get("tourapi") or {}).get("contentid") or p.get("kind") != kind:
            continue
        pk = name_key(p.get("name"), region)
        ratio = SequenceMatcher(None, nk, pk).ratio()
        same_road = bool(rk) and rk == road_key((p.get("facts") or {}).get("address"))
        contains = min(len(core(nk)), len(core(pk))) >= 2 and (core(nk) in core(pk) or core(pk) in core(nk))
        if same_road or ratio >= 0.7 or contains:
            out.append({"slug": p["slug"], "name": p["name"], "address": (p.get("facts") or {}).get("address", ""),
                        "ratio": round(ratio, 2), "same_road": same_road, "contains": contains})
    return sorted(out, key=lambda c: (-c["same_road"], -c["ratio"]))[:3]


def festival_event(item: dict, intro: dict, common: dict, today: str) -> dict:
    iso = lambda d: f"{d[:4]}-{d[4:6]}-{d[6:8]}" if re.fullmatch(r"\d{8}", d or "") else ""
    cid = str(item["contentid"])
    ev = {
        "id": f"event-tourapi-{cid}", "contentid": cid, "status": "draft",
        "name": clean(item.get("title")),
        "start_date": iso(str(item.get("eventstartdate") or intro.get("eventstartdate") or "")),
        "end_date": iso(str(item.get("eventenddate") or intro.get("eventenddate") or "")),
        "place_name": clean(intro.get("eventplace")),
        "address": " ".join(x for x in (clean(item.get("addr1")), clean(item.get("addr2"))) if x),
        "summary": "", "source_name": PROVIDER, "source_url": "", "checked_at": today,
    }
    for key, field in (("playtime", "playtime"), ("fee", "usetimefestival"), ("sponsor", "sponsor1"),
                       ("tel", "sponsor1tel"), ("agelimit", "agelimit")):
        value = clean(intro.get(field))
        if value:
            ev[key] = value
    homepage = extract_url(common.get("homepage") or intro.get("eventhomepage"))
    if homepage:
        ev["homepage"] = homepage
    try:
        ev["geo"] = {"lat": float(item.get("mapy")), "lng": float(item.get("mapx")), "source": "TourAPI"}
    except (TypeError, ValueError):
        ev["geo"] = {}
    return ev


def event_key(name: str | None) -> str:
    """'2026 ○○축제' and '제12회 ○○축제' -> same key."""
    s = re.sub(r"^\s*(\d{4}\s*년?|제\s*\d+\s*회)\s*", "", name or "")
    return normalize_name(s)
