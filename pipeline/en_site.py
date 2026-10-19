"""Every language version besides Korean, built by one engine next to the Korean pages.

English (/en/), Japanese (/ja/), Simplified and Traditional Chinese (/zh-hans/, /zh-hant/), German (/de/), French
(/fr/), Spanish (/es/) and Russian (/ru/). What differs by language is the locale table (pipeline/locales.py, English
being one locale) and the words the pages print (UIText: English's in pipeline/intl_text.py, every other version's
translated from those into data/<region>/<code>/strings.json 'chrome.<key>'). The module keeps its first name and
its English helpers (en_slug, sentences_en, brief_en, load …) for the code and tests that import them.

A version exists only when data/<region>/<code> exists (the sample data has none) and its UI words are complete.
Its records are translations of OUR Korean data (tools/en_content.py prepare → check → merge --lang <code>). Each
stores the hash of the Korean item it was translated from (`ko_hash`, pipeline/en_source.py — the same hash for every
language); this module recomputes that hash from the current Korean data. A stale record (the Korean changed since the
translation) is not rendered at all: the Korean page is then the only version, and the build prints the count.
Nothing here adds a fact: every value on a page is the language's record value, a number from the Korean data
(dates, distances, counts, phone numbers, coordinates), or a label from data/<region>/<code>/strings.json.

Routes (per version, <home> = /en/, /ja/ …):
    <home> · <home>places/ · <home>food/ · <home>stays/ · <home>places/<english-slug>/ · <home>guides/ (+ /<slug>/) ·
    <home>courses/ (+ /<slug>/) · <home>events/ · <home>about/
Slugs: every version uses the English slug of the same record (lowercase ASCII from name_en / title — guides: the
title before its colon — at most 60 characters cut at a word boundary; a name two records share keeps the plain slug
for the one translated first (then by id) and the others get the digits of their id, so a slug never changes while
its record stays). A record without a current English page gets the slug English would give it (SlugBook).
Index rule: a place page is indexable only when its Korean page is (schema.index_status, production) and its record
is current; otherwise noindex and out of sitemap.xml / llms.txt (still listed). hreflang: ko, every version the page
has (en, ja, zh-Hans, zh-Hant, de, fr, es, ru) and x-default (= Korean), the same list on every page of the set
(Intl.alternates). The language menu (templates/_lang.html.j2, Intl.menu) links each version's counterpart page,
else that version's home; it lists only the versions this build has.
"""
from __future__ import annotations

import json
import re
import unicodedata
from collections import Counter
from pathlib import Path
from urllib.parse import urlencode

from markupsafe import Markup, escape

from . import art, ask, intl_text, jsonld, media, present
from . import locales as LC
from .en_source import CONFLICT_NOTE, EVENT_CONFLICT_NOTE, HANGUL, _admin, current_hashes, event_series, romanize
from .maplinks import DEFAULT_TMAP_SCHEME, build_links
from .schema import FACT_ALIASES, KEY_FACTS, KEY_FACTS_BY_CATEGORY, designations, node_types, schema_type
from .textutil import display_address, extract_phones, link_url, phone_intl, url_domain, web_text, web_url

EN = LC.get("en")
EN_SITE_NAME = EN.site_name   # the owner's '군산 여행의 모든 것', matching the owner's address all-about-gunsan (2026-10-09)
EN_HOME = "/en/"
KINDS = ("attraction", "food", "stay")
# list pages: the path under the version's home, the Korean counterpart and the hub guide
LIST_PAGES = {"attraction": {"seg": "places/", "ko": "/places/", "hub": "guide-15"},
              "food": {"seg": "food/", "ko": "/food/", "hub": "guide-13"},
              "stay": {"seg": "stays/", "ko": "/stays/", "hub": "guide-14"}}
HUBS = ("guide-13", "guide-14", "guide-15")   # food by dish · lodging & pensions · things to do
NAV_KEYS = (("nav_attraction", "places/"), ("nav_food", "food/"), ("nav_stay", "stays/"), ("guides", "guides/"),
            ("courses", "courses/"), ("events", "events/"))
CURRENT = {"place-attraction": "places/", "places": "places/", "place-food": "food/", "list-food": "food/",
           "place-stay": "stays/", "list-stay": "stays/", "guide": "guides/", "guides": "guides/",
           "course": "courses/", "courses": "courses/", "events": "events/"}
SHORT_PROVIDER = {"한국관광공사": "provider_kto", "군산시": "provider_city", "공식 홈페이지": "provider_official"}
# key-fact slots: the label key in strings.json (the Korean slot names: present.SLOT_LABEL)
SLOT_STRING = {"hours": "TITLE_LABELS.usetime", "closed": "FACT_LABELS.restdate", "fee": "STATUS_PREFIX.usefee",
               "parking": "FACT_LABELS.parking", "tel": "INDEX_GROUP_LABELS.phone", "menu": "FACT_LABELS.menu",
               "checkin": "FACT_LABELS.checkin", "checkout": "FACT_LABELS.checkout", "rooms": "STATUS_PREFIX.roomcount"}
ABBR = EN.abbr
SENT_SPLIT = re.compile(r"(?<=[.?!])\s+(?=[A-Z0-9\"'(\[])")
TIME_RANGE = re.compile(r"\d{1,2}:\d{2}\s*[–-]\s*\d{1,2}:\d{2}")
WEEKDAY = re.compile(r"\b(Mon|Tues|Wednes|Thurs|Fri|Satur|Sun)days?\b")
CLOSED_WORDS = re.compile(r"(closed|open all year|open every day|no regular clos|open 24 hours|closing day)", re.I)
# the same two tests in the other languages (key-fact tiles: the closed-day part of an hours value, a weekday clause)
CLOSED_BY = {
    "ja": re.compile(r"(休み|休業|定休|休館|休園|年中無休|無休|24時間営業)"),
    "zh-hans": re.compile(r"(休息|闭馆|休馆|停业|全年无休|全年开放|24小时营业|无休)"),
    "zh-hant": re.compile(r"(休息|閉館|休館|停業|全年無休|全年開放|24小時營業|無休)"),
    "de": re.compile(r"(geschlossen|Ruhetag|ganzjährig geöffnet|täglich geöffnet|rund um die Uhr)", re.I),
    "fr": re.compile(r"(fermé|fermeture|ouvert toute l'année|ouvert tous les jours|ouvert 24 h)", re.I),
    "es": re.compile(r"(cerrado|cierra|abierto todo el año|abierto todos los días|abierto las 24 horas)", re.I),
    "ru": re.compile(r"(выходн|закрыт|без выходных|круглосуточно|круглый год)", re.I),
}
DURATION_ORDER = {"당일": 0, "1박 2일": 1, "2박 3일": 2}   # course groups: day trip, one night, two nights, the rest
BRIEF_MAX = 40
CELL_MAX = 48


# ---------------------------------------------------------------------------------------------- small helpers
def squash_ws(text: str | None) -> str:
    """textutil.squash_ws, but a narrow no-break space stays: French and Russian write thousands with it
    ('3\u202f000 wons'), and a line never breaks there (the data has none elsewhere)."""
    return re.sub(r"[^\S\u202f]+", " ", text or "").strip()


SLUG_TAIL = {"a", "an", "and", "at", "by", "for", "from", "in", "of", "on", "or", "the", "to", "with"}


def en_slug(text: str | None, max_len: int = 60) -> str:
    """'Eunpa Lake Park' -> 'eunpa-lake-park': lowercase ASCII, words joined by '-' ('Modern–Gogunsan' ->
    'modern-gogunsan'), cut at a word boundary without a dangling 'and' / 'the' …"""
    t = unicodedata.normalize("NFKD", squash_ws(text))
    t = "".join(c if c.isascii() else ("" if unicodedata.category(c).startswith("M") else " ") for c in t).lower()
    t = t.replace("&", " and ").replace("'", "")
    words = [w for w in re.split(r"[^a-z0-9]+", t) if w]
    out: list[str] = []
    for w in words:
        if out and len("-".join(out + [w])) > max_len:
            break
        out.append(w[:max_len])
    while len(out) > 1 and out[-1] in SLUG_TAIL:
        out.pop()
    return "-".join(out) or "item"


def sentences_en(text: str | None) -> list[str]:
    """English sentences; 'No. 183', 'Dr. Lee' and the like do not end one."""
    out: list[str] = []
    for part in SENT_SPLIT.split(squash_ws(text)):
        if out and re.search(rf"\b(?:{'|'.join(ABBR)})\.$", out[-1]):
            out[-1] = f"{out[-1]} {part}"
        elif part:
            out.append(part)
    return out


def sentences(text: str | None, loc: LC.Locale) -> list[str]:
    return sentences_en(text) if loc.code == "en" else loc.sentences(text)


def dist_en(m) -> str:
    """'430 m' (rounded to 10 m), '2.4 km'; '' for unknown."""
    return EN.dist(m)


def en_date(iso: str | None) -> str:
    """'2026-10-09' -> 'October 9, 2026'."""
    return EN.date(iso)


def en_md(iso: str | None) -> str:
    """'2026-10-09' -> 'Oct 9'."""
    return EN.md(iso)


def area_en(area: str | None) -> str:
    """'장미동' -> 'Jangmi-dong' (Revised Romanization, the administrative unit hyphenated)."""
    a = squash_ws(area)
    if not a:
        return ""
    if re.fullmatch(r"[가-힣]{2,}", a) and a[-1] in "동읍면리":
        return _admin(a)
    return romanize(a)


def no_hangul(text: str) -> str:
    return "" if HANGUL.search(text or "") else (text or "")


def lines_html(text: str | None) -> Markup:
    return Markup("<br>").join(escape(x) for x in str(text or "").split("\n"))


def _segments(value: str, timeish: bool) -> list[tuple[str, str]]:
    """A stored value cut into (header, text) parts at line breaks and ' / '. A '[Header]' line labels the part
    after it: hours read 'Summer (March–October) 09:00–18:00'; other values keep the header apart (fees: 'Adults
    500 won' under 'Individuals')."""
    parts = [p.strip() for p in re.split(r"\s*\n\s*|\s+/\s+", value or "") if p.strip()]
    out, head = [], ""
    for p in parts:
        m = re.fullmatch(r"\[(.+)\]", p)
        if m:
            head = m.group(1).strip()
            continue
        p = re.sub(r"^[-•※]\s*", "", p)
        out.append((("", f"{head} {p}") if timeish and head else (head, p)))
        if timeish:
            head = ""
    return out


def _clauses(t: str, loc: LC.Locale) -> list[str]:
    if loc.code == "en":
        cs = [re.sub(r"^(?:and|or)\s+", "", c.strip()).rstrip(".,;") for c in re.split(r"[,;]\s+|\.\s+|\s+and\s+", t)]
    elif loc.cjk:
        cs = [c.strip().rstrip("。、，；") for c in re.split(r"[、，；。]\s*", t)]
    else:
        conj = {"de": "und|oder", "fr": "et|ou", "es": "y|o", "ru": "и|или"}.get(loc.code, "and")
        cs = [re.sub(rf"^(?:{conj})\s+", "", c.strip()).rstrip(".,;") for c in
              re.split(rf"[,;]\s+|\.\s+|\s+(?:{conj})\s+", t)]
    return [c for c in cs if c]


def _weekday(text: str, loc: LC.Locale) -> bool:
    if loc.code == "en":
        return bool(WEEKDAY.search(text))
    return any(w[:3].lower() in text.lower() for w in loc.weekdays) if not loc.cjk else \
        any(w in text for w in loc.weekdays) or bool(re.search(r"[月火水木金土日]曜", text))


def _reduce(text: str, prefer_day: bool = False, loc: LC.Locale = EN) -> str:
    """A short main part of one segment: the whole when short; else without a trailing '(…)', else the first
    clause (the one naming a weekday for closed days), else the time range it states; else the whole segment
    (never cut inside a word or number)."""
    t = squash_ws(text)
    limit = BRIEF_MAX // 2 if loc.cjk else BRIEF_MAX
    if len(t) <= limit:
        return t
    s = t
    while re.search(r"\s*[(（][^()（）]*[)）]$", s) and len(s) > limit:
        s = re.sub(r"\s*[(（][^()（）]*[)）]$", "", s).strip()
    if len(s) <= limit and len(s) >= (3 if loc.cjk else 5):
        return s
    clauses = _clauses(t, loc)
    if prefer_day:
        day = next((c for c in clauses if _weekday(c, loc) and len(c) <= limit), "")
        if day:
            return day[0].upper() + day[1:]
    if clauses and (3 if loc.cjk else 5) <= len(clauses[0]) <= limit:
        return clauses[0]
    m = TIME_RANGE.search(t)
    if m:
        return m.group(0)
    return t


