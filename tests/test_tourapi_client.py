"""TourAPI client: URL building, cache, refresh, offline and error handling (network mocked)."""
import io
import json
import urllib.parse
import urllib.error
import traceback
from pathlib import Path

import pytest

from pipeline import tourapi
from pipeline.tourapi import TourAPI, TourAPIError


class FakeResp(io.BytesIO):
    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False


def _ok(items):
    return json.dumps({"response": {"header": {"resultCode": "0000", "resultMsg": "OK"},
                                    "body": {"items": {"item": items}}}}).encode("utf-8")


def test_cache_refresh_offline(tmp_path, monkeypatch):
    seen = []

    def fake_urlopen(req, timeout=20):
        seen.append(req.full_url)
        return FakeResp(_ok([{"contentid": "1", "title": "경암동 철길마을"}]))

    monkeypatch.setattr(tourapi.urllib.request, "urlopen", fake_urlopen)
    api = TourAPI("디코딩키+/=", cache_dir=tmp_path, min_interval=0)
    assert api.search_keyword("경암동 철길마을")[0]["contentid"] == "1"
    assert api.search_keyword("경암동 철길마을")[0]["contentid"] == "1"
    assert api.live_calls == 1 and api.cache_hits == 1

    q = urllib.parse.parse_qs(urllib.parse.urlsplit(seen[0]).query)
    assert seen[0].startswith("https://apis.data.go.kr/B551011/KorService2/searchKeyword2?")
    assert q["serviceKey"] == ["디코딩키+/="] and q["_type"] == ["json"] and q["MobileOS"] == ["ETC"]

    fresh = TourAPI("k", cache_dir=tmp_path, min_interval=0, refresh=True)
    fresh.search_keyword("경암동 철길마을")
    assert fresh.live_calls == 1

    off = TourAPI("k", cache_dir=tmp_path, offline=True)
    assert off.search_keyword("경암동 철길마을")             # served from cache
    with pytest.raises(TourAPIError):
        off.search_keyword("캐시에 없는 검색어")


def test_errors_are_not_cached_and_show_provider_message(tmp_path, monkeypatch):
    bodies = [b"<OpenAPI_ServiceResponse><cmmMsgHeader><returnAuthMsg>SERVICE_KEY_IS_NOT_REGISTERED_ERROR</returnAuthMsg>"
              b"<returnReasonCode>30</returnReasonCode></cmmMsgHeader></OpenAPI_ServiceResponse>",
              json.dumps({"response": {"header": {"resultCode": "22", "resultMsg": "LIMITED_NUMBER_OF_SERVICE_REQUESTS_EXCEEDS_ERROR"}}}).encode()]
    monkeypatch.setattr(tourapi.urllib.request, "urlopen", lambda req, timeout=20: FakeResp(bodies.pop(0)))
    api = TourAPI("k", cache_dir=tmp_path, min_interval=0)
    with pytest.raises(TourAPIError, match="SERVICE_KEY_IS_NOT_REGISTERED_ERROR"):
        api.detail_common("1")
    with pytest.raises(tourapi.TourAPIQuotaError, match="resultCode=22 LIMITED_NUMBER"):
        api.detail_common("1")
    assert not list(tmp_path.glob("*.json"))


def test_missing_key_is_reported(tmp_path):
    with pytest.raises(TourAPIError, match="TOURAPI_KEY"):
        TourAPI("", cache_dir=tmp_path).search_keyword("x")


@pytest.mark.parametrize("given", ["AbC+dEf/GhI=jKl123456789==", "AbC%2BdEf%2FGhI%3DjKl123456789%3D%3D"])
def test_encoding_or_decoding_key_is_encoded_exactly_once(tmp_path, monkeypatch, given):
    seen = []
    monkeypatch.setattr(tourapi.urllib.request, "urlopen",
                        lambda req, timeout=20: seen.append(req.full_url) or FakeResp(_ok([{"contentid": "1"}])))
    TourAPI(given, cache_dir=tmp_path, min_interval=0).detail_common("1")
    assert "serviceKey=AbC%2BdEf%2FGhI%3DjKl123456789%3D%3D&" in seen[0]
    assert "%25" not in seen[0]


