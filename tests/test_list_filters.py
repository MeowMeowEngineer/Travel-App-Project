"""List filters of /places/, /food/, /stays/ and /map/ (outside evaluation 2026-10-18): after '박물관·전시' cut the list to
11 places the 권역 and theme chips kept their whole-list counts, and '박물관·전시 + 섬과 바다' gave 0 places with only a
sentence telling to change the filters.

Now (site.js 'list filters', templates/_filters.html.j2):
  - faceted counts: each chip reads the places the list would show if it were chosen with the other groups' filters;
    one that would show none reads 0 and is drawn faint (.is-zero) but stays a working button in the tab order;
  - zero results: one '<값> 조건 해제' button per filter whose removal alone brings places back, then '전체 조건
    초기화', each restoring the list in one press, outside the ledger (the phone's 지도 view shows them too);
  - the map caption says how many shown places are not on the map ('지도에 없는 n곳은 목록에서');
  - /map/: the 권역 tabs and kind toggles count the same way, and nothing left for a 권역 and the kinds shown offers
    the 권역 ('고군산 조건 해제') and the hidden kinds ('관광지 숨김 해제') back; a count line in a role="status"
    element announces every change of the count, 0 among them;
  - the desktop band's count per 권역 (.band-data) follows the filters: each number is its group's shown places, an
    entry whose group shows none is faint and no link;
  - no chip changes width when its count changes (each live count keeps its build-time number's width, data-w), so
    the chips after it never move.
Without JS the bar, the panel and the caption's live counts are absent and the lists are complete.

The build: the sample data with eight attractions around three 권역 anchors (근대역사박물관 → 원도심, 은파호수공원 →
은파, 선유도 → 고군산): three museums (one without coordinates, one free), two parks (one free) and three islands (two
free), so '박물관·전시 + 섬과 바다' leaves nothing, and with '요금 무료' as well, taking off '요금 무료' alone still
leaves nothing (that filter gets no button). The browser tests (Playwright + Chromium, the build served through
page.route and the Kakao SDK stand-in tests/js/kakao_stub.js — nothing leaves the machine) run as a phone (390px,
a touch screen: the type chips are one row it swipes) and as a desktop with a mouse (1440px: the chips wrap)."""
import copy
import html as H
import json
import mimetypes
import re
import shutil
from pathlib import Path
from urllib.parse import unquote, urlsplit

import pytest

from pipeline import locales as LC
from pipeline.build import build, css_source

ROOT = Path(__file__).resolve().parent.parent
MUSEUM, ISLANDS = "박물관·전시", "islands-sea"

# (slug, name, category, theme, (lat, lng) or None, address, free)
ADDED = (
    ("근대역사박물관", "근대역사박물관", "박물관", "modern-history", (35.9895, 126.7110), "군산시 해망로 240(장미동)", True),
    ("test-art-hall", "근대미술관", "전시관", "modern-history", (35.9890, 126.7120), "군산시 해망로 230(장미동)", False),
    ("test-customs", "관세박물관", "박물관", "modern-history", None, "군산시 해망로 244-7(장미동)", False),
    ("은파호수공원", "은파 호수 산책로", "공원", "parks-nature", (35.9530, 126.7600), "군산시 은파순환길 9(나운동)", True),
    ("test-bridge", "물빛다리 공원", "공원", "parks-nature", (35.9540, 126.7610), "군산시 은파순환길 10(나운동)", False),
    ("선유도", "선유도", "섬", ISLANDS, (35.8110, 126.4120), "군산시 옥도면 선유북길 40", True),
    ("test-jangja", "장자도", "섬", ISLANDS, (35.8050, 126.4050), "군산시 옥도면 장자도길 1", True),
    ("test-daejang", "대장도", "섬", ISLANDS, (35.8030, 126.4010), "군산시 옥도면 대장도길 2", False),
)


def filters_build(tmp_path):
    data = tmp_path / "data"
    shutil.copytree(ROOT / "data" / "sample", data)
    site = json.loads((data / "site.json").read_text("utf-8"))
    site["kakao_js_key"] = "test-key-123"
    (data / "site.json").write_text(json.dumps(site, ensure_ascii=False), "utf-8")
    places = json.loads((data / "places.json").read_text("utf-8"))
    base = next(p for p in places if p["id"] == "sample-0003")
    for i, (slug, name, cat, theme, geo, addr, free) in enumerate(ADDED):
        p = copy.deepcopy(base)
        p.update(id=f"test-{i:02d}", slug=slug, name=name, category=cat, themes=[theme])
        p["facts"] = {"address": addr, **({"usefee": "무료"} if free else {})}
        if geo:
            p["geo"] = {"lat": geo[0], "lng": geo[1], "source": "TourAPI"}
        places.append(p)
    (data / "places.json").write_text(json.dumps(places, ensure_ascii=False), "utf-8")
    out = tmp_path / "out"
    build(data, out, "preview")
    return out


@pytest.fixture(scope="module")
def built(tmp_path_factory):
    return filters_build(tmp_path_factory.mktemp("filters"))


def rows(h: str) -> list[str]:
    return re.findall(r'<li class="rec"[^>]*>', h)


