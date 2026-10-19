"""The city is configuration (pipeline/city.py, data/<region>/site.json): the Incheon config with a clearly fake tiny
dataset (tests/fixtures/incheon_tiny — never data/incheon) builds and validates with no trace of the sample city in
any output file; the empty data/incheon builds an empty-state preview and stops a production build with the
collection hint; the 권역 rule is the configured district rule, and the map page prints the rule that assigned the
places."""
import json
import re
import shutil
from pathlib import Path

import pytest

from pipeline import city
from pipeline.build import NoPlacesError, build
from pipeline.textutil import area_from_address
from pipeline.validate import validate

ROOT = Path(__file__).resolve().parent.parent
INCHEON = ROOT / "data" / "incheon"
TINY = Path(__file__).resolve().parent / "fixtures" / "incheon_tiny"
# the sample city's names in every script the engine has used: none may reach an Incheon page, script or data file
FOREIGN = re.compile(r"군산|gunsan|Gunsan|GUNSAN|群山|Кунсан|선유도|Seonyudo|고군산")
YJ = ("운서동", "운남동", "운북동", "중산동", "을왕동", "남북동", "덕교동", "무의동")


def _incheon_data(tmp_path: Path, with_fixture: bool) -> Path:
    data = tmp_path / "data"
    data.mkdir()
    for f in INCHEON.glob("*.json"):
        shutil.copy(f, data / f.name)
    if with_fixture:
        for f in TINY.glob("*.json"):
            shutil.copy(f, data / f.name)
    return data


def _foreign_hits(out: Path) -> list[str]:
    hits = []
    for f in sorted(out.rglob("*")):
        if f.is_file() and f.suffix in (".html", ".js", ".css", ".json", ".txt", ".xml", ".md", ".webmanifest"):
            m = FOREIGN.search(f.read_text("utf-8", errors="replace"))
            if m:
                hits.append(f"{f.relative_to(out)}: {m.group(0)}")
    return hits


def test_incheon_district_rule_and_its_text():
    C = city.activate_dir(INCHEON)
    assert C.region_method == "district" and C.locality == "인천광역시" and C.region_admin == ""
    cases = {
        "인천광역시 중구 공항로 272 (운서동)": ("중구", "영종·용유"),
        "인천광역시 중구 신포로27번길 80 (관동1가)": ("중구", "개항장·원도심"),   # a 법정동 with a 가 number stays whole
        "인천광역시 중구 공항로 272": ("중구", None),                            # 중구 without a 법정동: not split
        "인천광역시 영종구 하늘중앙로 201": ("영종구", "영종·용유"),
        "인천광역시 제물포구 금곡로 27 (송림동)": ("제물포구", "개항장·원도심"),
        "인천광역시 동구 테스트로 1": ("동구", "개항장·원도심"),
        "인천광역시 연수구 테스트대로 2": ("연수구", "송도·연수"),
        "인천광역시 서해구 테스트로 3": ("서해구", "도심 생활권"),
        "인천광역시 검단구 테스트로 4": ("검단구", "도심 생활권"),
        "인천광역시 강화군 강화읍 테스트로 5": ("강화군", "강화"),
        "인천광역시 옹진군 테스트면 테스트리 6": ("옹진군", "옹진 섬"),
        "서울특별시 중구 테스트로 7": ("", None),                                 # another city's 중구 is not Incheon's
    }
    for address, (district, region) in cases.items():
        d = C.district_of(address)
        assert d == district, address
        assert C.district_region(d, area_from_address(address)) == region, address
    assert C.district_of("테스트로 5", "제물포구") == "제물포구"                   # TourAPI's 구·군 when the address has none
    lines = C.region_rule_lines()
    assert lines[0] == f"개항장·원도심: 제물포구, 동구, 중구 중 {'·'.join(YJ)}을 뺀 곳"
    assert lines[1] == f"영종·용유: 영종구, 중구 중 {'·'.join(YJ)}"
    assert [line.split(":")[0] for line in lines] == ["개항장·원도심", "영종·용유", "송도·연수", "도심 생활권", "강화", "옹진 섬"]
    # the city's own names in the stock-phrase rule, the address split for JSON-LD, the prefix that goes
    assert re.match(C.taut_rx("가"), "가는 인천광역시 중구 테스트동에 있는 관광지입니다.")
    assert not re.match(C.taut_rx("가"), "가는 바다를 내려다보는 전망대가 있는 관광지입니다.")
    assert C.postal_parts("인천광역시 중구 테스트로 1") == ("인천광역시", "중구", "테스트로 1")
    assert C.strip_prefix("인천광역시 중구 테스트로 1") == "중구 테스트로 1"
    assert C.place_where("연수구", "테스트동") == "인천광역시 연수구 테스트동"


