"""The scenario QA of 2026-10-19 in a real browser (Playwright + Chromium; skipped without them): the site search
(QA-06 the directory kept out of the first paint with a query, QA-23 fields matched one by one, QA-24 filler words,
QA-25 one dish in two spellings and the city's short names, QA-14 the rain words, QA-26 no company name suggested)
and a list map that cannot load (QA-42: the box keeps only its line, the list comes back). The Incheon configuration
with the tiny fixture (made-up places); the search index is replaced by made-up rows."""
import json
import mimetypes
import shutil
from pathlib import Path
from urllib.parse import unquote, urlsplit

import pytest

from pipeline.build import build

sync_api = pytest.importorskip("playwright.sync_api")

ROOT = Path(__file__).resolve().parent.parent
INCHEON = ROOT / "data" / "incheon"
TINY = Path(__file__).resolve().parent / "fixtures" / "incheon_tiny"
RECORDS = ("places.json", "events.json", "courses.json", "guides.json", "themes.json", "videos.json")
ROWS = [
    {"n": "[테스트] 상점 가", "a": "", "k": "shopping", "t": "쇼핑", "d": "관교동", "r": "도심·소래", "p": "/places/x1/"},
    {"n": "[테스트] 교동도 마을", "a": "", "k": "attraction", "t": "관광지", "d": "교동면", "r": "강화", "p": "/places/x2/"},
    {"n": "[테스트] 어린이 공원", "a": "", "k": "attraction", "t": "관광지", "d": "가상동", "r": "", "p": "/places/x3/"},
    {"n": "인천국제공항 제2여객터미널", "a": "", "k": "attraction", "t": "관광지", "d": "", "r": "영종·용유", "p": "/places/x4/"},
    {"n": "[테스트] 산짜장", "a": "", "k": "food", "t": "음식점", "d": "", "r": "", "p": "/places/x5/"},
    {"n": "[테스트] 실내관", "a": "", "k": "attraction", "t": "박물관·전시", "d": "", "r": "", "p": "/places/x6/"},
    {"n": "[테스트] 소품점 (주식회사소중한것)", "a": "", "k": "shopping", "t": "쇼핑", "d": "", "r": "", "p": "/places/x7/"},
    {"n": "[테스트] 인천가족공원 묘지", "a": "", "k": "attraction", "t": "관광지", "d": "", "r": "", "p": "/places/x8/"},
]


@pytest.fixture(scope="module")
def site(tmp_path_factory):
    tmp = tmp_path_factory.mktemp("qab")
    data = tmp / "data"
    data.mkdir()
    for f in INCHEON.glob("*.json"):
        if f.name not in RECORDS:
            shutil.copy(f, data / f.name)
    for f in TINY.glob("*.json"):
        shutil.copy(f, data / f.name)
    out = tmp / "out"
    build(data, out, "preview")
    return out


def _browser(p):
    try:
        return p.chromium.launch()
    except Exception as ex:  # noqa: BLE001 — Chromium is not installed here
        pytest.skip(f"Chromium 없음: {ex}")


def _serve(out, index="rows", delay=0):
    def serve(route):
        url = route.request.url
        if not url.startswith("http://site.test/"):
            return route.abort()
        path = unquote(urlsplit(url).path)
        if path == "/search/index.json":
            if index == "fail":
                return route.abort()
            if delay:
                import time
                time.sleep(delay)
            return route.fulfill(status=200, body=json.dumps(ROWS, ensure_ascii=False), content_type="application/json")
        f = out / path.strip("/")
        if f.is_dir():
            f = f / "index.html"
        if not f.is_file():
            return route.fulfill(status=404, body="")
        return route.fulfill(status=200, body=f.read_bytes(),
                             content_type=mimetypes.guess_type(str(f))[0] or "application/octet-stream")
    return serve


def _found(page, q):
    page.fill("#search-q, form[data-search] input[name=q]", q)
    page.wait_for_timeout(400)
    return page.eval_on_selector_all("[data-results] .res-nm", "els => els.map(e => e.textContent)")


