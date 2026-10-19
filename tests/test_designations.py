"""Official designations (지정): 군산맛집·모범음식점·백년가게 … on the place page (chips + the '지정' row with each list's
name as a link), list records (one short chip + the lists' source line), the search index, llms.txt / llms-full.txt and
JSON-LD award — and the validator checks that keep them sourced (never relaxed). Each list's 확인일 stays in the data
and is never shown (operator decision 2026-10-09: no visible check dates)."""
import json
import re
import shutil
from pathlib import Path

from pipeline import jsonld, schema
from pipeline.build import build
from pipeline.validate import scan_file, validate

ROOT = Path(__file__).resolve().parent.parent
SAMPLE = ROOT / "data" / "sample"
CHECKED = "2026-10-09"
MATJIP = {"type": "gunsan_matjip", "label": "군산맛집(2026, 군산시 지정)", "year": 2026,
          "source_name": "군산시 문화관광 「군산맛집」 지정 현황(2026)", "url": "https://www.gunsan.go.kr/tour/m2555",
          "checked_at": CHECKED, "match": {"row_ref": "matjip_2026#22", "confidence": "high", "basis": "name+road+number"}}
MOBEOM = {"type": "mobeom", "label": "모범음식점(군산시 지정)", "year": 2026, "source_name": "군산시 문화관광 모범음식점 현황",
          "url": "https://www.gunsan.go.kr/tour/m2554", "checked_at": CHECKED,
          "match": {"row_ref": "mobeom_2026#9", "confidence": "medium", "basis": "name+phone"}}
ANSIM = {"type": "ansim", "label": "안심식당", "year": None, "source_name": "군산시 문화관광 안심식당 지정업소 현황",
         "url": "https://www.gunsan.go.kr/tour/m2807", "checked_at": CHECKED,
         "match": {"row_ref": "ansim_2026#3", "confidence": "high", "basis": "name+road+number"}}
SUMMARY = "복성루는 해물짬뽕과 볶음밥을 내는 35석 규모의 중식당으로, 일요일에 쉽니다."


def food(slug, name, designations=None, **extra):
    e = {"id": slug, "slug": slug, "name": name, "kind": "food", "category": "중식", "tier": "basic",
         "status": "published", "approved_at": "2026-10-08", "themes": [], "summary": SUMMARY,
         "facts": {"address": "전북특별자치도 군산시 월명로 382 (미원동)", "usetime_restdate": "10:00~16:00 / 일요일",
                   "menu": "해물짬뽕", "infocenter": "063-445-8412"},
         "facts_source": {"provider": "군산시 문화관광", "checked_at": "2026-10-08"},
         "original": {"source_name": "군산시 문화관광", "source_url": "https://www.gunsan.go.kr/tour/m2147/view/306591",
                      "license": "NONE", "collected_at": "2026-10-08"}, **extra}
    if designations is not None:
        e["designations"] = designations
    return e


def data_with(tmp_path, places):
    data = tmp_path / "data"
    shutil.copytree(SAMPLE, data)
    (data / "places.json").write_text(json.dumps(places, ensure_ascii=False), "utf-8")
    return data


def dz_errors(data, out, mode="production"):
    errors, _, _ = validate(data, out, mode)
    return [x for x in errors if "지정" in x or "award" in x]


# ---------------------------------------------------------------- schema
def test_designations_order_short_labels_and_what_may_not_be_shown():
    e = food("a", "복성루", [ANSIM, MOBEOM, MATJIP])
    ds = schema.designations(e)
    assert [d["type"] for d in ds] == ["gunsan_matjip", "mobeom", "ansim"]          # DESIGNATION_ORDER
    assert [d["short"] for d in ds] == ["군산맛집 2026", "모범음식점", "안심식당"]
    hyangto = {**ANSIM, "type": "hyangto", "label": "향토음식점(전북, 2020)", "year": 2020}
    assert schema.designation_short(hyangto) == "향토음식점 2020"
    assert schema.designation_problems(MATJIP) == []
    low = {**MATJIP, "match": {"confidence": "low"}}
    flagged = {**MATJIP, "match": {"confidence": "high", "needs_check": True}}
    no_src = {**MATJIP, "url": "", "checked_at": "10월 9일"}
    assert schema.designation_problems(low) and schema.designation_problems(flagged)
    assert schema.designation_problems(no_src) == ["출처 주소(url) 없음", "확인일(checked_at) 없음"]
    assert schema.designations(food("b", "대정소바", [low, flagged, no_src])) == []


