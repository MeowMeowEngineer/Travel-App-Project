"""The language versions' content: official names, translation batches, parity checks, merge (CLAUDE.md 3절).

    python tools/en_content.py names [--lang en] [--max-calls 40] [--offline]   # TourAPI EngService2 (JpnService2 …)
                                                                                  #   -> data/incheon/<lang>/names.json
    python tools/en_content.py prepare --out <dir> [--lang en] [--batch 40]     # <lang>-XX.input.json batches
    python tools/en_content.py check <dir>/<lang>-03.output.json [...]          # parity checks, exit 1 on findings
    python tools/en_content.py merge <dir>/<lang>-*.output.json                 # data/incheon/<lang>/{places,guides,…}.json

--lang: en (default) | ja | zh-hans | zh-hant | de | fr | es | ru (pipeline/locales.py). check and merge read the
language from the input batch. English is described below and unchanged; the other languages (section 'the other
languages' near the end) get the same items with their own name fields (official TourAPI name when names --lang
matched one, otherwise written by the translator: name source 'translated'), rules, conflict notes, parity (money,
decimal marks, thousands separators, weekday and month names as the language writes them), style (promotional words,
disclaimers, 24-hour times, full-width punctuation in Japanese and Chinese) and script checks (Chinese script both
ways with OpenCC, kana in Japanese, Cyrillic in Russian, the language of German/French/Spanish prose). Their strings
batch carries the labels from the Korean and the pages' own words (pipeline/intl_text.py) from the English.

The English text is a translation of OUR Korean data (data/incheon/*.json) and nothing else: no new facts, no
general knowledge, no TourAPI overview, nothing from the city tourism site's originals beyond what the Korean already states.

Names: the official English name from TourAPI EngService2 when a place matches (coordinates within 150 m and a
matching content type); otherwise the name in data/incheon/en/names.json — the specific part in Revised Romanization and the generic
part in English after the MCST guideline for public terms (은파호수공원 -> Eunpa Lake Park; business names stay
romanized) — and the plain Revised Romanization (romanize() below) only for a place missing there. The Korean
name is always kept in its own field (name_ko).

Batches (prepare): places first — published and indexable (pipeline.schema.index_status), then the other
published places — then one batch each for guides, courses, event series and site strings (template UI text,
pipeline labels, categories, providers, themes). Every input file carries the `rules` translators follow.

Checks (check; any finding blocks merge)
- parity: every phone, time, won amount, weekday and number of the Korean appears in the English with the same
  digits, and the English adds none. Times stay 24-hour with a two-digit hour ('09:00–18:00', never 9:00 AM);
  money is written '3,000 won' (1만원 -> '10,000 won'; never ₩/KRW); English month names count as their numbers.
- every input item and field translated (counts of details, FAQ, stops, highlights, alternatives …),
  name_en exactly as given, placeholders in UI strings kept
- a fact with values from two sources (non-'also' fact_alternatives) keeps both, with the note
  'Sources differ — call before visiting'
- no Korean script left, no promotional words (best, must-see, famous, popular …), no disclaimers,
  US spelling, no '~', sentences of at most 40 words in prose
"""
from __future__ import annotations

import argparse
import datetime as dt
import json
import os
import re
import sys
from pathlib import Path

if __package__ in (None, ""):
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from pipeline import city, intl_text, tickets
from pipeline import locales as LC
from pipeline.schema import FACT_LABELS, designations, index_status
from pipeline.textutil import extract_phones, normalize_name, squash_ws
# Romanization, the Korean items and their ko_hash live in the pipeline (pipeline/en_site.py recomputes the hashes
# at build time to skip stale translations); re-exported here for the commands and tests below.
from pipeline.en_source import (CONFLICT_NOTE, EVENT_CONFLICT_NOTE, EVENT_FIELDS, HANGUL, URL_KEYS,  # noqa: F401
                                YEAR_PREFIX, Glossary, _admin, _boundary, _fact_rows, _hash, _load, _name_table,
                                _road, _rr_cap, _rr_run, _syllables, address_en, course_item, event_item,
                                event_series, guide_item, place_item, romanize)

ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "data" / "incheon"
EN_BASE_URL = "https://apis.data.go.kr/B551011/EngService2"
MATCH_RADIUS_M = 150


# ------------------------------------------------------------------ TourAPI EngService2 names
# English-service content types differ from the Korean ones (KorService 12/14/28/38/32/39/15).
EN_TYPE_KO = {"76": "12", "78": "14", "75": "28", "79": "38", "80": "32", "82": "39", "85": "15"}
KIND_BY_KO_TYPE = {"12": "attraction", "14": "attraction", "28": "attraction", "38": "attraction",
                   "32": "stay", "39": "food"}


def _letters(s: str) -> str:
    return re.sub(r"[^a-z]", "", (s or "").lower())


def _title_ko(title: str) -> str:
    """Korean in an English title: '○○do Island (○○도)' -> '○○도'."""
    m = re.search(r"\(([^()]*[가-힣][^()]*)\)", title or "")
    return m.group(1) if m else ""


def match_en(place: dict, items: list[dict], latin: bool = True) -> tuple[dict | None, float | None, str]:
    """English list item for one place: within MATCH_RADIUS_M and of the place's kind (the same content type
    when the place has a Korean TourAPI type). One candidate is taken; several are separated by the Korean name
    in the English title, then by a shared photo file, then by the romanized name; anything else stays
    unmatched (romanized name used instead)."""
    from difflib import SequenceMatcher
    from pipeline.enrich import haversine_m
    geo = place.get("geo") or {}
    if geo.get("lat") is None or geo.get("lng") is None:
        return None, None, ""
    ko_type = str((place.get("tourapi") or {}).get("contenttypeid") or "")
    cands = []
    for it in items:
        t = EN_TYPE_KO.get(str(it.get("contenttypeid")))
        if not t or KIND_BY_KO_TYPE.get(t) != place.get("kind") or (ko_type and t != ko_type):
            continue
        try:
            d = haversine_m(geo["lat"], geo["lng"], float(it["mapy"]), float(it["mapx"]))
        except (KeyError, TypeError, ValueError):
            continue
        if d <= MATCH_RADIUS_M:
            cands.append((d, it))
    cands.sort(key=lambda x: x[0])
    if not cands:
        return None, None, ""
    names = {normalize_name(n) for n in [place.get("name"), *(place.get("alternate_names") or []),
                                         (place.get("tourapi") or {}).get("title")] if n}
    hit = [(d, it) for d, it in cands if normalize_name(_title_ko(it.get("title"))) in names]
    if len(hit) == 1:
        return hit[0][1], hit[0][0], "coordinates_type_korean_title"
    files = {i.get("url", "").rsplit("/", 1)[-1] for i in place.get("images") or [] if i.get("source") == "TourAPI"}
    hit = [(d, it) for d, it in cands if (it.get("firstimage") or "").rsplit("/", 1)[-1] in files - {""}]
    if len(hit) == 1:
        return hit[0][1], hit[0][0], "coordinates_type_same_photo"
    if len(cands) == 1:
        return cands[0][1], cands[0][0], "coordinates_type"
    if not latin:   # Japanese, Chinese and Russian titles: no romanized-name test
        return None, None, "ambiguous"
    rr = _letters(romanize(place.get("name")))
    scored = sorted(((SequenceMatcher(None, rr, _letters(re.sub(r"\(.*?\)", "", it.get("title") or ""))).ratio(), d, it)
                     for d, it in cands), key=lambda x: -x[0])
    if scored[0][0] >= 0.6 and (len(scored) == 1 or scored[0][0] - scored[1][0] >= 0.2):
        return scored[0][2], scored[0][1], "coordinates_type_romanized_name"
    return None, None, "ambiguous"


def names(data: Path = DATA, max_calls: int = 40, offline: bool = False, lang: str = "en") -> dict:
    """List every English-service item in the region (all content types, paged), match published places,
    write data/<region>/en/names.json {place_id: {...}}. On a provider error the message (key masked) is reported
    and every place keeps its romanized name. Another language: names_l()."""
    if lang != "en":
        return names_l(data, max_calls, offline, LC.get(lang).code)
    from pipeline.enrich import load_dotenv
    from pipeline.tourapi import TourAPI, TourAPIError, TourAPIStopError, from_site_config
    from tools.tourapi_bulk import RegionError, region_codes, retry
    load_dotenv(ROOT / ".env")
    site = json.loads((data / "site.json").read_text("utf-8"))
    places = [p for p in json.loads((data / "places.json").read_text("utf-8")) if p.get("status") == "published"]
    cache = data.parent / "cache" / "tourapi"
    key = os.environ.get("TOURAPI_KEY", "")
    stats = {"service": EN_BASE_URL, "list_items": 0, "live_calls": 0, "cache_hits": 0, "error": "",
             "matched": 0, "matched_by": {}, "ambiguous": [], "published": len(places)}
    items: list[dict] = []
    try:
        kor = from_site_config(site, key, cache, offline=offline, max_calls=4)  # statutory codes (cached)
        regn, signgus, _ = region_codes(kor, site)   # the city's 시군구 (a 광역시: every 구·군), tools/tourapi_bulk.py
        api = TourAPI(key, base_url=EN_BASE_URL, mobile_app=(site.get("tourapi") or {}).get("mobile_app", "WebforAI"),
                      cache_dir=cache, offline=offline, max_calls=max_calls)
        try:
            for signgu, _ in signgus:
                page = 1
                while True:
                    got = retry(api.call, "areaBasedList", lDongRegnCd=regn, lDongSignguCd=signgu, numOfRows=200,
                                pageNo=page, arrange="A")
                    items += got
                    if len(got) < 200:
                        break
                    page += 1
        finally:
            stats["live_calls"], stats["cache_hits"] = api.live_calls + kor.live_calls, api.cache_hits + kor.cache_hits
    except (TourAPIError, TourAPIStopError, StopIteration, RegionError) as err:
        stats["error"] = str(err) or type(err).__name__
    stats["list_items"] = len(items)
    out = {}
    for p in places:
        it, dist, basis = match_en(p, items) if items else (None, None, "")
        rr = romanize(p["name"])
        row = {"name_ko": p["name"], "name_en": rr, "name_en_source": "romanized", "name_rr": rr,
               "en_contentid": "", "addr_en": "", "match_m": None, "match_basis": ""}
        if it:
            title = squash_ws(re.sub(r"\s*\([^()]*[가-힣][^()]*\)", "", it.get("title") or ""))
            row.update({"name_en": title or rr, "name_en_source": "TourAPI EngService2" if title else "romanized",
                        "en_contentid": str(it.get("contentid", "")), "addr_en": squash_ws(it.get("addr1")),
                        "match_m": round(dist, 1), "match_basis": basis})
            stats["matched"] += 1
            stats["matched_by"][basis] = stats["matched_by"].get(basis, 0) + 1
        elif basis == "ambiguous":
            stats["ambiguous"].append(p["name"])
        out[p["id"]] = row
    (data / "en").mkdir(exist_ok=True)
    (data / "en" / "names.json").write_text(json.dumps(out, ensure_ascii=False, indent=2) + "\n", "utf-8")
    return stats


# ------------------------------------------------------------------ prepare
RULES = {
    "source": "Translate only the Korean in this file. No new facts, no general knowledge, nothing from other "
              "sites or from the TourAPI overview. If the Korean does not say it, the English does not say it.",
    "style": "Answer-first plain US English; short sentences (40 words at most). No superlatives or promotional "
             "words (best, must-see, must-visit, famous, popular, amazing, stunning, hidden gem, iconic, renowned). "
             "No disclaimers. No Korean script anywhere in English fields.",
    "names": "The place itself: name_en exactly as given (copy it to the output; do not translate or re-spell it). "
             "Other places, areas and courses: the 'mentions' table. Other proper nouns: Revised Romanization, "
             "with the generic part of a place name in English (Eunpa Lake Park, Dongguksa Temple; MCST guideline).",
    "numbers": "Every number keeps its digits. Times are 24-hour with a two-digit hour and an en dash: "
               "09:00–18:00 (never 9:00 or AM/PM). Money: '3,000 won' (1만원 -> '10,000 won'; never ₩ or KRW). "
               "Dates: 'October 9, 2026' (or keep ISO 2026-10-09). Phones exactly as in the Korean. Keep the "
               "Korean unit (110 m, 1.7 km, 9,907 pyeong); no conversions. A number the Korean writes as a word "
               "stays a word (두 곳 -> two places). Ranges use an en dash, never '~'.",
    "weekdays": "Full day names: 매주 월요일 -> every Monday; 토·일요일 -> Saturday and Sunday.",
    "conflicts": f"A fact with 'alternatives' (two sources disagree): translate the main value and every "
                 f"alternative in the same order, and set note to exactly '{CONFLICT_NOTE}'. Events use "
                 f"'{EVENT_CONFLICT_NOTE}'. Never pick one side.",
    "faq": "Same number of questions and answers, same order; each question ends with '?'.",
    "address": "Use address_en_candidate when it is given; otherwise write '<number> <Road>, <eup/myeon/dong>, "
               "<the city's English address tail>' with Revised Romanization and every digit kept.",
}

TAIL_MARK = "<the city's English address tail>"


def city_fill(obj):
    """The rules and examples with the city's English address tail (site.json city.intl.en.address.tail) in place of
    TAIL_MARK; the mark stays when the city has none (the translator then writes the city as the Korean names it)."""
    tail = ((city.current().intl("en").get("address") or {}).get("tail") or "").strip()
    if not tail:
        return obj
    return json.loads(json.dumps(obj, ensure_ascii=False).replace(TAIL_MARK, tail.replace('"', "")))


