"""Map provider: Kakao Maps (owner decision 2026-10-14, CLAUDE.md 9 '지도 제공자').

The JavaScript key is site.json kakao_js_key (a public key Kakao accepts only from the registered web domains); the
build writes the SDK URL into every map box (data-kakao-sdk) and assets/map.js fetches it when a box nears the screen,
after the page has loaded. A page without a map box names neither map.js nor the SDK. Without JS the map figure is not
shown (the page's lists and text are the answer); when the SDK is refused the box keeps its text with the failure line."""
import json
import re
import shutil
from pathlib import Path

from pipeline import intl_text
from pipeline.build import KAKAO_SDK, build, css_source, kakao_sdk_url, site_css

ROOT = Path(__file__).resolve().parent.parent
ASSETS = ROOT / "templates" / "assets"
# the key the site.json of the sample carries (a fake fixture key: this site's own key is the owner's to register —
# data/incheon/site.json kakao_js_key is empty until then)
SITE = json.loads((ROOT / "data" / "sample" / "site.json").read_text("utf-8"))
MAP_BOX = re.compile(r'<div class="map"[^>]*>')


def sample_build(tmp_path, key: str | None = "test-key-123"):
    data = tmp_path / "data"
    shutil.copytree(ROOT / "data" / "sample", data)
    site = json.loads((data / "site.json").read_text("utf-8"))
    if key is None:
        site.pop("kakao_js_key", None)
    else:
        site["kakao_js_key"] = key
    (data / "site.json").write_text(json.dumps(site, ensure_ascii=False), "utf-8")
    places = json.loads((data / "places.json").read_text("utf-8"))
    places[0]["geo"] = {"lat": 35.98, "lng": 126.72, "source": "test"}
    places[1]["geo"] = {"lat": 35.9805, "lng": 126.7215, "source": "test"}
    (data / "places.json").write_text(json.dumps(places, ensure_ascii=False), "utf-8")
    out = tmp_path / "out"
    build(data, out, "preview")
    pages = {p: p.read_text("utf-8") for p in out.rglob("*.html")}
    return out, places, pages


def test_the_key_comes_from_site_json_and_nowhere_else(tmp_path):
    out, places, pages = sample_build(tmp_path, "test-key-123")
    html = (out / "places" / places[0]["slug"] / "index.html").read_text("utf-8")
    boxes = MAP_BOX.findall(html)
    assert boxes and all('data-kakao-sdk="https://dapi.kakao.com/v2/maps/sdk.js?appkey=test-key-123&amp;autoload=false"' in b
                         for b in boxes)
    # the site's own key is in site.json, and no template, script or pipeline module spells it out
    key = SITE["kakao_js_key"]
    assert re.fullmatch(r"[0-9a-f]{32}", key)
    assert kakao_sdk_url(SITE) == KAKAO_SDK.format(key=key)
    sources = [*ASSETS.glob("*.js"), *(ROOT / "templates").rglob("*.j2"), *(ROOT / "pipeline").glob("*.py")]
    assert not [p.name for p in sources if key in p.read_text("utf-8")]
    # no key: the boxes stay (their text and the failure line), with no SDK to fetch
    assert kakao_sdk_url({}) == "" and kakao_sdk_url({"kakao_js_key": "  "}) == ""
    out2, places2, _ = sample_build(tmp_path / "nokey", None)
    html2 = (out2 / "places" / places2[0]["slug"] / "index.html").read_text("utf-8")
    assert MAP_BOX.search(html2) and "data-kakao-sdk" not in html2 and "dapi.kakao.com" not in html2


def test_pages_with_a_map_carry_the_loader_and_the_no_js_fallback(tmp_path):
    out, places, pages = sample_build(tmp_path)
    with_map = {p: h for p, h in pages.items() if 'class="map"' in h}
    assert len(with_map) >= 2  # the place pages with coordinates (and the lists that show them)
    for path, html in with_map.items():
        for box in MAP_BOX.findall(html):
            assert "data-kakao-sdk=" in box and "data-lenis-prevent" in box, path
            assert 'role="region"' in box and 'aria-label="' in box, path
            assert re.search(r"data-(map|points)=", box), path
        # the box's text while the map loads (and the failure line's place), inside a figure credited to Kakao
        assert '<p class="map-off">지도를 불러오는 중입니다.</p>' in html, path
        assert '<figure class="mapfig' in html and "지도: 카카오맵" in html, path
        # one script in the HTML: the SDK is never in the markup as a script, only as the box's data
        assert html.count("<script src=") == 1 and '<script src="https://dapi.kakao.com' not in html, path
    # without JS the map figure is not shown; the place page's own text and lists stay the answer
    css = site_css()  # the built stylesheet (whitespace collapsed)
    rule = re.search(r"([^{}]*html:not\(\.js\) \.mapfig[^{}]*)\{([^}]*)\}", css)
    assert rule and "display:none" in rule.group(2).replace(" ", "")
    place = (out / "places" / places[0]["slug"] / "index.html").read_text("utf-8")
    assert places[0]["name"] in place and "주소" in place


