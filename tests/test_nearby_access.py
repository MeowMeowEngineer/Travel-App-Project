"""'근처 주차·버스' on place pages: public parking lots (parking_lots.json) and bus stops (nearby.json) near a place,
shown below the first screen after the map — the view model, the template and the validator checks that keep every
shown value from the two files. Nearby lots are not the place's own parking and never count toward the index criteria."""
import json
import re
import shutil
from pathlib import Path

from pipeline import present, schema
from pipeline.build import State, build
from pipeline.validate import nearby_data_problems, nearby_stale_problems, scan_file, validate

ROOT = Path(__file__).resolve().parent.parent
SAMPLE = ROOT / "data" / "sample"
SUMMARY = "카페 소금은 소금빵과 핸드드립 커피를 내는 12석 카페로, 화요일에 쉽니다."

FREE = {"id": "lot-free", "management_no": "307-1-000030", "name": "월명동 6", "type": "노상",
        "address": "전북특별자치도 군산시 구영7길 69 (신창동 )", "address_jibun": "전북특별자치도 군산시 신창동 1-2",
        "lat": 35.98676791, "lng": 126.7104599, "spaces": 24, "paid": "무료", "reference_date": "2026-04-17"}
TYPO = {"id": "lot-typo", "management_no": "307-2-000031", "name": "삼학동 1", "type": "노외",
        "address": "전북특별자치도 군산시 동 국사길19, (금광동 , 베르하임)", "address_jibun": "전북특별자치도 군산시 금광동 165-36",
        "address_note": "원자료 도로명주소 띄어쓰기 오류로 보임", "lat": 35.9824897, "lng": 126.707832, "spaces": 27,
        "paid": "무료", "reference_date": "2026-04-17"}
PAID = {"id": "lot-paid", "management_no": "307-2-000128", "name": "옥도면 선유2", "type": "노외", "address": None,
        "address_jibun": "전북특별자치도 군산시 옥도면 선유도리 279-8", "lat": 35.81311581, "lng": 126.4131432,
        "spaces": 359, "paid": "유료", "reference_date": "2026-04-17",
        "alt": {"name": {"value": "선유2구 주차장", "source_name": "군산시 문화관광", "url": "https://www.gunsan.go.kr/tour/m2197"},
                "spaces": {"value": 331, "source_name": "군산시 문화관광", "url": "https://www.gunsan.go.kr/tour/m2197"}},
        "fee": {"basic_minutes": 60, "differs": True, "contact": "063-454-3773", "versions": [
            {"source": "ordinance", "tier": "도서지역", "free_minutes": 60,
             "small": {"to_1h30": 1000, "per_30min": 1500, "day_over_5h": 12000},
             "large": {"to_1h30": 2000, "per_30min": 2500, "day_over_5h": 20000}},
            {"source": "tourapi", "free_minutes": 60, "small": {"per_30min": 1500}, "large": {"per_30min": 2500}}]}}
CARGO = {"id": "lot-cargo", "management_no": "307-2-000006", "name": "화물전용 군산시 임시주차장", "type": "노외",
         "address": "전북특별자치도 군산시 조촌로 215 (경암동 )", "address_jibun": None, "lat": 35.98, "lng": 126.73,
         "spaces": 255, "paid": "무료", "nearby": False, "nearby_excluded": "화물차 전용(이름)"}
LOTS = {"contacts": [{"phone": "063-454-3773", "unit": "군산시 교통항만수산국 교통행정과 교통기획계",
                      "duty": "유료 공영주차장 운영관리"}],
        "lots": [FREE, TYPO, PAID, CARGO]}
NEARBY = {"_meta": {"parking": {"radius_m": 500, "max": 3}, "bus": {"radius_m": 500, "max": 2}},
          "sample-0001": {"parking": [{"lot_id": "lot-free", "meters": 71}, {"lot_id": "lot-typo", "meters": 265},
                                      {"lot_id": "lot-paid", "meters": 330}],
                          "bus": [{"stop_name": "해양경찰서", "meters": 40, "routes": ["01", "08"]},
                                  {"stop_name": "교보빌딩", "meters": 50, "routes": []}]},
          "sample-0002": {"parking": [], "bus": []}}


def data_with(tmp_path, nearby=NEARBY, lots=LOTS):
    data = tmp_path / "data"
    shutil.copytree(SAMPLE, data)
    places = json.loads((data / "places.json").read_text("utf-8"))
    for p in places:
        if p["id"] in ("sample-0001", "sample-0002"):
            p["geo"] = {"lat": 35.9870443303, "lng": 126.7111681428, "source": "TourAPI"}
    (data / "places.json").write_text(json.dumps(places, ensure_ascii=False), "utf-8")
    if lots is not None:
        (data / "parking_lots.json").write_text(json.dumps(lots, ensure_ascii=False), "utf-8")
    if nearby is not None:
        (data / "nearby.json").write_text(json.dumps(nearby, ensure_ascii=False), "utf-8")
    return data


def access_errors(data, out, mode="sample"):
    errors, _, _ = validate(data, out, mode)
    return [x for x in errors if "근처" in x or "정류장" in x or "nearby.json" in x]


