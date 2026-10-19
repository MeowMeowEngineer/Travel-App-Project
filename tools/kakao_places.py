"""카카오 장소 ID 매칭 — Kakao Local 키워드 검색으로 공개 장소마다 `map_ids.kakao_place_id`를 찾는다.

운영자 결정 2026-10-14: 지도 제공자는 카카오(CLAUDE.md 9 '지도 제공자' 결정). '카카오맵'을 누르면 주소 핀이
아니라 그 가게·시설의 카카오 장소 페이지(https://place.map.kakao.com/<id>, 후기 포함)가 열려야 한다.
pipeline/maplinks.py가 이 ID로 링크를 만든다.

검색: https://dapi.kakao.com/v2/local/search/keyword.json (머리글 Authorization: KakaoAK <키>)
- 좌표가 있는 장소: query=이름, x/y=우리 좌표, radius=1000, sort=accuracy. 받아들일 후보가 없으면
  '<지역> ' + 이름, 괄호 안 이름·별칭(alternate_names) 순으로 한 번씩 더 묻는다.
- 좌표가 없는 장소: query='<지역> ' + 이름(좌표 없이), 없으면 이름만.
- <지역>·지역어는 그 지역 site.json에서 읽는다(pipeline/city.py: region·locality, city.kakao_safe_extras·
  city.kakao_admin_words — 이름 앞에 붙어도 같은 곳으로 보는 도 이름·별칭).
- 응답 원문은 data/cache/kakao/에 저장한다(git 제외). 다시 실행하면 호출하지 않는다. 실행당 호출 상한 --max-calls.
- 키는 환경 변수 KAKAO_REST_KEY 또는 --key-file로만 받는다. 오류 메시지에서는 키만 «KEY»로 가리고 공급자
  메시지는 그대로 보인다.

같은 곳일 때만 받아들인다(추측하지 않는다):
- 이름: 정규화한 이름(공백·문장부호·괄호 제거)이 같거나(괄호 안 이름·alternate_names 포함), 한쪽이 다른 쪽을
  포함하고 남는 부분이
  · 지역어(<지역>·<시 이름>·city.kakao_safe_extras·'본점')면 그대로 통과('○○관세박물관' / '관세박물관'),
  · 업종어·지점명·설명어('식당'·'모텔'·'게스트하우스'·'○○점'·'짬뽕전문점' 등)면 도로명 건물번호(없으면 지번)가
    같을 때만 통과. 업종어 위치만 다른 이름('호텔파라다이스'/'파라다이스 호텔')과 가운데 <지역>만 다른 이름도 같다,
  · 그 밖('주차장'·'입구'·'2호점'·'신관'·'대웅전'·'해수욕장' 등 다른 대상을 가리키는 말)이면 탈락.
- 유형: 우리 숙소가 카카오 음식점·카페이거나 우리 음식점이 카카오 숙박이면 탈락('달' 게스트하우스 ≠ 같은 건물 카페 '달').
- 거리: 우리 좌표에서 150m 이내. 섬·공원·해수욕장·산·항구처럼 넓은 곳(우리 분류·이름 또는 카카오 분류)은 400m.
- 주소: 양쪽 모두 도로명 주소가 있으면 도로명과 건물번호가 같아야 한다. 우리 주소가 지번뿐이면 지번
  (동·리 + 번지)을 비교하고, 넓은 곳이 아니면 달라도 탈락이다. 카카오 주소는 그 지역(region — 카카오는 '인천 중구 …'처럼 줄여 쓴다) 안이어야 한다.
  예외 하나: 이름이 정확히 같고 우리 연락처(facts.infocenter)의 전화번호가 카카오 전화번호와 같으면 건물번호가
  달라도 받는다('중화반점' 동령길 27 / 29, 둘 다 063-452-4044). 우리 좌표가 없으면 도로명은 같아야 한다.
- 좌표가 없는 장소: 이름 + 그 지역 + 건물번호(지번 주소면 번지) 일치(또는 위 전화 예외)가 모두 있어야 한다.
- 통과 후보가 여럿이면, 이름이 정확히 같은 후보가 하나뿐이고 그것이 가장 가까울 때만 받는다. 아니면 보류.
- 우리 장소 둘이 같은 카카오 ID에 붙으면, 본래 이름으로 정확히 맞은 쪽만 남기고 나머지는 보류.

기록(--apply): map_ids.kakao_place_id = "<id>", map_id_sources.kakao_place_id = {provider: 'Kakao Local API',
checked_at, matched_name, distance_m, basis, url, query}. 이 도구가 전에 쓴 ID가 다시 확인되지 않으면 지우고,
사람이 넣은 ID(출처 없음)는 그대로 둔다. 결과 전체는 --report(JSON)에 남긴다.

  KAKAO_REST_KEY=... python tools/kakao_places.py --data data/incheon            # 미리보기(dry-run)
  python tools/kakao_places.py --data data/incheon --key-file <파일> --apply      # places.json에 반영
  python tools/kakao_places.py --data data/incheon --offline --apply             # 캐시만으로 다시 반영
"""
from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import json
import math
import os
import re
import sys
import time
import unicodedata
import urllib.error
import urllib.parse
import urllib.request
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

