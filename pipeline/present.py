"""View models for the redesigned templates (SPEC §13.2 of the merged direction).

Pure helpers: they turn the build State's data into what a template prints, so the templates carry no logic.
Every fact comes from the data (CLAUDE.md 3.1); every number in a computed sentence is stored, counted or
computed from stored coordinates. Values are never shortened (P1-7): a parsed form (timetable, price table)
keeps every source word in source order, otherwise the whole display text prints.

State-level fields are set once by prepare(S) (called at the end of build.State.__init__):
    e["_type"], e["_street"], e["_photos"] (with KOGL-1 derivative srcsets, pipeline/media.py), e["_line"],
    e["_region"], e["_region_basis"], e["_twins"], S.image_sizes, S.anchors, S.region_names, S.course_vms, S.warnings
Per-page view models: place_vm, list_vm, home_vm, course page (course_vm + stop_details), guide_vm,
guide_rows, events_vm, event_vm, map_vm, search_index / search_directory, about_vm, video_groups_vm.
Shared-markup helpers (templates/_ui.html.j2, as Jinja globals): card_vm (place cards with fixed key slots),
nav_items (the main navigation of common_vm).
"""
from __future__ import annotations

import datetime as dt
import functools
import json
import re
from collections import Counter, defaultdict
from pathlib import Path
from urllib.parse import quote

from markupsafe import Markup, escape

from . import art, booking, city, jsonld, media, relations, tickets   # booking imports present only inside its functions
from . import locales as LC          # locales imports nothing from the package
from .enrich import haversine_m
from .maplinks import kakao_route_url, kakao_transit_url
from .schema import (FACT_ALIASES, FACT_LABELS, KEY_FACTS, KEY_FACTS_BY_CATEGORY, KIND_LABELS, alias_holds,
                     designations, fact_label, geo_provider, geo_providers, parking_seats_half)
from .textutil import (TILDE, TIME, course_display_name, dash_times, display_address, display_value, josa, link_url,
                       normalize_name, parking_text, phone_e164, restore_lines, squash_ws, url_domain, web_text, web_url)

WEEK = "월화수목금토일"
LIST_PATH = {"attraction": "/places/", "stay": "/stays/", "food": "/food/"}
# Main navigation (owner, 2026-10-08): 관광지 숙소 음식점 영상 코스 가이드 행사 지도 (+ 검색 in the masthead). Each item
# shows only when its page is built (nav_items); 영상 sits in the first four so a 390px phone shows it.
NAV = (("관광지", "/places/", "attraction"), ("숙소", "/stays/", "stay"), ("음식점", "/food/", "food"),
       ("영상", "/videos/", "videos"), ("코스", "/courses/", "courses"), ("가이드", "/guides/", "guides"),
       ("행사", "/events/", "events"), ("지도", "/map/", "map"), ("해외에서 본 {region}", "/abroad/", "abroad"))

# 권역 (map page, list groups) and the places a page measures distances to come from the city's configuration
# (site.json city.travel_regions, city.distance_anchors; pipeline/city.py). Two rules exist:
# - nearest_anchor: the nearest of the anchor places by straight-line distance; beyond far_m of every anchor a place
#   is far_label ('먼 섬'); without coordinates it follows the 권역 most places of its 읍·면·동 fall in, and with no
#   읍·면·동 either it is none_label ('권역 미정').
# - district: by the 구·군 the address names (else the one TourAPI's statutory code gave) and, where a match lists
#   them, its 법정동; an address no region matches is none_label.
# The map page states the rule in force. Each 권역's AI art band on /map/ is area.<art> (pipeline/art.py).


def far_label() -> str:
    return city.current().far_label


def none_label() -> str:
    return city.current().none_label


def region_art() -> dict:
    return city.current().region_art

# Type labels: plain names; generic source buckets ('음식점', '기타') are not shown as a type.
STAY_TYPE = {"여관/모텔": "모텔·여관", "숙박": "숙박업소", "기타": "그 밖의 숙소", "": "그 밖의 숙소",
             "일반호텔": "호텔", "굿스테이": "굿스테이 인증 숙소"}
FOOD_TYPE = {"식육(숯불구이)": "고기구이", "음식점": "", "기타": ""}
ATTR_TYPE = {"쇼핑": "시장·쇼핑", "레포츠": "레포츠", "문화시설": "문화시설", "산업/회의 시설": "산업·회의 시설",
             "공중하강체험시설": "체험"}
# '숙소 문의: 독채 여부·반려동물 동반' only where the answer can differ (small stays), never on a 181-room hotel
SMALL_STAY = ("게스트하우스", "펜션", "한옥")
SMALL_STAY_ROOMS = 3
STAY_ASK = ("독채 여부", "반려동물 동반")


# ----------------------------------------------------------------------------- small helpers
def frag(text: str) -> str:
    """Fragment ids without spaces (aria-labelledby and # links split on them): '먼 섬' -> '먼-섬'."""
    return re.sub(r"[\s·/&,()]+", "-", squash_ws(text)).strip("-")


def hav(a: dict | None, b: dict | None) -> float | None:
    if not (a and b):
        return None
    return haversine_m(float(a["lat"]), float(a["lng"]), float(b["lat"]), float(b["lng"]))


def dist(m) -> str:
    """'같은 좌표' under 10m, '430m' (rounded to 10m), '2.4km'."""
    if m is None:
        return ""
    m = float(m)
    if m < 10:
        return "같은 좌표"
    if m < 1000:
        return f"{int(round(m / 10) * 10)}m"
    return f"{m / 1000:.1f}km"


def short_date(iso: str) -> str:
    """'2026-10-09' -> '10. 9.(금)' (calendar weekday only)."""
    d = dt.date.fromisoformat(iso[:10])
    return f"{d.month}. {d.day}.({WEEK[d.weekday()]})"


def sentences(text: str | None) -> list[str]:
    return [p for p in re.split(r"(?<=[다요]\.)\s+", squash_ws(text)) if p]


LOCATOR = re.compile(r"^.{1,40}?[은는이가] \S+(?:동|면|읍|가|리|로|길|도)(?:의 \S+)?에 있는")


def distinct_line(text: str | None) -> str:
    """One whole sentence that says something only this place has. A sentence of the form 'X는 Y동에 있는 Z…'
    only restates the meta line and is skipped (the next sentence, preferring one with a figure). Never cut
    or paraphrased; '' when every sentence is a locator."""
    ss = [s for s in sentences(text) if not LOCATOR.match(s)]
    if not ss:
        return ""
    with_fig = [s for s in ss if re.search(r"\d", s)]
    return ss[0] if not with_fig or ss[0] in with_fig else (ss[0] if len(ss[0]) > 30 else with_fig[0])


# Owner item 7 (no caution copy): the data's straight-line caveats become plain unit wording ('직선거리'), and
# sentences that only warn ('… 바뀔 수 있어 … 미리 봐야 합니다', '… 전화해 확인하세요') are dropped from prose shown by
# a template that opts in (the `decaution` filter: guide prose, guide items, FAQ answers, place details). Facts are
# untouched; a digit or a place name is never removed (only whole warning sentences and the caveat clause). The
# content track should make the same edits in the data; JSON-LD that repeats such a text must use the same filter.
CAUTION_SUBS = (
    (re.compile(r"\s*\((?:모두\s*)?(?:직선거리(?:로|라|는)?,?\s*)?실제 이동 거리와 다릅니다\)"), ""),
    (re.compile(r"(이며|로|이고),\s*실제 이동 거리와 다릅니다\."), "입니다."),
    (re.compile(r"(?:모두\s*)?직선거리라\s*실제 이동 거리와 다릅니다"), "모두 직선거리입니다"),
    (re.compile(r"직선거리이며\s*실제 이동 거리와 다릅니다"), "직선거리입니다"),
)
CAUTION_SENT = re.compile(r"(바뀔 수 있어[^.]*미리 봐야 합니다|전화해 확인하세요|실제 이동 거리와 다릅니다)")


def decaution(text: str | None) -> str:
    t = str(text or "")
    for rx, rep in CAUTION_SUBS:
        t = rx.sub(rep, t)
    t = t.replace("입니다입니다", "입니다").replace("모두 모두", "모두")
    return " ".join(x for x in re.split(r"(?<=[.!?])\s+", t) if x and not CAUTION_SENT.search(x))


# The repo's P0-1 pattern: whole numbers only (0507-1364-9263 must never become 07-1364-9263).
PHONE = re.compile(r"(?<![\d-])(0\d{1,3}-\d{3,4}-\d{4}|1\d{3}-\d{4})(?![\d-])")


def tel_digits(number: str) -> str:
    return re.sub(r"\D", "", number or "")


def tel_href(number: str, intl: bool = False) -> str:
    """The tel: target of a visible number: its digits on Korean pages; on the other versions (intl) the +82 form a
    caller abroad dials ('063-443-3077' -> '+82634433077') — never for a number with no international form
    (nationwide 1577-…, 080, 060: textutil.phone_e164), which keeps its digits."""
    digits = tel_digits(number)
    return "+82" + digits[1:] if intl and phone_e164(squash_ws(number)) else digits


# Official sites the data writes as bare text ('예매는 한국해운조합(island.theksa.co.kr)에서'), linked where the text
# names them (QA 2026-10-15 SRC-05b) — only these hosts, each to the address checked on the given date: {host: (Korean
# page's URL, the other versions' URL or None, checked)}. A host the data says does not open or one not checked
# (www.kobus.co.kr: no answer from the build machine on 2026-10-15) stays plain text. These are the national ones; a
# city adds its own (a campground, a race, an airline: site.json city.official_web) — official_web(), web_rx().
OFFICIAL_WEB = {
    "island.theksa.co.kr": ("https://island.theksa.co.kr/", "https://island.theksa.co.kr/page/booking?lang=en", "2026-10-15"),
    "www.korail.com": ("https://www.korail.com/", None, "2026-10-15"),
    # the passenger-ship service page guide-32 cites for '여객선 운항정보 조회'
    "www.komsa.or.kr": ("https://www.komsa.or.kr/prog/pssgCurState/kor/sub03_0202/list.do", None, "2026-10-15"),
    "kma.go.kr": ("https://www.kma.go.kr/weather/main.jsp", None, "2026-10-15"),     # a weather guide's source (→ 날씨누리)
    "khoa.go.kr": ("https://www.khoa.go.kr/", None, "2026-10-15"),                   # a sea guide's source
}


def official_web() -> dict:
    """The national hosts (OFFICIAL_WEB) and the city's own (site.json city.official_web {host: [Korean page, other
    versions' page or null, checked]})."""
    own = {h: tuple(v) for h, v in (city.current().get("official_web") or {}).items()
           if isinstance(v, (list, tuple)) and len(v) == 3}
    return {**OFFICIAL_WEB, **own}


@functools.lru_cache(maxsize=8)
def _web_rx(hosts: tuple) -> re.Pattern:
    return re.compile(r"(?<![A-Za-z0-9.@/-])(" + "|".join(map(re.escape, sorted(hosts, key=len, reverse=True)))
                      + r")(/[A-Za-z0-9._~%/?=&-]*[A-Za-z0-9/])?(?![A-Za-z0-9-])")


def web_rx() -> re.Pattern:
    """A host of official_web() written in a text, with the path written after it."""
    return _web_rx(tuple(sorted(official_web())))


def web_href(host: str, path: str | None = None, intl: bool = False) -> str:
    """The link of an official host written in the text: the written path on that host when the text gives one
    ('example.com/resv'), else the other versions' entry page (intl) when there is one, else the checked page."""
    ko_url, intl_url, _ = official_web()[host]
    if path:
        return "https://" + host + path
    return intl_url if intl and intl_url else ko_url


def web_anchor(seg, url: str) -> Markup:
    return Markup('<a class="xl" href="{}" rel="noopener" data-track="official_click">{}</a>').format(url, seg)


def tel_markup(text: str | None, place: str = "", intl: bool = False, skip: int = 0) -> Markup:
    """Phone numbers as tap-to-call links (tel_click, + data-place on a place page) and the official hosts the text
    writes (OFFICIAL_WEB) as links (official_click). The tel: digits are always exactly the digits of the visible
    number (tests check it) — on the other versions (intl) in the +82 form (tel_href) — and the number never breaks
    across lines (class tel). The text of the result is `text`, character for character. skip: no link starts in the
    first characters (an FAQ answer: FAQPage repeats it and pipeline.validate compares its first PLAIN_HEAD characters
    with the page as one run, as in rich())."""
    text = str(text or "")
    found = [(m.start(1), m.end(1), "tel", m) for m in PHONE.finditer(text)]
    found += [(m.start(), m.end(), "web", m) for m in web_rx().finditer(text)]
    parts, last = [], 0
    for a, b, kind, m in sorted(found, key=lambda x: x[0]):
        if a < max(last, skip):
            continue
        parts.append(escape(text[last:a]))
        if kind == "tel":
            num = m.group(1)
            pl = Markup(' data-place="{}"').format(place) if place else ""
            parts.append(Markup(f'<a class="tel" data-track="tel_click"{pl} href="tel:{tel_href(num, intl)}">{escape(num)}</a>'))
        else:
            parts.append(web_anchor(escape(text[a:b]), web_href(m.group(1), m.group(2), intl)))
        last = b
    parts.append(escape(text[last:]))
    return Markup("").join(parts)


def first_phone(*values) -> tuple[str, str]:
    """(visible number, tel: digits) of the first whole phone number in the values, else ('', '')."""
    for v in values:
        m = PHONE.search(str(v or ""))
        if m:
            return m.group(1), tel_digits(m.group(1))
    return "", ""


def settled_phone(e: dict) -> tuple[str, str]:
    """The place's call number (문의, else 예약 안내) for a call button, a list cell or the status line — ('', '')
    when another source gives that field differently (CLAUDE.md 3.2: never pick one; the facts row shows both)."""
    if contested(e, "infocenter") or contested(e, "reservation"):
        return "", ""
    facts = e.get("facts") or {}
    return first_phone(facts.get("infocenter"), facts.get("reservation"))


NUM_RUN = re.compile(r"(\d+(?:[-–]\d+)+)")


def nowrap_numbers(text: str | None) -> Markup:
    """House numbers like '12-1' never break across lines."""
    text = str(text or "")
    out, last = [], 0
    for m in NUM_RUN.finditer(text):
        out.append(escape(text[last:m.start()]))
        out.append(Markup('<span class="nw">') + escape(m.group(1)) + Markup("</span>"))
        last = m.end()
    out.append(escape(text[last:]))
    return Markup("").join(out)


# the emphasised end of a site name of the '○○각' family (the engine's first site, operator 2026-10-17: ○○각 → 각,
# ○○gak → gak); a city may name its own (site.json city.brand_em), a name without such an end has none
BRAND_EM = ("각", "gak")


def wordmark(name: str | None) -> Markup:
    """The site name in the bar and the footer with its emphasised end in its own span (css .wm-em: the site blue, as
    in the brand's logos); one word to a screen reader, the text unchanged."""
    s = str(name or "")
    for em in city.current().get("brand_em") or BRAND_EM:
        if s.endswith(em) and len(s) > len(em):
            return escape(s[:-len(em)]) + Markup('<span class="wm-em">') + escape(em) + Markup("</span>")
    return escape(s)


ADDRESS_WORD_MAX = 16   # the longest hyphenated word kept whole; the next in the data is 13 characters ('174-4,2층(미룡동)')


def nowrap_address(text: str | None) -> Markup:
    """An address on the page (templates/_p1.html.j2): each word holding a hyphen ('244-7(장미동)') in one no-wrap piece,
    split at the spaces already there; a longer word — an address the source gives without spaces — stays plain, one
    text run (the validator reads it whole, as JSON-LD has it), and the body's overflow-wrap breaks it on a phone.
    Text unchanged."""
    def word(w: str) -> Markup:
        if "-" not in w or len(w) > ADDRESS_WORD_MAX:
            return escape(w)
        return Markup('<span class="nw">') + escape(w) + Markup("</span>")
    return Markup(" ").join(word(w) for w in str(text or "").split(" "))


def lines_html(text: str | None) -> Markup:
    return Markup("<br>").join(escape(x) for x in str(text or "").split("\n"))


def kind_type(e: dict, theme_names: dict) -> str:
    """Human type label; '' when the source only has a generic bucket (shown as no type)."""
    kind = e.get("kind")
    cat = squash_ws(e.get("category"))
    if kind == "stay":
        return STAY_TYPE.get(cat, cat)
    if kind == "food":
        if "특화거리" in cat:
            return cat.partition("(")[2].rstrip(")").strip()
        return FOOD_TYPE.get(cat, cat)
    g = e.get("_group") or ""
    if g and g != "테마 여행지":
        return g
    if cat in ATTR_TYPE:
        return ATTR_TYPE[cat]
    for t in e.get("themes") or []:
        if t in theme_names:
            return theme_names[t]
    return ""


def street_of(e: dict) -> str:
    """'짬뽕 특화거리' for a food place listed under a 특화거리 category."""
    cat = squash_ws(e.get("category"))
    return cat.partition("(")[0].strip() if e.get("kind") == "food" and "특화거리" in cat else ""


def name_key(name: str):
    """가나다 first, Latin and digits after (so 'MCL' does not lead a group)."""
    return (0 if re.match(r"[가-힣]", name or "") else 1, name or "")


# ----------------------------------------------------------------------------- value presentation
# a label may hold a month span ('3~10월', '11~2월') but no other figure
_LABEL = rf"(?:\d{{1,2}}\s*(?:{TILDE}|[\-–])\s*\d{{1,2}}\s*월|\d{{1,2}}\s*월|[^\d\[\]])*?"
RANGE_RX = re.compile(rf"^(?P<label>{_LABEL})\s*(?P<a>{TIME})\s*(?:{TILDE}|[\-–—])\s*(?P<b>{TIME})\s*(?P<note>.*)$")
SINGLE_RX = re.compile(rf"^(?P<label>[가-힣][^\d\[\]]*?)\s*(?P<a>{TIME})\s*(?P<note>.*)$")
CLOSED_LABEL_RX = re.compile(r"^(?P<label>휴무일?|휴관일|정기휴일|쉬는\s*날)\s*[:：]\s*(?P<value>.+)$")
OPEN_WORDS = ("연중무휴", "연중 무휴", "년중 무휴", "상시 개방", "상시개방", "휴무일 : 없음", "휴무일: 없음")
CLOSED_HINT = re.compile(r"(휴무|휴관|휴일|휴장|요일|명절|설날|추석|설·추석|공휴일|\d+월\s*\d+일)")
TIME_KEYS = ("usetime", "usetime_restdate", "openperiod")


def is_open_value(text: str | None) -> bool:
    t = squash_ws(text)
    return any(t.startswith(w) for w in OPEN_WORDS) or t in ("없음", "무휴")


def timetable(raw: str | None):
    """Conservative parse of hours text into rows. Every segment must be understood, otherwise None and the
    caller prints the whole display text (P1-7). Rows keep every source word in source order and add no
    label of their own, so printing group · label · value · note per row, then the foot notes, shows the
    same words as display_value() (pipeline.validate checks exactly that). Row kinds: time, closed, open."""
    lines = restore_lines(raw)
    if not lines or not re.search(TIME, " ".join(lines)):
        return None
    rows, foot, group = [], [], ""
    for line in lines:
        if line.startswith("※"):
            foot.append(line.lstrip("※ ").strip())
            continue
        if foot:  # a note in the middle would move in a table: keep the whole text instead
            return None
        m = re.fullmatch(r"\[([^\]]+)\]", line)
        if m:
            group = squash_ws(m.group(1))
            continue
        for seg in re.split(r"\s*/\s*|,\s*(?=휴무일)", line):
            seg = seg.strip().lstrip("-").strip().strip(",").strip()
            if not seg:
                continue
            m = RANGE_RX.match(seg)
            if m:
                note = m.group("note").strip()
                if note and not re.fullmatch(r"\(([^()]*)\)", note):
                    return None
                rows.append({"group": group, "label": m.group("label").strip(" :,"), "kind": "time", "closed": False,
                             "value": f"{m.group('a')}–{m.group('b')}", "note": note[1:-1].strip() if note else ""})
                continue
            m = SINGLE_RX.match(seg)
            if m and not m.group("note").strip():
                rows.append({"group": group, "label": m.group("label").strip(" :,"), "kind": "time", "closed": False,
                             "value": m.group("a"), "note": ""})
                continue
            if CLOSED_HINT.search(seg) and not re.search(TIME, seg):
                m = CLOSED_LABEL_RX.match(seg)
                label, value = (squash_ws(m.group("label")), squash_ws(m.group("value"))) if m else ("", seg)
                shut = not is_open_value(value)
                rows.append({"group": "", "label": label, "kind": "closed" if shut else "open", "closed": shut,
                             "value": value, "note": ""})
                continue
            if is_open_value(seg):
                rows.append({"group": "", "label": "", "kind": "open", "closed": False, "value": seg, "note": ""})
                continue
            return None
    return {"rows": rows, "foot": foot} if rows else None


def time_set(raw: str | None) -> set:
    return set(re.findall(rf"{TIME}–{TIME}", dash_times(str(raw or "")).replace(" ", "")))


PRICE = r"(?:[\d,]+원(?:\s*\([\d,]+원\))?|무료)"
FEE_RX = re.compile(rf"^(?P<who>[^\d\[\]][^:]*?)\s*:?\s*(?P<price>{PRICE})$")
# a city fee table flattened into one line: '개인 단체(20인 이상) 성인 (시민) 1,000 (500) 700 (300) …'
GRID_ROW = re.compile(r"(?P<who>[^\d()]+?)\s*\((?P<sub>[^)]+)\)\s*(?P<a>[\d,]+)\s*\((?P<asub>[\d,]+)\)\s*"
                      r"(?P<b>[\d,]+)\s*\((?P<bsub>[\d,]+)\)")


def fee_grid(raw: str | None):
    """The flattened two-column fee table (a park's two-column table): columns, the bracketed sub-group, rows. None unless
    the whole text parses."""
    t = squash_ws(raw)
    m = re.match(r"^(?P<c1>[가-힣]+)\s+(?P<c2>[가-힣]+(?:\([^)]*\))?)\s+(?P<rest>.+)$", t)
    if not m:
        return None
    rows, pos, rest = [], 0, m.group("rest")
    for r in GRID_ROW.finditer(rest):
        if rest[pos:r.start()].strip():
            return None
        rows.append(r.groupdict())
        pos = r.end()
    if not rows or rest[pos:].strip() or len({r["sub"] for r in rows}) != 1:
        return None
    return {"cols": [m.group("c1"), m.group("c2")], "sub": rows[0]["sub"],
            "rows": [{"who": squash_ws(r["who"]), "sub": r["sub"], "a": r["a"], "asub": r["asub"], "b": r["b"],
                      "bsub": r["bsub"]} for r in rows]}


def fee_table(raw: str | None):
    """'[개별권]' groups of 'who price' rows. None unless every line parses (then the whole text prints)."""
    lines = restore_lines(raw)
    if not lines or "원" not in " ".join(lines) or len(lines) < 2:
        return None
    groups, foot, cur = [], [], None
    for line in lines:
        if line.startswith("※"):
            foot.append(line.lstrip("※ ").strip())
            continue
        if foot:
            return None
        m = re.fullmatch(r"\[([^\]]+)\]\s*(.*)", line)
        if m:
            cur = {"label": squash_ws(f"{m.group(1)} {m.group(2)}"), "rows": []}
            groups.append(cur)
            continue
        m = FEE_RX.match(line.lstrip("-").strip())
        if not m:
            return None
        if cur is None:
            cur = {"label": "", "rows": []}
            groups.append(cur)
        cur["rows"].append({"who": m.group("who").strip(), "price": m.group("price")})
    if not groups or not all(g["rows"] for g in groups):
        return None
    return {"groups": groups, "foot": foot}


CLOSED_SPAN = re.compile(
    r"((?:휴무일?\s*[:：]\s*)?(?:매주|매달|매월|격주|첫째|둘째|셋째|넷째|\d째주|[,·\s])*\s*"
    r"(?:(?:(?:(?<![가-힣])|(?<=[주째]))[월화수목금토일](?:요일)?|공휴일|법정\s*공휴일)[,·\s~]*)+(?:\s*\([^)]*\))?\s*"
    r"(?:정기\s*)?(?:휴무|휴관|휴일)"
    r"|휴무일?\s*[:：]\s*(?:매주\s*)?[월화수목금토일]요일"
    r"|명절(?:당일)?\s*휴무|명절\s*당일\s*휴무)")


def mark_closed(text: str | None) -> Markup:
    """Wrap closed-day phrases inside a mixed value (hours + closed day) in <span class="closed">. Text unchanged."""
    text = str(text or "")
    out, last = [], 0
    for m in CLOSED_SPAN.finditer(text):
        if is_open_value(m.group(0)):
            continue
        a, b = m.span()
        lead = len(m.group(0)) - len(m.group(0).lstrip(" ,·"))
        out.append(escape(text[last:a + lead]))
        out.append(Markup('<span class="closed">') + escape(text[a + lead:b]) + Markup("</span>"))
        last = b
    out.append(escape(text[last:]))
    return Markup("").join(out)


def closed_head(text: str | None) -> Markup:
    """A closed-day phrase in a one-line row (templates/_near.html.j2): its first word — unspaced Japanese or Chinese,
    its first two characters — in one no-wrap piece that carries the red square (css/71-nearby.css), so the square never
    ends a line alone ('■ / Every Monday'); a ' / ' never starts a line ('/ 법정공휴일'). Text unchanged but that space."""
    s = squash_ws(text).replace(" / ", "\u00a0/ ")
    head, sep, tail = s.partition(" ")
    if not sep and len(head) > 6:
        head, tail = s[:2], s[2:]
    return Markup('<span class="nw">') + escape(head) + Markup("</span>") + escape(sep + tail)


def glue_dots(text: str | None) -> Markup:
    """'… 무료 해설·스탬프투어': each middle dot kept with the character before it (a no-wrap pair), so a line never
    starts with '·'. Text unchanged."""
    t, out, last = squash_ws(text), [], 0
    for m in re.finditer(r"\S·", t):
        out += [escape(t[last:m.start()]), Markup('<span class="nw">') + escape(m.group(0)) + Markup("</span>")]
        last = m.end()
    out.append(escape(t[last:]))
    return Markup("").join(out)


def split_closed(text: str | None) -> tuple[str, str]:
    """'10:00~21:00 / 매주 월요일' -> ('10:00~21:00', '매주 월요일'); ('…', '') when no closed part."""
    t = squash_ws(text)
    if " / " in t:
        hours, rest = t.rsplit(" / ", 1)
        if CLOSED_HINT.search(rest) and not re.search(TIME, rest):
            return hours, rest
    m = re.search(r"(?:,\s*)?휴무일?\s*[:：]\s*([^/]+)$", t)
    if m and not re.search(TIME, m.group(1)):
        return t[:m.start()].strip(" ,"), squash_ws(m.group(1))
    return t, ""


def value_view(key: str, raw, place: str = "") -> dict:
    """One stored value for a template: text (display_value, '\\n' line breaks), html (the whole text with
    line breaks, closed days marked, phone links, house numbers kept whole), and a parsed form when the whole
    value parses: tt (timetable), fees (price table) or grid (two-column fee table). A parsed form keeps every
    source word in order; otherwise the template prints html. Never shortens a value. place: the entity id put on
    the value's tracked links (data-place) on a place page. A template that prints
    the parsed form marks it with data-form (e.g. <table data-form="tt">) inside the row's <dd data-key>:
    pipeline.validate then lets the table drop layout punctuation; text rows must match display_value
    verbatim."""
    text = display_value(key, raw)
    v = {"text": text, "html": lines_html(text), "tt": None, "fees": None, "grid": None, "closed": False,
         "wide": "\n" in text or len(text) > 22}
    if not text:
        return v
    raw_s = str(raw)
    if key in TIME_KEYS:
        tt = timetable(raw_s)
        if tt and (len(tt["rows"]) > 1 or tt["rows"][0]["label"] or tt["rows"][0]["group"] or tt["foot"]):
            v.update(tt=tt, wide=True)
        v["html"] = Markup("<br>").join(mark_closed(x) for x in text.split("\n"))
    elif key == "restdate":
        v["closed"] = not is_open_value(text)
    elif key in ("usefee", "parkingfee", "discount"):
        grid = fee_grid(raw_s) if key == "usefee" else None
        fees = None if grid or squash_ws(raw_s) in ("무료", "없음") else fee_table(raw_s)
        if grid:
            v.update(grid=grid, wide=True)
        elif fees:
            v.update(fees=fees, wide=True)
    elif key in ("homepage", "reservationurl"):
        url = link_url(raw_s)
        if url:
            v["url"] = url
            pl = Markup(' data-place="{}"').format(place) if place else ""
            v["html"] = Markup(f'<a href="{escape(url)}" rel="noopener" data-track="official_click"{pl}>'
                               f'{escape(text)}</a>')
    elif key in ("infocenter", "reservation"):
        v["html"] = Markup("<br>").join(tel_markup(x, place) for x in text.split("\n"))
    elif key == "address":
        v["html"] = nowrap_numbers(text)
    return v


def linear_text(v: dict) -> str:
    """The words a parsed form prints, in order (what a table shows to a text reader). Tests use it to prove
    that every parsed form passes the validator's token check against display_value()."""
    if v.get("tt"):
        parts, g = [], None
        for r in v["tt"]["rows"]:
            parts += [r["group"] if r["group"] != g else "", r["label"], r["value"], r["note"]]
            g = r["group"]
        return squash_ws(" ".join(p for p in parts + v["tt"]["foot"] if p))
    if v.get("fees"):
        parts = []
        for g in v["fees"]["groups"]:
            parts.append(g["label"])
            for x in g["rows"]:
                parts += [x["who"], x["price"]]
        return squash_ws(" ".join(p for p in parts + v["fees"]["foot"] if p))
    if v.get("grid"):
        g = v["grid"]
        parts = list(g["cols"])
        for r in g["rows"]:
            parts += [r["who"], r["sub"], r["a"], r["asub"], r["b"], r["bsub"]]
        return squash_ws(" ".join(parts))
    return squash_ws(v.get("text"))


# ----------------------------------------------------------------------------- per-field sources as footnotes
class Notes:
    """Numbered source notes for one page: value¹ … ¹ 한국관광공사 TourAPI (linked when the source has a URL).
    One note per provider, URL and 재확인 source: the 확인일 is kept on the item (the newest of the values it backs)
    but never printed — operator decision 2026-10-09: no visible check dates; they stay in the data and JSON-LD."""

    def __init__(self):
        self.items: list[dict] = []

    def ref(self, src: dict, label: str) -> int:
        provider = squash_ws(src.get("provider") or src.get("name") or "출처 미기재")
        confirmed = re.sub(r"\s+\d{4}-\d{2}-\d{2}$", "", squash_ws(src.get("confirmed_by")))
        key = (provider, confirmed, web_url(src.get("url") or ""))
        checked = squash_ws(src.get("checked_at"))
        for i, it in enumerate(self.items):
            if it["key"] == key:
                if label not in it["labels"]:
                    it["labels"].append(label)
                it["checked_at"] = max(it["checked_at"], checked)
                return i + 1
        self.items.append({"key": key, "provider": provider, "checked_at": checked,
                           "confirmed_by": confirmed, "url": key[2], "labels": [label]})
        return len(self.items)


class ChapterNotes:
    """Chapter source notes (FAQ, 자세히): one superscript per answer, the providers listed once at the end."""

    def __init__(self, labels: dict, default: str):
        self.labels, self.default, self.items = labels, default, []

    def ref(self, source: str | None) -> int | None:
        s = squash_ws(source)
        if not s:
            return None
        if s.startswith("http"):
            name = self.labels.get(s) or ("한국관광공사 대한민국 구석구석" if "visitkorea" in s
                                          else self.default if city.current().official_url(s) else url_domain(s))
            item = {"url": s, "name": name}
        else:
            item = {"url": "", "name": s}
        if item not in self.items:
            self.items.append(item)
        return self.items.index(item) + 1


def short_provider(p: str | None) -> str:
    """'한국관광공사', the city's short name for its official site (site.json city.official), else the name as given."""
    return city.current().short_provider(squash_ws(p))


