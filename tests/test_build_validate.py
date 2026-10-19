"""End-to-end: build the bundled sample and validate it."""
import json
import shutil
from pathlib import Path

from pipeline.build import build
from pipeline.validate import PageScan, seat_only_parking_problems, validate

ROOT = Path(__file__).resolve().parent.parent
SAMPLE = ROOT / "data" / "sample"


def test_sample_builds_and_passes_sample_rules(tmp_path):
    out = tmp_path / "dist-sample"
    stats = build(SAMPLE, out, "sample")
    assert stats["entities"] == 5 and stats["excluded_entities"] == 1     # draft is never built
    assert (out / "places" / "gyeongam-railroad-village" / "index.html").exists()
    assert not (out / "places" / "sample-draft").exists()
    assert "Disallow: /" in (out / "robots.txt").read_text("utf-8")        # sample is never indexable
    errors, warns, s = validate(SAMPLE, out, "sample")
    assert errors == [], errors
    assert s["original_shown"] == 2 and s["original_linked"] == 1


def test_unknown_licence_text_never_appears(tmp_path):
    out = tmp_path / "d"
    build(SAMPLE, out, "sample")
    page = (out / "places" / "chowon-photo-studio" / "index.html").read_text("utf-8")
    assert "이용조건 확인 전 원문입니다" not in page
    assert "원문 보기" in page


def test_jsonld_matches_visible_text(tmp_path):
    out = tmp_path / "d"
    build(SAMPLE, out, "sample")
    html = (out / "places" / "gyeongam-railroad-village" / "index.html").read_text("utf-8")
    raw = html.split('<script type="application/ld+json">')[1].split("</script>")[0]
    graph = json.loads(raw)["@graph"]
    node = next(n for n in graph if n.get("@type") == "TouristAttraction")
    assert node["name"] == "경암동 철길마을"
    assert node["description"] in html

    # P0-3: an old-province address and a 0507 number build clean; every page passes the visibility rule
    data = tmp_path / "data"
    shutil.copytree(SAMPLE, data)
    places = json.loads((data / "places.json").read_text("utf-8"))
    places[0]["facts"].update(address="전라북도 군산시 경촌4길 14", infocenter="0507-1302-6070")
    (data / "places.json").write_text(json.dumps(places, ensure_ascii=False), "utf-8")
    out = tmp_path / "fixture"
    build(data, out, "sample")
    page = out / "places" / "gyeongam-railroad-village" / "index.html"
    html = page.read_text("utf-8")
    node = next(n for n in json.loads(html.split('<script type="application/ld+json">')[1].split("</script>")[0])["@graph"]
                if n.get("@id", "").endswith("#place"))
    assert node["address"] == {"@type": "PostalAddress", "addressRegion": "전북특별자치도", "addressLocality": "군산시",
                               "streetAddress": "경촌4길 14", "addressCountry": "KR"}
    assert "전북특별자치도 군산시 경촌4길 14" in html and "전라북도" not in html
    assert node["telephone"] == "+82-507-1302-6070" and "0507-1302-6070" in html
    errors, _, _ = validate(data, out, "sample")
    assert errors == [], errors
    # a description that the page does not show is caught
    raw = html.split('<script type="application/ld+json">')[1].split("</script>")[0]
    doc = json.loads(raw)
    next(n for n in doc["@graph"] if n.get("@id", "").endswith("#place"))["description"] = "화면에 없는 설명입니다"
    page.write_text(html.replace(raw, json.dumps(doc, ensure_ascii=False)), "utf-8")
    errors, _, _ = validate(data, out, "sample")
    assert any("구조화 데이터가 화면과 다름" in x and "화면에 없는 설명입니다" in x for x in errors), errors


def test_production_rules_catch_sample_leftovers(tmp_path):
    out = tmp_path / "prod"
    build(SAMPLE, out, "production")
    errors, _, _ = validate(SAMPLE, out, "production")
    text = "\n".join(errors)
    assert "site_url" in text and "ga4_id" in text and "자리표시" in text


