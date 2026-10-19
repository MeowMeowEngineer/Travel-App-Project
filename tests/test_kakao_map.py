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
# the key the site.json of the sample carries (a fake fixture key; this site's own key — data/incheon/site.json
# kakao_js_key, the operator's of 2026-10-19 — is never used here)
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
    places[0]["geo"] = {"lat": 35.98, "lng": 126.72, "source": "TourAPI"}
    places[1]["geo"] = {"lat": 35.9805, "lng": 126.7215, "source": "TourAPI"}
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
        # the box's own text is true without the map (a text reader, an AI fetching the HTML — review 2026-10-17: '불러오는
        # 중' was all it read); map.js writes 'loading' when it starts, then the map or the failure line
        assert '<p class="map-off">이 지도의 장소는 이 페이지에 글로도 적었습니다.</p>' in html, path
        assert "불러오는 중" not in html.split('<p class="map-off">', 1)[1].split("</p>", 1)[0], path
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
    # the course planner (/plan/) draws its numbered maps only after a plan comes back: its root names the SDK address
    # for that moment (data-kakao-sdk) and the page loads nothing of the map before — no map.js, no SDK script
    later = [p for p, h in pages.items() if "data-plan " in h and 'class="map"' not in h]
    for p in later:
        html = pages[p]
        assert "map.js" not in html and '<script src="https://dapi.kakao.com' not in html, p
        assert re.search(r'<div class="trp" data-plan [^>]*data-kakao-sdk="https://dapi\.kakao\.com/', html), p
    plan_js = (ASSETS / "plan.js").read_text("utf-8")
    assert 'if (!box.getAttribute("data-kakao-sdk")) return;' in plan_js and "win.GSMapStart(box)" in plan_js
    without = [p for p, h in pages.items() if 'class="map"' not in h and p not in later]
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
    # 'loading' only once drawing starts (the box's own text says the page lists the same places)
    assert 'if (o) o.textContent = W.load || (EN ? "Loading the map." : "지도를 불러오는 중입니다.");\n    afterLoad(' in js


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
    # every marker that is a link is named by its place (QA 2026-10-15 F10: also a list map's dots, which the phone's
    # 지도 view puts in the tab order); the packed list dots keep their own small hit area
    assert 'if (label && url) a.setAttribute("aria-label", label);' in js and "function listQuiet(r)" in js
    assert 'a.mk-a:not([tabindex="-1"]):not(.mk-li)' in css
    # the site's img rule must not shrink Kakao's tiles
    assert ".kmap img { max-width: none; max-height: none; }" in css


def test_in_a_browser_the_sdk_waits_for_load_and_the_box_then_says_it_failed(tmp_path):
    """Post-launch review 2026-10-14 (the source-text checks above, in a browser — Playwright + Chromium, the build
    served through page.route, nothing leaves the machine): a place page asks dapi.kakao.com for nothing before the
    window 'load' event and before a map box nears the screen; scrolled to its map, it asks once; when Kakao refuses
    (HTTP 401 — a domain the key is not registered for) the box shows the failure line instead of a blank."""
    import mimetypes
    from urllib.parse import unquote, urlsplit

    import pytest
    sync_api = pytest.importorskip("playwright.sync_api")
    out, places, pages = sample_build(tmp_path)
    slug = places[0]["slug"]
    assert MAP_BOX.search(pages[out / "places" / slug / "index.html"])
    sdk: list[str] = []

    def serve(route):
        url = route.request.url
        if "dapi.kakao.com" in url:
            sdk.append(url)
            return route.fulfill(status=401, body="unauthorized")
        if not url.startswith("http://site.test/"):
            return route.abort()
        path = unquote(urlsplit(url).path)
        f = out / path.strip("/")
        f = f / "index.html" if path.endswith("/") else f
        if not f.is_file():
            return route.fulfill(status=404, body="")
        route.fulfill(status=200, body=f.read_bytes(), content_type=mimetypes.guess_type(f.name)[0] or "application/octet-stream")

    with sync_api.sync_playwright() as p:
        try:
            browser = p.chromium.launch()
        except Exception as ex:  # noqa: BLE001 — Chromium is not installed here
            pytest.skip(f"Chromium 없음: {ex}")
        try:
            ctx = browser.new_context(viewport={"width": 390, "height": 844})
            ctx.route("**/*", serve)
            page = ctx.new_page()
            page.goto(f"http://site.test/places/{slug}/", wait_until="load")
            page.wait_for_timeout(600)
            box = page.locator(".map[data-points], .map[data-map]").first
            far = page.evaluate("(s) => document.querySelector(s).getBoundingClientRect().top > innerHeight + 400",
                                ".map[data-points], .map[data-map]")
            if far:
                assert sdk == []                                       # loaded, but no map near the screen yet
            box.scroll_into_view_if_needed()
            page.wait_for_timeout(1500)
            assert len(sdk) == 1 and "appkey=test-key-123" in sdk[0]    # one request, with the key from site.json
            assert "지도를 불러오지 못했습니다." in box.inner_text()       # the refusal is said, not a blank box
        finally:
            browser.close()