def src_of(e: dict, k: str) -> dict:
    """Where facts[k] came from (same rule as build.fact_source, plus confirmed_by)."""
    src = (e.get("fact_sources") or {}).get(k) or e.get("facts_source") or {}
    return {"provider": squash_ws(src.get("provider")) or squash_ws((e.get("original") or {}).get("source_name")),
            "checked_at": squash_ws(src.get("checked_at")), "url": web_url(src.get("url")),
            "confirmed_by": squash_ws(src.get("confirmed_by"))}


def alternatives(e: dict, k: str) -> list[dict]:
    """Other sources' values that differ from the stored one (relation 'also' adds, it does not contradict)."""
    raw = (e.get("facts") or {}).get(k) or ""
    shown = display_address(raw) if k == "address" else raw
    seen, out = {squash_ws(str(shown))}, []
    for a in (e.get("fact_alternatives") or {}).get(k) or []:
        v = str(a.get("value") or "")
        if k == "address":
            v = display_address(v)
        if not squash_ws(v) or squash_ws(v) in seen:
            continue
        seen.add(squash_ws(v))
        out.append({**a, "value": v})
    return out


def contested(e: dict, k: str) -> list[dict]:
    return [a for a in alternatives(e, k) if a.get("relation") != "also"]


def conflict_label(key: str, main: str, alts: list[dict]) -> str:
    """'영업시간만 다름' when the closed day agrees (both 매주 월요일) and only the hours differ."""
    if key == "usetime_restdate":
        _, c1 = split_closed(main)
        if c1 and all(split_closed(a["value"])[1] == c1 for a in alts):
            return "영업시간만 다름"
    return "출처마다 다름"


CALL_LINE = "방문 전 전화 확인"


def fact_rows(e: dict, keys, notes: Notes, tel: tuple = ("", "")) -> list[dict]:
    """Rows for a facts list. A row: key, keys (data-key values; two when 문의·예약 merge), label, the value
    view (text/html/tt/fees/grid/closed/wide), n (footnote), provider (short) / provider_full, alts (relation
    'also' values: '또는 …'), and for a conflict: conflict=True, flag ('출처마다 다름' or '영업시간만 다름'),
    flag_text ('… · 방문 전 전화 확인', to print first), blocks (one per source, provider header first), tel
    ((visible number, tel: digits) on the first conflict row only), same_times (both sources state the same
    hours)."""
    facts = e.get("facts") or {}
    out, called = [], False
    for k in keys:
        raw = facts.get(k) or ""
        alts = alternatives(e, k)
        if not raw and not alts:
            continue
        label = fact_label(e, k)
        src = src_of(e, k)
        view = value_view(k, raw, e.get("id") or "")
        row = {"key": k, "keys": [k], "label": label, **view, "n": notes.ref(src, label) if raw else None,
               "provider": short_provider(src["provider"]) if raw else "", "provider_full": src["provider"] if raw else "",
               "checked_at": src["checked_at"] if raw else "", "alts": [], "conflict": False, "same_times": False,
               "blocks": [], "flag": "", "flag_text": "", "tel": None}
        for a in alts:
            also = a.get("relation") == "also"
            a_src = {"provider": squash_ws(a.get("provider")), "checked_at": squash_ws(a.get("checked_at")),
                     "url": a.get("url") or "", "confirmed_by": squash_ws(a.get("confirmed_by"))}
            av = value_view(k, a["value"], e.get("id") or "")
            item = {**av, "n": notes.ref(a_src, label + ("(추가)" if also else "(다른 값)")),
                    "provider": short_provider(a_src["provider"]), "provider_full": a_src["provider"],
                    "checked_at": a_src["checked_at"], "also": also}
            if also:
                row["alts"].append(item)
                continue
            row["conflict"] = True
            if k in TIME_KEYS and time_set(raw) and time_set(raw) == time_set(a["value"]):
                row["same_times"] = True
            row["blocks"].append(item)
        if row["conflict"]:
            row["wide"] = True
            if raw:
                row["blocks"].insert(0, {**view, "n": row["n"], "provider": row["provider"],
                                         "provider_full": row["provider_full"], "checked_at": row["checked_at"],
                                         "also": False})
            row["flag"] = conflict_label(k, raw, [a for a in alts if a.get("relation") != "also"])
            row["flag_text"] = f"{row['flag']} · {CALL_LINE}"
            if not called and tel[0]:
                row["tel"], called = (tel[0], tel[1]), True  # (visible number, tel: digits)
        out.append(row)
    # 문의 and 예약 안내 with the same text collapse into one row ('문의·예약'); a homepage and a booking page
    # that display the same way into '홈페이지·예약' — only when they also link to the same address (one row has one
    # link: 'hotel.example.kr:4446/' and 'hotel.example.kr' display alike but are two pages)
    for a_key, b_key, merged in (("infocenter", "reservation", "문의·예약"), ("homepage", "reservationurl", "홈페이지·예약")):
        ra = next((r for r in out if r["key"] == a_key), None)
        rb = next((r for r in out if r["key"] == b_key), None)
        if ra and rb and ra["text"] and ra["text"] == rb["text"] and ra.get("url", "") == rb.get("url", "") \
                and not (ra["alts"] or rb["alts"] or ra["conflict"] or rb["conflict"]):
            ra["label"], ra["keys"] = merged, [a_key, b_key]
            out.remove(rb)
    return out


FEE_ANCHOR = "f-usefee"   # the facts card's 요금 row, where a ticket row whose table it already holds points


def ticket_rows(e: dict, notes: Notes) -> list[dict]:
    """The facts card's rows for the combined tickets that open the place (pipeline/tickets.py), one per ticket, after
    its own 요금: the ticket's name, what it opens in our words — its places by their page names, each linked but this
    one ('4곳: 근대역사박물관 · …'; never the table's own words for them, tickets.json 'covers', CLAUDE.md 3.3) — and
    its price table, with the table's source as the row's note: the combined price the fee tile sets beside the
    place's own (fee_with_ticket) is on the page with its source, also where the place's own table does not name the
    ticket. Where the place's own table already holds the ticket as a group with the same prices (same_ticket_group),
    the row points to that group (FEE_ANCHOR) instead of printing the table twice."""
    out = []
    for t in e.get("_tickets") or []:
        places = t.get("_places") or []
        head = f"{len(places)}곳: "
        same = same_ticket_group(e, t)
        lines = [f"요금: 위 이용요금의 [{same}]"] if same else tickets.price_lines(t)
        text = "\n".join([head + " · ".join(p["name"] for p in places), *lines])
        html = escape(head) + Markup(" · ").join(
            escape(p["name"]) if p["id"] == e["id"] else Markup('<a href="{}">{}</a>').format(p["path"], p["name"])
            for p in places)
        if same:
            html += Markup('<br><a href="#{}">{}</a>').format(FEE_ANCHOR, lines[0])
        else:
            html += Markup("<br>") + lines_html("\n".join(lines))
        src = t.get("src") or {}
        label = squash_ws(t["name"])
        out.append({"key": "tickets", "keys": ["tickets"], "label": label, "text": text, "html": html, "same": same,
                    "tt": None, "fees": None, "grid": None, "closed": False, "wide": True,
                    "n": notes.ref({"provider": src.get("provider"), "checked_at": src.get("checked_at"),
                                    "url": src.get("url") or ""}, label),
                    "provider": short_provider(src.get("provider")), "provider_full": squash_ws(src.get("provider")),
                    "checked_at": squash_ws(src.get("checked_at")), "alts": [], "conflict": False,
                    "same_times": False, "blocks": [], "flag": "", "flag_text": "", "tel": None})
    return out


# ----------------------------------------------------------------------------- status line (핵심 정보 줄)
STATUS_KEYS = {"attraction": ("usetime", "restdate", "usefee", "parking"),
               "stay": ("checkin", "checkout", "parking", "roomcount"),
               "food": ("usetime_restdate", "usetime", "restdate", "menu", "parking_seats", "parking")}
STATUS_PREFIX = {"usefee": "요금", "parking_seats": "주차·좌석", "checkin": "체크인", "checkout": "체크아웃",
                 "roomcount": "객실", "menu": "대표 메뉴"}
CONTEST_LABEL = {"usetime": "이용시간", "restdate": "쉬는 날", "usefee": "요금", "parking": "주차",
                 "usetime_restdate": "영업시간", "checkin": "체크인", "checkout": "체크아웃", "menu": "대표 메뉴",
                 "parking_seats": "주차·좌석", "roomcount": "객실"}
STATUS_MAX, CLOSED_MAX = 24, 48


def _closed_word(text: str, kind: str) -> str:
    """'매주 월요일' -> '매주 월요일 휴관' (휴무 for food); text that already says so, or is a sentence, as is.
    An open value keeps what it answers: '휴무일 : 없음' split to '없음' reads '휴무일 없음', never a bare '없음'."""
    if is_open_value(text):
        return text if re.search(r"무휴|개방|휴", text) else f"휴무일 {text}"
    if re.search(r"휴|쉼|쉬", text) or not re.search(r"(요일|[0-9]일|날|명절|연휴|설날|추석)\)?$", text):
        return text
    return f"{text} {'휴무' if kind == 'food' else '휴관'}"


def missing_keys(e: dict) -> list[str]:
    """Labels of the kind's key facts the data has no value for (category rules: a market has no fee)."""
    facts = e.get("facts") or {}
    alt = set((e.get("fact_alternatives") or {}).keys())
    keys = KEY_FACTS_BY_CATEGORY.get(e.get("category"), KEY_FACTS.get(e.get("kind"), ()))
    out = []
    for k in keys:
        have = facts.get(k) or any(alias_holds(e, k, a) for a in FACT_ALIASES.get(k, ())) or k in alt
        if k == "parking" and facts.get("parkingfee"):
            have = True
        if not have:
            out.append(FACT_LABELS[k])
    return out


def status_items(e: dict, full: bool = False) -> list[dict]:
    """The key-information line (CLAUDE.md 7: 운영시간·쉬는 날·요금·주차·전화). Items are whole values
    (≤24 characters; a closed day may wrap up to 48); a contested value is never picked: it reads
    '<label> 출처마다 다름' and links to both sources (#h-facts). With no value at all the line still says what
    is missing ('확인 필요: …'), so it is never empty. full=True (the place page) adds the phone. No 확인일:
    operator decision 2026-10-09 (check dates stay in the data and JSON-LD, never on the page).
    Item: {key, text, html, closed, cls, href}."""
    facts = e.get("facts") or {}
    kind = e.get("kind")
    out: list[dict] = []
    facts_href = ("" if full else e.get("_path", "")) + "#h-facts"

    def add(k, text, closed=False, cls="", html=None, src_key=None):
        out.append({"key": k, "text": text, "html": html if html is not None else escape(text), "closed": closed,
                    "cls": cls, "href": ""})

    def flag(k):
        text = f"{CONTEST_LABEL.get(k, FACT_LABELS[k])} 출처마다 다름"
        out.append({"key": k + "-c", "text": text, "html": escape(text), "closed": False, "cls": "st-flag",
                    "href": facts_href})

    for k in STATUS_KEYS.get(kind, ()):
        raw = facts.get(k)
        if not raw:
            # a seats-only parking_seats item ('좌석 30석') does not answer parking: the fee still goes in
            answered = any(x["key"] == "parking" or (x["key"] == "parking_seats"
                                                     and alias_holds(e, "parking", "parking_seats")) for x in out)
            if k == "parking" and facts.get("parkingfee") and not answered:
                fee = squash_ws(facts["parkingfee"])
                if len(fee) <= STATUS_MAX and "\n" not in str(facts["parkingfee"]).strip() and not contested(e, "parkingfee"):
                    add("parkingfee", "주차 무료" if fee == "무료" else f"주차 요금 {display_value('parkingfee', fee)}")
            if contested(e, k):
                flag(k)
            continue
        alts = contested(e, k)
        if alts:
            if k == "usetime_restdate":
                _, c1 = split_closed(raw)
                if c1 and all(split_closed(a["value"])[1] == c1 for a in alts) and len(c1) <= CLOSED_MAX:
                    word = _closed_word(c1, kind)
                    add(k + "-closed", word, not is_open_value(c1), src_key=k)
                    text = "영업시간 출처마다 다름"
                    out.append({"key": k + "-c", "text": text, "html": escape(text), "closed": False,
                                "cls": "st-flag", "href": facts_href})
                    continue
            flag(k)
            continue
        multi = "\n" in str(raw).strip() and k != "parking"
        if k == "usetime_restdate":
            hours, closed = split_closed(raw)
            text = dash_times(squash_ws(raw))
            if not multi and len(text) <= CLOSED_MAX and closed:
                add(k, dash_times(hours))
                add(k + "-closed", _closed_word(closed, kind),
                    not is_open_value(closed), src_key=k)
            elif not multi and len(text) <= STATUS_MAX:
                add(k, text, html=mark_closed(text))
            elif closed and len(closed) <= CLOSED_MAX:
                add(k + "-closed", _closed_word(closed, kind),
                    not is_open_value(closed), src_key=k)
            continue
        if k == "restdate":
            text = squash_ws(raw)
            if multi or len(text) > CLOSED_MAX:
                continue
            if is_open_value(text):
                add(k, _closed_word(text, kind))
            else:
                add(k, _closed_word(text, kind), True)
            continue
        text = parking_text(raw) if k == "parking" else dash_times(squash_ws(raw))
        if multi or len(text) > STATUS_MAX + (8 if k == "parking" else 0):
            continue
        if k == "usefee" and text == "무료":
            add(k, "입장 무료" if kind == "attraction" else "요금 무료")
        elif k == "parking":
            if any(x["key"] == "parking_seats" for x in out) and alias_holds(e, "parking", "parking_seats"):
                continue
            add(k, "주차 가능(무료)" if text == "가능, 요금 무료" else f"주차 {text}")
        elif k == "roomcount":
            add(k, f"객실 {text}실" if text.isdigit() else f"객실 {text}")
        elif k == "parking_seats" and parking_seats_half(e):
            lab = fact_label(e, k)   # one half only: '좌석 30석', never '주차·좌석 30석'
            add(k, text if text.startswith(lab) else f"{lab} {text}")
        else:
            add(k, f"{STATUS_PREFIX[k]} {text}" if k in STATUS_PREFIX else text)
    if not out:
        miss = missing_keys(e)
        if miss:
            text = "확인 필요: " + "·".join(miss)
            out.append({"key": "missing", "text": text, "html": escape(text), "closed": False, "cls": "st-missing",
                        "href": facts_href})
    if full:
        tel_text, tel = settled_phone(e)
        if tel:
            out.append({"key": "tel", "text": tel_text, "closed": False, "cls": "st-tel", "href": f"tel:{tel}",
                        "html": Markup(f'<a class="tel" href="tel:{tel}" data-track="tel_click">{escape(tel_text)}</a>')})
    return out


# ----------------------------------------------------------------------------- key facts (Apple spec tiles, card rows)
# One slot model (CINEMATIC.md §6, the Apple direction keeps it): a place's key values come from slot_value() in the
# kind's fixed order wherever the place appears — the first-screen tiles (HERO_SLOTS, 5), card rows and list cells
# (KF_CARD_SLOTS, 3; KF_LIST_COLS, 4). A value is never paraphrased or cut with an ellipsis: a long value shows its
# main part (the first parsed range / row / clause, in source order) and more=True ('외' → the facts table, which
# prints the whole value). Hours are read segment by segment ('[group]' lines, ' / ' parts, every time range with
# the words before it as its condition: '3~10월', '평일', '하절기'); ranges labelled 준비·휴게·마지막 주문·입장 마감 are
# secondary; a closed-day phrase inside an hours value goes to 쉬는 날; '※ …' notes and '(전화문의)' asides are left to
# the facts table. A slot is in conflict only when the sources' main parts differ: both are shown with their
# providers (never one picked, CLAUDE.md 3.2) and the page prints one call line (ui.kfnote).
ASK_NOTE = re.compile(r"(문의|참조)\s*(요망|바랍니다)|문의 후 방문|방문 전 전화|전화문의 요망")
ASK_PAREN = re.compile(r"\s*\((?:전화\s*문의|전화문의)\)\s*")
SECONDARY = re.compile(r"(준비|브레이크|쉬는\s*시간|휴게|마지막\s*주문|라스트\s*오더|라스트오더|입장\s*마감|점심\s*마지막|저녁\s*마지막)")
OPENISH = re.compile(r"(연중\s*무휴|년중\s*무휴|휴무\s*없음|휴무일\s*[:：]?\s*없음|^무휴|^없음$|상시\s*개방|연중\s*휴무|특별한\s*휴무\s*없음)")
WEEKLY = re.compile(r"([월화수목금토일]\s*요일|매주|매월|매달|격주|째\s*주|째주|[월화수목금토일]\s*[,·~]\s*[월화수목금토일])")
RANGE_FIND = re.compile(rf"({TIME})\s*(?:{TILDE}|[\-–])\s*({TIME})")
BASE_WORDS = ("영업시간", "이용시간", "운영시간", "관람시간")
BASE_LABEL = {"usetime": "이용시간", "usetime_restdate": "영업시간", "openperiod": "운영 기간"}
OPEN_HOURS = re.compile(r"(상시\s*개방|상시|24\s*시간|일출|일몰|예약제)")
FIRST_ADULT = re.compile(r"성인[^\d]{0,16}?([\d,]+원)")
FIRST_PRICE = re.compile(r"([가-힣][가-힣·]*)\s*:?\s*([\d,]+원)")


def clean_lines(raw) -> list[str]:
    """Source lines without the '※ …' notes and '(전화문의)' asides; an unmatched '(' left by a split note goes."""
    out = []
    for x in restore_lines(raw):
        if x.startswith("※"):
            continue
        x = ASK_PAREN.sub(" ", x)
        x = re.sub(r"\s*\(\s*$", "", x).strip(" ,")
        if x:
            out.append(squash_ws(x))
    return out


def is_closed_word(text: str | None) -> bool:
    t = squash_ws(text)
    return bool(t) and not OPENISH.search(t) and not is_open_value(t)


def _b(main="", sub="", more=False, closed=False) -> dict:
    """A brief value: the main part, its condition or second part (sub), more=True when the facts hold more."""
    return {"main": squash_ws(main), "sub": squash_ws(sub), "more": bool(more), "closed": bool(closed)}


def fmt_time(t: str) -> str:
    h, mm = t.split(":")
    return f"{int(h):02d}:{mm}"


def _closed_part(text: str) -> str:
    """The closed-day words of a split value without the label; a bracket goes only when it is left unpaired by the
    split ('연중무휴(명절제외)' keeps its closing bracket, '(매주 월요일' loses the stray opening one)."""
    t = squash_ws(text).strip(" ,")
    if t.startswith("(") and t.endswith(")") and t.count("(") == t.count(")") == 1:
        t = t[1:-1]
    while t.endswith(")") and t.count(")") > t.count("("):
        t = t[:-1].rstrip(" ,")
    while t.startswith("(") and t.count("(") > t.count(")"):
        t = t[1:].lstrip(" ,")
    return re.sub(r"^휴(?:무|관)일?\s*[:：]\s*", "", t)


# The last entry (operator-forwarded evaluation 2026-10-18: it belongs in the first summary whenever the data gives
# it). A time ('입장마감 17:30') belongs to the range it follows; when the tile would leave it behind '외' (a second
# season takes the sub line, or another secondary does), it is folded into that range as the source writes it
# ('3~10월 09:00–18:00(입장마감 17:30)'). A rule without a time ('※ 20분 전 입장마감', '폐관 30분 전까지 입장') is
# added to the sub line in its own words.
LAST_ENTRY = re.compile(r"입장\s*(?:마감|종료)|마지막\s*입장")
LAST_RULE = re.compile(r"[^,/※()]*\d+\s*분\s*전[^,/※()]*입장[^,/※()]*|[^,/※()]*입장[^,/※()]*?\d+\s*분\s*전[^,/※()]*")


def brief_hours(raw, base: str = "") -> tuple[dict | None, str]:
    """(hours brief, closed-day text found inside the hours value). The first primary range is the main part, the
    next range (or a secondary one) the sub, more when anything else is left; the last entry always shows
    (LAST_ENTRY, LAST_RULE)."""
    b, closed = _brief_hours(raw, base)
    if b and not LAST_ENTRY.search(f"{b['main']} {b['sub']}"):
        # a last entry stated as a rule, in a '※' note or a clause of its own: its words on the sub line
        rule = next((squash_ws(m.group(0)) for x in restore_lines(raw) for m in [LAST_RULE.search(x)] if m), "")
        if rule:
            b["sub"] = f"{b['sub']} · {rule}" if b["sub"] else rule
    return b, closed


def shows_last_entry(b: dict | None) -> bool:
    """A brief hours value names a last entry: a time ('입장마감 17:30') or a rule ('폐관 30분 전까지 입장')."""
    t = f"{(b or {}).get('main', '')} {(b or {}).get('sub', '')}"
    return bool(LAST_ENTRY.search(t) or LAST_RULE.search(t))


def last_entry_part(raw, base: str = "") -> str:
    """The last entry an hours value gives, in a few words for the sub line of another value's tile (slot_value
    'hours': a source that adds to the stored hours, relation 'also'): each range's last entry after its season, the
    months in brackets left out ('하절기(입장마감 17:30), 동절기(입장마감 16:30)'), a lone one as written ('입장마감
    20:30'), else a rule in its own words ('20분 전 입장마감'); '' when the value gives none."""
    b, _ = brief_hours(raw, base)
    out = []
    for x in ((b["main"], b["sub"]) if b else ()):
        m = re.fullmatch(r"(.*?)\s*\d{2}:\d{2}–\d{2}:\d{2}\s*\(([^()]*)\)", x)
        if m and LAST_ENTRY.search(m.group(2)):
            season = squash_ws(re.sub(r"\([^()]*\)", "", m.group(1)))
            out.append(f"{season}({m.group(2)})" if season else m.group(2))
        elif LAST_ENTRY.search(x) and not RANGE_FIND.search(x):
            out.append(x)
    if out:
        return ", ".join(out)
    return next((squash_ws(m.group(0)) for x in restore_lines(raw) for m in [LAST_RULE.search(x)] if m), "")


def _brief_hours(raw, base: str = "") -> tuple[dict | None, str]:
    lines = clean_lines(raw)
    if not lines:
        return None, ""
    group, prim, sec, closed, other, notes = "", [], [], [], [], 0
    last_of: dict[int, str] = {}   # primary range index → the last entry time that follows it ('입장마감 17:30')
    for line in lines:
        m = re.fullmatch(r"\[([^\]]+)\]", line)
        if m:
            group = squash_ws(m.group(1))
            continue
        for part in re.split(r"\s*/\s*|,\s*(?=휴무일)|\s+-\s+(?=[가-힣\[])|^-\s*", line):
            part = (part or "").strip(" ,-")
            if not part:
                continue
            found = list(RANGE_FIND.finditer(part))
            if not found:
                if OPEN_HOURS.search(part) and not CLOSED_HINT.search(part.replace("휴무일", "")):
                    other.append(part)
                elif not re.search(TIME, part) and (CLOSED_HINT.search(part) or OPENISH.search(part)):
                    closed.append(_closed_part(part))
                elif re.search(TIME, part) and SECONDARY.search(part):
                    sec.append(dash_times(squash_ws(part.strip("()"))))
                else:
                    other.append(part)
                continue
            pos, cur = 0, None
            for k, m in enumerate(found):
                cond = squash_ws(part[pos:m.start()]).strip(" :,-()[]")
                if cond in BASE_WORDS or cond == base:
                    cond = ""
                head = " ".join(x for x in ((group if not cond or k == 0 else ""), cond) if x)
                text = f"{head} {fmt_time(m.group(1))}–{fmt_time(m.group(2))}".strip()
                if SECONDARY.search(cond):   # a break inside the range: the last entry after it is still the range's
                    sec.append(text)
                else:
                    prim.append(text)
                    cur = len(prim) - 1
                pos = m.end()
            tail = part[pos:].strip(" ,")
            if tail:
                for par in re.findall(r"\(([^()]*)\)", tail):
                    par = squash_ws(par)
                    if not par:
                        continue
                    if not re.search(TIME, par) and (CLOSED_HINT.search(par) or OPENISH.search(par)):
                        closed.append(_closed_part(par))
                    elif re.search(TIME, par):
                        sec.append(dash_times(par))
                        if cur is not None and LAST_ENTRY.search(par):
                            last_of.setdefault(cur, sec[-1])
                    else:
                        notes += 1
                rest = re.sub(r"\([^()]*\)", "", tail).strip(" ,")
                if rest:
                    if not re.search(TIME, rest) and (CLOSED_HINT.search(rest) or OPENISH.search(rest)):
                        closed.append(_closed_part(rest))
                    else:
                        notes += 1
    if not prim and sec:
        prim, sec = sec[:1], sec[1:]
    if prim:
        rest = prim[1:] + sec
        hidden = [x for x in sec if LAST_ENTRY.search(x) and x != rest[0]]
        if hidden and last_of:
            # the last entry would be left behind '외': each one joins the range it follows
            prim = [f"{p}({last_of[i]})" if i in last_of else p for i, p in enumerate(prim)]
            joined = set(last_of.values())
            sec = [x for x in sec if x not in joined]
            rest = prim[1:] + sec
        late = next((x for x in rest[1:] if x in sec and LAST_ENTRY.search(x)), None)
        if late and not LAST_ENTRY.search(f"{prim[0]} {rest[0]}"):
            # a last entry of no range of its own ('… / 입장마감 17:30'): it takes the sub line
            rest = [late] + [x for x in rest if x is not late]
        return _b(prim[0], rest[0] if rest else "", len(rest) > 1 or notes > 0 or bool(other)), ", ".join(closed)
    if other:
        return _b(other[0], "", len(other) > 1), ", ".join(closed)
    return None, ", ".join(closed)


def brief_closed(text: str | None) -> dict | None:
    """A closed-day text: whole when short (or a sentence); else the weekly clause(s) as main, the rest as sub."""
    t = squash_ws(text).strip(" ,/")
    if not t:
        return None
    if len(t) <= 18 or re.search(r"(며|고),", t) or t.endswith("다."):
        return _b(t, closed=is_closed_word(t))
    clauses = [c.strip() for c in re.split(r"\s*[,/]\s*|\s+및\s+", t) if c.strip()]
    weekly = [c for c in clauses if WEEKLY.search(c)]
    main = ", ".join(weekly) if weekly else clauses[0]
    others = [c for c in clauses if c not in weekly] if weekly else clauses[1:]
    sub, more = ", ".join(others), False
    if len(sub) > 20:
        sub, more = "", True
    return _b(main, sub, more, is_closed_word(main))


def brief_fee(raw) -> dict | None:
    """'무료' / the first row of a price table ('성인 3,000원') with its group as sub ('박물관 통합권'), more when the
    table has more rows; a value that only says to call reads '전화 문의' (the facts table keeps the sentence)."""
    lines = clean_lines(raw)
    if not lines:
        return None
    text = " ".join(lines)
    if ASK_NOTE.search(text) and not re.search(r"\d", text):
        return _b("전화 문의")
    if text in ("무료", "없음"):
        return _b(text)
    gr = fee_grid(text)
    if gr:
        r = gr["rows"][0]
        return _b(f"{r['who']} {r['a']}원", gr["cols"][0], True)
    fees = fee_table("\n".join(lines))
    if fees:
        rows = [(g["label"], x) for g in fees["groups"] for x in g["rows"]]
        g0, r0 = rows[0]
        sub = g0 or (f"{rows[1][1]['who']} {rows[1][1]['price']}" if len(rows) > 1 else "")
        return _b(f"{r0['who']} {r0['price']}".strip(), sub, len(rows) > (1 if g0 else 2))
    if len(text) <= 28:
        return _b(text)
    m = FIRST_ADULT.search(text)
    if m:
        return _b(f"성인 {m.group(1)}", "", True)
    m = FIRST_PRICE.search(text)
    if m:
        return _b(f"{m.group(1)} {m.group(2)}", "", True)
    return _b(text)


# A place a combined ticket also opens (data/<region>/tickets.json, pipeline/tickets.py; operator-forwarded evaluation
# 2026-10-18: 근대역사박물관's body gave the single-site 성인 2,000원 while its first screen showed the 박물관 통합권's
# 3,000원 alone, as if it were the only price). Its fee tile shows both side by side: the visitor's own first price as
# the place's table lists it — the table's combined-ticket groups and its residents' groups taken out ('[○○시민]
# 성인 1,000원' first in the table is not the visitor's price; review 2026-10-18) — ('개별 성인 2,000원'), then the same
# visitor's price of the narrowest ticket that opens it, from that ticket's table, under the ticket's name and the same
# visitor's word ('박물관 통합권 성인 3,000원'; what it opens is the facts card's, in our words: ticket_rows). Each value
# keeps its own source: the ticket's provider joins the providers under the tiles and its table is a row of the facts
# card.
COMBINED = "통합권"
TICKET_CATS = (("성인", "성인"), ("청소년", "청소년·군인"), ("군인", "청소년·군인"), ("어린이", "어린이"))
VISITOR_GROUP = re.compile(r"개별|개인|일반|타지역|관외")   # a group that is the visitor's own price: no condition shown
PRICE_ROW = re.compile(r"^[-•]?\s*([가-힣][가-힣·,/ ]*?)\s*:?\s*([\d,]+)\s*원$")


def fee_groups(raw) -> list[dict]:
    """A fee table's groups in order: {label (the '[…]' line, '' before the first), lines}."""
    groups = [{"label": "", "lines": []}]
    for x in clean_lines(raw):
        m = re.fullmatch(r"\[([^\]]+)\]", x)
        if m:
            groups.append({"label": squash_ws(m.group(1)), "lines": []})
        else:
            groups[-1]["lines"].append(x)
    return [g for g in groups if g["label"] or g["lines"]]


def own_fee_row(raw) -> dict | None:
    """The visitor's first price row of a place's own fee table: the first group that is neither a combined ticket
    ('[박물관 통합권] …') nor a residents' price ('[○○시민] …', tickets.is_resident): {who, price, group, index} — ('성인', '2,000원',
    '타지역', 1), index = the group's place among the table's '[…]' groups (None for a table without them, for the
    other versions to find the same group: en_site.own_fee_row); None when no such price row is left (free, a sentence,
    a call, residents only)."""
    groups = fee_groups(raw)
    heads = [g for g in groups if g["label"]]
    for g in groups:
        if COMBINED in g["label"] or tickets.is_resident(g["label"]):
            continue
        lines = ([f"[{g['label']}]"] if g["label"] else []) + g["lines"]
        text = " ".join(g["lines"])
        idx = next((i for i, h in enumerate(heads) if h is g), None)
        gr = fee_grid(text)
        if gr:
            r = gr["rows"][0]
            return {"who": squash_ws(r["who"]), "price": f"{r['a']}원", "group": squash_ws(g["label"] or gr["cols"][0]),
                    "index": idx}
        fees = fee_table("\n".join(lines))
        fg = next((x for x in (fees or {}).get("groups") or [] if x["rows"]), None)
        if fg:
            r = fg["rows"][0]
            return {"who": squash_ws(r["who"]), "price": squash_ws(r["price"]), "group": squash_ws(fg["label"]),
                    "index": idx}
        m = FIRST_ADULT.search(text)
        if m:
            return {"who": "성인", "price": m.group(1), "group": squash_ws(g["label"]), "index": idx}
    return None


def same_ticket_group(e: dict, t: dict) -> str:
    """The label of the place's own fee group that is ticket t's table ('박물관 통합권', '통합권'): a combined-ticket
    group whose every price row is the ticket's individual price for that visitor; '' when the table has none."""
    want = (t.get("prices") or {}).get("개인") or {}
    for g in fee_groups((e.get("facts") or {}).get("usefee")):
        if COMBINED not in g["label"]:
            continue
        got: dict[str, int] = {}
        for m in (PRICE_ROW.match(x) for x in g["lines"]):
            if m:
                cat = next((c for w, c in TICKET_CATS if squash_ws(m.group(1)).startswith(w)), "")
                got.setdefault(cat, int(m.group(2).replace(",", "")))
        if got and set(got) == set(want) and all(got[c] == want[c][0] for c in want):
            return g["label"]
    return ""


