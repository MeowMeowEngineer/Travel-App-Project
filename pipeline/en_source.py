"""The Korean side of the English pages: what each English record was translated from, and its hash.

tools/en_content.py prepare writes these items as translation batches; pipeline/en_site.py recomputes them at build
time from the current Korean data. A record whose stored `ko_hash` differs from the hash of the current Korean item
was translated from older Korean text: it is stale and its English page is not built (the Korean page is the only
version until the record is translated again).

Also here: Revised Romanization of Korean names and English road/lot addresses (MCST rules), used by both.
"""
from __future__ import annotations

import hashlib
import json
import re
from pathlib import Path

from .schema import FACT_LABELS, FIT_ORDER, FACT_ORDER
from .textutil import display_address, display_value, normalize_name, slugify, squash_ws

CONFLICT_NOTE = "Sources differ — call before visiting"
EVENT_CONFLICT_NOTE = "Sources differ — check with the organizer before visiting"
URL_KEYS = ("homepage", "reservationurl")  # shown as links from the Korean data, nothing to translate
YEAR_PREFIX = re.compile(r"^20\d\d\s+")
HANGUL = re.compile(r"[ᄀ-ᇿㄱ-ㆎ가-힣]")

# ------------------------------------------------------------------ Revised Romanization (문화관광부 2000)
_CHO = ("g", "kk", "n", "d", "tt", "r", "m", "b", "pp", "s", "ss", "", "j", "jj", "ch", "k", "t", "p", "h")
_JUNG = ("a", "ae", "ya", "yae", "eo", "e", "yeo", "ye", "o", "wa", "wae", "oe", "yo", "u", "wo", "we", "wi",
         "yu", "eu", "ui", "i")
# final consonant before another consonant or at the end of a word (index = jongseong 0..27)
_JONG = ("", "k", "k", "k", "n", "n", "n", "t", "l", "k", "m", "l", "l", "l", "p", "l", "m", "p", "p", "t", "t",
         "ng", "t", "t", "k", "t", "p", "t")
# final consonant before a vowel (initial ㅇ): (kept in this syllable, carried to the next) — liaison
_LIAISON = {1: ("", "g"), 2: ("", "kk"), 3: ("k", "s"), 4: ("", "n"), 5: ("n", "j"), 6: ("n", ""), 7: ("", "d"),
            8: ("", "r"), 9: ("l", "g"), 10: ("l", "m"), 11: ("l", "b"), 12: ("l", "s"), 13: ("l", "t"),
            14: ("l", "p"), 15: ("", "r"), 16: ("", "m"), 17: ("", "b"), 18: ("p", "s"), 19: ("", "s"),
            20: ("", "ss"), 21: ("ng", ""), 22: ("", "j"), 23: ("", "ch"), 24: ("", "k"), 25: ("", "t"),
            26: ("", "p"), 27: ("", "")}
_K, _T, _P = {1, 2, 3, 9, 24}, {7, 19, 20, 22, 23, 25, 27}, {14, 17, 18, 26}
_L = {8, 11, 12, 13, 15}
_ADMIN = {"동": "dong", "읍": "eup", "면": "myeon", "리": "ri", "구": "gu", "군": "gun"}


