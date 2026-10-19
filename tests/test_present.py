"""pipeline/present.py (redesign view models), textutil.display_value and the validator's row check, on the real
Gunsan data: 빈해원's TourAPI hours, 근대역사박물관's fee table, '가능요금 (무료)', 0507 phone numbers, the meal
stops of the 2박 3일 course and menu search."""
import json
import os
import re
import shutil
import struct
import subprocess
from html import unescape
from pathlib import Path
from urllib.parse import quote

import pytest

from pipeline import jsonld, present
from pipeline.build import State, build, entity_ctx
from pipeline.schema import fact_label, parking_seats_half, parking_seats_part
from pipeline.textutil import dash_times, display_value, value_shown, value_tokens
from pipeline.validate import PageScan, fact_shown, seat_only_parking_problems, validate
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

def test_stroller_rental_from_the_homepage_and_tourapi_none_show_two_blocks():
    """QA 2026-10-15 F02: a facility homepage says strollers can be borrowed, TourAPI says 없음 — both shown, the
    homepage's block first, with the flag and the call line; neither value is picked."""
    e = {"id": "x", "name": "박물관", "kind": "attraction",
         "facts": {"babycarriage": "대여 가능(예약 없이 박물관 안내소에서)", "infocenter": "063-454-7870"},
         "facts_source": {"provider": "군산시 문화관광", "checked_at": "2026-10-08"},
         "fact_sources": {"babycarriage": {"provider": "군산근대역사박물관 홈페이지", "checked_at": "2026-10-15",
                                           "url": "https://museum.example/qna/2166"}},
         "fact_alternatives": {"babycarriage": [{"value": "없음", "provider": "한국관광공사 TourAPI",
                                                 "checked_at": "2026-10-08", "contentid": "1684836"}]}}
    rows = present.fact_rows(e, present.FIT, present.Notes(), ("063-454-7870", "0634547870"))
    row = next(r for r in rows if r["key"] == "babycarriage")
    assert row["conflict"] and row["flag_text"] == "출처마다 다름 · 방문 전 전화 확인"
    assert [b["provider_full"] for b in row["blocks"]] == ["군산근대역사박물관 홈페이지", "한국관광공사 TourAPI"]
    assert [b["text"] for b in row["blocks"]] == ["대여 가능(예약 없이 박물관 안내소에서)", "없음"]
    assert row["tel"] == ("063-454-7870", "0634547870")
    assert not any(f["name"] == "유모차 대여" for f in
                   jsonld.entity_node(e, {"locality": "군산시"}, "https://x", "https://x/p/", [], []).get("amenityFeature", []))


# ------------------------------------------------------------------ the fee tile beside a combined ticket
TICKET_PLACES = ("근대역사박물관", "구-일본-제18은행-군산지점", "군산근대건축관", "진포해양공원", "채만식-문학관",
                 "31운동-100주년-기념관", "금강미래체험관")


