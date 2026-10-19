"""Rights reports keep source integrity and separate article/photo decisions."""
import hashlib
import json
from pathlib import Path

from tools.rights_report import inventory, main, render


def write(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False), "utf-8")


def source_entity(name, code, images=None):
    text = f" {name} 원문\n둘째 줄\r\n"
    return {"id": name, "name": name, "original": {
        "text": text, "source_url": f"https://www.gunsan.go.kr/tour/{name}",
        "license": code, "sha256": hashlib.sha256(text.encode()).hexdigest(),
        "license_evidence": f"fixture: {code}",
    }, "images": images or []}


def dataset(tmp_path, places, courses=None, rules=None):
    data = tmp_path / "data"
    write(data / "site.json", {"publish_rules": rules if rules is not None else {
        "allowed_original_licenses": ["KOGL-1", "KOGL-3"],
        "allowed_image_licenses": ["KOGL-1", "KOGL-3"],
    }})
    write(data / "places.json", places)
    write(data / "courses.json", courses or [])
    return data


def test_all_codes_and_verbatim_permissions_include_courses(tmp_path):
    codes = ["KOGL-1", "KOGL-2", "KOGL-3", "KOGL-4", "NONE", "UNKNOWN"]
    data = dataset(tmp_path, [source_entity(f"p{i}", c) for i, c in enumerate(codes)],
                   [source_entity("course", "KOGL-3")])
    report = inventory(data)
    output = render(report)
    assert len(report["originals"]) == 7
    assert "| 등록 장소·코스 원문 | 3 | 4 |" in output
    assert "KOGL-3은 변경 금지" in output
    assert all(row["sha256_check"] == "일치" for row in report["originals"])
    assert not report["errors"]


def test_photo_rights_deduplicated_separately_from_article(tmp_path):
    image = {"url": "https://www.gunsan.go.kr/p.jpg", "license": "UNKNOWN"}
    data = dataset(tmp_path, [source_entity("p1", "KOGL-1", [image, image]),
                             source_entity("p2", "KOGL-3", [image])])
    report = inventory(data)
    assert len(report["photos"]) == 2  # Shared URL across different entities stays separate.
    assert all(row["license"] == "UNKNOWN" for row in report["photos"])
    assert "| 등록 사진 | 0 | 2 |" in render(report)


def test_raw_observed_photos_and_pending_course_have_separate_counts(tmp_path):
    registered_course = source_entity("course-imported", "KOGL-1")
    pending_course = source_entity("course-pending", "NONE")
    pending_course["original"].pop("sha256")
    data = dataset(tmp_path, [source_entity("p", "NONE", [{"url": "https://www.gunsan.go.kr/1.jpg", "license": "UNKNOWN"}])],
                   [registered_course])
    raw = tmp_path / "raw" / "gunsan"
    evidence = [{"id": "p", "name": "p", "source_url": "https://www.gunsan.go.kr/tour/p",
                 "license_evidence": "본문 유형 표기 없음", "images": [
                     {"url": "https://www.gunsan.go.kr/1.jpg", "license": "UNKNOWN", "evidence": "사진별 표기 없음"},
                     {"url": "https://www.gunsan.go.kr/2.jpg", "license": "KOGL-2", "evidence": "사진 제2유형"},
                 ]}]
    write(raw / "rights_evidence.json", evidence)
    write(raw.parent / "gunsan_courses.json", [registered_course, pending_course])
    report = inventory(data, raw)
    assert len(report["originals"]) == 3
    assert len(report["photos"]) == 1 and len(report["observed_photos"]) == 2
    assert len([row for row in report["originals"] if row["scope"] == "미수입 수집 코스 원문"]) == 1
    assert report["originals"][0]["evidence"] == "fixture: NONE"
    assert report["photos"][0]["evidence"] == "사진별 표기 없음"
    assert not report["errors"]
    assert "미기록 (해시를 생성하거나 저장하지 않음)" in render(report)


def test_invalid_codes_stay_unknown_and_never_write_back(tmp_path):
    data = dataset(tmp_path, [source_entity("p", "공공누리 제1유형", [{"url": "x", "license": "Type1"}])])
    before = {path: path.read_bytes() for path in data.iterdir()}
    report = inventory(data)
    assert report["originals"][0]["license"] == "UNKNOWN"
    assert report["photos"][0]["license"] == "UNKNOWN"
    assert len(report["warnings"]) == 2
    assert "| 등록 장소·코스 원문 | 0 | 1 |" in render(report)
    assert all(path.read_bytes() == value for path, value in before.items())