def fee_with_ticket(e: dict, raw) -> dict | None:
    """The fee tile of a place a combined ticket also opens (COMBINED above): {main '개별 성인 2,000원', sub '박물관
    통합권 성인 3,000원', more, ticket {id, name, price, cat, provider, provider_full, date, url}}; None when the place has
    no ticket, no visitor's price row of its own, or a visitor the ticket's table has no price for. Both are the
    visitor's prices (a resident's table first in the place's table is passed over: own_fee_row)."""
    tks = e.get("_tickets") or []
    own = own_fee_row(raw) if tks else None
    if not own:
        return None
    t = tks[0]
    cat = next((c for w, c in TICKET_CATS if own["who"].startswith(w)), "")
    pair = ((t.get("prices") or {}).get("개인") or {}).get(cat)
    if not pair:
        return None
    cond = own["group"] if own["group"] and not VISITOR_GROUP.search(own["group"]) else ""
    src = t.get("src") or {}
    # the ticket's price names its visitor as the place's own does ('박물관 통합권 성인 3,000원'; the other versions:
    # en_site.fee_pair 'Museum combined ticket: Adults 3,000 won')
    return {"main": squash_ws(f"개별 {cond} {own['who']} {own['price']}"),
            "sub": squash_ws(f"{t['name']} {own['who']} {tickets.won(pair[0])}"), "more": True, "closed": False,
            "ticket": {"id": t["id"], "name": t["name"], "price": pair[0], "cat": cat,
                       "provider": slot_provider(src.get("provider")), "provider_full": squash_ws(src.get("provider")),
                       "date": squash_ws(src.get("checked_at")), "url": web_url(src.get("url"))}}


def brief_parking(raw) -> dict | None:
    t = parking_text(raw)
    if not t:
        return None
    if len(t) <= 26:
        return _b(t)
    for sep in (" 요금", " / ", ", "):
        if sep in t:
            a, b = t.split(sep, 1)
            b = (sep.strip(" /,") + " " + b).strip() if sep == " 요금" else b
            return _b(a, b if len(b) <= 20 else "", len(b) > 20)
    return _b(t)


MENU_SEP = re.compile(r"\s*,(?!(?<=\d,)\d{3}(?!\d))\s*")   # a comma between items, never a thousands separator


def brief_menu(raw) -> dict | None:
    # '한우떡갈비(200g)24,000원, 돼지떡갈비…' -> '한우떡갈비(200g)24,000원' + 외 (a price is never cut at its comma)
    items = [squash_ws(x) for x in MENU_SEP.split(str(raw or "")) if squash_ws(x)]
    if not items:
        return None
    main, k = items[0], 1
    while k < len(items) and len(main) + 2 + len(items[k]) <= 18:
        main += ", " + items[k]
        k += 1
    return _b(main, "", k < len(items))


def brief_plain(raw) -> dict | None:
    lines = clean_lines(raw)
    return _b(" ".join(lines)) if lines else None


SLOT_LABEL = {"hours": "이용시간", "closed": "쉬는 날", "fee": "요금", "parking": "주차", "tel": "전화", "menu": "대표 메뉴",
              "checkin": "체크인", "checkout": "체크아웃", "rooms": "객실"}
HERO_SLOTS = {"attraction": ("hours", "closed", "fee", "parking", "tel"),
              "food": ("hours", "closed", "menu", "parking", "tel"),
              "stay": ("checkin", "checkout", "parking", "rooms", "tel")}
KF_CARD_SLOTS = {"attraction": ("hours", "closed", "fee"), "food": ("menu", "hours", "closed"),
                 "stay": ("checkin", "parking", "rooms")}
KF_LIST_COLS = {"attraction": (("hours", "이용시간"), ("closed", "쉬는 날"), ("fee", "요금"), ("parking", "주차")),
                "stay": (("checkin", "체크인"), ("checkout", "체크아웃"), ("parking", "주차"), ("tel", "전화")),
                "food": (("menu", "대표 메뉴"), ("hours", "영업시간"), ("closed", "쉬는 날"), ("parking", "주차"))}


def slot_provider(p: str | None) -> str:
    """The short provider name a slot shows beside a contested value: 한국관광공사 · <the city> · 공식 홈페이지."""
    p = squash_ws(p)
    if "홈페이지" in p or "누리집" in p:
        return "공식 홈페이지"
    return short_provider(p)


def _slot_label(e: dict, name: str) -> str:
    return "영업시간" if name == "hours" and e.get("kind") == "food" else SLOT_LABEL[name]


def slot_value(e: dict, name: str) -> dict | None:
    """One slot of one place: {key, src_key, label, main, sub, more, closed, conflict, vals [{provider, main, sub,
    closed, more}], provider, date (확인일 of the source), tel (digits, tel slot)}; None when the source has no value.
    vals is set only for a real source conflict (both values shown, each with its provider)."""
    f = e.get("facts") or {}
    kind = e.get("kind")
    label = _slot_label(e, name)

    def pack(key, b, alts_b=None):
        if not b or not b["main"]:
            return None
        src = src_of(e, key)
        out = {"key": name, "src_key": key, "label": label, **b, "conflict": False, "vals": [],
               "provider": slot_provider(src["provider"]), "date": src["checked_at"]}
        if alts_b:
            out["conflict"] = True
            out["vals"] = [{"provider": out["provider"], **b}] + alts_b
        return out

    def alt_briefs(key, fn, keep=None):
        out = []
        for a in contested(e, key):
            b = fn(a.get("value") or "") or _b()
            if b["main"] and (keep is None or keep(b)):
                out.append({"provider": slot_provider(a.get("provider")), **b})
        return out

    if name == "tel":
        tel_text, tel = settled_phone(e)
        if tel:
            key = "infocenter" if PHONE.search(str(f.get("infocenter") or "")) else "reservation"
            src = src_of(e, key)
            return {"key": "tel", "src_key": key, "label": label, "main": tel_text, "sub": "", "more": False,
                    "closed": False, "conflict": False, "vals": [], "tel": tel,
                    "provider": slot_provider(src["provider"]), "date": src["checked_at"]}
        # sources give the number differently: both numbers with their providers, no call link picked
        for key in ("infocenter", "reservation"):
            alts = contested(e, key)
            own = first_phone(f.get(key))[0]
            if alts and own:
                b = _b(own)
                vals = [{"provider": slot_provider(a.get("provider")), **_b(first_phone(a.get("value"))[0])}
                        for a in alts]
                vals = [v for v in vals if v["main"] and v["main"] != own]
                out = pack(key, b, vals or None)
                if out:  # the same number under two wordings is no conflict: it stays a call link
                    out["tel"] = "" if out["conflict"] else tel_digits(own)
                return out
        return None
    if name in ("hours", "closed"):
        hkey = "usetime_restdate" if kind == "food" and f.get("usetime_restdate") else "usetime"
        base = BASE_LABEL.get(hkey, "")
        hb, hclosed = brief_hours(f.get(hkey), base) if f.get(hkey) else (None, "")
        if name == "hours":
            alt_b = alt_briefs(hkey, lambda v: brief_hours(v, base)[0])
            if alt_b and hb and all(x["main"] == hb["main"] and x["sub"] == hb["sub"] for x in alt_b):
                alt_b = []
            out = pack(hkey, hb, alt_b or None)
            shown = (out["vals"][0] if out["conflict"] else out) if out else None
            if shown and not shows_last_entry(shown):
                # the last entry belongs in the first summary (evaluation 2026-10-18): a source that adds to the stored
                # hours (relation 'also', the facts card's '또는 …') and gives one puts it on the sub line, as
                # brief_hours does for a rule of the value's own; its provider joins those under the tiles
                for i, a in enumerate(a for a in alternatives(e, hkey) if a.get("relation") == "also"):
                    extra = last_entry_part(a["value"], base)
                    if extra:   # index: the other versions' 'also' values in the same order (en_site slot)
                        shown["sub"] = f"{shown['sub']} · {extra}" if shown["sub"] else extra
                        out["also"] = {"index": i, "provider": slot_provider(a.get("provider")),
                                       "provider_full": squash_ws(a.get("provider")),
                                       "date": squash_ws(a.get("checked_at"))}
                        break
            return out
        # closed day: its own field first, else the part found inside the hours value
        if f.get("restdate"):
            cb = brief_closed(" ".join(clean_lines(f["restdate"])))
            alt_b = alt_briefs("restdate", lambda v: brief_closed(" ".join(clean_lines(v))),
                               lambda x: (not cb or x["main"] != cb["main"]) and (not cb or x["closed"] or cb["closed"]))
            return pack("restdate", cb, alt_b or None)
        if hclosed:
            cb = brief_closed(hclosed)
            alt_b = []
            for a in contested(e, hkey):
                _, ac = brief_hours(a.get("value") or "", base)
                acb = brief_closed(ac) if ac else None
                if acb and cb and acb["main"] != cb["main"] and (acb["closed"] or cb["closed"]):
                    alt_b.append({"provider": slot_provider(a.get("provider")), **acb})
            return pack(hkey, cb, alt_b or None)
        return None
    if name == "fee":
        b = brief_fee(f.get("usefee"))
        alt_b = alt_briefs("usefee", brief_fee, lambda x: not b or x["main"] != b["main"])
        # a place a combined ticket also opens: its own price beside the ticket's (fee_with_ticket) — unless the
        # sources give the fee differently, where both of their values are the tile (never one of them settled here)
        both = None if alt_b else fee_with_ticket(e, f.get("usefee"))
        if both:
            out = pack("usefee", {k: v for k, v in both.items() if k != "ticket"})
            if out:
                out["ticket"] = both["ticket"]
            return out
        return pack("usefee", b, alt_b or None)
    if name == "parking":
        if f.get("parking"):
            b = brief_parking(f["parking"])
            return pack("parking", b, alt_briefs("parking", brief_parking, lambda x: not b or x["main"] != b["main"]) or None)
        if f.get("parking_seats") and alias_holds(e, "parking", "parking_seats"):
            # a seat count alone ('30석') is no parking value: the slot stays missing (seats_note under it)
            b = brief_plain(f["parking_seats"])
            out = pack("parking_seats", b, alt_briefs("parking_seats", brief_plain,
                                                      lambda x: not b or x["main"] != b["main"]) or None)
            if out:
                out["label"] = "주차" if parking_seats_half(e) == "parking" else "주차·좌석"
            return out
        if f.get("parkingfee"):
            fee = " ".join(clean_lines(f["parkingfee"]))
            m = re.search(r"(\d+분(?:\s*이내)?)\s*[-:]?\s*(무료|[\d,]+원)", fee)
            b = _b(fee) if len(fee) <= 26 else (_b(f"{m.group(1)} {m.group(2)}", "", True) if m else _b(fee))
            out = pack("parkingfee", b)
            if out:
                out["label"] = "주차 요금"
            return out
        return None
    if name == "menu":
        return pack("menu", brief_menu(f.get("menu")))
    if name in ("checkin", "checkout"):
        return pack(name, brief_plain(f.get(name)))
    if name == "rooms":
        r = squash_ws(f.get("roomcount"))
        return pack("roomcount", _b(f"{r}실" if r.isdigit() else r)) if r else None
    return None


def seats_note(e: dict) -> str:
    """'좌석 30석' under a missing parking cell when the city's '주차 및 좌석수' gives seats only (one source, or every
    source the same); '' otherwise."""
    raw = (e.get("facts") or {}).get("parking_seats")
    if not raw or parking_seats_half(e) != "seats" or contested(e, "parking_seats"):
        return ""
    text, lab = squash_ws(raw), FACT_LABELS["seat"]
    return text if text.startswith(lab) else f"{lab} {text}"


def missing_slot(e: dict, name: str, label: str = "") -> dict:
    return {"key": name, "src_key": "", "label": label or _slot_label(e, name), "main": "",
            "sub": seats_note(e) if name == "parking" else "", "more": False,
            "closed": False, "conflict": False, "vals": [], "provider": "", "date": "", "missing": True}


SLOT_EXTRA = ("ticket", "also")   # a slot's part from another source: {provider, provider_full, date} (slot_value)


def key_facts(e: dict, mode: str = "hero") -> dict:
    """{slots, missing, date, providers, conflict, tel}: the kind's fixed slots in order (HERO_SLOTS for the first
    screen, KF_CARD_SLOTS for cards). Card mode keeps a missing slot in its place ('확인 필요'); hero mode leaves it
    out and lists it once in missing ('확인 필요: …'). date = the earliest 확인일 of the slots shown; tel = (visible
    number, tel: digits) of a settled phone, else ('', '')."""
    kind = e.get("kind") if e.get("kind") in HERO_SLOTS else "attraction"
    names = (HERO_SLOTS if mode == "hero" else KF_CARD_SLOTS)[kind]
    slots, missing = [], []
    for n in names:
        v = slot_value(e, n)
        if v:
            slots.append({**v, "missing": False})
        else:
            missing.append(_slot_label(e, n))
            if mode != "hero":
                slots.append(missing_slot(e, n))
    dates = [d for s in slots for d in (s.get("date"), *((s.get(x) or {}).get("date") for x in SLOT_EXTRA)) if d]
    provs = []
    for s in slots:   # a combined ticket's price beside the place's own fee comes from the ticket's table, a last
        extra = [(s.get(x) or {}).get("provider") for x in SLOT_EXTRA]   # entry from a source that adds to the hours
        for p in [s.get("provider")] + [v["provider"] for v in s.get("vals") or []] + extra:
            if p and p not in provs:
                provs.append(p)
    tel = next((s for s in slots if s["key"] == "tel" and s.get("tel")), None)
    return {"slots": slots, "missing": missing, "date": min(dates) if dates else "", "providers": provs,
            "conflict": any(s.get("conflict") for s in slots), "tel": (tel["main"], tel["tel"]) if tel else ("", "")}


def slot_cell(e: dict, name: str, label: str) -> dict:
    """A list cell = the place's slot (the same brief value the first screen shows), or '확인 필요' (missing)."""
    v = slot_value(e, name)
    if not v:
        return missing_slot(e, name, label)
    return {**v, "label": v["label"] if name == "parking" else label, "missing": False}


def desc_parts(kf: dict) -> list[str]:
    """The first-screen slots as shown ('이용시간 09:00–18:00'), for a meta description's tail; a conflicting slot is
    left out (the page shows both values and the call line), so is the phone."""
    return [f"{s['label']} {s['main']}" for s in kf["slots"] if s["key"] != "tel" and not s.get("conflict") and s.get("main")]


# ----------------------------------------------------------------------------- weekly closures (요일표)
DAY_RX = re.compile(r"(?:(?<![\d가-힣])|(?<=매주))((?:[월화수목금토일]\s*[·,]\s*)*[월화수목금토일])요일")  # '매주목요일' too
PARTIAL_RX = re.compile(r"(첫째|둘째|셋째|넷째|다섯째|\d째|격주|매달|매월)")


def closed_text(e: dict) -> tuple[str, bool]:
    """(closed-day text, contested) for the week grid and closure counts; '' when the source has none."""
    f = e.get("facts") or {}
    for k in ("restdate", "usetime_restdate"):
        raw = f.get(k)
        if not raw:
            continue
        text = squash_ws(raw) if k == "restdate" else split_closed(raw)[1]
        if k == "usetime_restdate" and not text:
            m = CLOSED_SPAN.search(squash_ws(raw)) or re.search(r"연중\s*무휴", squash_ws(raw))
            text = m.group(0).strip(" ,") if m else ""
        if not text:
            continue
        c = contested(e, k)
        if c and k == "usetime_restdate":
            c = [a for a in c if split_closed(a["value"])[1] != text]
        return text, bool(c)
    return "", False


def week_closure(text: str | None) -> dict:
    """Weekly closed days parsed from the source text: {'days': {...}, 'partial': {...}, 'open': bool}.
    Conditional phrases ('월요일이 공휴일이면', '경우 화요일') are not counted."""
    t = squash_ws(text)
    out = {"days": set(), "partial": set(), "open": False}
    if not t:
        return out
    if is_open_value(t) or re.search(r"연중\s*무휴|상시\s*개방|휴무일?\s*[:：]?\s*없음|^무휴", t):
        out["open"] = True
        return out
    for m in DAY_RX.finditer(t):
        after, before = t[m.end():m.end() + 8], t[max(0, m.start() - 12):m.start()]
        if re.match(r"\s*(이|인|가)?\s*(공휴일|법정|휴일)", after) or re.search(r"(경우|이면|다음\s*날|익일|대체)\s*$", before):
            continue
        days = set(re.findall(r"[월화수목금토일]", m.group(1)))
        (out["partial"] if PARTIAL_RX.search(before) else out["days"]).update(days)
    return out


def monday_open(text: str | None) -> bool:
    """The text marks Monday as open: it states weekly closed days (or 연중무휴/상시 개방) and Monday is not
    among them, not even partly ('둘째주 월요일'). A text without closed-day information marks nothing."""
    t = squash_ws(text)
    wc = week_closure(t)
    return weekly_stated(t, wc) and "월" not in wc["days"] and "월" not in wc["partial"] and "월요일" not in t


def weekly_stated(text: str | None, wc: dict | None = None) -> bool:
    """The text says which weekdays are closed: weekly closed days, 연중무휴/상시 개방/휴무일 없음, or closures
    on holidays only. '비정기적 휴무', '전화문의' or a seasonal note say nothing about a weekday."""
    t = squash_ws(text)
    wc = wc or week_closure(t)
    return bool(wc["open"] or wc["days"] or wc["partial"] or re.search(r"명절|설날|추석|공휴일|연휴|설\s*당일", t))


def closed_days(e: dict) -> set:
    """Weekdays this place is closed every week, from uncontested source text only."""
    text, cont = closed_text(e)
    return set() if cont or not text else week_closure(text)["days"]


def week_grid(ents: list[dict]) -> dict | None:
    """Place × 월–일 grid of weekly closures (a guide or course with at least 3 known places)."""
    rows = []
    for t in ents:
        text, cont = closed_text(t)
        wc = week_closure(text)
        stated = bool(text) and weekly_stated(text, wc)  # a text without weekday information is not 'open'
        cells = []
        for d in WEEK:
            if cont or not stated:
                cells.append("na")
            elif d in wc["days"]:
                cells.append("closed")
            elif d in wc["partial"]:
                cells.append("partial")
            else:
                cells.append("")
        rows.append({"e": t, "name": t["name"], "path": t["_path"], "text": text, "contested": cont, "cells": cells,
                     "open": wc["open"], "stated": stated})
    known = [r for r in rows if r["stated"] and not r["contested"]]
    if len(known) < 3:
        return None
    per_day = {d: sum(1 for r in known if r["cells"][i] == "closed") for i, d in enumerate(WEEK)}
    return {"rows": rows, "per_day": per_day, "busiest": max(per_day, key=lambda d: per_day[d]),
            "partial": any("partial" in r["cells"] for r in rows), "na": any(not r["stated"] or r["contested"] for r in rows)}


# ----------------------------------------------------------------------------- photos
LIC = {"KOGL-1": ("공공누리 제1유형", 1), "KOGL-3": ("공공누리 제3유형(변경금지)", 3)}


def small_rendition(url: str) -> str:
    """The provider's own small rendition (TourAPI smallimageurl '…_image3_1.*') of an original '…_image2_1.*'."""
    return url.replace("_image2_1", "_image3_1") if "_image2_1" in url else ""


def load_image_sizes(data_dir: Path) -> dict:
    """data/<region>/image_sizes.json {url: [width, height, bytes]} (tools/image_sizes.py); {} when absent."""
    path = Path(data_dir) / "image_sizes.json"
    try:
        return json.loads(path.read_text("utf-8")) if path.exists() else {}
    except (OSError, ValueError):
        return {}


def photo(im: dict, name: str, sizes: dict) -> dict:
    """A licensed TourAPI photo with its intrinsic size (None when not measured; never guessed), the licence,
    the alt text and the provider's small rendition for thumbnails when measured."""
    size = sizes.get(im["url"]) or [None, None, None]
    w, h, b = (list(size) + [None, None, None])[:3]
    lab, t = LIC[im["license"]]
    small = small_rendition(im["url"])
    th = sizes.get(small) if small else None
    return {"url": im["url"], "w": w, "h": h, "bytes": b, "ar": f"{w}/{h}" if w and h else "", "type": t, "lic": lab,
            "credit": squash_ws(im.get("credit")) or "한국관광공사",
            "alt": im.get("_alt") or squash_ws(im.get("alt")) or name, "name": name,
            "th": {"url": small, "w": th[0], "h": th[1], "bytes": th[2]} if th else None}


def photos(e: dict, sizes: dict) -> list[dict]:
    """Only TourAPI photos under KOGL-1/KOGL-3 (CLAUDE.md 3.4); the city tourism site's photos are never shown."""
    return [photo(i, e["name"], sizes) for i in e.get("_images") or []
            if i.get("source") == "TourAPI" and i.get("license") in LIC]


def thumb(ph: dict | None) -> dict | None:
    """A list row's or card's small picture: the provider's own small copy, else the smallest same-origin derivative
    of a KOGL-1 photo (media.smallest), else the original."""
    if not ph:
        return None
    t = ph.get("th")
    if t:
        return {"url": t["url"], "w": t["w"], "h": t["h"], "alt": ph["alt"], "type": ph["type"]}
    small = media.smallest(ph)
    if small:
        return {"url": small[0], "w": small[1], "h": small[2], "alt": ph["alt"], "type": ph["type"]}
    return {"url": ph["url"], "w": ph["w"], "h": ph["h"], "alt": ph["alt"], "type": ph["type"]}


# ----------------------------------------------------------------------------- State-level preparation
def prepare(S, data_dir: Path) -> None:
    """Computed once per build: type labels, photos with sizes, distinct lines, 권역, twins, course models."""
    S.warnings = getattr(S, "warnings", [])
    S.image_sizes = load_image_sizes(data_dir)
    S.theme_names = {t["slug"]: t["name"] for t in S.themes}
    for e in S.entities:
        e["_type"] = kind_type(e, S.theme_names)
        e["_street"] = street_of(e)
        e["_photos"] = photos(e, S.image_sizes)
        e["_line"] = distinct_line(e.get("summary"))
    media.attach(S)  # ph.avif / ph.webp: same-origin derivatives of KOGL-1 photos (tools/kogl1_media.py)
    assign_regions(S)
    # the places a place page measures straight-line distances to (city.distance_anchors), resolved from the data
    S.dist_anchors = []
    for key in city.current().distance_anchors:
        a = find_place(S, key)
        if a and a.get("_geo"):
            S.dist_anchors.append(a)
        else:
            S.warnings.append(f"거리 기준 장소 없음(좌표 포함): {key} — 장소 페이지의 그 거리 생략")
    # same building, two pages ('X' and '<city> X'): cross-linked by name without the city in front
    C = city.current()
    by_norm = defaultdict(list)
    for e in S.entities:
        by_norm[normalize_name(C.without_city(e["name"]))].append(e)
    for xs in by_norm.values():
        for e in xs:
            e["_twins"] = [x for x in xs if x is not e]
    # two pages for one building by the data (part_of rel same_building, pipeline/relations.py): twins both ways too
    for e in S.entities:
        e["_twins"] += [x for x in e.get("_same") or [] if x not in e["_twins"]]
    S.course_vms = {c["slug"]: course_vm(S, c) for c in S.courses}


def find_place(S, key: str) -> dict | None:
    """A place named in the city's configuration, by slug or else by name (spacing, brackets and the city in front
    ignored: '인천 X' = 'X'); None when the collected data does not have it (or has two such names)."""
    e = S.ent_by_slug.get(key)
    if e:
        return e
    C = city.current()
    want = normalize_name(C.without_city(key))
    hits = [x for x in S.entities if normalize_name(C.without_city(x.get("name", ""))) == want]
    return hits[0] if len(hits) == 1 else None


def assign_regions(S) -> None:
    """e['_district'] (the 구·군 of a 광역시 address), e['_region'] and e['_region_basis'] ('좌표', '읍·면·동',
    '주소' or ''), S.anchors (the nearest_anchor rule's anchor places found in the data), S.region_names (the 권역
    in display order, the leftover labels last). An anchor place missing from the build (or without coordinates) is
    skipped with a warning; with no anchor at all, or no rule, every place is none_label."""
    C = city.current()
    S.anchors = []
    for e in S.entities:
        e["_district"] = C.district_of((e.get("facts") or {}).get("address"), e.get("district") or "")
        e["_region"], e["_region_basis"] = C.none_label, ""
    if C.region_method == "district":
        for e in S.entities:
            r = C.district_region(e["_district"], e.get("_area") or "")
            if r:
                e["_region"], e["_region_basis"] = r, "주소"
        S.region_names = [r.name for r in C.regions] + [C.none_label]
        return
    if C.region_method != "nearest_anchor":
        S.region_names = [C.none_label]
        return
    for r in C.regions:
        a = find_place(S, r.anchor)
        if not (a and a.get("_geo")):
            S.warnings.append(f"권역 기준점 없음(좌표 포함): {r.anchor} — {r.name} 권역 생략")
            continue
        S.anchors.append({"name": r.name, "slug": a["slug"], "place": a["name"], "path": a["_path"], "geo": a["_geo"],
                          "id": "r-" + frag(r.name)})
    far_m = C.far_m
    by_area: dict[str, Counter] = defaultdict(Counter)
    for e in S.entities:
        if e.get("_geo") and S.anchors:
            d = {a["name"]: hav(e["_geo"], a["geo"]) for a in S.anchors}
            best = min(d, key=d.get)
            e["_region"] = best if not far_m or d[best] <= far_m else C.far_label
            e["_region_basis"] = "좌표"
            if e.get("_area") and e["_region"] != C.far_label:
                by_area[e["_area"]][best] += 1
    for e in S.entities:
        if not e.get("_geo"):
            c = by_area.get(e.get("_area") or "")
            if c:
                e["_region"], e["_region_basis"] = c.most_common(1)[0][0], "읍·면·동"
    S.region_names = [a["name"] for a in S.anchors] + ([C.far_label] if far_m else []) + [C.none_label]


# ----------------------------------------------------------------------------- courses
MEAL_RX = re.compile(r"(중식|석식|조식|점심|저녁|점심식사|저녁식사)")
LODGING_RX = re.compile(r"(숙소|숙박)")
ACTIVITY_RX = re.compile(r"^(야경|유람선)")
STOP_KIND_LABELS = {"meal": "식사", "lodging": "숙박", "activity": "일정", "day": "일차"}


def split_course_name(name: str) -> tuple[str, str]:
    """'A코스 | 원도심~섬' -> ('A코스', '원도심~섬'); a name without a code -> ('', name)."""
    m = re.match(r"^\s*(\S*코스)\s*\|\s*(.+)$", name or "")
    return (m.group(1), m.group(2).strip()) if m else ("", squash_ws(name))


def stop_kind(name: str, target) -> str:
    """Course rows that are not places — meals, the night's lodging, activities — are itinerary lines: they
    are not counted as 경유지 and get no distance, board or map search."""
    if target:
        return "place"
    n = squash_ws(name)
    if MEAL_RX.fullmatch(n):
        return "meal"
    if LODGING_RX.fullmatch(n):
        return "lodging"
    if ACTIVITY_RX.match(n):
        return "activity"
    return "place"


MEASURED_SHARE = 0.8  # a course's distance sum is shown only when at least this share of legs is measured


def course_vm(S, c: dict) -> dict:
    """A course: place stops (numbered, coded, with straight-line legs), itinerary separators (meals, lodging,
    activities, and the source's day / option headings '1일차', '2일차(1안)'), totals and the computed lede. The leg
    sum shows only when ≥80% of legs are measured; the band positions follow real leg ratios only when every leg is
    measured, else equal spacing (order only).
    QA 2026-10-15 F09-b/c: no leg exists between two options of a day — the first stop of a '(2안)' block after a
    '(1안)' block is a break (s['brk']: no prev/next across it) — nor into or out of a stop the source marks optional
    ('어청도 (선택사항)': s['optional'], neighbours named, no distance); both stay out of legs, legs_possible and cum.
    A day change keeps its leg (like the 숙소 rows). 'see': a stop that names two places ('○○도,△△도일원') links
    both, with no coordinates and no leg."""
    region = S.site.get("region", "")
    code, title = split_course_name(c["name"])
    letter = code[0] if code and re.match(r"[A-Z]코스", code) else ""
    rows, stops = [], []
    day_now, prev_day = "", ""
    for s in c.get("stops") or []:
        t = S.ent_by_slug.get(s.get("place_slug") or "")
        label = squash_ws(s.get("name") or "")
        kind = stop_kind(label, t)
        day = squash_ws(s.get("day"))
        if day and day != day_now:
            rows.append({"sep": True, "kind": "day", "kind_label": day, "name": "", "note": ""})
            day_now = day
        if kind != "place":
            rows.append({"sep": True, "kind": kind, "kind_label": STOP_KIND_LABELS[kind], "name": label,
                         "note": squash_ws(s.get("note"))})
            continue
        part_of = bool(t) and str(s.get("link_basis", "")).startswith("part_of")
        # a stop inside a place keeps the course's own name for it ('옥돌해변 명품 데크길' in 옥돌해변): the place's name
        # twice in a row read as a mistake (review 2026-10-17); the row says whose place it is and links its page
        name = label if part_of and label else t["name"] if t else label
        i = len(stops) + 1
        short = squash_ws(re.sub(r"\(.*$", "", name)) or name
        st = {"sep": False, "kind": "place", "n": i, "code": f"{letter}{i:02d}" if letter else f"{i:02d}",
              "name": name, "short": short, "paren": squash_ws(name[len(short):]) if "(" in name else "",
              "t": t, "geo": t["_geo"] if t else None, "path": t["_path"] if t else "",
              "part_of": part_of,
              "label": label if label and t and not part_of and normalize_name(label) != normalize_name(t["name"]) else "",
              "note": squash_ws(s.get("note")), "day": day, "optional": bool(s.get("optional")),
              "brk": bool(stops) and "(2안)" in day and "(1안)" in prev_day,
              "see": [{"name": x["name"], "path": x["_path"], "id": x["id"]}
                      for x in (S.ent_by_slug.get(k) for k in s.get("see") or []) if x],
              "guide": _stop_guide(S, s.get("guide")),
              "search": "" if t else f"https://map.naver.com/p/search/{quote(f'{region} {label}'.strip(), safe='')}"}
        prev_day = day
        stops.append(st)
        rows.append(st)
    legs, pairs = [], []
    for a, b in zip(stops, stops[1:]):
        if b["brk"] or a["optional"] or b["optional"]:
            continue
        d = 0.0 if a["t"] is not None and a["t"] is b["t"] else hav(a["geo"], b["geo"])
        a["next_m"], b["prev_m"] = d, d
        legs.append(d)
        pairs.append((a, b))
    for i, s in enumerate(stops):
        s["prev"] = stops[i - 1] if i and not s["brk"] else None
        s["next"] = stops[i + 1] if i + 1 < len(stops) and not stops[i + 1]["brk"] else None
        s.setdefault("prev_m", None)
        s.setdefault("next_m", None)
    measured = [d for d in legs if d is not None]
    complete = len(measured) == len(legs)
    show_total = bool(legs) and len(measured) >= MEASURED_SHARE * len(legs)
    # whose coordinates the measured legs join (TourAPI first): '한국관광공사 TourAPI', or with another provider too
    leg_geo = geo_providers([s["geo"] for a, b in pairs if a["geo"] and b["geo"] for s in (a, b)])
    cum, ok = 0.0, True  # the distance from the start, only while every earlier leg is measured
    for s in stops:
        s["cum"] = cum if ok else None
        if s["next_m"] is None:
            ok = False
        else:
            cum += s["next_m"]
    n = len(stops)
    if complete and n > 1 and sum(measured) > 0:
        pos, x = [0.0], 0.0
        for b in stops[1:]:
            x += b["prev_m"] or 0.0
            pos.append(x)
        xs = [p / pos[-1] for p in pos]
    else:
        xs = [i / max(1, n - 1) for i in range(n)]
    for s, x in zip(stops, xs):
        s["x"] = x
    ys, prev = [], None
    for s in stops:
        v = s["x"] if prev is None else max(s["x"], prev + 0.06)
        ys.append(v)
        prev = v
    for s, v in zip(stops, ys):
        s["y"] = v / (ys[-1] or 1)
    linked = [s["t"] for s in stops if s["t"]]
    by_day = Counter(d for t in {id(t): t for t in linked}.values() for d in closed_days(t))
    closed_note = ""
    if by_day:
        day, cnt = max(by_day.items(), key=lambda kv: (kv[1], -WEEK.index(kv[0])))
        kinds = {t.get("kind") for t in linked if day in closed_days(t)}
        closed_note = f"{day}요일 {'휴관' if kinds == {'attraction'} else '휴무'} {cnt}곳"
    vm = {"c": c, "slug": c["slug"], "path": c["_path"], "code": code, "letter": letter, "title": title,
          "display": course_display(c["name"]), "group": c.get("group") or "", "duration": c.get("duration") or "",
          # seps: the itinerary rows of the source's list (meals, lodging, activities); days: its day headings
          "rows": rows, "stops": stops, "seps": [r for r in rows if r["sep"] and r["kind"] != "day"], "legs": legs,
          "pairs": pairs, "days": [r["kind_label"] for r in rows if r["sep"] and r["kind"] == "day"],
          "taketime": _taketime(c.get("taketime")),
          "transit_guides": [x for x in c.get("transit_guides") or [] if x],
          "total": sum(measured), "measured": len(measured), "legs_possible": len(legs), "complete": complete,
          "show_total": show_total, "measure_note": f"좌표 있는 구간 {len(measured)}/{len(legs)}" if legs else "",
          "geo_providers": leg_geo, "geo_src": "·".join(leg_geo),
          "n_places": n, "linked": len(linked), "geo_n": sum(1 for s in stops if s["geo"]),
          "first": stops[0]["name"] if stops else "", "last": stops[-1]["name"] if stops else "",
          "monday": by_day.get("월", 0), "closed_by_day": dict(by_day), "closed_note": closed_note,
          "orig_url": (c.get("original") or {}).get("source_url") or "",
          "orig_name": (c.get("original") or {}).get("source_name") or (S.site.get("source") or {}).get("name", ""),
          # 예약하기 (pipeline/booking.py): the services of the stops' guides and places, a box under the lede
          "booking": booking.view(booking.course_targets(S, c), "ko"), "bw": LC.BOOK_WORDS["ko"]}
    vm["lede"] = course_lede(c, vm)
    return vm