ENDPOINT = "https://dapi.kakao.com/v2/local/search/keyword.json"
PROVIDER = "Kakao Local API"
PLACE_URL = "https://place.map.kakao.com/{id}"
DEFAULT_MAX_CALLS = 1500
NEAR_M, LARGE_M, SEARCH_RADIUS = 150, 400, 1000

# ----------------------------------------------------------------------------- names
# What may be left over when one normalised name contains the other: '본점' and the city's own words
# (safe_extras(): its names and site.json city.kakao_safe_extras).
SAFE_EXTRAS = {"본점"}


def _city():
    from pipeline import city
    return city.current()


def city_words() -> list[str]:
    """The city's names, normalised, longest first ('인천광역시', '인천')."""
    return sorted({norm(x) for x in _city().names if norm(x)}, key=len, reverse=True)


def safe_extras() -> set[str]:
    return SAFE_EXTRAS | set(city_words()) | {norm(x) for x in _city().get("kakao_safe_extras", []) or []}


def region_prefix() -> re.Pattern:
    """A province word (city.kakao_admin_words) and then the city's name at the start of a normalised name."""
    admins = sorted({norm(x) for x in _city().get("kakao_admin_words", []) or [] if norm(x)}, key=len, reverse=True)
    names = city_words()
    if not names:
        return re.compile(r"(?!)")
    head = f"(?:{'|'.join(map(re.escape, admins))})?" if admins else ""
    return re.compile(rf"^{head}(?:{'|'.join(map(re.escape, names))})")
# Business-type words, descriptors and branch names: the same place only when the building number (or 지번)
# agrees too ('유락식당' / '유락', '링스모텔' / '링스모텔 장미점', '보천사' / '대한불교조계종 보천사').
WEAK_WORDS = ("식당", "음식점", "카페", "커피", "펜션", "모텔", "호텔", "관광호텔", "비즈니스호텔", "민박", "게스트하우스",
              "하우스", "스테이", "리조트", "여관", "횟집", "회집", "회센터", "반점", "중화요리", "레스토랑", "베이커리",
              "제과", "제과점", "빵집", "식육식당", "숯불갈비", "갈비", "한우", "꽃게장", "게장", "명가", "본가",
              "농장", "농원", "도예", "공방", "대한불교조계종", "대한불교태고종", "점")
# a branch: up to five characters + 점 ('경암점', '○○미장점', '비응본점') — but not a kind of shop ('정육점')
BRANCH_RE = re.compile(r"^[가-힣a-z0-9]{1,5}점$")
NOT_BRANCH = re.compile(r"(정육|음식|편의|제과|할인|철물|판매|대리|직영|소매|도매|잡화|문구|꽃|과일|상|매|분)점$")
DESCRIPTOR_RE = re.compile(r"^[가-힣]{1,4}전문점$")         # '짬뽕전문점'
# Generic lodging/food words dropped from both names before a last comparison ('호텔파라다이스' / '파라다이스 호텔',
# '리츠프라자 관광호텔' / '리츠프라자호텔'): equal cores are a weak match (address must agree).
GENERIC_WORDS = re.compile(r"관광호텔|비즈니스호텔|호텔|모텔|게스트하우스|펜션|여관|리조트|식당|카페")
# Leftovers that name a different thing: always rejected.
BAD_EXTRA = re.compile(
    r"주차장|주차타워|주차|정류장|정류소|승강장|터미널|입구|출구|정문|후문|매표소|화장실|관리사무소|사무소|안내소|"
    r"안내센터|관리동|충전소|atm|\d+호점|신관|별관|\d+관$|분점|직영점|임시|공사|해수욕장|캠핑장|선착장|전망대|"
    r"등산로|산책로|둘레길|광장|쉼터|휴게소|매점|편의점|약국|병원|학교|교회|아파트|빌라|오피스텔")

LARGE_CATEGORIES = {"섬여행", "산", "관광명소 > 공원", "골프장"}   # + the city's own (site.json city.kakao_large_categories)
LARGE_NAME = re.compile(r"(공원|해수욕장|해변|섬|산|봉|항|포구|호수|저수지|숲|휴양림|수목원|유원지|방조제|"
                        r"갯벌|습지|관광지|관광단지|생태지|철새조망대|금강하구둑|하굿둑|마을|길|도)$")
