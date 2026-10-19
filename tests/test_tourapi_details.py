"""tools/tourapi_details.py — per-field sources, agreement vs. conflict, TourAPI-only places, festivals."""
from tools.tourapi_details import (alternate_name, duplicate_candidates, event_key, festival_event, merge_facts,
                                   new_place, same_meaning, tourapi_facts)

TODAY = "2026-10-08"


def test_same_meaning_keeps_detail_and_flags_real_differences():
    assert same_meaning("09:00~18:00", "09:00 ~ 18:00")
    assert same_meaning("10:00~17:00", "10:00~17:00<br>※ 20분 전 입장마감")
    assert same_meaning("7대/40석", "가능")          # a count implies parking exists
    assert not same_meaning("09:00~18:00", "10:00~17:00")
    assert not same_meaning("가능", "불가능")
    assert not same_meaning("매주 월요일", "연중무휴")


def test_tourapi_facts_maps_intro_info_and_common():
    common = {"tel": "063-000-0000", "homepage": '<a href="https://ex.kr">ex</a>', "addr1": "군산시 해망로 240"}
    intro = {"usetime": "09:00~18:00<br>입장마감 17:00", "restdate": "매주 월요일", "parking": "가능",
             "chkcreditcard": "가능", "infocenter": ""}
    info = [{"infoname": "입 장 료", "infotext": "무료"}, {"infoname": "촬영장소", "infotext": "영화 촬영지"}]
    f = tourapi_facts(common, intro, info, "12")
    assert f["usetime"] == "09:00~18:00\n입장마감 17:00" and f["restdate"] == "매주 월요일"
    assert f["usefee"] == "무료" and f["filming"] == "영화 촬영지" and f["infocenter"] == "063-000-0000"
    assert f["homepage"] == "https://ex.kr" and f["address"] == "군산시 해망로 240" and f["creditcard"] == "가능"
    food = tourapi_facts({}, {"opentimefood": "11:00~21:00", "kidsfacility": "0", "firstmenu": "짬뽕"}, [], "39")
    assert food == {"usetime": "11:00~21:00", "menu": "짬뽕"}  # 0/1 flag '0' is not a fact


def test_merge_adds_with_source_confirms_agreement_and_keeps_both_on_conflict():
    place = {"name": "가게", "facts": {"address": "군산시 구영3길 70", "usetime_restdate": "11:30~21:00 / 연중무휴",
                                      "parking_seats": "7대/40석", "menu": "짬뽕"},
             "facts_source": {"provider": "군산시 문화관광", "checked_at": TODAY}}
    new = {"usetime": "11:30~21:00", "restdate": "연중무휴", "parking": "가능", "seat": "40석",
           "infocenter": "063-1", "menu": "물짜장", "address": "군산시 구영3길 70 (영화동)"}
    res = merge_facts(place, new, TODAY, "99")
    assert res["added"] == ["infocenter"]
    assert place["facts"]["infocenter"] == "063-1"
    assert place["fact_sources"]["infocenter"] == {"provider": "한국관광공사 TourAPI", "checked_at": TODAY, "contentid": "99"}
    assert "usetime" not in place["facts"] and "restdate" not in place["facts"]   # same info as usetime_restdate
    assert place["fact_sources"]["usetime_restdate"]["confirmed_by"].startswith("한국관광공사 TourAPI")
    assert place["fact_sources"]["address"]["provider"] == "군산시 문화관광"
    assert place["facts"]["menu"] == "짬뽕"                                     # never overwritten
    assert place["fact_alternatives"]["menu"] == [{"value": "물짜장", "provider": "한국관광공사 TourAPI",
                                                   "checked_at": TODAY, "contentid": "99", "relation": "also"}]
    assert res["also"] == ["menu"] and res["conflicts"] == []   # a second dish is not a contradiction
    again = merge_facts(place, new, TODAY, "99")                               # idempotent
    assert len(place["fact_alternatives"]["menu"]) == 1 and again["added"] == []


def test_locked_facts_untouched_and_alternate_name():
    place = {"name": "근대역사박물관", "locks": ["facts"], "facts": {}}
    assert merge_facts(place, {"usetime": "9"}, TODAY, "1") == {"added": [], "confirmed": [], "conflicts": [], "also": []}
    assert place["facts"] == {}
    assert alternate_name({"name": "근대역사박물관"}, "군산근대역사박물관") == "군산근대역사박물관"
    assert alternate_name({"name": "동국사"}, "동국사(군산)") == ""
    assert alternate_name({"name": "쌍용반점"}, "[백년가게]쌍용반점") == ""
    assert alternate_name({"name": "군산 동국사 대웅전"}, "동국사") == ""          # the whole temple, not this hall
    assert alternate_name({"name": "홍인모텔"}, "H(에이치)모텔") == "H(에이치)모텔"


def test_new_place_and_duplicate_candidates():
    item = {"contentid": "7", "contenttypeid": "32", "title": "바다 게스트하우스", "addr1": "군산시 월명로 1",
            "mapx": "126.7", "mapy": "35.9", "firstimage": "http://x/a.jpg", "cpyrhtDivCd": "Type1"}
    p = new_place(item, {"tel": "063-2"}, {"checkintime": "15:00"}, [], TODAY, ["KOGL-1", "KOGL-3"], {"바다-게스트하우스"})
    assert p["slug"] == "바다-게스트하우스-2" and p["kind"] == "stay" and p["status"] == "draft" and p["tier"] == "basic"
    assert p["facts"]["checkin"] == "15:00" and p["fact_sources"]["checkin"]["provider"] == "한국관광공사 TourAPI"
    assert p["images"][0]["url"] == "https://x/a.jpg" and p["geo"]["lat"] == 35.9 and p["summary"] == ""
    ours = [{"slug": "바다", "name": "바다", "kind": "stay", "facts": {"address": "군산시 월명로 1"}},
            {"slug": "산", "name": "산 모텔", "kind": "stay", "facts": {"address": "군산시 다른로 9"}}]
    assert [c["slug"] for c in duplicate_candidates(item, ours, "군산")] == ["바다"]


