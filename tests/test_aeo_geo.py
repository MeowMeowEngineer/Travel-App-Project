"""AEO/GEO spec (docs/handover/aeo_geo_spec.md): markup equals visible text, honest dates, answer-first titles,
event leaf pages, typed values only from exact source strings, production URL gate."""
import datetime as real_dt
import json
import re
import shutil
from pathlib import Path

from pipeline import build as build_mod
from pipeline import jsonld, schema
from pipeline.build import State, build, course_title
from pipeline.validate import scan_file, validate

ROOT = Path(__file__).resolve().parent.parent
SAMPLE = ROOT / "data" / "sample"
SITE = {"locality": "군산시", "region_admin": "전북특별자치도"}


def data_with(tmp_path, places=None, events=None, site=None, name="data"):
    data = tmp_path / name
    shutil.copytree(SAMPLE, data)
    if places is not None:
        (data / "places.json").write_text(json.dumps(places, ensure_ascii=False), "utf-8")
    if events is not None:
        (data / "events.json").write_text(json.dumps(events, ensure_ascii=False), "utf-8")
    if site:
        cfg = json.loads((data / "site.json").read_text("utf-8"))
        cfg.update(site)
        (data / "site.json").write_text(json.dumps(cfg, ensure_ascii=False), "utf-8")
    return data


def nodes(path: Path) -> list[dict]:
    out = []
    for raw in scan_file(path).jsonld_raw:
        doc = json.loads(raw)
        out += doc.get("@graph", [doc])
    return out


def place_node(path: Path) -> dict:
    return next(n for n in nodes(path) if str(n.get("@id", "")).endswith("#place"))


def sample_places():
    return json.loads((SAMPLE / "places.json").read_text("utf-8"))


# ---------------------------------------------------------------- P0-2 labels
def test_stroller_and_card_labels_stay_true_out_of_context(tmp_path):
    assert schema.FACT_LABELS["babycarriage"] == "유모차 대여" and schema.FACT_LABELS["creditcard"] == "신용카드 결제"
    out = tmp_path / "s"
    build(SAMPLE, out, "sample")
    assert "<dt>유모차 대여</dt>" in (out / "places/gyeongam-railroad-village/index.html").read_text("utf-8")
    assert not any("<dt>유모차</dt>" in p.read_text("utf-8") for p in out.rglob("*.html"))


# ---------------------------------------------------------------- P0-4 dates
def test_dates_come_from_data_never_from_the_build_clock(tmp_path, monkeypatch):
    real = tmp_path / "real"
    build(SAMPLE, real, "sample")

    class Future(real_dt.date):
        @classmethod
        def today(cls):
            return cls(2099, 1, 1)

    monkeypatch.setattr(build_mod.dt, "date", Future)
    fake = tmp_path / "fake"
    build(SAMPLE, fake, "sample")
    sitemap = (fake / "sitemap.xml").read_text("utf-8")
    assert "2099" not in sitemap
    assert sitemap == (real / "sitemap.xml").read_text("utf-8")
    # dateModified / lastReviewed stay in JSON-LD as ISO dates and are never shown on the page (operator decision
    # 2026-10-09: check dates in the data and structured data only — rule change, P0-3 no longer asks for them on screen)
    errors, _, _ = validate(SAMPLE, fake, "sample")
    assert errors == [], errors
    page = fake / "places/gyeongam-railroad-village/index.html"
    web = next(n for n in nodes(page) if n["@type"] == "WebPage")
    assert web["dateModified"] == "2026-10-08" and web["lastReviewed"] == "2026-10-08"
    assert "2026-10-08" not in scan_file(page).visible


def test_unknown_dates_leave_out_lastmod(tmp_path):
    places = sample_places()
    for p in places:
        p.pop("reviewed_at", None)
        p["facts_source"] = {"provider": "군산시 문화관광"}
        p.pop("fact_sources", None)
    data = data_with(tmp_path, places, events=[])
    out = tmp_path / "p"
    build(data, out, "preview")
    sm = (out / "sitemap.xml").read_text("utf-8")
    assert "<loc>https://example.com/places/eunpa-lake-park/</loc></url>" in sm   # no date known -> no lastmod
    assert "<loc>https://example.com/courses/day-course-a/</loc><lastmod>2026-10-08</lastmod>" in sm


