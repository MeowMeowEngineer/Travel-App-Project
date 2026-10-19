"""AI art (owner decisions 2026-10-13, CLAUDE.md 4): data/gunsan/art.json, the renditions tools/art_media.py writes,
the one macro that shows a picture (templates/_art.html.j2), the build publishing only what a page uses, and the
validate rules — alt '일러스트: …' with width and height, never on a place page, inside a place card or in a place's
structured data, and no 'AI 생성 이미지' label on any page (owner 2026-10-13 night: '다 빼'; /about/ says once that the
illustrations are drawn with generative AI). The home's news cards use the pictures; the season hero is no longer a
slot (the Korean home opens on an official photo). A slot whose files are missing renders exactly as the site does
without art."""
import io
import json
import shutil
from pathlib import Path

import pytest

from pipeline import art
from pipeline.build import build, make_env
from pipeline.validate import validate

ROOT = Path(__file__).resolve().parent.parent
SAMPLE = ROOT / "data" / "sample"
# Ported 2026-10-19 from the Gunsan site: its pictures (data/gunsan/art.json, templates/assets/art/) depict Gunsan and were
# not copied, so the tests below that used them as a fixture build a small test-owned set instead (art_set); the tests
# about the Gunsan pictures themselves stayed behind (tests/excluded_gunsan_tests.txt).


def page(body: str = "", head: str = "", jsonld: dict | None = None, lang: str = "ko") -> str:
    ld = f'<script type="application/ld+json">{json.dumps(jsonld)}</script>' if jsonld else ""
    return f"<!doctype html><html lang=\"{lang}\"><head>{head}{ld}</head><body>{body}</body></html>"


def fig(alt="일러스트: 바다", size=' width="640" height="427"', name="hero-autumn-640", caption=""):
    """A picture as templates/_art.html.j2 draws it: no caption (caption: a label as the pages carried it before)."""
    cap = f'<figcaption class="art-label">{caption}</figcaption>' if caption else ""
    return (f'<figure class="art" data-art="hero-autumn"><picture><source type="image/avif" '
            f'srcset="/assets/art/{name}.avif 640w"><img src="/assets/art/{name}.webp" alt="{alt}"{size}></picture>'
            f'{cap}</figure>')


def art_set(tmp_path: Path, rows, files: bool = True) -> tuple[dict, Path]:
    """A test-owned art set: rows of (art_id, meta, (w, h), fmt) — fmt 'img' gives one 400px AVIF and WebP, 'jpg' one
    1200px JPEG (a link preview). Writes the renditions (files=True) and manifest.json into tmp_path/'art' and returns
    ({art_id: meta}, art_dir) for an art.json."""
    art_dir = tmp_path / "art"
    art_dir.mkdir(parents=True, exist_ok=True)
    blob = tiny_picture()
    images, manifest = {}, {}
    for art_id, meta, (w, h), fmt in rows:
        names = {"jpg": f"{art_id}-1200.jpg"} if fmt == "jpg" else {f: f"{art_id}-400.{f}" for f in ("avif", "webp")}
        width = 1200 if fmt == "jpg" else 400
        if files:
            for name in names.values():
                (art_dir / name).write_bytes(blob)
        manifest[art_id] = {"w": w, "h": h, **{f: [[name, width, len(blob)]] for f, name in names.items()}}
        images[art_id] = meta
    (art_dir / "manifest.json").write_text(json.dumps(manifest), "utf-8")
    return images, art_dir


def card_event(art_id: str = "card-test-event") -> tuple:
    return (art_id, {"file": f"{art_id}.png", "alt": "일러스트: 시험 그림 행사 카드", "alt_en": "Illustration: a test event card",
                     "slot": "home.card.event", "status": "연결"}, (1024, 1024), "img")


# ------------------------------------------------------------------ the repository's art: data, renditions, budget
# the renditions the owner's pictures need, written out here (not read from tools/art_media.py, so a wrong change to
# its tables fails a test even after the renditions are made again): the 2.4:1 bands are cut 1536:640 from the
# centre; a picture a phone shows at its width (the bands, the campaign cards, the about head) gets a small file first
BANDS = ("head-", "theme-", "vtopic-", "course-", "area-")
PHONE_WIDTH = (*BANDS, "camp-", "en-camp-", "about-")


