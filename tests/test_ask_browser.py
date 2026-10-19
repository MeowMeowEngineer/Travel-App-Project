"""Asking from the homes in a real browser (Playwright + Chromium): a sample build with a starter file, served locally
together with a fake /api/chat/ that streams its answer over about a second (SSE) or answers 503 not_configured.

The Korean home (owner 2026-10-13 night: '이 상자를 챗봇 질문창으로'; UI4 2026-10-14: the white question card under the
light opening; owner 2026-10-14: '페이지 상단에는 검색, 중앙 부분에는 AI챗봇으로 확실히 구분'): the card is the assistant
only — its box sits in a 390×844 and a 1440×900 first screen — and the conversation opens in its own panel right under
the card. Asking from the box at 390
and 1440 shows the panel at once and brings it into view, the streamed answer, its checked link and link card come in
the panel (announced once) while nothing above the panel moves and nothing below it moves while it streams, and the
floating panel is never built there; the panel's own box asks the next question into the same conversation; a starter
asks (with a modifier key it stays a link); an Enter the input method keeps (a conversion) and an empty box ask
nothing, in either box, while the Enter that ends a Korean syllable asks at once — on the page served as the public
host (site.json site_url) too (the 2026-10-14 bug: that Enter was swallowed); the button stops an answer; the
header's search goes to /search/?q= (desktop: its field; phones: '검색' opens it over the bar; without JS a link);
Korean + not_configured lands on /search/?q=…; without
chat.js the box searches and a starter follows its link; the launcher is there from the first paint (390 and 1440),
puts the focus in the box (or in the open conversation's own box) and never steps aside (owner 2026-10-14);
the same conversation shows in the floating panel on another page; nothing of the chat loads and nothing shifts while
the page loads (fonts already cached, as on any second page); no console errors. Skipped where Playwright or its
Chromium is missing."""
import functools
import http.server
import json
import mimetypes
import shutil
import threading
import time
from pathlib import Path
from urllib.parse import parse_qs, unquote, urlsplit

import pytest

from pipeline.build import build

sync_api = pytest.importorskip("playwright.sync_api")

ROOT = Path(__file__).resolve().parent.parent
SAMPLE = ROOT / "data" / "sample"
SITE = json.loads((SAMPLE / "site.json").read_text("utf-8"))["site_url"]   # the public address chat.js reads (data-chat-site)
STARTERS = {"starters": [{"q": {"ko": "차 없이 하루 여행", "en": "A day without a car"}, "guide": "guide-sample-1"},
                         {"q": {"ko": "이번 달 행사", "en": "Events this month"}, "page": "events"}]}
ANSWER = ("은파호수공원은 쉬는 날 없이 열려 있습니다. [은파호수공원](/places/eunpa-lake-park/)\n\n"
          "- 시간: 상시 개방\n- 주차: 가능 — **무료**\n\n[없는 페이지](/places/nowhere/)")
DONE = {"type": "done", "links": [{"title": "은파호수공원", "url": f"{SITE}/places/eunpa-lake-park/", "ext": False}],
        "fix": {"/places/eunpa-lake-park/": f"{SITE}/places/eunpa-lake-park/", "/places/nowhere/": None}}
API = {"mode": "ok", "gap": 0.06, "calls": []}
BUILT = {}
PUBLIC = SITE   # the public host (site.json site_url); served here through page routes
SHIFTS = """window.__ls = []; new PerformanceObserver(l => { for (const e of l.getEntries()) window.__ls.push({v: e.value,
  input: e.hadRecentInput, t: e.startTime, src: (e.sources || []).map(s => s.node && s.node.className || '')}); })
  .observe({type: 'layout-shift', buffered: true});"""


def sse(event) -> bytes:
    return f"data: {json.dumps(event, ensure_ascii=False)}\n\n".encode("utf-8")


