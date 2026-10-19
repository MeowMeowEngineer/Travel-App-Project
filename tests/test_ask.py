"""Asking the site assistant from the homes (owner 2026-10-13): the starter questions (pipeline/ask.py,
data/<region>/ask.json), the English home's centre card and the Korean home's opening box with its conversation panel
(owner 2026-10-13 night: '이 상자를 챗봇 질문창으로'; templates/_ask.html.j2 card / box / panel). A starter is a question
for the site assistant and, without JS, a link to the page that answers it — never a link to a page the build does not
have."""
import json
import re
import shutil
from pathlib import Path

from pipeline import ask, icons
from pipeline.build import make_env

ROOT = Path(__file__).resolve().parent.parent
GUNSAN = ROOT / "data" / "gunsan"

ITEMS = [
    {"q": {"ko": "선유도 가는 법", "en": "How do I get to Seonyudo?"}, "guide": "guide-08"},
    {"q": {"ko": "월요일에 여는 음식점"}, "guide": "guide-24"},
    {"q": {"ko": "없는 가이드", "en": "Missing guide"}, "guide": "guide-99"},
    {"q": {"ko": "이번 달 행사·축제", "en": "Events this month"}, "page": "events"},
]


def card(lang="ko", starters=None, dark_top=False):
    macro = make_env().get_template("_ask.html.j2").module.card
    return str(macro(lang, "군산" if lang == "ko" else "Gunsan", starters or [], dark_top))


def test_starters_link_only_to_pages_the_build_has():
    ko = ask.starters(ITEMS, "ko", {"guide-08": "/guides/a/", "guide-24": "/guides/b/"}, {"events": "/events/"})
    assert ko == [{"q": "선유도 가는 법", "href": "/guides/a/"}, {"q": "월요일에 여는 음식점", "href": "/guides/b/"},
                  {"q": "이번 달 행사·축제", "href": "/events/"}]
    # English: a starter without an English question or without the English guide is left out; no events, no chip
    en = ask.starters(ITEMS, "en", {"guide-08": "/en/guides/a/"}, {})
    assert en == [{"q": "How do I get to Seonyudo?", "href": "/en/guides/a/"}]
    assert ask.starters([], "ko", {}, {}) == []


def test_data_problems_catch_bad_starters(tmp_path):
    (tmp_path / "ask.json").write_text(json.dumps({"starters": [
        {"q": {"en": "No Korean"}, "guide": "guide-01"},
        {"q": {"ko": "둘 다"}, "guide": "guide-01", "page": "events"},
        {"q": {"ko": "없는 가이드"}, "guide": "guide-99"},
        {"q": {"ko": "없는 목록"}, "page": "stays"},
        {"q": {"ko": "가" * 41}, "guide": "guide-01"},
    ]}, ensure_ascii=False), "utf-8")
    errs = ask.data_problems(tmp_path, {"guide-01"})
    assert any("starters[0]" in e and "q.ko" in e for e in errs)
    assert any("starters[1]" in e and "하나만" in e for e in errs)
    assert any("starters[2]" in e and "guide-99" in e for e in errs)
    assert any("starters[3]" in e and "page" in e for e in errs)
    assert any("starters[4]" in e and "40자" in e for e in errs)
    assert ask.data_problems(tmp_path / "none", set()) == []   # no file, no starters, nothing to check


def test_korean_card_is_a_search_form_without_js_and_its_starters_are_links():
    html = card("ko", [{"q": "선유도 가는 법", "href": "/guides/고군산군도-섬-여행/"}])
    assert 'data-chat-dock' in html and 'aria-labelledby="h-ask"' in html and 'id="h-ask"' in html
    assert '군산 여행, 무엇이 궁금하세요?' in html
    assert 'action="/search/"' in html and 'name="q"' in html and 'for="ask-q"' in html and 'id="ask-q"' in html
    assert '<a class="ask-chip" href="/guides/고군산군도-섬-여행/" data-ask="선유도 가는 법">선유도 가는 법</a>' in html
    assert 'formaction="/search/"' in html and '사이트 검색' in html   # the second button always searches
    assert 'href="/about/#chatbot"' in html and 'ask-jsonly' not in html and 'ask-dark' not in html
    assert 'data-ask-log hidden' in html   # the conversation area starts empty and hidden (no layout shift)
    assert '<img' not in html   # text only: nothing for the first paint to wait for