def _boundary(f: int, i: int, v: int) -> tuple[str, str]:
    """Sound change between a final consonant f and the next initial i (next vowel v), as RR writes it.
    Nasalization, liquidization, liaison, palatalization and ㅎ-aspiration are written; tensing is not, and in
    nouns ㄱ·ㄷ·ㅂ + ㅎ stays k/t/p + h (묵호 Mukho)."""
    if f == 0:
        return "", _CHO[i]
    if i == 11:  # vowel next
        if v == 20 and f in (7, 25):  # 해돋이 haedoji, 같이 gachi
            return "", "j" if f == 7 else "ch"
        return _LIAISON[f]
    if f in (27, 6, 15) and i in (0, 3, 12):  # 좋고 joko
        return {27: "", 6: "n", 15: "l"}[f], {0: "k", 3: "t", 12: "ch"}[i]
    if f == 27 and i == 2:  # 놓는 nonneun
        return "n", "n"
    if f == 27 and i == 9:
        return "", "s"
    if i in (2, 6):  # ㄴ·ㅁ next: 백마 Baengma, 박물관 bangmulgwan, 십만 simman
        if f in _K:
            return "ng", _CHO[i]
        if f in _T:
            return "n", _CHO[i]
        if f in _P:
            return "m", _CHO[i]
        if i == 2 and f in _L:  # 칼날 kallal
            return "l", "l"
    if i == 5:  # ㄹ next: 신라 Silla, 종로 Jongno, 백리 baengni, 십리 simni
        if f == 4 or f in _L:
            return "l", "l"
        if f in (10, 16, 21):
            return _JONG[f], "n"
        if f in _K:
            return "ng", "n"
        if f in _P:
            return "m", "n"
        return "n", "n"
    return _JONG[f], _CHO[i]


