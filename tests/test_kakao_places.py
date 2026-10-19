"""tools/kakao_places.py — the matcher accepts a Kakao place only when it is clearly the same place."""
import json

import pytest

from tools import kakao_places as K

# 35.9870, 126.7110 is our point; 0.0009° of latitude is about 100 m
LAT, LNG = 35.9870, 126.7110


def place(name, kind="food", address="전북특별자치도 군산시 중앙로 177 (중앙로1가)", geo=True, **extra):
    p = {"id": "p1", "name": name, "kind": kind, "category": extra.pop("category", "음식점"), "status": "published",
         "facts": {"address": address}}
    if geo:
        p["geo"] = {"lat": LAT, "lng": LNG, "source": "TourAPI"}
    p.update(extra)
    return p


def doc(name, dlat=0.0, road="전북특별자치도 군산시 중앙로 177", jibun="전북특별자치도 군산시 중앙로1가 12-3",
        id="100", group="FD6", category="음식점 > 제과,베이커리"):
    return {"id": id, "place_name": name, "x": str(LNG), "y": str(LAT + dlat), "road_address_name": road,
            "address_name": jibun, "category_group_code": group, "category_name": category,
            "category_group_name": {"FD6": "음식점", "CE7": "카페", "AD5": "숙박"}.get(group, "")}


def test_accepts_exact_name_nearby_with_the_same_building_number():
    r = K.decide(place("이성당"), [doc("이성당", 0.0002)])
    assert r["status"] == "accepted" and r["doc"]["id"] == "100"
    assert r["judge"]["name"]["cls"] == "exact" and round(r["judge"]["dist"]) == 22
    assert "도로명 건물번호 일치(중앙로 177)" in K.basis_text(r["judge"])


def test_accepts_branch_or_region_suffix_only_with_address_agreement():
    # '이성당 본점' (본점 is safe), '링스모텔 장미점' (a branch: the building number must agree)
    assert K.decide(place("이성당"), [doc("이성당 본점")])["status"] == "accepted"
    assert K.decide(place("소담촌"), [doc("소담촌 군산점")])["status"] == "accepted"
    far_street = doc("소담촌 군산점", road="전북특별자치도 군산시 조촌4길 3")
    r = K.decide(place("소담촌"), [far_street])
    assert r["status"] == "none" and r["reason"].startswith("건물번호 불일치")
    # a branch whose road address we cannot compare is not taken on the name alone
    r = K.decide(place("소담촌"), [doc("소담촌 군산점", road="")])
    assert r["status"] == "none" and r["reason"].startswith("이름에 업종·지점어")


def test_rejects_a_chain_branch_with_the_same_name_far_away():
    r = K.decide(place("돔베초밥"), [doc("돔베초밥", 0.0045, road="전북특별자치도 군산시 수송남로 2")])  # ~500 m
    assert r["status"] == "none" and r["reason"].startswith("거리 초과")
    # another numbered branch next door is a different shop
    r = K.decide(place("돔베초밥"), [doc("돔베초밥 2호점", 0.0001)])
    assert r["status"] == "none" and r["reason"].startswith("이름 일부만 같음")


def test_rejects_a_name_contained_but_different_thing():
    for other in ("이성당 주차장", "불주사 대웅전", "선유도해수욕장", "말랭이마을 관광안내소", "이성당 전기차충전소"):
        r = K.decide(place(other.split()[0] if " " in other else "선유도", kind="attraction"), [doc(other)])
        assert r["status"] == "none", other
        assert r["reason"].startswith("이름 일부만 같음"), (other, r["reason"])
    # unrelated names are never matched however close
    assert K.decide(place("신가네칼국수"), [doc("신가네해물칼국수")])["reason"] == "이름 불일치"


def test_rejects_building_number_mismatch():
    r = K.decide(place("스위트인디아", address="전북특별자치도 군산시 우체통거리1길 14-1 (신창동) 1층"),
                 [doc("스위트인디아", road="전북특별자치도 군산시 우체통거리1길 14")])
    assert r["status"] == "none" and r["reason"] == "건물번호 불일치(우체통거리1길 14-1 ≠ 우체통거리1길 14)"