def test_refuses_to_wipe_foreign_folder(tmp_path):
    foreign = tmp_path / "mine"
    foreign.mkdir()
    (foreign / "keep.txt").write_text("x")
    try:
        build(SAMPLE, foreign, "sample")
        raised = False
    except SystemExit:
        raised = True
    assert raised and (foreign / "keep.txt").exists()
    shutil.rmtree(foreign)


def test_empty_draft_guides_stay_in_review_data_but_not_visitor_routes(tmp_path):
    from tools.make_review_list import make_report

    data = tmp_path / "data"
    shutil.copytree(SAMPLE, data)
    guides_path = data / "guides.json"
    guides = json.loads(guides_path.read_text("utf-8"))
    guides += [
        {"id": "empty-plan", "slug": "empty-plan", "title": "작성할 가이드", "status": "draft",
         "summary": "제목과 계획만 있는 초안", "body": [{"heading": "예정", "text": "  "}],
         "items": [], "faq": [], "sources": []},
        {**guides[0], "id": "readable-draft", "slug": "readable-draft", "status": "draft"},
    ]
    guides_path.write_text(json.dumps(guides, ensure_ascii=False), "utf-8")
    before = {p: p.read_bytes() for p in data.glob("*.json")}
    out = tmp_path / "preview"
    result = build(data, out, "preview")
    assert result["guides"] == 2
    assert not (out / "guides" / "empty-plan").exists()
    assert (out / "guides" / "readable-draft" / "index.html").exists()
    for p in list(out.rglob("*.html")) + [out / "sitemap.xml", out / "llms.txt"]:
        assert "/guides/empty-plan/" not in p.read_text("utf-8"), p
    review, errors, counts = make_report(data)
    assert counts["가이드"] == 2 and not errors
    assert "empty-plan" in review and "미리보기 미생성" in review
    assert "[/guides/empty-plan/]" not in review
    assert "[/guides/readable-draft/]" in review
    assert all(p.read_bytes() == contents for p, contents in before.items())


def test_seat_count_alone_is_never_shown_as_parking():
    """validate.seat_only_parking_problems: a '30석' value under 주차 / 주차·좌석 is an error, under 좌석 it is not;
    a seats-only place must name 주차 in both '확인 필요' lines."""
    e = {"facts": {"parking_seats": "30석"}}

    def page(dt, need="주차", value="30석"):
        p = PageScan()
        p.feed(f'<p class="kf-need">확인 필요: {need}</p><section data-block="facts"><dl><div><dt>{dt}</dt>'
               f'<dd data-key="parking_seats">{value}</dd></div></dl><p class="need"><b>확인 필요</b> {need}</p></section>')
        return p

    assert seat_only_parking_problems(e, page("좌석")) == []
    assert len(seat_only_parking_problems(e, page("주차·좌석"))) == 1
    assert len(seat_only_parking_problems(e, page("주차"))) == 1
    assert len(seat_only_parking_problems(e, page("좌석", need="쉬는 날"))) == 2
    # both halves, or a parking value of its own: nothing to report
    assert seat_only_parking_problems({"facts": {"parking_seats": "20대/30석"}}, page("주차·좌석", "", "20대/30석")) == []
    assert seat_only_parking_problems({"facts": {"parking_seats": "30석", "parking": "가능"}}, page("좌석", need="")) == []


def _state(tmp_path, edit):
    from pipeline.build import State
    data = tmp_path / "data"
    shutil.copytree(SAMPLE, data)
    places = json.loads((data / "places.json").read_text("utf-8"))
    edit({p["id"]: p for p in places})
    (data / "places.json").write_text(json.dumps(places, ensure_ascii=False), "utf-8")
    return State(data, "sample")


CITY = {"source": "군산시 문화관광", "url": "https://www.gunsan.go.kr/tour/m2096/view/305391", "checked_at": "2026-10-16"}


