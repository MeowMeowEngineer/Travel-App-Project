"""The AI course planner's page /plan/ (operator 2026-10-17: its own page, very visible, many cute 3D pictures;
chatbot/planner.js answers /api/plan/). The build writes the page — noindex, not in the sitemap — and /plan/places.json,
each place's first-screen values, TourAPI photo and point; the page's choices are real inputs; in a browser
(Playwright, /api/plan/ mocked with scripted SSE, nothing leaves the machine) the form asks with the conditions, the
steps light up, the plan is drawn from the site's own data with day tabs, legs with directions links, the fee card and
what to check, an edit sends the plan and the change, an error offers a retry, a reload shows the plan again, and no
phone width scrolls sideways."""
import json
import re
import shutil
from pathlib import Path

import pytest

from pipeline.build import build
from pipeline.icons import REGISTRY   # the site's picture registry (data/<region>/icons.json)

ROOT = Path(__file__).resolve().parent.parent
SAMPLE = ROOT / "data" / "sample"
PNG = bytes.fromhex("89504e470d0a1a0a0000000d49484452000000010000000108060000001f15c4890000000d49444154789c6360000002000154a24f5d0000000049454e44ae426082")


def plan_build(tmp_path):
    data = tmp_path / "data"
    shutil.copytree(SAMPLE, data)
    site = json.loads((data / "site.json").read_text("utf-8"))
    site["kakao_js_key"] = "test-key-123"
    (data / "site.json").write_text(json.dumps(site, ensure_ascii=False), "utf-8")
    places = json.loads((data / "places.json").read_text("utf-8"))
    pub = [p for p in places if p.get("status") in ("published", "reviewed")]
    for i, p in enumerate(pub[:4]):
        p["geo"] = {"lat": 35.98 + i * 0.01, "lng": 126.72 + i * 0.012, "source": "TourAPI"}
    pub[0]["images"] = [{"url": "https://tong.visitkorea.or.kr/cms/resource/00/1_image2_1.jpg", "license": "KOGL-3",
                         "source": "TourAPI", "credit": "한국관광공사", "alt": "사진"}]
    (data / "places.json").write_text(json.dumps(places, ensure_ascii=False), "utf-8")
    out = tmp_path / "out"
    build(data, out, "sample")
    return out


@pytest.fixture(scope="module")
def site(tmp_path_factory):
    return plan_build(tmp_path_factory.mktemp("plan"))


def test_the_page_is_a_noindex_utility_page_with_real_inputs_and_its_place_data(site):
    html = (site / "plan" / "index.html").read_text("utf-8")
    assert '<meta name="robots" content="noindex' in html
    assert "/plan/" not in (site / "sitemap.xml").read_text("utf-8")
    assert '<link rel="stylesheet" href="/assets/plan.css">' in html
    assert (site / "assets" / "plan.js").is_file() and (site / "assets" / "plan.css").is_file()
    assert 'data-plan data-api="/api/plan/" data-places="/plan/places.json" data-kakao-sdk="' in html
    # every choice is a real radio or check box inside its card's label
    for name, kind, n in (("days", "radio", 3), ("move", "radio", 2), ("with", "radio", 4), ("prefs", "checkbox", 9),
                          ("needs", "checkbox", 6)):
        assert len(re.findall(rf'<label class="trp-card[^"]*"><input type="{kind}" name="{name}"', html)) == n, name
    assert html.count('<fieldset class="trp-step">') == 6 and html.count("<legend>") == 6
    assert 'aria-label="어른 한 명 더하기"' in html and 'type="date" name="date" required' in html
    # without JS the page says so and points to the courses and guides
    assert re.search(r"<noscript><p class=\"wrap trp-nojs\">코스 만들기는 자바스크립트가 켜져 있어야 동작합니다\. <a href=\"/courses/\">", html)
    places = json.loads((site / "plan" / "places.json").read_text("utf-8"))
    first = next(v for v in places.values() if v.get("img"))
    assert first["img"]["u"].startswith("https://tong.visitkorea.or.kr/") and first["img"]["t"] == 3
    assert all({"n", "k", "t", "ic"} <= set(v) for v in places.values())
    assert sum(1 for v in places.values() if "g" in v) == 4


def test_the_new_pictures_are_registered_and_fall_back_to_line_glyphs():
    icons = json.loads(REGISTRY.read_text("utf-8"))["icons"]
    ui = (ROOT / "templates" / "_ui.html.j2").read_text("utf-8")
    for pid in ("icon-plan", "plan-dur-day", "plan-dur-1n2d", "plan-dur-2n3d", "plan-with-solo", "plan-with-couple",
                "plan-with-parents", "pref-photo", "cond-stroller", "cond-wheelchair", "cond-parking", "plan-budget", "plan-swap"):
        g = icons[pid]["glyph"]
        assert f"name == '{g}'" in ui, (pid, g)
    prompts = (ROOT / "docs" / "image_prompts_incheongak.md").read_text("utf-8")
    assert all(f"`{pid}`" in prompts for pid in icons if icons[pid]["group"] == "plan")


def test_every_picture_the_result_draws_is_on_the_page(site):
    """plan.js clones the result's pictures by ID from the page's <template id="trp-pics"> (present.PLAN_RESULT_PICS);
    one not there is drawn as an empty pale circle (review 2026-10-18, fourth round: the status row '필요한 조건' asked
    for cond-wheelchair and the tile '들르는 곳' for icon-course). Every registered picture plan.js names, and every
    kind's picture a stop may carry (places.json ic), is in the template as its 3D picture — or, while a city's picture
    has not come in yet (not in templates/assets/icons/manifest.json), as the registry's interim line glyph (pic-tmp),
    never an empty circle."""
    from pipeline import present
    icons = json.loads(REGISTRY.read_text("utf-8"))["icons"]
    made = json.loads((ROOT / "templates" / "assets" / "icons" / "manifest.json").read_text("utf-8"))
    js = (ROOT / "templates" / "assets" / "plan.js").read_text("utf-8")
    named = set(re.findall(r'"([a-z]+-[a-z0-9-]+)"', js)) & set(icons)
    assert {"cond-wheelchair", "icon-course", "transit-bus", "plan-budget"} <= named
    wanted = named | set(present.KIND_PIC.values())
    assert wanted <= set(present.PLAN_RESULT_PICS), wanted - set(present.PLAN_RESULT_PICS)
    html = (site / "plan" / "index.html").read_text("utf-8")
    pics = html[html.index('<template id="trp-pics">'):]
    pics = pics[:pics.index("</template>")]
    assert {"cond-wheelchair", "plan-budget", "icon-course"} <= set(made)   # the planner's own pictures are 3D
    for pid in wanted:
        look = "pic pic-3d" if pid in made else "pic pic-tmp"
        assert f'<span data-id="{pid}"><span class="{look}" data-pic="{pid}"' in pics, pid


SITE = "https://gunsan.webforai.kr"


def sse(*events) -> str:
    return "".join(f"data: {json.dumps(e, ensure_ascii=False)}\n\n" for e in events)


