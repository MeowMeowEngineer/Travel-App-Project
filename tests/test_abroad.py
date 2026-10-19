"""해외에서 본 군산 (/abroad/, owner 2026-10-13): our note + the link for articles (with the outlet's og:image from its
own address, never in JSON-LD), a card for social posts (no third-party script in the HTML — site.js loads the embed
near the screen), only published items, and the place page's block."""
import json
import re
import shutil
from html.parser import HTMLParser
from pathlib import Path

from pipeline.build import build
from pipeline.validate import validate
from tools.abroad_check import article_meta, item_from, platform_of

ROOT = Path(__file__).resolve().parent.parent
SAMPLE = ROOT / "data" / "sample"


def abroad_data(tmp_path):
    data = tmp_path / "data"
    shutil.copytree(SAMPLE, data)
    items = [
        {"id": "a1", "kind": "article", "source_type": "press", "outlet": "Example Daily", "lang": "en",
         "url": "https://news.example.org/gunsan-railroad", "title": "Walking the old tracks", "date": "2026-06-26",
         "note": "철길마을을 걸어서 둘러본 기사입니다.", "place_slugs": ["gyeongam-railroad-village"], "status": "published",
         "image": "https://img.example.org/tracks.jpg"},
        {"id": "a3", "kind": "article", "source_type": "blog", "outlet": "Old Blog", "url": "https://old.example.org/y",
         "title": "Plain http picture", "note": "사진 주소가 http인 기사입니다.", "place_slugs": [], "status": "published",
         "image": "http://old.example.org/pic.jpg"},
        {"id": "a2", "kind": "article", "source_type": "blog", "outlet": "Draft Blog", "url": "https://blog.example.org/x",
         "title": "Not yet", "note": "아직 승인 전입니다.", "place_slugs": ["gyeongam-railroad-village"], "status": "draft"},
        {"id": "p1", "kind": "post", "platform": "instagram", "url": "https://www.instagram.com/p/EXAMPLE1/",
         "author": "", "date": "2026-10", "note": "철길마을 교복 사진 게시물입니다.",
         "place_slugs": ["gyeongam-railroad-village"], "status": "published"},
        {"id": "p2", "kind": "post", "platform": "myspace", "url": "https://myspace.example/x", "note": "알 수 없는 서비스",
         "place_slugs": [], "status": "published"},
    ]
    (data / "abroad.json").write_text(json.dumps({"items": items}, ensure_ascii=False), "utf-8")
    return data


def test_abroad_page_and_place_block(tmp_path):
    data = abroad_data(tmp_path)
    out = tmp_path / "out"
    build(data, out, "sample")
    page = (out / "abroad" / "index.html").read_text("utf-8")
    assert "Walking the old tracks" in page and "철길마을을 걸어서 둘러본 기사입니다." in page
    assert "Not yet" not in page                                   # drafts stay out
    assert "알 수 없는 서비스" not in page                            # unknown services are not shown
    assert 'data-embed="instagram"' in page and "data-embed-load" in page
    assert "instagram.com/embed.js" not in page                     # no third-party script in the HTML itself
    thumb = page.split('src="https://img.example.org/tracks.jpg"', 1)[1].split(">", 1)[0]
    assert 'loading="lazy"' in thumb and 'referrerpolicy="no-referrer"' in thumb
    assert "old.example.org/pic.jpg" not in page                    # only https pictures
    ld = "".join(x.split("</script>", 1)[0] for x in page.split('<script type="application/ld+json">')[1:])
    assert "img.example.org" not in ld                              # the outlet's picture is not ours to describe
    place = (out / "places" / "gyeongam-railroad-village" / "index.html").read_text("utf-8")
    assert "해외에서 본" in place and "https://news.example.org/gunsan-railroad" in place and 'href="/abroad/"' in place
    ids = re.findall(r'\sid="([^"]+)"', page)
    assert len(ids) == len(set(ids)), [i for i in ids if ids.count(i) > 1]
    assert "/abroad/" in (out / "sitemap.xml").read_text("utf-8")
    errors, _, _ = validate(data, out, "sample")
    assert errors == [], errors[:5]