def brief_en(key: str, value: str | None, loc: LC.Locale = EN) -> dict:
    """{main, sub, more} for a key-fact tile or a list cell (the facts card prints the whole value)."""
    v = squash_ws(value) if "\n" not in str(value or "") else str(value).strip()
    if not v:
        return {"main": "", "sub": "", "more": False}
    timeish = key in ("usetime", "usetime_restdate", "openperiod", "checkin", "checkout")
    if key == "menu":
        if loc.cjk:
            items = [x.strip() for x in re.split(r"[、，,]\s*(?!\d{3}(?!\d))|\n", v) if x.strip()]
            sep, room = loc.list_sep, 16
        else:
            items = [x.strip() for x in re.split(r",(?!(?<=\d,)\d{3}(?!\d))\s*|\n", v) if x.strip()]   # never at a thousands comma
            sep, room = ", ", 32
        main, k = items[0], 1
        while k < len(items) and len(main) + len(sep) + len(items[k]) <= room:
            main += sep + items[k]
            k += 1
        return {"main": cap(main), "sub": "", "more": k < len(items)}
    segs = _segments(v, timeish)
    if not segs:
        return {"main": squash_ws(v), "sub": "", "more": False}
    limit = BRIEF_MAX // 2 if loc.cjk else BRIEF_MAX
    if len(segs) == 1 and len(segs[0][1]) <= limit and not segs[0][0]:
        return {"main": segs[0][1], "sub": "", "more": False}
    head, first = segs[0]
    main = _reduce(first, key == "restdate", loc)
    sub = head
    used = 1
    if not sub and len(segs) > 1 and timeish:
        nxt = _reduce(segs[1][1], False, loc)
        if len(nxt) <= limit:
            sub, used = nxt, 2
    whole = squash_ws(" ".join(f"{h} {t}".strip() for h, t in segs))
    shown = squash_ws(f"{sub} {main}") if head else squash_ws(f"{main} {sub}")
    return {"main": cap(main), "sub": cap(sub),
            "more": used < len(segs) or main != squash_ws(first) or len(shown) < len(whole) - 2}


def cap(text: str) -> str:
    """A tile's main part starts with a capital ('closed on the second Monday' -> 'Closed on …')."""
    return text[:1].upper() + text[1:] if text[:1].islower() else text


def closed_part_en(value: str | None, loc: LC.Locale = EN) -> str:
    """The closed-days part of an hours value ('11:00–20:00 / Closed every Monday' -> 'Closed every Monday')."""
    words = CLOSED_WORDS if loc.code == "en" else CLOSED_BY[loc.code]
    v = squash_ws(value)
    for p in re.split(r"\s+/\s+|\n", str(value or "")):
        if words.search(p) and not TIME_RANGE.search(p):
            return squash_ws(p).rstrip(".。")
    m = re.search(r"[(（]([^()（）]*)[)）]", v)
    if m and words.search(m.group(1)) and not TIME_RANGE.search(m.group(1)):
        return squash_ws(m.group(1))
    if loc.code == "en":
        m = re.search(r"[,.;]\s*((?:closed|open all year|open every day)[^.;]*)", v, re.I)
        if m:
            return squash_ws(m.group(1))
    else:
        for c in re.split(r"[,.;、，；。]\s*", v):
            if words.search(c) and not TIME_RANGE.search(c):
                return squash_ws(c)
    return ""


def _load(path: Path, default):
    return json.loads(path.read_text("utf-8")) if path.exists() else default


def add_filters(env) -> None:
    """Jinja filters of the English helpers (registered by build.make_env; the templates of every version use the
    locale's own methods: loc.md, loc.dist, E.sup …)."""
    env.filters["en_date"] = en_date
    env.filters["en_md"] = en_md
    env.filters["edist"] = dist_en
    env.filters["first_sentence_en"] = lambda t: (sentences_en(t) or [""])[0]
    # footnote superscripts: the visible number plus a hidden ' — source n' (fact rows) / ' source n' (chapters)
    env.filters["esup"] = lambda n: Markup(f'<sup class="fn"><span class="vh"> — source </span>{n}</sup>') if n else ""
    env.filters["ecsup"] = lambda n: Markup(f'<sup class="fn"><span class="vh"> source </span>{n}</sup>') if n else ""


def title_list(tail: str, loc: LC.Locale = EN) -> list[str]:
    """'jjamppong, kkotgejang (marinated blue crab), bakdae … and bakeries' → ['Jjamppong', 'Kkotgejang', 'Bakdae', …]:
    the items of a guide title's list, glosses in brackets dropped, each capitalised (the home bento's pills)."""
    if loc.code == "en":
        return en_title_list(tail)
    t = re.sub(r"\s*[(（][^)）]*[)）]", "", squash_ws(tail))
    conj = {"de": "und", "fr": "et", "es": "y", "ru": "и"}.get(loc.code)
    rx = r"[、，,]\s*" + (rf"|\s+{conj}\s+" if conj else "")
    return [w[:1].upper() + w[1:] for w in (w.strip() for w in re.split(rx, t)) if w]


def en_title_list(tail: str) -> list[str]:
    words = re.split(r",\s*(?:and\s+)?|\s+and\s+", re.sub(r"\s*\([^)]*\)", "", squash_ws(tail)))
    return [w[:1].upper() + w[1:] for w in (w.strip() for w in words) if w]


# ---------------------------------------------------------------------------------------------- UI words
class UIText:
    """The words one version's pages print. English: pipeline/intl_text.EN; every other version: its
    data/<region>/<code>/strings.json 'chrome.<key>' rows (translations of the English, tools/en_content.py).
    In templates: {{ t.key }} and {{ t.f('key', name=…) }} / {{ t.n('key', count) }} give markup (English is
    written in this repository, so it is printed as it is; a translation is escaped); in Python t.s() / t.sn() give
    plain text (escaped where the page prints it). Plural keys have one form per CLDR category (loc.plural)."""

    def __init__(self, loc: LC.Locale, strings: dict[str, str]):
        self.loc = loc
        if loc.code == "en":
            self._w = intl_text.flat(intl_text.EN)
        else:
            self._w = {k[len("chrome."):]: v for k, v in strings.items() if k.startswith("chrome.") and v}
        self.missing = [k for k in intl_text.keys_for(loc) if not self._w.get(k)]

    def _raw(self, key: str, count: int | None = None) -> str:
        if count is not None:
            return self._w.get(f"{key}.{self.loc.plural_form(count)}", "")
        return self._w.get(key, "")

    def _m(self, v: str) -> Markup:
        return Markup(v) if self.loc.code == "en" else Markup(escape(v))

    def __getattr__(self, key: str) -> Markup:
        if key.startswith("_"):
            raise AttributeError(key)
        return self._m(self._raw(key))

    def s(self, key: str, **kw) -> str:
        v = self._raw(key)
        return v.format(**kw) if kw else v

    def sn(self, key: str, count: int, **kw) -> str:
        kw.setdefault("n", count)
        return self._raw(key, count).format(**kw)

    def f(self, key: str, **kw) -> Markup:
        return self._m(self._raw(key)).format(**kw)

    def n(self, key: str, count: int, **kw) -> Markup:
        kw.setdefault("n", count)
        return self._m(self._raw(key, count)).format(**kw)

    def printf(self, key: str) -> str:
        """A '{n}' text as a printf pattern for the shared macros ('+ {n} more' -> '+ %d more')."""
        return self._raw(key).replace("%", "%%").replace("{n}", "%d")

    def map_words(self) -> str:
        """The words map.js writes, for a version other than English and Korean (data-words on the map box)."""
        return json.dumps({"in": self.s("map_zoom_in"), "out": self.s("map_zoom_out"), "all": self.s("map_whole_course"),
                           "fail": self.s("map_fail"), "off": self.s("map_off")}, ensure_ascii=False)


