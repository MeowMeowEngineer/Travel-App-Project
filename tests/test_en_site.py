"""The English site (/en/, pipeline/en_site.py): built in production from a copy of data/gunsan in which one Korean
summary was edited after translation (its English record is then stale and must not be rendered)."""
import json
import re
import shutil
import xml.etree.ElementTree as ET
from pathlib import Path
from urllib.parse import unquote, urlsplit

import pytest

from pipeline.build import build
from pipeline.en_site import en_slug, sentences_en
from pipeline.validate import PageScan, hreflang_problems, scan_file, validate

ROOT = Path(__file__).resolve().parent.parent
GUNSAN = ROOT / "data" / "gunsan"
SAMPLE = ROOT / "data" / "sample"
STALE_ID = "gunsan-305395"      # 근대역사박물관: its Korean summary is edited in the copy
HANGUL = re.compile(r"[가-힣]")


@pytest.fixture(scope="module")
def site(tmp_path_factory):
    tmp = tmp_path_factory.mktemp("en")
    data = tmp / "data"
    shutil.copytree(GUNSAN, data)
    places = json.loads((data / "places.json").read_text("utf-8"))
    p = next(x for x in places if x["id"] == STALE_ID)
    p["summary"] = p["summary"] + " 번역 뒤에 바뀐 문장입니다."
    (data / "places.json").write_text(json.dumps(places, ensure_ascii=False), "utf-8")
    out = tmp / "dist"
    stats = build(data, out, "production")
    return {"data": data, "out": out, "stats": stats, "ko_slug": p["slug"]}


def _html_files(out: Path, prefix: str = "en"):
    return sorted((out / prefix).rglob("*.html"))


def test_sample_build_has_no_english_site(tmp_path):
    out = tmp_path / "s"
    stats = build(SAMPLE, out, "sample")
    assert "en" not in stats and not (out / "en").exists()
    for f in out.rglob("*.html"):
        html = f.read_text("utf-8")
        assert "hreflang" not in html and 'class="mast-lang"' not in html, f
    errors, _, _ = validate(SAMPLE, out, "sample")
    assert errors == []


def test_page_scan_finds_hangul_outside_lang_ko():
    p = PageScan()
    p.feed('<html lang="en"><head><title>Hello</title></head><body><p>Hi 안녕</p><p><span lang="ko">군산</span></p>'
           '<img alt="사진" src="x.jpg"><a href="/places/동국사/" lang="ko">한국어</a></body></html>')
    assert p.html_lang == "en"
    assert p.hangul == ["Hi 안녕", "<img alt> 사진"]


def test_hreflang_problems_catch_one_sided_pairs():
    ko, en = "https://x.test/a/", "https://x.test/en/a/"
    both = [("ko", ko), ("en", en), ("x-default", ko)]
    assert hreflang_problems({"/a/index.html": (ko, both), "/en/a/index.html": (en, both)}) == []
    assert hreflang_problems({"/a/index.html": (ko, both), "/en/a/index.html": (en, [])})
    wrong = [("ko", ko), ("en", en), ("x-default", en)]
    assert hreflang_problems({"/a/index.html": (ko, wrong), "/en/a/index.html": (en, wrong)})


def test_slugs_and_sentences():
    assert en_slug("Eunpa Lake Park") == "eunpa-lake-park"
    assert en_slug("Course A Modern–Gogunsan") == "course-a-modern-gogunsan"
    assert en_slug("Where and when to eat jjamppong, marinated blue crab and bakdae in Gunsan") == \
        "where-and-when-to-eat-jjamppong-marinated-blue-crab"
    assert sentences_en("It is Registered Cultural Heritage No. 64. Dr. Lee built it. Open daily.") == \
        ["It is Registered Cultural Heritage No. 64.", "Dr. Lee built it.", "Open daily."]
    assert not HANGUL.search(en_slug("동국사 Dongguksa Temple"))


def _filter_bar(html: str) -> dict:
    """The list page's filter bar: {key: [(value, label, n)]}, the check box, the view switch and the rows' keys."""
    bar = re.search(r'<div class="filters" data-filters hidden>.*?<div class="ledger" data-ledger>', html, re.S)
    assert bar, "no filter bar"
    bar = bar.group(0)
    chips = {}
    for k, v, lab, n in re.findall(r'<button type="button" data-f="(\w+)" data-v="([^"]*)" aria-pressed="[^"]*">([^<]*?)\s*(?:<span class="tn">(\d+)</span>)?</button>', bar):
        chips.setdefault(k, []).append((html_unescape(v), lab.strip(), int(n or 0)))
    check = re.search(r'<input type="checkbox" data-f="check" value="(\w+)"> ([^<]*?) <span class="tn">(\d+)</span>', bar)
    rows = re.findall(r'<li class="rec"[^>]*>', html)
    return {"chips": chips, "check": check.groups() if check else None, "views": re.findall(r'data-view="(\w+)"', bar),
            "rows": rows, "result": re.search(r'<span data-result data-forms="([^"]*)" data-of="([^"]*)">', bar)}


def html_unescape(s: str) -> str:
    import html as H
    return H.unescape(s)


# ------------------------------------------------------------------ 예약하기 (pipeline/booking.py, ui.book)
BOOK_RX = re.compile(r'<div class="book[^"]*" data-block="booking">.*?</div>', re.S)
BOOK_A = re.compile(r'<a [^>]*data-track="booking_click"[^>]*>')


def _with(out: Path, code: str, needle: str, subs=("places", "food", "stays", "guides", "courses")) -> list[str]:
    """The pages of a version (ko: the root) under subs whose HTML contains needle."""
    base = out if code == "ko" else out / code
    return [t for s in subs for f in sorted((base / s).glob("*/index.html")) if needle in (t := f.read_text("utf-8"))]