class Site(http.server.SimpleHTTPRequestHandler):
    """The static build, plus POST /api/chat/: a streamed answer (a chunk every API['gap'] seconds) or a 503."""

    def log_message(self, *args):
        return None

    def do_POST(self):
        body = self.rfile.read(int(self.headers.get("Content-Length") or 0))
        if self.path != "/api/chat/":
            self.send_error(404)
            return
        API["calls"].append(json.loads(body or b"{}"))
        try:
            if API["mode"] == "503":
                out = b'{"code":"not_configured"}'
                self.send_response(503)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(out)))
                self.end_headers()
                self.wfile.write(out)
                return
            self.send_response(200)
            self.send_header("Content-Type", "text/event-stream; charset=utf-8")
            self.end_headers()
            self.wfile.write(sse({"type": "status", "text": "찾는 중: 은파호수공원"}))
            self.wfile.flush()
            for i in range(0, len(ANSWER), 8):
                time.sleep(API["gap"])
                self.wfile.write(sse({"type": "text", "delta": ANSWER[i:i + 8]}))
                self.wfile.flush()
            self.wfile.write(sse(DONE))
            self.wfile.flush()
        except (BrokenPipeError, ConnectionResetError, ConnectionAbortedError):
            pass   # the reader stopped the answer


class Server(http.server.ThreadingHTTPServer):
    def handle_error(self, request, client_address):   # a tab closed while a file was still being sent
        return None


@pytest.fixture(scope="module")
def site(tmp_path_factory):
    tmp = tmp_path_factory.mktemp("askweb")
    data = tmp / "data"
    shutil.copytree(SAMPLE, data)
    (data / "ask.json").write_text(json.dumps(STARTERS, ensure_ascii=False), "utf-8")
    out = tmp / "out"
    build(data, out, "sample")
    BUILT["out"] = out
    srv = Server(("127.0.0.1", 0), functools.partial(Site, directory=str(out)))
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    yield f"http://127.0.0.1:{srv.server_address[1]}"
    srv.shutdown()


@pytest.fixture(scope="module")
def browser():
    with sync_api.sync_playwright() as p:
        try:
            b = p.chromium.launch()
        except sync_api.Error as err:
            pytest.skip(f"Chromium is not installed for Playwright: {err}")
        yield b
        b.close()


def open_home(browser, site, width, height, mode="ok", gap=0.06, reduced="no-preference"):
    """A fresh tab whose fonts are already cached (one page first), then the home. Returns (ctx, page, errors)."""
    API.update(mode=mode, gap=gap, calls=[])
    ctx = browser.new_context(viewport={"width": width, "height": height}, locale="ko-KR", reduced_motion=reduced)
    page = ctx.new_page()
    errors = []
    page.on("console", lambda m: errors.append(m.text) if m.type == "error" else None)
    page.on("pageerror", lambda e: errors.append(str(e)))
    page.add_init_script(SHIFTS)
    page.goto(site + "/about/")
    page.evaluate("document.fonts.ready.then(() => 1)")
    page.goto(site + "/")
    page.wait_for_load_state("load")
    page.wait_for_timeout(500)
    return ctx, page, errors


def doc_top(page, sel):
    return page.evaluate(f"Math.round(document.querySelector('{sel}').getBoundingClientRect().top + window.scrollY)")


def in_viewport(page, sel):
    return page.evaluate(f"""(() => {{ const r = document.querySelector('{sel}').getBoundingClientRect();
      return r.top >= -1 && r.bottom <= window.innerHeight + 1; }})()""")


def korean_enter(page, syllable):
    """Enter pressed while a Korean input method still composes the last syllable, as Chrome delivers it (CDP): a
    keydown 229 that the input method keeps (it commits the syllable: compositionend), then the reader's own Enter a
    few milliseconds later — the Enter the 2026-10-14 bug swallowed."""
    cdp = page.context.new_cdp_session(page)
    cdp.send("Input.imeSetComposition", {"text": syllable, "selectionStart": 1, "selectionEnd": 1})
    cdp.send("Input.dispatchKeyEvent", {"type": "rawKeyDown", "key": "Enter", "code": "Enter",
                                        "windowsVirtualKeyCode": 229, "nativeVirtualKeyCode": 229})
    cdp.send("Input.insertText", {"text": syllable})
    page.keyboard.press("Enter")
    cdp.detach()


def converting_enter(page, text):
    """Enter pressed to confirm an input method's conversion (Japanese, Chinese): the key comes while composing (and
    headless Chromium would even submit the form with it), then the text is committed."""
    cdp = page.context.new_cdp_session(page)
    cdp.send("Input.imeSetComposition", {"text": text, "selectionStart": len(text), "selectionEnd": len(text)})
    page.keyboard.press("Enter")
    cdp.send("Input.insertText", {"text": text})
    cdp.detach()