PLACE_OUTPUT_EXAMPLE = {
    "id": "place-0001", "name_en": "Hosu Park",
    "summary": "Hosu Park is a lakeside park ...",
    "facts": [{"key": "address", "value": "26 Hosugongwon 1-gil, <the city's English address tail>"},
              {"key": "usetime", "value": "09:00–18:00", "alternatives": [{"value": "Always open"}], "note": CONFLICT_NOTE},
              {"key": "usefee", "value": "Free"}],
    "details": [{"heading": "...", "text": "..."}],
    "faq": [{"q": "Do I need to pay to enter Hosu Park?", "a": "No. Admission is free, and parking is available."}],
}


# ---- site strings: template UI text and pipeline labels
_JINJA = re.compile(r"\{\{.*?\}\}|\{%.*?%\}", re.S)
_LITERAL = re.compile(r"'([^'\n]*[가-힣][^'\n]*)'|\"([^\"\n]*[가-힣][^\"\n]*)\"")
_ATTR = re.compile(r"([\w:-]+)=\"([^\"]*)\"")


def template_strings(path: Path) -> list[dict]:
    """Visible Korean in one Jinja template: text nodes and attribute values ({{ … }} -> {0}, {1} …) and
    Korean string literals inside {{ }} / {% %}."""
    src = re.sub(r"\{#.*?#\}", "", path.read_text("utf-8"), flags=re.S)
    out: list[dict] = []
    exprs: list[str] = []

    def keep(text: str, where: str):
        vars_: list[str] = []

        def ph(m):
            vars_.append(exprs[int(m.group(1))])
            return "{" + str(len(vars_) - 1) + "}"
        t = squash_ws(re.sub(r"\x01(\d+)\x01", ph, text))
        t = t.strip(" ·|—-")
        if HANGUL.search(t) and not re.fullmatch(r"[가-힣]+/[가-힣]+", t):  # josa pairs ('은/는') are code
            out.append({"ko": t, "vars": vars_, "where": f"{path.name} {where}"})

    for m in _JINJA.finditer(src):
        for lit in _LITERAL.finditer(m.group(0)):
            keep(lit.group(1) or lit.group(2), "jinja literal")

    def sub(m):
        tok = m.group(0)
        if tok.startswith("{%"):
            return "\x02"
        exprs.append(squash_ws(tok[2:-2]))
        return f"\x01{len(exprs) - 1}\x01"
    body = _JINJA.sub(sub, src)
    for tag in re.finditer(r"<[^>]*>", body):
        for a in _ATTR.finditer(tag.group(0)):
            if a.group(1) not in ("href", "src", "class", "id", "data-track", "data-key", "data-place", "data-provider"):
                keep(a.group(2), f"attribute {a.group(1)}")
    for chunk in re.split(r"<[^>]*>|\x02|\n", body):
        keep(chunk, "text")
    return out


def pipeline_strings() -> list[dict]:
    from pipeline import build as B, city, present as PR, schema as SC
    C = city.current()   # the city's own labels (site.json city: purposes, travel_regions)
    rows: list[dict] = []

    def add(id_, ko, where):
        if ko and HANGUL.search(str(ko)):
            rows.append({"id": id_, "ko": str(ko), "where": where})
    for k, v in SC.KIND_LABELS.items():
        add(f"KIND_LABELS.{k}", v, "pipeline/schema.py")
    for k, v in SC.FACT_LABELS.items():
        add(f"FACT_LABELS.{k}", v, "pipeline/schema.py")
    for k, v in SC.INDEX_GROUP_LABELS.items():
        add(f"INDEX_GROUP_LABELS.{k}", v, "pipeline/schema.py")
    for k, v in B.TITLE_LABELS.items():
        add(f"TITLE_LABELS.{k}", v, "pipeline/build.py")
    for kind, cfg in B.LISTS.items():
        for f in ("title", "h1", "seo", "lead"):
            add(f"LISTS.{kind}.{f}", cfg.get(f), "pipeline/build.py")
    for i, (name, _) in enumerate(B.ATTRACTION_GROUPS):
        add(f"ATTRACTION_GROUPS.{i}", name, "pipeline/build.py")
    for i, (label, _, _, note) in enumerate(C.get("purposes", []) or []):
        add(f"PURPOSES.{i}.label", label, "site.json city.purposes")
        add(f"PURPOSES.{i}.note", note, "site.json city.purposes")
    for k, v in B.ALT_LABELS.items():
        add(f"ALT_LABELS.{k}", v, "pipeline/build.py")
    for i, v in enumerate(B.VIDEO_TOPICS):
        add(f"VIDEO_TOPICS.{i}", v, "pipeline/build.py")
    for i, (label, *_) in enumerate(PR.NAV):
        add(f"NAV.{i}", label, "pipeline/present.py")
    for i, r in enumerate(C.regions):
        add(f"REGIONS.{i}", r.name, "site.json city.travel_regions")
    add("FAR_LABEL", C.far_label, "site.json city.travel_regions")
    add("NONE_LABEL", C.none_label, "site.json city.travel_regions")
    for name in ("STAY_TYPE", "FOOD_TYPE", "ATTR_TYPE", "STATUS_PREFIX", "CONTEST_LABEL", "STOP_KIND_LABELS"):
        for k, v in getattr(PR, name).items():
            add(f"{name}.{k}", v, "pipeline/present.py")
    for i, v in enumerate(PR.STAY_ASK):
        add(f"STAY_ASK.{i}", v, "pipeline/present.py")
    for kind, cfg in PR.LIST_CFG.items():
        add(f"LIST_CFG.{kind}.title", cfg["title"], "pipeline/present.py")
        for key, label in cfg["cols"]:
            add(f"LIST_CFG.{kind}.cols.{key}", label, "pipeline/present.py")
        add(f"LIST_CFG.{kind}.check", cfg["check"][1], "pipeline/present.py")
    for k, (label, _) in PR.LIC.items():
        add(f"LIC.{k}", label, "pipeline/present.py")
    add("CALL_LINE", PR.CALL_LINE, "pipeline/present.py")
    add("ORGANISER_LINE", PR.ORGANISER_LINE, "pipeline/present.py")
    add("CONFLICT.sources_differ", "출처마다 다름", "pipeline/present.py conflict_label")
    add("CONFLICT.hours_only", "영업시간만 다름", "pipeline/present.py conflict_label")
    return rows


def strings_items(data: Path, places: list[dict]) -> list[dict]:
    site = _load(data, "site.json", {})
    city.activate(site)
    rows = pipeline_strings()
    for f in ("site_name", "description", "disclaimer"):
        rows.append({"id": f"site.{f}", "ko": squash_ws(site.get(f)), "where": "data/incheon/site.json",
                     **({"note": "Brand name: translate literally; the owner decides the English brand."}
                        if f == "site_name" else {})})
    rows.append({"id": "site.operator.name", "ko": squash_ws((site.get("operator") or {}).get("name")),
                 "where": "data/incheon/site.json", "note": "Company name: Revised Romanization; the owner confirms."})
    for i, link in enumerate(site.get("official_links") or []):
        rows.append({"id": f"site.official_links.{i}.name", "ko": squash_ws(link.get("name")), "where": "site.json"})
        rows.append({"id": f"site.official_links.{i}.note", "ko": squash_ws(link.get("note")), "where": "site.json"})
    for t in _load(data, "themes.json", []):
        rows.append({"id": f"theme.{t['slug']}.name", "ko": squash_ws(t.get("name")), "where": "data/incheon/themes.json"})
        rows.append({"id": f"theme.{t['slug']}.description", "ko": squash_ws(t.get("description")),
                     "where": "data/incheon/themes.json"})
    cats, provs = [], []
    for p in places:
        c = squash_ws(p.get("category"))
        if c and c not in cats:
            cats.append(c)
        srcs = [p.get("facts_source") or {}, *(p.get("fact_sources") or {}).values(),
                *[a for alts in (p.get("fact_alternatives") or {}).values() for a in alts]]
        srcs += [{"provider": f.get("source")} for f in p.get("faq") or [] if not str(f.get("source", "")).startswith("http")]
        for s in srcs:
            v = squash_ws(s.get("provider"))
            if v and v not in provs:
                provs.append(v)
    rows += [{"id": f"category:{c}", "ko": c, "where": "places.json category (list/type labels)"} for c in cats]
    rows += [{"id": f"provider:{v}", "ko": v, "where": "places.json fact source provider"} for v in provs]
    # official designations the Korean pages show (schema.designations): the label and the list's name, keyed by the
    # Korean text like category:/provider: (en_site.En.designations; a label without both strings is not shown)
    dz_labels, dz_lists = [], []
    for p in places:
        for d in designations(p):
            if d["label"] not in dz_labels:
                dz_labels.append(d["label"])
            if squash_ws(d["source_name"]) not in dz_lists:
                dz_lists.append(squash_ws(d["source_name"]))
    rows += [{"id": f"designation:{v}", "ko": v, "where": "places.json designations label (official list name)",
              "note": "Official designation: keep the list's own name and its designating body; keep any year."}
             for v in dz_labels]
    rows += [{"id": f"designation_source:{v}", "ko": v, "where": "places.json designations source_name (the list)"}
             for v in dz_lists]
    # combined tickets: each ticket's name and the short '통합권' (en_site.fee_pair: a place's fee tile sets the
    # ticket's price beside its own, under the ticket's name in the language, or the short name when that is long)
    names = [squash_ws(t.get("name")) for t in (_load(data, "tickets.json", {}) or {}).get("tickets") or []]
    rows += [{"id": f"ticket:{v}", "ko": v, "where": "tickets.json ticket name (fee tile)",
              "note": "A ticket for several museums: as the places' own fee tables name it in this language."}
             for v in [*names, "통합권"] if v] if names else []
    # the words of a ticket's table on the facts card (en_site.ticket_rows), as the places' own fee tables write them
    rows += [{"id": f"ticket:{v}", "ko": v, "where": "tickets.json price table (facts card)",
              "note": "A word of a museum ticket's price table: as the places' own fee tables write it in this language."}
             for v in tickets.table_words()] if names else []
    seen: dict[str, dict] = {}
    for path in sorted((ROOT / "templates").glob("*.j2")):
        for s in template_strings(path):
            if s["ko"] in seen:
                seen[s["ko"]]["where"] += f"; {s['where']}"
                continue
            seen[s["ko"]] = {"id": f"ui:{s['ko']}", "ko": s["ko"], "where": s["where"],
                             **({"vars": s["vars"]} if s["vars"] else {})}
    rows += list(seen.values())
    out, ids = [], set()
    for r in rows:
        if r["ko"] and HANGUL.search(r["ko"]) and r["id"] not in ids:
            ids.add(r["id"])
            out.append(r)
    return out


def prepare(out: Path, batch: int = 40, data: Path = DATA, lang: str = "en") -> dict:
    if lang != "en":
        return prepare_l(out, batch, data, LC.get(lang).code)
    places_all = json.loads((data / "places.json").read_text("utf-8"))
    places = [p for p in places_all if p.get("status") == "published" and not p.get("duplicate_of")]
    names_en = _name_table(data, places)
    courses = [c for c in _load(data, "courses.json", []) if c.get("status") == "published"]
    guides = [g for g in _load(data, "guides.json", []) if g.get("status") == "published"]
    events = _load(data, "events.json", [])
    gloss = Glossary(places, names_en, courses)
    by_slug = {p["slug"]: p for p in places}
    order = {"attraction": 0, "food": 1, "stay": 2}
    flagged = [(p, index_status(p)[0]) for p in places]
    flagged.sort(key=lambda x: (not x[1], order.get(x[0]["kind"], 9), x[0].get("tier") != "full", x[0]["name"]))
    city.activate_dir(data)   # the city's English address tail in the rules and examples (city_fill)
    out.mkdir(parents=True, exist_ok=True)
    for old in out.glob("en-*.input.json"):
        old.unlink()
    files: list[dict] = []

    def write(kind: str, items: list[dict], example: dict):
        n = len(files) + 1
        path = out / f"en-{n:02d}.input.json"
        payload = {"type": kind, "rules": city_fill(RULES), "output_file": f"en-{n:02d}.output.json",
                   "output_example": city_fill(example), "items": items}
        path.write_text(json.dumps(payload, ensure_ascii=False, indent=1) + "\n", "utf-8")
        chars = sum(len(HANGUL.findall(json.dumps(i, ensure_ascii=False))) for i in items)
        files.append({"file": str(path), "type": kind, "items": len(items), "hangul_chars": chars,
                      **({"indexable": sum(1 for i in items if i.get("indexable"))} if kind == "places" else {})})

    for i in range(0, len(flagged), batch):
        write("places", [place_item(p, names_en[p["id"]], gloss, ok) for p, ok in flagged[i:i + batch]],
              PLACE_OUTPUT_EXAMPLE)
    write("guides", [guide_item(g, by_slug, names_en, gloss) for g in guides], OUTPUT_EXAMPLES["guides"])
    write("courses", [course_item(c, by_slug, names_en, gloss) for c in courses], OUTPUT_EXAMPLES["courses"])
    write("events", [event_item(sr, gloss) for sr in event_series(events)], OUTPUT_EXAMPLES["events"])
    write("strings", strings_items(data, places), OUTPUT_EXAMPLES["strings"])
    return {"batches": files, "places": len(flagged), "indexable": sum(1 for _, ok in flagged if ok)}