# ------------------------------------------------------------------ the built pages (no browser)
def test_the_zero_panel_and_the_caption_are_built_hidden_and_in_the_pages_words(built):
    """The zero-result panel sits between the bar and the ledger, hidden, with the sentence, the '{v} 조건 해제'
    template and the reset; the map caption names the list's places without coordinates (rows without data-geo)."""
    h = (built / "places" / "index.html").read_text("utf-8")
    w = LC.LIST_WORDS["ko"]
    bar_end = h.index('<div class="ledger" data-ledger>')
    # the sentence in its span, after the mascot with an empty basket when the site has one (decorative, alt="")
    panel = re.search(r'<p class="empty" data-empty hidden>(?:<picture class="empty-pic">.*?alt="".*?</picture>)?'
                      r'<span>([^<]*)</span></p>\s*<div class="f-undo" data-f-undo data-one="([^"]*)" '
                      r'hidden><button type="button" data-f-reset>([^<]*)</button></div>', h)
    assert panel and h.index('data-filters hidden') < panel.start() < bar_end
    assert panel.groups() == (w["empty"], "{v} 조건 해제", "전체 조건 초기화")
    rs = rows(h)
    n_geo = sum('data-geo="1"' in r for r in rs)
    assert (n_geo, len(rs) - n_geo) == (7, 5)
    assert ('<figcaption><span data-geo-cap>좌표가 있는 7곳만 표시</span><span data-geo-off data-tpl=" · 지도에 없는 {n}곳은 목록에서">'
            ' · 지도에 없는 5곳은 목록에서</span> · 지도: 카카오맵</figcaption>') in h
    # every row with coordinates is a point of the list map, so the caption's two numbers add up to the list
    pts = json.loads(H.unescape(re.search(r"data-points='([^']*)'", h).group(1)))["list"]
    assert len(pts) == n_geo
    # the chips start with the whole list's counts (site.js facets them as soon as it runs)
    assert f'data-v="{MUSEUM}" aria-pressed="false">{MUSEUM} <span class="tn">3</span>' in h
    assert 'data-v="islands-sea" aria-pressed="false">섬과 바다 <span class="tn">3</span>' in h


def test_a_list_whose_places_all_have_coordinates_names_none_off_the_map():
    from pipeline.build import make_env
    from pipeline.present import filter_vm
    F = filter_vm(4, [], [], [], ("free", "요금 무료", 0), 4, LC.LIST_WORDS["ko"], {"other": "관광지 {n}곳"})
    assert F["n_off"] == 0
    fb = make_env().get_template("_filters.html.j2").module
    assert str(fb.off_map(0, LC.LIST_WORDS["ko"])).strip() == ""
    assert str(fb.off_map(23, LC.LIST_WORDS["en"])) == \
        '<span data-geo-off data-tpl=" · Not on the map: {n} (see the list)"> · Not on the map: 23 (see the list)</span>'


def test_the_count_line_carries_its_widest_filtered_forms(built):
    """The room the desktop keeps for the count line: after it, one invisible copy per plural form of the filtered
    line with the whole count for both numbers (a shown count has no more digits; the digits are tabular)."""
    from pipeline.present import filter_vm
    h = (built / "places" / "index.html").read_text("utf-8")
    assert re.search(r'<p class="f-result" aria-live="polite"><span data-result [^>]*>관광지 12곳</span>'
                     r'<span class="f-w" aria-hidden="true">관광지 12곳 \(전체 12곳 중\)</span></p>', h)
    ru = {"one": "{n} достопримечательность", "few": "{n} достопримечательности", "many": "{n} достопримечательностей"}
    F = filter_vm(160, [], [], [], ("free", "", 0), 0, LC.LIST_WORDS["ru"], ru)
    assert F["widest"] == [f.replace("{n}", "160") + " (из 160)" for f in ru.values()]
    en = filter_vm(9, [], [], [], ("free", "", 0), 0, LC.LIST_WORDS["en"], {"one": "{n} stays", "other": "{n} stays"})
    assert en["widest"] == ["9 stays (of 9)"]
    css = " ".join(css_source().split())
    # the room is kept on a desktop, and from 761px with a mouse, whose chips wrap beside the tools there too (review
    # 2026-10-18, fourth round)
    assert (".f-w { display: none; } @media (min-width: 1024px), (min-width: 761px) and (hover: hover) and (pointer: fine) { "
            ".f-tools .f-result { font-variant-numeric: tabular-nums; } "
            ".f-w { display: block; height: 0; overflow: hidden; visibility: hidden; } "
            ".f-tools .f-badge[hidden] { display: inline-flex !important; visibility: hidden; } }") in css