def test_validate_checks_every_published_point(tmp_path):
    """geo_problems: numbers inside the region's box, never the 군산시 map script's default point, a source, and for a
    source other than TourAPI the page and the day it was read (errors); three places at one point with different
    addresses (warning). A TourAPI point and a complete 군산시 문화관광 point pass."""
    from pipeline.validate import geo_problems

    def edit(by):
        by["sample-0001"]["geo"] = {"lat": 36.5, "lng": 126.72, "source": "TourAPI"}             # out of the box
        by["sample-0002"]["geo"] = {"lat": 35.96761, "lng": 126.73684, "source": "TourAPI"}      # the default point
        by["sample-0003"]["geo"] = {"lat": 35.95, "lng": 126.69}                                 # no source
        by["sample-0101"]["geo"] = {"lat": 35.97, "lng": 126.70, "source": "군산시 문화관광"}     # no url, no day
        by["sample-0201"]["geo"] = {"lat": 35.98, "lng": "x", "source": "TourAPI"}               # not a number
        by["sample-0999"]["geo"] = {"lat": 99.0, "lng": 126.7}                                   # a draft: not checked
    errors, warns = geo_problems(_state(tmp_path, edit))
    assert len(errors) == 6 and warns == [], errors
    for pid, words in (("sample-0001", "범위"), ("sample-0002", "기본점"), ("sample-0003", "geo.source"),
                       ("sample-0101", "geo.url"), ("sample-0101", "geo.checked_at"), ("sample-0201", "숫자가 아님")):
        assert any(x.startswith(pid) and words in x for x in errors), (pid, words)

    def fine(by):
        for i, pid in enumerate(("sample-0001", "sample-0002", "sample-0003")):
            by[pid]["geo"] = {"lat": 35.98, "lng": 126.72, "source": "TourAPI"}       # one point …
            by[pid]["facts"]["address"] = f"전북특별자치도 군산시 경촌4길 {10 + i}"   # … three addresses
        by["sample-0101"]["geo"] = {"lat": 35.97, "lng": 126.70, **CITY}
    errors, warns = geo_problems(_state(tmp_path / "b", fine))
    assert errors == [] and len(warns) == 1 and "주소가 다른 장소 3곳" in warns[0], warns


def test_validate_checks_whose_points_a_nearby_list_names(tmp_path):
    """nearby_provenance_problems: a list with providers must name exactly the providers of the place's point and
    every listed place's, in its list and its line (errors); a list stored before providers were recorded whose line
    misses one is one warning naming the place."""
    from pipeline.validate import nearby_provenance_problems
    tour = {"source": "TourAPI"}
    listed = lambda slug: {"name": slug, "kind": "attraction", "distance_m": 10, "internal_slug": slug}  # noqa: E731
    one, both = ["한국관광공사 TourAPI"], ["한국관광공사 TourAPI", "군산시 문화관광"]

    def edit(by):
        by["sample-0001"].update(geo={"lat": 35.98, "lng": 126.72, **tour}, nearby=[listed("chowon-photo-studio")],
                                 nearby_source={"provider": "한국관광공사 TourAPI 좌표", "providers": one})
        by["sample-0002"].update(geo={"lat": 35.981, "lng": 126.72, **CITY}, nearby=[listed("gyeongam-railroad-village")],
                                 nearby_source={"provider": "한국관광공사 TourAPI 좌표", "providers": both})
        by["sample-0003"].update(geo={"lat": 35.982, "lng": 126.72, **tour}, nearby=[listed("chowon-photo-studio")],
                                 nearby_source={"provider": "한국관광공사 TourAPI 좌표"})      # stored before providers
        by["sample-0101"].update(geo={"lat": 35.983, "lng": 126.72, **tour}, nearby=[listed("eunpa-lake-park")],
                                 nearby_source={"provider": "한국관광공사 TourAPI 좌표", "providers": one})
    errors, warns = nearby_provenance_problems(_state(tmp_path, edit))
    assert len(errors) == 2, errors
    assert errors[0].startswith("sample-0001") and "providers" in errors[0]          # it lists the 군산시 point
    assert errors[1].startswith("sample-0002") and "provider '한국관광공사 TourAPI 좌표'" in errors[1]
    assert len(warns) == 1 and "1곳" in warns[0] and "sample-0101" not in warns[0], warns
