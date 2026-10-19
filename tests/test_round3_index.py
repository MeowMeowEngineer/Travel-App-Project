"""Round 3: index criteria, field-level provenance, alternateName, course distances, verification meta."""
import importlib.util
import json
import shutil
from pathlib import Path

from pipeline import schema
from pipeline.build import State, build, fact_alternatives, fmt_dist
from pipeline.enrich import haversine_m
from pipeline.validate import scan_file, validate

ROOT = Path(__file__).resolve().parent.parent
SAMPLE = ROOT / "data" / "sample"
spec = importlib.util.spec_from_file_location("quality_report", ROOT / "tools" / "quality_report.py")
qr = importlib.util.module_from_spec(spec)
spec.loader.exec_module(qr)

GOOD_SUMMARY = "근대관은 1층 해양물류역사관과 3층 근대생활관으로 나뉜 시립 박물관입니다. 월요일에 쉽니다."


def place(slug, name, summary, facts, **extra):
    return {"id": slug, "slug": slug, "name": name, "kind": "attraction", "tier": "basic", "status": "published",
            "reviewed_at": "2026-10-08", "themes": [], "summary": summary,
            "facts": {"address": "전북특별자치도 군산시 해망로 240", **facts},
            "facts_source": {"provider": "군산시 문화관광", "checked_at": "2026-10-08"},
            "original": {"source_name": "군산시 문화관광", "source_url": "https://www.gunsan.go.kr/tour",
                         "license": "NONE", "collected_at": "2026-10-05"}, **extra}


def data_with(tmp_path, places, site_changes=None):
    data = tmp_path / "data"
    shutil.copytree(SAMPLE, data)
    (data / "places.json").write_text(json.dumps(places, ensure_ascii=False), "utf-8")
    if site_changes:
        site = json.loads((data / "site.json").read_text("utf-8"))
        site.update(site_changes)
        (data / "site.json").write_text(json.dumps(site, ensure_ascii=False), "utf-8")
    return data


def index_errors(data, out, mode="production"):
    errors, _, stats = validate(data, out, mode)
    return [x for x in errors if "색인" in x or "noindex" in x], stats


def test_index_groups_match_quality_report():
    assert schema.INDEX_GROUPS == qr.GROUPS
    assert schema.INDEX_KIND_GROUPS == qr.KIND_GROUPS
    assert schema.INDEX_TAUT == qr.TAUT


def test_index_status_reasons():
    R = schema.INDEX_REASONS
    two = {"usetime": "09:00~18:00", "infocenter": "063-000-0000"}
    assert schema.index_status(place("a", "근대관", GOOD_SUMMARY, two)) == (True, [])
    ok, reasons = schema.index_status(place("b", "근대관", GOOD_SUMMARY, {"parking": "가능"}, reviewed_at=""))
    assert not ok and reasons == [R["groups"], R["unreviewed"]]
    taut = place("c", "근대관", "근대관은 군산시 장미동에 있는 박물관입니다.", two)
    assert schema.index_status(taut) == (False, [R["taut"]])
    # the first sentence is judged: a fact in a later sentence does not rescue a stock first sentence
    assert schema.summary_ok(place("c2", "근대관", "근대관은 군산시 장미동에 있는 박물관입니다. 월요일에 쉽니다.", two)) is False
    assert schema.summary_ok(place("c3", "근대관", "근대관은 1층 해양물류역사관과 3층 근대생활관을 둔 군산시 박물관입니다.", two))
    commentary = place("d", "근대관", "원문은 이곳을 군산 근대사의 출발점이라고 소개합니다.", two)
    assert schema.index_status(commentary) == (False, [R["commentary"]])
    assert schema.index_status(place("e", "근대관", "", two)) == (False, [R["no_summary"]])
    stay = dict(place("f", "호텔", "호텔은 객실 30개와 주차장 40면을 갖춘 숙소입니다.", {"checkin": "15:00", "parking": "가능"}), kind="stay")
    assert schema.index_status(stay) == (True, [])


def production_fixture(tmp_path):
    two = {"usetime": "09:00~18:00", "restdate": "월요일", "infocenter": "063-000-0000"}
    places = [
        place("good", "근대관", GOOD_SUMMARY, two),
        place("taut", "철길마을", "철길마을은 군산시 경암동에 있는 마을입니다.", two),
        place("thin", "작은공원", "작은공원은 호수 둘레 2km 산책로를 따라 벚나무가 심긴 공원입니다.", {"parking": "가능"}),
    ]
    data = data_with(tmp_path, places)
    out = tmp_path / "prod"
    stats = build(data, out, "production")
    return data, out, stats


