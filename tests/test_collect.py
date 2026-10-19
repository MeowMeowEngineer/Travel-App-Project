"""tools/collect.py — the one command that turns a TourAPI key into data/<city>/*.json, run against a fake TourAPI.

No network and no real key: urllib.request.urlopen is replaced by a router that answers like KorService2 for a
made-up 인천광역시 with two 구 and one 군. Every name, code, phone number, address, coordinate and date below is
invented test data (codes 98/901-903 are not real statutory codes); none of it is Incheon content and none of it is
written under data/incheon.
"""
import datetime as dt
import io
import json
import re
import shutil
import urllib.parse
from pathlib import Path

import pytest

from pipeline.build import build
from pipeline.validate import validate
from tools import collect
from tools import image_sizes
from tools import tourapi_doctor as doctor

ROOT = Path(__file__).resolve().parent.parent
# the files a collection or a writer adds to data/incheon (TourAPI writes places·events): left out of a copy that
# stands for this site's configuration before collection
RECORDS = ("places.json", "events.json", "courses.json", "guides.json", "themes.json", "videos.json", "image_sizes.json")
FAKE_KEY = "TEST-ONLY-fake+key/=0123456789"          # not a real key; has + / = so its encoded forms differ
TODAY = dt.date.today()
D = lambda days: (TODAY + dt.timedelta(days=days)).strftime("%Y%m%d")
SENTINEL = "OVERVIEW-SENTINEL 시험용 개요 문장"           # overview text: must never reach a built page
IMG = "http://tong.visitkorea.or.kr/cms/resource/test/{}.jpg"

SIDO = [{"rnum": 1, "code": "97", "name": "서울특별시"}, {"rnum": 2, "code": "98", "name": "인천광역시"}]
SIGNGU = [{"rnum": 1, "code": "901", "name": "연수구"}, {"rnum": 2, "code": "902", "name": "미추홀구"},
          {"rnum": 3, "code": "903", "name": "강화군"}]


def _item(cid, ctype, title, addr, lng, lat, image_type=None):
    it = {"contentid": cid, "contenttypeid": ctype, "title": title, "addr1": addr, "addr2": "",
          "mapx": str(lng), "mapy": str(lat), "modifiedtime": "20261001000000", "lclsSystm3": ""}
    if image_type:
        it.update(firstimage=IMG.format(cid), cpyrhtDivCd=image_type)
    return it


LISTS = {   # (lDongSignguCd, contentTypeId) -> items
    ("901", "12"): [_item("990001", "12", "[시험] 가상 공원", "인천광역시 연수구 시험공원로 1", 126.651, 37.401, "Type1")],
    ("901", "39"): [_item("990002", "39", "[시험] 가상 식당", "인천광역시 연수구 시험맛길 2", 126.652, 37.402, "Type2")],
    ("902", "32"): [_item("990003", "32", "[시험] 가상 호텔", "인천광역시 미추홀구 시험숙박로 3", 126.661, 37.451, "Type4")],
    ("902", "14"): [_item("990004", "14", "[시험] 가상 미술관", "인천광역시 미추홀구 시험문화로 4", 126.662, 37.452, "Type3")],
    ("903", "12"): [_item("990005", "12", "[시험] 가상 전망대", "인천광역시 강화군 강화읍 시험산길 5", 126.481, 37.741)],
}
INTRO = {
    "990001": {"usetime": "09:00~18:00", "restdate": "매주 월요일", "parking": "가능(시험 값)", "infocenter": "032-000-0001"},
    "990002": {"opentimefood": "11:00~21:00", "restdatefood": "연중무휴", "firstmenu": "시험국수",
               "parkingfood": "불가", "infocenterfood": "032-000-0002"},
    "990003": {"checkintime": "15:00", "checkouttime": "11:00", "parkinglodging": "가능", "roomcount": "10",
               "infocenterlodging": "032-000-0003"},
    "990004": {"usetimeculture": "10:00~17:00", "restdateculture": "매주 화요일", "usefee": "무료",
               "parkingculture": "가능", "infocenterculture": "032-000-0004"},
    "990005": {"usetime": "상시 개방", "parking": "없음"},
    "990101": {"eventstartdate": D(10), "eventenddate": D(12), "eventplace": "시험 광장", "playtime": "10:00~18:00",
               "usetimefestival": "무료", "sponsor1": "시험 주최", "sponsor1tel": "032-000-0101"},
}
INFO = {"990001": [{"infoname": "입장료", "infotext": "무료(시험 값)"}], "990005": []}
FESTIVALS = [{**_item("990101", "15", "[시험] 가상 축제", "인천광역시 강화군 강화읍 시험광장로 1", 126.482, 37.742, "Type1"),
              "eventstartdate": D(10), "eventenddate": D(12)}]


