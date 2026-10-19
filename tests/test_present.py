"""pipeline/present.py (redesign view models), textutil.display_value and the validator's row check, on the real
Gunsan data: 빈해원's TourAPI hours, 근대역사박물관's fee table, '가능요금 (무료)', 0507 phone numbers, the meal
stops of the 2박 3일 course and menu search."""
import json
import re
import shutil
import struct
from pathlib import Path

import pytest

from pipeline import jsonld, present
from pipeline.build import State, build, entity_ctx
from pipeline.textutil import dash_times, display_value, value_shown, value_tokens
from pipeline.validate import PageScan, fact_shown, validate
from tools.image_sizes import image_size

ROOT = Path(__file__).resolve().parent.parent
DATA = ROOT / "data" / "gunsan"
SAMPLE = ROOT / "data" / "sample"


@pytest.fixture(scope="module")
def S():
    return State(DATA, "preview")


@pytest.fixture(scope="module")
def built(tmp_path_factory):
    out = tmp_path_factory.mktemp("present") / "preview"
    build(DATA, out, "preview")
    return out


def place(S, slug):
    return S.ent_by_slug[slug]


def all_values(S):
    """(entity, key, value) for every stored fact and every other source's value."""
    for e in S.entities:
        for k, v in (e.get("facts") or {}).items():
            yield e, k, v
        for k, alts in (e.get("fact_alternatives") or {}).items():
            for a in alts or []:
                if a.get("value"):
                    yield e, k, a["value"]


# ------------------------------------------------------------------ display_value
def test_display_value_normalises_presentation_only():
    assert display_value("parking", "가능요금 (무료)") == "가능, 요금 무료"
    assert display_value("parking", "가능\n요금 (무료)") == "가능, 요금 무료"
    assert display_value("parking", "주차장이 구비") == "가능"
    assert display_value("parking", "주차가능") == "가능"
    assert display_value("parking", "불가능") == "불가"
    assert display_value("usetime", "10:00 ~ 21:00,  휴무일 : 매주 월요일") == "10:00–21:00, 휴무일 : 매주 월요일"
    assert display_value("usetime", "[하절기]09:00~18:00[동절기] 09:00~17:00 ※ 매표마감 17:00") == \
        "[하절기]\n09:00–18:00\n[동절기]\n09:00–17:00\n※ 매표마감 17:00"
    assert display_value("homepage", "http://www.gunsandal.kr/") == "gunsandal.kr"
    assert display_value("homepage", "https://www.instagram.com/some.place/") == "instagram.com/some.place"
    assert display_value("course_name", "A코스 | 근대~고군산") == "A코스 근대~고군산"
    assert display_value("address", "전라북도 군산시 해망로 240") == "전북특별자치도 군산시 해망로 240"


# ------------------------------------------------------------------ 빈해원: TourAPI hours vs 군산시
# ------------------------------------------------------------------ 근대역사박물관: fees and seasons
# ------------------------------------------------------------------ '가능요금 (무료)'
# ------------------------------------------------------------------ phones
def test_contested_phone_is_never_the_call_number(tmp_path):
    """CLAUDE.md 3절 2항 for phones, on a data/sample place with a made-up second number: when sources give the phone
    differently, neither is the page's call number (no settled phone for the status line, the list cell or the flag
    line's call link); the facts row shows both, equally."""
    data = tmp_path / "data"
    shutil.copytree(SAMPLE, data)
    places = json.loads((data / "places.json").read_text("utf-8"))
    e = next(x for x in places if x["slug"] == "gyeongam-railroad-village")
    e["facts"]["infocenter"] = "000-0000-0001"
    assert present.settled_phone(e) == ("000-0000-0001", "00000000001")
    e["fact_alternatives"] = {**(e.get("fact_alternatives") or {}),
                              "infocenter": [{"value": "000-0000-0002", "provider": "[테스트] 다른 출처",
                                              "checked_at": "2026-10-19"}]}
    assert present.settled_phone(e) == ("", "")
    assert not [x for x in present.status_items(e, full=True) if x["key"] == "tel"]
    assert present.cell({**e, "_path": "/places/x/"}, "tel")["text"] == "출처마다 다름"
    (data / "places.json").write_text(json.dumps(places, ensure_ascii=False), "utf-8")
    out = tmp_path / "out"
    build(data, out, "sample")
    html = (out / "places" / e["slug"] / "index.html").read_text("utf-8")
    one, two = html.count('href="tel:00000000001"'), html.count('href="tel:00000000002"')
    assert one == two >= 1                                  # both numbers, the same way; neither picked
    assert "방문 전 전화 확인" in html


# ------------------------------------------------------------------ courses
# ------------------------------------------------------------------ search
# ------------------------------------------------------------------ status line, stays, regions, home
# ------------------------------------------------------------------ home opening (owner 2026-10-13, specs/home_redesign.md)
NEWS_ORDER = ("festival", "event", "abroad", "guide", "video")