LARGE_KAKAO = re.compile(r"섬|공원|해수욕장|해변|산$|산,|봉우리|항구|항$|포구|저수지|호수|댐|숲|휴양림|수목원|유원지|"
                         r"관광단지|마을|방조제|갯벌|습지|골프장|캠핑장")
# Kakao category groups that cannot be our kind ('달' the guesthouse is not '달' the café in the same building)
KIND_CONFLICT = {"stay": {"FD6", "CE7"}, "food": {"AD5"}}


def norm(name: str | None) -> str:
    """NFKC, brackets dropped, spaces/punctuation dropped, lower case: '중화반점 1968' -> '중화반점1968'."""
    s = unicodedata.normalize("NFKC", name or "")
    s = re.sub(r"\(.*?\)|\[.*?\]", "", s)
    s = re.sub(r"[\s\-_·.,'\"!?~/&+@#:;|*`’‘“”・]", "", s)
    return s.lower()


def our_names(p: dict) -> list[tuple[str, str]]:
    """[(normalised, how)] — the record's name, the part in brackets, its alternate_names."""
    out: list[tuple[str, str]] = []

    def add(raw, how):
        n = norm(raw)
        if n and n not in [x for x, _ in out]:  # a one-letter name ('달') is kept; _relation limits what it matches
            out.append((n, how))
    add(p.get("name"), "name")
    for inner in re.findall(r"\(([^)]*)\)", p.get("name") or ""):
        add(inner, "bracket")
    for alt in p.get("alternate_names") or []:
        add(alt, "alternate")
    return out


def _extra_class(extra: str) -> str:
    if not extra:
        return "exact"
    if BAD_EXTRA.search(extra):
        return "bad"
    if extra in safe_extras():
        return "safe"

    def weak(x):
        return x in WEAK_WORDS or DESCRIPTOR_RE.match(x) or (BRANCH_RE.match(x) and not NOT_BRANCH.search(x))
    if weak(extra):
        return "weak"
    # the city's name + a weak word ('<city>점', '<city>미장점') stays weak
    for prefix in city_words():
        if extra.startswith(prefix) and weak(extra[len(prefix):]):
            return "weak"
    return "other"


RANK = {"exact": 0, "safe": 1, "weak": 2, "bad": 3, "other": 4, "none": 5}


def _relation(n: str, k: str) -> dict | None:
    """How our normalised name n relates to the Kakao name k, or None when unrelated."""
    if n == k:
        return {"cls": "exact", "extra": ""}
    rp = region_prefix()
    words = city_words()
    region = words[-1] if words else ""
    nr, kr = rp.sub("", n), rp.sub("", k)
    if nr == kr and len(nr) >= 2:                      # '<city>어린이교통공원' / '<city>시 어린이교통공원'
        return {"cls": "safe", "extra": region}
    if n in k or k in n:
        longer, shorter = (k, n) if n in k else (n, k)
        parts = [x for x in longer.split(shorter, 1) if x]
        classes = [_extra_class(x) for x in parts]
        cls = max(classes, key=lambda c: RANK[c]) if classes else "exact"
        # a one-letter name ('달') only with a business word around it ('게스트하우스 달'), never a branch
        if len(shorter) < 2 and not (cls == "weak" and all(x in WEAK_WORDS for x in parts)):
            return None
        return {"cls": cls, "extra": "+".join(parts)}
    if region and n.replace(region, "") == k.replace(region, "") and len(n.replace(region, "")) >= 2:
        return {"cls": "weak", "extra": f"{region}(가운데)"}  # 'X 수송점' / 'X <city>수송점'
    nc, kc = GENERIC_WORDS.sub("", nr), GENERIC_WORDS.sub("", kr)
    if nc == kc and len(nc) >= 2 and (nc != nr or kc != kr):
        return {"cls": "weak", "extra": "업종어 위치"}    # '호텔파라다이스' / '파라다이스 호텔'
    return None


def name_relation(ours: list[tuple[str, str]], kakao_name: str) -> dict:
    """Best relation between our names and the Kakao name.
    {"cls": exact|safe|weak|bad|other|none, "how": name|bracket|alternate, "extra": leftover}."""
    k = norm(kakao_name)
    best = {"cls": "none", "how": "", "extra": ""}
    if not k:
        return best
    for n, how in ours:
        rel = _relation(n, k)
        if rel is None:
            continue
        rel["how"] = how
        if RANK[rel["cls"]] < RANK[best["cls"]] or (RANK[rel["cls"]] == RANK[best["cls"]] and how == "name"
                                                   and best["how"] != "name"):
            best = rel
    return best


