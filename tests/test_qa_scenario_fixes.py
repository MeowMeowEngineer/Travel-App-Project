"""The scenario QA of 2026-10-19 (QA lead's merged list, 'fix now' items): each fix read against made-up values — the
TourAPI shapes the testers met, written here with fake names and numbers — and against a build of the Incheon
configuration with the tiny fixture (tests/fixtures/incheon_tiny) plus a few fake records. Nothing here is real data.

QA-04 search rows carry their kind as type · QA-08 a closed day says so · QA-11 the official places in the catalog ·
QA-12 an event's programme places · QA-13 running events before later ones · QA-14/24/25 the search's words ·
QA-18 hours brackets and open groups · QA-19 the visitor's own fee group · QA-20 paid parking · QA-21 every homepage
address, Korean domains · QA-22 TourAPI dash lists · QA-27 one '확인 필요' a card · QA-29 perf_check gzips ·
QA-30 the fee table's own word · QA-31 hours without times · QA-33 the planner's count · QA-35 one check date a record ·
QA-38 the reference distances · QA-43 particles after digits and Latin letters · QA-44 the same missing labels ·
QA-45 a misspelt 연중무휴 · QA-46 the phone's range · QA-49 쇼핑 in the menu, the launcher early · QA-50 one planner
link · QA-51/52/53 event pages and their venues."""
import datetime as dt
import gzip
import json
import re
import shutil
import types
import urllib.request
from pathlib import Path

import pytest

from pipeline import city, fee_table, present
from pipeline.build import State, build
from pipeline.textutil import (display_value, extract_url, extract_urls, josa, link_url, parking_text, url_shown,
                               web_text, web_url)
from tools import tourapi_details

ROOT = Path(__file__).resolve().parent.parent
INCHEON = ROOT / "data" / "incheon"
TINY = Path(__file__).resolve().parent / "fixtures" / "incheon_tiny"
RECORDS = ("places.json", "events.json", "courses.json", "guides.json", "themes.json", "videos.json")
SRC = {"provider": "한국관광공사 TourAPI", "checked_at": "2026-10-19", "contentid": ""}


# ------------------------------------------------------------------ values (no build)
def test_paid_parking_reads_as_words_on_the_page_and_its_tile():
    """QA-20: '가능요금 (대형 8,000원 / 소형 2,000원)' showed as it came."""
    assert parking_text("가능요금 (대형 8,000원 / 소형 2,000원)") == "가능, 요금 대형 8,000원 / 소형 2,000원"
    assert parking_text("가능\n요금 (1일 최대 2,000원)") == "가능, 요금 1일 최대 2,000원"
    assert parking_text("가능 (○○ 주차장 이용)\n요금 (무료)") == "가능 (○○ 주차장 이용), 요금 무료"
    assert parking_text("가능요금 (무료)") == "가능, 요금 무료" and parking_text("불가능") == "불가"
    assert display_value("parking", "가능요금 (대형 8,000원 / 소형 2,000원)") == "가능, 요금 대형 8,000원 / 소형 2,000원"
    b = present.brief_parking("가능요금 (대형 8,000원 / 소형 2,000원)")
    assert (b["main"], b["sub"], b["more"]) == ("가능", "요금 대형 8,000원", True)


