"""Unit tests: text helpers, map links, TourAPI parsing, importer."""
import csv
import json

import pytest

from pipeline import importer
from pipeline.maplinks import build_links, precision_summary
from pipeline.textutil import (display_address, extract_phone, extract_phones, extract_url, first_sentence,
                               normalize_name, phone_domestic, phone_e164, phone_intl, phone_intl_shown, sha256_text,
                               slugify, strip_html)
from pipeline.tourapi import TourAPIError, parse_items


def test_strip_html_keeps_line_breaks():
    assert strip_html("09:00~18:00<br />매주 월요일 휴무&nbsp;") == "09:00~18:00\n매주 월요일 휴무"


def test_extract_url_from_anchor_and_text():
    assert extract_url('<a href="https://www.gunsan.go.kr" target="_blank">군산시</a>') == "https://www.gunsan.go.kr"
    assert extract_url("홈페이지 http://example.org/x 참고") == "http://example.org/x"
    assert extract_url("") == ""


def test_phone_and_names():
    assert extract_phone("문의 063-454-1234 (평일)") == "063-454-1234"
    assert normalize_name("신흥동 일본식 가옥(히로쓰 가옥)") == "신흥동일본식가옥"
    assert slugify("경암동 철길마을") == "경암동-철길마을"
    assert len(sha256_text("가")) == 64


def test_phone_extraction_never_truncates_or_merges():
    # P0-1: the old pattern turned 0507-1302-6070 into 07-1302-6070 and read two glued numbers as one
    assert extract_phone("0507-1302-6070") == "0507-1302-6070"
    assert extract_phone("1577-4050") == "1577-4050"
    assert extract_phone("063-443-1981063-443-4819") == ""
    assert extract_phone("군산시청 063-454-3337") == "063-454-3337"
    assert extract_phone("010-9267-4166") == "010-9267-4166"
    assert extract_phones("063-443-1981, 063-443-4819") == ["063-443-1981", "063-443-4819"]
    # P2-6: +82 form for markup, and back to the visible domestic form; a nationwide number has no +82 form (QA
    # 2026-10-15 SRC-05a: structured data keeps 1577-4050 as written)
    assert phone_intl("063-454-7870") == "+82-63-454-7870" and phone_intl("1577-4050") == "1577-4050"
    for n in ("063-454-7870", "0507-1302-6070", "010-9267-4166", "1577-4050"):
        assert phone_domestic(phone_intl(n)) == n


def test_phone_international_forms_only_for_numbers_that_answer_from_abroad():
    # QA 2026-10-15 SRC-05a: the +82 form a caller abroad dials; never for a domestic-only number
    assert phone_e164("063-454-7870") == "+82-63-454-7870"
    assert phone_e164("02-530-6311") == "+82-2-530-6311"
    assert phone_e164("010-4891-5402") == "+82-10-4891-5402"
    assert phone_e164("070-4064-1517") == "+82-70-4064-1517"
    assert phone_e164("0507-1394-3390") == "+82-507-1394-3390"
    for n in ("1577-4050", "1644-8774", "080-123-4567", "060-123-4567"):
        assert phone_e164(n) == "" and phone_intl(n) == n, n
    # the visible '+82 …' form: area codes, mobiles, 070 — not 0507 (reach from abroad unverified), 15xx, 080, 060
    assert phone_intl_shown("02-530-6311") == "+82 2-530-6311"
    assert phone_intl_shown("063-454-7870") == "+82 63-454-7870"
    assert phone_intl_shown("010-4891-5402") == "+82 10-4891-5402"
    assert phone_intl_shown("070-4064-1517") == "+82 70-4064-1517"
    for n in ("0507-1394-3390", "1577-4050", "080-123-4567", "060-123-4567", "050-123-4567"):
        assert phone_intl_shown(n) == "", n