def test_a_range_keeps_its_season_in_one_unit_and_the_last_entry_its_own_weight():
    """Review 2026-10-18, fourth round: on the Korean museum page at 390px the hours tile broke after a season's word
    ('… 11~2월 | 09:00–17:00(입장마감 16:30)'). The nwt filter keeps the word right before a range — its season or days
    — with the range and the bracket after it in one unit (.nwu: a line breaks before it, not inside it); a time is
    never a season. The last entry's bracket is .kfl; the words do not change."""
    from markupsafe import escape

    from pipeline.build import css_source, make_env
    nwt = make_env().filters["nwt"]
    nw, kfl = '<span class="nw">{}</span>', '<span class="kfl">({} <span class="nw">{}</span>)</span>'
    cases = {
        "3~10월 09:00–18:00(입장마감 17:30)":
            '<span class="nwu">3~10월 ' + nw.format("09:00–18:00") + kfl.format("입장마감", "17:30") + "</span>",
        "동절기(11월~2월) 09:00–17:00(입장 마감 16:30)":
            '<span class="nwu">동절기(11월~2월) ' + nw.format("09:00–17:00") + kfl.format("입장 마감", "16:30") + "</span>",
        "평일 09:00–18:00, 토,일 10:00–19:00":
            '<span class="nwu">평일 ' + nw.format("09:00–18:00") + '</span>, <span class="nwu">토,일 ' + nw.format("10:00–19:00") + "</span>",
        "11:00–21:00(입장마감 20:00)": '<span class="nwu">' + nw.format("11:00–21:00") + kfl.format("입장마감", "20:00") + "</span>",
        "09:00–12:00 13:00–18:00": nw.format("09:00–12:00") + " " + nw.format("13:00–18:00"),
        "09:00–21:00 입장마감 20:30": nw.format("09:00–21:00") + " 입장마감 20:30",
        "하절기(입장마감 17:30), 동절기(입장마감 16:30)":
            '<span class="nwu">하절기' + kfl.format("입장마감", "17:30") + '</span>, <span class="nwu">동절기' + kfl.format("입장마감", "16:30") + "</span>",
        "11:00–21:00 (브레이크 15:00–17:00)": nw.format("11:00–21:00") + ' <span class="kfl">(브레이크 ' + nw.format("15:00–17:00") + ")</span>",
        "성인 3,000원(1,500원)": "성인 " + nw.format("3,000원(1,500원)"),
        "A&B 09:00–18:00": '<span class="nwu">A&amp;B ' + nw.format("09:00–18:00") + "</span>",
        # UI review 2026-10-19: a list mark stays out of the unit after it, at the end of the line before — a Japanese or
        # Chinese line never starts with '、' (the last entries en_site.last_entry_tr joins with the locale's list mark)
        "夏季（入場締切17:30）、冬季（入場締切16:30）":
            '<span class="nwu">夏季<span class="kfl">（入場締切' + nw.format("17:30") + '）</span></span>、<span class="nwu">冬季'
            '<span class="kfl">（入場締切' + nw.format("16:30") + "）</span></span>",
        "平日 09:00–18:00、土日 10:00–17:00":
            '<span class="nwu">平日 ' + nw.format("09:00–18:00") + '</span>、<span class="nwu">土日 ' + nw.format("10:00–17:00") + "</span>",
        "夏季（17:30停止入场），冬季（16:30停止入场）":
            '<span class="nwu">夏季<span class="kfl">（' + nw.format("17:30") + '停止入场）</span></span>，<span class="nwu">冬季'
            '<span class="kfl">（' + nw.format("16:30") + "停止入场）</span></span>",
        "월,화(입장마감 17:00)": '<span class="nwu">월,화' + kfl.format("입장마감", "17:00") + "</span>",
    }
    for text, want in cases.items():
        assert str(nwt(text)) == want, text
        assert re.sub(r"<[^>]+>", "", want) == str(escape(text))   # the words do not change
        assert not re.search(r'class="(?:nwu|kfl|nw)">[、，,;；·・]', want), text   # no unit begins with a list mark
    css = " ".join(css_source().split())
    assert ".nwu, .kfl { display: inline-block; }" in css
    # the size down is the first screen's big tiles' only, never under 13px; elsewhere the bracket keeps the value's size
    assert ".kf-main .kfl { font-weight: 400; letter-spacing: -.01em; }" in css
    assert not re.search(r"(?:^|[}/]\s)\.kf-main \.kfl \{[^}]*font-size", css)
    assert ".kf-hero .kf-main .kfl { font-size: max(13px, .68em); }" in css


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


