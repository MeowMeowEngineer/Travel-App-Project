"""The site assistant in a real browser (Playwright + Chromium) on a sample build served locally, /api/chat/ mocked
with scripted SSE: the 1440px card (non-modal) opens from the launcher with focus in the question box, an input method's
Enter does not send (a conversion) while the Enter that ends a Korean syllable does, a streamed answer is drawn with its checked links and link cards and announced once, Esc closes
and returns focus to the launcher, the conversation comes back on the next page (sessionStorage); the 390px sheet is
modal (page inert, full height), the launcher is there from the first paint (64px; owner 2026-10-13 night), the
error states (with retry; the not-configured state: tests/test_chat_key_ready_browser.py), a text of its own for each 429 (the client's minute, its day, the whole
instance, the Vercel Firewall), a cut answer that goes on in place ('이어서 보기': continue: true with the cut answer as
the last message), earlier answers sent back with their checked links as page paths and a stopped question left out —
and no console errors. Skipped where Playwright or its Chromium is missing."""
import functools
import http.server
import json
import threading
from pathlib import Path

import pytest

from pipeline.build import build

sync_api = pytest.importorskip("playwright.sync_api")

ROOT = Path(__file__).resolve().parent.parent
SAMPLE = ROOT / "data" / "sample"
SITE = json.loads((SAMPLE / "site.json").read_text("utf-8"))["site_url"]   # the public address chat.js reads (data-chat-site)
ANSWER = ("은파호수공원은 쉬는 날 없이 열려 있습니다. [은파호수공원](/places/eunpa-lake-park/)\n\n"
          "- 시간: 상시 개방\n- 주차: 가능 — **무료**\n\n[없는 페이지](/places/nowhere/)")


def sse(*events) -> str:
    return "".join(f"data: {json.dumps(e, ensure_ascii=False)}\n\n" for e in events)


def answer_stream() -> str:
    deltas = [{"type": "text", "delta": ANSWER[i:i + 7]} for i in range(0, len(ANSWER), 7)]
    done = {"type": "done", "links": [{"title": "은파호수공원", "url": f"{SITE}/places/eunpa-lake-park/", "ext": False}],
            "fix": {"/places/eunpa-lake-park/": f"{SITE}/places/eunpa-lake-park/", "/places/nowhere/": None}}
    return sse({"type": "status", "text": "찾는 중: 은파호수공원"}, *deltas, done)


OK = (200, answer_stream(), "text/event-stream; charset=utf-8")
# an answer cut at the length limit, and the rest the server writes when the reader asks to go on
CUT_TEXT = "후보 일정입니다.\n- 10:00 | [은파호수공원](/places/eunpa-lake-park/) | 그날 운영: 엶 | 요금: 무"
REST = "료 | 이동: 미확인\n\n이동 확인이 필요한 후보 일정입니다."
PARK = {"title": "은파호수공원", "url": f"{SITE}/places/eunpa-lake-park/", "ext": False}


def stream_of(text: str, **done) -> tuple:
    deltas = [{"type": "text", "delta": text[i:i + 7]} for i in range(0, len(text), 7)]
    end = {"type": "done", "links": [PARK], "fix": {"/places/eunpa-lake-park/": PARK["url"]}, **done}
    return 200, sse(*deltas, end), "text/event-stream; charset=utf-8"
BUSY = (200, sse({"type": "error", "code": "busy", "message": "x"}), "text/event-stream; charset=utf-8")
# the function's 429s (chatbot/server.js: a code per limit) and the Vercel Firewall's own 429 (no code)
LIMITED = [(429, json.dumps({"code": code, "message": "x"}), "application/json")
           for code in ("rate_limited", "daily_limit", "busy")] + [(429, "<html>Too Many Requests</html>", "text/html")]


class Quiet(http.server.SimpleHTTPRequestHandler):
    def log_message(self, *args):   # the test output stays readable; failures show up as assertions
        return None


