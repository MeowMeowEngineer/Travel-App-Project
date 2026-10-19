"""The AI art slots of the owner's second picture list (docs/handover/image_prompts_round2_2026-10-13.md, groups
H·I·J·K·L·M·N·P·Q·S): theme.head, videos.head, course.banner, area, events.month, events.kind, abroad.group,
og.<lang>, en.guide.banner and about.head, built through the one AI art system (pipeline/art.py,
templates/_art.html.j2, css/49-art.css).

A small world is built twice from the sample data — with an art.json naming a tiny test picture for every new slot, and
without it — plus fake English and Japanese translations (tests/test_intl_site.write_translations), videos, /abroad/
articles, a past and a coming event and two 권역 anchors: the pictures show on exactly their pages, in the page's
language (the alt; no label on any page since the owner dropped it, 2026-10-13 night), lazy below the first screen,
never on a place page, in a place card or in JSON-LD; a page
without its picture is byte for byte the page of a build without art (and the stylesheet carries the slot rules only
when a page shows such a picture). The owner's list and the code agree: every slot it names is a place the site has
(but chat.empty, which waits for the chat panel, and the dropped home.season.*) with a guide, course or theme id of
data/gunsan, its 자리 column says so, no line holds back a picture that has a place, and the event-kind table is the
code's. A '연결' picture whose id the data lacks is an error; one whose page the build does not have, a warning."""
import datetime as dt
import json
import re
import shutil
from pathlib import Path

import pytest

from pipeline import art, city, present
from pipeline import locales as LC
from pipeline.build import ART_SLOT_CSS, VIDEO_TOPIC_ART, VIDEO_TOPICS, build, make_env, site_css, slugify
from pipeline.validate import validate

ROOT = Path(__file__).resolve().parent.parent
SAMPLE = ROOT / "data" / "sample"
DOC = ROOT / "docs" / "handover" / "image_prompts_round2_2026-10-13.md"


# ------------------------------------------------------------------ the owner's list and the code agree
def _doc_rows() -> list[list[str]]:
    rows = []
    for line in DOC.read_text("utf-8").splitlines():
        if line.startswith("| `"):
            rows.append([c.strip() for c in re.split(r"(?<!\\)\|", line.strip())[1:-1]])
    return rows


def _doc_slots() -> dict[str, tuple[str, str]]:
    """{slot: (picture id, 자리 column)} of every picture row of the owner's list."""
    out = {}
    for cells in _doc_rows():
        m = re.match(r"`([a-z0-9.-]+)`", cells[1]) if len(cells) > 2 else None
        if m and art.SLOT_RE.match(m.group(1)):
            out[m.group(1)] = (cells[0].strip("`"), cells[2])
    return out


def test_slot_name_tables_cover_their_data():
    assert list(VIDEO_TOPIC_ART) == list(VIDEO_TOPICS)
    C = city.current()   # the sample city's 권역 (data/sample/site.json city.travel_regions)
    assert set(present.region_art()) == {r.name for r in C.regions} | {C.far_label}
    for slug in present.region_art().values():
        assert art.known_slot(f"area.{slug}")
    for name, words in (("saemangeum-and-bieung", "area"), ("travel-course", "videos.head"), ("13", "events.month"),
                        ("en", "og"), ("course", "home.card"), ("empty", "chat"), ("season.spring", "home")):
        assert not art.known_slot(f"{words}.{name}"), name                      # typos and slots without a place
    assert [art.id_slot(s) for s in ("guide.banner.guide-04", "en.guide.banner.guide-16", "course.banner.c-1",
                                     "theme.head.islands-sea", "home.card.guide", "og.zh-hans", "about.head")] == [
        ("guide.banner", "guide-04"), ("en.guide.banner", "guide-16"), ("course.banner", "c-1"),
        ("theme.head", "islands-sea"), None, None, None]


def _kind_rows() -> list[tuple[str, list[str], list[str]]]:
    """(kind, words, series names) of the list's K table."""
    out = []
    for cells in _doc_rows():
        m = re.fullmatch(r"`([a-z]+)`", cells[0])
        if m and len(cells) == 3:
            words = [] if cells[1].startswith("(") else [w.strip() for w in cells[1].split(",")]
            names = [n.strip() for n, _ in re.findall(r"\s*(.+?)\((\d+)\)(?:,|$)", cells[2])]
            out.append((m.group(1), words, names))
    return out


