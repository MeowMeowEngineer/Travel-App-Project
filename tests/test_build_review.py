from copy import deepcopy
import json
from pathlib import Path
import shutil

import pytest

from pipeline.validate import scan_file
from tools import build_review


SAMPLE = Path(__file__).resolve().parents[1] / "data/sample"


def setup(tmp_path):
    data = tmp_path / "data"
    shutil.copytree(SAMPLE, data)
    places = json.loads((data / "places.json").read_text("utf-8"))
    hidden = deepcopy(places[0])
    hidden.update(id="hidden", slug="hidden", name="작성할 장소", summary="   ", status="draft")
    places.append(hidden)
    places[0].setdefault("nearby", []).append({"name": "작성할 장소", "internal_slug": "hidden", "kind": "attraction"})
    # A course stop that points at a duplicate record: never built, so the stop loses its link but keeps its name.
    dupe = deepcopy(places[1])
    dupe.update(id="dupe-stop", slug="dupe-stop", name="중복 경유지", duplicate_of=places[1]["id"])
    places.append(dupe)
    (data / "places.json").write_text(json.dumps(places, ensure_ascii=False), "utf-8")
    courses = json.loads((data / "courses.json").read_text("utf-8"))
    courses[0]["stops"].append({"place_slug": "dupe-stop", "note": "기존 경유 메모"})
    (data / "courses.json").write_text(json.dumps(courses, ensure_ascii=False), "utf-8")
    (data / "source_documents.json").write_text('{"private_secret_archive":true}')
    return data, places, courses


def test_curated_preview_preserves_source_and_excludes_unwritten_places_with_safe_links(tmp_path, monkeypatch):
    data, places, courses = setup(tmp_path)
    before = {p.name: p.read_bytes() for p in data.glob("*.json")}
    actual_build = build_review.build
    captured = {}

    def inspect_build(staged, out, mode):
        assert not (staged / "source_documents.json").exists()
        assert (staged / "site.json").read_bytes() == before["site.json"]
        captured["places"] = json.loads((staged / "places.json").read_text("utf-8"))
        captured["courses"] = json.loads((staged / "courses.json").read_text("utf-8"))
        assert captured["courses"][0]["stops"][-1] == {"name": "중복 경유지", "note": "기존 경유 메모"}
        assert captured["places"][0]["nearby"][-1] == {"name": "작성할 장소", "kind": "attraction"}
        assert mode == "preview"
        return actual_build(staged, out, mode)

    monkeypatch.setattr(build_review, "build", inspect_build)
    out = tmp_path / "out"
    report = build_review.run(data, out, tmp_path / "reports")
    assert report["source_data_unchanged"]
    assert {p.name: p.read_bytes() for p in data.glob("*.json")} == before
    reasons = {x["slug"]: x["reason"] for x in report["excluded"]}
    assert reasons == {"eunpa-lake-park": "no_practical_info", "sample-draft": "no_practical_info",
                       "hidden": "summary_not_written", "dupe-stop": "duplicate_record"}
    assert len(report["selected"]) == len(places) - 4
    assert len(captured["courses"]) == len(courses)
    assert not (out / "places/hidden").exists()
    assert "Disallow: /" in (out / "robots.txt").read_text("utf-8")
    for page in out.rglob("*.html"):
        assert "noindex" in scan_file(page).meta["robots"]
        assert "/places/hidden/" not in page.read_text("utf-8")
        assert "private_secret_archive" not in page.read_text("utf-8")
    assert not any("내부 링크 깨짐" in error for error in report["qa"]["errors"])
    assert (tmp_path / "reports/review_build_selection.json").exists()
    old_by_id = {p["id"]: p for p in places}
    assert all(new["original"] == old_by_id[new["id"]]["original"] and new["status"] == old_by_id[new["id"]]["status"]
               for new in captured["places"])


def test_places_linked_from_courses_and_guides_are_always_selected(tmp_path):
    data, places, courses = setup(tmp_path)
    stop = deepcopy(places[0])
    stop.update(id="course-stop", slug="course-stop", name="코스 경유지", summary="", tier="basic",
                facts={"address": "전북특별자치도 군산시 해망로 1"}, nearby=[], faq=[])
    places.append(stop)
    (data / "places.json").write_text(json.dumps(places, ensure_ascii=False), "utf-8")
    courses[0]["stops"].insert(0, {"place_slug": "course-stop"})
    (data / "courses.json").write_text(json.dumps(courses, ensure_ascii=False), "utf-8")
    guides = json.loads((data / "guides.json").read_text("utf-8"))
    guides[0]["items"].append({"place_slug": "eunpa-lake-park", "reason": "가이드가 고른 이유"})
    (data / "guides.json").write_text(json.dumps(guides, ensure_ascii=False), "utf-8")
    out, reports = tmp_path / "out", tmp_path / "reports"
    report = build_review.run(data, out, reports)
    selected = {p["slug"]: p for p in report["selected"]}
    # no summary / no practical info, but a course stop or guide item points here -> kept, with the reason
    assert selected["course-stop"]["reason"] == "linked_from_course_or_guide"
    assert selected["course-stop"]["linked_from"] == ["courses:day-course-a"]
    assert selected["eunpa-lake-park"]["reason"] == "linked_from_course_or_guide"
    assert selected["eunpa-lake-park"]["linked_from"] == ["guides:no-car-day-trip"]
    assert selected["gyeongam-railroad-village"]["reason"] == "full_tier"
    assert {x["slug"] for x in report["excluded"]} == {"sample-draft", "hidden", "dupe-stop"}  # duplicates still out
    assert "/places/course-stop/" in (out / "courses/day-course-a/index.html").read_text("utf-8")
    assert "/places/eunpa-lake-park/" in (out / "guides/no-car-day-trip/index.html").read_text("utf-8")
    # the only staged link change left is the duplicate stop and the unwritten nearby place
    assert {c["target"] for c in report["staging_link_changes"]} == {"dupe-stop", "hidden"}
    md = (reports / "review_build_selection.md").read_text("utf-8")
    assert "course-stop — 코스 경유지: courses:day-course-a" in md


def test_content_qa_errors_are_retained_in_report_and_exit_status(tmp_path):
    data, places, _ = setup(tmp_path)
    places[0]["tier"] = "full"
    places[0]["faq"] = []
    (data / "places.json").write_text(json.dumps(places, ensure_ascii=False), "utf-8")
    report = build_review.run(data, tmp_path / "out", tmp_path / "reports")
    assert report["status"] == "built_with_qa_errors"
    assert any("필수 블록 없음: faq" in error for error in report["qa"]["errors"])
    assert build_review.main(["--data", str(data), "--out", str(tmp_path / "out"),
                              "--report-dir", str(tmp_path / "reports")]) == 1


def test_refuses_output_inside_source_without_changing_inputs(tmp_path):
    data, _, _ = setup(tmp_path)
    before = {p.name: p.read_bytes() for p in data.glob("*.json")}
    with pytest.raises(ValueError, match="overlap"):
        build_review.run(data, data / "public", tmp_path / "reports")
    assert {p.name: p.read_bytes() for p in data.glob("*.json")} == before


def test_missing_reference_name_fails_before_building(tmp_path):
    data, _, courses = setup(tmp_path)
    courses[0]["stops"].append({"place_slug": "unknown-source-place"})
    (data / "courses.json").write_text(json.dumps(courses))
    with pytest.raises(ValueError, match="unresolved reference"):
        build_review.run(data, tmp_path / "out", tmp_path / "reports")
    assert not (tmp_path / "out").exists()