# ---------------------------------------------------------------------------------------------- the site
class Site:
    """One language version: its records that are current, their slugs and paths, the ko ↔ version pairs, and the
    page view models."""

    def __init__(self, S, data_dir: Path, loc: LC.Locale = EN, book: "SlugBook | None" = None):
        self.S, self.loc = S, loc
        ldir = Path(data_dir) / loc.code
        strings = _load(ldir / "strings.json", {}) or {}
        self.strings = {k: no_hangul(squash_ws((v or {}).get(loc.tag))) for k, v in strings.items()}
        self.t = UIText(loc, self.strings)
        recs = {k: _load(ldir / f"{k}.json", {}) or {} for k in ("places", "guides", "courses", "events")}
        hashes = current_hashes(Path(data_dir))
        self.region = (romanize(S.site.get("region", "")) or "Gunsan") if loc.code == "en" else loc.city
        self.stale: dict[str, list[str]] = {k: [] for k in recs}
        self.hashes, self.recs = hashes, recs
        self.home = loc.home
        self.misses: set[str] = set()

        def current(kind: str, key: str) -> dict | None:
            rec, h = recs[kind].get(key), hashes[kind].get(key)
            if not rec or h is None:   # untranslated, or not published (no hash): no page in this language
                return None
            if rec.get("ko_hash") != h:
                self.stale[kind].append(key)
                return None
            return rec

        own = loc.code == "en" or book is None
        # places: slugs from name_en, unique and stable (first translated keeps the plain slug)
        self.places: dict[str, dict] = {}
        for e in S.entities:
            rec = current("places", e["id"])
            if rec:
                self.places[e["id"]] = {"e": e, "rec": rec}
        if own:
            self._slugs(list(self.places.values()), lambda p: p["rec"].get("name_en"), lambda p: p["e"]["id"],
                        lambda p: p["rec"].get("translated_at") or "")
        else:
            for pid, p in self.places.items():
                p["slug"] = book.slug("places", pid)
        for p in self.places.values():
            e = p["e"]
            p["path"] = f"{self.home}places/{p['slug']}/"
            p["url"] = S.abs(p["path"])
            p["name"] = squash_ws(p["rec"].get(loc.name_key)) or self.fallback_name(e["name"])
            p["noindex"] = S.mode == "production" and not e["_index_ok"]
            e.setdefault("_intl", {})[loc.code] = p
            if loc.code == "en":
                e["_en"] = p
        self.guides: dict[str, dict] = {}
        for g in S.guides:
            rec = current("guides", g["id"])
            if rec:
                self.guides[g["id"]] = {"g": g, "rec": rec}
        if own:
            self._slugs(list(self.guides.values()), lambda x: re.split(r":\s", x["rec"].get("title") or "", maxsplit=1)[0],
                        lambda x: x["g"]["id"], lambda x: x["rec"].get("translated_at") or "")
        else:
            for gid, x in self.guides.items():
                x["slug"] = book.slug("guides", gid)
        for x in self.guides.values():
            x["path"] = f"{self.home}guides/{x['slug']}/"
            x["url"] = S.abs(x["path"])
        self.courses: dict[str, dict] = {}
        for c in S.courses:
            rec = current("courses", c["id"])
            if rec:
                self.courses[c["id"]] = {"c": c, "rec": rec}
        if own:
            self._slugs(list(self.courses.values()), lambda x: x["rec"].get("name"), lambda x: x["c"]["id"],
                        lambda x: x["rec"].get("translated_at") or "")
        else:
            for cid, x in self.courses.items():
                x["slug"] = book.slug("courses", cid)
        for x in self.courses.values():
            x["path"] = f"{self.home}courses/{x['slug']}/"
            x["url"] = S.abs(x["path"])
        # event series exactly as tools/en_content.py prepared them (published records), keyed by the series slug
        self.series: list[dict] = []
        events_all = getattr(S, "events_all", []) or []
        for sr in event_series(events_all):
            rec = current("events", sr["slug"])
            if rec:
                self.series.append({"sr": sr, "rec": rec, "slug": sr["slug"]})
        if own:
            self._slugs(self.series, lambda x: x["rec"].get("series_name"), lambda x: x["slug"],
                        lambda x: x["rec"].get("translated_at") or "")
        else:
            for x in self.series:
                x["slug_en"] = book.slug("events", x["slug"])
        for x in self.series:
            x["anchor"] = x.pop("slug_en", None) or x["slug"]
        self.by_kind = {k: [p for p in self.places.values() if p["e"].get("kind") == k] for k in KINDS}
        self.guide_by_id = {gid: x for gid, x in self.guides.items()}
        self.place_by_ko_slug = {p["e"]["slug"]: p for p in self.places.values()}
        # ko ↔ version pairs (both pages are built)
        pairs: dict[str, str] = {}
        if self.places:
            pairs["/"] = self.home
            pairs["/about/"] = f"{self.home}about/"
            for kind, cfg in LIST_PAGES.items():
                if self.by_kind[kind] and S.lists.get(kind):
                    pairs[cfg["ko"]] = self.home + cfg["seg"]
            for p in self.places.values():
                pairs[p["e"]["_path"]] = p["path"]
            if self.guides:
                pairs["/guides/"] = f"{self.home}guides/"
            for x in self.guides.values():
                pairs[x["g"]["_path"]] = x["path"]
            if self.courses:
                pairs["/courses/"] = f"{self.home}courses/"
            for x in self.courses.values():
                pairs[x["c"]["_path"]] = x["path"]
            if self.series and S.events:
                pairs["/events/"] = f"{self.home}events/"
        self.ko2en = pairs
        self.en2ko = {v: k for k, v in pairs.items()}
        # a Korean event page has no twin: its link opens that series on <home>events/
        self.event_links = {}
        by_slug = {x["slug"]: x for x in self.series}
        for sr in getattr(S, "series", []) or []:
            x = by_slug.get(sr["slug"])
            if x:
                self.event_links[sr["_path"]] = f"{self.home}events/#{x['anchor']}"
        self._type_map()

    # ---- strings and labels
    def T(self, key: str, default: str = "", track: bool = False) -> str:
        """A label from strings.json. track: a label whose fallback is its key (Latin on a page of another script),
        so a missing one is listed (build stats, a validate warning)."""
        v = self.strings.get(key)
        if not v and track and self.loc.code != "en":
            self.misses.add(key)
        return v or default

    def fallback_name(self, ko: str) -> str:
        """A name with no translated form: Revised Romanization (Kontsevich Cyrillic in Russian)."""
        return LC.kontsevich(ko) if self.loc.code == "ru" else romanize(ko)

    def area(self, area: str | None) -> str:
        return area_en(area) if self.loc.code == "en" else LC.area_name(area, self.loc.code)

    def first_sentence(self, text: str | None) -> str:
        return (sentences(text, self.loc) or [""])[0]

    def lists(self) -> dict[str, dict]:
        """The three list pages of this version: path, Korean counterpart, nav label, H1, <title>, hub guide."""
        t, r = self.t, self.region
        return {kind: {"path": self.home + c["seg"], "ko": c["ko"], "hub": c["hub"], "kind": kind,
                       "nav": t.s(f"nav_{kind}"), "h1": t.s(f"h1_{kind}", r=r)} for kind, c in LIST_PAGES.items()}

    def nav(self) -> list[tuple[str, str]]:
        return [(self.t.s(k), self.home + seg) for k, seg in NAV_KEYS]

    def current_nav(self, page_kind: str) -> str:
        seg = CURRENT.get(page_kind)
        return self.home + seg if seg else ""

    def _slugs(self, items: list[dict], name, ident, translated) -> None:
        """x['slug'] (x['slug_en'] for event anchors, which keep x['slug'] = the Korean series slug)."""
        field = "slug_en" if items and "sr" in items[0] else "slug"
        base = {id(x): en_slug(name(x)) for x in items}
        groups: dict[str, list] = {}
        for x in items:
            groups.setdefault(base[id(x)], []).append(x)
        for b, xs in groups.items():
            xs.sort(key=lambda x: (translated(x), ident(x)))
            for i, x in enumerate(xs):
                tail = re.sub(r"\D", "", ident(x))[-6:] or str(i + 1)
                x[field] = b if i == 0 else f"{b}-{tail}"

    def _type_map(self) -> None:
        from . import build as B
        S, T = self.S, self.T
        m: dict[str, str] = {}
        for cat in {squash_ws(e.get("category")) for e in S.entities_all}:
            if cat and T(f"category:{cat}"):
                m[cat] = T(f"category:{cat}")
        for k, v in present.STAY_TYPE.items():
            if v and T(f"STAY_TYPE.{k}"):
                m[v] = T(f"STAY_TYPE.{k}")
        for k, v in present.FOOD_TYPE.items():
            if v and T(f"FOOD_TYPE.{k}"):
                m[v] = T(f"FOOD_TYPE.{k}")
        for k, v in present.ATTR_TYPE.items():
            if v and T(f"ATTR_TYPE.{k}"):
                m[v] = T(f"ATTR_TYPE.{k}")
        for i, (name, _) in enumerate(B.ATTRACTION_GROUPS):
            if T(f"ATTRACTION_GROUPS.{i}"):
                m[name] = T(f"ATTRACTION_GROUPS.{i}")
        for t in S.themes:
            if T(f"theme.{t['slug']}.name"):
                m[t["name"]] = T(f"theme.{t['slug']}.name")
        self.type_en = m
        self.region_en = {name: T(f"REGIONS.{i}") for i, (name, _) in enumerate(present.REGIONS) if T(f"REGIONS.{i}")}
        self.region_en[present.FAR_LABEL] = T("FAR_LABEL")
        self.region_en[present.NONE_LABEL] = T("NONE_LABEL")

    def kind_label(self, kind: str) -> str:
        return self.T(f"KIND_LABELS.{kind}", kind, track=True)

    def type_label(self, e: dict) -> str:
        return self.type_en.get(e.get("_type") or "") or self.kind_label(e.get("kind", "attraction"))

    def fact_label(self, key: str) -> str:
        return self.T(f"FACT_LABELS.{key}", track=True) or key

    def provider(self, ko: str | None) -> str:
        """A source's name in this language (strings provider:*), else its short name; never Korean script."""
        k = squash_ws(ko)
        if not k:
            return ""
        short = SHORT_PROVIDER.get(present.slot_provider(k))
        return self.T(f"provider:{k}") or (self.t.s(short) if short else "") or no_hangul(k) or self.t.s("source")

    def short_provider(self, ko: str | None) -> str:
        k = squash_ws(ko)
        short = SHORT_PROVIDER.get(present.slot_provider(k))
        return (self.t.s(short) if short else "") or self.provider(k)

    def event_source(self, rec: dict, ko: str | None) -> str:
        k = squash_ws(ko)
        return no_hangul(squash_ws((rec.get("sources") or {}).get(k))) or self.provider(k)

    def lic(self, code: str) -> str:
        return self.T(f"LIC.{code}") or code

    def designations(self, e: dict) -> list[dict]:
        """The official designations the Korean page shows (schema.designations), in this language: {type, label,
        source_name, url, checked_at}. The label and the list's name come from strings.json (designation:<label>,
        designation_source:<list name>); one without both is left out (never Korean script on these pages) and
        pipeline.validate reports it."""
        out = []
        for d in designations(e):
            label = self.T(f"designation:{d['label']}")
            src = self.T(f"designation_source:{squash_ws(d['source_name'])}")
            if label and src:
                out.append({"type": d["type"], "label": label, "source_name": src, "url": d["url"],
                            "checked_at": d["checked_at"]})
        return out

    # ---- pairs (this version's own; Intl.alternates / Intl.menu combine every version's)
    def en_link(self, ko_path: str) -> str:
        """This version's page for a Korean page: its twin, the series on <home>events/, else <home>."""
        return self.ko2en.get(ko_path) or self.event_links.get(ko_path) or self.home

    def ko_link(self, en_path: str) -> str:
        return self.en2ko.get(en_path) or "/"

    def place_href(self, slug: str | None) -> str:
        p = self.place_by_ko_slug.get(slug or "")
        return p["path"] if p else ""

    def own(self, e: dict | None) -> dict | None:
        """This version's page record of a Korean place (None when it has no current page here)."""
        return ((e or {}).get("_intl") or {}).get(self.loc.code)

    # ---- photos
    def photos(self, p: dict) -> list[dict]:
        """The place's licensed photos with alt text in this language, credit and licence label."""
        out = []
        phs = p["e"].get("_photos") or []
        kto = self.t.s("kto")
        for i, ph in enumerate(phs, 1):
            alt = self.t.s("photo_alt", name=p["name"], i=i) if len(phs) > 1 else p["name"]
            out.append({**ph, "alt": alt, "name": p["name"], "credit": kto,
                        "lic": self.lic("KOGL-1" if ph["type"] == 1 else "KOGL-3")})
        return out

    # ---- key facts (the first-screen tiles and card rows)
    def slot_label(self, e: dict, name: str, v: dict | None = None) -> str:
        if name == "parking" and v and v.get("src_key") == "parking_seats":
            return self.T("CONTEST_LABEL.parking_seats", self.t.s("parking_seats"))
        if name == "parking" and v and v.get("src_key") == "parkingfee":
            return self.fact_label("parkingfee")
        return self.T(SLOT_STRING[name], name, track=True)

    def slot(self, p: dict, name: str) -> dict | None:
        """One key-fact slot from the record, following the Korean slot (present.slot_value): which field it reads,
        whether two sources differ. None when the Korean slot is empty; {'skip': True} when the translated value
        cannot be split the way the Korean was (a closed day inside an hours value)."""
        e, facts, loc = p["e"], p["rec"].get("facts") or {}, self.loc
        v = present.slot_value(e, name)
        if not v:
            return None
        label = self.slot_label(e, name, v)
        base = {"key": name, "src_key": v["src_key"], "label": label, "sub": "", "more": False, "closed": False,
                "conflict": False, "vals": [], "tel": "", "date": v.get("date") or "",
                "provider": self.short_provider(present.src_of(e, v["src_key"])["provider"]), "missing": False}
        f = facts.get(v["src_key"]) or {}
        if name == "tel":
            if v.get("tel"):
                main = extract_phones(v["main"])[0] if extract_phones(v["main"]) else ""
                return {**base, "main": main, "tel": v["tel"]} if main else None
            own = (extract_phones(f.get("value")) or [""])[0]
            vals = [{"provider": base["provider"], "main": own, "sub": "", "closed": False}] if own else []
            for a in f.get("alternatives") or []:
                ph = (extract_phones(a.get("value")) or [""])[0]
                if ph and ph != own:
                    vals.append({"provider": self.short_provider(a.get("provider")), "main": ph, "sub": "", "closed": False})
            if len(vals) > 1:
                return {**base, "main": own, "conflict": True, "vals": vals}
            return {**base, "main": own, "tel": re.sub(r"\D", "", own)} if own else None
        if not f.get("value") and not f.get("alternatives"):
            return None
        if name == "closed" and v["src_key"] != "restdate":
            part = closed_part_en(f.get("value"), loc)
            if not part:
                return {"skip": True}
            b = {"main": cap(part), "sub": "", "more": True}
            alt_b = [{"main": cap(closed_part_en(a.get("value"), loc)), "sub": "", "more": True}
                     for a in f.get("alternatives") or []]
        elif name == "rooms":
            r = squash_ws(f.get("value"))
            b = {"main": self.t.sn("rooms_n", int(r), n=r) if r.isdigit() else r, "sub": "", "more": False}
            alt_b = []
        else:
            b = brief_en(v["src_key"], f.get("value"), loc)
            alt_b = [brief_en(v["src_key"], a.get("value"), loc) for a in f.get("alternatives") or []]
        out = {**base, **b, "closed": v.get("closed", False)}
        if v.get("conflict") and f.get("alternatives"):
            ko_vals = v.get("vals") or []
            vals = [{"provider": base["provider"], **b, "closed": v.get("closed", False)}] if b.get("main") else []
            for i, (a, ab) in enumerate(zip(f.get("alternatives") or [], alt_b)):
                if ab.get("main"):
                    closed = (ko_vals[i + 1].get("closed", False) if i + 1 < len(ko_vals) else False)
                    vals.append({"provider": self.short_provider(a.get("provider")), **ab, "closed": closed})
            if len(vals) > 1:
                out.update(conflict=True, vals=vals)
        if not out.get("main") and not out["vals"]:
            return None
        return out

    def key_facts(self, p: dict, mode: str = "hero") -> dict:
        """present.key_facts in this language: the kind's slots in fixed order; hero mode lists a missing slot
        once ('Not listed: …'), card mode keeps it in its place."""
        e = p["e"]
        kind = e.get("kind") if e.get("kind") in present.HERO_SLOTS else "attraction"
        names = (present.HERO_SLOTS if mode == "hero" else present.KF_CARD_SLOTS)[kind]
        slots, missing = [], []
        for n in names:
            s = self.slot(p, n)
            if s and s.get("skip"):
                continue
            if s:
                slots.append(s)
            else:
                missing.append(self.slot_label(e, n))
                if mode != "hero":
                    slots.append({"key": n, "label": self.slot_label(e, n), "main": "", "sub": "", "more": False,
                                  "closed": False, "conflict": False, "vals": [], "missing": True, "tel": ""})
        dates = [s["date"] for s in slots if s.get("date")]
        provs: list[str] = []
        for s in slots:
            for pr in [s.get("provider")] + [v["provider"] for v in s.get("vals") or []]:
                if pr and pr not in provs:
                    provs.append(pr)
        tel = next((s for s in slots if s["key"] == "tel" and s.get("tel")), None)
        return {"slots": slots, "missing": missing, "date": min(dates) if dates else "", "providers": provs,
                "conflict": any(s.get("conflict") for s in slots), "tel": (tel["main"], tel["tel"]) if tel else ("", "")}

    # ---- facts card
    def fact_rows(self, p: dict, keys, notes: "present.Notes", tel: tuple = ("", "")) -> list[dict]:
        """Every fact in `keys` order, whole, with its source as a footnote; both values (each with its source) and
        the record's note when two sources differ; 'also' values as 'or …'."""
        e, facts = p["e"], p["rec"].get("facts") or {}
        ko = e.get("facts") or {}
        out, called = [], False
        for k in keys:
            label = self.fact_label(k)
            if k in ("homepage", "reservationurl"):
                url = link_url(ko.get(k))
                if not url:
                    continue
                text = web_text(url)
                text = text if not HANGUL.search(text) else url_domain(url)
                src = present.src_of(e, k)
                n = notes.ref({**src, "provider": self.provider(src["provider"]), "confirmed_by": ""}, label)
                out.append({"key": k, "label": label, "text": text, "url": url, "n": n, "conflict": False,
                            "blocks": [], "alts": [], "note": "", "tel": None, "wide": False})
                continue
            f = facts.get(k)
            if not f:
                continue
            value = f.get("value") or ""
            src = present.src_of(e, k)
            conf = squash_ws(src.get("confirmed_by"))
            conf = self.provider(re.sub(r"\s+\d{4}-\d{2}-\d{2}$", "", conf)) if conf else ""
            row = {"key": k, "label": label, "text": value, "url": "", "n": None, "conflict": False, "blocks": [],
                   "alts": [], "note": "", "tel": None, "wide": "\n" in value or len(value) > (11 if self.loc.cjk else 22),
                   "provider": self.provider(src["provider"]), "checked_at": src["checked_at"]}
            if value:
                row["n"] = notes.ref({**src, "provider": row["provider"], "confirmed_by": conf}, label)
            ko_alts = present.contested(e, k)
            for i, a in enumerate(f.get("alternatives") or []):
                ka = ko_alts[i] if i < len(ko_alts) else {}
                a_src = {"provider": self.provider(a.get("provider")), "checked_at": squash_ws(ka.get("checked_at")),
                         "url": ka.get("url") or "", "confirmed_by": ""}
                row["blocks"].append({"provider": a_src["provider"], "checked_at": a_src["checked_at"],
                                      "text": a.get("value") or "", "n": notes.ref(a_src, label + " (other value)")})
            ko_also = [a for a in present.alternatives(e, k) if a.get("relation") == "also"]
            for i, a in enumerate(f.get("also") or []):
                ka = ko_also[i] if i < len(ko_also) else {}
                a_src = {"provider": self.provider(a.get("provider")), "checked_at": squash_ws(ka.get("checked_at")),
                         "url": ka.get("url") or "", "confirmed_by": ""}
                row["alts"].append({"provider": a_src["provider"], "text": a.get("value") or "",
                                    "n": notes.ref(a_src, label + " (also)")})
            if row["blocks"]:
                row["conflict"], row["wide"] = True, True
                if value:
                    row["blocks"].insert(0, {"provider": row["provider"], "checked_at": row["checked_at"],
                                             "text": value, "n": row["n"]})
                row["note"] = squash_ws(f.get("note")) or (CONFLICT_NOTE if self.loc.code == "en" else self.loc.conflict)
                if not called and tel[0]:
                    row["tel"], called = tel, True
            out.append(row)
        return out

    def missing_facts(self, p: dict) -> list[str]:
        """Labels of the kind's key facts no source gives (one 'Not listed: …' line under the facts)."""
        e, facts = p["e"], p["rec"].get("facts") or {}
        kind = e.get("kind", "attraction")
        keys = KEY_FACTS_BY_CATEGORY.get(e.get("category"), KEY_FACTS.get(kind, ()))
        out = []
        for k in keys:
            if any(facts.get(x) for x in (k, *FACT_ALIASES.get(k, ()))):
                continue
            if k == "parking" and facts.get("parkingfee"):
                continue
            out.append(self.fact_label(k))
        return out

    # ---- chapters with their own sources (details, FAQ)
    def chapter_notes(self, e: dict):
        S = self.S
        from .build import source_labels
        labels = {u: self.provider(n) for u, n in source_labels(e).items()}
        site = self

        class Notes:
            def __init__(self):
                self.items: list[dict] = []

            def ref(self, source: str | None):
                s = squash_ws(source)
                if not s:
                    return None
                if s.startswith("http"):
                    name = labels.get(s) or (site.t.s("kto_visitkorea") if "visitkorea" in s
                                             else site.provider((S.site.get("source") or {}).get("name"))
                                             if "gunsan.go.kr" in s else url_domain(s))
                    item = {"url": s, "name": name}
                else:
                    item = {"url": "", "name": site.provider(s)}
                if item not in self.items:
                    self.items.append(item)
                return self.items.index(item) + 1
        return Notes()

    # ---- routes
    def route(self, p: dict) -> dict:
        """Front row: Google Maps (by coordinates, else the Korean name + 군산), Naver Map, Kakao Map (the Korean
        page's exact links); the rest under 'Other maps'. Same data-track / data-provider values as the Korean."""
        e, S, t = p["e"], self.S, self.t
        geo = e["_geo"] or {}
        mid = e.get("map_ids") or {}
        links = build_links(e["name"], geo.get("lat"), geo.get("lng"), region=S.site.get("region", ""),
                            address=(e.get("facts") or {}).get("address", ""), naver_place_id=mid.get("naver_place_id", ""),
                            google_place_id=mid.get("google_place_id", ""),
                            tmap_scheme=S.site.get("tmap_scheme", DEFAULT_TMAP_SCHEME),
                            kakao_place_id=mid.get("kakao_place_id", ""))
        by = {l["key"]: l for l in links}
        region = S.site.get("region", "")
        if geo:
            google = {"key": "google", "url": f"https://www.google.com/maps/search/?api=1&query={geo['lat']},{geo['lng']}",
                      "precise": True}
        else:
            q = e["name"] if region and region in e["name"] else f"{e['name']} {region}".strip()
            google = {"key": "google", "url": "https://www.google.com/maps/search/?" + urlencode({"api": "1", "query": q}),
                      "precise": False}
        front = [{**google, "label": t.s("map_google"), "role": "map"},
                 {**by["naver"], "label": t.s("map_naver")}, {**by["kakao"], "label": t.s("map_kakao")}]
        names = {"kakao_route": t.s("route_kakao"), "google_route": t.s("route_google"), "tmap": t.s("route_tmap")}
        rest = [{**by[k], "label": lab} for k, lab in names.items() if k in by]
        for l in front + rest:
            l["track"] = "route_click" if l["role"] == "route" else "map_click"
        cta = by.get("google_route") or google
        return {"front": front, "rest": rest,
                "cta": {"url": cta["url"], "label": t.s("directions") if cta.get("role") == "route" else t.s("sec_map"),
                        "ext": True, "track": "route_click" if cta.get("role") == "route" else "map_click",
                        "provider": cta["key"], "place": e["id"]}}

    # ---- place page
    def place_vm(self, p: dict) -> dict:
        S, e, rec, loc = self.S, p["e"], p["rec"], self.loc
        kind = e.get("kind", "attraction")
        tel_text, tel = present.settled_phone(e)
        tel = (tel_text, tel) if tel_text and not HANGUL.search(tel_text) else ("", "")
        notes = present.Notes()
        facts = rec.get("facts") or {}
        practical_keys = list(present.PRACTICAL[kind])
        shown = set(practical_keys)
        known = set(present.MORE) | set(present.FIT) | shown
        more_keys = [k for k in present.MORE if k not in shown] + [k for k in facts if k not in known]
        practical = self.fact_rows(p, practical_keys, notes, tel)
        more = self.fact_rows(p, more_keys, notes, tel)
        fit = self.fact_rows(p, present.FIT, notes, tel)
        summary = squash_ws(rec.get("summary"))
        ss = sentences(summary, loc)
        photos = self.photos(p)
        lead = photos[0] if photos else None
        details_n, faq_n = self.chapter_notes(e), self.chapter_notes(e)
        details = [{"heading": squash_ws(d.get("heading")), "text": squash_ws(d.get("text")), "n": details_n.ref(d.get("source"))}
                   for d in rec.get("details") or [] if squash_ws(d.get("text"))]
        faqs = [{"q": squash_ws(f.get("q")), "a": squash_ws(f.get("a")), "n": faq_n.ref(f.get("source"))}
                for f in rec.get("faq") or [] if squash_ws(f.get("q")) and squash_ws(f.get("a"))]
        # nearby places that have pages in this version (TourAPI nearby list, straight-line distance)
        near = []
        for n in e.get("nearby") or []:
            t = S.ent_by_slug.get(n.get("internal_slug") or "") or S.ent_by_cid.get(str(n.get("contentid")))
            tp = self.own(t)
            if not tp:
                continue
            near.append({"name": tp["name"], "href": tp["path"], "kind": t.get("kind"), "type": self.type_label(t),
                         "m": n.get("distance_m") or 0, "d": loc.dist(n.get("distance_m")), "geo": t["_geo"],
                         "track": {"stay": "stay_click", "food": "food_click"}.get(t.get("kind"), "nearby_click")})
        near.sort(key=lambda x: x["m"])
        points = None
        if e["_geo"]:
            points = {"self": {"lat": e["_geo"]["lat"], "lng": e["_geo"]["lng"], "name": p["name"]},
                      "near": [{"lat": n["geo"]["lat"], "lng": n["geo"]["lng"], "name": n["name"], "d": n["d"],
                                "url": n["href"], "kind": n["kind"]} for n in near if n["geo"]][:12],
                      "anchors": []}
        courses = [self.courses[c["id"]] for c in e["_courses"] if c["id"] in self.courses]
        guides = [self.guides[g["id"]] for g in e["_guides"] if g["id"] in self.guides]
        events = [x for x in self.series if e["slug"] in self._series_places(x)]
        official = e.get("official") or {}
        orig = e.get("original") or {}
        list_cfg = self.lists()[kind]
        kicker = [(list_cfg["nav"], list_cfg["path"])]
        tl = self.type_label(e)
        if tl and tl != self.kind_label(kind):
            kicker.append((tl, ""))
        facts_checked = e.get("_facts_checked") or ""
        k = self.key_facts(p, "hero")
        own_home = web_url(official.get("homepage")) or web_url((e.get("facts") or {}).get("homepage"))
        return {
            "p": p, "e": e, "rec": rec, "kind": kind, "name": p["name"], "name_ko": e["name"], "kicker": kicker,
            "area": self.area(e.get("_area")), "lede": ss[0] if ss else "", "story": ss[1:], "summary": summary,
            "kf": k, "route": self.route(p), "photos": photos,
            # official designations (Site.designations): chips under the answer, the 'Designations' row of the facts card
            "designations": self.designations(e),
            "hero_k1": lead if lead and lead["type"] == 1 else None,
            "hero_k3": lead if lead and lead["type"] != 1 else None,
            "thumbs": [{"url": ph["th"]["url"], "w": ph["th"]["w"], "h": ph["th"]["h"], "alt": ph["alt"], "type": ph["type"]}
                       for ph in photos[:6] if ph.get("th") and ph["th"].get("w")],
            "practical": practical, "more": more, "fit": fit, "notes": notes.items, "missing": self.missing_facts(p),
            "address_ko": display_address((e.get("facts") or {}).get("address")),
            "details": details, "detail_notes": details_n.items, "faqs": faqs, "faq_notes": faq_n.items,
            "near_sights": [n for n in near if n["kind"] == "attraction"][:8],
            "near_biz": [n for n in near if n["kind"] in ("stay", "food")][:8],
            "nearby_source": e.get("nearby_source") or {}, "points": points,
            "courses": courses, "guides": guides, "events": events,
            "orig_url": orig.get("source_url") or official.get("source_url") or "",
            "orig_name": self.provider(orig.get("source_name") or (S.site.get("source") or {}).get("name")),
            "visitkorea": official.get("visitkorea_url", ""), "homepage": own_home if own_home and not HANGUL.search(own_home) else "",
            "facts_checked": facts_checked, "reviewed_at": e.get("reviewed_at") or "",
            "translated_at": rec.get("translated_at") or "", "ko_path": e["_path"],
            "lics": list(dict.fromkeys(ph["lic"] for ph in photos)),
        }

    def _series_places(self, x: dict) -> list[str]:
        out: list[str] = []
        for ev in x["sr"]["editions"]:
            for s in [*(ev.get("place_slugs") or []), ev.get("place_slug")]:
                if s and s not in out:
                    out.append(s)
        return out

    def card(self, p: dict, photo: dict | None = None) -> dict:
        e = p["e"]
        phs = self.photos(p)
        if photo is not None:
            photo = next((x for x in phs if x["url"] == photo.get("url")), phs[0] if phs else None)
        else:
            photo = phs[0] if phs else None
        return {"p": p, "e": e, "id": e["id"], "kind": e.get("kind", "attraction"), "name": p["name"], "path": p["path"],
                "type": self.type_label(e), "area": self.area(e.get("_area")), "photo": photo,
                "kf": self.key_facts(p, "card")}

    # ---- lists
    def list_vm(self, kind: str) -> dict:
        """The Korean list's records (present.list_vm: grouped by 권역, same order) that have pages here."""
        S = self.S
        L = present.list_vm(S, kind)
        groups, n_photo, lics = [], 0, set()
        points = []
        for g in L["groups"]:
            recs = []
            for it in g["recs"]:
                p = self.own(it["e"])
                if not p:
                    continue
                cells = []
                for key, _ in present.KF_LIST_COLS[kind]:
                    s = self.slot(p, key)
                    label = self.slot_label(p["e"], key, s if s and not s.get("skip") else None)
                    if s and s.get("skip"):
                        s = None
                    cells.append(s or {"key": key, "label": label, "main": "", "missing": True, "conflict": False,
                                       "vals": [], "sub": "", "more": False, "closed": False, "tel": ""})
                    if s:
                        cells[-1]["label"] = label
                th = present.thumb(p["e"]["_photos"][0]) if p["e"].get("_photos") else None
                if th:
                    n_photo += 1
                    lics.add(th["type"])
                rid = f"r{it['i']}"
                recs.append({"p": p, "e": p["e"], "id": rid, "name": p["name"], "path": p["path"],
                             "type": self.type_label(p["e"]), "area": self.area(p["e"].get("_area")), "photo": th,
                             "cells": cells})
                if p["e"]["_geo"]:
                    points.append({"lat": p["e"]["_geo"]["lat"], "lng": p["e"]["_geo"]["lng"], "name": p["name"],
                                   "url": p["path"], "id": rid, "kind": kind, "r": it["region"]})
            if recs:
                name = self.region_en.get(g["name"]) or g["name"]
                groups.append({"name": name, "id": "g-" + (en_slug(name) if self.loc.code == "en" else
                                                           en_slug(romanize(g["name"]))), "recs": recs})
        count = sum(len(g["recs"]) for g in groups)
        cols = [(key, self.slot_label({"kind": kind}, key)) for key, _ in present.KF_LIST_COLS[kind]]
        return {"kind": kind, "groups": groups, "count": count, "cols": cols, "points": points, "n_geo": len(points),
                "map_open": len(points) >= 0.3 * max(1, count), "n_photo": n_photo,
                "lics": [self.lic("KOGL-1") if t == 1 else self.lic("KOGL-3") for t in sorted(lics)]}

    # ---- guides
    def guide_vm(self, x: dict) -> dict:
        S, g, rec, loc = self.S, x["g"], x["rec"], self.loc
        ss = sentences(rec.get("summary"), loc)
        items = []
        for i, it in enumerate(rec.get("items") or [], 1):
            p = self.place_by_ko_slug.get(it.get("place_slug") or "")
            t = S.ent_by_slug.get(it.get("place_slug") or "")
            name = p["name"] if p else (self.fallback_name(t["name"]) if t else "")
            ko_name = (t or {}).get("name", "")
            if not name:
                rows = (self.recs["places"] or {})
                name = next((squash_ws(r.get(loc.name_key)) for r in rows.values() if r.get("slug") == it.get("place_slug")), "")
            items.append({"n": i, "p": p, "name": name, "name_ko": ko_name if not p else "", "reason": squash_ws(it.get("reason")),
                          "path": p["path"] if p else "", "kf": self.key_facts(p, "card") if p else None,
                          "type": self.type_label(p["e"]) if p else "", "area": self.area(p["e"].get("_area")) if p else "",
                          "photo": self.photos(p)[0] if p and p["e"].get("_photos") else None})
        pts = [{"lat": it["p"]["e"]["_geo"]["lat"], "lng": it["p"]["e"]["_geo"]["lng"], "name": it["name"],
                "url": it["path"], "n": it["n"], "kind": it["p"]["e"].get("kind"), "id": it["p"]["e"]["slug"]} for it in items
               if it["p"] and it["p"]["e"]["_geo"]]
        # the reading layer (present.rich / guide_sections, the Korean guide's components): the answer line, sentence
        # bullets with figures emphasised and the guide's places linked, mini cards
        uniq = list({it["p"]["e"]["id"]: it["p"] for it in items if it["p"]}.values())
        names = [{"name": p["name"], "path": p["path"], "id": p["e"]["id"]} for p in uniq]
        cards = {}
        for p in uniq:
            ph = self.photos(p)
            cards[p["e"]["id"]] = present.mini_card(p["e"], self.key_facts(p, "card"), p["name"], p["path"],
                                                    self.type_label(p["e"]), self.area(p["e"].get("_area")),
                                                    {**present.thumb(ph[0]), "lic": ph[0]["lic"]} if ph else None)
        heads = [(squash_ws(b.get("heading")), [squash_ws(t) for t in str(b.get("text") or "").split("\n") if t.strip()])
                 for b in rec.get("body") or []]
        split = sentences_en if loc.code == "en" else loc.sentences
        reading = present.guide_reading(ss, heads, names, cards, loc.code, split, len(items))
        cn = self.chapter_notes({})
        faqs = [{"q": squash_ws(f.get("q")), "a": squash_ws(f.get("a")), "n": cn.ref(f.get("source"))}
                for f in rec.get("faq") or [] if squash_ws(f.get("q")) and squash_ws(f.get("a"))]
        sources = [{"name": no_hangul(squash_ws(s.get("name"))) or url_domain(s.get("url")), "url": s.get("url") or ""}
                   for s in rec.get("sources") or [] if s.get("url")]
        return {**reading, "x": x, "g": g, "rec": rec, "label": squash_ws(rec.get("label")), "title": squash_ws(rec.get("title")),
                "summary": squash_ws(rec.get("summary")), "lede": ss[0] if ss else "", "dek": loc.sjoin.join(ss[1:]),
                "body": [{"heading": squash_ws(b.get("heading")), "text": str(b.get("text") or "")} for b in rec.get("body") or []],
                "places": items, "points": pts, "faqs": faqs, "faq_notes": cn.items, "sources": sources,
                "checked": g.get("_page_date") or "", "reviewed_at": g.get("reviewed_at") or "",
                "translated_at": rec.get("translated_at") or ""}

    # ---- courses
    def course_vm(self, x: dict) -> dict:
        S, c, rec = self.S, x["c"], x["rec"]
        cv = S.course_vms.get(c["slug"]) or {}
        stops_en = rec.get("stops") or []
        rows, stops = [], []
        for i, s in enumerate(c.get("stops") or []):
            se = stops_en[i] if i < len(stops_en) else {}
            t = S.ent_by_slug.get(s.get("place_slug") or "")
            kind = present.stop_kind(squash_ws(s.get("name")), t)
            name = squash_ws(se.get("name")) or (self.fallback_name(s.get("name")) if s.get("name") else "")
            note = squash_ws(se.get("note"))
            if kind != "place":
                rows.append({"sep": True, "kind_label": self.T(f"STOP_KIND_LABELS.{kind}", kind.title()), "name": name,
                             "note": note})
                continue
            p = self.own(t)
            st = {"sep": False, "n": len(stops) + 1, "name": name, "note": note, "p": p, "t": t,
                  "path": p["path"] if p else "", "geo": t["_geo"] if t else None,
                  "kf": self.key_facts(p, "card") if p else None, "photo": self.photos(p)[0] if p and t.get("_photos") else None,
                  "type": self.type_label(t) if t else "", "area": self.area((t or {}).get("_area")),
                  "place_name": p["name"] if p else ""}
            stops.append(st)
            rows.append(st)
        ko_stops = cv.get("stops") or []
        for st, ks in zip(stops, ko_stops):   # straight-line legs from the Korean course model (same stops, same order)
            st["next_m"], st["prev_m"] = ks.get("next_m"), ks.get("prev_m")
        s0 = next((s for s in stops if s["geo"]), None)
        first_route = {"n": s0["n"], "name": s0["name"],
                       "url": "https://www.google.com/maps/dir/?" + urlencode({"api": "1", "destination": f"{s0['geo']['lat']},{s0['geo']['lng']}"}),
                       "place": (s0["t"] or {}).get("id", "")} if s0 else None
        # the course map as on the Korean page (present.course_map): numbered as the stop list, only when at least
        # half of the stops have coordinates
        cmap = present.course_map(stops)
        orig = c.get("original") or {}
        # a summary_auto course (the Korean summary is a template sentence) is described the way the Korean page
        # describes it (present.course_lede): computed from the stops' coordinates; a written summary is kept
        summary = squash_ws(rec.get("summary"))
        if c.get("summary_auto") or not summary:
            summary = self.course_lede(stops, cv) or summary
        return {"x": x, "c": c, "rec": rec, "name": squash_ws(rec.get("name")), "group": squash_ws(rec.get("group")),
                "duration": squash_ws(rec.get("duration")), "summary": summary, "rows": rows,
                "stops": stops, "n_places": len(stops), "total": cv.get("total") or 0, "measured": cv.get("measured") or 0,
                "legs_possible": cv.get("legs_possible") or 0, "complete": bool(cv.get("complete")),
                "first": stops[0]["name"] if stops else "", "last": stops[-1]["name"] if stops else "",
                "first_route": first_route, "map": cmap,
                "orig_url": orig.get("source_url") or "",
                "orig_name": self.provider(orig.get("source_name") or (S.site.get("source") or {}).get("name")),
                "collected": orig.get("collected_at") or "", "reviewed_at": c.get("reviewed_at") or "",
                "translated_at": rec.get("translated_at") or ""}

    def course_lede(self, stops: list[dict], cv: dict) -> str:
        """present.course_lede in this language: how many first stops lie within 1 km of the start, and the longest
        leg when every leg is measured (straight lines between stored coordinates); else where the stops start and end."""
        if not stops:
            return ""
        t, loc = self.t, self.loc
        cluster = 1
        if stops[0]["geo"]:
            while cluster < len(stops) and stops[cluster]["geo"] and \
                    present.hav(stops[0]["geo"], stops[cluster]["geo"]) <= 1000:
                cluster += 1
        legs = cv.get("legs") or []
        longest = ""
        if cv.get("complete") and cv.get("measured") and len(legs) == len(stops) - 1:
            i = max(range(len(legs)), key=lambda j: legs[j] or 0)
            if legs[i]:
                longest = t.s("lede_longest", a=stops[i]["name"], b=stops[i + 1]["name"], d=loc.dist(legs[i]))
        near = t.sn("lede_near", cluster) if cluster > 2 else ""
        if near and longest:
            return t.s("lede_both", near=near, longest=longest)
        if near:
            return t.s("lede_one", text=near)
        if longest:
            return t.s("lede_one", text=f"{longest[0].upper()}{longest[1:]}")
        return t.sn("lede_ends", len(stops), a=stops[0]["name"], b=stops[-1]["name"])

    # ---- events
    def events_vm(self) -> dict:
        """Every current series: the newest dated edition's facts (from the record; dates from the Korean), both
        values and the organizer note where sources differ, highlights, the usual timing, earlier editions."""
        from . import build as B
        S, t = self.S, self.t
        out_up, out_past = [], []
        ko_ev = {ev["id"]: ev for ev in getattr(S, "events_all", []) or []}
        note_default = EVENT_CONFLICT_NOTE if self.loc.code == "en" else self.loc.event_conflict
        for x in self.series:
            sr, rec = x["sr"], x["rec"]
            ko = sr["newest"]
            new = rec.get("newest") or {}
            ev = ko_ev.get(new.get("id")) or ko
            alts = rec.get("alternatives") or {}
            src_name = squash_ws(ev.get("source_name"))
            primary = self.event_source(rec, src_name)
            rows = []
            for field, label in (("period_text", "ev_dates"), ("playtime", "ev_time"), ("fee", "ev_fee"),
                                 ("place_name", "ev_venue"), ("address", "ev_address"), ("sponsor", "ev_organizer"),
                                 ("tel", "ev_contact")):
                value = squash_ws(new.get(field))
                a = alts.get("period" if field == "period_text" else field) or {}
                if not value and not a:
                    continue
                row = {"field": field, "label": t.s(label), "value": value, "blocks": [], "note": ""}
                if a.get("values"):
                    row["blocks"] = [{"provider": primary, "value": value}] if value else []
                    for v, pr in zip(a.get("values") or [], a.get("providers") or []):
                        row["blocks"].append({"provider": self.event_source(rec, pr), "value": squash_ws(v)})
                    row["note"] = squash_ws(a.get("note")) or note_default
                rows.append(row)
            last = B.event_last_day(ev) if ev.get("start_date") else ""
            # sources: the names in this language, linked when a Korean record of the series gives the URL
            urls: dict[str, str] = {}
            for r in sr["editions"]:
                if r.get("source_name") and r.get("source_url"):
                    urls.setdefault(squash_ws(r["source_name"]), r["source_url"])
                for a in r.get("also_sources") or []:
                    if a.get("name") and a.get("url"):
                        urls.setdefault(squash_ws(a["name"]), a["url"])
                for u in r.get("usual") or []:
                    if u.get("source_name") and u.get("source_url"):
                        urls.setdefault(squash_ws(u["source_name"]), u["source_url"])
            sources = [{"name": no_hangul(squash_ws(en)) or self.provider(ko_name), "url": urls.get(squash_ws(ko_name), "")}
                       for ko_name, en in (rec.get("sources") or {}).items()]
            places = [self.place_by_ko_slug[s] for s in self._series_places(x) if s in self.place_by_ko_slug]
            item = {"x": x, "anchor": x["anchor"], "series_name": squash_ws(rec.get("series_name")),
                    "name": squash_ws(new.get("name")) or squash_ws(rec.get("series_name")), "rows": rows,
                    "start": ev.get("start_date") or "", "end": ev.get("end_date") or "", "last": last,
                    "highlights": [squash_ws(h) for h in rec.get("highlights") or [] if squash_ws(h)],
                    "program_notes": [squash_ws(h) for h in rec.get("program_notes") or [] if squash_ws(h)],
                    "notes": [squash_ws(n) for n in new.get("notes") or [] if squash_ws(n)],
                    "usual": [u for u in rec.get("usual") or [] if squash_ws(u.get("text"))],
                    "editions": [ed for ed in rec.get("editions") or [] if squash_ws(ed.get("name"))],
                    "sources": sources, "places": places, "checked": sr.get("checked") or latest_date(sr["editions"]),
                    "flag": any(r["blocks"] for r in rows), "ko_path": f"/events/{sr['slug']}/",
                    "homepage": web_url(ev.get("homepage")) if not HANGUL.search(web_url(ev.get("homepage")) or "") else ""}
            (out_up if last and last >= S.today else out_past).append(item)
        out_up.sort(key=lambda r: (r["start"], r["name"]))
        out_past.sort(key=lambda r: (r["start"], r["name"]), reverse=True)
        return {"upcoming": out_up, "past": out_past, "n": len(out_up) + len(out_past),
                "checked": max((r["checked"] or "" for r in out_up + out_past), default="")}