# ----------------------------------------------------------------------------- addresses
def _addr_body(addr: str | None) -> str:
    s = unicodedata.normalize("NFKC", addr or "")
    s = re.sub(r"\s+", " ", s).strip()
    s = _city().strip_prefix(s)           # the province / city in front (site.json city.address_prefixes)
    loc = _city().locality
    if loc and s.startswith(loc):
        s = s[len(loc):].lstrip()
    # '축산 1길 8' -> '축산1길 8', '번영로 12번길 3' -> '번영로12번길 3'
    s = re.sub(r"([가-힣])\s+(\d+(?:번)?(?:로|길))", r"\1\2", s)
    return s


def parse_road(addr: str | None) -> tuple[str, str] | None:
    """('동령길', '39') from '<도> <시> 동령길 39(장미동)'; None for a 지번 address. A 동 named '…로N가'
    ('중앙로1가 12-3') is not a road: the number must end the token."""
    s = _addr_body(addr)
    m = re.search(r"(?:^|\s)([가-힣A-Za-z0-9]+(?:로|길))\s*(\d+(?:-\d+)?)(?=$|[\s(,]|번지)", s)
    return (m.group(1), m.group(2)) if m else None


def parse_jibun(addr: str | None) -> tuple[str, str] | None:
    """('성덕리', '421-4') from '… 성산면 성덕리 421-4'; ('장미동', '1-71') from '… 장미동 1-71(…)'."""
    s = _addr_body(addr)
    m = re.search(r"(?:^|\s)([가-힣0-9]+(?:동|리|가))\s*(산\s*)?(\d+(?:-\d+)?)(?=$|[\s(,]|번지)", s)
    if not m:
        return None
    return m.group(1), ("산" if m.group(2) else "") + m.group(3)


def address_check(our_addr: str, doc: dict) -> dict:
    """{"kind": road|jibun|none, "agree": True/False/None, "ours": .., "theirs": ..}."""
    ours_road = parse_road(our_addr)
    if ours_road:
        theirs = parse_road(doc.get("road_address_name"))
        if theirs:
            return {"kind": "road", "agree": ours_road == theirs, "ours": " ".join(ours_road),
                    "theirs": " ".join(theirs)}
        return {"kind": "road", "agree": None, "ours": " ".join(ours_road), "theirs": ""}
    ours_j = parse_jibun(our_addr)
    if ours_j:
        theirs = parse_jibun(doc.get("address_name"))
        if theirs:
            return {"kind": "jibun", "agree": ours_j == theirs, "ours": " ".join(ours_j), "theirs": " ".join(theirs)}
        return {"kind": "jibun", "agree": None, "ours": " ".join(ours_j), "theirs": ""}
    return {"kind": "none", "agree": None, "ours": "", "theirs": ""}


# '063-452-4044', '0507-1315-5312', '063)452-4044' -> digits; local numbers without an area code are ignored
PHONE_RE = re.compile(r"(?<!\d)(0\d{1,3})[-)\s.]?(\d{3,4})[-\s.]?(\d{4})(?!\d)")


def phone_numbers(text: str | None) -> set[str]:
    return {"".join(m.groups()) for m in PHONE_RE.finditer(unicodedata.normalize("NFKC", text or ""))}


# ----------------------------------------------------------------------------- geometry
def distance_m(lat1: float, lng1: float, lat2: float, lng2: float) -> float:
    r = 6371008.8
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dp, dl = p2 - p1, math.radians(lng2 - lng1)
    a = math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return 2 * r * math.asin(math.sqrt(a))


def is_large(p: dict, doc: dict | None = None) -> bool:
    """Islands, parks, beaches, mountains, ports and the like: 400 m instead of 150 m."""
    if p.get("kind") != "attraction":
        return False
    if p.get("category") in LARGE_CATEGORIES | set(_city().get("kakao_large_categories", []) or []):
        return True
    if LARGE_NAME.search(norm(p.get("name"))):
        return True
    cat = (doc or {}).get("category_name") or ""
    last = cat.split(">")[-1].strip() if cat else ""
    return bool(last and LARGE_KAKAO.search(last))


def place_geo(p: dict) -> tuple[float, float] | None:
    g = p.get("geo") or {}
    if g.get("lat") is None or g.get("lng") is None:
        return None
    return float(g["lat"]), float(g["lng"])


