"""QA for a built site. Run after every build.

    python -m pipeline.validate --data data/incheon --out dist                      # 공개 기준(엄격)
    python -m pipeline.validate --data data/incheon --out dist-preview --mode preview
    python -m pipeline.validate --data data/sample --out dist-sample --mode sample

Writes reports/qa_report.md. Exit code 1 when any ERROR exists.

What is checked
- every published entity page exists and renders the blocks its tier requires
- structured data parses, describes the same entity and matches the visible text: on every HTML page each
  JSON-LD string value must appear in the visible text or <title> (jsonld_visibility), event dates (startDate,
  endDate) in the text or a <time datetime>, page dates (dateModified, datePublished, lastReviewed) as ISO dates
  that are machine-readable only (operator decision 2026-10-09: no visible check dates), telephone numbers in
  their domestic form, opening-hours times shown, isAccessibleForFree
  only when the fee row reads 무료, amenityFeature/petsAllowed only when the 주차·유모차 대여·반려동물 동반 row
  holds the matching Y/N value
- the source text is shown verbatim only when its licence allows it, never otherwise
- our sentences (place summary · FAQ · 자세히, guide and course text) share no stretch of 15 or more characters with
  a stored source text — a place's TourAPI overview or original, a guide's or course's places' texts — once names and
  fact values are taken out (pipeline/content_check.py; tools/content_check.py adds the number, source and wording
  checks a writer runs before approval)
- canonical, title/description length (a Korean page's description, og:description and twitter:description: a
  warning over build.DESC_MAX = 80 characters), internal links, robots.txt, sitemap.xml, llms.txt
- every stored fact is shown whole in its own row of the facts block (<dd data-key>, else the <dd> under its
  label): the whole textutil.display_value(raw) verbatim, every word and symbol in order (textutil.value_shown),
  and a homepage/booking URL linked in full (fact_shown). Only a row marked data-form that prints a parsed
  timetable/price table may drop the layout punctuation (/ , : ( ) [ ] ※ list dashes) its cells replace.
  Replaced the round-2 probe "first 20 characters anywhere in the block", which is never stricter (round 3).
- facts another source gives differently are shown with both values (same row check), their providers and
  "방문 전 전화 확인"
- no visible check / update / review / collection date (operator decision 2026-10-09, CLAUDE.md 3.2 '확인일 화면
  표시' → data and structured data only): on every HTML page (body, <title>, meta description, og text) and in
  llms.txt / llms-full.txt, no '확인일'·'수집일'·'검수일' label, no '<date> 확인/조회/기준/수집/업데이트', no 'n일 전
  업데이트', no English 'Checked/Updated/Reviewed/Collected <date>', 'As of <date>' or 'n days ago'
  (visible_check_dates). Event dates and periods, timetable 시행일 and a source document's own date stay.
- official designations (schema.designations): every stored one has a label, its list's link and 확인일 (in the
  data) and a list row matched with high/medium confidence and no needs_check flag; each is shown in the facts
  card's '지정' row with the list's name as a link — never its 확인일 — and as a chip linking to the list; JSON-LD
  award holds only those labels, visible on the page; a list page links the lists behind its chips, without
  their 확인일
- production only: review date present, no placeholders, GA4 id, real site_url; every canonical, og:url,
  og:image, sitemap <loc>, robots Sitemap line, llms link and JSON-LD @id/url/breadcrumb item starts with the
  https site_url (og:image may also be a TourAPI photo); index criteria
  (schema.index_status) — a page that meets them is indexable and in sitemap.xml, a page that does not is
  noindex and absent from sitemap.xml, llms.txt and llms-full.txt
- nearby public parking lots and bus stops (access_problems, nearby_data_problems): the place page's '근처 주차·버스'
  rows are exactly nearby.json's entries for the place, each showing its stored values from parking_lots.json /
  nearby.json and no number that is not stored; the block sits outside the facts block (never the place's own parking,
  never counted by the index criteria); nearby.json names only usable lots, within its radius, nearest first.
  Warnings (nearby_stale_problems): a parking distance the current coordinates no longer give, or a published place
  with coordinates and no nearby.json entry — nearby.json has to be made again
- English pages (/en/, with data/<region>/en; validate_en): lang="en", no Korean script outside lang="ko",
  hreflang ko / en / x-default complete and reciprocal, no stale translation rendered, name_en and every English
  fact value (both values + note where sources differ) in its facts row, every designation the Korean page shows
  in English (chip + 'Designations' row with the list's name as a link, no checked date), the Korean index rule
  mirrored; every
  generic check above (JSON-LD visibility, internal links, URL gate) runs over the English pages too
- /abroad/ highlights (data/<region>/abroad_highlights.json, owner 2026-10-13; quotations 2026-10-14;
  highlight_problems): every id is a published abroad.json item that /abroad/ shows, once, with an https source
  address; an article has its quote (a post may have none — only a service whose oEmbed returns the post's text, X,
  can be quoted); a quote is at most HL_QUOTE_MAX characters and HL_QUOTE_WORDS words, not wrapped in quotation marks,
  with its language (quote_lang) and the day it was checked against the original (quote_checked); basis_ko and
  checked are recorded; label_ko is short; the row on /abroad/ links every original, the viewer's markup
  (build.HL_VIEWER, fetched on the first press) holds every quote in a <blockquote> with its lang and the original's
  address, and each quoted article's card on /abroad/ shows it too
- 예약하기 (pipeline/booking.py, booking_problems, booking.data_problems): every place, guide and course page of every
  version links exactly the booking pages booking.view gives it (inside data-block="booking", data-track=
  "booking_click"), each one an address of booking.json or a published place's own booking address, never on an
  excluded host (OTA, Naver, blogs, social networks); a version never opens the Korean page of a service that has a
  page in its language or in English; no other page (home, lists, search …) has a booking button; booking.json's
  services have their address, basis and checked date and a name in every language, its places are published
- places that belong together (data part_of, pipeline/relations.py, operator decision 2026-10-16; relation_page_problems):
  every relation is well formed, points at a built place, does not loop or run deeper than 3 levels, and every basis
  code it states reproduces from the two records (relations.evidence) — a relation cannot be invented; two built places
  that share a TourAPI contentid have a relation. On each built page, Korean and every version: an inside child
  links its parent in its relation line (a parent without a page in that version: its name, no link), same-building
  pages link each other, a parent lists every part that has a page there and nothing else, the nearby rows and the
  similar-name rows never show the page's own family nor an alias beside its parent, and JSON-LD containedInPlace /
  containsPlace say exactly the same (same_building: neither). Warning: same-building partners whose shared facts
  differ without each listing the other's value (relations.fact_differences)
- the site assistant's catalog (chat/catalog.txt, the prompt's cached part): a warning when its estimated tokens
  (chat_index.estimate_tokens) exceed the design budget chat_index.CATALOG_BUDGET — never an error, the collection
  grows day by day (operator decision 2026-10-20)
"""
from __future__ import annotations

import argparse
import json
import math
import re
import sys
import xml.etree.ElementTree as ET
from html import unescape
from html.parser import HTMLParser
from pathlib import Path
from urllib.parse import unquote, urlsplit

from . import art, ask, booking, chat_index, city, en_site, notices, present, relations, tickets
from .content_check import copy_issues, guide_issues
from . import locales as LC
from .build import DESC_MAX, HL_VIEWER, LISTS, MODES, State, fact_row, index_counts, load_abroad
from .jsonld import AMENITY_VALUES, amenity_value
from .maplinks import DEFAULT_TMAP_SCHEME, build_links, precision_summary
from .schema import (ENTITY_TYPES, FACT_LABELS, FACT_ORDER, FIT_ORDER, REQUIRED_BLOCKS,
                     designation_problems, designations, geo_provider, is_default_point, license_allowed,
                     nearby_geo_providers, nearby_provider, node_types, parking_seats_half, parking_seats_part)
from .textutil import (address_key, dead_reason, dead_tokens, display_value, link_url, phone_domestic, sha256_text,
                       squash_ws, url_key, value_shown, value_tokens)

VOID = {"area", "base", "br", "col", "embed", "hr", "img", "input", "link", "meta", "param", "source", "track", "wbr"}
HANGUL = re.compile(r"[ᄀ-ᇿㄱ-ㆎ가-힣]")
MIN_LEN = {"summary": 20, "facts": 10, "directions": 5, "nearby": 5, "media": 5, "faq": 10, "original": 10, "sources": 10}
PLACEHOLDERS = ("[샘플]", "TODO", "TBD", "lorem ipsum", "연락처 입력", "(입력)", "example.com")
SITEMAP_NS = "{http://www.sitemaps.org/schemas/sitemap/0.9}"
# JSON-LD keys whose values are links, codes or machine values rather than text a reader sees
VISIBILITY_SKIP = {"url", "item", "image", "contentUrl", "license", "acquireLicensePage", "sameAs", "isBasedOn",
                   "mainEntityOfPage", "hasMap", "inLanguage", "addressCountry", "latitude", "longitude",
                   "dayOfWeek", "opens", "closes", "validFrom", "validThrough"}
EVENT_DATE_KEYS = {"startDate", "endDate"}                         # an event's own dates: shown on the page
PAGE_DATE_KEYS = {"dateModified", "datePublished", "lastReviewed"}  # check / review dates: machine-readable only
ISO_DATE = re.compile(r"^\d{4}-\d{2}-\d{2}$")
# Visible check / update / review / collection dates (operator decision 2026-10-09: the dates stay in the data,
# JSON-LD and sitemap lastmod, never on a page). Event dates, timetable 시행일 ('2024.10.21 시행 시간표 기준'),
# a schedule day ('2026-10-13 배차') and a source document's own date ('보도자료(2026-09-11)') do not match.
_KO_DATE = r"(?:\d{4}\s?[-.]\s?\d{1,2}\s?[-.]\s?\d{1,2}\.?|\d{4}년\s?\d{1,2}월\s?\d{1,2}일)"
_EN_DATE = (r"(?:\d{4}-\d{2}-\d{2}|(?:Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Sept|Oct|Nov|Dec)[a-z]*\.? \d{1,2},? \d{4}"
            r"|\d{1,2} (?:Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)[a-z]* \d{4})")
CHECK_DATE = re.compile("|".join([
    r"(?:정보 |일정 |원문 )?(?:확인일|수집일|검수일)",
    rf"{_KO_DATE}\)?\s?(?:에\s?)?(?:확인(?!\s?필요|되)|조회|수집|검수|업데이트|갱신)",
    rf"{_KO_DATE}\s?기준",
    r"\d+\s?(?:일|시간|분|주|개월)\s?전\s?(?:업데이트|확인|갱신|수정)",
    rf"\b(?:[Cc]hecked|[Uu]pdated|[Rr]eviewed|[Cc]ollected|[Rr]etrieved|[Vv]erified|[Tt]ranslated)(?: into English)?"
    rf"(?: on)?:? {_EN_DATE}",
    rf"\b[Aa]s of {_EN_DATE}",
    r"\b\d+ (?:days?|hours?|weeks?|months?) ago\b",
    r"\b(?:Information checked|Last (?:checked|updated|reviewed)|Source collected|Translated into English)\b",
]))


def visible_check_dates(text: str) -> list[str]:
    """Check / update / review / collection dates (or their labels) in visible text — none may remain."""
    return [m.group(0) for m in CHECK_DATE.finditer(squash_ws(text))]


def notice_problems(S, out: Path) -> list[tuple[str, str]]:
    """data/<region>/notices.json (pipeline/notices.py, operator decision 2026-10-15): every entry has its provider,
    url, checked_at and until and names published places only; a notice still current (until ≥ the build date) is
    on each of its places' pages in every version this build has, and one past its `until` is on none of them."""
    found = [("notices.json", x) for x in notices.problems(S.notices_all, {p["id"]: p for p in S.entities_all})]
    paths: dict[str, list[str]] = {e["id"]: [e["_path"]] for e in S.entities}
    for site in (getattr(S, "intl", None) and S.intl.sites or {}).values():
        for p in site.places.values():
            paths.setdefault(p["e"]["id"], []).append(p["path"])
    current = {n["id"] for n in S.notices}
    for n in S.notices_all:
        nid = str(n.get("id") or "")
        for path in [x for pid in (n.get("place_ids") or []) for x in paths.get(pid, [])] if nid else []:
            f = _file_for(out, path)
            if not f.exists():
                continue
            shown = f'data-notice="{nid}"' in f.read_text("utf-8")
            if nid in current and not shown:
                found.append((path, f"현재 공지가 화면에 없음: {nid}"))
            elif nid not in current and shown:
                found.append((path, f"끝난(until이 지난) 또는 잘못된 공지가 화면에 남음: {nid}"))
    return found


def dead_link_problems(text: str, hrefs: list[str], dead: dict | None) -> list[str]:
    """A link to, or the written form of, an address data/<region>/dead_links.json lists (QA 2026-10-15 SRC-02):
    build.State drops them from the data, so one found here came in through prose or a template."""
    if not dead:
        return []
    out = []
    for href in dict.fromkeys(hrefs):
        reason = dead_reason(href, dead) if urlsplit(href).scheme in ("http", "https") else ""
        if reason:
            out.append(f"종료·없는 주소 링크: {href} ({reason})")
    low = (text or "").lower()
    out += [f"종료·없는 주소가 글에 남음: {t}" for t in dead_tokens(dead) if t.lower() in low]
    return out


def booking_expectations(S, out: Path) -> dict[str, list[dict]]:
    """{page file as '/path/index.html': the booking buttons it must show (booking.view)} for every place, guide and
    course page of Korean and every version; a page not in it may show none."""
    def rel(path: str) -> str:
        return "/" + str(_file_for(out, path).relative_to(out)).replace("\\", "/")
    exp: dict[str, list[dict]] = {}
    for e in S.entities:
        exp[rel(e["_path"])] = booking.view(booking.place_targets(S, e), "ko")
    for g in S.guides:
        exp[rel(g["_path"])] = booking.view(booking.guide_targets(S, g), "ko")
    for c in S.courses:
        exp[rel(c["_path"])] = booking.view(booking.course_targets(S, c), "ko")
    intl = getattr(S, "intl", None)
    for code, site in (intl.sites.items() if intl else []):
        ink = (lambda t: lambda n: t.s("in_korean_paren", name=n))(site.t)
        for p in site.places.values():
            exp[rel(p["path"])] = booking.view(booking.place_targets(S, p["e"]), code, ink)
        for x in site.guides.values():
            exp[rel(x["path"])] = booking.view(booking.guide_targets(S, x["g"]), code, ink)
        for x in site.courses.values():
            exp[rel(x["path"])] = booking.view(booking.course_targets(S, x["c"]), code, ink)
    return exp