En = Site   # the English site's first name (tests and tools import it)


def latest_date(records: list[dict]) -> str:
    return max((squash_ws(r.get("checked_at")) for r in records if r.get("checked_at")), default="")


# ---------------------------------------------------------------------------------------------- every version
class SlugBook:
    """The English slug of every record — the path segment all versions share (/de/places/<english-slug>/). For a
    record with a current English page, that page's slug; otherwise the slug English would give it: from the English
    record (even a stale one) or en/names.json, else from the romanized Korean name (guides and courses: their id),
    never one an English page already uses."""

    def __init__(self, S, data_dir: Path, en: Site | None):
        d = Path(data_dir) / "en"
        recs = {k: _load(d / f"{k}.json", {}) or {} for k in ("places", "guides", "courses", "events")}
        names = _load(d / "names.json", {}) or {}
        self.map: dict[str, dict[str, str]] = {"places": {}, "guides": {}, "courses": {}, "events": {}}
        if en:
            self.map["places"] = {pid: p["slug"] for pid, p in en.places.items()}
            self.map["guides"] = {gid: x["slug"] for gid, x in en.guides.items()}
            self.map["courses"] = {cid: x["slug"] for cid, x in en.courses.items()}
            self.map["events"] = {x["slug"]: x["anchor"] for x in en.series}
        self._fill("places", [(e["id"], (recs["places"].get(e["id"]) or {}).get("name_en")
                               or ((names.get(e["id"]) or {}).get("name_ko") == e["name"] and names[e["id"]].get("name_en"))
                               or romanize(e["name"])) for e in S.entities])
        self._fill("guides", [(g["id"], re.split(r":\s", (recs["guides"].get(g["id"]) or {}).get("title") or "",
                                                  maxsplit=1)[0] or g["id"]) for g in S.guides])
        self._fill("courses", [(c["id"], (recs["courses"].get(c["id"]) or {}).get("name") or c["id"]) for c in S.courses])
        self._fill("events", [(sr["slug"], (recs["events"].get(sr["slug"]) or {}).get("series_name") or romanize(sr["name"]))
                              for sr in event_series(getattr(S, "events_all", []) or [])])

    def _fill(self, kind: str, rows: list[tuple[str, str]]) -> None:
        have = self.map[kind]
        used = set(have.values())
        for ident, name in rows:
            if ident in have:
                continue
            base = en_slug(name)
            slug, tail = base, re.sub(r"\D", "", ident)[-6:]
            if slug in used:
                slug = f"{base}-{tail}" if tail else base
            n = 2
            while slug in used:
                slug, n = f"{base}-{n}", n + 1
            used.add(slug)
            have[ident] = slug

    def slug(self, kind: str, ident: str) -> str:
        return self.map[kind][ident]


