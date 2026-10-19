"""Visitor navigation must reach real sections while rights and preview rules hold."""
import json
import re
import shutil
from html.parser import HTMLParser
from pathlib import Path
from urllib.parse import unquote, urlsplit

from pipeline import icons
from pipeline.build import build
from pipeline.textutil import sha256_text

ROOT = Path(__file__).resolve().parent.parent
SAMPLE = ROOT / "data" / "sample"


class NavigationScan(HTMLParser):
    """images: the page's pictures; chrome_images: the ones inside the site assistant's launcher (button.chat-fab: the
    mascot's face, the same on every page — site furniture, not a picture of the page's subject)."""

    def __init__(self):
        super().__init__()
        self.ids = []
        self.links = []
        self.images = []
        self.chrome_images = []
        self.in_fab = False
        self.current_links = []
        self.main = []
        self.scroll_navs = 0
        self.robots = ""

    def handle_starttag(self, tag, attrs):
        attrs = dict(attrs)
        if attrs.get("id"):
            self.ids.append(attrs["id"])
        if tag == "a":
            self.links.append(attrs.get("href", ""))
            if attrs.get("aria-current") == "page":
                self.current_links.append(attrs.get("href"))
        if tag == "main":
            self.main.append(attrs)
        if tag == "nav" and "menu-panel" in (attrs.get("class") or "").split():
            self.scroll_navs += 1
        if tag == "button" and "chat-fab" in (attrs.get("class") or "").split():
            self.in_fab = True
        if tag == "img":
            (self.chrome_images if self.in_fab else self.images).append(attrs)
        if tag == "meta" and attrs.get("name") == "robots":
            self.robots = attrs.get("content", "")

    def handle_endtag(self, tag):
        if tag == "button":
            self.in_fab = False


def scan(path):
    parsed = NavigationScan()
    parsed.feed(path.read_text("utf-8"))
    return parsed


def test_every_navigation_fragment_targets_a_real_unique_section(tmp_path):
    out = tmp_path / "sample"
    build(SAMPLE, out, "sample")
    pages = {p: scan(p) for p in out.rglob("*.html")}
    for path, page in pages.items():
        assert len(page.ids) == len(set(page.ids)), path
        assert len(page.main) == 1
        assert page.main[0]["id"] == "main-content"
        assert page.main[0]["tabindex"] == "-1"
        assert "#main-content" in page.links
        # Phone menu (Apple skin, deliberate change from the scrolling link row): one <details class="menu"> panel
        # holding the whole nav, which opens without JavaScript.
        assert page.scroll_navs == 1
        for href in page.links:
            url = urlsplit(href)
            if url.scheme or url.netloc or not url.fragment:
                continue
            if not url.path:
                target = path
            elif url.path.endswith("/"):
                target = out / unquote(url.path).strip("/") / "index.html"
            else:
                target = out / unquote(url.path).lstrip("/")
            assert target in pages, (path, href)
            assert unquote(url.fragment) in pages[target].ids, (path, href)
    detail = pages[out / "places" / "gyeongam-railroad-village" / "index.html"]
    assert "#h-facts" in detail.links and "#h-dir" in detail.links and "#h-near" in detail.links
    assert "/places/" in detail.current_links
    assert "/guides/" in pages[out / "guides" / "index.html"].current_links


def test_place_headings_name_the_place_and_the_city(tmp_path):
    # P1-2: a lifted section still says which place (and city) it is about. Apple place page (deliberate design
    # change): headings carry the name in its own span (ink) before the section word (grey), the route block's
    # heading is '… 가는 길' (the map is its own section, '… 지도'), and the city sits in the kicker line above the H1.
    out = tmp_path / "sample"
    build(SAMPLE, out, "sample")
    html = (out / "places" / "gyeongam-railroad-village" / "index.html").read_text("utf-8")
    heading = lambda hid: re.sub(r"<[^>]+>", "", re.search(rf'<h2 id="{hid}"[^>]*>(.*?)</h2>', html).group(1))
    assert heading("h-facts") == "경암동 철길마을 방문 전 확인"
    assert heading("h-dir") == "경암동 철길마을 가는 길"
    kicker = html.split('<p class="kicker">')[1].split("</p>")[0]
    assert "군산시" in kicker