OUTPUT_EXAMPLES = {
    "guides": {"id": "guide-01", "label": "Car-free trip", "title": "...", "summary": "...",
               "body": [{"heading": "...", "text": "..."}], "items": [{"place_slug": "근대역사박물관", "reason": "..."}],
               "faq": [{"q": "...?", "a": "..."}], "sources": [{"name": "..."}]},
    "courses": {"id": "course-0001", "name": "Course 1 Modern Cultural Heritage Tour", "group": "...",
                "duration": "", "summary": "...", "stops": [{"name": "Geundaeyeoksabangmulgwan", "note": ""}]},
    "events": {"id": "음식축제", "series_name": "Food Festival",
               "newest": {"name": "2026 Food Festival", "period_text": "October 9 (Fri)–October 11 (Sun), 2026, 3 days",
                          "place_name": "...", "address": "...", "fee": "Free", "playtime": "12:00–22:00",
                          "sponsor": "...", "tel": "063-454-3912, 3913", "notes": ["..."]},
               "alternatives": {"fee": {"values": ["..."], "note": EVENT_CONFLICT_NOTE}},
               "highlights": ["..."], "program_notes": [], "usual": [{"text": "...", "place": "..."}],
               "editions": [{"id": "event-…", "name": "...", "period_text": "...", "place_name": "..."}],
               "sources": ["..."]},
    "strings": {"id": "FACT_LABELS.usetime", "en": "Hours"},
}


# ------------------------------------------------------------------ check
BANNED = re.compile(r"\b(best|must[- ]see|must[- ]visit|must[- ]try|famous|popular|amazing|stunning|hidden gems?|"
                    r"iconic|renowned|breathtaking|world[- ]class|picturesque|unmissable)\b", re.I)
DISCLAIMER = re.compile(r"\b(disclaimer|subject to change|may vary|please note|for reference only|not responsible|"
                        r"at your own risk)\b", re.I)
BRITISH = re.compile(r"\b(centres?|colours?|metres?|kilometres?|programmes?|travell(?:ing|ed|ers?)|"
                     r"harbours?|neighbourhoods?|theatres?|favourites?|organis(?:e|ed|es|ing|ation)|catalogue|licence|"
                     r"jewellery|grey|storeys?|car parks?|tyres?|cheques?)\b", re.I)
AMPM = re.compile(r"\b\d{1,2}(?::\d{2})?\s*(?:a\.?m\.?|p\.?m\.?)(?![a-z])", re.I)
EN_TIME = re.compile(r"(?<![\d:])(\d{1,2}):(\d{2})(?![\d:])")
KO_TIME = re.compile(r"(?<![\d:])(\d{1,2}):(\d{2})(?![\d:])")
KO_HOUR = re.compile(r"(오전|오후|낮|밤|저녁|새벽|아침)?\s*(?<![\d.])(\d{1,2})시"
                     r"(?=$|[^가-힣]|까지|부터|에|반|쯤|경|전|후|이후|이전|와|과|로|이나|정각|께|\s*\d{1,2}\s*분|"
                     r"이고|입니다|이며|이다|이에요|예요|이라|이었|였|(?:가|은|는|도|을|를)(?![가-힣]))"
                     r"(?:\s*(\d{1,2})\s*분|\s*(반))?")
WON_EN = re.compile(r"(\d[\d,]*)\s*won\b")
# an amount never starts inside a time and never ends in a comma: '14:00~17:00, 원풍갈비' is a time and a name, not
# 0 won (review 2026-10-14, zh-hans)
WON_KO = re.compile(r"(?<![\d:])(\d(?:[\d,]*\d)?)\s*원")
MONTHS = {m: i + 1 for i, m in enumerate(("january", "february", "march", "april", "may", "june", "july", "august",
                                          "september", "october", "november", "december"))}
MONTHS.update({"jan": 1, "feb": 2, "mar": 3, "apr": 4, "jun": 6, "jul": 7, "aug": 8, "sep": 9, "sept": 9, "oct": 10,
               "nov": 11, "dec": 12})
EN_MONTH = re.compile(r"\b(January|February|March|April|May|June|July|August|September|October|November|December|"
                      r"Jan|Feb|Mar|Apr|Jun|Jul|Aug|Sept|Sep|Oct|Nov|Dec)\b\.?")
DAYS_EN = ("monday", "tuesday", "wednesday", "thursday", "friday", "saturday", "sunday")
EN_DAY = re.compile(r"\b(Mon|Tues?|Wed|Thu(?:rs?)?|Fri|Sat|Sun)(?:day)?s?\b\.?|\b(Wednes|Satur)days?\b")
KO_WEEK = "월화수목금토일"
KO_DAY_CHAIN = re.compile(r"((?:[월화수목금토일]\s*[·,~∼～\-]\s*)*[월화수목금토일])요일")
KO_DAY_BARE = re.compile(r"(?<![가-힣])([월화수목금토일](?:\s*[·,~∼～\-]\s*[월화수목금토일])+)(?=[은는에]|[^가-힣]|$)")
KO_DAY_PAREN = re.compile(r"\(([월화수목금토일])\)")
KO_DAY_LONE = re.compile(r"(?<![가-힣\d])([월화수목금토일])[은는]?\s*(?=\d{1,2}:\d{2})")  # '금 11:00', '금은 11:00'
_BIG = {"억": 100_000_000, "만": 10_000, "천": 1_000}
# a big-number unit never follows a time's minutes: '07:00~16:00만 엽니다' is 'only 07:00–16:00', not 0 × 10,000
KO_BIG = re.compile(r"(?<![\d:])((?:\d(?:[\d,]*\d)?(?:\.\d+)?\s*여?\s*[억만천](?!\s*\d+\s*세)\s*)+)(\d[\d,]*)?(?=\s*(?:원|명|개|평|㎡|여|곳|권|마리|그루|송이|대|석|실|"
                    r"m|km|$|[\s,.)·~\-]))")
EN_BIG = re.compile(r"(\d+(?:\.\d+)?)\s*(million|billion)\b", re.I)
WORDS_MAX = 40


def _num(s: str) -> str:
    """'09' -> '9', '3,000' -> '3000', '1.50' -> '1.5'."""
    s = s.replace(",", "")
    if "." in s:
        a, b = s.split(".", 1)
        return (a.lstrip("0") or "0") + "." + (b.rstrip("0") or "0")
    return s.lstrip("0") or "0"


def _ko_big(text: str) -> str:
    """'1만원' -> '10000원', '2만 5천원' -> '25000원', '30억 원' -> '3000000000 원', '70여만 평' -> '700000 평'.
    Not a unit: '만' of an age ('만 19세') and a number that ends a list item ('8.7, 만 19세')."""
    def rep(m):
        total = 0.0
        for n, unit in re.findall(r"(\d(?:[\d,]*\d)?(?:\.\d+)?)\s*여?\s*([억만천])", m.group(1)):
            total += float(n.replace(",", "")) * _BIG[unit]
        if m.group(2):
            total += float(m.group(2).replace(",", ""))
        return str(int(round(total)))
    return KO_BIG.sub(rep, text)


def _en_big(text: str) -> str:
    return EN_BIG.sub(lambda m: str(int(round(float(m.group(1)) * (1e6 if m.group(2).lower() == "million" else 1e9)))), text)


def _numbers(text: str) -> tuple[set[str], set[str]]:
    """(integers, decimals) left in a text after phones, times and money were taken out."""
    decimals, ints = set(), set()
    for chain in re.findall(r"\d[\d,]*(?:\.\d+)+", text):
        grouped = re.fullmatch(r"\d{1,3}(?:,\d{3})+\.\d+", chain)   # '1,868.7' (an area): one decimal number
        if grouped or (chain.count(".") == 1 and not re.search(r",\d{3}\.", chain)
                       and not re.fullmatch(r"\d{4}\.\d{1,2}", chain)):
            decimals.add(chain.replace(",", ""))  # raw: '10.10' may be October 10
        else:
            ints.update(_num(x) for x in re.split(r"\.", chain) if x)
        text = text.replace(chain, " ", 1)
    for n in re.findall(r"\d+(?:,\d{3})+|\d+", text):
        ints.add(_num(n))
    return ints, decimals


def _ko_days(text: str) -> tuple[set[str], set[str]]:
    """(stated weekdays, weekdays a faithful English may also name: ranges' insides, 주말, 평일)."""
    stated, allowed = set(), set()

    def chain(s: str):
        days = [KO_WEEK.index(c) for c in s if c in KO_WEEK]
        stated.update(DAYS_EN[d] for d in days)
        for a, sep, b in re.findall(r"([월화수목금토일])\s*([~∼～\-])\s*([월화수목금토일])", s):
            i, j = KO_WEEK.index(a), KO_WEEK.index(b)
            rng = range(i, j + 1) if i <= j else [*range(i, 7), *range(0, j + 1)]
            allowed.update(DAYS_EN[d] for d in rng)
    for m in KO_DAY_CHAIN.finditer(text):
        chain(m.group(1))
    for m in KO_DAY_BARE.finditer(text):
        chain(m.group(1))
    for m in KO_DAY_PAREN.finditer(text):
        stated.add(DAYS_EN[KO_WEEK.index(m.group(1))])
    if "주말" in text:
        allowed.update(("saturday", "sunday"))
    if "평일" in text:
        allowed.update(DAYS_EN[:5])
    return stated, stated | allowed


def _en_days(text: str) -> tuple[set[str], set[str]]:
    """(named weekdays, weekdays covered incl. ranges 'Monday–Friday', 'weekends', 'weekdays')."""
    named = set()
    for m in EN_DAY.finditer(text):
        w = (m.group(1) or m.group(2) or "").lower()
        day = next((d for d in DAYS_EN if d.startswith(w[:3])), None)
        if day:
            named.add(day)
    covered = set(named)
    rx = r"\b(Mon|Tue|Wed|Thu|Fri|Sat|Sun)[a-z]*\.?\s*(?:–|-|to|through)\s*(Mon|Tue|Wed|Thu|Fri|Sat|Sun)[a-z]*"
    for a, b in re.findall(rx, text):
        i = next(n for n, d in enumerate(DAYS_EN) if d.startswith(a.lower()))
        j = next(n for n, d in enumerate(DAYS_EN) if d.startswith(b.lower()))
        rng = range(i, j + 1) if i <= j else [*range(i, 7), *range(0, j + 1)]
        covered.update(DAYS_EN[d] for d in rng)
    if re.search(r"\bweekends?\b", text, re.I):
        covered.update(("saturday", "sunday"))
    if re.search(r"\bweekdays\b", text, re.I):
        covered.update(DAYS_EN[:5])
    if re.search(r"\bevery day\b|\bdaily\b", text, re.I):
        covered.update(DAYS_EN)
    return named, covered


def _times_ko(text: str) -> tuple[list[set[str]], str]:
    """Each Korean time as the set of 24-hour forms it may be written as; the text with the times taken out."""
    found: list[set[str]] = []

    def hm(h: int, m: int) -> str:
        return f"{h:02d}:{m:02d}"
    for m in KO_TIME.finditer(text):
        found.append({hm(int(m.group(1)), int(m.group(2)))})
    text = KO_TIME.sub(" ", text)

    def rep(m):
        ampm, h, mi = m.group(1), int(m.group(2)), int(m.group(3) or (30 if m.group(4) else 0))
        if h > 24 or mi > 59:
            return m.group(0)
        if ampm in ("오후", "저녁", "밤") and h < 12:
            opts = {hm(h + 12, mi)}
        elif ampm in ("오전", "새벽", "아침") or h >= 12:
            opts = {hm(h, mi)}
        else:
            opts = {hm(h, mi), hm(h + 12, mi)} if h < 12 else {hm(h, mi)}
        found.append(opts)
        return " "
    return found, KO_HOUR.sub(rep, text)


# titles whose 'N시' is part of a name, not a clock time (KBS 6시 내고향 -> '6si Nae Gohyang'); the digit still counts
NOT_A_TIME = re.compile(r"(\d{1,2})시(\s*내\s*고향)")