def _check_news(S, day: str) -> list[dict]:
    """The ranking rule (the comment above present.NEWS_MAX) checked against the data itself on one build date."""
    S.today = day
    news = present.home_news(S)
    kinds = [c["kind"] for c in news]
    assert present.NEWS_MIN <= len(news) <= present.NEWS_MAX, (day, kinds)
    assert len({c["key"] for c in news}) == len(news) and all(c["href"] and c["title"] for c in news)
    assert kinds == sorted(kinds, key=NEWS_ORDER.index), (day, kinds)    # focus → events → abroad → guides → video
    # events: the running / coming editions within 30 days, in ranked_events order; nothing past
    rows = [r for r in present.ranked_events(S) if r["days"] <= present.NEWS_EVENT_DAYS]
    want = ["ev:" + str(r["ev"].get("id")) for r in rows]
    got = [c["key"] for c in news if c["kind"] in ("festival", "event")]
    assert got == [k for k in want if k in got] and all(r["last"] >= day for r in rows)
    if "festival" not in kinds:
        assert got == want[:3]
    # foreign press: the newest articles dated on or before the build date (date, then id)
    dated = sorted((a for a in S.abroad if a.get("kind") == "article" and a.get("date")
                    and present.iso_floor(a["date"]) <= day), key=lambda a: a["id"])
    dated.sort(key=lambda a: present.iso_floor(a["date"]), reverse=True)
    ab = [c["key"] for c in news if c["kind"] == "abroad"]
    assert ab and ab == ["ab:" + a["id"] for a in dated[:len(ab)]]
    # guides: approved_at, then the guide number, both newest first
    guides = [c["href"] for c in news if c["kind"] == "guide"]
    top = sorted(S.guides, key=present._guide_rank, reverse=True)
    assert guides and guides == [g["_path"] for g in top[:len(guides)]]
    return news


# ------------------------------------------------------------------ events, photos
def test_image_header_parser():
    png = b"\x89PNG\r\n\x1a\n" + b"\x00\x00\x00\rIHDR" + struct.pack(">II", 940, 627) + b"\x08\x02\x00\x00\x00"
    assert image_size(png) == (940, 627)
    app0 = b"\xff\xe0" + struct.pack(">H", 16) + b"JFIF\x00" + b"\x00" * 9
    sof = b"\xff\xc0" + struct.pack(">HBHH", 17, 8, 626, 940) + b"\x03" + b"\x00" * 9
    assert image_size(b"\xff\xd8" + app0 + sof) == (940, 626)
    assert image_size(b"\xff\xd8" + app0) is None


# ------------------------------------------------------------------ validator row check
FACTS_PAGE = ('<section data-block="facts"><dl>'
              '<div><dt>쉬는 날</dt><dd data-key="restdate">{a}</dd></div>'
              '<div><dt>주차</dt><dd data-key="parking">{b}</dd></div></dl></section>')
CLOSED = "매주 월요일, 1월 1일, 시장이 휴관일로 정한 날"


def scan(a, b="가능"):
    p = PageScan()
    p.feed(FACTS_PAGE.format(a=a, b=b))
    return p


def old_probe(p, raw):
    return raw[:20] in " ".join(p.blocks["facts"].split())


def test_validator_row_check_is_stricter_than_the_old_prefix_probe():
    assert fact_shown(scan(CLOSED), "restdate", CLOSED)
    # line breaks, a table layout or a closed-day mark do not matter, the words and their order do
    assert fact_shown(scan("매주 월요일,<br>1월 1일, <b>시장이 휴관일로 정한 날</b>"), "restdate", CLOSED)
    cases = {"tail cut after 20 characters": scan(CLOSED[:21]),
             "shown in another row": scan("", CLOSED),
             "a word slipped in": scan(CLOSED.replace("휴관일로 정한", "휴관일로 임시로 정한")),
             "words reordered": scan("1월 1일, 매주 월요일, 시장이 휴관일로 정한 날")}
    for why, p in cases.items():
        assert not fact_shown(p, "restdate", CLOSED), why
    # the old probe (first 20 characters anywhere in the block) let the first three through
    assert all(old_probe(cases[k], CLOSED) for k in ("tail cut after 20 characters", "shown in another row",
                                                     "a word slipped in"))
    # parking compares against the displayed form, never the raw '가능요금 (무료)'
    assert fact_shown(scan("", "가능, 요금 무료"), "parking", "가능요금 (무료)")
    assert not fact_shown(scan("", "가능"), "parking", "가능요금 (무료)")


# ------------------------------------------------------------------ review fixes (r3-wpa review)
def row_page(key, inner):
    p = PageScan()
    p.feed(f'<section data-block="facts"><dl><div><dt>x</dt><dd data-key="{key}">{inner}</dd></div></dl></section>')
    return p


