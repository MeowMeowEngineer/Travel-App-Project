"""English pages: Revised Romanization, English addresses, EngService2 matching and the parity check."""
import json

from tools.en_content import CONFLICT_NOTE, address_en, check, match_en, parity, romanize, style

ITEM = {"id": "p1", "slug": "근대건축관", "kind": "attraction", "category": "관광지", "indexable": True,
        "name": "군산근대건축관", "name_en": "Gunsangeundaegeonchukgwan", "name_en_source": "romanized",
        "alternate_names": [],
        "facts": [{"key": "address", "label": "주소", "value": "전북특별자치도 군산시 해망로 214",
                   "address_en_candidate": "214 Haemang-ro, Gunsan-si, Jeonbuk State"},
                  {"key": "usetime", "label": "이용시간", "value": "09:00–18:00",
                   "alternatives": [{"value": "상시 개방", "provider": "한국관광공사 TourAPI"}]},
                  {"key": "restdate", "label": "쉬는 날", "value": "매주 월요일"},
                  {"key": "usefee", "label": "이용요금", "value": "성인 500원, 단체 1만원"},
                  {"key": "infocenter", "label": "문의", "value": "063-454-7870"}],
        "summary": "군산근대건축관은 옛 조선은행 군산지점 건물로, 2008년에 복원을 마쳤습니다.",
        "details": [], "faq": [{"q": "군산근대건축관은 언제 쉬나요?", "a": "매주 월요일에 쉽니다."}],
        "mentions": [], "ko_hash": "x"}

GOOD = {"id": "p1", "name_en": "Gunsangeundaegeonchukgwan",
        "summary": "Gunsangeundaegeonchukgwan is the former Gunsan branch of the Bank of Chosun. Its restoration "
                   "was finished in 2008.",
        "facts": [{"key": "address", "value": "214 Haemang-ro, Gunsan-si, Jeonbuk State"},
                  {"key": "usetime", "value": "09:00–18:00", "alternatives": [{"value": "Always open"}],
                   "note": CONFLICT_NOTE},
                  {"key": "restdate", "value": "Every Monday"},
                  {"key": "usefee", "value": "Adults 500 won, groups 10,000 won"},
                  {"key": "infocenter", "value": "063-454-7870"}],
        "details": [], "faq": [{"q": "When is Gunsangeundaegeonchukgwan closed?", "a": "It is closed every Monday."}]}


def write_pair(tmp_path, out):
    (tmp_path / "en-01.input.json").write_text(json.dumps({"type": "places", "items": [ITEM]}, ensure_ascii=False), "utf-8")
    path = tmp_path / "en-01.output.json"
    path.write_text(json.dumps({"items": [out]}, ensure_ascii=False), "utf-8")
    return path


def test_romanize_follows_revised_romanization():
    assert romanize("월명공원") == "Wolmyeonggongwon"
    assert romanize("신라") == "Silla"            # ㄴ+ㄹ -> ll
    assert romanize("종로") == "Jongno"           # ㅇ+ㄹ -> ng n
    assert romanize("백마") == "Baengma"          # nasalization
    assert romanize("해돋이") == "Haedoji"        # palatalization
    assert romanize("묵호") == "Mukho"            # noun: ㄱ+ㅎ stays k h
    assert romanize("선유도") == "Seonyudo"
    assert romanize("경암동 철길마을") == "Gyeongam-dong Cheolgilmaeul"
    assert romanize("구 일본 제18은행") == "Gu Ilbon Je18eunhaeng"


def test_address_en_reads_road_and_lot_addresses():
    assert address_en("전라북도 군산시 월명공원1길 26") == "26 Wolmyeonggongwon 1-gil, Gunsan-si, Jeonbuk State"
    assert address_en("전북특별자치도 군산시 백토로 284-22 (나운동)") == \
        "284-22 Baekto-ro (Naun-dong), Gunsan-si, Jeonbuk State"
    assert address_en("전북특별자치도 군산시 옥도면 선유도리 474-1") == \
        "474-1 Seonyudo-ri, Okdo-myeon, Gunsan-si, Jeonbuk State"
    assert address_en("전북특별자치도 군산시 수송안7길 36 청담횟집") == ""   # a business name: the translator writes it