def booking_problems(S, page: "PageScan", expect: list[dict] | None, code: str = "ko",
                     allowed: set[str] | None = None) -> list[str]:
    """예약하기 (pipeline/booking.py) on one page: expect = booking.view for a place, guide or course page, None for
    any other page (which may have no booking button). Each booking_click link sits in data-block="booking", opens an
    address of booking.json or a published place's own booking address (allowed: url_key forms) and never an excluded
    host; the page shows exactly the expected addresses; a version (code) never opens a service's Korean page when the
    service has a page in its language or in English."""
    reg = booking.registry(S)
    links = [x for x in page.tracked if x["track"] == "booking_click"]
    if expect is None:
        return [f"예약 버튼은 장소·가이드·코스 페이지에만 둔다 — 이 페이지에 {len(links)}개"] if links else []
    allowed = booking.allowed_urls(S) if allowed is None else allowed
    out = []
    for x in links:
        href = x["href"]
        if "booking" not in x["blocks"]:
            out.append(f"예약 버튼이 data-block=\"booking\" 밖에 있음: {href}")
        if booking.excluded(href, reg):
            out.append(f"예약 버튼이 버튼에서 빼는 호스트(OTA·네이버·블로그·SNS)로 감: {href}")
        if url_key(href) not in allowed:
            out.append(f"예약 버튼 주소가 booking.json·공개 장소의 예약 주소에 없음: {href}")
        if code != "ko":
            for s in (reg.get("services") or {}).values():
                if url_key(href) == url_key(s.get("url")) and booking.page_lang(s.get("pages") or {}, code):
                    out.append(f"{code} 페이지가 한국어 예약 페이지로 감 — 이 언어나 영어 페이지가 booking.json에 있음: {href}")
    got = [x["href"] for x in links if "booking" in x["blocks"]]
    want = [b["url"] for b in expect]
    out += [f"데이터에 있는 공식 예약 페이지 버튼이 없음: {u}" for u in want if u not in got]
    out += [f"데이터와 다른 예약 버튼: {u}" for u in got if u not in want]
    return out


# /abroad/ highlights (owner 2026-10-13; quotations 2026-10-14, CLAUDE.md 3.10): a short verbatim passage of the
# original in its own language — one or two consecutive sentences — with the outlet / author and the link
HL_QUOTE_MAX = 300      # characters
HL_QUOTE_WORDS = 45     # space-separated words (a Japanese or Chinese passage is held by HL_QUOTE_MAX)
HL_QUOTE_PLATFORMS = ("x",)   # services whose official oEmbed returns the post's own text (tools/abroad_quotes.py)
HL_WRAPPED = re.compile("^[\"'“‘「『«＂].*[\"'”’」』»＂]$", re.S)
HL_LANG = re.compile(r"^[a-z]{2,3}(-[A-Za-z0-9]{2,8})*$")
HL_LABEL_MAX = 8


def highlight_problems(data_dir: Path) -> list[str]:
    """data/<region>/abroad_highlights.json: every id is a published abroad.json item that /abroad/ shows (an article,
    or a post on a service with an embed), once, with an https address to quote from; an article has its quote, a post
    only on a service whose oEmbed gives its text (HL_QUOTE_PLATFORMS); a quote is at most HL_QUOTE_MAX characters
    and HL_QUOTE_WORDS words, not wrapped in quotation marks (the page wraps it in a <blockquote>), with quote_lang (a
    language tag) and quote_checked (YYYY-MM-DD, the day tools/abroad_quotes.py found it in the original); basis_ko
    (what the original says, for us) and checked (the day the original was opened) are recorded; label_ko (the
    circle's name), when given, is short."""
    path = Path(data_dir) / "abroad_highlights.json"
    if not path.exists():
        return []
    try:
        raw = json.loads(path.read_text("utf-8")) or {}
        stored = json.loads((Path(data_dir) / "abroad.json").read_text("utf-8")) if (Path(data_dir) / "abroad.json").exists() else {}
    except ValueError as ex:
        return [f"JSON 오류: {ex}"]
    known = {a.get("id"): a for a in (stored or {}).get("items") or []}
    shown = {a.get("id") for a in load_abroad(Path(data_dir))}
    out, seen = [], set()
    for n, h in enumerate(raw.get("items") or [], 1):
        hid = str(h.get("id") or "")
        where = f"items[{n}] {hid or '(id 없음)'}"
        a = known.get(hid) if hid else None
        if not a:
            out.append(f"{where}: abroad.json에 없는 id")
        elif hid not in shown:
            out.append(f"{where}: abroad.json 항목이 /abroad/에 나가지 않음(status·note·platform 확인)")
        if hid and hid in seen:
            out.append(f"{where}: 같은 id가 두 번 있음")
        seen.add(hid)
        quote = squash_ws(h.get("quote"))
        if not quote:
            if a and a.get("kind") != "post":
                out.append(f"{where}: quote(원문 인용) 없음 — 기사 하이라이트는 원문의 한두 문장을 그대로 싣는다")
        else:
            if a and not str(a.get("url") or "").startswith("https://"):
                out.append(f"{where}: 인용문의 원문 주소(abroad.json url, https)가 없음")
            if a and a.get("kind") == "post" and a.get("platform") not in HL_QUOTE_PLATFORMS:
                out.append(f"{where}: {a.get('platform')} 게시물은 oEmbed가 글을 주지 않아 인용문을 원문과 맞춰 볼 수 없음 — quote 없이 임베드로만")
            if len(quote) > HL_QUOTE_MAX:
                out.append(f"{where}: quote {len(quote)}자 — {HL_QUOTE_MAX}자 이하(연속한 1~2문장)로")
            if len(quote.split()) > HL_QUOTE_WORDS:
                out.append(f"{where}: quote {len(quote.split())}단어 — {HL_QUOTE_WORDS}단어 이하로")
            if HL_WRAPPED.match(quote):
                out.append(f"{where}: quote를 따옴표로 감쌈 — 화면이 blockquote로 감싼다")
            if not HL_LANG.match(str(h.get("quote_lang") or "")):
                out.append(f"{where}: quote_lang(원문 언어, 예: en·ja) 없음")
            if not ISO_DATE.match(str(h.get("quote_checked") or "")):
                out.append(f"{where}: quote_checked(원문과 맞춰 본 날, YYYY-MM-DD) 없음")
        if not squash_ws(h.get("basis_ko")):
            out.append(f"{where}: basis_ko(원문에서 확인한 근거) 없음")
        if not ISO_DATE.match(str(h.get("checked") or "")):
            out.append(f"{where}: checked(원문 확인일, YYYY-MM-DD) 없음")
        if len(squash_ws(h.get("label_ko"))) > HL_LABEL_MAX:
            out.append(f"{where}: label_ko {len(squash_ws(h.get('label_ko')))}자 — {HL_LABEL_MAX}자 이하로")
    return out


def _quotations(html: str, cls: str) -> set[tuple[str, str, str]]:
    """(text, lang, cite) of each <blockquote lang cite> (with class cls, or none when cls is '') in html."""
    attr = f' class="{cls}"' if cls else ""
    return {(squash_ws(unescape(re.sub(r"<[^>]+>", "", q))), lang, unescape(cite)) for lang, cite, q in
            re.findall(rf'<blockquote{attr} lang="([^"]+)" cite="([^"]+)">(.*?)</blockquote>', html, re.S)}


FEE_LABELS = (FACT_LABELS["usefee"], "요금")          # place fee row, event fee row (not 주차요금)
AMENITY_LABELS = {FACT_LABELS[k]: k for k in AMENITY_VALUES}   # 주차 / 유모차 대여 / 반려동물 동반 -> fact key
TOURAPI_IMAGE_HOSTS = ("https://tong.visitkorea.or.kr/",)
URL_KEYS = ("homepage", "reservationurl")