def a_plan(paths, days=2):
    """A checked plan as chatbot/planner.js finish (v 2) sends it."""
    stop = lambda p, a, b, role="visit", day="open", checks=(): {"path": p, "name": p.split("/")[2], "start": a, "end": b,  # noqa: E731
                                                               "role": role, "why": "1층에 어린이박물관이 있습니다", "day": day,
                                                               "notes": [], "flags": [], "checks": list(checks)}
    d1 = {"date": "2026-10-24", "label": "1일차 · 10월 24일 (토)",
          "stops": [stop(paths[0], "10:00", "11:30"), stop(paths[1], "12:00", "13:00", "meal"),
                    stop(paths[2], "13:00", "14:30", "visit", "unknown", ["쉬는 날이 사이트에 없음 — 그날 여는지 확인 필요"]),
                    stop(paths[3], "20:00", "21:00", "stay")],
          "legs": [{"from": 0, "to": 1, "m": 1430, "gap": 30, "routes": ["07", "99"], "flag": "", "mode": "traffic",
                    "url": "https://map.kakao.com/link/by/traffic/a,35.98,126.72/b,35.99,126.73"},
                   {"from": 1, "to": 2, "m": 400, "gap": 0, "routes": [], "flag": "직선 400m인데 이동 시간을 두지 않음", "mode": "walk",
                    "url": "https://map.kakao.com/link/by/walk/b,35.99,126.73/c,36.0,126.74"}],
          "hubs": [{"dir": "from", "name": "군산역", "stop": "a", "at": "09:00", "gap": 60, "url": "https://map.kakao.com/?sName=a&eName=b"}]}
    d2 = {"date": "2026-10-25", "label": "2일차 · 10월 25일 (일)", "stops": [stop(paths[2], "10:00", "12:00")], "legs": [], "hubs": []}
    return {"v": 2, "made": "2026-10-17T01:00:00Z", "title": "아이와 원도심 박물관 1박 2일", "summary": "실내 위주로 돕니다.",
            "notes": ["구간 시간은 여유입니다"], "conditions": {}, "days": [d1, d2][:days],
            "fees": {"state": "known", "total": 3000, "known": 3000, "limit": 10000, "verdict": "within", "open": [], "conds": [],
                     "days": [{"date": "2026-10-24", "lines": [{"what": "근대역사박물관", "who": "어른", "count": 1, "status": "paid",
                                                                "won": 3000, "sub": 3000, "basis": "요금표 '성인'"}]}]},
            "needs": [{"key": "stroller", "label": "유모차", "rows": [
                {"day": 0, "i": 0, "name": "a", "state": "ok", "text": "출입구: 경사로"},
                {"day": 0, "i": 1, "name": "b", "state": "unknown", "text": "출입구 접근 정보 없음"}]}],
            "checks": [{"k": "need", "t": "유모차: b — 출입구 접근 정보 없음"}, {"k": "move", "t": "장소 사이 시간은 계획상 여유"}],
            "flags": ["1일차 2→3번 b → c: 직선 400m인데 이동 시간을 두지 않음"], "status": "unmet",
            "fixed": ["1일차 장미갤러리: 10월 26일(월)은 쉬는 날이라 일정에서 뺐습니다"],
            "complete": {"meals": [{"day": 0, "kind": "lunch", "state": "ok"}], "gaps": [],
                         "prefs": [{"key": "history", "label": "역사·문화", "met": True}, {"key": "islands", "label": "섬·바다", "met": False}]},
            "todo": ["legs"]}


def plan_paths(site):
    places = json.loads((site / "plan" / "places.json").read_text("utf-8"))
    shot = next(p for p in places if places[p].get("img"))   # the place with a TourAPI photo comes first
    return [shot, next(p for p in places if places[p]["k"] == "food" and p != shot),
            next(p for p in places if places[p]["k"] == "attraction" and p != shot),
            next(p for p in places if places[p]["k"] == "stay" and p != shot)]


def server(site, plan, calls, script):
    """The browser's whole network: the built site from disk, /api/plan/ answered from `script` (then `plan`), the
    Kakao SDK's stand-in, a TourAPI photo; anything else is refused."""
    import mimetypes
    from urllib.parse import unquote, urlsplit

    def serve(route):
        url = route.request.url
        if url.endswith("/api/plan/"):
            calls.append(route.request.post_data_json)
            body = script["next"].pop(0) if script["next"] else sse({"type": "plan", "plan": plan})
            if isinstance(body, tuple):   # (status, JSON body): an answer before any streaming (422 preflight, 429 …)
                return route.fulfill(status=body[0], body=json.dumps(body[1], ensure_ascii=False), content_type="application/json")
            return route.fulfill(status=200, body=body, headers={"content-type": "text/event-stream; charset=utf-8"})
        if "dapi.kakao.com" in url:   # the Kakao SDK's stand-in (tests/js/kakao_stub.js)
            return route.fulfill(status=200, body=(ROOT / "tests" / "js" / "kakao_stub.js").read_text("utf-8"),
                                 content_type="application/javascript")
        if "tong.visitkorea.or.kr" in url:
            return route.fulfill(status=200, body=PNG, content_type="image/png")
        if not url.startswith("http://site.test/"):
            return route.abort()
        path = unquote(urlsplit(url).path)
        f = site / path.strip("/")
        f = f / "index.html" if path.endswith("/") else f
        if not f.is_file():
            return route.fulfill(status=404, body="")
        route.fulfill(status=200, body=f.read_bytes(), content_type=mimetypes.guess_type(f.name)[0] or "application/octet-stream")
    return serve


