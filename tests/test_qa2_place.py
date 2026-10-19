"""The scenario QA of 2026-10-19, second round (docs/qa/2026-10-19_scenario_qa.md 7-4), place items: QA-67 a course
stop's hours of that weekday, QA-68 the fee tile keeps its row's words, QA-69 no TourAPI dash run in a description,
QA-73 closed red only for a closure, QA-75 no break inside a time, QA-77 one '확인 필요' a list card. Made-up values in
the TourAPI shapes the testers met, and a build of the Incheon configuration with the tiny fixture plus a few fake
records (tests/fixtures/incheon_tiny). Nothing here is real data."""
import datetime as dt
import json
import re
import shutil
from pathlib import Path

import pytest

from pipeline import present
from pipeline.build import answer_description, build
from pipeline.textutil import restore_lines, value_line

ROOT = Path(__file__).resolve().parent.parent
INCHEON = ROOT / "data" / "incheon"
TINY = Path(__file__).resolve().parent / "fixtures" / "incheon_tiny"
RECORDS = ("places.json", "events.json", "courses.json", "guides.json", "themes.json", "videos.json")
SRC = {"provider": "한국관광공사 TourAPI", "checked_at": "2026-10-19", "contentid": ""}

# the shapes of the QA's examples, with made-up times and prices
BY_WEEKDAY = ("[평일]\n- 11:30~23:00\n- 준비시간 15:00~17:00\n- 마지막 주문 22:30\n[금요일]\n- 12:00~24:00\n"
              "- 마지막 주문 23:30\n[토요일]\n- 12:00~24:00\n- 마지막 주문 23:30\n[일요일]\n- 11:30~23:00")
BY_LINE = "- 평일 10:00~17:00- 토요일 14:30~18:00- 일요일 11:30~18:00※ 평일은 단체만 예약제로 운영"


def _place(pid, slug, name, kind, facts, geo=None, **extra):
    return {"id": pid, "slug": slug, "name": name, "kind": kind, "category": present.KIND_LABELS[kind], "themes": [],
            "tier": "basic", "status": "draft", "summary": "", "facts": facts, "facts_source": dict(SRC),
            "fact_sources": {k: dict(SRC) for k in facts}, "official": {}, "original": {},
            "map_ids": {"naver_place_id": "", "google_place_id": ""}, "images": [], "tourapi": {},
            **({"geo": {"lat": geo[0], "lng": geo[1], "source": "TourAPI"}} if geo else {}), **extra}


# ------------------------------------------------------------------ values (no build)
def test_the_fee_tile_keeps_every_word_of_its_first_row():
    """QA-68: '이상 6,000원' for '중학생 이상 6,000원', '이하 55,000원' for '5㎏ 이하 55,000원' — the short fee writer took
    the last word before the price; a later row ('… 군인 20,000원') when the first row's label had a bracket."""
    b = present.brief_fee("중학생 이상 6,000원 12개월 이상~초등학생 7,000원 12개월 미만 무료")
    assert (b["main"], b["more"]) == ("중학생 이상 6,000원", True)
    b = present.brief_fee("[디럭스룸]\n- 5㎏ 이하 55,000원\n- 5㎏ 초과 66,000원\n[스위트룸]\n- 1견 기준 77,000원\n※ 전화 문의 요망")
    assert (b["main"], b["sub"]) == ("5㎏ 이하 55,000원", "디럭스룸")
    b = present.brief_fee("- 대인(14세 이상) 28,000원\n- 소인(13세 이하) 20,000원\n- 만 65세 이상/장애인/군인 20,000원\n※ 무료\n- 36개월 미만")
    assert b["main"] == "대인(14세 이상) 28,000원"
    b = present.brief_fee("[개인]- 2인승 25,000원- 3인승 29,000원[단체]- 2인승 25,000원- 3인승 26,100원- 4인승 28,000원")
    assert (b["main"], b["sub"]) == ("2인승 25,000원", "")   # the visitor's own group says nothing next to it (QA-19)
    b = present.brief_fee("- 그린피 시즌별 상이함\n- 캐디피 160,000원~\n- 카트피 100,000원~\n※ 이용요금은 변동될 수 있음")
    assert b["main"] == "캐디피 160,000원~"   # an open-ended price as the source writes it
    assert present.brief_fee("성인 3,000원 / 어린이 1,000원")["main"] == "성인 3,000원 / 어린이 1,000원"   # short: whole