def test_the_season_hero_is_not_a_slot_any_more(tmp_path):
    """Owner 2026-10-13 night: the Korean home opens on the official photo, so home.hero.<season> is no slot of the
    site, and a season picture put back to '연결' is an error, not a picture shown nowhere. (The Gunsan repository's own
    four season pictures and their '개편 뒤 연결' notes stayed there — tests/excluded_gunsan_tests.txt.)"""
    for season in ("spring", "summer", "autumn", "winter"):
        assert not art.known_slot(f"home.hero.{season}"), season
    assert art.known_slot("home.card.event") and art.known_slot("list.head.places")
    cfg = {"images": {"hero-autumn": {"file": "hero-autumn.png", "alt": "일러스트: 시험 가을 언덕길",
                                      "alt_en": "Illustration: a test autumn path", "slot": "home.hero.autumn",
                                      "status": "연결"}}}
    (tmp_path / "art.json").write_text(json.dumps(cfg, ensure_ascii=False), "utf-8")
    assert any("'연결'인데 사이트에 없는 자리: home.hero.autumn" in p for p in art.data_problems(tmp_path))


def test_a_picture_without_its_renditions_is_an_empty_slot(tmp_path):
    data = tmp_path / "data"
    data.mkdir()
    images, art_dir = art_set(tmp_path, [card_event()])           # listed and connected, its renditions present …
    (data / "art.json").write_text(json.dumps({"images": images}, ensure_ascii=False), "utf-8")
    assert set(art.slots(data, art_dir)) == {"home.card.event"}
    assert art.slots(data, tmp_path / "no-art") == {}          # … files missing: the slot renders as without art
    assert art.slots(SAMPLE) == {}                             # a region without art.json has no art
    assert any("파생본 없음" in p for p in art.data_problems(data, tmp_path / "no-art"))


def test_data_problems_catch_bad_alt_slot_status_and_held(tmp_path):
    bad = {"images": {"hero-autumn": {"alt": "가을 풍경", "alt_en": "autumn", "slot": "Home Hero", "status": "보류"}},
           "held": {"hero-autumn": "다시 만들기"}}
    (tmp_path / "art.json").write_text(json.dumps(bad, ensure_ascii=False), "utf-8")
    problems = "\n".join(art.data_problems(tmp_path))
    for needle in ("alt는 '일러스트: '", "alt_en는 'Illustration: '", "slot 형식", "status는", "held(보류)에도"):
        assert needle in problems, needle


# ------------------------------------------------------------------ the macro: alt, size, loading — and no label
def test_figure_macro_draws_the_picture_without_a_label_and_passes_the_page_rules(tmp_path):
    data = tmp_path / "data"
    data.mkdir()
    images, art_dir = art_set(tmp_path, [card_event()])
    (data / "art.json").write_text(json.dumps({"images": images}, ensure_ascii=False), "utf-8")
    pic = art.slots(data, art_dir)["home.card.event"]
    macro = make_env().get_template("_art.html.j2").module.figure
    ko = str(macro(pic, sizes="(min-width: 1024px) 50vw, 100vw"))
    assert f'data-art="{pic["id"]}"' in ko and f'alt="{pic["alt"]}"' in ko and pic["alt"].startswith("일러스트: ")
    assert "<figcaption" not in ko and not art.dropped_labels(ko)    # owner 2026-10-13 night: no label
    assert f'width="{pic["w"]}" height="{pic["h"]}"' in ko and 'loading="lazy"' in ko and "fetchpriority" not in ko
    assert 'type="image/avif"' in ko and 'type="image/webp"' in ko
    en = str(macro(pic, lang="en", eager=True))
    assert f'alt="{pic["alt_en"]}"' in en and pic["alt_en"].startswith("Illustration: ")
    assert "<figcaption" not in en and not art.dropped_labels(en)
    assert "fetchpriority" not in en and "loading=" not in en      # first screen: not lazy, not ahead of fonts
    assert 'fetchpriority="high"' in str(macro(pic, high=True))
    assert art.page_problems(page(ko), [], place=False) == []
    assert art.page_problems(page(en, lang="en"), [], place=False) == []


# ------------------------------------------------------------------ page rules (validate.py uses page_problems)
def test_page_rules_accept_a_figure_without_label_and_og_image_off_place_pages():
    head = '<meta property="og:image" content="https://x.test/assets/art/og-ko-1200.jpg">' \
           '<link rel="preload" as="image" imagesrcset="/assets/art/hero-autumn-640.avif 640w">'
    assert art.page_problems(page(fig(), head), [{"@type": "WebPage", "image": "/assets/art/og.jpg"}], False) == []
    assert art.page_problems(page("<p>no art</p>"), [], True) == []