def test_in_a_browser_the_planner_asks_draws_edits_recovers_and_comes_back(site):
    sync_api = pytest.importorskip("playwright.sync_api")
    paths = plan_paths(site)
    plan = a_plan(paths)
    calls = []
    script = {"next": [sse({"type": "status", "step": "search", "text": "장소를 찾고 있어요"},
                           {"type": "status", "step": "check", "text": "휴무·운영시간을 확인하고 있어요"},
                           {"type": "plan", "plan": plan})]}
    serve = server(site, plan, calls, script)

    with sync_api.sync_playwright() as p:
        try:
            browser = p.chromium.launch()
        except Exception as ex:  # noqa: BLE001 — Chromium is not installed here
            pytest.skip(f"Chromium 없음: {ex}")
        try:
            ctx = browser.new_context(viewport={"width": 390, "height": 844}, locale="ko-KR")
            ctx.route("**/*", serve)
            page = ctx.new_page()
            errors: list[str] = []
            page.on("pageerror", lambda e: errors.append(str(e)))
            page.on("console", lambda m: errors.append(m.text) if m.type == "error" else None)
            page.goto("http://site.test/plan/", wait_until="load")
            page.wait_for_function("() => document.querySelector('[data-plan-sum]').textContent.length > 0")
            assert page.evaluate("() => document.documentElement.scrollWidth") <= 390
            page.click('label.trp-card:has(input[name="days"][value="2"])')
            page.click('label.trp-card:has(input[name="with"][value="kids"])')   # adds a child (age 7)
            page.select_option("[data-ages] select", "4")
            for v in ("history", "food", "islands", "nature", "night"):
                page.click(f'label.trp-card:has(input[name="prefs"][value="{v}"])')
            assert page.evaluate("() => document.querySelectorAll('input[name=prefs]:checked').length") == 4
            page.click('label.trp-card:has(input[name="needs"][value="rain"])')
            page.click('[data-budget="10000"]')
            page.fill("textarea[name=note]", "짬뽕 먹고 싶어요")
            assert "1박 2일" in page.text_content("[data-plan-sum]") and "아이 4살" in page.text_content("[data-plan-sum]")
            page.click(".trp-submit")
            page.wait_for_selector("#h-result")
            c = calls[0]["conditions"]
            assert c["days"] == 2 and c["with"] == "kids" and c["kids"] == [4] and c["adults"] == 2
            assert c["prefs"] == ["history", "food", "islands", "nature"] and c["needs"] == ["rain"] and c["budget"] == 10000
            assert c["note"] == "짬뽕 먹고 싶어요" and re.fullmatch(r"\d{4}-\d{2}-\d{2}", c["date"])
            # what the code says first (review 2026-10-17: a '6/6 확인' badge above unconfirmed places): the status, each
            # check in its own state, the first things to check
            assert "is-bad" in page.get_attribute(".trp-status", "class") and "조건을 다 맞추지 못한" in page.text_content(".trp-status h3")
            assert page.locator(".trp-flags li").all_text_contents() == ["1일차 2→3번 b → c: 직선 400m인데 이동 시간을 두지 않음"]
            # what the site put right itself (planner.repair) is not listed (operator 2026-10-18: '이런 거 좀 안 뜨게')
            assert page.locator(".trp-fixed").count() == 0 and "바로잡은" not in page.text_content(".trp-result")
            rows = page.locator(".trp-st4 li")
            assert rows.count() == 6
            # what the data does not say is information, not a check (operator 2026-10-18)
            assert "공휴일·특별 운영" in rows.nth(1).text_content() and "그날 운영 자료가 없는 곳 1곳" in rows.nth(1).text_content()
            assert "is-info" in rows.nth(1).get_attribute("class")
            assert "자료 있음 1 · 정보 없음 1 · 맞지 않음 0" in rows.nth(2).text_content()
            assert "3,000원 · 예산 안" in rows.nth(3).text_content()
            assert "구간마다 계획상 여유를 두었어요 · 실제 이동 시간은 지도 앱에서" in rows.nth(4).text_content()
            assert "is-info" in rows.nth(4).get_attribute("class")
            assert page.locator(".trp-st4 li.is-check, .trp-top").count() == 0
            # how complete the day is (outside evaluation 2026-10-18): meals, likings, empty time
            assert rows.nth(5).locator(".trp-st4-l").text_content() == "일정 완성도"
            assert "1일차 점심 포함 · 역사·문화 반영 / 섬·바다 미반영 · 2시간 넘게 빈 시간 없음" in rows.nth(5).text_content()
            assert "is-info" in rows.nth(5).get_attribute("class")
            # an unmet plan: one-tap fixes for what is left (the flagged leg)
            assert page.locator(".trp-qfix .trp-qf").all_text_contents() == ["이동 구간 다시 짜기"]
            # the travel-time line once above the day, under a leg only when it is flagged
            assert page.locator(".trp-tl-note").count() == 1 and "실제 이동 시간은 확인되지 않았어요" in page.text_content(".trp-tl-note")
            assert page.locator(".trp-leg:not(.trp-hub) .trp-leg-note").count() == 1
            assert "직선 400m인데 이동 시간을 두지 않음" in page.text_content(".trp-leg-bad .trp-leg-note")
            # the plan: title, day tabs, stops from the site's data, legs, the start, fees, checks
            assert page.text_content("#h-result") == "아이와 원도심 박물관 1박 2일"
            assert page.locator(".trp-days [role=tab]").count() == 2
            assert page.locator(".trp-stop").count() == 4
            assert page.locator(".trp-stop .trp-ai").first.text_content() == "AI"
            assert page.locator(".trp-ph figcaption").first.text_content() == "출처: 한국관광공사"
            assert page.locator(".trp-ph.t3 img").count() == 1   # KOGL-3: framed whole
            assert page.locator(".trp-stop[data-day=unknown] .trp-day").text_content().endswith("운영 확인 필요")
            assert "확인: 쉬는 날이 사이트에 없음" in page.text_content(".trp-stop[data-day=unknown] .trp-warn")
            assert page.locator(".trp-leg").count() == 3 and page.locator(".trp-leg-bad").count() == 1 and page.locator(".trp-hub").count() == 1
            assert "군산역 09:00 출발" in page.text_content(".trp-hub") and "계획상 여유 60분" in page.text_content(".trp-hub")
            assert page.get_attribute(".trp-leg:not(.trp-hub) .trp-leg-go >> nth=0", "href").startswith("https://map.kakao.com/link/by/traffic/")
            assert "같은 번호 노선 07·99번" in page.text_content(".trp-leg:not(.trp-hub) >> nth=0")
            assert "계획상 여유 30분" in page.text_content(".trp-leg:not(.trp-hub) >> nth=0")
            assert page.text_content(".trp-total") == "3,000원" and "예산 안" in page.text_content(".trp-verdict")
            assert "근대역사박물관 · 어른 1명:" in page.text_content(".trp-budget-c .trp-lines")
            assert "유모차: b — 출입구 접근 정보 없음" in page.text_content(".trp-check-c")
            assert page.locator(".trp-map .map[data-map][data-kakao-sdk]").count() == 1
            # on a phone the charts are folded; the reader opens them
            assert page.locator(".trp-fold[open]").count() == 0 and page.is_visible(".trp-fine-s")
            for summary in page.locator(".trp-fold > summary").all():
                summary.click()
            # the diagrams, every number from the checked plan: tiles, the day clock, the needs, the stations, the bars
            kpis = page.locator(".trp-kpi")
            assert kpis.count() == 4
            assert kpis.nth(0).locator(".trp-kpi-v").text_content() == "5곳" and "관람 3 · 식사 1 · 숙소 1" in kpis.nth(0).text_content()
            assert kpis.nth(1).locator(".trp-kpi-v").text_content() == "1.8km"   # 1,430m + 400m, straight lines
            assert kpis.nth(2).locator(".trp-kpi-v").text_content() == "3,000원"
            assert page.get_attribute(".trp-meter", "aria-label") == "확인된 입장료 3,000원 / 예산 10,000원"
            assert page.evaluate("() => document.querySelector('.trp-meter span').style.width") == "30%"
            assert kpis.nth(3).locator(".trp-kpi-v").text_content() == "5/5" and "그날 운영 확인 필요 1곳" in kpis.nth(3).text_content()
            assert page.locator(".trp-tlx-row").count() == 2
            day1 = page.locator(".trp-tlx-track >> nth=0")
            assert day1.locator(".trp-seg:not(.trp-seg-gap)").count() == 4 and day1.locator(".trp-seg-gap").count() == 2
            assert day1.locator(".trp-seg-flag").count() == 1
            assert page.locator(".trp-tlx-ticks span").all_text_contents() == ["10시", "12시", "14시", "16시", "18시", "20시"]
            assert page.locator(".trp-legend li").all_text_contents() == [
                "관람 5시간", "식사 1시간", "숙소 1시간", "계획상 여유 6시간", "이동이 빠듯한 곳 1곳"]
            first = day1.locator(".trp-seg >> nth=0")
            assert first.get_attribute("role") == "img" and first.get_attribute("tabindex") == "0"
            assert first.get_attribute("aria-label").endswith("관람 10:00~11:30 (1시간 30분)")
            first.hover()
            assert page.is_visible(".trp-tip") and page.text_content(".trp-tip") == first.get_attribute("aria-label")
            page.mouse.move(2, 2)
            assert page.is_hidden(".trp-tip")
            assert page.locator(".trp-ndt tbody tr").count() == 5 and page.locator(".trp-ndt thead th").all_text_contents() == ["장소", "유모차"]
            assert page.locator(".trp-nd.is-ok").count() == 1 and page.locator(".trp-nd.is-unknown").count() == 1
            assert page.locator(".trp-metro .trp-st").count() == 5 and page.locator(".trp-metro .trp-st-hub").count() == 1
            assert page.locator(".trp-metro .trp-link:not(.trp-link-hub) .tn").all_text_contents() == ["1.4km", "400m"]
            assert page.locator(".trp-metro .trp-link.bad").count() == 1
            assert page.locator(".trp-bars li").count() == 2 and page.locator(".trp-bar.bad").count() == 1
            assert page.locator(".trp-bar-v").all_text_contents() == ["1.4km", "400m ⚠"]
            # passing it on: a text file with the whole plan, every day and what to check
            with page.expect_download() as dl:
                page.click(".trp-x:has-text('파일로 저장')")
            text = Path(dl.value.path()).read_text("utf-8")
            # a draft still unmet says so on its first line (outside evaluation 2026-10-18)
            assert text.startswith("[수정이 필요한 초안] 아이와 원도심 박물관 1박 2일") and "■ 2일차 · 10월 25일 (일)" in text
            assert "유모차: b — 출입구 접근 정보 없음" in text and "일정 완성도: 1일차 점심 포함" in text
            assert "09:00 군산역 출발" in text and "입장료: 3,000원" in text and "구간 직선거리: 합 1.8km" in text
            assert "trp-print" in page.inner_html(".trp-result")
            assert page.evaluate("() => document.documentElement.scrollWidth") <= 390
            # the second day by keyboard
            page.focus("#trp-tab-0")
            page.keyboard.press("ArrowRight")
            assert page.evaluate("() => document.activeElement.id") == "trp-tab-1"
            assert page.locator(".trp-stop").count() == 1
            # an edit: a quick chip fills the box; the request carries the plan and the change
            page.click(".trp-qe >> nth=0")
            assert page.input_value("#trp-ask") == "비가 오면 실내 위주로 바꿔 주세요"
            page.click(".trp-edit-f button[type=submit]")
            page.wait_for_function("() => document.querySelector('[data-plan-work]').hidden")
            e = calls[1]
            assert e["request"] == "비가 오면 실내 위주로 바꿔 주세요" and e["conditions"] == calls[0]["conditions"]
            assert e["plan"]["days"][0]["stops"][0] == {"page": paths[0], "start": "10:00", "end": "11:30", "role": "visit",
                                                         "why": "1층에 어린이박물관이 있습니다"}
            assert page.locator(".trp-diff li").all_text_contents() == ["장소와 시각은 그대로예요."]
            # a reload shows the plan again (this tab's storage) and the form holds its conditions (review: the form
            # went back to its defaults)
            page.reload(wait_until="load")
            page.wait_for_selector("#h-result")
            assert page.input_value("textarea[name=note]") == "짬뽕 먹고 싶어요" and page.input_value("input[name=budget]") == "10000"
            assert page.is_checked('input[name="days"][value="2"]') and page.locator("[data-ages] select").count() == 1
            assert page.input_value("[data-ages] select") == "4"
            # a change that fails keeps the plan and says so above the edit box
            script["next"] = [sse({"type": "error", "code": "busy", "message": "지금은 코스를 만들 수 없습니다."})]
            page.fill("#trp-ask", "덜 걷게 해 주세요")
            page.click(".trp-edit-f button[type=submit]")
            page.wait_for_selector(".trp-fail-edit")
            assert page.locator(".trp-stop").count() == 4 and page.evaluate("() => document.activeElement.textContent") == "바꾸지 못했어요"
            # an error offers a retry
            script["next"] = [sse({"type": "error", "code": "busy", "message": "지금은 코스를 만들 수 없습니다."})]
            page.click(".trp-submit")
            page.wait_for_selector(".trp-fail")
            assert "지금은 코스를 만들 수 없습니다." in page.text_content(".trp-fail")
            page.click(".trp-fail .btn")
            page.wait_for_selector("#h-result")
            assert errors == [], errors
            ctx.close()
            for width in (360, 1440):
                ctx = browser.new_context(viewport={"width": width, "height": 900}, locale="ko-KR")
                ctx.route("**/*", serve)
                page = ctx.new_page()
                page.goto("http://site.test/plan/", wait_until="load")
                page.click(".trp-submit")
                page.wait_for_selector("#h-result")
                assert page.evaluate("() => document.documentElement.scrollWidth") <= width, width
                ctx.close()
        finally:
            browser.close()