# ------------------------------------------------------------------ languages: alt prefix, no label, data rules
def test_every_language_has_an_alt_prefix_and_no_label():
    assert art.LANGS == ("ko", *LC.CODES)
    for lang in art.LANGS:
        assert art.ALT_PREFIX[lang].strip(), lang
    assert not hasattr(art, "LABEL") and not any(hasattr(loc, "art_label") for loc in LC.LOCALES.values())
    assert len(art.DROPPED_LABELS) == len(art.LANGS)            # the dropped label of every page language is watched
    assert art.ALT_PREFIX["ko"] == "일러스트: " and art.ALT_PREFIX["en"] == "Illustration: "
    assert art.ALT_PREFIX["ja"] == "イラスト：" and art.ALT_PREFIX["fr"] == "Illustration : "
    assert [art.alt_key(c) for c in ("ko", "en", "ja", "zh-hans", "zh-hant", "ru")] == \
        ["alt", "alt_en", "alt_ja", "alt_zh_hans", "alt_zh_hant", "alt_ru"]


def test_figure_describes_a_picture_in_the_page_language_without_a_label():
    macro = make_env().get_template("_art.html.j2").module.figure
    alts = {lang: f"{art.ALT_PREFIX[lang]}x {lang}" for lang in art.LANGS}
    pic = {"id": "t", "avif": "/assets/art/t-400.avif 400w", "webp": "/assets/art/t-400.webp 400w",
           "src": "/assets/art/t-400.webp", "w": 1024, "h": 1024, "alts": alts}
    for lang in art.LANGS:
        html = str(macro(pic, lang))
        assert f'alt="{alts[lang]}"' in html and "<figcaption" not in html and not art.dropped_labels(html), lang
        tag = "ko" if lang == "ko" else LC.get(lang).html
        page = f'<!doctype html><html lang="{tag}"><body>{html}</body></html>'
        assert art.page_problems(page, [], place=False) == [], lang


def _art_dir(tmp: Path, pictures: dict) -> Path:
    """Tiny renditions and the manifest for {id: (w, h)} (a link preview, og-*: one JPEG)."""
    d = tmp / "art"
    d.mkdir(exist_ok=True)
    manifest = {}
    for art_id, (w, h) in pictures.items():
        if art_id.startswith("og-"):
            name = f"{art_id}-1200.jpg"
            (d / name).write_bytes(b"\xff\xd8test")
            manifest[art_id] = {"w": 1200, "h": 630, "jpg": [[name, 1200, 6]]}
            continue
        blob = bytes.fromhex("524946461e000000574542505650384c110000002f000000000750f3fa77b9ff8188e87f0000")
        entry = {"w": w, "h": h}
        for fmt in ("avif", "webp"):
            (d / f"{art_id}-400.{fmt}").write_bytes(blob)
            entry[fmt] = [[f"{art_id}-400.{fmt}", 400, len(blob)]]
        manifest[art_id] = entry
    (d / "manifest.json").write_text(json.dumps(manifest), "utf-8")
    return d