def _ok(items, total=None):
    items = list(items)
    return json.dumps({"response": {"header": {"resultCode": "0000", "resultMsg": "OK"},
                                    "body": {"items": {"item": items} if items else "", "numOfRows": len(items),
                                             "pageNo": 1, "totalCount": len(items) if total is None else total}}},
                      ensure_ascii=False).encode("utf-8")


class Resp(io.BytesIO):
    status = 200
    headers = {"Content-Type": "application/json"}

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False


class FakeTourAPI:
    """Answers KorService2 requests from the tables above; `fail` maps an operation to an error body."""

    def __init__(self, fail: dict | None = None):
        self.calls: list[tuple[str, dict]] = []
        self.fail = fail or {}

    def __call__(self, req, timeout=None):
        url = req.full_url if hasattr(req, "full_url") else str(req)
        parts = urllib.parse.urlsplit(url)
        op = parts.path.rsplit("/", 1)[-1]
        q = {k: v[0] for k, v in urllib.parse.parse_qs(parts.query).items()}
        assert q.get("serviceKey") == FAKE_KEY            # the key arrives decoded once, intact
        self.calls.append((op, q))
        if op in self.fail:
            return Resp(self.fail[op].replace("{KEY}", q["serviceKey"]).encode("utf-8"))
        base = op.rstrip("0123456789")
        if base == "searchKeyword":
            return Resp(_ok([LISTS[("901", "12")][0]]))
        if base == "ldongCode":
            return Resp(_ok(SIGNGU if q.get("lDongRegnCd") == "98" else SIDO if "lDongRegnCd" not in q else []))
        if base == "areaCode":
            return Resp(_ok([{"code": "1", "name": "강화군"}] if q.get("areaCode") == "91" else
                            [{"code": "90", "name": "서울"}, {"code": "91", "name": "인천"}]))
        if base == "areaBasedList":
            assert q["lDongRegnCd"] == "98"
            return Resp(_ok(LISTS.get((q["lDongSignguCd"], q["contentTypeId"]), [])))
        if base == "searchFestival":
            assert q["lDongRegnCd"] == "98" and "lDongSignguCd" not in q
            return Resp(_ok(FESTIVALS))
        cid = q.get("contentId", "")
        if base == "detailCommon":
            item = next((i for i in [*sum(LISTS.values(), []), *FESTIVALS] if i["contentid"] == cid), None)
            return Resp(_ok([{**item, "tel": "", "overview": f"{SENTINEL} {cid}입니다."}] if item else []))
        if base == "detailIntro":
            return Resp(_ok([{"contentid": cid, "contenttypeid": q["contentTypeId"], **INTRO.get(cid, {})}]))
        if base == "detailInfo":
            return Resp(_ok(INFO.get(cid, [])))
        raise AssertionError(f"unexpected TourAPI call {op}")

    def ops(self):
        return [op for op, _ in self.calls]


@pytest.fixture
def region(tmp_path, monkeypatch):
    """A copy of the Incheon config in a scratch folder (no places yet), the working directory there (no .env, the
    reports go there), no key in the environment, no pause between calls, the network check stubbed."""
    data = tmp_path / "data" / "incheon"
    data.mkdir(parents=True)
    for f in (ROOT / "data" / "incheon").glob("*.json"):
        if f.name not in RECORDS:
            shutil.copy(f, data / f.name)
    site = json.loads((data / "site.json").read_text("utf-8"))
    site["tourapi"]["min_interval"] = 0
    (data / "site.json").write_text(json.dumps(site, ensure_ascii=False, indent=1), "utf-8")
    monkeypatch.chdir(tmp_path)
    monkeypatch.delenv("TOURAPI_KEY", raising=False)
    monkeypatch.setattr(doctor, "tcp_check", lambda *a, **k: (True, "시험"))
    # the photo-size step reads the photo hosts, not TourAPI: answered here (an original 940×627, no small rendition)
    monkeypatch.setattr(image_sizes, "probe", lambda url: (url, None, "HTTPError: 404") if "_image3_1" in url
                        else (url, [940, 627, 100000], ""))
    return data


