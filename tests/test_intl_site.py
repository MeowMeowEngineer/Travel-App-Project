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

from pipeline import intl_text, present
from pipeline import locales as LC
from pipeline.build import build
from pipeline.en_source import (Glossary, _name_table, course_item, current_hashes, event_item, event_series,
                                guide_item, place_item, romanize)
from pipeline.validate import hreflang_problems, scan_file, validate
from tools.en_content import PLACEHOLDER, strings_items

ROOT = Path(__file__).resolve().parent.parent
GUNSAN, SAMPLE = ROOT / "data" / "gunsan", ROOT / "data" / "sample"
NEW = ("ja", "zh-hans", "zh-hant", "de", "fr", "es", "ru")
PLACES = ("gunsan-305395", "gunsan-306687", "gunsan-307033", "gunsan-305362")   # conflict · food+designation · stay · noindex
# a dated notice of the facility (pipeline/notices.py) on PLACES[0], written into the copy: one still current, one ended
NOTICES = [{"id": "test-current", "place_ids": [PLACES[0]], "kind": "hours", "start": "2099-10-09", "end": "2099-10-11",
            "from": "18:00", "to": "22:00", "last_entry": "21:40", "provider": "군산근대역사박물관 홈페이지",
            "url": "https://museum.gunsan.go.kr/new/board/index.do?act=view&bbs_id=1&id=9999", "checked_at": "2026-10-15",
            "until": "2099-10-11"},
           {"id": "test-ended", "place_ids": [PLACES[0]], "kind": "closed", "date": "2000-01-03",
            "provider": "군산근대역사박물관 홈페이지", "url": "https://museum.gunsan.go.kr/new/board/index.do?act=view&bbs_id=1&id=9998",
            "checked_at": "1999-12-30", "until": "2000-01-03"}]
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
    (data / "notices.json").write_text(json.dumps(NOTICES, ensure_ascii=False), "utf-8")
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


def _menu(page: Path) -> str:
    return re.search(r'<details class="lang-menu".*?</details>', page.read_text("utf-8"), re.S).group(0)


def _menu_items(page: Path) -> dict:
    """{hreflang: (href, note)} of a page's language menu."""
    return {h: (href, note) for href, h, note in re.findall(
        r'<a class="mast-lang" href="([^"]*)" hreflang="([^"]*)" lang="[^"]*"(?: aria-current="true")?>[^<]*'
        r'(?:<small class="lang-note">([^<]*)</small>)?</a>', _menu(page))}


def test_locale_formats():
    d = "2026-10-13"   # a Tuesday
    assert [LC.get(c).date(d) for c in NEW] == ["2026年10月13日（火）", "2026年10月13日（周二）", "2026年10月13日（週二）",
                                               "13. Oktober 2026 (Di.)", "13 octobre 2026 (mar.)",
                                               "13 de octubre de 2026 (mar.)", "13 октября 2026 г. (вт)"]
    assert [LC.get(c).money(3000) for c in NEW] == ["3,000ウォン", "3,000韩元", "3,000韓元", "3.000 Won",
                                                   "3\u202f000 wons", "3.000 wones", "3\u202f000 вон"]
    assert [LC.get(c).dist(1234) for c in NEW] == ["1.2 km", "1.2 km", "1.2 km", "1,2 km", "1,2 km", "1,2 km", "1,2 км"]
    assert LC.get("en").date(d) == "October 13, 2026" and LC.get("en").md(d) == "Oct 13"
    # a month standing alone (an end the source gives only as a month): Russian in the nominative
    assert [LC.get(c).mon("2026-10") for c in ("en", "de", "ja", "ru")] == ["Oct", "Okt.", "10月", "окт."]
    assert LC.get("ru").mon("2026-05") == "май" and LC.get("ru").md("2026-05-01") == "1 мая"
    ru = LC.get("ru")
    assert [ru.plural_form(n) for n in (1, 2, 5, 11, 21, 22, 25)] == ["one", "few", "many", "many", "one", "few", "many"]
    assert LC.get("ja").sentences("一つ目です。二つ目です！三つ目？") == ["一つ目です。", "二つ目です！", "三つ目？"]
    assert LC.get("de").sentences("Am 13. Oktober ist es offen. Nr. 5 ist zu.") == ["Am 13. Oktober ist es offen.", "Nr. 5 ist zu."]
    assert LC.kontsevich("군산") == "Кунсан" and LC.kontsevich("신라") == "Силла" and LC.kontsevich("선유도") == "Сонюдо"
    assert LC.area_name("장미동", "ru") == "Чанми-дон" and LC.area_name("장미동", "de") == "Jangmi-dong"