def _taketime(v) -> dict | None:
    """The one duration a course source gives ('B코스 | … 소요시간 : 12시간'): {value, source_name,
    source_url, checked_at, hours} or None."""
    if not isinstance(v, dict) or not squash_ws(v.get("value")):
        return None
    m = re.fullmatch(r"(\d+)시간", squash_ws(v["value"]))
    return {**v, "value": squash_ws(v["value"]), "hours": int(m.group(1)) if m else None}


def _stop_guide(S, ref) -> dict | None:
    """A guide a course stop points to ('guide-32#h-b2': the island ferry guide on 어청도): {id, frag, label, path}."""
    gid, _, frag = str(ref or "").partition("#")
    g = (getattr(S, "guide_by_id", None) or {}).get(gid) if gid else None
    if not g:
        return None
    return {"id": gid, "frag": frag, "label": squash_ws(g.get("label")) or squash_ws(g.get("title")),
            "path": g["_path"] + (f"#{frag}" if frag else "")}


def course_display(name: str) -> str:
    return course_display_name(name)


def course_lede(c: dict, vm: dict) -> str:
    """Computed lede (summary_auto courses): how many first stops sit within 1km of the start, and the longest
    leg when every leg is measured. A course with a written summary (summary_auto false) keeps it."""
    if not c.get("summary_auto") and squash_ws(c.get("summary")):
        return squash_ws(c["summary"])
    stops = vm["stops"]
    cluster = 1
    if stops and stops[0]["geo"]:
        while cluster < len(stops) and stops[cluster]["geo"] and hav(stops[0]["geo"], stops[cluster]["geo"]) <= 1000:
            cluster += 1
    longest = None
    if vm["complete"] and vm["measured"]:
        i = max(range(len(vm["legs"])), key=lambda j: vm["legs"][j] or 0)
        if vm["legs"][i]:
            a, b = vm["pairs"][i]
            longest = f"가장 긴 구간은 {a['name']}에서 {b['name']}까지 직선 {dist(vm['legs'][i])}"
    near = f"처음 {cluster}곳은 출발지에서 직선 1km 안에 모여 있" if cluster > 2 else ""
    if near and longest:
        return f"{near}고, {longest}입니다."
    if near:
        return f"{near}습니다."
    if longest:
        return f"{longest}입니다."
    if stops:
        return f"경유지 {len(stops)}곳은 {stops[0]['name']}에서 출발해 {stops[-1]['name']}에서 끝납니다."
    return squash_ws(c.get("summary"))


def course_stop_details(vm: dict) -> dict:
    """Per-stop status, key facts (card mode: ui.kfrows), photo, distinct line, 동 and type for the course page
    (computed on demand); the course's first_route (카카오맵 길찾기 to the first stop with coordinates: {n, name,
    url}) and map (course_map: the stops with coordinates for the course map, or None)."""
    for s in vm["stops"]:
        t = s["t"]
        s["status"] = status_items(t) if t else []
        s["kf"] = key_facts(t, "card") if t else None
        s["photo"] = t["_photos"][0] if t and t.get("_photos") else None
        s["line"] = t["_line"] if t else ""
        s["dong"] = t["_area"] if t else ""
        s["type"] = t["_type"] if t else ""
    s0 = next((s for s in vm["stops"] if s["geo"]), None)
    # the stop's place ID when tools/kakao_places.py matched one (the route opens that place), else its coordinates
    kid = ((s0["t"] or {}).get("map_ids") or {}).get("kakao_place_id", "") if s0 else ""
    vm["first_route"] = {"n": s0["n"], "name": s0["short"],
                         "url": kakao_route_url(s0["name"], s0["geo"]["lat"], s0["geo"]["lng"], kid)} if s0 else None
    vm["map"] = course_map(vm["stops"])
    return vm


# ----------------------------------------------------------------------------- 차 없이 다니기 (QA 2026-10-15 F09)
LONG_LEG_M = 3000                         # legs longer than this (straight line) are listed first


def move_config() -> dict:
    """The city's '차 없이 다니기' guides (site.json city.course_move): guides (every course, before its own transit
    guides — a car-free day guide), guides_after (after them — a getting-here guide), island_guide (a course whose
    transit guides point at it gets island_route's first and last times)."""
    m = city.current().get("course_move") or {}
    return {"guides": list(m.get("guides") or []), "guides_after": list(m.get("guides_after") or []),
            "island_guide": str(m.get("island_guide") or ""), "island_route": str(m.get("island_route") or ""),
            "timetable_guide": str(m.get("timetable_guide") or "")}


def course_move(S, vm: dict) -> dict | None:
    """The course page's '차 없이 다니기' block, from data the site already holds — never a mode, a time or 'walkable'
    of our own (CLAUDE.md 3.1):
    - bus: per place stop (each place once) its nearest bus stops from nearby.json (공공데이터포털 정류장 좌표; route
      numbers only when the timetable names the stop — an empty list is not 'no bus'), the first and last stops first
      (lead), the rest after (rest);
    - legs: every measured leg between two places (straight line ≥ 10 m) with a public-transport directions link that
      lets the map app compute the route and its times (Korean: Kakao /link/by/traffic, coordinates only), longer than
      LONG_LEG_M first; a leg into a stop with a guide (the island ferry) carries that guide;
    - routes: the city bus timetable's reference-stop first and last times (transit.json) of the routes the bus rows
      name, and the island route when the course's transit_guides point at the island guide (move_config); it first;
    - guides: the city's car-free guides, the course's transit_guides ('guide-NN#h-bN'), the city's getting-here guide;
    - missing: what no source gives (per-leg travel time; the total time unless the source states one).
    None for a course with no place stop."""
    stops = vm["stops"]
    if not stops:
        return None
    nb = getattr(S, "nearby", None) or {}
    rows, seen = [], set()
    for s in stops:
        t = s["t"]
        if not t or not t.get("_geo") or t["id"] in seen:
            continue
        bus = [{"name": squash_ws(x["stop_name"]), "m": int(x["meters"]), "routes": list(x.get("routes") or []),
                "routes_text": "·".join(x.get("routes") or [])} for x in (nb.get(t["id"]) or {}).get("bus") or []]
        if bus:
            seen.add(t["id"])
            rows.append({"n": s["n"], "s": s, "id": t["id"], "bus": bus})
    ends = {rows[0]["n"], rows[-1]["n"]} if rows else set()   # where the course starts and ends (of the stops with data)
    lead, rest = [r for r in rows if r["n"] in ends], [r for r in rows if r["n"] not in ends]
    legs = []
    for a, b in vm.get("pairs") or []:
        d = a.get("next_m")
        if d is None or d < 10 or not (a["geo"] and b["geo"]):
            continue
        legs.append({"a": a, "b": b, "d": d, "long": d > LONG_LEG_M, "guide": b.get("guide"),
                     "url": kakao_transit_url(a["name"], a["geo"]["lat"], a["geo"]["lng"],
                                              b["name"], b["geo"]["lat"], b["geo"]["lng"])})
    legs.sort(key=lambda x: not x["long"])
    transit = getattr(S, "transit", None) or {}
    held = {r["no"]: r for r in transit.get("routes") or []}
    nums = {n for r in rows for b in r["bus"] for n in b["routes"]}
    mc = move_config()
    island = mc["island_route"]
    if island and any(g.split("#")[0] == mc["island_guide"] for g in vm.get("transit_guides") or []):
        nums.add(island)
    routes = sorted((held[n] for n in nums if n in held), key=lambda r: (r["no"] != island, r["no"]))
    gids = mc["guides"] + list(vm.get("transit_guides") or []) + mc["guides_after"]
    guides, seen_g = [], set()
    for ref in gids:
        g = _stop_guide(S, ref)
        if g and g["path"] not in seen_g:
            seen_g.add(g["path"])
            guides.append(g)
    missing = ["구간별 이동 시간"] + ([] if vm.get("taketime") else ["총 소요 시간"])
    keys = (["stops"] if rows else []) + (["timetable"] if any(b["routes"] for r in rows for b in r["bus"]) else [])
    meta = (getattr(S, "nearby_meta", None) or {}).get("bus") or {}
    tt = transit.get("_meta") or {}
    tel = ((tt.get("contact") or {}).get("tel") or "") if routes else ""
    return {"lead": lead, "rest": rest, "legs": legs, "routes": [route_parts(r) for r in routes], "guides": guides,
            "missing": missing, "sources": [access_sources()[k] for k in keys], "source_keys": keys, "tt": tt,
            "tel": tel, "tel_html": tel_markup(tel) if tel else "", "bus_radius": meta.get("radius_m") or 500,
            "island_route": island}


def route_parts(r: dict) -> dict:
    """One timetable route (transit.json) as the course block prints it: the weekday rows by direction, and the
    Sat/Sun/holiday rows only where they differ ('same': every weekend value equals the weekday one)."""
    times = r.get("times") or []
    same = all(t["weekend"] == t["weekday"] and t["weekend_n"] == t["weekday_n"] for t in times)
    # a row whose departures are not one even run ('pattern': '06:10, 09:10~20:10' at one stop) shows the source's
    # pattern instead of the first~last range, so no hourly bus is implied in the gap
    shown = lambda t: {**t, "weekday": t.get("pattern") or t["weekday"],
                       "weekend": t["pattern"] if t.get("pattern") and t["weekend"] == t["weekday"] else t["weekend"]}
    return {"no": r["no"], "out": [shown(t) for t in times if t["dir"] == "out"],
            "back": [shown(t) for t in times if t["dir"] == "back"], "same": same, "alts": [t for t in times if t.get("alt")]}


MAP_MIN_SHARE = 0.5  # a course map is drawn only when at least half of its stops have coordinates


def map_name(s: dict) -> str:
    """A stop's name as its board in the stop list prints it: the short name, then the bracket after one space
    ('OO동일본식가옥 (히로쓰가옥)'); English stops have no short name and keep theirs."""
    if s.get("short"):
        return f"{s['short']} {s['paren']}" if s.get("paren") else s["short"]
    return s["name"]


def course_map(stops: list[dict]) -> dict | None:
    """The course map (ui.mapfig {'course': points}; map.js draws it with Kakao Maps): the stops that
    have coordinates, numbered as in the stop list (n), joined in course order by straight lines. None when fewer
    than half of the stops (or fewer than two) have coordinates — the numbered stop list is then the answer, and a
    few dots joined by long lines would only mislead. Each point is named as the stop list names it (map_name).
    An optional stop (s['optional'], '어청도 (선택사항)') is not drawn nor counted for that share; a break between two
    options of a day (s['brk']) starts a new line: points after it carry 'seg' (1, 2 …; map.js draws one line per seg)."""
    pts, seg = [], 0
    for s in stops:
        if s.get("brk"):
            seg += 1
        if s.get("geo") and not s.get("optional"):
            pts.append((s, seg))
    if len(pts) < 2 or len(pts) < MAP_MIN_SHARE * sum(1 for s in stops if not s.get("optional")):
        return None
    return {"points": [{"lat": s["geo"]["lat"], "lng": s["geo"]["lng"], "name": map_name(s), "url": s.get("path") or "",
                        "n": s["n"], **({"seg": k} if k else {})} for s, k in pts],
            "n_geo": len(pts), "n_all": len(stops), "n_opt": sum(1 for s in stops if s.get("geo") and s.get("optional"))}


def course_groups_vm(S) -> list[dict]:
    """Courses index groups in the order 당일 / 1박 2일 / 2박 3일 / the rest ({title, id, courses})."""
    by_group: dict[str, list] = {}
    for c in S.courses:
        by_group.setdefault(c.get("duration") or c.get("group") or "여행 코스", []).append(S.course_vms[c["slug"]])
    order = ["당일", "1박 2일", "2박 3일"]
    groups = sorted(by_group.items(), key=lambda kv: (order.index(kv[0]) if kv[0] in order else 9, kv[0]))
    return [{"title": t, "id": "g-" + frag(t), "courses": cvs} for t, cvs in groups]


# ----------------------------------------------------------------------------- place page
PRACTICAL = {"attraction": ("usetime", "restdate", "usefee", "parking", "parkingfee", "spendtime", "infocenter", "address"),
             "stay": ("checkin", "checkout", "parking", "roomcount", "infocenter", "reservation", "address"),
             "food": ("usetime_restdate", "usetime", "restdate", "menu", "parking_seats", "parking", "infocenter",
                      "reservation", "address")}
MORE = ("openperiod", "discount", "usefee", "roomtype", "cooking", "subfacility", "treatmenu", "seat", "packing",
        "creditcard", "expguide", "filming", "reservationurl", "homepage", "spendtime")
FIT = ("babycarriage", "pet", "kidsfacility", "expagerange", "useseason", "accessible_parking", "wheelchair",
       "accessible_toilet", "accessible_route")


def city_line(S, e: dict) -> str:
    """P1-2: '<province> <시> <동>' or '<광역시> <구> <동>' (the 구·군 is kept: it is location information); without a
    동 in the address, the road name."""
    return city.current().place_where(e.get("_district") or "", e.get("_area") or e.get("_road") or "")


def route_links(links: list[dict]) -> dict:
    """CLAUDE.md 7: three in front — 카카오맵 길찾기 (the one filled button; '카카오맵에서 찾기' without
    coordinates or a Kakao place ID), 네이버 지도, 카카오맵 (the place's own Kakao page when its ID is known,
    pipeline/maplinks.py) — the rest folded under '다른 지도'. Exact links come first; labels
    lose '(검색)', which the template states once (search_note)."""
    def clean(l):
        return {**l, "label": re.sub(r"\s*\(검색\)$", "", l["label"]),
                "track": "route_click" if l["role"] == "route" else "map_click"}
    by = {l["key"]: l for l in links}
    route_l, kakao, naver = by.get("kakao_route"), by.get("kakao"), by.get("naver")
    primary = route_l or ({**kakao, "label": "카카오맵에서 찾기"} if kakao else None)
    front = [l for l in (naver, kakao if route_l else None) if l]
    used = {id(x) for x in front} | {id(route_l), id(kakao)}
    rest = [l for l in links if id(l) not in used]
    return {"primary": clean(primary) if primary else None, "front": [clean(l) for l in front],
            "rest": [clean(l) for l in rest],
            "search_note": [clean(l)["label"] for l in ([primary] if primary and not primary["precise"] else []) + front
                            if not l["precise"]],
            "map_links": [clean(l) for l in links if l["role"] == "map"],
            "route_links": [clean(l) for l in links if l["role"] == "route"]}


# ----------------------------------------------------------------------------- nearby public parking and bus stops
# data/<region>/parking_lots.json (the city's public lots, 전국주차장정보표준데이터) and nearby.json ({place_id: {parking:
# [{lot_id, meters}], bus: [{stop_name, meters, routes}]}). Shown on the place page below the first screen, after the
# map: about public lots and stops near the place, never the place's own parking (its facts row stays as it is) and
# never counted by the index criteria (schema.index_groups reads facts only). pipeline.validate.access_problems checks
# every shown row against the two files.
LOT_TYPE = {"노외": "노외주차장", "노상": "노상주차장"}
# what the block's source line names (provider names only, no dates — owner, 2026-10-09): the national datasets here,
# the city's own (its parking ordinance, its tourism site, its bus-stop list and timetable) from site.json
# city.access_sources; a key the city does not name reads as the generic dataset name
ACCESS_BASE = {"standard": "공공데이터포털 전국주차장정보표준데이터", "tourapi": "한국관광공사 TourAPI",
               "ordinance": "주차장 조례", "stops": "공공데이터포털 버스정류장현황", "timetable": "시내버스 시간표"}


def access_sources() -> dict:
    C = city.current()
    return {**ACCESS_BASE, "city_tour": C.official["name"], **(C.get("access_sources") or {})}


def fee_source(v: dict) -> str:
    """A parking fee version's source: the city's name for that key (site.json city.fee_sources), else the version's
    own source_name."""
    return (city.current().get("fee_sources") or {}).get(v.get("source")) or v.get("source_name", "")


def tidy_brackets(text: str | None) -> str:
    """Spaces just inside brackets or before a comma dropped ('(신창동 )' -> '(신창동)'); nothing else changes."""
    return re.sub(r"\s+,", ",", re.sub(r"\s+\)", ")", re.sub(r"\(\s+", "(", squash_ws(text))))


def lot_address(raw: str | None) -> str:
    """'<city> 구영7길 69 (신창동 )' -> '구영7길 69 (신창동)': the city prefix goes (the page is in the city; a 구·군
    after it stays) and the bracket spaces (tidy_brackets); every word and number stays as the source wrote it (a
    spacing slip such as '동 국사길19' is kept — such lots show their 지번 too)."""
    return tidy_brackets(city.current().strip_prefix(raw))


def won(n) -> str:
    return f"{int(n):,}원"


def free_span(minutes) -> str:
    m = int(minutes)
    return f"{m // 60}시간" if m % 60 == 0 else f"{m}분"


def fee_text(v: dict) -> str:
    """One fee version of a paid lot as one line: every amount the source gives, small and large cars."""
    s, l = v.get("small") or {}, v.get("large") or {}
    parts = [f"{free_span(v['free_minutes'])}까지 무료"] if v.get("free_minutes") else []
    if s.get("to_1h30") is not None:
        parts.append(f"1시간 30분까지 소형 {won(s['to_1h30'])}·대형 {won(l['to_1h30'])}")
    if s.get("per_30min") is not None:
        parts.append(f"이후 30분마다 소형 {won(s['per_30min'])}·대형 {won(l['per_30min'])}")
    if s.get("day_over_5h") is not None:
        parts.append(f"5시간 넘으면 1일 소형 {won(s['day_over_5h'])}·대형 {won(l['day_over_5h'])}")
    return " · ".join(parts)


def lot_row(S, lot: dict, meters: int, place: str) -> dict:
    """One '근처 공영주차장' row: name, type, address (+ 지번 when the road address is blank or has a source spacing slip),
    straight-line metres, spaces (both values when the city tourism site gives another), 무료/유료 and, for a paid lot, each
    fee version with its source, '방문 전 전화 확인' when the sources differ, and the city's paid-parking desk."""
    road = lot_address(lot.get("address"))
    jibun = lot_address(lot.get("address_jibun"))
    alt = lot.get("alt") or {}
    alt_spaces = (alt.get("spaces") or {}).get("value")
    fee = lot.get("fee") or {}
    fees = [{"src": fee_source(v), "text": fee_text(v), "key": v["source"]}
            for v in fee.get("versions") or []]
    differ = (["면수"] if alt_spaces is not None and alt_spaces != lot.get("spaces") else []) + \
        (["요금"] if fee.get("differs") else [])
    desk = next((c for c in S.parking_contacts if c.get("phone") == fee.get("contact")), None) if fee else None
    contact = ""
    if desk:
        loc = city.current().locality   # '<시> 교통국 교통행정과 교통기획계' -> '<시> 교통행정과 교통기획계'
        unit = re.sub(rf"^{re.escape(loc)}\s+\S+국\s+", f"{loc} ", squash_ws(desk.get("unit"))) if loc else squash_ws(desk.get("unit"))
        contact = f"{unit} {desk['phone']}"
    geo = lot.get("lat") is not None and lot.get("lng") is not None
    return {
        "id": lot["id"], "name": tidy_brackets(lot["name"]), "type": LOT_TYPE.get(lot.get("type"), lot.get("type") or ""),
        "addr": road or jibun, "jibun": jibun if road and lot.get("address_note") else "",
        "m": int(meters), "spaces": lot.get("spaces"), "paid": lot.get("paid") or "",
        "alt_name": squash_ws((alt.get("name") or {}).get("value")), "alt_spaces": alt_spaces,
        "alt_src": access_sources()["city_tour"] if alt else "",
        "fees": fees, "confirm": bool(differ), "differ": "·".join(differ), "contact": contact,
        "contact_html": tel_markup(contact, place) if contact else "",
        "map": f"https://map.kakao.com/link/map/{quote(lot['name'], safe='')},{lot['lat']},{lot['lng']}" if geo else "",
    }


def access_vm(S, e: dict) -> dict | None:
    """The place page's '근처 주차·버스' block, or None (no coordinates, no entry, or nothing within the radius)."""
    entry = (getattr(S, "nearby", None) or {}).get(e.get("id"))
    if not (e.get("_geo") and entry):
        return None
    lots = []
    for x in entry.get("parking") or []:
        lot = S.parking_lots.get(x.get("lot_id"))
        if lot is None:
            S.warnings.append(f"근처 주차장 없음: {e['id']} → {x.get('lot_id')} (parking_lots.json)")
            continue
        lots.append(lot_row(S, lot, x["meters"], e["id"]))
    stops = [{"name": squash_ws(s["stop_name"]), "m": int(s["meters"]), "routes": list(s.get("routes") or []),
              "routes_text": "·".join(s.get("routes") or [])} for s in entry.get("bus") or []]
    if not (lots or stops):
        return None
    used = []
    if lots:
        used.append("standard")
    if any(l["fees"] for l in lots):
        used.append("ordinance")
    if any(f["key"] == "tourapi" for l in lots for f in l["fees"]):
        used.append("tourapi")
    if any(l["alt_src"] for l in lots):
        used.append("city_tour")
    if stops:
        used.append("stops")
    if any(s["routes"] for s in stops):
        used.append("timetable")
    meta = getattr(S, "nearby_meta", None) or {}
    names = access_sources()
    return {"lots": lots, "stops": stops, "sources": [names[k] for k in used],
            "radius": (meta.get("parking") or {}).get("radius_m") or 500,
            "bus_radius": (meta.get("bus") or {}).get("radius_m") or 500}


# ----------------------------------------------------------------------------- 주변·함께 가기 (templates/_near.html.j2)
# the course segments through a place, the nearby rows with one stepped straight-line scale per page, the guide and
# event cards. Words: locales.NEAR_WORDS. Every distance is a straight line between stored coordinates.
NEAR_GLYPH = {"attraction": "pin", "stay": "bed", "food": "bowl"}
NEAR_TRACK = {"stay": "stay_click", "food": "food_click"}
NEAR_STEPS = (100, 250, 500, 1000, 2000)


def same_shape(w, h, w2, h2, tol: float = 0.02) -> bool:
    """Two sizes with the same width-to-height ratio (within tol): a small copy that kept its original's shape."""
    return bool(w and h and w2 and h2) and abs((w2 / h2) / (w / h) - 1) <= tol


def small_thumb(ph: dict | None) -> dict | None:
    """A nearby row's picture: the provider's small copy when measured and of the original's shape (the provider
    squeezes some 940×705 or 940×470 originals into 300×200 copies — a distorted KOGL-3 photo is an altered one, and a
    squeezed KOGL-1 one looks wrong even cropped), else the smallest same-origin derivative of a KOGL-1 photo
    (media.smallest), else None (the row shows its kind icon) — never the 300–500 KB original."""
    if not ph:
        return None
    t = ph.get("th")
    if t and same_shape(ph.get("w"), ph.get("h"), t.get("w"), t.get("h")):
        return {"url": t["url"], "w": t["w"], "h": t["h"], "alt": ph.get("alt", ""), "type": ph["type"],
                "lic": ph.get("lic", "")}
    small = media.smallest(ph)
    if small:
        return {"url": small[0], "w": small[1], "h": small[2], "alt": ph.get("alt", ""), "type": ph["type"],
                "lic": ph.get("lic", "")}
    return None


def photo_credits(rows) -> list[str]:
    """The licences of the rows' pictures, once each, KOGL-1 before KOGL-3 (the same order on every page)."""
    return [lic for _, lic in sorted({(r["photo"]["type"], r["photo"]["lic"]) for r in rows if r.get("photo")})]


def near_scale(ms, radius=None) -> int:
    """The page's one bar scale: the first step at or above the farthest row (100 · 250 · 500 · 1000 · 2000 m), else
    the nearby radius."""
    top = max(ms, default=0)
    return next((s for s in NEAR_STEPS if s >= top), radius or 2000)


def near_fill(m, scale: int) -> float:
    """A row's bar length as a share of the page scale (0 under 10 m: '같은 좌표')."""
    if not m or m < 10 or not scale:
        return 0
    return round(min(float(m) / scale, 1), 3)


def one_value(v: dict | None) -> dict | None:
    """A slot in a one-line row: the value, or {label, varies} when two sources give it differently — the row reads
    '<label> 출처마다 다름' (NEAR_WORDS varies; never one value picked, CLAUDE.md 3.2) and the place's page shows both."""
    if not v or v.get("skip"):
        return None
    return {"label": v["label"], "varies": True} if v.get("conflict") else v


def near_row(S, t: dict | None, n: dict | None = None) -> dict:
    """One row of the chapter: a nearby place (n: its nearby entry, t: its page or None) or a twin / related place
    (n None: no distance). photo: its own first TourAPI photo, small copy only; icon: the kind glyph; closed: its weekly
    closed day (not stays); fact: a stay's check-in. A value two sources give differently: {label, varies} (one_value)."""
    if n is not None:
        kind = n.get("kind")
        lab = re.sub(r"^관광명소 > ", "", n.get("type_label") or KIND_LABELS.get(kind, ""))
        lab = STAY_TYPE.get(lab, lab)
        m = n.get("distance_m")
        row = {"name": n["name"], "href": t["_path"] if t else n.get("href", ""), "m": m or 0,
               "d": dist(m) if m is not None else "", "track": n.get("track") or NEAR_TRACK.get(kind, "nearby_click"),
               "type": (t["_type"] or KIND_LABELS.get(t["kind"], "")) if t else lab}
    else:
        kind = t.get("kind")
        row = {"name": t["name"], "href": t["_path"], "m": None, "d": None,
               "track": NEAR_TRACK.get(kind, "nearby_click"), "type": t["_type"] or KIND_LABELS.get(kind, "")}
    cl = slot_value(t, "closed") if t and t.get("kind") != "stay" else None
    fact = slot_value(t, "checkin") if t and t.get("kind") == "stay" else None
    return {**row, "internal": bool(t), "kind": kind, "geo": t["_geo"] if t else None,
            "closed": one_value(cl), "fact": one_value(fact),
            "photo": small_thumb(t["_photos"][0]) if t and t.get("_photos") else None,
            "icon": (t.get("_visual") or ("", "pin"))[1] if t else NEAR_GLYPH.get(kind, "pin")}


def route_segs(boards: list[dict], dist_fn, name_fn) -> list[dict]:
    """The official courses through a place as segments: boards [{display, path, stops, at}] (stops: the course's
    place stops in order, at: the indexes of this place's stops — a course may pass it more than once) grouped by the
    same neighbours at the same straight-line distances — {prev, next: {name, path, d, same} | None, courses:
    [{display, path, n, N, p}]} (p: the position in the course, order only; same: under 10 m, d is then '같은 좌표').
    Each visit is one board: consecutive stops at this place (C코스 은파호수공원야경 → 은파호수공원) are one visit,
    its neighbours the stops around them and n its first stop; a later visit (B코스 장자도 6 · 8 · 13) is another.
    Most courses first, then first appearance; every visit lands in exactly one group.
    A break between two options of a day (s['brk'], present.course_vm) has no neighbour across it and never joins a
    run: that side reads 'branch' (prev_branch / next_branch; NEAR_WORDS 'branch'), not the course's start or end."""
    key = lambda x: None if x is None else (("t", id(x["t"])) if x.get("t") else ("s", x.get("short") or x.get("name")))
    end = lambda x, m: None if x is None else {"name": name_fn(x), "path": x.get("path") or "", "d": dist_fn(m),
                                               "same": m is not None and float(m) < 10}
    groups: dict = {}
    for b in boards:
        stops = b["stops"]
        runs: list[list[int]] = []
        for k in sorted(b["at"] if b.get("at") is not None else [b["i"]]):
            if runs and k == runs[-1][1] + 1 and not stops[k].get("brk"):
                runs[-1][1] = k
            else:
                runs.append([k, k])
        N = len(stops)
        for i, j in runs:
            pb, nb = i > 0 and bool(stops[i].get("brk")), j + 1 < N and bool(stops[j + 1].get("brk"))
            prev = stops[i - 1] if i > 0 and not pb else None
            nxt = stops[j + 1] if j + 1 < N and not nb else None
            pm, nm = stops[i].get("prev_m") if prev else None, stops[j].get("next_m") if nxt else None
            k = (key(prev), dist_fn(pm) if prev else None, key(nxt), dist_fn(nm) if nxt else None, pb, nb)
            g = groups.setdefault(k, {"prev": end(prev, pm), "next": end(nxt, nm), "prev_branch": pb,
                                      "next_branch": nb, "courses": []})
            g["courses"].append({"display": b["display"], "path": b["path"], "n": i + 1, "N": N,
                                 "p": round(i / (N - 1), 3) if N > 1 else 0})
    return sorted(groups.values(), key=lambda g: -len(g["courses"]))


def card_range(r: dict, today: str) -> str:
    """An event card's dates (event_row's range) with the year in front when the edition starts in another year
    ('2025. 10. 30.(목)–11. 2.(일)' seen in 2026): a past edition never reads as this year's."""
    rng, start = r["range"], r["start"]
    if not rng or not start or "period" in r["contested"] or start[:4] == str(today)[:4]:
        return rng
    return f"{start[:4]}. {rng}"


def relation_vm(S, e: dict) -> tuple[list[dict], list[dict]]:
    """The place's relation lines and parts rows (pipeline/relations.py; words: NEAR_WORDS part_of / same_building /
    parts). Lines: [{rel, word ('속한 곳: {name}'), places [{name, path}]}] — an inside child names its parent, a
    same-building page its partners (both ways, the same words). Parts: the places inside this one as nearby rows
    (near_row), with the straight line between the two coordinates when both have them."""
    w = LC.NEAR_WORDS["ko"]
    lines = []
    parent = e.get("_parent")
    if parent is not None and e.get("_rel") == "inside":
        lines.append({"rel": "inside", "word": w["part_of"], "places": [{"name": parent["name"], "path": parent["_path"]}]})
    same = e.get("_same") or []
    if same:
        lines.append({"rel": "same_building", "word": w["same_building"],
                      "places": [{"name": x["name"], "path": x["_path"]} for x in same]})
    parts = []
    for c in e.get("_parts") or []:
        r = near_row(S, c)
        m = hav(e.get("_geo"), c.get("_geo"))
        if m is not None:
            r["m"], r["d"] = m, dist(m)
        parts.append(r)
    return lines, parts