def _run(argv, capsys):
    code = collect.main(argv)
    out = capsys.readouterr()
    return code, out.out, out.err


def test_without_a_key_it_stops_at_once_and_says_where_to_put_it(region, monkeypatch, capsys):
    monkeypatch.setattr("urllib.request.urlopen", lambda *a, **k: pytest.fail("no call without a key"))
    code, out, err = _run(["--data", str(region)], capsys)
    assert code == 2
    assert "TOURAPI_KEY가 없습니다" in err and "환경 변수" in err and ".env" in err and "export TOURAPI_KEY=" in err
    assert "Traceback" not in out + err
    assert not (region / "places.json").exists() and not (region.parent.parent / "reports").exists()


def test_fake_incheon_collection_writes_sourced_data_and_builds(region, monkeypatch, capsys, tmp_path):
    api = FakeTourAPI()
    monkeypatch.setattr("urllib.request.urlopen", api)
    monkeypatch.setenv("TOURAPI_KEY", FAKE_KEY)
    code, out, err = _run(["--data", "data/incheon"], capsys)
    assert code == 0, err
    # the doctor read the codes from the provider and printed them; the collection used the same list
    assert "법정동 시도 코드(lDongRegnCd) 98" in out and "901 연수구 · 902 미추홀구 · 903 강화군" in out
    assert {q.get("lDongSignguCd") for op, q in api.calls if op == "areaBasedList2"} == {"901", "902", "903"}
    fest = [q for op, q in api.calls if op == "searchFestival2"]
    assert len(fest) == 1 and fest[0]["eventStartDate"] == TODAY.strftime("%Y%m%d")   # from today, the whole 시도

    places = {p["tourapi"]["contentid"]: p for p in json.loads((region / "places.json").read_text("utf-8"))}
    assert set(places) == {"990001", "990002", "990003", "990004", "990005"}
    assert {cid: (p["name"], p["kind"], p["district"], p["status"]) for cid, p in places.items()} == {
        "990001": ("가상 공원", "attraction", "연수구", "draft"), "990002": ("가상 식당", "food", "연수구", "draft"),
        "990003": ("가상 호텔", "stay", "미추홀구", "draft"), "990004": ("가상 미술관", "attraction", "미추홀구", "draft"),
        "990005": ("가상 전망대", "attraction", "강화군", "draft")}
    today = TODAY.isoformat()
    for cid, p in places.items():   # every fact carries its own source and check date
        assert p["facts"] and set(p["fact_sources"]) == set(p["facts"]), cid
        assert all(s == {"provider": "한국관광공사 TourAPI", "checked_at": today, "contentid": cid}
                   for s in p["fact_sources"].values()), cid
        assert p["geo"]["source"] == "TourAPI" and p["summary"] == ""
    assert places["990001"]["facts"]["usetime"] == "09:00~18:00" and places["990001"]["facts"]["usefee"] == "무료(시험 값)"
    assert places["990003"]["facts"]["checkin"] == "15:00" and places["990002"]["facts"]["menu"] == "시험국수"
    # photos: Type1 and Type3 only, https, credited; Type2 (식당) and Type4 (호텔) are not taken
    assert places["990001"]["images"] == [{"url": IMG.format("990001").replace("http:", "https:"), "alt": "가상 공원",
                                           "credit": "한국관광공사", "license": "KOGL-1", "source": "TourAPI"}]
    assert places["990004"]["images"][0]["license"] == "KOGL-3"
    assert places["990002"]["images"] == [] and places["990003"]["images"] == [] and places["990005"]["images"] == []
    # overview kept for fact checking only
    assert SENTINEL in places["990001"]["tourapi"]["overview"]

    events = json.loads((region / "events.json").read_text("utf-8"))
    assert [(e["name"], e["start_date"], e["status"], e["source_name"]) for e in events] == [
        ("[시험] 가상 축제", f"{D(10)[:4]}-{D(10)[4:6]}-{D(10)[6:]}", "draft", "한국관광공사 TourAPI")]

    assert "장소 5곳(관광지 3 · 음식점 1 · 숙소 1)" in out and "강화군 1, 미추홀구 2, 연수구 2" in out
    assert "대표 사진 제1유형 1 · 제3유형 1; 제2·4유형·유형 없음은 받지 않음 2곳" in out
    assert "전화 4 · 이용시간 4 · 쉬는 날 3 · 요금 2 · 주차 5 · 체크인 1" in out
    assert "행사 1건(오늘 이후 진행 1건)" in out and "남은 호출(캐시에 없는 응답): 약 0회" in out
    # the photo sizes the build reads (tools/image_sizes.py): every shown photo, read from the photo host, not TourAPI
    sizes = json.loads((region / "image_sizes.json").read_text("utf-8"))
    assert sizes == {i["url"]: [940, 627, 100000] for p in places.values() for i in p["images"]} and len(sizes) == 2
    assert "사진 크기(" in out and "사진 2/2장 · 작은 크기 파일 0장" in out
    assert not [op for op, _ in api.calls if "image" in op]
    assert "python -m pipeline.build --data data/incheon --out dist-preview --mode preview" in out
    assert "python tools/approve_publication.py --data data/incheon --date " + today in out
    assert (tmp_path / "reports" / "collect.md").exists() and (tmp_path / "reports" / "tourapi_bulk.md").exists()
    for text in (out, err, *(f.read_text("utf-8") for f in (tmp_path / "reports").iterdir()),
                 *(f.read_text("utf-8") for f in region.glob("*.json"))):
        assert FAKE_KEY not in text and urllib.parse.quote(FAKE_KEY, safe="") not in text

    # the printed next step works on what was written: a preview build that validates, without the overview text
    dist = tmp_path / "dist-preview"
    stats = build(region, dist, "preview")
    assert stats["entities"] == 5
    errors, _, _ = validate(region, dist, "preview")
    assert errors == [], errors[:5]
    leaked = [str(f.relative_to(dist)) for f in dist.rglob("*") if f.is_file() and f.suffix in (".html", ".json", ".txt", ".xml")
              and "OVERVIEW-SENTINEL" in f.read_text("utf-8", errors="replace")]
    assert leaked == []
    assert "가상 전망대" in (dist / "places" / places["990005"]["slug"] / "index.html").read_text("utf-8")

    # and the approval step's preview runs on a region that has no guides or courses yet
    from tools import approve_publication, build_review
    build_review.run(region, tmp_path / "dist-review", tmp_path / "reports")
    assert approve_publication.main(["--data", str(region), "--date", today,
                                     "--selection", str(tmp_path / "reports" / "review_build_selection.json")]) == 0
    assert '"guides": {"published_now": 0' in capsys.readouterr().out