def parity(ko: str, en: str) -> list[str]:
    """Every phone, time, won amount, weekday and number of `ko` in `en` with the same digits, and none added."""
    issues: list[str] = []
    ko = NOT_A_TIME.sub(r"\1 \2", ko or "")
    ko, en = squash_ws(ko), squash_ws(en)
    if not ko:
        return issues
    if not en:
        return ["English is empty"]
    # phones
    kp, ep = extract_phones(ko), extract_phones(en)
    issues += [f"phone {p} missing" for p in kp if p not in ep]
    issues += [f"phone {p} not in Korean" for p in ep if p not in kp]
    for p in set(kp) | set(ep):
        ko, en = ko.replace(p, " "), en.replace(p, " ")
    # money
    ko = _ko_big(ko)
    en = _en_big(en)
    k_won = {_num(x) for x in WON_KO.findall(ko)}
    e_won = {_num(x) for x in WON_EN.findall(en)}
    issues += [f"amount {int(x):,} won missing" for x in sorted(k_won - e_won, key=float)]
    issues += [f"amount {x} won not in Korean" for x in sorted(e_won - k_won, key=float)]
    ko, en = WON_KO.sub(" ", ko), WON_EN.sub(" ", en)
    # times (a lone weekday right before a time, '금 11:00', is read first: the times are taken out here)
    lone = {DAYS_EN[KO_WEEK.index(d)] for d in KO_DAY_LONE.findall(ko)}
    k_times, ko = _times_ko(ko)
    e_times = {f"{int(h):02d}:{m}" for h, m in EN_TIME.findall(en)}
    issues += [f"time {sorted(opts)[0]} missing" for opts in k_times if not opts & e_times]
    k_all = set().union(*k_times) if k_times else set()
    issues += [f"time {t} not in Korean" for t in sorted(e_times - k_all)]
    en = EN_TIME.sub(" ", en)
    # weekdays
    k_stated, k_allowed = _ko_days(ko)
    k_stated, k_allowed = k_stated | lone, k_allowed | lone
    e_named, e_covered = _en_days(en)
    issues += [f"weekday {d.title()} missing" for d in sorted(k_stated - e_covered)]
    issues += [f"weekday {d.title()} not in Korean" for d in sorted(e_named - k_allowed)]
    # numbers (English month names count as their numbers)
    def month(m):
        word = m.group(1)
        if word == "May" and not re.search(r"(?:\d|–|-|to|through|and|until|from|in)\s*$", en[:m.start()]) \
                and not re.match(r"\s*(?:\d|–|-|to|through|and)", en[m.end():]):
            return word
        return f" {MONTHS[word.lower().rstrip('.')]} "
    en = EN_MONTH.sub(month, en)
    k_int, k_dec = _numbers(ko)
    e_int, e_dec = _numbers(en)
    def parts(d: str) -> set[str]:
        return {x.lstrip("0") or "0" for x in d.split(".")}
    k_decn, e_decn = {_num(d) for d in k_dec}, {_num(d) for d in e_dec}
    for d in sorted(k_dec):  # '10.9' (a date or a decimal) may be written 'October 9' or '10.9'
        if _num(d) not in e_decn and not parts(d) <= e_int:
            issues.append(f"number {d} missing")
    for d in sorted(e_dec):
        if _num(d) not in k_decn and not parts(d) <= k_int:
            issues.append(f"number {d} not in Korean")
    k_parts = {x for d in k_dec for x in parts(d)}
    issues += [f"number {x} missing" for x in sorted(k_int - e_int, key=float)]
    issues += [f"number {x} not in Korean" for x in sorted(e_int - k_int - k_parts, key=float)]
    if "무료" in ko and not re.search(r"\bfree\b", en, re.I):
        issues.append("'무료' (free) missing")
    return issues


_NAMED: list[str] | None = None


def _named_with_banned_word() -> list[str]:
    """English place names that contain a word from BANNED (Best Western … Hotel): a name is not promotion."""
    global _NAMED
    if _NAMED is None:
        rows = (_load(DATA, "en/names.json", {}) or {}).values()
        _NAMED = sorted({r["name_en"] for r in rows if BANNED.search(r.get("name_en") or "")}, key=len, reverse=True)
    return _NAMED


def style(en: str, prose: bool = True) -> list[str]:
    issues = []
    text = en or ""
    if HANGUL.search(text):
        issues.append(f"Korean script left: {''.join(HANGUL.findall(text))[:20]}")
    unnamed = text
    for name in _named_with_banned_word():
        unnamed = unnamed.replace(name, " ")
    for rx, what, t in ((BANNED, "promotional word", unnamed), (DISCLAIMER, "disclaimer", text),
                        (BRITISH, "British spelling (use US)", text)):
        for m in rx.finditer(t):
            issues.append(f"{what}: '{m.group(0)}'")
    for m in AMPM.finditer(text):
        issues.append(f"12-hour time '{m.group(0)}' (write 24-hour HH:MM)")
    for m in EN_TIME.finditer(text):
        if len(m.group(1)) == 1:
            issues.append(f"time '{m.group(0)}' needs a two-digit hour (0{m.group(0)})")
    if re.search(r"[~∼～〜]", text):
        issues.append("'~' (use an en dash for ranges)")
    if re.search(r"₩|\bKRW\b", text):
        issues.append("write money as '3,000 won' (no ₩/KRW)")
    for m in re.finditer(r"\b(\d{4,})\s*won\b", text):
        issues.append(f"'{m.group(0)}' needs thousands commas")
    if prose:
        for s in re.split(r"(?<=[.!?])\s+", squash_ws(text)):
            n = len(s.split())
            if n > WORDS_MAX:
                issues.append(f"sentence of {n} words (max {WORDS_MAX}): '{s[:60]}…'")
    return issues


def _pair(where: str, ko: str, en, prose: bool = True) -> list[str]:
    if not isinstance(en, str):
        return [f"{where}: missing"] if squash_ws(ko) else []
    if squash_ws(ko) and not squash_ws(en):
        return [f"{where}: empty"]
    return [f"{where}: {x}" for x in parity(ko, en) + style(en, prose)]


def _list(where: str, ko: list, en) -> tuple[list, list[str]]:
    if not isinstance(en, list):
        return [], ([f"{where}: missing"] if ko else [])
    if len(en) != len(ko):
        return en, [f"{where}: {len(en)} given, Korean has {len(ko)}"]
    return en, []


def _q_ok(q, L) -> bool:
    return L.question(q) if L else squash_ws(q).endswith("?")


def check_place(item: dict, inp: dict, L: "LangCheck | None" = None) -> list[str]:
    issues = []
    _pair_ = L.pair if L else _pair
    note = L.loc.conflict if L else CONFLICT_NOTE
    if L:
        issues += L.name(item, inp)
    elif item.get("name_en") != inp["name_en"]:
        issues.append(f"name_en must be exactly '{inp['name_en']}' (got '{item.get('name_en')}')")
    issues += _pair_("summary", inp["summary"], item.get("summary"))
    got = {f.get("key"): f for f in item.get("facts") or [] if isinstance(f, dict)}
    for f in inp["facts"]:
        o = got.get(f["key"])
        w = f"facts.{f['key']}"
        if not o:
            issues.append(f"{w}: missing")
            continue
        issues += _pair_(w, f["value"], o.get("value"), prose=False)
        if f["key"] == "address" and f.get("address_en_candidate") and o.get("value") != f["address_en_candidate"]:
            issues.append(f"{w}: use the candidate '{f['address_en_candidate']}'")
        for part in ("alternatives", "also"):
            ko_alts = f.get(part) or []
            en_alts, problems = _list(f"{w}.{part}", ko_alts, o.get(part))
            issues += problems
            if not problems:
                for i, (a, b) in enumerate(zip(ko_alts, en_alts)):
                    issues += _pair_(f"{w}.{part}[{i}]", a["value"], (b or {}).get("value") if isinstance(b, dict) else b,
                                     prose=False)
        if f.get("alternatives") and o.get("note") != note:
            issues.append(f"{w}: note must be '{note}' (two sources differ)")
        if not f.get("alternatives") and o.get("note"):
            issues.append(f"{w}: note only where the Korean has two source values")
    issues += [f"facts.{k}: not in the Korean" for k in got if k not in {f['key'] for f in inp["facts"]}]
    for part, fields in (("details", ("heading", "text")), ("faq", ("q", "a"))):
        en_rows, problems = _list(part, inp[part], item.get(part))
        issues += problems
        if problems:
            continue
        for i, (a, b) in enumerate(zip(inp[part], en_rows)):
            for fld in fields:
                issues += _pair_(f"{part}[{i}].{fld}", a[fld], (b or {}).get(fld), prose=fld != "heading")
            if part == "faq" and not _q_ok((b or {}).get("q"), L):
                issues.append(f"faq[{i}].q must end with '?'")
    return issues


def check_guide(item: dict, inp: dict, L: "LangCheck | None" = None) -> list[str]:
    issues = []
    _pair_ = L.pair if L else _pair
    for f in ("label", "title", "summary"):
        issues += _pair_(f, inp[f], item.get(f), prose=f == "summary")
    for part, fields in (("body", ("heading", "text")), ("items", ("reason",)), ("faq", ("q", "a")),
                         ("sources", ("name",))):
        en_rows, problems = _list(part, inp[part], item.get(part))
        issues += problems
        if problems:
            continue
        for i, (a, b) in enumerate(zip(inp[part], en_rows)):
            b = b or {}
            for fld in fields:
                issues += _pair_(f"{part}[{i}].{fld}", a[fld], b.get(fld), prose=fld in ("text", "reason", "a"))
            if part == "items" and b.get("place_slug") != a["place_slug"]:
                issues.append(f"items[{i}].place_slug must be '{a['place_slug']}'")
            if part == "faq" and not _q_ok(b.get("q"), L):
                issues.append(f"faq[{i}].q must end with '?'")
    return issues


def check_course(item: dict, inp: dict, L: "LangCheck | None" = None) -> list[str]:
    issues = []
    _pair_ = L.pair if L else _pair
    for f in ("name", "group", "duration", "summary"):
        issues += _pair_(f, inp[f], item.get(f), prose=f == "summary")
    en_rows, problems = _list("stops", inp["stops"], item.get("stops"))
    issues += problems
    if not problems:
        for i, (a, b) in enumerate(zip(inp["stops"], en_rows)):
            for fld in ("name", "note"):
                issues += _pair_(f"stops[{i}].{fld}", a[fld], (b or {}).get(fld), prose=False)
    return issues


def check_event(item: dict, inp: dict, L: "LangCheck | None" = None) -> list[str]:
    _pair_ = L.pair if L else _pair
    ev_note = L.loc.event_conflict if L else EVENT_CONFLICT_NOTE
    issues = _pair_("series_name", inp["series_name"], item.get("series_name"), prose=False)
    newest = item.get("newest") or {}
    for f, ko in inp["newest"].items():
        if f in ("id", "address_en_candidate", "notes"):
            continue
        issues += _pair_(f"newest.{f}", ko, newest.get(f), prose=f == "summary")
    cand = inp["newest"].get("address_en_candidate")
    if cand and newest.get("address") != cand:
        issues.append(f"newest.address: use the candidate '{cand}'")
    en_notes, problems = _list("newest.notes", inp["newest"].get("notes") or [], newest.get("notes", []))
    issues += problems
    if not problems:
        for i, (a, b) in enumerate(zip(inp["newest"].get("notes") or [], en_notes)):
            issues += _pair_(f"newest.notes[{i}]", a, b)
    alts = item.get("alternatives") or {}
    for f, vals in inp["alternatives"].items():
        o = alts.get(f) or {}
        en_vals, problems = _list(f"alternatives.{f}.values", vals, o.get("values"))
        issues += problems
        if not problems:
            for i, (a, b) in enumerate(zip(vals, en_vals)):
                issues += _pair_(f"alternatives.{f}[{i}]", a["value"], b, prose=False)
        if o.get("note") != ev_note:
            issues.append(f"alternatives.{f}.note must be '{ev_note}'")
    for part in ("highlights", "program_notes", "sources"):
        en_rows, problems = _list(part, inp[part], item.get(part))
        issues += problems
        if not problems:
            for i, (a, b) in enumerate(zip(inp[part], en_rows)):
                issues += _pair_(f"{part}[{i}]", a, b, prose=part != "sources")
    for part, fields in (("usual", ("text", "place")), ("editions", ("name", "period_text", "place_name"))):
        en_rows, problems = _list(part, inp[part], item.get(part))
        issues += problems
        if not problems:
            for i, (a, b) in enumerate(zip(inp[part], en_rows)):
                for fld in fields:
                    issues += _pair_(f"{part}[{i}].{fld}", a[fld], (b or {}).get(fld), prose=False)
                if part == "editions" and (b or {}).get("id") != a["id"]:
                    issues.append(f"editions[{i}].id must be '{a['id']}'")
    return issues


PLACEHOLDER = re.compile(r"\{[a-z_0-9]*\}")


def check_string(item: dict, inp: dict, L: "LangCheck | None" = None) -> list[str]:
    if L:
        return check_string_l(item, inp, L)
    issues = _pair("en", inp["ko"], item.get("en"), prose=False)
    if sorted(PLACEHOLDER.findall(inp["ko"])) != sorted(PLACEHOLDER.findall(item.get("en") or "")):
        issues.append(f"placeholders must stay {sorted(PLACEHOLDER.findall(inp['ko']))}")
    return issues


def check_string_l(item: dict, inp: dict, L: "LangCheck") -> list[str]:
    """A strings row of another language: a label from the Korean (parity as for every field) or one of the pages'
    own words from the English (chrome.*: every {placeholder} and digit kept, style and script checks)."""
    field = L.loc.tag
    text = item.get(field)
    if "ko" in inp:
        issues = L.pair(field, inp["ko"], text, prose=False)
        src = inp["ko"]
    else:
        src = inp["en"]
        if not isinstance(text, str) or not squash_ws(text):
            return [f"{field}: missing"]
        issues = [f"{field}: {x}" for x in style_l(text, L.code, len(src.split()) >= 8, L.names)]
        have = re.findall(r"\d+", PLACEHOLDER.sub(" ", text))
        issues += [f"{field}: number {d} missing" for d in re.findall(r"\d+", PLACEHOLDER.sub(" ", src)) if d not in have]
    if sorted(PLACEHOLDER.findall(src)) != sorted(PLACEHOLDER.findall(text or "")):
        issues.append(f"placeholders must stay {sorted(PLACEHOLDER.findall(src))}")
    return issues


CHECKERS = {"places": check_place, "guides": check_guide, "courses": check_course, "events": check_event,
            "strings": check_string}


def _input_for(path: Path) -> Path:
    return path.with_name(re.sub(r"\.output(?:[-.][\w-]+)?\.json$", ".input.json", path.name))