def open_public(browser, width, height, js=True):
    """The sample build served as the public host (every request answered here, nothing leaves the machine), its
    /api/chat/ a scripted SSE answer that records each request. Returns (ctx, page, errors, requests)."""
    out, requests = BUILT["out"], []

    def files(route):
        path = unquote(urlsplit(route.request.url).path)
        f = out / path.lstrip("/")
        if f.is_dir():
            f = f / "index.html"
        if not f.is_file():
            return route.fulfill(status=404, body="")
        route.fulfill(status=200, body=f.read_bytes(), content_type=mimetypes.guess_type(f.name)[0] or "application/octet-stream")

    def api(route):
        r = route.request
        requests.append({"url": r.url, "method": r.method, "origin": r.header_value("origin"), "body": r.post_data_json})
        body = sse({"type": "status", "text": "찾는 중: 은파호수공원"}) + b"".join(
            sse({"type": "text", "delta": ANSWER[i:i + 8]}) for i in range(0, len(ANSWER), 8)) + sse(DONE)
        route.fulfill(status=200, body=body, headers={"content-type": "text/event-stream; charset=utf-8"})

    ctx = browser.new_context(viewport={"width": width, "height": height}, locale="ko-KR", java_script_enabled=js)
    ctx.route("**/*", lambda route: route.abort())
    ctx.route(f"{PUBLIC}/**", files)
    ctx.route(f"{PUBLIC}/api/chat/", api)
    page = ctx.new_page()
    errors = []
    page.on("console", lambda m: errors.append(m.text) if m.type == "error" else None)
    page.on("pageerror", lambda e: errors.append(str(e)))
    page.goto(PUBLIC + "/")
    page.wait_for_load_state("load")
    return ctx, page, errors, requests


@pytest.mark.parametrize("width,height", [(390, 844), (1440, 900)])
def test_enter_asks_on_the_public_host(browser, site, width, height):
    """Owner 2026-10-14: '궁금한 것을 적어주세요 칸에 뭘 입력하고 엔터를 쳤을 때도 반응이 없고'. On the page served as
    the public host: typed words + Enter ask (a same-origin POST to /api/chat/, the Origin the server's
    allow-list checks) and the answer is drawn under the card; then a Korean question whose last syllable is still
    composing when Enter goes down asks at once — the case the old 50 ms guard after compositionend swallowed."""
    ctx, page, errors, requests = open_public(browser, width, height)
    page.locator("#ask-q").press_sequentially("은파 주차")
    page.keyboard.press("Enter")
    page.wait_for_selector("[data-ask-log] .chat-a .chat-card")
    assert len(requests) == 1 and requests[0]["url"] == f"{PUBLIC}/api/chat/" and requests[0]["method"] == "POST"
    assert requests[0]["origin"] == PUBLIC   # chatbot/server.js allowedOrigins must hold this host
    assert requests[0]["body"]["messages"] == [{"role": "user", "content": "은파 주차"}] and requests[0]["body"]["page"] == "/"
    md = page.locator("[data-ask-log] .chat-a .chat-md")
    assert "은파호수공원은 쉬는 날 없이" in md.inner_text() and page.url == PUBLIC + "/"
    page.wait_for_function("document.querySelector('[data-ask-go]').getAttribute('data-mode') !== 'stop'")
    # Korean: '…되나' typed, '요' still composing when Enter goes down — one Enter asks
    page.click(".ask-new")
    page.locator("#ask-q").press_sequentially("은파호수공원 주차 되나")
    korean_enter(page, "요")
    page.wait_for_function("document.querySelectorAll('[data-ask-log] .chat-a .chat-card').length === 1")
    assert len(requests) == 2 and requests[1]["body"]["messages"] == [{"role": "user", "content": "은파호수공원 주차 되나요"}]
    assert page.input_value("#ask-q") == "" and page.url == PUBLIC + "/"
    assert errors == []
    ctx.close()