def test_an_exact_name_and_the_same_phone_stand_in_for_the_building_number():
    # '중화반점': ours 동령길 27, Kakao 동령길 29, both 063-452-4044 — no coordinates, same road
    p = place("중화반점", address="전북특별자치도 군산시 동령길 27(장미동)", geo=False)
    p["facts"]["infocenter"] = "063-452-4044"
    same = {**doc("중화반점", road="전북특별자치도 군산시 동령길 29"), "phone": "063-452-4044"}
    r = K.decide(p, [same])
    assert r["status"] == "accepted"
    assert "건물번호 다름(동령길 27 / 동령길 29) · 전화 일치(063-452-4044)" in K.basis_text(r["judge"])
    # another number, or no number on one side: still rejected
    for phone in ("063-452-4045", ""):
        r = K.decide(p, [{**same, "phone": phone}])
        assert r["status"] == "none" and r["reason"].startswith("건물번호 불일치"), phone
    # without our coordinates the road name must agree; with them, the distance check is what places it
    other_road = {**same, "road_address_name": "전북특별자치도 군산시 거석길 29"}
    assert K.decide(p, [other_road])["reason"].startswith("건물번호 불일치")
    near = place("사골뚝배기", address="전북특별자치도 군산시 거석길 29 (신창동)")
    near["facts"]["infocenter"] = "063-445-1107"
    corner = {**doc("사골뚝배기", 0.00005, road="전북특별자치도 군산시 우체통거리1길 7"), "phone": "063-445-1107"}
    assert K.decide(near, [corner])["status"] == "accepted"
    assert K.decide(near, [{**corner, "y": str(LAT + 0.0045)}])["reason"].startswith("거리 초과")
    # a name that is not exact does not get the exception (a branch needs the building number)
    branch = {**doc("중화반점 장미점", road="전북특별자치도 군산시 동령길 29"), "phone": "063-452-4044"}
    assert K.decide(p, [branch])["status"] == "none"


def test_phone_numbers():
    assert K.phone_numbers("063-452-4044") == {"0634524044"}
    assert K.phone_numbers("0507-1315-5312") == {"050713155312"}
    assert K.phone_numbers("군산시청 관광진흥과 063-454-3333\n010-1234-5678, 452-1234") == {"0634543333", "01012345678"}
    assert K.phone_numbers("") == set() and K.phone_numbers(None) == set()


def test_large_places_get_400_m_and_small_ones_150_m():
    island = place("장자도", kind="attraction", category="섬여행", address="전북특별자치도 군산시 옥도면 장자도리")
    assert K.decide(island, [doc("장자도", 0.0030, road="", category="여행 > 관광,명소 > 섬")])["status"] == "accepted"
    assert K.decide(island, [doc("장자도", 0.0040, road="", category="여행 > 관광,명소 > 섬")])["reason"].startswith(
        "거리 초과(445m > 400m)")
    museum = place("국립군산대학교 박물관", kind="attraction", category="문화시설", address="전북특별자치도 군산시 대학로 558")
    r = K.decide(museum, [doc("국립군산대학교 박물관", 0.0023, road="전북특별자치도 군산시 대학로 558")])
    assert r["status"] == "none" and r["reason"].startswith("거리 초과(256m > 150m)")


def test_several_passing_candidates_need_one_clearly_better():
    near_exact, farther_branch = doc("이성당", 0.0001, id="1"), doc("이성당 본점", 0.0005, id="2")
    r = K.decide(place("이성당"), [farther_branch, near_exact])
    assert r["status"] == "accepted" and r["doc"]["id"] == "1"
    # the exact one is not the nearest: hold it
    r = K.decide(place("이성당"), [doc("이성당", 0.0005, id="1"), doc("이성당 본점", 0.0001, id="2")])
    assert r["status"] == "ambiguous"
    # two exact names: hold it
    r = K.decide(place("이성당"), [doc("이성당", 0.0001, id="1"), doc("이성당", 0.0002, id="2")])
    assert r["status"] == "ambiguous"