def test_english_card_hides_its_box_without_js_and_keeps_its_starters():
    html = card("en", [{"q": "Events this month", "href": "/en/events/"}], dark_top=True)
    assert 'What would you like to know about Gunsan?' in html
    assert 'class="ask ask-dark ask-jsonly"' in html and 'formaction' not in html
    assert 'href="/en/about/#chatbot"' in html and 'href="/en/events/"' in html
    assert 'ask-sug' not in card("en", [])   # no starters, no "Try asking" row


LANGS = ("ko", "en", "ja", "zh-Hans", "zh-Hant", "de", "fr", "es", "ru")
CHAT_JS = ROOT / "templates" / "assets" / "chat.js"


def test_the_card_can_leave_out_its_second_search_button_and_still_searches_without_js():
    macro = make_env().get_template("_ask.html.j2").module.card
    html = str(macro("ko", "군산", [], search_alt=False))
    assert '사이트 검색' not in html and 'formaction' not in html and 'data-ask-search' not in html
    assert '<form class="ask-box" action="/search/" method="get" data-ask-form="search" data-empty="' in html
    assert 'ask-jsonly' not in html


def test_the_card_speaks_nine_languages_and_its_button_keeps_both_labels():
    macro = make_env().get_template("_ask.html.j2").module.card
    js = CHAT_JS.read_text("utf-8")
    for lang in LANGS:
        html = str(macro(lang, "군산" if lang == "ko" else "Gunsan", [{"q": "Q", "href": "/x/"}]))
        # the two labels share the button (ask / stop): its width never changes when it turns into the stop button
        go, stop = re.search(r'<button type="submit" class="ask-go" data-ask-go><span class="ask-go-l">([^<]+)</span>'
                             r'<span class="ask-go-l ask-go-s">([^<]+)</span></button>', html).groups()
        key = f'"{lang}"' if "-" in lang else lang
        block = js[js.index(f"\n    {key}: {{"):]
        assert f'stop: "{stop}"' in block[:block.index("\n    },")], lang     # the same word chat.js uses
        assert 'data-ask-log hidden data-fail="' in html and 'data-fail=""' not in html, lang
        if lang != "ko":
            assert not re.search(r"[가-힣]", html), lang                        # no Hangul outside the Korean card
            assert 'ask-jsonly' in html and 'action=' not in html and "data-ask-form data-empty=" in html, lang
        if lang not in ("ko", "en"):
            assert '<a href="/en/about/#chatbot" hreflang="en">' in html, lang   # the help page is English
            assert "What would you like to know" not in html, lang              # its own words, not the English
    assert "Que voulez-vous savoir sur Gunsan ?" in str(macro("fr", "Gunsan", []))
    assert 'What would you like to know about Gunsan?' in str(macro("xx", "Gunsan", []))   # any other: English


def test_without_js_the_starters_are_links_and_the_card_says_so():
    """The external evaluation of 2026-10-18 read the home's '#' tags as links to guides, while the floating panel's
    chips ask. Without JS they are exactly that — links to the pages that answer them — and a line shown only without
    JS (.hk-nojs) says so, in every language; with JS site.js makes each one a button that asks (role=button: a click,
    Enter or Space), as the panel's chips do (tests/test_ask_browser.py). The first paint carries no role."""
    mod = make_env().get_template("_ask.html.j2").module
    ko = str(mod.box([{"q": "선유도 가는 법", "href": "/guides/a/"}], "군산"))
    nojs = ko.split('<p class="hk-nojs">', 1)[1].split("</p>")[0]
    assert "사이트 검색" in nojs and "예시 질문은 답이 실린 페이지로 연결합니다" in nojs
    assert "role=" not in ko[ko.index('class="hk-pills"'):]
    lines = []
    for lang in LANGS:
        html = str(mod.box_intl(lang, [{"q": "Q", "href": "/x/"}], "Gunsan"))
        line = re.search(r'<p class="hk-nojs">([^<]+)</p>', html).group(1)
        assert html.index('class="hk-nojs"') < html.index('class="hk-pills"') and "role=" not in html, lang
        if lang != "ko":
            assert not re.search(r"[가-힣]", line), lang
        lines.append(line)
        assert 'class="hk-nojs"' not in str(mod.box_intl(lang, [], "Gunsan")), lang   # no starters, no line
    assert len(set(lines)) == len(LANGS)
    assert "html.js .hk-nojs { display: none; }" in (ROOT / "templates" / "assets" / "css" / "46-home-open.css").read_text("utf-8")