def test_missing_language_and_incomplete_strings(tmp_path, capsys):
    """No data/<region>/<code>: no pages, no hreflang, no menu item. Incomplete UI words: not built (a warning).
    Without English, the slugs are what English would give (romanized). A version that lacks translations of
    published records gets a build warning with the count (QA 2026-10-15 SRC-03a)."""
    data = tmp_path / "data"
    shutil.copytree(SAMPLE, data)
    site = json.loads((data / "site.json").read_text("utf-8"))   # the sample's contact is a Korean placeholder
    site["operator"]["contact"] = "corrections@test.invalid"
    (data / "site.json").write_text(json.dumps(site, ensure_ascii=False), "utf-8")
    pid = json.loads((data / "places.json").read_text("utf-8"))[0]["id"]
    write_translations(data, ["ja"], stale=None, places=(pid,), guide=None, course=None, series=None)
    write_translations(data, ["es"], stale=None, places=(pid,), guide=None, course=None, series=None, strings_ok=False)
    out = tmp_path / "dist"
    capsys.readouterr()
    stats = build(data, out, "sample")
    assert stats["intl"]["ja"]["places"] == 1 and stats["intl_skipped"]["es"] > 0 and "en" not in stats
    untranslated = stats["intl"]["ja"]["untranslated"]
    published = sum(1 for p in json.loads((data / "places.json").read_text("utf-8")) if p.get("status") == "published")
    assert untranslated["places"] == published - 1 > 0
    assert f"경고: ja 번역이 없는 공개 항목 {sum(untranslated.values())}건" in capsys.readouterr().err
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


def _search_words(page: str) -> dict:
    return json.loads(html.unescape(re.search(r'data-words="([^"]+)"', page).group(1)))


SEARCH_STRIP = re.compile(r"[\s·\-()（）\[\]|,]")


def _found(rows: list[dict], query: str) -> list[dict]:
    """assets/search.js score() replayed: the rows a query finds (any of n, a, o, v, m, g, or 동·권역·type)."""
    def norm(s):
        return SEARCH_STRIP.sub("", str(s or "").lower())
    q = norm(query)
    return [r for r in rows if any(q in norm(r.get(f)) for f in ("n", "a", "o", "v", "m", "g"))
            or q in norm(" ".join([r.get("d") or "", r.get("r") or "", r.get("t") or ""]))]


def test_list_filter_words_cover_every_version():
    """QA 2026-10-15 SRC-01: the list filter bar's own words (locales.LIST_WORDS) exist for Korean and every version,
    each with the same keys, hand-written (no English stand-in for a version that lacks them)."""
    assert set(LC.LIST_WORDS) >= {"ko", *LC.ORDER}
    for code, w in LC.LIST_WORDS.items():
        assert set(w) == set(LC.LIST_WORDS["ko"]), code
        assert all(str(v).strip() for v in w.values()) and "{m}" in w["of"], code
        # the zero-result panel's buttons (a chip's label in {v}) and the map caption's places off the map ({n})
        assert "{v}" in w["clear_one"] and "{n}" in w["off_map"] and "{" not in w["clear_all"], code
        if code != "ko":
            assert not HANGUL.search(" ".join(w.values())), code


def _bar(h: str) -> str:
    m = re.search(r'<div class="filters" data-filters hidden>.*?<div class="ledger" data-ledger>', h, re.S)
    assert m, "no filter bar"
    return m.group(0)