def test_sample_city_keeps_its_anchor_rule():
    C = city.current()   # tests/conftest.py: the sample fixture's city
    assert C.region_method == "nearest_anchor" and C.far_m == 12000 and C.region_art["먼 섬"] == "outlying-islands"
    assert C.postal_parts("전북특별자치도 군산시 테스트로 1") == ("전북특별자치도", "군산시", "테스트로 1")
    assert C.display_address("전라북도 군산시 테스트로 1") == "전북특별자치도 군산시 테스트로 1"


def test_neutral_city_assumes_nothing():
    C = city.activate({})
    assert C.names == () and C.region_method == "none" and C.distance_anchors == [] and C.region_rule_lines() == []
    assert C.strip_prefix("어디시 테스트로 1") == "어디시 테스트로 1" and C.district_of("어디시 중구 1") == ""


def test_incheon_fixture_builds_and_validates_with_no_trace_of_the_sample_city(tmp_path):
    data = _incheon_data(tmp_path, with_fixture=True)
    out = tmp_path / "out"
    stats = build(data, out, "preview")
    assert stats["entities"] == 5
    errors, _, _ = validate(data, out, "preview")
    assert errors == [], errors[:5]
    assert _foreign_hits(out) == []
    # the map page prints the rule that assigned the places, and the places sit in their 권역
    page = (out / "map" / "index.html").read_text("utf-8")
    assert "권역은 주소에 적힌 구·군" in page and "영종·용유: 영종구, 중구 중 운서동" in page
    regions = re.findall(r'<h2 id="r-[^"]*-h">([^<]*?) <span', page)
    assert regions == ["개항장·원도심", "영종·용유", "송도·연수", "강화", "권역 미정"]
    assert "중구 운서동" in page                                           # a 광역시's 동 carries its 구·군
    # the home: the assistant's card in the centre (data/incheon/ask.json), the city's words for chat.js
    home = (out / "index.html").read_text("utf-8")
    assert 'id="ask-q"' in home and 'data-chat-site="https://incheon.example.com"' in home
    assert "지금 인천 · " in home and "인천 여행의 모든 것" in home
    site = json.loads((out / "chat" / "site.json").read_text("utf-8"))
    assert site == {"city": {"en": "Incheon", "ko": "인천"}, "name": "인천 여행의 모든 것", "origins": [],
                    "url": "https://incheon.example.com"}
    # structured data: the neutral city node, a 광역시 address split into 시 and 구
    assert '"@id":"https://incheon.example.com/#city","name":"인천광역시"' in home.replace(" ", "")
    beach = (out / "places" / "test-beach-a" / "index.html").read_text("utf-8").replace(" ", "")
    assert '"addressRegion":"인천광역시","addressLocality":"중구"' in beach


def test_incheon_before_collection_preview_is_empty_state_and_production_stops(tmp_path, capsys):
    data = _incheon_data(tmp_path, with_fixture=False)
    out = tmp_path / "out"
    stats = build(data, out, "preview")
    assert stats["entities"] == 0 and "TourAPI 수집 전" in capsys.readouterr().err
    errors, _, _ = validate(data, out, "preview")
    assert errors == [], errors[:5]
    assert _foreign_hits(out) == []
    assert "여행지 안내를 준비하고 있습니다" in (out / "index.html").read_text("utf-8")
    with pytest.raises(NoPlacesError, match="tools/tourapi_bulk.py --data"):
        build(data, tmp_path / "prod", "production")