def test_the_header_searches_on_every_page(browser, site):
    """The site search is the bar's (owner 2026-10-14: '페이지 상단에는 검색'). 1440: the field is in the bar of the home
    and of a place page; words + Enter go to /search/?q=, where search.js answers; no '물어보기' in the bar. 390: '검색'
    opens the same form over the bar — the bar keeps its 52px (the fixed area stays ≤ 15% of the screen) — with the
    focus in the field; Escape closes it and gives the focus back to '검색'; the round button searches. Without JS
    '검색' is a link to /search/."""
    ctx, page, errors, _ = open_public(browser, 1440, 900)
    for path in ("/", "/places/eunpa-lake-park/"):
        page.goto(PUBLIC + path)
        field = page.locator(".mast #hs-q")
        assert field.is_visible() and field.get_attribute("placeholder") == "장소·음식·지역 검색"
        assert page.locator(".mast-search").is_hidden() and page.locator(".mast [data-chat-open]").count() == 0
    field.fill("은파")
    field.press("Enter")
    page.wait_for_url("**/search/?q=*")
    assert parse_qs(urlsplit(page.url).query)["q"] == ["은파"]
    page.wait_for_selector("[data-results] a")
    assert "은파호수공원" in page.inner_text("[data-results]") and page.locator(".mast .hs").count() == 0
    assert errors == []
    ctx.close()
    ctx, page, errors, _ = open_public(browser, 390, 844)
    bar = page.locator(".mast").bounding_box()["height"]
    assert page.locator(".mast #hs-q").is_hidden()
    toggle = page.locator(".mast-search")
    assert toggle.get_attribute("role") == "button" and toggle.get_attribute("aria-expanded") == "false"
    toggle.click()
    assert page.locator(".mast #hs-q").is_visible() and page.evaluate("document.activeElement.id") == "hs-q"
    assert toggle.get_attribute("aria-expanded") == "true"
    assert page.locator(".mast").bounding_box()["height"] == bar == 52 and bar / 844 <= 0.15
    for sel in (".mast .hs-f", ".mast .hs-go", ".mast .hs-x"):
        box = page.locator(sel).bounding_box()
        assert box["height"] >= 40 and box["y"] >= 0 and box["y"] + box["height"] <= bar, sel
    page.keyboard.press("Escape")
    assert page.locator(".mast #hs-q").is_hidden() and page.evaluate("document.activeElement.className") == "mast-search"
    toggle.click()
    page.keyboard.type("짬뽕")
    page.click(".mast .hs-go")
    page.wait_for_url("**/search/?q=*")
    assert parse_qs(urlsplit(page.url).query)["q"] == ["짬뽕"]
    assert errors == []
    ctx.close()
    ctx, page, errors, _ = open_public(browser, 390, 844, js=False)
    page.click(".mast-search")
    page.wait_for_url(f"{PUBLIC}/search/")
    ctx.close()


