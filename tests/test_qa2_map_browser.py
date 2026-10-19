"""The scenario QA of 2026-10-19, second pass (docs/qa/2026-10-19_scenario_qa.md 7-4), maps and the launcher, in a real
browser (Playwright + Chromium; skipped without them) with the stand-in Kakao SDK (tests/js/kakao_stub.js — nothing
leaves the machine). The Incheon configuration with made-up places (no real record):

- QA-41: a 권역 whose places lie in two island groups a sea apart (10 near, 2 far — 백령도 is 15% of 옹진 섬, 160 km
  from 영흥도: robust(pts, 0.08) kept it and the phone opened at 64 km) is framed on its main body, on /map/ and on a
  list's 권역 filter alike; a '지도 밖 n곳도 보기' control frames them all.
- QA-40: a list map beside its list at 1440, its lower part below the window: the zoom buttons zoom on the middle of
  the part in the window (two zoom-ins on the box's middle left no marker in view), and once the page has scrolled the
  sticky box all in, its places are framed in the whole of it — not after the reader has moved the map.
- QA-63: a nearby group's '지도에서 보기' keeps out of the launcher's column below 1024px."""
import copy
import json
import mimetypes
import shutil
from pathlib import Path
from urllib.parse import quote, unquote, urlsplit

import pytest

from pipeline.build import build

sync_api = pytest.importorskip("playwright.sync_api")