def test_official_hosts_in_the_text_are_links_and_the_text_stays():
    """QA 2026-10-15 SRC-05b: an official site the text writes as a bare host is a link (only OFFICIAL_WEB's hosts);
    the text of the result is the input, character for character."""
    t = "예매는 한국해운조합(island.theksa.co.kr), 문의는 1644-8774"
    h = str(present.tel_markup(t))
    assert h.count('class="xl"') == 1 and h.count('class="tel"') == 1
    assert re.sub(r"<[^>]+>", "", h) == t
    assert 'href="https://island.theksa.co.kr/"' in h and 'data-track="official_click"' in h
    # the other versions: the English booking page of the same site
    assert 'href="https://island.theksa.co.kr/page/booking?lang=en"' in str(present.tel_markup(t, intl=True))
    for plain in ("gsmg-marathon.com은 열리지 않았습니다", "홈페이지 주소는 funvillage.kr입니다", "xwww.korail.com",
                  "https://www.korail.com/", "abc.mndcamp.com", "www.kobus.co.kr"):
        assert 'class="xl"' not in str(present.tel_markup(plain)), plain
    # an FAQ answer (skip): no link starts in its head, which FAQPage repeats and the validator compares as one run
    a = "It is 063-454-7870. Booking is at island.theksa.co.kr or 063-454-7871."
    h = str(present.tel_markup(a, intl=True, skip=present.PLAIN_HEAD))
    assert h.startswith("It is 063-454-7870. ") and h.count('class="tel"') == 1 and 'href="tel:+82634547871"' in h
    assert h.count('class="xl"') == 1 and re.sub(r"<[^>]+>", "", h) == a


# ------------------------------------------------------------------ courses

def _course(S, cid):
    return next(v for v in S.course_vms.values() if v["c"]["id"] == cid)


def _move_block(built, cv) -> str:
    html = (built / "courses" / cv["slug"] / "index.html").read_text("utf-8")
    m = re.search(r'<section class="wrap chapter chapter-mid co-move"[^>]*data-block="move">(.*?)</section>', html, re.S)
    assert m, cv["slug"]
    return m.group(1)


# ------------------------------------------------------------------ search


def test_other_names_keep_only_what_the_search_would_not_find_anyway():
    """present.other_names (QA 2026-10-15 U10): the names in the other versions, ' · '-joined in their order, each
    once — without one search.js finds anyway (inside n, a or a longer name kept, compared as search.js does)."""
    row = {"n": "선유도", "a": "선유도 해수욕장"}
    present.other_names(row, "Seonyudo Island", "", None, "seonyudo island", "선유 도", "2026 Seonyudo Island Festival")
    assert row["o"] == "2026 Seonyudo Island Festival"
    row = {"n": "군산시간여행축제", "a": ""}
    present.other_names(row, "2026 군산시간여행축제", "Gunsan Time Travel Festival")
    assert row["o"] == "2026 군산시간여행축제 · Gunsan Time Travel Festival"
    row = {"n": "A", "a": ""}
    present.other_names(row, "", None, "A")
    assert "o" not in row
    present.other_names(row, "선유도", "Seonyudo Island", key="v")
    assert row["v"] == "선유도 · Seonyudo Island"


def test_the_index_has_no_other_language_names_without_the_english_version():
    """A build without an English version (the sample data): no row carries o or v, and nothing breaks."""
    S = State(ROOT / "data" / "sample", "sample")
    assert getattr(S, "en", None) is None
    rows = present.search_index(S)
    assert rows and not any("o" in r or "v" in r for r in rows)


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


MUSEUM_EV = "fest-군산근대역사박물관-주말상설행사-2026"


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


# ------------------------------------------------------------------ 군산시 '주차 및 좌석수' with one half only
def test_parking_seats_part_reads_each_half():
    for raw in ("40석", "좌석 100석", "1,200석"):
        assert parking_seats_part(raw) == "seats", raw
    for raw in ("20대", "공영주차장", "불가"):
        assert parking_seats_part(raw) == "parking", raw
    for raw in ("20대/80석", "좌석 40석/ 주차 15대", "30 ~ 40대/100석", "불가능 / 70석", "전화문의", ""):
        assert parking_seats_part(raw) == "", raw


def _seat_only(S) -> list[dict]:
    out = [e for e in S.entities if parking_seats_half(e) == "seats"]
    assert "모트" in {e["slug"] for e in out}
    return out