def test_the_map_page_counts_its_kinds_and_names_the_places_off_the_map(built):
    h = (built / "map" / "index.html").read_text("utf-8")
    kinds = re.findall(r'<button type="button" data-kind="(\w+)" aria-pressed="true"><i [^>]*></i>([^<]*) <span class="tn">(\d+)</span></button>', h)
    rows_ = re.findall(r'<li data-kind-row="(\w+)"( data-pt="[^"]*")?>', h)
    assert [(k, int(n)) for k, _, n in kinds] == [(k, sum(1 for x, _ in rows_ if x == k)) for k in ("attraction", "stay", "food")]
    n_geo = sum(1 for _, pt in rows_ if pt)
    assert f'<figcaption><span data-geo-cap>좌표가 있는 {n_geo}곳</span><span data-geo-off data-tpl=" · 지도에 없는 {{n}}곳은 목록에서"> · 지도에 없는 {len(rows_) - n_geo}곳은 목록에서</span>' in h
    assert '<p class="empty" data-map-empty hidden>' in h
    assert re.search(r'<div class="f-undo" data-map-undo data-one="\{v\} 조건 해제" data-kind-one="\{v\} 숨김 해제" hidden>'
                     r'<button type="button" data-map-reset>전체 조건 초기화</button></div>', h)
    # the count line: a status region from the first paint (JS-only furniture), the whole page's count
    assert re.search(r'<div class="f-tools map-tools js-only">\s*<p class="f-result" role="status"><span data-map-result '
                     r'data-tpl="장소 \{n\}곳" data-of=" \(전체 \{m\}곳 중\)">장소 (\d+)곳</span></p>', h).group(1) == str(len(rows_))
    # the 권역 and 동 headings carry the count site.js keeps to the shown rows
    assert h.count('<span class="count tn" data-group-n>') == h.count('<section class="region')
    assert h.count('<span class="tn" data-group-n>') == h.count('<section class="dong')   # 'dong' or 'dong cvk' (QA-28)


def test_the_faint_chip_keeps_its_contrast_and_the_mouse_rule_stays():
    """A 0 chip is drawn faint but stays a working control, so its text keeps 4.5:1 (ink-3); the undo buttons are 44px
    pills; the chips' wrapping for a fine pointer (operator 2026-10-18) is untouched."""
    css = " ".join(css_source().split())   # the partials as written
    assert (".f-row button.is-zero, .f-row > a.is-zero { background: transparent; box-shadow: none; border: 1px dashed "
            "var(--ink-3); padding: 0 15px; color: var(--ink-3); }") in css
    assert "--ink-3: #5F6878" in css   # 5.62:1 on white, 5.22:1 on the panel's bg-2
    assert re.search(r"\.f-undo button \{[^}]*min-height: 44px", css)
    rule = css[css.index("@media (hover: hover) and (pointer: fine)"):]
    rule = rule[:rule.index("} }") + 3]
    assert ".f-row { flex-wrap: wrap; overflow-x: visible; }" in rule
    assert ".f-top .f-row { -webkit-mask-image: none; mask-image: none; padding-right: 0; margin-right: 0; }" in rule


# ------------------------------------------------------------------ in a browser
def _serve(out: Path):
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
    return serve


@pytest.fixture(scope="module")
def browser():
    sync_api = pytest.importorskip("playwright.sync_api")
    with sync_api.sync_playwright() as p:
        try:
            b = p.chromium.launch()
        except Exception as ex:  # noqa: BLE001 — Chromium is not installed here
            pytest.skip(f"Chromium 없음: {ex}")
        yield b
        b.close()


# a phone (a coarse pointer, no hover: the chips are one row it swipes) and a desktop with a mouse (the chips wrap)
PHONE = {"viewport": {"width": 390, "height": 844}, "is_mobile": True, "has_touch": True}
DESKTOP = {"viewport": {"width": 1440, "height": 900}}
VIEWPORTS = [pytest.param(PHONE, id="390"), pytest.param(DESKTOP, id="1440")]

# every chip of the bar: key, value, its count, faint or not, pressed or not, and whether it is a plain working button
CHIPS = """() => [...document.querySelectorAll('[data-filters] [data-f]')].map(c => {
  const host = c.type === 'checkbox' ? c.closest('label') : c;
  return { k: c.getAttribute('data-f'), v: c.type === 'checkbox' ? 'check' : c.getAttribute('data-v'),
           n: host.querySelector('.tn') ? +host.querySelector('.tn').textContent : null, zero: host.classList.contains('is-zero'),
           on: c.type === 'checkbox' ? c.checked : c.getAttribute('aria-pressed') === 'true',
           live: !c.disabled && !c.hasAttribute('aria-disabled') && c.tabIndex === 0 };
})"""
SHOWN = "() => document.querySelectorAll('.rec:not([hidden])').length"
UNDO = "() => { const u = document.querySelector('[data-f-undo]'); return u.hidden ? null : [...u.querySelectorAll('button')].map(b => b.textContent); }"


def _page(browser, out, dev, **kw):
    ctx = browser.new_context(**dev, **kw)
    ctx.route("**/*", _serve(out))
    page = ctx.new_page()
    errors: list[str] = []
    page.on("pageerror", lambda e: errors.append(str(e)))
    return ctx, page, errors


def _open_panel(page):
    if page.get_attribute("[data-f-more]", "aria-expanded") != "true":
        page.click("[data-f-more]")