def test_every_homepage_address_is_kept_and_korean_domains_read_as_written():
    """QA-21: '인천관광 https://itour.example.kr국가유산청 https://www.heritage.example.kr/' was one broken link."""
    assert extract_urls("관광 https://itour.example.kr국가유산청 https://www.heritage.example.kr/main.html") == \
        ["https://itour.example.kr", "https://www.heritage.example.kr/main.html"]
    assert extract_urls("관광 https://www.example.kr/tour/국가유산청 https://h.example.kr/") == \
        ["https://www.example.kr/tour/", "https://h.example.kr/"]
    assert extract_urls("투어 https://itour.example.kr/DRFA365예술극장 https://drfa.example.kr/") == \
        ["https://itour.example.kr/", "https://drfa.example.kr/"]
    assert extract_urls("공식 https://instagram.com/x_y공식 블로그 https://blog.naver.com/z") == \
        ["https://instagram.com/x_y", "https://blog.naver.com/z"]
    assert extract_urls("http://달빛마을.kr/") == ["http://달빛마을.kr/"]   # a Korean domain alone stays whole
    assert extract_url('<a href="https://a.example.kr/x?b=1&amp;c=2" target="_blank">https://a.example.kr/</a>') == \
        "https://a.example.kr/x?b=1&c=2"
    assert web_text("http://www.xn--939a42kurip4ljpixnkywb.com/") == "강화바다캠핑장.com"
    assert url_shown("http://www.xn--939a42kurip4ljpixnkywb.com/a?b=1") == "www.강화바다캠핑장.com/a?b=1"   # the sources list
    two = "https://itour.example.kr\nhttps://www.heritage.example.kr/main.html"
    assert display_value("homepage", two) == "itour.example.kr\nheritage.example.kr"
    assert link_url(two) == web_url(two) == "https://itour.example.kr"
    v = present.value_view("homepage", two)
    assert v["url"] == "https://itour.example.kr" and str(v["html"]).count("<a ") == 2
    facts = tourapi_details.tourapi_facts({"homepage": "관광 https://itour.example.kr국가유산청 https://h.example.kr/"}, {}, [], "12")
    assert facts["homepage"] == "https://itour.example.kr\nhttps://h.example.kr/"


def test_tourapi_dash_lists_are_lines_not_one_run_in_the_status_line():
    """QA-22: '- 입실 14:00- 퇴실 12:00' and '무료※ 기획 전시는 유료…' showed raw in search rows."""
    e = {"kind": "stay", "facts": {"checkin": "- 입실 14:00- 퇴실 12:00", "parking": "가능"}}
    texts = [x["text"] for x in present.status_items(e)]
    assert texts and not any("- " in t for t in texts)
    e = {"kind": "attraction", "facts": {"usefee": "무료※ 기획 전시는 유료", "usetime": "09:00~18:00"}}
    assert not any("※" in x["text"] for x in present.status_items(e))


def test_a_closed_day_says_it_is_closed_and_a_misspelt_open_value_is_open():
    """QA-08: 연휴 and 공휴일 hold 휴 but say no closure; QA-45: '얀중무휴'."""
    assert present._closed_word("1월 1일 / 설·추석 연휴", "attraction") == "1월 1일 / 설·추석 연휴 휴관"
    assert present._closed_word("매주 월요일 (단, 공휴일이면 다음날 휴관)", "attraction") == "매주 월요일 (단, 공휴일이면 다음날 휴관)"
    assert present._closed_word("주말 / 공휴일", "attraction") == "주말 / 공휴일"   # the search row adds '쉬는 날'
    assert present.is_open_value("얀중무휴") and present.is_open_value("연중무휴")
    assert not present.is_open_value("매주 월요일 무휴") and not present.is_open_value("명절 무휴")
    assert not present.is_closed_word("얀중무휴")


def test_hours_and_fee_tiles_keep_brackets_open_groups_and_the_visitors_second_price():
    """QA-18: '하절기 (3~10월 09:30–17:30' and a group's '상시 개방' left behind; QA-19: '일반 3,000원 / 개인'."""
    b, _ = present.brief_hours("[1관]\n- 하절기 (3~10월) 09:30~17:30\n- 동절기 (11~2월) 09:30~16:30")
    assert b["main"] == "1관 하절기 (3~10월) 09:30–17:30" and b["sub"] == "1관 동절기 (11~2월) 09:30–16:30"
    b, _ = present.brief_hours("[공원] - 상시 개방[체험장] - 10:00~12:00- 14:00~15:00※ 겨울에는 실내 교육")
    assert b["main"] == "공원 상시 개방" and b["sub"] == "체험장 10:00–12:00" and b["more"]
    b = present.brief_fee("[개인]- 일반 3,000원- 어린이 2,000원[단체]- 일반 2,500원- 어린이 1,500원")
    assert (b["main"], b["sub"], b["more"]) == ("일반 3,000원", "어린이 2,000원", True)
    b = present.brief_fee("[개인]- 성인 1,000원[단체]- 성인 800원")
    assert (b["main"], b["sub"], b["more"]) == ("성인 1,000원", "", True)


