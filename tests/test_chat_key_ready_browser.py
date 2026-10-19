"""The site assistant before and after ANTHROPIC_API_KEY, in a real browser (Playwright + Chromium): this site's
configuration (data/incheon/site.json) with the fake tiny dataset (tests/fixtures/incheon_tiny), served locally with
a stand-in /api/chat/ that answers like chatbot/server.js — no key: GET and POST 503 {code: 'not_configured'}; with
the key: GET 200 {ready: true} and a streamed answer.

No key: the launcher opens a calm resting block ('AI 도우미 준비 중' and the site search) instead of a question box —
no question field, no starters, the focus in the search field (on a phone the title), the search goes to
/search/?q=, and not one question is sent. The home's card ([data-chat-dock]) rests the same way once the reader turns
to it: its line says what is going on, its button says '검색하기', Enter searches — and nothing on the page moves. With
the key, the same pages ask and show the answer with its page link, nothing else changed. A key removed after the page
asked: the question that meets 503 turns the panel to the resting block, the question already in the search field.
Skipped where Playwright or its Chromium is missing."""
import functools
import http.server
import json
import shutil
import threading
from pathlib import Path
from urllib.parse import parse_qs, urlsplit

import pytest

from pipeline.build import build

sync_api = pytest.importorskip("playwright.sync_api")

ROOT = Path(__file__).resolve().parent.parent
INCHEON = ROOT / "data" / "incheon"
# the files a collection or a writer adds to data/incheon (TourAPI writes places·events): left out of a copy that
# stands for this site's configuration before collection
RECORDS = ("places.json", "events.json", "courses.json", "guides.json", "themes.json", "videos.json")
TINY = Path(__file__).resolve().parent / "fixtures" / "incheon_tiny"
SITE = "https://incheon.example.com"
API = {"get": "off", "post": "off", "gets": 0, "posts": []}
OFF = "AI 도우미 준비 중"
ANSWER = "[테스트] 가상 해변 A의 주차는 [테스트] 주차 값입니다(한국관광공사 TourAPI).\n\n[가상 해변 A](/places/test-beach-a/)"


def sse(event) -> bytes:
    return f"data: {json.dumps(event, ensure_ascii=False)}\n\n".encode("utf-8")


class Site(http.server.SimpleHTTPRequestHandler):
    def log_message(self, *args):
        return None

    def _json(self, status: int, body: dict) -> None:
        out = json.dumps(body).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(out)))
        self.end_headers()
        self.wfile.write(out)

    def do_GET(self):
        if self.path.split("?")[0] != "/api/chat/":
            return super().do_GET()
        API["gets"] += 1
        if API["get"] == "on":
            return self._json(200, {"ready": True})
        return self._json(503, {"ready": False, "code": "not_configured", "message": "The site assistant is not set up yet."})

    def do_POST(self):
        body = self.rfile.read(int(self.headers.get("Content-Length") or 0))
        if self.path != "/api/chat/":
            return self.send_error(404)
        API["posts"].append(json.loads(body or b"{}"))
        if API["post"] != "on":
            return self._json(503, {"code": "not_configured", "message": "The site assistant is not set up yet."})
        self.send_response(200)
        self.send_header("Content-Type", "text/event-stream; charset=utf-8")
        self.end_headers()
        for i in range(0, len(ANSWER), 9):
            self.wfile.write(sse({"type": "text", "delta": ANSWER[i:i + 9]}))
        self.wfile.write(sse({"type": "done", "links": [{"title": "[테스트] 가상 해변 A", "url": f"{SITE}/places/test-beach-a/",
                                                        "ext": False}], "fix": {"/places/test-beach-a/": f"{SITE}/places/test-beach-a/"}}))


@pytest.fixture(scope="module")
def site(tmp_path_factory):
    tmp = tmp_path_factory.mktemp("chatready_web")
    data = tmp / "data"
    data.mkdir()
    for src in (INCHEON, TINY):
        for f in src.glob("*.json"):
            if src is TINY or f.name not in RECORDS:
                shutil.copy(f, data / f.name)
    out = tmp / "out"
    build(data, out, "preview")
    srv = http.server.ThreadingHTTPServer(("127.0.0.1", 0), functools.partial(Site, directory=str(out)))
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


def tab(browser, width, height, get="off", post="off"):
    API.update(get=get, post=post, gets=0, posts=[])
    ctx = browser.new_context(viewport={"width": width, "height": height}, locale="ko-KR")
    page = ctx.new_page()
    errors = []
    page.on("console", lambda m: errors.append(m.text) if m.type == "error" else None)
    page.on("pageerror", lambda e: errors.append(str(e)))
    return ctx, page, errors


def real_errors(errors):
    # Chromium logs a scripted 503 as a failed resource; nothing else may reach the console
    return [e for e in errors if "status of 503" not in e]


