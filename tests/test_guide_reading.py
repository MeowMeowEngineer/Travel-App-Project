"""The guide reading layer (owner 2026-10-09: "guide pages are walls of prose — fine for AI, tiring for people").
Every sentence of a guide stays on its page, verbatim and in order (Korean and English); the layer only wraps spans
of the guide's own text: figures emphasised (present.rich), the guide's places linked once per section, the summary's
first sentence as the answer line with the summary still one run in the DOM, mini cards, the table of contents, the
FAQ as an accordion with every answer in the DOM. Also: a menu price is never cut at its thousands comma."""
import html as htmlmod
import re
from pathlib import Path

import pytest

from pipeline import en_site, present
from pipeline.build import State, build
from pipeline.textutil import squash_ws
from pipeline.validate import PageScan

ROOT = Path(__file__).resolve().parent.parent
DATA = ROOT / "data" / "gunsan"
BLOCK_END = re.compile(r"</(?:li|p|h[1-6]|dt|dd|div|section|summary|details|ol|ul|nav|header|figure|figcaption|td|th)>|<br\s*/?>")


def text_of(markup: str) -> str:
    """What a reader sees: inline tags join their text without a space (unlike PageScan), block ends separate it."""
    t = BLOCK_END.sub(" ", str(markup))
    t = re.sub(r"<script\b.*?</script>|<style\b.*?</style>", " ", t, flags=re.S)
    return squash_ws(htmlmod.unescape(re.sub(r"<[^>]+>", "", t)))


@pytest.fixture(scope="module")
def S():
    return State(DATA, "preview")


@pytest.fixture(scope="module")
def built(tmp_path_factory):
    out = tmp_path_factory.mktemp("guides") / "preview"
    build(DATA, out, "preview")
    return out


def test_rich_keeps_every_character_and_marks_only_figures():
    names = [{"name": "근대역사박물관", "path": "/places/a/", "id": "p1"}, {"name": "채만식 문학관", "path": "/places/b/", "id": "p2"}]
    t = ("근대역사박물관 1층에는 126㎡ 넓이의 어린이박물관이 있고, 어린이 500원·통합권 1,000원이며 10:00~19:00에 열고 "
         "매주 월요일과 월·화요일에 쉬며 01·18·19번과 11~19·61번 버스가 서고 2시간30분 걸립니다(문의 063-443-3077).")
    seen: set = set()
    h = present.rich(t, "ko", names, seen)
    assert text_of(h) == t
    assert h.count('class="gl"') == 1 and 'href="/places/a/"' in h and seen == {"p1"}
    figs = re.findall(r'class="gk"[^>]*>([^<]+)</b>', h)
    assert figs == ["126㎡", "500원", "1,000원", "10:00~19:00", "월요일", "월·화요일", "01·18·19번", "11~19·61번", "2시간30분"]
    assert 'href="tel:0634433077"' in h
    # a place already linked in this section is not linked again (and never emphasised inside)
    again = present.rich("근대역사박물관·채만식 문학관", "ko", names, seen)
    assert again.count('class="gl"') == 1 and 'href="/places/b/"' in again
    # dates, years, floors, titles and phone digits are not figures
    for plain in ("2026-10-08 조회", "「8월의 크리스마스」(1998)", "3층 전시관", "2024.10.21 시행", "4200t급", "LJ463"):
        assert 'class="gk"' not in present.rich(plain), plain
    # skip: no markup starts inside the first characters (the validator compares them as one run)
    h = present.rich("이 사이트에 실린 군산 숙소 89곳의 정보에는 객실 25실", skip=present.PLAIN_HEAD)
    assert re.findall(r'class="gk"[^>]*>([^<]+)', h) == ["25실"]
    # English figures
    t = "About 500 m away; 1,000 won; 10:00–19:00 on Mondays; ages 6 and under; from 18 months; 16 pieces; 2 hours 30 minutes."
    h = present.rich(t, "en")
    assert text_of(h) == t
    assert re.findall(r'class="gk"[^>]*>([^<]+)</b>', h) == ["500 m", "1,000 won", "10:00–19:00", "Mondays", "ages 6 and under",
                                                              "18 months", "16 pieces", "2 hours 30 minutes"]
    # the roll-in hook: every figure with digits (its own digits roll; a weekday has none), only when asked, never
    # [data-roll] (the home story's year)
    h = present.rich("16대 · 1.5km · 20,900원 · 10:00~19:00 · 7~12세 · 월요일", roll=True)
    assert re.findall(r'<b class="gk" data-numroll>([^<]+)', h) == ["16대", "1.5km", "20,900원", "10:00~19:00", "7~12세"]
    assert 'data-numroll' in present.rich("16 pieces", "en", roll=True) and 'data-numroll' not in present.rich("Mondays", "en", roll=True)
    assert 'data-numroll' not in present.rich("16대") and "data-roll" not in h.replace("data-numroll", "")


def test_menu_price_is_never_cut_at_its_thousands_comma():
    b = present.brief_menu("한우떡갈비(200g)24,000원, 돼지떡갈비(200g)11,000원")
    assert b["main"] == "한우떡갈비(200g)24,000원" and b["more"]
    assert en_site.brief_en("menu", "Hanwoo tteokgalbi (200 g) 24,000 won, pork tteokgalbi 11,000 won")["main"].endswith("24,000 won")


def _guide_pages(S, built):
    """(page html, summary as shown, [(heading, [paragraph as shown])], faqs, lang) for every Korean and English guide."""
    out = []
    for g in S.guides:
        page = (built / "guides" / g["slug"] / "index.html").read_text("utf-8")
        body = [(squash_ws(b.get("heading")), [present.decaution(squash_ws(p)) for p in str(b.get("text") or "").split("\n")
                                               if p.strip()]) for b in g.get("body") or []]
        faqs = [present.decaution(squash_ws(f["a"])) for f in g.get("faq") or [] if f.get("q") and f.get("a")]
        out.append((page, present.decaution(g.get("summary")), body, faqs, "ko"))
    en = en_site.load(S, DATA)
    for x in en.guides.values():
        rec = x["rec"]
        page = (built / x["path"].strip("/") / "index.html").read_text("utf-8")
        body = [(squash_ws(b.get("heading")), [squash_ws(p) for p in str(b.get("text") or "").split("\n") if p.strip()])
                for b in rec.get("body") or []]
        out.append((page, squash_ws(rec.get("summary")), body, [squash_ws(f["a"]) for f in rec.get("faq") or []], "en"))
    return out


def test_english_figures_match_the_korean_units():
    """The English figures of the Korean units 곳 / 번 / 세 이하; tonnage and '1박 2일' stay plain in both languages."""
    t = ("The site lists 89 lodgings (56 inns and motels); take city bus 11, 12 or 19, then bus 99; children 6 and under "
         "are free; a 4,200-ton ship; 1-night, 2-day courses.")
    h = present.rich(t, "en")
    assert text_of(h) == t
    assert re.findall(r'class="gk"[^>]*>([^<]+)</b>', h) == ["89 lodgings", "56 inns", "bus 11, 12 or 19", "bus 99",
                                                              "6 and under"]
    # an age in months is the months figure, not 'ages 18' cut off from its unit
    h = present.rich("Activities are open to ages 18 months through adults; ages 7–12 pay 1,000 won.", "en")
    assert re.findall(r'class="gk"[^>]*>([^<]+)</b>', h) == ["18 months", "ages 7–12", "1,000 won"]