def test_a_description_says_a_dash_list_as_one_line():
    """QA-69: 98 place pages' meta description read '이용시간: - 11:00–19:00 - 마지막 주문 …'."""
    assert value_line("usetime", "- 11:00~19:00- 마지막 주문 18:45") == "11:00–19:00 · 마지막 주문 18:45"
    assert value_line("usetime", "- 입실 15:00\n- 퇴실 11:00") == "입실 15:00 · 퇴실 11:00"
    assert value_line("usetime", "[평일]\n- 11:30~23:00\n[주말]\n- 12:00~22:00") == "평일 11:30–23:00 · 주말 12:00–22:00"
    assert value_line("usetime", "09:00~18:00") == "09:00–18:00"
    rows = [{"key": "usetime", "label": "이용시간", "value": "- 11:00~19:00- 마지막 주문 18:45", "alternatives": []},
            {"key": "restdate", "label": "쉬는 날", "value": "연중무휴", "alternatives": []}]
    d = answer_description("가상 카페는 인천광역시 가상구에 있는 카페입니다.", "", rows)
    assert "이용시간: 11:00–19:00 · 마지막 주문 18:45." in d and " - " not in d and ": -" not in d


def test_closed_red_is_for_a_closure_only():
    """QA-73: '점포 별로 상이함' (a market's closed-day field) showed in closed red on the nearby rows, as '연중무휴' did
    before QA-31; the tiles, list cells and facts card read the same rule."""
    for t in ("점포 별로 상이함", "※ 점포별 상이하므로 홈페이지 참고", "전화 문의 후 방문 요망", "홈페이지 참조", "10:00~18:00",
              "연중무휴", "연중무휴(명절 당일 제외)", "휴무일 : 없음"):
        assert not present.is_closure(t), t
        assert not present.brief_closed(t)["closed"], t
        assert not present.value_view("restdate", t)["closed"], t
    for t in ("매주 월요일", "주말", "월 2회", "설·추석 당일", "1월 1일", "비정기적 휴무 (전화 문의)", "매주 월요일 (홈페이지 참조)",
              "- 전망대 (연중무휴)- 홍보관 (1월 1일 / 설날·추석 당일)"):
        assert present.is_closure(t), t
    assert present.brief_closed("매주 월요일")["closed"] and present.value_view("restdate", "매주 월요일")["closed"]
    items = present.status_items({"kind": "shopping", "facts": {"restdate": "점포 별로 상이함"}})
    assert [(x["text"], x["closed"]) for x in items] == [("점포 별로 상이함", False)]


def test_a_group_after_a_space_starts_its_line():
    """QA-67 (the hours read by group): '- 입장 마감 17:00 [동절기] - 10:00~17:00' kept the winter group at the end of
    the summer line ('하절기 10:00–18:00 · 입장 마감 17:00 [동절기]' on the course card)."""
    assert restore_lines("[하절기] - 10:00~18:00 - 입장 마감 17:00 [동절기] - 10:00~17:00 - 입장 마감 16:00") == [
        "[하절기]", "- 10:00~18:00", "- 입장 마감 17:00", "[동절기]", "- 10:00~17:00", "- 입장 마감 16:00"]
    b, _ = present.brief_hours("[하절기] - 10:00~18:00 - 입장 마감 17:00 [동절기] - 10:00~17:00 - 입장 마감 16:00")
    assert "[" not in f"{b['main']} {b['sub']}"


def test_the_hours_of_one_weekday():
    """QA-67: a Saturday's stop showed '평일 11:30–23:00 · 금요일 12:00–24:00' (the first two lines) as that day's hours;
    a Sunday's '평일 · 토요일'. day_hours gives each weekday its own group, Sunday first."""
    w = present.day_hours(BY_WEEKDAY)
    assert w[6] == "토요일 12:00–24:00 · 마지막 주문 23:30"
    assert w[5] == "금요일 12:00–24:00 · 마지막 주문 23:30"            # the narrower group over 평일
    assert w[1] == "평일 11:30–23:00 · 준비시간 15:00–17:00 · 마지막 주문 22:30"
    assert w[0] == "일요일 11:30–23:00"
    w = present.day_hours(BY_LINE)
    assert (w[0], w[3], w[6]) == ("일요일 11:30–18:00", "평일 10:00–17:00", "토요일 14:30–18:00")
    w = present.day_hours("- 목요일~일요일 10:00~19:00\n- 수요일 13:00~19:00\n- 마지막 주문 18:30")
    assert (w[1], w[2]) == ("", "") and w[0] == "목요일~일요일 10:00–19:00 · 마지막 주문 18:30"   # a day no group names
    w = present.day_hours("[일요일~금요일]\n- 10:00~21:00\n[토요일]\n- 10:00~22:00")
    assert w[0] == w[5] == "일요일~금요일 10:00–21:00" and w[6] == "토요일 10:00–22:00"
    assert present.day_hours("- 평일 / 일요일 11:30~23:00\n- 토요일 11:30~24:00")[1] == "평일 / 일요일 11:30–23:00"
    assert present.day_hours("[금요일/주말/공휴일]\n- 10:00~21:00\n[평일]\n- 10:00~20:30")[6] == "금요일/주말/공휴일 10:00–21:00"
    for v in ("09:00~18:00", "[일반자료실]\n- 평일 09:00~20:00\n- 주말 09:00~17:00", "[하절기]\n- 평일 10:00~18:00",
              "09:00~18:00\n[토요일]\n09:00~20:00", "- 11:00~21:00\n- 준비시간(평일) 15:00~17:00"):
        assert present.day_hours(v) is None, v


