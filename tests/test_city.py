"""The city is configuration (pipeline/city.py, data/<region>/site.json): the Incheon config with a clearly fake tiny
dataset (tests/fixtures/incheon_tiny — never data/incheon's collected records) builds and validates with no trace of
the sample city in any output file; the config before collection (no records) builds an honest empty-state preview —
no picture but the menu's own icons, no link to a page that has no data — and stops a production build with the
collection hint; the 권역 rule is the configured district rule, and the map page prints the rule that assigned the
places; the city's tourism site (site.json `source`) is credited as '원문 출처' only when a built record cites it."""
import json
import re
import shutil
from html.parser import HTMLParser
from pathlib import Path

import pytest

from pipeline import city
from pipeline.build import NoPlacesError, build
from pipeline.textutil import area_from_address
from pipeline.validate import validate

ROOT = Path(__file__).resolve().parent.parent
INCHEON = ROOT / "data" / "incheon"
# the files a collection or a writer adds to data/incheon (TourAPI writes places·events): left out of a copy that
# stands for this site's configuration before collection
RECORDS = ("places.json", "events.json", "courses.json", "guides.json", "themes.json", "videos.json")
TINY = Path(__file__).resolve().parent / "fixtures" / "incheon_tiny"
# the sample city's names in every script the engine has used: none may reach an Incheon page, script or data file
FOREIGN = re.compile(r"군산|gunsan|Gunsan|GUNSAN|群山|Кунсан|선유도|Seonyudo|고군산")
YJ = ("운서동", "운남동", "운북동", "중산동", "을왕동", "남북동", "덕교동", "무의동")


def _incheon_data(tmp_path: Path, with_fixture: bool) -> Path:
    data = tmp_path / "data"
    data.mkdir()
    for f in INCHEON.glob("*.json"):
        if f.name not in RECORDS:
            shutil.copy(f, data / f.name)
    if with_fixture:
        for f in TINY.glob("*.json"):
            shutil.copy(f, data / f.name)
    return data


class _Scan(HTMLParser):
    """images (src, alt) outside the assistant's launcher, chrome (the launcher's own), every link."""

    def __init__(self):
        super().__init__()
        self.images, self.chrome, self.links, self.in_fab = [], [], [], False

    def handle_starttag(self, tag, attrs):
        a = dict(attrs)
        if tag == "button" and "chat-fab" in (a.get("class") or "").split():
            self.in_fab = True
        if tag == "img":
            (self.chrome if self.in_fab else self.images).append((a.get("src") or "", a.get("alt")))
        if tag == "a":
            self.links.append(a.get("href") or "")

    def handle_endtag(self, tag):
        if tag == "button":
            self.in_fab = False


def _scan(page: Path) -> _Scan:
    s = _Scan()
    s.feed(page.read_text("utf-8"))
    return s


def _foreign_hits(out: Path) -> list[str]:
    hits = []
    for f in sorted(out.rglob("*")):
        if f.is_file() and f.suffix in (".html", ".js", ".css", ".json", ".txt", ".xml", ".md", ".webmanifest"):
            m = FOREIGN.search(f.read_text("utf-8", errors="replace"))
            if m:
                hits.append(f"{f.relative_to(out)}: {m.group(0)}")
    return hits


# the operator's 권역 of 2026-10-19: each 구·군 TourAPI lists in exactly one 권역
REGION_OF = {"제물포구": "개항장·월미", "영종구": "영종·용유", "연수구": "송도·연수", "강화군": "강화", "옹진군": "옹진 섬",
             "미추홀구": "도심·소래", "남동구": "도심·소래", "부평구": "도심·소래", "계양구": "도심·소래", "서해구": "도심·소래",
             "검단구": "도심·소래"}


def test_incheon_districts_are_tourapi_s_eleven_each_in_one_region():
    """site.json districts are the 11 구·군 TourAPI's ldongCode2 (lDongRegnCd 28) lists, the old names stay readable
    (districts_former), and the district rule puts every one of them in exactly one 권역 — the operator's table."""
    site = json.loads((INCHEON / "site.json").read_text("utf-8"))
    assert site["districts"] == ["제물포구", "영종구", "미추홀구", "연수구", "남동구", "부평구", "계양구", "서해구", "검단구",
                                 "강화군", "옹진군"]
    assert site["districts_former"] == ["중구", "동구", "서구"]
    C = city.activate(site)
    for district, region in REGION_OF.items():
        hits = [r.name for r in C.regions if any(m.get("district") == district for m in r.match)]
        assert hits == [region], district                                        # one 권역, never two
        assert C.district_region(district, "") == region == C.district_region(district, "테스트동")
    assert set(REGION_OF) == set(site["districts"])
    assert [r.name for r in C.regions] == ["개항장·월미", "영종·용유", "송도·연수", "강화", "옹진 섬", "도심·소래"]
    # an address with an old name follows the 구·군 that took its place
    assert C.district_region("동구", "송림동") == "개항장·월미" and C.district_region("서구", "") == "도심·소래"
    assert C.district_region("중구", "을왕동") == "영종·용유" and C.district_region("중구", "신포동") == "개항장·월미"
    assert C.district_region("중구", "") is None                               # 중구 with no 법정동: 권역 미정


