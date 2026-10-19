"""Site assistant knowledge (owner decision 2026-10-13, CLAUDE.md 3.10): the files api/chat.js answers from, written
by pipeline.build under <out>/chat/ (public/chat/ in the public build; vercel.json bundles public/chat/** with the
function through functions.includeFiles).

    catalog.txt  one line per page the site publishes: places, guides, courses, event series, /abroad/ articles,
                 video topic pages, theme and site pages — with the short facts those pages show (a place's first-screen
                 key facts exactly as present.key_facts gives them, both values with their providers where two sources
                 differ; its other names, '다른 이름'; the places of a combined ticket in its fee table, '통합권 N곳').
                 It is the cached part of the system prompt: deterministic (sorted, no build date) and under
                 CATALOG_BUDGET estimated tokens (estimate_tokens) so the whole prompt stays in the cheaper price tier.
    docs.json    {v, site, docs: {key: {t title, k kind, e English path, l {hreflang: that version's path}, n {hreflang:
                 that version's name}, u page, h heading, a other names, x text}},
                 alias, ext}: what get_pages returns. key = the page path (a guide section: the guide path + '#h-b<n>', the section's anchor on the
                 page; an /abroad/ article or a video: 'abroad:<id>' / 'video:<id>' with u = the page that lists it).
                 x = every fact with its source, the address it came from and 출처 확인일, both values where sources
                 differ, a combined ticket's places as the guides name them (ticket_lines), FAQ, nearby public parking
                 and bus stops, guide sections (a timetable chain spelled out stop by stop with the way back),
                 course stops, event editions with programmes. alias maps every version's path to its key; ext lists the
                 outside addresses the data links to (the only outside links an answer may carry); book = the
                 예약하기 addresses the docs list (pipeline/booking.py) {url: {k service, p {hreflang: the page that
                 version's button opens}, l {page: its language}}}: chatbot/knowledge.js links that page for a reader
                 of that language.
    index.json   {v, docs: {key: [title tokens, body tokens]}} for search_site (tokens(): Hangul and CJK bigrams,
                 Latin / Cyrillic / digit words; api/chat.js tokenizes queries the same way).

Facts come only from the records and helpers the pages use (CLAUDE.md 3.1, 3.2). Never included: TourAPI overview text
(3.4), the city tourism site's original text, photos. Single videos are not catalog lines (hundreds of them would take a large share of the
token budget): the catalog lists the video topic pages, docs/index hold every video. Nothing here names a city: the
site's name, address and region come from site.json (pipeline/city.py), every fact from the records.
"""
from __future__ import annotations

import json
import math
import re
import unicodedata
from pathlib import Path

from . import booking, city, fee_table, jsonld, present, relations, tickets
from . import locales as LC
from .schema import FACT_LABELS, FACT_ORDER, FIT_ORDER, KIND_LABELS, base_kind, designations
from .textutil import display_address, first_sentence, parking_text, squash_ws, web_text, web_url

CHAT_DIR = "chat"
VERSION = 1
CATALOG_BUDGET = 72_000      # estimated tokens (estimate_tokens). The spec's ceiling is ~80K; 72K keeps 25K+ for the
                             # conversation and tool results (api: 20K characters) under the 100K-token price tier
DOC_LIMIT = 9_000            # characters of one doc's text (get_pages caps what it returns again, api/chat.js)
KIND_ORDER = ("attraction", "food", "cafe", "stay", "shopping")   # 카페·디저트 its own list (operator 2026-10-19)
KIND_HEAD = {k: KIND_LABELS[k] for k in KIND_ORDER}
LINE_MAX = 60                # a place's one-line summary: a whole sentence up to this length, else cut at a clause
GUIDE_LINE_MAX = 100         # a guide's answer line, an event's usual timing
SEP = " | "


# ---------------------------------------------------------------- tokens (search) and the token estimate (budget)
TOKEN_RX = re.compile(r"[가-힣]+|[\u3040-\u30ff\u3400-\u9fff]+|[a-z0-9\u00c0-\u024f\u0400-\u04ff]+")


def tokens(text: str | None) -> list[str]:
    """Search tokens in first-seen order, each once: Hangul / kana / CJK runs as bigrams (a one-syllable run as
    itself), Latin, Cyrillic and digit runs as words (one-letter Latin words dropped). NFKC + lower case.
    chatbot/knowledge.js tokens() is the same function for queries — keep the two in step."""
    t = unicodedata.normalize("NFKC", str(text or "")).lower()
    out: list[str] = []
    seen: set[str] = set()
    for run in TOKEN_RX.findall(t):
        if run[0] >= "\u3040":
            grams = [run] if len(run) == 1 else [run[i:i + 2] for i in range(len(run) - 1)]
        else:
            grams = [run] if len(run) > 1 or run.isdigit() else []
        for g in grams:
            if g not in seen:
                seen.add(g)
                out.append(g)
    return out


def estimate_tokens(text: str) -> int:
    """A tokenizer-free, deliberately high estimate of Claude's token count: a Hangul syllable, kana or CJK character
    counts 1.0 (the newer tokenizer of Claude 4.7+ models, Haiku 5.5 among them, needs about 30% more tokens than the
    one before; Korean is near one token per syllable there), any other non-ASCII character 1.0, ASCII 1 per 2.5
    characters (the published 2.5M characters per 1M tokens). chars/3 alone undercounts Korean about threefold.
    The real count is in the function log (usage.cache_creation_input_tokens / cache_read_input_tokens)."""
    wide = sum(1 for ch in text if ord(ch) > 127)
    ascii_ = len(text) - wide
    return int(math.ceil(wide + ascii_ / 2.5))


# ---------------------------------------------------------------- small helpers
# a month range written with the first 월 left out ('3~10월 09:00~18:00'): the model read it as days of one month in a
# Spanish answer ('3–10 de octubre', review 2026-10-17 L08); the docs and catalog name both months ('3월~10월')
MONTH_RANGE = re.compile(r"(?<![\d.\-/월])(1[0-2]|[1-9])\s*~\s*(1[0-2]|[1-9])월")


def month_ranges(text: str) -> str:
    return MONTH_RANGE.sub(r"\1월~\2월", text)


def _clean(text) -> str:
    return squash_ws(str(text or "").replace("\n", " "))