def _text(fragment: str) -> str:
    return re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " ", fragment)).strip()


def squash(text: str) -> str:
    return re.sub(r"\s+", " ", text or "").strip()


def test_an_unspaced_address_keeps_only_its_house_number_together():
    """present.nowrap_address: a word holding a hyphen ('244-7(장미동)') stays one no-wrap piece; a word longer than
    ADDRESS_WORD_MAX — an address the source gives without spaces — stays one plain text run (no no-wrap piece, so
    the body's overflow-wrap can break it on a phone, and the validator reads it whole as JSON-LD has it)."""
    assert str(present.nowrap_address("전북특별자치도 군산시 해망로 244-7(장미동)")) == \
        '전북특별자치도 군산시 해망로 <span class="nw">244-7(장미동)</span>'
    long = "전북특별자치도군산시임피면구신기길104-3수에어항공"
    assert str(present.nowrap_address(long)) == long


SHARE_BTN = re.compile(r'<button type="button" class="lnav-share" data-share data-share-id="([^"]*)" '
                       r'data-copied="([^"]*)" data-failed="([^"]*)" data-js-only>.*?<span class="lnav-share-t">([^<]*)</span>'
                       r'</button>', re.S)


def _serve(built):
    """A page.route handler serving the built site at http://site.test/ (nothing leaves the machine)."""
    import mimetypes
    from urllib.parse import unquote, urlsplit

    def serve(route):
        url = route.request.url
        if not url.startswith("http://site.test/"):
            return route.abort()
        path = unquote(urlsplit(url).path)
        f = built / path.strip("/")
        f = f / "index.html" if path.endswith("/") else f
        if not f.is_file():
            return route.fulfill(status=404, body="")
        route.fulfill(status=200, body=f.read_bytes(),
                      content_type=mimetypes.guess_type(f.name)[0] or "application/octet-stream")
    return serve


# the browser's share sheet, clipboard and GA4 sender stood in for: what the page hands them is recorded
SHARE_STUBS = """
window.__events = []; window.__copied = []; window.__shared = [];
window.gunsanTrack = function (name, params) { window.__events.push([name, params]); };
Object.defineProperty(navigator, 'clipboard', {configurable: true, value: {writeText: function (t) {
  window.__copied.push(t); return Promise.resolve(); }}});
var mode = (location.search.match(/share=(\\w+)/) || [])[1];
Object.defineProperty(navigator, 'share', {configurable: true, value: mode === 'none' ? undefined : function (data) {
  window.__shared.push(data);
  if (mode === 'abort') return Promise.reject(new DOMException('closed', 'AbortError'));
  if (mode === 'deny') return Promise.reject(new DOMException('no', 'NotAllowedError'));
  return Promise.resolve(); }});
"""


def test_the_site_name_and_the_logos_colour_its_end():
    """Operator 2026-10-17 (ChatGPT colour study A, 'gak' too): the bar's and the footer's name keeps its text and puts
    its end in .wm-em (군산<각>, Gunsan<gak>); the light logos draw 각 and gak in the site blue #2F6FC9, the reverse in
    the lantern yellow #FFD54A, the mono one in one black path per line as before. (The logo files' colours are the
    city's own brand files — tests/excluded_gunsan_tests.txt; the name's end is the engine's.)"""
    assert str(present.wordmark("군산각")) == '군산<span class="wm-em">각</span>'
    assert str(present.wordmark("Gunsangak")) == 'Gunsan<span class="wm-em">gak</span>'
    assert str(present.wordmark("인천각")) == '인천<span class="wm-em">각</span>'
    assert str(present.wordmark("군산 여행")) == "군산 여행" and str(present.wordmark("<b>")) == "&lt;b&gt;"
    css = (ROOT / "templates" / "assets" / "css" / "20-chrome.css").read_text("utf-8")
    assert ".wm-em { color: var(--sea); }" in css