def test_an_event_time_never_breaks_inside_a_time_in_words():
    """QA-75: each time one no-wrap piece; a break before the bracket after a range, none inside the bracket."""
    assert str(present.time_units("10:00–18:00(17:00입장마감)")) == \
        '<span class="nw">10:00–18:00</span><wbr>(<span class="nw">17:00</span>입장마감)'
    assert str(present.time_units("09:00–17:00 (입장 마감 16:30)")) == \
        '<span class="nw">09:00–17:00</span> (입장 마감 <span class="nw">16:30</span>)'
    assert str(present.time_units("<b>")) == "&lt;b&gt;"


# ------------------------------------------------------------------ a build
@pytest.fixture(scope="module")
def site(tmp_path_factory):
    tmp = tmp_path_factory.mktemp("qa2")
    data = tmp / "data"
    data.mkdir()
    for f in INCHEON.glob("*.json"):
        if f.name not in RECORDS:
            shutil.copy(f, data / f.name)
    for f in TINY.glob("*.json"):
        shutil.copy(f, data / f.name)
    places = json.loads((data / "places.json").read_text("utf-8"))
    places += [
        _place("test-0201", "test-diner-j", "[테스트] 가상 식당 J", "food",
               {"address": "인천광역시 미추홀구 테스트로 21 (숭의동)", "usetime": BY_WEEKDAY, "restdate": "연중무휴",
                "menu": "가상 볶음"}, (37.46, 126.65),
               nearby=[{"name": "[테스트] 가상 시장 K", "kind": "shopping", "type_label": "쇼핑", "distance_m": 140,
                        "internal_slug": "test-market-k"}]),
        _place("test-0202", "test-market-k", "[테스트] 가상 시장 K", "shopping",
               {"address": "인천광역시 미추홀구 테스트로 22 (숭의동)", "usetime": "09:00~21:00", "restdate": "점포 별로 상이함",
                "parking": "가능", "infocenter": "032-000-0001"}, (37.461, 126.651)),
        _place("test-0203", "test-cafe-l", "[테스트] 가상 카페 L", "cafe",
               {"address": "인천광역시 미추홀구 테스트로 23", "usetime": "- 11:00~19:00- 마지막 주문 18:45"},
               (37.462, 126.652)),
        _place("test-0204", "test-kids-m", "[테스트] 가상 어린이관 M", "attraction",
               {"address": "인천광역시 미추홀구 테스트로 24 (숭의동)", "usetime": "10:00~18:00", "restdate": "매주 월요일",
                "usefee": "중학생 이상 6,000원 12개월 이상~초등학생 7,000원 12개월 미만 무료"}, (37.463, 126.653)),
    ]
    (data / "places.json").write_text(json.dumps(places, ensure_ascii=False), "utf-8")
    today = dt.date.today()
    events = [{"id": "event-test-2", "contentid": "", "status": "draft", "name": "[테스트] 가상 국화축제",
               "start_date": (today - dt.timedelta(days=1)).isoformat(),
               "end_date": (today + dt.timedelta(days=9)).isoformat(),
               "place_name": "가상 야생화단지", "address": "인천광역시 서구 테스트로 5", "summary": "",
               "source_name": "한국관광공사 TourAPI", "checked_at": "2026-10-19",
               "playtime": "10:00~18:00(17:00입장마감)", "fee": "무료", "tel": "", "homepage": "", "images": []}]
    (data / "events.json").write_text(json.dumps(events, ensure_ascii=False), "utf-8")
    out = tmp / "out"
    build(data, out, "preview")
    return {"data": data, "out": out}


def _page(site, slug):
    return (site["out"] / "places" / slug / "index.html").read_text("utf-8")


def _card(html, name):
    return re.search(rf'<li class="rec"[^>]*>(?:(?!</li>).)*{re.escape(name)}(?:(?!</li>).)*</li>', html, re.S).group(0)