@pytest.mark.parametrize("dev", VIEWPORTS)
def test_in_a_browser_every_chip_counts_what_choosing_it_would_show(built, browser, dev):
    """Faceted counts: with '박물관·전시' on, the 권역 and theme chips and the check box count the museums only — and
    for every chip, choosing it shows exactly the number it read (the definition, checked by pressing each one). The
    type chips are not cut by their own group. A 0 chip is faint (.is-zero) yet a working button in the tab order; a
    chip that is on is never faint."""
    ctx, page, errors = _page(browser, built, dev)
    try:
        page.goto("http://site.test/places/", wait_until="load")
        whole = {(c["k"], c["v"]): c["n"] for c in page.evaluate(CHIPS)}
        page.click(f'[data-f=type][data-v="{MUSEUM}"]')
        assert page.evaluate(SHOWN) == 3
        chips = {(c["k"], c["v"]): c for c in page.evaluate(CHIPS)}
        got = {k: c["n"] for k, c in chips.items() if c["n"] is not None}
        assert got[("region", "원도심")] == 3 and got[("region", "은파")] == 0 and got[("region", "고군산")] == 0
        assert got[("theme", "modern-history")] == 3 and got[("theme", "parks-nature")] == 0 and got[("theme", ISLANDS)] == 0
        assert got[("check", "check")] == 1
        # the type chips count without their own group's choice: the whole list's numbers stay
        assert all(got[k] == whole[k] for k in got if k[0] == "type")
        for k, c in chips.items():
            assert c["zero"] == (c["n"] == 0 and not c["on"]), (k, c)
            assert c["live"], (k, c)   # never disabled, never aria-disabled, in the tab order
        # pressing each chip of the other groups shows exactly its number (then back to the museums alone)
        for (k, v), c in chips.items():
            if k == "type" or c["n"] is None:
                continue
            _open_panel(page)
            if k == "check":
                page.check("input[data-f=check]")
            else:
                page.click(f'[data-f="{k}"][data-v="{v}"]')
            assert page.evaluate(SHOWN) == c["n"], (k, v)
            page.goto(f"http://site.test/places/?type={MUSEUM}", wait_until="load")
        # the zero chip can be reached with the keyboard and chosen
        _open_panel(page)
        page.focus(f'[data-f=theme][data-v="{ISLANDS}"]')
        page.keyboard.press("Enter")
        assert page.evaluate(SHOWN) == 0 and page.evaluate(UNDO)
        assert errors == [], errors
    finally:
        ctx.close()


@pytest.mark.parametrize("dev", VIEWPORTS)
def test_in_a_browser_zero_results_offer_one_press_ways_back(built, browser, dev):
    """'박물관·전시 + 섬과 바다' leaves nothing: the panel offers '박물관·전시 조건 해제', '섬과 바다 조건 해제' and '전체
    조건 초기화' — 44px, keyboard-operable, each bringing places back in one press (the focus goes to the count line).
    With '요금 무료' as well, removing '요금 무료' alone would still leave nothing: it gets no button. The phone's 지도
    view (the ledger hidden) shows the panel too."""
    ctx, page, errors = _page(browser, built, dev)
    q = f"?type={MUSEUM}&theme={ISLANDS}"
    try:
        page.goto("http://site.test/places/" + q, wait_until="load")
        assert page.evaluate(SHOWN) == 0
        assert page.evaluate(UNDO) == [f"{MUSEUM} 조건 해제", "섬과 바다 조건 해제", "전체 조건 초기화"]
        assert page.is_visible("[data-empty]") and "조건에 맞는 곳이 없습니다" in page.inner_text("[data-empty]")
        for b in page.query_selector_all("[data-f-undo] button"):
            box = b.bounding_box()
            assert box["height"] >= 44 and box["width"] >= 44, box
        # the keyboard: Tab from the sentence reaches the first button, Enter presses it
        page.focus("[data-f-undo] button")
        page.keyboard.press("Enter")
        assert page.evaluate(SHOWN) == 3 and page.evaluate(UNDO) is None
        assert page.evaluate("location.search") == f"?theme={ISLANDS}"
        assert page.evaluate("document.activeElement.matches('.f-result')")
        assert "3곳" in page.inner_text("[data-result]")
        for i, (label, left) in enumerate(((f"{MUSEUM} 조건 해제", 3), ("섬과 바다 조건 해제", 3), ("전체 조건 초기화", 12))):
            page.goto("http://site.test/places/" + q, wait_until="load")
            page.click(f"[data-f-undo] button >> nth={i}")
            assert page.evaluate(SHOWN) == left, label
            assert not page.is_visible("[data-empty]") and page.evaluate(UNDO) is None, label
        # three filters, one of which alone would not bring anything back
        page.goto("http://site.test/places/" + q + "&check=1", wait_until="load")
        assert page.evaluate(UNDO) == [f"{MUSEUM} 조건 해제", "섬과 바다 조건 해제", "전체 조건 초기화"]
        for i in range(3):
            page.goto("http://site.test/places/" + q + "&check=1", wait_until="load")
            page.click(f"[data-f-undo] button >> nth={i}")
            assert page.evaluate(SHOWN) > 0, i
        # the 지도 view: the ledger is hidden below 1024px, the panel is not
        page.goto("http://site.test/places/" + q + "&view=map", wait_until="load")
        assert page.is_visible("[data-f-undo] [data-f-reset]") and page.is_visible("[data-empty]")
        page.click("[data-f-reset]")
        assert page.evaluate(SHOWN) == 12 and page.evaluate("location.search") == "?view=map"
        assert errors == [], errors
    finally:
        ctx.close()