def test_data_problems_for_languages_slots_and_status(tmp_path):
    images = {
        "ok-ja": {"alt": "일러스트: 가", "alt_en": "Illustration: a", "alt_ja": "イラスト：あ",
                  "slot": "course.banner.c-1", "status": "연결", "langs": ["ko", "en", "ja"]},
        "no-ja-alt": {"alt": "일러스트: 가", "slot": "about.head", "status": "연결", "langs": ["ko", "ja"]},
        "bad-lang": {"alt": "일러스트: 가", "slot": "area.eunpa", "status": "연결", "langs": ["ko", "xx"]},
        "two-langs": {"alt": "일러스트: 가 나", "alt_en": "Illustration: 가 나", "slot": "theme.head.t", "status": "연결",
                      "text": ["가 나"]},
        "en-camp-x": {"alt": "일러스트: A", "alt_en": "Illustration: A", "slot": "en.guide.banner.guide-01",
                      "status": "연결", "langs": ["ko", "en"]},
        "og-ja": {"alt_en": "Illustration: 群山", "slot": "og.ja", "status": "연결", "langs": ["en"], "text": ["群山"]},
        "typo": {"alt": "일러스트: 가", "alt_en": "Illustration: a", "slot": "area.saemangeum-and-bieung", "status": "연결"},
        "later": {"alt": "일러스트: 가", "alt_en": "Illustration: a", "slot": "chat.empty", "status": "개편 뒤 연결"},
        # an id the region's data does not have: a typo, though the slot's form is right (known_slot)
        "course-typo": {"alt": "일러스트: 가", "alt_en": "Illustration: a", "slot": "course.banner.c-9", "status": "연결"},
        "theme-typo": {"alt": "일러스트: 가", "alt_en": "Illustration: a", "slot": "theme.head.tt", "status": "연결"},
        "camp-typo": {"alt": "일러스트: 가", "slot": "guide.banner.guide-61", "status": "연결", "langs": ["ko"]},
        "en-camp-ko-only": {"alt_en": "Illustration: a", "slot": "en.guide.banner.guide-02", "status": "연결",
                            "langs": ["en"]},                     # a guide without an English translation
        "course-later": {"alt": "일러스트: 가", "alt_en": "Illustration: a", "slot": "course.banner.c-8",
                         "status": "개편 뒤 연결"},                # not shown: its id is not checked
    }
    (tmp_path / "art.json").write_text(json.dumps({"images": images}, ensure_ascii=False), "utf-8")
    for name, records in (("guides.json", [{"id": "guide-01"}, {"id": "guide-02"}]), ("courses.json", [{"id": "c-1"}]),
                          ("themes.json", [{"slug": "t"}]), ("en/guides.json", {"guide-01": {"title": "A"}})):
        (tmp_path / name).parent.mkdir(exist_ok=True)
        (tmp_path / name).write_text(json.dumps(records), "utf-8")
    d = _art_dir(tmp_path, {k: (1024, 1024) for k in images})
    problems = art.data_problems(tmp_path, d)
    text = "\n".join(problems)
    assert not any(p.startswith(("art.json ok-ja:", "art.json later:", "art.json course-later:")) for p in problems), text
    assert "art.json no-ja-alt: alt_ja는 'イラスト：'로 시작하는 설명이어야 함" in text
    assert "art.json bad-lang: langs는" in text
    assert "art.json two-langs: 글자가 든 그림은 그 글자의 언어 하나만" in text
    assert "art.json en-camp-x: slot en.guide.banner.guide-01은 en 페이지 전용" in text
    assert "art.json og-ja: slot og.ja은 ja 페이지 전용" in text
    assert "art.json typo: '연결'인데 사이트에 없는 자리: area.saemangeum-and-bieung" in text
    for art_id, slot, where in (("course-typo", "course.banner.c-9", "courses.json에 없는 코스 id: c-9"),
                                ("theme-typo", "theme.head.tt", "themes.json에 없는 테마 slug: tt"),
                                ("camp-typo", "guide.banner.guide-61", "guides.json에 없는 가이드 id: guide-61"),
                                ("en-camp-ko-only", "en.guide.banner.guide-02",
                                 "en/guides.json에 없는 영어 가이드 id: guide-02")):
        assert f"art.json {art_id}: '연결'인데 사이트에 없는 자리: {slot} — {where} (오타 확인" in text, art_id
    assert sum("사이트에 없는 자리" in p for p in problems) == 5        # the four ids and the area typo, nothing else
    (tmp_path / "courses.json").unlink()                               # a region without courses: no course page
    assert any(p.startswith("art.json ok-ja: '연결'인데 사이트에 없는 자리: course.banner.c-1")
               for p in art.data_problems(tmp_path, d))


def test_unshown_names_a_connected_picture_whose_page_is_not_in_the_build(tmp_path):
    """An id the data has, but no page of the build shows the picture (a theme without places …): a warning."""
    images = {"theme-empty": {"alt": "일러스트: 가", "alt_en": "Illustration: a", "slot": "theme.head.t", "status": "연결"},
              "course-shown": {"alt": "일러스트: 가", "alt_en": "Illustration: a", "slot": "course.banner.c-1",
                               "status": "연결"},
              "course-typo": {"alt": "일러스트: 가", "alt_en": "Illustration: a", "slot": "course.banner.c-9",
                              "status": "연결"},              # an error (data_problems), not this warning
              "about": {"alt": "일러스트: 가", "alt_en": "Illustration: a", "slot": "about.head", "status": "연결"},
              "theme-later": {"alt": "일러스트: 가", "alt_en": "Illustration: a", "slot": "theme.head.u",
                              "status": "개편 뒤 연결"}}
    (tmp_path / "art.json").write_text(json.dumps({"images": images}, ensure_ascii=False), "utf-8")
    (tmp_path / "courses.json").write_text(json.dumps([{"id": "c-1"}]), "utf-8")
    (tmp_path / "themes.json").write_text(json.dumps([{"slug": "t"}, {"slug": "u"}]), "utf-8")
    d = _art_dir(tmp_path, {k: (1536, 640) for k in images})
    assert art.unshown(tmp_path, {"course-shown-400.webp"}, d) == [
        "art.json theme-empty: '연결'인데 이번 빌드의 어느 페이지에도 나오지 않음: theme.head.t — 그 페이지가 이번 빌드에 "
        "없음(비공개, 영어 번역 갱신 전, 장소 없는 테마) 또는 langs 확인"]
    assert art.unshown(tmp_path, {"course-shown-400.webp", "theme-empty-400.webp"}, d) == []


