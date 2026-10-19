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


class FakeMetroAPI:
    """A TourAPI stand-in for a 광역시 (no network): one 시도 with three 구·군 in its code list — two the Incheon
    site.json lists and one it does not — and clearly fake list items, details and a festival."""

    def __init__(self):
        self.live_calls, self.cache_hits, self.fetched_dates, self.calls = 0, 0, [], []

    def _hit(self, op, *args):
        self.calls.append((op, *args))
        self.live_calls += 1
        self.fetched_dates.append("2026-10-19")

    def ldong_code(self, regn=None, rows=100):
        self._hit("ldong", regn)
        if regn is None:
            return [{"code": "11", "name": "서울특별시"}, {"code": "28", "name": "인천광역시"}]
        return [{"code": "110", "name": "중구"}, {"code": "185", "name": "연수구"}, {"code": "999", "name": "테스트구"}]

    def area_based(self, regn, signgu, ctype, rows=200, page=1):
        self._hit("area", regn, signgu, ctype)
        items = {("110", "12"): [{"contentid": "900001", "contenttypeid": "12", "title": "[테스트] 가상 해변",
                                  "addr1": "인천광역시 중구 테스트로 1 (운서동)", "mapx": "126.5", "mapy": "37.5"}],
                 ("185", "39"): [{"contentid": "900002", "contenttypeid": "39", "title": "[테스트] 가상 식당",
                                  "addr1": "인천광역시 연수구 테스트대로 2", "mapx": "126.6", "mapy": "37.4"}]}
        return items.get((signgu, ctype), [])

    def detail_common(self, cid):
        self._hit("common", cid)
        return {"title": {"900001": "[테스트] 가상 해변", "900002": "[테스트] 가상 식당"}.get(cid, ""), "overview": ""}

    def detail_intro(self, cid, ctype):
        self._hit("intro", cid, ctype)
        return {"usetime": "[테스트] 이용시간"} if ctype == "12" else {}

    def detail_info(self, cid, ctype):
        self._hit("info", cid, ctype)
        return []

    def detail_image(self, cid):
        return []

    def search_festival(self, start, regn=None, signgu=None, rows=100, page=1):
        self._hit("festival", regn, signgu)
        return []


def test_metro_run_loops_every_district_without_places_json(tmp_path, monkeypatch):
    """Before the first collection (no places.json) a 광역시 run reads every 구·군 TourAPI lists under the 시도,
    adds its items as draft places carrying their 구·군, reports a 구·군 site.json does not list, and asks for the
    festivals of the whole 시도 in one call."""
    import json
    import shutil
    from pathlib import Path

    import tools.tourapi_bulk as tb
    data = tmp_path / "data"
    data.mkdir()
    shutil.copy(Path(__file__).resolve().parent.parent / "data" / "incheon" / "site.json", data / "site.json")
    api = FakeMetroAPI()
    monkeypatch.setattr(tb, "from_site_config", lambda *a, **k: api)
    monkeypatch.chdir(tmp_path)   # the run writes reports/tourapi_bulk.md here
    stats = tb.run(data, 900, offline=False, add_new=True, events=True)
    assert stats["districts"] == ["중구", "연수구", "테스트구"]
    assert stats["region_notes"] == ["site.json districts에 없는 구·군(TourAPI): 테스트구"]
    places = json.loads((data / "places.json").read_text("utf-8"))
    assert [(p["name"], p["kind"], p["status"], p.get("district")) for p in places] == [
        ("가상 해변", "attraction", "draft", "중구"), ("가상 식당", "food", "draft", "연수구")]   # '[…]' tags dropped
    assert ("festival", "28", None) in api.calls                               # one call for the whole 시도
    assert {c[2] for c in api.calls if c[0] == "area"} == {"110", "185", "999"}
    only = FakeMetroAPI()
    monkeypatch.setattr(tb, "from_site_config", lambda *a, **k: only)
    (data / "places.json").unlink()
    tb.run(data, 900, offline=False, add_new=True, districts=["연수구"])
    assert {c[2] for c in only.calls if c[0] == "area"} == {"185"}
    assert "테스트구" not in json.dumps(json.loads((data / "places.json").read_text("utf-8")), ensure_ascii=False)


def test_region_without_region_full_stops_with_a_message(tmp_path, monkeypatch, capsys):
    import json

    import tools.tourapi_bulk as tb
    data = tmp_path / "data"
    data.mkdir()
    (data / "site.json").write_text(json.dumps({"region": "테스트"}, ensure_ascii=False), "utf-8")
    monkeypatch.setattr(tb, "from_site_config", lambda *a, **k: FakeMetroAPI())
    monkeypatch.chdir(tmp_path)
    assert tb.main(["--data", str(data)]) == 1
    assert "region_full" in capsys.readouterr().err