@pytest.mark.parametrize("dev", VIEWPORTS)
def test_in_a_browser_the_map_caption_names_the_places_off_the_map(built, browser, dev):
    """'좌표가 있는 n곳만 표시 · 지도에 없는 m곳은 목록에서' under the list map follows the filter, and the part about the
    places off the map leaves when every shown place is on it."""
    ctx, page, errors = _page(browser, built, dev)
    cap = """() => { const o = document.querySelector('.list-map [data-geo-off]');
      return [document.querySelector('.list-map [data-geo-cap]').textContent, o.hidden ? null : o.textContent]; }"""
    try:
        page.goto("http://site.test/places/", wait_until="load")
        assert page.evaluate(cap) == ["좌표가 있는 7곳만 표시", " · 지도에 없는 5곳은 목록에서"]
        page.goto(f"http://site.test/places/?type={MUSEUM}", wait_until="load")
        assert page.evaluate(cap) == ["좌표가 있는 2곳만 표시", " · 지도에 없는 1곳은 목록에서"]
        page.goto(f"http://site.test/places/?theme={ISLANDS}&view=map", wait_until="load")
        assert page.evaluate(cap) == ["좌표가 있는 3곳만 표시", None]
        assert page.is_visible(".list-map figcaption")
        assert errors == [], errors
    finally:
        ctx.close()


@pytest.mark.parametrize("dev", VIEWPORTS)
def test_in_a_browser_the_map_page_counts_and_recovers_the_same_way(built, browser, dev):
    """/map/: with 고군산 chosen the kind toggles count its places (관광지 3, 숙소 0, 음식점 0); hiding 관광지 leaves
    nothing — the 권역 tabs then count the shown kinds (원도심 0, faint) and the panel offers '고군산 조건 해제',
    '관광지 숨김 해제' (the focus goes back to that toggle) and '전체 조건 초기화'. The '지도 n' count, the caption and
    the count line follow — the line is a status region there from the start, so each change, 0 among them, is
    announced."""
    ctx, page, errors = _page(browser, built, dev)
    state = """() => ({
      tabs: Object.fromEntries([...document.querySelectorAll('a[data-region]')].map(a => [a.getAttribute('data-region') || '전체', [+a.querySelector('.tn').textContent, a.classList.contains('is-zero')]])),
      kinds: Object.fromEntries([...document.querySelectorAll('button[data-kind]')].map(b => [b.getAttribute('data-kind'), [+b.querySelector('.tn').textContent, b.getAttribute('aria-pressed') === 'true', b.classList.contains('is-zero')]])),
      shown: document.querySelectorAll('[data-kind-row]:not([hidden])').length,
      undo: document.querySelector('[data-map-undo]').hidden ? null : [...document.querySelectorAll('[data-map-undo] button')].map(b => b.textContent),
      empty: !document.querySelector('[data-map-empty]').hidden,
      map: document.querySelector('[data-segmap] [data-view=map] .tn').textContent,
      cap: document.querySelector('.map-side [data-geo-cap]').textContent,
      off: document.querySelector('.map-side [data-geo-off]').hidden ? null : document.querySelector('.map-side [data-geo-off]').textContent,
      status: [...document.querySelectorAll('[role=status]')].filter(e => e.closest('.map-dir')).map(e => e.textContent) })"""
    try:
        page.goto("http://site.test/map/", wait_until="load")
        s0 = page.evaluate(state)
        assert s0["undo"] is None and not s0["empty"] and s0["off"] and s0["map"] == "7" and s0["cap"] == "좌표가 있는 7곳"
        n_all = s0["shown"]
        assert s0["status"] == [f"장소 {n_all}곳"] and page.is_visible(".map-dir [role=status]")
        # the status region is there (and in the accessibility tree) before anything changes in it
        assert page.get_by_role("status").filter(has_text=f"장소 {n_all}곳").count() == 1
        page.click("a[data-region='고군산']")
        s = page.evaluate(state)
        assert s["kinds"] == {"attraction": [3, True, False], "stay": [0, True, False], "food": [0, True, False]}
        assert s["shown"] == 3 and s["map"] == "3" and s["cap"] == "좌표가 있는 3곳" and s["off"] is None
        assert s["status"] == [f"장소 3곳 (전체 {n_all}곳 중)"]
        page.click("button[data-kind='attraction']")
        s = page.evaluate(state)
        assert s["shown"] == 0 and s["empty"] and s["map"] == "0"
        assert s["status"] == [f"장소 0곳 (전체 {n_all}곳 중)"]   # zero results announced
        assert s["undo"] == ["고군산 조건 해제", "관광지 숨김 해제", "전체 조건 초기화"]
        assert s["tabs"]["원도심"] == [0, True] and s["tabs"]["고군산"] == [0, False]   # the chosen tab is never faint
        assert s["tabs"]["전체"][0] == s0["kinds"]["stay"][0] + s0["kinds"]["food"][0]
        assert s["kinds"]["attraction"] == [3, False, False]
        for b in page.query_selector_all("[data-map-undo] button"):
            assert b.bounding_box()["height"] >= 44
        page.focus("[data-map-undo] button >> nth=1")
        page.keyboard.press("Enter")
        s = page.evaluate(state)
        assert s["shown"] == 3 and s["undo"] is None and not s["empty"]
        assert page.evaluate("document.activeElement.getAttribute('data-kind')") == "attraction"
        page.click("button[data-kind='attraction']")
        page.click("[data-map-undo] button >> nth=0")   # 고군산 조건 해제: every 권역, the kinds as they are
        s = page.evaluate(state)
        assert s["shown"] == s0["kinds"]["stay"][0] + s0["kinds"]["food"][0] and s["kinds"]["attraction"][1] is False
        assert page.evaluate("document.activeElement.getAttribute('data-region')") == ""
        page.click("button[data-kind='stay']")
        page.click("button[data-kind='food']")
        assert page.evaluate(state)["undo"] == ["관광지 숨김 해제", "숙소 숨김 해제", "음식점 숨김 해제", "전체 조건 초기화"]
        page.click("[data-map-reset]")
        s = page.evaluate(state)
        assert s["shown"] == s0["shown"] and all(v[1] for v in s["kinds"].values()) and s["map"] == "7"
        assert s["status"] == [f"장소 {n_all}곳"]
        assert errors == [], errors
    finally:
        ctx.close()