def block(html):
    return html[html.index('data-block="access"'):html.index("</section>", html.index('data-block="access"'))]


# ---------------------------------------------------------------- view model
def test_access_vm_rows_come_from_the_two_files(tmp_path):
    S = State(data_with(tmp_path), "sample")
    e = S.ent_by_slug["gyeongam-railroad-village"]
    A = present.access_vm(S, e)
    assert [l["id"] for l in A["lots"]] == ["lot-free", "lot-typo", "lot-paid"]
    free, typo, paid = A["lots"]
    assert (free["name"], free["type"], free["addr"], free["m"], free["spaces"], free["paid"]) == \
        ("월명동 6", "노상주차장", "구영7길 69 (신창동)", 71, 24, "무료")
    assert free["fees"] == [] and not free["confirm"] and free["contact"] == ""
    assert free["map"] == "https://map.kakao.com/link/map/%EC%9B%94%EB%AA%85%EB%8F%99%206,35.98676791,126.7104599"
    # a road address with a source spacing slip stays as written, with its 지번 beside it
    assert typo["addr"] == "동 국사길19, (금광동, 베르하임)" and typo["jibun"] == "금광동 165-36"
    # paid lot: no road address -> the 지번; every fee version with its source; both 면수; one call line
    assert paid["addr"] == "옥도면 선유도리 279-8" and paid["jibun"] == ""
    assert [f["src"] for f in paid["fees"]] == ["군산시 주차장 조례 도서지역 요금", "한국관광공사 선유도해수욕장 안내"]
    assert paid["fees"][0]["text"] == ("1시간까지 무료 · 1시간 30분까지 소형 1,000원·대형 2,000원 · 이후 30분마다 소형 "
                                       "1,500원·대형 2,500원 · 5시간 넘으면 1일 소형 12,000원·대형 20,000원")
    assert paid["fees"][1]["text"] == "1시간까지 무료 · 이후 30분마다 소형 1,500원·대형 2,500원"
    assert paid["confirm"] and paid["differ"] == "면수·요금"
    assert (paid["alt_name"], paid["alt_spaces"]) == ("선유2구 주차장", 331)
    assert paid["contact"] == "군산시 교통행정과 교통기획계 063-454-3773"
    assert A["stops"] == [{"name": "해양경찰서", "m": 40, "routes": ["01", "08"], "routes_text": "01·08"},
                          {"name": "교보빌딩", "m": 50, "routes": [], "routes_text": ""}]
    assert A["sources"] == ["공공데이터포털 전국주차장정보표준데이터", "군산시 주차장 조례", "한국관광공사 TourAPI",
                            "군산시 문화관광", "공공데이터포털 군산시 버스정류장현황", "군산시 시내버스 시간표"]
    # nothing within the radius, no coordinates, or no files: no block
    assert present.access_vm(S, S.ent_by_slug["chowon-photo-studio"]) is None
    assert present.access_vm(S, S.ent_by_slug["eunpa-lake-park"]) is None
    S0 = State(data_with(tmp_path / "none", nearby=None, lots=None), "sample")
    assert present.access_vm(S0, S0.ent_by_slug["gyeongam-railroad-village"]) is None


def test_nearby_lots_never_count_toward_the_index_criteria(tmp_path):
    S = State(data_with(tmp_path), "sample")
    e = S.ent_by_slug["gyeongam-railroad-village"]
    bare = {**e, "facts": {k: v for k, v in e["facts"].items() if not k.startswith("parking")}}
    assert present.access_vm(S, bare)["lots"]              # public lots nearby ...
    assert "parking" not in schema.index_groups(bare)      # ... are not the place's parking
    assert schema.index_status(bare) == schema.index_status({**bare, "_nearby": S.nearby[e["id"]]})
    S0 = State(data_with(tmp_path / "none", nearby=None, lots=None), "sample")
    assert [(x["id"], x["_index_ok"]) for x in S.entities] == [(x["id"], x["_index_ok"]) for x in S0.entities]