# ------------------------------------------------------------------ QA 2026-10-15: call links, booking sites, dates
def _kf_tel(page: str) -> str:
    """The place opening's call tile (kf-tel) as markup."""
    i = page.index('class="kf-i kf-tel')
    return page[i:page.index("</div>", i)]


def _fact_row(page: str, key: str) -> str:
    i = page.index(f'<dd data-key="{key}">')
    return page[i:page.index("</dd>", i)]


@pytest.fixture(scope="module")
def real():
    """The real data/gunsan with every version, on a fixed build date (2026-10-13: the museum's weekend programme,
    '2026. 6. 6. ~ 10월', is running)."""
    from pipeline import en_site
    from pipeline.build import State, kakao_sdk_url, make_env
    S = State(GUNSAN, "production")
    S.today = "2026-10-13"
    S.intl = en_site.load_all(S, GUNSAN)
    S.en = S.intl.sites.get("en")
    env = make_env()
    env.globals["kakao_sdk"] = kakao_sdk_url(S.site)
    return {"S": S, "env": env}


MUSEUM_EV = "fest-군산근대역사박물관-주말상설행사-2026"


TICKET_PLACES = ("근대역사박물관", "구-일본-제18은행-군산지점", "군산근대건축관", "진포해양공원", "채만식-문학관",
                 "31운동-100주년-기념관", "금강미래체험관")


def test_japanese_and_chinese_group_headers_label_their_rows():
    """A '【…】' header line in Japanese and Chinese is the group's name, as '[…]' is in the other versions: the fee tile
    shows the group's first row, never the bare header; the fee pair reads the Korean visitor's group in the
    translated table (review 2026-10-18: the price row as main, the ticket's name and price as sub)."""
    from pipeline import en_site
    ja = LC.get("ja")
    assert en_site.brief_en("usefee", "【個人】\n- 大人500ウォン\n- 子ども200ウォン\n【団体】\n- 大人300ウォン", ja) == \
        {"main": "大人500ウォン", "sub": "個人", "more": True}
    ko = "[박물관 통합권]\n- 성인 3,000원\n[개별권]\n- 성인 2,000원"
    names = ("博物館統合券", "統合券")
    assert en_site.fee_pair(ko, "【博物館統合券】\n- 大人3,000ウォン\n【個別券】\n- 大人2,000ウォン", 3000, names, ja) == \
        {"main": "大人2,000ウォン", "sub": "博物館統合券：大人3,000ウォン", "more": True}
    en = LC.get("en")
    names = ("Museum combined ticket", "Combined ticket")
    assert en_site.fee_pair(ko, "[Museum combined ticket]\n- Adults 3,000 won\n[Single-site ticket]\n- Adults 2,000 won",
                            3000, names, en) == \
        {"main": "Adults 2,000 won", "sub": "Museum combined ticket: Adults 3,000 won", "more": True}
    # a table without the ticket: its own row, the ticket's price from tickets.json
    assert en_site.fee_pair("- 성인 500원\n- 어린이 200원", "- Adults 500 won\n- Children 200 won", 3000, names, en) == \
        {"main": "Adults 500 won", "sub": "Museum combined ticket: Adults 3,000 won", "more": True}
    # residents first: the visitor's group, in the same place among the translated groups
    assert en_site.fee_pair("[군산시민]\n- 성인 1,000원\n[타지역]\n- 성인 2,000원",
                            "[Gunsan residents]\n- Adults 1,000 won\n[Other regions]\n- Adults 2,000 won", 5000,
                            ("Geumgang area combined ticket", "Combined ticket"), en) == \
        {"main": "Adults 2,000 won", "sub": "Combined ticket: Adults 5,000 won", "more": True}   # the name: too long
    assert en_site.fee_pair(ko, "- Adults 3,000 won\n- Adults 2,000 won", 3000, names, en) is None   # groups do not line up
    assert en_site.fee_pair(ko, "[A]\n- Adults 3,000 won\n[B]\n- Adults 1,000 won", 3000, names, en) is None  # not the amount
    assert en_site.fee_pair(ko, "[A]\n- Adults 3,000 won\n[B]\n- Adults 2,000 won", 3000, ("", ""), en) is None