def place_vm(S, e: dict, ctx: dict) -> dict:
    """Everything the redesigned place page prints (built on entity_ctx; no template logic)."""
    kind = ctx["kind"]
    facts = e.get("facts") or {}
    tel_text, tel = settled_phone(e)
    notes = Notes()
    # the combined tickets that open the place right after its own 요금 (ticket_rows), their notes numbered in that
    # order; the call number stays on the first conflict row of the card
    keys = PRACTICAL[kind]
    cut = keys.index("usefee") + 1 if "usefee" in keys else len(keys)
    practical = fact_rows(e, keys[:cut], notes, (tel_text, tel))
    trows = ticket_rows(e, notes)
    if any(r["same"] for r in trows):   # a ticket row points to the group of the 요금 row that is its table
        next(r for r in practical if r["key"] == "usefee")["anchor"] = FEE_ANCHOR
    practical += trows
    practical += fact_rows(e, keys[cut:], notes, ("", "") if any(r["tel"] for r in practical) else (tel_text, tel))
    shown = {k for r in practical for k in r["keys"]}
    rest_keys = [k for k in FACT_LABELS if k not in shown and k not in MORE and k not in FIT and k not in PRACTICAL[kind]]
    more = fact_rows(e, [k for k in MORE if k not in shown] + rest_keys, notes, (tel_text, tel))
    fit = fact_rows(e, FIT, notes, (tel_text, tel))
    all_rows = practical + more + fit
    missing = [m for m in ctx["missing"] if not (m == FACT_LABELS["parking"] and facts.get("parkingfee"))]
    rooms = squash_ws(facts.get("roomcount"))
    ask = []
    if kind == "stay" and (any(w in e["_type"] for w in SMALL_STAY) or (rooms.isdigit() and int(rooms) <= SMALL_STAY_ROOMS)):
        ask = [a for a in STAY_ASK if not (a == "반려동물 동반" and facts.get("pet"))]
    status = status_items(e, full=True)
    ss = sentences(e.get("summary"))
    links = route_links(ctx["links"])
    near = []
    for n in ctx["nearby_sights"] + ctx["nearby_biz"]:
        t = S.ent_by_slug.get(n.get("internal_slug") or "") or S.ent_by_cid.get(str(n.get("contentid")))
        near.append(near_row(S, t, n))
    near.sort(key=lambda x: x["m"])
    # one stepped straight-line scale for the page (both groups), its end value printed under the rows
    scale = near_scale([r["m"] for r in near], (ctx["nearby_source"] or {}).get("radius_m"))
    for r in near:
        r["f"] = near_fill(r["m"], scale)
    anchors = []
    if e["_geo"]:
        for a in getattr(S, "dist_anchors", None) or []:
            if a is not e and a["_geo"]:
                m = hav(e["_geo"], a["_geo"])
                anchors.append({"name": a["name"], "path": a["_path"], "m": m, "d": dist(m), "geo": a["_geo"]})
        anchors = sorted(anchors, key=lambda x: x["m"])[:3]
    place_points = None
    if e["_geo"]:
        place_points = {
            "self": {"lat": e["_geo"]["lat"], "lng": e["_geo"]["lng"], "name": e["name"]},
            "near": [{"lat": n["geo"]["lat"], "lng": n["geo"]["lng"], "name": n["name"], "d": n["d"] if n["m"] else "",
                      "url": n["href"], "kind": n["kind"]} for n in near if n["geo"]],
            "anchors": [{"lat": a["geo"]["lat"], "lng": a["geo"]["lng"], "name": a["name"],
                         "label": f"{a['name']} 직선 {a['d']}"} for a in anchors if a["m"] <= 3000]}
    boards = []
    for c in e["_courses"]:
        cv = S.course_vms.get(c["slug"])
        s = next((s for s in (cv or {}).get("stops", []) if s["t"] is e), None)
        if s:
            boards.append({"cv": cv, "s": s})
    # every visit of every course (route_segs: consecutive stops here are one visit, a later one is another)
    segs = route_segs([{"display": b["cv"]["display"], "path": b["cv"]["path"], "stops": b["cv"]["stops"],
                        "at": [k for k, x in enumerate(b["cv"]["stops"]) if x["t"] is e]} for b in boards], dist,
                      lambda x: x["t"]["name"] if x.get("t") else x["short"])
    guide_cards = [{"label": squash_ws(g.get("label")) if squash_ws(g.get("label")) != squash_ws(g.get("title")) else "",
                    "title": squash_ws(g.get("title")), "path": g["_path"]} for g in ctx["guides"]]
    from . import build as B
    event_cards = [{"name": sr["name"], "path": sr["_path"], "range": card_range(event_row(sr["newest"]), S.today),
                    "past": B.event_last_day(sr["newest"]) < S.today} for sr in ctx["events"]]
    twins = e.get("_twins") or []
    twin_rows = [{**near_row(S, t), "track": ""} for t in twins]
    near_hrefs = {r["href"] for r in near}
    rel_rows = [near_row(S, x) for x in ctx["related"] if x not in twins and x["_path"] not in near_hrefs]
    relation, parts = relation_vm(S, e)
    photo_lics = photo_credits(near + twin_rows + rel_rows + parts)
    kicker = [(KIND_LABELS[kind], LIST_PATH[kind])]
    if e["_type"]:
        kicker.append((e["_type"], f"{LIST_PATH[kind]}?type={quote(e['_type'])}"))
    for t in ctx["themes"]:
        if t["name"] not in (lab for lab, _ in kicker):  # a type named like its theme ('골목과 문화') once
            kicker.append((t["name"], f"/themes/{t['slug']}/"))
    orig = ctx["orig"]
    labels = ctx["src_labels"]
    default_src = orig.get("source_name") or city.current().official["name"]
    dn = ChapterNotes(labels, default_src)
    details = [{"heading": squash_ws(d.get("heading")), "text": squash_ws(d.get("text")),
                "html": tel_markup(squash_ws(d.get("text"))), "source": squash_ws(d.get("source")),
                "n": dn.ref(d.get("source"))} for d in e.get("details") or [] if squash_ws(d.get("text"))]
    fq = ChapterNotes(labels, default_src)
    faqs = [{"q": f["q"], "a": f["a"], "html": tel_markup(squash_ws(f["a"])), "source": squash_ws(f.get("source")),
             "n": fq.ref(f.get("source"))} for f in ctx["faqs"]]
    area_same = {"attraction": ctx["area_sights"], "stay": ctx["area_stays"], "food": ctx["area_food"]}[kind]
    official = e.get("official") or {}
    n_facts = len([r for r in practical if r["key"] != "address"])
    lead = e["_photos"][0] if e["_photos"] else None
    return {
        # Apple first screen: the kind's five key facts as spec tiles (ui.kf / ui.kfnote), the lead photo by licence
        # (hero_k1: a KOGL-1 product shot, cropped 3:2; hero_k3: whole, desktop only — phones get thumbs, the
        # provider's small renditions, so a 400–660KB original never becomes the mobile LCP)
        "kf": key_facts(e, "hero"), "hero_k1": lead if lead and lead["type"] == 1 else None,
        "hero_k3": lead if lead and lead["type"] != 1 else None,
        "thumbs": [{"url": p["th"]["url"], "w": p["th"]["w"], "h": p["th"]["h"], "alt": p["alt"], "type": p["type"]}
                   for p in e["_photos"][:6] if p.get("th") and p["th"].get("w")],
        "e": e, "kind": kind, "kind_label": KIND_LABELS[kind], "name": e["name"], "list_path": LIST_PATH[kind],
        "type": e["_type"], "region": e["_region"], "dong": e["_area"], "city": city_line(S, e), "kicker": kicker,
        "where": city.current().place_short(e.get("_district") or "", e["_area"] or ""),   # '<시> (<구·군>) <동>'
        "alt_names": ctx["alt_names"], "status": status,
        # official designations (schema.designations): chips under the answer, the '지정' row of the facts card
        "designations": designations(e),
        "lede": ss[0] if ss else "", "story": ss[1:],
        "practical": practical, "more": more, "fit": fit, "notes": notes.items, "missing": missing, "ask": ask,
        "conflicts": [r for r in all_rows if r["conflict"]], "tel": tel, "tel_text": tel_text,
        **links, "precise": bool(e["_geo"]),
        "photos": e["_photos"], "geo": e["_geo"], "place_points": place_points, "anchors": anchors,
        "access": access_vm(S, e),
        "near_sights": [n for n in near if n["kind"] == "attraction"],
        "near_biz": [n for n in near if n["kind"] in ("stay", "food")],
        "nearby_source": ctx["nearby_source"], "boards": boards, "near_scale": scale, "route_segs": segs,
        # whose point this is: the map caption's '위치: …' (the nearby note prints nearby_source.provider, which
        # tools/tourapi_bulk.compute_nearby writes from every point it used; validate.nearby_provenance_problems)
        "geo_src": geo_provider(e["_geo"]) if e["_geo"] else "",
        "guide_cards": guide_cards, "event_cards": event_cards, "twin_rows": twin_rows, "rel_rows": rel_rows,
        # places that belong together (pipeline/relations.py): the line under the name, the parts list of a parent
        "relation": relation, "parts": parts,
        "photo_lics": photo_lics, "nw": LC.NEAR_WORDS["ko"],
        # 예약하기 (pipeline/booking.py): the official booking pages, a row under the route row on the first screen
        "booking": booking.view(booking.place_targets(S, e), "ko"), "bw": LC.BOOK_WORDS["ko"],
        "guides": ctx["guides"], "events": ctx["events"], "twins": e.get("_twins") or [],
        "area_same": area_same, "area_label": ctx["area_label"],
        "faq_vm": faqs, "faq_notes": fq.items, "details": details, "detail_notes": dn.items,
        "videos": [v for v in ctx["media"].get("videos") or [] if v.get("youtube_id")],
        "facts_checked": ctx["facts_checked"],
        "orig": orig, "orig_url": orig.get("source_url") or official.get("source_url") or "",
        "visitkorea": official.get("visitkorea_url", ""),
        "tourapi_id": str((e.get("tourapi") or {}).get("contentid") or ""),
        "compact": not e["_photos"] and n_facts <= 2,
    }


def designation_sources(ds: list[dict]) -> list[dict]:
    """The lists behind shown designations, once each: {name, url, checked_at, labels} (a list page's source line)."""
    out: list[dict] = []
    for d in ds:
        key = (d["source_name"], d["url"], d["checked_at"])
        hit = next((x for x in out if (x["name"], x["url"], x["checked_at"]) == key), None)
        if hit:
            hit["labels"].append(d["short"])
        else:
            out.append({"name": d["source_name"], "url": d["url"], "checked_at": d["checked_at"], "labels": [d["short"]]})
    return out


# ----------------------------------------------------------------------------- lists
LIST_CFG = {
    "attraction": {"title": "관광지", "cols": [("usetime", "이용시간"), ("restdate", "쉬는 날"), ("usefee", "요금"), ("parking", "주차")],
                   "check": ("free", "요금 무료")},
    "stay": {"title": "숙소", "cols": [("checkin", "체크인"), ("checkout", "체크아웃"), ("parking", "주차"), ("tel", "문의")],
             "check": ("checkin", "체크인 시간 있음")},
    "food": {"title": "음식점", "cols": [("menu", "대표 메뉴"), ("usetime_restdate", "영업시간·정기휴일"), ("parking_seats", "주차·좌석"), ("tel", "문의")],
             "check": ("open_mon", "월요일 영업 표기")},
}
ASK_WORDS = re.compile(r"^\s*전화\s*문의\s*$")
CELL_MAX = 48


def cell(e: dict, key: str) -> dict:
    """A list cell shows the whole value (≤48 characters, no '[group]') or a pointer to the place page (P1-7);
    missing=True ('—') when the source has none. A contested value shows no side: the flag and the link only
    (CLAUDE.md 3.2). Closed days carry class closed."""
    f = e.get("facts") or {}
    more = Markup(f'<a class="more" href="{escape(e["_path"])}#h-facts">장소 페이지에서 확인</a>')
    if key == "tel":
        if contested(e, "infocenter") or contested(e, "reservation"):
            return {"html": Markup('<span class="flag">출처마다 다름</span> ') + more, "text": "출처마다 다름",
                    "missing": False, "contested": True}
        t, n = settled_phone(e)
        return {"html": Markup(f'<a class="tel" href="tel:{n}" data-track="tel_click">{escape(t)}</a>') if t else "", "text": t, "missing": not t}
    composed = False
    if key == "usetime_restdate" and not f.get(key):
        if not (f.get("usetime") or f.get("restdate")):
            return {"html": "", "text": "", "missing": True}
        composed = True
    elif key == "parking_seats" and not f.get(key):
        if not f.get("parking"):
            return {"html": "", "text": "", "missing": True}
        key = "parking"
    raw = f.get(key) or ""
    if not composed and not raw:
        return {"html": "", "text": "", "missing": True}
    keys = ("usetime", "restdate") if composed else (key,)
    if any(contested(e, k) for k in keys):
        return {"html": Markup('<span class="flag">출처마다 다름</span> ') + more, "text": "출처마다 다름", "missing": False,
                "contested": True}
    if composed:
        lines = [re.sub(r"^-\s+", "", x) for x in display_value("usetime", f.get("usetime")).split("\n")] \
            if f.get("usetime") else []
        closed = display_value("restdate", f.get("restdate")).replace("\n", " ")
        if sum(len(x) for x in lines) + len(closed) > CELL_MAX or len(lines) > 2 or any(x.startswith("[") for x in lines):
            return {"html": more, "text": "", "missing": False, "more": True}
        html = Markup("<br>").join(escape(x) for x in lines)
        if closed:
            cl = Markup('<span class="closed">') + escape(closed) + Markup("</span>") if not is_open_value(closed) else escape(closed)
            html = html + (Markup("<br>") if lines else Markup("")) + cl
        return {"html": html, "text": " ".join(lines + [closed]).strip(), "missing": False}
    if ASK_WORDS.match(str(raw)):
        return {"html": escape("전화 문의"), "text": "전화 문의", "missing": False}
    lines = [re.sub(r"^-\s+", "", x) for x in display_value(key, raw).split("\n")]  # a cell drops list dashes
    if sum(len(x) for x in lines) > CELL_MAX or len(lines) > 3 or any(x.startswith("[") for x in lines):
        return {"html": more, "text": "", "missing": False, "more": True}
    text = " ".join(lines)
    if key == "restdate":
        html = Markup('<span class="closed">') + escape(text) + Markup("</span>") if not is_open_value(text) else escape(text)
    elif key == "usetime_restdate":
        html = Markup("<br>").join(mark_closed(x) for x in lines)
    else:
        html = Markup("<br>").join(escape(x) for x in lines)
    return {"html": html, "text": text, "missing": False}


# Place cards: the same key values in the same slots on every card of a kind (owner feedback 2026-10-08).
CARD_SLOTS = {"attraction": (("usetime", "이용시간"), ("restdate", "쉬는 날"), ("usefee", "요금")),
              "food": (("menu", "대표 메뉴"), ("usetime_restdate", "영업시간")),
              "stay": (("checkin", "체크인"), ("parking", "주차"))}


def card_vm(e: dict, photo: dict | None = None, mode: str = "card") -> dict:
    """A place card (ui.card / ui.place_card): name, path, type and 동 (meta = 'type · 동'), the distinct line, the
    photo (the given one, else the first licensed TourAPI photo; None: the card shows a type icon), kf = the kind's
    key facts in card mode (key_facts: 3 slots in fixed order, '확인 필요' in place), web = a stay's own homepage.
    slots: the round-2 card cells (cell(): the whole value ≤48 characters, a pointer when longer)."""
    kind = e.get("kind") if e.get("kind") in CARD_SLOTS else "attraction"
    meta = " · ".join(x for x in (e.get("_type") or KIND_LABELS.get(kind, ""), e.get("_area") or "") if x)
    photos_ = e.get("_photos") or []
    if photo is None and photos_:
        photo = photos_[0]
    slots = []
    for k, lab in CARD_SLOTS[kind]:
        c = {"key": k, "label": lab, **cell(e, k)}
        # the whole card already links to the place: a pointer or a conflict flag is text here, not a second link
        if c.get("contested"):
            c["html"] = Markup('<span class="flag">출처마다 다름</span> <span class="more">장소 페이지에서 확인</span>')
        elif c.get("more"):
            c["html"] = Markup('<span class="more">장소 페이지에서 확인</span>')
        slots.append(c)
    web = web_url((e.get("facts") or {}).get("homepage")) if kind == "stay" else ""
    return {"e": e, "id": e.get("id", ""), "kind": kind, "name": e["name"], "path": e.get("_path", ""), "meta": meta,
            "type": e.get("_type") or KIND_LABELS.get(kind, ""), "dong": e.get("_area") or "",
            "line": e.get("_line") or "", "photo": photo, "slots": slots, "kf": key_facts(e, mode), "web": web}


def list_vm(S, kind: str, theme: dict | None = None) -> dict:
    """A list page (or a theme list): records grouped by 권역, filters, map points. Within a group: records
    that answer more columns first, then 가나다 (Latin and digits after)."""
    from . import build as B
    cfg = LIST_CFG[kind]
    ents = [e for e in S.lists[kind] if not theme or theme["slug"] in (e.get("themes") or [])]
    items = []
    for i, e in enumerate(ents):
        f = e.get("facts") or {}
        cells = [{"key": k, "label": lab, **cell(e, k)} for k, lab in cfg["cols"]]
        web = web_url(f.get("homepage") or "")
        if web and (B._url_key(web) in S.shared_homepages or city.current().official_url(web)):
            web = ""
        rest = f"{squash_ws(f.get('restdate'))} {squash_ws(f.get('usetime_restdate'))}".strip()
        # '월요일 영업 표기': every source's text states its closed days (or 연중무휴) and Monday is not one
        rest_all = [rest] + [a["value"] for k in ("restdate", "usetime_restdate") for a in contested(e, k)]
        tags = [t for t in (e["_type"], e["_street"]) if t]
        flags = {"free": squash_ws(f.get("usefee")) == "무료" and not contested(e, "usefee"),
                 "checkin": bool(f.get("checkin")), "open_mon": all(monday_open(t) for t in rest_all)}
        ds = designations(e)
        items.append({"i": i, "e": e, "name": e["name"], "path": e["_path"], "type": e["_type"], "street": e["_street"],
                      "dz": ds[0] if ds else None,
                      "dong": e["_area"], "region": e["_region"], "themes": e.get("themes") or [], "tags": tags,
                      "cells": cells, "slots": [slot_cell(e, k, lab) for k, lab in KF_LIST_COLS[kind]],
                      "answered": sum(1 for c in cells if not c["missing"]), "web": web,
                      "web_text": web_text(web) if web else "", "photo": thumb(e["_photos"][0]) if e["_photos"] else None,
                      "geo": e["_geo"], "flags": flags, "id": f"r{i}",
                      "rooms": squash_ws(f.get("roomcount")) if kind == "stay" else ""})
    groups = []
    for rname in S.region_names:
        xs = sorted((it for it in items if it["region"] == rname), key=lambda it: (-it["answered"], name_key(it["name"])))
        if xs:
            groups.append({"name": rname, "id": "g-" + frag(rname), "recs": xs})
    tagc = Counter(t for it in items for t in it["tags"])
    regions = Counter(it["region"] for it in items)
    themes = Counter(t for it in items for t in it["themes"])
    points = [{"lat": it["geo"]["lat"], "lng": it["geo"]["lng"], "name": it["name"], "url": it["path"], "id": it["id"],
               "kind": kind, "r": it["region"]} for it in items if it["geo"]]
    ck, clabel = cfg["check"]
    # one chip per record (its first designation): the lists behind the chips shown, with link and 확인일, once
    dz_sources = designation_sources([it["dz"] for it in items if it["dz"]])
    return {"kind": kind, "cfg": cfg, "dz_sources": dz_sources, "slot_cols": KF_LIST_COLS[kind], "title": theme["name"] if theme else cfg["title"],
            "path": f"/themes/{theme['slug']}/" if theme else LIST_PATH[kind], "count": len(items), "groups": groups,
            "types": [(t, n) for t, n in tagc.most_common() if n >= 2],
            "regions": [(r, regions[r]) for r in S.region_names if regions[r]],
            "themes": [(s, S.theme_names.get(s, s), n) for s, n in themes.most_common()] if kind == "attraction" and not theme else [],
            "check": (ck, clabel, sum(1 for it in items if it["flags"][ck])), "points": points, "n_geo": len(points),
            "map_open": len(points) >= 0.3 * max(1, len(items)), "n_photo": sum(1 for it in items if it["photo"]),
            "theme": theme,
            "filters": filter_vm(
                len(items), [(t, t, n) for t, n in tagc.most_common() if n >= 2],
                [(r, r, regions[r]) for r in S.region_names if regions[r]],
                [(s, S.theme_names.get(s, s), n) for s, n in themes.most_common()] if kind == "attraction" and not theme else [],
                (ck, clabel, sum(1 for it in items if it["flags"][ck])), len(points), LC.LIST_WORDS["ko"],
                {"other": f"{theme['name'] if theme else cfg['title']} {{n}}곳"})}


def filter_vm(count: int, types: list, regions: list, themes: list, check: tuple, n_geo: int, words: dict,
              forms: dict) -> dict:
    """The list filter bar (templates/_filters.html.j2) of Korean and every version: chips as (value, label, n) — the
    value is the Korean key every version shares (?type=한식&region=원도심), the label the version's; check =
    (flag, label, n); forms = the count line by plural category ({n}); words = locales.LIST_WORDS[code]. n_off = the
    places of the list without coordinates (the map caption's '지도에 없는 n곳은 목록에서', _filters.off_map).
    widest = the count line's widest filtered forms, one per plural form, {n} and {m} both the whole count (a shown
    count has no more digits, and the line's digits are tabular): the room the desktop keeps for the line."""
    form = forms.get("other") or next(iter(forms.values()), "{n}")
    m = str(count)
    widest = list(dict.fromkeys(f.replace("{n}", m) + words["of"].replace("{m}", m) for f in forms.values()))
    return {"count": count, "types": types, "regions": regions, "themes": themes, "check": check, "n_geo": n_geo,
            "n_off": max(0, count - n_geo), "w": words, "forms": forms, "result": form.replace("{n}", m),
            "widest": widest}


# ----------------------------------------------------------------------------- answers (home, guides index, 404)
KNUM = {"한": 1, "두": 2, "세": 3, "네": 4, "다섯": 5, "여섯": 6, "일곱": 7, "여덟": 8, "아홉": 9, "열": 10}
FIG_RX = re.compile(r"(\d[\d,]*(?:\.\d+)?)\s*(곳|개|편|가지|km|m|회|시간|분|원|실|명|대)")
BARE_UNITS = {"곳", "개", "편", "가지", "km", "m", "회", "시간", "분", "원", "실", "명", "대", "코스", ""}


def figures(text: str | None) -> set:
    t = squash_ws(text)
    out = {x.replace(",", "") for x in re.findall(r"\d[\d,]*(?:\.\d+)?", t)}
    for w, n in KNUM.items():
        if re.search(rf"(?<![가-힣]){w}\s*(곳|가지|개|편|장|대|채|실)", t):
            out.add(str(n))
    return out


def answer_row(key: str, href: str, answer: str, fig: str = "", unit: str = "", fig_label: str = "",
               closed: str = "", warn=None) -> dict:
    """An answer row. Its figure must be a number written in the row's own sentence, or carry an explicit
    label naming what is counted (fig_label); otherwise it is dropped (no figure without a referent)."""
    if fig and fig.replace(",", "") not in figures(answer) and not fig_label:
        if warn is not None:
            warn.append(f"답 줄 '{key}': 숫자 {fig}{unit}이 문장에 없어 뺐습니다")
        fig, unit = "", ""
    return {"key": key, "href": href, "answer": answer, "closed": closed, "fig": fig, "unit": unit,
            "fig_label": fig_label}


# Short answers in 개조식 (noun endings), one per guide (Apple direction, approved 2026-10-08), written per city in
# site.json city.home.answer_copy {guide id: {answer, fig, unit, closed}}. Every figure in them is checked against the
# guide's own text at build time (guide_answer): a mismatch falls back to the guide's first heading with a warning, so
# a data edit can never leave a stale number on the page. {free} = the attractions whose 이용요금 reads '무료' (and no
# other source says otherwise). The content track may move them into guides.json as the field `answer`, which then
# wins.
def answer_copy() -> dict:
    return city.current().home("answer_copy", {}) or {}


def guide_text(g: dict) -> str:
    """Everything a guide says (summary, title, body, item reasons): the text an answer's figures are checked against."""
    return " ".join([g.get("summary") or "", g.get("title") or ""] +
                    [f"{b.get('heading', '')} {b.get('text', '')}" for b in g.get("body") or []] +
                    [f"{i.get('reason', '')}" for i in g.get("items") or []])


def free_attractions(S) -> int:
    return sum(1 for e in S.lists["attraction"]
               if squash_ws((e.get("facts") or {}).get("usefee")) == "무료" and not contested(e, "usefee"))


def guide_answer(g: dict, S=None) -> dict:
    """The guide's short answer: the data field `answer` ({answer, fig, unit, closed}) when the content track
    wrote one; else (with the build state S) the city's answer copy when every figure in it is written in the guide;
    else the guide's first declarative heading with the first figure written in it. A figure the answer sentence does
    not contain word for word carries the copy's unit as its label (fig_label: '09:30 토·일 첫 출발')."""
    a = g.get("answer")
    if isinstance(a, dict) and squash_ws(a.get("answer")):
        return {"answer": squash_ws(a["answer"]), "fig": squash_ws(a.get("fig")), "unit": squash_ws(a.get("unit")),
                "closed": squash_ws(a.get("closed")), "fig_label": squash_ws(a.get("fig_label"))}
    copy = answer_copy().get(g.get("id")) if S is not None else None
    if copy:
        free = str(free_attractions(S))
        c = {k: str(v).replace("{free}", free) for k, v in copy.items()}
        mine = figures(c["answer"]) | figures(c.get("closed")) | figures(c["fig"])
        bad = sorted(mine - (figures(guide_text(g)) | {free}))
        if not bad:
            own = c["fig"].replace(",", "") in figures(c["answer"])
            return {"answer": c["answer"], "fig": c["fig"], "unit": c["unit"] if own else "", "closed": c.get("closed", ""),
                    "fig_label": "" if own else c["unit"]}
        S.warnings.append(f"답 줄 {g.get('id')}: 가이드 본문에 없는 숫자 {bad} — 가이드 첫 소제목 사용")
    head = squash_ws(((g.get("body") or [{}])[0]).get("heading")) or squash_ws(g.get("title"))
    # the first figure that is a whole amount: neither part of '2시간30분' is used (each alone is a cut value);
    # a figure that stands alone after it is
    ms = list(FIG_RX.finditer(head))
    joined = {i for i in range(len(ms) - 1) if not head[ms[i].end():ms[i + 1].start()].strip()}
    m = next((x for i, x in enumerate(ms) if i not in joined and i - 1 not in joined), None)
    return {"answer": head, "fig": m.group(1) if m else "", "unit": m.group(2) if m else "", "closed": "", "fig_label": ""}


def guide_rows(S) -> list[dict]:
    """Guides index rows: {g, n_items, head, answer…}."""
    out = []
    for g in S.guides:
        a = guide_answer(g, S)
        row = answer_row(g.get("label") or g["title"], g["_path"], a["answer"], a["fig"], a["unit"], a["fig_label"],
                         a["closed"], S.warnings)
        out.append({"g": g, "n_items": len(g.get("items") or []),
                    "head": squash_ws(((g.get("body") or [{}])[0]).get("heading")), **row})
    return out


# ----------------------------------------------------------------------------- home
# The home's city content is configuration (site.json city.home; pipeline/city.py): the answer rows (answers: [[key,
# guide id]], answer_default: the last row when no dish leads), the dish focus (focus_dishes), the search example,
# the story chapters, the photo picks (pipeline/media.py), the gallery, the teaser course, the video topics and the
# answer bar's hub rows. Every place it names is looked up in the collected data and the block is left out with a
# warning when it is missing; a new city without these keys gets a home built from its data alone.
#
# Home focus (owner 2026-10-13: the dish tile outlived its festival): what the home leads with is one rule over the
# data on the build date, not fixed copy. A dish leads only while a festival named after it is running or starts
# within focus_days — then it heads the 맛집 tile (hub_short row + lead below), takes the home's last answer row and
# comes first in the search example. Otherwise the 맛집 tile leads with the hub's restaurant count and every dish is an
# equal pill (largest count first), the last answer row is answer_default and the search example names places.
# Every figure is still checked against the guide's own text.
FOCUS_DAYS = 21


def home_answers() -> list[tuple[str, str]]:
    return [(str(k), str(g)) for k, g in city.current().home("answers", []) or []]


def home_answer_default() -> tuple[str, str] | None:
    d = city.current().home("answer_default")
    return (str(d[0]), str(d[1])) if d else None


def focus_dishes() -> dict:
    """{dish: (words in the event name, hub row while it leads, the figure's lead, home answer row)}."""
    out = {}
    for dish, v in (city.current().home("focus_dishes", {}) or {}).items():
        out[dish] = (tuple(v.get("words") or (dish,)), tuple(v["row"]), v.get("lead", ""), tuple(v["answer"]))
    return out


def home_focus(S) -> dict | None:
    """The dish the home leads with today, or None: the festival (an edition whose name has the dish's word) that is
    running or starts soonest within focus_days of the build date (S.today)."""
    dishes = focus_dishes()
    if not dishes:
        return None
    today = dt.date.fromisoformat(S.today)
    window = int(city.current().home("focus_days", FOCUS_DAYS))
    best = None
    for ev in S.events:
        r = event_row(ev)
        if not r["start"] or not r["last"] or r["last"] < S.today:
            continue
        days = (dt.date.fromisoformat(r["start"]) - today).days
        if days > window:
            continue
        name = squash_ws(ev.get("name"))
        for dish, (words, row, lead, answer) in dishes.items():
            if any(w in name for w in words) and (best is None or days < best["days"]):
                best = {"dish": dish, "row": row, "lead": lead, "answer": answer, "event": ev, "days": days}
    return best


def search_example(S) -> str:
    """The home search field's example: the focus dish first while there is one (home_focus), then the city's
    configured words (city.home.search_example); '' without either."""
    focus = home_focus(S)
    words = list(city.current().home("search_example", []) or [])
    if focus:
        words = [focus["dish"], *words[:1], *words[-1:]]
    return ("예: " + ", ".join(dict.fromkeys(words))) if words else ""


def home_vm(S) -> dict:
    """The home page: answer rows, events, courses, 권역, the photo slots and the showcase (home_showcase). Every place
    the city's configuration names is looked up and skipped with a warning when missing, so a data edit never breaks
    the build."""
    from . import build as B
    warn = S.warnings
    gmap = {x["id"]: x for x in S.guides}
    stays = S.lists["stay"]
    checkins = Counter(squash_ws(e["facts"]["checkin"]) for e in stays
                       if (e.get("facts") or {}).get("checkin") and not contested(e, "checkin"))
    day = [S.course_vms[c["slug"]] for c in S.courses if c.get("duration") == "당일"]
    official = city.current().official["short"]
    answers = []
    if day:
        answers.append(answer_row("당일", "/courses/#g-당일", f"{official} 공식 당일 코스: ".lstrip()
                                  + " · ".join(cv["display"] for cv in day),
                                  str(len(day)), "개", "공식 당일 코스", "", warn))
    focus = home_focus(S)
    last = focus["answer"] if focus else home_answer_default()
    for key, gid in [*home_answers(), *([last] if last else [])]:
        g = gmap.get(gid)
        if not g:
            warn.append(f"홈 답 줄: {gid} 없음 — 줄 생략")
            continue
        a = guide_answer(g, S)
        answers.append(answer_row(key, g["_path"], a["answer"], a["fig"], a["unit"], a["fig_label"], a["closed"], warn))
    if checkins:
        top_in, top_n = checkins.most_common(1)[0]
        # the figure is the check-in time most stays give, when it is a plain hh:mm (the stay count is already in the
        # link row, the 숙소·펜션 tile and the numerals band above)
        timed = re.fullmatch(r"\d{1,2}:\d{2}", top_in)
        answers.append(answer_row("숙소 찾기", "/stays/",
                                  f"숙소 {len(stays)}곳 · 체크인 시간이 나온 {sum(checkins.values())}곳 중 {top_n}곳이 {top_in} 체크인",
                                  top_in if timed else str(len(stays)), "" if timed else "곳",
                                  "가장 많은 체크인" if timed else "", "", warn))
    upcoming = sorted([ev for ev in S.events if ev.get("start_date") and B.event_last_day(ev) >= S.today],
                      key=lambda ev: ev["start_date"])
    past = sorted([ev for ev in S.events if ev.get("start_date") and B.event_last_day(ev) < S.today],
                  key=lambda ev: ev["start_date"], reverse=True)
    events = [event_row(ev) for ev in upcoming]
    months = sorted({r["start"][:7] for r in events})
    ev_head = (" · ".join(f"{int(m[:4])}년 {int(m[5:])}월" for m in months) + " 행사") if months else "행사"
    lines = [S.course_vms[c["slug"]] for grp in ("당일", "1박 2일", "2박 3일") for c in S.courses if c.get("duration") == grp]
    C = city.current()
    regions = []
    for rname in S.region_names:
        if rname == C.none_label or (rname == C.far_label and C.region_method == "nearest_anchor"):
            continue
        members = [e for e in S.entities if e["_region"] == rname]
        if not members:
            continue
        dongs = Counter(e["_area"] for e in members if e["_area"]).most_common(4)
        anchor = next((a for a in S.anchors if a["name"] == rname), None)
        regions.append({"name": rname, "n": len(members), "k": Counter(e["kind"] for e in members),
                        "dongs": [d for d, _ in dongs], "anchor": anchor, "id": "r-" + frag(rname)})
    annual_n = sum(1 for ev in S.events if not ev.get("start_date") and "매년" in str(ev.get("period_text") or ""))
    h = {"answers": answers, "search_example": search_example(S), "guides": S.guides, "events": events,
         "ev_head": ev_head, "annual_n": annual_n, "last_event": event_row(past[0]) if past and not events else None,
         "lines": lines, "course_total": len(S.courses), "regions": regions,
         "region_rule": region_rule_vm(S),
         "counts": {k: len(v) for k, v in S.lists.items()}, "official": S.site.get("official_links") or [],
         "starts": home_starts(S),   # the first screen's situational entries (words only)
         "slots": media.slot_photos(S)}  # hero / story / gallery photos (pipeline/media.py, licence-checked)
    h.update(home_showcase(S, h))
    return h