# ---------------------------------------------------------------- P1-1 titles and descriptions
def test_titles_carry_present_facts_and_descriptions_answer(tmp_path):
    out = tmp_path / "s"
    build(SAMPLE, out, "sample")
    gy = scan_file(out / "places/gyeongam-railroad-village/index.html")
    assert gy.title == "군산 경암동 철길마을 이용시간·주차 | 군산 여행 · WebforAI (샘플)"  # usetime + parking; <title> ends with site_name
    assert "요금" not in gy.title and "쉬는 날" not in gy.title             # no usefee / restdate in data
    stay = scan_file(out / "places/sample-stay-a/index.html")
    assert "체크인" in stay.title and "주차" in stay.title
    assert build_mod.TITLE_LABELS["usetime_restdate"] == "영업시간"     # the food row is 영업시간·정기휴일
    for slug in ("gyeongam-railroad-village", "chowon-photo-studio"):
        desc = scan_file(out / f"places/{slug}/index.html").meta["description"]
        assert 40 <= len(desc) <= 160, desc
    for page in out.rglob("*.html"):
        assert "방문 전 확인 정보와 길찾기, 함께 갈 곳을 정리했습니다" not in page.read_text("utf-8")
    assert scan_file(out / "places/index.html").meta["description"].startswith("군산 관광지를 ")
    assert scan_file(out / "stays/index.html").meta["description"].startswith("군산 숙소를 ")


def test_conflicting_values_stay_out_of_the_description(tmp_path):
    places = sample_places()
    p = places[1]
    p["facts"].update(restdate="매주 월요일", parkingfee="무료")
    p["fact_alternatives"] = {"restdate": [{"value": "연중무휴", "provider": "한국관광공사 TourAPI"}]}
    out = tmp_path / "p"
    build(data_with(tmp_path, places), out, "preview")
    desc = scan_file(out / f"places/{p['slug']}/index.html").meta["description"]
    assert "매주 월요일" not in desc and "연중무휴" not in desc


# ---------------------------------------------------------------- P1-4 events
EVENTS = [
    {"id": "ev-2026", "status": "published", "name": "군산시간여행축제", "start_date": "2026-10-02",
     "end_date": "2026-10-05", "place_name": "구·시청광장 및 시간여행마을 일원", "address": "전라북도 군산시 중앙로1가 11-1",
     "geo": {"lat": 35.987791, "lng": 126.711671}, "fee": "무료", "sponsor": "군산시", "tel": "063-454-3300",
     "homepage": "https://festival.gunsan.go.kr/", "playtime": "10:00~21:00", "summary": "",
     "source_name": "한국관광공사 TourAPI", "source_url": "", "checked_at": "2026-10-08", "question_ids": ["N27"]},
    {"id": "ev-2025", "status": "published", "name": "2025 군산시간여행축제", "period_text": "2025. 10. 9.(목) ~ 10. 12.(일) 4일간",
     "start_date": "2025-10-09", "end_date": "2025-10-12", "place_name": "시간여행마을 권역 일원", "address": "",
     "source_name": "군산시 문화관광", "source_url": "https://www.gunsan.go.kr/tour/m2101/view/306508",
     "checked_at": "2026-10-07"},
    {"id": "ev-yearly", "status": "published", "name": "군산꽁당보리축제", "period_text": "매년 5월", "start_date": "",
     "end_date": "", "place_name": "국제문화마을 앞들", "source_name": "군산시 문화관광",
     "source_url": "https://www.gunsan.go.kr/tour/m2101/view/306505", "checked_at": "2026-10-08"},
]