def test_particles_follow_digits_latin_letters_and_skip_a_bracket():
    """QA-43: '오션97는', '마레 616는'."""
    assert josa("카페97", "은/는") == "카페97은" and josa("마레 616", "은/는") == "마레 616은"
    assert josa("카페2", "은/는") == "카페2는" and josa("홀 10", "이/가") == "홀 10이" and josa("홀 1000", "으로/로") == "홀 1000으로"
    assert josa("ABC HOTEL", "은/는") == "ABC HOTEL은" and josa("CGV", "은/는") == "CGV는" and josa("Inn", "은/는") == "Inn은"
    assert josa("12코스 (가상길)", "은/는") == "12코스 (가상길)는" and josa("공원", "으로/로") == "공원으로"


def test_the_first_screen_phone_keeps_the_sources_range():
    """QA-46: '032-000-0000~4' read '032-000-0000' on the first screen."""
    e = {"kind": "attraction", "facts": {"infocenter": "032-000-0000~4"}, "fact_sources": {"infocenter": SRC}}
    tel = next(x for x in present.status_items(e, full=True) if x["key"] == "tel")
    assert tel["text"] == "032-000-0000~4" and str(tel["html"]).endswith("</a>~4")
    assert present.slot_value(e, "tel")["tel_tail"] == "~4"


def test_the_fee_table_keeps_its_own_word_for_the_adult_price():
    """QA-30: the planner quoted '요금표 '성인'' where the table says 일반."""
    t = fee_table.parse("[개인]- 일반 3,000원- 어린이 2,000원[단체]- 일반 2,500원")
    assert t["tab"]["성인"] == 3000 and t["aw"] == "일반"
    assert "aw" not in fee_table.parse("성인 2,000원 / 청소년 1,000원")


def test_running_events_ending_this_week_rank_before_events_weeks_away():
    """QA-13: a festival in its last days sat below events a month away and left the home's top three."""
    today = dt.date(2026, 10, 19)
    d = lambda n: (today + dt.timedelta(days=n)).isoformat()   # noqa: E731
    evs = [{"name": "[테스트] 영화 주간", "start_date": d(4), "end_date": d(6)},
           {"name": "[테스트] 디자인 박람회", "start_date": d(32), "end_date": d(34)},
           {"name": "[테스트] 마켓", "start_date": d(5), "end_date": d(6)},
           {"name": "[테스트] 국화축제", "start_date": d(-3), "end_date": d(6)},
           {"name": "[테스트] 연중 행사", "start_date": d(-200), "end_date": d(70)}]
    S = types.SimpleNamespace(events=evs, today=today.isoformat())
    names = [r["ev"]["name"] for r in present.ranked_events(S)]
    assert names.index("[테스트] 국화축제") < names.index("[테스트] 디자인 박람회") < names.index("[테스트] 연중 행사")
    assert names[:3] == ["[테스트] 영화 주간", "[테스트] 마켓", "[테스트] 국화축제"]


def test_the_festival_collector_keeps_the_programmes_place_lines():
    """QA-12: '장소: 인천국제공항' hid '출국장 면세구역' (a boarding pass is needed)."""
    item = {"contentid": "1", "title": "[테스트] 산책", "eventstartdate": "20260105", "eventenddate": "20261231"}
    intro = {"eventplace": "가상공항", "program": "- 기간 : 2026/1/5~2026/12/31\n- 장소 : 가상공항 제1터미널 출국장 면세구역\n"
             "- 주요 프로그램 : 행렬\n\n- 장소 : 가상공항 제2터미널 출국장 면세구역\n- 장소 : 가상공항 제1터미널 출국장 면세구역"}
    ev = tourapi_details.festival_event(item, intro, {}, "2026-10-19")
    assert ev["place_detail"] == "가상공항 제1터미널 출국장 면세구역\n가상공항 제2터미널 출국장 면세구역"