def test_cap_stops_the_run_and_the_same_command_resumes_from_the_cache(region, monkeypatch, capsys):
    api = FakeTourAPI()
    monkeypatch.setattr("urllib.request.urlopen", api)
    monkeypatch.setenv("TOURAPI_KEY", FAKE_KEY)
    args = ["--data", str(region), "--max-calls", "34", "--events-from", D(-30)]
    code, out, err = _run(args, capsys)
    assert code == 3, err
    assert "멈춤:" in out and "이어 받기" in out and "python tools/collect.py --data" in out
    resume = next(line for line in out.splitlines() if "이어 받기" in line)
    assert f"--events-from {D(-30)}" in resume                         # the same question, so the cache answers it
    first = len(api.calls)
    added = len(json.loads((region / "places.json").read_text("utf-8")))
    assert 0 < added < 5
    estimate = int(re.search(r"남은 호출\(캐시에 없는 응답\): 약 (\d+)회", out).group(1))
    code, out, err = _run(args, capsys)
    assert code == 0, err
    assert len(json.loads((region / "places.json").read_text("utf-8"))) == 5
    second = api.calls[first:]
    detail_ids = lambda calls: [(op, q.get("contentId"), q.get("contentTypeId")) for op, q in calls if op.startswith("detail")]
    assert not set(detail_ids(api.calls[:first])) & set(detail_ids(second))   # nothing fetched twice
    assert not [op for op, _ in second if op == "areaBasedList2"]              # the lists came from the cache
    assert estimate == len(detail_ids(second)) > 0                             # the printed estimate was exact