def test_page_rules_follow_the_page_language_and_keep_art_out_of_json_ld():
    def fig(alt, label=""):
        cap = f'<figcaption class="art-label">{label}</figcaption>' if label else ""
        return (f'<figure class="art" data-art="t"><picture><img src="/assets/art/t-400.webp" alt="{alt}" width="1" '
                f'height="1"></picture>{cap}</figure>')

    def page(lang, body):
        return f'<!doctype html><html lang="{lang}"><body>{body}</body></html>'
    en, ja = fig("Illustration: a"), fig("イラスト：あ")
    assert art.page_problems(page("ja", ja), [], False) == []
    assert art.page_problems(page("ko", fig("일러스트: 가")), [], False) == []
    assert any("alt가 'イラスト：'" in p for p in art.page_problems(page("ja", en), [], False))       # English on /ja/
    assert any("alt가 '일러스트: '" in p for p in art.page_problems(page("ko", en), [], False))       # English on Korean
    assert art.page_problems(page("zh-Hans", fig("插图：山")), [], False) == []
    # the label each language's pictures carried until 2026-10-13 night is a problem on any page, in any language
    for lang, label in (("ko", "AI 생성 이미지"), ("en", "AI-generated image"), ("ja", "AI生成画像"), ("zh-Hans", "AI生成图像"),
                        ("zh-Hant", "AI生成圖像"), ("de", "KI-generiertes Bild"), ("fr", "Image générée par IA"),
                        ("es", "Imagen generada por IA"), ("ru", "Изображение создано ИИ")):
        alt = art.ALT_PREFIX["zh-hans" if lang == "zh-Hans" else "zh-hant" if lang == "zh-Hant" else lang] + "x"
        problems = art.page_problems(page(lang, fig(alt, label)), [], False)
        assert [p for p in problems if "가 페이지에 있음" in p], (lang, problems)
    for node in ({"@type": "Event", "name": "축제", "image": "/assets/art/evkind-race-400.webp"},
                 {"@type": "TouristTrip", "image": ["/assets/art/course-x-400.webp"]},
                 {"@type": "WebPage", "about": {"@type": "Festival", "image": "/assets/art/x.webp"}}):
        assert any("구조화 데이터" in p for p in art.page_problems(page("ko", ""), [node], False)), node
    assert art.page_problems(page("ko", ""), [{"@type": "WebPage", "image": "/assets/art/og-ko-1200.jpg"}], False) == []


def test_og_fallback_and_for_lang_per_language():
    pic = lambda i, langs: {"id": i, "langs": langs}
    found = {"og.default": pic("og-ko", ["ko"]), "og.default-en": pic("og-en", ["en"]), "og.ja": pic("og-ja", ["ja"]),
             "og.de": pic("og-de", ["ja"]), "about.head": pic("about", ["ko", "en"])}
    assert art.og_fallback(art.for_lang(found, "ja"), "/ja/about/", "ja")["id"] == "og-ja"
    assert art.og_fallback(art.for_lang(found, "ja"), "/ja/places/x/", "ja") is None          # never a place page
    assert art.og_fallback(art.for_lang(found, "de"), "/de/about/", "de") is None             # langs do not name de
    assert art.og_fallback(found, "/de/about/", "de") is None
    assert art.og_fallback(art.for_lang(found, "en"), "/en/", "en")["id"] == "og-en"
    assert art.og_fallback(art.for_lang(found, "ko"), "/about/", "ko")["id"] == "og-ko"
    assert set(art.for_lang(found, "ja")) == {"og.ja", "og.de"} and "about.head" in art.for_lang(found, "en")


# ------------------------------------------------------------------ a small world, built with and without the pictures
TODAY = dt.date.today()
PAST = TODAY - dt.timedelta(days=70)          # an edition finished in another month: a month heading under 지난 행사
SOON = TODAY + dt.timedelta(days=5)           # a coming race without a photo: a news card on the home
PICTURES = {   # id: (slot, w, h, langs, extra fields)
    "theme-test": ("theme.head.alleys-culture", 1536, 640, None, {}),
    "theme-later": ("theme.head.parks-nature", 1536, 640, None, {"status": "개편 뒤 연결"}),   # not shown: status
    "theme-nopage": ("theme.head.islands-sea", 1536, 640, None, {}),   # a theme without places: no page (a warning)
    "vtopic-test": ("videos.head.islands-sea", 1536, 640, None, {}),
    "course-test": ("course.banner.course-sample-1", 1536, 640, ["ko", "en", "ja"], {}),
    "area-test": ("area.old-downtown", 1536, 640, None, {}),
    "month-test": (f"events.month.{PAST:%m}", 1024, 1024, None, {}),
    "evkind-test": ("events.kind.race", 1024, 1024, None, {}),
    "abroad-press-test": ("abroad.group.press", 1024, 1024, None, {}),
    "abroad-videos-test": ("abroad.group.videos", 1024, 1024, None, {}),
    "og-ja": ("og.ja", 1200, 630, ["ja"], {"text": ["群山旅行のすべて"]}),
    "en-camp-test": ("en.guide.banner.guide-sample-1", 1536, 1024, ["en"], {"text": ["A car-free day trip"]}),
    "about-test": ("about.head", 1536, 1024, ["ko", "en", "ja"], {}),
}
REGIONS = (("원도심", "gyeongam-railroad-village"), ("은파", "eunpa-lake-park"))   # 권역 anchors of the test world


