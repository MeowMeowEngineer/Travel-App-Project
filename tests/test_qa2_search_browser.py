"""Scenario QA of 2026-10-19, second round, in a real browser (Playwright + Chromium; skipped without them): the
search page of a build of the Incheon configuration with the tiny fixture, its index replaced by made-up rows.

QA-70 '더 보기' shows 80 more and takes the focus to the first of them · QA-24 '전시' finds no 작전시장 · QA-06 /
QA-71 rows far down a long group are not drawn (so their names fetch no font file) while the first ones are, and the
page with a query fetches its index once · the breadcrumbs fetch no font file of their own."""
import json
import mimetypes
import re
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
FOOD = [{"n": f"[테스트] 가상식당 {i:03d}", "a": "", "k": "food", "t": "음식점", "d": "가상동", "r": "", "p": f"/places/f{i}/"}
        for i in range(1, 171)]
ROWS = FOOD + [
    {"n": "[테스트] 작전시장", "a": "", "k": "shopping", "t": "쇼핑", "d": "작전동", "r": "", "p": "/places/x1/"},
    {"n": "[테스트] 디지털전시체험관", "a": "", "k": "attraction", "t": "체험", "d": "", "r": "", "p": "/places/x2/"},
    {"n": "[테스트] 가상 박물관", "a": "", "k": "attraction", "t": "박물관·전시", "d": "", "r": "", "p": "/places/x3/"},
]


@pytest.fixture(scope="module")
def site(tmp_path_factory):
    tmp = tmp_path_factory.mktemp("qa2b")
    data = tmp / "data"
    data.mkdir()
    for f in INCHEON.glob("*.json"):
        if f.name not in RECORDS:
            shutil.copy(f, data / f.name)
    for f in TINY.glob("*.json"):
        shutil.copy(f, data / f.name)
    out = tmp / "out"
    build(data, out, "preview")
    # a long directory group of made-up names, as the 가나다 list of a city's 1,946 places starts
    html = (out / "search" / "index.html").read_text("utf-8")
    names = "".join(f'<li><a href="/places/d{i}/">[테스트] 가상 장소 {i:03d}</a><span>관광지</span></li>' for i in range(300))
    (out / "long").mkdir()
    (out / "long" / "index.html").write_text(
        re.sub(r'(<ul class="dir-list">)', r"\1" + names, html, count=1), "utf-8")
    return out


def _browser(p):
    try:
        return p.chromium.launch()
    except Exception as ex:  # noqa: BLE001 — Chromium is not installed here
        pytest.skip(f"Chromium 없음: {ex}")


def _serve(out, seen):
    def serve(route):
        url = route.request.url
        if not url.startswith("http://site.test/"):
            return route.abort()
        path = unquote(urlsplit(url).path)
        seen.append(path)
        if path == "/search/index.json":
            return route.fulfill(status=200, body=json.dumps(ROWS, ensure_ascii=False), content_type="application/json")
        f = out / path.strip("/")
        if f.is_dir():
            f = f / "index.html"
        if not f.is_file():
            return route.fulfill(status=404, body="")
        return route.fulfill(status=200, body=f.read_bytes(),
                             content_type=mimetypes.guess_type(str(f))[0] or "application/octet-stream")
    return serve


def test_more_rows_one_press_away_and_the_focus_on_the_first_of_them(site):
    with sync_api.sync_playwright() as p:
        browser = _browser(p)
        try:
            ctx = browser.new_context(viewport={"width": 390, "height": 844}, is_mobile=True, has_touch=True)
            seen = []
            ctx.route("**/*", _serve(site, seen))
            page = ctx.new_page()
            errors = []
            page.on("pageerror", lambda e: errors.append(str(e)))
            page.goto("http://site.test/search/?q=%EA%B0%80%EC%83%81%EC%8B%9D%EB%8B%B9", wait_until="load")
            page.wait_for_selector("[data-results] .res-nm")
            assert page.text_content(".f-result") == "‘가상식당’ 170곳 중 80곳"
            assert seen.count("/search/index.json") == 1   # the head's preload is the request search.js uses
            more = page.locator("button[data-more]")
            assert more.text_content() == "80곳 더 보기" and more.bounding_box()["height"] >= 44
            more.click()
            page.wait_for_function("document.querySelectorAll('[data-results] li').length === 160")
            assert page.evaluate("document.activeElement.closest('li').hasAttribute('data-new')")
            assert page.evaluate("document.activeElement.textContent").startswith("[테스트] 가상식당 081")
            assert page.text_content(".f-result") == "‘가상식당’ 170곳 중 160곳"
            page.click("button[data-more]")
            page.wait_for_function("document.querySelectorAll('[data-results] li').length === 170")
            assert page.locator("button[data-more]").count() == 0
            # QA-24: '전시' is no run inside 작전시장, and stays inside 디지털전시체험관
            page.fill("form[data-search] input[name=q]", "전시")
            page.wait_for_timeout(400)
            names = page.eval_on_selector_all("[data-results] .res-nm", "els => els.map(e => e.textContent)")
            assert names == ["[테스트] 디지털전시체험관", "[테스트] 가상 박물관"]
            assert errors == [], errors
            ctx.close()
        finally:
            browser.close()


def test_rows_far_down_a_long_group_wait_and_the_breadcrumbs_fetch_no_font_file_of_their_own(site):
    """QA-06, QA-71: the first group of the directory was drawn whole on the first screen."""
    fonts = (ROOT / "templates" / "assets" / "vendor" / "pretendard" / "pretendard.css").read_text("utf-8")
    face = next(f for f in re.findall(r"@font-face\s*\{[^}]*\}", fonts)
                if "font-weight:400" in f and "U+2010-2027" in f and "Pretendard-Regular" in f)
    punct = re.search(r"url\((Pretendard-Regular\.\d+\.woff2)\)", face).group(1)   # the file with '›' (U+203A)
    with sync_api.sync_playwright() as p:
        browser = _browser(p)
        try:
            for w, h in ((390, 844), (1440, 900)):
                ctx = browser.new_context(viewport={"width": w, "height": h})
                seen = []
                ctx.route("**/*", _serve(site, seen))
                page = ctx.new_page()
                page.goto("http://site.test/long/", wait_until="load")
                page.wait_for_timeout(300)
                # a skipped row keeps its box; what is inside it is not drawn (its name sets no glyph)
                shown = page.evaluate("""[...document.querySelectorAll('.dir-g:first-of-type .dir-list > li > a')]
                    .map(a => a.checkVisibility({contentVisibilityAuto: true}))""")
                assert all(shown[:8]) and not any(shown[200:]), (w, shown.index(False) if False in shown else None)
                # the grid keeps a row's names together: a drawn row's first and last name share a top
                tops = page.evaluate("[...document.querySelectorAll('.dir-list > li')].slice(0, 8).map(li => Math.round(li.getBoundingClientRect().top))")
                assert len(set(tops)) == (8 if w == 390 else 2), (w, tops)
                assert not any(s.endswith(punct) for s in seen), punct
                ctx.close()
        finally:
            browser.close()