def test_the_search_reads_its_words(site):
    with sync_api.sync_playwright() as p:
        browser = _browser(p)
        try:
            ctx = browser.new_context(viewport={"width": 390, "height": 844})
            ctx.route("**/*", _serve(site))
            page = ctx.new_page()
            errors = []
            page.on("pageerror", lambda e: errors.append(str(e)))
            page.goto("http://site.test/search/", wait_until="load")
            # QA-23: '관교동 도심·소래' is no '교동도'
            assert _found(page, "교동도") == ["[테스트] 교동도 마을"]
            # QA-24: 함께 and 근처 are filler words; QA-25: the city's short name (site.json city.search_aliases)
            assert "[테스트] 어린이 공원" in _found(page, "아이와 함께")
            assert "인천국제공항 제2여객터미널" in _found(page, "인천공항 근처")
            # QA-24: 아이랑 is no bare 가족 (a cemetery found by it)
            assert "[테스트] 인천가족공원 묘지" not in _found(page, "아이랑")
            # QA-25: one dish, two spellings
            assert "[테스트] 산짜장" in _found(page, "자장면")
            # QA-14: the rain words find the indoor types
            assert "[테스트] 실내관" in _found(page, "비 오는 날")
            # QA-26: a company name in brackets is never suggested; the list links include cafés and shops
            _found(page, "중식")
            assert "주식회사" not in (page.text_content("[data-results]") or "")
            links = page.eval_on_selector_all("[data-none-help] .res-lists a", "els => els.map(e => e.getAttribute('href'))")
            assert "/cafes/" in links and "/shopping/" in links
            assert errors == [], errors
            ctx.close()
        finally:
            browser.close()


SHIFTS = """window.__ls = 0; new PerformanceObserver(l => { for (const e of l.getEntries()) if (!e.hadRecentInput)
  window.__ls += e.value; }).observe({type: 'layout-shift', buffered: true});"""


def test_a_query_in_the_address_keeps_the_directory_out_of_the_first_paint(site):
    """QA-06: the whole 가나다 list painted first, then went (CLS 0.36)."""
    with sync_api.sync_playwright() as p:
        browser = _browser(p)
        try:
            ctx = browser.new_context(viewport={"width": 390, "height": 844})
            ctx.add_init_script(SHIFTS)
            ctx.route("**/*", _serve(site, delay=0.6))
            page = ctx.new_page()
            page.goto("http://site.test/search/?q=%EA%B5%90%EB%8F%99%EB%8F%84", wait_until="domcontentloaded")
            assert page.evaluate("document.documentElement.classList.contains('has-q')")
            assert not page.is_visible("[data-directory]")
            # the results to come push nothing in view: the footer starts below the first screen
            assert page.evaluate("document.querySelector('footer.foot').getBoundingClientRect().top >= innerHeight")
            page.wait_for_selector("[data-results] .res-nm")
            page.wait_for_timeout(300)
            assert not page.is_visible("[data-directory]") and page.evaluate("window.__ls") < 0.1
            # the directory on request
            page.fill("form[data-search] input[name=q]", "")
            page.wait_for_timeout(400)
            assert page.is_visible("[data-directory]")
            ctx.close()
            # the index does not load: the directory is the answer
            ctx = browser.new_context(viewport={"width": 390, "height": 844})
            ctx.route("**/*", _serve(site, index="fail"))
            page = ctx.new_page()
            page.goto("http://site.test/search/?q=%EA%B5%90%EB%8F%99%EB%8F%84", wait_until="load")
            page.wait_for_timeout(500)
            assert page.is_visible("[data-directory]")
            ctx.close()
        finally:
            browser.close()


def test_a_map_that_cannot_load_keeps_only_its_line_and_the_list_comes_back(site):
    """QA-42: a 400 px box with one line stayed (an address the provider's key is not registered for)."""
    with sync_api.sync_playwright() as p:
        browser = _browser(p)
        try:
            ctx = browser.new_context(viewport={"width": 390, "height": 844})
            ctx.route("**/*", _serve(site))   # the SDK's address is refused, as a 401 would leave it
            page = ctx.new_page()
            page.goto("http://site.test/places/?view=map", wait_until="load")
            page.wait_for_function("() => document.querySelector('.map.map-failed')", timeout=30000)
            h = page.evaluate("document.querySelector('.map.map-failed').getBoundingClientRect().height")
            assert h < 120, h
            assert "지도를 불러오지 못했습니다" in page.text_content(".map.map-failed")
            page.wait_for_timeout(200)
            assert page.is_visible("[data-ledger]")   # back to the list
            ctx.close()
        finally:
            browser.close()
