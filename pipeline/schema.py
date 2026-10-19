"""Field definitions, labels and licence codes.

The full data model is documented in docs/02_page_standard.md (section 4).
Keep this module and that document in sync.
"""
from __future__ import annotations

import re

KINDS = ("attraction", "stay", "food")
KIND_LABELS = {"attraction": "관광지", "stay": "숙소", "food": "음식점"}
STATUSES = ("draft", "reviewed", "published")
TIERS = ("full", "basic")

# Licence codes used everywhere in data files.
LICENSE_LABELS = {
    "KOGL-1": "공공누리 제1유형(출처표시)",
    "KOGL-2": "공공누리 제2유형(출처표시·상업적 이용금지)",
    "KOGL-3": "공공누리 제3유형(출처표시·변경금지)",
    "KOGL-4": "공공누리 제4유형(출처표시·상업적 이용금지·변경금지)",
    "NONE": "공공누리 미표시(사전 협의 필요)",
    "UNKNOWN": "이용조건 확인 전",
}
# Default: only types that allow commercial use are republished verbatim.
DEFAULT_ALLOWED_LICENSES = ("KOGL-1", "KOGL-3")
# TourAPI image field cpyrhtDivCd -> licence code
TOURAPI_LICENSE_MAP = {"Type1": "KOGL-1", "Type3": "KOGL-3"}

# Facts block (블록 2). Display order and labels.
FACT_ORDER = (
    "address", "usetime", "usetime_restdate", "restdate", "openperiod", "fairday", "usefee", "discount", "parking",
    "parking_seats", "parkingfee", "spendtime", "checkin", "checkout", "roomcount", "roomtype", "cooking",
    "subfacility", "menu", "treatmenu", "saleitem", "shopguide", "seat", "packing", "expguide", "filming", "reservation", "reservationurl",
    "infocenter", "homepage", "creditcard",
)
FIT_ORDER = ("babycarriage", "pet", "kidsfacility", "expagerange", "useseason",
             "accessible_parking", "wheelchair", "accessible_toilet", "accessible_route")
FACT_LABELS = {
    "address": "주소",
    "usetime": "이용시간",
    "usetime_restdate": "영업시간·정기휴일",
    "restdate": "쉬는 날",
    "usefee": "이용요금",
    "parking": "주차",
    "parking_seats": "주차·좌석",
    "parkingfee": "주차요금",
    "spendtime": "관람 소요시간",
    "checkin": "체크인",
    "checkout": "체크아웃",
    "menu": "대표 메뉴",
    "infocenter": "문의",
    "homepage": "홈페이지",
    "babycarriage": "유모차 대여",   # TourAPI chkbabycarriage = stroller rental, not "strollers allowed"
    "pet": "반려동물 동반",
    "expagerange": "체험 가능 연령",
    "useseason": "이용 시기",
    "accessible_parking": "장애인 주차장",
    "wheelchair": "휠체어 대여",
    "accessible_toilet": "장애인 화장실",
    "accessible_route": "주 출입 접근로",
    # TourAPI detailIntro2·detailInfo2 fields added in round 3 (tools/tourapi_details.py)
    "openperiod": "운영 기간",
    "discount": "할인",
    "roomcount": "객실 수",
    "roomtype": "객실 유형",
    "cooking": "객실 내 취사",
    "subfacility": "부대시설",
    "treatmenu": "취급 메뉴",
    "seat": "좌석",
    "packing": "포장",
    "expguide": "체험 안내",
    "filming": "촬영지 정보",
    "reservation": "예약 안내",
    "reservationurl": "예약 페이지",
    "creditcard": "신용카드 결제",
    "kidsfacility": "어린이 놀이방",
    "fairday": "장날",
    "saleitem": "판매 품목",
    "shopguide": "매장 안내",
}
# A missing key fact counts as present when one of these source fields holds it.
FACT_ALIASES = {"parking": ("parking_seats",), "usetime": ("usetime_restdate",), "restdate": ("usetime_restdate",)}
# Facts a visitor needs before going. Missing ones are shown as "확인 필요".
KEY_FACTS = {
    "attraction": ("usetime", "restdate", "usefee", "parking"),
    "stay": ("checkin", "checkout", "parking", "infocenter"),
    "food": ("usetime", "restdate", "menu", "parking"),
}
# Shops and markets (TourAPI type 38) are attractions without an admission fee.
KEY_FACTS_BY_CATEGORY = {"쇼핑": ("usetime", "restdate", "parking")}