class Intl:
    """The versions this build has (in menu order) and what their pages share: hreflang sets and the language menu."""

    def __init__(self, sites: dict[str, Site], skipped: dict[str, list[str]] | None = None):
        self.sites = sites
        self.skipped = skipped or {}

    def __bool__(self) -> bool:
        return bool(self.sites)

    def site_of(self, path: str) -> Site | None:
        return self.sites.get(LC.code_of_path(path))

    def ko_path(self, path: str) -> str | None:
        site = self.site_of(path)
        if site is None:
            return path
        return site.en2ko.get(path)

    def alternates(self, path: str) -> list[dict]:
        """hreflang links for a page that has at least one twin: ko, every version with a twin, x-default (= ko)."""
        ko = self.ko_path(path)
        if not ko:
            return []
        twins = [(s.loc.html, s.ko2en[ko]) for s in self.sites.values() if ko in s.ko2en]
        if not twins:
            return []
        S = next(iter(self.sites.values())).S
        return ([{"hreflang": "ko", "href": S.abs(ko)}] + [{"hreflang": h, "href": S.abs(p)} for h, p in twins]
                + [{"hreflang": "x-default", "href": S.abs(ko)}])

    def menu(self, path: str) -> list[dict]:
        """The language menu of a page: Korean and every version, each its counterpart of this page (else that
        version's home), the page's own version marked current. Empty when the build has no other version."""
        if not self.sites:
            return []
        own = self.site_of(path)
        ko = self.ko_path(path) if own else path
        items = [{"code": "ko", "hreflang": "ko", "label": LC.KO["label"], "current": own is None,
                  "href": path if own is None else (ko or "/")}]
        for code, s in self.sites.items():
            href = path if s is own else (s.en_link(ko) if ko else s.home)
            items.append({"code": code, "hreflang": s.loc.html, "label": s.loc.label, "current": s is own, "href": href})
        return items