def _sample(tmp_path, starters=None, places=True):
    data = tmp_path / "data"
    shutil.copytree(ROOT / "data" / "sample", data)
    if starters is not None:
        (data / "ask.json").write_text(json.dumps({"starters": starters}, ensure_ascii=False), "utf-8")
    if not places:
        (data / "places.json").write_text("[]", "utf-8")
    return data


def test_the_korean_card_is_the_assistant_only_and_searches_without_js():
    """The Korean home's centre card (owner 2026-10-14: '페이지 상단에는 검색, 중앙 부분에는 AI챗봇으로 확실히 구분'): the
    assistant only. Its head — the mascot (decorative), the heading with the assistant's name (h2#h-ask, the name kept
    on one line) and one line saying that AI answers from this site's pages with the source pages — then ONE GET form
    to /search/ (without JS it searches; no role=search: with JS it is not a search) with the question field and ONE
    submit button '물어보기' carrying both of its labels (ask / stop) in one cell: no '검색' button, no formaction. A
    line shown only without JS says the box searches then. The starters are links to the pages that answer them; one
    plain line says chats are not stored and links the help page. The panel: hidden and empty until the reader asks,
    with the follow-up box's placeholder and the line that the answers are AI-written from this site's data and can be
    wrong. No machine-like wording (docs/handover 2026-10-14: not 'AI 여행 도우미', not '무엇이든 물어보세요')."""
    mod = make_env().get_template("_ask.html.j2").module
    html = str(mod.box([{"q": "선유도 가는 법", "href": "/guides/a/"}, {"q": "이번 달 행사·축제", "href": "/events/"}], "군산"))
    assert '<form class="hk-box" action="/search/" method="get" data-ask-form="search" data-empty="질문을 먼저 적어 주세요">' in html
    assert 'role="search"' not in html and "formaction" not in html and "data-ask-search" not in html
    assert re.findall(r"<button[^>]*>", html) == ['<button type="submit" class="ask-go hk-go" data-ask-go>']
    assert '<span class="ask-go-l">물어보기</span><span class="ask-go-l ask-go-s">멈추기</span>' in html
    assert ">검색<" not in html
    assert 'for="ask-q"' in html and 'id="ask-q" name="q"' in html and "data-ask-q" in html
    assert 'placeholder="궁금한 것을 적어 주세요"' in html and '<svg class="hk-ico"' in html and 'aria-hidden="true"' in html
    assert '<h2 id="h-ask" class="hk-h"><span class="hk-hn">군산 여행 도우미에게</span> 물어보세요</h2>' in html
    assert '<p class="hk-sub" data-ask-line>AI가 이 사이트에 실린 정보로 답하고, 답마다 출처 페이지를 붙입니다.</p>' in html
    assert '<p class="hk-nojs">' in html and "사이트 검색" in html.split('<p class="hk-nojs">', 1)[1].split("</p>")[0]
    assert '<a class="hk-pill" href="/guides/a/" data-ask="선유도 가는 법">선유도 가는 법</a>' in html
    assert '<a class="hk-pill" href="/events/" data-ask="이번 달 행사·축제">' in html
    # what happens to a conversation, as it is (operator 2026-10-18, 해남각's wording): kept in this tab only, the
    # questions sent to Anthropic — never a bare '저장하지 않습니다'
    assert "대화는 이 탭에만 임시 보관됩니다" in html and 'href="/about/#chatbot"' in html
    assert "대화는 저장하지 않습니다" not in html
    chat_js = (ROOT / "templates" / "assets" / "chat.js").read_text("utf-8")
    feet = re.findall(r'foot: "([^"]*)"', chat_js)
    assert len(feet) == 9 and all("Anthropic" in f for f in feet), feet
    ask = (ROOT / "templates" / "_ask.html.j2").read_text("utf-8")
    assert ask.count("'terms': ") + ask.count("'terms': \"") >= 9 and ask.count("Anthropic") >= 9
    assert "not stored" not in ask and "保存されません" not in ask and "不会被保存" not in ask
    if icons.mascot("mascot-hello"):                 # the mascot is optional (pipeline/icons.py; ported 2026-10-19)
        assert 'class="hk-mascot"' in html and 'alt=""' in html and "/assets/mascot/mascot-hello-96.avif 1x" in html
    else:                                            # no mascot yet: the head is the heading alone, nothing to load
        assert "hk-mascot" not in html and "/assets/mascot/" not in html
    assert html.index('class="hk-head"') < html.index('<form class="hk-box"') < html.index('class="hk-pills"')
    assert "AI 여행 도우미" not in html and "무엇이든" not in html
    assert '<ul class="hk-pills"' not in str(mod.box([], "군산"))   # no starters, no row
    panel = str(mod.panel())
    assert 'data-ask-log hidden' in panel and 'data-ask-more="이어서 물어보기"' in panel
    assert 'data-note="AI가 이 사이트의 정보로 쓴 답입니다. 틀릴 수 있으니 방문 전에 확인하세요."' in panel
    assert re.search(r"data-ask-log[^>]*></div>", panel)                      # empty: chat.js draws into it