def test_display_address_rewrites_only_the_province_prefix():
    assert display_address("전라북도 군산시 해망로 240") == "전북특별자치도 군산시 해망로 240"
    assert display_address("전북 군산시 평화길 123-5 (장미동)") == "전북특별자치도 군산시 평화길 123-5 (장미동)"
    assert display_address("전북 특별자치도 군산시 동국사길 16 (금광동)") == "전북특별자치도 군산시 동국사길 16 (금광동)"
    assert display_address("전북특별자치도 군산시 해망로 240") == "전북특별자치도 군산시 해망로 240"
    assert display_address("군산시 미장남로 111-5(미장동)") == "군산시 미장남로 111-5(미장동)"   # nothing derived
    assert display_address("  ") == "" and display_address(None) == ""


def test_first_sentence_korean():
    assert first_sentence("철길 옆 마을입니다. 산책하기 좋습니다.") == "철길 옆 마을입니다."
    assert first_sentence("") == ""


def test_links_without_geo_are_marked_search():
    links = build_links("경암동 철길마을", region="군산")
    assert all(not l["precise"] for l in links if l["role"] == "map")
    assert all("(검색)" in l["label"] for l in links if l["role"] == "map")
    assert precision_summary(links) == "none"
    assert not any(l["role"] == "route" for l in links)


def test_links_with_geo_and_ids_are_precise():
    links = build_links("경암동 철길마을", 35.98, 126.72, region="군산", address="군산시 경촌4길 14",
                        naver_place_id="123", google_place_id="ChIJabc")
    by = {l["key"]: l for l in links}
    assert by["naver"]["url"].endswith("/p/entry/place/123") and by["naver"]["precise"]
    assert "query_place_id=ChIJabc" in by["google"]["url"]
    assert by["kakao"]["url"].startswith("https://map.kakao.com/link/map/")
    assert "destination_place_id=ChIJabc" in by["google_route"]["url"]
    assert by["tmap"]["url"].startswith("tmap://route?")
    assert precision_summary(links) == "all"


def _payload(items, code="0000"):
    return {"response": {"header": {"resultCode": code, "resultMsg": "OK"},
                         "body": {"items": items, "numOfRows": 10, "pageNo": 1, "totalCount": 1}}}


def test_parse_items_shapes():
    assert parse_items(_payload({"item": [{"a": 1}, {"a": 2}]})) == [{"a": 1}, {"a": 2}]
    assert parse_items(_payload({"item": {"a": 1}})) == [{"a": 1}]
    assert parse_items(_payload("")) == []
    with pytest.raises(TourAPIError):
        parse_items(_payload("", code="22"))
    with pytest.raises(TourAPIError):
        parse_items({"unexpected": True})


def test_importer_merge_keeps_enrichment(tmp_path):
    data = tmp_path / "data"
    data.mkdir()
    (data / "site.json").write_text(json.dumps({"source": {"name": "군산시 문화관광"}}), "utf-8")
    existing = [{"id": "g-1", "name": "경암동 철길마을", "slug": "경암동-철길마을", "kind": "attraction", "status": "reviewed",
                 "summary": "기존 요약", "facts": {"usetime": "상시"}, "original": {"sha256": "old"}}]
    (data / "places.json").write_text(json.dumps(existing, ensure_ascii=False), "utf-8")
    csv_path = tmp_path / "in.csv"
    with open(csv_path, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=importer.COLUMNS)
        w.writeheader()
        w.writerow({"id": "g-1", "name": "경암동 철길마을", "kind": "attraction", "original_text": "새 원문",
                    "original_license": "KOGL-1", "collected_at": "2026-10-07", "source_url": "https://x"})
        w.writerow({"id": "g-2", "name": "경암동 철길마을", "kind": "attraction", "original_text": "다른 항목",
                    "original_license": "UNKNOWN"})
    assert importer.run(csv_path, data) == 0
    out = {e["id"]: e for e in json.loads((data / "places.json").read_text("utf-8"))}
    assert out["g-1"]["summary"] == "기존 요약" and out["g-1"]["facts"] == {"usetime": "상시"}
    assert out["g-1"]["status"] == "reviewed"            # review state is not reset by re-import
    assert out["g-1"]["original"]["text"] == "새 원문"
    assert out["g-2"]["slug"] == "경암동-철길마을-2"         # unique slug fixed at import time
