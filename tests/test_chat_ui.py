"""The site assistant in the pages: one launcher at the end of every page (every language) — 64px, the mascot's face
at 1x and 2x with its size set, a plain-words name (owner 2026-10-13 night) — nothing else of the chat in the first
paint (chat.js and chat.css load on the first press — site.js), the module builds the page from text nodes only and
keeps input methods from sending, the /about/ sections, the launcher's few rules in style.css. (Ported 2026-10-19: the
mascot is optional — without one the launcher's face is the chat glyph; tests/test_mascot.py covers both.)"""
import json
import re
from pathlib import Path

import pytest

from pipeline import en_site, icons
from pipeline.build import build, make_env

ROOT = Path(__file__).resolve().parent.parent
SAMPLE = ROOT / "data" / "sample"
ASSETS = ROOT / "templates" / "assets"
LABELS = {"ko": "AI 챗봇", "en": "AI chat", "ja": "AIチャット", "zh-Hans": "AI助手", "zh-Hant": "AI助手", "de": "KI-Chat",
          "fr": "Chat IA", "es": "Chat IA", "ru": "ИИ-чат"}


@pytest.fixture(scope="module")
def sample(tmp_path_factory):
    out = tmp_path_factory.mktemp("chatui") / "out"
    build(SAMPLE, out, "sample")
    return out


def test_every_page_has_one_launcher_and_nothing_else_of_the_chat(sample):
    pages = sorted(sample.rglob("*.html"))
    assert len(pages) > 10
    for p in pages:
        html = p.read_text("utf-8")
        # the launcher on every page, and it is the only opener: the header searches (owner 2026-10-14: '페이지 상단에는
        # 검색, 중앙 부분에는 AI챗봇') and the home's centre card asks in place
        assert html.count('class="chat-fab"') == 1, p
        openers = re.findall(r'<(?:button|a)[^>]*data-chat-open[^>]*>', html)
        # one exception: a search that finds nothing offers to ask the chat that query (QA 2026-10-15 F08; the
        # button is in the hidden help search.js shows then)
        asks = [o for o in openers if "data-chat-q" in o]
        assert len(asks) == (1 if p.parent.name == "search" else 0), p
        openers = [o for o in openers if o not in asks]
        assert len(openers) == 1 and 'class="chat-fab"' in openers[0], p
        assert "mast-ask" not in html, p
        assert '<span class="chat-fab-l">AI 챗봇</span>' in html and 'aria-haspopup="dialog"' in html
        fab = html[html.index('class="chat-fab"'):]
        fab = fab[:fab.index("</button>")]
        if icons.mascot("mascot-icon-3d"):                                # the mascot's face (optional, pipeline/icons.py)
            assert '<source type="image/avif" srcset="/assets/mascot/mascot-icon-3d-64.avif 1x, ' \
                   '/assets/mascot/mascot-icon-3d-128.avif 2x">' in fab, p
            assert 'width="52" height="52" alt=""' in fab and 'fetchpriority="low"' in fab, p
        else:                                                             # no mascot yet: the chat glyph, nothing to load
            assert '<span class="chat-fab-face"><span class="mascot-g" style="--mg:52px" aria-hidden="true"><svg' in fab, p
            assert "/assets/mascot/" not in html, p
        # right after the header, early in the tab order (QA 2026-10-19 QA-49: it was the last of 68 tab stops); the
        # quick menu and the pictures stay after the footer
        assert html.index("</header>") < html.index('class="chat-fab"') < html.index("<main"), p
        if '<nav class="qm"' in html:
            assert html.index('<nav class="qm"') > html.rindex("</footer>"), p
        assert "chat.js" not in html and "chat.css" not in html and "/api/chat" not in html
        assert html.count("<script src=") == 1
    assert (sample / "assets" / "chat.js").exists() and (sample / "assets" / "chat.css").exists()
    for name in ("64.avif", "128.avif", "64.webp", "128.webp") if icons.mascot("mascot-icon-3d") else ():   # its face
        assert (sample / "assets" / "mascot" / f"mascot-icon-3d-{name}").stat().st_size <= 8 * 1024, name
    style = (sample / "assets" / "style.css").read_text("utf-8")
    assert ".chat-fab{" in style and "html:not(.js) .chat-fab" in style
    assert ".chat-log" not in style and ".chat-card" not in style      # the panel's rules come with chat.js
    assert len((ASSETS / "css" / "49-chat.css").read_text("utf-8").encode("utf-8")) < 4000