def test_event_series_get_leaf_pages_with_one_marked_up_edition(tmp_path):
    data = data_with(tmp_path, events=EVENTS)
    out = tmp_path / "s"
    stats = build(data, out, "sample")
    assert stats["event_pages"] == 1
    leaf = out / "events/군산시간여행축제/index.html"
    events = [n for n in nodes(leaf) if n["@type"] == "Event"]
    assert len(events) == 1
    ev = events[0]
    assert ev["name"] == "2026 군산시간여행축제" and ev["startDate"] == "2026-10-02" and ev["endDate"] == "2026-10-05"
    assert ev["url"] == scan_file(leaf).canonical == "https://example.com/events/%EA%B5%B0%EC%82%B0%EC%8B%9C%EA%B0%84%EC%97%AC%ED%96%89%EC%B6%95%EC%A0%9C/"
    assert ev["isAccessibleForFree"] is True and ev["organizer"]["name"] == "군산시"
    assert ev["location"]["address"]["addressRegion"] == "전북특별자치도" and ev["sameAs"] == "https://festival.gunsan.go.kr/"
    assert "eventStatus" not in ev and "image" not in ev
    page = scan_file(leaf)
    assert "2026-10-02" in page.datetimes and "2026-10-05" in page.datetimes
    text = page.body
    assert "2026 군산시간여행축제 기간: 2026년 10월 2일(금) ~ 10월 5일(월) · 장소: 구·시청광장 및 시간여행마을 일원" in text
    # Apple event page (r3-apple-p2): the time range is shown the way place pages show one (textutil.dash_times)
    for shown in ("10:00–21:00", "요금 무료", "주최 군산시", "063-454-3300", "festival.gunsan.go.kr", "출처 한국관광공사 TourAPI"):
        assert shown in text, shown
    # the source stays, its 확인일 does not (operator decision 2026-10-09)
    assert "확인일" not in text and "2026-10-08" not in text
    assert "지난 회차" in text and "2025 군산시간여행축제" in text          # past edition shown, not marked up
    assert not (out / "events/군산꽁당보리축제").exists()                 # no dated record, no leaf
    index = out / "events/index.html"
    assert not [n for n in nodes(index) if n["@type"] == "Event"]
    items = next(n for n in nodes(index) if n["@type"] == "ItemList")["itemListElement"]
    assert [i["url"] for i in items] == [ev["url"]]
    idx = scan_file(index).body
    assert "2026년 10월" in idx and "2025년 10월" in idx  # no aggregate check-date line on the index (owner, 2026-10-08)
    assert "이번 달" not in idx and "다가오는" not in idx
    assert "매년 5월" in idx
    sm = (out / "sitemap.xml").read_text("utf-8")
    assert ev["url"] + "</loc><lastmod>2026-10-08</lastmod>" in sm
    errors, _, _ = validate(data, out, "sample")
    assert errors == [], errors


def test_event_place_links_both_ways_and_no_invented_location(tmp_path):
    events = [dict(EVENTS[0], place_slug="eunpa-lake-park"), EVENTS[1]]
    data = data_with(tmp_path, events=events)
    out = tmp_path / "s"
    build(data, out, "sample")
    leaf = out / "events/군산시간여행축제/index.html"
    text = scan_file(leaf).body
    assert "군산시간여행축제가 열리는 곳" in text                      # particle, not '축제 열리는 곳'
    assert "열린 달" not in scan_file(out / "events/index.html").body   # no past tense over future editions
    place = (out / "places/eunpa-lake-park/index.html").read_text("utf-8")
    assert "이곳에서 열리는 행사" in place and 'href="/events/군산시간여행축제/"' in place
    assert validate(data, out, "sample")[0] == []
    # a record with neither place name nor address gets no location (its own title is not a place)
    bare = dict(EVENTS[0], place_name="", address="", _title="2026 군산시간여행축제")
    node = jsonld.event_graph(bare, "https://x/events/a/", [], SITE)["@graph"][0]
    assert "location" not in node