def korean_enter(page, syllable):
    """Enter pressed while a Korean input method still composes the last syllable, as Chrome delivers it (CDP): a
    keydown 229 that the input method keeps (it commits the syllable: compositionend), then the reader's own Enter a
    few milliseconds later."""
    cdp = page.context.new_cdp_session(page)
    cdp.send("Input.imeSetComposition", {"text": syllable, "selectionStart": 1, "selectionEnd": 1})
    cdp.send("Input.dispatchKeyEvent", {"type": "rawKeyDown", "key": "Enter", "code": "Enter",
                                        "windowsVirtualKeyCode": 229, "nativeVirtualKeyCode": 229})
    cdp.send("Input.insertText", {"text": syllable})
    page.keyboard.press("Enter")
    cdp.detach()


def converting_enter(page, text):
    """Enter pressed to confirm an input method's conversion (Japanese, Chinese): the key comes while composing, then
    the text is committed."""
    cdp = page.context.new_cdp_session(page)
    cdp.send("Input.imeSetComposition", {"text": text, "selectionStart": len(text), "selectionEnd": len(text)})
    page.keyboard.press("Enter")
    cdp.send("Input.insertText", {"text": text})
    cdp.detach()


@pytest.fixture(scope="module")
def site(tmp_path_factory):
    out = tmp_path_factory.mktemp("chatweb") / "out"
    build(SAMPLE, out, "sample")
    srv = http.server.ThreadingHTTPServer(("127.0.0.1", 0), functools.partial(Quiet, directory=str(out)))
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


def open_page(browser, width, height, responses):
    """A fresh tab whose /api/chat/ is scripted: GET (chat.js asks once whether the assistant is set up) answers ready;
    each POST gets the next of `responses` and is recorded in `calls`."""
    ctx = browser.new_context(viewport={"width": width, "height": height}, locale="ko-KR")
    page = ctx.new_page()
    errors, calls = [], []
    page.on("console", lambda m: errors.append(m.text) if m.type == "error" else None)
    page.on("pageerror", lambda e: errors.append(str(e)))

    def handle(route):
        if route.request.method == "GET":
            route.fulfill(status=200, body='{"ready":true}', headers={"content-type": "application/json"})
            return
        calls.append(route.request.post_data_json)
        status, body, ctype = responses[min(len(calls), len(responses)) - 1]
        route.fulfill(status=status, body=body, headers={"content-type": ctype})
    page.route("**/api/chat/", handle)
    return ctx, page, errors, calls


def test_desktop_card(browser, site):
    ctx, page, errors, calls = open_page(browser, 1440, 900, [OK])
    page.goto(site + "/places/")
    fab = page.locator(".chat-fab")
    assert fab.is_visible()                                   # a list page: the launcher is there from the start
    fab.click()
    panel = page.locator("#chat")
    panel.wait_for(state="visible")
    assert panel.get_attribute("role") == "dialog" and panel.get_attribute("aria-modal") == "false"
    assert page.evaluate("document.activeElement.id") == "chat-q"
    assert page.locator(".chat-chip").count() == 5
    assert not page.evaluate("document.querySelector('main').inert")
    page.wait_for_timeout(350)                                # after the opening slide
    box = {k: round(v) for k, v in panel.bounding_box().items()}
    assert box["width"] == 400 and box["height"] == 640 and box["x"] + box["width"] == 1440 - 24
    # an Enter the input method keeps for itself (a Japanese or Chinese conversion): nothing is sent
    page.fill("#chat-q", "은파 주")
    converting_enter(page, "차")
    page.wait_for_timeout(120)
    assert calls == []
    # Korean: the Enter that ends the last syllable sends at once (the 2026-10-14 bug: a guard after compositionend
    # swallowed it, so the reader had to press Enter twice)
    page.fill("#chat-q", "은파 주")
    korean_enter(page, "차")
    page.wait_for_selector(".chat-a .chat-card")
    assert calls[0]["messages"] == [{"role": "user", "content": "은파 주차"}]
    assert calls[0]["lang"] == "ko" and calls[0]["page"] == "/places/"
    md = page.locator(".chat-a .chat-md")
    assert "주차: 가능 — 무료" in md.inner_text() and md.locator("strong").inner_text() == "무료"
    assert md.locator("ul li").count() == 2
    links = md.locator("a")
    assert links.count() == 1 and links.first.get_attribute("href") == "/places/eunpa-lake-park/"   # checked; the fake one is text
    assert "없는 페이지" in md.inner_text() and md.locator(".chat-lk").count() == 0
    card = page.locator(".chat-card")
    assert card.get_attribute("href") == "/places/eunpa-lake-park/" and card.get_attribute("data-track") == "chat_link_click"
    page.wait_for_timeout(150)
    assert "은파호수공원은 쉬는 날 없이" in page.locator("[data-chat-live]").inner_text()
    # Esc closes; focus returns to the launcher
    page.keyboard.press("Escape")
    assert panel.is_hidden()
    assert page.evaluate("document.activeElement.classList.contains('chat-fab')")
    # the next page restores the open chat and the conversation from sessionStorage
    fab.click()
    panel.wait_for(state="visible")
    page.click(".chat-card")
    page.wait_for_url("**/places/eunpa-lake-park/")
    page.locator("#chat").wait_for(state="visible")
    assert "은파 주차" in page.inner_text("#chat") and page.locator(".chat-card").count() == 1
    assert errors == []
    ctx.close()