def test_in_a_browser_conditions_come_from_the_address_and_an_unmet_plan_is_honest_about_what_is_left(site):
    """Outside evaluation 2026-10-18: the assistant hands a reader over with conditions in the address (never sent by
    themselves); a plan still 'unmet' shows no distance total over legs without one, never reads all-clear beside a
    closed stop, says how complete the day is, offers one-tap fixes that send an edit, and its text says it is a draft."""
    import datetime
    from urllib.parse import quote
    sync_api = pytest.importorskip("playwright.sync_api")
    paths = plan_paths(site)
    plan = a_plan(paths)
    d1 = plan["days"][0]
    d1["stops"][1]["added"] = True                                    # the lunch the site put in
    d1["stops"][3]["added"] = True                                    # the night's stay the site put in
    d1["stops"][2].update({"day": "closed", "checks": [], "flags": ["2026-10-24(토)은 정기 휴무"]})
    d1["legs"][1].update({"m": None, "flag": "", "gap": 20, "url": None})   # a place with no point: no distance
    plan.update({"status": "unmet", "flags": ["1일차 3번 c: 2026-10-24(토)은 정기 휴무", "1일차: 14:30~18:00 3시간 30분 동안 들르는 곳이 없다"],
                 "todo": ["closed", "legs", "meal", "gaps"],
                 "complete": {"meals": [{"day": 0, "kind": "lunch", "state": "missing"}, {"day": 1, "kind": "lunch", "state": "missing"}],
                              "gaps": [{"day": 0, "from": "14:30", "to": "18:00", "minutes": 210}],
                              "prefs": [{"key": "history", "label": "역사·문화", "met": True}, {"key": "night", "label": "야경", "met": None}],
                              "edit": [{"what": "점심", "state": "lost"}]}})
    calls: list = []
    serve = server(site, plan, calls, {"next": []})
    day = (datetime.date.today() + datetime.timedelta(days=10)).isoformat()
    address = (f"/plan/?date={day}&days=2&start=09:00&end=20:00&move=car&with=kids&adults=3&seniors=1&kids=8,5"
               f"&needs=rain,stroller,bogus&prefs=history,food,islands,nature,night&from=station&to=bus&note={quote('짬뽕 먹고 싶어요')}")
    with sync_api.sync_playwright() as p:
        try:
            browser = p.chromium.launch()
        except Exception as ex:  # noqa: BLE001 — Chromium is not installed here
            pytest.skip(f"Chromium 없음: {ex}")
        try:
            ctx = browser.new_context(viewport={"width": 390, "height": 844}, locale="ko-KR")
            ctx.route("**/*", serve)
            page = ctx.new_page()
            errors: list[str] = []
            page.on("pageerror", lambda e: errors.append(str(e)))
            # values that are not the form's own choices are left out: the defaults stay
            page.goto("http://site.test/plan/?days=9&move=plane&adults=99&kids=40&prefs=bogus&start=05:00&from=harbour", wait_until="load")
            assert page.is_checked('input[name="days"][value="1"]') and page.is_checked('input[name="move"][value="transit"]')
            assert page.text_content('[data-count="adults"] [data-count-value]') == "2" and page.locator("[data-ages] select").count() == 0
            assert page.input_value("select[name=start]") == "10:00" and page.input_value("select[name=from]") == ""
            assert page.locator('input[name="prefs"]:checked').count() == 0 and page.get_attribute("[data-plan]", "data-prefilled") is None
            # the assistant's hand-over: every condition in the form, nothing sent
            page.goto("http://site.test" + address, wait_until="load")
            assert page.get_attribute("[data-plan]", "data-prefilled") == ""
            assert page.input_value("input[name=date]") == day and page.is_checked('input[name="days"][value="2"]')
            assert page.input_value("select[name=start]") == "09:00" and page.input_value("select[name=end]") == "20:00"
            assert page.is_checked('input[name="move"][value="car"]') and page.is_checked('input[name="with"][value="kids"]')
            assert page.text_content('[data-count="adults"] [data-count-value]') == "3"
            assert page.text_content('[data-count="seniors"] [data-count-value]') == "1"
            assert [page.input_value(f"[data-ages] select >> nth={i}") for i in range(2)] == ["8", "5"]
            assert page.eval_on_selector_all('input[name="needs"]:checked', "els => els.map(e => e.value)") == ["rain", "stroller"]
            assert page.eval_on_selector_all('input[name="prefs"]:checked', "els => els.map(e => e.value)") == ["history", "food", "islands", "nature"]
            assert page.input_value("select[name=from]") == "station" and page.input_value("select[name=to]") == "bus"
            assert page.input_value("textarea[name=note]") == "짬뽕 먹고 싶어요" and "1박 2일" in page.text_content("[data-plan-sum]")
            page.wait_for_timeout(300)
            assert calls == []                                        # never sent by itself
            page.click(".trp-submit")
            page.wait_for_selector("#h-result")
            c = calls[0]["conditions"]
            assert (c["date"], c["days"], c["start"], c["end"], c["move"], c["with"]) == (day, 2, "09:00", "20:00", "car", "kids")
            assert (c["adults"], c["seniors"], c["kids"], c["from"], c["to"]) == (3, 1, [8, 5], "station", "bus")
            assert c["needs"] == ["rain", "stroller"] and c["prefs"] == ["history", "food", "islands", "nature"]
            # the distance tile: no total over legs without a distance
            tile = page.locator(".trp-kpi >> nth=1")
            assert tile.locator(".trp-kpi-v").text_content() == "전체 이동거리 계산 안 됨"
            assert tile.locator(".trp-kpi-n").text_content() == "2개 구간 중 1개만 거리 있음"
            assert "좌표가 없어 거리를 모르는 구간 1개는 막대에 없어요." in page.text_content(".trp-bars")
            assert page.locator(".trp-kpi >> nth=3").locator(".trp-kpi-n").text_content() == "그날 휴무 1곳"
            # a closed stop: the holiday row never reads all-clear beside it
            rows = page.locator(".trp-st4 li")
            assert "그날 휴무인 곳 1곳" in rows.nth(0).text_content()
            assert "is-bad" in rows.nth(1).get_attribute("class") and "그날 쉬는 곳 1곳이 남아 있음" in rows.nth(1).text_content()
            done = rows.nth(5)
            assert "is-bad" in done.get_attribute("class")
            # every picture of the result is a picture: none is the empty circle of an ID the page does not carry
            assert page.locator("[data-plan-result] .pic").count() > 10
            assert page.locator("[data-plan-result] .pic:empty").count() == 0
            assert done.locator(".trp-st4-v").text_content().endswith(
                "1·2일차 점심 빠짐 · 역사·문화 반영 / 자료로 판단 못 함: 야경 · 1일차 14:30~18:00 3시간 30분 비어 있음 · 고치기 전 일정의 점심: 빠짐")
            # the stop the site put in says so where the AI's reason would be
            assert page.text_content(".trp-stop[data-by=site] .trp-site") == "사이트"
            assert "식사할 곳이 없어 사이트가 넣은 가까운 음식점이에요" in page.text_content(".trp-stop[data-role=meal][data-by=site] .trp-by")
            assert "묵을 곳이 없어 사이트가 넣은 숙소예요" in page.text_content(".trp-stop[data-role=stay][data-by=site] .trp-by")
            # the text passed on starts as a draft
            with page.expect_download() as dl:
                page.click(".trp-x:has-text('파일로 저장')")
            text = Path(dl.value.path()).read_text("utf-8")
            assert text.startswith("[수정이 필요한 초안] 아이와 원도심 박물관 1박 2일")
            assert "구간 직선거리: 전체 이동거리 계산 안 됨(2개 구간 중 1개만 거리 있음)" in text and "· 사이트가 넣음]" in text
            # one-tap fixes: each sends the edit request with fixed words and the plan on screen
            assert page.locator(".trp-qfix .trp-qf").all_text_contents() == ["휴무 장소 바꾸기", "이동 구간 다시 짜기", "빠진 점심 넣기", "빈 시간 채우기"]
            page.click(".trp-qf[data-fix=gaps]")
            page.wait_for_function("() => document.querySelector('[data-plan-work]').hidden")
            e = calls[-1]
            assert e["request"] == "비어 있는 시간에 가까운 장소를 넣어 주세요" and e["conditions"] == calls[0]["conditions"]
            assert [s["page"] for s in e["plan"]["days"][0]["stops"]] == paths
            page.click(".trp-qf[data-fix=meal]")
            page.wait_for_function("() => document.querySelector('[data-plan-work]').hidden")
            assert calls[-1]["request"] == "빠진 점심을 그 시간에 여는 가까운 음식점으로 넣어 주세요"
            assert page.evaluate("() => document.documentElement.scrollWidth") <= 390
            assert errors == [], errors
            ctx.close()
        finally:
            browser.close()