def test_pages_without_a_map_load_nothing_of_it(tmp_path):
    out, places, pages = sample_build(tmp_path)
    without = [p for p, h in pages.items() if 'class="map"' not in h]
    assert without
    for p in without:
        html = pages[p]
        assert "dapi.kakao.com" not in html and "map.js" not in html and "data-kakao-sdk" not in html, p
    # site.js attaches map.js only when the page has a map box; map.js takes the SDK address only from the box and
    # fetches it when a box nears the screen (or a folded map opens), never before the window 'load' event
    site = (ASSETS / "site.js").read_text("utf-8")
    assert 'var maps = $all(".map[data-points], .map[data-map]");\n  if (maps.length) {' in site
    js = (ASSETS / "map.js").read_text("utf-8")
    assert "dapi.kakao.com/v2/maps/sdk.js?appkey=…" in js  # named in the header comment only
    assert 'el.getAttribute("data-kakao-sdk")' in js and "kakao.maps.load(" in js
    assert 'src = "https://dapi.kakao.com' not in js and "appkey=" + SITE["kakao_js_key"] not in js
    assert "afterLoad(function () {\n      load(el)" in js
    assert 'rootMargin: "400px 0px"' in js and 'addEventListener("gs:showmap"' in js
    # the failure line when the SDK is refused (a domain the key is not registered for) or never arrives
    assert '"지도를 불러오지 못했습니다."' in js and "s.onerror = function () { clearTimeout(t); rej(); };" in js


def test_no_leaflet_or_openstreetmap_is_left(tmp_path):
    out, places, pages = sample_build(tmp_path)
    assert not (ASSETS / "vendor" / "leaflet").exists() and not (out / "assets" / "vendor" / "leaflet").exists()
    for p, html in pages.items():
        low = html.lower()
        assert "leaflet" not in low and "openstreetmap" not in low, p
    for f in [*ASSETS.glob("*.js"), *(ASSETS / "css").glob("*.css")]:
        low = f.read_text("utf-8").lower()
        assert "leaflet" not in low and "tile.openstreetmap.org" not in low, f.name
    # the footer and the map captions credit Kakao; the other versions' words follow the English
    footer = pages[out / "index.html"]
    assert "<li>지도: 카카오맵</li>" in footer
    assert "Kakao" in intl_text.EN["foot_maps"] and "Kakao" in intl_text.EN["map_credit"]
    for strings in (ROOT / "data" / "incheon").glob("*/strings.json"):
        rows = json.loads(strings.read_text("utf-8"))
        for key in ("chrome.foot_maps", "chrome.map_credit"):
            for text in (rows.get(key) or {}).values():
                assert "OpenStreetMap" not in text, (strings.parent.name, key)


def test_map_module_keeps_44px_controls_and_keyboard_use():
    js = (ASSETS / "map.js").read_text("utf-8")
    css = " ".join(css_source().split())  # the partials as written
    # zoom buttons are real buttons with names; the map itself takes the focus (arrow keys move it, + − zoom), and
    # the scroll wheel never zooms it
    assert 'zin.setAttribute("aria-label"' in js and 'zout.setAttribute("aria-label"' in js
    assert "box.tabIndex = 0;" in js and '{ ArrowLeft: [-1, 0], ArrowRight: [1, 0], ArrowUp: [0, -1], ArrowDown: [0, 1] }' in js
    assert "scrollwheel: false" in js
    assert ".map-zoom button { width: 44px; height: 44px;" in css and ".far-ctl {" in css and "min-height: 44px" in css
    assert ".kmap:focus-visible {" in css and ".mk-a:focus-visible {" in css
    # the site's img rule must not shrink Kakao's tiles
    assert ".kmap img { max-width: none; max-height: none; }" in css
