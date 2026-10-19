import csv
import hashlib
import json

import pytest

from tools.question_coverage import assess_question, course_candidates, guide_candidates, run, source_documents


def question(ident):
    return {"id": ident, "group": ident[0], "question": ident + " 검토 질문"}


def place(name, text, slug="place-1"):
    return {"name": name, "slug": slug, "original": {"text": text,
            "source_url": "https://www.gunsan.go.kr/tour/m2080/view/1", "license": "NONE"}}


def course(page="m2135", text="공식 코스\n첫 장소\n둘째 장소", name="A코스"):
    return {"name": name, "source_url": f"https://www.gunsan.go.kr/tour/{page}",
            "original": {"text": text, "source_url": f"https://www.gunsan.go.kr/tour/{page}", "license": "NONE"},
            "stops": [{"name": "첫 장소"}, {"name": "둘째 장소"}]}


def test_name_or_course_stop_match_does_not_supply_operational_answers():
    places = [place("경암동 철길마을", "경암동 철길마을은 마을이다.", "rail")]
    courses = course_candidates([course(text="근대역사박물관\n경암동 철길마을\n숙소\n이성당")])
    for ident in ("N03", "N17", "N18", "N25", "N29", "N30", "P01", "P03"):
        result = assess_question(question(ident), places, courses)
        assert result["answer_status"] == "미확인"
        assert result["missing"]
    assert assess_question(question("N18"), places, courses)["candidate_slugs"] == ["rail"]


def test_compound_description_and_fee_question_stays_partial():
    source = "\n경암동 철길마을은 철로 주변의 마을이다.\n"
    result = assess_question(question("N01"), [place("경암동 철길마을", source)], [])
    assert result["answer_status"] == "일부"
    assert "입장료" in result["missing"][0]
    assert result["evidence"][0]["quote"] in source


def test_official_day_course_satisfies_day_course_but_not_car_free_trip():
    courses = course_candidates([course()])
    assert assess_question(question("N09"), [], courses)["answer_status"] == "답충분"
    assert assess_question(question("P02"), [], courses)["answer_status"] == "답충분"
    assert assess_question(question("N14"), [], courses)["answer_status"] == "미확인"
    assert guide_candidates([], courses)[0]["candidates"] == []


def test_source_period_and_missing_third_day_are_checked_separately():
    courses = course_candidates([course("m2136", "1일차\n첫 장소\n2일차\n둘째 장소"),
                                 course("m2137", "1일차\n첫 장소\n2일차\n둘째 장소", "2박 3일 코스")])
    assert assess_question(question("N10"), [], courses)["answer_status"] == "답충분"
    result = assess_question(question("N13"), [], courses)
    assert result["answer_status"] == "일부"
    assert "3일차" in result["missing"][0]


def test_film_night_autumn_require_explicit_source_text():
    records = [place("초원사진관", "영화의 촬영 장소이다.", "studio"),
               place("은파호수공원", "음악분수와 함께 야경을 연출한다.", "lake"),
               place("월명공원", "가을에는 아름다운 단풍이 보인다.", "park")]
    for ident in ("N23", "N24", "N26"):
        result = assess_question(question(ident), records, [])
        assert result["answer_status"] == "답충분"
        assert result["evidence"]
    for ident in ("N23", "N24", "N26"):
        assert assess_question(question(ident), [place("명소", "관광지 소개")], [])["answer_status"] == "미확인"


def test_guide_candidates_do_not_infer_indoor_from_museum_or_private_house_from_hotel():
    source = "어린이들의 체험학습의 \n장으로 활용한다. 영상관이 있다. 관광호텔이 있다."
    candidates = guide_candidates([place("진포해양공원", source, "jinpo")], course_candidates([course()]))
    by_name = {g["name"]: g for g in candidates}
    assert by_name["아이와 함께"]["candidates"][0]["slug"] == "jinpo"
    assert by_name["아이와 함께"]["candidates"][0]["quote"] in source
    assert by_name["비 오는 날"]["candidates"] == []
    assert by_name["독채 숙소 고르기"]["candidates"] == []
    assert by_name["차 없는 당일여행"]["candidates"] == []


def test_existing_course_slug_reused_by_source_and_name():
    raw = course()
    imported = [{"name": "A코스", "slug": "stable-course", "original": raw["original"]}]
    mapped = course_candidates([raw], imported)[0]
    assert mapped["slug"] == "stable-course"
    assert mapped["slug_registered"] is True