def test_designations_do_not_count_toward_the_index_groups():
    plain = food("a", "복성루")
    plain["facts"] = {"address": plain["facts"]["address"], "menu": "해물짬뽕"}
    assert schema.index_groups(plain) == ["menu"]
    assert schema.index_groups({**plain, "designations": [MATJIP, MOBEOM]}) == ["menu"]


def test_jsonld_award_only_on_business_types_and_only_shown_labels():
    site = {"locality": "군산시", "region_admin": "전북특별자치도"}
    node = jsonld.entity_node(food("a", "복성루", [MATJIP, {**MOBEOM, "match": {"confidence": "low"}}]),
                              site, "https://x.kr", "https://x.kr/places/a/", [], [])
    assert node["award"] == "군산맛집(2026, 군산시 지정)"
    two = jsonld.entity_node(food("a", "복성루", [MATJIP, ANSIM]), site, "https://x.kr", "https://x.kr/places/a/", [], [])
    assert two["award"] == ["군산맛집(2026, 군산시 지정)", "안심식당"]
    sight = {**food("s", "공원", [MATJIP]), "kind": "attraction", "category": "관광명소 > 공원"}
    assert "award" not in jsonld.entity_node(sight, site, "https://x.kr", "https://x.kr/places/s/", [], [])
    assert "award" not in jsonld.entity_node(food("b", "빈집"), site, "https://x.kr", "https://x.kr/places/b/", [], [])


# ---------------------------------------------------------------- build + validate
def built(tmp_path, places, mode="production"):
    data = data_with(tmp_path, places)
    out = tmp_path / mode
    build(data, out, mode)
    return data, out


def test_place_page_list_search_llms_and_jsonld_show_designations_with_sources(tmp_path):
    data, out = built(tmp_path, [food("bok", "복성루", [ANSIM, MATJIP]), food("plain", "중화반점")])
    html = (out / "places" / "bok" / "index.html").read_text("utf-8")
    page = scan_file(out / "places" / "bok" / "index.html")
    # first screen: chips under the answer, before the key-fact tiles, each linking to its list
    assert html.index('data-block="summary"') < html.index('class="dz"') < html.index('class="kf kf-hero')
    assert "군산맛집(2026, 군산시 지정)" in page.blocks["designations"]
    assert set(page.block_hrefs["designations"]) >= {MATJIP["url"], ANSIM["url"], "#dz"}
    # the facts card's '지정' row: label and the list (a link) for each — no 확인일 (operator decision 2026-10-09)
    row = next(r for r in page.fact_rows if r["keys"] == ["designations"])
    assert row["dt"] == "지정"
    assert "군산맛집(2026, 군산시 지정) 군산시 문화관광 「군산맛집」 지정 현황(2026)" in row["text"]
    assert "안심식당 군산시 문화관광 안심식당 지정업소 현황" in row["text"]
    assert CHECKED not in row["text"] and "확인일" not in page.visible
    assert row["hrefs"] == [MATJIP["url"], ANSIM["url"]]
    node = next(n for b in page.jsonld_raw for n in json.loads(b)["@graph"] if str(n.get("@id", "")).endswith("#place"))
    assert node["award"] == ["군산맛집(2026, 군산시 지정)", "안심식당"]
    plain = (out / "places" / "plain" / "index.html").read_text("utf-8")
    assert 'class="dz' not in plain and '"award"' not in plain
    # list record: one short chip (the first designation); the lists behind the chips once, linked, without 확인일
    lst = (out / "food" / "index.html").read_text("utf-8")
    assert re.findall(r'<span class="dz-chip">([^<]*)</span>', lst) == ["군산맛집 2026"]
    foot = scan_file(out / "food" / "index.html")
    assert foot.block_hrefs["designation-sources"] == [MATJIP["url"]]
    assert "군산시 문화관광 「군산맛집」 지정 현황(2026)" in foot.blocks["designation-sources"]
    assert CHECKED not in foot.blocks["designation-sources"]
    # search index, llms.txt (short) and llms-full.txt (label, list and its link — no 확인일)
    rows = {r["n"]: r for r in json.loads((out / "search" / "index.json").read_text("utf-8"))}
    assert rows["복성루"]["g"] == "군산맛집(2026, 군산시 지정) · 안심식당" and "g" not in rows["중화반점"]
    short = (out / "llms.txt").read_text("utf-8")
    assert re.search(r"- \[복성루\]\([^)]+\): .* 지정: 군산맛집 2026·안심식당\.$", short, re.M)
    full = (out / "llms-full.txt").read_text("utf-8")
    assert ("- 지정: 군산맛집(2026, 군산시 지정) (출처: 군산시 문화관광 「군산맛집」 지정 현황(2026) "
            "https://www.gunsan.go.kr/tour/m2555)") in full
    assert "확인일" not in full and CHECKED not in full
    assert dz_errors(data, out) == []