def _entry(art_id: str) -> dict:
    slot, _, _, langs, extra = PICTURES[art_id]
    langs = langs or ["ko", "en"]
    words = " ".join(extra.get("text") or [])
    meta = {"file": f"{art_id}.png", "slot": slot, "status": extra.get("status", "연결")}
    for lang in langs:
        meta[art.alt_key(lang)] = f"{art.ALT_PREFIX[lang]}{words or 'test'} {art_id} {lang}"
    if langs != ["ko", "en"]:
        meta["langs"] = langs
    if extra.get("text"):
        meta["text"] = extra["text"]
    return meta


def _write_world(data: Path) -> None:
    """The sample plus what the slots need: two 권역 anchors with coordinates, a finished and a coming edition,
    videos (one in English) and two /abroad/ articles; fake English and Japanese translations."""
    from test_intl_site import NAME, PROSE, QUESTION, WORD, write_translations
    site = json.loads((data / "site.json").read_text("utf-8"))
    site["operator"]["contact"] = "corrections@test.invalid"      # the sample's contact is a Korean placeholder
    arts = {r["name"]: r.get("art", "") for r in site["city"]["travel_regions"]["regions"]}
    site["city"]["travel_regions"]["regions"] = [{"name": n, "anchor": a, "art": arts.get(n, "")} for n, a in REGIONS]
    (data / "site.json").write_text(json.dumps(site, ensure_ascii=False), "utf-8")
    places = json.loads((data / "places.json").read_text("utf-8"))
    for p in places:
        p["geo"] = {"gyeongam-railroad-village": {"lat": 35.9799, "lng": 126.7244},
                    "eunpa-lake-park": {"lat": 35.9520, "lng": 126.6935}}.get(p["slug"], p.get("geo"))
    (data / "places.json").write_text(json.dumps(places, ensure_ascii=False), "utf-8")
    events = json.loads((data / "events.json").read_text("utf-8"))
    events[0].update(start_date=(TODAY + dt.timedelta(days=20)).isoformat(),
                     end_date=(TODAY + dt.timedelta(days=22)).isoformat())
    base = {"status": "published", "place_name": "", "address": "", "source_name": "한국관광공사 TourAPI",
            "source_url": "", "checked_at": TODAY.isoformat()}
    events += [{**base, "id": "ev-past", "name": "군산시간여행축제", "start_date": PAST.isoformat(),
                "end_date": (PAST + dt.timedelta(days=1)).isoformat()},
               {**base, "id": "ev-race", "name": "군산새만금마라톤대회", "start_date": SOON.isoformat(),
                "end_date": SOON.isoformat()}]
    (data / "events.json").write_text(json.dumps(events, ensure_ascii=False), "utf-8")
    video = {"channel": "채널", "channel_kind": "creator", "published_date": "2024-01-02", "place_slugs": [],
             "event_names": [], "checked_at": "2026-10-08", "verified_by": "YouTube oEmbed",
             "thumbnail": {"url": "https://i.ytimg.com/vi/x/mqdefault.jpg", "width": 320, "height": 180}}
    videos = [{**video, "youtube_id": f"vid{n}", "url": f"https://www.youtube.com/watch?v=vid{n}", "title": title,
               "topics": [topic], "lang": lang}
              for n, (title, topic, lang) in enumerate((("섬 영상", "섬·바다", "ko"), ("먹거리 영상", "먹거리", "ko"),
                                                        ("Gunsan food", "먹거리", "en")))]
    (data / "videos.json").write_text(json.dumps(videos, ensure_ascii=False), "utf-8")
    item = {"kind": "article", "status": "published", "checked_at": "2026-10-13", "place_slugs": [], "date": "2023-05-01"}
    abroad = {"items": [{**item, "id": "a-press", "outlet": "Paper", "url": "https://paper.example/a", "title": "Gunsan",
                         "lang": "en", "note": "군산 옛 도심을 다룬 기사입니다.", "source_type": "press"},
                        {**item, "id": "a-travel", "outlet": "Guide", "url": "https://guide.example/b", "title": "Gunsan",
                         "lang": "en", "note": "군산 섬 여행을 다룬 글입니다.", "source_type": "travel"}]}
    (data / "abroad.json").write_text(json.dumps(abroad, ensure_ascii=False), "utf-8")
    pids = (places[0]["id"],)                  # one place, as the intl tests' sample build (its fake text validates)
    with pytest.MonkeyPatch.context() as mp:   # English the way the other versions are faked (the sample has none)
        mp.setitem(WORD, "en", "Info")
        mp.setitem(NAME, "en", "Spot")
        mp.setitem(PROSE, "en", "This is place number {n}. There is a parking lot and the hall is open to all.")
        mp.setitem(QUESTION, "en", "Is this question {n}?")
        for code in ("en", "ja"):
            write_translations(data, [code], stale=None, places=pids, guide="guide-sample-1",
                               course="course-sample-1", series=None)