def _rr_run(text: str) -> str:
    """One run of Hangul syllables (sound changes inside the run)."""
    syl = [divmod(ord(c) - 0xAC00, 28) for c in text]
    parts = [(cv // 21, cv % 21, jong) for cv, jong in syl]
    out = []
    carry = _CHO[parts[0][0]]
    for n, (cho, jung, jong) in enumerate(parts):
        nxt = parts[n + 1] if n + 1 < len(parts) else None
        if nxt:
            fin, carry_next = _boundary(jong, nxt[0], nxt[1])
        else:
            fin, carry_next = _JONG[jong], ""
        out.append(carry + _JUNG[jung] + fin)
        carry = carry_next
    return "".join(out)


def _syllables(word: str) -> bool:
    return bool(word) and all(0xAC00 <= ord(c) <= 0xD7A3 for c in word)


def romanize(text: str | None) -> str:
    """Revised Romanization of a Korean name: each word capitalized, Latin letters and digits kept,
    administrative units hyphenated ('경암동 철길마을' -> 'Gyeongam-dong Cheolgilmaeul', '종로' -> 'Jongno')."""
    words = []
    for word in squash_ws(re.sub(r"(?<=[^\s(\[])([(\[])(?=[^)\]]*[\uac00-\ud7a3])", r" \1", text or "")).split(" "):
        if not word:
            continue
        if _syllables(word) and len(word) >= 3 and word[-1] in ("동", "읍", "면"):
            base = _rr_run(word[:-1])
            words.append(base[:1].upper() + base[1:] + "-" + _ADMIN[word[-1]])
            continue
        out, prev = [], ""
        for run in re.findall(r"[가-힣]+|[^가-힣]+", word):
            if _syllables(run):
                r = _rr_run(run)
                if not prev or not prev[-1].isalnum():
                    r = r[:1].upper() + r[1:]
                out.append(r)
            else:
                out.append(run)
            prev = out[-1]
        words.append("".join(out))
    return " ".join(words)


def _rr_cap(text: str) -> str:
    r = _rr_run(text)
    return r[:1].upper() + r[1:]


# ------------------------------------------------------------------ English address (road-name / lot address)
_ROAD = re.compile(r"^(?P<base>[가-힣]+?)(?P<num>[0-9][0-9.]*)?(?P<sfx>대로|로|길)$")


def _address_rx() -> tuple[re.Pattern, re.Pattern, str] | None:
    """The road- and lot-address patterns and the English tail of the active city (site.json city.intl.en.address
    {prefix: [words the address starts with — the first required, the rest optional in a road address], tail}), a
    광역시's 구·군 read after them; None when the city has no English address form."""
    from . import city
    cfg = (city.current().intl("en").get("address") or {})
    prefix, tail = [str(x) for x in cfg.get("prefix") or [] if str(x)], str(cfg.get("tail") or "")
    if not (prefix and tail):
        return None
    head = re.escape(prefix[0]) + r"\s+" + "".join(rf"(?:{re.escape(w)}\s+)?" for w in prefix[1:])
    head_lot = "".join(rf"{re.escape(w)}\s+" for w in prefix)
    gu = r"(?:(?P<gu>[가-힣]+[구군])\s+)?"
    addr = re.compile(rf"^{head}{gu}(?:(?P<em>[가-힣]+[읍면])\s+)?(?:(?P<ri>[가-힣0-9]+리)\s+)?"
                      r"(?P<road>[가-힣]+[0-9.]*(?:대로|로|길))(?:\s?(?P<rn>\d+)번길)?\s?(?P<no>\d+(?:-\d+)?)"
                      r"(?:\s?\((?P<dong>[가-힣0-9]+동)\))?$")
    lot = re.compile(rf"^{head_lot}{gu}(?:(?P<em>[가-힣]+[읍면])\s*)?(?:(?P<ri>[가-힣0-9]+[리동])"
                     r"(?:\s+(?P<san>산)?(?P<no>\d+(?:-\d+)?))?)?$")
    return addr, lot, tail


def _admin(word: str) -> str:
    return f"{_rr_cap(word[:-1])}-{_ADMIN[word[-1]]}"


def _road(word: str) -> str:
    m = _ROAD.match(word)
    sfx = {"대로": "daero", "로": "ro", "길": "gil"}[m.group("sfx")]
    base = _rr_cap(m.group("base"))
    return f"{base} {m.group('num')}-{sfx}" if m.group("num") else f"{base}-{sfx}"


def address_en(address: str | None) -> str:
    """'<province> <시> 월명공원1길 26' -> '26 Wolmyeonggongwon 1-gil, <tail>' (the city's English address form,
    site.json city.intl.en.address). '' when the address has parts this does not read (floors, business names,
    '일원' …) or the city has no English form: the translator writes it."""
    rx = _address_rx()
    if not rx:
        return ""
    addr_rx, lot_rx, tail = rx
    a = display_address(address)
    m = addr_rx.match(a)
    if m:
        road = _road(m.group("road"))
        if m.group("rn"):
            road += f" {m.group('rn')}beon-gil"
        parts = [f"{m.group('no')} {road}" + (f" ({_admin(m.group('dong'))})" if m.group("dong") else "")]
        parts += [_admin(m.group(k)) for k in ("ri", "em", "gu") if m.group(k)]
        return ", ".join(parts + [tail])
    m = lot_rx.match(a)
    if m and (m.group("em") or m.group("ri")):
        parts = []
        if m.group("ri"):
            lot = (("San " if m.group("san") else "") + m.group("no") + " ") if m.group("no") else ""
            parts.append(lot + _admin(m.group("ri")))
        parts += [_admin(m.group(k)) for k in ("em", "gu") if m.group(k)]
        return ", ".join(parts + [tail])
    return ""


def _hash(obj) -> str:
    return hashlib.sha256(json.dumps(obj, ensure_ascii=False, sort_keys=True).encode("utf-8")).hexdigest()[:16]


def _load(data: Path, name: str, default=None):
    path = data / name
    if not path.exists():
        return default
    return json.loads(path.read_text("utf-8"))


def _name_table(data: Path, places: list[dict]) -> dict:
    """place id -> names.json row (official English name or romanized), romanized when names.json lacks it."""
    table = _load(data, "en/names.json", {}) or {}
    out = {}
    for p in places:
        row = table.get(p["id"]) or {}
        if row.get("name_ko") != p["name"]:  # renamed since names.json was written: romanize again
            row = {}
        rr = romanize(p["name"])
        out[p["id"]] = {"name_en": row.get("name_en") or rr, "name_en_source": row.get("name_en_source") or "romanized",
                        "addr_en": row.get("addr_en") or ""}
    return out


class Glossary:
    """Names that appear inside Korean text, with the English form translators must use (mentions)."""

    def __init__(self, places: list[dict], names_en: dict, courses: list[dict]):
        terms: dict[str, str] = {}
        for p in places:
            for n in [p["name"], *(p.get("alternate_names") or [])]:
                n = squash_ws(n)
                if len(n) >= 3 and n not in terms:
                    terms[n] = names_en[p["id"]]["name_en"]
        areas = set()
        for p in places:
            for tok in re.findall(r"[가-힣0-9]+(?:동|읍|면|리)(?=[\s,)]|$)", display_address((p.get("facts") or {}).get("address"))):
                if _syllables(tok) and len(tok) >= 3:  # 2-letter areas ('금동') also occur inside other words
                    areas.add(tok)
        for a in sorted(areas):
            terms.setdefault(a, _admin(a))
        self.terms = dict(sorted(terms.items(), key=lambda kv: -len(kv[0])))

    def mentions(self, texts: list[str], skip: tuple = ()) -> list[dict]:
        hay = " ".join(t for t in texts if t)
        found, taken = [], []
        for ko, en in self.terms.items():
            if ko in skip or ko not in hay:
                continue
            if any(ko in t for t in taken):  # 'X도' inside an already listed 'X도해수욕장'
                if hay.count(ko) <= sum(hay.count(t) for t in taken if ko in t):
                    continue
            taken.append(ko)
            found.append({"ko": ko, "en": en})
        return found


def _fact_rows(p: dict, names_row: dict) -> list[dict]:
    facts = p.get("facts") or {}
    rows = []
    for key in [k for k in (*FACT_ORDER, *FIT_ORDER) if k in facts] + [k for k in facts if k not in FACT_ORDER + FIT_ORDER]:
        if key in URL_KEYS:
            continue
        value = display_value(key, facts.get(key))
        alts = (p.get("fact_alternatives") or {}).get(key) or []
        conflict = [a for a in alts if a.get("relation") != "also" and squash_ws(str(a.get("value") or ""))
                    and squash_ws(display_value(key, a["value"])) != squash_ws(value)]
        also = [a for a in alts if a.get("relation") == "also" and squash_ws(str(a.get("value") or ""))]
        if not value and not conflict:
            continue
        row = {"key": key, "label": FACT_LABELS.get(key, key), "value": value}
        if conflict:
            row["alternatives"] = [{"value": display_value(key, a["value"]), "provider": a.get("provider", "")}
                                   for a in conflict]
        if also:
            row["also"] = [{"value": display_value(key, a["value"]), "provider": a.get("provider", "")} for a in also]
        if key == "address":
            row["address_en_candidate"] = names_row.get("addr_en") or address_en(facts.get(key))
        rows.append(row)
    return rows


def place_item(p: dict, names_row: dict, gloss: Glossary, indexable: bool) -> dict:
    item = {"id": p["id"], "slug": p["slug"], "kind": p["kind"], "category": p.get("category", ""),
            "indexable": indexable, "name": p["name"], "name_en": names_row["name_en"],
            "name_en_source": names_row["name_en_source"], "alternate_names": p.get("alternate_names") or [],
            "facts": _fact_rows(p, names_row), "summary": squash_ws(p.get("summary")),
            "details": [{"heading": squash_ws(d.get("heading")), "text": squash_ws(d.get("text"))}
                        for d in p.get("details") or []],
            "faq": [{"q": squash_ws(f.get("q")), "a": squash_ws(f.get("a"))} for f in p.get("faq") or []]}
    texts = [item["summary"], *[d["heading"] + " " + d["text"] for d in item["details"]],
             *[f["q"] + " " + f["a"] for f in item["faq"]]]
    item["mentions"] = gloss.mentions(texts, skip=(p["name"], *(p.get("alternate_names") or []))) if gloss else []
    item["ko_hash"] = _hash({k: item[k] for k in ("name", "facts", "summary", "details", "faq")})
    return item


def guide_item(g: dict, by_slug: dict, names_en: dict, gloss: Glossary) -> dict:
    items = []
    for it in g.get("items") or []:
        p = by_slug.get(it.get("place_slug"))
        items.append({"place_slug": it.get("place_slug", ""), "place_name": p["name"] if p else "",
                      "place_name_en": names_en[p["id"]]["name_en"] if p else "", "reason": squash_ws(it.get("reason"))})
    item = {"id": g["id"], "slug": g["slug"], "label": squash_ws(g.get("label")), "title": squash_ws(g.get("title")),
            "summary": squash_ws(g.get("summary")),
            "body": [{"heading": squash_ws(b.get("heading")), "text": squash_ws(b.get("text"))} for b in g.get("body") or []],
            "items": items, "faq": [{"q": squash_ws(f.get("q")), "a": squash_ws(f.get("a"))} for f in g.get("faq") or []],
            "sources": [{"name": squash_ws(s.get("name")), "url": s.get("url", "")} for s in g.get("sources") or []]}
    texts = [item["title"], item["summary"], *[b["heading"] + " " + b["text"] for b in item["body"]],
             *[i["reason"] for i in items], *[f["q"] + " " + f["a"] for f in item["faq"]]]
    item["mentions"] = gloss.mentions(texts) if gloss else []
    item["ko_hash"] = _hash({k: item[k] for k in ("label", "title", "summary", "body", "items", "faq", "sources")})
    return item


def course_item(c: dict, by_slug: dict, names_en: dict, gloss: Glossary) -> dict:
    stops = []
    for s in c.get("stops") or []:
        p = by_slug.get(s.get("place_slug"))
        stops.append({"name": squash_ws(s.get("name")), "note": squash_ws(s.get("note")),
                      "place_slug": s.get("place_slug") or "", "place_name_en": names_en[p["id"]]["name_en"] if p else "",
                      "name_rr": romanize(s.get("name"))})
    item = {"id": c["id"], "slug": c["slug"], "name": display_value("course_name", c.get("name")),
            "group": squash_ws(c.get("group")), "duration": squash_ws(c.get("duration")),
            "summary": squash_ws(c.get("summary")), "stops": stops}
    item["mentions"] = gloss.mentions([item["name"], item["summary"], *[s["name"] + " " + s["note"] for s in stops]]) \
        if gloss else []
    item["ko_hash"] = _hash({k: item[k] for k in ("name", "group", "duration", "summary", "stops")})
    return item


EVENT_FIELDS = ("name", "period_text", "place_name", "address", "fee", "playtime", "sponsor", "tel")


def event_series(events: list[dict]) -> list[dict]:
    """Series as pipeline.build.event_series groups them (same key and slug rule): dated series only."""
    groups: dict[str, list] = {}
    for ev in events:
        if ev.get("status") != "published":
            continue
        name = squash_ws(ev.get("name"))
        key = normalize_name(YEAR_PREFIX.sub("", squash_ws(ev.get("series")) or name))
        groups.setdefault(key, []).append(ev)
    out, slugs = [], set()
    for key, evs in groups.items():
        dated = sorted((x for x in evs if x.get("start_date")), key=lambda x: (x["start_date"], x.get("end_date") or ""),
                       reverse=True)
        if not dated:
            continue
        newest = dated[0]
        undated = [x for x in evs if not x.get("start_date")]
        name = next((squash_ws(x["series"]) for x in [newest, *evs] if squash_ws(x.get("series"))), "") \
            or YEAR_PREFIX.sub("", squash_ws(newest["name"]))
        slug = base = slugify(name)
        n = 2
        while slug in slugs:
            slug, n = f"{base}-{n}", n + 1
        slugs.add(slug)
        out.append({"key": key, "name": name, "slug": slug, "newest": newest, "editions": dated + undated})
    return out


def event_item(sr: dict, gloss: Glossary) -> dict:
    ev = sr["newest"]
    newest = {"id": ev["id"]}
    for f in EVENT_FIELDS:
        v = squash_ws(ev.get(f))
        if f == "address":
            v = display_address(v)
        if f == "playtime":
            v = display_value("playtime", v)
        if v:
            newest[f] = v
    if newest.get("address"):
        newest["address_en_candidate"] = address_en(ev.get("address"))
    if ev.get("summary"):
        newest["summary"] = squash_ws(ev["summary"])
    newest["notes"] = [squash_ws(n) for n in ev.get("notes") or [] if squash_ws(n)]
    alts = {f: [{"value": squash_ws(a.get("value")), "provider": squash_ws(a.get("source_name"))} for a in vals]
            for f, vals in (ev.get("alternatives") or {}).items() if vals}
    program = next((x for x in sr["editions"] if x.get("highlights")), None)
    usual = []
    for x in sr["editions"]:
        if not x.get("start_date") and "매년" in str(x.get("period_text", "")):
            usual.append({"text": squash_ws(x["period_text"]), "place": squash_ws(x.get("place_name"))})
    usual += [{"text": squash_ws(u.get("text")), "place": squash_ws(u.get("place"))}
              for x in sr["editions"] for u in x.get("usual") or [] if squash_ws(u.get("text"))]
    editions = [{"id": x["id"], "name": squash_ws(x.get("name")), "period_text": squash_ws(x.get("period_text")),
                 "place_name": squash_ws(x.get("place_name"))} for x in sr["editions"] if x is not ev]
    sources: list[str] = []
    for x in sr["editions"]:
        names_ = [x.get("source_name"), *[a.get("name") for a in x.get("also_sources") or []],
                  *[u.get("source_name") for u in x.get("usual") or []],
                  *[a.get("source_name") for vals in (x.get("alternatives") or {}).values() for a in vals]]
        for s in names_:
            s = squash_ws(s)
            if s and s not in sources:
                sources.append(s)
    item = {"id": sr["slug"], "series_name": sr["name"], "newest": newest, "alternatives": alts,
            "highlights": [squash_ws(h) for h in (program or {}).get("highlights") or [] if squash_ws(h)],
            "program_notes": [squash_ws(n) for n in (program or {}).get("notes") or [] if squash_ws(n)]
            if program is not ev else [],
            "usual": usual, "editions": editions, "sources": sources}
    texts = [sr["name"], *[v for v in newest.values() if isinstance(v, str)], *item["highlights"],
             *[u["text"] + " " + u["place"] for u in usual], *[e["name"] + " " + e["place_name"] for e in editions]]
    item["mentions"] = gloss.mentions(texts) if gloss else []
    item["ko_hash"] = _hash({k: item[k] for k in ("series_name", "newest", "alternatives", "highlights",
                                                  "program_notes", "usual", "editions", "sources")})
    return item


def current_hashes(data: Path) -> dict:
    """The ko_hash of every item `prepare` would write from the current Korean data in `data`:
    {"places": {id: hash}, "guides": {id: hash}, "courses": {id: hash}, "events": {series slug: hash}}.
    Same filters as prepare: published places that are not duplicates, published guides and courses, and the
    dated event series of published records. Mentions (the glossary) are not part of a hash, so none is built."""
    places_all = _load(data, "places.json", []) or []
    places = [p for p in places_all if p.get("status") == "published" and not p.get("duplicate_of")]
    names_en = _name_table(data, places)
    by_slug = {p["slug"]: p for p in places}
    guides = [g for g in _load(data, "guides.json", []) or [] if g.get("status") == "published"]
    courses = [c for c in _load(data, "courses.json", []) or [] if c.get("status") == "published"]
    events = _load(data, "events.json", []) or []
    return {"places": {p["id"]: place_item(p, names_en[p["id"]], None, True)["ko_hash"] for p in places},
            "guides": {g["id"]: guide_item(g, by_slug, names_en, None)["ko_hash"] for g in guides},
            "courses": {c["id"]: course_item(c, by_slug, names_en, None)["ko_hash"] for c in courses},
            "events": {sr["slug"]: event_item(sr, None)["ko_hash"] for sr in event_series(events)}}