def check(paths: list[Path]) -> list[str]:
    """Findings for output files; several outputs of one input batch (en-12.output-a.json …) count together."""
    issues: list[str] = []
    covered: dict[Path, set] = {}
    seen_q: dict[str, str] = {}
    for path in paths:
        try:
            out = json.loads(path.read_text("utf-8"))
        except (OSError, ValueError) as err:
            issues.append(f"{path.name}: not readable JSON ({err})")
            continue
        inp_path = _input_for(path)
        if not inp_path.exists():
            issues.append(f"{path.name}: input {inp_path.name} not found")
            continue
        inp = json.loads(inp_path.read_text("utf-8"))
        checker = CHECKERS[inp["type"]]
        by_id = {i["id"]: i for i in inp["items"]}
        lang = inp.get("lang") or "en"   # English batches carry no 'lang' (unchanged)
        got = covered.setdefault(inp_path, set())
        for item in out.get("items", []) if isinstance(out, dict) else []:
            iid = item.get("id") if isinstance(item, dict) else None
            if iid not in by_id:
                issues.append(f"{path.name} {iid}: id not in the input")
                continue
            if iid in got:
                issues.append(f"{path.name} {iid}: translated twice")
            got.add(iid)
            if lang == "en":
                found = checker(item, by_id[iid])
            else:
                src = by_id[iid]
                key = LC.get(lang).name_key
                names_ = (src.get(key), item.get(key) if isinstance(item, dict) else "",
                          *[m.get(lang) for m in src.get("mentions") or []])
                found = checker(item, src, LangCheck(lang, tuple(squash_ws(n) for n in names_ if isinstance(n, str))))
            issues += [f"{path.name} {iid} {x}" for x in found]
            for f in item.get("faq") or []:
                q = squash_ws((f or {}).get("q")).lower()
                if q and q in seen_q and seen_q[q] != iid:
                    issues.append(f"{path.name} {iid}: same question as {seen_q[q]}: {q}")
                seen_q[q] = iid
    for inp_path, got in covered.items():
        missing = [i["id"] for i in json.loads(inp_path.read_text("utf-8"))["items"] if i["id"] not in got]
        issues += [f"{inp_path.name.replace('.input', '.output')} {x}: not translated" for x in missing]
    return issues


# ------------------------------------------------------------------ merge
def _merge_place(item: dict, inp: dict, today: str, src: dict) -> dict:
    facts = {}
    got = {f["key"]: f for f in item["facts"]}
    for f in inp["facts"]:
        o = got[f["key"]]
        row = {"value": squash_ws(o["value"]) if "\n" not in o["value"] else o["value"].strip()}
        for part in ("alternatives", "also"):
            if f.get(part):
                row[part] = [{"value": (b["value"] if isinstance(b, dict) else b), "provider": a["provider"]}
                             for a, b in zip(f[part], o[part])]
        if f.get("alternatives"):
            row["note"] = CONFLICT_NOTE
        facts[f["key"]] = row
    faq_src = [x.get("source", "") for x in src.get("faq") or []]
    det_src = [x.get("source", "") for x in src.get("details") or []]
    return {"slug": inp["slug"], "kind": inp["kind"], "name_ko": inp["name"], "name_en": inp["name_en"],
            "name_en_source": inp["name_en_source"], "summary": squash_ws(item.get("summary")), "facts": facts,
            "details": [{"heading": squash_ws(d["heading"]), "text": squash_ws(d["text"]), "source": s}
                        for d, s in zip(item.get("details") or [], det_src)],
            "faq": [{"q": squash_ws(f["q"]), "a": squash_ws(f["a"]), "source": s}
                    for f, s in zip(item.get("faq") or [], faq_src)],
            "ko_hash": inp["ko_hash"], "translated_at": today}


def merge(paths: list[Path], data: Path = DATA) -> dict:
    problems = check(paths)
    if problems:
        raise SystemExit("검사 미통과 — 병합하지 않습니다:\n" + "\n".join(problems))
    langs = {json.loads(_input_for(p).read_text("utf-8")).get("lang") or "en" for p in paths}
    if len(langs) > 1:
        raise SystemExit(f"한 번에 한 언어만 병합합니다: {sorted(langs)}")
    lang = langs.pop() if langs else "en"
    if lang != "en":
        return merge_l(paths, data, lang)
    today = dt.date.today().isoformat()
    en_dir = data / "en"
    en_dir.mkdir(exist_ok=True)
    stores = {k: _load(data, f"en/{k}.json", {}) or {} for k in CHECKERS}
    places = {p["id"]: p for p in json.loads((data / "places.json").read_text("utf-8"))}
    guides = {g["id"]: g for g in _load(data, "guides.json", [])}
    counts = {k: 0 for k in CHECKERS}
    for path in paths:
        inp = json.loads(_input_for(path).read_text("utf-8"))
        kind = inp["type"]
        by_id = {i["id"]: i for i in inp["items"]}
        for item in json.loads(path.read_text("utf-8"))["items"]:
            src = by_id[item["id"]]
            if kind == "places":
                rec = _merge_place(item, src, today, places.get(item["id"], {}))
            elif kind == "guides":
                g = guides.get(item["id"], {})
                rec = {"slug": src["slug"], "label": squash_ws(item["label"]), "title": squash_ws(item["title"]),
                       "summary": squash_ws(item["summary"]),
                       "body": [{"heading": squash_ws(b["heading"]), "text": squash_ws(b["text"])} for b in item["body"]],
                       "items": [{"place_slug": a["place_slug"], "reason": squash_ws(b["reason"])}
                                 for a, b in zip(src["items"], item["items"])],
                       "faq": [{"q": squash_ws(b["q"]), "a": squash_ws(b["a"]), "source": (a or {}).get("source", "")}
                               for a, b in zip(g.get("faq") or [{}] * len(item["faq"]), item["faq"])],
                       "sources": [{"name": squash_ws(b["name"]), "url": a["url"]} for a, b in zip(src["sources"], item["sources"])],
                       "ko_hash": src["ko_hash"], "translated_at": today}
            elif kind == "courses":
                rec = {"slug": src["slug"], "name": squash_ws(item["name"]), "group": squash_ws(item.get("group")),
                       "duration": squash_ws(item.get("duration")), "summary": squash_ws(item["summary"]),
                       "stops": [{"name": squash_ws(b["name"]), "note": squash_ws(b.get("note")), "place_slug": a["place_slug"]}
                                 for a, b in zip(src["stops"], item["stops"])],
                       "ko_hash": src["ko_hash"], "translated_at": today}
            elif kind == "events":
                newest = {k: v for k, v in (item.get("newest") or {}).items() if k != "id"}
                newest["id"] = src["newest"]["id"]
                rec = {"series_name": squash_ws(item["series_name"]), "newest": newest,
                       "alternatives": {f: {"values": item["alternatives"][f]["values"],
                                            "providers": [a["provider"] for a in vals], "note": EVENT_CONFLICT_NOTE}
                                        for f, vals in src["alternatives"].items()},
                       "highlights": item.get("highlights") or [], "program_notes": item.get("program_notes") or [],
                       "usual": item.get("usual") or [], "editions": item.get("editions") or [],
                       "sources": {ko: en for ko, en in zip(src["sources"], item.get("sources") or [])},
                       "ko_hash": src["ko_hash"], "translated_at": today}
            else:
                rec = {"ko": src["ko"], "en": squash_ws(item["en"])}
            stores[kind][item["id"]] = rec
            counts[kind] += 1
    for kind, store in stores.items():
        if store:
            (en_dir / f"{kind}.json").write_text(json.dumps(store, ensure_ascii=False, indent=2) + "\n", "utf-8")
    return counts


# ------------------------------------------------------------------ the other languages (--lang ja | zh-hans | …)
# Everything above is English's (unchanged). The other versions (pipeline/locales.py) get the same items, batches,
# checks and merge, adapted: the place name field is name_<tag> (official TourAPI name when names --lang matched one,
# else written by the translator: name source 'translated'), the conflict notes are the language's, parity reads the
# language's money, decimal marks, thousands separators, weekday and month names, and the strings batch carries the
# pages' own words (pipeline/intl_text.py, given in English as 'chrome.<key>') instead of the Korean template text.
CJK_CHARS = r"぀-ヿ㐀-䶿一-鿿"
WON_L = {
    "ja": re.compile(r"(\d[\d,]*(?:\.\d+)?)\s*ウォン"),
    "zh-hans": re.compile(r"(\d[\d,]*(?:\.\d+)?)\s*韩元"),
    "zh-hant": re.compile(r"(\d[\d,]*(?:\.\d+)?)\s*韓元"),
    "de": re.compile(r"(\d[\d.]*(?:,\d+)?)\s*Won\b"),
    "fr": re.compile(r"(\d[\d\u202f\u00a0]*(?:,\d+)?)\s*wons?\b"),
    "es": re.compile(r"(\d[\d.]*(?:,\d+)?)\s*won(?:es)?\b"),
    "ru": re.compile(r"(\d[\d\u202f\u00a0]*(?:,\d+)?)\s*вон\b"),
}
WRONG_MONEY = {
    "ja": re.compile(r"₩|\bKRW\b|\bwons?\b|韓国ウォン", re.I),
    "zh-hans": re.compile(r"₩|\bKRW\b|\bwons?\b|韩币|韓元", re.I),
    "zh-hant": re.compile(r"₩|\bKRW\b|\bwons?\b|韓幣|韩元", re.I),
    "de": re.compile(r"₩|\bKRW\b|\bwon\b"),
    "fr": re.compile(r"₩|\bKRW\b"),
    "es": re.compile(r"₩|\bKRW\b"),
    "ru": re.compile(r"₩|\bKRW\b|\bwons?\b", re.I),
}
TWELVE_HOUR = {
    "ja": re.compile(r"(?:午前|午後)\s*\d|\d{1,2}時(?!間)"),
    "zh-hans": re.compile(r"(?:上午|下午|晚上|早上|中午|凌晨)\s*\d|\d{1,2}[点點](?!\d)"),
    "zh-hant": re.compile(r"(?:上午|下午|晚上|早上|中午|凌晨)\s*\d|\d{1,2}[点點](?!\d)"),
    "de": re.compile(r"(?<![\d:])\d{1,2}(?:\.\d{2})?\s?Uhr\b|\b\d{1,2}\s?(?:AM|PM|am|pm)\b"),
    "fr": re.compile(r"(?<![\d:])\d{1,2}\s?h(?:\s?\d{2})?(?![\w])|\b\d{1,2}\s?(?:AM|PM|am|pm)\b"),
    "es": re.compile(r"\b\d{1,2}(?::\d{2})?\s?(?:a\.\s?m\.|p\.\s?m\.|AM|PM|am|pm)"),
    "ru": re.compile(r"(?<![\d:])\d{1,2}\s?ч\.?(?![\w])|\b\d{1,2}\s?(?:AM|PM|am|pm)\b"),
}
# weekdays the translation names: (regex, day index or None, group of the day word) per language; ranges and
# 'weekend' / 'weekdays' / 'every day' words widen what a faithful translation may name
_WD_ZH = "一二三四五六日天"
DAY_RX = {
    "ja": re.compile(r"([月火水木金土日])(?=(?:[・、–-][月火水木金土日])*曜)|[（(]([月火水木金土日])[)）]"),
    "zh-hans": re.compile(r"(?:周|星期|礼拜)([一二三四五六日天])"),
    "zh-hant": re.compile(r"(?:週|周|星期|禮拜)([一二三四五六日天])"),
    "de": re.compile(r"\b(Montag|Dienstag|Mittwoch|Donnerstag|Freitag|Samstag|Sonnabend|Sonntag)(?:s|e|en)?\b"
                     r"|\b(Mo|Di|Mi|Do|Fr|Sa|So)\.|\b(Mo|Di|Mi|Do|Fr|Sa|So)(?=\s?[–-]\s?(?:Mo|Di|Mi|Do|Fr|Sa|So)\b)"
                     r"|(?<=[–-])\s?(Mo|Di|Mi|Do|Fr|Sa|So)\b"),
    "fr": re.compile(r"\b(lundi|mardi|mercredi|jeudi|vendredi|samedi|dimanche)s?\b|\b(lun|mar|mer|jeu|ven|sam|dim)\.", re.I),
    "es": re.compile(r"\b(lunes|martes|miércoles|miercoles|jueves|viernes|sábado|sabado|domingo)s?\b"
                     r"|\b(lun|mar|mié|mie|jue|vie|sáb|sab|dom)\.", re.I),
    "ru": re.compile(r"\b(понедельник|вторник|сред|четверг|пятниц|суббот|воскресень)\w*|\b(пн|вт|ср|чт|пт|сб|вс)\b", re.I),
}
DAY_INDEX = {
    "de": {"mon": 0, "die": 1, "mit": 2, "don": 3, "fre": 4, "sam": 5, "son": 6, "mo": 0, "di": 1, "mi": 2, "do": 3,
           "fr": 4, "sa": 5, "so": 6},
    "fr": {"lun": 0, "mar": 1, "mer": 2, "jeu": 3, "ven": 4, "sam": 5, "dim": 6},
    "es": {"lun": 0, "mar": 1, "mié": 2, "mie": 2, "jue": 3, "vie": 4, "sáb": 5, "sab": 5, "dom": 6},
    "ru": {"пон": 0, "вто": 1, "сре": 2, "чет": 3, "пят": 4, "суб": 5, "вос": 6, "пн": 0, "вт": 1, "ср": 2, "чт": 3,
           "пт": 4, "сб": 5, "вс": 6},
}
DAY_SPAN = {   # (weekend, weekdays, every day)
    "ja": (r"週末|土日", r"平日", r"毎日|年中無休|無休"),
    "zh-hans": (r"周末", r"工作日|平日", r"每天|每日|全年无休"),
    "zh-hant": (r"週末", r"工作日|平日", r"每天|每日|全年無休"),
    "de": (r"Wochenende", r"werktags|wochentags|Werktage", r"täglich|jeden Tag|ganzjährig"),
    "fr": (r"week-?ends?", r"en semaine|jours ouvrables", r"tous les jours|chaque jour|toute l'année"),
    "es": (r"fines? de semana", r"entre semana|días laborables|dias laborables", r"todos los días|diariamente|todo el año"),
    "ru": (r"выходн", r"будн|рабочие дни", r"ежедневно|каждый день|без выходных|круглый год"),
}
DAY_RANGE_SEP = {"ja": r"[–-]", "zh-hans": r"至|到|[–-]", "zh-hant": r"至|到|[–-]", "de": r"[–-]|bis", "fr": r"[–-]|au|à",
                 "es": r"[–-]|a", "ru": r"[–-]|по"}