def test_match_en_needs_distance_and_type():
    place = {"name": "선유도", "kind": "attraction", "geo": {"lat": 35.81, "lng": 126.41},
             "tourapi": {"contenttypeid": "12"}}
    near = {"contentid": "1", "contenttypeid": "76", "title": "Seonyudo Island (선유도)", "mapy": "35.8105", "mapx": "126.41"}
    food = {**near, "contentid": "2", "contenttypeid": "82"}
    far = {**near, "contentid": "3", "mapy": "35.83"}
    it, dist, basis = match_en(place, [food, far, near])
    assert it["contentid"] == "1" and dist < 150 and basis == "coordinates_type_korean_title"
    assert match_en(place, [food, far])[0] is None


def test_check_passes_a_faithful_translation(tmp_path):
    assert check([write_pair(tmp_path, GOOD)]) == []


def test_check_finds_changed_values_style_and_missing_conflict(tmp_path):
    bad = json.loads(json.dumps(GOOD))
    bad["facts"][1] = {"key": "usetime", "value": "9:00 AM–6:00 PM"}            # 12-hour, conflict dropped
    bad["facts"][2]["value"] = "Every Tuesday"                                   # wrong weekday
    bad["facts"][3]["value"] = "Adults ₩500, groups 1 man won"                   # money convention, 1만원
    bad["facts"][4]["value"] = "+82-63-454-7870"                                 # phone changed
    bad["summary"] = "A famous former bank, restored in 2009. 군산"               # banned word, number, Korean left
    issues = "\n".join(check([write_pair(tmp_path, bad)]))
    for want in ("12-hour time", "facts.usetime.alternatives: missing", f"note must be '{CONFLICT_NOTE}'",
                 "weekday Monday missing", "weekday Tuesday not in Korean", "amount 10,000 won missing",
                 "no ₩/KRW", "phone 063-454-7870 missing", "promotional word: 'famous'", "number 2008 missing",
                 "number 2009 not in Korean", "Korean script left"):
        assert want in issues, want


def test_check_requires_every_item(tmp_path):
    path = write_pair(tmp_path, GOOD)
    path.write_text(json.dumps({"items": []}), "utf-8")
    assert any("p1: not translated" in x for x in check([path]))


def test_parity_reads_approximate_korean_myriads():
    assert parity("부지 70여만 평", "a site of about 700,000 pyeong") == []      # 70여만 = 700,000-plus
    assert parity("5만여 평", "about 50,000 pyeong") == []
    assert "number 70000 not in Korean" in parity("70여만 평", "about 70,000 pyeong")


def test_parity_reads_weekday_abbreviations_with_particles():
    # '월~금은', '토~일에는' (a particle after the range) and '금 11:00' (one day right before a time)
    assert parity("월~금은 11:00-17:00, 토~일은 11:00-18:00에 영업합니다.",
                  "Monday–Friday 11:00–17:00, Saturday–Sunday 11:00–18:00.") == []
    assert parity("월~목 11:00–23:00 금 11:00~익일02:00", "Monday–Thursday 11:00–23:00, Friday 11:00–02:00 the next day") == []
    assert "weekday Friday missing" in parity("금은 11:00~익일 02:00", "11:00–02:00 the next day")
    assert parity("매월 10:00 개장", "Opens at 10:00 every month") == []   # '매월' is not Monday


def test_hours_followed_by_copula_or_particle_are_times():
    assert parity("체크인은 15시이고 체크아웃은 11시입니다", "Check-in is 15:00 and check-out is 11:00.") == []
    assert parity("체크아웃은 12시가 많습니다", "Check-out is usually 12:00.") == []
    assert parity("3시간 걸립니다", "It takes 3 hours.") == []          # 시간 (hours) is not a clock time


def test_programme_title_hour_is_not_a_clock_time():
    assert parity("방송사 채널 영상: 6시 내고향 — 만남스넥", "Broadcaster channel video: 6si Nae Gohyang — Mannam Snack") == []
    assert "number 6 missing" in parity("6시 내고향", "Nae Gohyang")
