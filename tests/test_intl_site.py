"""The seven language versions (/ja/ /zh-hans/ /zh-hant/ /de/ /fr/ /es/ /ru/, pipeline/en_site.py + pipeline/locales.py).

Built in production from a copy of data/gunsan with tiny fake translations written into tmp folders here (never into
data/gunsan): four places (one with two-source values and a designation, a restaurant, a stay, one below the index
rule), one more place whose record is stale (its ko_hash is not the current Korean's), the food hub guide, a course
and an event series with two-source values, and complete strings (labels from the Korean, the pages' own words from
pipeline/intl_text.py) — the records written exactly the way tools/en_content.py merge writes them. A second, small
build of the sample data (no English) has Japanese only, plus Spanish with incomplete strings (not built)."""
import html
import json
import re
import shutil
import xml.etree.ElementTree as ET
from pathlib import Path
from urllib.parse import unquote, urlsplit

import pytest

from pipeline import intl_text
from pipeline import locales as LC
from pipeline.build import build
from pipeline.en_source import (Glossary, _name_table, course_item, current_hashes, event_item, event_series,
                                guide_item, place_item, romanize)
from pipeline.validate import hreflang_problems, scan_file, validate
from tools.en_content import PLACEHOLDER, strings_items

ROOT = Path(__file__).resolve().parent.parent
GUNSAN, SAMPLE = ROOT / "data" / "gunsan", ROOT / "data" / "sample"
NEW = ("ja", "zh-hans", "zh-hant", "de", "fr", "es", "ru")
PLACES = ("gunsan-1379526", "gunsan-306687", "gunsan-307033", "gunsan-305362")   # conflict · food+designation · stay · noindex
STALE = "gunsan-305373"
GUIDE, COURSE, SERIES = "guide-13", "gunsan-course-m2135-2", "군산-수제맥주블루스-페스티벌"
WORD = {"ja": "情報", "zh-hans": "信息", "zh-hant": "資訊", "de": "Angabe", "fr": "Donnée", "es": "Dato", "ru": "Сведения"}
NAME = {"ja": "スポット", "zh-hans": "景点", "zh-hant": "景點", "de": "Ort", "fr": "Lieu", "es": "Lugar", "ru": "Место"}
PROSE = {"ja": "これは{n}番目の場所です。駐車場があります。",
         "zh-hans": "这是第{n}个地点。这里有停车场。",
         "zh-hant": "這是第{n}個地點。這裡有停車場。",
         "de": "Das ist der Ort Nummer {n}. Es gibt einen Parkplatz und die Halle ist für alle offen.",
         "fr": "C'est le lieu numéro {n}. Il y a un parking et la salle est ouverte pour tous.",
         "es": "Es el lugar número {n}. Hay un aparcamiento y la sala está abierta para todos.",
         "ru": "Это место номер {n}. Здесь есть парковка, и зал открыт для всех."}
QUESTION = {"ja": "{n}番目の質問ですか？", "zh-hans": "这是第{n}个问题吗？", "zh-hant": "這是第{n}個問題嗎？",
            "de": "Ist das die Frage {n}?", "fr": "Est-ce la question {n} ?", "es": "¿Es la pregunta {n}?",
            "ru": "Это вопрос {n}?"}
HANGUL = re.compile(r"[가-힣]")


def fake(code: str, text: str) -> str:
    """A value in the language: its words replaced, digits, times, phones and punctuation kept."""
    t = HANGUL.sub("", re.sub(r"[가-힣A-Za-z][가-힣A-Za-z'’]*", WORD[code], str(text or "")))
    return re.sub(r"\s+", " ", t).strip() or WORD[code]