def test_production_noindexes_pages_below_criteria_and_drops_them_from_sitemap_and_llms(tmp_path):
    data, out, stats = production_fixture(tmp_path)
    assert stats["index"]["indexable"] == 1 and stats["index"]["entity_pages"] == 3
    assert dict(stats["index"]["top_reasons"]) == {schema.INDEX_REASONS["taut"]: 1, schema.INDEX_REASONS["groups"]: 1}
    url = lambda slug: f"https://example.com/places/{slug}/"
    sitemap = (out / "sitemap.xml").read_text("utf-8")
    llms, full = (out / "llms.txt").read_text("utf-8"), (out / "llms-full.txt").read_text("utf-8")
    assert scan_file(out / "places/good/index.html").meta["robots"].startswith("index")
    assert url("good") in sitemap and url("good") in llms and url("good") in full
    for slug in ("taut", "thin"):
        assert scan_file(out / f"places/{slug}/index.html").meta["robots"] == "noindex, follow"
        assert url(slug) not in sitemap and url(slug) not in llms and url(slug) not in full
        # still reachable for visitors: lists and the map keep the page
        assert f"/places/{slug}/" in (out / "places/index.html").read_text("utf-8")
        assert f"/places/{slug}/" in (out / "map/index.html").read_text("utf-8")
    assert "색인" not in (out / "places/good/index.html").read_text("utf-8")   # reviewer note is preview-only
    errors, vstats = index_errors(data, out)
    assert errors == [] and vstats["index"]["indexable"] == 1


def test_validate_catches_index_mismatches(tmp_path):
    data, out, _ = production_fixture(tmp_path)
    good, taut = out / "places/good/index.html", out / "places/taut/index.html"
    good.write_text(good.read_text("utf-8").replace("index, follow, max-image-preview:large", "noindex, follow"), "utf-8")
    taut.write_text(taut.read_text("utf-8").replace('content="noindex, follow"', 'content="index, follow"'), "utf-8")
    sm = out / "sitemap.xml"
    sm.write_text(sm.read_text("utf-8").replace("https://example.com/places/good/", "https://example.com/places/thin/"), "utf-8")
    llms = out / "llms-full.txt"
    llms.write_text(llms.read_text("utf-8") + "\nURL: https://example.com/places/thin/\n", "utf-8")
    errors, _ = index_errors(data, out)
    text = "\n".join(errors)
    assert "[good 근대관] 색인 기준을 충족한 공개 페이지에 noindex" in text
    assert "[good 근대관] 색인 대상인데 sitemap.xml에 없음" in text
    assert "[taut 철길마을] 색인 기준 미달인데 noindex 없음" in text
    assert "[thin 작은공원] 색인 기준 미달인데 sitemap.xml에 있음" in text
    assert "[thin 작은공원] 색인 기준 미달인데 llms-full.txt에 있음" in text


def test_preview_keeps_index_note_out_of_sight_and_keeps_everything_listed(tmp_path):
    out = tmp_path / "preview"
    build(SAMPLE, out, "preview")
    assert 'data-index="색인 기준 충족"' in (out / "places/gyeongam-railroad-village/index.html").read_text("utf-8")
    eunpa = (out / "places/eunpa-lake-park/index.html").read_text("utf-8")
    assert 'data-index="색인 제외 예정: 유형별 필수 정보 2개 미만(하나도 없음)"' in eunpa
    assert "검수 전" not in eunpa and 'class="banner"' not in eunpa and "status-note" not in eunpa
    assert "/places/eunpa-lake-park/" in (out / "sitemap.xml").read_text("utf-8")   # preview is noindex anyway


def provenance_places():
    places = json.loads((SAMPLE / "places.json").read_text("utf-8"))
    p = places[0]
    p["facts"] = {"address": "전북특별자치도 군산시 경촌4길 14", "usetime": "09:00~18:00", "parking": "가능",
                  "infocenter": "063-000-0000"}
    p["facts_source"] = {"provider": "한국관광공사 TourAPI", "contentid": "1", "checked_at": "2026-10-08"}
    p["fact_sources"] = {"address": {"provider": "군산시 문화관광", "checked_at": "2026-10-07"}}
    p["fact_alternatives"] = {
        "usetime": [{"value": "10:00~17:00", "provider": "군산시 문화관광", "checked_at": "2026-10-07"}],
        "parking": [{"value": "주차장 없음", "provider": "시설 홈페이지", "checked_at": "2026-10-06"},
                    {"value": "가능", "provider": "중복 값", "checked_at": "2026-10-06"}],
    }
    p["alternate_names"] = ["군산 경암동 철길마을", "경암동철길마을"]
    return places