def test_event_leaf_shows_programme_usual_timing_and_differing_values(tmp_path):
    alt = {"value": "구 시청광장 특설무대 일대", "source_name": "군산시 보도자료 '개막' (보도자료 번호 1)",
           "source_url": "https://eminwon.gunsan.go.kr/list", "checked_at": "2026-10-08"}
    soon = (real_dt.date.today() + real_dt.timedelta(days=30)).isoformat()
    events = [dict(EVENTS[0], series="군산시간여행축제", highlights=["개막 퍼포먼스와 시간여행 콘서트"],
                   usual=[{"text": "2027년 일정은 아직 발표되지 않았습니다."}],
                   alternatives={"place_name": [alt]}), EVENTS[1],
              {"id": "ev-next", "status": "published", "name": "2099 군산짬뽕페스티벌", "start_date": soon,
               "end_date": soon, "place_name": "백년광장 일원", "source_name": "군산시 문화관광",
               "source_url": "https://www.gunsan.go.kr/tour/m2101/view/1", "checked_at": "2026-10-08"},
              {"id": "ev-yearly-ttf", "status": "published", "name": "군산시간여행축제", "series": "군산시간여행축제",
               "period_text": "매년 10월", "start_date": "", "end_date": "", "place_name": "시간여행마을 일원",
               "source_name": "군산시 문화관광", "source_url": "https://www.gunsan.go.kr/tour/m2101/view/2",
               "checked_at": "2026-10-08"}]
    data = data_with(tmp_path, events=events)
    out = tmp_path / "s"
    build(data, out, "sample")
    text = scan_file(out / "events/군산시간여행축제/index.html").body
    order = ["군산시간여행축제 주요 프로그램", "개막 퍼포먼스와 시간여행 콘서트", "군산시간여행축제는 보통 언제 열리나",
             "매년 10월 · 장소: 시간여행마을 일원",      # a '매년 …' record keeps the place its source gives
             "2027년 일정은 아직 발표되지 않았습니다.", "군산시간여행축제 지난 회차",
             "출처마다 다르게 적힌 값", "구 시청광장 특설무대 일대", "보도자료 번호 1", "방문 전 주최 측 확인"]
    pos = 0
    for s in order:             # each block after the previous one
        assert s in text[pos:], s
        pos = text.index(s, pos)
    # the index lists editions still to come apart from finished ones
    idx = scan_file(out / "events/index.html").body
    current, past = idx.index("진행 중이거나 열릴 예정인 행사"), idx.index("지난 행사")
    assert current < idx.index("2099 군산짬뽕페스티벌") < past < idx.index("2025 군산시간여행축제")
    assert validate(data, out, "sample")[0] == []


# ---------------------------------------------------------------- P1-5 / P2-2 / P2-6 typed values
def entity(**facts):
    return {"name": "해망굴", "kind": "attraction", "category": "관광지", "facts": facts}


def test_free_entry_only_for_an_exact_free_fee():
    node = lambda fee: jsonld.entity_node(entity(usefee=fee), SITE, "https://x", "https://x/p/", [], [])
    assert node("무료")["isAccessibleForFree"] is True
    for fee in ("무료 (일부 유료)", "없음", "", "성인 2,000원"):
        assert "isAccessibleForFree" not in node(fee), fee
    e = entity(usefee="무료")
    e["fact_alternatives"] = {"usefee": [{"value": "성인 1,000원", "provider": "다른 출처"}]}
    assert "isAccessibleForFree" not in jsonld.entity_node(e, SITE, "https://x", "https://x/p/", [], [])