def test_original_hash_mismatch_reported_and_cli_fails_without_repair(tmp_path):
    entity = source_entity("p", "KOGL-1")
    entity["original"]["text"] += "변경"
    data = dataset(tmp_path, [entity])
    before = (data / "places.json").read_bytes()
    out = tmp_path / "rights.md"
    assert main(["--data", str(data), "--out", str(out)]) == 1
    assert "original.sha256 불일치" in out.read_text("utf-8")
    assert (data / "places.json").read_bytes() == before


def test_explicit_empty_rules_do_not_fall_back_to_default(tmp_path):
    data = dataset(tmp_path, [source_entity("p", "KOGL-1")], rules={
        "allowed_original_licenses": [], "allowed_image_licenses": [],
    })
    assert "| 등록 장소·코스 원문 | 0 | 1 |" in render(inventory(data))


def test_conflicting_duplicate_photo_and_wrong_source_evidence_are_conservative(tmp_path):
    entity = source_entity("p", "NONE", [{"url": "x", "license": "KOGL-1"},
                                         {"url": "x", "license": "KOGL-3"}])
    entity["original"].pop("license_evidence")
    data = dataset(tmp_path, [entity])
    raw = tmp_path / "raw"
    write(raw / "rights_evidence.json", [{"id": "p", "name": "p", "source_url": "different",
          "license_evidence": "이 근거는 사용하면 안 됨", "images": []}])
    report = inventory(data, raw)
    assert report["photos"][0]["license"] == "UNKNOWN"
    assert "이 근거는 사용하면 안 됨" not in report["originals"][0]["evidence"]
    assert len(report["warnings"]) == 2


def test_bundled_sample_cli_keeps_inputs_intact(tmp_path):
    data = Path(__file__).resolve().parent.parent / "data" / "sample"
    before = {path: path.read_bytes() for path in data.glob("*.json")}
    out = tmp_path / "sample-rights.md"
    assert main(["--data", str(data), "--out", str(out)]) == 0
    assert "샘플 데이터 — 실제 권리 확인 결과가 아닙니다" in out.read_text("utf-8")
    assert all(path.read_bytes() == value for path, value in before.items())


def test_full_detail_evidence_extends_samples_without_double_count(tmp_path):
    entity = source_entity('p', 'NONE', [{'url': 'https://www.gunsan.go.kr/a.jpg', 'license': 'UNKNOWN'}])
    entity['original'].pop('license_evidence')
    data = dataset(tmp_path, [entity])
    raw = tmp_path / 'raw'
    sample = {'id': 'p', 'name': 'p', 'source_url': entity['original']['source_url'],
              'license_evidence': '본문 유형 표기 없음', 'images': [
                  {'url': 'https://www.gunsan.go.kr/a.jpg', 'license': 'UNKNOWN', 'evidence': '사진 유형 표기 없음'}]}
    write(raw / 'rights_evidence.json', [sample])
    write(raw / 'details_crawl.json', {'records': [sample, {
        'id': 'new', 'name': 'new', 'source_url': 'https://www.gunsan.go.kr/tour/new',
        'images': [{'url': 'https://www.gunsan.go.kr/b.jpg', 'license': 'UNKNOWN', 'evidence': '개별 미표기'}]}]})
    before = {p: p.read_bytes() for p in [*data.iterdir(), *raw.iterdir()]}
    report = inventory(data, raw)
    assert report['originals'][0]['evidence'] == '본문 유형 표기 없음'
    assert report['photos'][0]['evidence'] == '사진 유형 표기 없음'
    assert len(report['observed_photos']) == 2
    assert all(p.read_bytes() == content for p, content in before.items())


def test_detail_alias_cannot_replace_matching_source_evidence(tmp_path):
    entity = source_entity('p', 'NONE')
    entity['original'].pop('license_evidence')
    data = dataset(tmp_path, [entity])
    raw = tmp_path / 'raw'
    write(raw / 'rights_evidence.json', [{'id': 'p', 'source_url': entity['original']['source_url'],
                                         'license_evidence': 'matching original source'}])
    write(raw / 'details_crawl.json', {'records': [{'id': 'p', 'source_url': 'https://www.gunsan.go.kr/tour/alias',
                                                   'license_evidence': 'different source'}]})
    assert inventory(data, raw)['originals'][0]['evidence'] == 'matching original source'