def write_translations(data: Path, codes, stale: str | None = STALE, places=PLACES, guide=GUIDE, course=COURSE,
                       series=SERIES, strings_ok: bool = True) -> None:
    """data/<code>/{places,guides,courses,events,strings}.json for each code, shaped as en_content merge writes them."""
    pl = [p for p in json.loads((data / "places.json").read_text("utf-8"))
          if p.get("status") == "published" and not p.get("duplicate_of")]
    by_id, by_slug = {p["id"]: p for p in pl}, {p["slug"]: p for p in pl}
    names_en = _name_table(data, pl)
    hashes = current_hashes(data)
    gl = Glossary(pl, names_en, [])
    labels = [r for r in strings_items(data, pl) if not r["id"].startswith("ui:")]
    for code in codes:
        loc = LC.get(code)
        d = data / code
        d.mkdir()
        recs = {}
        for i, pid in enumerate([*places, *([stale] if stale else [])], 1):
            item = place_item(by_id[pid], names_en[pid], gl, True)
            facts = {}
            for f in item["facts"]:
                row = {"value": fake(code, f["value"])}
                if f.get("alternatives"):
                    row["alternatives"] = [{"value": fake(code, a["value"]), "provider": a["provider"]} for a in f["alternatives"]]
                    row["note"] = loc.conflict
                if f.get("also"):
                    row["also"] = [{"value": fake(code, a["value"]), "provider": a["provider"]} for a in f["also"]]
                facts[f["key"]] = row
            src = by_id[pid]
            recs[pid] = {"slug": item["slug"], "kind": item["kind"], "name_ko": item["name"],
                         loc.name_key: f"{NAME[code]}{i}", f"{loc.name_key}_source": "translated",
                         "summary": PROSE[code].format(n=i), "facts": facts,
                         "details": [{"heading": WORD[code], "text": PROSE[code].format(n=i), "source": x.get("source", "")}
                                     for x in src.get("details") or []],
                         "faq": [{"q": QUESTION[code].format(n=j), "a": PROSE[code].format(n=j), "source": x.get("source", "")}
                                 for j, x in enumerate(src.get("faq") or [], 1)],
                         "ko_hash": "0" * 16 if pid == stale else item["ko_hash"], "translated_at": "2026-10-13"}
        guides = {}
        if guide:
            g = next(x for x in json.loads((data / "guides.json").read_text("utf-8")) if x["id"] == guide)
            it = guide_item(g, by_slug, names_en, None)
            colon = "：" if loc.cjk else ": "
            guides[guide] = {"slug": it["slug"], "label": WORD[code],
                             "title": f"{NAME[code]}{colon}{WORD[code]}{loc.list_sep}{NAME[code]}",
                             "summary": PROSE[code].format(n=1), "body": [{"heading": WORD[code], "text": PROSE[code].format(n=k)}
                                                                         for k, _ in enumerate(it["body"], 1)],
                             "items": [{"place_slug": x["place_slug"], "reason": PROSE[code].format(n=k)}
                                       for k, x in enumerate(it["items"], 1)],
                             "faq": [{"q": QUESTION[code].format(n=k), "a": PROSE[code].format(n=k), "source": ""}
                                     for k, _ in enumerate(it["faq"], 1)],
                             "sources": [{"name": WORD[code], "url": s["url"]} for s in it["sources"]],
                             "ko_hash": hashes["guides"][guide], "translated_at": "2026-10-13"}
        courses = {}
        if course:
            c = next(x for x in json.loads((data / "courses.json").read_text("utf-8")) if x["id"] == course)
            it = course_item(c, by_slug, names_en, None)
            courses[course] = {"slug": it["slug"], "name": f"{NAME[code]} 1", "group": WORD[code],
                               "duration": WORD[code] if it["duration"] else "", "summary": PROSE[code].format(n=1),
                               "stops": [{"name": f"{NAME[code]}{k}", "note": "", "place_slug": s["place_slug"]}
                                         for k, s in enumerate(it["stops"], 1)],
                               "ko_hash": hashes["courses"][course], "translated_at": "2026-10-13"}
        events = {}
        if series:
            sr = next(x for x in event_series(json.loads((data / "events.json").read_text("utf-8"))) if x["slug"] == series)
            it = event_item(sr, None)
            newest = {k: fake(code, v) for k, v in it["newest"].items() if isinstance(v, str) and k not in ("id",)}
            newest.pop("address_en_candidate", None)
            newest.update(id=it["newest"]["id"], notes=[PROSE[code].format(n=k) for k, _ in enumerate(it["newest"]["notes"], 1)])
            events[series] = {"series_name": f"{NAME[code]} {WORD[code]}", "newest": newest,
                              "alternatives": {f: {"values": [fake(code, a["value"]) for a in vals],
                                                   "providers": [a["provider"] for a in vals], "note": loc.event_conflict}
                                               for f, vals in it["alternatives"].items()},
                              "highlights": [PROSE[code].format(n=k) for k, _ in enumerate(it["highlights"], 1)],
                              "program_notes": [PROSE[code].format(n=k) for k, _ in enumerate(it["program_notes"], 1)],
                              "usual": [{"text": WORD[code], "place": WORD[code]} for _ in it["usual"]],
                              "editions": [{"id": e["id"], "name": WORD[code], "period_text": WORD[code], "place_name": WORD[code]}
                                           for e in it["editions"]],
                              "sources": {s: WORD[code] for s in it["sources"]},
                              "ko_hash": it["ko_hash"], "translated_at": "2026-10-13"}
        strings = {r["id"]: {"ko": r["ko"], loc.tag: f"{WORD[code]}{k}"} for k, r in enumerate(labels, 1)}
        keys = intl_text.keys_for(loc)
        for key in keys[: None if strings_ok else len(keys) // 2]:
            src = intl_text.source_for(key)
            strings[f"chrome.{key}"] = {"en": src, loc.tag: " ".join([WORD[code], *PLACEHOLDER.findall(src)])}
        for name, store in (("places", recs), ("guides", guides), ("courses", courses), ("events", events),
                            ("strings", strings)):
            (d / f"{name}.json").write_text(json.dumps(store, ensure_ascii=False, indent=1), "utf-8")


@pytest.fixture(scope="module")
def site(tmp_path_factory):
    tmp = tmp_path_factory.mktemp("intl")
    data = tmp / "data"
    # the real data/gunsan/<code>/ folders (official TourAPI names so far) give way to this test's own translations
    shutil.copytree(GUNSAN, data, ignore=lambda d, names: [n for n in names if n == "cache" or
                                                           (Path(d) == GUNSAN and n in NEW)])
    write_translations(data, NEW)
    out = tmp / "dist"
    stats = build(data, out, "production")
    en = json.loads((data / "en" / "places.json").read_text("utf-8"))
    by_h1: dict[str, list[str]] = {}   # the English place pages by their H1 (name_en)
    for f in (out / "en" / "places").glob("*/index.html"):
        h1 = re.search(r'<h1 class="d1 vt-title">(.*?)</h1>', f.read_text("utf-8"), re.S)
        if h1:
            by_h1.setdefault(html.unescape(h1.group(1)), []).append(f.parent.name)
    return {"data": data, "out": out, "stats": stats, "en": en, "by_h1": by_h1}


def _slug(site, pid: str) -> str:
    """The English page slug of a place (every version uses it)."""
    hits = site["by_h1"].get(site["en"][pid]["name_en"], [])
    assert len(hits) == 1, (pid, hits)
    return hits[0]


def _ko_page(site, pid: str) -> Path:
    slug = next(p["slug"] for p in json.loads((site["data"] / "places.json").read_text("utf-8")) if p["id"] == pid)
    return site["out"] / "places" / slug / "index.html"


def test_locale_formats():
    d = "2026-10-13"   # a Tuesday
    assert [LC.get(c).date(d) for c in NEW] == ["2026年10月13日（火）", "2026年10月13日（周二）", "2026年10月13日（週二）",
                                               "13. Oktober 2026 (Di.)", "13 octobre 2026 (mar.)",
                                               "13 de octubre de 2026 (mar.)", "13 октября 2026 г. (вт)"]
    assert [LC.get(c).money(3000) for c in NEW] == ["3,000ウォン", "3,000韩元", "3,000韓元", "3.000 Won",
                                                   "3\u202f000 wons", "3.000 wones", "3\u202f000 вон"]
    assert [LC.get(c).dist(1234) for c in NEW] == ["1.2 km", "1.2 km", "1.2 km", "1,2 km", "1,2 km", "1,2 km", "1,2 km"]
    assert LC.get("en").date(d) == "October 13, 2026" and LC.get("en").md(d) == "Oct 13"
    ru = LC.get("ru")
    assert [ru.plural_form(n) for n in (1, 2, 5, 11, 21, 22, 25)] == ["one", "few", "many", "many", "one", "few", "many"]
    assert LC.get("ja").sentences("一つ目です。二つ目です！三つ目？") == ["一つ目です。", "二つ目です！", "三つ目？"]
    assert LC.get("de").sentences("Am 13. Oktober ist es offen. Nr. 5 ist zu.") == ["Am 13. Oktober ist es offen.", "Nr. 5 ist zu."]
    assert LC.kontsevich("군산") == "Кунсан" and LC.kontsevich("신라") == "Силла" and LC.kontsevich("선유도") == "Сонюдо"
    assert LC.area_name("장미동", "ru") == "Чанми-дон" and LC.area_name("장미동", "de") == "Jangmi-dong"


def test_missing_language_and_incomplete_strings(tmp_path):
    """No data/<region>/<code>: no pages, no hreflang, no menu item. Incomplete UI words: not built (a warning).
    Without English, the slugs are what English would give (romanized)."""
    data = tmp_path / "data"
    shutil.copytree(SAMPLE, data)
    site = json.loads((data / "site.json").read_text("utf-8"))   # the sample's contact is a Korean placeholder
    site["operator"]["contact"] = "corrections@test.invalid"
    (data / "site.json").write_text(json.dumps(site, ensure_ascii=False), "utf-8")
    pid = json.loads((data / "places.json").read_text("utf-8"))[0]["id"]
    write_translations(data, ["ja"], stale=None, places=(pid,), guide=None, course=None, series=None)
    write_translations(data, ["es"], stale=None, places=(pid,), guide=None, course=None, series=None, strings_ok=False)
    out = tmp_path / "dist"
    stats = build(data, out, "sample")
    assert stats["intl"]["ja"]["places"] == 1 and stats["intl_skipped"]["es"] > 0 and "en" not in stats
    assert (out / "ja").exists() and not (out / "es").exists() and not (out / "en").exists()
    for f in out.rglob("*.html"):
        html = f.read_text("utf-8")
        assert 'hreflang="es"' not in html and 'hreflang="en"' not in html and 'lang="es"' not in html, f
    ko = next(f for f in (out / "places").glob("*/index.html"))
    menu = re.findall(r'class="mast-lang" href="([^"]*)" hreflang="([^"]*)"', ko.read_text("utf-8"))
    assert [h for _, h in menu] == ["ko", "ja"]
    slug = next(p.parent.name for p in (out / "ja" / "places").glob("*/index.html"))
    assert re.fullmatch(r"[a-z0-9]+(-[a-z0-9]+)*", slug)
    errors, warnings, _ = validate(data, out, "sample")
    assert errors == [], errors[:5]
    assert any("/es/" in w and "chrome" in w for w in warnings)


def test_validator_reads_japanese_citations_and_unspaced_sentences():
    """2026-10-14 (first /ja/ build): a citation line '出典：群山市文化観光' is a label of names, not a kana-less
    sentence; and Japanese/Chinese structured-data text is compared without whitespace, sentence by sentence (the
    page joins elements with a space and the first sentence is often under 25 characters) — every sentence must
    still be on screen."""
    from pipeline.validate import PageScan, jsonld_visibility
    html = ('<html lang="ja"><body><div data-block="faq"><div class="qa"><h3>予約できますか？</h3><p>はい、予約できます。'
            '</p></div><p class="ch-notes">出典：群山市文化観光</p></div>'
            '<div data-block="summary"><p class="lede">メロディは体験施設です。</p></div><dl><dt>電話</dt><dd>010</dd></dl>'
            '<p class="lede-more">ブドウ収穫の体験を予約制で運営しています。</p></body></html>')
    p = PageScan()
    p.feed(html)
    assert "出典：群山市文化観光" in "".join(p.notes) and "出典" in p.blocks["faq"]
    node = {"@type": "Place", "description": "メロディは体験施設です。ブドウ収穫の体験を予約制で運営しています。"}
    assert jsonld_visibility([node], p) == []
    node["description"] += "画面にない文です。"
    assert jsonld_visibility([node], p) and "画面にない" in jsonld_visibility([node], p)[0]