MONTHS_L = {
    "de": ("januar", "februar", "märz", "april", "mai", "juni", "juli", "august", "september", "oktober", "november",
           "dezember"),
    "fr": ("janvier", "février", "mars", "avril", "mai", "juin", "juillet", "août", "septembre", "octobre", "novembre",
           "décembre"),
    "es": ("enero", "febrero", "marzo", "abril", "mayo", "junio", "julio", "agosto", "septiembre", "octubre",
           "noviembre", "diciembre"),
    "ru": ("январ", "феврал", "март", "апрел", "ма[йя]", "июн", "июл", "август", "сентябр", "октябр", "ноябр", "декабр"),
}
QUESTION_END = re.compile(r"[?？]$")


def _sq(text: str | None) -> str:
    """squash_ws keeping the narrow no-break space (French and Russian thousands: '3\u202f000 wons')."""
    return re.sub(r"[^\S\u202f]+", " ", text or "").strip()


def _day_of(word: str, code: str) -> int | None:
    w = word.lower()
    if code in ("zh-hans", "zh-hant"):
        return {"一": 0, "二": 1, "三": 2, "四": 3, "五": 4, "六": 5, "日": 6, "天": 6}.get(word)
    if code == "ja":
        return "月火水木金土日".index(word) if word in "月火水木金土日" else None
    table = DAY_INDEX[code]
    for k in sorted(table, key=len, reverse=True):
        if w.startswith(k):
            return table[k]
    return None


def _l_days(text: str, code: str) -> tuple[set[str], set[str]]:
    """(named weekdays, weekdays covered incl. ranges and 'weekend' words), as DAYS_EN names."""
    named: list[int] = []
    spans: list[tuple[int, int, int]] = []   # (position, end, day)
    for m in DAY_RX[code].finditer(text):
        word = next((g for g in m.groups() if g), "")
        d = _day_of(word, code)
        if d is not None:
            named.append(d)
            spans.append((m.start(), m.end(), d))
    covered = set(named)
    sep = DAY_RANGE_SEP[code]
    for (a0, a1, i), (b0, _, j) in zip(spans, spans[1:]):
        between = text[a1:b0].strip()
        if code == "ja":
            between = between.replace("曜日", "").replace("曜", "").strip()
        if re.fullmatch(rf"(?:{sep})", between, re.I) or (code == "ru" and re.fullmatch(r"по", between)):
            rng = range(i, j + 1) if i <= j else [*range(i, 7), *range(0, j + 1)]
            covered.update(rng)
    weekend, weekdays, daily = DAY_SPAN[code]
    if re.search(weekend, text, re.I):
        covered.update((5, 6))
    if re.search(weekdays, text, re.I):
        covered.update(range(5))
    if re.search(daily, text, re.I):
        covered.update(range(7))
    return {DAYS_EN[d] for d in named}, {DAYS_EN[d] for d in covered}


def _l_months(text: str, code: str) -> str:
    months = MONTHS_L.get(code)
    if not months:
        return text
    for i, m in enumerate(months, 1):
        text = re.sub(rf"\b{m}\w*\.?", f" {i} ", text, flags=re.I)
    return text


def _l_num(s: str, code: str) -> str:
    """A number as the language writes it -> '3000' / '1.5' (thousands separators out, decimal mark '.')."""
    loc = LC.get(code)
    s = s.replace("\u202f", "").replace("\u00a0", "")
    if loc.dec == ",":
        s = s.replace(".", "").replace(",", ".")
    else:
        s = s.replace(",", "")
    return _num(s)


def _l_big(text: str, code: str) -> str:
    """'1万ウォン' -> '10000ウォン' (Japanese and Chinese myriads)."""
    if not LC.get(code).cjk:
        return text
    return re.sub(r"(\d+(?:\.\d+)?)\s*([万萬億亿])",
                  lambda m: str(int(round(float(m.group(1)) * (1e8 if m.group(2) in "億亿" else 1e4)))), text)


def _l_numbers(text: str, code: str) -> tuple[set[str], set[str]]:
    """(integers, decimals) left in a translated text after phones, times and money were taken out."""
    loc = LC.get(code)
    if loc.dec == ".":
        return _numbers(text)
    ints, decs = set(), set()
    grp = r"\." if loc.grp == "." else r"[\u202f\u00a0]"
    for m in re.findall(rf"\d{{1,3}}(?:{grp}\d{{3}})+,\d+", text):   # '1.868,7' / '1 868,7': one decimal number
        decs.add(_l_num(m, code))
    text = re.sub(rf"\d{{1,3}}(?:{grp}\d{{3}})+,\d+", " ", text)
    for m in re.findall(rf"\d{{1,3}}(?:{grp}\d{{3}})+(?![\d,])", text):
        ints.add(_l_num(m, code))
    text = re.sub(rf"\d{{1,3}}(?:{grp}\d{{3}})+(?![\d,])", " ", text)
    for m in re.findall(r"\d+,\d+", text):
        decs.add(m.replace(",", "."))
    text = re.sub(r"\d+,\d+", " ", text)
    ints.update(_num(n) for n in re.findall(r"\d+", text))
    return ints, decs


def parity_l(ko: str, text: str, code: str) -> list[str]:
    """parity() for another language: every phone, time, won amount, weekday and number of `ko` in `text` with the
    same digits (thousands separators and decimal marks as the language writes them), and none added."""
    loc = LC.get(code)
    issues: list[str] = []
    ko = NOT_A_TIME.sub(r"\1 \2", ko or "")
    ko, tx = squash_ws(ko), _sq(text)
    if not ko:
        return issues
    if not tx:
        return [f"{loc.english} is empty"]
    kp, tp = extract_phones(ko), extract_phones(tx)
    issues += [f"phone {p} missing" for p in kp if p not in tp]
    issues += [f"phone {p} not in Korean" for p in tp if p not in kp]
    for p in set(kp) | set(tp):
        ko, tx = ko.replace(p, " "), tx.replace(p, " ")
    ko, tx = _ko_big(ko), _l_big(tx, code)
    won = WON_L[code]
    k_won = {_num(x) for x in WON_KO.findall(ko)}
    t_won = {_l_num(x, code) for x in won.findall(tx)}
    issues += [f"amount {loc.money(int(float(x)))} missing" for x in sorted(k_won - t_won, key=float)]
    issues += [f"amount {loc.money(int(float(x)))} not in Korean" for x in sorted(t_won - k_won, key=float)]
    ko, tx = WON_KO.sub(" ", ko), won.sub(" ", tx)
    lone = {DAYS_EN[KO_WEEK.index(d)] for d in KO_DAY_LONE.findall(ko)}
    k_times, ko = _times_ko(ko)
    t_times = {f"{int(h):02d}:{m}" for h, m in EN_TIME.findall(tx)}
    issues += [f"time {sorted(opts)[0]} missing" for opts in k_times if not opts & t_times]
    k_all = set().union(*k_times) if k_times else set()
    issues += [f"time {t} not in Korean" for t in sorted(t_times - k_all)]
    tx = EN_TIME.sub(" ", tx)
    k_stated, k_allowed = _ko_days(ko)
    k_stated, k_allowed = k_stated | lone, k_allowed | lone
    t_named, t_covered = _l_days(tx, code)
    name = dict(zip(DAYS_EN, loc.weekdays))
    issues += [f"weekday {name[d]} missing" for d in sorted(k_stated - t_covered, key=DAYS_EN.index)]
    issues += [f"weekday {name[d]} not in Korean" for d in sorted(t_named - k_allowed, key=DAYS_EN.index)]
    if code == "ja":   # '(月)' and '月曜' were read as weekdays; a month '10月' is a number
        tx = re.sub(r"[（(][月火水木金土日][)）]|[月火水木金土日](?=(?:[・、–-][月火水木金土日])*曜)", " ", tx)
    tx = _l_months(tx, code)
    # '203,204호' lists rooms 203 and 204 (a comma before a counter of rooms, floors, numbers), not 203204
    ko = re.sub(r"(\d+),(\d{3})(?=\s*(?:호|층|번|실)(?![가-힣]))", r"\1, \2", ko)
    k_int, k_dec = _numbers(ko)
    t_int, t_dec = _l_numbers(tx, code)

    def parts(d: str) -> set[str]:
        return {x.lstrip("0") or "0" for x in d.split(".")}
    k_decn, t_decn = {_num(d) for d in k_dec}, {_num(d) for d in t_dec}
    for d in sorted(k_dec):
        if _num(d) not in t_decn and not parts(d) <= t_int:
            issues.append(f"number {d} missing")
    for d in sorted(t_dec):
        if _num(d) not in k_decn and not parts(d) <= k_int:
            issues.append(f"number {d} not in Korean")
    k_parts = {x for d in k_dec for x in parts(d)}
    issues += [f"number {x} missing" for x in sorted(k_int - t_int, key=float)]
    issues += [f"number {x} not in Korean" for x in sorted(t_int - k_int - k_parts, key=float)]
    if "무료" in ko and loc.free and not re.search(loc.free, tx, re.I):
        issues.append("'무료' (free) missing")
    return issues


def style_l(text: str, code: str, prose: bool = True, names: tuple = ()) -> list[str]:
    """style() for another language: no Korean script, no promotional words or disclaimers, 24-hour HH:MM times, en
    dash ranges, money and numbers as the language writes them, full-width punctuation in Japanese and Chinese, the
    script and language of the text (pipeline/locales.script_problems), sentence length."""
    loc = LC.get(code)
    issues: list[str] = []
    t = text or ""
    if HANGUL.search(t):
        issues.append(f"Korean script left: {''.join(HANGUL.findall(t))[:20]}")
    unnamed = t
    for n in sorted((n for n in names if n), key=len, reverse=True):
        unnamed = unnamed.replace(n, " ")
    for rx, what in ((LC.promo_rx(code), "promotional word"), (LC.disclaimer_rx(code), "disclaimer")):
        if rx:
            for m in rx.finditer(unnamed if what == "promotional word" else t):
                issues.append(f"{what}: '{m.group(0)}'")
    for m in TWELVE_HOUR[code].finditer(t):
        issues.append(f"time '{m.group(0).strip()}' (write 24-hour HH:MM, e.g. 09:00–18:00)")
    for m in EN_TIME.finditer(t):
        if len(m.group(1)) == 1:
            issues.append(f"time '{m.group(0)}' needs a two-digit hour (0{m.group(0)})")
    if re.search(r"[~∼～〜]", t):
        issues.append("'~' (use an en dash for ranges)")
    for m in WRONG_MONEY[code].finditer(t):
        issues.append(f"money '{m.group(0)}': write '{loc.money(3000)}'")
    word = {"ja": "ウォン", "zh-hans": "韩元", "zh-hant": "韓元", "de": "Won", "fr": "wons?", "es": "won(?:es)?",
            "ru": "вон"}[code]
    for m in re.finditer(rf"(?<![\d.,\u202f\u00a0])(\d{{4,}})\s*{word}", t):
        issues.append(f"'{m.group(0)}' needs thousands separators ('{loc.money(int(m.group(1)))}')")
    wrong_grp = {",": r"[.\u202f\u00a0 ]", ".": r"[,\u202f\u00a0 ]", "\u202f": r"[,.\u00a0 ]"}[loc.grp]
    for m in re.finditer(rf"\d{{1,3}}{wrong_grp}\d{{3}}\s*{word}", t):
        issues.append(f"'{m.group(0)}': thousands as '{loc.money(3000)}'")
    if loc.dec == ",":
        for m in re.finditer(r"(?<![\d.])\d+\.\d{1,2}(?!\d)\s?(?:km|m\b|%)", t):
            issues.append(f"'{m.group(0)}': decimal mark is ',' ({loc.dist(1200)})")
    if loc.cjk:
        cjk = CJK_CHARS
        if re.search(rf"(?<=[{cjk}]),|,(?=[{cjk}])", t):
            issues.append("ASCII comma next to Chinese/Japanese text (use 、 or ，)")
        if re.search(rf"(?<=[{cjk}])\.(?!\d)", t):
            issues.append("ASCII period after Chinese/Japanese text (use 。)")
        if re.search(rf"\([^()]*[{cjk}][^()]*\)", t):
            issues.append("ASCII brackets around Chinese/Japanese text (use （）)")
    issues += LC.script_problems(t, code, prose)
    if prose:
        for s in loc.sentences(squash_ws(t)):
            n = len(re.sub(r"\s", "", s)) if loc.cjk else len(s.split())
            if n > loc.sent_max:
                unit = "characters" if loc.cjk else "words"
                issues.append(f"sentence of {n} {unit} (max {loc.sent_max}): '{s[:40]}…'")
    return issues