def test_in_a_browser_a_finished_plan_reads_as_finished(site):
    """Operator 2026-10-18 ('이런 거 좀 안 뜨게 할 수 없어? 무조건 완성된 결과가 나오게'): a plan that breaks nothing reads
    as a finished course. What holds for any plan (planned margins, a hub's leg, a stay's booking — finish 'aware') and
    what the data does not say (finish 'checks') sit in one closed box, '가기 전에 알아 둘 것', never on top as something
    left to check; what the site put right itself is not listed; no '초안', no '?' mark."""
    sync_api = pytest.importorskip("playwright.sync_api")
    paths = plan_paths(site)
    plan = a_plan(paths)
    plan["days"][0]["legs"][1].update({"gap": 10, "flag": ""})
    plan.update({"status": "ready", "flags": [], "todo": [],
                 "checks": [{"k": "need", "t": "유모차: b — 출입구 접근 정보 없음"}],
                 "aware": [{"k": "move", "t": "장소 사이 시간은 계획상 여유이고, 실제 이동 시간은 확인되지 않음(직선거리만 있음)"},
                           {"k": "stay", "t": "d: 체크인 15:00(사이트 값) — 객실·예약은 숙소에 확인"}]})
    calls: list = []
    serve = server(site, plan, calls, {"next": [sse({"type": "plan", "plan": plan})]})
    with sync_api.sync_playwright() as p:
        try:
            browser = p.chromium.launch()
        except Exception as ex:  # noqa: BLE001 — Chromium is not installed here
            pytest.skip(f"Chromium 없음: {ex}")
        try:
            ctx = browser.new_context(viewport={"width": 390, "height": 844}, locale="ko-KR")
            ctx.route("**/*", serve)
            page = ctx.new_page()
            errors: list[str] = []
            page.on("pageerror", lambda e: errors.append(str(e)))
            page.goto("http://site.test/plan/", wait_until="load")
            page.click(".trp-submit")
            page.wait_for_selector("#h-result")
            assert "is-ok" in page.get_attribute(".trp-status", "class")
            assert page.text_content(".trp-status h3").endswith("완성된 코스예요")
            assert page.text_content(".trp-r-head .trp-eyebrow") == "AI가 짜고 사이트 자료와 코드로 검사한 코스"
            res = page.text_content(".trp-result")
            for word in ("초안", "바로잡은", "가기 전에 확인할 것", "확인할 것이 남은"):
                assert word not in res, word
            assert page.locator(".trp-st4 li.is-check, .trp-st4 li.is-bad, .trp-flags, .trp-qfix, .trp-top, .trp-fixed").count() == 0
            assert page.locator(".trp-mark").all_text_contents().count("?") == 0
            # the box: closed, the data's gaps and what holds for any plan, by kind
            box = page.locator("details#trp-checks")
            assert box.count() == 1 and box.get_attribute("open") is None
            assert page.text_content("#trp-checks summary").strip() == "가기 전에 알아 둘 것"
            assert page.locator("#trp-checks .trp-qg h4").all_text_contents() == ["필요한 조건", "숙소", "이동"]
            page.click("#trp-checks summary")
            assert page.is_visible("#trp-checks .trp-qs") and "객실·예약은 숙소에 확인" in page.text_content("#trp-checks")
            with page.expect_download() as dl:
                page.click(".trp-x:has-text('파일로 저장')")
            text = Path(dl.value.path()).read_text("utf-8")
            assert text.startswith("아이와 원도심 박물관 1박 2일") and "상태: 완성된 코스예요" in text
            assert "가기 전에 알아 둘 것:\n- 유모차: b — 출입구 접근 정보 없음\n- 장소 사이 시간은 계획상 여유" in text
            assert "\n- d: 체크인 15:00(사이트 값) — 객실·예약은 숙소에 확인" in text
            assert "바로잡은" not in text and "초안" not in text
            assert page.evaluate("() => document.documentElement.scrollWidth") <= 390
            assert errors == [], errors
            ctx.close()
        finally:
            browser.close()