# ----------------------------------------------------------------------------- matching
def judge(p: dict, doc: dict) -> dict:
    """One candidate against one place: {"ok": bool, "reason": .., "name": rel, "dist": m|None, "addr": ..}."""
    rel = name_relation(our_names(p), doc.get("place_name") or "")
    addr = address_check((p.get("facts") or {}).get("address", ""), doc)
    geo = place_geo(p)
    dist = None
    if geo and doc.get("x") and doc.get("y"):
        dist = distance_m(geo[0], geo[1], float(doc["y"]), float(doc["x"]))
    large = is_large(p, doc)
    # An exact name and the same telephone number stand in for the building number; without our coordinates the
    # road name must still agree (only the number differs).
    same_phone = phone_numbers(doc.get("phone")) & phone_numbers((p.get("facts") or {}).get("infocenter"))
    road_ours = parse_road((p.get("facts") or {}).get("address", ""))
    road_theirs = parse_road(doc.get("road_address_name"))
    phone_ok = bool(rel["cls"] == "exact" and same_phone and addr["kind"] == "road" and addr["agree"] is False
                    and (geo or (road_ours and road_theirs and road_ours[0] == road_theirs[0])))
    out = {"ok": False, "reason": "", "name": rel, "dist": dist, "addr": addr, "large": large,
           "limit": (LARGE_M if large else NEAR_M) if geo else None,
           "phone": (doc.get("phone") or "") if phone_ok else ""}
    where = _city().region or _city().locality   # Kakao writes the 시도 short ('인천 중구 …'), a 시 in full
    in_city = bool(where) and where in (doc.get("address_name") or "") + (doc.get("road_address_name") or "")
    if rel["cls"] == "none":
        out["reason"] = "이름 불일치"
    elif rel["cls"] in ("bad", "other"):
        out["reason"] = f"이름 일부만 같음(다른 대상: '{rel['extra']}')"
    elif doc.get("category_group_code") in KIND_CONFLICT.get(p.get("kind"), ()):
        out["reason"] = f"유형 불일치(우리 {p.get('kind')}, 카카오 {doc.get('category_group_name')})"
    elif not in_city:
        out["reason"] = f"{where or '지역'} 밖"
    elif geo and dist is None:
        out["reason"] = "카카오 좌표 없음 — 거리 확인 불가"
    elif geo and dist > out["limit"]:
        out["reason"] = f"거리 초과({round(dist)}m > {out['limit']}m)"
    elif addr["agree"] is False and (addr["kind"] == "road" or not large) and not phone_ok:
        out["reason"] = f"{'건물번호' if addr['kind'] == 'road' else '지번'} 불일치({addr['ours']} ≠ {addr['theirs']})"
    elif rel["cls"] == "weak" and addr["agree"] is not True:
        out["reason"] = f"이름에 업종·지점어('{rel['extra']}')가 붙었는데 주소 일치 확인 불가"
    elif not geo and addr["agree"] is not True and not phone_ok:
        out["reason"] = "좌표 없음 — 주소(건물번호) 일치 확인 불가"
    else:
        out["ok"] = True
    return out


def basis_text(j: dict) -> str:
    rel, addr = j["name"], j["addr"]
    label = "이름 일치" if rel["cls"] == "exact" else f"이름 포함(+{rel['extra']})"
    if rel["extra"].endswith("(가운데)") or rel["extra"] == "업종어 위치":
        label = f"이름 일치({rel['extra']} 차이)"
    bits = [label + {"bracket": "·괄호 안 이름", "alternate": "·별칭"}.get(rel["how"], "")]
    if j["dist"] is not None:
        bits.append(f"{round(j['dist'])}m(기준 {j['limit']}m)")
    else:
        bits.append("좌표 없음")
    if addr["agree"] is True:
        bits.append(f"{'도로명 건물번호' if addr['kind'] == 'road' else '지번'} 일치({addr['ours']})")
    elif addr["agree"] is False and j.get("phone"):
        bits.append(f"건물번호 다름({addr['ours']} / {addr['theirs']}) · 전화 일치({j['phone']})")
    elif addr["agree"] is False:
        bits.append(f"지번 다름({addr['ours']} / {addr['theirs']}, 넓은 곳)")
    else:
        bits.append("주소 대조 불가(한쪽 없음)")
    return " · ".join(bits)