def test_opening_hours_only_from_strict_strings():
    oh = jsonld.opening_hours
    spec = oh("09:00~18:00", "매주 월요일")
    assert spec == [{"@type": "OpeningHoursSpecification", "dayOfWeek": list(jsonld.DAYS[1:]),
                     "opens": "09:00", "closes": "18:00"}]
    assert oh("10:00 ~ 21:30", "연중무휴")[0]["dayOfWeek"] == list(jsonld.DAYS)
    assert oh("9:00~18:00", "매주 일요일")[0]["opens"] == "09:00"
    seasons = oh("3~10월 09:00~18:00 / 11~2월 09:00~17:00", "매주 월요일")
    assert [(s["validFrom"], s["validThrough"], s["closes"]) for s in seasons] == [
        ("--03-01", "--10-31", "18:00"), ("--11-01", "--02-29", "17:00")]
    for usetime, rest in (("상시 개방", "연중무휴"), ("09:00~18:00(입장마감 17:30)", "매주 월요일"),
                          ("[하절기]08:00~19:00[동절기]08:00~18:00", "연중무휴"), ("09:00~18:00", "매주 월요일, 1월 1일"),
                          ("09:00~18:00", "연중 무휴"), ("09:00~18:00", "연중휴무"), ("17:00~02:00", "연중무휴"),
                          ("09:00~18:00", ""), ("00:00~24:00", "연중무휴"), ("09:00~18:75", "연중무휴"),
                          ("3~10월 09:00~24:00 / 11~2월 09:00~17:00", "매주 월요일")):
        assert oh(usetime, rest) == [], (usetime, rest)
    e = entity(usetime="09:00~18:00", restdate="연중무휴")
    node = jsonld.entity_node(e, SITE, "https://x", "https://x/p/", [], [])
    assert node["openingHoursSpecification"] and "이용시간" not in [p["name"] for p in node.get("additionalProperty", [])]
    e["fact_alternatives"] = {"usetime": [{"value": "10:00~17:00", "provider": "다른 출처"}]}
    node = jsonld.entity_node(e, SITE, "https://x", "https://x/p/", [], [])
    # additionalProperty carries the value as the page prints it (textutil.display_value: '~' -> '–'), round 3
    assert "openingHoursSpecification" not in node and node["additionalProperty"][0]["value"] == "09:00–18:00"


def test_no_amenity_when_sources_differ_on_stroller_rental():
    """QA 2026-10-15 F02: a homepage's '대여 가능(…)' against TourAPI '없음' is no typed amenity either way."""
    e = entity(babycarriage="대여 가능(예약 없이 박물관 안내소에서)", parking="가능")
    e["fact_alternatives"] = {"babycarriage": [{"value": "없음", "provider": "한국관광공사 TourAPI"}]}
    names = [f["name"] for f in jsonld.entity_node(e, SITE, "https://x", "https://x/p/", [], [])["amenityFeature"]]
    assert names == ["주차"]
    e["facts"]["babycarriage"] = "있음"   # even a plain yes/no main value stays untyped while another source differs
    names = [f["name"] for f in jsonld.entity_node(e, SITE, "https://x", "https://x/p/", [], [])["amenityFeature"]]
    assert names == ["주차"]


def test_amenities_only_from_yes_no_values():
    node = jsonld.entity_node(entity(parking="가능", babycarriage="없음", pet="5층에 한하여 반려견 동반"),
                              SITE, "https://x", "https://x/p/", [], [])
    assert node["amenityFeature"] == [
        {"@type": "LocationFeatureSpecification", "name": "주차", "value": True},
        {"@type": "LocationFeatureSpecification", "name": "유모차 대여", "value": False}]
    stay = dict(entity(pet="불가", checkin="15:00"), kind="stay", category="관광호텔")
    node = jsonld.entity_node(stay, SITE, "https://x", "https://x/p/", [], [])
    assert node["@type"] == "Hotel" and node["petsAllowed"] is False and node["checkinTime"] == "15:00"
    assert "petsAllowed" not in jsonld.entity_node(dict(stay, facts={"pet": "문의"}), SITE, "https://x", "https://x/p/", [], [])


