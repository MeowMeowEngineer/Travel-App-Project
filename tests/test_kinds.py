"""카페·디저트 and 쇼핑 (operator decision 2026-10-19): two kinds besides 관광지·숙소·음식점. A place is 카페·디저트 when
TourAPI's new classification (lclsSystm3) starts with FD05 (카페/찻집) or is FD030100 (제과) — the old cat3 A05020900
(카페/전통찻집) counts only when the new classification is missing; a TourAPI type-38 place is 쇼핑. The collection
keeps each item's classification codes (lclsSystm1·2·3, cat1·2·3) on the place and the kind follows them on every run
(tools/tourapi_bulk.reclassify, a locked kind stays). The build gives both kinds their list (/cafes/, /shopping/), the
café list a menu item and a home tile, the search groups, the assistant's catalog a section each and the map its
toggles. All names, codes and values here are clearly fake."""
import json
import shutil
from pathlib import Path

from pipeline.build import build
from pipeline.schema import KIND_LABELS, base_kind, schema_type
from pipeline.tourapi import is_cafe_class, kind_of

ROOT = Path(__file__).resolve().parent.parent
INCHEON = ROOT / "data" / "incheon"
TINY = Path(__file__).resolve().parent / "fixtures" / "incheon_tiny"
RECORDS = ("places.json", "events.json", "courses.json", "guides.json", "themes.json", "videos.json")


def test_the_cafe_rule_on_tourapi_classification_codes():
    item = lambda **kw: {"contenttypeid": "39", **kw}
    assert kind_of(item(lclsSystm3="FD050100")) == "cafe"            # 카페/찻집 (카페·찻집·기타음료점)
    assert kind_of(item(lclsSystm3="FD050300")) == "cafe"
    assert kind_of(item(lclsSystm3="FD030100")) == "cafe"            # 제과
    assert kind_of(item(lclsSystm3="FD030200")) == "food"            # another 간이음식 class is a restaurant
    assert kind_of(item(lclsSystm3="FD010100")) == "food"
    assert kind_of(item(cat3="A05020900")) == "cafe"                 # old class, no new one: counts
    assert kind_of(item(lclsSystm3="FD010100", cat3="A05020900")) == "food"   # the new class decides when present
    assert kind_of(item(cat3="A05020100")) == "food"
    assert kind_of(item(lcls="FD050100")) == "cafe"                  # a record collected before 2026-10-19 ('lcls')
    assert kind_of({"contenttypeid": "38"}) == "shopping" and kind_of({"contenttypeid": "12"}) == "attraction"
    assert kind_of({"contenttypeid": "32"}) == "stay" and kind_of({"contenttypeid": "15"}) == ""
    assert not is_cafe_class("", "") and is_cafe_class("FD05", "")
    # the two kinds read like food and a place to visit; their labels and structured-data types
    assert (base_kind("cafe"), base_kind("shopping"), base_kind("stay")) == ("food", "attraction", "stay")
    assert (KIND_LABELS["cafe"], KIND_LABELS["shopping"]) == ("카페·디저트", "쇼핑")
    assert schema_type({"kind": "cafe", "tourapi": {"lclsSystm3": "FD050100"}}) == "CafeOrCoffeeShop"
    assert schema_type({"kind": "cafe", "tourapi": {"lclsSystm3": "FD030100"}}) == "Bakery"
    assert schema_type({"kind": "shopping", "category": "쇼핑"}) == "Store"