def test_every_language_version_names_the_maps_keyboard_use():
    """Post-launch review 2026-10-14: the Japanese maps' accessible name had no keyboard line (map.js reads it from
    data-words.keys for the versions other than Korean and English). Every such version has its own."""
    from pipeline import en_site
    from pipeline import locales as LC
    for code, loc in LC.LOCALES.items():
        if code in ("en", "ko"):
            continue
        words = json.loads(en_site.UIText(loc, {}).map_words())
        assert words["keys"] and "+" in words["keys"] and "−" in words["keys"], code


def list_build(tmp_path):
    """The sample build with three attractions on the map, two of them free ('요금 무료', the attraction list's check
    box: ?check=1 keeps exactly two of the three map points)."""
    data = tmp_path / "data"
    shutil.copytree(ROOT / "data" / "sample", data)
    site = json.loads((data / "site.json").read_text("utf-8"))
    site["kakao_js_key"] = "test-key-123"
    (data / "site.json").write_text(json.dumps(site, ensure_ascii=False), "utf-8")
    places = json.loads((data / "places.json").read_text("utf-8"))
    attr = [p for p in places if p.get("kind") == "attraction" and p.get("status") == "published"][:3]
    assert len(attr) == 3
    for i, p in enumerate(attr):
        p["geo"] = {"lat": 35.98 + i * 0.01, "lng": 126.72 + i * 0.012, "source": "TourAPI"}
    for p in (attr[0], attr[2]):
        p.setdefault("facts", {})["usefee"] = "무료"
    (data / "places.json").write_text(json.dumps(places, ensure_ascii=False), "utf-8")
    out = tmp_path / "out"
    build(data, out, "preview")
    return out, attr


def test_list_rows_and_the_list_map_share_their_places(tmp_path):
    """QA 2026-10-15 F04: a list row with coordinates carries data-geo="1" (site.js counts the shown ones: '지도 n' and
    the map caption's [data-geo-cap]); those rows are exactly the map's points."""
    import html as H
    out, attr = list_build(tmp_path)
    h = (out / "places" / "index.html").read_text("utf-8")
    rows = re.findall(r'<li class="rec"[^>]*>', h)
    geo = sorted(re.search(r'id="(r\d+)"', r).group(1) for r in rows if 'data-geo="1"' in r)
    pts = json.loads(H.unescape(re.search(r"data-points='([^']*)'", h).group(1)))["list"]
    assert len(geo) == 3 and geo == sorted(p["id"] for p in pts)
    # the caption also names the list's places that are not on the map (outside evaluation 2026-10-18; site.js keeps
    # the number to the shown rows, tests/test_list_filters.py)
    assert ("<figcaption><span data-geo-cap>좌표가 있는 3곳만 표시</span><span data-geo-off data-tpl=\" · 지도에 없는 {n}곳은 "
            f"목록에서\"> · 지도에 없는 {len(rows) - 3}곳은 목록에서</span> · 지도: 카카오맵</figcaption>") in h
    assert len(rows) > 3
    assert '>지도 <span class="tn">3</span></button>' in h
    assert all('data-group="' in r and 'data-area="' in r and 'data-region="' in r for r in rows)
    # the bar's tools wrap below 761px instead of pushing the page sideways (QA 2026-10-15 SRC-01d: /places/?check=1
    # was 449px wide at 412): the 필터 button and the list | map switch never shrink, the count line wraps
    css = " ".join(css_source().split())
    assert ".f-tools .f-more, .f-tools .seg { flex: none; }" in css
    assert ("@media (max-width: 760px) { .f-tools { flex-wrap: wrap; row-gap: 6px; } .f-tools .f-result { flex: 1 1 5.5em; "
            "min-width: min-content; white-space: normal; line-height: 1.3; } }") in css