def test_phone_sheet_and_error_states(browser, site):
    ctx, page, errors, calls = open_page(browser, 390, 844, [BUSY, OK])
    page.goto(site + "/")
    fab = page.locator(".chat-fab")
    assert fab.is_visible()                                   # there from the first paint, on the home too
    box = fab.bounding_box()
    assert box["height"] == 64 and box["width"] == 64 and box["y"] + box["height"] <= 844 - 16   # a round face
    page.mouse.wheel(0, 700)
    page.wait_for_timeout(400)
    assert fab.is_visible()
    fab.click()
    panel = page.locator("#chat")
    panel.wait_for(state="visible")
    assert panel.get_attribute("aria-modal") == "true"
    assert page.evaluate("document.querySelector('main').inert && document.querySelector('footer').inert")
    page.wait_for_timeout(350)
    sheet = {k: round(v) for k, v in panel.bounding_box().items()}
    assert sheet["x"] == 0 and sheet["y"] == 0 and sheet["width"] == 390 and sheet["height"] == 844
    assert page.evaluate("document.activeElement.id") == "chat-title"
    chip = page.locator(".chat-chip").first.inner_text()
    page.locator(".chat-chip").first.click()
    page.wait_for_selector(".chat-retry")                      # an error event: retry
    assert "지금은 답을 만들 수 없습니다" in page.inner_text(".chat-err")
    page.click(".chat-retry")
    page.wait_for_selector(".chat-a .chat-card")
    assert len(calls) == 2 and calls[1]["messages"] == calls[0]["messages"] == [{"role": "user", "content": chip}]
    page.keyboard.press("Tab")
    assert page.evaluate("document.getElementById('chat').contains(document.activeElement)")
    page.click('.chat-ib[aria-label="닫기"]')
    assert panel.is_hidden() and not page.evaluate("document.querySelector('main').inert")
    assert errors == []
    ctx.close()


def test_each_limit_tells_the_reader_what_it_is(browser, site):
    """The client's minute (and the Firewall's 429): 'ask again in a minute', with retry. The client's day: the day's
    limit, no retry, the site search instead. The whole instance full: 'cannot answer right now', not the reader's
    doing."""
    ctx, page, errors, calls = open_page(browser, 1440, 900, LIMITED)
    page.goto(site + "/places/")
    page.locator(".chat-fab").click()
    page.locator("#chat").wait_for(state="visible")
    for i, q in enumerate(["하나", "둘", "셋", "넷"]):
        page.fill("#chat-q", q)
        page.keyboard.press("Enter")
        page.locator(".chat-err").nth(i).wait_for()
    errs = page.locator(".chat-err")
    minute, day, busy, firewall = (errs.nth(i).inner_text() for i in range(4))
    assert "1분 뒤" in minute and firewall == minute and errs.nth(0).locator(".chat-retry").count() == 1
    assert "1분" not in day and "내일" in day and "질문이 너무 잦습니다" not in day
    assert errs.nth(1).locator(".chat-retry").count() == 0 and errs.nth(1).locator("a[href='/search/']").count() == 1
    assert "지금은 답을 만들 수 없습니다" in busy and "1분" not in busy and errs.nth(2).locator(".chat-retry").count() == 1
    assert len(calls) == 4
    assert [e for e in errors if "status of 429" not in e] == []
    ctx.close()