def test_per_run_cap_stops_this_client_only_and_leaves_no_ledger(tmp_path, monkeypatch):
    calls = []
    monkeypatch.setattr(tourapi.urllib.request, "urlopen",
                        lambda req, timeout=20: calls.append(1) or FakeResp(_ok([{"contentid": "x"}])))
    api = TourAPI("test-key", cache_dir=tmp_path, min_interval=0, max_calls=2)
    api.detail_common("1")
    api.detail_common("2")
    assert api.detail_common("1")["contentid"] == "x"          # cache hits are free
    with pytest.raises(tourapi.TourAPIStopError, match="2회"):
        api.detail_common("3")
    assert len(calls) == 2
    TourAPI("test-key", cache_dir=tmp_path, min_interval=0, max_calls=2).detail_common("3")  # next run continues
    assert len(calls) == 3
    assert sorted(p.name for p in tmp_path.iterdir() if p.name.startswith(".")) == []
    assert TourAPI("k").max_calls == 900


@pytest.mark.parametrize("kind", ["http_gateway", "network", "non_json", "result_msg"])
def test_errors_show_provider_message_but_mask_every_key_form(tmp_path, monkeypatch, kind):
    key = "SYNTHETIC-secret+/=token"
    encoded = urllib.parse.quote(key, safe="")

    def response(req, timeout):
        echoed = req.full_url + " " + key
        if kind == "http_gateway":
            payload = {"OpenAPI_ServiceResponse": {"cmmMsgHeader": {
                "errMsg": "SERVICE ERROR", "returnAuthMsg": "INVALID_REQUEST_PARAMETER_ERROR " + echoed,
                "returnReasonCode": "10"}}}
            raise urllib.error.HTTPError(req.full_url, 400, echoed, {}, io.BytesIO(json.dumps(payload).encode()))
        if kind == "network":
            raise urllib.error.URLError(echoed)
        if kind == "non_json":
            return FakeResp(echoed.encode())
        return FakeResp(json.dumps({"response": {"header": {"resultCode": "30", "resultMsg": "NOT_REGISTERED " + echoed}}}).encode())

    monkeypatch.setattr(tourapi.urllib.request, "urlopen", response)
    api = TourAPI(encoded, cache_dir=tmp_path, min_interval=0)
    with pytest.raises(TourAPIError) as caught:
        api.detail_common("1")
    message = str(caught.value)
    assert key not in message and encoded not in message and "«KEY»" in message
    if kind == "http_gateway":
        assert "HTTP 400" in message and "resultCode=10" in message and "INVALID_REQUEST_PARAMETER_ERROR" in message
    if kind == "result_msg":
        assert "NOT_REGISTERED" in message


def test_cache_hits_do_not_count_against_the_cap(tmp_path, monkeypatch):
    monkeypatch.setattr(tourapi.urllib.request, "urlopen", lambda req, timeout: FakeResp(_ok([{"contentid": "1"}])))
    api = TourAPI("test-key", cache_dir=tmp_path, min_interval=0, max_calls=1)
    api.detail_common("1")
    assert api.detail_common("1")["contentid"] == "1"
    assert api.live_calls == 1 and api.cache_hits == 1


def test_new_operations_use_kor_service2_names(tmp_path, monkeypatch):
    calls = []
    monkeypatch.setattr(tourapi.urllib.request, "urlopen",
                        lambda req, timeout=20: calls.append(req.full_url) or FakeResp(_ok([{"code": "1"}])))
    api = TourAPI("k-123456", cache_dir=tmp_path, min_interval=0)
    api.ldong_code("52")
    api.search_festival("20261001", "52", "130")
    api.detail_image("1")
    paths = [urllib.parse.urlsplit(u).path.rsplit("/", 1)[1] for u in calls]
    assert paths == ["ldongCode2", "searchFestival2", "detailImage2"]
    assert urllib.parse.parse_qs(urllib.parse.urlsplit(calls[1]).query)["eventStartDate"] == ["20261001"]
    with pytest.raises(ValueError):
        api.search_festival("2026-10-01")