@pytest.mark.parametrize("width,height", [(390, 844), (1440, 900)])
def test_the_opening_asks_and_the_panel_below_answers(browser, site, width, height):
    ctx, page, errors = open_home(browser, site, width, height)
    assert page.evaluate("window.__ls") == []                       # nothing shifts while the page loads
    assert not page.evaluate("!!window.gsChat")                      # nothing of the chat before the reader comes
    assert page.locator('link[href$="chat.css"]').count() == 0 and page.locator('script[src$="chat.js"]').count() == 0
    log = page.locator("[data-chat-dock] [data-ask-log]")
    assert log.is_hidden()
    # the box is in the question card, inside the first screen; the panel comes right under the card
    box = page.locator(".hk-box").bounding_box()
    assert box["y"] >= 0 and box["y"] + box["height"] <= height
    assert page.evaluate("document.querySelector('.hq').contains(document.getElementById('ask-q'))")
    assert page.evaluate("document.querySelector('.hq').nextElementSibling.matches('.hk-conv')")
    assert page.locator(".chat-fab").is_visible()                    # the launcher too, at load (owner 2026-10-14)
    later = ".foot"
    page.fill("#ask-q", "은파 주차")
    above = {s: doc_top(page, s) for s in ("#h-home", ".hk-box", ".hk-note")}
    page.press("#ask-q", "Enter")
    assert log.is_visible()                                          # at once, before chat.js has come
    page.wait_for_selector(".ask-log .chat-a .chat-md")              # the answer is streaming in
    page.wait_for_timeout(700 if width >= 700 else 600)             # the panel's smooth scroll has settled
    assert in_viewport(page, "[data-ask-log]")                       # brought into view
    during = {s: doc_top(page, s) for s in (*above, later)}
    go = page.locator("[data-ask-go]")
    assert go.inner_text() == "멈추기" and go.get_attribute("data-mode") == "stop"
    assert page.locator(".hk-box").get_by_role("button", name="멈추기", exact=True).count() == 1   # its name follows the label
    page.wait_for_selector(".ask-log .chat-a .chat-card")
    after = {s: doc_top(page, s) for s in (*above, later)}
    assert after == during and {s: after[s] for s in above} == above   # nothing above moves; nothing below while it streams
    assert API["calls"][-1]["messages"] == [{"role": "user", "content": "은파 주차"}] and API["calls"][-1]["page"] == "/"
    assert log.is_visible() and page.locator("#chat").count() == 0   # the panel below; the floating one is never built
    md = log.locator(".chat-a .chat-md")
    assert "주차: 가능 — 무료" in md.inner_text() and md.locator("a").count() == 1
    assert md.locator("a").get_attribute("href") == "/places/eunpa-lake-park/" and "없는 페이지" in md.inner_text()
    card = log.locator(".chat-card")
    assert card.count() == 1 and card.get_attribute("href") == "/places/eunpa-lake-park/"
    assert card.get_attribute("data-track") == "chat_link_click" and card.get_attribute("data-chat-where") == "dock"
    assert "대화" in log.locator(".ask-log-head").inner_text() and log.locator(".ask-new").inner_text() == "새 대화"
    assert log.locator(".ask-note").inner_text() == "AI가 이 사이트의 정보로 쓴 답입니다. 틀릴 수 있으니 방문 전에 확인하세요."
    page.wait_for_timeout(150)
    assert "은파호수공원은 쉬는 날 없이" in page.inner_text("[data-ask-log] [data-chat-live]")
    assert go.inner_text() == "물어보기" and page.input_value("#ask-q") == ""
    lh = log.bounding_box()["height"]
    assert (500 <= lh <= 600) if width >= 700 else (abs(lh - 0.7 * height) <= 4)   # a fixed height from the first paint
    # every shift after the page loaded is the reader's own (the panel opening on their Enter), none from the answer
    late = [e for e in page.evaluate("window.__ls") if not e["input"] and "chat-fab" not in e["src"]]
    assert late == []
    # the panel's own box asks the next question into the same conversation; its send button stops an answer
    API["gap"] = 0.2
    page.fill("#ask-q2", "주차 요금은요?")
    page.press("#ask-q2", "Enter")
    page.wait_for_selector(".ask-log .chat-u >> nth=1")
    send2 = log.locator(".ask-more .chat-send")
    assert send2.get_attribute("data-mode") == "stop" and go.get_attribute("data-mode") == "stop"
    msgs = API["calls"][-1]["messages"]
    assert [m["role"] for m in msgs] == ["user", "assistant", "user"] and msgs[-1]["content"] == "주차 요금은요?"
    send2.click()
    page.wait_for_selector(".ask-log .chat-note2")
    assert "답을 멈췄습니다" in log.locator(".chat-a").last.inner_text() and go.inner_text() == "물어보기"
    # '새 대화' empties the conversation and closes the panel; the focus goes back to the question box
    page.click(".ask-new")
    assert log.is_hidden() and page.evaluate("document.activeElement.id") == "ask-q"
    assert errors == []
    ctx.close()