def test_a_cut_answer_goes_on_in_place(browser, site):
    """done.cut: the last answer says it was cut and offers '이어서 보기'. That request carries continue: true and the cut
    answer, raw, as the last message; the rest streams into the same answer, the links of both parts stay links, the
    link cards are not doubled, and the next question sends the whole answer back with its links as page paths."""
    ctx, page, errors, calls = open_page(browser, 1440, 900, [stream_of(CUT_TEXT, cut=True), stream_of(REST), OK])
    page.goto(site + "/places/")
    page.locator(".chat-fab").click()
    page.locator("#chat").wait_for(state="visible")
    page.fill("#chat-q", "일정 짜줘")
    page.keyboard.press("Enter")
    more = page.locator(".chat-a .chat-retry")
    more.wait_for()
    assert more.inner_text() == "이어서 보기" and "답이 길어 여기서 끊겼습니다" in page.inner_text(".chat-a")
    more.click()
    page.wait_for_function("document.querySelector('.chat-a .chat-md').innerText.includes('이동 확인이 필요한')")
    page.wait_for_timeout(100)
    assert calls[1]["continue"] is True
    assert calls[1]["messages"] == [{"role": "user", "content": "일정 짜줘"}, {"role": "assistant", "content": CUT_TEXT}]
    answer = page.locator(".chat-a")
    assert answer.count() == 1 and "요금: 무료 | 이동: 미확인" in answer.inner_text()   # one answer, joined at the cut
    assert "끊겼습니다" not in answer.inner_text() and answer.locator(".chat-retry").count() == 0
    assert answer.locator(".chat-md a[href='/places/eunpa-lake-park/']").count() == 1
    assert answer.locator(".chat-card").count() == 1
    page.fill("#chat-q", "다음 질문")
    page.keyboard.press("Enter")
    page.wait_for_function("document.querySelectorAll('.chat-a').length === 2"
                           " && document.querySelectorAll('.chat-a')[1].querySelector('.chat-card')")
    prior = calls[2]["messages"]
    assert [m["role"] for m in prior] == ["user", "assistant", "user"] and "continue" not in calls[2]
    assert "요금: 무료 | 이동: 미확인" in prior[1]["content"]
    assert "[은파호수공원](/places/eunpa-lake-park/)" in prior[1]["content"]
    assert errors == []
    ctx.close()


def test_earlier_answers_go_back_with_page_paths_and_without_a_stopped_question(browser, site):
    """In this tab: a question the reader stopped (no answer) and a question with a long answer whose checked link is at
    the end (a Korean page path). The next request leaves the stopped question out, cuts the long answer to 2,000
    characters and keeps its link, as a readable page path."""
    long = "가" * 2300 + "\n[가옥](/places/한글/)"
    state = {"v": 1, "open": True, "msgs": [
        {"r": "u", "t": "3박 4일 일정 길게"}, {"r": "a", "t": "", "s": True},
        {"r": "u", "t": "첫 질문"},
        {"r": "a", "t": long, "f": {"/places/한글/": SITE + "/places/%ED%95%9C%EA%B8%80/"}, "l": []}]}
    ctx, page, errors, calls = open_page(browser, 1440, 900, [OK])
    page.goto(site + "/places/")
    page.evaluate("s => sessionStorage.setItem('gs-chat', JSON.stringify(s))", state)
    page.reload()
    page.locator("#chat").wait_for(state="visible")
    page.fill("#chat-q", "새 질문")
    page.keyboard.press("Enter")
    page.wait_for_selector(".chat-a .chat-card")
    msgs = calls[0]["messages"]
    assert [m["role"] for m in msgs] == ["user", "assistant", "user"]
    assert msgs[0]["content"] == "첫 질문" and msgs[2]["content"] == "새 질문"
    assert len(msgs[1]["content"]) <= 2000 and msgs[1]["content"].endswith(" …\n[가옥](/places/한글/)")
    assert errors == []
    ctx.close()