def test_festival_event_and_key():
    ev = festival_event({"contentid": "5", "title": "2026 군산시간여행축제", "eventstartdate": "20261009",
                         "eventenddate": "20261012", "addr1": "군산시 월명동", "mapx": "126.7", "mapy": "35.98"},
                        {"eventplace": "월명동 일원", "usetimefestival": "무료"}, {}, TODAY)
    assert ev["start_date"] == "2026-10-09" and ev["end_date"] == "2026-10-12" and ev["fee"] == "무료"
    assert ev["source_name"] == "한국관광공사 TourAPI" and ev["status"] == "draft"
    assert event_key("2025 군산시간여행축제") == event_key("제12회 군산시간여행축제") == event_key("군산시간여행축제")


def test_equivalent_always_open_and_more_exact_values_win():
    assert same_meaning("연중무휴", "상시 개방") and same_meaning("연중", "상시개방")
    assert same_meaning("매주 월요일 휴관", "매주 월요일 / 1월 1일 / 시장이 휴관일로 정한 날")
    place = {"name": "굴", "facts": {"address": "전북특별자치도 군산시 해망동", "restdate": "매주 월요일 휴관"},
             "facts_source": {"provider": "군산시 문화관광", "checked_at": TODAY}}
    merge_facts(place, {"address": "전북특별자치도 군산시 군산창2길 48 (해망동)",
                        "restdate": "매주 월요일 / 1월 1일"}, TODAY, "3")
    assert place["facts"]["address"] == "전북특별자치도 군산시 군산창2길 48 (해망동)"
    assert place["fact_sources"]["address"]["provider"] == "한국관광공사 TourAPI"
    assert place["fact_sources"]["address"]["note"] == "군산시 문화관광 표기: 전북특별자치도 군산시 해망동"
    assert place["facts"]["restdate"] == "매주 월요일 / 1월 1일" and "fact_alternatives" not in place
    other = {"name": "역", "facts": {"address": "군산시 임피면 서원석곡로 2-5"}, "facts_source": {"provider": "군산시 문화관광"}}
    merge_facts(other, {"address": "군산시 임피면 서원석곡로 37"}, TODAY, "4")
    assert other["fact_alternatives"]["address"][0]["value"] == "군산시 임피면 서원석곡로 37"


def test_sub_number_address_is_the_same_place_and_more_exact():
    place = {"name": "골프", "facts": {"address": "군산시 옥서면 남군산로 1685"}, "facts_source": {"provider": "군산시 문화관광"}}
    merge_facts(place, {"address": "군산시 옥서면 남군산로 1685-53"}, TODAY, "5")
    assert place["facts"]["address"] == "군산시 옥서면 남군산로 1685-53" and "fact_alternatives" not in place
    hours = {"name": "식당", "facts": {"usetime_restdate": "11:00~21:00 / 연중무휴"}, "facts_source": {"provider": "군산시 문화관광"}}
    res = merge_facts(hours, {"usetime": "11:00~20:00", "restdate": "매주 수요일"}, TODAY, "6")
    assert res["conflicts"] == ["usetime_restdate"] and "relation" not in hours["fact_alternatives"]["usetime_restdate"][0]


def test_rerun_keeps_confirmations_and_shop_fields_map():
    # the weekly refresh merges the same TourAPI values again: notes about the other source must survive
    place = {"name": "굴", "facts": {"address": "전북특별자치도 군산시 해망동", "restdate": "매주 월요일 휴관"},
             "facts_source": {"provider": "군산시 문화관광", "checked_at": TODAY}}
    new = {"address": "전북특별자치도 군산시 군산창2길 48 (해망동)", "restdate": "매주 월요일 / 1월 1일"}
    merge_facts(place, dict(new), TODAY, "3")
    first = {k: dict(v) for k, v in place["fact_sources"].items()}
    merge_facts(place, dict(new), "2026-10-15", "3")
    assert place["fact_sources"]["address"]["note"] == first["address"]["note"]
    assert place["fact_sources"]["address"]["checked_at"] == "2026-10-15"
    rich = {"name": "관", "facts": {"usetime": "09:00~18:00"},
            "fact_sources": {"usetime": {"provider": "관 홈페이지", "confirmed_by": "한국관광공사 TourAPI · 군산시 문화관광 본문"}}}
    merge_facts(rich, {"usetime": "09:00~18:00"}, TODAY, "9")
    assert rich["fact_sources"]["usetime"]["confirmed_by"] == "한국관광공사 TourAPI · 군산시 문화관광 본문"
    shop = tourapi_facts({"tel": ""}, {"opentime": "07:00~20:00", "restdateshopping": "매주 화요일", "fairday": "1, 6일",
                                      "saleitem": "활어 / 건어물", "infocentershopping": "063-443-1981063-443-4819"},
                         [], "38")
    assert shop["usetime"] == "07:00~20:00" and shop["fairday"] == "1, 6일" and shop["saleitem"] == "활어 / 건어물"
    assert shop["infocenter"] == "063-443-1981, 063-443-4819"