def test_in_a_browser_the_list_map_follows_the_filter_and_names_its_markers(tmp_path):
    """QA 2026-10-15 F04 / F10 (Playwright + Chromium; the build served through page.route and a stand-in for the Kakao
    SDK, tests/js/kakao_stub.js — nothing leaves the machine). On a phone, filtering first and opening the 지도 view
    after builds the map with the filtered places only, framed on them, and '지도 n' and the caption count them; the
    same from a URL that sets the filter. The markers are links named by their places, in the tab order while the
    list is not shown (the phone's 지도 view) and quiet beside the shown list (목록 view, desktop). On a desktop, where
    the map is built first, the filter takes markers off and back."""
    import mimetypes
    from urllib.parse import unquote, urlsplit

    import pytest
    sync_api = pytest.importorskip("playwright.sync_api")
    out, attr = list_build(tmp_path)
    stub = (ROOT / "tests" / "js" / "kakao_stub.js").read_text("utf-8")

    def serve(route):
        url = route.request.url
        if "dapi.kakao.com" in url:
            return route.fulfill(status=200, body=stub, content_type="application/javascript")
        if not url.startswith("http://site.test/"):
            return route.abort()
        path = unquote(urlsplit(url).path)
        f = out / path.strip("/")
        f = f / "index.html" if path.endswith("/") else f
        if not f.is_file():
            return route.fulfill(status=404, body="")
        route.fulfill(status=200, body=f.read_bytes(), content_type=mimetypes.guess_type(f.name)[0] or "application/octet-stream")

    state = """() => {
      const r = GSMaps.find(m => m.data && m.data.list), as = [...r.el.querySelectorAll('a.mk-a')];
      const rows = [...document.querySelectorAll('.rec:not([hidden])[data-geo] .rec-link')];
      const b = r.map.getBounds(), sw = b.getSouthWest(), ne = b.getNorthEast(), keep = new Set(as.map(a => a.getAttribute('href')));
      const name = {}; document.querySelectorAll('.rec-link').forEach(a => { name[a.getAttribute('href')] = a.textContent.trim(); });
      return { markers: [...keep].sort(), rows: rows.map(a => a.getAttribute('href')).sort(),
               tn: document.querySelector('[data-view=map] .tn').textContent,
               cap: document.querySelector('.list-map [data-geo-cap]').textContent,
               inb: r.data.list.filter(p => keep.has(p.url)).every(p => p.lat >= sw.getLat() && p.lat <= ne.getLat() && p.lng >= sw.getLng() && p.lng <= ne.getLng()),
               named: as.every(a => a.getAttribute('aria-label') === name[a.getAttribute('href')]),
               open: as.every(a => a.tabIndex === 0 && !a.hasAttribute('aria-hidden')),
               quiet: as.every(a => a.tabIndex === -1 && a.getAttribute('aria-hidden') === 'true' && a.getAttribute('aria-label')) };
    }"""
    free = sorted(f"/places/{p['slug']}/" for p in (attr[0], attr[2]))

    with sync_api.sync_playwright() as p:
        try:
            browser = p.chromium.launch()
        except Exception as ex:  # noqa: BLE001 — Chromium is not installed here
            pytest.skip(f"Chromium 없음: {ex}")
        try:
            ctx = browser.new_context(viewport={"width": 390, "height": 844})
            ctx.route("**/*", serve)
            for how in ("clicks", "url"):
                page = ctx.new_page()
                errors: list[str] = []
                page.on("pageerror", lambda e: errors.append(str(e)))
                if how == "clicks":   # filter first, then the 지도 view (the map is built only then)
                    page.goto("http://site.test/places/", wait_until="load")
                    page.click("[data-f-more]")
                    page.check("input[data-f=check]")
                    page.click("[data-filters] [data-view=map]")
                else:
                    page.goto("http://site.test/places/?check=1&view=map", wait_until="load")
                page.wait_for_function("() => (window.GSMaps || []).some(m => m.data && m.data.list)", timeout=10000)
                page.wait_for_timeout(200)
                s = page.evaluate(state)
                assert s["markers"] == s["rows"] == free, (how, s)
                assert s["tn"] == "2" and "2곳" in s["cap"] and s["inb"], (how, s)
                assert s["named"] and s["open"], (how, s)
                page.focus(".list-map .kmap")
                page.keyboard.press("Tab")
                assert page.evaluate("() => document.activeElement.matches('.list-map a.mk-a')"), how
                page.click("[data-filters] [data-view=list]")
                page.wait_for_timeout(100)
                assert page.evaluate(state)["quiet"], how
                assert errors == [], errors
                page.close()
            ctx.close()
            ctx = browser.new_context(viewport={"width": 1440, "height": 900})
            ctx.route("**/*", serve)
            page = ctx.new_page()
            page.goto("http://site.test/places/", wait_until="load")
            page.evaluate("() => document.querySelector('.list-map').scrollIntoView()")
            page.wait_for_function("() => (window.GSMaps || []).some(m => m.data && m.data.list)", timeout=10000)
            assert len(page.evaluate(state)["markers"]) == 3
            page.click("[data-f-more]")
            page.check("input[data-f=check]")
            page.wait_for_timeout(200)
            s = page.evaluate(state)
            assert s["markers"] == s["rows"] == free and s["tn"] == "2" and s["inb"] and s["quiet"] and s["named"], s
            page.uncheck("input[data-f=check]")
            page.wait_for_timeout(200)
            s = page.evaluate(state)
            assert len(s["markers"]) == 3 and s["tn"] == "3" and "3곳" in s["cap"], s
        finally:
            browser.close()