def test_launcher_in_every_language_is_named_by_its_visible_label():
    tpl = make_env().get_template("_chat.html.j2")
    for lang, label in {**LABELS, "xx": "AI chat"}.items():
        html = tpl.render(lang=lang)
        visible = re.search(r'<span class="chat-fab-l">([^<]+)</span>', html).group(1)
        name = re.search(r'aria-label="([^"]+)"', html).group(1)
        assert visible == label, lang
        assert name.lower().startswith(label.lower()), (lang, name)      # WCAG 2.5.3 label in name
        # it says it is an AI chat (owner 2026-10-14: '우측 하단에 지금 뭔지 잘 모르겠는데, AI 챗봇인 거 더 크게 잘
        # 보이면 좋겠네' — this replaces 2026-10-13's plain-words-only rule for the launcher) and what it is for
        assert re.search(r"AI|KI|IA|ИИ", label) and " — " in name, (lang, name)
        if lang not in ("ko",):
            assert not re.search(r"[가-힣]", html), lang                 # English pages carry no Hangul


def test_english_pages_render_the_english_launcher():
    env = make_env()
    site = json.loads((SAMPLE / "site.json").read_text("utf-8"))
    page = {"title": "Test", "description": "", "canonical": "https://example.com/en/", "crumbs": [], "jsonld": []}
    child = env.from_string('{% extends "base.html.j2" %}{% block content %}<p>x</p>{% endblock %}')
    # every foreign page gets the language engine's chrome words and locale (pipeline/en_site.py); English here
    html = child.render(site=site, page=page, page_kind="home", lang="en", nav=[], nav_current="", mode="sample",
                        wordmark="All About Gunsan Travel", lang_link=None, tourapi_used=False,
                        t=en_site.UIText(en_site.EN, {}), loc=en_site.EN, langs=[])
    assert '<span class="chat-fab-l">AI chat</span>' in html and "챗봇" not in html
    assert html.index("</header>") < html.index('class="chat-fab"') < html.index("<main")


def test_about_pages_explain_the_assistant(sample):
    html = (sample / "about" / "index.html").read_text("utf-8")
    section = html[html.index('id="chatbot"'):]
    section = section[:section.index("</section>")]
    for words in ("사이트 안내 챗봇", "Claude Haiku 5.5", "Anthropic", "틀릴 수", "저장하지 않습니다", "링크", "예약·결제·회원가입"):
        assert words in section, words
    en = (ROOT / "templates" / "en" / "about.html.j2").read_text("utf-8")
    section = en[en.index('id="chatbot"'):]
    section = section[:section.index("</section>")]
    for words in ("Claude Haiku 5.5", "Anthropic", "can be wrong", "does not store", "cannot book"):
        assert words in section, words


def test_the_chat_module_builds_text_nodes_only_and_keeps_input_methods_from_sending():
    js = (ASSETS / "chat.js").read_text("utf-8")
    for sink in ("innerHTML", "outerHTML", "insertAdjacentHTML", "document.write", "eval(", "new Function"):
        assert sink not in js, sink
    # an Enter is the input method's when it comes while composing, or with keyCode 229 (Safari, after compositionend);
    # no timer after compositionend: the Enter Chrome sends right after a Korean syllable is committed is the reader's
    assert "function imeEnter(e) { return e.isComposing || e.keyCode === 229; }" in js
    assert 'addEventListener("compositionend"' not in js and "compEnd" not in js
    assert 'addEventListener("compositionend"' not in (ASSETS / "site.js").read_text("utf-8")
    assert 'role: "dialog"' in js and '"aria-modal"' in js and '"aria-live": "polite"' in js
    assert 'sessionStorage' in js and "requestAnimationFrame" in js and 'a.rel = "noopener"' in js
    assert '"data-track": "chat_link_click"' in js and 'track("chat_open")' in js and 'track("chat_send")' in js
    for lang in LABELS:
        key = f'"{lang}"' if "-" in lang else lang
        assert re.search(rf"\n    {re.escape(key)}: {{", js), lang
    site = (ASSETS / "site.js").read_text("utf-8")
    hook = site[site.index("site assistant: chat.js"):site.index("masthead: compact")]
    assert 'doc.querySelector("[data-chat-open]")' in hook and 'BASE + "chat.js"' in hook and 'BASE + "chat.css"' in hook
    # the module is fetched only from the press handler or the restore path (after load), never at startup
    assert hook.count("chatLoad().then") == 2 and "afterLoad(function () { chatLoad()" in hook