def _tree(out: Path) -> dict[str, bytes]:
    return {str(f.relative_to(out)).replace("\\", "/"): f.read_bytes() for f in sorted(out.rglob("*")) if f.is_file()}


@pytest.fixture(scope="module")
def world(tmp_path_factory):
    tmp = tmp_path_factory.mktemp("slots")
    data = tmp / "data"
    shutil.copytree(SAMPLE, data)
    _write_world(data)
    art_dir = _art_dir(tmp, {k: (w, h) for k, (_, w, h, _, _) in PICTURES.items()})
    (data / "art.json").write_text(json.dumps({"images": {k: _entry(k) for k in PICTURES}}, ensure_ascii=False), "utf-8")
    with pytest.MonkeyPatch.context() as mp:
        mp.setattr(art, "ART_DIR", art_dir)
        build(data, tmp / "with", "sample")
        errors, warnings, _ = validate(data, tmp / "with", "sample")
        problems = art.data_problems(data)
        (data / "art.json").unlink()
        build(data, tmp / "without", "sample")
    return {"data": data, "with": tmp / "with", "without": tmp / "without", "errors": errors, "warnings": warnings,
            "problems": problems, "a": _tree(tmp / "with"), "b": _tree(tmp / "without")}


def _html(world, rel: str) -> str:
    return world["a"][rel].decode("utf-8")


def _figure(html: str, art_id: str) -> str:
    return html.split(f'data-art="{art_id}"', 1)[1].split("</figure>", 1)[0]


def _pages_with(world, art_id: str) -> set[str]:
    return {rel for rel, b in world["a"].items() if rel.endswith(".html") and f'data-art="{art_id}"'.encode() in b}


def _slug_of(world, folder: str, text: str) -> str:
    """The leaf page under folder (folder/<slug>/index.html) that names `text`."""
    for rel in world["a"]:
        if rel.startswith(folder) and rel.count("/") == folder.count("/") + 1 and rel.endswith("/index.html") \
                and text in _html(world, rel):
            return rel
    raise AssertionError((folder, text))


def test_world_is_valid_and_its_art_json_clean(world):
    assert world["problems"] == []
    assert world["errors"] == [], world["errors"][:10]
    assert [w for w in world["warnings"] if w.startswith("[art.json]")] == [
        "[art.json] art.json theme-nopage: '연결'인데 이번 빌드의 어느 페이지에도 나오지 않음: theme.head.islands-sea — 그 "
        "페이지가 이번 빌드에 없음(비공개, 영어 번역 갱신 전, 장소 없는 테마) 또는 langs 확인"]


def test_pictures_change_exactly_their_pages(world):
    """With the pictures: their pages, the Japanese pages' link preview, the renditions and the slot rules of the
    stylesheet differ from a build without art — nothing else (sitemap, llms, every other page the same bytes)."""
    a, b = world["a"], world["b"]
    changed = {rel for rel in set(a) | set(b) if a.get(rel) != b.get(rel)}
    topic = f"videos/{slugify('섬 바다')}/index.html"
    course = _slug_of(world, "courses/", "[샘플] 당일 코스 A")
    pages = {"themes/alleys-culture/index.html", topic, course, "en/courses/spot-1/index.html",
             "ja/courses/spot-1/index.html", "map/index.html", "events/index.html", "index.html", "abroad/index.html",
             "about/index.html", "en/about/index.html", "ja/about/index.html", "en/guides/spot/index.html"}
    ja_previews = {rel for rel in b if rel.startswith("ja/") and rel.endswith(".html")
                   and not re.match(r"ja/places/[^/]+/index\.html$", rel) and b'property="og:image"' not in b[rel]}
    renditions = {rel for rel in a if rel.startswith("assets/art/")}
    assert changed == pages | ja_previews | renditions | {"assets/style.css"}, sorted(changed ^ (pages | ja_previews))
    assert not any(rel.startswith("assets/art/") for rel in b)
    used = {f"assets/art/{n}" for n in art.used_files(world["with"])}
    assert renditions == used and not any("theme-later" in rel or "theme-nopage" in rel for rel in renditions)