def test_the_search_words_find_indoor_places_one_spelling_and_the_citys_short_names():
    """QA-14, QA-24, QA-25: the rain words find the indoor types (never a bare 전시), 아이 never a bare 가족, 짜장면
    and 자장면 each other, and site.json city.search_aliases ('인천공항' → 인천국제공항) join the words."""
    by_say = {w: c for c in present.SEARCH_CONCEPTS for w in c["say"]}
    rain = by_say["비 오는"]["find"]
    assert {"박물관", "미술관", "과학관", "전시관", "박물관·전시", "문화시설"} <= set(rain) and "전시" not in rain
    assert "가족" not in by_say["아이랑"]["find"]
    assert by_say["자장면"] is by_say["짜장면"] and {"짜장", "자장면"} <= set(by_say["자장면"]["find"])
    city.activate_dir(INCHEON)
    concepts = json.loads(present.search_form_data("인천")["concepts"])
    assert {"say": ["인천공항"], "find": ["인천국제공항"]} in concepts


def test_perf_check_serves_text_gzipped_like_the_host(tmp_path):
    """QA-29: the plain http.server sent everything raw (FCP = LCP, a failing exit)."""
    from tools import perf_check
    (tmp_path / "a").mkdir()
    (tmp_path / "a" / "index.html").write_text("<p>" + "가" * 4000 + "</p>", "utf-8")
    (tmp_path / "f.woff2").write_bytes(b"\0" * 100)
    srv = perf_check.serve(tmp_path, 8797)
    try:
        req = urllib.request.Request("http://127.0.0.1:8797/a/", headers={"Accept-Encoding": "gzip"})
        with urllib.request.urlopen(req) as r:
            assert r.headers["Content-Encoding"] == "gzip" and r.headers["Content-Type"].startswith("text/html")
            assert "가" * 4000 in gzip.decompress(r.read()).decode("utf-8")
        with urllib.request.urlopen(urllib.request.Request("http://127.0.0.1:8797/f.woff2",
                                                           headers={"Accept-Encoding": "gzip"})) as r:
            assert r.headers.get("Content-Encoding") is None and len(r.read()) == 100
    finally:
        srv.terminate()


# ------------------------------------------------------------------ a build of the Incheon configuration
def _place(pid, slug, name, kind, facts, geo=None, **extra):
    return {"id": pid, "slug": slug, "name": name, "kind": kind, "category": present.KIND_LABELS[kind], "themes": [],
            "tier": "basic", "status": "draft", "summary": "", "facts": facts, "facts_source": dict(SRC),
            "fact_sources": {k: dict(SRC) for k in facts}, "official": {}, "original": {},
            "map_ids": {"naver_place_id": "", "google_place_id": ""}, "images": [], "tourapi": {},
            **({"geo": {"lat": geo[0], "lng": geo[1], "source": "TourAPI"}} if geo else {}), **extra}


@pytest.fixture(scope="module")
def site(tmp_path_factory):
    tmp = tmp_path_factory.mktemp("qa")
    data = tmp / "data"
    data.mkdir()
    for f in INCHEON.glob("*.json"):
        if f.name not in RECORDS:
            shutil.copy(f, data / f.name)
    for f in TINY.glob("*.json"):
        shutil.copy(f, data / f.name)
    cfg = json.loads((data / "site.json").read_text("utf-8"))
    cfg["city"]["distance_anchors"] = ["[테스트] 가상 해변 A"]
    (data / "site.json").write_text(json.dumps(cfg, ensure_ascii=False), "utf-8")
    places = json.loads((data / "places.json").read_text("utf-8"))
    places += [
        _place("test-0101", "test-museum-h", "[테스트] 가상 박물관 H", "attraction",
               {"address": "인천광역시 연수구 테스트로 9 (송도동)", "usetime": "09:00~18:00", "restdate": "주말 / 공휴일",
                "usefee": "[개인]- 일반 3,000원- 어린이 2,000원[단체]- 일반 2,500원",
                "parking": "가능요금 (대형 8,000원 / 소형 2,000원)", "infocenter": "032-000-0000~4",
                "homepage": "https://a.example.kr\nhttps://www.xn--939a42kurip4ljpixnkywb.com/"},
               (37.41, 126.65)),
        _place("test-0102", "test-gym-i", "[테스트] 가상 체육공원 I", "attraction",
               {"address": "인천광역시 서구 테스트로 3 (왕길동)", "usetime": "※ 시설별 상이하므로 홈페이지 참고",
                "restdate": "연중무휴"}, (37.6, 126.6)),
    ]
    (data / "places.json").write_text(json.dumps(places, ensure_ascii=False), "utf-8")
    today = dt.date.today()
    events = [{"id": "event-test-1", "contentid": "", "status": "draft", "name": "[테스트] 가상 축제",
               "start_date": (today - dt.timedelta(days=1)).isoformat(),
               "end_date": (today + dt.timedelta(days=60)).isoformat(),
               "place_name": "가상 박물관 H", "place_detail": "가상 박물관 H 1층 로비\n가상 박물관 H 2층 전시실",
               "address": "인천광역시 연수구 테스트로 9 (송도동)", "summary": "", "source_name": "한국관광공사 TourAPI",
               "source_url": "", "checked_at": "2026-10-19",
               "playtime": "- 1관 11:00~11:30 / 14:00~14:30- 2관 일요일~화요일 13:00~13:30", "fee": "무료",
               "geo": {"lat": 37.41005, "lng": 126.65005, "source": "TourAPI"}}]
    (data / "events.json").write_text(json.dumps(events, ensure_ascii=False), "utf-8")
    out = tmp / "out"
    build(data, out, "preview")
    city.activate_dir(data)
    return {"data": data, "out": out, "S": State(data, "preview")}