class WallScan(HTMLParser):
    """The /abroad/ SNS section: its list, and for each post card its service, its address, the text and the links a
    reader gets without JS (nothing inside [data-js-only]) and every link's visible text."""

    VOID = {"area", "base", "br", "col", "embed", "hr", "img", "input", "link", "meta", "source", "track", "wbr"}

    def __init__(self):
        super().__init__()
        self.stack = []          # (tag, in_section, js_only)
        self.walls = []          # the class / data-wall of each list in the section
        self.cards = []
        self.link = None

    def handle_starttag(self, tag, attrs):
        a = dict(attrs)
        sec, js = self.stack[-1][1:] if self.stack else (False, False)
        sec = sec or a.get("id") == "ab-sns"
        js = js or "data-js-only" in a
        if sec and tag == "ul":
            self.walls.append((a.get("class"), "data-wall" in a))
        if sec and tag == "li" and "data-embed" in a:
            self.cards.append({"kind": a["data-embed"], "url": a.get("data-url"), "text": "", "links": [], "all_links": []})
        if sec and tag == "a" and self.cards:
            self.link = {"href": a.get("href"), "text": "", "js_only": js}
        if tag not in self.VOID:
            self.stack.append((tag, sec, js))

    def handle_endtag(self, tag):
        if tag == "a" and self.link is not None:
            self.cards[-1]["all_links"].append(self.link)
            if not self.link["js_only"]:
                self.cards[-1]["links"].append(self.link)
            self.link = None
        if self.stack and tag not in self.VOID:
            self.stack.pop()

    def handle_data(self, data):
        if self.stack and self.stack[-1][1] and self.cards:
            if not self.stack[-1][2]:
                self.cards[-1]["text"] += data
            if self.link is not None:
                self.link["text"] += data


def test_sns_wall_one_card_per_post_with_note_and_link_without_js(tmp_path):
    """owner 2026-10-14 ('바둑판식'): the posts are one list ([data-wall], the tiles of the grid) with one card per published
    post in order; without JS each card still has our note and a link to the original named by the service, and no
    link anywhere shows a post's address as its text (the embed's own quote included — site.js names it too)."""
    data = abroad_data(tmp_path)
    raw = json.loads((data / "abroad.json").read_text("utf-8"))
    raw["items"].append({"id": "p3", "kind": "post", "platform": "x", "url": "https://x.com/someone/status/123",
                         "author": "someone", "date": "2026-09-01", "note": "철길마을 사진을 올린 일본어 게시물입니다.",
                         "place_slugs": ["gyeongam-railroad-village"], "status": "published"})
    (data / "abroad.json").write_text(json.dumps(raw, ensure_ascii=False), "utf-8")
    out = tmp_path / "out"
    build(data, out, "sample")
    scan = WallScan()
    scan.feed((out / "abroad" / "index.html").read_text("utf-8"))
    assert scan.walls == [("ab-wall", True)]                        # one list: the wall
    assert [(c["kind"], c["url"]) for c in scan.cards] == [
        ("instagram", "https://www.instagram.com/p/EXAMPLE1/"), ("x", "https://x.com/someone/status/123")]
    notes = {"instagram": "철길마을 교복 사진 게시물입니다.", "x": "철길마을 사진을 올린 일본어 게시물입니다."}
    labels = {"instagram": "Instagram", "x": "X"}
    for c in scan.cards:
        assert notes[c["kind"]] in c["text"]                        # our note, without JS
        orig = [ln for ln in c["links"] if ln["href"] == c["url"]]
        assert len(orig) == 1 and orig[0]["text"].startswith(f"{labels[c['kind']]}에서 보기")
        assert "/places/gyeongam-railroad-village/" in {ln["href"] for ln in c["links"]}   # its place as a chip
        assert c["url"] not in c["text"] and "://" not in c["text"]   # no address as text in the card
        for ln in c["all_links"]:
            assert "://" not in ln["text"] and "www." not in ln["text"], ln
    js = (ROOT / "templates" / "assets" / "site.js").read_text("utf-8")
    assert "a.textContent = url" not in js                          # the quote handed to the service is not the address


