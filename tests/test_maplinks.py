"""pipeline/maplinks.py — the Kakao links with and without a matched Kakao place ID (owner decision 2026-10-14)."""
from pipeline import present
from pipeline.maplinks import build_links, kakao_place_url, kakao_route_url, precision_summary


def _by(links):
    return {l["key"]: l for l in links}


def test_kakao_place_id_opens_the_place_page_and_routes_to_the_id():
    by = _by(build_links("이성당", 35.987, 126.711, region="군산", address="군산시 중앙로 177", kakao_place_id="8237245"))
    assert by["kakao"] == {"key": "kakao", "label": "카카오맵", "precise": True, "role": "map",
                           "url": "https://place.map.kakao.com/8237245"}
    assert by["kakao_route"]["url"] == "https://map.kakao.com/link/to/8237245"
    assert by["kakao_route"]["precise"]
    # the other providers keep their coordinate links
    assert by["google_route"]["url"].startswith("https://www.google.com/maps/dir/?api=1&destination=35.987")
    assert by["tmap"]["url"].startswith("tmap://route?")


def test_without_an_id_the_coordinate_links_stay():
    by = _by(build_links("경암동 철길마을", 35.98, 126.72, region="군산"))
    assert by["kakao"]["url"] == "https://map.kakao.com/link/map/%EA%B2%BD%EC%95%94%EB%8F%99%20%EC%B2%A0%EA%B8%B8%EB%A7%88%EC%9D%84,35.98,126.72"
    assert by["kakao_route"]["url"].startswith("https://map.kakao.com/link/to/%EA%B2%BD%EC%95%94")
    assert by["kakao_route"]["url"].endswith(",35.98,126.72")


def test_id_without_coordinates_is_still_precise_with_a_kakao_route_only():
    links = build_links("호텔나운", region="군산", kakao_place_id="12345")
    by = _by(links)
    assert by["kakao"]["url"] == "https://place.map.kakao.com/12345" and by["kakao"]["precise"]
    assert by["kakao"]["label"] == "카카오맵"
    assert by["kakao_route"]["url"] == "https://map.kakao.com/link/to/12345"
    assert "google_route" not in by and "tmap" not in by     # those need coordinates
    assert precision_summary(links) == "some"                 # naver/google stay searches
    # the place page's route row: the filled button is the Kakao route, not '카카오맵에서 찾기'
    rl = present.route_links(links)
    assert rl["primary"]["key"] == "kakao_route" and rl["primary"]["url"].endswith("/link/to/12345")
    assert [l["key"] for l in rl["front"]] == ["naver", "kakao"]


def test_no_id_no_coordinates_is_a_search():
    by = _by(build_links("호텔나운", region="군산"))
    assert by["kakao"]["url"].startswith("https://map.kakao.com/link/search/") and not by["kakao"]["precise"]
    assert "kakao_route" not in by


def test_single_builders():
    assert kakao_place_url("") == "" and kakao_place_url(None) == ""
    assert kakao_place_url(" 42 ") == "https://place.map.kakao.com/42"
    assert kakao_route_url("x", None, None, "") == ""
    assert kakao_route_url("x", 1.5, 2.5, "") == "https://map.kakao.com/link/to/x,1.5,2.5"
    assert kakao_route_url("x", 1.5, 2.5, "42") == "https://map.kakao.com/link/to/42"


def test_course_first_route_uses_the_stop_place_id(monkeypatch):
    monkeypatch.setattr(present, "key_facts", lambda *a, **k: None)
    monkeypatch.setattr(present, "status_items", lambda *a: [])
    monkeypatch.setattr(present, "course_map", lambda stops: None)
    place = {"map_ids": {"kakao_place_id": "99"}, "_photos": [], "_line": "", "_area": "", "_type": ""}
    vm = {"stops": [{"n": 1, "name": "이성당", "short": "이성당", "t": place, "geo": {"lat": 35.9, "lng": 126.7}}]}
    assert present.course_stop_details(vm)["first_route"]["url"] == "https://map.kakao.com/link/to/99"
    place["map_ids"] = {}
    assert present.course_stop_details(vm)["first_route"]["url"] == \
        "https://map.kakao.com/link/to/%EC%9D%B4%EC%84%B1%EB%8B%B9,35.9,126.7"