def test_cjk_hours_tiles_cut_at_their_own_marks_and_keep_the_season():
    """Review 2026-10-18: a Japanese or Chinese hours value is cut at '／', at a '/' with no space before it and after
    a range another part follows (never inside brackets), as the Korean tile reads its ranges one by one; a long part
    loses its months in brackets before its season word; '[Season]' headers inside a line label their range in every
    version; a last entry the Korean tile shows stays."""
    from pipeline import en_site
    ja, zh, en = LC.get("ja"), LC.get("zh-hans"), LC.get("en")
    b = en_site.brief_en
    assert b("usetime", "3–10月 09:00–18:00（入場締切17:30）／11–2月 09:00–17:00（入場締切16:30）", ja, keep_last=True) == \
        {"main": "3–10月 09:00–18:00（入場締切17:30）", "sub": "11–2月 09:00–17:00（入場締切16:30）", "more": False}
    assert b("usetime", "3–10月 09:00–18:00（17:30停止入场）/ 11–2月 09:00–17:00（16:30停止入场）", zh, keep_last=True)["sub"] == \
        "11–2月 09:00–17:00（16:30停止入场）"
    assert b("usetime", "【夏季（3月–10月）】\n09:00–18:00（入場締切17:30）\n【冬季（11月–2月）】\n09:00–17:00（入場締切16:30）",
             ja, keep_last=True) == {"main": "夏季 09:00–18:00（入場締切17:30）", "sub": "冬季 09:00–17:00（入場締切16:30）",
                                     "more": True}
    v = "【夏季（3月–10月）】 09:00–18:00 【冬季（11月–2月）】 09:00–17:00 ※入場は終了30分前まで可能"
    assert (b("usetime", v, ja)["main"], b("usetime", v, ja)["sub"]) == ("夏季 09:00–18:00", "冬季 09:00–17:00")
    assert (b("usetime", "冬季 09:00–17:00 夏季 09:00–18:00", ja)["main"], b("usetime", "冬季09:00–17:00，夏季09:00–18:00", zh)["sub"]) \
        == ("冬季 09:00–17:00", "夏季09:00–18:00")
    # never cut inside brackets; a fee keeps its '／' (a price with its other price)
    assert en_site._segments("11:30–22:30（準備時間 15:00–17:00／ラストオーダー 21:30）", True, True) == \
        [("", "11:30–22:30（準備時間 15:00–17:00／ラストオーダー 21:30）")]
    assert len(en_site._segments("成人（群山市民）1,000（500）／700（300）", False, True)) == 1
    # a part that holds its only time in brackets keeps the time
    assert b("usetime", "時間旅行観光案内所（10:00–17:00）／チョウォン写真館（09:00–21:30）", ja)["main"] == "10:00–17:00"
    # inline '[Season]' headers in the other versions too; the rule of a '※' note is rule_part's
    v = "[Sommer (März–Oktober)] 09:00–18:00 [Winter (November–Februar)] 09:00–17:00 ※ Einlass bis 30 Minuten vor Schließung"
    assert (b("usetime", v, LC.get("de"))["main"], b("usetime", v, LC.get("de"))["sub"]) == \
        ("Sommer (März–Oktober) 09:00–18:00", "Winter (November–Februar) 09:00–17:00")
    assert en_site.rule_part(v) == "Einlass bis 30 Minuten vor Schließung"
    # the other versions cut after a range only where another part with a range of its own follows (never inside or
    # before brackets), and keep their own tile length
    de = LC.get("de")
    assert b("usetime", "Montag 09:00–18:00 Dienstag–Sonntag 09:00–21:30", de) == \
        {"main": "Montag 09:00–18:00", "sub": "Dienstag–Sonntag 09:00–21:30", "more": False}
    assert en_site._segments("09:00–18:00 daily (break 15:00–17:00)", True) == [("", "09:00–18:00 daily (break 15:00–17:00)")]
    assert en_site._segments("09:00–18:00 except Mondays", True) == [("", "09:00–18:00 except Mondays")]
    assert en_site._segments("Open (Mon 09:00–18:00 Tue 10:00–17:00)", True) == [("", "Open (Mon 09:00–18:00 Tue 10:00–17:00)")]
    assert en_site.rule_part("Summer 10:00–18:00 / winter 10:00–17:00, entry until 30 minutes before closing") == \
        "entry until 30 minutes before closing"
    assert en_site.last_entry_tr("[Summer (March–October)]\n09:00–18:00 (last entry 17:30)\n[Winter (November–February)]\n"
                                 "09:00–17:00 (last entry 16:30)", en) == "Summer (last entry 17:30), Winter (last entry 16:30)"
    assert en_site.last_entry_tr("【夏季（3–10月）】 09:00–18:00（入場締切17:30） 【冬季（11月–2月）】 09:00–17:00（入場締切16:30）", ja) \
        == "夏季（入場締切17:30）、冬季（入場締切16:30）"
    # the last entry the Korean tile shows: a part that ends in it stays whole, here and in Japanese
    v = "March–October 09:00–18:00 (last entry 17:30) / November–February 09:00–17:00 (last entry 16:30)"
    assert b("usetime", v, en, keep_last=True) == {
        "main": "March–October 09:00–18:00 (last entry 17:30)", "sub": "November–February 09:00–17:00 (last entry 16:30)",
        "more": False}
    assert b("usetime", v, en)["main"] == "March–October 09:00–18:00"
    assert b("usetime", "09:00–21:00（入場締切20:30）", ja, keep_last=True)["main"] == "09:00–21:00（入場締切20:30）"