def decide(p: dict, docs: list[dict]) -> dict:
    """{"status": accepted|ambiguous|none, "doc", "judge", "candidates": [...], "reason"}."""
    seen, judged = set(), []
    for d in docs:
        if not d.get("id") or d["id"] in seen:
            continue
        seen.add(d["id"])
        judged.append((d, judge(p, d)))
    passing = [(d, j) for d, j in judged if j["ok"]]
    cands = [{"id": d["id"], "name": d.get("place_name"), "dist": None if j["dist"] is None else round(j["dist"]),
              "ok": j["ok"], "reason": j["reason"], "road": d.get("road_address_name") or "",
              "category": d.get("category_name") or ""} for d, j in judged]
    if not judged:
        return {"status": "none", "reason": "검색 결과 없음", "candidates": cands}
    if not passing:
        # the most telling reason: a candidate whose name matched comes first
        order = ("거리 초과", "건물번호 불일치", "지번 불일치", "이름에 업종", "좌표 없음", "유형 불일치",
                 f"{_city().region or _city().locality or '지역'} 밖",
                 "이름 일부만", "이름 불일치")
        reasons = [j["reason"] for _, j in judged]
        top = min(reasons, key=lambda r: next((i for i, o in enumerate(order) if r.startswith(o)), 99))
        return {"status": "none", "reason": top, "candidates": cands}
    if len(passing) == 1:
        d, j = passing[0]
        return {"status": "accepted", "doc": d, "judge": j, "candidates": cands}
    exact = [(d, j) for d, j in passing if j["name"]["cls"] == "exact"]
    if len(exact) == 1:
        d, j = exact[0]
        if j["dist"] is None:
            return {"status": "accepted", "doc": d, "judge": j, "candidates": cands}
        if all(j["dist"] <= x["dist"] for _, x in passing if x is not j and x["dist"] is not None):
            return {"status": "accepted", "doc": d, "judge": j, "candidates": cands}
    names = ", ".join(f"{d.get('place_name')}({'' if j['dist'] is None else round(j['dist'])}m)" for d, j in passing)
    return {"status": "ambiguous", "reason": f"통과 후보 {len(passing)}곳 — {names}", "candidates": cands}


def resolve_collisions(results: dict[str, dict]) -> None:
    """Two of our places on one Kakao id: the one matched exactly by its own name keeps it, the rest are held."""
    by_id: dict[str, list[str]] = {}
    for pid, r in results.items():
        if r["status"] == "accepted":
            by_id.setdefault(r["doc"]["id"], []).append(pid)
    for kid, pids in by_id.items():
        if len(pids) < 2:
            continue
        own = [pid for pid in pids if results[pid]["judge"]["name"]["cls"] == "exact"
               and results[pid]["judge"]["name"]["how"] == "name"]
        keep = own[0] if len(own) == 1 else None
        for pid in pids:
            if pid != keep:
                other = ", ".join(x for x in pids if x != pid)
                results[pid] = {**results[pid], "status": "ambiguous",
                                "reason": f"같은 카카오 장소({kid})가 다른 장소({other})에도 맞음"}


# ----------------------------------------------------------------------------- client
class KakaoError(RuntimeError):
    pass


class KakaoStop(KakaoError):
    """Per-run call cap or quota: stop; the next run resumes from the cache."""


def redact(text: str, key: str) -> str:
    out = str(text or "")
    if key and len(key) >= 6:
        for form in sorted({key, urllib.parse.quote(key, safe="")}, key=len, reverse=True):
            out = out.replace(form, "«KEY»")
    return out


class KakaoClient:
    def __init__(self, key: str, cache_dir: Path, max_calls: int = DEFAULT_MAX_CALLS, offline: bool = False,
                 refresh: bool = False, min_interval: float = 0.12):
        self.key, self.cache_dir = key, Path(cache_dir)
        self.max_calls, self.offline, self.refresh, self.min_interval = max_calls, offline, refresh, min_interval
        self.calls = self.cache_hits = 0
        self._last = 0.0

    def _path(self, params: dict) -> Path:
        h = hashlib.sha1(json.dumps(params, sort_keys=True, ensure_ascii=False).encode()).hexdigest()[:20]
        return self.cache_dir / f"keyword-{h}.json"

    def search(self, query: str, x: float | None = None, y: float | None = None,
               radius: int = SEARCH_RADIUS) -> tuple[list[dict], str]:
        """(documents, fetched date). Cached responses are used as they are."""
        params = {"query": query, "sort": "accuracy", "size": 15, "page": 1}
        if x is not None and y is not None:
            params.update({"x": f"{x:.7f}", "y": f"{y:.7f}", "radius": radius})
        path = self._path(params)
        if path.exists() and not self.refresh:
            self.cache_hits += 1
            blob = json.loads(path.read_text("utf-8"))
            return blob["response"].get("documents") or [], blob.get("fetched_at", "")
        if self.offline:
            return [], ""
        if self.calls >= self.max_calls:
            raise KakaoStop(f"실행당 호출 상한 {self.max_calls}회 도달 — 다음 실행이 캐시에서 이어 간다")
        if not self.key:
            raise KakaoError("KAKAO_REST_KEY(또는 --key-file)가 없다")
        wait = self.min_interval - (time.monotonic() - self._last)
        if wait > 0:
            time.sleep(wait)
        url = ENDPOINT + "?" + urllib.parse.urlencode(params)
        req = urllib.request.Request(url, headers={"Authorization": f"KakaoAK {self.key}"})
        self.calls += 1
        self._last = time.monotonic()
        try:
            with urllib.request.urlopen(req, timeout=20) as resp:
                body = resp.read().decode("utf-8")
        except urllib.error.HTTPError as e:
            msg = e.read().decode("utf-8", "replace")
            err = KakaoStop if e.code in (429,) or "LIMIT" in msg.upper() else KakaoError
            raise err(redact(f"Kakao Local HTTP {e.code}: {msg}", self.key)) from None
        except (urllib.error.URLError, TimeoutError) as e:
            raise KakaoError(redact(f"Kakao Local 연결 실패: {e}", self.key)) from None
        payload = json.loads(body)
        if "documents" not in payload:
            raise KakaoError(redact(f"Kakao Local 응답 이상: {body[:300]}", self.key))
        today = dt.date.today().isoformat()
        self.cache_dir.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps({"params": params, "fetched_at": today, "response": payload},
                                   ensure_ascii=False), "utf-8")
        return payload["documents"] or [], today