def test_typed_booleans_and_hours_must_restate_a_visible_row(tmp_path):
    from pipeline.validate import jsonld_visibility
    places = sample_places()
    next(p for p in places if p["slug"] == "chowon-photo-studio")["facts"]["parkingfee"] = "무료"
    data = data_with(tmp_path, places)
    out = tmp_path / "s"
    build(data, out, "sample")
    page = out / "places/chowon-photo-studio/index.html"
    html = page.read_text("utf-8")
    raw = html.split('<script type="application/ld+json">')[1].split("</script>")[0]

    def problems(mutate):
        doc = json.loads(raw)
        mutate(next(n for n in doc["@graph"] if str(n.get("@id", "")).endswith("#place")))
        page.write_text(html.replace(raw, json.dumps(doc, ensure_ascii=False)), "utf-8")
        scan = scan_file(page)
        found = []
        for block in scan.jsonld_raw:
            d = json.loads(block)
            found += jsonld_visibility(d.get("@graph", [d]), scan)
        return found

    assert problems(lambda n: None) == []
    assert "주차요금 무료" in scan_file(page).body
    # a fee row that is not exactly 무료 (a 주차요금 무료 row elsewhere does not count)
    assert any("isAccessibleForFree" in x for x in problems(lambda n: n.update(isAccessibleForFree=True)))
    feature = {"@type": "LocationFeatureSpecification", "name": "주차", "value": False}
    assert any("주차" in x for x in problems(lambda n: n.update(amenityFeature=[feature])))
    hours = [{"@type": "OpeningHoursSpecification", "dayOfWeek": ["Monday"], "opens": "06:00", "closes": "07:00"}]
    assert any("opens" in x for x in problems(lambda n: n.update(openingHoursSpecification=hours)))
    image = [{"@type": "ImageObject", "contentUrl": "https://tong.visitkorea.or.kr/x.jpg", "creditText": "다른 기관"}]
    assert any("다른 기관" in x for x in problems(lambda n: n.update(image=image)))


def test_telephone_is_whole_and_international():
    tel = lambda v: jsonld.entity_node(entity(infocenter=v), SITE, "https://x", "https://x/p/", [], []).get("telephone")
    assert tel("063-443-1981, 063-443-4819") == ["+82-63-443-1981", "+82-63-443-4819"]
    assert tel("0507-1302-6070") == "+82-507-1302-6070"
    assert tel("063-443-1981063-443-4819") is None
    assert tel("1577-4050") == "1577-4050"   # a nationwide number has no +82 form (QA 2026-10-15 SRC-05a)


# ---------------------------------------------------------------- P1-6 images
def test_image_credit_licence_and_og_image(tmp_path):
    places = sample_places()
    p = places[0]
    p["images"] = [{"url": f"https://tong.visitkorea.or.kr/t3-{i}.jpg", "alt": "경암동 철길마을", "license": "KOGL-3",
                    "credit": "한국관광공사", "source": "TourAPI"} for i in range(8)]
    p["images"].append({"url": "https://tong.visitkorea.or.kr/t1.jpg", "alt": "경암동 철길마을", "license": "KOGL-1",
                        "credit": "한국관광공사", "source": "TourAPI"})
    data = data_with(tmp_path, places)
    out = tmp_path / "s"
    build(data, out, "sample")
    page = out / "places/gyeongam-railroad-village/index.html"
    images = place_node(page)["image"]
    assert len(images) == 7                                            # hero + images[1:7], as rendered
    assert images[0] == {"@type": "ImageObject", "contentUrl": "https://tong.visitkorea.or.kr/t3-0.jpg",
                         "creditText": "한국관광공사", "copyrightNotice": "한국관광공사",
                         "creator": {"@type": "Organization", "name": "한국관광공사"},
                         "license": "https://www.kogl.or.kr/info/licenseType3.do",
                         "acquireLicensePage": "https://www.kogl.or.kr/info/licenseType3.do"}
    assert scan_file(page).meta["og:image"] == "https://tong.visitkorea.or.kr/t1.jpg"   # Type1 preferred
    html = page.read_text("utf-8")
    assert 'alt="경암동 철길마을 사진 1"' in html and 'alt="경암동 철길마을 사진 2"' in html
    # every page whose cards carry a licensed photo has og:image (home uses its first hero photo instead)
    for rel in ("places/index.html", "themes/alleys-culture/index.html", "guides/no-car-day-trip/index.html",
                "courses/day-course-a/index.html"):
        assert scan_file(out / rel).meta.get("og:image", "").startswith("https://tong.visitkorea.or.kr/"), rel
    assert validate(data, out, "sample")[0] == []