def region_rule_vm(S) -> dict:
    """The 권역 rule as the pages print it (map page, home): method, the anchors (nearest_anchor) or the district lines
    and note (district), the far threshold and the leftover labels."""
    C = city.current()
    return {"method": C.region_method if S.region_names != [C.none_label] else "none", "anchors": S.anchors,
            "lines": C.region_rule_lines(), "note": C.region_rule_note, "far_m": C.far_m,
            "far_label": C.far_label, "none_label": C.none_label}


# ----------------------------------------------------------------------------- home: the Apple layer
# Every figure and date below is read from the data or computed from it (CINEMATIC.md §6, kept by the Apple
# direction). Places the configuration names are looked up and skipped with a warning when missing.
FEATURED_MIN_COURSES = 7  # 대표 장소: attractions on at least this many official courses (the rule is printed)
# The answer bar's order and its accent bento (owner, 2026-10-09, after masstige.io): the hub guides' tiles take the
# city's accent tones (city.home.accent_tones {guide id: [tone, icon]}), the official 당일 courses the one dark card;
# every other tile stays Apple grey. Role names (review 2026-10-14): the lead tile and two pale sea tints, the
# official courses' tile in the brand sea.
PURPOSE_ORDER = ("맛집", "숙소·펜션", "가볼만한 곳", "당일", "아이와 함께", "비 오는 날", "차 없이", "숙소 찾기")
ACCENT_DARK = {"tone": "sea", "icon": "route"}


def _rows(key: str) -> dict:
    """{guide id: (key, desktop line, phone line, figure, unit)} from city.home.<key> (hub_short, answer_short)."""
    return {gid: tuple(v) for gid, v in (city.current().home(key, {}) or {}).items()}


def accent_tones() -> dict:
    return {gid: tuple(v) for gid, v in (city.current().home("accent_tones", {}) or {}).items()}


def hub_lead() -> dict:
    """A hub figure that counts one part of the guide names that part in front of it (review 2026-10-09: a dish count
    read as all restaurants): {guide id: lead}; the desktop line's other parts become the tile's pills."""
    return dict(city.current().home("hub_lead", {}) or {})


def purposes_vm(S) -> list[dict]:
    """The home answer bar's purposes: the hub guides (city.home.hub_short), 당일 (the official 당일 courses), the
    other answer rows (city.home.answer_short; every figure checked against its guide) and, only when there is no
    숙소·펜션 hub, 숙소 찾기 (the most common 체크인 time among the stays that state one), in PURPOSE_ORDER (or
    city.home.purpose_order). Row: {key, href, short (desktop), tiny (phones), fig, unit, tone / icon / pill (the
    accent bento; '' = an Apple grey tile), lead + pills (hub_lead: what the figure counts, and the desktop line's
    other parts as pills)}."""
    out = []
    official = city.current().official["short"]
    day = [S.course_vms[c["slug"]] for c in S.courses if c.get("duration") == "당일"]
    if day:
        letters = "·".join(cv["letter"] for cv in day if cv["letter"])
        out.append({"key": "당일", "href": "/courses/#g-당일",
                    "short": f"{official} 공식 당일 코스".lstrip() + (f" {letters}" if letters else ""),
                    "tiny": f"{official} 공식 코스".lstrip(), "fig": str(len(day)), "unit": "코스",
                    "track": "course_click", **ACCENT_DARK, "pill": "공식 코스"})
    gmap = {g["id"]: g for g in S.guides}
    focus = home_focus(S)
    hub_short, leads, answer_short, tones = _rows("hub_short"), hub_lead(), _rows("answer_short"), accent_tones()
    if focus and hub_short:
        food_hub = next(iter(hub_short))
        hub_short[food_hub], leads[food_hub] = focus["row"], focus["lead"]
    for gid, (key, short, tiny, fig, unit) in [*hub_short.items(), *answer_short.items()]:
        g = gmap.get(gid)
        if not g:
            if gid in answer_short:
                S.warnings.append(f"답 막대: {gid} 없음 — 줄 생략")
            continue
        bad = sorted((figures(short) | figures(tiny) | figures(fig)) - figures(guide_text(g)))
        if bad:
            S.warnings.append(f"답 막대 {gid}: 가이드 본문에 없는 숫자 {bad} — 줄 생략")
            continue
        tone, icon = tones.get(gid, ("", ""))
        lead = leads.get(gid, "")
        out.append({"key": key, "href": g["_path"], "short": short, "tiny": tiny, "fig": fig, "unit": unit,
                    "track": "guide_click", "tone": tone, "icon": icon, "lead": lead,
                    "pills": [x for x in short.split(" · ") if not x.startswith(lead)] if lead else []})
    stays = S.lists["stay"]
    checkins = Counter(squash_ws(e["facts"]["checkin"]) for e in stays
                       if (e.get("facts") or {}).get("checkin") and not contested(e, "checkin"))
    if checkins and not any(r["key"] == "숙소·펜션" for r in out):
        top_in, top_n = checkins.most_common(1)[0]
        out.append({"key": "숙소 찾기", "href": "/stays/", "fig": str(len(stays)), "unit": "곳",
                    "short": f"체크인 시간이 나온 {sum(checkins.values())}곳 중 {top_n}곳이 {top_in}",
                    "tiny": f"{top_n}곳이 {top_in} 체크인"})
    order = tuple(city.current().home("purpose_order", PURPOSE_ORDER))
    rank = {k: i for i, k in enumerate(order)}
    return sorted(out, key=lambda r: rank.get(r["key"], len(rank)))


def date_parts(r: dict) -> dict:
    """The parts of a dated row's big date: a = start {md '10. 9.', wd '금'}, b = last day (or None), end_month ('10')
    when the source gives only an end month — then b is None: the month's last day (build.event_last_day, the sort
    key) is never shown as the end (QA 2026-10-15 SRC-06)."""
    from . import build as B

    def one(iso):
        d = dt.date.fromisoformat(iso[:10])
        return {"md": f"{d.month}. {d.day}.", "wd": WEEK[d.weekday()]}
    em = B.event_end_month(r.get("ev") or {})
    a = one(r["start"]) if r.get("start") else None
    b = one(r["last"]) if not em and r.get("last") and r.get("last") != r.get("start") else None
    return {"a": a, "b": b, "end_month": em[5:]}


def ranked_events(S) -> list[dict]:
    """Dated editions still to come or running on the build date (S.today), ranked: today, tomorrow, this week,
    later; then the running ones by the day they end. Each row (event_row) gets chip (오늘 · 내일 시작 · n일 뒤 시작 ·
    m월 d일 시작 · 진행 중 · m.d.까지, or 진행 중 · m월 중 끝남 when the source gives the end only as a month), rank, days
    (to the start; < 0 while running) and dp (date_parts). The site is rebuilt daily by the events command, so the
    chips stay true."""
    from . import build as B
    today = dt.date.fromisoformat(S.today)
    rows = []
    for ev in S.events:
        r = event_row(ev)
        if not r["start"] or not r["last"] or r["last"] < S.today:
            continue
        st, last = dt.date.fromisoformat(r["start"]), dt.date.fromisoformat(r["last"])
        d = (st - today).days
        if d == 0:
            chip, rank = "오늘", (0, d)
        elif d == 1:
            chip, rank = "내일 시작", (1, d)
        elif 1 < d <= 6:
            chip, rank = f"{d}일 뒤 시작", (2, d)
        elif d > 6:
            chip, rank = f"{st.month}월 {st.day}일 시작", (3, d)
        else:
            em = B.event_end_month(r["ev"])   # '~10월': the source gives no end day — never '10.31.까지'
            chip = f"진행 중 · {int(em[5:])}월 중 끝남" if em else f"진행 중 · {last.month}.{last.day}.까지"
            rank = (4, (last - today).days)
        rows.append({**r, "chip": chip, "rank": rank, "days": d, "dp": date_parts(r)})
    rows.sort(key=lambda r: (r["rank"], r["start"]))
    return rows


def pick_next_event(rows: list[dict]) -> dict | None:
    """The answer bar's one event: the nearest dated edition starting today or later within 30 days, else the
    running one that ends soonest."""
    ahead = [r for r in rows if 0 <= r["days"] <= 30]
    if ahead:
        return min(ahead, key=lambda r: (r["days"], r["start"]))
    running = [r for r in rows if r["days"] < 0]
    return running[0] if running else None


def sentence_with(e: dict | None, needle: str) -> str:
    """The first whole summary sentence of a place that contains needle ('' when none does)."""
    return next((x for x in sentences((e or {}).get("summary")) if needle in x), "") if e else ""


def _story_line(S, spec: dict) -> tuple[str, dict | None]:
    """One configured story sentence: the first whole summary sentence of the place that contains the needle
    (with the place's name in front when `subject` asks for it and the sentence lacks it)."""
    e = find_place(S, spec.get("place", ""))
    t = sentence_with(e, spec.get("needle", "")) if e and spec.get("needle") else ""
    if t and spec.get("subject") and not t.startswith(e["name"]):
        t = josa(e["name"], "은/는") + " " + t
    return t, e


def _story_fig(S, spec: dict) -> dict | None:
    """A computed story figure: 'within' (attractions within m metres of a place, straight line) or 'between' (the
    straight line between two places, in km). None when a place or its coordinates are missing."""
    if spec.get("kind") == "within":
        e = find_place(S, spec.get("place", ""))
        if not (e and e.get("_geo")):
            return None
        m = float(spec.get("m") or 1000)
        # one building counts once (a same_building pair, pipeline/relations.py) and the place's own building not
        # at all
        own = {e["id"], *(x["id"] for x in e.get("_same") or [])}
        near = relations.one_per_building([x for x in S.lists["attraction"] if x["id"] not in own and x["_geo"]
                                           and hav(e["_geo"], x["_geo"]) <= m])
        return {"n": str(len(near)), "unit": "곳", "label": spec.get("label", ""), "src": e,
                "geo": [e["_geo"]] + [x["_geo"] for x in near]}
    if spec.get("kind") == "between":
        a, b = find_place(S, spec.get("a", "")), find_place(S, spec.get("b", ""))
        if not (a and b and a.get("_geo") and b.get("_geo")):
            return None
        return {"n": str(round(hav(a["_geo"], b["_geo"]) / 1000)), "unit": "km", "label": spec.get("label", ""),
                "src": None, "geo": [a["_geo"], b["_geo"]]}
    return None


def home_story(S) -> list[dict]:
    """The home story (city.home.story): chapters whose every sentence is a place summary sentence and whose figures
    are computed from coordinates. A chapter: {id, big, kicker, title, lines [{place, needle, required, subject}],
    steps [{place, needle, year}], figs [{kind within|between, …, label}], photo [place, n]}. A required sentence
    gone from the data drops its chapter with a warning; a chapter with nothing left is dropped too. Output chapter:
    {id, big, kicker, title, text [sentences], steps [{y, name, path, text}], figs [{n, unit, label}], src
    [(name, path)], photo (media.slot_photos story: KOGL-1 may be zoomed in the stage, KOGL-3 is shown whole)}."""
    ph = media.slot_photos(S)["story"]
    out = []
    for c in city.current().home("story", []) or []:
        cid = c.get("id") or f"ch-{len(out) + 1}"
        text, src, missing = [], [], ""
        for spec in c.get("lines") or []:
            t, e = _story_line(S, spec)
            if not t:
                if spec.get("required"):
                    missing = f"{spec.get('place')} 요약에 '{spec.get('needle')}'이(가) 없음"
                    break
                continue
            if t not in text:
                text.append(t)
            if (e["name"], e["_path"]) not in src:
                src.append((e["name"], e["_path"]))
        if missing:
            S.warnings.append(f"홈 이야기: {missing} — {cid} 장 생략")
            continue
        steps = []
        for spec in c.get("steps") or []:
            t, e = _story_line(S, spec)
            if t:
                steps.append({"y": str(spec.get("year") or ""), "name": e["name"], "path": e["_path"], "text": t})
                src.append((e["name"], e["_path"]))
        figs = [f for f in (_story_fig(S, spec) for spec in c.get("figs") or []) if f]
        if not (text or steps or figs):
            S.warnings.append(f"홈 이야기: {cid} 장에 쓸 문장·수치가 데이터에 없음 — 생략")
            continue
        title = str(c.get("title") or "")
        if steps:
            title = title.format(first=steps[0]["y"], last=steps[-1]["y"]) if "{" in title else title
        out.append({"id": cid, "big": str(c.get("big") or (steps[0]["y"] if steps else "")),
                    "kicker": str(c.get("kicker") or ""), "title": title, "text": text, "steps": steps,
                    "figs": [{k: f[k] for k in ("n", "unit", "label")} for f in figs], "src": src,
                    # geo_src: whose coordinates the figures join ('한국관광공사 TourAPI', …), named in the cite
                    "geo_src": "·".join(geo_providers([g for f in figs for g in f["geo"]])),
                    "photo": ph.get(cid)})
    return out


def home_showcase(S, h: dict) -> dict:
    """The Apple home's view model, added to home_vm: hero (KOGL-1 slides), cover (the full-bleed opening photo,
    city.home.photos.cover), opening + news + services (the Korean opening's kicker, its one-card news carousel and
    its round service icons: home_opening, home_news, home_services), purposes + next_event (the answer bar),
    featured (대표 장소 cards, featured_min), events_ranked (3) + n_upcoming, regions2 + region_map (권역 tiles and,
    under the anchor rule, the anchors map), chapters (the story), gallery (city.home.gallery: its cards, its 권역 and
    the count of attractions in it, the story's km figure), teaser {cv, map} + day_lines (the 당일 course on a map),
    vfeat / vrows / vchips / n_videos (영상으로 보는 <city>), region_word (the region in Revised Romanization, upper
    case)."""
    from . import build as B
    from .en_source import romanize
    C = city.current()
    by = S.ent_by_slug
    slots = h.get("slots") or media.slot_photos(S)
    used = {p["url"] for p in slots["hero"]}
    gallery = []
    for p in slots["gallery"]:
        e = by.get(p["slug"])
        if e:
            gallery.append(card_vm(e, p))
            used.add(p["url"])
    cnt = Counter()
    for c in S.courses:
        for st in S.course_vms[c["slug"]]["stops"]:
            if st["t"] and st["t"].get("kind") == "attraction":
                cnt[st["t"]["slug"]] += 1
    featured = []
    featured_min = int(C.home("featured_min_courses", FEATURED_MIN_COURSES))
    for slug, k in sorted(cnt.items(), key=lambda kv: (-kv[1], name_key(by[kv[0]]["name"]))):
        if k < featured_min:
            break
        e = by[slug]
        ph = next((p for p in e["_photos"] if p["url"] not in used), e["_photos"][0] if e["_photos"] else None)
        featured.append({**card_vm(e, ph), "n_courses": k})
    ranked = ranked_events(S)
    regions2 = [{**r, "dongs": r["dongs"][:3]} for r in h.get("regions") or []]
    region_map = {"anchors": [{"lat": r["anchor"]["geo"]["lat"], "lng": r["anchor"]["geo"]["lng"], "name": r["name"],
                               "label": r["name"], "n": r["n"], "url": f"/map/#{r['id']}", "place": r["anchor"]["place"]}
                              for r in regions2 if r.get("anchor")]}
    teaser = C.home("teaser_course", "")
    cv = S.course_vms.get(teaser) if teaser else None
    if teaser and not cv:
        S.warnings.append(f"홈 코스: {teaser} 없음 — 코스 지도 생략")
    gcfg = C.home("gallery", {}) or {}
    g_region = gcfg.get("region", "")
    n_gal = sum(1 for e in S.lists["attraction"] if g_region and e["_region"] == g_region)
    vg = B.video_groups(S.videos) if getattr(S, "videos", None) else []
    by_t = {g["title"]: g for g in vg}
    vfeat = by_t["여행 코스"]["items"][0] if "여행 코스" in by_t else (vg[0]["items"][0] if vg else None)
    chapters = home_story(S)
    km = next(({"n": f["n"], "label": f["label"]} for c in chapters for f in c["figs"] if f["unit"] == "km"), None)
    return {"hero": slots["hero"], "cover": slots.get("cover"), "purposes": purposes_vm(S),
            "opening": home_opening(S), "news": home_news(S), "services": home_services(S, len(ranked)),
            "next_event": pick_next_event(ranked),
            "events_ranked": ranked[:3], "n_upcoming": len(ranked), "featured": featured,
            "featured_min": featured_min, "regions2": regions2, "region_map": region_map,
            "chapters": chapters, "gallery": gallery,
            "gallery_head": {"kicker": gcfg.get("kicker", ""), "title": gcfg.get("title", ""), "region": g_region,
                             "n": n_gal, "km": km},
            "teaser": {"cv": cv, "map": course_map(cv["stops"])} if cv else None,
            "day_lines": [S.course_vms[c["slug"]] for c in S.courses if c.get("duration") == "당일"],
            "vfeat": vfeat, "n_videos": len(getattr(S, "videos", []) or []),
            "region_word": romanize(S.site.get("region", "")).upper(),   # the black band's oversized word
            "vrows": [{"topic": t, "v": by_t[t]["items"][0], "n": len(by_t[t]["items"]), "id": "v-" + frag(t),
                       "path": by_t[t].get("_path", "")} for t in C.home("video_row_topics", []) or [] if t in by_t],
            "vchips": [{"title": g["title"], "n": len(g["items"]), "id": "v-" + frag(g["title"]), "path": g.get("_path", "")}
                       for g in vg]}


# ----------------------------------------------------------------------------- home: the opening
# Owner 2026-10-13 ('첫 화면 디자인도 이런 식으로 개편하자. 카드 알아서 넘어가게, 최신 소식들 담아서'): news cards that
# advance by themselves, then a row of round service icons. Owner 2026-10-13 night ('첫 메인 화면이 너무 알록달록하고 …
# 차라리 고화질 실사로 배경을 넣고, 글자 우측에 카드로 소식 하나씩 넘기는 형태가 낫지 않나?'; docs/handover/specs/
# home_redesign.md): the official KOGL-1 photo full-bleed (city.home.photos.cover, as the English home), the kicker · H1 · lede
# and the question box at the left, ONE news card at a time at the right (below the opening on phones). The season's
# field and illustration are gone (art.json home.hero.* is '개편 뒤 연결'). Everything is computed from the data and the
# build date (S.today); the site is rebuilt daily, so the home changes by itself.
#
# home_news(S) — THE RANKING RULE (this comment is its record; the page prints the cards, not the rule):
#   1. focus: the dish festival home_focus() leads with (running, or starting within focus_days) — one card, chip 축제
#   2. events: ranked_events() rows running now or starting within NEWS_EVENT_DAYS, in that order (today → tomorrow →
#      this week → later → running ones by the day they end), the focus festival left out; at most 3
#   3. abroad: /abroad/ articles dated within NEWS_ABROAD_DAYS of the build date, newest first (date, then id); at most 3
#   4. guides: the newest guides (approved_at — else reviewed_at — then the guide number, both descending); at most 2
#   5. videos: the newest videos published within NEWS_VIDEO_DAYS (build.video_rank); at most 1
#   Then, while there are fewer than NEWS_MIN cards, the next candidates over those caps in the same source order; never
#   more than NEWS_MAX. Past events never come in (ranked_events keeps only running and coming editions).
# Each card's picture, in order: an allowed photo — a TourAPI photo (KOGL-1/3, credited) of the event's / guide's /
# article's attraction (news_photo), and for an article first the outlet's own link-preview image (og:image, credited
# to the outlet, loaded from its address) — else the kind's AI art slot (home.card.<kind>; a dish festival first takes
# home.card.festival-<dish>, an event or festival card first its event kind's events.kind.<kind>, art.event_kind),
# else a small type icon on a tinted tile. A video card never shows a YouTube thumbnail.
NEWS_MAX, NEWS_MIN = 8, 6
NEWS_EVENT_DAYS = 30
NEWS_ABROAD_DAYS = 365
NEWS_VIDEO_DAYS = 30
NEWS_NEW_DAYS = 30        # a guide approved within this many days reads '새 가이드', an older one '가이드'
NEWS_CAPS = (("event", 3), ("abroad", 3), ("guide", 2), ("video", 1))
NEWS_KIND = {  # kind: (chip, icon, tint)
    "festival": ("축제", "bowl", "lime"), "event": ("행사", "calendar", "lime"),
    "abroad": ("해외에서 본 {region}", "globe", "sky"), "guide": ("새 가이드", "book", "lav"), "video": ("새 영상", "play", "sky")}
NEWS_PHOTO_SCAN = 6       # how many related places a card looks through for a light KOGL-1 photo
PLACE_SPLIT = re.compile(r"\s*(?:,|/|·|및|\s와\s|\s과\s)\s*")


def event_places(S, ev: dict) -> list[dict]:
    """The places an event edition is held at: its place_slugs (and place_slug), then each part of place_name
    ('X회관, Y1981'; the city in front, brackets and a trailing 일원·일대 dropped) matched to a place name, then its TourAPI
    contentid."""
    out: list[dict] = []

    def add(e):
        if e and e not in out:
            out.append(e)
    for slug in [*(ev.get("place_slugs") or []), ev.get("place_slug") or ""]:
        add(S.ent_by_slug.get(slug))
    by_name = getattr(S, "_ent_by_name", None)
    if by_name is None:
        by_name = S._ent_by_name = {normalize_name(e["name"]): e for e in S.entities}
    raw = city.current().strip_prefix(ev.get("place_name"))
    for part in PLACE_SPLIT.split(raw):
        part = re.sub(r"\([^)]*\)|\s*(?:일원|일대)$", "", part).strip()
        if part:
            add(by_name.get(normalize_name(part)))
    for cid in (ev.get("contentid"), ev.get("tourapi_contentid")):
        if cid:
            add(S.ent_by_cid.get(str(cid)))
    return out


def news_photo(ents: list[dict], used: set | frozenset = frozenset()) -> dict | None:
    """A news card's TourAPI photo from its related places, in their order: the first KOGL-1 photo with a same-origin
    derivative among the first NEWS_PHOTO_SCAN places (light, and it may be cropped), else the first place's lead
    photo (a KOGL-3 one is shown whole). A photo an earlier card already shows (used: urls) is passed over for that
    place's next one. With the place's name and path. Attractions only: a restaurant's or a stay's photo on the home's
    first screen would single out one business (CLAUDE.md 3.10) — such a card takes its art or icon instead."""
    ents = [e for e in ents if e.get("kind") == "attraction"]
    for e in ents[:NEWS_PHOTO_SCAN]:
        ph = next((p for p in e.get("_photos") or [] if p.get("type") == 1 and p.get("avif") and p["url"] not in used),
                  None)
        if ph:
            return {**ph, "place": e["name"], "path": e["_path"]}
    for e in ents:
        ph = next((p for p in e.get("_photos") or [] if p["url"] not in used), None)
        if ph:
            return {**ph, "place": e["name"], "path": e["_path"]}
    return None


def dot_date(iso: str) -> str:
    """'2026-10-10' -> '2026. 10. 10.', '2020-02' -> '2020. 2.', '2021' -> '2021'."""
    parts = [p for p in (iso or "").split("-") if p]
    if not parts:
        return ""
    return ". ".join([parts[0], *(str(int(x)) for x in parts[1:])]) + ("." if len(parts) > 1 else "")


def iso_floor(d: str) -> str:
    """A partial date as its first day ('2020-02' -> '2020-02-01', '2021' -> '2021-01-01'); '' stays ''."""
    d = (d or "")[:10]
    return {4: d + "-01-01", 7: d + "-01"}.get(len(d), d)


def _news_card(S, kind: str, title: str, href: str, **kw) -> dict:
    chip, icon, tint = NEWS_KIND[kind]
    card = {"kind": kind, "chip": chip.format(region=S.site.get("region", "")), "icon": icon, "tint": tint,
            "title": title, "href": href, "when": "", "when_iso": "", "sub": "", "status": "", "photo": None,
            "og": "", "outlet": "", "ext": False, "lang": "", "track": "", "key": href, "art": None, "places": [],
            "ev_kind": ""}
    card.update(kw)
    return card


def _event_card(S, r: dict, kind: str = "event") -> dict:
    dp = r.get("dp") or date_parts(r)
    when = ""
    if dp.get("a"):
        end = f"{int(dp['end_month'])}월" if dp.get("end_month") else dp["b"]["md"] if dp.get("b") else ""
        when = dp["a"]["md"] + (f"–{end}" if end else "")
    return _news_card(S, kind, r["title"], r["path"] or r["source_url"], when=when, when_iso=r["start"],
                      sub=r["place"], status=r.get("chip", ""), places=event_places(S, r["ev"]),
                      ext=not r["path"], track="" if r["path"] else "official_click", key="ev:" + str(r["ev"].get("id")),
                      ev_kind=art.event_kind(r["ev"]))


def _guide_rank(g: dict) -> tuple:
    m = re.search(r"(\d+)$", g.get("id") or "")
    return (g.get("approved_at") or g.get("reviewed_at") or "", int(m.group(1)) if m else -1)


def home_news(S) -> list[dict]:
    """The home's news cards for the build date S.today (the rule is the comment above NEWS_MAX). Card: {kind, chip,
    icon, tint, title, href, when (shown), when_iso, sub, status, photo (TourAPI photo or None), og (an article's own
    preview image or ''), outlet, ext (an outside link), lang, track, key, art (an AI art picture or None), ev_kind
    (an event card's kind, art.event_kind)}. A card without a photo or preview image takes an AI picture: the dish
    festival's own, else the event kind's (events.kind.<kind>), else the card kind's (home.card.<kind>). A region
    with no place yet has no news row: its home stays the honest empty state, nothing dressed up (CLAUDE.md 4)."""
    from . import build as B
    if not S.entities:
        return []
    today = dt.date.fromisoformat(S.today)
    tiers: list[tuple[list[dict], int]] = []
    focus = home_focus(S)
    ranked = ranked_events(S)
    focus_id = focus["event"].get("id") if focus else None
    if focus:
        r = next((x for x in ranked if x["ev"].get("id") == focus_id), None)
        tiers.append(([_event_card(S, r, "festival")] if r else [], 1))
    caps = dict(NEWS_CAPS)
    tiers.append(([_event_card(S, r) for r in ranked
                   if r["days"] <= NEWS_EVENT_DAYS and r["ev"].get("id") != focus_id], caps["event"]))
    arts = [a for a in getattr(S, "abroad", None) or [] if a.get("kind") == "article" and a.get("date")
            and 0 <= (today - dt.date.fromisoformat(iso_floor(a["date"]))).days <= NEWS_ABROAD_DAYS]
    arts.sort(key=lambda a: a["id"])
    arts.sort(key=lambda a: iso_floor(a["date"]), reverse=True)
    tiers.append(([_news_card(S, "abroad", squash_ws(a.get("title")) or a["outlet"], a["url"], when=dot_date(a["date"]),
                              when_iso=a["date"], sub=a["outlet"], outlet=a["outlet"], og=a.get("image") or "",
                              places=[] if a.get("image") else
                              [S.ent_by_slug[s] for s in a.get("place_slugs") or [] if s in S.ent_by_slug],
                              ext=True, lang=a["lang"] if a.get("lang") not in (None, "", "ko") else "",
                              track="abroad_click", key="ab:" + a["id"]) for a in arts], caps["abroad"]))
    cards = []
    for g in sorted(S.guides, key=_guide_rank, reverse=True):
        slugs = [*(g.get("route_slugs") or []), *(it.get("place_slug") for it in g.get("items") or [] if isinstance(it, dict))]
        title, _, rest = squash_ws(g.get("title")).partition(" — ")
        approved = g.get("approved_at") or g.get("reviewed_at") or ""
        fresh = bool(approved) and (today - dt.date.fromisoformat(approved[:10])).days <= NEWS_NEW_DAYS
        cards.append(_news_card(S, "guide", title, g["_path"], sub=rest, chip="새 가이드" if fresh else "가이드",
                                places=[S.ent_by_slug[s] for s in slugs if s and s in S.ent_by_slug],
                                track="guide_click", key="g:" + g["id"]))
    tiers.append((cards, caps["guide"]))
    vids = [v for v in getattr(S, "videos", None) or [] if v.get("published_date")
            and 0 <= (today - dt.date.fromisoformat(v["published_date"][:10])).days <= NEWS_VIDEO_DAYS]
    vids.sort(key=B.video_rank)
    tiers.append(([_news_card(S, "video", squash_ws(v.get("title")), v["url"], when=dot_date(v["published_date"][:10]),
                              when_iso=v["published_date"][:10], sub=squash_ws(v.get("channel")), ext=True,
                              lang=v["lang"] if v.get("lang") not in (None, "", "ko") else "", track="video_click",
                              key="v:" + v["youtube_id"]) for v in vids], caps["video"]))
    out = [c for tier, cap in tiers for c in tier[:cap]]
    for tier, cap in tiers:
        for c in tier[cap:]:
            if len(out) >= NEWS_MIN:
                break
            out.append(c)
    out = out[:NEWS_MAX]
    slots = art.for_lang(getattr(S, "art", None) or {}, "ko")
    dish = romanize_slug(focus["dish"]) if focus else ""
    used: set[str] = set()
    for i, c in enumerate(out):
        c["photo"] = news_photo(c.pop("places"), used)
        if i == 0 and c["photo"] and not (c["photo"]["type"] == 1 and c["photo"].get("avif")):
            c["photo"] = None    # the first slide is the home's LCP: no heavy original there (see the note below)
        if c["photo"]:
            used.add(c["photo"]["url"])
        if not (c["photo"] or c["og"]):
            c["art"] = (slots.get(f"home.card.festival-{dish}") if c["kind"] == "festival" else None) \
                or (slots.get("events.kind." + c["ev_kind"]) if c["ev_kind"] else None) \
                or slots.get("home.card." + ("event" if c["kind"] == "festival" else c["kind"]))
    # The first slide (review 2026-10-14): its picture is the home's LCP and is preloaded, so it is a KOGL-1 photo
    # with a local AVIF derivative or the card's art (local, light) — a KOGL-3 original (940w, ~470 KB from the
    # provider) made LCP 5.8 s. The original is never re-encoded smaller (CLAUDE.md 3.4) and the ranking order stays.
    return out


def romanize_slug(word: str) -> str:
    """'짬뽕' -> 'jjamppong' (Revised Romanization, lower case, letters and digits only): an art slot's name part."""
    from .en_source import romanize
    return re.sub(r"[^a-z0-9]+", "-", romanize(word).lower()).strip("-")


def home_opening(S) -> dict:
    """The opening's words that follow the build date: the kicker '지금 <region> · 10월' (the photo is the configured
    cover, h.cover)."""
    region = S.site.get("region") or S.site.get("locality", "")
    return {"kicker": f"지금 {region} · {int(S.today[5:7])}월"}