class FakeAPI:
    """A 광역시 with one 구·군 and its 음식점 / 쇼핑 lists: a café, a bakery, a restaurant, an old-classed tea house and a
    market. `cafe_class` is what the list says of the café's code."""

    def __init__(self, cafe_class="FD050100"):
        self.live_calls, self.cache_hits, self.fetched_dates, self.cafe_class = 0, 0, [], cafe_class

    def _hit(self):
        self.live_calls += 1
        self.fetched_dates.append("2026-10-19")

    def ldong_code(self, regn=None, rows=100):
        self._hit()
        return [{"code": "28", "name": "인천광역시"}] if regn is None else [{"code": "185", "name": "연수구"}]

    def area_based(self, regn, signgu, ctype, rows=200, page=1):
        self._hit()
        base = {"addr1": "인천광역시 연수구 테스트대로 1", "mapx": "126.6", "mapy": "37.4"}
        items = {
            "39": [{**base, "contentid": "910001", "contenttypeid": "39", "title": "[테스트] 가상 카페",
                    "lclsSystm1": "FD", "lclsSystm2": "FD05", "lclsSystm3": self.cafe_class,
                    "cat1": "A05", "cat2": "A0502", "cat3": "A05020900"},
                   {**base, "contentid": "910002", "contenttypeid": "39", "title": "[테스트] 가상 제과점",
                    "lclsSystm1": "FD", "lclsSystm2": "FD03", "lclsSystm3": "FD030100"},
                   {**base, "contentid": "910003", "contenttypeid": "39", "title": "[테스트] 가상 식당",
                    "lclsSystm1": "FD", "lclsSystm2": "FD01", "lclsSystm3": "FD010100", "cat3": "A05020100"},
                   {**base, "contentid": "910004", "contenttypeid": "39", "title": "[테스트] 가상 찻집",
                    "cat1": "A05", "cat2": "A0502", "cat3": "A05020900"}],
            "38": [{**base, "contentid": "910005", "contenttypeid": "38", "title": "[테스트] 가상 시장",
                    "lclsSystm1": "SH", "lclsSystm2": "SH06", "lclsSystm3": "SH060100"}]}
        return items.get(ctype, [])

    def detail_common(self, cid):
        self._hit()
        return {"overview": ""}

    def detail_intro(self, cid, ctype):
        self._hit()
        return {}

    def detail_info(self, cid, ctype):
        self._hit()
        return []

    def detail_image(self, cid):
        return []

    def search_festival(self, start, regn=None, signgu=None, rows=100, page=1):
        return []


def _run(tmp_path, monkeypatch, api):
    import tools.tourapi_bulk as tb
    monkeypatch.setattr(tb, "from_site_config", lambda *a, **k: api)
    monkeypatch.chdir(tmp_path)   # the run writes reports/tourapi_bulk.md here
    return tb.run(tmp_path / "data", 900, offline=False, add_new=True)


def test_the_collection_keeps_the_codes_and_the_kind_follows_them(tmp_path, monkeypatch):
    data = tmp_path / "data"
    data.mkdir()
    shutil.copy(INCHEON / "site.json", data / "site.json")
    _run(tmp_path, monkeypatch, FakeAPI())
    places = {p["tourapi"]["contentid"]: p for p in json.loads((data / "places.json").read_text("utf-8"))}
    kinds = {cid: (p["kind"], p["category"]) for cid, p in places.items()}
    assert kinds == {"910001": ("cafe", "카페·디저트"), "910002": ("cafe", "카페·디저트"), "910003": ("food", "음식점"),
                     "910004": ("cafe", "카페·디저트"), "910005": ("shopping", "쇼핑")}
    cafe = places["910001"]["tourapi"]
    assert {k: cafe.get(k) for k in ("lclsSystm1", "lclsSystm2", "lclsSystm3", "cat1", "cat2", "cat3")} == {
        "lclsSystm1": "FD", "lclsSystm2": "FD05", "lclsSystm3": "FD050100", "cat1": "A05", "cat2": "A0502",
        "cat3": "A05020900"}
    assert "lcls" not in cafe
    assert places["910004"]["tourapi"]["cat3"] == "A05020900" and "lclsSystm3" not in places["910004"]["tourapi"]

    # a record collected before the codes were kept ('lcls' only) gets them on the next run, and its kind follows
    # TourAPI's class when that changes (food ↔ café); a locked kind stays as the person set it
    rows = json.loads((data / "places.json").read_text("utf-8"))
    for p in rows:
        t = p["tourapi"]
        if t["contentid"] == "910003":                       # TourAPI now files the restaurant as a café
            p["tourapi"] = {k: v for k, v in t.items() if not k.startswith(("lclsSystm", "cat"))} | {"lcls": "FD010100"}
        if t["contentid"] == "910002":
            p["locks"] = ["kind"]
            p["kind"] = "food"
    (data / "places.json").write_text(json.dumps(rows, ensure_ascii=False), "utf-8")

    class Later(FakeAPI):
        def area_based(self, regn, signgu, ctype, rows=200, page=1):
            out = super().area_based(regn, signgu, ctype, rows, page)
            for it in out:
                if it["contentid"] == "910003":
                    it.update(lclsSystm2="FD05", lclsSystm3="FD050200")
            return out

    stats = _run(tmp_path, monkeypatch, Later())
    places = {p["tourapi"]["contentid"]: p for p in json.loads((data / "places.json").read_text("utf-8"))}
    assert (places["910003"]["kind"], places["910003"]["category"]) == ("cafe", "카페·디저트")
    assert places["910003"]["tourapi"]["lclsSystm3"] == "FD050200" and "lcls" not in places["910003"]["tourapi"]
    assert places["910002"]["kind"] == "food"                  # locked
    assert stats["reclassified"] == ["가상 식당: 음식점 → 카페·디저트"]