def test_search_js_matches_designations():
    js = (ROOT / "templates" / "assets" / "search.js").read_text("utf-8")
    assert 'row._g = norm(row.g)' in js and '"지정: "' in js


def test_a_low_or_needs_check_match_is_never_shown_and_is_an_error(tmp_path):
    flagged = {**MATJIP, "match": {"row_ref": "matjip_2026#19", "confidence": "low", "needs_check": True}}
    data, out = built(tmp_path, [food("dj", "대정소바", [flagged])])
    html = (out / "places" / "dj" / "index.html").read_text("utf-8")
    assert "군산맛집" not in html and 'class="dz' not in html and '"award"' not in html
    assert "dz-chip" not in (out / "food" / "index.html").read_text("utf-8")
    assert "지정" not in (out / "llms.txt").read_text("utf-8").split("## 음식점")[1]
    errors = dz_errors(data, out)
    assert any("대정소바" in x and "매칭 신뢰도가 low" in x for x in errors)
    assert any("needs_check" in x for x in errors)


def test_validator_catches_a_designation_without_its_list_link_or_with_its_date_on_the_page(tmp_path):
    data, out = built(tmp_path, [food("bok", "복성루", [MATJIP])])
    f = out / "places" / "bok" / "index.html"
    html = f.read_text("utf-8")
    assert dz_errors(data, out) == []
    # the '지정' row loses its list link, the chip loses its link
    f.write_text(html.replace(f'<span class="dz-s"><a href="{MATJIP["url"]}"', '<span class="dz-s"><a href="#"')
                 .replace(f'<a class="dz-c" href="{MATJIP["url"]}"', '<a class="dz-c" href="#"'), "utf-8")
    errors = dz_errors(data, out)
    assert any("'지정' 줄에 목록 이름·링크와 함께 없음" in x for x in errors)
    assert any("첫 화면 지정 칩에 목록 링크와 함께 없음" in x for x in errors)
    # the row shows the list's 확인일 again: an error (operator decision 2026-10-09 — data and JSON-LD only)
    f.write_text(html.replace(f'{MATJIP["source_name"]}</a></span></li>',
                              f'{MATJIP["source_name"]}</a> · <span class="tn">{CHECKED}</span> 확인</span></li>'), "utf-8")
    errors, _, _ = validate(data, out, "production")
    assert any(f"확인일({CHECKED})이 '지정' 줄에 보임" in x for x in errors), errors
    assert any("확인·갱신 날짜가 화면에 보임" in x and f"{CHECKED} 확인" in x for x in errors), errors


def test_validator_catches_an_award_the_data_does_not_hold_or_the_page_does_not_show(tmp_path):
    data, out = built(tmp_path, [food("bok", "복성루", [MATJIP])])
    f = out / "places" / "bok" / "index.html"
    html = f.read_text("utf-8")
    f.write_text(html.replace('"award":"군산맛집(2026, 군산시 지정)"', '"award":["군산맛집(2026, 군산시 지정)","백년가게"]'),
                 "utf-8")
    assert any("award가 표시할 수 있는 지정이 아님: 백년가게" in x for x in dz_errors(data, out))
    # a chip that is not on the page any more: award no longer visible
    f.write_text(re.sub(r'<p class="dz".*?</p>', "", html, flags=re.S)
                 .replace('<span class="dz-l">군산맛집(2026, 군산시 지정)</span>', '<span class="dz-l">군산맛집</span>'), "utf-8")
    errors = dz_errors(data, out)
    assert any("award가 화면에 없음: 군산맛집(2026, 군산시 지정)" in x for x in errors)
    assert any("구조화 데이터가 화면과 다름" in x and "award" in x for x in errors)


def test_validator_catches_a_list_page_without_the_chip_sources(tmp_path):
    data, out = built(tmp_path, [food("bok", "복성루", [MATJIP])])
    f = out / "food" / "index.html"
    html = f.read_text("utf-8")
    f.write_text(re.sub(r'<p class="note list-foot dz-foot".*?</p>', "", html, flags=re.S), "utf-8")
    assert any("목록(군산시 문화관광 「군산맛집」 지정 현황(2026)) 이름·링크가 지정 출처 줄에 없음" in x
               for x in dz_errors(data, out))
    # the source line with the list's 확인일 again: an error
    f.write_text(html.replace(f'{MATJIP["source_name"]}</a></p>', f'{MATJIP["source_name"]}</a> {CHECKED} 확인</p>'),
                 "utf-8")
    assert any(f"지정 출처 줄에 확인일({CHECKED})이 보임" in x for x in dz_errors(data, out))