@pytest.mark.parametrize("dev", VIEWPORTS)
def test_in_a_browser_a_phone_swipes_one_row_and_a_mouse_wraps(built, browser, dev):
    """The phone (a touch screen, no hover) keeps the type chips in one row it swipes, the faint 0 chips in it and
    working when tapped; a desktop with a mouse wraps them, every one in view (operator 2026-10-18)."""
    ctx, page, errors = _page(browser, built, dev)
    phone = dev is PHONE
    row = """() => { const r = document.querySelector('.f-top .f-row'), cs = [...r.querySelectorAll('button')];
      return { coarse: matchMedia('(pointer: coarse)').matches, fine: matchMedia('(hover: hover) and (pointer: fine)').matches,
               wrap: getComputedStyle(r).flexWrap, overflow: getComputedStyle(r).overflowX, sw: r.scrollWidth, cw: r.clientWidth,
               tops: [...new Set(cs.map(c => Math.round(c.getBoundingClientRect().top)))].length,
               zero: cs.filter(c => c.classList.contains('is-zero')).map(c => c.getAttribute('data-v')) }; }"""
    try:
        page.goto(f"http://site.test/places/?theme={ISLANDS}", wait_until="load")
        r = page.evaluate(row)
        assert r["zero"], r   # with 섬과 바다 some type chips would show nothing
        if phone:
            assert r["coarse"] and not r["fine"], r
            assert (r["wrap"], r["overflow"], r["tops"]) == ("nowrap", "auto", 1) and r["sw"] > r["cw"], r
            # the faint chip at the end of the row is reached by swiping and works when tapped
            page.tap(f'.f-top [data-f=type][data-v="{r["zero"][-1]}"]')
            assert page.evaluate(SHOWN) == 0 and page.evaluate(UNDO)
        else:
            assert r["fine"] and not r["coarse"], r
            assert r["wrap"] == "wrap" and r["sw"] <= r["cw"], r
            page.click(f'.f-top [data-f=type][data-v="{r["zero"][-1]}"]')
            assert page.evaluate(SHOWN) == 0 and page.evaluate(UNDO)
        assert errors == [], errors
    finally:
        ctx.close()


# the chips and counts whose width must hold: the list's chips (and the check box label), its '지도 n', the band per
# 권역; on /map/ the 권역 tabs, the kind toggles and '지도 n' — each with its pressed state and its number
WIDTHS = """() => [...document.querySelectorAll('[data-filters] [data-f], [data-filters] [data-view=map], .band-data a, a[data-region], button[data-kind], [data-segmap] [data-view=map]')]
  .map(c => c.type === 'checkbox' ? c.closest('label') : c)
  .filter(c => c.getBoundingClientRect().width > 0)
  .map(c => ({ key: [c.querySelector('input') || c].map(e => ['data-f', 'data-v', 'data-view', 'data-region', 'data-kind'].map(a => e.getAttribute(a)).join('|'))[0]
                    + (c.closest('.band-data') ? '|band ' + c.querySelector('span').textContent : ''),
               w: c.getBoundingClientRect().width, on: c.getAttribute('aria-pressed') || c.getAttribute('aria-current') || String(!!(c.querySelector('input') || {}).checked),
               n: (c.querySelector('.tn, .num') || {}).textContent }))"""
# layout shifts (those of the load too: buffered), as the rows they moved: a source inside the type chips' row
# ('top'), the kind toggles ('kinds'), another chip row or the band ('chips'), else ''
SHIFTS = """() => { window.__ls = []; new PerformanceObserver(l => { for (const e of l.getEntries()) window.__ls.push(...e.sources.map(s => {
    const el = s.node && (s.node.nodeType === 1 ? s.node : s.node.parentElement);
    return !el ? '' : el.closest('.f-top .f-row') ? 'top' : el.closest('[data-kinds]') ? 'kinds' : el.closest('.f-row, .band-data') ? 'chips' : ''; })); })
  .observe({ type: 'layout-shift', buffered: true }); }"""


def _same_widths(before, after):
    """Every chip whose pressed state stayed keeps its width to the hundredth of a pixel; some numbers did change."""
    assert [b["key"] for b in before] == [a["key"] for a in after]
    held = [(b, a) for b, a in zip(before, after) if b["on"] == a["on"]]
    assert any(b["n"] != a["n"] for b, a in held), "no count changed: the case proves nothing"
    moved = [(b["key"], b["n"], a["n"], b["w"], a["w"]) for b, a in held if abs(b["w"] - a["w"]) > 0.01]
    assert not moved, moved