class LangCheck:
    """check() for one language other than English: the pair checks and the name rules of its batches."""

    def __init__(self, code: str, names: tuple = ()):
        self.code = code
        self.loc = LC.get(code)
        self.names = names

    def pair(self, where: str, ko: str, text, prose: bool = True) -> list[str]:
        if not isinstance(text, str):
            return [f"{where}: missing"] if squash_ws(ko) else []
        if squash_ws(ko) and not squash_ws(text):
            return [f"{where}: empty"]
        return [f"{where}: {x}" for x in parity_l(ko, text, self.code) + style_l(text, self.code, prose, self.names)]

    def name(self, item: dict, inp: dict) -> list[str]:
        key, loc = self.loc.name_key, self.loc
        given, got = squash_ws(inp.get(key)), squash_ws(item.get(key))
        if given:
            return [] if item.get(key) == inp[key] else [f"{key} must be exactly '{inp[key]}' (got '{item.get(key)}')"]
        if not got:
            return [f"{key}: missing (write the name in {loc.english}: rules.names)"]
        issues = [f"{key}: {x}" for x in style_l(got, self.code, False)]
        if self.code == "ru" and not LC.CYR.search(got):
            issues.append(f"{key}: a Russian name is written in Cyrillic (rules.names)")
        if self.code == "ja" and not (LC.KANA.search(got) or LC.CJK.search(got)):
            issues.append(f"{key}: a Japanese name is written in katakana or kanji (rules.names)")
        return issues

    def question(self, q: str) -> bool:
        return bool(QUESTION_END.search(squash_ws(q)))


def rules_for(code: str) -> dict:
    """The rules a translator into `code` follows (each input batch carries them)."""
    loc = LC.get(code)
    days = ", ".join(f"{k} -> {v}" for k, v in zip(KO_WEEK, loc.weekdays))
    script = {
        "ja": "Japanese with kana (never Chinese-only sentences); full-width punctuation 、。（）; no Korean script.",
        "zh-hans": "Simplified Chinese characters only (never Traditional forms); full-width punctuation ，。（）、; "
                   "no Japanese kana, no Korean script.",
        "zh-hant": "Traditional Chinese characters only (Taiwan standard; never Simplified forms); full-width "
                   "punctuation ，。（）、; no Japanese kana, no Korean script.",
        "de": "German only (no English or other words left untranslated); no Korean script.",
        "fr": "French only (no English or other words left untranslated); no Korean script.",
        "es": "Spanish only (no English or other words left untranslated); no Korean script.",
        "ru": "Russian in Cyrillic only (Latin letters only in brand names their owners write that way); no Korean "
              "script.",
    }[code]
    names = {
        "ja": "The place itself: name_ja exactly as given when it is not empty (an official TourAPI name). When it is "
              "empty, write the name: the proper part in katakana after the Korean pronunciation and the generic part "
              "in Japanese (e.g. ウンパ湖水公園); business names in katakana. Other places: the 'mentions' table.",
        "zh-hans": "The place itself: name_zh_hans exactly as given when it is not empty (an official TourAPI name). When "
                   "it is empty, write the name in Simplified Chinese: the proper part in its Chinese characters only "
                   "when you are sure of them, otherwise keep name_rr (Revised Romanization); the generic part in Chinese "
                   "(e.g. 银波湖公园). Never guess Chinese characters for a Korean name. Other places: 'mentions'.",
        "zh-hant": "The place itself: name_zh_hant exactly as given when it is not empty (an official TourAPI name). "
                   "When it is empty, write the name in Traditional Chinese: the proper part in its Chinese characters "
                   "only when you are sure of them, otherwise keep name_rr (Revised Romanization); the generic part in "
                   "Chinese (e.g. 銀波湖公園). Never guess Chinese characters for a Korean name. Other places: 'mentions'.",
        "de": "The place itself: name_de exactly as given when it is not empty (an official TourAPI name). When it is "
              "empty, write the proper part in Revised Romanization (name_rr) and the generic part in German "
              "(e.g. Eunpa-See-Park); business names stay romanized. Other places: the 'mentions' table.",
        "fr": "The place itself: name_fr exactly as given when it is not empty (an official TourAPI name). When it is "
              "empty, write the proper part in Revised Romanization (name_rr) and the generic part in French "
              "(e.g. parc du lac Eunpa); business names stay romanized. Other places: the 'mentions' table.",
        "es": "The place itself: name_es exactly as given when it is not empty (an official TourAPI name). When it is "
              "empty, write the proper part in Revised Romanization (name_rr) and the generic part in Spanish "
              "(e.g. parque del lago Eunpa); business names stay romanized. Other places: the 'mentions' table.",
        "ru": "The place itself: name_ru exactly as given when it is not empty (an official TourAPI name). When it is "
              "empty, write the proper part in Kontsevich Cyrillic (name_ru_candidate is the whole Korean name in "
              "Kontsevich) and the generic part in Russian (e.g. парк озера Ынпха); business names in Kontsevich. "
              "Other places: the 'mentions' table.",
    }[code]
    return {
        "source": f"Translate only the Korean in this file into {loc.english}. No new facts, no general knowledge, "
                  "nothing from other sites or from the TourAPI overview. If the Korean does not say it, the "
                  "translation does not say it.",
        "style": f"Answer-first plain {loc.english}; short sentences (at most {loc.sent_max} "
                 f"{'characters' if loc.cjk else 'words'}). No superlatives or promotional words "
                 f"({', '.join(loc.promo)}). No disclaimers ({', '.join(loc.disclaimers)}). {script}",
        "names": names,
        "numbers": f"Every number keeps its digits. Times are 24-hour with a two-digit hour and an en dash: "
                   f"09:00–18:00 in every language (never 9:00, AM/PM or words for the hour). Money: "
                   f"'{loc.money(3000)}' (1만원 -> '{loc.money(10000)}'; never ₩ or KRW). Dates: "
                   f"'{loc.date('2026-10-13')}'. Decimals: '{loc.dist(1200)}'. Phones exactly as in the Korean. Keep "
                   f"the Korean unit (110 m, {loc.dist(1700)}, {loc.num(9907)} pyeong); no conversions. A number the "
                   "Korean writes as a word stays a word. Ranges use an en dash (–), never '~'.",
        "weekdays": f"Weekdays: {days}; 주말 = the weekend, 평일 = weekdays.",
        "conflicts": f"A fact with 'alternatives' (two sources disagree): translate the main value and every alternative "
                     f"in the same order, and set note to exactly '{loc.conflict}'. Events use "
                     f"'{loc.event_conflict}'. Never pick one side.",
        "faq": "Same number of questions and answers, same order; each question ends with a question mark.",
        "address": "Use address_en_candidate (the romanized address, the same in every language) as the address value "
                   "when it is given; otherwise write '<number> <Road>, <eup/myeon/dong>, <the city's English address tail>' "
                   "with Revised Romanization and every digit kept.",
        "strings": "Rows with 'ko' are labels to translate from the Korean. Rows with 'en' (chrome.*) are the pages' own "
                   "words, given in English: translate them, keep every {placeholder} exactly, keep it short like the "
                   "English. A row whose id ends in .one / .few / .many / .other is a plural form for that CLDR "
                   f"category of {loc.english} ({' / '.join(loc.plural)}): write the form a count of that category takes.",
    }


def _names_l(data: Path, places: list[dict], code: str) -> dict:
    """place id -> {name: official name in this language or '', source: 'TourAPI <service>' or 'translated'}."""
    loc = LC.get(code)
    table = _load(data, f"{code}/names.json", {}) or {}
    out = {}
    for p in places:
        row = table.get(p["id"]) or {}
        if row.get("name_ko") != p["name"]:   # renamed since names.json was written
            row = {}
        official = squash_ws(row.get(loc.name_key)) if str(row.get(f"{loc.name_key}_source", "")).startswith("TourAPI") else ""
        out[p["id"]] = {"name": official, "source": row.get(f"{loc.name_key}_source") if official else "translated"}
    return out


def _l_item(item: dict, kind: str, code: str, names_l: dict, done: dict) -> dict:
    """An English batch item made into one for `code`: the name fields of the language (the official name or empty
    with source 'translated', plus candidates), mentions with the language's names when known. Same ko_hash."""
    loc = LC.get(code)
    out = dict(item)
    if kind == "places":
        row = names_l.get(item["id"]) or {"name": "", "source": "translated"}
        en_name = out.pop("name_en")
        out.pop("name_en_source", None)
        out = {**{k: out[k] for k in ("id", "slug", "kind", "category", "indexable", "name")},
               loc.name_key: row["name"], f"{loc.name_key}_source": row["source"], "name_rr": romanize(item["name"]),
               "name_en_reference": en_name,
               **({"name_ru_candidate": LC.kontsevich(item["name"])} if code == "ru" else {}),
               **{k: v for k, v in out.items() if k not in ("id", "slug", "kind", "category", "indexable", "name")}}
    if kind == "guides":
        out["items"] = [{**it, f"place_{loc.name_key}": done.get(it.get("place_name") or "", "")} for it in out["items"]]
    if kind == "courses":
        out["stops"] = [{**s, f"place_{loc.name_key}": done.get(s.get("name") or "", "")} for s in out["stops"]]
    if out.get("mentions"):
        out["mentions"] = [{**m, code: done.get(m["ko"], "")} for m in out["mentions"]]
    return out


def chrome_rows(code: str) -> list[dict]:
    """The pages' own words (pipeline/intl_text.py) as strings rows with the English source."""
    loc = LC.get(code)
    rows = []
    for key in intl_text.keys_for(loc):
        base, _, form = key.partition(".")
        src = intl_text.source_for(key)
        note = intl_text.NOTES.get(base, "")
        if form:
            note = (note + " " if note else "") + f"Plural form '{form}' of {loc.english}."
        ph = sorted(set(PLACEHOLDER.findall(src)))
        if ph:
            note = (note + " " if note else "") + f"Keep {', '.join(ph)}."
        rows.append({"id": f"chrome.{key}", "en": src, "where": "pipeline/intl_text.py", **({"note": note} if note else {})})
    return rows


def prepare_l(out: Path, batch: int, data: Path, code: str) -> dict:
    """prepare for another language: the English batches' items (same order, same ko_hash) with the language's name
    fields and rules, then the strings batch (labels from the Korean, the pages' own words from the English)."""
    city.activate_dir(data)   # the city's names in this language (LC.get) and its English address tail (city_fill)
    loc = LC.get(code)
    places_all = json.loads((data / "places.json").read_text("utf-8"))
    places = [p for p in places_all if p.get("status") == "published" and not p.get("duplicate_of")]
    names_en = _name_table(data, places)
    names_l = _names_l(data, places, code)
    done_recs = _load(data, f"{code}/places.json", {}) or {}
    done = {}   # Korean name -> this language's name (official, or an earlier translation still current)
    for p in places:
        nm = names_l[p["id"]]["name"] or squash_ws((done_recs.get(p["id"]) or {}).get(loc.name_key))
        if nm:
            done[p["name"]] = nm
    courses = [c for c in _load(data, "courses.json", []) if c.get("status") == "published"]
    guides = [g for g in _load(data, "guides.json", []) if g.get("status") == "published"]
    events = _load(data, "events.json", [])
    gloss = Glossary(places, names_en, courses)
    by_slug = {p["slug"]: p for p in places}
    order = {"attraction": 0, "food": 1, "stay": 2}
    flagged = [(p, index_status(p)[0]) for p in places]
    flagged.sort(key=lambda x: (not x[1], order.get(x[0]["kind"], 9), x[0].get("tier") != "full", x[0]["name"]))
    out.mkdir(parents=True, exist_ok=True)
    for old in out.glob(f"{code}-*.input.json"):
        old.unlink()
    files: list[dict] = []
    rules = rules_for(code)
    example = {**{k: v for k, v in PLACE_OUTPUT_EXAMPLE.items() if k != "name_en"}, loc.name_key: "…",
               "facts": [{"key": "address", "value": "26 Hosugongwon 1-gil, <the city's English address tail>"},
                         {"key": "usetime", "value": "09:00–18:00", "alternatives": [{"value": "…"}], "note": loc.conflict},
                         {"key": "usefee", "value": "…"}],
               "summary": "…", "faq": [{"q": "…?", "a": "…"}]}

    def write(kind: str, items: list[dict], ex: dict):
        n = len(files) + 1
        path = out / f"{code}-{n:02d}.input.json"
        payload = {"type": kind, "lang": code, "rules": city_fill(rules), "output_file": f"{code}-{n:02d}.output.json",
                   "output_example": city_fill(ex), "items": items}
        path.write_text(json.dumps(payload, ensure_ascii=False, indent=1) + "\n", "utf-8")
        chars = sum(len(HANGUL.findall(json.dumps(i, ensure_ascii=False))) for i in items)
        files.append({"file": str(path), "type": kind, "items": len(items), "hangul_chars": chars,
                      **({"indexable": sum(1 for i in items if i.get("indexable"))} if kind == "places" else {})})

    for i in range(0, len(flagged), batch):
        write("places", [_l_item(place_item(p, names_en[p["id"]], gloss, ok), "places", code, names_l, done)
                         for p, ok in flagged[i:i + batch]], example)
    write("guides", [_l_item(guide_item(g, by_slug, names_en, gloss), "guides", code, names_l, done) for g in guides],
          OUTPUT_EXAMPLES["guides"])
    write("courses", [_l_item(course_item(c, by_slug, names_en, gloss), "courses", code, names_l, done) for c in courses],
          OUTPUT_EXAMPLES["courses"])
    write("events", [_l_item(event_item(sr, gloss), "events", code, names_l, done) for sr in event_series(events)],
          {**OUTPUT_EXAMPLES["events"], "alternatives": {"fee": {"values": ["…"], "note": loc.event_conflict}}})
    labels = [r for r in strings_items(data, places) if not r["id"].startswith("ui:")]
    write("strings", labels + chrome_rows(code), {"id": "FACT_LABELS.usetime", loc.tag: "…"})
    return {"lang": code, "batches": files, "places": len(flagged), "indexable": sum(1 for _, ok in flagged if ok)}