def test_starters_ask_and_the_boxes_ignore_input_methods_and_empty_questions(browser, site):
    ctx, page, errors = open_home(browser, site, 1440, 900, gap=0.25)
    chip = page.locator(".hk-pill").first
    href = chip.get_attribute("href")
    assert href == "/guides/no-car-day-trip/" and chip.get_attribute("data-ask") == "차 없이 하루 여행"
    # with a modifier key a starter is a link (a new tab), and nothing is asked
    with ctx.expect_page() as other:
        chip.click(modifiers=["Control"])
    other.value.wait_for_url(lambda u: not u.startswith("about:"))   # a new tab starts at about:blank, then navigates
    other.value.wait_for_load_state()
    assert unquote(urlsplit(other.value.url).path) == href and API["calls"] == []
    other.value.close()
    # an Enter the input method keeps (a conversion) commits the text; an empty box only takes the focus — nothing
    # is asked
    page.fill("#ask-q", "은파 주")
    converting_enter(page, "차")
    page.wait_for_timeout(150)
    assert page.input_value("#ask-q") == "은파 주차" and page.url.rstrip("/") == site
    page.fill("#ask-q", "")
    page.click("[data-ask-go]")
    page.wait_for_timeout(150)
    assert API["calls"] == [] and page.evaluate("document.activeElement.id") == "ask-q"
    assert page.url.rstrip("/") == site and page.locator("[data-ask-log]").is_hidden()
    # a plain click asks the starter's question; the button (now '멈추기') stops the answer
    chip.click()
    page.wait_for_selector(".ask-log .chat-a .chat-md")
    assert API["calls"][-1]["messages"] == [{"role": "user", "content": "차 없이 하루 여행"}]
    assert page.url.rstrip("/") == site
    page.click("[data-ask-go]")
    page.wait_for_selector(".ask-log .chat-note2")
    assert "답을 멈췄습니다" in page.inner_text(".ask-log .chat-a") and page.inner_text("[data-ask-go]") == "물어보기"
    # the panel's own box: an Enter the input method keeps sends nothing either; the Enter that ends a Korean
    # syllable sends at once
    n = len(API["calls"])
    page.fill("#ask-q2", "다음 질")
    converting_enter(page, "문")
    page.wait_for_timeout(150)
    assert len(API["calls"]) == n and page.input_value("#ask-q2") == "다음 질문"
    page.fill("#ask-q2", "주차 요금은 얼마인가")
    korean_enter(page, "요")
    page.wait_for_function(f"document.querySelectorAll('.ask-log .chat-u').length === {n + 1}")
    assert API["calls"][-1]["messages"][-1] == {"role": "user", "content": "주차 요금은 얼마인가요"}
    assert page.locator("[data-ask-search]").count() == 0   # the card has no '검색': the search is the header's
    assert errors == []
    ctx.close()


def test_korean_box_without_the_api_key_is_the_site_search(browser, site):
    ctx, page, errors = open_home(browser, site, 390, 844, mode="503")
    page.fill("#ask-q", "은파호수공원 주차")
    page.click("[data-ask-go]")
    page.wait_for_url("**/search/?q=*")
    assert parse_qs(urlsplit(page.url).query)["q"] == ["은파호수공원 주차"] and len(API["calls"]) == 1
    # the failed exchange left the conversation: nothing of it comes back in the panel
    assert page.evaluate("JSON.parse(sessionStorage.getItem('gs-chat')).msgs") == []
    # Chromium logs the scripted 503 as a failed resource; nothing else may reach the console
    assert [e for e in errors if "status of 503" not in e] == []
    ctx.close()


def test_without_chat_js_the_box_searches_and_a_starter_follows_its_link(browser, site):
    ctx, page, errors = open_home(browser, site, 1440, 900)
    page.route("**/assets/chat.js", lambda route: route.abort())
    page.fill("#ask-q", "철길마을")
    page.press("#ask-q", "Enter")
    page.wait_for_url("**/search/?q=*")
    assert parse_qs(urlsplit(page.url).query)["q"] == ["철길마을"] and API["calls"] == []
    page.goto(site + "/")
    page.wait_for_load_state("load")
    page.locator(".hk-pill").first.click()
    page.wait_for_url("**/guides/no-car-day-trip/")
    page.wait_for_load_state("load")
    assert API["calls"] == []
    assert [e for e in errors if "ERR_FAILED" not in e] == []
    ctx.close()


@pytest.mark.parametrize("width,height", [(390, 844), (1440, 900)])
def test_the_launcher_is_there_from_the_start_and_goes_to_the_box(browser, site, width, height):
    ctx, page, errors = open_home(browser, site, width, height)
    fab = page.locator(".chat-fab")
    assert fab.is_visible()                                          # from the first paint, on the home too
    b = fab.bounding_box()
    assert b["height"] == (72 if width >= 1024 else 64) and b["y"] + b["height"] <= height - 16 and b["x"] + b["width"] <= width - 16
    assert fab.get_attribute("aria-haspopup") is None                # here it goes to the box, it opens no dialog
    # the label beside the face from 700px; from 1024px the round face alone (UI4, the reference's launcher: its label
    # a tooltip on hover and focus, still the accessible name), so it never covers the question card
    assert (b["width"] > 72) == (700 <= width < 1024) and "물어보기" in fab.get_attribute("aria-label")
    page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
    page.wait_for_timeout(400)
    fab.click()                                                      # nothing asked yet: the card's question box
    page.wait_for_timeout(1000)
    assert page.evaluate("document.activeElement.id") == "ask-q" and in_viewport(page, ".hk-box")
    assert page.locator("#chat").count() == 0 and page.locator("[data-ask-log]").is_hidden()
    assert errors == []
    ctx.close()


