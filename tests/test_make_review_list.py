"""Preview review lists never mutate data or invent review/publication outcomes."""
import json
from pathlib import Path

import pytest

from pipeline.textutil import sha256_text
from tools.make_review_list import main, make_report


def write(path, data):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False), "utf-8")


def dataset(tmp_path):
    root = tmp_path / "data"
    write(root / "site.json", {"site_url": "https://production.example", "publish_rules": {
        "allowed_original_licenses": ["KOGL-1", "KOGL-3"], "allowed_image_licenses": ["KOGL-1", "KOGL-3"],
    }})
    original = {"text": "원문\n둘째 줄", "sha256": sha256_text("원문\n둘째 줄"),
                "license": "NONE", "source_url": "https://www.gunsan.go.kr/tour/p"}
    write(root / "places.json", [
        {"id": "p", "slug": "장소", "name": "장소", "status": "draft", "tier": "full", "kind": "attraction",
         "original": original, "images": [{"url": "x", "license": "UNKNOWN"}]},
        {"id": "approved", "slug": "approved", "name": "확인 완료", "status": "published"},
    ])
    write(root / "guides.json", [{"id": "g", "slug": "guide", "title": "가이드", "status": "draft",
                                 "items": [{"place_slug": "missing"}]}])
    write(root / "courses.json", [{"id": "c", "slug": "course", "name": "코스", "status": "draft",
                                  "original": original, "stops": [{"place_slug": "장소", "name": "장소"},
                                  {"place_slug": "장소", "name": "장 소"}, {"name": "장소"}]}])
    write(root / "events.json", [{"id": "e", "name": "행사", "status": "draft", "source_url": "source"}])
    return root


def test_draft_paths_and_checks_are_read_only_and_relative(tmp_path):
    data = dataset(tmp_path)
    before = {path: path.read_bytes() for path in data.glob("*.json")}
    report, errors, counts = make_report(data)
    assert counts == {"장소": 1, "가이드": 1, "코스": 1, "행사": 1}
    assert "[ /places" not in report
    assert "[/places/장소/](/places/장소/)" in report
    assert "[/events/](/events/)" in report
    assert "production.example" not in report
    assert "noindex" in report and "미게재 1건" in report
    assert "full 주변 장소 미작성" in report and "full 영상·소식 미작성" in report
    assert "주소·이용시간·쉬는 날·이용요금·주차" in report
    assert "SHA-256 일치" in report and "경유지 명칭 불일치" in report
    assert "정확히 일치하는 후보 장소 (자동 연결하지 않음)" in report
    assert "가이드 장소 연결 대상 없음" in report
    assert not errors
    assert all(path.read_bytes() == value for path, value in before.items())


def test_explicit_preview_base_only_and_url_encoded_paths(tmp_path):
    data = dataset(tmp_path)
    report, _, _ = make_report(data, "https://preview.example/review/")
    assert "https://preview.example/review/places/%EC%9E%A5%EC%86%8C/" in report
    assert "production.example" not in report


def test_hash_failure_is_reported_and_cli_exit_one(tmp_path):
    data = dataset(tmp_path)
    places = json.loads((data / "places.json").read_text("utf-8"))
    places[0]["original"]["text"] += "변경"
    write(data / "places.json", places)
    out = tmp_path / "review.md"
    assert main(["--data", str(data), "--out", str(out)]) == 1
    assert "원문 SHA-256 불일치" in out.read_text("utf-8")


@pytest.mark.parametrize("base", ["ftp://example", "https://name:password@example", "https://example?q=x", "relative"])
def test_rejects_invalid_preview_base(tmp_path, base):
    data = dataset(tmp_path)
    with pytest.raises(SystemExit) as failure:
        main(["--data", str(data), "--base-url", base])
    assert failure.value.code == 2


def test_cli_with_bundled_sample_preserves_all_records(tmp_path):
    data = Path(__file__).resolve().parents[1] / "data" / "sample"
    before = {path: path.read_bytes() for path in data.glob("*.json")}
    out = tmp_path / "review.md"
    assert main(["--data", str(data), "--out", str(out)]) == 0
    assert "sample-draft" in out.read_text("utf-8")
    assert all(path.read_bytes() == value for path, value in before.items())