@pytest.mark.parametrize("body, needle", [
    ('<img src="/assets/art/hero-autumn-640.webp" alt="일러스트: 바다" width="1" height="1">', "figure[data-art]"),
    ('<div style="background:url(/assets/art/hero-autumn-640.webp)"></div>', "figure[data-art]"),
    (fig(caption="AI 생성 이미지"), "'AI 생성 이미지'가 페이지에 있음"),
    (fig(alt="바다 사진"), "alt가 '일러스트: '"),
    (fig(alt="일러스트: "), "alt가 '일러스트: '"),
    (fig(size=""), "width·height"),
    (f'<a href="/places/seonyudo/">{fig()}</a>', "장소 카드"),
    (f'<a href="/en/places/seonyudo/">{fig()}</a>', "장소 카드"),
    ('<figure data-art="x"></figure>', "<img>가 없음"),
])
def test_page_rules_reject_misplaced_or_badly_described_art(body, needle):
    problems = art.page_problems(page(body), [], place=False)
    assert any(needle in p for p in problems), problems


@pytest.mark.parametrize("body, lang", [
    (fig(caption="AI 생성 이미지"), "ko"),                               # the caption the pictures carried
    ("<p>사진 아래 AI 생성 이미지라고 적음</p>", "ko"),                      # any text, art or not
    ("<p>AI생성  이미지</p>", "ko"),                                      # any spacing
    ('<img src="/x.webp" alt="AI 생성 이미지" width="1" height="1">', "ko"),   # an attribute too
    ("<p>AI <b>생성</b> 이미지</p>", "ko"),                                # split by tags
    ("<p>An AI-Generated Image</p>", "en"), ("<p>AI生成画像</p>", "ja"), ("<p>KI-generiertes Bild</p>", "de"),
    ("<p>Image générée par IA</p>", "fr"), ("<p>Изображение создано ИИ</p>", "ru"),
])
def test_no_page_may_carry_the_dropped_label(body, lang):
    """Owner 2026-10-13 night ('AI 생성 이미지 표시는 다 빼'): the label may not come back on any page — with or
    without a picture on it — in any page language."""
    problems = art.page_problems(page(body, lang=lang), [], place=False)
    assert any("가 페이지에 있음" in p for p in problems), problems


def test_the_label_check_leaves_plain_words_alone():
    for text in ("이 사이트의 일러스트는 생성형 AI로 그렸습니다", "AI가 이 사이트 정보로 답합니다",
                 "The illustrations on this site were drawn with generative AI", "생성 이미지 파일"):
        assert art.page_problems(page(f"<p>{text}</p>"), [], place=False) == [], text


def test_page_rules_keep_art_off_place_pages_and_out_of_place_data():
    assert any("장소 페이지에 AI 그림" in p for p in art.page_problems(page(fig()), [], place=True))
    head = '<meta property="og:image" content="https://x.test/assets/art/og-ko-1200.jpg">'
    assert any("og:image" in p for p in art.page_problems(page("", head), [], place=True))
    place = {"@type": "TouristAttraction", "@id": "https://x.test/places/a/#place", "image": "/assets/art/a.webp"}
    assert any("장소 페이지 구조화 데이터" in p for p in art.page_problems(page(), [place], place=True))
    photo = {"@type": "WebPage", "primaryImageOfPage": {"@type": "ImageObject", "contentUrl": "/assets/art/a.webp"}}
    assert any("ImageObject" in p for p in art.page_problems(page(), [photo], place=False))


def test_page_rules_report_a_rendition_the_build_did_not_publish(tmp_path):
    assert any("빌드에 없음" in p for p in art.page_problems(page(fig()), [], False, tmp_path))
    (tmp_path / "assets" / "art").mkdir(parents=True)
    for ext in ("avif", "webp"):
        (tmp_path / "assets" / "art" / f"hero-autumn-640.{ext}").write_bytes(b"x")
    assert art.page_problems(page(fig()), [], False, tmp_path) == []