def test_differing_sources_show_both_values_with_providers(tmp_path):
    places = provenance_places()
    data = data_with(tmp_path, places)
    out = tmp_path / "preview"
    build(data, out, "preview")
    page = out / "places/gyeongam-railroad-village/index.html"
    facts = " ".join(scan_file(page).blocks["facts"].split())
    # values print through textutil.display_value (time ranges with '–'), round 3; llms-full keeps the source text.
    # Apple facts card (deliberate design change): each source is a caption row — provider and its note number —
    # over its own value; every conflicting row ends with its own '출처마다 다름 · 방문 전 전화 확인' line; per-field
    # sources are the note numbers on each value with the numbered provider list under the card. No 확인일 on the
    # page (operator decision 2026-10-09: CLAUDE.md 3.2 '확인일 화면 표시' → data and structured data only).
    for text in ("한국관광공사 TourAPI — 출처 1 09:00–18:00", "군산시 문화관광 — 출처 2 10:00–17:00",
                 "한국관광공사 TourAPI — 출처 1 가능", "시설 홈페이지 — 출처 3 주차장 없음"):
        assert text in facts, text
    assert not any(d in facts for d in ("2026-10-08", "2026-10-07", "2026-10-06")) and "확인일" not in facts
    assert facts.count("출처마다 다름 · 방문 전 전화 확인") == 2              # 이용시간, 주차
    assert "중복 값" not in facts                                     # same value from another source adds nothing
    assert "063-000-0000 — 출처 1" in facts and "전북특별자치도 군산시 경촌4길 14 — 출처 2" in facts
    assert "1한국관광공사 TourAPI2군산시 문화관광3시설 홈페이지" in facts
    full = (out / "llms-full.txt").read_text("utf-8")
    assert "- 이용시간: 09:00~18:00 (출처: 한국관광공사 TourAPI)" in full
    assert "- 주소: 전북특별자치도 군산시 경촌4길 14 (출처: 군산시 문화관광)" in full
    assert "- 이용시간(다른 출처 값): 10:00~17:00 (출처: 군산시 문화관광) — 출처마다 값이 달라 방문 전 전화 확인" in full
    assert "확인일" not in full
    errors, _, _ = validate(data, out, "preview")
    assert errors == [], errors
    # a template that drops the other value is caught
    page.write_text(page.read_text("utf-8").replace("주차장 없음", "").replace("방문 전 전화 확인", ""), "utf-8")
    errors, _, _ = validate(data, out, "preview")
    assert any("facts.parking: 출처마다 다른 값" in x for x in errors)
    assert any("'방문 전 전화 확인' 안내 없음" in x for x in errors)


def test_field_level_tourapi_source_brings_the_credit_line(tmp_path):
    places = json.loads((SAMPLE / "places.json").read_text("utf-8"))
    for p in places:
        p["facts_source"] = {"provider": "군산시 문화관광", "checked_at": "2026-10-08"}
    places[0]["fact_sources"] = {"usetime": {"provider": "한국관광공사 TourAPI", "checked_at": "2026-10-08"}}
    out = tmp_path / "preview"
    build(data_with(tmp_path, places), out, "preview")
    assert "관광 정보·사진: 한국관광공사 TourAPI" in (out / "llms.txt").read_text("utf-8")