def _text(html: str) -> str:
    html = re.sub(r"<script.*?</script>|<template.*?</template>", " ", html, flags=re.S)
    return re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " ", html)).replace("&amp;", "&")


def test_search_rows_carry_the_kind_and_say_a_closed_day(site):
    """QA-04: 음식점 and 관광지 rows had no type to find them by; QA-08: '주말 / 공휴일' read like opening days."""
    rows = json.loads((site["out"] / "search" / "index.json").read_text("utf-8"))
    by = {r["n"]: r for r in rows}
    assert by["[테스트] 가상 식당 B"]["t"] == "음식점"
    assert all(r["t"] for r in rows if r["k"] in ("attraction", "food", "cafe", "shopping", "stay"))
    assert "관광지" in {r["t"] for r in rows if r["k"] == "attraction"}
    assert "쉬는 날 주말 / 공휴일" in by["[테스트] 가상 박물관 H"]["s"]


def test_place_page_parking_homepages_phone_and_missing_labels(site):
    """QA-20, QA-21, QA-44, QA-46 on the built page."""
    html = (site["out"] / "places" / "test-museum-h" / "index.html").read_text("utf-8")
    t = _text(html)
    assert "가능요금" not in t and "가능, 요금 대형 8,000원 / 소형 2,000원" in t
    assert 'href="https://a.example.kr"' in html and "강화바다캠핑장.com" in t and "xn--" not in t
    # each address its own link wherever the homepage is printed (the facts table too)
    assert not re.search(r"<a [^>]*>[^<]*\n[^<]*</a>", html)
    assert 'href="https://www.xn--939a42kurip4ljpixnkywb.com/"' in html
    assert "</a>~4" in html
    cafe = (site["out"] / "places" / "test-cafe-f" / "index.html").read_text("utf-8") \
        if (site["out"] / "places" / "test-cafe-f").exists() else None
    pages = [p for p in (site["out"] / "places").glob("*/index.html") if "[테스트] 가상 카페 F" in p.read_text("utf-8")[:4000]]
    cafe = cafe or pages[0].read_text("utf-8")
    need = re.search(r'<p class="kf-need">확인 필요: ([^<]+)</p>', cafe)
    card = re.search(r'<p class="need"><b>확인 필요</b> ([^<]+)</p>', cafe)
    assert need and card and need.group(1) == card.group(1)   # one wording on one page


def test_a_list_card_with_no_value_says_so_once(site):
    """QA-27: '확인 필요' in every cell of a list-only card."""
    html = (site["out"] / "places" / "index.html").read_text("utf-8")
    li = re.search(r'<li class="rec"[^>]*>(?:(?!</li>).)*\[테스트\] 가상 공원 D(?:(?!</li>).)*</li>', html, re.S).group(0)
    assert li.count("확인 필요") == 1 and '<p class="rec-need">확인 필요: ' in li and "rec-cells" not in li