# ------------------------------------------------------------------ build: only used renditions; same site without art
def test_build_publishes_only_the_renditions_pages_use(tmp_path, monkeypatch):
    art_dir = tmp_path / "art"                                   # renditions on disk: the used one and an unused one
    art_dir.mkdir()
    for name in ("hero-autumn-640.avif", "hero-autumn-640.webp", "card-unused-400.avif", "card-unused-400.webp"):
        (art_dir / name).write_bytes(b"x")
    monkeypatch.setattr(art, "ART_DIR", art_dir)
    out = tmp_path / "out"
    out.mkdir()
    (out / "a.html").write_text(page(fig()), "utf-8")
    assert art.copy_used(out) == ["hero-autumn-640.avif", "hero-autumn-640.webp"]
    assert sorted(f.name for f in (out / "assets" / "art").iterdir()) == ["hero-autumn-640.avif",
                                                                           "hero-autumn-640.webp"]


def test_without_art_files_the_site_is_the_same(tmp_path, monkeypatch):
    """A slot whose files are missing renders exactly as the site did before AI art: the same bytes as a build
    without art.json — no band, no banner, no og:image fallback, nothing under /assets/art/."""
    def tree(out):
        return {str(f.relative_to(out)): f.read_bytes() for f in sorted(out.rglob("*")) if f.is_file()}
    data = tmp_path / "data"
    shutil.copytree(SAMPLE, data)
    rows = [card_event(), ("card-test-guide", {"file": "x.png", "alt": "일러스트: 시험 가이드 카드", "alt_en": "Illustration: a test guide card",
                                              "slot": "home.card.guide", "status": "연결"}, (1024, 1024), "img"),
            ("head-places", {"file": "x.png", "alt": "일러스트: 시험 띠 그림", "alt_en": "Illustration: a test band",
                             "slot": "list.head.places", "status": "연결"}, (1536, 640), "img"),
            ("og-ko", {"file": "x.png", "alt": "일러스트: 시험 미리보기", "slot": "og.default", "status": "연결", "langs": ["ko"]},
             (1200, 630), "jpg"),
            ("art-404", {"file": "x.png", "alt": "일러스트: 시험 404", "alt_en": "Illustration: a test 404", "slot": "page.404",
                         "status": "연결"}, (1024, 1024), "img")]
    images, _ = art_set(tmp_path / "listed", rows, files=False)
    (data / "art.json").write_text(json.dumps({"images": images}, ensure_ascii=False), "utf-8")   # every picture listed …
    monkeypatch.setattr(art, "ART_DIR", tmp_path / "no-art")   # … but no rendition on disk
    build(data, tmp_path / "missing", "sample")
    (data / "art.json").unlink()
    build(data, tmp_path / "none", "sample")
    assert tree(tmp_path / "missing") == tree(tmp_path / "none")
    assert not (tmp_path / "missing" / "assets" / "art").exists()


def test_validate_rejects_art_misused_in_a_built_site(tmp_path):
    out = tmp_path / "out"
    build(SAMPLE, out, "sample")
    home = out / "index.html"
    home.write_text(home.read_text("utf-8").replace("</main>", f'<img src="/assets/art/x-640.webp" alt="x"></main>', 1),
                    "utf-8")
    place = next((out / "places").glob("*/index.html"))
    place.write_text(place.read_text("utf-8").replace("</main>", fig() + "</main>", 1), "utf-8")
    (out / "assets" / "style.css").write_text(".h{background:url(/assets/art/x.webp)}", "utf-8")
    errors = "\n".join(validate(SAMPLE, out, "sample")[0])
    assert "figure[data-art]" in errors and "장소 페이지에 AI 그림" in errors and "CSS 배경" in errors


# ------------------------------------------------------------------ tools/art_media.py (needs Pillow with AVIF)
def test_art_media_widths_never_upscale():
    from tools import art_media
    assert art_media.widths_for(1536, 1024) == [640, 1280, 1536]
    assert art_media.widths_for(2400, 1600) == [640, 1280, 1920]
    assert art_media.widths_for(1024, 1024) == [400, 800]
    assert art_media.widths_for(96, 64) == [96]
    assert art_media.widths_for(1536, 640, "head-places") == [400, 800, 1280, 1536]   # phones get a small file
    assert art_media.widths_for(1536, 1024, "camp-night") == [400, 800, 1280, 1536]
    for prefix in PHONE_WIDTH:                                       # every picture a phone shows at its width
        assert art_media.widths_for(1536, 1024, prefix + "x") == [400, 800, 1280, 1536], prefix
    for art_id in ("hero-autumn", "card-guide", "evkind-race", "month-01", "abroad-press", "art-404"):
        assert art_media.widths_for(1536, 1024, art_id) == [640, 1280, 1536], art_id
        assert art_media.widths_for(1024, 1024, art_id) == [400, 800], art_id