class PageScan(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.title, self.h1, self.canonical = "", "", ""
        self.meta: dict[str, str] = {}
        self.jsonld_raw: list[str] = []
        self.blocks: dict[str, str] = {}
        self.notes: list[str] = []          # text of citation lines (class ch-notes: '출처: …' and its translations)
        self._note_depth: int | None = None
        # '확인 필요' lines: (class, text) of each <p class="kf-need"> (first screen) and <p class="need"> (facts card)
        self.needs: list[tuple[str, str]] = []
        self._need_depth: int | None = None
        self.block_hrefs: dict[str, list[str]] = {}   # links inside each data-block (nested blocks: every one)
        # links with data-track: {track, href, hreflang, provider, blocks (the data-blocks around it)}
        self.tracked: list[dict] = []
        self.hrefs: list[str] = []
        self.text: list[str] = []
        self.body_text: list[str] = []      # body text without <title>, <script> or <style> contents
        self.datetimes: list[str] = []      # <time datetime="..."> values
        self.pairs: list[tuple[str, str]] = []   # (<dt> text, <dd> text) of every definition list row
        # fact rows inside the facts block: {keys (data-key), dt, text (pieces joined by spaces, so table cells
        # stay apart), exact (pieces as they run, the visible text), hrefs (links inside the row), form (the row
        # prints a parsed timetable/price table: an element inside it carries data-form)}
        self.fact_rows: list[dict] = []
        self._dt: list[str] | None = None
        self._dd: list[str] | None = None
        self._dd_raw: list[str] = []
        self._dd_hrefs: list[str] = []
        self._dd_form = False
        self._dd_keys: list[str] = []
        self._dd_in_facts = False
        self._last_dt = ""
        self._stack: list[tuple[str, str | None]] = []
        self._in_title = self._in_h1 = self._in_jsonld = self._in_code = False
        self._buf: list[str] = []
        # languages: <html lang>, hreflang links, the records a page renders (data-entity-id / data-record), and
        # Korean script outside an element with lang="ko" (text, <title>, alt / aria-label / title / placeholder,
        # meta description and og text) — the English pages' checks (validate_en)
        self.html_lang = ""
        self.alternates: list[tuple[str, str]] = []
        self.records: list[str] = []
        self.hangul: list[str] = []
        self.foreign: list[str] = []   # text and alt / aria-label / title / placeholder in the page's own language
        self._lstack: list[tuple[str, str | None]] = []
        # '근처 주차·버스' rows (p1.access): {kind 'lot'|'stop', id (data-lot / data-stop), text (visible, as it runs),
        # hrefs, in_facts}; access_in_facts when the block itself sits inside data-block="facts"
        self.access_rows: list[dict] = []
        self.access_in_facts = False
        self._rows_open: list[dict] = []

    def _lang(self) -> str:
        return next((lg for _, lg in reversed(self._lstack) if lg), self.html_lang)

    def handle_starttag(self, tag, attrs):
        a = dict(attrs)
        if tag == "html":
            self.html_lang = a.get("lang") or ""
        elif tag == "link" and a.get("rel") == "alternate" and a.get("hreflang"):
            self.alternates.append((a["hreflang"], a.get("href") or ""))
        if a.get("data-entity-id"):
            self.records.append("place:" + a["data-entity-id"])
        if a.get("data-record"):
            self.records.append(a["data-record"])
        here = a.get("lang") or self._lang()
        if not here.startswith("ko"):
            for k in ("alt", "aria-label", "title", "placeholder"):
                if HANGUL.search(a.get(k) or ""):
                    self.hangul.append(f"<{tag} {k}> {squash_ws(a[k])[:30]}")
                if a.get(k) and here == self.html_lang:
                    self.foreign.append(a[k])
            if tag == "meta" and (a.get("name") == "description" or str(a.get("property", "")).startswith("og:")) \
                    and a.get("property") not in ("og:url", "og:image") and HANGUL.search(a.get("content") or ""):
                self.hangul.append(f"<meta {a.get('name') or a.get('property')}> {squash_ws(a.get('content'))[:30]}")
        if tag == "title":
            self._in_title = True
        elif tag == "meta" and (a.get("name") or a.get("property")):
            self.meta[a.get("name") or a.get("property")] = a.get("content") or ""
        elif tag == "link" and a.get("rel") == "canonical":
            self.canonical = a.get("href") or ""
        elif tag == "script" and a.get("type") == "application/ld+json":
            self._in_jsonld, self._buf = True, []
        elif tag in ("script", "style"):
            self._in_code = True
        elif tag == "time" and a.get("datetime"):
            self.datetimes.append(a["datetime"])
        elif tag == "h1":
            self._in_h1 = True
        elif tag == "dt":
            self._dt = []
        elif tag == "dd":
            self._dd, self._dd_raw, self._dd_hrefs, self._dd_form = [], [], [], bool(a.get("data-form"))
            self._dd_keys = (a.get("data-key") or "").split()
            self._dd_in_facts = any(b == "facts" for _, b in self._stack)
        if tag == "a" and a.get("href"):
            self.hrefs.append(a["href"])
            for r in self._rows_open:
                r["hrefs"].append(a["href"])
            if self._dd is not None:
                self._dd_hrefs.append(a["href"])
            for _, b in self._stack:
                if b:
                    self.block_hrefs.setdefault(b, []).append(a["href"])
            if a.get("data-track"):
                self.tracked.append({"track": a["data-track"], "href": a["href"], "hreflang": a.get("hreflang") or "",
                                     "provider": a.get("data-provider") or "",
                                     "blocks": [b for _, b in self._stack if b]})
        if self._dd is not None and tag != "dd" and a.get("data-form"):
            self._dd_form = True
        if tag == "br":
            self.handle_data("\n")
        if tag in VOID:
            return
        in_facts = any(b == "facts" for _, b in self._stack)
        self._stack.append((tag, a.get("data-block")))
        self._lstack.append((tag, a.get("lang")))
        if self._note_depth is None and "ch-notes" in (a.get("class") or "").split():
            self._note_depth = len(self._stack)
        need_cls = next((c for c in (a.get("class") or "").split() if c in ("kf-need", "need")), "")
        if self._need_depth is None and need_cls:
            self._need_depth = len(self._stack)
            self.needs.append((need_cls, ""))
        if a.get("data-block"):
            self.blocks.setdefault(a["data-block"], "")
            if a["data-block"] == "access" and in_facts:
                self.access_in_facts = True
        row_kind = next((k for k in ("lot", "stop", "bus", "leg") if a.get(f"data-{k}")), None)
        if row_kind:
            # a course page's '차 없이 다니기' (data-block="move"): bus rows (data-bus, data-for = the place) and legs
            # (data-leg); its stop list's li data-stop are the stops' numbers, not bus stops (course_move_problems)
            self._rows_open.append({"kind": row_kind, "id": a.get(f"data-{row_kind}"), "parts": [], "hrefs": [],
                                    "in_facts": in_facts, "depth": len(self._stack), "for": a.get("data-for") or ""})

    def handle_endtag(self, tag):
        if tag == "title":
            self._in_title = False
        elif tag == "script" and self._in_jsonld:
            self.jsonld_raw.append("".join(self._buf))
            self._in_jsonld = False
        elif tag in ("script", "style"):
            self._in_code = False
        elif tag == "h1":
            self._in_h1 = False
        elif tag == "dt" and self._dt is not None:
            self._last_dt, self._dt = squash_ws(" ".join(self._dt)), None
        elif tag == "dd" and self._dd is not None:
            text = squash_ws(" ".join(self._dd))
            self.pairs.append((self._last_dt, text))
            if self._dd_in_facts:
                self.fact_rows.append({"keys": self._dd_keys, "dt": self._last_dt, "text": text,
                                       "exact": squash_ws("".join(self._dd_raw)), "hrefs": self._dd_hrefs,
                                       "form": self._dd_form})
            self._dd = None
        for i in range(len(self._stack) - 1, -1, -1):
            if self._stack[i][0] == tag:
                del self._stack[i:]
                break
        if self._note_depth is not None and len(self._stack) < self._note_depth:
            self._note_depth = None
        if self._need_depth is not None and len(self._stack) < self._need_depth:
            self._need_depth = None
        for i in range(len(self._lstack) - 1, -1, -1):
            if self._lstack[i][0] == tag:
                del self._lstack[i:]
                break
        while self._rows_open and self._rows_open[-1]["depth"] > len(self._stack):
            r = self._rows_open.pop()
            self.access_rows.append({"kind": r["kind"], "id": r["id"], "text": squash_ws("".join(r["parts"])),
                                     "hrefs": r["hrefs"], "in_facts": r["in_facts"], "for": r["for"]})

    def handle_data(self, data):
        if self._in_jsonld:
            self._buf.append(data)
            return
        if not self._in_code and HANGUL.search(data) and not self._lang().startswith("ko"):
            self.hangul.append(squash_ws(data)[:30])
        if not self._in_code and self._lang() == self.html_lang:
            self.foreign.append(data)
        if self._need_depth is not None:
            cls, text = self.needs[-1]
            self.needs[-1] = (cls, text + data)
        if self._note_depth is not None:
            self.notes.append(data)
        if self._in_title:
            self.title += data
        if self._in_h1:
            self.h1 += data
        for _, b in self._stack:
            if b:
                self.blocks[b] += data
        self.text.append(data)
        if not self._in_code and not self._in_title:
            self.body_text.append(data)
            for r in self._rows_open:
                r["parts"].append(data)
            for buf in (self._dt, self._dd):
                if buf is not None:
                    buf.append(data)
            if self._dd is not None:
                self._dd_raw.append(data)

    @property
    def plain(self) -> str:
        return squash_ws(" ".join(self.text))

    @property
    def body(self) -> str:
        """Text a reader sees in the page body (no <title>, <script> or <style>)."""
        return squash_ws(" ".join(self.body_text))

    @property
    def visible(self) -> str:
        """Body text plus <title> — what structured data may repeat."""
        return squash_ws(self.title + " " + " ".join(self.body_text))


def scan_file(path: Path) -> PageScan:
    p = PageScan()
    p.feed(path.read_text("utf-8"))
    return p


def _file_for(out: Path, href_path: str) -> Path:
    p = unquote(href_path)
    if p.endswith("/"):
        return out / p.strip("/") / "index.html"
    if "." in p.rsplit("/", 1)[-1]:
        return out / p.lstrip("/")
    return out / p.strip("/") / "index.html"


def _graph_nodes(raw_blocks: list[str]) -> tuple[list[dict], list[str]]:
    nodes, errs = [], []
    for raw in raw_blocks:
        try:
            data = json.loads(raw)
        except json.JSONDecodeError as ex:
            errs.append(f"JSON-LD 파싱 실패: {ex}")
            continue
        nodes += data.get("@graph", [data]) if isinstance(data, dict) else []
    return nodes, errs


def _strings(value, key: str = "", parent: dict | None = None):
    """(key, value, parent node) for every string or boolean in a JSON-LD node, recursively. @-keys are skipped,
    and so are link/code keys when they hold plain strings; a node under such a key (an ImageObject under
    `image`, a Place under an itinerary `item`) is still walked, so its credit text or name is checked."""
    if isinstance(value, dict):
        for k, v in value.items():
            if k.startswith("@"):
                continue
            if k in VISIBILITY_SKIP and k not in ("opens", "closes") and (
                    isinstance(v, str) or (isinstance(v, list) and all(isinstance(x, str) for x in v))):
                continue
            yield from _strings(v, k, value)
    elif isinstance(value, list):
        for v in value:
            yield from _strings(v, key, parent)
    elif isinstance(value, (str, bool)):
        yield key, value, parent or {}


def fact_texts(page: PageScan, key: str) -> list[dict]:
    """The facts-block row(s) for one fact key: the <dd data-key> holding the key, else the <dd> under the
    key's label. Nothing outside the facts block counts."""
    rows = [r for r in page.fact_rows if key in r["keys"]]
    if rows:
        return rows
    label = FACT_LABELS.get(key, key)
    return [r for r in page.fact_rows if r["dt"] == label]


def _verbatim(needle: str, text: str) -> bool:
    """needle occurs in text and does not start inside a word ('가능' is not shown by '불가능')."""
    i = text.find(needle)
    while i >= 0:
        if i == 0 or not text[i - 1].isalnum():
            return True
        i = text.find(needle, i + 1)
    return False


def fact_shown(page: PageScan, key: str, raw) -> bool:
    """True when one row of this key shows the whole value as displayed (textutil.display_value):
    - every token in order — words and symbols; only whitespace and layout punctuation (textutil.LAYOUT) may
      differ (textutil.value_shown);
    - and the whole display text verbatim in the row's visible text — unless the row prints the value as a
      table (an element with data-form inside the row) and the value does parse into one (present.value_view):
      table cells replace the layout punctuation, so only the token rule applies there;
    - and for a homepage or booking URL (shown as its domain) a link to the full URL in that row.
    This replaced the round-2 probe "first 20 characters of the raw value anywhere in the block"; on every
    value it is at least as strict, except that a row marked as a table (data-form) of a value that parses
    into one may drop / , : ( ) [ ] ※ and list dashes — the words, numbers and other symbols stay checked."""
    shown = display_value(key, raw)
    if not value_tokens(shown) and not squash_ws(shown):
        return True
    view = present.value_view(key, raw)
    parses = bool(view["tt"] or view["fees"] or view["grid"])
    url = link_url(raw) if key in URL_KEYS else ""
    for r in fact_texts(page, key):
        if not (value_shown(shown, r["text"]) or value_shown(shown, r["exact"])):
            continue
        if not (parses and r["form"]) and not _verbatim(squash_ws(shown), r["exact"]):
            continue
        if url and url not in (link_url(h) for h in r["hrefs"]):
            continue
        return True
    return False


def _shown(page: PageScan, labels) -> list[str]:
    """The value part of every <dt>label</dt><dd>value — provider…</dd> row with one of these labels."""
    labels = (labels,) if isinstance(labels, str) else tuple(labels)
    return [re.split(r"\s—\s", dd, maxsplit=1)[0] for dt, dd in page.pairs if dt in labels]


def _bool_problem(key: str, value: bool, parent: dict, page: PageScan) -> str:
    """A typed true/false must restate a row the page shows: the fee row reads exactly 무료, or the 주차 /
    유모차 대여 / 반려동물 동반 row holds a Y/N value that maps to the same boolean."""
    if key == "isAccessibleForFree":
        if value and "무료" not in _shown(page, FEE_LABELS):
            return "isAccessibleForFree인데 화면 요금 칸 값이 '무료'가 아님"
        return ""
    if key == "petsAllowed":
        label = FACT_LABELS["pet"]
    elif key == "value" and "LocationFeatureSpecification" in node_types(parent):
        label = squash_ws(parent.get("name"))
    else:
        return f"{key or '값'}={value}: 화면 값과 맞춰 볼 수 없는 참/거짓 값"
    fact_key = AMENITY_LABELS.get(label)
    if not fact_key or not any(amenity_value(fact_key, v) is value for v in _shown(page, label)):
        return f"화면의 '{label}' 칸 값과 다른 참/거짓 — {key}={value}"
    return ""


def jsonld_visibility(nodes: list[dict], page: PageScan) -> list[str]:
    """Structured data must say only what the page shows (Google/Bing/Naver; AI fetchers read visible HTML).
    Each string's first 25 characters (whitespace squashed) must be in the visible text or <title>; an event's
    dates may instead be a <time datetime>; page dates (dateModified, datePublished, lastReviewed) are ISO dates
    that are not shown (operator decision 2026-10-09: check dates stay machine-readable only); telephone numbers
    are compared in their domestic form; opening hours must show their times; booleans must restate a visible row
    (_bool_problem)."""
    visible = page.visible
    # Japanese and Chinese write no spaces between sentences, the page text joins elements with one ('。 土'):
    # those pages are also compared without whitespace
    cjk = (page.html_lang or "").lower().startswith(("ja", "zh"))
    visible_ns = re.sub(r"\s", "", visible) if cjk else ""
    problems = []
    for node in nodes:
        for key, value, parent in _strings(node):
            if isinstance(value, bool):
                problem = _bool_problem(key, value, parent, page)
                if problem:
                    problems.append(problem)
                continue
            text = squash_ws(value)
            if not text:
                continue
            if key in PAGE_DATE_KEYS:
                if not ISO_DATE.match(text):
                    problems.append(f"ISO 날짜(YYYY-MM-DD)가 아님 — {key} {text}")
                continue
            if key in EVENT_DATE_KEYS:
                if text not in visible and text not in page.datetimes:
                    problems.append(f"화면(본문·<time datetime>)에 없는 날짜 — {key} {text}")
                continue
            if key in ("opens", "closes"):   # '09:00' may be shown as '9:00'
                if text not in visible and re.sub(r"^0(?=\d:)", "", text) not in visible:
                    problems.append(f"화면에 없는 시각 — {key} {text}")
                continue
            if key == "telephone":
                text = phone_domestic(text)
            if cjk:   # every sentence on screen (the first one is often under 25 characters, the facts follow it)
                gone = [x for x in re.split(r"(?<=[。！？])", re.sub(r"\s", "", text)) if x and x[:25] not in visible_ns]
                if gone:
                    problems.append(f"화면에 없는 값 — {key or '값'} '{gone[0][:25]}'")
                continue
            if text[:25] not in visible:
                problems.append(f"화면에 없는 값 — {key or '값'} '{text[:25]}'")
    return problems


def designation_page_problems(e: dict, page: PageScan) -> list[str]:
    """Official designations (schema.designations) on a place page. Never relaxed:
    - every stored designation may be shown: a label, the list's link and 확인일 (data), and a list row matched to
      the place with high/medium confidence that is not flagged needs_check (schema.designation_problems) — else an
      error;
    - each one shown is in the facts card's '지정' row (<dd data-key="designations">) with its label and its list's
      name linking to the list — and not its 확인일 (operator decision 2026-10-09) — and its chip under the answer
      (data-block="designations") links to the same list;
    - the page shows no designation chip or row the data does not hold."""
    out = []
    for d in e.get("designations") or []:
        for problem in designation_problems(d):
            out.append(f"지정 '{squash_ws(d.get('label')) or d.get('type')}' 표시 불가: {problem}")
    shown = designations(e)
    rows = [r for r in page.fact_rows if "designations" in r["keys"]]
    chips_text = squash_ws(page.blocks.get("designations", ""))
    chips_hrefs = page.block_hrefs.get("designations", [])
    for d in shown:
        line = f"{d['label']} {squash_ws(d['source_name'])}"   # label and its list (linked)
        if not any(line in r["text"] and d["url"] in r["hrefs"] for r in rows):
            out.append(f"지정 '{d['label']}'이 방문 전 확인의 '지정' 줄에 목록 이름·링크와 함께 없음")
        if any(d["checked_at"] in r["text"] for r in rows):
            out.append(f"지정 '{d['label']}'의 확인일({d['checked_at']})이 '지정' 줄에 보임 — 확인일은 데이터·구조화 데이터에만")
        if d["label"] not in chips_text or d["url"] not in chips_hrefs:
            out.append(f"지정 '{d['label']}'이 첫 화면 지정 칩에 목록 링크와 함께 없음")
    if not shown and (rows or "designations" in page.blocks):
        out.append("지정 데이터가 없는데 '지정' 줄이나 칩이 있음")
    return out


def seat_only_parking_problems(e: dict, page: PageScan) -> list[str]:
    """A city source's '주차 및 좌석수' (facts.parking_seats) with a seat count only ('30석') is not a parking value
    (schema.parking_seats_part). Never relaxed:
    - no row labelled 주차 or 주차·좌석 (first-screen tile, facts card) shows a seat count alone;
    - a place whose parking_seats holds seats only, with no parking or parking-fee value from any source, names 주차
      in the first screen's '확인 필요' line and in the facts card's '확인 필요' line."""
    out = []
    labels = (FACT_LABELS["parking"], FACT_LABELS["parking_seats"])
    for dt, dd in page.pairs:
        if dt in labels and any(parking_seats_part(part) == "seats" for part in re.split(r"\s—\s", dd)):
            out.append(f"좌석 수만 있는 값이 '{dt}' 칸에 보임: {dd[:30]}")
    facts, alts = e.get("facts") or {}, e.get("fact_alternatives") or {}
    if parking_seats_half(e) == "seats" and not any(facts.get(k) or alts.get(k) for k in ("parking", "parkingfee")):
        for cls, where in (("kf-need", "첫 화면"), ("need", "방문 전 확인")):
            lines = [squash_ws(t) for c, t in page.needs if c == cls]
            if not any(FACT_LABELS["parking"] in line for line in lines):
                out.append(f"좌석 수만 있고 주차 값이 없는데 {where}의 '확인 필요'에 주차가 없음")
    return out


def designation_awards(e: dict, node: dict, page: PageScan) -> list[str]:
    """JSON-LD `award` on a place node: each value is the label of a designation the page shows (schema.designations),
    whole in the visible body."""
    award = node.get("award") or []
    labels = {d["label"] for d in designations(e)}
    out = []
    for a in [award] if isinstance(award, str) else award:
        if squash_ws(a) not in labels:
            out.append(f"구조화 데이터 award가 표시할 수 있는 지정이 아님: {a}")
        elif squash_ws(a) not in page.body:
            out.append(f"구조화 데이터 award가 화면에 없음: {a}")
    return out


def designation_list_problems(S, kind: str, page: PageScan) -> list[str]:
    """A list page shows each record's first designation as a chip; the lists behind those chips are linked once,
    by name and without their 확인일, in the page's source line (data-block="designation-sources")."""
    shown = [designations(e)[0] for e in S.lists[kind] if designations(e)]
    text = squash_ws(page.blocks.get("designation-sources", ""))
    hrefs = page.block_hrefs.get("designation-sources", [])
    out = []
    for d in {(d["url"], d["checked_at"], d["source_name"]): d for d in shown}.values():
        if d["url"] not in hrefs or squash_ws(d["source_name"]) not in text:
            out.append(f"지정 칩 '{d['short']}'의 목록({d['source_name']}) 이름·링크가 지정 출처 줄에 없음")
        if d["checked_at"] in text:
            out.append(f"지정 출처 줄에 확인일({d['checked_at']})이 보임 — 확인일은 데이터·구조화 데이터에만")
    if not shown and "designation-sources" in page.blocks:
        out.append("지정 칩이 없는데 지정 출처 줄이 있음")
    return out


NUM = re.compile(r"\d[\d,]*\d|\d")


def _nums(*values) -> set[str]:
    return {n for v in values if v is not None for n in NUM.findall(str(v))}


def nearby_data_problems(S) -> list[str]:
    """nearby.json against parking_lots.json: every lot it names exists and may be used for nearby lists, and every
    distance is within the stated radius and count (the file's _meta)."""
    meta = S.nearby_meta or {}
    pr, br = meta.get("parking") or {}, meta.get("bus") or {}
    out = []
    for pid, entry in S.nearby.items():
        lots, stops = entry.get("parking") or [], entry.get("bus") or []
        for x in lots:
            lot = S.parking_lots.get(x.get("lot_id"))
            if lot is None:
                out.append(f"nearby.json {pid}: parking_lots.json에 없는 주차장 {x.get('lot_id')}")
            elif lot.get("nearby") is False:
                out.append(f"nearby.json {pid}: 근처 목록에서 뺀 주차장 {x.get('lot_id')} ({lot.get('nearby_excluded')})")
            if not isinstance(x.get("meters"), int) or x["meters"] > (pr.get("radius_m") or 500):
                out.append(f"nearby.json {pid}: 주차장 거리 {x.get('meters')}m가 반경 밖이거나 정수가 아님")
        for s in stops:
            if not isinstance(s.get("meters"), int) or s["meters"] > (br.get("radius_m") or 500):
                out.append(f"nearby.json {pid}: 정류장 거리 {s.get('meters')}m가 반경 밖이거나 정수가 아님")
        if len(lots) > (pr.get("max") or 3) or len(stops) > (br.get("max") or 2):
            out.append(f"nearby.json {pid}: 주차장·정류장 수가 _meta의 max를 넘음")
        if [x.get("meters") for x in lots] != sorted(x.get("meters") or 0 for x in lots):
            out.append(f"nearby.json {pid}: 주차장이 가까운 순이 아님")
    return out


def _tt_segments(text: str) -> dict[str, str]:
    """The timetable guide's number record ('… — 01 ○○ 평일 17(06:29~22:14)·주말 9, …; 08 △△ …') by route."""
    out = {}
    for part in re.split(r";\s*|\s—\s", text or ""):
        m = re.match(r"\s*(\d{2}) ", part)
        if m:
            out[m.group(1)] = part
    return out


def transit_problems(S) -> list[str]:
    """transit.json (the course pages' timetable rows, QA 2026-10-15 F09 / operator decision 4) against the reviewed
    timetable guide (site.json city.course_move.timetable_guide, '시내버스로 관광지 가기'), so the two copies cannot drift: in the guide's timetable number record
    (_number_sources, the line of route counts) each route's part names every reference stop with its weekday range and
    count and its Sat/Sun/holiday range; another source's value ('<route> <stop> 매시 40분') and the timetable's own wording of
    it (매시 35분) are in the guide's text; the source is the guide's timetable file."""
    tr = getattr(S, "transit", None) or {}
    routes = tr.get("routes") or []
    if not routes:
        return []
    gid = present.move_config()["timetable_guide"]
    g = next((x for x in S.guides_all if gid and x.get("id") == gid), None)
    if not g:
        return [f"transit.json: 대조할 시간표 가이드 {gid or '(site.json city.course_move.timetable_guide 없음)'}이 없음"]
    meta = tr.get("_meta") or {}
    out = []
    if meta.get("url") not in [s.get("url") for s in g.get("sources") or []]:
        out.append(f"transit.json: 출처 {meta.get('url')}가 {gid} 출처에 없음")
    record = next((x for x in g.get("_number_sources") or [] if "기준 정류장 횟수" in x), "")
    segs = _tt_segments(record)
    body = " ".join(str(b.get("text") or "") for b in g.get("body") or [])
    for r in routes:
        seg = segs.get(r["no"], "")
        if not seg:
            out.append(f"transit.json {r['no']}번: {gid} 시간표 기록에 이 노선이 없음")
            continue
        for t in r.get("times") or []:
            where = f"transit.json {r['no']}번 {t['stop']}"
            if t["stop"] not in seg:
                out.append(f"{where}: {gid} 시간표 기록의 이 노선에 정류장 이름이 없음")
            if f"{t['weekday_n']}({t['weekday']})" not in seg and not (t["weekday"] in seg and str(t["weekday_n"]) in seg):
                out.append(f"{where}: 평일 {t['weekday']}({t['weekday_n']}회)가 {gid} 시간표 기록과 다름")
            if t["weekend"] not in seg and t["weekend"] != t["weekday"]:
                out.append(f"{where}: 토·일·공휴일 {t['weekend']}가 {gid} 시간표 기록에 없음")
            if t["weekend_n"] != t["weekday_n"] and f"주말 {t['weekend_n']}" not in seg:
                out.append(f"{where}: 토·일·공휴일 {t['weekend_n']}회가 {gid} 시간표 기록에 없음")
            if t.get("pattern") and t["pattern"] not in body:
                out.append(f"{where}: 출발 시각 '{t['pattern']}'가 {gid} 본문에 없음")
            alt = t.get("alt") or {}
            for v in (alt.get("value"), t.get("every") if alt else None):
                if v and v not in body:
                    out.append(f"{where}: '{v}'가 {gid} 본문에 없음")
    return out


def course_move_problems(S, c: dict, page: "PageScan") -> list[str]:
    """A Korean course page's '차 없이 다니기' block (present.course_move) against the data: its bus rows are exactly
    nearby.json's stops of each place, in order (name, metres, every route number); every 대중교통 길찾기 link joins
    the two stops' stored coordinates (never a place ID) for a leg the course measures; the block says once what no
    source gives ('확인 필요: 구간별 이동 시간'); no walking time or minutes of our own."""
    out = []
    cv = S.course_vms[c["slug"]]
    if "move" not in page.blocks:
        return ["코스 페이지에 '차 없이 다니기' 블록 없음"]
    text = squash_ws(page.blocks["move"])
    rows = [r for r in page.access_rows if r["kind"] == "bus"]
    want = []
    for s in cv["stops"]:
        t = s["t"]
        if t and t.get("_geo") and t["id"] not in [w[0] for w in want]:
            for b in (S.nearby.get(t["id"]) or {}).get("bus") or []:
                want.append((t["id"], squash_ws(b["stop_name"]), b))
    got = [(r.get("for"), r["id"]) for r in rows]
    by_place = lambda xs: {k: [n for p, n in xs if p == k] for k, _ in xs}   # each place's stops, in order
    if by_place(got) != by_place([(p, n) for p, n, _ in want]):
        out.append(f"차 없이 다니기 정류장 줄이 nearby.json과 다름: {got}")
    stored = {(p, n): b for p, n, b in want}
    for r in rows:
        b = stored.get((r.get("for"), r["id"]))
        miss = [x for x in [f"{b['meters']}m"] + list(b.get("routes") or []) if x not in r["text"]] if b else []
        if miss:
            out.append(f"차 없이 다니기 정류장 {r['id']}: {miss} 없음")
    legs = {(a["n"], b["n"]): (a, b) for a, b in cv.get("pairs") or [] if a.get("next_m") is not None and a["next_m"] >= 10}
    for r in (r for r in page.access_rows if r["kind"] == "leg"):
        try:
            key = tuple(int(x) for x in r["id"].split("-"))
        except ValueError:
            key = ()
        if key not in legs:
            out.append(f"차 없이 다니기 구간 {r['id']}: 코스가 재는 구간이 아님")
            continue
        a, b = legs[key]
        hrefs = [h for h in r["hrefs"] if "map.kakao.com/link/by/traffic/" in h]
        ok = [h for h in hrefs if re.search(rf",{re.escape(str(a['geo']['lat']))},{re.escape(str(a['geo']['lng']))}/", h)
              and h.endswith(f",{b['geo']['lat']},{b['geo']['lng']}")]
        if len(hrefs) != 1 or not ok:
            out.append(f"차 없이 다니기 구간 {r['id']}: 대중교통 길찾기 링크가 두 경유지 좌표와 다름 {hrefs}")
    if len([r for r in page.access_rows if r["kind"] == "leg"]) != len(legs):
        out.append(f"차 없이 다니기 구간 수가 코스의 잰 구간 수({len(legs)})와 다름")
    if "확인 필요: 구간별 이동 시간" not in text:
        out.append("차 없이 다니기에 '확인 필요: 구간별 이동 시간' 없음")
    if re.search(r"\d+\s*분\s*(?:걸|소요)|도보\s*\d|걸어서\s*\d", text):
        out.append("차 없이 다니기에 우리가 쓴 이동 시간이 있음")
    return out


NEARBY_EARTH_R = 6371008.8  # nearby.json _meta.parking.method (haversine, whole metres)


def nearby_stale_problems(S) -> list[str]:
    """Warnings for a nearby.json that no longer fits the places (it is made outside the build from the verified gap
    data): a parking distance that the place's current coordinates and the lot's coordinates no longer give (e.g.
    after tools/tourapi_bulk.py moved a place), and a published place with coordinates that has no nearby.json entry
    (e.g. a newly approved place) — both mean nearby.json needs to be made again."""
    if not S.nearby:
        return []
    out = []
    for e in S.entities:
        geo = e.get("_geo")
        if not geo or e.get("status") != "published":
            continue
        entry = S.nearby.get(e["id"])
        if entry is None:
            out.append(f"nearby.json {e['id']} {e['name']}: 좌표가 있는 공개 장소인데 항목이 없음 — 근처 주차·버스 블록이 안 나감")
            continue
        for x in entry.get("parking") or []:
            lot = S.parking_lots.get(x.get("lot_id")) or {}
            if lot.get("lat") is None or lot.get("lng") is None or not isinstance(x.get("meters"), int):
                continue
            p1, p2 = math.radians(float(geo["lat"])), math.radians(float(lot["lat"]))
            dp, dl = p2 - p1, math.radians(float(lot["lng"]) - float(geo["lng"]))
            h = math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
            m = round(2 * NEARBY_EARTH_R * math.asin(math.sqrt(h)))
            if abs(m - x["meters"]) > 1:
                out.append(f"nearby.json {e['id']} {e['name']}: {x['lot_id']} 거리 {x['meters']}m가 지금 좌표로는 {m}m "
                           "— nearby.json을 다시 만들어야 함")
    return out


def relation_page_problems(S, e: dict, page: PageScan, node: dict | None, ref) -> list[str]:
    """pipeline/relations.py on one built place page (Korean or a version; module docstring). ref(x) -> (path, url) of
    place x's page in this version, or None when it has none there. node: the page's own JSON-LD place node."""
    out = []
    links = lambda blk: set(page.block_hrefs.get(blk, []))  # noqa: E731
    parent = e.get("_parent") if e.get("_rel") == "inside" else None
    if parent is not None:
        pr = ref(parent)
        if "rel-inside" not in page.blocks:
            out.append(f"속한 곳 줄이 없음({parent['name']})")
        elif pr and pr[0] not in links("rel-inside"):
            out.append(f"속한 곳 줄에 {parent['name']} 링크가 없음")
    elif "rel-inside" in page.blocks:
        out.append("속한 곳 관계가 없는데 속한 곳 줄이 있음")
    same = e.get("_same") or []
    if same and "rel-same_building" not in page.blocks:
        out.append("같은 건물 줄이 없음(" + ", ".join(x["name"] for x in same) + ")")
    for x in same:
        r = ref(x)
        if r and "rel-same_building" in page.blocks and r[0] not in links("rel-same_building"):
            out.append(f"같은 건물 줄에 {x['name']} 링크가 없음")
    if not same and "rel-same_building" in page.blocks:
        out.append("같은 건물 관계가 없는데 같은 건물 줄이 있음")
    parts = [(c, ref(c)) for c in e.get("_parts") or []]
    want = {r[0] for _, r in parts if r}
    got = links("parts")
    for c, r in parts:
        if r and r[0] not in got:
            out.append(f"안에 있는 곳 목록에 {c['name']} 링크가 없음")
    if got - want:
        out.append(f"안에 있는 곳 목록에 이 장소의 부분이 아닌 링크: {sorted(got - want)[:3]}")
    by_id = {x["id"]: x for x in S.entities}
    fam = {r[0] for r in (ref(by_id[i]) for i in relations.family(e) if i in by_id) if r}
    own = ref(e)
    if own:
        fam.add(own[0])
    aliases = [(r, ref(x["_alias_of"])) for x in S.entities if x.get("_alias_of") is not None and (r := ref(x))]
    for blk, label in (("near-rows", "주변 장소"), ("similar", "이름이 비슷한 곳")):
        hs = links(blk)
        if hs & fam:
            out.append(f"{label} 줄에 이 장소의 가족(속한 곳·안에 있는 곳·같은 건물)이 있음: {sorted(hs & fam)[:3]}")
        for a, pa in aliases:
            if pa and a[0] in hs and pa[0] in hs:
                out.append(f"{label} 줄에 같은 건물의 두 페이지가 함께 있음: {a[0]} · {pa[0]}")
    if node is not None:
        as_list = lambda v: v if isinstance(v, list) else ([v] if v else [])  # noqa: E731
        ids = lambda v: {str(x.get("@id", "")) for x in as_list(v) if isinstance(x, dict)}  # noqa: E731
        pr = ref(parent) if parent is not None else None
        inside = {i for i in ids(node.get("containedInPlace")) if i.endswith("#place")}
        if inside != ({pr[1] + "#place"} if pr else set()):
            out.append(f"구조화 데이터 containedInPlace가 관계 데이터와 다름: {sorted(inside)}")
        contains = ids(node.get("containsPlace"))
        if contains != {r[1] + "#place" for _, r in parts if r}:
            out.append(f"구조화 데이터 containsPlace가 관계 데이터와 다름: {sorted(contains)[:3]}")
    return out
def geo_problems(S) -> tuple[list[str], list[str]]:
    """(errors, warnings) for the published places' points (geo). Errors: lat/lng not numbers, outside the region's
    box (site.json city.geo_bounds, when the city has one), an official map's default point (city.geo_default_points —
    what its pages show for a record without coordinates), no source, and a source other
    than TourAPI without the page it was read from (url) or the day (checked_at). Warning: three or more places at one
    point with different addresses (textutil.address_key) — a list page's point copied to several places."""
    errors, warns = [], []
    box = city.current().geo_bounds
    at: dict[tuple, list] = {}
    for e in S.entities:
        geo = e.get("geo") or {}
        if e.get("status") != "published" or (geo.get("lat") is None and geo.get("lng") is None):
            continue
        where = f"{e['id']} {e['name']}"
        try:
            lat, lng = float(geo["lat"]), float(geo["lng"])
        except (KeyError, TypeError, ValueError):
            errors.append(f"{where}: 좌표가 숫자가 아님 (lat {geo.get('lat')!r}, lng {geo.get('lng')!r})")
            continue
        if box and not (box[0] <= lat <= box[1] and box[2] <= lng <= box[3]):
            errors.append(f"{where}: 좌표 ({lat}, {lng})가 {S.site.get('region')} 범위 {box} 밖")
        if is_default_point(lat, lng):
            errors.append(f"{where}: 좌표 ({lat}, {lng})가 공식 지도의 기본점(city.geo_default_points) — 장소 위치가 아님")
        src = squash_ws(geo.get("source"))
        if not src:
            errors.append(f"{where}: 좌표 출처(geo.source) 없음")
        elif src != "TourAPI":
            if not re.match(r"https?://\S+$", str(geo.get("url") or "")):
                errors.append(f"{where}: {src} 좌표에 읽은 페이지 주소(geo.url) 없음")
            if not ISO_DATE.match(str(geo.get("checked_at") or "")):
                errors.append(f"{where}: {src} 좌표에 확인일(geo.checked_at, YYYY-MM-DD) 없음")
        at.setdefault((round(lat, 6), round(lng, 6)), []).append(
            (e, address_key((e.get("facts") or {}).get("address"))))
    for (lat, lng), xs in at.items():
        if len(xs) >= 3 and len({k for _, k in xs}) > 1:
            warns.append(f"좌표 ({lat}, {lng})에 주소가 다른 장소 {len(xs)}곳: "
                         + ", ".join(f"{e['name']}" for e, _ in xs) + " — 목록 지점을 여러 곳에 붙였는지 확인")
    return errors, warns


def nearby_provenance_problems(S) -> tuple[list[str], list[str]]:
    """Whose coordinates a nearby list was measured between (CLAUDE.md 3.2): nearby_source.providers, written by
    tools/tourapi_bulk.compute_nearby, is exactly the providers of the place's point and every listed place's
    (schema.nearby_geo_providers) and its provider line names them (errors). A list written before providers were
    recorded (no 'providers') is checked by its line only, as one warning listing the places — recomputing the lists
    (tools/official_coords.py --apply or tools/tourapi_bulk.py) writes both."""
    errors, stale = [], []
    by_slug = S.ent_all_by_slug
    for e in S.entities:
        src = e.get("nearby_source") or {}
        if e.get("status") != "published" or not src or not e.get("_geo"):
            continue
        want = nearby_geo_providers(e, by_slug)
        if "providers" in src:
            if list(src.get("providers") or []) != want:
                errors.append(f"{e['id']} {e['name']}: nearby_source.providers {src.get('providers')} ≠ 좌표 출처 {want} "
                              "— 주변 목록을 다시 계산해야 함")
            elif squash_ws(src.get("provider")) != nearby_provider(want):
                errors.append(f"{e['id']} {e['name']}: nearby_source.provider '{src.get('provider')}'가 좌표 출처 "
                              f"'{nearby_provider(want)}'와 다름")
        elif any(p not in squash_ws(src.get("provider")) for p in want):
            stale.append(e["name"])
    warns = [f"nearby_source에 좌표 출처 목록(providers)이 없고 출처 줄이 좌표 출처를 다 적지 않은 장소 {len(stale)}곳: "
             f"{', '.join(stale)} — tools/official_coords.py --apply(또는 tools/tourapi_bulk.py)로 주변 목록을 다시 "
             "계산해야 함"] if stale else []
    return errors, warns


def place_geo_page_problems(e: dict, page: PageScan) -> list[str]:
    """The Korean place page names whose point it maps: the map caption '위치: <provider>' (CLAUDE.md 3.2)."""
    want = geo_provider(e.get("_geo")) if e.get("_geo") else ""
    if want and f"위치: {want}" not in squash_ws(page.visible):
        return [f"지도 캡션에 좌표 출처 '위치: {want}'가 없음"]
    return []


def access_problems(S, e: dict, page: PageScan) -> list[str]:
    """The place page's '근처 주차·버스' block (p1.access) against parking_lots.json / nearby.json:
    - the rows are exactly the file's lots and stops for this place, in order, and nothing when there are none;
    - a lot row shows its name, 노외/노상, address, metres, 면수 and 무료/유료 from the files; a paid lot every fee amount
      of every version with its source, '방문 전 전화 확인' when the sources differ, and the other source's 면수;
      a stop row its name, metres and each route number stored for it;
    - every number in a row is one of those stored values (or a fee rule's own 1시간·30분·5시간·1일) — nothing invented;
    - the block is never inside data-block="facts": nearby lots are not the place's parking and never count toward
      the index criteria (schema.index_groups reads facts only)."""
    out = []
    entry = S.nearby.get(e["id"]) if e.get("_geo") else None
    want_lots = [x for x in (entry or {}).get("parking") or [] if x.get("lot_id") in S.parking_lots]
    want_stops = (entry or {}).get("bus") or []
    lots = [r for r in page.access_rows if r["kind"] == "lot"]
    stops = [r for r in page.access_rows if r["kind"] == "stop"]
    if page.access_in_facts or any(r["in_facts"] for r in page.access_rows):
        out.append("근처 주차·버스가 방문 전 확인(facts) 안에 있음 — 장소의 주차 정보로 읽힘")
    if not (want_lots or want_stops):
        if "access" in page.blocks or page.access_rows:
            out.append("nearby.json에 값이 없는데 근처 주차·버스 블록이 있음")
        return out
    if "access" not in page.blocks:
        out.append("nearby.json에 값이 있는데 근처 주차·버스 블록이 없음")
        return out
    if [r["id"] for r in lots] != [x["lot_id"] for x in want_lots]:
        out.append(f"근처 공영주차장 줄이 nearby.json과 다름: {[r['id'] for r in lots]}")
    if [r["id"] for r in stops] != [squash_ws(s["stop_name"]) for s in want_stops]:
        out.append(f"가까운 버스 정류장 줄이 nearby.json과 다름: {[r['id'] for r in stops]}")
    for r, x in zip(lots, want_lots):
        lot = S.parking_lots[x["lot_id"]]
        t = r["text"]
        alt = lot.get("alt") or {}
        alt_spaces = (alt.get("spaces") or {}).get("value")
        fee = lot.get("fee") or {}
        need = [f"{x['meters']}m", f"{lot['spaces']}면", lot.get("paid") or "", lot.get("type") or ""]
        if alt_spaces is not None:
            need.append(f"{alt_spaces}대")
        amounts = set()
        for v in fee.get("versions") or []:
            for size in ("small", "large"):
                for n in (v.get(size) or {}).values():
                    if n is not None:
                        amounts.add(f"{int(n):,}원")
        need += sorted(amounts)
        if fee.get("differs") or (alt_spaces is not None and alt_spaces != lot.get("spaces")):
            need.append("방문 전 전화 확인")
        missing = [w for w in need if w and w not in t]
        for label, value in (("이름", present.tidy_brackets(lot["name"])),
                             ("주소", present.lot_address(lot.get("address") or lot.get("address_jibun"))),
                             ("다른 출처 이름", (alt.get("name") or {}).get("value"))):
            if value and not value_shown(value, t):
                missing.append(f"{label} {value}")
        if missing:
            out.append(f"근처 공영주차장 {lot['name']}: 파일 값이 줄에 없음 — {', '.join(missing)}")
        allowed = _nums(lot["name"], lot.get("address"), lot.get("address_jibun"), lot.get("spaces"), alt_spaces,
                        (alt.get("name") or {}).get("value"), x["meters"], *amounts, fee.get("contact"))
        if fee:
            allowed |= {"1", "30", "5"}  # fee rule wording: 1시간까지 · 1시간 30분까지 · 30분마다 · 5시간 넘으면 1일
        extra = sorted(_nums(t) - allowed)
        if extra:
            out.append(f"근처 공영주차장 {lot['name']}: 파일에 없는 숫자 {extra}")
    for r, s in zip(stops, want_stops):
        t = r["text"]
        need = [squash_ws(s["stop_name"]), f"{s['meters']}m", *(s.get("routes") or [])]
        missing = [w for w in need if w not in t]
        if missing:
            out.append(f"가까운 버스 정류장 {s['stop_name']}: 파일 값이 줄에 없음 — {', '.join(missing)}")
        extra = sorted(_nums(t) - _nums(s["stop_name"], s["meters"], *(s.get("routes") or [])))
        if extra:
            out.append(f"가까운 버스 정류장 {s['stop_name']}: 파일에 없는 숫자 {extra}")
    return out


def _url_gate(out: Path, html_files: list[Path], site_url: str) -> tuple[int, list[str]]:
    """Every public URL must be absolute on the https site_url (P1-12). Returns (count, first examples)."""
    prefix = site_url.rstrip("/") if site_url.startswith("https://") else ""

    def ok(u: str, image: bool = False) -> bool:
        return (bool(prefix) and (u == prefix or u.startswith(prefix + "/"))) or (image and u.startswith(TOURAPI_IMAGE_HOSTS))

    bad: list[str] = []
    for f in html_files:
        rel = "/" + str(f.relative_to(out)).replace("\\", "/")
        if rel == "/404.html":
            continue
        p = scan_file(f)
        checks = [("canonical", p.canonical, False), ("og:url", p.meta.get("og:url", ""), False)]
        if p.meta.get("og:image"):
            checks.append(("og:image", p.meta["og:image"], True))
        nodes, _ = _graph_nodes(p.jsonld_raw)
        stack: list = list(nodes)
        while stack:
            n = stack.pop()
            if isinstance(n, list):
                stack += n
                continue
            if not isinstance(n, dict):
                continue
            for k, v in n.items():
                if k == "@id" and isinstance(v, str):
                    checks.append(("JSON-LD @id", v, False))
                elif k == "url" and isinstance(v, str) and "Organization" not in node_types(n):
                    checks.append(("JSON-LD url", v, False))
                elif k == "item" and isinstance(v, str):   # BreadcrumbList items
                    checks.append(("JSON-LD item", v, False))
                elif isinstance(v, (dict, list)):
                    stack.append(v)
        bad += [f"{rel} {what}: {u or '(빈 값)'}" for what, u, image in checks if not ok(u, image)]
    for loc in sorted(_sitemap_locs(out)):
        if not ok(loc):
            bad.append(f"sitemap.xml <loc>: {loc}")
    robots = (out / "robots.txt").read_text("utf-8") if (out / "robots.txt").exists() else ""
    for line in robots.splitlines():
        if line.startswith("Sitemap:") and not ok(line.split(":", 1)[1].strip()):
            bad.append(f"robots.txt {line}")
    for name in ("llms.txt", "llms-full.txt"):
        text = (out / name).read_text("utf-8") if (out / name).exists() else ""
        for u in re.findall(r"\]\(([^)\s]+)\)", text) + re.findall(r"^URL: (\S+)", text, re.M):
            if not ok(u):
                bad.append(f"{name}: {u}")
    return len(bad), bad[:5]


def _sitemap_locs(out: Path) -> set[str]:
    try:
        return {el.text or "" for el in ET.parse(out / "sitemap.xml").getroot().iter(f"{SITEMAP_NS}loc")}
    except (OSError, ET.ParseError):
        return set()


def hreflang_problems(pages: dict[str, tuple[str, list[tuple[str, str]]]]) -> list[tuple[str, str]]:
    """(page, problem) for hreflang links that are not complete and reciprocal. pages: {rel path: (canonical,
    [(hreflang, href)])}. A page with links lists ko, x-default and at least one other version (en, ja, zh-Hans,
    zh-Hant, de, fr, es, ru), each once; x-default is the Korean URL; its own language's link is its canonical; every
    page it lists exists and lists exactly the same links."""
    known = {"ko", "x-default"} | {loc.html for loc in LC.LOCALES.values()}
    by_canon = {canon: (rel, alts) for rel, (canon, alts) in pages.items() if alts}
    out = []
    for rel, (canon, alts) in pages.items():
        if not alts:
            continue
        d = dict(alts)
        if len(d) != len(alts) or not {"ko", "x-default"} < set(d) or not set(d) <= known:
            out.append((rel, f"hreflang은 ko·x-default와 다른 언어 하나 이상이 한 번씩이어야 함: {sorted(h for h, _ in alts)}"))
            continue
        if d["x-default"] != d["ko"]:
            out.append((rel, "hreflang x-default가 한국어 주소가 아님"))
        code = LC.code_of_path(rel)
        own = "ko" if code == "ko" else LC.get(code).html
        if own not in d:
            out.append((rel, f"hreflang에 이 페이지 언어({own})가 없음"))
            continue
        if d[own] != canon:
            out.append((rel, f"hreflang {own}이 이 페이지(canonical)가 아님: {d[own]}"))
        for h, href in d.items():
            if h in (own, "x-default"):
                continue
            other = by_canon.get(href)
            if not other:
                out.append((rel, f"hreflang 짝 페이지가 없거나 짝 쪽에 hreflang이 없음: {href}"))
            elif dict(other[1]) != d:
                out.append((rel, f"hreflang이 서로 맞지 않음(짝 {other[0]})"))
    return out


LANG_KO = {"en": "영어", "ja": "일본어", "zh-hans": "중국어 간체", "zh-hant": "중국어 번체", "de": "독일어", "fr": "프랑스어",
           "es": "스페인어", "ru": "러시아어"}


# a foreign version's call link: '+82' then a number without its trunk 0 (hyphens allowed: '+82-2-1330'), or a number
# that has no international form (textutil.phone_e164: nationwide 1577-4050 -> tel:15774050; 119, 112, 1330; 080, 060)
TEL_ABROAD = re.compile(r"tel:(?:\+82-?[1-9][\d-]{3,14}|1\d{2,7}|0[68]0\d{7,8})")


def validate_intl(S, site, data_dir: Path, out: Path, strict: bool, E, W, sitemap: set, llms: dict, stats: dict,
                  pages: dict) -> None:
    """One version besides Korean (/en/, /ja/ …, pipeline/en_site.py). Added checks — the generic ones (JSON-LD
    visibility, internal links, the URL gate, noindex in preview/sample, hreflang reciprocity over every page) run over
    these files with every other page:
    - every page of the version: <html lang> of its locale (en, ja, zh-Hans, zh-Hant, de, fr, es, ru), no Korean
      script outside an element with lang="ko" (text, <title>, alt, aria-label, title, placeholder, meta description /
      og text)
    - hreflang present on both pages of every pair the version defines, each listing ko and the version
    - no stale record rendered: every record a page renders (data-entity-id / data-record) has the ko_hash of the
      current Korean data (pipeline/en_source.current_hashes, computed here independently of the build)
    - every current place page exists and shows the record's name as its H1, the Korean name, and each fact value of
      data/<region>/<code> whole in its own row of the facts block (dd data-key) — for two sources, both values, each
      source's name in this language and the record's note; 'also' values too
    - official designations: every one the Korean page shows (schema.designations) has its label and list name in
      this language (strings designation:/designation_source:) and is on the page as a chip linking to its list and
      in the facts card's 'Designations' row with the list's name as that link, never its checked date; no row or
      chip without data
    - production: a place page is indexable exactly when its Korean page is; noindex ones are absent from sitemap.xml
      and llms.txt; every URL of the version in sitemap.xml is a page without noindex
    - <home>events/: every value two sources give differently, and the note, are on the page
    - the closed day of the key facts (hero tiles, list cells, cards): wherever the Korean slot shows one, this
      version's slot shows it with as many sources, from its own value, whole where the Korean is whole
      (key_fact_problems); the places / food / stays lists row by row against the Korean lists (list_closed_problems)
    - every tel: link dials from abroad: +82 and the number without its leading 0 (QA 2026-10-15 SRC-05a), except a
      number with no international form — nationwide 15xx/16xx/18xx, the short emergency / 1330 numbers, 080, 060
    - the other versions (not English): the script and language of the rendered text (pipeline/locales.
      script_problems — Chinese script both ways, kana in Japanese prose, Cyrillic in Russian prose, the language of
      German / French / Spanish prose, no Han or kana in a Latin or Cyrillic version), and a warning for every label
      strings.json lacks (the page shows its key instead)"""
    from .en_source import current_hashes
    loc, code = site.loc, site.loc.code
    name = LANG_KO[code]
    ldir = Path(data_dir) / code
    recs = {k: (json.loads((ldir / f"{k}.json").read_text("utf-8")) if (ldir / f"{k}.json").exists() else {})
            for k in ("places", "guides", "courses", "events")}
    hashes = current_hashes(Path(data_dir))
    stores = {"place": "places", "guide": "guides", "course": "courses", "event": "events"}
    files = sorted((out / code).rglob("*.html")) if (out / code).exists() else []
    stats[f"{code}_pages"] = len(files)
    scans: dict[str, PageScan] = {}
    for f in files:
        rel = "/" + str(f.relative_to(out)).replace("\\", "/")
        p = scans[rel] = scan_file(f)
        if p.html_lang != loc.html:
            E(rel, f'{name} 페이지인데 <html lang="{p.html_lang}">')
        if p.hangul:
            E(rel, f'lang="ko" 밖에 한글 {len(p.hangul)}곳 (예: {p.hangul[0]})')
        for h in p.hrefs:
            if h.startswith("tel:") and not TEL_ABROAD.fullmatch(h):
                E(rel, f"국제 형식이 아닌 전화 링크(외국어 페이지): {h}")
        for r in p.records:
            kind, _, key = r.partition(":")
            store = stores.get(kind)
            if store and (key not in recs[store] or recs[store][key].get("ko_hash") != hashes[store].get(key)):
                E(rel, f"현재 한국어와 맞지 않는(낡은) {name} 번역을 화면에 냄: {r}")
        if code != "en":
            for problem in LC.script_problems(HANGUL.sub(" ", " ".join(p.foreign)), code, prose=False):
                E(rel, f"글자·언어: {problem}")
            for blk in ("summary", "details", "faq"):
                prose = p.blocks.get(blk, "")
                for note in p.notes:   # a citation line ('出典：○○市文化観光') is a label of names, not prose
                    if note.strip():
                        prose = prose.replace(note, " ")
                for problem in LC.script_problems(HANGUL.sub(" ", prose), code, prose=True):
                    E(rel, f"글자·언어({blk}): {problem}")
    for ko_path, l_path in site.ko2en.items():
        for path in (ko_path, l_path):
            rel = "/" + str(_file_for(out, path).relative_to(out)).replace("\\", "/")
            alts = dict((pages.get(rel) or ("", []))[1])
            if not alts:
                E(rel, f"한·영 짝 페이지인데 hreflang 없음 ({ko_path} ↔ {l_path})" if code == "en" else
                  f"한국어·{name} 짝 페이지인데 hreflang 없음 ({ko_path} ↔ {l_path})")
            elif "ko" not in alts or loc.html not in alts:
                E(rel, f"hreflang에 ko 또는 {loc.html}이 없음 ({ko_path} ↔ {l_path})")

    def page_of(path: str) -> PageScan | None:
        rel = "/" + str(_file_for(out, path).relative_to(out)).replace("\\", "/")
        return scans.get(rel)

    for p in site.places.values():
        e, rec = p["e"], p["rec"]
        where = f"en {e['id']} {p['name']}" if code == "en" else f"{code} {e['id']} {p['name']}"
        page = page_of(p["path"])
        if not page:
            E(where, f"{name} 페이지 없음: {p['path']}")
            continue
        if squash_ws(page.h1) != squash_ws(rec.get(loc.name_key)):
            E(where, f"h1이 {loc.name_key}과 다름: {page.h1!r}")
        if squash_ws(e["name"]) not in page.body:
            E(where, "한국어 이름이 화면에 없음")
        block = squash_ws(page.blocks.get("facts", ""))
        for k, fv in (rec.get("facts") or {}).items():
            rows = [r for r in page.fact_rows if k in r["keys"]]

            def shown(v) -> bool:
                return any(_verbatim(squash_ws(v), r["exact"]) for r in rows)
            if squash_ws(fv.get("value")) and not shown(fv["value"]):
                E(where, f"facts.{k} {name} 값이 방문 전 확인 블록의 해당 줄에 그대로 보이지 않음")
            for a in fv.get("alternatives") or []:
                provider = site.provider(a.get("provider"))
                if not shown(a.get("value")) or provider not in block:
                    E(where, f"facts.{k}: 출처마다 다른 값이 출처와 함께 보이지 않음({provider}: {squash_ws(a.get('value'))[:20]})")
            if fv.get("alternatives") and squash_ws(fv.get("note") or loc.conflict) not in block:
                E(where, f"facts.{k}: 출처마다 값이 다른데 '{squash_ws(fv.get('note') or loc.conflict)}' 없음")
            for a in fv.get("also") or []:
                if not shown(a.get("value")):
                    E(where, f"facts.{k}: 추가 값이 보이지 않음({squash_ws(a.get('value'))[:20]})")
        # the closed day of the first screen and the list cells (present.slot_value): wherever the Korean shows one,
        # this version shows it too, from its own value at the place the Korean parse finds (en_site.closed_span), with
        # every source the Korean shows, and the hours tile does not carry it
        for problem in key_fact_problems(site, p):
            E(where, problem)
        # places that belong together (pipeline/relations.py): the relation line, parts, nearby rows and JSON-LD here
        nodes, _ = _graph_nodes(page.jsonld_raw)
        node = next((n for n in nodes if str(n.get("@id", "")) == f"{p['url']}#place"), None)
        ref = lambda x: (lambda xp: (xp["path"], xp["url"]) if xp else None)(site.own(x))  # noqa: E731
        for problem in relation_page_problems(S, e, page, node, ref):
            E(where, problem)
        # official designations: the Korean page's, each in this language as a chip and in the 'Designations' row
        l_ds = site.designations(e)
        if len(l_ds) != len(designations(e)):
            E(where, f"한국어 페이지의 지정 가운데 {name} 이름·목록 이름(strings designation:/designation_source:)이 없는 것이 있음")
        dz_rows = [r for r in page.fact_rows if "designations" in r["keys"]]
        dz_chips, dz_hrefs = squash_ws(page.blocks.get("designations", "")), page.block_hrefs.get("designations", [])
        for d in l_ds:
            line = f"{d['label']} {d['source_name']}"
            if not any(line in r["text"] and d["url"] in r["hrefs"] for r in dz_rows):
                E(where, f"지정 '{d['label']}'이 Designations 줄에 목록 이름·링크와 함께 없음")
            if any(d["checked_at"] in r["text"] for r in dz_rows):
                E(where, f"지정 '{d['label']}'의 확인일({d['checked_at']})이 Designations 줄에 보임")
            if d["label"] not in dz_chips or d["url"] not in dz_hrefs:
                E(where, f"지정 '{d['label']}'이 첫 화면 지정 칩에 목록 링크와 함께 없음")
        if not l_ds and (dz_rows or "designations" in page.blocks):
            E(where, "지정 데이터가 없는데 Designations 줄이나 칩이 있음")
        if strict:
            noindex = page.meta.get("robots", "").startswith("noindex")
            if e["_index_ok"] and noindex:
                E(where, f"한국어 페이지가 색인 대상인데 {name} 페이지에 noindex")
            if not e["_index_ok"]:
                if not noindex:
                    E(where, f"한국어 페이지가 색인 기준 미달인데 {name} 페이지에 noindex 없음")
                if p["url"] in sitemap:
                    E(where, "색인 기준 미달인데 sitemap.xml에 있음")
                if p["url"] in llms.get("llms.txt", ""):
                    E(where, "색인 기준 미달인데 llms.txt에 있음")
            elif p["url"] not in sitemap:
                E(where, "색인 대상인데 sitemap.xml에 없음")
    for x in list(site.guides.values()) + list(site.courses.values()):
        if not page_of(x["path"]):
            E(x["path"], f"{name} 페이지 없음")
    if strict:
        for url in sorted(sitemap):
            path = unquote(urlsplit(url).path)
            if path.startswith(site.home):
                page = page_of(path)
                if not page:
                    E("sitemap.xml", f"없는 {name} 페이지: {url}")
                elif page.meta.get("robots", "").startswith("noindex"):
                    E("sitemap.xml", f"noindex {name} 페이지가 들어 있음: {url}")
    ev = page_of(f"{site.home}events/")
    if site.series and S.events:
        if not ev:
            E(f"{site.home}events/", f"{name} 행사 페이지 없음")
        else:
            for x in site.series:
                for field, a in (x["rec"].get("alternatives") or {}).items():
                    for v in a.get("values") or []:
                        # Japanese and Chinese: the page joins elements with a space ('2445 （運営'), compared without
                        if squash_ws(v)[:40] not in ev.body and not (
                                loc.cjk and re.sub(r"\s", "", v)[:40] in re.sub(r"\s", "", ev.body)):
                            E(f"{site.home}events/", f"{x['rec'].get('series_name')}: 출처마다 다른 값이 화면에 없음({squash_ws(v)[:20]})")
                    if squash_ws(a.get("note") or loc.event_conflict) not in ev.body:
                        E(f"{site.home}events/", f"{x['rec'].get('series_name')}: '{loc.event_conflict}' 없음")
                for h in x["rec"].get("highlights") or []:
                    if squash_ws(h)[:40] not in ev.body:
                        E(f"{site.home}events/", f"{x['rec'].get('series_name')}: 주요 프로그램이 화면에 없음({squash_ws(h)[:20]})")
    for kind, lp in en_site.LIST_PAGES.items():
        ko_list, l_list = _file_for(out, lp["ko"]), _file_for(out, f"{site.home}{lp['seg']}")
        if ko_list.exists() and l_list.exists():
            for problem in list_closed_problems(ko_list.read_text("utf-8"), l_list.read_text("utf-8")):
                E(f"{site.home}{lp['seg']}", problem)
    if code != "en" and site.misses:
        W(site.home, f"strings.json에 없는 이름표 {len(site.misses)}개(화면에 키가 대신 나옴): {sorted(site.misses)[:5]}")


def key_fact_problems(site, p: dict) -> list[str]:
    """The closed-day slot of one place in a version besides Korean against the Korean slot (present.slot_value):
    present when the Korean has one (never 'not listed', never left out), the same number of sources when the
    Korean shows two, each value a part of this version's own value (no rewording), and a closed-day field the
    Korean tile shows whole shown whole here too (never 'the first' of 'the first and third Sundays')."""
    e, out = p["e"], []
    ko = present.slot_value(e, "closed") if e.get("kind") != "stay" else None
    if not ko:
        return out
    mine = site.slot(p, "closed")
    if not mine or mine.get("skip") or not (mine.get("main") or mine.get("vals")):
        return [f"쉬는 날: 한국어 첫 화면·목록에 있는데({ko['main']}) 이 판에서 찾지 못함 — "
                f"{(mine or {}).get('why') or '값 없음'}"]
    if ko.get("conflict") and len(mine.get("vals") or []) != len(ko["vals"]):
        out.append(f"쉬는 날: 한국어는 출처 {len(ko['vals'])}곳의 값을 함께 보이는데 이 판은 {len(mine.get('vals') or [1])}곳")
    f = (p["rec"].get("facts") or {}).get(ko["src_key"]) or {}
    whole = " ".join(squash_ws(x) for x in [f.get("value")] + [a.get("value") for a in f.get("alternatives") or []])
    for x in [mine] + list(mine.get("vals") or []):
        t = squash_ws(x.get("main"))
        if t and t.lower() not in whole.lower():
            out.append(f"쉬는 날 '{t[:20]}'이 이 판의 값에 그대로 없음")
    if ko["src_key"] == "restdate":
        def norm(x) -> str:
            return squash_ws(x).lower().rstrip(".。")
        ko_raw = (e.get("facts") or {}).get("restdate")
        ko_alts = [a["value"] for a in en_site.conflict_alternatives(e, "restdate")]
        tr_alts = [a.get("value") for a in f.get("alternatives") or []]
        ko_shown = [squash_ws(x.get("main")) for x in (ko.get("vals") or [])[1:]]
        mine_alts = [norm(x.get("main")) for x in (mine.get("vals") or [])[1:]]
        pairs = [(ko_raw, f.get("value"), [norm(mine.get("main"))])]
        if len(ko_alts) == len(tr_alts):   # another source's value, where the Korean tile shows it
            for k, t in zip(ko_alts, tr_alts):
                kb = present.brief_closed(" ".join(present.clean_lines(k)))
                if kb and kb["main"] in ko_shown:
                    pairs.append((k, t, mine_alts))
        for k, t, shown in pairs:
            want = en_site.closed_whole(t, k) if en_site.ko_closed_whole(k) else ""
            if want and want.lower() not in shown:
                out.append(f"쉬는 날이 잘림: '{(shown or [''])[0][:24]}' (값: '{want[:40]}')")
    return out


LIST_ROW = re.compile(r'<li class="rec"[^>]*>(.*?)</li>', re.S)


def list_closed_problems(ko_html: str, l_html: str) -> list[str]:
    """A version's list page against the Korean one, row by row (data-place): a closed-day cell 'not listed'
    (kf-na) only where the Korean cell is, and two sources (is-conflict) where the Korean shows two."""
    def rows(h: str) -> dict[str, tuple[bool, bool]]:
        out = {}
        for m in LIST_ROW.finditer(h):
            pid = re.search(r'data-place="([^"]+)"', m.group(1))
            # (a Korean card with an empty cell leaves it out and says its columns: data-c — QA 2026-10-19 QA-77)
            cell = re.search(r'<div class="c-closed( is-conflict)?"(?: data-c="\d")?>(.*?)</div>', m.group(1), re.S)
            if pid and cell:
                out[pid.group(1)] = (bool(cell.group(1)), 'class="kf-na"' in cell.group(2))
        return out
    ko, mine, out = rows(ko_html), rows(l_html), []
    for pid, (conflict, na) in mine.items():
        if pid not in ko:
            continue
        if na and not ko[pid][1]:
            out.append(f"{pid}: 쉬는 날이 한국어 목록에는 있는데 '기재 없음'으로 나옴")
        if ko[pid][0] and not conflict:
            out.append(f"{pid}: 한국어 목록은 쉬는 날을 출처별로 함께 보이는데 이 판은 한 값만")
    return out


def validate_en(S, data_dir: Path, out: Path, strict: bool, E, W, sitemap: set, llms: dict, stats: dict,
                pages: dict) -> None:
    """The English pages (validate_intl with the English site) and the hreflang links of every page."""
    validate_intl(S, S.en, data_dir, out, strict, E, W, sitemap, llms, stats, pages)
    for rel, problem in hreflang_problems(pages):
        E(rel, problem)


def validate(data_dir: Path, out: Path, mode: str = "production") -> tuple[list[str], list[str], dict]:
    S = State(data_dir, mode)
    S.intl = en_site.load_all(S, data_dir)
    S.en = S.intl.sites.get("en")
    strict = mode == "production"
    errors: list[str] = []
    warns: list[str] = []
    stats = {"entity_pages": 0, "blocks_ok": 0, "precision": {"all": 0, "some": 0, "none": 0},
             "original_shown": 0, "original_linked": 0, "index": index_counts(S.entities)}
    E = lambda where, msg: errors.append(f"[{where}] {msg}")
    W = lambda where, msg: warns.append(f"[{where}] {msg}")
    sitemap = _sitemap_locs(out)
    llms = {name: (out / name).read_text("utf-8") if (out / name).exists() else ""
            for name in ("llms.txt", "llms-full.txt")}

    for problem in nearby_data_problems(S):
        E("nearby.json", problem)
    for where, problem in relations.problems(S.entities_all, S.entities):   # part_of (pipeline/relations.py)
        E(where, problem)
    for where, problem in relations.fact_differences(S.entities):
        W(where, problem)
    for problem in nearby_stale_problems(S):
        W("nearby.json", problem)
    for problems, report in zip(geo_problems(S), (E, W)):   # every published point: box, source, url/date
        for problem in problems:
            report("geo", problem)
    for problems, report in zip(nearby_provenance_problems(S), (E, W)):
        for problem in problems:
            report("nearby_source", problem)
    for problem in transit_problems(S):
        E("transit.json", problem)
    for c in S.courses:   # the '차 없이 다니기' block of each course page (QA 2026-10-15 F09)
        f = _file_for(out, c["_path"])
        if f.exists():
            scan = scan_file(f)
            for problem in course_move_problems(S, c, scan):
                E(c["_path"], problem)
            # the sources name whose coordinates the measured legs join (present.course_vm geo_src)
            cv = S.course_vms[c["slug"]]
            want = f"{cv['measured']}구간을 {cv['geo_src']} 좌표 사이 직선으로 잼"
            if cv["legs_possible"] and cv["geo_src"] and want not in squash_ws(scan.visible):
                E(c["_path"], f"거리 계산 출처에 좌표 출처가 없음: '{want}'")
    for problem in art.data_problems(data_dir):
        E("art.json", problem)
    for problem in highlight_problems(data_dir):
        E("abroad_highlights.json", problem)
    if S.abroad_highlights:   # the row on /abroad/ links every original; the viewer's markup holds every quotation
        f = _file_for(out, "/abroad/")
        scan = scan_file(f) if f.exists() else PageScan()
        viewer, shown, html = out / HL_VIEWER.strip("/"), PageScan(), ""
        if viewer.exists():
            try:
                html = json.loads(viewer.read_text("utf-8")).get("html") or ""
            except ValueError as ex:
                E(HL_VIEWER, f"JSON 오류: {ex}")
        shown.feed(html)
        quotes = _quotations(html, "")
        page_quotes = _quotations(f.read_text("utf-8"), "ab-q") if f.exists() else set()
        for h in S.abroad_highlights:
            a = h["item"]
            if a["url"] not in scan.hrefs:
                E("/abroad/", f"하이라이트 줄에 원문 링크가 없음: {a['id']}")
            if f'data-url="{a["url"]}"' not in unescape(html) and a["url"] not in shown.hrefs:
                E(HL_VIEWER, f"하이라이트가 보기 창에 없음: {a['id']}")
            if h["quote"] and (h["quote"], h["quote_lang"], a["url"]) not in quotes:
                E(HL_VIEWER, f"인용문이 보기 창에 blockquote(lang·cite)로 없음: {a['id']}")
            if h["quote"] and a.get("kind") == "article" and (h["quote"], h["quote_lang"], a["url"]) not in page_quotes:
                E("/abroad/", f"인용문이 기사 카드에 없음: {a['id']}")
    # the homes' starter questions (pipeline/ask.py): each names one guide this build publishes, or a list page
    for problem in ask.data_problems(data_dir, {g["id"] for g in S.guides}):
        E("ask.json", problem)
    for where, problem in notice_problems(S, out):
        E(where, problem)
    # combined tickets (pipeline/tickets.py): published places, and every price and rule written in its source's table
    for problem in tickets.problems(S.tickets, {p["id"]: p for p in S.entities_all}, {e["id"] for e in S.entities}):
        E("tickets.json", problem)
    style = out / "assets" / "style.css"
    if style.exists() and art.URL_PREFIX in style.read_text("utf-8"):
        E("style.css", "CSS 배경으로 AI 그림을 씀 — templates/_art.html.j2 figure()의 <img>로만(표기·alt 규칙)")
    for e in S.entities:
        where = f"{e['id']} {e['name']}"
        f = _file_for(out, e["_path"])
        if not f.exists():
            E(where, f"페이지 없음: {e['_path']}")
            continue
        stats["entity_pages"] += 1
        p = scan_file(f)
        tier = e.get("tier") or "basic"
        ok = True
        for b in REQUIRED_BLOCKS[tier]:
            if b not in p.blocks:
                E(where, f"{tier} 등급 필수 블록 없음: {b}")
                ok = False
            elif len(squash_ws(p.blocks[b])) < MIN_LEN[b]:
                (E if strict else W)(where, f"블록 내용 부족: {b}")
                ok = False
        stats["blocks_ok"] += ok

        nodes, errs = _graph_nodes(p.jsonld_raw)
        for x in errs:
            E(where, x)
        main = [n for n in nodes if set(node_types(n)) & ENTITY_TYPES and n.get("name") == e["name"]
                and str(n.get("@id", "")).endswith("#place") and "url" in n]
        if not main:
            E(where, "구조화 데이터에 이 장소 노드가 없음")
        else:
            node = main[0]
            if (e.get("geo") or {}).get("lat") is not None and "geo" not in node:
                E(where, "좌표가 있는데 구조화 데이터에 geo 없음")
            if node.get("description") and squash_ws(node["description"]) not in p.plain:
                E(where, "구조화 데이터 description이 본문 요약과 다름")
            alt = node.get("alternateName") or []
            for name in [alt] if isinstance(alt, str) else alt:
                if squash_ws(name) not in p.body:   # the title holds the qualified name; the body must show it
                    E(where, f"구조화 데이터 alternateName이 화면에 없음: {name}")
            for problem in designation_awards(e, node, p):
                E(where, problem)
        for problem in designation_page_problems(e, p):
            E(where, problem)
        for problem in seat_only_parking_problems(e, p):
            E(where, problem)
        for problem in access_problems(S, e, p):
            E(where, problem)
        for problem in relation_page_problems(S, e, p, main[0] if main else None, lambda x: (x["_path"], x["_url"])):
            E(where, problem)
        for problem in place_geo_page_problems(e, p):
            E(where, problem)
        if squash_ws(p.h1) != squash_ws(e["name"]):
            E(where, f"h1이 장소명과 다름: {p.h1!r}")
        practical = [k for k in (e.get("facts") or {}) if k not in ("address", "homepage")]
        if not practical:
            (E if strict else W)(where, "실용 정보 없음 — 주소 외 방문 정보가 하나 이상 있어야 공개(02 표준 3절)")
        facts_block = squash_ws(p.blocks.get("facts", ""))
        # Every stored value is shown whole in its own row of the facts block (fact_shown): verbatim, every word
        # and symbol in order, URLs linked in full. This replaced a probe of the first 20 characters anywhere in
        # the block — the whole value is now checked, in its own row.
        for k, v in (e.get("facts") or {}).items():
            if not fact_shown(p, k, v):
                W(where, f"facts.{k} 값이 방문 전 확인 블록의 해당 줄에 그대로 보이지 않음")
        # CLAUDE.md 3.2: when sources disagree, every value is on the page with its provider, plus one call note
        alt_rows = [r for r in (fact_row(e, k) for k in FACT_ORDER + FIT_ORDER) if r and r["alternatives"]]
        for r in alt_rows:
            shown = [(r["value"], r["source"].get("provider"))] if r["value"] else []
            for value, provider in shown + [(a["value"], a["provider"]) for a in r["alternatives"]]:
                if not fact_shown(p, r["key"], value) or (provider and provider not in facts_block):
                    E(where, f"facts.{r['key']}: 출처마다 다른 값이 출처와 함께 보이지 않음({provider}: {squash_ws(value)[:20]})")
        conflicting = [r for r in alt_rows if any(not a.get("also") for a in r["alternatives"])]
        if conflicting and "방문 전 전화 확인" not in facts_block:  # 'also' values (a second dish) do not contradict
            E(where, "출처마다 값이 다른 항목이 있는데 '방문 전 전화 확인' 안내 없음")

        if p.canonical != e["_url"]:
            E(where, f"canonical 불일치: {p.canonical}")
        if len(p.title) > 70:
            W(where, f"title 70자 초과({len(p.title)})")
        desc = p.meta.get("description", "")
        if not (40 <= len(desc) <= 160):
            W(where, f"description 길이 {len(desc)}자 (권장 40~160)")

        orig = e.get("original") or {}
        text = orig.get("text") or ""
        if text:
            shown = squash_ws(text) in squash_ws(p.blocks.get("original", ""))
            allowed = license_allowed(orig.get("license"), S.allowed_original)
            if allowed:
                stats["original_shown"] += 1
                if not shown:
                    E(where, "원문이 그대로 게재되지 않음(수정·누락 의심)")
                if orig.get("sha256") and orig["sha256"] != sha256_text(text):
                    E(where, "원문 해시 불일치 — 데이터의 원문이 수집 후 수정됨")
            else:
                stats["original_linked"] += 1
                probe = squash_ws(text)[:30]
                if probe and probe in p.plain:
                    E(where, f"이용조건 미확인({orig.get('license')}) 원문이 페이지에 노출됨")
        # our sentences never copy a stored source text (TourAPI overview, the original) for 15+ characters
        for issue in copy_issues(e):
            E(where, f"원문 베끼기(CLAUDE.md 3절 3항) — {issue}")

        geo, mid = e.get("geo") or {}, e.get("map_ids") or {}
        links = build_links(e["name"], geo.get("lat"), geo.get("lng"), S.site.get("region", ""),
                            (e.get("facts") or {}).get("address", ""), mid.get("naver_place_id", ""),
                            mid.get("google_place_id", ""), S.site.get("tmap_scheme", DEFAULT_TMAP_SCHEME),
                            kakao_place_id=mid.get("kakao_place_id", ""))
        stats["precision"][precision_summary(links)] += 1

        if strict:
            if not (e.get("reviewed_at") or e.get("approved_at")):
                E(where, "published인데 reviewed_at(검수일)도 approved_at(운영자 공개 승인)도 없음")
            noindex = p.meta.get("robots", "").startswith("noindex")
            in_llms = [name for name, text in llms.items() if e["_url"] in text]
            if e["_index_ok"]:
                if noindex:
                    E(where, "색인 기준을 충족한 공개 페이지에 noindex")
                if e["_url"] not in sitemap:
                    E(where, "색인 대상인데 sitemap.xml에 없음")
                if "llms.txt" not in in_llms:
                    W(where, "색인 대상인데 llms.txt에 없음")
            else:
                why = ", ".join(e["_index_reasons"])
                if not noindex:
                    E(where, f"색인 기준 미달인데 noindex 없음 ({why})")
                if e["_url"] in sitemap:
                    E(where, f"색인 기준 미달인데 sitemap.xml에 있음 ({why})")
                for name in in_llms:
                    E(where, f"색인 기준 미달인데 {name}에 있음 ({why})")

    # list pages: the designation chips' lists, linked with their 확인일
    for kind, cfg in LISTS.items():
        f = _file_for(out, cfg["path"])
        if S.lists[kind] and f.exists():
            for problem in designation_list_problems(S, kind, scan_file(f)):
                E(cfg["path"], problem)

    for g in S.guides:
        for it in g.get("items") or []:
            if it.get("place_slug") and it["place_slug"] not in S.ent_by_slug:
                W(g["title"], f"가이드가 비공개/없는 장소를 참조: {it['place_slug']}")
        if strict and not (g.get("reviewed_at") or g.get("approved_at")):
            E(g["title"], "published 가이드에 reviewed_at·approved_at 없음")
    # guide and course text: no 15+ character stretch of its own original or of a place it points to (CLAUDE.md 3.3)
    places_by_slug = {x.get("slug"): x for x in S.entities_all if not x.get("duplicate_of")}
    for g in [*S.guides, *S.courses]:
        for issue in guide_issues(g, places_by_slug, copy_only=True):
            E(g.get("title") or g.get("name") or g.get("slug", ""), f"원문 베끼기(CLAUDE.md 3절 3항) — {issue}")

    # Event leaf pages (CLAUDE.md 3.2): every value that differs between sources is shown with the confirm line,
    # and the programme list is on the page.
    for sr in S.series:
        f = _file_for(out, sr["_path"])
        if not f.exists():
            E(sr["name"], f"행사 페이지 없음: {sr['_path']}")
            continue
        body = scan_file(f).body
        values = [a for r in sr["alternatives"] for a in r["values"]]
        for a in values:
            if squash_ws(a.get("value"))[:20] not in body:
                E(sr["name"], f"출처마다 다른 값이 화면에 없음: {squash_ws(a.get('value'))[:20]}")
        if values and "방문 전 주최 측 확인" not in body:
            E(sr["name"], "출처마다 값이 다른 항목이 있는데 '방문 전 주최 측 확인' 안내 없음")
        for h in (sr["program"] or {}).get("highlights") or []:
            if squash_ws(h)[:20] not in body:
                E(sr["name"], f"주요 프로그램이 화면에 없음: {squash_ws(h)[:20]}")

    # 예약하기 (pipeline/booking.py): booking.json itself, then every page's buttons in the loop below
    for problem in booking.data_problems(S):
        E("booking.json", problem)
    book_expect, book_allowed = booking_expectations(S, out), booking.allowed_urls(S)
    # Every HTML file: internal links, placeholders, noindex consistency
    html_files = sorted(out.rglob("*.html"))
    lang_pages: dict[str, tuple[str, list]] = {}   # rel -> (canonical, hreflang links), for the hreflang checks
    art_used: set[str] = set()                     # the AI art renditions the pages show
    for f in html_files:
        rel = "/" + str(f.relative_to(out)).replace("\\", "/")
        raw = f.read_text("utf-8")
        p = PageScan()
        p.feed(raw)
        lang_pages[rel] = (p.canonical, p.alternates)
        nodes, _ = _graph_nodes(p.jsonld_raw)
        for problem in jsonld_visibility(nodes, p):
            E(rel, f"구조화 데이터가 화면과 다름: {problem}")
        # AI art (owner decision 2026-10-13, CLAUDE.md 4): labelled, never on a place page or in a place's data
        place = any(set(node_types(n)) & ENTITY_TYPES and str(n.get("@id", "")).endswith("#place") for n in nodes)
        for problem in art.page_problems(raw, nodes, place, out):
            E(rel, problem)
        art_used |= art.files_in(raw)
        seen_text = " ".join([p.visible, p.meta.get("description", ""), p.meta.get("og:description", ""),
                              p.meta.get("og:title", "")])
        for hit in dict.fromkeys(visible_check_dates(seen_text)):
            E(rel, f"확인·갱신 날짜가 화면에 보임(운영자 결정 2026-10-09: 데이터·구조화 데이터에만): {hit}")
        for problem in dead_link_problems(" ".join([seen_text, *p.jsonld_raw]), p.hrefs, S.dead_links):
            E(rel, problem)
        for problem in booking_problems(S, p, book_expect.get(rel), LC.code_of_path(rel), book_allowed):
            E(rel, problem)
        # Korean pages (owner 2026-10-14, Naver Search Advisor): the description and its og / twitter copies ≤ DESC_MAX
        if p.html_lang.startswith("ko"):
            for key in ("description", "og:description", "twitter:description"):
                if len(p.meta.get(key, "")) > DESC_MAX:
                    W(rel, f"{key} {len(p.meta[key])}자 — 한국어 설명문은 {DESC_MAX}자 이내(네이버 서치어드바이저 권장)")
        for href in p.hrefs:
            parts = urlsplit(href)
            if parts.scheme or href.startswith("//") or not parts.path.startswith("/"):
                continue
            if not _file_for(out, parts.path).exists():
                E(rel, f"내부 링크 깨짐: {href}")
        if strict:
            for ph in PLACEHOLDERS:
                if ph in p.plain:
                    E(rel, f"자리표시 문구 남음: {ph}")
        elif MODES[mode]["noindex"] and not p.meta.get("robots", "").startswith("noindex"):
            E(rel, "미리보기/샘플인데 noindex 없음")
    # a '연결' picture of a guide, course or theme that no page shows: that page is not in this build
    for problem in art.unshown(data_dir, art_used):
        W("art.json", problem)
    # the site says once, on /about/, that its illustrations are drawn with generative AI (CLAUDE.md 4), whenever a page
    # shows one
    about = out / "about" / "index.html"
    if art_used and about.exists() and "생성형 AI" not in about.read_text("utf-8"):
        E("/about/", "AI 일러스트를 싣는데 소개 페이지에 '이 사이트의 일러스트는 생성형 AI로 그렸다'는 안내가 없음(CLAUDE.md 4절)")

    # the other versions (/en/ /ja/ …) — only with data/<region>/<code> and complete UI words; a build without them
    # has no such pages and no hreflang or language menu link to them
    for code, site in S.intl.sites.items():
        validate_intl(S, site, data_dir, out, strict, E, W, sitemap, llms, stats, lang_pages)
    for code in LC.CODES:
        if code not in S.intl.sites and (out / code).exists():
            E(f"/{code}/", "data/<지역>/en 없이 영어 페이지가 있음" if code == "en" else
              f"data/<지역>/{code} 없이(또는 화면 문구가 모자라 만들지 않을) {LANG_KO[code]} 페이지가 있음")
    for code in S.intl.no_names:
        W(f"/{code}/", f"site.json city.intl.{code}에 사이트 이름·도시 이름이 없어 이 언어 페이지를 만들지 않음")
    for code, missing in S.intl.skipped.items():
        W(f"/{code}/", f"data/<지역>/{code}/strings.json에 화면 문구(chrome.*) {len(missing)}개가 없어 이 언어 페이지를 "
                       f"만들지 않음 (예: {missing[:3]})")
    built = {s.loc.html for s in S.intl.sites.values()} | {"ko", "x-default"}
    for rel, (_, alts) in lang_pages.items():   # a hreflang to a version this build does not have
        for h in sorted({h for h, _ in alts} - built):
            E(rel, f"이 빌드에 없는 언어의 hreflang: {h}")
    for rel, problem in hreflang_problems(lang_pages):
        E(rel, problem)

    robots = (out / "robots.txt").read_text("utf-8") if (out / "robots.txt").exists() else ""
    if not robots:
        E("robots.txt", "없음")
    elif strict:
        if "User-agent: *\nDisallow: /" in robots:
            E("robots.txt", "공개 모드인데 전체 차단")
        if "OAI-SearchBot" not in robots:
            W("robots.txt", "OAI-SearchBot 명시 없음")
        if "Sitemap:" not in robots:
            E("robots.txt", "Sitemap 줄 없음")
    sm = out / "sitemap.xml"
    if not sm.exists():
        E("sitemap.xml", "없음")
    else:
        try:
            locs = [el.text for el in ET.parse(sm).getroot().iter(f"{SITEMAP_NS}loc")]
            stats["sitemap_urls"] = len(locs)
            bad = [u for u in locs if not (u or "").startswith(S.site_url)]
            if bad:
                E("sitemap.xml", f"site_url과 다른 주소 {len(bad)}건")
        except ET.ParseError as ex:
            E("sitemap.xml", f"XML 오류: {ex}")
    if not (out / "llms.txt").exists():
        W("llms.txt", "없음")
    for name, text in llms.items():
        for hit in dict.fromkeys(visible_check_dates(text)):
            E(name, f"확인·갱신 날짜가 보임(운영자 결정 2026-10-09: 데이터·구조화 데이터에만): {hit}")
    # the AI-facing files: llms.txt, llms-full.txt and the assistant's knowledge (chat/catalog.txt, docs.json …)
    ai_files = dict(llms)
    if (out / "chat").is_dir():
        ai_files.update({"/" + f.relative_to(out).as_posix(): f.read_text("utf-8")
                         for f in sorted((out / "chat").iterdir()) if f.is_file() and f.suffix in (".txt", ".json")})
    for name, text in ai_files.items():
        for problem in dead_link_problems(text, [], S.dead_links):
            E(name, problem)
    # the assistant's cached catalog against its design budget (chat_index.CATALOG_BUDGET): a warning, never an error
    if "/chat/catalog.txt" in ai_files:
        stats["catalog_tokens_est"] = chat_index.estimate_tokens(ai_files["/chat/catalog.txt"])
        over = chat_index.budget_warning(stats["catalog_tokens_est"])
        if over:
            W("chat/catalog.txt", over)

    if strict:
        su = S.site_url
        if not su.startswith("https://") or "example" in su or "(" in su:
            E("site.json", f"site_url이 최종 공개 주소가 아님: {su}")
        if not S.site.get("ga4_id"):
            waived = (S.site.get("launch_exceptions") or {}).get("ga4_id")
            if waived:  # the owner chose to launch first and add GA4 later (recorded in site.json)
                W("site.json", f"ga4_id 없음 — 운영자 예외: {waived}")
            else:
                E("site.json", "ga4_id 없음 — 신규 사이트 GA4 설치는 확정 사항")
        if not (S.site.get("operator") or {}).get("contact"):
            E("site.json", "operator.contact(정정 요청 연락처) 없음")
        n_bad, examples = _url_gate(out, html_files, su)
        if n_bad:
            E("URL", f"절대 주소 {n_bad}건이 site_url({su or '빈 값'})로 시작하지 않음 — canonical·og·sitemap·robots·"
                     f"llms·JSON-LD @id/url/item은 모두 https://공개 도메인 기준이어야 함 (예: {'; '.join(examples)})")
    stats.update({"errors": len(errors), "warnings": len(warns), "html_files": len(html_files), "mode": mode})
    return errors, warns, stats


def write_report(errors, warns, stats, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    pr = stats["precision"]
    lines = ["# QA 리포트", "",
             f"- 모드: {stats['mode']} / HTML {stats['html_files']}개 / 장소 페이지 {stats['entity_pages']}개",
             f"- 등급별 필수 블록 충족: {stats['blocks_ok']} / {stats['entity_pages']}",
             f"- 원문 전문 게재 {stats['original_shown']}건 / 이용조건 미확인으로 링크 처리 {stats['original_linked']}건",
             f"- 지도 링크 정확도(장소 단위): 모두 정확 {pr['all']} · 일부 {pr['some']} · 검색뿐 {pr['none']}",
             f"- sitemap URL {stats.get('sitemap_urls', '-')}개",
             f"- 색인 기준 충족 {stats['index']['indexable']} / 장소 페이지 {stats['index']['entity_pages']}"
             + ("" if stats["mode"] == "production" else " (기준은 production에서 적용)")
             + "".join(f" · {r} {n}" for r, n in stats["index"]["top_reasons"]),
             f"- 오류 {stats['errors']}건 / 경고 {stats['warnings']}건", "", "## 오류"]
    lines += [f"- {x}" for x in errors] or ["- 없음"]
    lines += ["", "## 경고"] + ([f"- {x}" for x in warns] or ["- 없음"])
    path.write_text("\n".join(lines) + "\n", "utf-8")


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--data", required=True, type=Path)
    ap.add_argument("--out", required=True, type=Path)
    ap.add_argument("--mode", choices=list(MODES), default="production")
    ap.add_argument("--report", type=Path, default=Path("reports/qa_report.md"))
    a = ap.parse_args(argv)
    errors, warns, stats = validate(a.data, a.out, a.mode)
    write_report(errors, warns, stats, a.report)
    print(json.dumps({k: v for k, v in stats.items()}, ensure_ascii=False))
    for x in errors[:30]:
        print("ERROR", x)
    return 1 if errors else 0


if __name__ == "__main__":
    sys.exit(main())