def test_the_ask_box_comes_with_ask_json_and_places(tmp_path):
    from pipeline.build import State, build
    # no ask.json: the home as before; ask.json but no places: no box either (nothing to answer from, no search page)
    assert State(_sample(tmp_path / "a"), "sample").ask is None
    assert State(_sample(tmp_path / "b", [], places=False), "sample").ask is None
    data = _sample(tmp_path / "c", [{"q": {"ko": "차 없이 하루 여행"}, "guide": "guide-sample-1"},
                                    {"q": {"ko": "이번 달 행사"}, "page": "events"}])
    out = tmp_path / "c" / "out"
    build(data, out, "sample")
    html = (out / "index.html").read_text("utf-8")
    assert html.count("data-chat-dock") == 1 and '<div class="hk" data-chat-dock>' in html
    assert '<form class="hk-box" action="/search/"' in html and 'class="ask-log ask-panel" data-ask-log hidden' in html
    assert '<a class="hk-pill" href="/guides/no-car-day-trip/" data-ask="차 없이 하루 여행">' in html
    assert '<a class="hk-pill" href="/events/" data-ask="이번 달 행사">' in html
    for page in out.rglob("*.html"):   # only the homes ask in place
        if page != out / "index.html" and page.parent.name != "en":
            assert "data-chat-dock" not in page.read_text("utf-8"), page
    # without ask.json: nothing asks in place, and the card keeps its menu only — the search is the header's
    plain = tmp_path / "a" / "out"
    build(tmp_path / "a" / "data", plain, "sample")
    home = (plain / "index.html").read_text("utf-8")
    assert "data-chat-dock" not in home and "hk-box" not in home and 'id="h-ask"' not in home
    assert '<form class="hs" id="hs" action="/search/" method="get" role="search" data-hs>' in home


def test_starter_problems_are_validate_errors(tmp_path):
    from pipeline.build import build
    from pipeline.validate import validate
    data = _sample(tmp_path, [{"q": {"ko": "차 없이 하루 여행"}, "guide": "guide-sample-1"},
                              {"q": {"ko": "없는 가이드"}, "guide": "guide-99"},
                              {"q": {"en": "No Korean"}, "page": "events"}])
    out = tmp_path / "out"
    build(data, out, "sample")
    errors = validate(data, out, "sample")[0]
    assert "[ask.json] starters[1]: 없는 가이드 guide-99" in errors
    assert any(e.startswith("[ask.json] starters[2]:") and "q.ko" in e for e in errors)
    assert [e for e in errors if not e.startswith("[ask.json]")] == []
    (data / "ask.json").write_text(json.dumps({"starters": [{"q": {"ko": "차 없이 하루 여행"}, "guide": "guide-sample-1"}]},
                                              ensure_ascii=False), "utf-8")
    assert validate(data, out, "sample")[0] == []