def test_incheon_district_rule_and_its_text():
    C = city.activate_dir(INCHEON)
    assert C.region_method == "district" and C.locality == "인천광역시" and C.region_admin == ""
    cases = {
        "인천광역시 중구 공항로 272 (운서동)": ("중구", "영종·용유"),
        "인천광역시 중구 신포로27번길 80 (관동1가)": ("중구", "개항장·월미"),   # a 법정동 with a 가 number stays whole
        "인천광역시 중구 공항로 272": ("중구", None),                            # 중구 without a 법정동: not split
        "인천광역시 영종구 하늘중앙로 201": ("영종구", "영종·용유"),
        "인천광역시 제물포구 금곡로 27 (송림동)": ("제물포구", "개항장·월미"),
        "인천광역시 동구 테스트로 1": ("동구", "개항장·월미"),
        "인천광역시 연수구 테스트대로 2": ("연수구", "송도·연수"),
        "인천광역시 서해구 테스트로 3": ("서해구", "도심·소래"),
        "인천광역시 검단구 테스트로 4": ("검단구", "도심·소래"),
        "인천광역시 남동구 테스트로 8": ("남동구", "도심·소래"),
        "인천광역시 강화군 강화읍 테스트로 5": ("강화군", "강화"),
        "인천광역시 옹진군 테스트면 테스트리 6": ("옹진군", "옹진 섬"),
        "서울특별시 중구 테스트로 7": ("", None),                                 # another city's 중구 is not Incheon's
    }
    for address, (district, region) in cases.items():
        d = C.district_of(address)
        assert d == district, address
        assert C.district_region(d, area_from_address(address)) == region, address
    assert C.district_of("테스트로 5", "제물포구") == "제물포구"                   # TourAPI's 구·군 when the address has none
    lines = C.region_rule_lines()
    assert lines[0] == f"개항장·월미: 제물포구, 옛 동구, 옛 중구 중 {'·'.join(YJ)}을 뺀 곳"
    assert lines[1] == f"영종·용유: 영종구, 옛 중구 중 {'·'.join(YJ)}"
    assert lines[5] == "도심·소래: 미추홀구, 남동구, 부평구, 계양구, 서해구, 검단구, 옛 서구"
    assert [line.split(":")[0] for line in lines] == ["개항장·월미", "영종·용유", "송도·연수", "강화", "옹진 섬", "도심·소래"]
    # the city's own names in the stock-phrase rule, the address split for JSON-LD, the prefix that goes
    assert re.match(C.taut_rx("가"), "가는 인천광역시 중구 테스트동에 있는 관광지입니다.")
    assert not re.match(C.taut_rx("가"), "가는 바다를 내려다보는 전망대가 있는 관광지입니다.")
    assert C.postal_parts("인천광역시 중구 테스트로 1") == ("인천광역시", "중구", "테스트로 1")
    assert C.strip_prefix("인천광역시 중구 테스트로 1") == "중구 테스트로 1"
    assert C.place_where("연수구", "테스트동") == "인천광역시 연수구 테스트동"


def test_sample_city_keeps_its_anchor_rule():
    C = city.current()   # tests/conftest.py: the sample fixture's city
    assert C.region_method == "nearest_anchor" and C.far_m == 12000 and C.region_art["먼 섬"] == "outlying-islands"
    assert C.postal_parts("전북특별자치도 군산시 테스트로 1") == ("전북특별자치도", "군산시", "테스트로 1")
    assert C.display_address("전라북도 군산시 테스트로 1") == "전북특별자치도 군산시 테스트로 1"


def test_neutral_city_assumes_nothing():
    C = city.activate({})
    assert C.names == () and C.region_method == "none" and C.distance_anchors == [] and C.region_rule_lines() == []
    assert C.strip_prefix("어디시 테스트로 1") == "어디시 테스트로 1" and C.district_of("어디시 중구 1") == ""


SITE = "https://incheon.webforai.kr"   # site_url (operator 2026-10-19)