def test_every_language_can_go_on_with_a_cut_answer():
    """A cut answer (done.cut) offers to go on in every language; the request says continue: true (chatbot/server.js
    cleanRequest then adds the request to go on as the last, user, message) and the rest joins the same answer."""
    js = (ASSETS / "chat.js").read_text("utf-8")
    more = re.findall(r'cut: "[^"]+", more: "([^"]+)"', js)
    assert len(more) == len(LABELS) and len(set(more)) >= 8, more
    assert 'body["continue"] = true' in js and "function cont(m)" in js and "run(m, true)" in js
    assert "Object.assign({}, m.f || {}, fix)" in js   # the rest's checked links join those already shown


def test_every_language_explains_every_refusal_and_only_the_minute_limit_says_a_minute():
    """server.js answers 429 with a code per limit: rate_limited (the client's minute, or the Vercel Firewall rule — the
    wait is at most a minute), daily_limit (the client's 24 hours: hours), busy (the whole instance is full — not the
    visitor's doing). Every language has a text for each, and the day's text never promises a minute."""
    js = (ASSETS / "chat.js").read_text("utf-8")
    blocks = re.findall(r"\berr: \{(.*?)\}", js, re.S)
    assert len(blocks) == len(LABELS)
    keys = [set(re.findall(r'(\w+): "', b)) for b in blocks]
    assert all(k == keys[0] for k in keys), keys
    assert {"rate_limited", "daily_limit", "busy", "not_configured", "too_long", "network", "error"} <= keys[0]
    minute = re.compile(r"1분|minute|1分|一分|Minute|minuto|минут", re.I)
    for b in blocks:
        texts = dict(re.findall(r'(\w+): "([^"]+)"', b))
        assert minute.search(texts["rate_limited"]), texts["rate_limited"]
        assert not minute.search(texts["daily_limit"]), texts["daily_limit"]
        assert texts["daily_limit"] not in (texts["rate_limited"], texts["busy"], texts["error"])
    # a day's limit offers the site search instead of a retry that would only be refused again
    err_el = js[js.index("function errEl(m)"):js.index("function linksEl(")]
    assert 'm.e === "daily_limit"' in err_el


def test_chat_styles_keep_the_type_rules_targets_and_reduced_motion():
    panel = (ASSETS / "chat.css").read_text("utf-8")
    launcher = (ASSETS / "css" / "49-chat.css").read_text("utf-8")
    for css in (panel, launcher):
        weights = set(re.findall(r"font-weight:\s*(\d+)", css)) | set(re.findall(r"font:\s*(\d+)\s", css))
        assert weights <= {"400", "700"}, weights
        assert "prefers-reduced-motion" in css
    rules = dict(re.findall(r"(\.chat-[\w-]+) \{([^}]*)\}", panel))
    for sel in (".chat-ib", ".chat-send"):
        assert "width: 44px" in rules[sel] and "height: 44px" in rules[sel], sel
    for sel in (".chat-chip", ".chat-retry"):
        assert "min-height: 44px" in rules[sel], sel
    assert "height: 68px" in launcher and "height: 84px" in launcher and "safe-area-inset-bottom" in launcher
    assert "chat-up" not in launcher                                  # on every page from the first paint
    # an answer written right to left (QA 2026-10-15 F06): its lists indent on the side it starts from
    lists = re.findall(r"\.chat-md [uo]l \{([^}]*)\}", panel)
    assert len(lists) == 2 and all("padding-inline-start" in r and "padding-left" not in r for r in lists), lists
    assert ".chat-num { white-space: nowrap; }" in panel and ".chat-links[dir=rtl] .chat-card .icon" in panel