def test_a_picture_shows_only_where_its_slot_is(world):
    where = {art_id: _pages_with(world, art_id) for art_id in PICTURES}
    course = _slug_of(world, "courses/", "[샘플] 당일 코스 A")
    assert where == {
        "theme-test": {"themes/alleys-culture/index.html"},
        "theme-later": set(),                                      # status '개편 뒤 연결': not shown though the slot exists
        "theme-nopage": set(),                                     # the sample's islands-sea theme has no place
        "vtopic-test": {f"videos/{slugify('섬 바다')}/index.html"},
        "course-test": {course, "en/courses/spot-1/index.html", "ja/courses/spot-1/index.html"},
        "area-test": {"map/index.html"},
        "month-test": {"events/index.html"},
        "evkind-test": {"index.html"},
        "abroad-press-test": {"abroad/index.html"},
        "abroad-videos-test": {"abroad/index.html"},
        "og-ja": set(),                                           # a link preview: no figure
        "en-camp-test": {"en/guides/spot/index.html"},
        "about-test": {"about/index.html", "en/about/index.html", "ja/about/index.html"},
    }


def test_never_on_a_place_page_in_a_place_card_or_in_json_ld(world):
    for rel, raw in world["a"].items():
        if not rel.endswith(".html"):
            continue
        html = raw.decode("utf-8")
        if re.match(r"(?:[a-z]{2}(?:-[a-z]+)?/)?places/[^/]+/index\.html$", rel):
            assert "/assets/art/" not in html, rel                  # neither a figure nor an og:image
        for block in re.findall(r'<script type="application/ld\+json">(.*?)</script>', html, re.S):
            assert "/assets/art/" not in block, rel


def test_header_bands_theme_topic_course(world):
    """H·M·I: the band above the H1, decorative, in the first screen (not lazy, no fetchpriority, a 400w file first);
    the course band in Korean, English and Japanese with each language's alt (no label), never in a stop card."""
    course = _slug_of(world, "courses/", "[샘플] 당일 코스 A")
    for rel, art_id, lang in (("themes/alleys-culture/index.html", "theme-test", "ko"),
                              (f"videos/{slugify('섬 바다')}/index.html", "vtopic-test", "ko"),
                              (course, "course-test", "ko"), ("en/courses/spot-1/index.html", "course-test", "en"),
                              ("ja/courses/spot-1/index.html", "course-test", "ja")):
        html = _html(world, rel)
        band = _figure(html, art_id)
        assert html.count('class="wrap art-band-wrap"') == 1, rel
        assert band.startswith(' aria-hidden="true">') and "loading=" not in band and "fetchpriority" not in band, rel
        assert f"{art_id}-400.avif 400w" in band and f'alt="{art.ALT_PREFIX[lang]}test {art_id} {lang}"' in band, rel
        assert "<figcaption" not in band and not art.dropped_labels(html), rel
        assert html.index(f'data-art="{art_id}"') < html.index("<h1"), rel
    for rel in (course, "en/courses/spot-1/index.html"):
        html = _html(world, rel)
        assert "data-art" not in html[html.index('id="stops"'):], rel           # the stop cards stay photo or icon
    # the other theme and the index keep what they had: no band (no list.head picture in this art.json)
    assert "data-art" not in _html(world, "themes/parks-nature/index.html")
    assert "data-art" not in _html(world, "videos/index.html")


def test_map_area_strip_heads_its_region(world):
    html = _html(world, "map/index.html")
    start = html.index('id="r-원도심"')
    strip = _figure(html, "area-test")
    assert start < html.index('data-art="area-test"') < html.index('class="region-head"', start)
    assert 'class="art art-band art-strip"' in html and 'loading="lazy"' in strip and 'aria-hidden="true"' in strip
    assert html.count("data-art=") == 1                                       # 은파 has no picture: nothing there