# schema.org type per kind (the default; schema_type() narrows it from the source category)
SCHEMA_TYPES = {"attraction": "TouristAttraction", "stay": "LodgingBusiness", "food": "Restaurant"}
# Most specific type from the source `category` (and the name suffix) — an explicit map, nothing inferred.
# Heritage categories become a building/landmark type only for things that are one: movable objects
# (statues, documents, sutras) and 무형 heritage keep plain TouristAttraction.
HERITAGE_BUILDING_CATEGORIES = ("국가지정 문화유산 - 사적", "국가지정 문화유산 - 보물", "국가등록 문화유산",
                                "도지정 유형 문화유산")
MOVABLE_HERITAGE = re.compile(r"좌상|삼존상|나한상|불상|기록물|신청서|참법|행적송|복장유물")
STAY_TYPES = {"관광호텔": "Hotel", "일반호텔": "Hotel", "여관/모텔": "Motel"}
CUISINE = {"한식": "한식", "중식": "중식", "일식": "일식", "분식": "분식", "짬뽕 특화거리 ( 중식)": "중식"}
ENTITY_TYPES = frozenset(SCHEMA_TYPES.values()) | {"Museum", "Park", "Mountain", "LandmarksOrHistoricalBuildings",
                                                   "GolfCourse", "Hotel", "Motel"}


def schema_type(e: dict) -> str | list[str]:
    """@type for an entity node: ["Museum", "TouristAttraction"] etc. for attractions, Hotel/Motel for stays."""
    kind = e.get("kind", "attraction")
    cat = re.sub(r"\s+", " ", str(e.get("category") or "")).strip()
    name = re.sub(r"\s+", " ", str(e.get("name") or "")).strip()
    if kind == "stay":
        return STAY_TYPES.get(cat, SCHEMA_TYPES["stay"])
    if kind != "attraction":
        return SCHEMA_TYPES.get(kind, "TouristAttraction")
    specific = ""
    if cat == "박물관/전시관" or name.endswith(("박물관", "미술관")):
        specific = "Museum"
    elif cat == "관광명소 > 공원" or name.endswith("공원"):
        specific = "Park"
    elif cat == "산":
        specific = "Mountain"
    elif cat in HERITAGE_BUILDING_CATEGORIES and "무형" not in cat and not MOVABLE_HERITAGE.search(name):
        specific = "LandmarksOrHistoricalBuildings"
    elif cat == "골프장":
        specific = "GolfCourse"
    return [specific, "TouristAttraction"] if specific else "TouristAttraction"


def serves_cuisine(e: dict) -> str:
    """Cuisine for a restaurant only when the source category names it exactly (한식·중식·일식·분식)."""
    if e.get("kind") != "food":
        return ""
    return CUISINE.get(re.sub(r"\s+", " ", str(e.get("category") or "")).strip(), "")


def node_types(node: dict) -> list[str]:
    t = node.get("@type")
    return list(t) if isinstance(t, list) else [t] if t else []

# Blocks every published entity page must render, by tier. `media` is recommended, not required:
# it is shown only when official videos or press items have been checked.
# (ids are the data-block attribute values in templates/place.html.j2)
REQUIRED_BLOCKS = {
    "full": ("summary", "facts", "directions", "nearby", "faq", "original", "sources"),
    "basic": ("summary", "facts", "directions", "original", "sources"),
}

# Index criteria (CLAUDE.md 3.8). Groups must stay identical to tools/quality_report.py GROUPS / KIND_GROUPS
# (tests/test_round3_index.py checks this), so the report and the production build judge pages the same way.
INDEX_GROUPS = {
    "hours": ("usetime", "usetime_restdate", "opentime", "opentimefood", "usetimeculture", "usetimeleports"),
    "restdate": ("restdate", "usetime_restdate", "restdatefood", "restdateculture", "restdateleports"),
    "fee": ("usefee", "fee", "usefeeleports", "parkingfee"),
    "parking": ("parking", "parking_seats", "parkingfood", "parkinglodging", "parkingculture", "parkingleports", "accessible_parking"),
    "phone": ("tel", "infocenter", "infocenterfood", "infocenterlodging", "infocenterculture", "infocenterleports", "phone"),
    "homepage": ("homepage", "reservationurl"),
    "checkin": ("checkin", "checkintime"),
    "menu": ("menu", "firstmenu", "treatmenu"),
}
INDEX_KIND_GROUPS = {
    "attraction": ("hours", "restdate", "fee", "parking", "phone"),
    "food": ("hours", "menu", "parking", "phone"),
    "stay": ("checkin", "parking", "phone", "homepage"),
}
INDEX_GROUP_LABELS = {"hours": "이용시간", "restdate": "쉬는 날", "fee": "요금", "parking": "주차", "phone": "전화",
                      "homepage": "홈페이지", "checkin": "체크인", "menu": "대표 메뉴"}