@pytest.mark.parametrize("width,height", [(1440, 900), (390, 844)])
def test_no_key_the_panel_rests_with_the_site_search(browser, site, width, height):
    ctx, page, errors = tab(browser, width, height)
    page.goto(site + "/places/")
    page.locator(".chat-fab").click()
    panel = page.locator("#chat")
    panel.wait_for(state="visible")
    off = panel.locator(".chat-off")
    assert off.is_visible() and panel.get_attribute("data-chat-off") == ""
    assert OFF in off.inner_text() and "사이트 검색을 이용해 주세요" in off.inner_text()
    assert page.locator("#chat-q").is_hidden() and page.locator(".chat-chip").count() == 0
    assert page.locator(".chat-hello").is_hidden() and page.locator(".chat-foot").is_hidden()
    search = page.locator("#chat-s")
    assert search.is_visible() and search.get_attribute("placeholder") == "장소·메뉴·동 이름"
    # measured once the panel's slide-in is over (a box read mid-animation sits on a fractional offset)
    page.wait_for_function("() => document.querySelector('#chat').getAnimations().every(a => a.playState !== 'running')")
    box = page.locator(".chat-off-go").bounding_box()
    assert box["height"] >= 44                                                  # a 44px target
    focused = page.evaluate("document.activeElement.id")
    assert focused == ("chat-title" if width < 640 else "chat-s")
    if width < 640:                                                              # the sheet keeps Tab inside, field included
        page.keyboard.press("Tab")
        for _ in range(6):
            assert page.evaluate("document.getElementById('chat').contains(document.activeElement)")
            page.keyboard.press("Tab")
    search.fill("가상 해변")
    search.press("Enter")
    page.wait_for_url("**/search/?q=*")
    assert parse_qs(urlsplit(page.url).query)["q"] == ["가상 해변"]
    assert API["gets"] == 1 and API["posts"] == []                               # asked once, nothing sent
    assert page.locator("#chat").count() == 0 or page.locator("#chat").is_hidden()   # the results, not the panel
    # the next page knows already (this tab, five minutes): the panel rests at once, without asking again
    page.goto(site + "/places/test-beach-a/")
    page.locator(".chat-fab").click()
    page.locator("#chat .chat-off").wait_for(state="visible")
    assert API["gets"] == 1 and API["posts"] == []
    assert real_errors(errors) == []
    ctx.close()


def test_no_key_the_home_card_searches_and_nothing_moves(browser, site):
    ctx, page, errors = tab(browser, 390, 844)
    page.goto(site + "/")
    page.wait_for_load_state("load")
    form = page.locator("[data-ask-form]")
    before = form.bounding_box()
    line = page.locator(".hk-sub")
    assert line.inner_text().startswith("AI가 이 사이트에 실린 정보로 답하고")
    page.locator("#ask-q").click()                                               # turning to the card loads chat.js
    page.wait_for_function("document.querySelector('[data-chat-dock]').hasAttribute('data-chat-off')")
    page.wait_for_function(f"document.querySelector('.hk-sub').textContent.startsWith('{OFF}')")
    assert line.inner_text() == "AI 도우미 준비 중 — 지금은 질문을 사이트 검색으로 찾아 드립니다." and line.get_attribute("role") == "status"
    assert page.locator("[data-ask-go] .ask-go-l").first.inner_text() == "검색하기"
    assert page.get_attribute("#ask-q", "placeholder") == "장소·메뉴·동 이름"
    after = form.bounding_box()
    assert (round(after["y"]), round(after["height"]), round(after["width"])) == \
        (round(before["y"]), round(before["height"]), round(before["width"]))     # the card did not move
    assert page.locator("[data-ask-log]").is_hidden()
    page.fill("#ask-q", "가상 식당")
    page.press("#ask-q", "Enter")
    page.wait_for_url("**/search/?q=*")
    assert parse_qs(urlsplit(page.url).query)["q"] == ["가상 식당"]
    assert API["gets"] == 1 and API["posts"] == []
    assert real_errors(errors) == []
    ctx.close()


def test_with_the_key_the_same_pages_ask_and_link_the_page(browser, site):
    ctx, page, errors = tab(browser, 1440, 900, get="on", post="on")
    page.goto(site + "/places/")
    page.locator(".chat-fab").click()
    page.locator("#chat").wait_for(state="visible")
    assert page.locator("#chat .chat-off").is_hidden() and page.get_attribute("#chat", "data-chat-off") is None
    assert page.evaluate("document.activeElement.id") == "chat-q"
    page.fill("#chat-q", "가상 해변 주차 돼?")
    page.keyboard.press("Enter")
    page.wait_for_selector(".chat-a .chat-card")
    assert page.locator(".chat-card").get_attribute("href") == "/places/test-beach-a/"
    assert page.locator(".chat-a .chat-md a").first.get_attribute("href") == "/places/test-beach-a/"
    assert API["gets"] == 1 and API["posts"][0]["messages"] == [{"role": "user", "content": "가상 해변 주차 돼?"}]
    # the home card asks in place too
    page.goto(site + "/")
    page.wait_for_load_state("load")
    page.fill("#ask-q", "가상 해변 주차")
    page.press("#ask-q", "Enter")
    page.wait_for_selector("[data-ask-log] .chat-a .chat-card")
    assert page.locator(".hk-sub").inner_text().startswith("AI가 이 사이트에 실린 정보로 답하고")
    assert len(API["posts"]) == 2 and errors == []
    ctx.close()


def test_a_key_removed_after_the_page_asked_turns_the_panel_to_rest(browser, site):
    ctx, page, errors = tab(browser, 1440, 900, get="on", post="off")
    page.goto(site + "/places/")
    page.locator(".chat-fab").click()
    page.locator("#chat").wait_for(state="visible")
    page.fill("#chat-q", "가상 숙소 체크인")
    page.keyboard.press("Enter")
    page.locator("#chat .chat-off").wait_for(state="visible")
    assert page.input_value("#chat-s") == "가상 숙소 체크인"                    # the question, ready to search
    assert page.locator(".chat-m").count() == 0 and page.locator("#chat-q").is_hidden()
    assert page.evaluate("document.activeElement.id") == "chat-s"
    page.wait_for_timeout(150)
    assert "AI 도우미가 아직 준비 중입니다" in page.inner_text("[data-chat-live]")
    assert page.evaluate("JSON.parse(sessionStorage.getItem('gs-chat-ready')).ok") is False
    assert len(API["posts"]) == 1 and real_errors(errors) == []
    ctx.close()