def load_all(S, data_dir: Path) -> Intl:
    """Every version this build has: data/<region>/<code> exists and its UI words are complete (a version whose
    strings.json lacks some 'chrome.<key>' rows is not built; build stats list the missing keys). English first:
    the other versions take its slugs."""
    data_dir = Path(data_dir)
    sites: dict[str, Site] = {}
    skipped: dict[str, list[str]] = {}
    en = Site(S, data_dir, EN) if (data_dir / "en").is_dir() else None
    if en:
        sites["en"] = en
    book = None
    for code in LC.ORDER[1:]:
        if not (data_dir / code).is_dir():
            continue
        book = book or SlugBook(S, data_dir, en)
        site = Site(S, data_dir, LC.get(code), book)
        if site.t.missing:
            skipped[code] = site.t.missing
            for e in S.entities:
                (e.get("_intl") or {}).pop(code, None)
            continue
        sites[code] = site
    return Intl(sites, skipped)


def load(S, data_dir: Path) -> Site | None:
    """The English site for this build, or None when data/<region>/en does not exist (the sample data)."""
    if not (Path(data_dir) / "en").is_dir():
        return None
    return Site(S, data_dir, EN)


# ---------------------------------------------------------------------------------------------- JSON-LD
def _webpage(site: Site, url: str, title: str, about: str | None = None, modified: str = "", based_on=None,
             reviewed: str = "") -> dict:
    S = site.S
    node = {"@type": "WebPage", "@id": url, "url": url, "name": title, "inLanguage": site.loc.html,
            "isPartOf": {"@id": f"{S.site_url}{site.home}#website"}, "publisher": jsonld.org_ref(S.site_url)}
    if about:
        node["about"] = {"@id": about}
    if modified:
        node["dateModified"] = modified
    if reviewed:
        node["lastReviewed"] = reviewed
    based_on = [u for u in (based_on or []) if u]
    if based_on:
        node["isBasedOn"] = based_on if len(based_on) > 1 else based_on[0]
    return node


def _city(site: Site) -> dict:
    return {"@id": f"{site.S.site_url}/#gunsan", "@type": "City", "name": site.region}


def _author(site: Site) -> dict:
    """The editor in charge (site.json editor) as on the footer, else the publisher."""
    S = site.S
    if site.loc.code == "en":
        return jsonld.author_node(S.site, S.site_url, "en")
    ed = S.site.get("editor") or {}
    if not ed.get("name"):
        return jsonld.org_ref(S.site_url)
    return {"@type": "Person", "name": ed["name"], "worksFor": jsonld.org_ref(S.site_url),
            "jobTitle": site.t.s("editor_role")}


def place_ref(p: dict) -> dict:
    return {"@id": f"{p['url']}#place", "@type": schema_type(p["e"]), "name": p["name"]}


def place_graph(site: Site, vm: dict, title: str, crumbs: list, images: list[dict]) -> dict:
    S, p, e, rec = site.S, vm["p"], vm["e"], vm["rec"]
    facts = rec.get("facts") or {}
    url = p["url"]
    node = {"@type": schema_type(e), "@id": f"{url}#place", "name": p["name"], "alternateName": e["name"], "url": url}
    if vm["summary"]:
        node["description"] = vm["summary"]
    addr = squash_ws((facts.get("address") or {}).get("value"))
    if addr:
        node["address"] = {"@type": "PostalAddress", "streetAddress": addr, "addressCountry": "KR"}
    if e["_geo"]:
        node["geo"] = {"@type": "GeoCoordinates", "latitude": e["_geo"]["lat"], "longitude": e["_geo"]["lng"]}
        node["hasMap"] = f"https://www.google.com/maps/search/?api=1&query={e['_geo']['lat']},{e['_geo']['lng']}"
    phones = [phone_intl(x) for x in extract_phones((facts.get("infocenter") or {}).get("value"))]
    if phones and not (facts.get("infocenter") or {}).get("alternatives"):
        node["telephone"] = phones if len(phones) > 1 else phones[0]
    if e.get("kind") == "stay":
        for key, prop in (("checkin", "checkinTime"), ("checkout", "checkoutTime")):
            v = squash_ws((facts.get(key) or {}).get("value"))
            if re.fullmatch(r"\d{2}:\d{2}", v) and not (facts.get(key) or {}).get("alternatives"):
                node[prop] = v
    ko = e.get("facts") or {}
    hours = []
    ut = squash_ws((facts.get("usetime") or {}).get("value"))
    if not (jsonld.conflicted(e, "usetime") or jsonld.conflicted(e, "restdate")):
        hours = [h for h in jsonld.opening_hours(ko.get("usetime"), ko.get("restdate"))]
        if not all(h["opens"] in ut and h["closes"] in ut for h in hours):
            hours = []
    if hours:
        node["openingHoursSpecification"] = hours
    typed = {"usetime", "restdate"} if hours else set()
    props = [{"@type": "PropertyValue", "name": site.fact_label(k), "value": squash_ws(facts[k]["value"])}
             for k in jsonld.PROP_KEYS if k in facts and squash_ws(facts[k].get("value")) and k not in typed]
    if props:
        node["additionalProperty"] = props
    if images:
        kto = site.t.s("kto")
        node["image"] = [{"@type": "ImageObject", "contentUrl": im["url"], "creditText": kto, "copyrightNotice": kto,
                          "creator": {"@type": "Organization", "name": kto},
                          "license": (lic := jsonld.LICENSE_URLS["KOGL-1" if im["type"] == 1 else "KOGL-3"]),
                          "acquireLicensePage": lic}
                         for im in images]
    awards = [d["label"] for d in vm["designations"]]   # the labels the page shows (as the Korean `award`)
    if awards and jsonld.AWARD_TYPES & set(node_types(node)):
        node["award"] = awards if len(awards) > 1 else awards[0]
    official = e.get("official") or {}
    same = [u for u in ((e.get("original") or {}).get("source_url"), official.get("visitkorea_url")) if u]
    if same:
        node["sameAs"] = same
    node["containedInPlace"] = _city(site)
    graph = [_webpage(site, url, title, f"{url}#place", vm["facts_checked"], [(e.get("original") or {}).get("source_url")],
                      vm["reviewed_at"]), node, jsonld.breadcrumb(crumbs)]
    if vm["faqs"]:
        graph.append(jsonld.faq_page(vm["faqs"], url))
    return {"@context": "https://schema.org", "@graph": graph}


def simple_graph(site: Site, url: str, title: str, crumbs: list, item_urls: list[str] | None = None) -> dict:
    graph = [_webpage(site, url, title), jsonld.breadcrumb(crumbs)]
    if item_urls:
        graph.append(jsonld.item_list(item_urls, url))
    return {"@context": "https://schema.org", "@graph": graph}