def _short_line(text: str, limit: int = LINE_MAX) -> str:
    """A catalog summary: the sentence whole when it is short, else cut after a clause (' …') — never inside a value."""
    s = _clean(text)
    if len(s) <= limit:
        return s
    cut = max(s.rfind(m, 0, limit) for m in (", ", "고 ", "며 ", "·"))
    return (s[:cut].rstrip(" ,·") if cut > limit // 2 else s[:limit].rsplit(" ", 1)[0]) + " …"


def _when(iso: str | None) -> str:
    return squash_ws(iso)[:10]


def _period(ev: dict) -> str:
    start, end = _when(ev.get("start_date")), _when(ev.get("end_date"))
    if not start:
        return _clean(ev.get("period_text"))
    if end and end != start:
        return f"{start}~{end[5:] if end[:4] == start[:4] else end}"
    if not end and re.fullmatch(r"\d{4}-\d{2}", ev.get("end_month") or ""):
        return f"{start}~{ev['end_month']}"
    return start


def _src(src: dict | None, url: str = "", day: str = "") -> str:
    """'○○박물관 홈페이지 https://… (출처 확인 2026-10-08)': the provider, the exact address the value came
    from when the data has one, and the date this site last checked that source (출처 확인 — not a page review date).
    day: the date the record's '날짜:' line gives — a value checked that day leaves its date to that line (QA 2026-10-19
    QA-35: every fact line carried it, and the assistant repeated '(… 출처 확인 2026-10-19)' unasked)."""
    src = src or {}
    p = _clean(src.get("provider")) or "출처 미기재"
    d = _clean(src.get("checked_at"))
    return p + (f" {url}" if url else "") + (f" (출처 확인 {d})" if d and d != day else "")


def _fact_url(e: dict, src: dict | None) -> str:
    """The address one fact's value came from: the source's own URL, else for the city tourism site the place's 원문 page (the
    page the importer read), else ''. TourAPI values come from an API: the place doc names the same content's public
    page (대한민국 구석구석) once instead of repeating it on every line."""
    src = src or {}
    url = web_url(src.get("url")) if src.get("url") else ""
    if url:
        return url
    orig, official = e.get("original") or {}, e.get("official") or {}
    if _clean(src.get("provider")).startswith(city.current().official["name"] or "\0"):
        return web_url(orig.get("source_url") or official.get("source_url") or "")
    return ""


# what a place's dates are for (QA 2026-10-19 QA-35: with the date left to the '날짜:' line alone, the assistant still
# wrote '(출처: 한국관광공사 TourAPI, 출처 확인 2026-10-19)' in 3 of 6 answers nobody asked about dates in). The site
# shows no check date (CLAUDE.md 3절 2항); an answer names one only for the question prompt.js rule 11 names.
# The note is how to read the line, not a word of the page: left out of the search tokens (index_json).
DATES_ASKED_ONLY = "이용자가 확인 날짜·최신 여부를 물을 때만 답에 씀(출처 표기에도 붙이지 않음)"


def _dates(checked: str = "", reviewed: str = "", approved: str = "", checked_label: str = "출처 확인",
           asked_only: bool = False) -> str:
    """The page's dates, each named for what it is: when this site last checked the sources (출처 확인), when a person
    reviewed the page (페이지 검수 — none yet means '검수 전'), when the operator approved publishing it. asked_only: the
    line says it is for a question about how current the information is (a place's; a guide's check date goes with its
    timetables' times, prompt.js rule 12)."""
    parts = [f"{checked_label} {checked}" if checked else "", f"페이지 검수 {reviewed}" if reviewed else "페이지 검수 전(검수일 없음)",
             f"운영자 공개 승인 {approved}" if approved else ""]
    return "날짜: " + " · ".join(p for p in parts if p) + (f" — {DATES_ASKED_ONLY}" if asked_only else "")


EFFECTIVE_RX = re.compile(r"(\d{4})\.(\d{1,2})\.(\d{1,2})\.?\s*시행")


def _effective(sources: list[dict]) -> list[str]:
    """Timetables a guide cites with their 시행일 (the date the timetable took effect, from the source's own title
    '○○시내버스시간표(2024.10.21 시행) — ○○시'): ['○○시내버스시간표 — ○○시, 시행 2024-10-21, https://…']."""
    out = []
    for s in sources or []:
        name = _clean(s.get("name") or s.get("title"))
        m = EFFECTIVE_RX.search(name)
        if m:
            day = f"{m.group(1)}-{int(m.group(2)):02d}-{int(m.group(3)):02d}"
            bare = squash_ws(EFFECTIVE_RX.sub("", name).replace("()", "").replace("( )", ""))
            out.append(f"{bare}, 시행 {day}" + (f", {s['url']}" if s.get("url") else ""))
    return out


URL_RX = re.compile(r"https?://\S+")
CHAIN_RX = re.compile(r"기준 시각은\s*(.+?)입니다")
CHAIN_STOP = re.compile(r"^(.+?)\s+(\d{1,2}:\d{2}.*)$")
CLOCK = re.compile(r"\d{1,2}:\d{2}")


def _chain_lines(text: str) -> list[str]:
    """A timetable chain written as '기준 시각은 A 06:10, 09:10~20:10 … → B 06:35~20:35 → … 입니다' spelled out one
    stop per line: the stop, what the time is (the first stop's departure; at the others, the time the bus is at that
    stop — when one gets on there), the direction (stops after the first one that comes round again are the way back)
    and the stop's first and last time. On a route that comes back, each stop on the way out also gets its way back:
    the times of that stop on the way back, or — when the chain lists none — the same bus, which goes on to the end
    and comes back past the stops of the way back (one row of the chain is one bus), with the last one. Nothing is
    added that the sentence does not say: a stop time is never a departure toward that stop, and a time the chain does
    not list (the way back past a stop, the arrival at the first stop) is said to be missing."""
    out = []
    for m in CHAIN_RX.finditer(text):
        segs = [s.strip(" ,") for s in m.group(1).split("→")]
        stops = []
        for s in segs:
            mm = CHAIN_STOP.match(s)
            if not mm or not CLOCK.search(mm.group(2)):
                stops = []
                break
            stops.append((mm.group(1).strip(), mm.group(2).strip()))
        if len(stops) < 3:
            continue
        names = [n for n, _ in stops]
        last = [CLOCK.findall(t)[-1] for _, t in stops]
        back = next((i for i in range(1, len(names)) if names[i] in names[:i]), len(names))
        loop = back < len(names)
        far, home = names[back - 1], names[0]
        out.append("기준 정류장별 시각 풀이(위 문장의 값 그대로, 정류장·방향·시각 종류를 붙임):")
        for i, (name, times) in enumerate(stops):
            clocks = CLOCK.findall(times)
            kind = "출발 시각(첫 정류장)" if i == 0 else "버스가 그 정류장에 오는 시각(거기서 타고 내림)"
            if not loop:
                way = "가는 길"
            elif i < back - 1:
                way = f"가는 길({far} 쪽)"
            elif i == back - 1:
                way = f"가는 길의 끝({far}, 여기서 돌아 나옴)"
            else:
                way = f"돌아오는 길({home} 쪽)"
            out.append(f"- {name} — {kind}, {way}: {times} (첫 {clocks[0]}, 마지막 {clocks[-1]})")
        # live check 2026-10-14: an example naming one stop's last time ('○○ 21:15 차는 … 떠나는 차가 아니다') made the
        # model deny that the same bus is the last one back from that stop — the rule is given without a named example
        out.append(f"읽는 법: 정류장에 붙은 시각은 버스가 그 정류장에 오는 시각이라 그 정류장에서 타는 시각이고, {home}에서 그 시각에 "
                   f"출발하는 차라는 뜻이 아니다. {far} 쪽으로 가는 마지막 차는 {home} {last[0]} 출발이다.")
        if not loop:
            continue
        way_back = " → ".join(f"{names[j]} {stops[j][1]}" for j in range(back, len(stops)))
        out.append(f"돌아오는 길: {far}까지 간 차가 돌아 나와 {way_back} 순으로 지난다."
                   + ("" if names[-1] == home else f" 이 표에는 {home}에 닿는 시각이 없다."))
        for i in range(1, back - 1):   # the stops on the way out, between the first stop and the far end
            name = names[i]
            if name in names[back:]:
                j = back + names[back:].index(name)
                out.append(f"{name}에서 {home} 쪽으로 가는 차: 돌아오는 길의 {name} {stops[j][1]} (마지막 {last[j]}).")
                continue
            onward = " → ".join(f"{names[j]} {last[j]}" for j in range(i + 1, len(stops)))
            if names[-1] != home:   # the whole loop back toward the first stop, whose arrival the chain does not give
                onward += f" → {home} 쪽, {home} 도착 시각은 이 표에 없음"
            out.append(f"{name}에서 {home} 쪽으로 가는 막차: {name}에 {last[i]}에 오는 차를 타고 그대로 있으면 된다({onward}). "
                       f"{name}에 오는 차({stops[i][1]})는 모두 {far}까지 갔다가 돌아 나와 {'·'.join(names[back:])} 순으로 "
                       f"지난다. 돌아오는 차가 {name} 정류장을 다시 지나는 시각은 이 표에 없다.")
        out.append(f"{far}에서 {home} 쪽으로 가는 차: {far}에 오는 차({stops[back - 1][1]})가 그대로 돌아 나간다(마지막 {last[back - 1]}).")
    return out


SHORT_LABEL = {"이용시간": "시간", "영업시간": "시간", "쉬는 날": "휴무", "대표 메뉴": "메뉴", "주차 요금": "주차요금"}
SLOT_MAX = 48                # a slot value longer than this is cut after an item (' 외'); get_pages has it whole
TICKET_LABEL = re.compile(r"\[([^\]\n]{2,40})\]")   # a ticket's name in a fee table: '[박물관 통합권] - 성인 3,000원 …'
COMBINED_TICKET = "통합권"   # a ticket for several places — the fee table often names them only by kind ('미술관+건축관')
NAME_MIN = 3                 # names shorter than this (without spaces) are not looked for in sentences ('연도')
TOPIC = re.compile(r"^(.{1,40}?)[은는]\s")   # what a sentence is about: '박물관 통합권은 …' → '박물관 통합권'
# the list a sentence about a ticket gives, right after its topic: '… ○○박물관·○○미술관·…·○○함 네 곳을 묶은 표로'
TICKET_ITEMS = re.compile(r"^(.+?)(?:\s*(?:두|세|네|다섯|여섯|일곱|여덟|아홉|열|\d+)\s*곳)?[을를]\s*(?:묶은|함께|더한)")
ITEM_SPLIT = re.compile(r"\s*[·,、]\s*")


def _bare(text) -> str:
    """A name or a sentence without spaces, for finding names in text ('○○ 근대건축관' = '○○근대건축관')."""
    return re.sub(r"\s+", "", unicodedata.normalize("NFC", str(text or "")))


def _same_place(a: str, b: str) -> bool:
    """Two names in ticket lists that are one place: one is the other with more in front ('근대미술관' · '○○근대미술관',
    '함정' · '○○공원 함정', the kind '박물관' · '근대역사박물관')."""
    x, y = _bare(a), _bare(b)
    return bool(x and y) and (x.endswith(y) or y.endswith(x))


def _cap(text: str, limit: int) -> str:
    """Cut a long value after a whole item (', ' · ' / ' · '; ') and mark it ' 외' — never inside an item."""
    if len(text) <= limit:
        return text
    cut = max(text.rfind(m, 0, limit) for m in (", ", " / ", "; ", " - "))
    return (text[:cut] if cut > 8 else text[:limit].rsplit(" ", 1)[0]).rstrip(" ,/;-") + " 외"


def _slot_text(s: dict) -> str:
    """A key-fact slot as the first screen gives it, with a short label ('시간 09:00–18:00'); a conflict names
    both providers ('시간 두 출처 다름: ○○시 09:00–18:00 / 한국관광공사 상시 개방')."""
    def one(v):
        t = _clean(v.get("main")) + _clean(v.get("tel_tail"))   # '032-453-7883~4' as the source writes it
        if v.get("sub"):
            t += f", {_clean(v['sub'])}"
        t = _cap(t, SLOT_MAX)
        if v.get("more") and not t.endswith(" 외"):
            t += " 외"
        return t
    label = SHORT_LABEL.get(s["label"], s["label"])
    if s.get("conflict"):
        return f"{label} 두 출처 다름: " + " / ".join(f"{v.get('provider') or '출처'} {one(v)}" for v in s["vals"])
    return f"{label} {one(s)}"


class Knowledge:
    """Everything the three files hold, computed from a build State (pipeline.build.State with S.en loaded)."""

    def __init__(self, S):
        self.S = S
        self.site = S.site_url
        en = getattr(S, "en", None)
        self.ko2en = dict(getattr(en, "ko2en", {}) or {})
        self.event_en = dict(getattr(en, "event_links", {}) or {})
        self.en_names = {}
        for p in (getattr(en, "places", {}) or {}).values():
            self.en_names[p["e"]["id"]] = p["name"]
        # every version's twin of a Korean page, its path and name: a reader of that language opens that page and
        # sees its name on the link card (chatbot/knowledge.js pathFor, fixLinks); ko path → {hreflang: [path, name]}
        self.twins: dict[str, dict[str, list[str]]] = {}
        intl = getattr(S, "intl", None)
        for site in (intl.sites.values() if intl else [en] if en else []):
            names = {p["e"]["_path"]: p["name"] for p in site.places.values()}
            names.update({x["g"]["_path"]: squash_ws(x["rec"].get("title")) for x in site.guides.values()})
            names.update({x["c"]["_path"]: squash_ws(x["rec"].get("name")) for x in site.courses.values()})
            # an event series opens <home>events/#anchor there: its card carries the series' name in that language
            by_slug = {x["slug"]: x for x in getattr(site, "series", None) or []}
            names.update({sr["_path"]: squash_ws(by_slug[sr["slug"]]["rec"].get("series_name"))
                          for sr in getattr(S, "series", None) or [] if sr["slug"] in by_slug})
            for ko, path in {**site.event_links, **site.ko2en}.items():
                self.twins.setdefault(ko, {})[site.loc.html] = [path, names.get(ko, "")]
            # the site search of that version (en_site Pages.search builds <home>search/ whenever it has places; not
            # in Site.ko2en: no hreflang or sitemap row for a noindex utility page): the chat's '사이트 검색' link
            # opens the reader's own (QA 2026-10-15)
            if site.places:
                self.twins.setdefault("/search/", {})[site.loc.html] = [f"{site.home}search/", ""]
        if en is not None and en.places:
            self.ko2en.setdefault("/search/", f"{en.home}search/")
        self.lines: list[str] = []
        self.docs: dict[str, dict] = {}
        self.ext: set[str] = set()
        self.book: dict[str, dict] = {}   # 예약하기 addresses the docs list: url → {k: service, p: {hreflang: page}}
        self.video_topic: dict[str, dict] = {}
        self._names: list | None = None
        self._sentences: list | None = None
        self._tickets: dict[str, list] = {}

    # -- paths
    def en_path(self, ko_path: str) -> str:
        return self.ko2en.get(ko_path) or ""

    def keep_url(self, *urls) -> None:
        for u in urls:
            u = web_url(u) if u else ""
            if u.startswith(("http://", "https://")) and not u.startswith(self.site):
                self.ext.add(u)

    def booking_lines(self, targets: list[dict]) -> list[str]:
        """예약하기 (pipeline/booking.py): the official booking pages the page shows as buttons, each with the page of
        the services in other languages and the basis in the data; kept as outside addresses (ext) and in docs.json
        'book', where chatbot/knowledge.js turns a link to one into the reader's language page."""
        if not targets:
            return []
        services = booking.registry(self.S).get("services") or {}
        L = ["예약하기(페이지의 공식 예약 페이지 버튼 — 이 사이트와 챗봇은 예약을 받지 않는다):"]
        for t in targets:
            p = {}
            for code in LC.ORDER:   # the page each version's button opens (booking.view's choice)
                k = booking.page_lang(t["pages"], code)
                if k:
                    p[LC.get(code).html] = t["pages"][k]
            # the language of each page (hreflang on the chat's card); a facility's own address: none claimed
            hl = {} if t["key"] == booking.OWN else {t["url"]: "ko", **{u: LC.get(k).html for k, u in t["pages"].items()}}
            if t["key"] == booking.OWN:
                L.append(f"- 시설 자체 예약 주소({web_text(t['url'])}, 정보의 '예약 주소' 값): {t['url']}")
            else:
                s = services.get(t["key"]) or {}
                other = "; ".join(f"{LC.get(k).label} 페이지 {u}" for k, u in t["pages"].items())
                L.append(f"- {booking.service_name(t, 'ko')}: {t['url']}" + (f" ({other})" if other else "")
                         + f" — 근거: {_clean(s.get('basis'))} (출처 확인 {_clean(s.get('checked_at'))})")
            self.keep_url(t["url"], *t["pages"].values())
            self.book[t["url"]] = {"k": t["key"], "p": p, **({"l": hl} if hl else {})}
        return L

    def plan_facts(self, e: dict) -> dict:
        """What chatbot/knowledge.js checkPlan reads of a place (review 2026-10-17 G01: a plan put 0 minutes between
        two places 5.7 km apart): its point (g), its hours (h) and closed days (c) as each source writes them — the whole
        value, so a last entry time and the months of a season stay —, the bus routes of the stops near it (b) and its
        dated notices still shown (n)."""
        from . import build as B
        out: dict = {}
        geo = e.get("_geo") or {}
        if isinstance(geo.get("lat"), (int, float)) and isinstance(geo.get("lng"), (int, float)):
            out["g"] = [round(geo["lat"], 6), round(geo["lng"], 6)]
        for slot in present.key_facts(e, "hero")["slots"]:
            if slot["key"] not in ("hours", "closed"):
                continue
            row = B.fact_row(e, slot["src_key"]) if slot["src_key"] in FACT_ORDER + FIT_ORDER else None
            if row and row["value"] and slot["key"] == "hours":
                texts = [{"p": row["source"].get("provider", ""), "t": month_ranges(_clean(row["value"]))}]
                texts += [{"p": a.get("provider", ""), "t": month_ranges(_clean(a["value"]))}
                          for a in row["alternatives"] if not a["also"]]
            else:   # closed days as the first screen splits them, and hours a combined field gives
                texts = [{"p": v.get("provider") or slot.get("provider") or "",
                          "t": month_ranges(", ".join(x for x in (v.get("main"), v.get("sub")) if x))}
                         for v in (slot["vals"] or [slot])]
            texts = [x for x in texts if x["t"]]
            if texts:
                out["h" if slot["key"] == "hours" else "c"] = texts
        if "h" not in out:
            # an hours value the first screen cannot brief ('※ 시설별 상이하므로 홈페이지 참고': no time in it) is still the
            # site's word on the hours — never '이용시간이 사이트에 없음' (QA 2026-10-19 QA-31)
            row = B.fact_row(e, "usetime")
            if row and row["value"]:
                out["h"] = [{"p": row["source"].get("provider", ""), "t": month_ranges(_clean(row["value"]))}]
        acc = present.access_vm(self.S, e) or {}
        routes = sorted({r for st in acc.get("stops") or [] for r in st.get("routes") or []})
        if routes:
            out["b"] = routes
        notes = []
        for row in e.get("_notices") or []:
            n = row["n"]
            start = str(n.get("start") or n.get("date") or "")
            notes.append({k: v for k, v in {"k": n["kind"], "s": start, "e": str(n.get("end") or start),
                                             "f": n.get("from"), "t": n.get("to"), "l": n.get("last_entry")}.items() if v})
        if notes:
            out["n"] = notes
        # what the course planner checks a plan's conditions with (review 2026-10-17, AI 코스 만들기 집중 평가: fees the
        # model left out or counted twice, access the page has said to be missing): the fee value read as a table
        # (fee_table.parse, the other sources' values beside it), the access rows as each source writes them, the own
        # parking value and the nearest public lot, the type the indoor check reads, the check-in time
        # kd: the kind the planner reads (chatbot/plan_*.js): a café as food, a shop as a place to visit
        # (schema.base_kind); kc: the site's own kind when it differs ('cafe' — always a café to the planner, 'shopping')
        out["kd"] = base_kind(e["kind"])
        if out["kd"] != e["kind"]:
            out["kc"] = e["kind"]
        if e.get("_type"):
            out["ty"] = e["_type"]
        if e.get("_region") and city.current().island_region(e["_region"]):
            out["isl"] = 1   # an island 권역 (site.json city.plan.island_regions): the planner's '섬·바다' liking
        row = B.fact_row(e, "usefee")
        if row and (row["value"] or row["alternatives"]):
            fee = fee_table.parse(row["value"]) if row["value"] else {}
            fee["t"] = _clean(row["value"]) if row["value"] else ""
            fee["p"] = row["source"].get("provider", "") if row["value"] else ""
            alt = [{"p": a.get("provider", ""), "t": _clean(a["value"])} for a in row["alternatives"] if not a["also"]]
            if alt:
                fee["alt"] = alt
            out["fee"] = fee
        access = []
        for key in ("accessible_route", "wheelchair", "accessible_toilet", "accessible_parking", "babycarriage"):
            row = B.fact_row(e, key)
            if not row:
                continue
            if row["value"]:
                access.append({"k": key, "t": _clean(row["value"]), "p": row["source"].get("provider", "")})
            access += [{"k": key, "t": _clean(a["value"]), "p": a.get("provider", "")} for a in row["alternatives"] if not a["also"]]
        if access:
            out["ac"] = access
        row = B.fact_row(e, "parking")
        if row and row["value"]:
            out["pk"] = _clean(row["value"])
        lots = acc.get("lots") or []
        if lots:
            out["pkn"] = {"n": lots[0].get("name") or "", "m": lots[0].get("m")}
        row = B.fact_row(e, "checkin")
        if row and row["value"]:
            out["ci"] = _clean(row["value"])
        return out

    def add_doc(self, key: str, title: str, kind: str, text: str, en: str = "", page: str = "", head: str = "",
                alt: list[str] | None = None) -> None:
        text = month_ranges(text.strip())
        if len(text) > DOC_LIMIT:
            text = text[:DOC_LIMIT].rsplit("\n", 1)[0] + "\n… (이하 생략: 전체는 페이지에서)"
        doc = {"t": title, "k": kind, "x": text}
        if en:
            doc["e"] = en
        twins = self.twins.get(key) if "#" not in key else None   # a guide section opens its guide's twin + anchor
        if twins:
            doc["l"] = {h: v[0] for h, v in twins.items()}
            if any(v[1] for v in twins.values()):
                doc["n"] = {h: v[1] for h, v in twins.items() if v[1]}
        if page:
            doc["u"] = page
        if head:   # a guide section's own heading: the title of its link card
            doc["h"] = head
        if alt:    # a place's other names (the page lists them under its name): search and get_pages show them by the title
            doc["a"] = list(alt)
        self.docs[key] = doc

    # -- build
    def build(self) -> "Knowledge":
        S = self.S
        self.video_topic = {}
        from .build import video_groups
        self.groups = video_groups(S.videos) if S.videos else []
        for g in self.groups:
            for v in g["items"]:
                self.video_topic[v["youtube_id"]] = g
        out = [
            f"# Site catalog of {S.site.get('site_name', '')} ({self.site}). One line = one page of this site.",
            "# Line letter: P place, G guide, C course, E event series, A foreign article (on /abroad/), V video topic page, "
            "T theme list, S site page. The second field is the page path (an article: its id): pass it to get_pages "
            f"as is, and link the page as {self.site} + path. A name in brackets is the place's English name; "
            "'다른 이름' = other names of the same place (a building and the museum in it, an old and a new name).",
            "# Place lines carry the key facts exactly as the page's first screen shows them, in this order — attraction: "
            "시간 (hours), 휴무 (closed days), 요금 (fee), 주차 (parking), 전화 (phone); food and 카페·디저트 (cafés, tea houses, "
            "bakeries — their own list, apart from 음식점): 시간, 휴무, 메뉴 (signature dishes), 주차, 전화; 쇼핑 (markets and "
            "shops): 시간, 휴무, 주차, 전화; stay: 체크인, 체크아웃, 주차, 객실 (rooms), 전화. One of these missing from a line = "
            "the site has no "
            "value for it. '외' = the page has more. '두 출처 다름' = two sources give different values and the page shows "
            "both (방문 전 전화 확인). '통합권 N곳' = the places a combined ticket in the fee covers, as the guides name "
            "them ('A(=B)': A is the name the guides use, B the place's page name). "
            "지정 = official designations the page lists. Everything else (all facts with sources, "
            "FAQ, nearby public parking and bus stops, guide text, event programmes) comes from get_pages.",
            *self.official_line(),
            "",
        ]
        for kind in KIND_ORDER:
            items = sorted(S.lists.get(kind) or [], key=lambda e: present.name_key(e["name"]))
            if not items:
                continue
            out.append(f"## {KIND_HEAD[kind]} {len(items)}곳 — 목록 {self._list_path(kind)}")
            out += [self.place(e) for e in items]
            out.append("")
        if S.guides:
            out.append(f"## 가이드 {len(S.guides)}편 — 목록 /guides/")
            out += [self.guide(g) for g in sorted(S.guides, key=lambda g: g["id"])]
            out.append("")
        if S.courses:
            out.append(f"## 여행 코스 {len(S.courses)}개 — 목록 /courses/")
            out += [self.course(c) for c in sorted(S.courses, key=lambda c: c["id"])]
            out.append("")
        if S.series:
            out.append(f"## 행사·축제 {len(S.series)}개 (회차 날짜는 정확한 값, 오늘 기준 진행·예정·종료는 직접 판단) — 목록 /events/")
            out += [self.series(sr) for sr in sorted(S.series, key=lambda sr: sr["slug"])]
            out.append("")
        if S.abroad:
            out.append(f"## 해외에서 본 {S.site.get('region', '')}: 외신·해외 매체 기사 {len(S.abroad)}건 — 페이지 /abroad/ "
                       "(우리가 쓴 한 줄 소개 + 원문 링크)")
            out += [self.abroad(a) for a in sorted(S.abroad, key=lambda a: (a.get("date") or "", a["id"]), reverse=True)]
            out.append("")
        for v in S.videos:
            self.video(v)
        if self.groups:
            out.append(f"## 영상 {len(S.videos)}편 — 주제별 페이지 (영상 하나하나는 search_site로 찾는다)")
            out += [self.video_page(g) for g in self.groups]
            out.append("")
        out.append("## 테마와 사이트 페이지")
        out += self.theme_lines() + self.site_pages()
        self.lines = out
        self.keep_url(S.site.get("source", {}).get("url"), *(l.get("url") for l in S.site.get("official_links") or []))
        return self

    def official_line(self) -> list[str]:
        """The official places to confirm what the site lacks (site.json official_links: name, address, what it is) — one
        catalog line, so an answer that says a value is not on the site can name where to check it when the page has no
        phone or homepage (CLAUDE.md 3.11; QA 2026-10-19 QA-11: '터미널 또는 운항 회사에 직접 확인하세요' named none)."""
        links = [x for x in self.S.site.get("official_links") or [] if x.get("name") and x.get("url")]
        if not links:
            return []
        return ["# 공식 확인처 (official places to confirm a value the site lacks): " + "; ".join(
            f"{_clean(x['name'])} {x['url']}" + (f" ({_clean(x['note'])})" if x.get("note") else "") for x in links)]

    def _list_path(self, kind: str) -> str:
        from .build import LISTS
        return LISTS[kind]["path"]

    # -- places
    def place(self, e: dict) -> str:
        name = e["name"]
        en_name = self.en_names.get(e["id"], "")
        kf = present.key_facts(e, "hero")
        slots = "; ".join(_slot_text(s) for s in kf["slots"])
        where = "·".join(x for x in (e.get("_district") or "", e.get("_area") or e.get("_road") or "",
                                     e.get("_region") if e.get("_region") != present.none_label() else "") if x)
        ds = designations(e)
        title = f"{name} ({en_name})" if en_name else name
        alt = jsonld.alternate_names(e)
        if alt:   # the other names the page lists under its name: a building and the museum in it, an old and a new name
            title += " · 다른 이름 " + ", ".join(alt)
        # a combined ticket's places as the guides name them, with the page name of a place they call by another name
        # ('○○미술관(=구 ○○은행 지점 /places/…/)'): the review's '정정' came from a model that could not tie
        # the two; live check 2026-10-14: without the path the model said the museum had no page of its own
        tickets = "; ".join(
            f"{t['label']} {len(t['places'])}곳: " + "·".join(
                f"{p['written']}(={p['e']['name']} {p['e']['_path']})" if p["e"] and p["by"] == "other" else p["written"]
                for p in t["places"])
            for t in self.tickets(e))
        parts = [f"P {e['_path']}", title, e.get("_type") or KIND_LABELS[e["kind"]],
                 where, _short_line(e.get("_line") or first_sentence(e.get("summary"), LINE_MAX)), slots, tickets,
                 "지정 " + "·".join(d["short"] for d in ds) if ds else ""]
        self.place_doc(e, self.en_path(e["_path"]), en_name)
        return SEP.join(p for p in parts if p)

    def place_doc(self, e: dict, en: str, en_name: str) -> None:
        from . import build as B
        S = self.S
        f = e.get("facts") or {}
        L = [f"{e['name']} — {KIND_LABELS.get(e['kind'], '')}{' · ' + e['_type'] if e.get('_type') else ''}"
             + (f" (English: {en_name})" if en_name else "")]
        alt = jsonld.alternate_names(e)
        if alt:
            L.append("다른 이름: " + ", ".join(alt))
        where = [x for x in (" ".join(y for y in (e.get("_district"), e.get("_area")) if y),
                             f"{e['_region']} 권역" if e.get("_region") not in (None, "", present.none_label()) else "") if x]
        if where:
            L.append("위치: " + " · ".join(where))
        # places that belong together (pipeline/relations.py): the page's own lines, so an answer about one names the other
        parent = e.get("_parent")
        if parent is not None and e.get("_rel") == "inside":
            L.append(f"속한 곳: {parent['name']} {parent['_path']} (이곳은 {parent['name']} 안에 있는 곳이며 페이지가 따로 있음)")
        for x in e.get("_same") or []:
            L.append(f"같은 건물: {x['name']} {x['_path']} (같은 건물·시설의 다른 페이지)")
        if e.get("_parts"):
            L.append(f"{e['name']} 안에 있는 곳: " + "; ".join(f"{c['name']} {c['_path']}" for c in e["_parts"]))
        if e.get("summary"):
            L.append("요약: " + _clean(e["summary"]))
        for d in e.get("details") or []:
            L.append(f"{_clean(d.get('heading'))}: {present.decaution(_clean(d.get('text')))}")
        day = B.facts_checked_date(e)
        L.append("정보(값 — 출처, 그 값을 가져온 주소, 출처 확인일 = 이 사이트가 그 출처를 확인한 날 — 아래 '날짜:' 줄의 날과"
                 " 다를 때만 값 옆에):")
        tourapi = False
        for k in FACT_ORDER + FIT_ORDER:
            row = B.fact_row(e, k)
            if not row:
                continue
            if row["value"]:
                # parking as the page words it ('가능요금 (대형 8,000원 …)' → '가능, 요금 대형 8,000원 …'; QA 2026-10-19 QA-20)
                value = _clean(parking_text(row["value"]) if k == "parking" else row["value"])
                url = _fact_url(e, row["source"])
                L.append(f"- {row['label']}: {value} — {_src(row['source'], url, day)}")
                self.keep_url(url)
                if k in ("homepage", "reservationurl"):
                    self.keep_url(*str(row["value"]).split("\n"))
                tourapi = tourapi or row["source"].get("provider") == "한국관광공사 TourAPI"
            for a in row["alternatives"]:
                tag = "추가 값" if a["also"] else "다른 출처 값"
                url = _fact_url(e, a)
                line = f"- {row['label']}({tag}): {_clean(a['value'])} — {_src(a, url, day)}"
                self.keep_url(url)
                tourapi = tourapi or a.get("provider") == "한국관광공사 TourAPI"
                if not a["also"]:
                    line += " → 출처마다 값이 달라 방문 전 전화 확인"
                L.append(line)
            if k == "usefee":
                L += self.ticket_lines(e)
                L += tickets.place_lines(getattr(S, "tickets", None) or {}, e, self.place_ref)
        L += self.booking_lines(booking.place_targets(S, e))
        official = e.get("official") or {}
        if tourapi and official.get("visitkorea_url"):
            L.append("한국관광공사 TourAPI 값은 API 자료다. 같은 콘텐츠의 공개 페이지: 대한민국 구석구석 "
                     f"{web_url(official['visitkorea_url'])}")
        L.append(_dates(day, _clean(e.get("reviewed_at")), _clean(e.get("approved_at")), asked_only=True))
        kf = present.key_facts(e, "hero")
        if kf["missing"]:
            L.append("사이트에 없는 값(확인 필요): " + "·".join(kf["missing"]))
        # dated notices of the facility (pipeline/notices.py; only those still shown, i.e. until ≥ the build date): a
        # question about one of these dates is answered from them, with the provider's post as the link
        for row in e.get("_notices") or []:
            n = row["n"]
            L.append(f"- 날짜별 공지: {row['text']} — {_src({'provider': n['provider'], 'checked_at': n['checked_at']}, n['url'])}"
                     f" (이 공지는 {n['until']}까지 표시; 그 밖의 날은 위 이용시간·쉬는 날)")
            self.keep_url(n["url"])
        for d in designations(e):
            L.append(f"- 지정: {d['label']} (출처: {_clean(d.get('source_name'))} {d.get('url') or ''})".rstrip())
            self.keep_url(d.get("url"))
        faqs = [x for x in e.get("faq") or [] if x.get("q") and x.get("a")]
        if faqs:
            L.append("자주 묻는 질문:")
            L += [f"- Q {_clean(x['q'])} A {present.decaution(_clean(x['a']))}" for x in faqs]
        acc = present.access_vm(S, e)
        if acc:
            if acc["lots"]:
                L.append(f"근처 공영주차장(직선 {acc['radius']}m 안): " + "; ".join(self._lot(l) for l in acc["lots"]))
            if acc["stops"]:
                L.append(f"가까운 버스 정류장(직선 {acc['bus_radius']}m 안): " + "; ".join(
                    f"{s['name']} {s['m']}m" + (f" (노선 {s['routes_text']})" if s["routes_text"] else "") for s in acc["stops"]))
            L.append("출처: " + "; ".join(self._access_source(name) for name in acc["sources"]))
        near = []
        target = lambda n: S.ent_by_slug.get(n.get("internal_slug") or "") or S.ent_by_cid.get(str(n.get("contentid")))  # noqa: E731
        for n in relations.keep_rows(e, e.get("nearby") or [], target):   # never its own family (relations.py)
            t = target(n)
            if t and n.get("distance_m"):
                near.append(f"{t['name']} {t['_path']} 직선 {present.dist(n['distance_m'])}")
        if near:
            L.append("가까운 장소: " + "; ".join(near))
        # the page's distances to the city's reference places (city.distance_anchors; QA 2026-10-19 QA-38: the page said
        # '인천국제공항 직선 5.9km' and the assistant that the site had no distance)
        anchors = present.anchor_rows(S, e)
        if anchors:
            L.append("기준 장소까지 직선거리: " + "; ".join(f"{a['name']} {a['path']} 직선 {a['d']}" for a in anchors))
        if e.get("_courses"):
            L.append("이 장소가 나오는 코스: " + "; ".join(f"{present.course_display(c['name'])} {c['_path']}" for c in e["_courses"]))
        if e.get("_guides"):
            L.append("이 장소가 나오는 가이드: " + "; ".join(f"{g['title']} {g['_path']}" for g in e["_guides"]))
        if e.get("_events"):
            L.append("이 장소의 행사: " + "; ".join(f"{sr['name']} {sr['_path']}" for sr in e["_events"]))
        vids = [v for v in S.videos if e["slug"] in (v.get("place_slugs") or [])]
        if vids:
            L.append(f"영상 {len(vids)}편: " + "; ".join(f"{_clean(v['title'])} — {_clean(v.get('channel'))}" for v in vids[:5]))
        if e.get("_abroad"):
            L.append("해외 기사(/abroad/): " + "; ".join(f"{a.get('outlet')} {a.get('date') or ''} {a['url']}" for a in e["_abroad"]))
        orig, official = e.get("original") or {}, e.get("official") or {}
        links = [("원문", orig.get("source_url") or official.get("source_url")), ("대한민국 구석구석", official.get("visitkorea_url")),
                 ("공식 홈페이지", official.get("homepage"))]
        links = [(lab, web_url(u)) for lab, u in links if u]
        if links:
            L.append("공식 링크: " + "; ".join(f"{lab} {u}" for lab, u in links))
            self.keep_url(*(u for _, u in links))
        self.add_doc(e["_path"], e["name"], "place", "\n".join(L), en, alt=alt)
        facts = self.plan_facts(e)
        if facts:
            self.docs[e["_path"]]["f"] = facts

    def place_ref(self, pid: str) -> dict:
        """{name, path} of a place id (the id and no path when it has no page here)."""
        e = next((x for x in self.S.entities if x["id"] == pid), None)
        return {"name": e["name"], "path": e["_path"]} if e else {"name": pid, "path": ""}

    # -- places named in sentences, and the combined tickets
    def names(self) -> list[tuple[str, str, dict]]:
        """(name without spaces, the name as written, the place) for every place's name and other names (the place page
        lists them under its name), longest first."""
        if self._names is None:
            out = []
            for e in self.S.entities:
                for n in [e["name"], *jsonld.alternate_names(e)]:
                    if len(_bare(n)) >= NAME_MIN:
                        out.append((_bare(n), _clean(n), e))
            self._names = sorted(out, key=lambda x: (-len(x[0]), x[0], x[2]["id"]))
        return self._names

    def places_in(self, text: str, skip=frozenset()) -> list[tuple[str, dict]]:
        """The places a sentence names, by their name or another name, in the order the sentence names them:
        [(the name as the sentence writes it, the place)]. Longer names are read first, so a name inside one already read
        (역사박물관 in 근대역사박물관) is not read again. Places whose id is in `skip` are left out."""
        t = _bare(text)
        found: dict[str, tuple[int, str, dict]] = {}
        for key, written, e in self.names():
            at = t.find(key)
            if at < 0:
                continue
            t = t.replace(key, "\0" * len(key))
            if e["id"] not in skip and (e["id"] not in found or at < found[e["id"]][0]):
                found[e["id"]] = (at, written, e)
        return [(w, e) for _, w, e in sorted(found.values(), key=lambda x: x[0])]

    def guide_sentences(self) -> list[tuple[str, str]]:
        """Every sentence of the guides' FAQ answers and sections with the guide's path, as the guide docs give them."""
        if self._sentences is None:
            out = []
            for g in sorted(self.S.guides or [], key=lambda g: g["id"]):
                texts = [x.get("a") for x in g.get("faq") or [] if x.get("q") and x.get("a")]
                texts += [b.get("text") for b in g.get("body") or []]
                for t in texts:
                    out += [(g["_path"], s) for s in present.sentences(present.decaution(_clean(t)))]
            self._sentences = out
        return self._sentences

    def tickets(self, e: dict) -> list[dict]:
        """The combined tickets (통합권) in the place's fee table, with what the guides say about them:
        [{label, said: [(guide path, sentence)], places: [{written, e, by}]}].

        The fee table often names a ticket's places only by kind ('[통합권]인근 전시장(박물관+미술관+건축관+○○함)'),
        so a reader of one page cannot tell that '미술관' is ○○미술관 = 구 ○○은행 지점 (the external
        evaluation's assistant then 'corrected' a right answer). The guides' sentences about the ticket ('박물관 통합권은
        …' — the ticket is what the sentence is about) that name this place say which places it covers: `said` = the two
        that name the most places. `places` = the ticket's places, one per place, in the order those sentences list them
        ('… ○○박물관·○○미술관·○○건축관·○○함 네 곳을 묶은 표로'), each with the name the guides write
        (`written`: the first of its names that names a place page — '○○공원 함정' rather than '함정'), the
        place (`e`, None when no place page has that name) and how the name points to it (`by`: 'name', or 'other' — one
        of its other names). Another sentence about the ticket adds its names only when every item of its list is
        already one of the ticket's places under a shorter or longer name ('근대미술관', '○○함'), never a new place
        ('○○권 통합권은 박물관 통합권 네 곳에 …을 더한'); a sentence about something else that mentions the ticket is
        never used: the places it names need not be the ticket's."""
        if e["id"] in self._tickets:
            return self._tickets[e["id"]]
        from . import build as B
        row = B.fact_row(e, "usefee")
        values = [row["value"], *(a["value"] for a in row["alternatives"])] if row else []
        labels: list[str] = []
        for v in values:
            for lab in TICKET_LABEL.findall(str(v or "")):
                lab = _clean(lab)
                if COMBINED_TICKET in lab and lab not in labels:
                    labels.append(lab)
        own = [b for b in (_bare(n) for n in [e["name"], *jsonld.alternate_names(e)]) if len(b) >= NAME_MIN]
        out = []
        for lab in labels:
            key = _bare(lab)
            about: list[tuple[str, str, list[str]]] = []   # every guide sentence about this ticket, with its list
            for path, s in self.guide_sentences():
                topic = TOPIC.match(s)
                if not topic or not _bare(topic.group(1)).endswith(key) or any(a[:2] == (path, s) for a in about):
                    continue
                m = TICKET_ITEMS.match(s[topic.end():])
                items = [x for x in ITEM_SPLIT.split(m.group(1).strip()) if x] if m else []
                about.append((path, s, items if len(items) >= 2 else []))
            said = [a for a in about if any(o in _bare(a[1]) for o in own)]
            said.sort(key=lambda a: -len(self.places_in(a[1])))   # stable: guide order otherwise
            said = said[:2]
            if not said:
                continue
            groups: list[list[str]] = []   # one per place of the ticket: the names the lists give it

            def group_of(item: str):
                return next((g for g in groups if any(_same_place(item, x) for x in g)), None)

            for a in said:
                for item in a[2]:
                    g = group_of(item)
                    if g is None:
                        groups.append([item])
                    elif item not in g:
                        g.append(item)
            for a in about:
                if a in said or not a[2] or any(group_of(item) is None for item in a[2]):
                    continue
                for item in a[2]:
                    g = group_of(item)
                    if item not in g:
                        g.append(item)
            places = []
            for g in groups:
                hit = None
                for x in g:
                    found = self.places_in(x)
                    if found:
                        written, t = found[0]
                        hit = {"written": x, "e": t, "by": "name" if _bare(written) == _bare(t["name"]) else "other"}
                        break
                places.append(hit or {"written": g[0], "e": None, "by": ""})
            out.append({"label": lab, "said": [(p, s) for p, s, _ in said], "places": places})
        self._tickets[e["id"]] = out
        return out

    def ticket_lines(self, e: dict) -> list[str]:
        """Under the fee line: each combined ticket's sentences from the guides, then its places with their pages — a
        place the guides call by another name with the page's own name ('○○미술관 = 구 ○○은행 지점
        /places/…/'), this page marked as such (tickets())."""
        out = []
        for t in self.tickets(e):
            out.append(f"- 이용요금의 '{t['label']}'(가이드의 설명): " + " / ".join(f"{s} ({p})" for p, s in t["said"]))
            if not t["places"]:
                continue
            named = []
            for p in t["places"]:
                x = p["e"]
                if x is None:
                    named.append(f"{p['written']} (장소 페이지 없음)")
                    continue
                one = (f"{p['written']} = {x['name']} {x['_path']}" if p["by"] == "other"
                       else f"{p['written']} {x['_path']}")
                named.append(one + (" (이 페이지)" if x["id"] == e["id"] else ""))
            out.append(f"  '{t['label']}' 시설 {len(t['places'])}곳(가이드가 쓴 이름 — 장소 페이지): " + "; ".join(named))
        return out

    def _access_source(self, name: str) -> str:
        """One source of the nearby parking / bus block with its address and dates from nearby.json _meta: the parking
        and bus-stop datasets (출처 확인), the bus timetable (시행일 + 출처 확인 — the route numbers are its values)."""
        meta = getattr(self.S, "nearby_meta", None) or {}
        park, bus = meta.get("parking") or {}, meta.get("bus") or {}
        tt = bus.get("timetable") or {}
        key = {v: k for k, v in present.access_sources().items()}.get(name, "")
        src = {"standard": park, "stops": bus}.get(key)
        if src:
            self.keep_url(src.get("url"))
            return name + (f" {src['url']}" if src.get("url") else "") + (f" (출처 확인 {src['checked_at']})" if src.get("checked_at") else "")
        if key == "timetable" and tt:
            self.keep_url(tt.get("url"))
            bits = [f"시행 {tt['effective_date']}" if tt.get("effective_date") else "",
                    f"출처 확인 {tt['checked_at']}" if tt.get("checked_at") else ""]
            return (f"{_clean(tt.get('name')) or name} — {_clean(tt.get('provider'))}" + (f" {tt['url']}" if tt.get("url") else "")
                    + (f" ({', '.join(b for b in bits if b)})" if any(bits) else "") + " — 노선 번호는 이 시간표 기준")
        return name

    @staticmethod
    def _lot(l: dict) -> str:
        bits = [l["type"], f"{l['m']}m"]
        if l.get("spaces") is not None:
            bits.append(f"{l['spaces']}면" + (f"({l['alt_src']} {l['alt_spaces']}면)" if l.get("alt_spaces") is not None
                                              and l["alt_spaces"] != l["spaces"] else ""))
        if l.get("paid"):
            bits.append(l["paid"])
        for fee in l.get("fees") or []:
            bits.append(f"{fee['text']}({fee['src']})")
        if l.get("confirm"):
            bits.append(f"{l['differ']} 출처마다 다름 — 방문 전 전화 확인")
        if l.get("contact"):
            bits.append(f"문의 {l['contact']}")
        return f"{l['name']} (" + ", ".join(b for b in bits if b) + f") {l['addr']}"

    # -- guides
    def guide(self, g: dict) -> str:
        S = self.S
        summary = present.decaution(_clean(g.get("summary")))
        answer = (present.sentences(summary) or [""])[0]
        en = self.en_path(g["_path"])
        parts = [f"G {g['_path']}", _clean(g["title"]), _short_line(answer, GUIDE_LINE_MAX)]
        L = [f"{_clean(g['title'])} — 가이드" + (f" ({_clean(g.get('label'))})" if g.get("label") else ""), "요약: " + summary]
        body = g.get("body") or []
        srcs = g.get("sources") or []
        # the dates and the timetables come first: a long guide is cut at DOC_LIMIT (and get_pages reads 6,000 characters)
        dates = _dates(_clean(g.get("checked_at")), _clean(g.get("reviewed_at")), _clean(g.get("approved_at")))
        timetables = _effective(srcs)
        L.append(dates)
        if timetables:
            L.append("시간표 시행일: " + "; ".join(timetables))
        L += self.booking_lines(booking.guide_targets(S, g))   # before the body: a long guide is cut at DOC_LIMIT
        at = next((i for i, b in enumerate(body, 1) if _chain_lines(_clean(b.get("text")))), 0)
        if at:   # the summary names stop times too ('○○ 기준 시각은 …'): how to read them, and where they are spelled out
            L.append(f"시각 읽는 법: '○○ 기준 시각'은 버스가 그 정류장에 오는 시각이라 그 정류장에서 타는 시각이고, 그 정류장으로 "
                     f"가는 차가 출발하는 시각이 아니다. 정류장·방향·첫차·막차와 정류장마다 돌아가는 차는 {g['_path']}#h-b{at} 절에 "
                     f"한 줄씩 풀어 두었다.")
            # the way back from each stop, here too: a reader of the whole guide asks it as often as of the section
            back = [x for x in _chain_lines(_clean(body[at - 1].get("text")))
                    if x.startswith("돌아오는 길:") or " 쪽으로 가는 차: " in x]
            if back:
                L.append(f"#h-b{at} 시간표에서 돌아가는 차(그 절의 값 그대로):")
                L += [f"- {x}" for x in back]
        if body:
            L.append("본문 절(get_pages에 '경로#h-bN'으로 한 절만 읽을 수 있다):")
            L += [f"- #h-b{i} {_clean(b.get('heading'))}" for i, b in enumerate(body, 1)]
        items = []
        for it in g.get("items") or []:
            t = S.ent_by_slug.get(it.get("place_slug") or "")
            name = t["name"] if t else _clean(it.get("name"))
            if name:
                items.append(f"- {name}{' ' + t['_path'] if t else ''}: {present.decaution(_clean(it.get('reason')))}")
        if items:
            L.append(f"이 가이드의 장소 {len(items)}곳:")
            L += items
        faqs = [x for x in g.get("faq") or [] if x.get("q") and x.get("a")]
        if faqs:
            L.append("자주 묻는 질문:")
            L += [f"- Q {_clean(x['q'])} A {present.decaution(_clean(x['a']))}" for x in faqs]
        if srcs:
            L.append("출처: " + "; ".join(f"{_clean(s.get('name') or s.get('title'))} {s.get('url') or ''}".strip() for s in srcs))
            self.keep_url(*(s.get("url") for s in srcs))
        self.add_doc(g["_path"], _clean(g["title"]), "guide", "\n".join(L), en)
        for i, b in enumerate(body, 1):
            text = "\n".join(present.decaution(_clean(p)) for p in str(b.get("text") or "").split("\n") if p.strip())
            extra = _chain_lines(_clean(b.get("text")))
            if timetables and "시간표" in text:   # this section's times come from a dated timetable
                extra.append("이 절의 시간표: " + "; ".join(timetables))
            extra.append(f"가이드 {dates}")
            self.add_doc(f"{g['_path']}#h-b{i}", f"{_clean(g['title'])} — {_clean(b.get('heading'))}", "section",
                         "\n".join([_clean(b.get("heading")), text, *extra]), en, head=_clean(b.get("heading")))
        return SEP.join(p for p in parts if p)

    # -- courses
    def course(self, c: dict) -> str:
        cv = self.S.course_vms[c["slug"]]
        stops = [s["name"] for s in cv["stops"]]
        en = self.en_path(c["_path"])
        head = cv["display"] + (f" ({cv['group']})" if cv.get("group") else "") + (f", {cv['duration']}" if cv.get("duration") else "")
        parts = [f"C {c['_path']}", head, f"경유지 {len(stops)}곳: " + " > ".join(stops), cv.get("closed_note") or ""]
        L = [f"{head} — 여행 코스", "요약: " + _clean(cv.get("lede"))]
        for r in cv["rows"]:
            if r["sep"] and r["kind"] == "day":   # the source's day / option heading (1일차, 2일차(1안) …)
                L.append(f"[{r['kind_label']}]")
                continue
            if r["sep"]:
                L.append(f"  ({r['kind_label']}: {r['name']}{' — ' + r['note'] if r.get('note') else ''})")
                continue
            nxt = f" → 다음 경유지까지 직선 {present.dist(r['next_m'])}" if r.get("next_m") else ""
            L.append(f"{r['n']}. {r['name']}{' ' + r['path'] if r['path'] else ''}"
                     f"{' (원문 표기: ' + r['label'] + ')' if r.get('label') else ''}{' (선택 경유지)' if r.get('optional') else ''}"
                     f"{' — ' + r['note'] if r.get('note') else ''}{nxt}")
        if cv.get("taketime"):
            tk = cv["taketime"]
            L.append(f"소요시간(코스 원문): {tk['value']} — {tk.get('source_name', '')} {tk.get('source_url', '')}".rstrip())
        if cv.get("show_total"):
            L.append(f"경유지 사이 직선거리 합: {present.dist(cv['total'])} ({cv['measure_note']}, 실제 이동 거리 아님)")
        # 차 없이 다니기 (present.course_move, QA 2026-10-15 F09): where the course starts and ends, the nearest stops and
        # routes, the timetable's first and last buses of those routes, the guides; never a travel time of our own
        mv = present.course_move(self.S, cv) or {}
        if mv.get("lead"):
            L.append("차 없이: 출발·끝 경유지 근처 버스 정류장(직선거리) — " + "; ".join(
                f"{r['s']['name']}: " + ", ".join(f"'{b['name']}' {b['m']}m" + (f" 시내버스 {b['routes_text']}번" if b["routes"] else "")
                                                for b in r["bus"]) for r in mv["lead"]))
        for R in mv.get("routes") or []:
            fmt = lambda ts, k: ", ".join(f"{t['stop']} {t[k]}({t[k + '_n']}회)" for t in ts)
            line = f"시내버스 {R['no']}번 첫차~막차(시간표 기준 정류장): 평일 가는 편 {fmt(R['out'], 'weekday')}"
            line += f", 돌아오는 편 {fmt(R['back'], 'weekday')}" if R["back"] else ""
            line += "; 토·일·공휴일 같음" if R["same"] else (f"; 토·일·공휴일 가는 편 {fmt(R['out'], 'weekend')}"
                                                         + (f", 돌아오는 편 {fmt(R['back'], 'weekend')}" if R["back"] else ""))
            for t in R["alts"]:
                line += (f"; {t['stop']}: 시간표 {t['every']}, {t['alt']['provider']} {t['alt']['value']} — 출처마다 다름, "
                         f"방문 전 전화 확인 {mv.get('tel', '')}")
            L.append(line)
        if mv.get("routes"):
            tt = mv["tt"]
            L.append(f"시각 출처: {tt.get('source_name', '')} — {tt.get('provider', '')} {tt.get('url', '')} ({tt.get('checked_at', '')} 확인)")
            self.keep_url(tt.get("url"))
        if mv.get("legs"):
            L.append(f"경유지 사이 대중교통 길찾기: 잰 구간 {len(mv['legs'])}곳마다 카카오맵 대중교통 길찾기 링크가 페이지에 있다(경로와 시간은 지도 앱이 계산).")
        if mv.get("guides"):
            L.append("차 없이 다니는 법 가이드: " + ", ".join(f"{g['label']} {g['path']}" for g in mv["guides"]))
        L.append("이동: 경유지 사이 값은 직선거리다. 구간별 소요시간" + ("은 자료에 없다(이동 미확인)." if cv.get("taketime")
                                                         else "·총 소요시간은 자료에 없다(이동 미확인)."))
        if cv.get("closed_note"):
            L.append(f"쉬는 날 주의: {cv['closed_note']}")
        L += self.booking_lines(booking.course_targets(self.S, c))
        if cv.get("orig_url"):
            L.append(f"출처: {cv['orig_name']} {cv['orig_url']}")
            self.keep_url(cv["orig_url"])
        orig = c.get("original") or {}
        L.append(_dates(_clean(orig.get("collected_at")), _clean(c.get("reviewed_at")), _clean(c.get("approved_at")),
                        checked_label="원문 수집"))
        self.add_doc(c["_path"], cv["display"], "course", "\n".join(L), en)
        return SEP.join(p for p in parts if p)

    # -- events
    def series(self, sr: dict) -> str:
        ev = sr["newest"]
        place = _clean(ev.get("place_name"))
        fee = _clean(ev.get("fee"))
        latest = f"최근 회차 {_period(ev)}" + (f" · 장소 {place}" if place else "") + (f" · 요금 {fee}" if fee else "")
        if sr.get("newest_alt_labels"):
            latest += f" · {'·'.join(sr['newest_alt_labels'])} 두 출처 다름"
        past = ", ".join(_when(x.get("start_date"))[:7] for x in sr.get("past") or [])
        usual = _clean((sr.get("usual") or [{}])[0].get("text"))
        en = self.event_en.get(sr["_path"], "")
        parts = [f"E {sr['_path']}", _clean(sr["name"]), latest, f"이전 회차 {past}" if past else "",
                 f"보통: {_short_line(usual, GUIDE_LINE_MAX)}" if usual else ""]
        L = [f"{_clean(sr['name'])} — 행사·축제 (회차 {len(sr['editions'])}개)"]
        for x in sorted(sr["editions"], key=lambda x: (x.get("start_date") or "", x.get("name", "")), reverse=True):
            L.append(f"[{_clean(x.get('name'))}] 기간: {_period(x)}"
                     + (f" (원문 표기: {_clean(x.get('period_text'))})" if x.get("period_text") else ""))
            for k, lab in (("place_name", "장소"), ("place_detail", "세부 장소"), ("address", "주소"), ("playtime", "시간"),
                           ("fee", "요금"), ("tel", "문의"),
                           ("homepage", "누리집"), ("sponsor", "주최·주관")):
                v = _clean(x.get(k))
                if v:
                    L.append(f"- {lab}: {display_address(v) if k == 'address' else v}")
            for k, vals in (x.get("alternatives") or {}).items():
                for a in vals or []:
                    L.append(f"- {k} 다른 출처 값: {_clean(a.get('value'))} — {_clean(a.get('source_name'))} → 출처마다 값이 달라 방문 전 확인")
                    self.keep_url(a.get("source_url"))
            for h in x.get("highlights") or []:
                L.append(f"- 프로그램: {_clean(h)}")
            for n in x.get("notes") or []:
                L.append(f"- 참고: {_clean(n)}")
            src = _clean(x.get("source_name"))
            if src or x.get("source_url"):
                L.append(f"- 출처: {src} {x.get('source_url') or ''}".rstrip() + (f" (출처 확인 {x['checked_at']})" if x.get("checked_at") else ""))
            for a in x.get("also_sources") or []:
                L.append(f"- 함께 본 출처: {_clean(a.get('name'))} {a.get('url') or ''}".rstrip())
                self.keep_url(a.get("url"))
            self.keep_url(x.get("source_url"), x.get("homepage"))
        for u in sr.get("usual") or []:
            L.append(f"보통 언제 열리나: {_clean(u.get('text'))} ({_clean(u.get('source_name'))})")
        places = [self.S.ent_by_slug[s] for s in sr.get("place_slugs") or [] if s in self.S.ent_by_slug]
        if places:
            L.append("관련 장소: " + "; ".join(f"{p['name']} {p['_path']}" for p in places))
        self.add_doc(sr["_path"], _clean(sr["name"]), "event", "\n".join(L), en)
        return SEP.join(p for p in parts if p)

    # -- /abroad/ articles
    def abroad(self, a: dict) -> str:
        key = f"abroad:{a['id']}"
        places = "·".join(p["name"] for p in a.get("_places") or [])
        lang = f" {a['lang']}" if a.get("lang") else ""
        parts = [f"A {key}", f"{_clean(a.get('outlet'))} {a.get('date') or '날짜 없음'}{lang}", _clean(a.get("note")),
                 f"장소 {places}" if places else ""]
        L = [f"{_clean(a.get('title'))} — {_clean(a.get('outlet'))} ({a.get('date') or '날짜 없음'})",
             f"우리가 쓴 한 줄 소개: {_clean(a.get('note'))}", f"원문: {a['url']} (이 사이트는 원문을 옮기지 않고 링크만 건다)",
             "실린 곳: /abroad/"]
        if a.get("_places"):
            L.append("관련 장소: " + "; ".join(f"{p['name']} {p['_path']}" for p in a["_places"]))
        self.keep_url(a["url"])
        self.add_doc(key, _clean(a.get("title")), "abroad", "\n".join(L), page="/abroad/")
        return SEP.join(p for p in parts if p)

    # -- videos
    def video(self, v: dict) -> None:
        g = self.video_topic.get(v["youtube_id"])
        places = [self.S.ent_by_slug[s] for s in v.get("place_slugs") or [] if s in self.S.ent_by_slug]
        kind = {"official": "공식 채널", "broadcaster": "방송사", "creator": "크리에이터"}.get(v.get("channel_kind"), "")
        L = [f"{_clean(v['title'])} — YouTube 영상", f"채널: {_clean(v.get('channel'))}" + (f" ({kind})" if kind else ""),
             f"올린 날: {v.get('published_date') or '모름'}", f"주소: {v['url']}"]
        if g:
            L.append(f"실린 곳: {g['_path']} ({g['title']} 영상)")
        if places:
            L.append("관련 장소: " + "; ".join(f"{p['name']} {p['_path']}" for p in places))
        if v.get("event_names"):
            L.append("관련 행사: " + ", ".join(_clean(n) for n in v["event_names"]))
        if (v.get("lang") or "ko") != "ko":
            L.append(f"언어: {v['lang']} (해외에서 본 {self.S.site.get('region', '')} /abroad/에도 실림)")
        self.keep_url(v["url"])
        self.add_doc(f"video:{v['youtube_id']}", _clean(v["title"]), "video", "\n".join(L), page=g["_path"] if g else "/videos/")

    def video_page(self, g: dict) -> str:
        items = g["items"]
        official = sum(1 for v in items if v.get("channel_kind") == "official")
        label = "그 밖의" if g["title"] == "기타" else g["title"]
        L = [f"{label} 영상 {len(items)}편 — 공식 채널 {official}편 (최신순)"]
        L += [f"- {_clean(v['title'])} — {_clean(v.get('channel'))}, {v.get('published_date') or '날짜 없음'}, video:{v['youtube_id']}"
              for v in items[:60]]
        if len(items) > 60:
            L.append(f"… 나머지 {len(items) - 60}편은 페이지에서")
        self.add_doc(g["_path"], f"{label} 영상", "page", "\n".join(L))
        return SEP.join([f"V {g['_path']}", f"{label} 영상 {len(items)}편(공식 채널 {official}편)"])

    # -- themes and site pages
    def theme_lines(self) -> list[str]:
        S, out = self.S, []
        for t in sorted(S.themes, key=lambda t: t["slug"]):
            members = [e for e in S.entities if t["slug"] in (e.get("themes") or [])]
            if not members:
                continue
            path = f"/themes/{t['slug']}/"
            out.append(SEP.join([f"T {path}", f"{t['name']} 여행지 {len(members)}곳", _clean(t.get("description"))]).rstrip(" |"))
            self.add_doc(path, f"{t['name']} 여행지", "page", f"{t['name']} 여행지 {len(members)}곳:\n"
                         + "\n".join(f"- {e['name']} {e['_path']}" for e in sorted(members, key=lambda e: present.name_key(e["name"]))))
        return out

    def site_pages(self) -> list[str]:
        S = self.S
        site = S.site
        region = site.get("region", "")
        n = {k: len(v) for k, v in S.lists.items()}
        op = site.get("operator") or {}
        contact = op.get("contact") or ""
        C = city.current()
        regions = [r for r in S.region_names if r != C.none_label and any(e["_region"] == r for e in S.entities)]
        if S.anchors:   # the rule in force, as the map page states it
            rule = ("권역은 좌표가 있는 장소를 가장 가까운 기준 장소(" + "·".join(f"{a['name']} {a['place']}" for a in S.anchors)
                    + ")에 묶고" + (f", 기준 장소에서 직선 {C.far_m // 1000}km보다 먼 곳은 '{C.far_label}'" if C.far_m else "")
                    + ", 좌표가 없으면 같은 읍·면·동의 권역을 따른다")
        elif C.region_method == "district" and regions:
            rule = ("권역은 주소의 구·군(일부는 법정동)으로 나눈다: " + "; ".join(C.region_rule_lines())
                    + (f". {C.region_rule_note}" if C.region_rule_note else ""))
        else:
            rule = ""
        pages = [
            ("/", f"홈 — {site.get('site_name', '')}: 관광지 {n.get('attraction', 0)}곳·음식점 {n.get('food', 0)}곳·"
                  + "".join(f"{KIND_LABELS[k]} {n[k]}곳·" for k in ("cafe", "shopping") if n.get(k))
                  + f"숙소 {n.get('stay', 0)}곳, 가이드 {len(S.guides)}편·코스 {len(S.courses)}개·행사 {len(S.series)}개·영상 {len(S.videos)}편",
             _clean(site.get("description"))),
            ("/places/", f"관광지 목록 {n.get('attraction', 0)}곳 (유형·테마·지역으로 거르기, 지도)", ""),
            # a list page the build makes only when it has places (build.py: /places/ always): an empty one is no
            # page to link (review 2026-10-19 — '/food/ 음식점 목록 0곳' sent the assistant to a 404)
            *([("/food/", f"음식점 목록 {n['food']}곳 (대표 메뉴·영업시간·쉬는 날)", "")] if n.get("food") else []),
            *([("/cafes/", f"카페·디저트 목록 {n['cafe']}곳 (카페·찻집·제과점, 대표 메뉴·영업시간·쉬는 날)", "")]
              if n.get("cafe") else []),
            *([("/shopping/", f"쇼핑 목록 {n['shopping']}곳 (시장·상점, 영업시간·쉬는 날·주차)", "")]
              if n.get("shopping") else []),
            *([("/stays/", f"숙소 목록 {n['stay']}곳 (체크인·체크아웃·주차·문의)", "")] if n.get("stay") else []),
            ("/guides/", f"목적별 가이드 {len(S.guides)}편", ""),
            ("/courses/", f"여행 코스 {len(S.courses)}개 ({city.current().official['name']} 안내 코스)", ""),
            ("/events/", f"행사·축제 일정 {len(S.series)}개 (월별 기간·장소)", ""),
            ("/map/", "지도·지역: 읍·면·동 묶음" + (f"과 여행 권역({', '.join(regions)})" if regions else ""), rule),
            ("/search/", "검색: 장소 이름·다른 이름·대표 메뉴·동 이름·코스·가이드·행사 이름으로 찾는다", ""),
            ("/videos/", f"영상 {len(S.videos)}편, 주제별 (공식 채널 표시, 누를 때만 YouTube 불러옴)", ""),
            ("/abroad/", f"해외에서 본 {region}: 외신·해외 매체 기사 {len(S.abroad)}건과 외국어 영상 {len(S.abroad_videos)}편", ""),
            ("/about/", f"소개·출처: 운영 {op.get('name', '')}, 공식 사이트 아님(독립 운영), 출처 {self.source_names()}, "
                        f"{f'정정 요청 {contact}, ' if contact else ''}사이트 안내 챗봇 설명 /about/#chatbot", ""),
        ]
        out = []
        for path, line, extra in pages:
            if path in ("/videos/",) and not S.videos or path == "/abroad/" and not (S.abroad or S.abroad_videos) \
                    or path in ("/guides/",) and not S.guides or path == "/courses/" and not S.courses \
                    or path == "/events/" and not S.series:
                continue
            en = self.en_path(path)
            out.append(SEP.join(p for p in (f"S {path}", line) if p))
            self.add_doc(path, line.split(":")[0].split(" — ")[0], "page", line + (f"\n{extra}" if extra else ""), en)
        self.about_doc()
        if site.get("emergency"):
            out.append(self.emergency(site["emergency"]))
        return out

    def source_names(self) -> str:
        """The sources the built pages cite: the city's tourism site only when a record cites it (State.source_used)."""
        S = self.S
        names = [*([(S.site.get("source") or {}).get("name", "")] if S.source_used else []), "한국관광공사 TourAPI"]
        return "·".join(n for n in names if n)

    def emergency(self, em: dict) -> str:
        """The emergency numbers the about pages list (#emergency; site.json emergency, operator 2026-10-15): one short
        catalog line without addresses (prompt rule 14 answers from it at once, without a tool) and a doc with each
        number's source, the address it came from and 출처 확인일, and the words a reader may search with."""
        src = em.get("sources") or {}
        checked = em.get("checked_at") or ""
        nums = ", ".join(f"{x['tel']} {x['ko']}" + (f" 해외 {x['abroad']}" if x.get("abroad") else "")
                         for x in em.get("lines") or [])
        phrases = "·".join(f"'{p}'" for p in em.get("phrases") or [])
        line = SEP.join(["S /about/#emergency", f"긴급 연락처(출처 확인 {checked}): {nums}"
                         + (f"; 통역: 연결 뒤 {phrases}" if phrases else "")])
        L = ["긴급 연락처 — 여행 중 위급할 때(사람이 쓰러짐·다침·화재·범죄·물에 빠짐·아이를 잃어버림) 바로 전화",
             "페이지: /about/#emergency (언어판마다 같은 절이 있다)"]
        for x in em.get("lines") or []:
            s = src.get(x.get("src")) or {}
            L.append(f"- {x['tel']}: {x['ko']}" + (f" — 해외에서 걸 때 {x['abroad']}" if x.get("abroad") else "")
                     + f" — {s.get('provider', '')} {s.get('url', '')} (출처 확인 {checked})")
        for x in em.get("steps") or []:
            s = src.get(x.get("src")) or {}
            L.append(f"- {x['ko']} — {s.get('provider', '')} {s.get('url', '')} (출처 확인 {checked})")
        L.append("이 사이트는 응급처치·의료 안내를 하지 않는다. 찾는 말: 응급, 구급차, 긴급, 경찰, 소방, 통역, 신고")
        self.keep_url(*(s.get("url") for s in src.values()))
        self.add_doc("/about/#emergency", "긴급 연락처", "page", "\n".join(L), self.en_path("/about/"), head="긴급 연락처")
        return line

    def about_doc(self) -> None:
        S = self.S
        site = S.site
        op = site.get("operator") or {}
        src = site.get("source") or {}
        L = [f"{site.get('site_name', '')} — 소개·출처",
             _clean(site.get("description")), _clean(site.get("disclaimer")),
             f"운영: {op.get('name', '')}{'(' + op['name_en'] + ')' if op.get('name_en') else ''}"
             + (f", 편집 책임 {site['editor']['name']}" if (site.get("editor") or {}).get("name") else "")
             + (f", 정정 요청 {op['contact']}" if op.get("contact") else ""),
             f"공식 제휴: {site.get('affiliation') or '없음 — 지자체·기관의 공식 사이트가 아니다'}",
             (f"원문 출처: {src.get('name', '')} {src.get('url', '')}. " if S.source_used else
              f"정보 출처: {self.source_names()}. ")
             + "장소의 실용 정보(이용시간·요금 등)는 값마다 출처를 적고, "
             "출처끼리 값이 다르면 둘 다 싣는다. 출처에 없는 항목은 '확인 필요'로 표시한다.",
             "사진: 한국관광공사 TourAPI의 공공누리 제1·3유형만, 출처와 함께. 제3유형은 자르거나 보정하지 않는다.",
             "거리: 코스·가이드·주변 목록의 거리는 모두 좌표 사이의 직선거리다.",
             "사이트 안내 챗봇(/about/#chatbot): 이 사이트에 실린 정보로만 답하고 답마다 페이지 링크를 단다. 모델은 Anthropic의 "
             "Claude Haiku 5.5. AI 답은 틀릴 수 있어 방문 전 확인이 필요하다. 예약·결제·회원가입은 하지 않고, 공식 예약 페이지 "
             "링크만 단다.",
             "예약하기: " + LC.BOOK_WORDS["ko"]["about"],
             "챗봇이 보내고 남기는 것: ① 브라우저 — 대화는 이 탭(sessionStorage)에만 남고, '새 대화'를 누르거나 탭을 닫으면 "
             "지워진다. ② 이 사이트의 서버 함수(/api/chat/) — 질문할 때마다 새 질문과 그 앞의 대화(최근 12개 메시지, 이전 답은 "
             "2,000자까지), 보고 있는 페이지 주소, 화면 언어를 받는다. 대화를 저장하지 않고, 서버 기록에는 처리 상태와 사용량 "
             "숫자만 남는다(질문·답의 글은 남기지 않음). ③ 외부 AI(Anthropic API) — 답을 만들려고 서버 함수가 위 내용을 "
             "Anthropic API로 보낸다. 그쪽의 처리·보관은 Anthropic의 정책을 따르고, 이 사이트는 이미 보낸 내용을 지울 수 없다.",
             "개인정보: 이름·전화번호·이메일을 자동으로 가리는 기능은 없다. 잘못 입력했다면 '새 대화'를 누른다. 그러면 이 탭의 "
             "대화가 지워지고 다음 질문부터는 보내지 않는다(그대로 두면 다음 질문 때 앞의 대화와 함께 다시 보낸다). 이미 보낸 "
             "질문은 되돌릴 수 없다."]
        self.add_doc("/about/", "소개·출처", "page", "\n".join(x for x in L if x), self.en_path("/about/"))

    # -- output
    def catalog(self) -> str:
        return month_ranges("\n".join(self.lines).rstrip("\n")) + "\n"

    def docs_json(self) -> dict:
        alias = {}
        for key, d in self.docs.items():
            if "#" in key:
                continue
            for path in [d.get("e"), *(d.get("l") or {}).values()]:
                if path and path not in alias:
                    alias[path] = key
        out = {"v": VERSION, "site": self.site, "docs": dict(sorted(self.docs.items())),
               "alias": dict(sorted(alias.items())), "ext": sorted(self.ext), "book": dict(sorted(self.book.items()))}
        # the combined tickets' tables for the fee_total tool (pipeline/tickets.py; chatbot/knowledge.js feeTotal)
        data = getattr(self.S, "tickets", None) or {}
        if data.get("tickets"):
            out["tickets"] = tickets.export(data, self.place_ref)
        return out

    def index_json(self) -> dict:
        out = {}
        for key, d in sorted(self.docs.items()):
            head = tokens(f"{d['t']} {key if key.startswith('/') else ''}")
            lines = d["x"].split("\n", 3)
            head += [t for t in tokens(lines[0]) if t not in head]
            # a place's other names count as its title: a museum's other name finds the building's page first
            alt = next((x[len("다른 이름: "):] for x in lines[1:3] if x.startswith("다른 이름: ")), "")
            head += [t for t in tokens(alt) if t not in head]
            # its names on the other versions of the site: a Japanese or a German name find the page as its
            # Korean name does (review 2026-10-17 E03: 10 of 16 such names missed the top 8)
            head += [t for t in tokens(" ".join((d.get("n") or {}).values())) if t not in head]
            # web addresses (sources, official links) are not words a reader searches for: 'tour', 'view', '305395'
            body = [t for t in tokens(URL_RX.sub(" ", d["x"].replace(DATES_ASKED_ONLY, " "))) if t not in set(head)]
            out[key] = [" ".join(head), " ".join(body)]
        return {"v": VERSION, "docs": out}


def dumps(obj) -> str:
    return json.dumps(obj, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def site_json(S) -> dict:
    """The site the assistant and the planner answer for (chatbot/site.js): the public address, the site's name, the
    city's name in each language (site.json city.chat.names; Korean defaults to the region), the further origins the
    owner allows (city.chat.origins) and the planner's hubs (city.plan.hubs)."""
    chat = city.current().get("chat", {}) or {}
    names = {k: str(v) for k, v in (chat.get("names") or {}).items() if str(v).strip()}
    if S.site.get("region") and "ko" not in names:
        names["ko"] = S.site["region"]
    return {"url": S.site_url, "name": S.site.get("site_name", ""), "city": names,
            "origins": [str(o) for o in chat.get("origins") or [] if str(o).strip()],
            # the AI course planner's start and end points (city.plan.hubs; chatbot/plan_prompt.js) — none: no hub
            "hubs": {h["key"]: h["name"] for h in city.current().plan["hubs"]}}


def export(S, out: Path) -> dict:
    """Write <out>/chat/catalog.txt, docs.json, index.json and site.json (UTF-8, LF line ends on every system) and
    return the sizes for the build stats."""
    k = Knowledge(S).build()
    target = Path(out) / CHAT_DIR
    target.mkdir(parents=True, exist_ok=True)
    catalog = k.catalog()
    files = {"catalog.txt": catalog, "docs.json": dumps(k.docs_json()) + "\n", "index.json": dumps(k.index_json()) + "\n",
             "site.json": dumps(site_json(S)) + "\n"}
    for name, text in files.items():
        (target / name).write_bytes(text.encode("utf-8"))
    places = sum(1 for line in k.lines if line.startswith("P "))
    return {"catalog_lines": sum(1 for line in k.lines if line[:2] in ("P ", "G ", "C ", "E ", "A ", "V ", "T ", "S ")),
            "places": places, "catalog_chars": len(catalog), "catalog_bytes": len(catalog.encode("utf-8")),
            "catalog_tokens_est": estimate_tokens(catalog), "docs": len(k.docs),
            "docs_bytes": len(files["docs.json"].encode("utf-8")), "index_bytes": len(files["index.json"].encode("utf-8"))}