def names_l(data: Path, max_calls: int, offline: bool, code: str) -> dict:
    """names for another language: list every item of the region in the language's TourAPI service (JpnService2 …),
    match published places the way English does (coordinates within MATCH_RADIUS_M and the content type), write
    data/<region>/<code>/names.json. A matched title is the official name (name source 'TourAPI <service>'); every
    other place has an empty name with source 'translated' (the translator writes it). On a provider error the
    message (key masked) is reported and every place stays 'translated'."""
    from pipeline.enrich import load_dotenv
    from pipeline.tourapi import TourAPI, TourAPIError, TourAPIStopError, from_site_config
    from tools.tourapi_bulk import RegionError, region_codes, retry
    loc = LC.get(code)
    base_url = f"https://apis.data.go.kr/B551011/{loc.service}"
    load_dotenv(ROOT / ".env")
    site = json.loads((data / "site.json").read_text("utf-8"))
    places = [p for p in json.loads((data / "places.json").read_text("utf-8")) if p.get("status") == "published"]
    cache = data.parent / "cache" / "tourapi"
    key = os.environ.get("TOURAPI_KEY", "")
    stats = {"lang": code, "service": base_url, "list_items": 0, "live_calls": 0, "cache_hits": 0, "error": "",
             "matched": 0, "matched_by": {}, "ambiguous": [], "published": len(places)}
    items: list[dict] = []
    try:
        kor = from_site_config(site, key, cache, offline=offline, max_calls=4)  # statutory codes (cached)
        regn, signgus, _ = region_codes(kor, site)   # the city's 시군구 (a 광역시: every 구·군), tools/tourapi_bulk.py
        api = TourAPI(key, base_url=base_url, mobile_app=(site.get("tourapi") or {}).get("mobile_app", "WebforAI"),
                      cache_dir=cache, offline=offline, max_calls=max_calls)
        try:
            for signgu, _ in signgus:
                page = 1
                while True:
                    got = retry(api.call, "areaBasedList", lDongRegnCd=regn, lDongSignguCd=signgu, numOfRows=200,
                                pageNo=page, arrange="A")
                    items += got
                    if len(got) < 200:
                        break
                    page += 1
        finally:
            stats["live_calls"], stats["cache_hits"] = api.live_calls + kor.live_calls, api.cache_hits + kor.cache_hits
    except (TourAPIError, TourAPIStopError, StopIteration, RegionError) as err:
        stats["error"] = str(err) or type(err).__name__
    stats["list_items"] = len(items)
    out = {}
    for p in places:
        it, dist, basis = match_en(p, items, latin=not (loc.cjk or code == "ru")) if items else (None, None, "")
        row = {"name_ko": p["name"], loc.name_key: "", f"{loc.name_key}_source": "translated",
               "name_rr": romanize(p["name"]), f"{loc.tag}_contentid": "", f"addr_{loc.tag}": "", "match_m": None,
               "match_basis": ""}
        if it:
            title = squash_ws(re.sub(r"\s*[(（][^()（）]*[가-힣][^()（）]*[)）]", "", it.get("title") or ""))
            if title and not HANGUL.search(title):
                row.update({loc.name_key: title, f"{loc.name_key}_source": f"TourAPI {loc.service}",
                            f"{loc.tag}_contentid": str(it.get("contentid", "")), f"addr_{loc.tag}": squash_ws(it.get("addr1")),
                            "match_m": round(dist, 1), "match_basis": basis})
                stats["matched"] += 1
                stats["matched_by"][basis] = stats["matched_by"].get(basis, 0) + 1
        elif basis == "ambiguous":
            stats["ambiguous"].append(p["name"])
        out[p["id"]] = row
    stats["rejected"] = vet_matches(out, {p["id"]: p for p in places}, loc)
    stats["matched"] -= len(stats["rejected"])
    (data / code).mkdir(exist_ok=True)
    (data / code / "names.json").write_text(json.dumps(out, ensure_ascii=False, indent=2) + "\n", "utf-8")
    return stats


STRONG_BASIS = ("coordinates_type_korean_title", "coordinates_type_same_photo", "coordinates_type_romanized_name")


def building_no(address) -> str:
    """'<도> <시> 해망로 240' -> '240' (the road address's building number), '' without one."""
    text = squash_ws(address.get("value") if isinstance(address, dict) else address)
    m = re.search(r"[가-힣0-9.]+(?:로|길)\s*(\d+(?:-\d+)?)", text)
    return m.group(1) if m else ""


def vet_matches(rows: dict, places: dict, loc) -> list[str]:
    """Review 2026-10-14: a match on coordinates and type alone (one candidate within the radius, nothing else in
    common) gave 이성당's title to six restaurants and the Jangmi Gallery's to the Modern History Museum. Such a
    match stands only when the item's address carries the place's building number, and one TourAPI item names one
    place unless the others also share its Korean title or photo (the same building under two records). A rejected
    match goes back to 'translated'. Returns the place ids whose match was dropped."""
    key, tag = loc.name_key, loc.tag
    official = {pid: r for pid, r in rows.items() if str(r.get(f"{key}_source", "")).startswith("TourAPI")}
    drop = []
    for pid, r in official.items():   # 1. a weak match needs the building number in the item's address
        bno = building_no(((places.get(pid) or {}).get("facts") or {}).get("address"))
        addr_ok = bool(bno) and bno in re.findall(r"\d+(?:-\d+)?", r.get(f"addr_{tag}") or "")
        if r.get("match_basis") not in STRONG_BASIS and not addr_ok:
            drop.append(pid)
    by_item: dict[str, list[str]] = {}
    for pid, r in official.items():
        if pid not in drop:
            by_item.setdefault(r.get(f"{tag}_contentid") or r.get(key), []).append(pid)
    for pids in by_item.values():     # 2. one item, several places: the weak ones give way
        if len(pids) > 1:
            drop += [pid for pid in pids if official[pid].get("match_basis") not in STRONG_BASIS]
    for pid in drop:
        rows[pid].update({key: "", f"{key}_source": "translated", f"{tag}_contentid": "", f"addr_{tag}": "",
                          "match_m": None, "match_basis": "rejected: " + rows[pid].get("match_basis", "")})
    return sorted(drop)


def _merge_place_l(item: dict, inp: dict, today: str, src: dict, code: str) -> dict:
    """_merge_place for another language: its name fields and conflict note; text squashed with _sq."""
    loc = LC.get(code)
    facts = {}
    got = {f["key"]: f for f in item["facts"]}
    for f in inp["facts"]:
        o = got[f["key"]]
        row = {"value": _sq(o["value"]) if "\n" not in o["value"] else o["value"].strip()}
        for part in ("alternatives", "also"):
            if f.get(part):
                row[part] = [{"value": _sq(b["value"] if isinstance(b, dict) else b), "provider": a["provider"]}
                             for a, b in zip(f[part], o[part])]
        if f.get("alternatives"):
            row["note"] = loc.conflict
        facts[f["key"]] = row
    faq_src = [x.get("source", "") for x in src.get("faq") or []]
    det_src = [x.get("source", "") for x in src.get("details") or []]
    return {"slug": inp["slug"], "kind": inp["kind"], "name_ko": inp["name"],
            loc.name_key: inp[loc.name_key] or _sq(item.get(loc.name_key)),
            f"{loc.name_key}_source": inp[f"{loc.name_key}_source"], "summary": _sq(item.get("summary")), "facts": facts,
            "details": [{"heading": _sq(d["heading"]), "text": _sq(d["text"]), "source": s}
                        for d, s in zip(item.get("details") or [], det_src)],
            "faq": [{"q": _sq(f["q"]), "a": _sq(f["a"]), "source": s} for f, s in zip(item.get("faq") or [], faq_src)],
            "ko_hash": inp["ko_hash"], "translated_at": today}


def merge_l(paths: list[Path], data: Path, code: str) -> dict:
    """merge for another language: data/<region>/<code>/{places,guides,courses,events,strings}.json, the same record
    shape as English with the language's name fields, notes and strings field."""
    loc = LC.get(code)
    today = dt.date.today().isoformat()
    ldir = data / code
    ldir.mkdir(exist_ok=True)
    stores = {k: _load(data, f"{code}/{k}.json", {}) or {} for k in CHECKERS}
    places = {p["id"]: p for p in json.loads((data / "places.json").read_text("utf-8"))}
    guides = {g["id"]: g for g in _load(data, "guides.json", [])}
    counts = {k: 0 for k in CHECKERS}
    for path in paths:
        inp = json.loads(_input_for(path).read_text("utf-8"))
        kind = inp["type"]
        by_id = {i["id"]: i for i in inp["items"]}
        for item in json.loads(path.read_text("utf-8"))["items"]:
            src = by_id[item["id"]]
            if kind == "places":
                rec = _merge_place_l(item, src, today, places.get(item["id"], {}), code)
            elif kind == "guides":
                g = guides.get(item["id"], {})
                rec = {"slug": src["slug"], "label": _sq(item["label"]), "title": _sq(item["title"]),
                       "summary": _sq(item["summary"]),
                       "body": [{"heading": _sq(b["heading"]), "text": _sq(b["text"])} for b in item["body"]],
                       "items": [{"place_slug": a["place_slug"], "reason": _sq(b["reason"])}
                                 for a, b in zip(src["items"], item["items"])],
                       "faq": [{"q": _sq(b["q"]), "a": _sq(b["a"]), "source": (a or {}).get("source", "")}
                               for a, b in zip(g.get("faq") or [{}] * len(item["faq"]), item["faq"])],
                       "sources": [{"name": _sq(b["name"]), "url": a["url"]} for a, b in zip(src["sources"], item["sources"])],
                       "ko_hash": src["ko_hash"], "translated_at": today}
            elif kind == "courses":
                rec = {"slug": src["slug"], "name": _sq(item["name"]), "group": _sq(item.get("group")),
                       "duration": _sq(item.get("duration")), "summary": _sq(item["summary"]),
                       "stops": [{"name": _sq(b["name"]), "note": _sq(b.get("note")), "place_slug": a["place_slug"]}
                                 for a, b in zip(src["stops"], item["stops"])],
                       "ko_hash": src["ko_hash"], "translated_at": today}
            elif kind == "events":
                newest = {k: v for k, v in (item.get("newest") or {}).items() if k != "id"}
                newest["id"] = src["newest"]["id"]
                rec = {"series_name": _sq(item["series_name"]), "newest": newest,
                       "alternatives": {f: {"values": item["alternatives"][f]["values"],
                                            "providers": [a["provider"] for a in vals], "note": loc.event_conflict}
                                        for f, vals in src["alternatives"].items()},
                       "highlights": item.get("highlights") or [], "program_notes": item.get("program_notes") or [],
                       "usual": item.get("usual") or [], "editions": item.get("editions") or [],
                       "sources": {ko: tr for ko, tr in zip(src["sources"], item.get("sources") or [])},
                       "ko_hash": src["ko_hash"], "translated_at": today}
            else:
                rec = ({"ko": src["ko"]} if "ko" in src else {"en": src["en"]}) | {loc.tag: _sq(item[loc.tag])}
            stores[kind][item["id"]] = rec
            counts[kind] += 1
    for kind, store in stores.items():
        if store:
            (ldir / f"{kind}.json").write_text(json.dumps(store, ensure_ascii=False, indent=2) + "\n", "utf-8")
    return {"lang": code, **counts}


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    a0 = sub.add_parser("names")
    a0.add_argument("--data", type=Path, default=DATA)
    a0.add_argument("--lang", default="en", choices=LC.CODES)
    a0.add_argument("--max-calls", type=int, default=40)
    a0.add_argument("--offline", action="store_true", help="캐시만 쓴다(네트워크 호출 없음)")
    a1 = sub.add_parser("prepare")
    a1.add_argument("--out", type=Path, required=True)
    a1.add_argument("--batch", type=int, default=40)
    a1.add_argument("--data", type=Path, default=DATA)
    a1.add_argument("--lang", default="en", choices=LC.CODES)
    a2 = sub.add_parser("check")
    a2.add_argument("paths", nargs="+", type=Path)
    a3 = sub.add_parser("merge")
    a3.add_argument("paths", nargs="+", type=Path)
    a3.add_argument("--data", type=Path, default=DATA)
    a = ap.parse_args(argv)
    if a.cmd == "names":
        print(json.dumps(names(a.data, a.max_calls, a.offline, a.lang), ensure_ascii=False))
    elif a.cmd == "prepare":
        print(json.dumps(prepare(a.out, a.batch, a.data, a.lang), ensure_ascii=False, indent=1))
    elif a.cmd == "check":
        problems = check(a.paths)
        print("\n".join(problems) or "OK")
        return 1 if problems else 0
    else:
        print(json.dumps(merge(a.paths, a.data), ensure_ascii=False))
    return 0


if __name__ == "__main__":
    sys.exit(main())