# ----------------------------------------------------------------------------- run
def queries(p: dict) -> list[str]:
    name = re.sub(r"\s+", " ", p.get("name") or "").strip()
    base = re.sub(r"\s*\(.*?\)\s*", " ", name).strip()
    geo = place_geo(p)
    r = _city().region
    with_r = lambda q: q if not r or r in q else f"{r} {q}"   # noqa: E731
    qs = [base] if geo else [with_r(base), base]
    if geo and r and r not in base:
        qs.append(f"{r} {base}")
    if " " in base:  # Kakao's keyword search may miss '○○호 시민공원' but find '○○호시민공원'
        tight = base.replace(" ", "")
        qs.append(tight if geo else with_r(tight))
    for inner in re.findall(r"\(([^)]*)\)", name):
        inner = inner.strip()
        if inner.endswith("점"):   # '현대옥(미장점)': a branch is searched with its name ('현대옥 미장점')
            inner = f"{base} {inner}"
        qs.append(inner if geo else with_r(inner))
    for alt in p.get("alternate_names") or []:
        qs.append(alt.strip())
    out = []
    for q in qs:
        if q and q not in out and len(norm(q)) >= 2:
            out.append(q)
    return out


def match_place(client: KakaoClient, p: dict) -> dict:
    geo = place_geo(p)
    docs, dates, asked = [], [], []
    result = None
    for q in queries(p):
        got, fetched = client.search(q, geo[1] if geo else None, geo[0] if geo else None)
        asked.append(q)
        if fetched:
            dates.append(fetched)
        for d in got:
            d = {**d, "_query": q, "_fetched": fetched}
            docs.append(d)
        result = decide(p, docs)
        if result["status"] != "none":
            break
    result = result or {"status": "none", "reason": "검색어 없음", "candidates": []}
    result["queries"] = asked
    result["checked_at"] = (result.get("doc") or {}).get("_fetched") or (max(dates) if dates else "")
    return result


def apply(places: list[dict], results: dict[str, dict]) -> Counter:
    changes = Counter()
    by_id = {p["id"]: p for p in places}
    for pid, r in results.items():
        p = by_id[pid]
        mid = p.setdefault("map_ids", {})
        srcs = p.get("map_id_sources") or {}
        old = mid.get("kakao_place_id")
        ours = (srcs.get("kakao_place_id") or {}).get("provider") == PROVIDER
        if r["status"] == "accepted":
            d, j = r["doc"], r["judge"]
            new_src = {"provider": PROVIDER, "checked_at": d.get("_fetched") or r["checked_at"],
                       "matched_name": d.get("place_name"), "distance_m": None if j["dist"] is None else round(j["dist"]),
                       "basis": basis_text(j), "url": PLACE_URL.format(id=d["id"]), "query": d.get("_query")}
            changes["same" if old == d["id"] else ("replaced" if old else "added")] += 1
            mid["kakao_place_id"] = str(d["id"])
            p["map_id_sources"] = {**srcs, "kakao_place_id": new_src}
        elif old and ours:
            mid.pop("kakao_place_id", None)
            srcs.pop("kakao_place_id", None)
            if srcs:
                p["map_id_sources"] = srcs
            else:
                p.pop("map_id_sources", None)
            changes["removed"] += 1
        elif old:
            changes["kept_manual"] += 1
    return changes