@pytest.mark.parametrize("reduced", ["reduce", "no-preference"])
def test_the_launcher_brings_the_conversation_and_the_panel_keeps_it(browser, site, reduced):
    ctx, page, errors = open_home(browser, site, 1440, 900, reduced=reduced)
    page.fill("#ask-q", "은파 주차")
    page.press("#ask-q", "Enter")
    page.wait_for_selector(".ask-log .chat-a .chat-card")
    fab = page.locator(".chat-fab")
    page.wait_for_timeout(800)
    assert fab.is_visible()                                          # never steps aside (owner 2026-10-14)
    page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
    page.wait_for_timeout(500)
    assert fab.is_visible()
    fab.click()
    page.wait_for_timeout(100 if reduced == "reduce" else 1200)
    assert in_viewport(page, "[data-ask-log]")                       # the conversation, in view
    assert page.evaluate("document.activeElement.id") == "ask-q2" and page.locator("#chat").count() == 0
    assert "은파 주차" in page.inner_text("[data-ask-log]")
    assert fab.is_visible()
    # another page: the launcher opens the floating panel with the same conversation (sessionStorage)
    page.goto(site + "/places/")
    page.locator(".chat-fab").click()
    page.locator("#chat").wait_for(state="visible")
    assert "은파 주차" in page.inner_text("#chat") and page.locator("#chat .chat-card").count() == 1
    assert page.locator("#chat .chat-card").get_attribute("data-chat-where") == "panel"
    # back home with that conversation in the tab: the launcher shows it in the panel under the opening
    page.goto(site + "/")
    page.wait_for_load_state("load")
    assert page.locator("[data-ask-log]").is_hidden()                # nothing restored while the page loads
    page.locator(".chat-fab").click()
    page.wait_for_selector("[data-ask-log] .chat-card")
    page.wait_for_timeout(100 if reduced == "reduce" else 1200)
    assert "은파 주차" in page.inner_text("[data-ask-log]") and page.evaluate("document.activeElement.id") == "ask-q2"
    assert errors == []
    ctx.close()


UNDER = """(sels) => { const out = []; for (const sel of sels) { const q = document.querySelector(sel);
  if (!q || getComputedStyle(q).display === 'none') continue; const r = q.getBoundingClientRect();
  for (const [x, y] of [[r.left + 4, r.top + r.height / 2], [r.left + r.width / 2, r.top + 6],
                        [r.left + r.width / 2, r.bottom - 6], [r.left + r.width / 2, r.top + r.height / 2]]) {
    q.style.pointerEvents = 'none'; const all = document.elementsFromPoint(x, y); q.style.pointerEvents = '';
    const e = all.find(e => !q.contains(e) && e.matches('a, button, input, label') && !e.closest('.chat-fab, .qm, .chat'));
    if (e) out.push(sel + ' over ' + e.tagName + ' ' + (e.textContent || '').trim().slice(0, 24)); } } return out; }"""


@pytest.mark.parametrize("width,height", [(1280, 800), (390, 844)])
def test_the_quick_menu_and_the_launcher_cover_no_control_while_scrolling(browser, site, width, height):
    """Review 2026-10-14: from 1024 to 1439px the rows outside .wrap (the home's carousels, the story stage) reached
    under the quick menu and the 72px launcher; at 390 the launcher sat on the starters' row. Down the whole home, step
    by step, no link, button or field is under either of them; on a phone (full-width rows pass under any floating
    button while scrolling) at load: the first screen's controls are clear of it."""
    ctx, page, errors = open_home(browser, site, width, height)
    hits = []
    end = page.evaluate("document.documentElement.scrollHeight") if width >= 1024 else 1
    for y in range(0, end, 300):
        page.evaluate(f"window.scrollTo(0, {y})")
        page.wait_for_timeout(60)
        hits += page.evaluate(UNDER, [".qm", ".chat-fab"])
    assert sorted(set(hits)) == []
    ctx.close()