# ---------------------------------------------------------------------------------------------- pages
def _title(base: str, labels: list[str], limit: int = 70, loc: LC.Locale = EN) -> str:
    """'<name>: Hours, Fees, Parking' with as many labels as fit in `limit` characters."""
    for n in range(len(labels), 0, -1):
        t = f"{base}{loc.colon}{loc.list_sep.join(labels[:n])}"
        if len(t) <= limit:
            return t
    return base


def answer_description(summary: str, rows: list[dict], limit: int = 160, loc: LC.Locale = EN) -> str:
    """The summary's first sentence (the next one too while short), then up to two short fact values no other
    source contradicts ('Hours: 09:00–18:00.'). Whole sentences and whole values only; a first sentence longer
    than the limit is cut back to its first clause (or its last whole word)."""
    ss = sentences(summary, loc)
    stop, join = ("。", "") if loc.cjk else (".", " ")
    out = ss[0] if ss else ""
    if len(out) > limit:
        if loc.cjk:
            cut = re.split(r"[、，；]", out)[0]
            out = cut if len(cut) <= limit - 1 else out[: limit - 1]
            return out.rstrip("、，；。") + stop
        cut = re.split(r",\s|;\s|\s—\s", out)[0]
        out = cut if len(cut) <= limit - 1 else out[: limit - 1].rsplit(" ", 1)[0]
        return out.rstrip(".,;") + "."
    short = 30 if loc.cjk else 60
    for nxt in ss[1:]:
        if len(out) >= short or len(out) + len(join) + len(nxt) > limit:
            break
        out = f"{out}{join}{nxt}"
    added = 0
    for r in rows:
        if added == 2:
            break
        if r["conflict"] or r["key"] in ("address", "infocenter", "homepage", "reservationurl") or not r["text"]:
            continue
        v = squash_ws(r["text"]).rstrip(".。")
        s = f"{r['label']}{loc.colon}{v}{stop}"
        if "\n" in r["text"] or len(v) > 30 or len(out) + len(join) + len(s) > limit or v in out:
            continue
        out, added = f"{out}{join}{s}", added + 1
    return out


def latest_of(dates) -> str | None:
    found = [squash_ws(str(d)) for d in dates if d and squash_ws(str(d))]
    return max(found) if found else None


class Pages:
    """Renders every page of one version into the build's output folder and records the sitemap rows."""

    def __init__(self, site: Site, env, out: Path, intl: Intl | None = None):
        self.site, self.en, self.S, self.env, self.out = site, site, site.S, env, out
        self.intl = intl or Intl({site.loc.code: site})
        self.t, self.loc = site.t, site.loc
        self.count = 0
        self.indexable = 0

    def abs(self, path: str) -> str:
        return self.S.abs(path)

    def common(self, page: dict, page_kind: str, path: str) -> dict:
        S, site, loc = self.S, self.site, self.loc
        page.setdefault("alternates", self.intl.alternates(path))
        nav = [(lab, href) for lab, href in site.nav() if self._built(href)]
        return {"site": {**S.site_view, "site_name": loc.site_name, "brand": loc.site_name}, "page": page,
                "page_kind": page_kind, "noindex": S.cfg["noindex"], "banner": "", "mode": S.mode, "lang": loc.html,
                "og_locale": loc.og, "nav": nav, "nav_current": site.current_nav(page_kind), "ctxbtn": None,
                "has_search": False, "has_videos": False, "tourapi_used": S.tourapi_used, "wordmark": loc.site_name,
                "build_date": S.today, "langs": self.intl.menu(path), "en": site, "t": site.t, "loc": loc,
                "region": site.region, "ko_site_name": S.site.get("site_name", ""),
                # AI art (pipeline/art.py): only the pictures whose langs name this version, with its alt and label
                "art_slots": art.for_lang(S.art, loc.code)}

    def _built(self, href: str) -> bool:
        site = self.site
        for kind, c in LIST_PAGES.items():
            if site.home + c["seg"] == href:
                return bool(site.by_kind[kind])
        return {f"{site.home}guides/": bool(site.guides), f"{site.home}courses/": bool(site.courses),
                f"{site.home}events/": bool(site.series and self.S.events)}.get(href, True)

    def render(self, template: str, path: str, page: dict, page_kind: str, lastmod: str | None = None,
               in_sitemap: bool = True, **ctx) -> None:
        from .build import _write
        code = self.loc.code
        og = None if page.get("image") else art.og_fallback(art.for_lang(self.S.art, code), path, code)
        if og:  # a page without a photo of its own: the version's link-preview illustration (og.default-en, og.ja …;
            # never a place page) with its alt in the version's language
            page.update(image=self.S.abs(og["src"]), image_alt=og["alts"].get(code, ""), image_w=og["w"], image_h=og["h"])
        html = self.env.get_template(template).render({**self.common(page, page_kind, path), **ctx})
        _write(self.out, path, html)
        self.count += 1
        if in_sitemap:
            self.S.pages.append((path, lastmod or None))
            self.indexable += 1

    def crumbs(self, *items) -> list:
        return [(self.t.s("home"), self.abs(self.site.home)), *items]

    def _simple(self, path: str, title: str, desc: str, crumbs: list, item_urls: list[str] | None = None) -> dict:
        url = self.abs(path)
        return {"title": title, "description": desc, "canonical": url, "crumbs": crumbs,
                "jsonld": [jsonld.dumps(simple_graph(self.site, url, title, crumbs, item_urls))]}

    # ---- pages
    def place(self, p: dict) -> None:
        site, t, loc = self.site, self.t, self.loc
        vm = site.place_vm(p)
        e = p["e"]
        cfg = site.lists()[vm["kind"]]
        crumbs = self.crumbs((cfg["nav"], self.abs(cfg["path"])), (p["name"], p["url"]))
        labels: list[str] = []
        for r in vm["practical"]:
            lab = site.T(f"TITLE_LABELS.{r['key']}")
            if lab and lab not in labels:
                labels.append(lab)
        qualified = p["name"] if site.region in p["name"] else t.s("name_in_region", name=p["name"], r=site.region)
        title = _title(qualified, labels[:3], loc.title_max, loc)
        if title == qualified and len(qualified) <= loc.title_max - 20:
            title = t.s("visit_information", name=qualified)
        desc = answer_description(vm["summary"], vm["practical"], loc.desc_max, loc) or \
            t.s("place_desc_fallback", name=p["name"], r=site.region)
        images = vm["photos"][:7]
        page = {"title": title, "description": desc, "canonical": p["url"], "og_type": "article",
                "image": next((ph["url"] for ph in vm["photos"] if ph["type"] == 1), vm["photos"][0]["url"] if vm["photos"] else ""),
                "geo": e["_geo"], "geo_placename": f"{site.region} {p['name']}", "crumbs": crumbs, "map": bool(e["_geo"]),
                "jsonld": [jsonld.dumps(place_graph(site, vm, title, crumbs, images))]}
        if p["noindex"]:
            page["robots"] = "noindex, follow"
        self.render("en/place.html.j2", p["path"], page, f"place-{vm['kind']}", e.get("_page_date"),
                    in_sitemap=not p["noindex"], v=vm)

    def lists(self) -> None:
        site, t, loc = self.site, self.t, self.loc
        for kind, cfg in site.lists().items():
            if not site.by_kind[kind]:
                continue
            L = site.list_vm(kind)
            r = site.region
            title = t.s(f"title_{kind}", r=r, n=L["count"])
            crumbs = self.crumbs((cfg["nav"], self.abs(cfg["path"])))
            hub = site.guides.get(cfg["hub"])
            urls = [it["p"]["url"] for g in L["groups"] for it in g["recs"]]
            desc = t.sn(f"desc_{kind}", L["count"], r=r)
            page = {**self._simple(cfg["path"], title, desc, crumbs, urls),
                    "image": next((it["photo"]["url"] for g in L["groups"] for it in g["recs"]
                                   if it["photo"] and it["photo"]["type"] == 1), "")}
            lastmod = latest_of([it["e"].get("_page_date") for g in L["groups"] for it in g["recs"]])
            self.render("en/list.html.j2", cfg["path"], page, "places" if kind == "attraction" else f"list-{kind}",
                        lastmod, L=L, cfg=cfg, h1=cfg["h1"], lead=site.T(f"LISTS.{kind}.lead"),
                        hub={"path": hub["path"], "label": squash_ws(hub["rec"].get("label"))} if hub else None)

    def guide_order(self) -> list[dict]:
        hubs = [self.site.guides[g] for g in HUBS if g in self.site.guides]
        return hubs + [x for gid, x in self.site.guides.items() if gid not in HUBS]

    def guides(self) -> None:
        site, t, loc = self.site, self.t, self.loc
        if not site.guides:
            return
        order = self.guide_order()
        rows = []
        home = site.home
        for x in order:
            G = site.guide_vm(x)
            rows.append(G)
            crumbs = self.crumbs((t.s("guides"), self.abs(f"{home}guides/")), (G["title"], x["url"]))
            title = G["title"] if len(G["title"]) <= loc.title_max else t.s("label_in_region", label=G["label"], r=site.region)
            unique = list({it["p"]["url"]: it["p"] for it in G["places"] if it["p"]}.values())
            art_ = {"@type": "Article", "@id": f"{x['url']}#article", "headline": G["title"][:110],
                    "mainEntityOfPage": x["url"], "inLanguage": loc.html, "author": _author(site),
                    "publisher": jsonld.org_ref(self.S.site_url)}
            if G["summary"]:
                art_["description"] = G["summary"]
            if G["checked"]:
                art_["dateModified"] = G["checked"]
            if unique:
                art_["about"] = [place_ref(p) for p in unique]
            srcs = [s["url"] for s in G["sources"] if s.get("url")]
            if srcs:
                art_["isBasedOn"] = srcs
            graph = [art_, jsonld.breadcrumb(crumbs)]
            if unique:
                graph.append(jsonld.item_list([p["url"] for p in unique], x["url"]))
            if G["faqs"]:
                graph.append(jsonld.faq_page(G["faqs"], x["url"]))
            page = {"title": title, "description": answer_description(G["summary"], [], loc.desc_max, loc),
                    "canonical": x["url"], "og_type": "article", "crumbs": crumbs, "map": bool(G["points"]),
                    "image": next((it["photo"]["url"] for it in G["places"] if it["photo"] and it["photo"]["type"] == 1), ""),
                    "jsonld": [jsonld.dumps({"@context": "https://schema.org", "@graph": graph})]}
            self.render("en/guide.html.j2", x["path"], page, "guide", x["g"].get("_page_date"), G=G)
        crumbs = self.crumbs((t.s("guides"), self.abs(f"{home}guides/")))
        page = self._simple(f"{home}guides/", t.s("guides_title", r=site.region),
                            t.sn("guides_desc", len(rows), r=site.region), crumbs, [x["url"] for x in order])
        self.render("en/guides.html.j2", f"{home}guides/", page, "guides",
                    latest_of([x["g"].get("_page_date") for x in order]), rows=rows)

    def courses(self) -> None:
        site, t, loc = self.site, self.t, self.loc
        if not site.courses:
            return
        home = site.home
        vms = []
        for x in site.courses.values():
            C = site.course_vm(x)
            vms.append(C)
            crumbs = self.crumbs((t.s("courses"), self.abs(f"{home}courses/")), (C["name"], x["url"]))
            refs = [place_ref(s["p"]) if s["p"] else {"@type": "Place", "name": s["name"]} for s in C["stops"]]
            trip = {"@type": "TouristTrip", "@id": f"{x['url']}#trip", "name": C["name"], "url": x["url"]}
            if C["summary"]:
                trip["description"] = C["summary"]
            if C["orig_url"]:
                trip["isBasedOn"] = C["orig_url"]
            if refs:
                trip["itinerary"] = {"@type": "ItemList", "itemListElement": [
                    {"@type": "ListItem", "position": i, "item": it} for i, it in enumerate(refs, 1)]}
            base = C["name"] if site.region in C["name"] else t.s("region_name", r=site.region, name=C["name"])
            title = _title(base, [t.sn("n_stops_title", C["n_places"])], loc.title_max, loc) \
                if len(base) <= loc.title_max - 10 else base
            page = {"title": title, "description": answer_description(C["summary"], [], loc.desc_max, loc)
                    or t.sn("course_desc_fallback", C["n_places"], name=C["name"]),
                    "canonical": x["url"], "crumbs": crumbs, "map": bool(C["map"]),
                    "image": next((s["photo"]["url"] for s in C["stops"] if s["photo"] and s["photo"]["type"] == 1), ""),
                    "jsonld": [jsonld.dumps({"@context": "https://schema.org", "@graph": [trip, jsonld.breadcrumb(crumbs)]})]}
            self.render("en/course.html.j2", x["path"], page, "course", x["c"].get("_page_date"), C=C)
        groups: dict[str, list] = {}
        for C in vms:
            groups.setdefault(C["duration"] or C["group"] or t.s("courses"), []).append(C)
        grouped = sorted(groups.items(), key=lambda kv: (DURATION_ORDER.get(kv[1][0]["c"].get("duration") or "", 9)
                                                         if kv[1][0]["duration"] else 9, kv[0]))
        crumbs = self.crumbs((t.s("courses"), self.abs(f"{home}courses/")))
        page = self._simple(f"{home}courses/", t.s("courses_title", r=site.region),
                            t.sn("courses_desc", len(vms), provider=site.provider((self.S.site.get("source") or {}).get("name"))),
                            crumbs, [C["x"]["url"] for C in vms])
        self.render("en/courses.html.j2", f"{home}courses/", page, "courses",
                    latest_of([C["c"].get("_page_date") for C in vms]),
                    groups=[{"title": tt, "id": "g-" + en_slug(tt if loc.code == "en" else
                                                               romanize(cs[0]["c"].get("duration") or cs[0]["c"].get("group") or "")
                                                               or tt), "courses": cs} for tt, cs in grouped])

    def events(self) -> None:
        site, S, t = self.site, self.S, self.t
        if not site.series or not S.events:
            return
        EV = site.events_vm()
        path = f"{site.home}events/"
        crumbs = self.crumbs((t.s("events"), self.abs(path)))
        url = self.abs(path)
        title = t.s("events_title", r=site.region)
        nodes = []
        for r in EV["upcoming"] + EV["past"]:
            if not r["start"]:
                continue
            node = {"@type": "Event", "@id": f"{url}#{r['anchor']}", "name": r["name"], "url": f"{url}#{r['anchor']}",
                    "startDate": r["start"]}
            if r["end"]:
                node["endDate"] = r["end"]
            by = {row["field"]: row for row in r["rows"]}
            venue = by.get("place_name")
            if venue and venue["value"] and not venue["blocks"]:
                loc_ = {"@type": "Place", "name": venue["value"]}
                ad = by.get("address")
                if ad and ad["value"] and not ad["blocks"]:
                    loc_["address"] = {"@type": "PostalAddress", "streetAddress": ad["value"], "addressCountry": "KR"}
                node["location"] = loc_
            sp = by.get("sponsor")
            if sp and sp["value"] and not sp["blocks"]:
                node["organizer"] = {"@type": "Organization", "name": sp["value"]}
            nodes.append(node)
        graph = [_webpage(site, url, title, None, EV["checked"]), jsonld.breadcrumb(crumbs), *nodes]
        page = {"title": title,
                "description": t.s("events_desc", a=len(EV["upcoming"]), b=len(EV["past"]), r=site.region),
                "canonical": url, "crumbs": crumbs,
                "jsonld": [jsonld.dumps({"@context": "https://schema.org", "@graph": graph})]}
        self.render("en/events.html.j2", path, page, "events", EV["checked"], EV=EV)

    def about(self) -> None:
        site, t = self.site, self.t
        path = f"{site.home}about/"
        crumbs = self.crumbs((t.s("about"), self.abs(path)))
        page = self._simple(path, t.s("about_title"), t.s("about_desc", site=site.loc.site_name), crumbs)
        lics = Counter(ph["type"] for p in site.places.values() for ph in p["e"].get("_photos") or [])
        self.render("en/about.html.j2", path, page, "about",
                    latest_of([p["e"].get("_page_date") for p in site.places.values()]),
                    n_places=len(site.places), n_index=sum(1 for p in site.places.values() if not p["noindex"]),
                    n_guides=len(site.guides), n_courses=len(site.courses), n_series=len(site.series), lics=lics)

    def home(self) -> None:
        site, S, t, loc = self.site, self.S, self.t, self.loc
        counts = {k: len(site.by_kind[k]) for k in KINDS}
        home = site.home
        lists = site.lists()
        tiles = []
        for g in HUBS:   # the accent bento (present.ACCENT_TONES): hub guides on lime · lavender · sky
            if g not in site.guides:
                continue
            x = site.guides[g]
            n = len([it for it in x["rec"].get("items") or [] if it.get("place_slug")])
            tone, icon = present.ACCENT_TONES.get(g, ("", ""))
            title = squash_ws(x["rec"].get("title"))
            if loc.code == "en":
                head, _, tail = title.partition(": ")
            else:   # 'title：list' (CJK) or 'title : list' (French spacing)
                parts = re.split(r"\s*[:：]\s*", title, maxsplit=1)
                head, tail = parts[0], (parts[1] if len(parts) > 1 else "")
            # the food hub (present.HUB_LEAD) shows its first dishes as pills, from the guide title's own list
            pills = (title_list(tail, loc)[:4] if g in present.HUB_LEAD else [])
            tiny = {"guide-14": "hub_tiny_stay", "guide-15": "hub_tiny_attraction"}.get(g)
            tiles.append({"href": x["path"], "fig": str(n), "unit": t.sn("places_unit", n), "key": squash_ws(x["rec"].get("label")),
                          "short": head, "tiny": " · ".join(pills[:3]) if pills else (t.s(tiny) if tiny else head),
                          "track": "guide_click", "tone": tone, "icon": icon, "pills": pills})
        if site.courses:   # the one black card, right after the hub guides
            tiles.append({"href": f"{home}courses/", "fig": str(len(site.courses)), "unit": "", "key": t.s("courses"),
                          "short": t.s("tile_courses_short"), "tiny": t.s("tile_courses_tiny"),
                          "track": "course_click", **present.ACCENT_DARK, "pill": t.s("tile_courses_pill")})
        # (desktop line, phone line): the phone line stays one short line in a 160px tile; the title is the list's
        # noun ('161 Attractions'), short enough for one line there too
        for kind in KINDS:
            if counts[kind]:
                tiles.append({"href": lists[kind]["path"], "fig": str(counts[kind]), "unit": "", "key": t.s(f"tile_{kind}"),
                              "short": t.s(f"tile_short_{kind}"), "tiny": t.s(f"tile_tiny_{kind}"), "track": ""})
        EV = site.events_vm() if site.series and S.events else {"upcoming": [], "past": []}
        if site.series and S.events:
            tiles.append({"href": f"{home}events/", "fig": str(len(EV["upcoming"])), "unit": "", "key": t.s("events"),
                          "short": t.s("tile_events_short"), "tiny": t.s("tile_events_tiny"), "track": ""})
        hero = None
        kto = t.s("kto")
        for ph in media.slot_photos(S).get("hero") or []:
            tg = S.ent_by_slug.get(ph.get("slug"))
            tp = site.own(tg)
            if tg and tp and ph.get("type") == 1:
                hero = {**ph, "alt": tp["name"], "name": tp["name"], "place": tp["name"],
                        "path": tp["path"], "credit": kto, "lic": site.lic("KOGL-1")}
                break
        cover = None   # the full-bleed opening photo (media.HOME_COVER, KOGL-1), with the place's name in this language
        ph = media.slot_photos(S).get("cover")
        tg = S.ent_by_slug.get(ph.get("slug")) if ph else None
        tp = site.own(tg)
        if ph and tg and tp and ph.get("type") == 1:
            cover = {**ph, "alt": tp["name"], "name": tp["name"], "place": tp["name"],
                     "path": tp["path"], "credit": kto, "lic": site.lic("KOGL-1")}
        # the opening's bottom bar: the same event the Korean home shows (present.pick_next_event), else the first
        ko_next = present.pick_next_event(present.ranked_events(S)) if EV["upcoming"] else None
        hero_ev = next((r for r in EV["upcoming"] if ko_next and r["ko_path"] == ko_next.get("path")),
                       EV["upcoming"][0] if EV["upcoming"] else None)
        h = present.home_vm(S)
        featured = [site.card(site.own(c["e"]), c.get("photo")) for c in h.get("featured") or [] if site.own(c["e"])][:8]
        day = [x for x in site.courses.values() if x["c"].get("duration") == "당일"]
        lines = [site.course_vm(x) for x in (day or list(site.courses.values()))[:4]]
        page = {"title": t.s("home_title", site=loc.site_name, r=site.region),
                "description": t.s("home_desc", a=counts["attraction"], f=counts["food"], s=counts["stay"], r=site.region),
                "canonical": self.abs(home), "crumbs": [], "image": (cover or hero or {}).get("url", "")}
        dest = {"@type": ["City", "TouristDestination"], "@id": f"{S.site_url}/#gunsan", "name": site.region}
        if featured:
            dest["includesAttraction"] = [place_ref(c["p"]) for c in featured]
        website = {"@type": "WebSite", "@id": f"{S.site_url}{home}#website", "url": self.abs(home), "name": loc.site_name,
                   "inLanguage": loc.html, "publisher": jsonld.org_ref(S.site_url)}
        page["jsonld"] = [jsonld.dumps({"@context": "https://schema.org",
                                        "@graph": [website, jsonld.organization(S.site, S.site_url), dest]})]
        # the opening photo fills the first screen: the template preloads it (md.preload) with high priority
        lastmod = latest_of([c["e"].get("_page_date") for c in featured]
                            + [x["g"].get("_page_date") for x in site.guides.values()])
        # the centre question card (templates/_ask.html.j2) under the photo: a starter shows only where its page in this
        # version is built — one of its guides, or its events list (State.ask None: no card). ask.json keys the
        # questions by the html language tag (ko, en, ja, zh-Hans …), like the card's own strings.
        items = getattr(S, "ask", None)
        ask_starters = None if items is None else ask.starters(
            items, loc.html, {gid: x["path"] for gid, x in site.guides.items()},
            {"events": f"{home}events/"} if site.series and S.events else {})
        self.render("en/home.html.j2", home, page, "home", lastmod, counts=counts, tiles=tiles, hero=hero, cover=cover,
                    hero_ev=hero_ev, today=S.today, featured=featured, events=EV["upcoming"][:4], lines=lines,
                    hubs=[site.guides[g] for g in HUBS if g in site.guides], lists=lists,
                    n_courses=len(site.courses), n_guides=len(site.guides), ask_starters=ask_starters)


