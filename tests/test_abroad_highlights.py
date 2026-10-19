"""해외에서 본 군산 — /abroad/ highlights (owner 2026-10-13; quotations 2026-10-14): the row of round pictures under the
title (links to the originals; with JS they open the viewer; the pictures arrive after 'load'), the viewer written to
/abroad/highlights.json and fetched on the first press (<dialog>: the original's own words in a <blockquote lang cite>,
'— outlet · language · date', '원문 보기' in a new tab, a post's official-embed slot), the same quotation on the article
cards of /abroad/ (not on place pages), validate's checks, the quote checker (tools/abroad_quotes.py) and /abroad/
unchanged when there is no highlight data."""
import json
import re
import shutil
from html import unescape
from pathlib import Path

from pipeline.build import build
from pipeline.validate import highlight_problems, validate
from tools import abroad_quotes

ROOT = Path(__file__).resolve().parent.parent
SAMPLE = ROOT / "data" / "sample"
PHOTO = "https://tong.visitkorea.or.kr/cms/resource/11/1111111_image2_1.jpg"
SMALL = PHOTO.replace("_image2_1", "_image3_1")

ITEMS = [
    {"id": "a1", "kind": "article", "source_type": "press", "outlet": "Example Daily", "lang": "en",
     "url": "https://news.example.org/gunsan-railroad", "title": "Walking the old tracks", "date": "2026-06-26",
     "note": "철길마을을 걸어서 둘러본 기사입니다.", "place_slugs": ["gyeongam-railroad-village"], "status": "published",
     "image": "https://img.example.org/tracks.jpg"},
    {"id": "a2", "kind": "article", "source_type": "blog", "outlet": "Lake Blog", "lang": "ja",
     "url": "https://blog.example.jp/lake", "title": "湖の公園", "date": "2025-04",
     "note": "호수공원을 걸은 일본어 블로그 글입니다.", "place_slugs": ["eunpa-lake-park"], "status": "published"},
    {"id": "a3", "kind": "article", "source_type": "blog", "outlet": "Studio Blog", "lang": "en",
     "url": "https://studio.example.org/x?a=1&b=2", "title": "A photo studio", "note": "사진관을 다룬 글입니다.",
     "place_slugs": ["chowon-photo-studio"], "status": "published"},
    {"id": "d1", "kind": "article", "source_type": "blog", "outlet": "Draft Blog", "url": "https://draft.example.org/x",
     "title": "Not yet", "note": "아직 승인 전입니다.", "place_slugs": [], "status": "draft"},
    {"id": "p1", "kind": "post", "platform": "instagram", "url": "https://www.instagram.com/p/EXAMPLE1/",
     "author": "", "date": "2026-10", "note": "철길마을 교복 사진 게시물입니다.",
     "place_slugs": ["gyeongam-railroad-village"], "status": "published"},
    {"id": "p2", "kind": "post", "platform": "x", "url": "https://x.com/example/status/1", "author": "うみねこ",
     "date": "2026-09-22", "note": "섬 해안 도로 사진을 올린 일본어 게시물입니다.", "place_slugs": [], "status": "published"},
]
Q1 = "Walking the old tracks was the best part of our day in town."
Q2 = "湖のまわりの散歩道は、静かで歩きやすい。"
Q3 = "It's a lovely old studio & a quiet lane — worth the detour."
Q4 = "西側の海沿い良き"
HL = [
    {"id": "a1", "label_ko": "철길마을", "quote": Q1, "quote_lang": "en", "quote_checked": "2026-10-14",
     "praise_ko": "영어권 신문 기자가 철길마을의 옛 선로 산책을 좋게 평가했습니다.",   # the retired summary: never shown
     "basis_ko": "기사가 산책을 칭찬함", "checked": "2026-10-14"},
    {"id": "a2", "quote": Q2, "quote_lang": "ja", "quote_checked": "2026-10-14",
     "basis_ko": "글이 산책로를 좋게 씀", "checked": "2026-10-14"},
    {"id": "p1", "label_ko": "교복 사진", "basis_ko": "게시물 내용(인스타그램은 oEmbed가 글을 주지 않아 인용하지 않음)",
     "checked": "2026-10-14"},
    {"id": "a3", "label_ko": "사진관", "quote": Q3, "quote_lang": "en", "quote_checked": "2026-10-14",
     "basis_ko": "글이 분위기를 좋게 씀", "checked": "2026-10-14"},
    {"id": "p2", "label_ko": "섬 해안길", "quote": Q4, "quote_lang": "ja", "quote_checked": "2026-10-14",
     "basis_ko": "X oEmbed가 돌려준 게시물 글", "checked": "2026-10-14"},
]
ORIGINALS = ["https://news.example.org/gunsan-railroad", "https://blog.example.jp/lake",
             "https://www.instagram.com/p/EXAMPLE1/", "https://studio.example.org/x?a=1&b=2",
             "https://x.com/example/status/1"]