INDEX_MIN_GROUPS = 2


def taut_pattern(name: str) -> str:
    """First sentence "○○은 <city> ○○에 있는 ○○입니다." alone, for the active city (pipeline/city.py taut_rx: its
    province, city and 구·군 names). tools/quality_report.py uses this same function."""
    from . import city
    return city.current().taut_rx(name)


# Source commentary ("원문은 ~라고 소개합니다") instead of an answer
SOURCE_COMMENTARY = re.compile(r"원문[은는이에서의]|라고\s*(소개|설명|안내|합니다|한다|전합니다|알려져)"
                               r"|(으)?로\s*소개(합니다|한다|하고|되어|됩니다)")
INDEX_REASONS = {
    "groups": f"유형별 필수 정보 {INDEX_MIN_GROUPS}개 미만",
    "no_summary": "요약 없음",
    "taut": "요약 첫 문장이 상투구('○○은 ○○시 ○○에 있는 ○○입니다')",
    "commentary": "요약에 출처 해설체('원문은…')",
    "unreviewed": "검수일(reviewed_at)·운영자 공개 승인(approved_at) 없음",
}

# Official designations (지정): the city / national lists a place is on — the city's own list, 모범음식점, 백년가게, …
# (data: e["designations"], one entry per list: type, label, year, source_name, url, checked_at, match). Shown on the
# place page (chips under the answer, a '지정' row in the facts card with each list's link and 확인일), as one short
# chip on list records, in the search index, llms.txt and JSON-LD `award`. Only entries matched with high/medium
# confidence and not flagged needs_check are shown (designation_problems). The display priority is the city's order
# (site.json city.designations.order: its own lists in front), then the national lists below; a list record shows the
# first. The index criteria (INDEX_GROUPS) do not count designations.
DESIGNATION_ORDER = ("baeknyeon", "mobeom", "hyangto", "goodprice", "ansim")
DESIGNATION_SHORT = {"baeknyeon": "백년가게", "mobeom": "모범음식점", "hyangto": "향토음식점",
                     "goodprice": "착한가격업소", "ansim": "안심식당"}
DESIGNATION_SHORT_YEAR = ("hyangto",)   # the year is part of what the designation says
DESIGNATION_MATCH_OK = ("high", "medium")


def designation_tables() -> tuple[tuple, dict, tuple]:
    """(order, short labels, types whose year is shown) — the city's lists (site.json city.designations) merged with
    the national ones."""
    from . import city
    d = city.current().get("designations", {}) or {}
    order = tuple(dict.fromkeys([*(d.get("order") or ()), *DESIGNATION_ORDER]))
    return order, {**DESIGNATION_SHORT, **(d.get("short") or {})}, (*DESIGNATION_SHORT_YEAR, *(d.get("short_year") or ()))


def designation_problems(d: dict) -> list[str]:
    """Why one stored designation may not be shown: no label, no source link or 확인일, or a list row matched to the
    place with low confidence / flagged for a phone check (needs_check)."""
    out = []
    if not str(d.get("label") or "").strip():
        out.append("이름(label) 없음")
    if not str(d.get("url") or "").strip().startswith(("https://", "http://")):
        out.append("출처 주소(url) 없음")
    if not re.match(r"^\d{4}-\d{2}-\d{2}$", str(d.get("checked_at") or "")):
        out.append("확인일(checked_at) 없음")
    match = d.get("match") or {}
    if match.get("confidence") not in DESIGNATION_MATCH_OK:
        out.append(f"목록 행과의 매칭 신뢰도가 {match.get('confidence') or '미기재'}")
    if match.get("needs_check"):
        out.append("매칭 확인 필요(needs_check)")
    return out