def summarize(places: list[dict], results: dict[str, dict]) -> dict:
    by_id = {p["id"]: p for p in places}
    table: dict[str, Counter] = {}
    reasons = Counter()
    for pid, r in results.items():
        p = by_id[pid]
        kind = p.get("kind", "?")
        geo = "coords" if place_geo(p) else "no_coords"
        table.setdefault(kind, Counter())[f"{r['status']}/{geo}"] += 1
        if r["status"] != "accepted":
            reasons[re.sub(r"\(.*$", "", r.get("reason") or "").strip() or r["status"]] += 1
    return {"by_kind": {k: dict(v) for k, v in table.items()}, "reasons": dict(reasons.most_common())}


def read_key(key_file: Path | None) -> str:
    if key_file:
        return key_file.read_text("utf-8").strip()
    return (os.environ.get("KAKAO_REST_KEY") or "").strip()


def run(data: Path, key: str, max_calls: int, offline: bool, refresh: bool, do_apply: bool, report: Path | None,
        cache_dir: Path, only: set[str] | None = None) -> int:
    from pipeline import city
    city.activate_dir(data)   # the region's words for names, addresses and queries
    path = data / "places.json"
    places = json.loads(path.read_text("utf-8"))
    targets = [p for p in places if p.get("status") == "published" and (not only or p["id"] in only)]
    client = KakaoClient(key, cache_dir, max_calls=max_calls, offline=offline, refresh=refresh)
    results: dict[str, dict] = {}
    stopped = ""
    for p in targets:
        try:
            results[p["id"]] = match_place(client, p)
        except KakaoStop as e:
            stopped = str(e)
            break
        except KakaoError as e:
            print(f"오류: {e}", file=sys.stderr)
            return 2
    resolve_collisions(results)
    summary = summarize(places, results)
    print(json.dumps({"targets": len(targets), "judged": len(results), "live_calls": client.calls,
                      "cache_hits": client.cache_hits, **summary}, ensure_ascii=False, indent=1))
    if stopped:
        print(f"중단: {stopped}", file=sys.stderr)
    if report:
        by_id = {p["id"]: p for p in places}
        rows = []
        for pid, r in results.items():
            p = by_id[pid]
            row = {"id": pid, "name": p["name"], "kind": p.get("kind"), "category": p.get("category"),
                   "coords": bool(place_geo(p)), "address": (p.get("facts") or {}).get("address", ""),
                   "status": r["status"], "reason": r.get("reason", ""), "queries": r.get("queries"),
                   "candidates": r.get("candidates")}
            if r["status"] == "accepted":
                row.update({"kakao_id": r["doc"]["id"], "kakao_name": r["doc"].get("place_name"),
                            "distance_m": None if r["judge"]["dist"] is None else round(r["judge"]["dist"]),
                            "basis": basis_text(r["judge"])})
            rows.append(row)
        report.parent.mkdir(parents=True, exist_ok=True)
        report.write_text(json.dumps({"summary": summary, "rows": rows}, ensure_ascii=False, indent=1), "utf-8")
        print(f"보고: {report}")
    if do_apply and not stopped:
        changes = apply(places, results)
        path.write_text(json.dumps(places, ensure_ascii=False, indent=2) + "\n", "utf-8")
        print(f"반영: {dict(changes)}")
    elif do_apply:
        print("호출 상한으로 중단되어 반영하지 않았다 — 다시 실행하면 캐시에서 이어 간다", file=sys.stderr)
    return 1 if stopped else 0


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--data", type=Path, default=Path("data/incheon"))
    ap.add_argument("--key-file", type=Path, help="키가 든 파일(없으면 환경 변수 KAKAO_REST_KEY)")
    ap.add_argument("--max-calls", type=int, default=DEFAULT_MAX_CALLS, help="실행당 실제 호출 상한")
    ap.add_argument("--cache", type=Path, default=Path("data/cache/kakao"))
    mode = ap.add_mutually_exclusive_group()
    mode.add_argument("--offline", action="store_true", help="캐시만 쓴다(네트워크 호출 없음)")
    mode.add_argument("--refresh", action="store_true", help="캐시를 무시하고 새로 받는다")
    ap.add_argument("--apply", action="store_true", help="places.json에 쓴다(없으면 미리보기)")
    ap.add_argument("--report", type=Path, default=Path("reports/kakao_places.json"))
    ap.add_argument("--only", nargs="*", help="이 ID의 장소만")
    a = ap.parse_args(argv)
    key = "" if a.offline else read_key(a.key_file)
    return run(a.data, key, a.max_calls, a.offline, a.refresh, a.apply, a.report, a.cache,
               set(a.only) if a.only else None)


if __name__ == "__main__":
    sys.exit(main())