def test_a_food_record_matches_its_tourapi_cafe_and_becomes_one(tmp_path, monkeypatch):
    """A record from another source (not TourAPI-only) is matched to TourAPI's café item although it was filed as
    음식점, and takes the 카페·디저트 kind from TourAPI's class; its own category stays."""
    data = tmp_path / "data"
    data.mkdir()
    shutil.copy(INCHEON / "site.json", data / "site.json")
    ours = {"id": "test-x", "slug": "x", "name": "[테스트] 가상 카페", "kind": "food", "category": "음식점",
            "status": "draft", "tier": "basic", "facts": {"address": "인천광역시 연수구 테스트대로 1"}, "images": []}
    (data / "places.json").write_text(json.dumps([ours], ensure_ascii=False), "utf-8")
    _run(tmp_path, monkeypatch, FakeAPI())
    mine = next(p for p in json.loads((data / "places.json").read_text("utf-8")) if p["id"] == "test-x")
    assert mine["tourapi"]["contentid"] == "910001" and mine["kind"] == "cafe" and mine["category"] == "음식점"


def test_the_build_gives_cafes_and_shops_their_lists(tmp_path):
    data = tmp_path / "data"
    data.mkdir()
    for f in INCHEON.glob("*.json"):
        if f.name not in RECORDS:
            shutil.copy(f, data / f.name)
    for f in TINY.glob("*.json"):
        shutil.copy(f, data / f.name)
    out = tmp_path / "out"
    build(data, out, "preview")
    home = (out / "index.html").read_text("utf-8")
    cafes = (out / "cafes" / "index.html").read_text("utf-8")
    shops = (out / "shopping" / "index.html").read_text("utf-8")
    # the list pages: their own heads, the place they hold, the menu item marked on the café list
    assert "카페·디저트</span>" in cafes and "[테스트] 가상 카페 F" in cafes and "[테스트] 가상 식당 B" not in cafes
    assert "[테스트] 가상 상점 G" in shops and "[테스트] 가상 카페 F" not in shops
    assert '<li><a href="/cafes/" aria-current="page">카페·디저트</a></li>' in cafes
    assert '<li><a href="/cafes/">카페·디저트</a></li>' in home and 'href="/shopping/"' in home   # menu item, home tile
    food = (out / "food" / "index.html").read_text("utf-8")
    assert "[테스트] 가상 카페 F" not in food                                       # apart from 음식점
    # the place pages read like food and a shop: 영업시간·대표 메뉴, no 요금 slot for the shop; their kickers lead to the lists
    cafe = (out / "places" / "test-cafe-f" / "index.html").read_text("utf-8")
    assert 'href="/cafes/"' in cafe and "대표 메뉴" in cafe and '"@type":"CafeOrCoffeeShop"' in cafe.replace(" ", "")
    shop = (out / "places" / "test-shop-g" / "index.html").read_text("utf-8")
    assert '"@type":"Store"' in shop.replace(" ", "") and "확인 필요: 요금" not in shop
    # the search index groups, the assistant's catalog, the map's toggles
    index = {r["n"]: r for r in json.loads((out / "search" / "index.json").read_text("utf-8"))}
    assert (index["[테스트] 가상 카페 F"]["k"], index["[테스트] 가상 카페 F"]["t"]) == ("cafe", "카페·디저트")
    assert index["[테스트] 가상 상점 G"]["k"] == "shopping"
    catalog = (out / "chat" / "catalog.txt").read_text("utf-8")
    assert "## 카페·디저트 1곳 — 목록 /cafes/" in catalog and "## 쇼핑 1곳 — 목록 /shopping/" in catalog
    docs = json.loads((out / "chat" / "docs.json").read_text("utf-8"))["docs"]
    assert docs["/places/test-cafe-f/"]["f"]["kd"] == "food" and docs["/places/test-cafe-f/"]["f"]["kc"] == "cafe"
    assert docs["/places/test-shop-g/"]["f"]["kd"] == "attraction" and docs["/places/test-shop-g/"]["f"]["kc"] == "shopping"
    page = (out / "map" / "index.html").read_text("utf-8")
    assert 'data-kind="cafe"' in page and 'data-kind="shopping"' in page and 'class="mk mk-c"' in page