def test_redesign_does_not_expose_unlicensed_originals_or_photos(tmp_path):
    data = tmp_path / "data"
    shutil.copytree(SAMPLE, data)
    places = json.loads((data / "places.json").read_text("utf-8"))
    place = places[0]
    hidden = "이 원문은 권리 미확인으로 모든 화면에서 숨겨져야 합니다."
    place["original"].update(text=hidden, license="NONE", sha256=sha256_text(hidden))
    # the Apple place page shows TourAPI photos only (present.photos, CLAUDE.md 3.4), so the allowed photo is one
    place["images"] = [
        {"url": "https://example.com/hidden.jpg", "license": "UNKNOWN", "alt": "미확인 사진"},
        {"url": "https://example.com/allowed.jpg", "license": "KOGL-1", "alt": "허용된 샘플 사진", "credit": "테스트 출처",
         "source": "TourAPI"},
    ]
    (data / "places.json").write_text(json.dumps(places, ensure_ascii=False), "utf-8")
    out = tmp_path / "preview"
    build(data, out, "preview")
    for page in out.rglob("*.html"):
        html = page.read_text("utf-8")
        assert hidden not in html
        assert "https://example.com/hidden.jpg" not in html
        assert scan(page).robots.startswith("noindex")
    detail = out / "places" / place["slug"] / "index.html"
    # the site's own 3D interface pictures (key-fact icons, the mascot: /assets/icons, /assets/mascot) are not photos
    images = [i for i in scan(detail).images if not i["src"].startswith(("/assets/icons/", "/assets/mascot/"))]
    assert [i["src"] for i in images] == ["https://example.com/allowed.jpg"]
    # the only other picture is the launcher's mascot face: decorative, and never a photo
    face = [("/assets/mascot/mascot-icon-3d-64.webp", "")] if icons.mascot("mascot-icon-3d") else []   # optional mascot
    assert [(i["src"], i["alt"]) for i in scan(detail).chrome_images] == face
    assert images[0]["alt"] == "허용된 샘플 사진"
    assert 'data-track="map_click"' in detail.read_text("utf-8")
    assert 'data-block="original"' in detail.read_text("utf-8")
    assert "검수 전" in (out / "places" / "sample-draft" / "index.html").read_text("utf-8")


def test_statistics_and_crawl_disclosures_match_actual_build_behavior(tmp_path):
    data = tmp_path / "data"
    shutil.copytree(SAMPLE, data)
    site_path = data / "site.json"
    site = json.loads(site_path.read_text("utf-8"))
    for mode, ga4 in (("preview", "G-ABC123DEF4"), ("production", ""), ("production", "G-ABC123DEF4")):
        site["ga4_id"] = ga4
        site_path.write_text(json.dumps(site, ensure_ascii=False), "utf-8")
        out = tmp_path / f"{mode}-{ga4 or 'unset'}"
        build(data, out, mode)
        about = (out / "about" / "index.html").read_text("utf-8")
        tracking_loaded = "googletagmanager.com/gtag/js" in about
        assert tracking_loaded == (mode == "production" and bool(ga4))
        assert tracking_loaded == ("이용 통계를 수집합니다" in about)
        if mode == "preview":
            assert "방문 통계를 수집하지 않습니다" in about
            assert "검색엔진 수집과 색인을 차단" in about
            assert "Disallow: /" in (out / "robots.txt").read_text("utf-8")
            assert "noindex" in scan(out / "about" / "index.html").robots
        # A TourAPI credit appears exactly when the built data uses TourAPI values.
        uses_tourapi = any("TourAPI" in (p.get("facts_source") or {}).get("provider", "")
                           for p in json.loads((data / "places.json").read_text("utf-8")))
        assert ("관광 정보·사진: 한국관광공사 TourAPI" in about) == uses_tourapi
        assert ("관광 정보·사진: 한국관광공사 TourAPI" in (out / "llms.txt").read_text("utf-8")) == uses_tourapi


def test_tourapi_data_brings_its_credit_line(tmp_path):
    data = tmp_path / "data"
    shutil.copytree(SAMPLE, data)
    places = json.loads((data / "places.json").read_text("utf-8"))
    for place in places:
        place["facts_source"] = {"provider": "군산시 문화관광", "checked_at": "2026-10-08"}
    (data / "places.json").write_text(json.dumps(places, ensure_ascii=False), "utf-8")
    build(data, tmp_path / "without", "preview")
    assert "관광 정보·사진: 한국관광공사 TourAPI" not in (tmp_path / "without" / "index.html").read_text("utf-8")
    places[0]["facts_source"] = {"provider": "한국관광공사 TourAPI", "contentid": "1", "checked_at": "2026-10-08"}
    (data / "places.json").write_text(json.dumps(places, ensure_ascii=False), "utf-8")
    out = tmp_path / "preview"
    build(data, out, "preview")
    for page in (out / "index.html", out / "about" / "index.html", out / "places" / places[0]["slug"] / "index.html"):
        assert "관광 정보·사진: 한국관광공사 TourAPI" in page.read_text("utf-8"), page
    assert "관광 정보·사진: 한국관광공사 TourAPI" in (out / "llms.txt").read_text("utf-8")