def test_art_media_tables_are_the_owners():
    """tools/art_media.py's crop and width tables, as the second picture list needs them (BANDS, PHONE_WIDTH above;
    the widths art.json _notes names)."""
    from tools import art_media
    assert art_media.CROPS == {p: (1536, 640) for p in BANDS}
    assert art_media.SMALL_FIRST == (PHONE_WIDTH, (400, 800, 1280, 1920))
    assert art_media.WIDTHS == {"landscape": (640, 1280, 1920), "square": (400, 800)}


def test_art_media_is_deterministic_keeps_committed_files_and_drops_stale(tmp_path):
    pytest.importorskip("PIL")
    from PIL import Image, features
    if not features.check("avif"):
        pytest.skip("Pillow without AVIF")
    from tools import art_media
    data, src = tmp_path / "data", tmp_path / "src"
    data.mkdir()
    src.mkdir()
    entry = {"file": "hero-test.png", "alt": "일러스트: 시험", "alt_en": "Illustration: test",
             "slot": "home.hero.autumn", "status": "개편 뒤 연결"}
    (data / "art.json").write_text(json.dumps({"images": {"hero-test": entry}}, ensure_ascii=False), "utf-8")
    im = Image.new("RGBA", (96, 64), (240, 200, 160, 255))
    im.putpixel((0, 0), (0, 0, 0, 230))                         # a semi-transparent edge pixel, as ChatGPT leaves
    im.save(src / "hero-test.png")
    one, two = tmp_path / "one", tmp_path / "two"
    assert art_media.main(["--data", str(data), "--src", str(src), "--out", str(one)]) == 0
    assert art_media.main(["--data", str(data), "--src", str(src), "--out", str(two), "--force"]) == 0
    names = sorted(f.name for f in one.iterdir())
    assert names == ["hero-test-96.avif", "hero-test-96.webp", "manifest.json"]
    assert all((one / n).read_bytes() == (two / n).read_bytes() for n in names)   # same original, same bytes
    assert art.data_problems(data, one) == []
    with Image.open(one / "hero-test-96.webp") as w:
        assert w.mode == "RGB"                                  # flattened, no alpha
    (src / "hero-test.png").unlink()                            # another computer: originals are not in git
    assert art_media.main(["--data", str(data), "--src", str(src), "--out", str(one)]) == 0
    assert sorted(f.name for f in one.iterdir()) == names
    (data / "art.json").write_text(json.dumps({"images": {}, "held": {"hero-test": "다시"}}), "utf-8")
    assert art_media.main(["--data", str(data), "--src", str(src), "--out", str(one)]) == 0
    assert sorted(f.name for f in one.iterdir()) == ["manifest.json"]
    assert json.loads((one / "manifest.json").read_text("utf-8")) == {}


# ------------------------------------------------------------------ the slots that are connected (C·D·E·F)
def test_og_fallback_never_reaches_a_place_page():
    found = {"og.default": {"id": "og-ko"}, "og.default-en": {"id": "og-en"}, "og.abroad": {"id": "og-abroad"}}
    assert art.og_fallback(found, "/places/seonyudo/") is None
    assert art.og_fallback(found, "/en/places/seonyudo/", "en") is None
    assert art.og_fallback(found, "/404.html") is None
    assert art.og_fallback(found, "/abroad/")["id"] == "og-abroad"
    assert art.og_fallback(found, "/about/")["id"] == "og-ko"
    assert art.og_fallback(found, "/places/")["id"] == "og-ko"           # the list, not a place
    assert art.og_fallback(found, "/en/guides/", "en")["id"] == "og-en"
    assert art.og_fallback({}, "/about/") is None                        # no picture: no og:image, as before