def home_services(S, n_events: int = 0) -> list[dict]:
    """The round service icons under the opening: each list or page this build has, with its count where it has
    one ({label, href, icon, n, unit, track, core}). Operator 2026-10-15 (mobile UX review): the four a traveller
    needs first lead — 가볼만한 곳, 맛집, 숙소, 가는 법 (core=True: one row of four larger tiles on phones) — then
    코스, 지도, 행사 달력, 영상, 해외에서 본 <city> (a compact row under them on phones; one row of all of them from
    1024px, as before)."""
    gm = {g["id"]: g for g in S.guides}
    way = home_answer_default()   # the city's 'how to get here' guide (city.home.answer_default)
    lists = S.lists
    abroad = sum(a.get("kind") == "article" for a in getattr(S, "abroad", None) or [])
    rows = [("가볼만한 곳", "/places/", "pin", len(lists.get("attraction") or []), "곳", "", True, True),
            ("맛집", "/food/", "bowl", len(lists.get("food") or []), "곳", "", bool(lists.get("food")), True),
            ("숙소", "/stays/", "bed", len(lists.get("stay") or []), "곳", "", bool(lists.get("stay")), True),
            ("가는 법", gm[way[1]]["_path"] if way and way[1] in gm else "", "bus", 0, "",
             "guide_click", bool(way and way[1] in gm), True),
            ("코스", "/courses/", "route", len(S.courses), "개", "course_click", bool(S.courses), False),
            ("지도", "/map/", "map", 0, "", "", bool(S.entities), False),
            ("행사 달력", "/events/", "calendar", n_events, "건", "", bool(S.events), False),
            ("영상", "/videos/", "play", len(getattr(S, "videos", None) or []), "편", "", bool(getattr(S, "videos", None)),
             False),
            (f"해외에서 본 {S.site.get('region', '')}", "/abroad/", "globe", abroad, "건", "",
             bool(getattr(S, "abroad", None) or getattr(S, "abroad_videos", None)), False)]
    pics = {"/food/": "icon-food", "/stays/": "icon-stay", "/places/": "icon-sights", "/courses/": "icon-course",
            "/events/": "icon-events", "/map/": "icon-map", "/videos/": "icon-video", "/abroad/": "icon-abroad"}
    return [{"label": label, "href": href, "icon": icon, "n": n, "unit": unit, "track": track, "core": core,
             "pic": pics.get(href, "icon-getting-here")}   # the 3D picture's ID (pipeline/icons.py, _pic.html.j2)
            for label, href, icon, n, unit, track, ok, core in rows if ok and href]


# '처음 가는 <city>' on the home's first screen: the guide whose title starts with these words (the whole-city overview,
# its places by 권역); without such a guide the entry is the guide index
FIRST_VISIT_TITLE = "{region} 가볼만한 곳"


def home_starts(S) -> list[dict]:
    """The home's three situational entries under its two actions (operator-forwarded evaluation 2026-10-18), words
    only ({label, href, track}): '처음 가는 <city>' (the FIRST_VISIT_TITLE guide, else /guides/), '내 조건으로 코스
    만들기' (/plan/, the AI planner) and '지도에서 찾기' (/map/, every place by 권역 on one map — no 'near me': the
    page has no location of the reader; review 2026-10-18). /plan/ and /map/ are built when the site has places
    (build.common has_plan, has_map: the same rule); an entry whose page this build does not write is left out."""
    region = S.site.get("region") or S.site.get("locality", "")
    want = FIRST_VISIT_TITLE.format(region=region)
    first = next((g for g in S.guides if squash_ws(g.get("title")).startswith(want)), None)
    rows = [(f"처음 가는 {region}", first["_path"] if first else "/guides/", "guide_click", bool(S.guides)),
            ("내 조건으로 코스 만들기", "/plan/", "plan_cta", bool(S.entities)),
            ("지도에서 찾기", "/map/", "", bool(S.entities))]
    return [{"label": label, "href": href, "track": track} for label, href, track, ok in rows if ok]


# ----------------------------------------------------------------------------- events
TEXT_DATE = re.compile(r"(20\d\d)\s*\.\s*(\d{1,2})\s*\.\s*(\d{1,2})")
DAYS_KO = {2: "이틀", 3: "사흘", 4: "나흘", 5: "닷새"}


def norm_period(text: str | None) -> str:
    t = squash_ws(text)
    t = re.sub(r"\(\s*([^()]*?)\s*\)", r"(\1)", t)
    return t.replace("~", "–") if re.search(r"\d\s*~\s*\d", t) else t


def event_row(ev: dict) -> dict:
    """One edition as a ticket row. A date written only in the text ('2025.5.28(수) 18:30~') sorts as that day,
    so it lands under 지난 회차 or 진행·예정 like a dated record (text_dated=True)."""
    from . import build as B
    sr = ev.get("_series") or {}
    start, end = ev.get("start_date") or "", ev.get("end_date") or ev.get("start_date") or ""
    period = squash_ws(ev.get("period_text"))
    text_dated = False
    if not start and "매년" not in period:
        m = TEXT_DATE.search(period)
        if m:
            start = end = f"{m.group(1)}-{int(m.group(2)):02d}-{int(m.group(3)):02d}"
            text_dated = True
    rng = ""
    if start:
        rng = short_date(start) + ("–" + short_date(end) if end and end != start else "")
        if not ev.get("end_date") and re.fullmatch(r"\d{4}-\d{2}", ev.get("end_month") or ""):
            rng += f"–{int(ev['end_month'][5:])}월"
    last = (B.event_last_day(ev) if ev.get("start_date") else end) or ""
    place = city.current().strip_prefix(ev.get("place_name")).strip()
    time, fee = dash_times(squash_ws(ev.get("playtime"))), squash_ws(ev.get("fee"))
    # a value another source gives differently is not picked in a one-line row (CLAUDE.md 3.2): the row reads
    # '<label> 출처마다 다름' and the event page shows both values with their sources
    contested_fields = sorted(f for f, vals in (ev.get("alternatives") or {}).items() if vals)
    if "period" in contested_fields and rng:
        rng = "기간 출처마다 다름"
    if "place_name" in contested_fields and place:
        place = "장소 출처마다 다름"
    if "playtime" in contested_fields and time:
        time = "시간 출처마다 다름"
    if "fee" in contested_fields and fee:
        fee = "요금 출처마다 다름"
    return {"ev": ev, "name": B.YEAR_PREFIX.sub("", squash_ws(ev.get("name"))), "title": squash_ws(ev.get("name")),
            "range": rng, "start": start, "end": end, "last": last, "year": start[:4], "place": place,
            "time": time, "fee": fee, "contested": contested_fields,
            "path": sr.get("_path", ""), "period_text": norm_period(period), "text_dated": text_dated,
            "source": squash_ws(ev.get("source_name")), "source_url": ev.get("source_url") or "",
            "checked": ev.get("checked_at") or ""}


SEASON_DAYS = 92   # /events/ 'held around this time': the next three months of the year


def season_ahead(start: str, today: str) -> int | None:
    """Days from `today` to the same day of the year as `start` (ISO dates), when `start` is one or two years back
    and that day comes within SEASON_DAYS; else None."""
    d, t = dt.date.fromisoformat(start[:10]), dt.date.fromisoformat(today[:10])
    if not 1 <= t.year - d.year <= 2:
        return None
    same_day = [dt.date(y, d.month, 28 if (d.month, d.day) == (2, 29) else d.day) for y in (t.year, t.year + 1)]
    ahead = next((x - t).days for x in same_day if x >= t)
    return ahead if ahead <= SEASON_DAYS else None


def season_rows(S) -> list[dict]:
    """The series whose newest dated edition — one or two years ago, nothing newer dated — began in the next
    SEASON_DAYS of the year (review 2026-10-17: two events on the calendar for a reader looking for festivals). The
    edition as it was, with its year; the page says this year's dates are not in the data yet, never that it will
    be held. Soonest first."""
    from . import build as B
    out = []
    for sr in S.series:
        ev = sr["newest"]
        if not ev.get("start_date") or B.event_last_day(ev) >= S.today:
            continue
        ahead = season_ahead(ev["start_date"], S.today)
        if ahead is None:
            continue
        # the year is in the title the series gives its newest edition ('2025 어촌 섬마을 장터', build._title)
        out.append((ahead, {**event_row(ev), "title": ev.get("_title") or squash_ws(ev.get("name"))}))
    return [r for _, r in sorted(out, key=lambda x: (x[0], x[1]["title"]))]


def events_vm(S) -> dict:
    """/events/: editions still running or to come (by month), the series held around this time in an earlier year
    (season_rows), finished ones by month (newest first), the '매년 …' records (only text that says 매년, period as
    sourced) and records with no date at all. A month's mm ('05') names its AI art picture (events.month.<mm>)."""
    rows = [event_row(ev) for ev in S.events]
    upcoming = sorted([r for r in rows if r["start"] and r["last"] >= S.today], key=lambda r: r["start"])
    past = sorted([r for r in rows if r["start"] and r["last"] < S.today], key=lambda r: r["start"], reverse=True)

    def by_month(xs, prefix):
        months: dict[str, list] = {}
        for r in xs:
            months.setdefault(r["start"][:7], []).append(r)
        return [{"title": f"{int(ym[:4])}년 {int(ym[5:])}월", "id": f"{prefix}-{ym}", "rows": v, "mm": ym[5:7]}
                for ym, v in months.items()]

    textonly = [r for r in rows if not r["start"] and "매년" not in r["period_text"]]
    year = int(S.today[:4])
    # an undated record whose text names an earlier year ('2025년 가을') is a past edition too
    old = [r for r in textonly if (m := re.match(r"^(20\d\d)\s*년?", r["period_text"] or r["title"])) and int(m.group(1)) < year]
    up = by_month(upcoming, "u")
    ranked = ranked_events(S)
    return {"ranked": ranked, "next": pick_next_event(ranked),
            "up": up, "up_months": up, "upcoming": upcoming, "season": season_rows(S), "season_days": SEASON_DAYS,
            "months": by_month(past, "m"), "past": past,
            "past_undated": old, "annual": [r for r in rows if not r["start"] and "매년" in r["period_text"]],
            "textonly": [r for r in textonly if r not in old],
            "series": S.series, "n_records": len(rows), "n_series": len(S.series)}


def short_src(name: str | None) -> str:
    """An event source's short name: 한국관광공사, the city's press releases (city.official.press), 행사 누리집, the
    city (city.official.short), else the name as given."""
    n = squash_ws(name)
    C = city.current()
    if "TourAPI" in n or "한국관광공사" in n:
        return "한국관광공사"
    if "보도자료" in n:
        return C.official["press"]
    if "누리집" in n or "홈페이지" in n:
        return "행사 누리집"
    if C.is_official(n):
        return C.official["short"]
    return n


def ev_period(x: dict) -> Markup:
    """'2026년 10월 9일(금)–10월 11일(일)' with <time>; a source that gives only an end month reads '–10월'."""
    from . import build as B
    start, end = x.get("start_date") or "", x.get("end_date") or ""
    if not start:
        return escape(norm_period(x.get("period_text")))
    html = Markup(f'<time datetime="{escape(start)}">{escape(B.ko_date(start))}</time>')
    if end and end != start:
        html += Markup(f'–<time datetime="{escape(end)}">{escape(B.ko_date(end, with_year=end[:4] != start[:4]))}</time>')
    elif not end and re.fullmatch(r"\d{4}-\d{2}", x.get("end_month") or ""):
        em = x["end_month"]
        html += escape(f"–{em[:4] + '년 ' if em[:4] != start[:4] else ''}{int(em[5:])}월")
    return html


ORGANISER_LINE = "방문 전 주최 측 확인"


def event_vm(S, sr: dict) -> dict:
    """An event series page: the newest dated edition in the place-page skeleton. A value another source gives
    differently sits in the same row with both providers (provider header per block), plus one
    '방문 전 주최 측 확인' line (CLAUDE.md 3.2). Programme highlights, '보통 언제 열리나' (usual), other
    editions' differing values, past and undated editions, videos."""
    from . import build as B
    ev = sr["newest"]
    notes = Notes()
    src = {"provider": ev.get("source_name") or "", "checked_at": ev.get("checked_at") or "", "url": ev.get("source_url") or ""}
    alts = {f: vals for f, vals in (ev.get("alternatives") or {}).items() if vals}
    rows, flagged = [], False
    # the call number on the flag line and the header: not when the phone itself differs between sources
    tel_text, tel = ("", "") if alts.get("tel") else first_phone(ev.get("tel"))

    def add(label, text, html, field):
        nonlocal flagged
        row = {"label": label, "field": field, "text": text, "html": html, "n": notes.ref(src, label), "blocks": [],
               "flag": False, "tel": None}
        if alts.get(field):
            row["blocks"] = [{"provider": short_src(src["provider"]), "provider_full": src["provider"], "n": row["n"],
                              "text": text, "html": html}]
            for a in alts[field]:
                a_src = {"provider": a.get("source_name") or "", "url": a.get("source_url") or "",
                         "checked_at": a.get("checked_at") or ""}
                a_text = squash_ws(a.get("value"))
                row["blocks"].append({"provider": short_src(a_src["provider"]), "provider_full": a_src["provider"],
                                      "text": a_text, "html": tel_markup(a_text) if field == "tel" else escape(a_text),
                                      "n": notes.ref(a_src, label + "(다른 값)")})
            row["flag"] = True
            row["tel"] = (tel_text, tel) if tel and not flagged else None
            flagged = True
        rows.append(row)

    period_html = ev_period(ev)
    add("기간", squash_ws(re.sub(r"<[^>]+>", "", str(period_html))), period_html, "period")
    if ev.get("playtime"):
        t = dash_times(squash_ws(ev["playtime"]))
        add("시간", t, escape(t), "playtime")
    if ev.get("fee"):
        add("요금", squash_ws(ev["fee"]), escape(squash_ws(ev["fee"])), "fee")
    if ev.get("place_name"):
        add("장소", squash_ws(ev["place_name"]), escape(squash_ws(ev["place_name"])), "place_name")
    if ev.get("address"):
        a = display_address(ev["address"])
        add("주소", a, nowrap_numbers(a), "address")
    if ev.get("sponsor"):
        add("주최", squash_ws(ev["sponsor"]), escape(squash_ws(ev["sponsor"])), "sponsor")
    if ev.get("tel"):
        add("문의", squash_ws(ev["tel"]), tel_markup(squash_ws(ev["tel"])), "tel")
    if ev.get("homepage"):
        url = web_url(ev["homepage"])
        if url:
            add("홈페이지", web_text(url), Markup(f'<a href="{escape(url)}" rel="noopener" data-track="official_click">'
                                                f'{escape(web_text(url))}</a>'), "homepage")
    for a in ev.get("also_sources") or []:
        notes.ref({"provider": a.get("name") or "", "checked_at": a.get("checked_at") or "", "url": a.get("url") or ""},
                  "같은 일정 확인" if a.get("agrees") else "함께 확인")
    places = [S.ent_by_slug[x] for x in sr["place_slugs"] if x in S.ent_by_slug]
    geo = ev.get("geo") or {}
    row = event_row(ev)
    point = {"self": {"lat": geo["lat"], "lng": geo["lng"], "name": row["place"] or sr["name"]}, "near": [], "anchors": []} \
        if geo.get("lat") is not None and geo.get("lng") is not None else None
    route = (f"https://map.kakao.com/link/to/{quote(squash_ws(ev.get('place_name')) or sr['name'], safe='')},"
             f"{geo['lat']},{geo['lng']}") if point else ""
    start = ev["start_date"]
    last = B.event_last_day(ev) or start
    ndays = (dt.date.fromisoformat(last) - dt.date.fromisoformat(start)).days + 1
    bits = []
    if ev.get("end_date") and "period" not in alts:
        bits.append(f"{DAYS_KO.get(ndays, f'{ndays}일')} 동안 열리는 행사입니다." if ndays > 1 else "하루 열리는 행사입니다.")
    if ev.get("sponsor") and "sponsor" not in alts:
        bits.append(f"주최는 {squash_ws(ev['sponsor'])}입니다.")
    past = [event_row(x) for x in sr["past"]]
    if past and past[0]["start"]:
        bits.append(f"지난 회차는 {int(past[0]['start'][:4])}년 {int(past[0]['start'][5:7])}월에 열렸습니다.")
    prog = sr.get("program")
    program = None
    if prog:
        program = {"items": [squash_ws(h) for h in prog.get("highlights") or [] if squash_ws(h)],
                   "notes": [squash_ws(n) for n in prog.get("notes") or [] if squash_ws(n)],
                   "basis": squash_ws(prog.get("name")) if prog is not ev else "",
                   "src": [{"name": prog.get("source_name") or "", "url": prog.get("source_url") or ""}] +
                          [{"name": a.get("name") or "", "url": a.get("url") or ""}
                           for a in prog.get("also_sources") or [] if not a.get("agrees")]}
    usual = [{"text": squash_ws(u.get("text")), "place": squash_ws(u.get("place")), "src": short_src(u.get("source_name")),
              "name": u.get("source_name") or "", "url": u.get("source_url") or "", "checked": u.get("checked_at") or ""}
             for u in sr.get("usual") or []]
    other_alts = [{"name": squash_ws(r["ev"].get("name")), "label": r["label"],
                   "main": squash_ws(r["ev"].get(r["field"])) if r["field"] != "period" else str(ev_period(r["ev"])),
                   "main_src": short_src(r["ev"].get("source_name")),
                   "values": [{"value": squash_ws(a.get("value")), "src": short_src(a.get("source_name")),
                               "url": a.get("source_url") or ""} for a in r["values"]]}
                  for r in sr.get("alternatives") or [] if r["ev"] is not ev]
    # status line: the period, the time and the fee as the rows show them (a value another source gives
    # differently is flagged, not picked)
    status = []
    for r in rows:
        if r["field"] in ("period", "playtime", "fee"):
            text = f"{r['label']} 출처마다 다름" if r["flag"] else r["text"]
            status.append({"key": r["field"], "text": text, "html": escape(text), "closed": False,
                           "cls": "st-flag" if r["flag"] else "", "href": "#h-facts" if r["flag"] else ""})
    # Apple first screen: the date big (dp), the relative chip of the ranked list, five tiles (기간 · 시간 · 요금 · 장소 ·
    # 문의 — a value another source gives differently reads '<label> 출처마다 다름'; the facts show both), '확인 필요'
    # for a slot the sources leave empty, the route row (front: 네이버 지도, 카카오맵 by coordinates) and the first
    # programme highlight as a second lede
    rk = next((x for x in ranked_events(S) if x["ev"] is ev), None)
    by_field = {r["field"]: r for r in rows}
    place_short = city.current().strip_prefix(ev.get("place_name")).strip()

    def tile(label, field, html):
        r = by_field.get(field)
        if r and r["flag"]:
            return {"label": label, "field": field, "html": Markup('<span class="flag">출처마다 다름</span>'), "flag": True}
        return {"label": label, "field": field, "html": html, "flag": False}
    slots = [tile("기간", "period", Markup(f'<time datetime="{escape(start)}">{escape(row["range"] or row["period_text"])}</time>'))]
    if ev.get("playtime"):
        slots.append(tile("시간", "playtime", Markup(f'<span class="nw">{escape(dash_times(squash_ws(ev["playtime"])))}</span>')))
    if ev.get("fee"):
        slots.append(tile("요금", "fee", escape(squash_ws(ev["fee"]))))
    if place_short:
        slots.append(tile("장소", "place_name", escape(place_short)))
    if tel:
        slots.append(tile("문의", "tel", Markup(f'<a class="tel" href="tel:{tel}" data-track="tel_click">{escape(tel_text)}</a>')))
    need = [lab for lab, k in (("시간", "playtime"), ("요금", "fee")) if not ev.get(k)]
    if B.event_end_month(ev):   # the source names only the end month (CLAUDE.md 3.1: the day is not filled in)
        need.insert(0, "끝나는 날")
    front = []
    if point:
        nm = place_short or sr["name"]
        region = S.site.get("region", "")
        front = [{"label": "네이버 지도", "url": f"https://map.naver.com/p/search/{quote(f'{region} {nm}'.strip(), safe='')}",
                  "key": "naver", "role": "map", "precise": False},
                 {"label": "카카오맵", "url": f"https://map.kakao.com/link/map/{quote(nm, safe='')},{geo['lat']},{geo['lng']}",
                  "key": "kakao", "role": "map", "precise": True}]
    apple = {"chip": rk["chip"] if rk else "", "dp": date_parts(row) if row["start"] else None, "slots": slots,
             "need": need, "front": front, "place_short": place_short,
             "lede2": squash_ws((prog or {}).get("highlights", [""])[0]) if prog and prog.get("highlights") else ""}
    return {**apple, "sr": sr, "ev": ev, "title": ev["_title"], "answer": B.event_answer(ev), "lede": " ".join(bits),
            "status": status, "also": [a for a in ev.get("also_sources") or [] if squash_ws(a.get("name"))],
            "linked_cid": str(ev.get("tourapi_contentid") or ""), "ev_notes": [squash_ws(n) for n in ev.get("notes") or []
                                                                               if squash_ws(n)],
            "recurring": bool(ev.get("recurring")),
            "rows": rows, "notes": notes.items, "places": places, "point": point, "route": route,
            "tel": tel, "tel_text": tel_text, "past": past, "undated": [event_row(x) for x in sr["undated"]],
            "videos": [v for v in sr.get("videos") or [] if v.get("youtube_id")], "program": program, "usual": usual,
            "other_alts": other_alts, "flagged": flagged or bool(other_alts),
            "confirm_line": ORGANISER_LINE if (flagged or other_alts) else "",
            "area": B.area_from_address(ev.get("address")),
            "where": city.current().place_short(city.current().district_of(ev.get("address")),
                                                B.area_from_address(ev.get("address")))}


# ----------------------------------------------------------------------------- guide reading layer
# Owner 2026-10-09: guide pages read as walls of prose ("AI가 읽기는 좋겠지만 사람이 읽기에는 불편"). Every sentence of a
# guide stays in the HTML, verbatim and in order (AI fetchers and pipeline.validate read it); a scannable layer is
# added on top: the summary's first sentence as the answer line, the body as sentence bullets, figures emphasised
# (bold + marker), the guide's places linked and shown as mini cards. None of this writes a word of its own: the
# markup only wraps spans of the guide's text (rich() keeps the text character for character; tests check it).
_NUM = r"\d[\d,]*(?:\.\d+)?"
EMPH_KO = re.compile(
    r"(?<![\d.,A-Za-z])(?:"
    r"\d{1,2}:\d{2}(?:\s?[~–-]\s?\d{1,2}:\d{2})?"                       # 10:00 · 10:00~19:00
    r"|\d+시간(?:\s?\d+분)?"                                              # 2시간30분 · 3시간 5분
    r"|\d+(?:[·~]\d+)*번"                                                 # bus numbers 01·18·19번 · 11~19·61번
    rf"|{_NUM}(?:\s?[~–-]\s?{_NUM})?(?:여\s?)?"
    r"(?:개월|km|cm|kg|㎡|m(?![A-Za-z])|원|세|대|곳|분|회|명|개|실))"
    r"|(?:[월화수목금토일][·~])*[월화수목금토일]요일")                      # 월요일 · 월·화요일 · 화~일요일
EMPH_EN = re.compile(
    r"(?<![\w.,])(?:"
    r"\d{1,2}:\d{2}(?:\s?[–~-]\s?\d{1,2}:\d{2})?"
    r"|\d+\s?hours?(?:\s(?:and\s)?\d+\s?minutes?)?"
    rf"|{_NUM}(?:\s?[–~-]\s?{_NUM})?\s?"
    r"(?:won|km|m²|cm|kg|minutes?|mins?|months?|years?\sold|places|restaurants|rooms|cars|vehicles|pieces|times|trips"
    r"|people|lodgings|inns|hotels|motels|guesthouses|pensions|homestays|stays|eateries|attractions|spots|sites"
    r"|islands|stops|seats|tables|m)(?![A-Za-z²])"
    # the Korean 곳/번/세 figures in English: '23 lodgings', 'bus 7, 8 or 9' (01·18·19번), '6 and under' (6세 이하)
    r"|(?:bus(?:es)?|route)\s\d+(?:(?:,\s|,?\sor\s|,?\sand\s)\d+)*(?!\d|,\d)"
    r"|\d+\sand\s(?:under|over|up|older|younger)\b"
    r"|ages?\s\d+(?:\s?[–-]\s?\d+)?(?!\d)(?!\s?months?\b)(?:\sand\s(?:under|over|up))?)"   # 'ages 18 months': 18 months
    r"|\b(?:Mon|Tues|Wednes|Thurs|Fri|Satur|Sun)days?\b")
# the other versions (pipeline/en_site.py, locale codes): times, and figures with a unit their translations write
EMPH_INTL = re.compile(
    r"(?<![\d.,])(?:\d{1,2}:\d{2}(?:\s?[–~-]\s?\d{1,2}:\d{2})?"
    rf"|\d[\d,.\u202f\u00a0]*(?:\s?[–-]\s?\d[\d,.\u202f\u00a0]*)?\s?(?:km|m²|m(?![A-Za-zА-Яа-я])|%|ウォン|韩元|韓元|Won|wones|wons|вон))")
CJK_LANGS = ("ja", "zh-hans", "zh-hant")   # sentences join without a space
SENT_KO = re.compile(r"(?<=[.!?])\s+")
# the validator compares the first 25 characters of a summary / FAQ answer with the JSON-LD as one text run
# (pipeline.validate.jsonld_visibility), so markup never starts inside them
PLAIN_HEAD = 25


def ko_sentences(text: str | None) -> list[str]:
    """Sentences as present.decaution cuts them (after . ! ?): joined with one space they are the text again."""
    return [s for s in SENT_KO.split(squash_ws(text)) if s]


def _name_rx(names: list[dict], lang: str):
    alts = "|".join(re.escape(n["name"]) for n in sorted(names, key=lambda n: -len(n["name"])) if n.get("name"))
    if not alts:
        return None
    return re.compile(rf"(?<![가-힣A-Za-z0-9])(?:{alts})" if lang == "ko" else rf"(?<![A-Za-z0-9])(?:{alts})(?![A-Za-z0-9])")


def mentions(text: str | None, names: list[dict], lang: str = "ko") -> list[dict]:
    """The guide places named in the text, in order of first mention (each once)."""
    rx = _name_rx(names, lang)
    if not rx:
        return []
    by = {n["name"]: n for n in names}
    out = []
    for m in rx.finditer(str(text or "")):
        n = by.get(m.group(0))
        if n and n not in out:
            out.append(n)
    return out


def rich(text: str | None, lang: str = "ko", names: list[dict] | None = None, seen: set | None = None,
         skip: int = 0, roll: bool = False, links: bool = True) -> Markup:
    """The guide's own text with its figures emphasised (<b class="gk">), the first mention of each guide place
    linked (names [{name, path, id}]; `seen` carries the ids already linked in this section), phone numbers as
    tap-to-call links (+82 on the other versions: tel_href) and the official hosts it writes as links (OFFICIAL_WEB;
    the other versions' entry page where there is one). The text of the result is `text`, character for character.
    skip: the first characters stay one plain run (PLAIN_HEAD). roll: a figure with digits gets data-numroll
    (motion.js: its own digits roll into place once it scrolls in — never a count from 0, which would show numbers
    that are not in the data)."""
    t = str(text or "")
    taken: list[tuple[int, int]] = [(0, skip)] if skip else []
    spans: list[tuple[int, int, str, object]] = []

    def free(a: int, b: int) -> bool:
        return not any(a < y and x < b for x, y in taken)

    rx = _name_rx(names or [], lang) if names else None
    by = {n["name"]: n for n in names or []}
    if rx:
        for m in rx.finditer(t):
            n = by.get(m.group(0))
            a, b = m.span()
            if not free(a, b):
                continue
            taken.append((a, b))   # a name is never emphasised inside, linked or not
            if links and n.get("path") and (seen is None or n["id"] not in seen):
                spans.append((a, b, "place", n))
                if seen is not None:
                    seen.add(n["id"])
    for m in web_rx().finditer(t):
        a, b = m.span()
        if free(a, b):
            taken.append((a, b))
            spans.append((a, b, "web", m))
    for m in PHONE.finditer(t):
        a, b = m.span(1)
        if free(a, b):
            taken.append((a, b))
            spans.append((a, b, "tel", m.group(1)))
    for m in (EMPH_EN if lang == "en" else EMPH_KO if lang == "ko" else EMPH_INTL).finditer(t):
        a, b = m.span()
        if free(a, b):
            taken.append((a, b))
            spans.append((a, b, "fig", m.group(0)))
    out, last = [], 0
    for a, b, kind, v in sorted(spans, key=lambda s: s[0]):
        out.append(escape(t[last:a]))
        seg = escape(t[a:b])
        if kind == "place":
            out.append(Markup('<a class="gl" href="{}" data-track="nearby_click" data-place="{}">{}</a>').format(v["path"], v["id"], seg))
        elif kind == "tel":
            out.append(Markup('<a class="tel" data-track="tel_click" href="tel:{}">{}</a>').format(tel_href(v, lang != "ko"), seg))
        elif kind == "web":
            out.append(web_anchor(seg, web_href(v.group(1), v.group(2), lang != "ko")))
        else:
            r = Markup(" data-numroll") if roll and re.search(r"\d", v) else Markup("")
            out.append(Markup('<b class="gk"{}>{}</b>').format(r, seg))
        last = b
    out.append(escape(t[last:]))
    return Markup("").join(out)


def answer_size(text: str) -> str:
    """The answer line's type size by its length: a short answer is set big, a long one smaller."""
    n = len(text)
    return "a-xl" if n <= 40 else "a-l" if n <= 90 else "a-m" if n <= 170 else "a-s"


# an English sentence that leans on the one before it ('They include…', 'It uses…', 'There is an elevator…') stays in
# that bullet: one bullet per sentence would cut a pronoun off from what it points to (review 2026-10-09)
EN_LEAN = re.compile(r"^(?:They|It|Its|This|These|There|Their|That|Those)\b")


def points_list(text: str, split, lang: str = "ko") -> list[str]:
    """A paragraph as bullets: split(text) must return sentences that, joined with spaces, are the text; in English a
    sentence that starts with a pronoun joins the bullet before it (joined with a space: still the text)."""
    out: list[str] = []
    for s in split(squash_ws(text)):
        if not s:
            continue
        if lang == "en" and out and EN_LEAN.match(s):
            out[-1] = f"{out[-1]} {s}"
        else:
            out.append(s)
    return out


def guide_sections(heads_texts: list[tuple[str, list[str]]], names: list[dict], lang: str, split,
                   cards: dict, prefix: str = "", shown: set | None = None) -> list[dict]:
    """Body sections: {n, id, heading, paras [[Markup bullet]], own [bool per paragraph: lines that already start with
    a list mark keep it], places [mini cards named in the section, first time on the page], again [the section's
    places already shown as a mini card above (the answer card or an earlier section): a one-line row of name + one
    fact, not the whole card again], pts [the map ids of all of them]}. heads_texts = [(heading, [paragraph text])]
    with the text already as the page shows it (decaution for Korean). shown: the ids of the answer card's cards."""
    out = []
    shown = set(shown or ())
    for i, (head, paras) in enumerate(heads_texts, 1):
        seen: set = set()
        body = []
        for p in paras:
            sents = points_list(p, split, lang)
            if not sents:
                continue
            body.append([{"html": rich(s, lang, names, seen), "own": bool(re.match(r"^[·•‧]\s", s))} for s in sents])
        named = [cards[n["id"]] for n in mentions(head + " " + " ".join(paras), names, lang) if n["id"] in cards]
        places = [c for c in named if c["id"] not in shown]
        shown.update(c["id"] for c in places)
        out.append({"n": i, "id": f"{prefix}h-b{i}", "heading": head, "paras": body, "places": places,
                    "again": [c for c in named if c not in places], "pts": [c["slug"] for c in named if c.get("geo")]})
    return out


def answer_block(sents: list[str], lang: str = "ko") -> dict:
    """The answer card's text: the summary's first sentence as the answer line (html, sized by its length) and the
    rest after it (the owner's layout: answer line, the mini cards under it, the rest of the summary below them).
    Joined with a space, first and rest are the summary; markup never starts in its first PLAIN_HEAD characters
    (pipeline.validate compares them with the JSON-LD as one run)."""
    sep = "" if lang in CJK_LANGS else " "
    first, rest = (sents[0] if sents else ""), sep.join(sents[1:])
    return {"first": first, "rest": rest, "size": answer_size(first),
            "html": rich(first, lang, skip=PLAIN_HEAD, roll=True),
            "rest_html": rich(rest, lang, skip=max(0, PLAIN_HEAD - len(first) - len(sep)), roll=True)}