def test_provider_errors_are_shown_as_given_with_the_key_masked(region, monkeypatch, capsys):
    xml = ("<OpenAPI_ServiceResponse><cmmMsgHeader><errMsg>SERVICE ERROR</errMsg><returnAuthMsg>"
           "SERVICE_KEY_IS_NOT_REGISTERED_ERROR serviceKey={KEY}</returnAuthMsg><returnReasonCode>30</returnReasonCode>"
           "</cmmMsgHeader></OpenAPI_ServiceResponse>")
    monkeypatch.setenv("TOURAPI_KEY", FAKE_KEY)
    monkeypatch.setattr("urllib.request.urlopen", FakeTourAPI(fail={"searchKeyword2": xml, "searchKeyword1": xml}))
    code, out, err = _run(["--data", str(region)], capsys)
    assert code == 1 and "SERVICE_KEY_IS_NOT_REGISTERED_ERROR serviceKey=«KEY»" in out
    assert "등록되지 않은 키" in out and "진단을 통과하지 못해" in err
    assert FAKE_KEY not in out + err and "Traceback" not in out + err
    assert not (region / "places.json").exists()

    # the key works, the list call fails: the provider's message as given, the key masked, no traceback
    body = json.dumps({"response": {"header": {"resultCode": "30", "resultMsg": "SERVICE ERROR for {KEY}"}}})
    monkeypatch.setattr("urllib.request.urlopen", FakeTourAPI(fail={"areaBasedList2": body}))
    code, out, err = _run(["--data", str(region)], capsys)
    assert code == 1 and "중단: areaBasedList2: resultCode=30 SERVICE ERROR for «KEY»" in err
    assert FAKE_KEY not in out + err and "Traceback" not in out + err


def test_doctor_reads_the_region_codes_live_and_compares_names(region, monkeypatch):
    monkeypatch.setattr("urllib.request.urlopen", FakeTourAPI())
    site = json.loads((region / "site.json").read_text("utf-8"))
    rep = doctor.run("인천", FAKE_KEY, site)
    assert rep["verdict"].startswith("정상") and "법정동 시도 코드 98, 시군구 3곳" in rep["verdict"]
    reg = rep["region"]
    assert reg["districts"] == [{"code": "901", "name": "연수구"}, {"code": "902", "name": "미추홀구"},
                                {"code": "903", "name": "강화군"}]
    assert reg["not_in_site"] == [] and "제물포구" in reg["site_not_in_tourapi"]   # names site.json has, TourAPI not
    assert reg["area"]["code"] == "91" and rep["calls"] == len(rep["attempts"]) + 4
    text = "\n".join(doctor.report_lines(rep))
    assert "확인: TourAPI 목록에 없는 site.json districts 이름" in text and FAKE_KEY not in text
    missing = doctor.run("인천", FAKE_KEY, {**site, "region_full": "가상특별시"})
    assert missing["verdict"].startswith("실패") and "region_full '가상특별시'" in missing["verdict"]


# the 카페·디저트 and 쇼핑 items of the list-only tests (invented like the rest): a 음식점 item TourAPI classifies as a
# café (lclsSystm3 FD05…) with a phone in the list item, and a type-38 shop
CAFE = {**_item("990006", "39", "[시험] 가상 카페", "인천광역시 미추홀구 시험커피길 6", 126.663, 37.453, "Type3"),
        "lclsSystm1": "FD", "lclsSystm2": "FD05", "lclsSystm3": "FD050100", "tel": "032-000-0006"}
SHOP = {**_item("990007", "38", "[시험] 가상 시장", "인천광역시 강화군 강화읍 시험장터길 7", 126.483, 37.743, "Type1"),
        "lclsSystm1": "SH", "lclsSystm2": "SH06", "lclsSystm3": "SH060200"}