def test_kind_conflict_and_one_letter_names():
    gh = place("달", kind="stay", address="전라북도 군산시 구영3길 21-2 (월명동 12-10)")
    cafe = doc("달", road="전북특별자치도 군산시 구영3길 21-2", id="cafe", group="CE7", category="음식점 > 카페")
    stay = doc("게스트하우스 달", road="전북특별자치도 군산시 구영3길 21-2", id="gh", group="AD5",
               category="여행 > 숙박 > 게스트하우스")
    r = K.decide(gh, [cafe, stay])
    assert r["status"] == "accepted" and r["doc"]["id"] == "gh"
    assert K.decide(gh, [cafe])["reason"].startswith("유형 불일치")
    # a one-letter name never matches a longer name by containment alone
    assert K.decide(place("틈"), [doc("틈새라면")])["reason"] == "이름 불일치"


def test_word_order_and_region_differences_need_the_address():
    hotel = place("파라다이스 호텔", kind="stay", address="전라북도 군산시 조촌1길 21 (경장동)")
    same = doc("호텔파라다이스", road="전북특별자치도 군산시 조촌1길 21", group="AD5", category="여행 > 숙박 > 호텔")
    assert K.decide(hotel, [same])["status"] == "accepted"
    elsewhere = doc("호텔파라다이스", road="전북특별자치도 군산시 조촌2길 9", group="AD5", category="여행 > 숙박 > 호텔")
    assert K.decide(hotel, [elsewhere])["status"] == "none"
    park = place("군산어린이교통공원", kind="attraction", category="관광지", address="전북특별자치도 군산시 동장산로 135 (소룡동)")
    r = K.decide(park, [doc("군산시 어린이교통공원", road="전북특별자치도 군산시 동장산로 135", category="여행 > 공원")])
    assert r["status"] == "accepted" and r["judge"]["name"]["cls"] == "safe"
    # '호남' is a region word: '호남관세박물관' is Kakao's '관세박물관' in the same building
    museum = place("호남관세박물관", kind="attraction", category="감성여행", address="전북특별자치도 군산시 해망로 244-7(장미동)")
    r = K.decide(museum, [doc("관세박물관", 0.0004, road="전북특별자치도 군산시 해망로 244-7",
                              category="문화,예술 > 문화시설 > 박물관")])
    assert r["status"] == "accepted" and r["judge"]["name"] == {"cls": "safe", "extra": "호남", "how": "name"}


def test_places_without_coordinates_need_name_gunsan_and_building_number():
    p = place("호텔나운", kind="stay", address="전북특별자치도 군산시 현충로 84 (나운동)", geo=False)
    ok = doc("호텔나운", road="전북특별자치도 군산시 현충로 84", group="AD5")
    assert K.decide(p, [ok])["status"] == "accepted"
    assert K.decide(p, [doc("호텔나운", road="전북특별자치도 군산시 현충로 86", group="AD5")])["status"] == "none"
    other_city = doc("호텔나운", road="전북특별자치도 익산시 현충로 84", jibun="전북특별자치도 익산시 영등동 1", group="AD5")
    assert K.decide(p, [other_city])["reason"] == "군산 밖"   # the region (site.json region) the Kakao address must name
    no_road = place("대각산", kind="attraction", category="산", address="전북특별자치도 군산시 옥도면 일원", geo=False)
    assert K.decide(no_road, [doc("대각산", road="", jibun="전북특별자치도 군산시 옥도면 신시도리 산 1",
                                   category="여행 > 산")])["reason"].startswith("좌표 없음")