@pytest.mark.parametrize("dev", VIEWPORTS)
def test_in_a_browser_no_chip_changes_width_when_its_count_changes(built, browser, dev):
    """CLS: each live count keeps the width of its build-time number (the largest it can read, data-w), so a chip whose
    number falls (전체 12 → 3) or rises keeps its width and the chips after it do not move — on the list (the type row
    while a 권역 chip is pressed in the panel, the band) and on /map/ (the kind toggles while a 권역 tab is chosen). A
    filtered URL loads without a chip moving. The copy that holds the width is no text for a screen reader: the
    chip's name is its label and its number."""
    ctx, page, errors = _page(browser, built, dev)
    frames = "() => new Promise(r => requestAnimationFrame(() => requestAnimationFrame(() => setTimeout(r, 50))))"
    try:
        page.goto(f"http://site.test/places/?region=고군산", wait_until="load")
        page.evaluate(SHIFTS)
        page.evaluate(frames)
        assert [x for x in page.evaluate("window.__ls") if x] == []   # the load of a filtered URL: no chip moved
        page.goto("http://site.test/places/", wait_until="load")
        assert page.get_attribute('[data-f=type][data-v=""] .tn', "data-w") == "12"
        _open_panel(page)
        before = page.evaluate(WIDTHS)
        page.evaluate(SHIFTS)
        page.evaluate(frames)
        page.click('[data-f=region][data-v="고군산"]')
        page.evaluate(frames)
        after = page.evaluate(WIDTHS)
        _same_widths(before, after)
        assert "top" not in page.evaluate("window.__ls")
        type_all = next(a for a in after if a["key"] == "type||||")
        assert type_all["n"] == "3"
        assert page.get_by_role("button", name="전체 3", exact=True).count() == 1
        page.goto("http://site.test/map/", wait_until="load")
        before = page.evaluate(WIDTHS)
        page.evaluate(SHIFTS)
        page.evaluate(frames)
        page.click("a[data-region='고군산']")
        page.evaluate(frames)
        after = page.evaluate(WIDTHS)
        _same_widths(before, after)
        assert "kinds" not in page.evaluate("window.__ls")
        assert page.get_by_role("button", name="관광지 3", exact=True).count() == 1
        assert errors == [], errors
    finally:
        ctx.close()


# the type chips' row on a desktop: the row's box, each chip's place (in the page: a press in the panel may scroll it),
# the tools beside it, the count line and the badge
TYPE_ROW = """() => { const box = e => { const r = e.getBoundingClientRect(); return [r.left + scrollX, r.top + scrollY, r.width, r.height]; };
  const b = document.querySelector('[data-f-badge]');
  return { row: box(document.querySelector('.f-top .f-row')), tools: box(document.querySelector('.f-top .f-tools')),
           chips: [...document.querySelectorAll('.f-top .f-row button')].map(c => [c.getAttribute('data-v'), ...box(c)]),
           result: document.querySelector('[data-result]').textContent, badge: b.hidden ? null : b.textContent }; }"""


@pytest.mark.parametrize("dev", [pytest.param(DESKTOP, id="1440"), pytest.param({"viewport": {"width": 900, "height": 900}}, id="900")])
def test_in_a_browser_on_a_desktop_a_filter_moves_no_type_chip(built, browser, dev):
    """Desktop (1440, and 900 — review 2026-10-18, fourth round: 761–1023px kept no room —, a mouse: the type chips
    wrap beside the tools): the count line and the 필터 button beside the type chips keep their width when a filter is
    applied — the line grows ('관광지 12곳' → '관광지 3곳 (전체 12곳 중)') and the 필터 button shows its badge ('1')
    inside the room the build reserved for them — so the type row keeps its width and every chip its place to the
    hundredth of a pixel: a 권역, a theme, the check box, a type chip then a 권역 (the type row's own pressed chip is not
    what moves here), and the load of a filtered URL, laid out as the whole list (outside evaluation 2026-10-18: '관광지
    219곳' → '관광지 28곳 (전체 219곳 중)' pushed a chip onto the next line)."""
    ctx, page, errors = _page(browser, built, dev)

    def same(before, after):
        assert (after["result"], after["badge"]) != (before["result"], before["badge"]), "nothing changed: proves nothing"
        assert after["row"] == before["row"] and after["tools"] == before["tools"], (before, after)
        moved = [(b, a) for b, a in zip(before["chips"], after["chips"]) if b != a]
        assert not moved and len(after["chips"]) == len(before["chips"]) > 2, moved

    try:
        page.goto("http://site.test/places/", wait_until="load")
        whole = page.evaluate(TYPE_ROW)
        assert (whole["result"], whole["badge"]) == ("관광지 12곳", None)
        for press in ('[data-f=region][data-v="고군산"]', f'[data-f=theme][data-v="{ISLANDS}"]', "input[data-f=check]"):
            page.goto("http://site.test/places/", wait_until="load")
            _open_panel(page)
            page.click(press)
            after = page.evaluate(TYPE_ROW)
            assert after["badge"] == "1" and "(전체 12곳 중)" in after["result"], after
            same(whole, after)
        page.goto("http://site.test/places/", wait_until="load")
        page.click(f'.f-top [data-f=type][data-v="{MUSEUM}"]')
        museums = page.evaluate(TYPE_ROW)
        assert museums["result"] == "관광지 3곳 (전체 12곳 중)"
        _open_panel(page)
        page.click('[data-f=region][data-v="원도심"]')
        same(museums, page.evaluate(TYPE_ROW))
        page.goto(f"http://site.test/places/?region=고군산&theme={ISLANDS}", wait_until="load")
        same(whole, page.evaluate(TYPE_ROW))
        assert errors == [], errors
    finally:
        ctx.close()