HOME_H1 = {"en": "All About Gunsan Travel", "ja": "群山旅行のすべて", "zh-hans": "群山旅游全攻略", "zh-hant": "群山旅遊全攻略",
           "de": "Alles über Gunsan", "fr": "Tout sur Gunsan", "es": "Todo sobre Gunsan", "ru": "Всё о Кунсане"}


def test_course_words_cover_every_version():
    """QA 2026-10-15 F09: the course pages' words (locales.COURSE_WORDS) exist for Korean and every version with the
    same keys, hand-written; a plural value has exactly the language's plural forms, a weekday tuple seven entries;
    no Korean script outside Korean."""
    assert set(LC.COURSE_WORDS) == {"ko", *LC.ORDER}
    keys = set(LC.COURSE_WORDS["ko"])
    for code, w in LC.COURSE_WORDS.items():
        assert set(w) == keys, (code, set(w) ^ keys)
        for k, v in w.items():
            if isinstance(v, dict):
                assert code != "ko" and set(v) == set(LC.get(code).plural), (code, k)
                vals = list(v.values())
            else:
                vals = list(v) if isinstance(v, tuple) else [v]
            assert all(str(x).strip() for x in vals), (code, k)
            if code != "ko":
                assert not HANGUL.search(" ".join(map(str, vals))), (code, k)
        assert all(len(w[k]) == 7 for k in ("closed_day", "wd_short")) and len(w["missing_items"]) == 2, code
        assert LC.course_word(code, "closed_n", 5, day=w["closed_day"][0])
        assert "{n}" in str(w["runs"]) and "{nos}" in w["routes_more"] and "{m}" in w["past_hour"], code
    assert LC.course_word("ru", "runs", 2) == "2 рейса" and LC.course_word("en", "hours_n", 12) == "12 hours"


def _course_page(site, code: str, cid: str) -> tuple[Path, str]:
    for f in (site["out"] / code / "courses").glob("*/index.html"):
        h = f.read_text("utf-8")
        if f'data-record="course:{cid}"' in h:
            return f, h
    raise AssertionError((code, cid))