PROBLEMS = {"code": "conditions", "message": "이 조건으로는 코스를 끝까지 짤 수 없어요. 아래를 바꿔 주세요.", "problems": [
    {"field": "needs", "text": "10월 24일(토)에 여는 곳 가운데 '휠체어'에 맞는다고 자료에 있는 곳이 1곳뿐이라 하루를 채울 수 없어요.",
     "fixes": [{"label": "'휠체어' 조건 빼기", "set": {"needs": []}}]},
    {"field": "date", "text": "다른 날을 고르면 짤 수 있을 수 있어요.", "fixes": [{"label": "날짜 바꾸기", "focus": "date"}]}]}


@pytest.mark.parametrize("width", [390, 1440])
def test_in_a_browser_conditions_no_plan_can_meet_are_said_by_the_button_with_their_fixes(site, width):
    """Operator 2026-10-18 ('문제가 있으면 아예 생성 버튼 누르는 단계에서 지적을 하고'): the planner's preflight answers
    422 {code: 'conditions', problems} before any model call — the page stays on the form, says why right above the
    button and offers the fixes; a fix sets the form (the summary follows) and the next press sends the new conditions.
    The same comes as an SSE error at the end; a hand change makes the box go. No failure page, no working view."""
    sync_api = pytest.importorskip("playwright.sync_api")
    paths = plan_paths(site)
    plan = a_plan(paths)
    plan.update({"status": "ready", "flags": [], "todo": []})
    plan["days"][0]["legs"][1].update({"gap": 10, "flag": ""})
    calls: list = []
    script = {"next": [(422, PROBLEMS), sse({"type": "plan", "plan": plan}),
                       sse({"type": "status", "step": "search", "text": "…"}, {"type": "error", **PROBLEMS})]}
    serve = server(site, plan, calls, script)
    with sync_api.sync_playwright() as p:
        try:
            browser = p.chromium.launch()
        except Exception as ex:  # noqa: BLE001 — Chromium is not installed here
            pytest.skip(f"Chromium 없음: {ex}")
        try:
            ctx = browser.new_context(viewport={"width": width, "height": 844}, locale="ko-KR",
                                      is_mobile=width < 900, has_touch=width < 900)
            ctx.route("**/*", serve)
            page = ctx.new_page()
            errors: list[str] = []
            page.on("pageerror", lambda e: errors.append(str(e)))
            page.goto("http://site.test/plan/", wait_until="load")
            page.click('label.trp-card:has(input[name="needs"][value="wheelchair"])')
            assert "휠체어" in page.text_content("[data-plan-sum]")
            page.click(".trp-submit")
            page.wait_for_selector(".trp-prob:not([hidden])")
            assert calls[0]["conditions"]["needs"] == ["wheelchair"]
            # the form, not a failure page; the working view is gone; the box sits right above the button's bar
            assert page.locator("#h-result").count() == 0 and page.locator(".trp-fail").count() == 0
            page.wait_for_function("() => document.querySelector('[data-plan-work]').hidden")
            assert page.evaluate("() => document.querySelector('.trp-prob').nextElementSibling.classList.contains('trp-go')")
            assert page.get_attribute(".trp-prob", "role") == "alert"
            assert page.evaluate("() => document.activeElement.matches('.trp-prob h3')")
            assert page.text_content(".trp-prob h3") == "이 조건으로는 코스를 끝까지 짤 수 없어요"
            assert page.text_content(".trp-prob-m") == "아래를 바꿔 주세요."
            assert page.locator(".trp-prob-l > li").count() == 2
            assert "'휠체어'에 맞는다고 자료에 있는 곳이 1곳뿐" in page.text_content(".trp-prob-l")
            assert page.locator(".trp-prob-fix").all_text_contents() == ["'휠체어' 조건 빼기", "날짜 바꾸기"]
            box = page.locator(".trp-prob").bounding_box()
            assert box["y"] >= 0 and box["y"] < 844 and box["width"] <= width
            assert page.evaluate("() => document.documentElement.scrollWidth") <= width
            # a fix that puts the cursor on a field
            page.click(".trp-prob-fix:has-text('날짜 바꾸기')")
            assert page.evaluate("() => document.activeElement.name") == "date"
            # a fix that sets the form: the box says what changed and offers to make the plan with it
            page.click(".trp-prob-fix:has-text('조건 빼기')")
            assert not page.is_checked('input[name="needs"][value="wheelchair"]')
            assert "휠체어" not in page.text_content("[data-plan-sum]")
            assert page.text_content(".trp-prob-done") == "조건을 바꿨어요. 바꾼 조건은 아래 요약 줄에 있어요."
            assert page.is_visible(".trp-prob-go") and page.evaluate("() => document.activeElement.matches('.trp-prob-go')")
            # in view and clear of the button's bar (on phones it stays at the screen's foot)
            assert page.evaluate("""() => { const g = document.querySelector('.trp-prob-go').getBoundingClientRect();
              const bar = document.querySelector('.trp-go').getBoundingClientRect();
              return g.top >= 0 && (g.bottom <= bar.top || getComputedStyle(document.querySelector('.trp-go')).position !== 'sticky'); }""")
            page.click(".trp-prob-go")
            page.wait_for_selector("#h-result")
            assert calls[1]["conditions"]["needs"] == []
            assert page.is_hidden(".trp-prob")
            # the same at the end of a stream; a change by hand makes the box go
            page.click(".trp-submit")
            page.wait_for_selector(".trp-prob:not([hidden])")
            page.click('label.trp-card:has(input[name="prefs"][value="food"])')
            assert page.is_hidden(".trp-prob")
            assert errors == [], errors
            ctx.close()
        finally:
            browser.close()