def test_in_a_browser_a_phone_opens_the_row_at_its_pressed_chip(built, browser):
    """A phone (390, touch: the type chips are one row it swipes; review 2026-10-18, fourth round): a list opened with
    a type filter — its address, or come back to from a place — shows the pressed chip in its row (the row scrolled
    sideways to it, the chip clear of the row's 36px faded end: the row's end leaves that room for the last chip), and
    the page itself does not move. The whole list's row starts at 전체."""
    ctx, page, errors = _page(browser, built, PHONE)
    seen = """() => { const r = document.querySelector('.f-top .f-row'), c = r.querySelector('[aria-pressed="true"]');
      const a = r.getBoundingClientRect(), b = c.getBoundingClientRect();
      return { v: c.getAttribute('data-v'), left: r.scrollLeft, inside: b.left >= a.left && b.right <= a.right - 35,
               y: scrollY, wide: r.scrollWidth > r.clientWidth }; }"""
    try:
        page.goto("http://site.test/places/", wait_until="load")
        last = page.evaluate("[...document.querySelectorAll('.f-top [data-f=type]')].at(-1).getAttribute('data-v')")
        assert page.evaluate(seen) == {"v": "", "left": 0, "inside": True, "y": 0, "wide": True}
        page.goto(f"http://site.test/places/?type={last}", wait_until="load")
        got = page.evaluate(seen)
        assert (got["v"], got["inside"], got["y"]) == (last, True, 0) and got["left"] > 0, got
        # to a place and back: the list comes back filtered, its chip in view
        page.click(".rec:not([hidden]) a")
        page.wait_for_load_state("load")
        page.go_back(wait_until="load")
        page.wait_for_timeout(200)
        got = page.evaluate(seen)
        assert (got["v"], got["inside"]) == (last, True) and got["left"] > 0, got
        assert errors == [], errors
    finally:
        ctx.close()


def test_in_a_browser_the_band_per_area_follows_the_filters(built, browser):
    """The desktop band's count per 권역 (.band-data): each number is its group's shown places, and an entry whose
    group shows nothing is faint (.is-zero) and no link (its group is hidden) — then back with the filters off."""
    ctx, page, errors = _page(browser, built, DESKTOP)
    band = """() => [...document.querySelectorAll('.band-data a')].map(a => [a.querySelector('span').textContent,
      +a.querySelector('.num').textContent, a.classList.contains('is-zero'), a.getAttribute('href')])"""
    groups = """() => Object.fromEntries([...document.querySelectorAll('.lg-group')].map(g => [g.querySelector('.lg-g').firstChild.textContent.trim(),
      [g.querySelectorAll('.rec:not([hidden])').length, '#' + g.id]]))"""
    try:
        page.goto("http://site.test/places/", wait_until="load")
        assert page.is_visible(".band-data")
        whole = page.evaluate(band)
        assert [(r, n) for r, n, _, _ in whole] == [("원도심", 3), ("은파", 2), ("고군산", 3), ("권역 미정", 4)]
        assert not any(z for _, _, z, _ in whole) and all(h for _, _, _, h in whole)
        for q in (f"?type={MUSEUM}", f"?theme={ISLANDS}", "?check=1", f"?type={MUSEUM}&theme={ISLANDS}"):
            page.goto("http://site.test/places/" + q, wait_until="load")
            g, b = page.evaluate(groups), page.evaluate(band)
            for r, n, zero, href in b:
                assert n == g[r][0], (q, r)
                assert zero == (n == 0) and href == (None if n == 0 else g[r][1]), (q, r, zero, href)
            assert any(z for _, _, z, _ in b), q
        # the band link of a shown group still leads to it; the filters off bring every entry back
        page.goto(f"http://site.test/places/?type={MUSEUM}", wait_until="load")
        page.click(".band-data a:not(.is-zero)")
        assert unquote(page.evaluate("location.hash")) == page.evaluate(groups)["원도심"][1]
        page.click('[data-f=type][data-v=""]')
        assert page.evaluate(band) == whole
        assert errors == [], errors
    finally:
        ctx.close()


def test_in_a_browser_without_js_the_lists_are_complete_and_the_bar_is_absent(built, browser):
    ctx, page, errors = _page(browser, built, PHONE, java_script_enabled=False)
    try:
        page.goto(f"http://site.test/places/?type={MUSEUM}&theme={ISLANDS}", wait_until="load")
        assert not page.is_visible("[data-filters]") and not page.is_visible("[data-f-undo]") and not page.is_visible("[data-empty]")
        assert page.evaluate(SHOWN) == len(rows((built / "places" / "index.html").read_text("utf-8"))) == 12
        page.goto("http://site.test/map/", wait_until="load")
        assert not page.is_visible("[data-kinds]") and not page.is_visible("[data-map-undo]")
    finally:
        ctx.close()