def test_connected_art_is_published_without_a_label_and_valid(tmp_path, monkeypatch):
    data = tmp_path / "data"
    shutil.copytree(SAMPLE, data)
    # a test-owned set, one picture per kind of slot (the Gunsan pictures were not copied): the band above the places
    # list, the link preview, 404 and the empty search, a guide's campaign card and a course's band — the guide and
    # the course take the sample's own ids (art.ID_SLOTS)
    ids = art.data_ids(data)
    guide_id, course_id = sorted(ids["guide.banner"])[0], sorted(ids["course.banner"])[0]
    camp = "camp-test"
    rows = [("head-places", {"file": "x.png", "alt": "일러스트: 시험 띠 그림", "alt_en": "Illustration: a test band",
                             "slot": "list.head.places", "status": "연결"}, (1536, 640), "img"),
            ("og-ko", {"file": "x.png", "alt": "일러스트: 시험 사이트 — 언제 열고 얼마인지", "slot": "og.default", "status": "연결",
                       "langs": ["ko"], "text": ["시험 사이트", "언제 열고 얼마인지"]}, (1200, 630), "jpg"),
            # as in the Gunsan set: the 404 and empty-search pictures wait for their slots ('개편 뒤 연결')
            ("art-404", {"file": "x.png", "alt": "일러스트: 빈 표지판", "alt_en": "Illustration: a blank signpost",
                         "slot": "page.404", "status": "개편 뒤 연결"}, (1024, 1024), "img"),
            ("art-empty", {"file": "x.png", "alt": "일러스트: 빈 바구니", "alt_en": "Illustration: an empty basket",
                           "slot": "search.empty", "status": "개편 뒤 연결"}, (1024, 1024), "img"),
            (camp, {"file": "x.png", "alt": "일러스트: 시험 캠페인 문구 — 버스와 바다", "slot": f"guide.banner.{guide_id}",
                    "status": "연결", "langs": ["ko"], "text": ["시험 캠페인 문구"]}, (1536, 1024), "img"),
            ("course-test", {"file": "x.png", "alt": "일러스트: 시험 코스 띠", "alt_en": "Illustration: a test course band",
                             "slot": f"course.banner.{course_id}", "status": "연결"}, (1536, 640), "img")]
    images, art_dir = art_set(tmp_path, rows)
    cfg = {"images": images}
    first = {"guide.banner": camp, "course.banner": "course-test"}
    monkeypatch.setattr(art, "ART_DIR", art_dir)
    (data / "art.json").write_text(json.dumps(cfg, ensure_ascii=False), "utf-8")
    assert art.data_problems(data, art_dir) == []
    out = tmp_path / "out"
    build(data, out, "sample")
    found = art.slots(data)
    assert {"list.head.places", "og.default", f"guide.banner.{guide_id}", f"course.banner.{course_id}"} <= set(found)

    def html(path):
        return (out / path).read_text("utf-8")
    if "list.head.places" in found:                                      # D: the band above the list's H1
        page = html("places/index.html")
        band = page.split('data-art="head-places"', 1)[1].split("</figure>", 1)[0]
        assert band.startswith(' aria-hidden="true">')              # decorative: not read on every list
        assert "fetchpriority" not in band and "loading=" not in band   # first screen, not ahead of css and fonts
        assert 'alt="일러스트: ' in band and "<figcaption" not in band and "head-places-400.avif 400w" in band
        assert page.index('data-art="head-places"') < page.index('id="h-list"')
    if camp:                                                             # C: the guide's campaign card
        guide = html(next((out / "guides").glob("*/index.html")).relative_to(out))
        printed = cfg["images"][camp]["text"]
        printed = printed if isinstance(printed, str) else " ".join(printed)
        assert 'class="art art-camp"' in guide and printed in guide and "has-camp" in guide
    if first.get("course.banner"):                                       # I: the band above the course's H1
        course = html(next((out / "courses").glob("*/index.html")).relative_to(out))
        assert f'data-art="{first["course.banner"]}"' in course and 'class="wrap art-band-wrap"' in course
    if "page.404" in found:                                              # F: 404 and the empty search result
        assert 'data-art="art-404"' in html("404.html")
    if "search.empty" in found and (out / "search" / "index.html").exists():
        search = html("search/index.html")
        assert "<div data-empty-art hidden>" in search and 'data-art="art-empty"' in search
    if "og.default" in found:                                            # E: link preview of photo-less pages
        about = html("about/index.html")
        assert 'property="og:image" content="https://example.com/assets/art/og-ko-1200.jpg"' in about
        assert 'property="og:image:alt" content="일러스트: ' in about and 'og:image:width" content="1200"' in about
    for f in (out / "places").glob("*/index.html"):                       # a place keeps its photo, or none
        assert "/assets/art/" not in f.read_text("utf-8"), f
    published = {f.name for f in (out / "assets" / "art").iterdir()} if (out / "assets" / "art").exists() else set()
    assert published == art.used_files(out)                              # exactly what the pages use
    errors = validate(data, out, "sample")[0]
    assert errors == [], errors[:10]