def test_home_sns_row_links_each_post_to_its_card(tmp_path):
    """owner 2026-10-14 ('SNS 게시물이 … 너무 구석에'): the home has a 'SNS에서 본 …' row — the published posts newest first,
    each our note under the service · account, each a link to its own card on /abroad/ (whose id is there), the count
    in the 'all' link, and no service's script or embed on the home. /abroad/ puts the wall right under its head."""
    data = abroad_data(tmp_path)
    raw = json.loads((data / "abroad.json").read_text("utf-8"))
    raw["items"].append({"id": "p3", "kind": "post", "platform": "x", "url": "https://x.com/someone/status/123",
                         "author": "someone", "date": "2026-09-01", "note": "철길마을 사진을 올린 일본어 게시물입니다.",
                         "place_slugs": [], "status": "published"})
    raw["items"].append({"id": "p4", "kind": "post", "platform": "x", "url": "https://x.com/draft/status/9",
                         "date": "2026-10-09", "note": "아직 승인 전 게시물입니다.", "place_slugs": [], "status": "draft"})
    (data / "abroad.json").write_text(json.dumps(raw, ensure_ascii=False), "utf-8")
    out = tmp_path / "out"
    build(data, out, "sample")
    home = (out / "index.html").read_text("utf-8")
    row = re.search(r'<ul class="hsns">(.*?)</ul>', home, re.S)
    assert row, "no SNS row on the home"
    hrefs = re.findall(r'<a class="hsns-c" href="([^"]+)"', row.group(1))
    assert hrefs == ["/abroad/#p1", "/abroad/#p3"]               # 2026-10 before 2026-09-01; no draft, no article
    assert "철길마을 교복 사진 게시물입니다." in row.group(1) and "<b>X</b> · someone" in row.group(1)
    assert "아직 승인 전" not in home
    assert 'href="/abroad/#ab-sns"' in home and "SNS 게시물 2개 모두" in home
    low = home.lower()
    assert "platform.twitter.com" not in low and "instagram.com/embed" not in low and "x.com/" not in low
    page = (out / "abroad" / "index.html").read_text("utf-8")
    for h in hrefs:
        assert f'id="{h.split("#")[1]}"' in page
    assert page.index('id="ab-sns"') < page.index('class="wrap ab-wrap"')   # the wall comes first


def test_no_abroad_page_without_items(tmp_path):
    data = tmp_path / "data"
    shutil.copytree(SAMPLE, data)
    out = tmp_path / "out"
    build(data, out, "production")
    assert not (out / "abroad").exists()


def test_check_tool_reads_og_image():
    body = ('<meta property="og:title" content="Gunsan walk"><meta property="og:site_name" content="Daily">'
            '<meta property="og:image" content="/img/walk.jpg">')
    m = article_meta(body, "https://news.example.org/a/1")
    assert m["title"] == "Gunsan walk" and m["image"] == "https://news.example.org/img/walk.jpg"
    assert article_meta('<meta property="og:image" content="https://x.example/favicon.svg">', "https://x.example/")["image"] == ""
    assert article_meta('<meta property="og:image" content="https://wimg.example.com">', "https://x.example/")["image"] == ""
    row = {"url": "https://news.example.org/a/1", "note": "우리 소개", "approve": "Y", "image": "-"}
    assert "image" not in item_from(row, {"ok": True, "image": "https://news.example.org/img/walk.jpg"}, "2026-10-13")
    row["image"] = ""
    assert item_from(row, {"ok": True, "image": "https://news.example.org/img/walk.jpg"}, "2026-10-13")["image"].endswith("walk.jpg")


def test_check_tool_platforms_and_approval():
    assert platform_of("https://www.instagram.com/p/abc/") == "instagram"
    assert platform_of("https://www.threads.com/@a/post/b") == "threads"
    assert platform_of("https://x.com/a/status/1") == "x"
    assert platform_of("https://m.facebook.com/a/posts/1") == "facebook"
    assert platform_of("https://www.koreaherald.com/article/1") == ""
    row = {"url": "https://x.com/a/status/1", "note": "우리 소개", "place_slugs": "선유도; 장자도", "approve": "y"}
    ok = item_from(row, {"ok": True, "platform": "x", "author": "a"}, "2026-10-13")
    assert ok["status"] == "published" and ok["kind"] == "post" and ok["place_slugs"] == ["선유도", "장자도"]
    failed = item_from(row, {"ok": False, "platform": "x", "why": "HTTP 404"}, "2026-10-13")
    assert failed["status"] == "draft"                             # a post that did not check out is never published