ROOT = Path(__file__).resolve().parent.parent
INCHEON = ROOT / "data" / "incheon"
TINY = Path(__file__).resolve().parent / "fixtures" / "incheon_tiny"
RECORDS = ("places.json", "events.json", "courses.json", "guides.json", "themes.json", "videos.json")
STUB = (ROOT / "tests" / "js" / "kakao_stub.js").read_text("utf-8")
NEAR = [(37.20 + 0.012 * (i % 4), 126.28 + 0.015 * (i // 4)) for i in range(10)]   # within ~8 km: one island group
FAR = [(37.95, 124.70), (37.958, 124.712)]                                          # 160 km away


def _place(tpl, n, slug, name, kind, district, dong, ll):
    p = copy.deepcopy(tpl)
    p.update(id=f"test-q2-{n:03d}", slug=slug, name=name, kind=kind, district=district,
             category={"cafe": "카페·디저트", "attraction": "관광지"}[kind], geo={"lat": ll[0], "lng": ll[1], "source": "TourAPI"})
    p["facts"] = {"address": f"인천광역시 {district} 테스트로 {n} ({dong})", "usetime": "[테스트] 이용시간 값", "parking": "[테스트] 주차 값"}
    return p


@pytest.fixture(scope="module")
def site(tmp_path_factory):
    tmp = tmp_path_factory.mktemp("qa2map")
    data = tmp / "data"
    data.mkdir()
    for f in INCHEON.glob("*.json"):
        if f.name not in RECORDS:
            shutil.copy(f, data / f.name)
    for f in TINY.glob("*.json"):
        shutil.copy(f, data / f.name)
    tpl = json.loads((TINY / "places.json").read_text("utf-8"))[0]
    places, n = [], 0
    for i, ll in enumerate(NEAR):
        n += 1
        places.append(_place(tpl, n, f"test-q2-near-{i}", f"[테스트] 가까운 섬 {i}", "attraction", "옹진군", "영흥면", ll))
    for i, ll in enumerate(FAR):
        n += 1
        places.append(_place(tpl, n, f"test-q2-far-{i}", f"[테스트] 먼 섬 {i}", "attraction", "옹진군", "백령면", ll))
    for i in range(15):   # 송도·연수 cafés a few hundred metres apart, and a few elsewhere
        n += 1
        places.append(_place(tpl, n, f"test-q2-cafe-{i}", f"[테스트] 카페 {i}", "cafe", "연수구", "송도동",
                             (37.385 + 0.003 * (i % 5), 126.635 + 0.004 * (i // 5))))
    for i in range(4):
        n += 1
        places.append(_place(tpl, n, f"test-q2-gh-{i}", f"[테스트] 강화 카페 {i}", "cafe", "강화군", "강화읍", (37.74 + 0.01 * i, 126.48)))
    for i in range(3):
        n += 1
        places.append(_place(tpl, n, f"test-q2-park-{i}", f"[테스트] 송도 공원 {i}", "attraction", "연수구", "송도동",
                             (37.39 + 0.002 * i, 126.64)))
    # one café's nearby rows (as tools/tourapi_bulk.compute_nearby writes them): a sight and a café, each its group
    cafe = next(p for p in places if p["slug"] == "test-q2-cafe-7")
    cafe["nearby"] = [{"name": "[테스트] 송도 공원 0", "kind": "attraction", "type_label": "관광지", "distance_m": 310,
                       "internal_slug": "test-q2-park-0"},
                      {"name": "[테스트] 카페 8", "kind": "cafe", "type_label": "카페", "distance_m": 330, "internal_slug": "test-q2-cafe-8"}]
    cafe["nearby_source"] = {"provider": "한국관광공사 TourAPI 좌표", "providers": ["한국관광공사 TourAPI"], "radius_m": 2000,
                             "distance_basis": "직선거리", "checked_at": "2026-10-19"}
    (data / "places.json").write_text(json.dumps(places, ensure_ascii=False), "utf-8")
    out = tmp / "out"
    build(data, out, "preview")
    return out


def _serve(out):
    def serve(route):
        url = route.request.url
        if "dapi.kakao.com" in url:
            return route.fulfill(status=200, body=STUB, content_type="application/javascript")
        if not url.startswith("http://site.test/"):
            return route.abort()
        f = out / unquote(urlsplit(url).path).strip("/")
        if f.is_dir():
            f = f / "index.html"
        if not f.is_file():
            return route.fulfill(status=404, body="")
        return route.fulfill(status=200, body=f.read_bytes(), content_type=mimetypes.guess_type(str(f))[0] or "application/octet-stream")
    return serve


def _browser(p):
    try:
        return p.chromium.launch()
    except Exception as ex:  # noqa: BLE001 — Chromium is not installed here
        pytest.skip(f"Chromium 없음: {ex}")


def _ctx(browser, out, w, h=844):
    ctx = browser.new_context(viewport={"width": w, "height": h}, **({"device_scale_factor": 2, "has_touch": True, "is_mobile": True} if w < 1024 else {}))
    ctx.route("**/*", _serve(out))
    return ctx


def _ready(page, kind):
    page.wait_for_function("(k) => (window.GSMaps || []).some(m => m.data && m.data[k])", arg=kind, timeout=15000)
    page.wait_for_timeout(150)


# which of the given points the map shows in its box (the stand-in SDK's bounds), its level and the '지도 밖' control
SEEN = """([kind, pts]) => {
  const r = GSMaps.find(m => m.data && m.data[kind]), b = r.map.getBounds(), sw = b.getSouthWest(), ne = b.getNorthEast();
  const btn = r.el.querySelector('.map-rest');
  return { lv: r.map.getLevel(), btn: btn && !btn.hidden ? btn.textContent : null,
           in: pts.map(p => p[0] >= sw.getLat() && p[0] <= ne.getLat() && p[1] >= sw.getLng() && p[1] <= ne.getLng()) };
}"""


def _check_body(page, kind):
    s = page.evaluate(SEEN, [kind, NEAR + FAR])
    assert all(s["in"][:len(NEAR)]) and not any(s["in"][len(NEAR):]), s   # the near group framed, the far one left out
    assert s["btn"] == "지도 밖 2곳도 보기", s
    page.click(f".map .map-rest")
    page.wait_for_timeout(100)
    s2 = page.evaluate(SEEN, [kind, NEAR + FAR])
    assert all(s2["in"]) and s2["lv"] > s["lv"] and s2["btn"] is None, s2   # all of them, the control gone


def test_qa41_a_region_in_two_island_groups_opens_on_its_main_body(site):
    with sync_api.sync_playwright() as p:
        browser = _browser(p)
        try:
            ctx = _ctx(browser, site, 390)
            page = ctx.new_page()
            errors: list[str] = []
            page.on("pageerror", lambda e: errors.append(str(e)))
            # /map/ on a phone: the 권역 tab, then the 지도 view (the map is built then)
            page.goto("http://site.test/map/", wait_until="load")
            page.click('[data-region-tabs] a[data-region="옹진 섬"]')
            page.click("[data-segmap] [data-view=map]")
            _ready(page, "all")
            _check_body(page, "all")
            # the same 권역 as a list's filter, then its 지도 view
            page.goto("http://site.test/places/", wait_until="load")
            page.click("[data-f-more]")
            page.click('[data-f=region][data-v="옹진 섬"]')
            page.click("[data-filters] [data-view=map]")
            _ready(page, "list")
            _check_body(page, "list")
            # another 권역 and back: framed on the main body again (the control's 'all' lasts for one selection)
            page.click('[data-f=region][data-v="송도·연수"]')
            page.click('[data-f=region][data-v="옹진 섬"]')
            page.wait_for_timeout(100)
            s = page.evaluate(SEEN, ["list", NEAR + FAR])
            assert all(s["in"][:len(NEAR)]) and not any(s["in"][len(NEAR):]) and s["btn"] == "지도 밖 2곳도 보기", s
            # a selection with no group a sea away has no control
            page.click('[data-f=region][data-v="송도·연수"]')
            page.wait_for_timeout(100)
            assert page.evaluate(SEEN, ["list", []])["btn"] is None
            assert errors == [], errors
            ctx.close()
            # beside the list at 1440: the same frame
            ctx = _ctx(browser, site, 1440, 900)
            page = ctx.new_page()
            page.goto("http://site.test/places/?region=" + quote("옹진 섬"), wait_until="load")
            page.evaluate("() => document.querySelector('.list-map').scrollIntoView()")
            _ready(page, "list")
            s = page.evaluate(SEEN, ["list", NEAR + FAR])
            assert all(s["in"][:len(NEAR)]) and not any(s["in"][len(NEAR):]) and s["btn"] == "지도 밖 2곳도 보기", s
            ctx.close()
        finally:
            browser.close()


# the list map's box, the part of it in the window, its picked points' container pixels and their middle
BOX = """() => {
  const r = GSMaps.find(m => m.data && m.data.list), b = r.g.box.getBoundingClientRect();
  const top = Math.max(b.top, 0), bot = Math.min(b.bottom, innerHeight);
  const ps = (r.picked ? r.picked.lls : []).map(a => r.g.cp(a));
  const ys = ps.map(p => p.y);
  return { lv: r.map.getLevel(), c: r.map.getCenter().getLat() + ',' + r.map.getCenter().getLng(), h: b.height, top: b.top,
           seen: [top - b.top, bot - b.top], mid: (Math.min(...ys) + Math.max(...ys)) / 2,
           inSeen: ps.filter(p => p.x >= 0 && p.x <= b.width && p.y >= top - b.top && p.y <= bot - b.top).length, n: ps.length };
}"""


def test_qa40_a_list_map_half_below_the_window_zooms_on_what_is_seen_and_refits_when_scrolled_in(site):
    with sync_api.sync_playwright() as p:
        browser = _browser(p)
        try:
            ctx = _ctx(browser, site, 1440, 760)
            page = ctx.new_page()
            errors: list[str] = []
            page.on("pageerror", lambda e: errors.append(str(e)))
            page.goto("http://site.test/cafes/", wait_until="load")
            _ready(page, "list")
            page.click("[data-f-more]")
            page.click('[data-f=region][data-v="송도·연수"]')
            page.wait_for_timeout(150)
            s = page.evaluate(BOX)
            assert s["seen"][1] < s["h"] - 100, s            # the box's lower part is below the window
            assert s["inSeen"] == s["n"] == 15, s             # framed in the part in the window
            # two zoom-ins: on the middle of the part in the window, so the places there stay in view
            mid = page.evaluate("() => { const r = GSMaps.find(m => m.data.list), b = r.g.box.getBoundingClientRect(); "
                                "return r.g.ll({x: b.width / 2, y: (Math.max(b.top, 0) + Math.min(b.bottom, innerHeight)) / 2 - b.top}); }")
            page.click(".list-map .mz-in")
            page.click(".list-map .mz-in")
            page.wait_for_timeout(100)
            z = page.evaluate(BOX)
            at = page.evaluate("(a) => GSMaps.find(m => m.data.list).g.cp(a)", mid)
            assert z["lv"] == s["lv"] - 2 and abs(at["y"] - sum(z["seen"]) / 2) < 1 and z["inSeen"] > 0, (s, z, at)
            # a fresh page: the region picked, then the page scrolled until the sticky box is all in view — its places
            # are framed in the whole box (they sat in its top third)
            page.goto("http://site.test/cafes/?region=" + quote("송도·연수"), wait_until="load")
            _ready(page, "list")
            a = page.evaluate(BOX)
            assert a["seen"][1] < a["h"] - 100 and a["mid"] < a["h"] * 0.4, a
            page.evaluate("() => window.scrollBy(0, document.querySelector('.list-map').getBoundingClientRect().top)")
            page.wait_for_timeout(450)
            b = page.evaluate(BOX)
            assert b["seen"] == [0, b["h"]] or b["seen"][1] >= b["h"] - 1, b
            assert abs(b["mid"] - b["h"] / 2) < b["h"] * 0.1 and b["inSeen"] == 15, (a, b)
            # once the reader has zoomed, scrolling leaves the map as it is
            page.click(".list-map .mz-in")
            kept = page.evaluate(BOX)
            page.evaluate("() => window.scrollTo(0, 0)")
            page.wait_for_timeout(450)
            back = page.evaluate(BOX)
            assert (back["lv"], back["c"]) == (kept["lv"], kept["c"]), (kept, back)
            assert errors == [], errors
            ctx.close()
        finally:
            browser.close()


def test_qa63_the_nearby_map_link_keeps_out_of_the_launchers_column(site):
    with sync_api.sync_playwright() as p:
        browser = _browser(p)
        try:
            for w in (360, 390, 768):
                ctx = _ctx(browser, site, w)
                page = ctx.new_page()
                page.goto("http://site.test/places/" + quote("test-q2-cafe-7") + "/", wait_until="load")
                m = page.evaluate("""() => { const f = document.querySelector('.chat-fab').getBoundingClientRect();
                  return { fab: f.left, links: [...document.querySelectorAll('.nb-map')].map(a => a.getBoundingClientRect().right) }; }""")
                assert m["links"] and all(x <= m["fab"] for x in m["links"]), (w, m)
                ctx.close()
        finally:
            browser.close()