def test_address_parsers():
    assert K.parse_road("전북특별자치도 군산시 임피면 축산 1길 8") == ("축산1길", "8")
    assert K.parse_road("전북특별자치도 군산시 비응로 43, 1,2층(비응도동)") == ("비응로", "43")
    assert K.parse_road("전북특별자치도 군산시 번영로 12번길 3") == ("번영로12번길", "3")
    assert K.parse_road("전북특별자치도 군산시 중앙로1가 12-3") is None
    assert K.parse_jibun("전북특별자치도 군산시 중앙로1가 12-3") == ("중앙로1가", "12-3")
    assert K.parse_jibun("전북특별자치도 군산시 옥도면 선유도리 산 66") == ("선유도리", "산66")
    assert K.parse_jibun("전북특별자치도 군산시 신흥동 34-5번지 일원(약 1만㎡)") == ("신흥동", "34-5")


def test_collisions_hold_the_alias_match():
    a = {"status": "accepted", "doc": {"id": "9"}, "judge": {"name": {"cls": "exact", "how": "name"}}}
    b = {"status": "accepted", "doc": {"id": "9"}, "judge": {"name": {"cls": "exact", "how": "alternate"}}}
    results = {"a": a, "b": b}
    K.resolve_collisions(results)
    assert results["a"]["status"] == "accepted" and results["b"]["status"] == "ambiguous"


def test_apply_writes_id_and_source_and_removes_its_own_stale_id():
    p1, p2, p3 = place("이성당"), place("돔베초밥"), place("수동")
    p2["id"], p3["id"] = "p2", "p3"
    p2["map_ids"] = {"kakao_place_id": "old"}
    p2["map_id_sources"] = {"kakao_place_id": {"provider": K.PROVIDER, "checked_at": "2026-10-01"}}
    p3["map_ids"] = {"kakao_place_id": "manual"}
    d = {**doc("이성당 본점", 0.0001), "_fetched": "2026-10-14", "_query": "이성당"}
    results = {"p1": K.decide(p1, [d]), "p2": {"status": "none"}, "p3": {"status": "none"}}
    changes = K.apply([p1, p2, p3], results)
    assert p1["map_ids"]["kakao_place_id"] == "100"
    src = p1["map_id_sources"]["kakao_place_id"]
    assert src["provider"] == "Kakao Local API" and src["checked_at"] == "2026-10-14"
    assert src["matched_name"] == "이성당 본점" and src["distance_m"] == 11 and src["url"] == "https://place.map.kakao.com/100"
    assert "kakao_place_id" not in p2["map_ids"] and "map_id_sources" not in p2
    assert p3["map_ids"]["kakao_place_id"] == "manual"
    assert changes == {"added": 1, "removed": 1, "kept_manual": 1}


def test_client_masks_the_key_and_uses_the_cache(tmp_path, monkeypatch):
    key = "abcdef1234567890"
    client = K.KakaoClient(key, tmp_path, max_calls=1)

    class Boom(K.urllib.error.HTTPError):
        def __init__(self):
            super().__init__("u", 401, "Unauthorized", {}, None)

        def read(self):
            return f'{{"errorType":"AccessDeniedError","message":"wrong appkey {key}"}}'.encode()

    def fail(req, timeout=0):
        assert req.get_header("Authorization") == f"KakaoAK {key}"
        raise Boom()
    monkeypatch.setattr(K.urllib.request, "urlopen", fail)
    with pytest.raises(K.KakaoError) as e:
        client.search("이성당", 126.7, 35.9)
    assert key not in str(e.value) and "«KEY»" in str(e.value) and "AccessDeniedError" in str(e.value)
    # a cached answer costs no call, and the per-run cap stops the next live one
    params = {"query": "이성당", "sort": "accuracy", "size": 15, "page": 1, "x": "126.7000000", "y": "35.9000000",
              "radius": 1000}
    client._path(params).write_text(json.dumps({"params": params, "fetched_at": "2026-10-14",
                                                "response": {"documents": [doc("이성당")]}}), "utf-8")
    docs, fetched = client.search("이성당", 126.7, 35.9)
    assert docs[0]["place_name"] == "이성당" and fetched == "2026-10-14" and client.cache_hits == 1
    with pytest.raises(K.KakaoStop):
        client.search("다른 곳", 126.7, 35.9)
    assert all(key not in f.read_text("utf-8") for f in tmp_path.iterdir())