def test_validator_forbids_visible_check_dates_but_keeps_event_and_timetable_dates(tmp_path):
    """Operator decision 2026-10-09 (rule change, CLAUDE.md 3.2 '확인일 화면 표시' → data and structured data only):
    no check / update / review / collection date on any page or in llms.txt / llms-full.txt
    (validate.visible_check_dates). Event dates, a timetable's 시행일, a schedule day, a source document's own date
    and a list's edition stay."""
    from pipeline.validate import visible_check_dates
    for keep in ("2026년 10월 9일(금)–10월 11일(일)", "2024.10.21 시행 시간표 기준",
                 "티머니 시외버스 운행정보 기준(2026-10-13 화요일 배차)", "군산시 보도자료 (행정지원과, 2026-10-06, 보도자료 번호 35137)",
                 "확인 필요: 요금·주차", "매년 6월 20일 전후", "이용 예정일 5일 전에 취소하면 전액",
                 "군산시 착한가격업소 목록(2025년 12월 기준)", "As of June 2026, 20 of the 141 places", "Oct 9 – Oct 11 2026",
                 "Gunsan City Culture and Tourism · rechecked with Korea Tourism Organization TourAPI"):
        assert visible_check_dates(keep) == [], keep
    for drop in ("정보 확인일 2026-10-08", "2026-10-08 확인", "메뉴와 영업시간은 2026-10-08에 확인했습니다.",
                 "요금과 시간은 2026년 10월 8일에 확인한 값입니다.", "요금은 우등 20,900원입니다(2026-10-08 조회).",
                 "2026. 10. 9. 기준 진행·예정 3건", "원문 수집일 2026-10-08", "검수일", "3일 전 업데이트", "Checked 2026-10-08",
                 "Fees and hours were checked on October 8, 2026.", "As of October 9, 2026",
                 "Translated into English 2026-10-08", "Updated 2 days ago"):
        assert visible_check_dates(drop), drop
    data = data_with(tmp_path, provenance_places())
    out = tmp_path / "preview"
    build(data, out, "preview")
    assert validate(data, out, "preview")[0] == []
    page = out / "places/gyeongam-railroad-village/index.html"
    page.write_text(page.read_text("utf-8").replace("</main>", "<p>정보 확인일 2026-10-08</p></main>"), "utf-8")
    llms = out / "llms.txt"
    llms.write_text(llms.read_text("utf-8") + "\n- 이용시간: 09:00~18:00 (출처: 한국관광공사 TourAPI, 확인일 2026-10-08)\n", "utf-8")
    errors = validate(data, out, "preview")[0]
    assert any("/places/gyeongam-railroad-village/index.html" in x and "확인·갱신 날짜가 화면에 보임" in x for x in errors), errors
    assert any(x.startswith("[llms.txt]") and "확인일" in x for x in errors), errors


def test_fact_alternatives_keep_only_distinct_values():
    e = {"fact_alternatives": {"usetime": [{"value": " 09:00~18:00 ", "provider": "A"}, {"value": "", "provider": "B"},
                                           {"value": "10:00~17:00", "provider": "C", "url": "www.example.org"}]}}
    alts = fact_alternatives(e, "usetime", "09:00~18:00")
    assert [(a["value"], a["provider"], a["url"]) for a in alts] == [("10:00~17:00", "C", "https://www.example.org")]


def test_alternate_name_in_jsonld_and_visible(tmp_path):
    data = data_with(tmp_path, provenance_places())
    out = tmp_path / "preview"
    build(data, out, "preview")
    page = out / "places/gyeongam-railroad-village/index.html"
    html = page.read_text("utf-8")
    graph = json.loads(html.split('<script type="application/ld+json">')[1].split("</script>")[0])["@graph"]
    node = next(n for n in graph if n.get("@type") == "TouristAttraction")
    assert node["alternateName"] == "군산 경암동 철길마을"            # the spacing variant of the name is dropped
    assert "다른 이름: 군산 경암동 철길마을" in html
    assert validate(data, out, "preview")[0] == []
    page.write_text(html.replace("다른 이름: 군산 경암동 철길마을", ""), "utf-8")
    assert any("alternateName이 화면에 없음" in x for x in validate(data, out, "preview")[0])


def test_course_shows_straight_line_distances(tmp_path):
    places = json.loads((SAMPLE / "places.json").read_text("utf-8"))
    by = {p["slug"]: p for p in places}
    by["gyeongam-railroad-village"]["geo"] = {"lat": 35.9800, "lng": 126.7200}
    by["chowon-photo-studio"]["geo"] = {"lat": 35.9890, "lng": 126.7110}
    data = data_with(tmp_path, places)
    out = tmp_path / "preview"
    build(data, out, "preview")
    html = " ".join((out / "courses/day-course-a/index.html").read_text("utf-8").split())
    leg = fmt_dist(round(haversine_m(35.98, 126.72, 35.989, 126.711)))
    assert leg == "1.3km"
    # Apple course page (r3-apple-p2, deliberate design change): each measured leg is on both station boards (the
    # next of stop 1, the previous of stop 2; the 3rd stop has no coordinates), the opening counts the measured legs,
    # the sources say how distances are measured — and the caution sentences are gone (owner: no caution copy)
    assert html.count(f'<span class="b-d tn">{leg}</span>') == 2
    assert '<dt>좌표 있는 구간</dt><dd class="tn">1/2</dd>' in html
    assert "경유지 사이 2구간 중 1구간을 한국관광공사 TourAPI 좌표 사이 직선으로 잼" in html
    assert "실제 이동 거리와 다릅니다" not in html and "실제 이동 경로가 아닙니다" not in html


