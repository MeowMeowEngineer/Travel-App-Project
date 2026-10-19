from tools.tourapi_bulk import fill, match, name_key, road_key


def _index(items):
    by_name, by_road = {}, {}
    for it in items:
        by_name.setdefault(name_key(it["title"], "군산"), []).append(it)
        by_road.setdefault(road_key(it["addr1"]), []).append(it)
    return by_name, by_road


def test_bulk_match_rules_and_licensed_photo_only():
    items = [
        {"contentid": "1", "contenttypeid": "12", "title": "동국사(군산)", "addr1": "전북특별자치도 군산시 동국사길 16"},
        {"contentid": "2", "contenttypeid": "32", "title": "게스트하우스 소설여행", "addr1": "군산시 월명로 516-1"},
        {"contentid": "3", "contenttypeid": "32", "title": "히노키잠(1호점)", "addr1": "군산시 구영6길 54-1"},
    ]
    by_name, by_road = _index(items)
    place = lambda name, kind, addr: {"name": name, "kind": kind, "facts": {"address": addr}}
    assert match(place("동국사", "attraction", "군산시 동국사길 16(금광동)"), by_name, by_road, "군산")[1] == "same_name"
    assert match(place("소설여행", "stay", "군산시 월명로 516-1 (신흥동)"), by_name, by_road, "군산")[0]["contentid"] == "2"
    assert match(place("히노키잠 게스트하우스 2호점", "stay", "군산시 구영6길 54-1"), by_name, by_road, "군산")[0] is None
    assert match(place("동국사", "food", "군산시 동국사길 16"), by_name, by_road, "군산")[0] is None  # kind must agree

    p = {"name": "동국사", "images": []}
    fill(p, {**items[0], "mapx": "126.7", "mapy": "35.98", "firstimage": "http://x/a.jpg", "cpyrhtDivCd": "Type3"},
         "same_name", ["KOGL-1", "KOGL-3"])
    assert p["images"][0] == {"url": "https://x/a.jpg", "alt": "동국사", "credit": "한국관광공사",
                              "license": "KOGL-3", "source": "TourAPI"}
    q = {"name": "동국사", "images": []}
    fill(q, {**items[0], "firstimage": "http://x/b.jpg", "cpyrhtDivCd": "Type2"}, "same_name", ["KOGL-1", "KOGL-3"])
    assert q["images"] == []