# ---------------------------------------------------------------- P1-7 chips
def test_chips_show_whole_values_or_nothing(tmp_path):
    long = "3~10월 09:00~18:00(입장마감 17:30) / 11~2월 09:00~17:00"
    chips = State.chips({"kind": "attraction", "facts": {"usetime": long, "parking": "가능"}})
    assert chips == [{"label": "주차", "value": "가능"}]
    chips = State.chips({"kind": "attraction", "facts": {"usetime": long}})
    assert chips == [{"label": "이용시간", "value": "장소 페이지에서 확인", "more": True}]
    places = sample_places()
    places[0]["facts"]["usetime"] = long
    out = tmp_path / "s"
    build(data_with(tmp_path, places), out, "sample")
    for page in out.rglob("*.html"):
        for chip in re.findall(r'<span class="chips?">.*?</span>', page.read_text("utf-8"), re.S):
            assert "…" not in chip, (page, chip)


# ---------------------------------------------------------------- P1-8 llms-full
def test_llms_full_lists_also_values_without_a_conflict_sentence(tmp_path):
    places = sample_places()
    food = next(p for p in places if p["kind"] == "food")
    food["fact_alternatives"] = {"menu": [{"value": "물짜장", "provider": "한국관광공사 TourAPI", "relation": "also"}]}
    out = tmp_path / "p"
    build(data_with(tmp_path, places), out, "preview")
    full = (out / "llms-full.txt").read_text("utf-8")
    line = next(x for x in full.splitlines() if "물짜장" in x)
    assert line == "- 대표 메뉴(추가): 물짜장 (출처: 한국관광공사 TourAPI)"
    assert "출처마다 값이 달라" not in line


# ---------------------------------------------------------------- P1-10 about
def test_about_says_how_pages_are_made_and_invents_no_profiles(tmp_path):
    out = tmp_path / "s"
    build(SAMPLE, out, "sample")
    about = out / "about/index.html"
    text = scan_file(about).body
    assert "이 사이트를 만드는 방법" in text and "AI의 도움" in text and "사람이 검토" in text
    assert 'href="/about/#how"' in (out / "index.html").read_text("utf-8")
    org = next(n for n in nodes(out / "index.html") if n["@type"] == "Organization")
    assert "sameAs" not in org and "url" not in org
    data = data_with(tmp_path, site={"operator": {"name": "에이아이오투오", "url": "https://aio2o.example.kr",
                                                  "sameAs": ["https://blog.example.kr/aio2o"], "contact": "x"}})
    out2 = tmp_path / "s2"
    build(data, out2, "sample")
    org = next(n for n in nodes(out2 / "index.html") if n["@type"] == "Organization")
    assert org["sameAs"] == ["https://blog.example.kr/aio2o"] and org["url"] == "https://aio2o.example.kr"


