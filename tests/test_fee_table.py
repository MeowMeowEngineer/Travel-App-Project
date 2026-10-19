"""pipeline/fee_table.py — a place's fee value read as the table a visitor pays (review 2026-10-17, AI 코스 만들기
집중 평가 CE01·CE03: the planner now prices every visit from these tables itself)."""
from pipeline.fee_table import parse


def test_free_and_free_with_a_proviso():
    assert parse("무료") == {"free": True}
    assert parse("무료 (단, 여객선 비용 별도)") == {"free": True, "note": "단, 여객선 비용 별도"}
    assert parse("무료 (※ 단, 체육시설은 유료)") == {"free": True, "note": "단, 체육시설은 유료"}


def test_the_place_s_own_ticket_not_the_combined_one():
    museum = "[박물관 통합권]\n- 성인 3,000원\n- 청소년·군인 2,000원\n- 어린이 1,000원\n[개별권]\n- 성인 2,000원\n- 청소년·군인 1,000원\n- 어린이 500원\n※ 자세한 사항은 홈페이지 참조"
    assert parse(museum) == {"tab": {"성인": 2000, "청소년·군인": 1000, "어린이": 500}, "tl": "개별권"}
    gallery = "[군산근대미술관 개별권]\n- 성인 500원\n- 청소년, 군인 300원\n- 어린이 200원\n[통합권]인근 전시장(박물관+미술관+건축관+위봉함)\n- 성인 3,000원"
    assert parse(gallery)["tab"] == {"성인": 500, "청소년·군인": 300, "어린이": 200}


def test_the_visitor_s_price_not_the_resident_s_or_the_group_s():
    t = ("[군산시민]\n- 성인 1,000원\n- 청소년/군인 500원\n- 어린이 300원\n[타지역]\n- 성인 2,000원\n- 청소년/군인 1,000원\n"
         "- 어린이 500원\n※ 무료 : 6세 이하 유아 / 65세 이상 경로대상자 / 매주 수요일 문화가 있는 날 무료 관람\n※ 자세한 사항은 홈페이지 참조")
    assert parse(t) == {"tab": {"성인": 2000, "청소년·군인": 1000, "어린이": 500}, "tl": "타지역",
                        "fr": [{"w": "6세 이하 유아", "max": 6}, {"w": "65세 이상 경로대상자", "min": 65},
                               {"w": "매주 수요일 문화가 있는 날 무료 관람", "wd": 3}]}
    columns = ("개인 20인이상 단체 성인(군산시거주자) 1,000원(500원) 700원(300원) 청소년·군인(군산시거주자) 700원(300원) "
               "400원(200원) 어린이(군산시거주자) 500원(200원) 300원(100원) 무료입장 6세이하 유아, 65세이상 어른, 장애인, 유공자")
    r = parse(columns)
    assert r["tab"] == {"성인": 1000, "청소년·군인": 700, "어린이": 500}
    assert r["fr"] == [{"w": "6세이하 유아", "max": 6}, {"w": "65세이상 어른", "min": 65}, {"w": "장애인"}, {"w": "유공자"}]
    assert parse("[개인]\n- 성인 12,000원\n- 청소년 11,000원\n- 어린이 10,000원\n[단체(20인 이상)]\n- 성인 10,000원\n※ 무료 : 만 36개월 미만") \
        == {"tab": {"성인": 12000, "청소년": 11000, "어린이": 10000}, "tl": "개인", "fr": [{"w": "만 36개월 미만", "max": 2}]}


def test_no_table_this_reader_can_be_priced_from():
    # numbers without 원, rooms, months, ferries, ages only in words: the planner says 확인 필요
    assert parse("개인 단체(20인 이상) 성인 (군산시민) 1,000 (500) 700 (300)") == {}
    assert parse("월마다 요금이 다르므로 전화 문의 또는 홈페이지 참조 요망") == {}
    assert parse("[배편요금]- 입도 13,050원 / 출도 12,000원 (성인기준)") == {}
    assert parse("초등학생이상(1만원), 유치원생이하(5,000원)") == {}
    assert parse("1박 198,000원~350,000원(날짜·시즌에 따라 다름)") == {}
    assert parse("") == {}