# ---------------------------------------------------------------- template
def test_place_page_shows_the_block_after_the_map_and_keeps_the_first_screen(tmp_path):
    out, out0 = tmp_path / "site", tmp_path / "site0"
    build(data_with(tmp_path), out, "sample")
    build(data_with(tmp_path / "none", nearby=None, lots=None), out0, "sample")
    page = out / "places" / "gyeongam-railroad-village" / "index.html"
    html, html0 = page.read_text("utf-8"), (out0 / "places" / "gyeongam-railroad-village" / "index.html").read_text("utf-8")
    hero = lambda h: h[h.index('<header class="pl-hero'):h.index("</header>")]
    assert hero(html) == hero(html0)                       # first screen unchanged
    assert html.index('id="h-map"') < html.index('data-block="access"') < html.index('id="h-near"')
    b = block(html)
    assert re.sub(r"<[^>]+>", "", b.split("</h2>")[0]).endswith("경암동 철길마을 근처 주차·버스")
    assert "근처 공영주차장" in b and "가까운 버스 정류장" in b and "직선거리" in b
    assert 'data-lot="lot-free"' in b and 'data-stop="해양경찰서"' in b
    assert 'data-track="parking_click" data-provider="kakao" data-place="sample-0001"' in b
    assert 'href="tel:0634543773"' in b and 'data-track="tel_click" data-place="sample-0001"' in b
    text = re.sub(r"\s+", " ", re.sub(r"<[^>]+>", "", b))
    assert "월명동 6 노상주차장" in text and "71m" in text and "24면 · 무료" in text
    assert "동 국사길19, (금광동, 베르하임) · 지번 금광동 165-36" in text
    assert "면수·요금 출처마다 다름 · 방문 전 전화 확인" in text and "331대" in text
    rows = text[:text.index("출처:")]
    assert "시내버스 01·08번" in rows and rows.count("시내버스") == 1    # a stop without known routes shows none
    src = text[text.index("출처:"):]
    assert "공공데이터포털 전국주차장정보표준데이터" in src and not re.search(r"\d{4}|확인일|기준|업데이트", src)
    # the place's own parking row stays as stored, in the facts card; the block is outside it
    p = scan_file(page)
    assert p.blocks["facts"].count("[샘플] TourAPI parking 값") >= 1 and not p.access_in_facts
    assert all(not r["in_facts"] for r in p.access_rows) and len(p.access_rows) == 5
    # no rows within the radius -> no block
    assert 'data-block="access"' not in (out / "places" / "chowon-photo-studio" / "index.html").read_text("utf-8")


# ---------------------------------------------------------------- validator
def test_validator_passes_the_built_block_and_catches_changed_values(tmp_path):
    data, out = data_with(tmp_path), tmp_path / "site"
    build(data, out, "sample")
    assert access_errors(data, out) == []
    page = out / "places" / "gyeongam-railroad-village" / "index.html"
    good = page.read_text("utf-8")

    def errors_after(html):
        page.write_text(html, "utf-8")
        found = access_errors(data, out)
        page.write_text(good, "utf-8")
        return found

    assert any("파일에 없는 숫자" in x or "파일 값이 줄에 없음" in x for x in errors_after(good.replace(">71m<", ">72m<")))
    assert any("파일에 없는 숫자 ['1,200']" in x for x in errors_after(good.replace("1,000원", "1,000원 · 1,200원", 1)))
    assert any("방문 전 전화 확인" in x for x in errors_after(good.replace(" · 방문 전 전화 확인", "")))
    assert any("시내버스" not in x and "01" in x for x in errors_after(good.replace("01·08", "08")))
    gone = re.sub(r'<li data-lot="lot-typo">.*?</li>', "", good, flags=re.S)
    assert any("근처 공영주차장 줄이 nearby.json과 다름" in x for x in errors_after(gone))
    inside = good.replace('data-block="access"', 'data-block="access-x"').replace(
        '<section class="pl-side" aria-labelledby="h-facts" data-block="facts" data-sticky>',
        '<section class="pl-side" aria-labelledby="h-facts" data-block="facts" data-sticky><div data-block="access"><ol><li data-lot="lot-free">월명동 6</li></ol></div>')
    assert any("facts" in x for x in errors_after(inside))
    # a block on a page without nearby entries
    other = out / "places" / "chowon-photo-studio" / "index.html"
    keep = other.read_text("utf-8")
    other.write_text(keep.replace('<article class="place"', f'<div data-block="access">{block(good)}</section></div><article class="place"'), "utf-8")
    assert any("nearby.json에 값이 없는데" in x for x in access_errors(data, out))
    other.write_text(keep, "utf-8")


def test_nearby_file_names_only_usable_lots_within_the_radius(tmp_path):
    bad = {**NEARBY, "sample-0001": {"parking": [{"lot_id": "lot-cargo", "meters": 120}, {"lot_id": "nope", "meters": 90},
                                                 {"lot_id": "lot-free", "meters": 640}], "bus": []}}
    S = State(data_with(tmp_path, nearby=bad), "sample")
    problems = nearby_data_problems(S)
    assert any("근처 목록에서 뺀 주차장 lot-cargo" in x for x in problems)
    assert any("parking_lots.json에 없는 주차장 nope" in x for x in problems)
    assert any("640m" in x for x in problems)
    assert any("가까운 순이 아님" in x for x in problems)


def test_stale_nearby_distances_and_missing_entries_are_warned(tmp_path):
    S = State(data_with(tmp_path), "sample")
    warned = nearby_stale_problems(S)
    assert not any("lot-free" in x for x in warned)        # 71m is what the coordinates give
    assert any("lot-typo 거리 265m가 지금 좌표로는" in x for x in warned)
    assert not any("sample-0002" in x for x in warned)     # an entry with no rows is still an entry
    S.nearby.pop("sample-0001")
    assert any("sample-0001" in x and "항목이 없음" in x for x in nearby_stale_problems(S))
    S0 = State(data_with(tmp_path / "none", nearby=None, lots=None), "sample")
    assert nearby_stale_problems(S0) == []