def test_in_a_browser_a_plan_the_site_built_itself_says_so_and_a_change_that_cannot_be_finished_keeps_the_plan(site):
    """When the AI gives no plan it can use, the planner sends one built from the site's data (one 'fixed' line starting
    '일정 전체:', every stop put in by the site): the page says so above the course, not 'AI가 짜고' and not '빈 시간이
    길어 사이트가 넣은 곳' on every stop. A change the planner cannot finish ('edit_failed') keeps the plan on screen."""
    sync_api = pytest.importorskip("playwright.sync_api")
    paths = plan_paths(site)
    plan = a_plan(paths)
    plan["days"][0]["legs"][1].update({"gap": 10, "flag": ""})
    for d in plan["days"]:
        for st in d["stops"]:
            st.update({"added": True, "why": ""})
    plan.update({"status": "ready", "flags": [], "todo": [], "notes": [], "summary": "원도심 박물관을 돕니다.",
                 "fixed": ["일정 전체: AI 응답을 받지 못해 사이트 자료로 일정을 짰습니다"]})
    calls: list = []
    msg = "요청한 변경으로는 코스를 끝까지 맞출 수 없어 보던 일정을 그대로 두었습니다. 요청을 조금 바꿔 다시 시도해 주세요."
    script = {"next": [sse({"type": "plan", "plan": plan}), sse({"type": "error", "code": "edit_failed", "message": msg})]}
    serve = server(site, plan, calls, script)
    with sync_api.sync_playwright() as p:
        try:
            browser = p.chromium.launch()
        except Exception as ex:  # noqa: BLE001 — Chromium is not installed here
            pytest.skip(f"Chromium 없음: {ex}")
        try:
            ctx = browser.new_context(viewport={"width": 390, "height": 844}, locale="ko-KR")
            ctx.route("**/*", serve)
            page = ctx.new_page()
            errors: list[str] = []
            page.on("pageerror", lambda e: errors.append(str(e)))
            page.goto("http://site.test/plan/", wait_until="load")
            page.click(".trp-submit")
            page.wait_for_selector("#h-result")
            assert page.text_content(".trp-r-head .trp-eyebrow") == "사이트 자료로 짜고 코드로 검사한 코스"
            assert page.text_content(".trp-r-code") == "사이트 AI 응답을 받지 못해 사이트 자료로 일정을 짰어요"
            assert page.locator(".trp-by").count() == 0
            assert page.text_content(".trp-foot").startswith("사이트 자료로 고른 순서와 시각을")
            with page.expect_download() as dl:
                page.click(".trp-x:has-text('파일로 저장')")
            text = Path(dl.value.path()).read_text("utf-8")
            assert "사이트가 넣음" not in text and "AI(Claude)가 고른" not in text
            name = json.loads((SAMPLE / "site.json").read_text("utf-8"))["site_name"]   # the page's data-site-name
            assert f"AI 응답을 받지 못해 사이트 자료로 일정을 짰어요. {name}(" in text
            # a change that cannot be finished: the plan stays, the message sits above the edit box
            page.fill("#trp-ask", "비 오면 실내로 바꿔 주세요")
            page.click(".trp-edit-f button[type=submit]")
            page.wait_for_selector(".trp-fail-edit")
            assert msg in page.text_content(".trp-fail-edit") and page.text_content("#h-result") == plan["title"]
            assert page.locator(".trp-prob:not([hidden])").count() == 0
            assert errors == [], errors
            ctx.close()
        finally:
            browser.close()