def test_period_limited_citytour_notice_is_partial_without_registered_page():
    samples = [{"name": "2026년 추석 연휴 맞이 시티투어버스 특별 증차 운행!",
                "source_url": "https://www.gunsan.go.kr/tour/m2172/view/9834787",
                "original_text": "2026년 추석 연휴를 맞아 시티투어버스를 특별 증차 운행합니다.\n",
                "original_license": "NONE"}]
    result = assess_question(question("N19"), [], [], samples)
    assert result["answer_status"] == "일부"
    assert result["candidate_slugs"] == []
    assert result["evidence"][0]["quote"] in samples[0]["original_text"]
    assert "현재 운행 여부" in result["missing"][0]
    assert "2026년 추석" in result["evidence"][0]["name"]


def test_reports_keep_n_p_separate_preserve_inputs_and_omit_u(tmp_path):
    data = tmp_path / "data"
    data.mkdir()
    original = [place("경암동 철길마을", "경암동 철길마을은 마을이다.")]
    places_path = data / "places.json"
    places_path.write_text(json.dumps(original, ensure_ascii=False), "utf-8")
    raw = tmp_path / "courses.json"
    raw.write_text(json.dumps([course()], ensure_ascii=False), "utf-8")
    questions = tmp_path / "questions.csv"
    with questions.open("w", encoding="utf-8-sig", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=["id", "group", "question"])
        writer.writeheader()
        writer.writerows(question(f"N{i:02d}") for i in range(1, 31))
        writer.writerows(question(f"P{i:02d}") for i in range(1, 4))
        writer.writerow(question("U01"))
    before = {p: hashlib.sha256(p.read_bytes()).digest() for p in (places_path, raw, questions)}
    reports = tmp_path / "reports"
    results = run(questions, data, raw, reports)
    assert len(results) == 33
    assert sum(r["group"] == "N" for r in results) == 30
    assert sum(r["group"] == "P" for r in results) == 3
    assert all(hashlib.sha256(p.read_bytes()).digest() == digest for p, digest in before.items())
    md = (reports / "question_coverage.md").read_text("utf-8")
    assert "N 核心" not in md
    assert "N 핵심 30문항" in md and "P 플랫폼 제외 3문항" in md
    assert "U01" not in md
    assert (reports / "guide_candidates.md").exists()


def test_changed_question_ids_require_review_instead_of_silent_remapping(tmp_path):
    questions = tmp_path / "questions.csv"
    questions.write_text("id,group,question\nN01,N,원문 질문\n", "utf-8")
    with pytest.raises(ValueError, match="fixed N30/P3"):
        run(questions, tmp_path, tmp_path / "missing.json", tmp_path / "reports")


def test_collected_dongguksa_and_mallaengi_originals_replace_stale_no_source_claims():
    # Exact excerpts observed in the saved 2026-10-08 source records.
    temple = "대웅전은 건축 자재를 일본에서 가져와 지었으며, 우리나라의 전통 사찰과 달리 승려들의 거처인 요사와 복도로 연결된 것이 특징이다."
    village = "산비탈에 위치한 말랭이 마을에는 예술인 레지던스 9동과 전시관 8동이 조성되어 있으며 골목길 곳곳에 그려진 벽화가 볼거리를 제공해주고 있다."
    originals = [place("동국사", temple, "동국사"), place("말랭이 마을", village, "말랭이-마을")]
    for ident, text, slug in (("N05", temple, "동국사"), ("N08", village, "말랭이-마을")):
        result = assess_question(question(ident), originals, [])
        assert result["answer_status"] == "답충분" and not result["missing"]
        assert result["candidate_slugs"] == [slug]
        assert result["evidence"][0]["quote"] in text


def test_verified_address_fact_resolves_location_but_unsourced_address_does_not():
    studio = place("초원사진관", '영화 "8월의 크리스마스"의 촬영 장소이다.', "studio")
    studio["facts"] = {"address": "전북특별자치도  군산시 구영2길 12-1 (신창동)"}
    assert assess_question(question("N02"), [studio], [])["answer_status"] == "일부"
    studio["facts_source"] = {"provider": "군산시 문화관광", "checked_at": "2026-10-08"}
    result = assess_question(question("N02"), [studio], [])
    assert result["answer_status"] == "답충분"
    assert any(e.get("source_field") == "facts.address" for e in result["evidence"])