PICKS_MAX = 12
AGAIN_MAIN_MAX = 16   # the longest value a one-line row (ui.again) shows: '매주 월요일', '10:00~19:00', '성인 3,000원'


def answer_picks(summary: str, names: list[dict], cards: dict, lang: str = "ko", total: int | None = None) -> tuple[list[dict], int]:
    """The answer card's mini cards: the places the summary names first (in the order it names them), then the
    guide's other places in its own order, at most PICKS_MAX (a hub guide of 41 places shows 12 and points to the
    full list below); returns (cards, how many of the guide's list are not among them). total: the number of rows
    of the guide's place list (a place without a published page is a row there but has no card), so the card's
    count and the '외 n곳' tile agree with the list below."""
    order = [n["id"] for n in mentions(summary, names, lang)] + [n["id"] for n in names]
    seen, out = set(), []
    for i in order:
        if i in cards and i not in seen:
            seen.add(i)
            out.append(cards[i])
    shown = out[:PICKS_MAX]
    return shown, max(0, (len(out) if total is None else total) - len(shown))


def card_icons(picks: list[dict], sections: list[dict]) -> list[str]:
    """The icons the page's mini cards draw (cards without a photo), plus the shelf buttons': the sprite's symbols."""
    used = [c["icon"] for c in picks + [c for s in sections for c in s["places"]] if not c["photo"]]
    return list(dict.fromkeys(used)) + ["prev", "next"]


def guide_reading(summary: list[str], heads: list[tuple[str, list[str]]], names: list[dict], cards: dict, lang: str,
                  split, total: int) -> dict:
    """The reading layer of a guide (Korean guide_vm, English En.guide_vm): the answer block, the answer card's mini
    cards (picks; picks_total = the rows of the place list, picks_more = those not on the card), the body sections
    (a place gets its whole mini card once on the page: the answer card or its first section) and the icons drawn."""
    picks, more = answer_picks(" ".join(summary), names, cards, lang, total)
    sections = guide_sections(heads, names, lang, split, cards, shown={c["id"] for c in picks})
    return {"ans": answer_block(summary, lang), "picks": picks, "picks_more": more, "picks_total": total,
            "sections": sections, "icons": card_icons(picks, sections)}


def mini_card(e: dict, kf: dict, name: str, path: str, type_: str, area: str, photo: dict | None) -> dict:
    """A mini card (guide answer card, section rows): thumbnail or type icon, name, 'type · area', two key-fact
    chips — the first two of the kind's card slots that have a settled value (a value two sources give differently
    is not put in a chip: the place page and the guide's place list show both; nothing is picked). need: '확인 필요'
    labels when no slot has a value."""
    chips = [s for s in kf["slots"] if not s.get("missing") and not s.get("conflict")][:2]
    need = [s["label"] for s in kf["slots"] if s.get("missing")] if not chips else []
    # brief: the fact a later section's one-line row shows (ui.again) — the first chip whose main value is short
    # enough for one line (the value whole, never cut; a longer one is left to the card and the place list)
    brief = next(({"label": s["label"], "main": s["main"], "closed": bool(s.get("closed"))} for s in chips
                  if len(str(s.get("main") or "")) <= AGAIN_MAIN_MAX), None)
    return {"e": e, "id": e.get("id", ""), "slug": e.get("slug", ""), "name": name, "path": path, "type": type_,
            "area": area, "photo": photo, "chips": chips, "need": need, "brief": brief, "geo": bool(e.get("_geo")),
            "icon": (e.get("_visual") or ("", "pin"))[1]}


# ----------------------------------------------------------------------------- guides
def guide_vm(S, g: dict) -> dict:
    """A guide: label, title, lede + dek (contiguous summary), body sections, items (numbered; route order
    when the guide has a route), the walking route with straight-line legs, map points, week grid, FAQ."""
    items = []
    route_slugs = g.get("route_slugs") or []
    for it in g.get("items") or []:
        t = S.ent_by_slug.get(it.get("place_slug") or "")
        rn = route_slugs.index(it["place_slug"]) + 1 if it.get("place_slug") in route_slugs else None
        # a place that is not published (draft) keeps its name, without a link
        raw = t or next((e for e in S.entities_all if e.get("slug") == it.get("place_slug")), None) or {}
        items.append({"t": t, "name": squash_ws(raw.get("name") or it.get("name")), "reason": squash_ws(it.get("reason")),
                      "reason_html": tel_markup(squash_ws(it.get("reason"))), "route_n": rn,
                      "status": status_items(t) if t else [], "kf": key_facts(t, "card") if t else None, "path": t["_path"] if t else "",
                      "dong": t["_area"] if t else "", "type": t["_type"] if t else "",
                      "photo": thumb(t["_photos"][0]) if t and t["_photos"] else None,
                      "alt": t["_photos"][0]["alt"] if t and t["_photos"] else ""})
    for i, it in enumerate(items, 1):
        it["n"] = i
    route = None
    if route_slugs:
        stops = []
        for i, slug in enumerate(route_slugs, 1):
            t = S.ent_by_slug.get(slug)
            stops.append({"n": i, "name": t["name"] if t else slug, "t": t, "geo": t["_geo"] if t else None,
                          "path": t["_path"] if t else "", "prev_m": None})
        legs = []
        for a, b in zip(stops, stops[1:]):
            d = hav(a["geo"], b["geo"])
            b["prev_m"] = d
            legs.append(d)
        measured = [d for d in legs if d is not None]
        route = {"stops": stops, "total": sum(measured), "measured": len(measured), "possible": len(legs),
                 "complete": len(measured) == len(legs),
                 "show_total": bool(legs) and len(measured) >= MEASURED_SHARE * len(legs)}
    points = [{"lat": it["t"]["_geo"]["lat"], "lng": it["t"]["_geo"]["lng"], "name": it["name"],
               "n": it["route_n"] if route else it["n"], "url": it["path"], "extra": bool(route and not it["route_n"]),
               "id": it["t"]["slug"]}
              for it in items if it["t"] and it["t"]["_geo"]]
    ss = sentences(g.get("summary"))
    unique = list({it["t"]["slug"]: it["t"] for it in items if it["t"]}.values())
    fq = ChapterNotes({}, city.current().official["name"])
    faqs = [{"q": f["q"], "a": f["a"], "html": tel_markup(squash_ws(f["a"])), "n": fq.ref(f.get("source"))}
            for f in g.get("faq") or [] if f.get("q") and f.get("a")]
    # the reading layer: the summary as the page and the JSON-LD show it (decaution), cut into the answer line and
    # the rest; the body paragraphs as the page shows them, as sentence bullets with the guide's places linked
    names = [{"name": t["name"], "path": t["_path"], "id": t["id"]} for t in unique]
    cards = {t["id"]: mini_card(t, key_facts(t, "card"), t["name"], t["_path"], t["_type"], t["_area"],
                                thumb(t["_photos"][0]) if t["_photos"] else None) for t in unique}
    heads = []
    for b in g.get("body") or []:
        paras = [decaution(squash_ws(p)) for p in str(b.get("text") or "").split("\n") if p.strip()]
        heads.append((squash_ws(b.get("heading")), [p for p in paras if p]))
    reading = guide_reading(ko_sentences(decaution(g.get("summary"))), heads, names, cards, "ko", ko_sentences, len(items))
    return {**reading, "g": g, "label": g.get("label") or "", "title": g["title"], "lede": ss[0] if ss else "",
            "dek": " ".join(ss[1:]), "dek_html": tel_markup(" ".join(ss[1:])),
            "body": [{"heading": squash_ws(b.get("heading")), "text": squash_ws(b.get("text")),
                      "html": tel_markup(squash_ws(b.get("text")))} for b in g.get("body") or []],
            "places": items, "route": route, "points": points,
            "week": week_grid([t for t in unique if t["kind"] in ("attraction", "food")]),
            "caveat_said": "실제 이동 거리와 다릅니다" in (g.get("summary") or ""),
            "faqs": faqs, "faq_notes": fq.items, "sources": g.get("sources") or [], "checked": g.get("checked_at") or "",
            "answer": guide_answer(g, S),
            # 예약하기 (pipeline/booking.py): the booking services the guide cites, a box under the answer card
            "booking": booking.view(booking.guide_targets(S, g), "ko"), "bw": LC.BOOK_WORDS["ko"]}


# ----------------------------------------------------------------------------- map page
def map_vm(S) -> dict:
    """/map/: 권역 → 읍·면·동 groups (CLAUDE.md 7: the 읍·면·동 grouping with a 권역 view added; in a 광역시 the 동
    carries its 구·군: '중구 신포동'), the rule in force (region_rule_vm: anchors with counts and the far threshold, or
    the district lines). Ids carry no spaces. A group's art: the key of its AI art band (city region art)."""
    kind_order = {"attraction": 0, "stay": 1, "food": 2}
    arts = region_art()
    regions = []
    for rname in S.region_names:
        members = [e for e in S.entities if e["_region"] == rname]
        if not members:
            continue
        dongs: dict[str, list] = defaultdict(list)
        for e in members:   # a 광역시: '중구 운서동', or the 구·군 alone when the address names no 동
            dongs[" ".join(x for x in (e.get("_district"), e["_area"]) if x)].append(e)
        dong_groups = []
        for d, xs in sorted(dongs.items(), key=lambda kv: (kv[0] == "", -len(kv[1]), kv[0])):
            xs.sort(key=lambda e: (kind_order.get(e["kind"], 9), name_key(e["name"])))
            dong_groups.append({"name": d or "주소에 읍·면·동 없음", "id": f"d-{frag(rname)}-{frag(d or '없음')}",
                                "members": xs, "k": Counter(e["kind"] for e in xs)})
        regions.append({"name": rname, "id": "r-" + frag(rname), "art": arts.get(rname, ""),
                        "anchor": next((a for a in S.anchors if a["name"] == rname), None), "members": members,
                        "k": Counter(e["kind"] for e in members), "geo": sum(1 for e in members if e["_geo"]),
                        "dongs": dong_groups,
                        "basis": Counter(e["_region_basis"] for e in members)})
    n_by = {r["name"]: len(r["members"]) for r in regions}
    rule = region_rule_vm(S)
    # k_all: the kind toggles' counts (site.js keeps them to the chosen 권역); list_words: the list filters' Korean words
    # (the zero-result panel, the caption's places not on the map)
    return {"regions": regions, "anchors": [{**a, "n": n_by.get(a["name"], 0)} for a in S.anchors],
            "far_m": rule["far_m"], "far_label": rule["far_label"], "none_label": rule["none_label"], "rule": rule,
            "n_geo": sum(1 for e in S.entities if e["_geo"]), "n_all": len(S.entities),
            "n_dong": len({(e.get("_district"), e["_area"]) for e in S.entities if e["_area"]}),
            "k_all": Counter(e["kind"] for e in S.entities), "list_words": LC.LIST_WORDS["ko"]}


# ----------------------------------------------------------------------------- search
def menu_words(e: dict) -> str:
    f = e.get("facts") or {}
    words = [squash_ws(f.get(k)) for k in ("menu", "treatmenu") if squash_ws(f.get(k))]
    words += [squash_ws(a.get("value")) for a in (e.get("fact_alternatives") or {}).get("menu") or [] if squash_ws(a.get("value"))]
    return " · ".join(dict.fromkeys(words))


SEARCH_STRIP = re.compile(r"[\s·\-()（）\[\]|,]")   # what assets/search.js norm() ignores when matching

# The site search's query words (evaluation 2026-10-18: '비 오는 날 아이랑' found nothing although the site has a guide
# for rainy days and one for travelling with children; only the chat was offered). One row per concept a reader asks
# about: say — the words a reader types for it (Korean first; each written once with its spaces: search.js ignores
# spaces and ·-()[]|, as norm() does, so '비 오는' is '비오는' too), find — the words of the site's own titles,
# labels, names, dishes and types that stand for it. Every find word finds at least one row of the engine's first
# site's index (the sample city's in tests/test_present.py): the table points at real pages and never stands in for a
# page the site lacks.
# assets/search.js reads a said word as its concept: a row has the concept when it has any find word or the word as
# typed; a query of several concepts and words finds the rows that have every one of them, ranked by how many of the
# words they have; when none has, the guides whose title or label has one of the concepts follow as '관련 가이드',
# before those that have only a plain word of the query (form[data-concepts], search_form_data). A said word counts
# only as a word of the query, or with a particle, or next to another said word or a filler word in one
# ('비오는날아이랑'), never as a run inside a longer word (review 2026-10-18: '아이스크림', '버스킹' and '가족사진관'
# are no 아이, 버스, 가족). Built into every version's search page: the other versions' rows carry the Korean names
# (o), so a Korean query finds there too.
SEARCH_CONCEPTS = [
    # travelling with children: a guide '아이와 함께 …' (label 가족여행), the places named 어린이…, a 어린이 dish
    {"say": ["아이랑", "아이와", "아이", "아이들", "아이들과", "아이들이랑", "애들", "애들이랑", "애들과", "어린이", "키즈",
             "가족", "가족여행", "유아", "아기랑"],
     "find": ["아이와", "어린이", "가족"]},
    # rain: a guide '비 오는 날 … 실내 관광지 …' (label 비 오는 날)
    {"say": ["비 오는", "비 올 때", "비 오면", "비가 오면", "비가 오는", "비 와도", "우천", "우천시", "장마", "실내"],
     "find": ["비 오는", "실내"]},
    # no car: a guide '차 없이 …', the bus guides, a walking route ('걸어서', 도보 동선)
    {"say": ["차 없이", "뚜벅이", "대중교통", "버스", "시내버스", "자차 없이", "자가용 없이", "걸어서", "도보"],
     "find": ["차 없이", "시내버스", "시외버스", "고속버스", "걸어서", "도보"]},
    # where to eat: the food guides (맛집, 음식점, 식당, 먹거리 in their titles), 모범음식점 and the city's own list, places
    # named …식당
    {"say": ["맛집", "밥집", "식당", "음식점", "먹을 곳", "밥 먹을 곳", "먹거리"],
     "find": ["음식점", "맛집", "식당", "먹거리"]},
    # coffee: a café guide, the cafés and the places with a coffee on the menu
    {"say": ["카페", "커피", "커피숍", "찻집"], "find": ["카페", "커피"]},
    # parking: the guides that list it (주차 in their titles), a public car park guide
    {"say": ["주차", "주차장", "차 댈 곳", "차 세울 곳", "파킹"], "find": ["주차"]},
    # night: a night-view guide (label '… 야경') and the courses that stop at a night view
    {"say": ["야경", "밤", "야간", "밤 산책", "해 진 뒤"], "find": ["야경"]},
    # no entry fee: a guide '입장료 없이 둘러보는 …, 어디가 무료일까?'
    {"say": ["무료", "공짜", "무료입장", "입장료 없는", "입장료 없이"], "find": ["무료", "입장료 없이"]},
    # a bed for the night: the stay guides (숙소·펜션·민박 in their titles), the places typed 숙박업소 or …민박업
    {"say": ["숙소", "숙박", "잘 곳", "묵을 곳", "잠잘 곳"], "find": ["숙소", "숙박", "펜션", "민박"]},
]


def search_form_data(region: str, planner: str = "") -> dict:
    """The search form's data attributes for assets/search.js: concepts (SEARCH_CONCEPTS as JSON), region (the city's
    names, space-separated: a query word that only names the city is no condition — every row is in it — so '<city>
    짬뽕' finds the places with 짬뽕), planner (the AI course planner's path, Korean only: a query that plans a trip —
    dates, 코스, 일정, 당일, 1박 — links to it)."""
    out = {"concepts": json.dumps(SEARCH_CONCEPTS, ensure_ascii=False, separators=(",", ":")), "region": region}
    if planner:
        out["planner"] = planner
    return out


def other_names(row: dict, *names, key: str = "o") -> None:
    """row[key] = names joined with ' · ' (a search row's names in the other versions, or a course's stops there),
    in their order, without empty ones and without a name that search.js would find anyway: one inside the row's
    name or other names (n, a) or inside a longer name kept here ('○○축제' in '2026 ○○축제'), as
    search.js compares them (lower case, without spaces and ·-()[]|,). Left out when none remain. Used by
    search_index and by every other version's index (en_site Pages.search)."""
    def flat(s):
        return SEARCH_STRIP.sub("", s or "").lower()
    cand = list(dict.fromkeys(n for n in (squash_ws(x) for x in names if x) if flat(n)))
    have = [flat(row.get("n")), flat(row.get("a"))]
    keep = set()
    for n in sorted(cand, key=lambda n: -len(flat(n))):
        if not any(flat(n) in h for h in have):
            keep.add(n)
            have.append(flat(n))
    if keep:
        row[key] = " · ".join(n for n in cand if n in keep)


def search_index(S) -> list[dict]:
    """/search/index.json rows: n name, a other names, k kind, t type, d 동 (or road), r 권역, p path,
    m 대표 메뉴 + 취급 메뉴 (searched, weighted below the name), g official designations (schema.designations labels,
    searched below the menu), s the status line as text (result meta); o the names on the English version and v a
    course's stops there, when it is built (QA 2026-10-15: a romanised island name, 'jjamppong' find the same as the
    Korean name, 짬뽕 —
    the romanised names on signs and maps)."""
    en = getattr(S, "en", None)
    en_courses = en.courses if en else {}
    en_guides = en.guides if en else {}
    en_series = {x["slug"]: x for x in (en.series if en else [])}
    out = []
    for e in S.entities:
        row = {"n": e["name"], "a": " ".join(jsonld.alternate_names(e)), "k": e["kind"], "t": e["_type"],
               "d": e["_area"] or e.get("_road") or "", "r": e["_region"], "p": e["_path"]}
        other_names(row, (e.get("_en") or {}).get("name") if en else "")
        m = menu_words(e)
        if m:
            row["m"] = m
        ds = designations(e)
        if ds:  # '모범음식점', the city's own list name find the places on those lists
            row["g"] = " · ".join(d["label"] for d in ds)
        st = [x["text"] for x in status_items(e) if x.get("cls") != "st-missing"][:3]
        if e.get("_alias_of") is not None:   # a second page for one building says so in the result (pipeline/relations.py)
            st.insert(0, LC.NEAR_WORDS["ko"]["same_building"].format(name=e["_alias_of"]["name"]))
        if st:
            row["s"] = " · ".join(st)
        out.append(row)
    for c in S.courses:
        cv = S.course_vms[c["slug"]]
        row = {"n": cv["display"], "a": " ".join(s["name"] for s in cv["stops"]), "k": "course", "t": "코스",
               "d": "", "r": "", "p": c["_path"], "s": f"경유지 {cv['n_places']}곳"}
        x = en_courses.get(c["id"])
        if x:
            other_names(row, x["rec"].get("name"))
            other_names(row, *(s.get("name") for s in en.cv(x)["stops"]), key="v")
        out.append(row)
    for g in S.guides:
        row = {"n": g["title"], "a": g.get("label") or "", "k": "guide", "t": "가이드", "d": "", "r": "", "p": g["_path"]}
        x = en_guides.get(g["id"])
        other_names(row, x and x["rec"].get("title"))
        out.append(row)
    for sr in S.series:
        row = {"n": sr["name"], "a": "", "k": "event", "t": "행사", "d": "", "r": "", "p": sr["_path"]}
        x = en_series.get(sr["slug"])
        other_names(row, x and x["rec"].get("series_name"))
        out.append(row)
    return out


CHO = "ㄱㄲㄴㄷㄸㄹㅁㅂㅃㅅㅆㅇㅈㅉㅊㅋㅌㅍㅎ"
CHO_GROUP = {"ㄲ": "ㄱ", "ㄸ": "ㄷ", "ㅃ": "ㅂ", "ㅆ": "ㅅ", "ㅉ": "ㅈ"}
OTHER_INITIAL = "A–Z·숫자"


def initial(name: str) -> str:
    ch = (name or " ")[0]
    if "가" <= ch <= "힣":
        c = CHO[(ord(ch) - 0xAC00) // 588]
        return CHO_GROUP.get(c, c)
    return OTHER_INITIAL


def search_directory(S) -> list[dict]:
    """The no-JS answer of /search/: every place in 가나다 groups ({initial, id, places})."""
    groups: dict[str, list] = defaultdict(list)
    for e in sorted(S.entities, key=lambda e: name_key(e["name"])):
        groups[initial(e["name"])].append(e)
    order = sorted(groups, key=lambda k: (k == OTHER_INITIAL, k))
    return [{"initial": k, "id": "i-" + frag(k), "places": groups[k]} for k in order]


# ----------------------------------------------------------------------------- about, videos, common
def about_vm(S) -> dict:
    lic = Counter(((e.get("original") or {}).get("license") or "UNKNOWN") for e in S.entities
                  if (e.get("original") or {}).get("source_url"))
    return {"lic": lic, "img_lic": Counter(p["type"] for e in S.entities for p in e["_photos"]),
            "n_tourapi": sum(1 for e in S.entities if (e.get("tourapi") or {}).get("contentid")),
            "n_photo_places": sum(1 for e in S.entities if e["_photos"]), "n_all": len(S.entities),
            "n_thumb": sum(1 for e in S.entities for p in e["_photos"] if p["th"]),
            "n_sized": sum(1 for e in S.entities for p in e["_photos"] if p["w"])}


def video_groups_vm(groups: list[dict]) -> list[dict]:
    """build.video_groups() with `vids` instead of `items` (a Jinja dict key 'items' resolves to the method)."""
    return [{"id": "v-" + frag(g["title"]), "title": g["title"], "vids": g["items"], "slug": g.get("slug"),
             "path": g.get("_path"), "preview": g.get("preview") or g["items"]} for g in groups]


def nav_items(S) -> list[tuple[str, str]]:
    """[(label, href)] of NAV whose page this build writes (/places/ always; the others when they have data)."""
    built = {"attraction": True, "stay": bool(S.lists.get("stay")), "food": bool(S.lists.get("food")),
             "videos": bool(getattr(S, "videos", None)), "courses": bool(S.courses), "guides": bool(S.guides),
             "events": bool(S.events), "map": bool(S.entities), "abroad": bool(getattr(S, "abroad", None))}
    region = S.site.get("region") or S.site.get("locality", "")
    return [(label.format(region=region), href) for label, href, key in NAV if built[key]]


def common_vm(S) -> dict:
    """Shared by every page: the wordmark is site.json site_name (the owner's name decision lives there, CLAUDE.md 9;
    '<region> 여행' only when it is empty), nav, counts."""
    region = f"{S.site.get('region') or S.site.get('locality', '')} 여행".strip()
    return {"wordmark": (S.site.get("site_name") or "").strip() or region, "nav": nav_items(S),
            "counts": {k: len(v) for k, v in S.lists.items()}, "n_courses": len(S.courses),
            "n_guides": len(S.guides), "n_series": len(S.series), "n_videos": len(getattr(S, "videos", []) or [])}


CURRENT = {"plan": "/plan/", "place-attraction": "/places/", "places": "/places/", "theme": "/places/", "place-stay": "/stays/",
           "list-stay": "/stays/", "place-food": "/food/", "list-food": "/food/", "course": "/courses/",
           "courses": "/courses/", "guide": "/guides/", "guides": "/guides/", "events": "/events/", "map": "/map/",
           "search": "/search/", "about": "/about/", "videos": "/videos/", "abroad": "/abroad/"}


def page_chrome(page_kind: str, has_courses: bool) -> dict:
    """nav_current (the nav path to mark; `current` is taken by the events index) and ctxbtn, the contextual
    header button (CLAUDE.md 7: a place page offers 길찾기, a course its stop list, every other page the courses).
    The courses button reads '추천 코스' (operator-forwarded evaluation 2026-10-18: '코스 보기' beside 'AI 코스' did
    not say which courses — these are the city's own; the planner's door keeps its own name)."""
    if page_kind.startswith("place-"):
        btn = ("길찾기", "#h-dir")
    elif page_kind == "course":
        btn = ("경유지 목록", "#h-stops")
    else:
        btn = ("추천 코스", "/courses/") if has_courses else None
    return {"nav_current": CURRENT.get(page_kind, ""), "ctxbtn": btn}


# ----------------------------------------------------------------------------- the AI course planner (/plan/)
# Operator 2026-10-17: 'AI 여행 코스 생성기' on its own page, very visible, many cute 3D pictures. The page asks
# /api/plan/ (chatbot/planner.js) and draws the plan from the site's own place data (plan_places, /plan/places.json):
# the model's words are only the title, the summary, a reason per stop and the notes; every fact on a card is a value
# of the place's first screen, every photo a TourAPI KOGL-1/3 photo with its credit (CLAUDE.md 3.4), and a place with
# no photo gets its kind's 3D picture (never an illustration in a photo's place, CLAUDE.md 4).
KIND_PIC = {"bed": "kind-stay", "bowl": "kind-food", "museum": "kind-museum", "spark": "kind-experience",
            "building": "theme-modern-history", "wave": "theme-islands-sea", "tree": "theme-parks-nature",
            "lamp": "theme-alleys-culture", "pin": "kind-attraction", "cup": "kind-cafe"}   # _ui.html.j2 KIND_PIC


def plan_places(S) -> dict:
    """{path: {n name, k kind, t type, a area, r 권역, ic its kind's picture ID, img? {u, w, h, alt, t KOGL type, s/sw the
    provider's small copy},
    h hours, c closed days, f fee, m menu, p parking, ci check-in, g [lat, lng]}} for every published place — each
    value as the place's first screen shows it (key_facts 'hero'; both sources where they differ)."""
    out = {}
    for e in S.entities:
        slots = {s["key"]: s for s in key_facts(e, "hero")["slots"]}

        def val(k):
            s = slots.get(k)
            if not s or s.get("missing"):
                return ""
            if s.get("vals"):
                return " / ".join(squash_ws(f"{v.get('provider') or ''} {v.get('main') or ''}") for v in s["vals"])
            return " · ".join(x for x in (s.get("main"), s.get("sub")) if x)

        ph = e["_photos"][0] if e.get("_photos") else None
        th = thumb(ph) if ph else None
        geo = e.get("_geo") or {}
        row = {"n": e["name"], "k": e["kind"], "t": e.get("_type") or KIND_LABELS.get(e["kind"], ""),
               "a": e.get("_area") or "", "r": e.get("_region") if e.get("_region") != none_label() else "",
               "ic": KIND_PIC.get((e.get("_visual") or ("", "pin"))[1], "kind-attraction")}
        if ph:   # the provider's own file (KOGL-3 is never cropped: the card frames it whole), its small copy in srcset
            row["img"] = {"u": ph["url"], "w": ph["w"], "h": ph["h"], "alt": ph["alt"], "t": ph["type"],
                          **({"s": th["url"], "sw": th["w"]} if th and th["url"] != ph["url"] and th.get("w") else {})}
        for key, slot in (("h", "hours"), ("c", "closed"), ("f", "fee"), ("m", "menu"), ("p", "parking"), ("ci", "checkin")):
            v = val(slot)
            if v:
                row[key] = v
        if isinstance(geo.get("lat"), (int, float)) and isinstance(geo.get("lng"), (int, float)):
            row["g"] = [round(geo["lat"], 6), round(geo["lng"], 6)]
        out[e["_path"]] = row
    return out


# the planner's choices: (value, label, picture ID, glyph for the interim look) — the values are chatbot/plan_prompt.js
# MOVE / WITH / PREFS / NEEDS keys, the pictures docs/handover/gpt_image_requests_2026-10-17_plan.md (new) or the
# registry's existing ones
PLAN_CHOICES = {
    "days": [(1, "당일치기", "plan-dur-day", "sun"), (2, "1박 2일", "plan-dur-1n2d", "moon"), (3, "2박 3일", "plan-dur-2n3d", "bag")],
    "move": [("car", "자가용", "fact-parking", "car"), ("transit", "대중교통·걷기", "sit-carfree", "bus")],
    "with": [("solo", "혼자", "plan-with-solo", "user"), ("couple", "연인·친구", "plan-with-couple", "heart"),
             ("kids", "아이와 가족", "sit-kids", "family"), ("parents", "부모님과", "plan-with-parents", "cup")],
    "prefs": [("history", "역사·문화", "theme-modern-history", "building"), ("food", "맛집", "icon-food", "bowl"),
              ("islands", "섬·바다", "theme-islands-sea", "wave"), ("nature", "자연·힐링", "theme-parks-nature", "tree"),
              ("alleys", "골목 산책", "theme-alleys-culture", "lamp"), ("cafe", "카페·빵집", "kind-cafe", "cup"),
              ("experience", "체험", "kind-experience", "spark"), ("night", "야경", "sit-night", "moon"),
              ("photo", "사진 명소", "pref-photo", "camera")],
    "needs": [("rain", "비 와도 실내 위주", "sit-rainy", "umbrella"), ("stroller", "유모차", "cond-stroller", "family"),
              ("wheelchair", "휠체어", "cond-wheelchair", "access"), ("parking", "주차 편한 곳", "cond-parking", "car"),
              ("free", "입장료 없는 곳 위주", "sit-free", "ticket"), ("lesswalk", "걷기 적게", "sit-walk", "walk")],
}
# the pictures the result draws by ID (plan.js clones them from the page's <template>; one missing here is drawn as an
# empty pale circle: every pic("…") of plan.js and every KIND_PIC value — tests/test_plan_page.py)
PLAN_RESULT_PICS = ("kind-attraction", "kind-food", "kind-stay", "kind-cafe", "kind-museum", "kind-experience",
                    "theme-modern-history", "theme-islands-sea", "theme-parks-nature", "theme-alleys-culture",
                    "transit-bus", "sit-walk", "fact-parking", "plan-budget", "plan-swap", "icon-map", "fact-hours",
                    "fact-closed", "fact-fee", "cond-wheelchair", "icon-course")
PLAN_QUICK_EDITS = [("비가 오면 실내 위주로 바꿔 주세요", "비 오면 실내로", "sit-rainy"),
                    ("걷는 거리를 줄여 주세요", "덜 걷게", "sit-walk"),
                    ("점심 맛집을 다른 곳으로 바꿔 주세요", "점심 바꾸기", "icon-food"),
                    ("입장료 없는 곳 위주로 바꿔 주세요", "입장료 줄이기", "sit-free"),
                    ("카페나 빵집을 한 곳 넣어 주세요", "카페 넣기", "kind-cafe")]


def plan_hubs() -> list[tuple[str, str]]:
    """Where a trip may start and end (site.json city.plan.hubs; chatbot/plan_prompt.js reads the same from
    public/chat/site.json): (key, name) — names only, the site has no point for them; none: the form asks no hub."""
    return [(h["key"], h["name"]) for h in city.current().plan["hubs"]]


def plan_vm(S) -> dict:
    """The /plan/ page's context: the choices, the result pictures and quick edits, the courses to fall back on."""
    # the planner's own mascot poses once tools/mascot_media.py has made them, else the nearest existing pose; a site
    # without a mascot (pipeline/icons.py mascot) draws none
    path = Path(__file__).resolve().parent.parent / "templates" / "assets" / "mascot" / "manifest.json"
    have = json.loads(path.read_text("utf-8")) if path.is_file() else {}

    def pose(own, other):   # {name, kind}: 'medium' (200·400) when its files exist, else 'small' (96·192)
        name = own if own in have else other
        files = [f for f, *_ in (have.get(name) or {}).get("webp", [])]
        return {"name": name, "kind": "medium" if f"{name}-200.webp" in files else "small"}
    hubs = plan_hubs()
    return {"choices": {**PLAN_CHOICES, "hubs": hubs}, "result_pics": PLAN_RESULT_PICS,
            "hubs_json": json.dumps(dict(hubs), ensure_ascii=False, separators=(",", ":")),
            "quick_edits": PLAN_QUICK_EDITS,
            "n_places": len(S.entities), "n_courses": len(S.courses), "n_guides": len(S.guides),
            "region": S.site.get("region") or "",
            "mascots": {"work": pose("mascot-plan", "mascot-think"), "done": pose("mascot-plan-done", "mascot-hello"),
                        "rain": pose("mascot-plan-rain", "mascot-point"), "sorry": pose("mascot-sorry", "mascot-sorry")}}