def test_in_a_browser_an_address_starts_from_the_defaults_and_never_shows_what_the_form_could_not(site):
    """The review of the hand-over (2026-10-18): conditions in the address were laid over the tab's kept conditions and
    its plan stayed on screen under them; with=solo&adults=3 showed three people travelling alone. Now the address
    starts from the form's defaults, the kept plan is not shown, a reload comes back to the address's conditions, and
    who comes and how many follow the rules the form's own buttons keep."""
    sync_api = pytest.importorskip("playwright.sync_api")
    paths = plan_paths(site)
    plan = a_plan(paths)
    calls: list = []
    serve = server(site, plan, calls, {"next": []})
    with sync_api.sync_playwright() as p:
        try:
            browser = p.chromium.launch()
        except Exception as ex:  # noqa: BLE001 — Chromium is not installed here
            pytest.skip(f"Chromium 없음: {ex}")
        try:
            ctx = browser.new_context(viewport={"width": 390, "height": 844}, locale="ko-KR")
            ctx.route("**/*", serve)
            page = ctx.new_page()
            errors: list[str] = []
            page.on("pageerror", lambda e: errors.append(str(e)))

            def who():
                return (page.eval_on_selector('input[name="with"]:checked', "e => e.value"),
                        page.text_content('[data-count="adults"] [data-count-value]'),
                        page.text_content('[data-count="seniors"] [data-count-value]'),
                        [page.input_value(f"[data-ages] select >> nth={i}") for i in range(page.locator("[data-ages] select").count())])
            # a plan made in this tab, with likings and a budget
            page.goto("http://site.test/plan/", wait_until="load")
            for v in ("history", "food"):
                page.click(f'label.trp-card:has(input[name="prefs"][value="{v}"])')
            page.click('[data-budget="10000"]')
            page.click(".trp-submit")
            page.wait_for_selector("#h-result")
            # the hand-over: the form's defaults with the address's values; the kept plan is not shown under them
            page.goto("http://site.test/plan/?move=car&prefs=nature", wait_until="load")
            page.wait_for_timeout(300)
            assert page.locator("#h-result").count() == 0 and page.get_attribute("[data-plan]", "data-prefilled") == ""
            assert page.is_checked('input[name="move"][value="car"]')
            assert page.eval_on_selector_all('input[name="prefs"]:checked', "els => els.map(e => e.value)") == ["nature"]
            assert page.input_value("input[name=budget]") == "" and who() == ("couple", "2", "0", [])
            assert page.url == "http://site.test/plan/"                    # the address is spent: a reload keeps these
            page.reload(wait_until="load")
            page.wait_for_timeout(300)
            assert page.locator("#h-result").count() == 0 and page.is_checked('input[name="move"][value="car"]')
            assert page.eval_on_selector_all('input[name="prefs"]:checked', "els => els.map(e => e.value)") == ["nature"]
            # who comes and how many, as the form's buttons keep them
            page.goto("http://site.test/plan/?with=solo&adults=3&seniors=2", wait_until="load")
            assert who() == ("solo", "1", "1", [])
            assert "혼자(어른 1(65세 이상 1))" in page.text_content("[data-plan-sum]")
            assert page.locator('input[name="prefs"]:checked').count() == 0 and page.is_checked('input[name="move"][value="transit"]')
            page.goto("http://site.test/plan/?with=solo&kids=8", wait_until="load")
            assert who() == ("kids", "2", "0", ["8"])
            page.goto("http://site.test/plan/?with=couple&adults=1&kids=5,3", wait_until="load")
            assert who() == ("kids", "1", "0", ["5", "3"])
            page.goto("http://site.test/plan/?with=kids", wait_until="load")
            assert who() == ("kids", "2", "0", ["7"])
            page.click(".trp-submit")
            page.wait_for_selector("#h-result")
            c = calls[-1]["conditions"]
            assert (c["with"], c["adults"], c["seniors"], c["kids"]) == ("kids", 2, 0, [7])
            assert errors == [], errors
            ctx.close()
        finally:
            browser.close()


PHONE = {"is_mobile": True, "has_touch": True}


@pytest.mark.parametrize("dev", [pytest.param({"viewport": {"width": 360, "height": 740}, **PHONE}, id="360"),
                                 pytest.param({"viewport": {"width": 375, "height": 667}, **PHONE}, id="375"),
                                 pytest.param({"viewport": {"width": 390, "height": 844}, **PHONE}, id="390"),
                                 pytest.param({"viewport": {"width": 1440, "height": 900}}, id="1440")])
def test_in_a_browser_a_hand_over_lands_on_the_form_under_a_line_that_says_so(site, dev):
    """Review 2026-10-18, fourth round: the assistant's hand-over opened /plan/ at its top, the filled form out of sight.
    Now the page opens at the form, under one line in a status region ('대화에서 말한 조건을 채웠어요 …', read out: its
    words come after it is in the page); nothing is sent. A plain visit has no line, stays at the top and moves
    nothing (no layout shift). The line's room is laid out from the first paint (plan.html.j2's head script marks
    <html> when the address carries the form's keys): here plan.js comes well after the paint, as on a slow phone, and
    its words move nothing (put in after the paint, the line pushed the form down: CLS 0.11–0.13 at 360–390px)."""
    sync_api = pytest.importorskip("playwright.sync_api")
    import time
    calls: list = []
    serve = server(site, a_plan(plan_paths(site)), calls, {"next": []})

    def slow(route):   # plan.js arrives after the first paint
        if route.request.url.endswith("/assets/plan.js"):
            time.sleep(0.4)
        serve(route)
    shifts = """() => new Promise(r => { let s = 0; new PerformanceObserver(l => { for (const e of l.getEntries()) s += e.value; })
      .observe({ type: 'layout-shift', buffered: true }); setTimeout(() => r(s), 400); })"""
    with sync_api.sync_playwright() as p:
        try:
            browser = p.chromium.launch()
        except Exception as ex:  # noqa: BLE001 — Chromium is not installed here
            pytest.skip(f"Chromium 없음: {ex}")
        try:
            ctx = browser.new_context(**dev, locale="ko-KR")
            ctx.route("**/*", slow)
            page = ctx.new_page()
            errors: list[str] = []
            page.on("pageerror", lambda e: errors.append(str(e)))
            page.goto("http://site.test/plan/", wait_until="load")
            assert page.evaluate(shifts) == 0
            assert page.locator(".trp-handed").is_hidden() and page.evaluate("scrollY") == 0
            assert page.evaluate("document.querySelector('.trp-handed-w').getBoundingClientRect().height") == 0
            page.goto("http://site.test/plan/?days=2&move=car&needs=rain", wait_until="commit")
            # the room is there before plan.js; the words come with it
            page.wait_for_selector("[data-plan-form]", state="attached")
            assert page.evaluate("document.documentElement.classList.contains('trp-handing')")
            line = page.locator(".trp-handed")
            page.wait_for_function("document.querySelector('.trp-handed').textContent !== ''")
            assert line.get_attribute("role") == "status"
            assert line.text_content() == "대화에서 말한 조건을 채웠어요. 확인하고 코스 만들기를 누르세요."
            assert page.locator(".trp-handed-ghost").get_attribute("aria-hidden") == "true"
            page.wait_for_timeout(200)
            assert page.evaluate(shifts) == 0
            box = line.bounding_box()
            mast = page.evaluate("document.querySelector('.mast').getBoundingClientRect().bottom")
            assert page.evaluate("scrollY") > 0 and mast <= box["y"] <= mast + 60, (box, mast)
            # the line sits right above the form's first step, both in view
            step = page.locator(".trp-step").first.bounding_box()
            assert box["y"] + box["height"] <= step["y"] < dev["viewport"]["height"] - 100, (box, step)
            assert page.is_checked('input[name="days"][value="2"]') and page.is_checked('input[name="needs"][value="rain"]')
            assert calls == [] and page.locator("[data-plan-work]").is_hidden()
            assert page.evaluate("() => document.documentElement.scrollWidth") <= dev["viewport"]["width"]
            # keys the form has no choice for: no line, no room
            page.goto("http://site.test/plan/?days=9", wait_until="load")
            page.wait_for_function("!document.documentElement.classList.contains('trp-handing')")
            assert page.locator(".trp-handed").is_hidden() and page.locator(".trp-handed").text_content() == ""
            assert errors == [], errors
            ctx.close()
        finally:
            browser.close()
