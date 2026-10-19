"""해외에서 본 군산 (/abroad/, owner 2026-10-13): our note + the link for articles (with the outlet's og:image from its
own address, never in JSON-LD), a card for social posts (no third-party script in the HTML — site.js loads the embed
near the screen), only published items, and the place page's block."""
import json
import re
import shutil
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