def test_actual_museum_conflicting_source_hours_remain_insufficient():
    original = "(3월~10월) 09:00 ~ 18:00\n(11월~2월) 09:00 ~ 17:00\n매주 월요일 휴관"
    documents = source_documents([{"name": "근대역사박물관", "original_text": original,
        "source_url": "https://www.gunsan.go.kr/tour/m2080/view/305395",
        "source_fields": [{"label": "이용시간", "value": "09:00~21:00(입장마감 20:30)"}]}], "raw_detail_source")
    result = assess_question(question("N03"), [], [], documents=documents)
    assert result["answer_status"] == "일부"
    assert any("상충을 확인함" in missing for missing in result["missing"])
    assert any(e["source_type"] == "raw_source_field" for e in result["evidence"])


def test_collected_citytour_static_page_is_evidence_without_claiming_live_operations():
    documents = source_documents([{"name": "시티투어 소개",
        "source_url": "https://www.gunsan.go.kr/tour/m2102",
        "original_text": "군산 시티투어는 사전예약을 통해 운영하고\r\n                있습니다.",
        "original_license": "NONE"}], "static_source")
    result = assess_question(question("N19"), [], [], documents=documents)
    assert result["answer_status"] == "일부" and result["candidate_slugs"] == []
    assert result["evidence"][0]["source_type"] == "static_source"
    assert result["evidence"][0]["slug_registered"] is False
    assert "현재 운행 여부" in result["missing"][0]
    assert not any("안내 원문 미확인" in m for m in result["missing"])


def test_collected_seonyu_traffic_is_partial_not_unsupported_or_current_confirmation():
    text = "신시도 새만금광장 – 무녀도 – 선유도 – 장자도 까지 자동차로 진입 가능하나\n주차장이 협소하오니 참고하시어 불편함이 없으시기 바랍니다."
    documents = source_documents([{"name": "교통안내", "original_text": text,
        "source_url": "https://www.gunsan.go.kr/tour/m2197"}], "static_source")
    result = assess_question(question("N15"), [], [], documents=documents)
    assert result["answer_status"] == "일부"
    assert result["evidence"][0]["quote"] in text
    assert result["missing"]


def test_editorial_summary_faq_never_supply_missing_raw_evidence():
    item = place("동국사", "자료")
    item.update(summary="대웅전과 사찰이 있다.", faq=[{"q": "어떤 절?", "a": "대웅전이 있다."}])
    assert assess_question(question("N05"), [item], [])["answer_status"] == "미확인"


def test_explicit_indoor_closure_is_evidence_but_never_rain_guide_candidate():
    text = "문화재 보호를 위하여 실내 개방은 하지 않습니다."
    originals = [place("군산신흥동일본식가옥(히로쓰가옥)", text)]
    result = assess_question(question("N04"), originals, [])
    assert result["answer_status"] == "일부"
    assert result["evidence"][0]["quote"] == text
    assert guide_candidates(originals, [])[2]["candidates"] == []


def test_run_reads_raw_auxiliary_documents_without_modifying_them(tmp_path):
    data, raw, reports = tmp_path / "data", tmp_path / "raw", tmp_path / "reports"
    data.mkdir()
    raw.mkdir()
    (data / "places.json").write_text("[]")
    raw_courses = tmp_path / "courses.json"
    raw_courses.write_text("[]")
    auxiliary = raw / "static_documents.json"
    auxiliary.write_text(json.dumps({"documents": [{"name": "시티투어 소개", "original_text": "군산 시티투어는 사전예약으로 운영합니다.",
                                                   "source_url": "https://www.gunsan.go.kr/tour/m2102"}]}))
    questions = tmp_path / "questions.csv"
    with questions.open("w", newline="", encoding="utf-8") as stream:
        writer = csv.DictWriter(stream, fieldnames=["id", "group", "question"])
        writer.writeheader()
        writer.writerows(question(f"N{i:02d}") for i in range(1, 31))
        writer.writerows(question(f"P{i:02d}") for i in range(1, 4))
        writer.writerow(question("U01"))
    before = {p: p.read_bytes() for p in (auxiliary, questions, raw_courses, data / "places.json")}
    results = run(questions, data, raw_courses, reports, raw_dir=raw)
    assert len(results) == 33 and all(r["group"] in ("N", "P") for r in results)
    assert next(r for r in results if r["id"] == "N19")["evidence"]
    assert all(p.read_bytes() == content for p, content in before.items())
    assert "공개 페이지 slug 미등록" in (reports / "question_coverage.md").read_text("utf-8")