def test_the_company_record_is_in_the_footer_the_about_page_and_the_publisher_node(tmp_path):
    # operator 2026-10-17 (the CEO's mail): the company's official record, as site.json operator gives it
    op = {"name": "에이아이오투오", "legal_name": "주식회사 에이아이오투오", "name_en": "AIO2O", "ceo": "안성민",
          "business_no": "620-87-00810", "corporate_no": "140111-0070330", "founded": "2017-08-16",
          "head_office": "대구광역시 북구 옥산로 111", "head_office_postal": "41593", "lab": "경기도 성남시 수정구 금토로 32",
          "tel": "070-4260-8310", "email": "contact@o2o.kr", "contact": "shyun@o2o.kr"}
    data = data_with(tmp_path, site={"operator": op})
    out = tmp_path / "s"
    build(data, out, "sample")
    home = (out / "index.html").read_text("utf-8")
    assert "대표이사 안성민" in home and "사업자등록번호 620-87-00810" in home and "본사 (41593) 대구광역시 북구 옥산로 111" in home
    for v in ("법인등록번호 140111-0070330", "설립 2017년 8월 16일", "연구소 경기도 성남시 수정구 금토로 32", "이메일", "contact@o2o.kr"):
        assert v in home, v   # the footer carries the whole record (operator 2026-10-17: '최대한 정보를 풍부하게')
    assert 'href="tel:07042608310"' in home and 'href="/about/#company"' in home
    assert "Copyright © 주식회사 에이아이오투오" in home
    about = scan_file(out / "about/index.html").body
    for v in ("법인등록번호", "140111-0070330", "2017년 8월 16일", "(41593) 대구광역시 북구 옥산로 111", "연구소", "contact@o2o.kr"):
        assert v in about, v
    org = next(n for n in nodes(out / "index.html") if n["@type"] == "Organization")
    # the node carries what the footer prints (validate: every value on the page); the founding date is printed in
    # words, so it stays off the node
    assert org["legalName"] == "주식회사 에이아이오투오" and org["taxID"] == "620-87-00810" and org["email"] == "contact@o2o.kr"
    assert org["address"]["postalCode"] == "41593" and org["telephone"] == "+82-70-4260-8310"
    assert "foundingDate" not in org
    assert not validate(data, out, "sample")[0]
    # without a business number the footer keeps its one operator line (the sample's own site.json)
    out2 = tmp_path / "s2"
    build(SAMPLE, out2, "sample")
    assert "foot-biz" not in (out2 / "index.html").read_text("utf-8")


# ---------------------------------------------------------------- P1-12 production URL gate
def test_production_url_gate_names_site_url(tmp_path):
    data = data_with(tmp_path, site={"site_url": ""})
    out = tmp_path / "prod"
    build(data, out, "production")
    errors, _, _ = validate(data, out, "production")
    gate = [x for x in errors if x.startswith("[URL]")]
    assert len(gate) == 1 and "site_url" in gate[0], errors
    out2 = tmp_path / "prod2"
    build(SAMPLE, out2, "production")
    assert not [x for x in validate(SAMPLE, out2, "production")[0] if x.startswith("[URL]")]


# ---------------------------------------------------------------- P2-1 types, P2-3 graph, P2-4 lists, P2-5 courses
def test_entity_graph_lists_and_courses(tmp_path):
    out = tmp_path / "s"
    build(SAMPLE, out, "sample")
    gy = place_node(out / "places/gyeongam-railroad-village/index.html")
    assert gy["containedInPlace"] == {"@id": "https://example.com/#city", "@type": "City", "name": "군산시"}
    home = next(n for n in nodes(out / "index.html") if n.get("@id") == "https://example.com/#city")
    assert home["@type"] == ["City", "TouristDestination"] and "description" not in home
    listing = scan_file(out / "places/index.html")
    items = next(n for n in nodes(out / "places/index.html") if n["@type"] == "ItemList")["itemListElement"]
    cards = [h for h in listing.hrefs if h.startswith("/places/") and h != "/places/"]
    assert [i["url"] for i in items] == ["https://example.com" + h for h in dict.fromkeys(cards)]
    trip = next(n for n in nodes(out / "courses/day-course-a/index.html") if n["@type"] == "TouristTrip")
    assert trip["isBasedOn"] == "https://www.gunsan.go.kr/tour"
    stops = [i["item"] for i in trip["itinerary"]["itemListElement"]]
    assert stops[0]["@id"] == "https://example.com/places/gyeongam-railroad-village/#place"
    assert stops[2] == {"@type": "Place", "name": "선유도"}
    guide = next(n for n in nodes(out / "guides/no-car-day-trip/index.html") if n["@type"] == "Article")
    assert guide["about"][0]["@id"].endswith("/places/gyeongam-railroad-village/#place")
    assert course_title("A코스 | 근대~고군산", 11, "군산") == "군산 근대~고군산(A코스) — 경유지 11곳"
    assert course_title("영화 속 군산 코스", 9, "군산") == "영화 속 군산 코스 — 경유지 9곳"