def test_incheon_fixture_builds_and_validates_with_no_trace_of_the_sample_city(tmp_path):
    data = _incheon_data(tmp_path, with_fixture=True)
    out = tmp_path / "out"
    stats = build(data, out, "preview")
    assert stats["entities"] == 7
    errors, _, _ = validate(data, out, "preview")
    assert errors == [], errors[:5]
    assert _foreign_hits(out) == []
    # the map page prints the rule that assigned the places, and the places sit in their 권역
    page = (out / "map" / "index.html").read_text("utf-8")
    assert "권역은 주소에 적힌 구·군" in page and "영종·용유: 영종구, 옛 중구 중 운서동" in page
    regions = re.findall(r'<h2 id="r-[^"]*-h">([^<]*?) <span', page)
    assert regions == ["개항장·월미", "영종·용유", "송도·연수", "강화", "옹진 섬", "도심·소래", "권역 미정"]
    assert "중구 운서동" in page                                           # a 광역시's 동 carries its 구·군
    # the home: the assistant's card in the centre (data/incheon/ask.json), the city's words for chat.js
    home = (out / "index.html").read_text("utf-8")
    assert 'id="ask-q"' in home and f'data-chat-site="{SITE}"' in home
    assert "지금 인천 · " in home and "인천 여행의 모든 것" not in home      # the old provisional name is gone
    site = json.loads((out / "chat" / "site.json").read_text("utf-8"))
    # no planner hubs yet (site.json city.plan.hubs: the operator's): the form asks none, the planner refuses one
    assert site == {"city": {"en": "Incheon", "ko": "인천"}, "name": "인천각", "origins": [], "url": SITE, "hubs": {}}
    # structured data: the neutral city node, a 광역시 address split into 시 and 구
    assert f'"@id":"{SITE}/#city","name":"인천광역시"' in home.replace(" ", "")
    beach = (out / "places" / "test-beach-a" / "index.html").read_text("utf-8").replace(" ", "")
    assert '"addressRegion":"인천광역시","addressLocality":"중구"' in beach
    # everything made from site_url names the operator's domain (canonical, sitemap, the assistant's site above)
    assert f'<link rel="canonical" href="{SITE}/">' in home
    assert f"<loc>{SITE}/cafes/</loc>" in (out / "sitemap.xml").read_text("utf-8")


def test_incheon_brand_name_symbol_and_h1(tmp_path):
    """Operator 2026-10-19: the site is 인천각 (English Incheongak), its symbol the bridge-pylon bookmark redrawn from
    the chosen raster (templates/assets/brand/incheongak-*.svg, tools/brand_kit.py) beside the name in the header and
    footer, the name's end '각' in the logo's blue (present.wordmark), titles and structured data named 인천각, and the
    home's H1 '오늘, 인천 가는 각' (city.home.h1)."""
    site = json.loads((INCHEON / "site.json").read_text("utf-8"))
    assert (site["site_url"], site["site_name"], site["brand"]) == (SITE, "인천각", "인천각")
    assert site["brand_symbol"] == "incheongak-symbol.svg" and "site_name_status" not in site
    assert site["city"]["intl"]["en"] == {"site_name": "Incheongak", "city": "Incheon"}
    assert site["brand_colors"] == {"sea": "#1764C0", "coral": "#FF7A5C", "ink": "#172033"}
    brand = ROOT / "templates" / "assets" / "brand"
    import xml.etree.ElementTree as ET
    for name in ("symbol", "symbol-reverse", "symbol-mono", "logo", "app-icon"):
        svg = ET.parse(brand / f"incheongak-{name}.svg").getroot()
        assert svg.tag.endswith("svg") and svg.get("viewBox"), name
    sym = (brand / "incheongak-symbol.svg").read_text("utf-8")
    assert 'aria-hidden="true"' in sym and 'fill="#1764C0"' in sym and 'fill="#FF7A5C"' in sym    # sea, coral sun
    assert 'fill="#FF7A5C"' not in (brand / "incheongak-symbol-reverse.svg").read_text("utf-8")   # the sun cut out
    assert 'aria-label="인천각 Incheongak"' in (brand / "incheongak-logo.svg").read_text("utf-8")
    from PIL import Image
    for px in (48, 96, 180, 192, 512):
        with Image.open(brand / f"icon-{px}.png") as im:
            assert im.size == (px, px) and im.getpixel((0, 0))[:3] == (0x17, 0x64, 0xC0)     # full bleed, sea blue
    with Image.open(brand / "favicon.ico") as ico:
        assert {(16, 16), (32, 32), (48, 48)} <= set(ico.info["sizes"])
    data = _incheon_data(tmp_path, with_fixture=True)
    out = tmp_path / "out"
    build(data, out, "preview")
    home = (out / "index.html").read_text("utf-8")
    assert '<h1 id="h-home" class="op-h1 hk-h1">오늘, 인천 가는 각</h1>' in home
    # the title names what the site has (UI review 2026-10-19, P2-6): the fixture's five kinds, no course, event or video
    assert '<title>인천각 — 인천 관광지·맛집·카페·숙소·쇼핑</title>' in home
    assert '<meta property="og:site_name" content="인천각">' in home
    assert '"@type":"WebSite"' in home.replace(" ", "") and '"name":"인천각"' in home.replace(" ", "")
    mark = '<span class="wm-a">인천<span class="wm-em">각</span></span>'
    assert home.count(mark) == 2 and home.count('<span class="wm-sym" aria-hidden="true"><svg') == 2   # bar and footer
    cafe = (out / "places" / "test-cafe-f" / "index.html").read_text("utf-8")
    assert "<title>" in cafe and " | 인천각</title>" in cafe