# ------------------------------------------------------------------ A·B: the home's season picture and news-card pictures
def tiny_picture() -> bytes:
    """A tiny generated test image (WebP from Pillow; a fixed 1×1 WebP when Pillow is not installed)."""
    try:
        from PIL import Image
    except ImportError:
        return bytes.fromhex("524946461e000000574542505650384c110000002f000000000750f3fa77b9ff8188e87f0000")
    buf = io.BytesIO()
    Image.new("RGB", (6, 4), (254, 230, 203)).save(buf, "WEBP")
    return buf.getvalue()


def test_home_opening_and_news_cards_with_and_without_art(tmp_path, monkeypatch):
    """Spec 7, owner 2026-10-13 night: with a picture in art.json (home.card.<kind>) a news card without a photo shows
    it through figure() — alt '일러스트: ', width·height, lazy, no label; without one, the card shows its type icon.
    The opening is the photo opening either way: a season picture ('개편 뒤 연결' — home.hero is no slot any more) never
    shows, and no page carries the dropped label. Both builds pass validate."""
    data = tmp_path / "data"
    shutil.copytree(SAMPLE, data)
    art_dir = tmp_path / "art"
    art_dir.mkdir()
    blob = tiny_picture()
    images, manifest = {}, {}
    for art_id, slot, size, status in (("hero-test", "home.hero.autumn", (1536, 1024), "개편 뒤 연결"),
                                       ("card-test-guide", "home.card.guide", (1024, 1024), "연결"),
                                       ("card-test-event", "home.card.event", (1024, 1024), "연결")):
        files = {fmt: f"{art_id}-400.{fmt}" for fmt in ("avif", "webp")}
        for name in files.values():
            (art_dir / name).write_bytes(blob)
        manifest[art_id] = {"w": size[0], "h": size[1], **{fmt: [[name, 400, len(blob)]] for fmt, name in files.items()}}
        images[art_id] = {"file": f"{art_id}.png", "alt": f"일러스트: 시험 그림 {art_id}",
                          "alt_en": f"Illustration: test picture {art_id}", "slot": slot, "status": status}
    (art_dir / "manifest.json").write_text(json.dumps(manifest), "utf-8")
    (data / "art.json").write_text(json.dumps({"images": images}, ensure_ascii=False), "utf-8")
    monkeypatch.setattr(art, "ART_DIR", art_dir)

    def home_parts(out):
        html = (out / "index.html").read_text("utf-8")
        news = html[html.index('<div class="ho-news">'):html.index('<section class="hq"')]
        guide = next(c for c in news.split('<article class="nc nc-')[1:] if c.startswith("guide"))
        return html, guide

    build(data, tmp_path / "with", "sample")
    html, guide = home_parts(tmp_path / "with")
    assert '<section class="ho"' in html and 'data-art="hero-test"' not in html   # the season picture: gone
    assert 'data-art="card-test-guide"' in guide and 'data-pic=' not in guide
    assert 'alt="일러스트: 시험 그림 card-test-guide"' in guide and "<figcaption" not in guide
    assert 'loading="lazy"' in guide and 'width="1024" height="1024"' in guide
    for f in (tmp_path / "with").rglob("*.html"):
        assert not art.dropped_labels(f.read_text("utf-8")), f
    assert sorted(f.name for f in (tmp_path / "with" / "assets" / "art").iterdir()) == \
        sorted(art.used_files(tmp_path / "with"))
    assert not any(n.startswith("hero-test") for n in art.used_files(tmp_path / "with"))
    assert validate(data, tmp_path / "with", "sample")[0] == []

    (data / "art.json").unlink()                                         # no picture: the type icon
    build(data, tmp_path / "without", "sample")
    html, guide = home_parts(tmp_path / "without")
    assert '<section class="ho"' in html and "data-art=" not in html
    # no picture: the kind's 3D picture by registry ID (the interim look until its file exists), never a photo
    assert 'data-pic="guide"' in guide and 'class="nc-frame nc-icof"' in guide
    assert not (tmp_path / "without" / "assets" / "art").exists()
    assert validate(data, tmp_path / "without", "sample")[0] == []