def render(site: Site, env, out: Path, intl: Intl | None = None) -> dict:
    """Every page of one version; returns the build line's stats (pages, indexable, stale records skipped)."""
    pg = Pages(site, env, out, intl)
    for p in site.places.values():
        pg.place(p)
    pg.lists()
    pg.guides()
    pg.courses()
    pg.events()
    pg.about()
    pg.home()
    out_ = {"pages": pg.count, "indexable": pg.indexable, "places": len(site.places),
            "places_indexable": sum(1 for p in site.places.values() if not p["noindex"]),
            "guides": len(site.guides), "courses": len(site.courses), "event_series": len(site.series),
            "stale_skipped": {k: len(v) for k, v in site.stale.items()}}
    if site.loc.code != "en":
        out_["missing_strings"] = sorted(site.misses)
    return out_


def llms_lines(site: Site) -> list[str]:
    """The llms.txt section of a version. English: home, the three hub guides, lists, courses, events, top place
    pages (indexable only; most official courses first). The other versions: home, the hub guides and the lists."""
    S, t = site.S, site.t
    if site.loc.code != "en":
        out = [f"## {site.loc.label}", f"- [{site.loc.site_name}]({S.abs(site.home)}): {t.s('llms_home', r=site.region)}"]
        for gid in HUBS:
            x = site.guides.get(gid)
            if x:
                first = (sentences(x["rec"].get("summary"), site.loc) or [""])[0]
                out.append(f"- [{squash_ws(x['rec'].get('title'))}]({x['url']}): {first}".rstrip(": "))
        for kind, cfg in site.lists().items():
            if site.by_kind[kind]:
                out.append(f"- [{cfg['h1']}]({S.abs(cfg['path'])}): {t.sn('count_' + kind, len(site.by_kind[kind]))}")
        return out + [""]
    out = ["## English", f"- [{EN_SITE_NAME}]({S.abs(EN_HOME)}): {t.s('llms_home', r=site.region)}"]
    for gid in HUBS:
        x = site.guides.get(gid)
        if x:
            first = (sentences_en(x["rec"].get("summary")) or [""])[0]
            out.append(f"- [{squash_ws(x['rec'].get('title'))}]({x['url']}): {first}".rstrip(": "))
    for kind, cfg in site.lists().items():
        if site.by_kind[kind]:
            out.append(f"- [{cfg['h1']}]({S.abs(cfg['path'])}): {t.sn('count_' + kind, len(site.by_kind[kind]))}")
    if site.courses:
        out.append(f"- [{site.region} travel courses]({S.abs('/en/courses/')}): {len(site.courses)} official courses")
    if site.series and S.events:
        out.append(f"- [{site.region} festivals and events]({S.abs('/en/events/')}): dates, venues and fees")
    out.append(f"- [About and sources]({S.abs('/en/about/')}): sources, photo licenses, corrections")
    top = [p for p in site.places.values() if not p["noindex"]]
    top.sort(key=lambda p: (-len(p["e"].get("_courses") or []), p["e"].get("tier") != "full",
                            not p["e"].get("_photos"), p["name"]))
    for p in top[:60]:
        first = (sentences_en(p["rec"].get("summary")) or [""])[0]
        out.append(f"- [{p['name']}]({p['url']}): {first}".rstrip(": "))
    return out + [""]