def _lists_in_cache(region, monkeypatch, capsys) -> FakeTourAPI:
    """A collection that stops at its call cap right after the lists (doctor 5 + region codes 2 + 3 구·군 × 6 types):
    the list responses are in the cache, no detail of any place is."""
    monkeypatch.setitem(LISTS, ("902", "39"), [CAFE])
    monkeypatch.setitem(LISTS, ("903", "38"), [SHOP])
    api = FakeTourAPI()
    monkeypatch.setattr("urllib.request.urlopen", api)
    monkeypatch.setenv("TOURAPI_KEY", FAKE_KEY)
    code, out, err = _run(["--data", str(region), "--max-calls", "25"], capsys)
    assert code == 3, err
    assert len([op for op, _ in api.calls if op == "areaBasedList2"]) == 18
    assert not [op for op, _ in api.calls if op.startswith("detail")]
    assert json.loads((region / "places.json").read_text("utf-8")) == []
    return api


def test_lists_only_adds_every_listed_place_from_the_cache_without_a_call(region, monkeypatch, capsys, tmp_path):
    _lists_in_cache(region, monkeypatch, capsys)
    sizes = (region / "image_sizes.json").read_text("utf-8")   # written by that run's photo step (no photo yet)
    monkeypatch.delenv("TOURAPI_KEY")
    monkeypatch.setattr("urllib.request.urlopen", lambda *a, **k: pytest.fail("--lists-only makes no call"))
    monkeypatch.setattr(image_sizes, "probe", lambda url: pytest.fail("--lists-only reads no photo host"))
    code, out, err = _run(["--data", str(region), "--lists-only"], capsys)
    assert code == 0, err

    places = {p["tourapi"]["contentid"]: p for p in json.loads((region / "places.json").read_text("utf-8"))}
    assert set(places) == {f"99000{i}" for i in range(1, 8)}
    assert {cid: (p["name"], p["kind"], p["category"], p["district"]) for cid, p in places.items()} == {
        "990001": ("가상 공원", "attraction", "관광지", "연수구"), "990002": ("가상 식당", "food", "음식점", "연수구"),
        "990003": ("가상 호텔", "stay", "숙박", "미추홀구"), "990004": ("가상 미술관", "attraction", "문화시설", "미추홀구"),
        "990005": ("가상 전망대", "attraction", "관광지", "강화군"), "990006": ("가상 카페", "cafe", "카페·디저트", "미추홀구"),
        "990007": ("가상 시장", "shopping", "쇼핑", "강화군")}
    today = TODAY.isoformat()   # the day the (cached) list pages were fetched
    item = {i["contentid"]: i for i in [*sum(LISTS.values(), []), CAFE, SHOP]}
    for cid, p in places.items():
        assert (p["status"], p["tier"], p["summary"], p["id"]) == ("draft", "basic", "", f"tourapi-{cid}"), cid
        assert p["tourapi"]["details_pending"] is True and "overview" not in p["tourapi"], cid
        assert p["tourapi"].get("lclsSystm3", "") == item[cid]["lclsSystm3"], cid   # as listed (empty: left out)
        # the list's own values only, each with its provider, check date and the operation it came from
        assert p["facts"]["address"] == item[cid]["addr1"], cid
        assert set(p["fact_sources"]) == set(p["facts"]) and all(
            s == {"provider": "한국관광공사 TourAPI", "checked_at": today, "contentid": cid, "via": "areaBasedList2"}
            for s in p["fact_sources"].values()), cid
        assert p["facts_source"] == {"provider": "한국관광공사 TourAPI", "checked_at": today, "contentid": cid}
        assert p["geo"] == {"lat": float(item[cid]["mapy"]), "lng": float(item[cid]["mapx"]), "source": "TourAPI",
                            "checked_at": today}, cid
    assert places["990006"]["facts"] == {"address": CAFE["addr1"], "infocenter": "032-000-0006"}   # phone: listed
    assert set(places["990001"]["facts"]) == {"address"}                                         # nothing else known
    # photos: Type1 and Type3 only, https, credited 한국관광공사; Type2 (식당), Type4 (호텔), none (전망대) not taken
    assert places["990007"]["images"] == [{"url": IMG.format("990007").replace("http:", "https:"), "alt": "가상 시장",
                                           "credit": "한국관광공사", "license": "KOGL-1", "source": "TourAPI",
                                           "checked_at": today}]
    assert [i["license"] for i in places["990006"]["images"]] == ["KOGL-3"]
    assert places["990002"]["images"] == places["990003"]["images"] == places["990005"]["images"] == []

    assert "실호출 0(진단 0 포함)" in out and "새 장소 7 (목록 값만 — 상세 대기)" in out
    assert "장소 7곳(관광지 3 · 카페·디저트 1 · 음식점 1 · 쇼핑 1 · 숙소 1) · draft 7 · 상세 대기(목록 값만) 7" in out
    assert "강화군 2, 미추홀구 3, 연수구 2" in out
    assert "상세 받기(날마다): python tools/collect.py --data" in out and "사진 크기: 건너뜀" in out
    assert "목록만으로 추가한 장소" in (tmp_path / "reports" / "tourapi_bulk.md").read_text("utf-8")
    assert not (region / "events.json").exists() and (region / "image_sizes.json").read_text("utf-8") == sizes

    # the preview build shows them (drafts, noindex) and validates; a page says what is still to be checked
    dist = tmp_path / "dist-preview"
    assert build(region, dist, "preview")["entities"] == 7
    errors, _, _ = validate(region, dist, "preview")
    assert errors == [], errors[:5]
    page = (dist / "places" / places["990007"]["slug"] / "index.html").read_text("utf-8")
    assert "가상 시장" in page and "출처: 한국관광공사" in page and "확인 필요" in page


