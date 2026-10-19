"""Enrichment logic with a fake TourAPI (no network)."""
import json
from copy import deepcopy

import pytest

from pipeline.enrich import fill_entity, match_entity, score_candidate
from pipeline import enrich
from pipeline.tourapi import TourAPIQuotaError


class FakeAPI:
    live_calls = 0
    cache_hits = 0

    def search_keyword(self, keyword, content_type_id=None, rows=20):
        return [
            {"contentid": "111", "contenttypeid": "12", "title": "경암동 철길마을", "addr1": "전북특별자치도 군산시 경촌4길 14",
             "mapx": "126.72", "mapy": "35.98"},
            {"contentid": "999", "contenttypeid": "12", "title": "철길마을", "addr1": "서울특별시 어딘가"},
        ]

    def detail_common(self, cid):
        return {"contentid": cid, "contenttypeid": "12", "title": "경암동 철길마을", "addr1": "전북특별자치도 군산시 경촌4길 14",
                "mapx": "126.72", "mapy": "35.98", "tel": "063-000-0000", "homepage": '<a href="https://example.org">x</a>',
                "overview": "개요<br>두 줄", "firstimage": "https://img/1.jpg", "cpyrhtDivCd": "Type1"}

    def detail_intro(self, cid, ctype):
        return {"usetime": "상시 개방", "parking": "인근 공영주차장<br>(유료)", "chkbabycarriage": "없음"}

    def detail_info(self, cid, ctype):
        return [{"infoname": "입 장 료", "infotext": "무료"}]

    def location_based(self, lat, lng, radius=2000, content_type_id=None, rows=40):
        return [
            {"contentid": "111", "contenttypeid": "12", "title": "경암동 철길마을", "dist": "0"},
            {"contentid": "222", "contenttypeid": "12", "title": "초원사진관", "dist": "850.5"},
            {"contentid": "333", "contenttypeid": "32", "title": "숙소 A", "dist": "400"},
            {"contentid": "444", "contenttypeid": "39", "title": "식당 A", "dist": "120"},
            {"contentid": "555", "contenttypeid": "25", "title": "코스(제외 대상)", "dist": "10"},
        ]


def test_score_prefers_region_and_exact_name():
    a = score_candidate("경암동 철길마을", {"title": "군산 경암동 철길마을", "addr1": "전북 군산시"}, "군산")
    b = score_candidate("경암동 철길마을", {"title": "경암동 철길마을", "addr1": "서울"}, "군산")
    assert a >= 0.85 > b


def test_match_and_fill():
    api = FakeAPI()
    e = {"id": "g-1", "name": "경암동 철길마을", "slug": "경암동-철길마을", "kind": "attraction"}
    best, score, _ = match_entity(api, e, "군산")
    assert best["contentid"] == "111" and score >= 0.75
    e["tourapi"] = {"contentid": "111", "contenttypeid": "12"}
    other = {"id": "g-2", "name": "초원사진관", "slug": "초원사진관", "tourapi": {"contentid": "222"}}
    site = {"tourapi": {"nearby_radius_m": 2000, "nearby_per_kind": 3}, "publish_rules": {}}
    fill_entity(api, e, site, {"222": other, "111": e}, "2026-10-12")
    f = e["facts"]
    assert f["usetime"] == "상시 개방" and f["usefee"] == "무료" and f["parking"] == "인근 공영주차장\n(유료)"
    assert f["babycarriage"] == "없음" and f["homepage"] == "https://example.org" and f["infocenter"] == "063-000-0000"
    assert e["geo"] == {"lat": 35.98, "lng": 126.72, "source": "TourAPI"}
    assert e["images"][0]["license"] == "KOGL-1"
    kinds = [(n["name"], n["kind"]) for n in e["nearby"]]
    assert kinds == [("초원사진관", "attraction"), ("숙소 A", "stay"), ("식당 A", "food")]
    assert e["nearby"][0]["internal_slug"] == "초원사진관" and e["nearby"][0]["distance_m"] == 850
    assert e["facts_source"]["checked_at"] == "2026-10-12"


def test_locks_are_respected():
    api = FakeAPI()
    e = {"id": "g-1", "name": "경암동 철길마을", "kind": "attraction", "locks": ["facts", "geo"],
         "facts": {"usetime": "수동 확인값"}, "geo": {"lat": 1.0, "lng": 2.0, "source": "manual"},
         "tourapi": {"contentid": "111", "contenttypeid": "12"}}
    fill_entity(api, e, {"tourapi": {}, "publish_rules": {}}, {}, "2026-10-12")
    assert e["facts"] == {"usetime": "수동 확인값"} and e["geo"]["source"] == "manual"


def test_disallowed_image_licence_is_dropped():
    class Type4(FakeAPI):
        def detail_common(self, cid):
            d = super().detail_common(cid)
            d["cpyrhtDivCd"] = "Type4"
            return d
    e = {"id": "g-1", "name": "경암동 철길마을", "kind": "attraction", "tourapi": {"contentid": "111", "contenttypeid": "12"}}
    fill_entity(Type4(), e, {"tourapi": {}, "publish_rules": {}}, {}, "2026-10-12")
    assert e["images"] == []


@pytest.mark.parametrize("phase", ["match", "detail", "events"])
def test_quota_stop_prevents_later_entities_and_events_and_restores_partial_fill(tmp_path, monkeypatch, phase):
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("TOURAPI_KEY", "synthetic-test-key")
    data = tmp_path / "data"
    data.mkdir()
    entities = [{"id": f"g-{i}", "name": "경암동 철길마을", "kind": "attraction",
                 "facts": {"address": "기존 주소"}, "original": {"text": "보존 원문"}}
                for i in range(2)]
    if phase != "match":
        for entity in entities:
            entity["tourapi"] = {"contentid": "111", "contenttypeid": "12"}
    before = deepcopy(entities)
    (data / "places.json").write_text(json.dumps(entities))
    (data / "site.json").write_text(json.dumps({"region": "군산", "center": {"lat": 35.9, "lng": 126.7}}))
    (data / "events.json").write_bytes(b"[]")

    class StoppingAPI(FakeAPI):
        def __init__(self):
            self.calls = []

        def search_keyword(self, *args, **kwargs):
            self.calls.append("match")
            raise TourAPIQuotaError("resultCode=22; quota stop")

        def detail_common(self, cid):
            self.calls.append("common")
            return super().detail_common(cid)

        def detail_intro(self, cid, ctype):
            self.calls.append("intro")
            if phase == "detail":
                raise TourAPIQuotaError("resultCode=22; quota stop")
            return super().detail_intro(cid, ctype)

        def location_based(self, *args, **kwargs):
            if kwargs.get("content_type_id") == "15":
                self.calls.append("events")
                raise TourAPIQuotaError("resultCode=22; quota stop")
            return super().location_based(*args, **kwargs)

    api = StoppingAPI()
    monkeypatch.setattr(enrich, "from_site_config", lambda *args, **kwargs: api)
    result = enrich.run(data, events=True)
    assert result["stopped"] and result["failed"] == 1
    saved = json.loads((data / "places.json").read_text("utf-8"))
    assert (data / "events.json").read_bytes() == b"[]"
    if phase == "match":
        assert api.calls == ["match"]
        assert saved[1] == before[1]
    elif phase == "detail":
        assert api.calls == ["common", "intro"]
        assert saved == before  # No half-filled geo/facts or later entity mutations.
    else:
        assert api.calls[-1] == "events"
    report = (tmp_path / "reports" / "enrich_report.md").read_text("utf-8")
    assert "호출 중단" in report and "synthetic-test-key" not in report