def data_with(tmp_path, highlights=None, items=ITEMS):
    data = tmp_path / "data"
    shutil.copytree(SAMPLE, data)
    places = json.loads((data / "places.json").read_text("utf-8"))
    for e in places:   # a KOGL-1 TourAPI photo of the lake park, with its provider's small rendition measured
        if e["slug"] == "eunpa-lake-park":
            e["images"] = [{"url": PHOTO, "alt": "호수 산책로", "credit": "한국관광공사", "license": "KOGL-1",
                            "source": "TourAPI"}]
    (data / "places.json").write_text(json.dumps(places, ensure_ascii=False), "utf-8")
    (data / "image_sizes.json").write_text(json.dumps({PHOTO: [940, 627, 100000], SMALL: [300, 200, 12000]}), "utf-8")
    (data / "abroad.json").write_text(json.dumps({"items": items}, ensure_ascii=False), "utf-8")
    if highlights is not None:
        (data / "abroad_highlights.json").write_text(json.dumps({"items": highlights}, ensure_ascii=False), "utf-8")
    return data


def test_highlights_row_and_viewer(tmp_path):
    data = data_with(tmp_path, HL)
    out = tmp_path / "out"
    build(data, out, "sample")
    page = (out / "abroad" / "index.html").read_text("utf-8")
    head = page.split('<h1 id="h-list"', 1)[1].split('<nav class="v-nav"', 1)[0]
    assert 'data-hl="/abroad/highlights.json"' in head               # the row sits right under the title
    row = re.search(r'<section class="hl"[^>]*data-hl="[^"]+">(.*?)</section>', page, re.S).group(1)
    links = re.findall(r'<a class="hl-a" href="([^"]+)" rel="noopener" data-hl-open="(\d+)">', row)
    assert [(unescape(h), i) for h, i in links] == [(h, str(i)) for i, h in enumerate(ORIGINALS)]   # file order
    imgs = [i for i in re.findall(r"<img [^>]*>", row) if "/assets/icons/" not in i]   # not the badges' globe
    assert len(imgs) == 2                                            # og:image and the KOGL-1 photo; the others are badges
    assert not any(re.search(r"\ssrcs?(et)?=", i) for i in imgs)    # pictures wait for 'load' (data-src): never the LCP
    og = next(i for i in imgs if 'data-src="https://img.example.org/tracks.jpg"' in i)
    assert 'loading="lazy"' in og and 'referrerpolicy="no-referrer"' in og and 'alt=""' in og
    kto = next(i for i in imgs if f'data-src="{SMALL}"' in i)        # the provider's small rendition, not the original
    assert 'loading="lazy"' in kto and 'data-kogl="1"' in kto
    assert PHOTO not in row
    assert row.count('class="hl-badge"') == 5                         # a badge under every picture
    # under each picture the 3D globe, not language / service letters ('EN' read as a label, owner 2026-10-14)
    assert ">IG<" not in row and ">EN<" not in row and row.count('data-pic="icon-abroad"') == 5
    assert "철길마을" in row and "Lake Blog" in row                   # label_ko, else the outlet
    assert "한국관광공사" in row                                      # the KOGL-1 photo's credit under the row

    assert "<dialog" not in page                                     # the viewer is not in the page's first load
    viewer = json.loads((out / "abroad" / "highlights.json").read_text("utf-8"))["html"]
    dlg = re.fullmatch(r"<dialog ([^>]*)>(.*)</dialog>", viewer.strip(), re.S)
    attrs, body = dlg.group(1), dlg.group(2)
    assert 'aria-labelledby="hl-dlg-h"' in attrs and "hidden" in attrs and "data-hl-dialog" in attrs
    assert 'id="hl-dlg-h"' in body
    slides = re.split(r'(?=<div class="hl-s" )', body)[1:]
    assert [re.match(r'<div class="hl-s" role="group" aria-roledescription="하이라이트" aria-label="(\d+) / 5"'
                     r' tabindex="-1" data-hl-slide hidden', x).group(1) for x in slides] == ["1", "2", "3", "4", "5"]
    # each card quotes the original in its own language, untranslated: <blockquote lang cite> + '— source' under it
    for x, h, url in zip(slides, HL, ORIGINALS):
        quotes = re.findall(r'<blockquote lang="([^"]+)" cite="([^"]+)"><p>(.*?)</p></blockquote>', x, re.S)
        if "quote" not in h:
            assert quotes == [] and "<blockquote" not in x           # Instagram: its official embed only
            continue
        assert [(lg, unescape(c), unescape(q)) for lg, c, q in quotes] == [(h["quote_lang"], url, h["quote"])]
        cap = re.search(r'</blockquote>\s*<figcaption class="hl-meta"><span aria-hidden="true">— </span>(.*?)</figcaption>',
                        x, re.S).group(1)
        assert 'class="ab-src"' in cap
    assert unescape(body).count(Q3) == 1 and "It&#39;s a lovely old studio &amp; a quiet lane" in body   # escaped once
    assert "Example Daily" in body and "영어" in body and "2026년 6월 26일" in body and "2025년 4월" in body
    x_card = slides[4]                                               # an X post: its quote's language, the account in it
    assert 'data-embed="x"' in x_card and '<span lang="ja">うみねこ</span> · <span>일본어</span>' in x_card
    assert x_card.index("<blockquote") < x_card.index("data-embed-slot")   # the quotation first, then the embed
    assert "<blockquote" not in slides[2] and 'data-embed="instagram"' in slides[2]
    assert HL[0]["praise_ko"] not in page + viewer                  # our own words never stand in for the original
    assert not any(h["basis_ko"] in page + viewer for h in HL)       # basis_ko is ours, never on the page
    go = re.findall(r'<a class="hl-go" href="([^"]+)" target="_blank" rel="noopener"', body)
    assert [unescape(g) for g in go] == ORIGINALS
    assert "data-hl-close" in body and '<span class="vh">닫기</span>' in body
    assert 'data-hl-dir="-1"' in body and 'data-hl-dir="1"' in body
    post = body.split('data-embed="instagram"', 1)[1].split('class="hl-s"', 1)[0]
    assert 'data-url="https://www.instagram.com/p/EXAMPLE1/"' in post and "data-embed-slot" in post and "data-embed-load" in post
    assert "instagram.com/embed.js" not in page + viewer            # the service's script only when the card is shown
    ids = re.findall(r'\sid="([^"]+)"', page + viewer)              # the dialog joins the page on the first press
    assert len(ids) == len(set(ids)), [i for i in ids if ids.count(i) > 1]
    assert (out / "assets" / "highlights.js").exists()
    assert "assets/highlights.js" not in page                        # site.js attaches it on the first press

    # the article cards of /abroad/ carry the same quotation under our note; the place page's block does not
    cards = re.findall(r'<blockquote class="ab-q" lang="([^"]+)" cite="([^"]+)"><p>(.*?)</p></blockquote>', page, re.S)
    assert sorted((lg, unescape(c), unescape(q)) for lg, c, q in cards) == sorted(
        [("en", ORIGINALS[0], Q1), ("ja", ORIGINALS[1], Q2), ("en", ORIGINALS[3], Q3)])
    a1 = page.split('href="https://news.example.org/gunsan-railroad" rel="noopener" lang="en"', 1)[1].split("</li>", 1)[0]
    assert a1.index('class="ab-note"') < a1.index('class="ab-q"')
    place = (out / "places" / "gyeongam-railroad-village" / "index.html").read_text("utf-8")
    assert "https://news.example.org/gunsan-railroad" in place and "ab-q" not in place and Q1 not in place

    errors, _, _ = validate(data, out, "sample")
    assert errors == [], errors[:5]
    (out / "abroad" / "highlights.json").unlink()                  # validate notices a viewer without the quotations
    errors, _, _ = validate(data, out, "sample")
    assert sum("하이라이트가 보기 창에 없음" in e for e in errors) == 5
    assert sum("인용문이 보기 창에 blockquote(lang·cite)로 없음" in e for e in errors) == 4
    f = out / "abroad" / "index.html"                               # …and an article card without its quotation
    f.write_text(page.replace('<blockquote class="ab-q" lang="ja"', '<blockquote class="ab-q" lang="en"'), "utf-8")
    errors, _, _ = validate(data, out, "sample")
    assert [e for e in errors if "인용문이 기사 카드에 없음" in e] == ["[/abroad/] 인용문이 기사 카드에 없음: a2"]