def test_the_daily_collection_completes_list_only_places_without_adding_them_twice(region, monkeypatch, capsys):
    _lists_in_cache(region, monkeypatch, capsys)
    code, out, err = _run(["--data", str(region), "--lists-only"], capsys)
    assert code == 0, err
    estimate = int(re.search(r"남은 호출\(캐시에 없는 응답\): 약 (\d+)회", out).group(1))
    listed = {p["id"]: p for p in json.loads((region / "places.json").read_text("utf-8"))}
    api = FakeTourAPI()
    monkeypatch.setattr("urllib.request.urlopen", api)
    code, out, err = _run(["--data", str(region)], capsys)
    assert code == 0, err
    places = json.loads((region / "places.json").read_text("utf-8"))
    assert sorted(p["id"] for p in places) == sorted(listed)               # the same places, none added twice
    by = {p["tourapi"]["contentid"]: p for p in places}
    assert not [p["name"] for p in places if p["tourapi"].get("details_pending")]
    assert all(p["slug"] == listed[p["id"]]["slug"] for p in places)      # page addresses stay
    details = [(op, q.get("contentId")) for op, q in api.calls if op.startswith("detail") and q.get("contentId") != "990101"]
    assert len(details) == len(set(details)) == estimate                  # each fetched once; the printed estimate exact
    assert "새 장소 0" in out and "(그중 목록만으로 더했던 곳 7)" in out
    today = TODAY.isoformat()
    # the detail values now stand with their own source (no 'via': the details replaced the list's copies)
    assert by["990001"]["facts"]["usetime"] == "09:00~18:00" and by["990001"]["facts"]["usefee"] == "무료(시험 값)"
    assert by["990001"]["fact_sources"]["address"] == {"provider": "한국관광공사 TourAPI", "checked_at": today,
                                                       "contentid": "990001"}
    assert by["990003"]["facts"]["checkin"] == "15:00" and by["990002"]["facts"]["menu"] == "시험국수"
    assert by["990006"]["kind"] == "cafe" and by["990007"]["kind"] == "shopping"
    assert SENTINEL in by["990001"]["tourapi"]["overview"]                 # kept for fact checking only
    assert [i["license"] for i in by["990004"]["images"]] == ["KOGL-3"] and by["990002"]["images"] == []


def test_lists_only_without_cached_lists_says_what_to_run(region, monkeypatch, capsys):
    monkeypatch.setattr("urllib.request.urlopen", lambda *a, **k: pytest.fail("--lists-only makes no call"))
    code, out, err = _run(["--data", str(region), "--lists-only"], capsys)
    assert code == 1 and "캐시가 없습니다" in err and "python tools/collect.py --data" in err
    assert not (region / "places.json").exists() and "Traceback" not in out + err
    from tools import tourapi_bulk
    with pytest.raises(SystemExit):   # no detail, event or photo option beside it
        tourapi_bulk.main(["--data", str(region), "--lists-only", "--details"])