def test_row_check_keeps_symbols_and_the_whole_text():
    """Counter-examples to the first token check, which ignored every symbol: each one passed it while the old
    20-character probe failed. A symbol is a token now, and a value that prints as text must be there verbatim."""
    cases = [("usetime", "~21:00", "21:00"), ("usetime", "10:00~", "10:00"), ("discount", "단체 50%", "단체 50"),
             ("usefee", "₩3,000", "3,000"), ("expagerange", "만 3세+", "만 3세"),
             ("usefee", "성인 3,000원(청소년 2,000원)", "성인 3,000원 청소년 2,000원"),
             ("expguide", "A/B 체험", "A B 체험")]
    for key, value, page in cases:
        p = row_page(key, page)
        assert not fact_shown(p, key, value), (key, value, page)
        assert not old_probe(p, value)                   # the old probe failed these too: nothing is looser
        assert fact_shown(row_page(key, value), key, value)
    # a value inside a longer word is not shown (the old substring probe let '가능' pass in '불가능')
    assert not fact_shown(row_page("parking", "불가능"), "parking", "가능") and old_probe(row_page("parking", "불가능"), "가능")
    assert not fact_shown(row_page("parking", "불<b>가능</b>"), "parking", "가능")
    # a footnote mark right after the value does not hide it
    assert fact_shown(row_page("usetime", "09:00–18:00<sup>1</sup> — 한국관광공사"), "usetime", "09:00~18:00")
    # a value that parses into a price table may lose the layout punctuation its cells replace — nothing else
    fee = "[개별권]\n- 성인 2,000원\n- 어린이 500원"
    assert present.value_view("usefee", fee)["fees"]
    table = '<table data-form="fees"><tr><th>개별권</th></tr><tr><td>성인</td><td>2,000원</td></tr><tr><td>어린이</td><td>500원</td></tr></table>'
    assert fact_shown(row_page("usefee", table), "usefee", fee)
    assert not fact_shown(row_page("usefee", table.replace("<td>500원</td>", "")), "usefee", fee)
    # the same cells without the table mark are plain text and must match verbatim
    assert not fact_shown(row_page("usefee", table.replace(' data-form="fees"', "")), "usefee", fee)
    # a value that does not parse gets no table allowance, mark or not
    assert not fact_shown(row_page("usefee", '<table data-form="fees"><tr><td>성인 3,000원 청소년 2,000원</td></tr></table>'),
                          "usefee", "성인 3,000원(청소년 2,000원)")


def test_row_check_requires_the_full_homepage_link():
    url = "https://booking.naver.com/booking/3/bizes/60723"
    shown = display_value("homepage", url)
    assert shown == "booking.naver.com/booking"
    assert fact_shown(row_page("homepage", f'<a href="{url}">{shown}</a>'), "homepage", url)
    assert not fact_shown(row_page("homepage", shown), "homepage", url)                       # text only
    assert not fact_shown(row_page("homepage", f'<a href="https://booking.naver.com/">{shown}</a>'), "homepage", url)


def test_open_every_day_inside_the_hours_value_is_read():
    """'11:00~20:00(연중무휴)' and '10:00~21:30 / 연중무휴' are open every day, not 'no data' in the week grid."""
    for raw in ("11:00~20:00(연중무휴)", "10:00~21:30 / 연중무휴", "10:00~20:00 연중무휴"):
        text, _ = present.closed_text({"facts": {"usetime_restdate": raw}})
        assert text == "연중무휴" and present.week_closure(text)["open"]


def test_guide_figure_is_never_part_of_a_compound_amount():
    g = {"body": [{"heading": "서울 센트럴시티→군산 고속버스는 2시간30분, 금호고속 운행분은 하루 23회"}], "title": "t"}
    a = present.guide_answer(g)
    assert (a["fig"], a["unit"]) == ("23", "회")


def test_thumb_uses_the_smallest_kogl1_derivative_when_the_provider_has_no_small_copy():
    # a TourAPI photo-gallery picture (KOGL-1, 1280 px) has no provider small copy: a list row gets our 480w WebP
    base = {"url": "https://tong.visitkorea.or.kr/cms2/website/28/3587128.jpg", "w": 1280, "h": 850, "alt": "고군산군도",
            "type": 1, "webp": "/assets/media/3587128-940.webp 940w, /assets/media/3587128-480.webp 480w", "th": None}
    assert present.thumb(base) == {"url": "/assets/media/3587128-480.webp", "w": 480, "h": 319, "alt": "고군산군도",
                                   "type": 1}
    # the provider's own small copy still wins; KOGL-3 (never re-encoded) and photos without derivatives keep the original
    own = {**base, "th": {"url": "https://tong.visitkorea.or.kr/x_image3_1.jpg", "w": 160, "h": 106}}
    assert present.thumb(own)["url"] == "https://tong.visitkorea.or.kr/x_image3_1.jpg"
    assert present.thumb({**base, "type": 3})["url"] == base["url"]
    assert present.thumb({**base, "webp": ""})["url"] == base["url"]
    assert present.thumb(None) is None