def test_long_name_lists_after_the_first_group_are_skipped_off_screen(site):
    """QA-28: list pages, /map/ and the search directory set every name at once (fonts over the 300 KB budget):
    every group but the first is content-visibility:auto (.cvk) with a size kept for it; on /map/ the 동 groups too."""
    css = "\n".join(f.read_text("utf-8") for f in sorted((ROOT / "templates" / "assets" / "css").glob("*.css")))
    assert re.search(r"\.cvk\s*\{[^}]*content-visibility:\s*auto", css)
    for page, cls in (("places", "lg-group"), ("map", "region"), ("map", "dong"), ("search", "dir-g")):
        html = (site["out"] / page / "index.html").read_text("utf-8")
        tags = [m.group(0) for m in re.finditer(rf'<section class="{cls}(?: cvk)?"[^>]*>', html)]
        assert tags and not tags[0].startswith(f'<section class="{cls} cvk"'), (page, cls)
        assert all("cvk" in t and "contain-intrinsic-size:auto " in t for t in tags[1:]), (page, cls)


def test_event_page_lines_venue_and_no_false_length(site):
    """QA-12 (세부 장소), QA-51 (no 'N일 동안' for a long programme), QA-52 (playtime lines), QA-53 (venue both ways)."""
    page = next((site["out"] / "events").glob("*/index.html"))
    html = page.read_text("utf-8")
    t = _text(html)
    assert "세부 장소" in t and "가상 박물관 H 1층 로비" in t
    assert "동안 열리는 행사입니다" not in t
    assert "14:00–14:30- 2관" not in t and "2관 일요일~화요일" in t
    assert "/places/test-museum-h/" in html   # 열리는 곳
    venue = (site["out"] / "places" / "test-museum-h" / "index.html").read_text("utf-8")
    assert page.parent.name in venue


def test_menu_home_and_planner_page(site):
    """QA-49 (쇼핑 in the menu, the launcher right after the header), QA-50 (one planner link on the first screen),
    QA-33 (the planner counts the places with hours)."""
    home = (site["out"] / "index.html").read_text("utf-8")
    assert '<a href="/shopping/"' in home.split("</header>", 1)[0]
    after = home.split("</header>", 1)[1]
    assert after.lstrip().startswith('<button type="button" class="chat-fab"')
    assert home.count('class="chat-fab"') == 1 and home.count('<nav class="qm"') == 1
    starts = re.search(r'<nav class="ho-go".*?</nav>', home, re.S)
    assert not starts or "/plan/" not in starts.group(0)
    plan = (site["out"] / "plan" / "index.html").read_text("utf-8")
    n_hours = sum(1 for e in site["S"].entities if (e.get("facts") or {}).get("usetime"))
    assert f'운영시간이 실린 곳 <b class="tn">{n_hours}</b>곳' in plan
    search = (site["out"] / "search" / "index.html").read_text("utf-8")
    assert "classList.add('has-q')" in search.split("</head>", 1)[0]
    assert '<a href="/cafes/">' in search.split("data-none-help", 1)[1].split("</nav>", 1)[0]


def test_the_assistants_knowledge(site):
    """QA-11 (공식 확인처 in the catalog), QA-35 (the check date once, on the 날짜 line), QA-38 (the reference
    distances), QA-20 (parking in words), QA-31 (hours without a time are the site's words)."""
    cat = (site["out"] / "chat" / "catalog.txt").read_text("utf-8")
    assert re.search(r"^# 공식 확인처 .*인천투어 https://itour\.incheon\.go\.kr/", cat, re.M)
    docs = json.loads((site["out"] / "chat" / "docs.json").read_text("utf-8"))["docs"]
    x = docs["/places/test-museum-h/"]["x"]
    assert "(출처 확인 2026-10-19)" not in x and "날짜: 출처 확인 2026-10-19" in x
    assert "- 주차: 가능, 요금 대형 8,000원 / 소형 2,000원 — 한국관광공사 TourAPI" in x
    assert re.search(r"^기준 장소까지 직선거리: \[테스트\] 가상 해변 A /places/test-beach-a/ 직선 [\d.]+k?m", x, re.M)
    gym = docs["/places/test-gym-i/"]
    assert gym["f"]["h"] == [{"p": "한국관광공사 TourAPI", "t": "※ 시설별 상이하므로 홈페이지 참고"}]
    assert "032-000-0000~4" in cat