def test_verification_meta_only_in_production_when_set(tmp_path):
    data = data_with(tmp_path, json.loads((SAMPLE / "places.json").read_text("utf-8")),
                     {"search_verification": {"google": "g-token", "bing": "b-token", "naver": ""}})
    for mode in ("preview", "production"):
        out = tmp_path / mode
        build(data, out, mode)
        meta = scan_file(out / "index.html").meta
        assert (meta.get("google-site-verification") == "g-token") == (mode == "production")
        assert (meta.get("msvalidate.01") == "b-token") == (mode == "production")
        assert "naver-site-verification" not in meta
    data2 = data_with(tmp_path / "unset", json.loads((SAMPLE / "places.json").read_text("utf-8")))
    build(data2, tmp_path / "prod-unset", "production")
    meta = scan_file(tmp_path / "prod-unset" / "index.html").meta
    assert not any(k in meta for k in ("google-site-verification", "msvalidate.01", "naver-site-verification"))


def test_collected_at_falls_back_to_latest_original_and_is_never_shown(tmp_path):
    # The footer / about / course index / llms.txt '원문 수집일' line is gone (operator decision 2026-10-09: no visible
    # check or collection dates). The date is still worked out (State.collected_at) and kept in the data.
    places = json.loads((SAMPLE / "places.json").read_text("utf-8"))
    places[1]["original"]["collected_at"] = "2026-10-09"
    site = {"source": {"name": "군산시 문화관광", "url": "https://www.gunsan.go.kr/tour", "collected_at": ""}}
    data = data_with(tmp_path, places, site)
    assert State(data, "preview").collected_at == "2026-10-09"
    out = tmp_path / "with"
    build(data, out, "preview")
    for name in ("llms.txt", "llms-full.txt"):
        assert "수집일" not in (out / name).read_text("utf-8")
    for page in ("index.html", "about/index.html", "courses/index.html"):
        if (out / page).exists():
            assert "수집일" not in scan_file(out / page).plain, page
    for p in places:
        p["original"].pop("collected_at", None)
    data = data_with(tmp_path / "none", places, site)
    assert State(data, "preview").collected_at == ""


def test_also_values_are_shown_without_the_call_note_but_conflicts_need_it():
    from pipeline.build import fact_alternatives
    e = {"facts": {"menu": "짬뽕", "usetime": "09:00~18:00"}, "facts_source": {"provider": "군산시 문화관광"},
         "fact_alternatives": {"menu": [{"value": "물짜장", "provider": "한국관광공사 TourAPI", "relation": "also"}],
                               "usetime": [{"value": "10:00~17:00", "provider": "한국관광공사 TourAPI"}]}}
    assert [a["also"] for a in fact_alternatives(e, "menu", "짬뽕")] == [True]
    assert [a["also"] for a in fact_alternatives(e, "usetime", "09:00~18:00")] == [False]


def test_source_links_are_named_after_the_page_they_open():
    from pipeline.build import source_labels
    e = {"original": {"source_url": "https://www.gunsan.go.kr/tour/m2080/view/1", "source_name": "군산시 문화관광"},
         "fact_sources": {"usetime": {"provider": "군산근대역사박물관 홈페이지", "url": "https://museum.gunsan.go.kr/a.jsp"}}}
    labels = source_labels(e)
    assert labels["https://museum.gunsan.go.kr/a.jsp"] == "군산근대역사박물관 홈페이지"
    assert labels["https://www.gunsan.go.kr/tour/m2080/view/1"] == "군산시 문화관광"


def test_owner_publication_approval_counts_for_index_but_is_not_shown_as_review():
    # 2026-10-08 the owner made the site public without per-page reviews: approved_at satisfies criterion (c),
    # but pages never show it as a 검수일 (review date)
    e = place("p1", "근대관", GOOD_SUMMARY, {"usetime": "09:00~18:00", "restdate": "매주 월요일"}, reviewed_at="",
              approved_at="2026-10-08")
    assert schema.index_status(e) == (True, [])
    e.pop("approved_at")
    assert schema.index_status(e)[0] is False
