"""Scenario QA of 2026-10-19, second round — the search and the font budget of long lists, read from a build of the
Incheon configuration with the tiny fixture (tests/fixtures/incheon_tiny, made-up places) and from the stylesheets.
The search's matching itself (QA-24, QA-70, QA-72) is tested in tests/js/search.test.js, in a browser in
tests/test_qa2_search_browser.py.

QA-06 /search/ without a query fetched 404 KB of fonts, QA-71 /cafes/ 301 KB (budget 300 KB): the rows of a group are
skipped one by one off screen, and the breadcrumbs' mark is drawn, not the '›' that alone cost a 36 KB font file."""
import re
import shutil
from pathlib import Path

import pytest

from pipeline import locales as LC
from pipeline.build import build

ROOT = Path(__file__).resolve().parent.parent
INCHEON = ROOT / "data" / "incheon"
TINY = Path(__file__).resolve().parent / "fixtures" / "incheon_tiny"
RECORDS = ("places.json", "events.json", "courses.json", "guides.json", "themes.json", "videos.json")
CSS = "\n".join(f.read_text("utf-8") for f in sorted((ROOT / "templates" / "assets" / "css").glob("*.css")))
FONTS = (ROOT / "templates" / "assets" / "vendor" / "pretendard" / "pretendard.css").read_text("utf-8")


@pytest.fixture(scope="module")
def site(tmp_path_factory):
    tmp = tmp_path_factory.mktemp("qa2s")
    data = tmp / "data"
    data.mkdir()
    for f in INCHEON.glob("*.json"):
        if f.name not in RECORDS:
            shutil.copy(f, data / f.name)
    for f in TINY.glob("*.json"):
        shutil.copy(f, data / f.name)
    out = tmp / "out"
    build(data, out, "preview")
    return out


def _chunk(ch: str, weight: int = 400) -> str:
    """The Pretendard file of one weight whose unicode-range has ch (the last declared wins, as in CSS)."""
    hit = ""
    for face in re.findall(r"@font-face\s*\{[^}]*\}", FONTS):
        m = re.search(rf"font-weight:{weight};[^}}]*src:url\((Pretendard-[^)]+)\)[^}}]*unicode-range:([^;}}]+)", face)
        if not m:
            continue
        for part in m.group(2).split(","):
            a, _, b = part.strip()[2:].partition("-")
            if int(a, 16) <= ord(ch) <= int(b or a, 16):
                hit = m.group(1)
    return hit


def test_the_breadcrumbs_mark_is_drawn_not_a_character_of_its_own_font_file(site):
    """QA-71: the one '›' between the breadcrumbs was the only character of the page in its Pretendard file."""
    core = _chunk("A")
    assert _chunk("›") != core   # the reason: not in the core file every page fetches
    for page in ("search", "cafes", "places", "map"):
        html = (site / page / "index.html").read_text("utf-8")
        crumbs = re.search(r'<nav class="crumbs".*?</nav>', html, re.S).group(0)
        assert "›" not in crumbs and '<span class="crumb-sep" aria-hidden="true"></span>' in crumbs, page
    assert re.search(r"\.crumbs \.crumb-sep \{[^}]*border-width:", CSS)
    for tpl in ("_ui.html.j2", "en/_chrome.html.j2"):
        assert ">›</span>" not in re.search(r"macro crumbs.*?endmacro", (ROOT / "templates" / tpl).read_text("utf-8"),
                                             re.S).group(0), tpl


def test_long_groups_are_skipped_row_by_row_and_their_focus_rings_stay_whole():
    """QA-06, QA-71: a group near the top was drawn whole (the directory's first 234 names, a list's second group) and
    every rare syllable in it fetched a font file; rows after the first few of a group now wait off screen, each with
    an estimated height, and the paint clip leaves room for a focus ring (overflow-clip-margin)."""
    rule = re.search(r"\n([^{}\n]*nth-child[^{}\n]*)\{\s*content-visibility:\s*auto;\s*contain-intrinsic-size:\s*auto \d+px;\s*\}", CSS)
    sels = [s.strip() for s in rule.group(1).split(",")]
    assert {".recs > .rec:nth-child(n+4)", ".dir-list > li:nth-child(n+9)", ".res-g li:nth-child(n+9)"} <= set(sels)
    assert re.search(r"\.dir-list > li:nth-child\(n\+9\) \{ contain-intrinsic-size: auto \d+px; \}", CSS)
    assert re.search(r"\.cvk, \.recs > \.rec, \.dir-list > li, \.res-g li \{ overflow-clip-margin: 8px; \}", CSS)
    # the directory is a grid, not columns: a row drawn late changes its own row's height only
    d = re.search(r"\.dir-list \{([^}]*)\}", CSS).group(1)
    assert "display: grid" in d and not re.search(r"(?:^|;)\s*columns:", d)


def test_a_query_in_the_address_fetches_the_index_at_once(site):
    """The results are the largest text of /search/?q=…: a preload starts the index with the page (a long query painted
    them at 2.5 s on a slow phone, 1.9 s with it); without a query nothing is fetched."""
    head = (site / "search" / "index.html").read_text("utf-8").split("</head>", 1)[0]
    script = re.search(r"<script>\(function\(h\)\{if\(/\[\?&\]q=\[\^&\]/\.test\(location\.search\)\)\{(.*?)</script>", head).group(1)
    assert "l.rel='preload'" in script and "l.as='fetch'" in script and "l.href='/search/index.json'" in script
    assert "l.crossOrigin='anonymous'" in script   # the same request search.js's fetch makes (no second download)


def test_every_version_names_the_more_button():
    """QA-70: the rows past the first 80 are one press away in every version ('{n}' the next batch)."""
    for code, w in LC.SEARCH_WORDS.items():
        assert "{n}" in w.get("more", ""), code
    src = (ROOT / "pipeline" / "en_site.py").read_text("utf-8")
    assert '"related", "syn", "more")' in src