def test_month_picture_beside_its_past_month_heading(world):
    html = _html(world, "events/index.html")
    row = html.split('<div class="art-hd">', 1)[1].split("</div>", 1)[0]      # the picture, then the month heading
    assert 'data-art="month-test"' in row and f'id="m-{PAST:%Y-%m}"' in row
    assert f">{PAST.year}년 {PAST.month}월</h3>" in row
    assert 'loading="lazy"' in row and 'aria-hidden="true"' in row and "<figcaption" not in row
    assert html.index('id="h-past"') < html.index('data-art="month-test"')    # the finished editions' months only
    assert html.count('class="art-hd"') == 1                                  # other months: no picture given


def test_event_kind_picture_on_a_news_card_without_photo(world):
    html = _html(world, "index.html")
    card = next(c for c in html.split('<article class="nc nc-')[1:] if "군산새만금마라톤대회" in c)
    assert 'data-art="evkind-test"' in card and "<figcaption" not in card and 'data-pic=' not in card
    assert 'alt="일러스트: test evkind-test ko"' in card
    if 'aria-label="1 / ' in card:     # the first slide (review 2026-10-14): the home's LCP — eager, high, preloaded
        assert 'fetchpriority="high"' in card and 'loading="lazy"' not in card
        assert 'rel="preload" as="image" type="image/avif" imagesrcset="/assets/art/' in html.split("</head>")[0]
    else:
        assert 'loading="lazy"' in card
    other = next(c for c in html.split('<article class="nc nc-')[1:] if "[샘플] 군산 행사 A" in c)
    assert "data-art" not in other and 'data-pic="icon-events"' in other       # kind 'other': its 3D picture slot
    race = _slug_of(world, "events/", "군산새만금마라톤대회")
    assert "/assets/art/" not in _html(world, race)                           # the event page and its Event JSON-LD


def test_abroad_group_pictures(world):
    html = _html(world, "abroad/index.html")
    rows = html.split('<div class="art-hd">')[1:]
    assert len(rows) == 2
    assert 'data-art="abroad-press-test"' in rows[0] and 'id="ab-press"' in rows[0]
    assert 'data-art="abroad-videos-test"' in rows[1] and 'id="ab-video-h"' in rows[1]
    assert '<h3 class="ab-sub" id="ab-travel">' in html and html.count("data-art=") == 2   # travel: no picture


def test_link_preview_in_each_language(world):
    ja = _html(world, "ja/about/index.html")
    assert '<meta property="og:image" content="https://example.com/assets/art/og-ja-1200.jpg">' in ja
    assert '<meta property="og:image:alt" content="イラスト：群山旅行のすべて og-ja ja">' in ja
    for rel, raw in world["a"].items():
        if rel.endswith(".html") and b"og-ja-1200.jpg" in raw:
            assert rel.startswith("ja/") and not re.match(r"ja/places/[^/]+/index\.html$", rel), rel   # not a place
    assert b"og-ja" not in world["a"]["en/about/index.html"] and b"og-ja" not in world["a"]["about/index.html"]


def test_english_campaign_banner_only_on_the_english_guide(world):
    en = _html(world, "en/guides/spot/index.html")
    banner = _figure(en, "en-camp-test")
    assert '<header class="pg-hero gd-head has-camp">' in en and 'class="art art-camp"' in en
    assert 'alt="Illustration: A car-free day trip en-camp-test en"' in banner
    assert "<figcaption" not in banner and "loading=" not in banner and "aria-hidden" not in banner
    assert "data-art" not in _html(world, "ja/guides/spot/index.html")       # English words: never on /ja/
    ko = _slug_of(world, "guides/", "차 없이 군산 당일여행")
    assert "data-art" not in _html(world, ko)


def test_about_head_picture_in_each_language(world):
    for rel, lang in (("about/index.html", "ko"), ("en/about/index.html", "en"), ("ja/about/index.html", "ja")):
        html = _html(world, rel)
        fig = _figure(html, "about-test")
        assert " has-art-hero" in html and 'class="art art-hero"' in html, rel
        assert f'alt="{art.ALT_PREFIX[lang]}test about-test {lang}"' in fig and "<figcaption" not in fig
        assert "loading=" not in fig and "fetchpriority" not in fig and "aria-hidden" not in fig, rel
        h1 = html.index("<h1")
        assert h1 < html.index('data-art="about-test"') < html.index("</header>", h1), rel   # in the page head


def test_slot_css_only_when_a_page_shows_such_a_picture(world):
    css_a, css_b = ((world["with"] / "assets" / "style.css").read_text("utf-8"),
                    (world["without"] / "assets" / "style.css").read_text("utf-8"))
    assert css_b == site_css() and css_a == site_css(True)
    assert ".art-hd{" not in css_b and ".art-hd{" in css_a and ".has-art-hero>.wrap{" in css_a
    assert ART_SLOT_CSS.search((ROOT / "templates" / "assets" / "css" / "49-art.css").read_text("utf-8"))