def test_the_course_planner_gets_each_weekdays_hours(site):
    """QA-67: plan/places.json hd (the card) and chat docs h[].w (checkPlan) — the same groups, Sunday first."""
    rows = json.loads((site["out"] / "plan" / "places.json").read_text("utf-8"))
    diner = next(v for v in rows.values() if v["n"] == "[테스트] 가상 식당 J")
    assert diner["hd"][6] == "토요일 12:00–24:00 · 마지막 주문 23:30" and diner["h"].startswith("평일")
    assert "hd" not in next(v for v in rows.values() if v["n"] == "[테스트] 가상 어린이관 M")   # one range: h alone
    docs = json.loads((site["out"] / "chat" / "docs.json").read_text("utf-8"))["docs"]
    h = next(d for d in docs.values() if d.get("t") == "[테스트] 가상 식당 J")["f"]["h"]
    assert h[0]["w"][6] == "토요일 12:00–24:00 · 마지막 주문 23:30" and "[토요일]" in h[0]["t"]


def test_the_fee_tile_on_the_page(site):
    """QA-68 on the first screen: the tile reads '중학생 이상 6,000원 외 ↓'."""
    tile = re.search(r'<div class="kf-i kf-fee[^"]*">(.*?)</div>', _page(site, "test-kids-m"), re.S).group(1)
    assert "중학생 이상 6,000원" in re.sub(r"<[^>]+>", "", tile)


def test_no_meta_description_carries_a_dash_run(site):
    """QA-69 over the whole build: no description, og or twitter text with a TourAPI list mark."""
    d = re.search(r'<meta name="description" content="([^"]*)"', _page(site, "test-cafe-l")).group(1)
    assert "11:00–19:00 · 마지막 주문 18:45" in d
    for f in site["out"].rglob("index.html"):
        for m in re.finditer(r'<meta (?:name|property)="(?:description|og:description|twitter:description)" '
                             r'content="([^"]*)"', f.read_text("utf-8")):
            assert not re.search(r"(?:^|[:\s])- \S", m.group(1)), (f, m.group(1))


def test_a_nearby_row_names_a_non_closure_without_red(site):
    """QA-73 on the page: the market's '점포 별로 상이함' in a neighbour's nearby rows, its own tile and its list cell."""
    row = re.search(r'<li class="nr">(?:(?!</li>).)*\[테스트\] 가상 시장 K(?:(?!</li>).)*</li>', _page(site, "test-diner-j"),
                    re.S).group(0)
    assert "점포 별로 상이함" in row and 'class="closed' not in row
    red = r'class="[^"]*closed[^"]*">(?:<[^>]+>)*[^<]*점포 별로 상이함'
    assert not re.search(red, _page(site, "test-market-k"))
    shopping = (site["out"] / "shopping" / "index.html").read_text("utf-8")
    assert "점포 별로 상이함" in shopping and not re.search(red, shopping)
    assert re.search(r'class="kf-main tn closed">매주 월요일', _page(site, "test-kids-m"))   # a closure stays red


def test_an_event_time_never_breaks_inside_a_time(site):
    """QA-75: '17:' / '00입장마감' — each time is one no-wrap piece, the bracket after the range may start a line."""
    ev = next((site["out"] / "events").glob("*/index.html")).read_text("utf-8")
    tile = re.search(r'<div class="kf-i kf-playtime">(.*?)</div>', ev, re.S).group(1)
    assert '<span class="nw">10:00–18:00</span><wbr>(<span class="nw">17:00</span>입장마감)' in tile


def test_a_list_card_says_what_it_lacks_once(site):
    """QA-77: a card with some empty cells said '확인 필요' in each (571 times on /places/): its values stay in their
    cells, the empty ones go into one line at its end; a card with none keeps its one line (QA-27)."""
    html = (site["out"] / "shopping" / "index.html").read_text("utf-8")
    li = _card(html, "[테스트] 가상 상점 G")
    assert li.count("확인 필요") == 1 and 'class="kf-na"' not in li
    assert '<p class="rec-need">확인 필요: 쉬는 날·전화</p>' in li
    assert '<div class="c-hours" data-c="2">' in li and '<div class="c-parking" data-c="4">' in li
    assert "c-closed" not in li and "c-tel" not in li
    full = _card(html, "[테스트] 가상 시장 K")   # nothing missing: no line, no column marks
    assert "확인 필요" not in full and "data-c=" not in full
    for page in ("places", "shopping", "food", "cafes", "stays"):
        p = site["out"] / page / "index.html"
        if p.exists():
            for m in re.finditer(r'<li class="rec"[^>]*>.*?</li>', p.read_text("utf-8"), re.S):
                assert m.group(0).count("확인 필요") <= 1, m.group(0)[:300]
