"""End-to-end: build the bundled sample and validate it."""
import json
import shutil
from pathlib import Path

from pipeline.build import build
from pipeline.validate import validate

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