def test_area_based_uses_inspected_modern_region_parameters_and_documented_sort(tmp_path, monkeypatch):
    calls = []

    def response(req, timeout):
        calls.append(req.full_url)
        return FakeResp(_ok([{"contentid": "area-result", "contenttypeid": "32"}]))

    monkeypatch.setattr(tourapi.urllib.request, "urlopen", response)
    api = TourAPI("synthetic-key", cache_dir=tmp_path, min_interval=0)
    result = api.area_based("51", "130", content_type_id="32", rows=25, page=2, arrange="Q")
    assert result[0]["contentid"] == "area-result"
    url = urllib.parse.urlsplit(calls[0])
    assert url.path.endswith("/areaBasedList2")
    query = urllib.parse.parse_qs(url.query)
    assert query["lDongRegnCd"] == ["51"] and query["lDongSignguCd"] == ["130"]
    assert query["contentTypeId"] == ["32"] and query["numOfRows"] == ["25"]
    assert query["pageNo"] == ["2"] and query["arrange"] == ["Q"]
    assert "areaCode" not in query and "sigunguCode" not in query


@pytest.mark.parametrize("params", [
    {"l_dong_signgu_cd": "130"}, {"l_dong_regn_cd": "군산"}, {"l_dong_regn_cd": ""},
    {"l_dong_regn_cd": "51", "l_dong_signgu_cd": "-1"}, {"content_type_id": "999"},
    {"rows": 0}, {"rows": True}, {"rows": 1.5}, {"page": 0}, {"page": "2"}, {"arrange": "E"},
])
def test_area_based_rejects_invalid_parameters_before_network(tmp_path, monkeypatch, params):
    monkeypatch.setattr(tourapi.urllib.request, "urlopen", lambda *a, **k: pytest.fail("network prohibited"))
    api = TourAPI("synthetic-key", cache_dir=tmp_path)
    with pytest.raises(ValueError):
        api.area_based(**params)
    assert api.live_calls == 0


def test_barrier_free_client_calls_korwith_service2_and_keeps_its_own_cache(tmp_path, monkeypatch):
    """한국관광공사 무장애 여행 정보 (KorWithService2): detailWithTour2 on its own base_url and cache folder; the
    KorService2 client and its cache stay as they are (QA 2026-10-15, F02-barrier-free-systemic)."""
    fixture = json.loads((Path(__file__).parent / "fixtures" / "detailWithTour2_documented_shape.json").read_text("utf-8"))
    calls = []

    def response(req, timeout=20):
        calls.append(req.full_url)
        return FakeResp(json.dumps(fixture).encode("utf-8"))

    monkeypatch.setattr(tourapi.urllib.request, "urlopen", response)
    site = {"tourapi": {"base_url": "https://apis.data.go.kr/B551011/KorService2", "min_interval": 0}}
    bf = tourapi.barrier_free_client(site, "synthetic-key", tmp_path)
    item = bf.detail_with_tour("988449")
    assert item["wheelchair"] == "대여가능(수동휠체어 2대)" and item["parking"].endswith("_무장애 편의시설")
    url = urllib.parse.urlsplit(calls[0])
    assert url.netloc == "apis.data.go.kr" and url.path == "/B551011/KorWithService2/detailWithTour2"
    assert urllib.parse.parse_qs(url.query)["contentId"] == ["988449"]
    cached = list((tmp_path / tourapi.BARRIER_FREE_CACHE).glob("detailWithTour-*.json"))
    assert len(cached) == 1 and not list(tmp_path.glob("*.json"))      # not in the KorService2 folder
    assert bf.detail_with_tour("988449") == item and bf.live_calls == 1  # served from its own cache
    kor = tourapi.from_site_config(site, "synthetic-key", tmp_path)
    assert kor.base_url.endswith("/KorService2") and kor.cache_dir == tmp_path
    assert tourapi.barrier_free_client({"tourapi": {"barrier_free_base_url": "https://example.test/KWS2/"}},
                                       "k", tmp_path).base_url == "https://example.test/KWS2"
    empty = TourAPI("k", cache_dir=tmp_path / "e", min_interval=0)
    monkeypatch.setattr(tourapi.urllib.request, "urlopen", lambda req, timeout=20: FakeResp(_ok([])))
    assert empty.detail_with_tour("1") == {}