def test_page_unchanged_without_highlights(tmp_path):
    pages = []
    for n, hl in enumerate((None, [])):
        data = data_with(tmp_path / f"d{n}", hl)
        out = tmp_path / f"out{n}"
        build(data, out, "sample")
        pages.append((out / "abroad" / "index.html").read_text("utf-8"))
        assert not (out / "abroad" / "highlights.json").exists()
    assert pages[0] == pages[1]
    for marker in ("data-hl", "hl-dlg", "<dialog", "하이라이트"):
        assert marker not in pages[0]
    hero = pages[0].split('<h1 id="h-list"', 1)[1].split("</section>", 1)[0]
    assert re.search(r'</h1>\s*<p class="lede">[^<]*</p>\s*<nav class="v-nav"', hero)   # title, lede, then the nav


def test_highlight_problems(tmp_path):
    long = " ".join(["word"] * 46)
    bad = [
        {"id": "zz", "quote": "Nowhere.", "quote_lang": "en", "quote_checked": "2026-10-14", "basis_ko": "-",
         "checked": "2026-10-14"},
        {"id": "d1", "quote": "Not yet out.", "quote_lang": "en", "quote_checked": "2026-10-14", "basis_ko": "-",
         "checked": "2026-10-14"},
        {"id": "a1", "quote": "“The best walk in town.”", "basis_ko": "-", "checked": "2026-10-14"},
        {"id": "a1", "quote": long + " " + "x" * 80, "quote_lang": "en", "quote_checked": "10/14", "basis_ko": "",
         "checked": "10/13", "label_ko": "아주 긴 썸네일 이름입니다"},
        {"id": "a2", "praise_ko": "일본어 블로거가 산책로를 좋게 봤습니다.", "basis_ko": "-", "checked": "2026-10-14"},
        {"id": "p1", "quote": "Uniform photos!", "quote_lang": "en", "quote_checked": "2026-10-14", "basis_ko": "-",
         "checked": "2026-10-14"},
        {"id": "nourl", "quote": "A quote with no address.", "quote_lang": "en", "quote_checked": "2026-10-14",
         "basis_ko": "-", "checked": "2026-10-14"},
        {"id": "p2", "basis_ko": "인용 없이 임베드만", "checked": "2026-10-14"},
    ]
    nourl = {"id": "nourl", "kind": "article", "source_type": "blog", "outlet": "No URL", "lang": "en", "url": "",
             "title": "No address", "note": "주소가 빠진 항목입니다.", "place_slugs": [], "status": "published"}
    data = data_with(tmp_path, bad, items=ITEMS + [nourl])
    problems = highlight_problems(data)
    text = "\n".join(problems)
    assert "items[1] zz: abroad.json에 없는 id" in text
    assert "items[2] d1: abroad.json 항목이 /abroad/에 나가지 않음" in text
    assert "items[3] a1: quote를 따옴표로 감쌈" in text and "items[3] a1: quote_lang" in text
    assert "items[3] a1: quote_checked" in text
    assert "items[4] a1: 같은 id가 두 번 있음" in text
    assert "items[4] a1: quote 310자 — 300자 이하" in text and "items[4] a1: quote 47단어 — 45단어 이하로" in text
    assert "items[4] a1: quote_checked" in text and "items[4] a1: basis_ko" in text
    assert "items[4] a1: checked" in text and "items[4] a1: label_ko" in text
    assert "items[5] a2: quote(원문 인용) 없음" in text                # an article needs the original's words…
    assert "items[6] p1: instagram 게시물은 oEmbed가 글을 주지 않아" in text   # …an Instagram post cannot have them
    assert "items[7] nourl: abroad.json 항목이 /abroad/에 나가지 않음" in text
    assert "items[7] nourl: 인용문의 원문 주소(abroad.json url, https)가 없음" in text
    assert not any(x.startswith("items[8]") for x in problems)       # an X post may go without a quotation
    out = tmp_path / "out"
    build(data, out, "sample")                                       # the build leaves out what it cannot show
    page = (out / "abroad" / "index.html").read_text("utf-8")
    # shown: items[4] a1 (its quote has a language), items[6] p1 and items[8] p2 (posts); not the unknown, the draft,
    # the quote without a language, the article without a quote (a2's retired praise_ko is no stand-in) or no address
    assert page.count("data-hl-open=") == 3 and "Nowhere." not in page and "Not yet out." not in page
    assert "산책로를 좋게 봤습니다" not in page
    errors, _, _ = validate(data, out, "sample")
    assert any(e.startswith("[abroad_highlights.json] items[1] zz") for e in errors)
    assert highlight_problems(data_with(tmp_path / "ok", HL)) == []