def test_incheon_before_collection_preview_is_empty_state_and_production_stops(tmp_path, capsys):
    data = _incheon_data(tmp_path, with_fixture=False)
    out = tmp_path / "out"
    stats = build(data, out, "preview")
    assert stats["entities"] == 0 and "TourAPI 수집 전" in capsys.readouterr().err
    errors, _, _ = validate(data, out, "preview")
    assert errors == [], errors[:5]
    assert _foreign_hits(out) == []
    assert "여행지 안내를 준비하고 있습니다" in (out / "index.html").read_text("utf-8")
    # nothing dresses the empty data up (CLAUDE.md 4): no photo, no illustration (no AI art at all before the first
    # place) — only the menu's own 3D icons, which sit beside their links with or without data; the mascot is decorative
    # site furniture (alt=""), as the launcher's face
    pages = sorted(out.rglob("*.html"))
    assert pages
    for page in pages:
        s = _scan(page)
        assert "/assets/art/" not in page.read_text("utf-8"), page
        assert [src for src, alt in s.images if not src.startswith("/assets/icons/")
                and not (src.startswith("/assets/mascot/") and alt == "")] == [], page
        assert all(src.startswith("/assets/") and alt == "" for src, alt in s.chrome), page
        # every way on goes to a page that exists: no guide, course, event, map or search page without data
        for href in s.links:
            path = href.split("#")[0].split("?")[0]
            assert not path.startswith(("/guides/", "/courses/", "/events/", "/map/", "/search/")), (page, href)
            if path.startswith("/") and not path.startswith("//"):
                target = out / path.lstrip("/")
                assert (target / "index.html").exists() or target.is_file(), (page, href)
    assert "/places/" in _scan(out / "index.html").links
    with pytest.raises(NoPlacesError, match="tools/collect.py --data"):
        build(data, tmp_path / "prod", "production")


def test_the_city_tourism_site_is_credited_only_when_a_record_cites_it(tmp_path):
    """TourAPI-only data names 한국관광공사 TourAPI, not the city's tourism site, as its source (footer, /about/,
    llms.txt, the assistant's knowledge); the city's site stays an official link. A record citing that site brings
    the '원문 출처' line back."""
    data = _incheon_data(tmp_path, with_fixture=True)
    site = json.loads((data / "site.json").read_text("utf-8"))
    name, url = site["source"]["name"], site["source"]["url"]
    out = tmp_path / "tourapi-only"
    build(data, out, "preview")
    home, about = (out / "index.html").read_text("utf-8"), (out / "about" / "index.html").read_text("utf-8")
    llms, docs = (out / "llms.txt").read_text("utf-8"), (out / "chat" / "docs.json").read_text("utf-8")
    for text in (home, about, llms, docs):
        assert "원문 출처" not in text
    assert "관광 정보·사진: 한국관광공사 TourAPI" in home and "관광 정보·사진: 한국관광공사 TourAPI" in llms
    assert "<dt>정보 출처</dt><dd>한국관광공사 TourAPI</dd>" in about and "정보 출처: 한국관광공사 TourAPI" in docs
    place = (out / "places" / "test-beach-a" / "index.html").read_text("utf-8")
    assert f"{name} 원문이 없어" not in place
    places = json.loads((data / "places.json").read_text("utf-8"))
    places[0]["official"] = {**(places[0].get("official") or {}), "source_url": url.rstrip("/") + "/test-page"}
    (data / "places.json").write_text(json.dumps(places, ensure_ascii=False), "utf-8")
    cited = tmp_path / "cited"
    build(data, cited, "preview")
    assert f'원문 출처: <a href="{url}"' in (cited / "index.html").read_text("utf-8")
    assert f"원문 출처: {name} ({url})." in (cited / "llms.txt").read_text("utf-8")
    assert f"<dt>원문 출처</dt><dd><a href=\"{url}\"" in (cited / "about" / "index.html").read_text("utf-8")
    assert f"원문 출처: {name} {url}." in (cited / "chat" / "docs.json").read_text("utf-8")