def test_in_a_browser_the_whole_map_view_lets_its_markers_into_the_tab_order(tmp_path):
    """Review 2026-10-17 (map access): on /map/ the markers stayed aria-hidden with tabindex -1 after the phone's 지도
    view hid the directory — listQuiet() only looked at list pages. Now /map/ follows the same rule: beside the shown
    directory (목록 view, desktop) the markers are quiet (the rows are the same links); in the phone's 지도 view they are
    links named by their places, in the tab order."""
    import mimetypes
    from urllib.parse import unquote, urlsplit

    import pytest
    sync_api = pytest.importorskip("playwright.sync_api")
    out, attr = list_build(tmp_path)
    stub = (ROOT / "tests" / "js" / "kakao_stub.js").read_text("utf-8")

    def serve(route):
        url = route.request.url
        if "dapi.kakao.com" in url:
            return route.fulfill(status=200, body=stub, content_type="application/javascript")
        if not url.startswith("http://site.test/"):
            return route.abort()
        path = unquote(urlsplit(url).path)
        f = out / path.strip("/")
        f = f / "index.html" if path.endswith("/") else f
        if not f.is_file():
            return route.fulfill(status=404, body="")
        route.fulfill(status=200, body=f.read_bytes(), content_type=mimetypes.guess_type(f.name)[0] or "application/octet-stream")

    state = """() => {
      const r = GSMaps.find(m => m.data && m.data.all), as = [...r.el.querySelectorAll('a.mk-a.mk-li')];
      return { n: as.length,
               named: as.every(a => a.getAttribute('aria-label')),
               open: as.length > 0 && as.every(a => a.tabIndex === 0 && !a.hasAttribute('aria-hidden')),
               quiet: as.length > 0 && as.every(a => a.tabIndex === -1 && a.getAttribute('aria-hidden') === 'true') };
    }"""
    with sync_api.sync_playwright() as p:
        try:
            browser = p.chromium.launch()
        except Exception as ex:  # noqa: BLE001 — Chromium is not installed here
            pytest.skip(f"Chromium 없음: {ex}")
        try:
            ctx = browser.new_context(viewport={"width": 390, "height": 844})
            ctx.route("**/*", serve)
            page = ctx.new_page()
            errors: list[str] = []
            page.on("pageerror", lambda e: errors.append(str(e)))
            page.goto("http://site.test/map/", wait_until="load")
            page.click("[data-segmap] [data-view=map]")
            page.wait_for_function("() => (window.GSMaps || []).some(m => m.data && m.data.all)", timeout=10000)
            page.wait_for_timeout(200)
            s = page.evaluate(state)
            assert s["n"] == 3 and s["named"] and s["open"], s
            page.focus(".map-side .kmap")
            page.keyboard.press("Tab")
            assert page.evaluate("() => document.activeElement.matches('.map-side a.mk-a')")
            page.click("[data-segmap] [data-view=list]")
            page.click("[data-segmap] [data-view=map]")
            page.wait_for_timeout(100)
            assert page.evaluate(state)["open"]
            assert errors == [], errors
            ctx.close()
            ctx = browser.new_context(viewport={"width": 1440, "height": 900})
            ctx.route("**/*", serve)
            page = ctx.new_page()
            page.goto("http://site.test/map/", wait_until="load")
            page.evaluate("() => document.querySelector('.map-side').scrollIntoView()")
            page.wait_for_function("() => (window.GSMaps || []).some(m => m.data && m.data.all)", timeout=10000)
            page.wait_for_timeout(200)
            assert page.evaluate(state)["quiet"]
        finally:
            browser.close()