def page_html(*paragraphs: str, script: str = "") -> str:
    return (f"<!doctype html><html><head><title>t</title><script>{script}</script></head><body><nav>Menu</nav>"
            + "".join(f"<p>{x}</p>" for x in paragraphs) + "</body></html>")


def test_quote_checker(tmp_path):
    """tools/abroad_quotes.py fetches each original again and looks for the stored quotation in its visible text:
    whitespace and inline markup do not matter, block boundaries and script / head text do; an X post is read through
    its oEmbed; an address that does not answer is reported, never passed."""
    hl = [dict(h) for h in HL]
    hl[3]["quote"] = "Only in a script tag."                         # a3: present in the HTML, but not visible
    data = data_with(tmp_path, hl)
    pages = {
        "https://news.example.org/gunsan-railroad": (200, page_html(
            "Intro.", "Walking the old <a href='#'>tracks</a> was the best\n part of  our day&nbsp;in town. Later more.")),
        "https://blog.example.jp/lake": (451, "Unavailable For Legal Reasons"),
        "https://studio.example.org/x?a=1&b=2": (200, page_html("A studio.", script="var q = 'Only in a script tag.';")),
    }
    asked = []

    def get(url):
        asked.append(url)
        if url.startswith(abroad_quotes.X_OEMBED):
            assert "url=https%3A%2F%2Fx.com%2Fexample%2Fstatus%2F1" in url
            return 200, json.dumps({"html": '<blockquote class="twitter-tweet"><p lang="ja" dir="ltr">写真 '
                                            '<a href="#">#群山</a> 西側の海沿い良き</p>&mdash; うみねこ</blockquote>'})
        return pages[url]

    rows = {hid: (state, detail) for hid, state, detail in abroad_quotes.check(data, get=get)}
    assert set(rows) == {"a1", "a2", "a3", "p2"}                     # p1 (Instagram) has no quotation to check
    assert rows["a1"][0] == "ok" and rows["p2"][0] == "ok"
    assert rows["a2"] == ("unreadable", "HTTP 451")
    assert rows["a3"][0] == "mismatch"
    assert len(asked) == len(set(asked)) == 4                        # each original fetched once
    assert abroad_quotes.visible_text("<div><p>One.</p><p>Two</p></div>") == "One. Two"   # blocks never run together
    assert abroad_quotes.visible_text("<p>a<b>b</b>c</p>") == "abc"  # inline markup joins as written
    assert abroad_quotes.decode("湖".encode("euc-jp"), "text/html; charset=EUC-JP") == "湖"


def test_quote_checker_exit_code(tmp_path, monkeypatch, capsys):
    data = data_with(tmp_path, HL[:1])
    monkeypatch.setattr(abroad_quotes, "fetch", lambda url: (200, page_html(Q1)))
    assert abroad_quotes.main(["--data", str(data)]) == 0
    assert "일치 1" in capsys.readouterr().out
    monkeypatch.setattr(abroad_quotes, "fetch", lambda url: (200, page_html("Something else entirely.")))
    assert abroad_quotes.main(["--data", str(data)]) == 1
    assert "불일치" in capsys.readouterr().out