def designation_short(d: dict) -> str:
    """'<city list> 2026', '모범음식점', '향토음식점 2020' — the one chip of a list record."""
    _, shorts, with_year = designation_tables()
    short = shorts.get(d.get("type"), "") or re.sub(r"\(.*?\)", "", str(d.get("label") or "")).strip()
    if d.get("type") in with_year and d.get("year"):
        short = f"{short} {d['year']}"
    return short


def designations(e: dict) -> list[dict]:
    """The designations a page shows, in the city's order (designation_tables), each with `short`."""
    order = {t: i for i, t in enumerate(designation_tables()[0])}
    shown = [d for d in e.get("designations") or [] if not designation_problems(d)]
    shown.sort(key=lambda d: order.get(d.get("type"), len(order)))
    return [{**d, "label": str(d["label"]).strip(), "short": designation_short(d)} for d in shown]


# GA4 custom events emitted by assets/track.js (data-track attribute values); the site assistant (assets/chat.js) adds
# chat_open and chat_send itself (no message text) and marks its links chat_link_click
TRACK_EVENTS = (
    "map_click", "route_click", "official_click", "nearby_click",
    "stay_click", "food_click", "course_click", "guide_click", "video_click", "news_click", "parking_click",
    "chat_open", "chat_send", "chat_link_click",
)


def license_allowed(code: str | None, allowed: tuple[str, ...] | list[str] | None = None) -> bool:
    return (code or "UNKNOWN") in tuple(allowed or DEFAULT_ALLOWED_LICENSES)


def summary_sentences(text: str | None) -> list[str]:
    return [s for s in re.split(r"(?<=[.!?])\s+", (text or "").strip()) if s]


def index_groups(e: dict) -> list[str]:
    """Practical-information groups of the entity's kind that hold a value (quality_report `has`)."""
    facts = e.get("facts") or {}
    return [g for g in INDEX_KIND_GROUPS.get(e.get("kind"), ())
            if any(str(facts.get(k) or "").strip() for k in INDEX_GROUPS[g])]


def summary_problems(e: dict) -> list[str]:
    """Reason keys (see INDEX_REASONS) why the summary breaks CLAUDE.md 3.5; empty when it is fine."""
    sentences = summary_sentences(e.get("summary"))
    if not sentences:
        return ["no_summary"]
    out = []
    if re.match(taut_pattern(e.get("name", "")), sentences[0]):
        out.append("taut")
    if SOURCE_COMMENTARY.search(e.get("summary") or ""):
        out.append("commentary")
    return out


def summary_ok(e: dict) -> bool:
    return not summary_problems(e)


def index_status(e: dict) -> tuple[bool, list[str]]:
    """(indexable, reasons) for a production entity page: (a) >= 2 groups of its kind, (b) summary rule,
    (c) reviewed_at. Reasons are fixed labels from INDEX_REASONS so they can be counted."""
    keys = []
    if len(index_groups(e)) < INDEX_MIN_GROUPS:
        keys.append("groups")
    keys += summary_problems(e)
    if not (str(e.get("reviewed_at") or "").strip() or str(e.get("approved_at") or "").strip()):
        keys.append("unreviewed")
    return not keys, [INDEX_REASONS[k] for k in keys]


def check_entity(e: dict) -> list[str]:
    """Structural problems in one entity record (used by importer and validate)."""
    problems = []
    for key in ("id", "name", "kind", "status"):
        if not e.get(key):
            problems.append(f"필수 필드 누락: {key}")
    if e.get("kind") and e["kind"] not in KINDS:
        problems.append(f"kind 값 오류: {e['kind']}")
    if e.get("status") and e["status"] not in STATUSES:
        problems.append(f"status 값 오류: {e['status']}")
    if e.get("tier", "basic") not in TIERS:
        problems.append(f"tier 값 오류: {e.get('tier')}")
    lic = (e.get("original") or {}).get("license")
    if lic and lic not in LICENSE_LABELS:
        problems.append(f"original.license 코드 오류: {lic} (허용: {', '.join(LICENSE_LABELS)})")
    for img in e.get("images") or []:
        if img.get("license") not in LICENSE_LABELS:
            problems.append(f"이미지 license 코드 오류: {img.get('license')}")
    return problems
