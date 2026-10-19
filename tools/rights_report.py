"""Read-only rights inventory; it does not grant rights or change source records.

    python tools/rights_report.py --data data/incheon --raw data/raw/incheon \
        --out reports/rights_report.md

The optional raw folder (data/raw/<region>) contains rights_evidence.json. Its courses.json, or the sibling
<region>_courses.json (the collector's layout), supplies courses which have not yet been imported.
Photos registered in the dataset and photos observed by the collector have
separate denominators. Images are never downloaded by this tool.
"""
from __future__ import annotations

import argparse
from collections import Counter
import hashlib
import json
from pathlib import Path
import sys


LICENSES = ("KOGL-1", "KOGL-2", "KOGL-3", "KOGL-4", "NONE", "UNKNOWN")


def _read(path: Path, default):
    return json.loads(path.read_text("utf-8")) if path.exists() else default


def _code(value, warnings: list[str], label: str) -> str:
    # No guessing, spelling repairs or inference from the page's other assets.
    if value in LICENSES:
        return value
    if value not in (None, ""):
        warnings.append(f"{label}: 유효하지 않은 이용조건 코드 {value!r}; 보고서에서 UNKNOWN으로 분류")
    return "UNKNOWN"


def _source_url(entity: dict) -> str:
    return ((entity.get("original") or {}).get("source_url")
            or entity.get("source_url")
            or (entity.get("official") or {}).get("source_url") or "")


def _image_rows(entity: dict, images: list[dict], scope: str,
                evidence: dict, warnings: list[str]) -> list[dict]:
    rows = {}
    evidence_photos = {photo.get("url"): photo for photo in evidence.get("images", [])}
    for index, image in enumerate(images, 1):
        url = image.get("url") or ""
        code = _code(image.get("license"), warnings, f"{entity.get('id', '')} 사진 {index}")
        proof = image.get("evidence") or image.get("license_evidence")
        proof = proof or evidence_photos.get(url, {}).get("evidence")
        proof = proof or "사진별 판별 근거 문자열 미저장; 페이지 이용조건을 사진에 적용하지 않음"
        # Dedupe URLs only within their owning entity. Missing URLs are separate
        # malformed assets, not one shared photograph.
        key = url or f"missing-url-{index}"
        if key in rows:
            existing = rows[key]
            if existing["license"] != code:
                warnings.append(f"{entity.get('id', '')} 사진 {url}: 중복 URL의 이용조건이 달라 UNKNOWN으로 분류")
                existing["license"] = "UNKNOWN"
                existing["evidence"] += f"; 중복 표기의 충돌: {code} ({proof})"
            continue
        if not url:
            warnings.append(f"{entity.get('id', '')} 사진 {index}: 사진 URL 누락")
        rows[key] = {
            "scope": scope, "id": entity.get("id") or "식별자 없음",
            "name": entity.get("name") or "명칭 없음", "url": url,
            "source_url": _source_url(entity), "license": code,
            "evidence": str(proof),
        }
    return list(rows.values())


def inventory(data_dir: Path, raw_dir: Path | None = None) -> dict:
    """Return report data without changing any input, even for invalid codes."""
    site = _read(data_dir / "site.json", {})
    warnings, errors = [], []
    rules = site.get("publish_rules") or {}
    allowed = {}
    for field in ("allowed_original_licenses", "allowed_image_licenses"):
        values = rules.get(field)
        if not isinstance(values, list):
            warnings.append(f"publish_rules.{field} 누락 또는 형식 오류; 허용 유형을 추측하지 않음")
            values = []
        allowed[field] = [v for v in values if v in LICENSES and v not in ("NONE", "UNKNOWN")]
        if allowed[field] != values:
            warnings.append(f"publish_rules.{field}: 미확인·유효하지 않은 유형은 허용 판정에서 제외")

    evidence = _read(raw_dir / "rights_evidence.json", []) if raw_dir else []
    if raw_dir:
        evidence += _read(raw_dir / "details_crawl.json", {}).get("records", [])
    # A detail checkpoint extends the initial sample evidence. Keep distinct
    # source URLs apart and avoid counting a sampled record twice.
    evidence = list({(e.get("id"), e.get("source_url")): e for e in evidence}.values())
    evidence_by_source = {(e.get("id"), e.get("source_url")): e for e in evidence if e.get("id")}
    evidence_by_id = {e.get("id"): e for e in evidence if e.get("id")}
    registered = [("등록 장소 원문", e) for e in _read(data_dir / "places.json", [])]
    registered += [("등록 코스 원문", e) for e in _read(data_dir / "courses.json", [])]
    registered_keys = {(_source_url(e), e.get("name")) for _, e in registered}
    pending_courses = []
    if raw_dir:
        raw_courses_path = raw_dir / "courses.json"
        if not raw_courses_path.exists():
            raw_courses_path = raw_dir.parent / f"{raw_dir.name}_courses.json"
        for index, entity in enumerate(_read(raw_courses_path, []), 1):
            if (_source_url(entity), entity.get("name")) in registered_keys:
                continue
            # This is a report locator, never a new entity ID or persisted slug.
            pending_courses.append(("미수입 수집 코스 원문", {
                **entity, "id": entity.get("id") or f"raw-course-row-{index}",
            }))

    originals, photos = [], []
    for scope, entity in registered + pending_courses:
        original = entity.get("original") or {}
        entity_id = entity.get("id") or "식별자 없음"
        code = _code(original.get("license", entity.get("license")), warnings, str(entity_id))
        proof = original.get("license_evidence") or original.get("evidence") or entity.get("license_evidence")
        observed = evidence_by_source.get((entity_id, _source_url(entity)),
                                          evidence_by_id.get(entity_id, {}))
        # A same ID at a different URL cannot silently supply rights evidence.
        if observed and observed.get("source_url") != _source_url(entity):
            warnings.append(f"{entity_id}: 근거 파일의 원문 URL이 달라 해당 근거를 사용하지 않음")
            observed = {}
        proof = proof or observed.get("license_evidence")
        proof = proof or f"데이터에 저장된 코드 {code}; 판별 근거 문자열 미저장"
        expected = original.get("sha256")
        hash_state = "미기록 (해시를 생성하거나 저장하지 않음)"
        text = original.get("text")
        if expected:
            if not isinstance(text, str):
                hash_state = "검증 실패: 원문 본문 누락"
                errors.append(f"{entity_id}: original.sha256이 있으나 원문 text가 문자열이 아님")
            elif hashlib.sha256(text.encode("utf-8")).hexdigest() != expected:
                hash_state = "불일치"
                errors.append(f"{entity_id}: original.sha256 불일치 — 원문 무결성 확인 필요")
            else:
                hash_state = "일치"
        elif scope != "미수입 수집 코스 원문":
            warnings.append(f"{entity_id}: original.sha256 미기록")
        originals.append({
            "scope": scope, "id": entity_id, "name": entity.get("name") or "명칭 없음",
            "url": _source_url(entity), "license": code, "evidence": str(proof),
            "sha256_check": hash_state,
        })
        if scope != "미수입 수집 코스 원문":
            photos += _image_rows(entity, entity.get("images") or [], "등록 사진", observed, warnings)

    observed_photos = []
    for entity in evidence:
        observed_photos += _image_rows(entity, entity.get("images") or [], "수집 관찰 사진", entity, warnings)

    return {
        "data_dir": str(data_dir), "raw_dir": str(raw_dir) if raw_dir else "미지정",
        "sample": data_dir.name == "sample", "allowed": allowed,
        "originals": originals, "photos": photos, "observed_photos": observed_photos,
        "warnings": warnings, "errors": errors,
    }


def _cell(value) -> str:
    return str(value).replace("|", "\\|").replace("\r", "").replace("\n", "<br>")


def _counts(rows: list[dict]) -> Counter:
    return Counter(row["license"] for row in rows)


def render(report: dict) -> str:
    originals = report["originals"]
    registered = [row for row in originals if row["scope"] != "미수입 수집 코스 원문"]
    pending = [row for row in originals if row["scope"] == "미수입 수집 코스 원문"]
    photos, observed = report["photos"], report["observed_photos"]
    groups = [("등록 장소·코스 원문", registered), ("미수입 수집 코스 원문", pending),
              ("등록 사진", photos), ("수집 관찰 사진", observed)]
    lines = ["# 이용조건 집계", ""]
    if report["sample"]:
        lines += ["**샘플 데이터 — 실제 권리 확인 결과가 아닙니다.**", ""]
    lines += [f"데이터: `{report['data_dir']}` / 수집 근거: `{report['raw_dir']}`", "",
              "이 보고서는 저장된 유형과 근거를 정리한 예상 집계입니다. 사람이 이용조건을 확정해야 합니다. "
              "데이터·원문·게재 규칙을 변경하지 않았으며 사진 파일을 다운로드하지 않았습니다.", "",
              "등록 원문은 장소와 코스를 항목별로 셉니다. 미수입 코스는 등록 데이터와 이름·원문 URL이 "
              "같은 항목을 제외합니다. 사진은 각 항목 안에서 동일 URL을 한 번만 세며, "
              "등록 사진과 수집 관찰 사진은 서로 중복될 수 있으므로 더하지 않습니다.", "",
              "## 유형별 건수", "", "| 구분 | 분모 | " + " | ".join(LICENSES) + " |",
              "|---|---:|" + "---:|" * len(LICENSES)]
    for label, rows in groups:
        counts = _counts(rows)
        lines.append(f"| {label} | {len(rows)} | " + " | ".join(str(counts[c]) for c in LICENSES) + " |")
    allowed_originals = report["allowed"]["allowed_original_licenses"]
    allowed_photos = report["allowed"]["allowed_image_licenses"]
    lines += ["", "## publish_rules 기준 예상", "",
              f"원문 허용 유형: {', '.join(allowed_originals) or '없음'} / "
              f"사진 허용 유형: {', '.join(allowed_photos) or '없음'}", "",
              "| 구분 | 전문 게재 가능 / 사진 게재 가능 | 링크 처리 / 사진 미게재 |",
              "|---|---:|---:|"]
    for label, rows in groups:
        allowed = allowed_photos if "사진" in label else allowed_originals
        permitted = sum(row["license"] in allowed for row in rows)
        lines.append(f"| {label} | {permitted} | {len(rows) - permitted} |")
    lines += ["", "KOGL-3은 변경 금지이므로 원문 그대로 게재하는 조건입니다. "
              "게재 가능 건수는 이용조건 기준이며 검수·공개 상태를 승인한 건수가 아닙니다. "
              "원문 해시 오류가 있으면 게재 전에 무결성 문제를 해결해야 합니다. "
              "사진은 원문의 유형을 물려받지 않고 사진별 유형만 사용합니다.", "",
              "## 원문 항목별 근거", "",
              "| 구분 | ID | 이름 | 원문 URL | 유형 | 판단 근거 | 원문 SHA-256 |",
              "|---|---|---|---|---|---|---|"]
    for row in originals:
        lines.append("| " + " | ".join(_cell(row[k]) for k in
                     ("scope", "id", "name", "url", "license", "evidence", "sha256_check")) + " |")
    for label, rows in [("등록 사진 항목별 근거", photos), ("수집 관찰 사진 항목별 근거", observed)]:
        lines += ["", f"## {label}", "", "| ID | 이름 | 사진 URL | 원문 URL | 유형 | 판단 근거 |",
                  "|---|---|---|---|---|---|"]
        for row in rows:
            lines.append("| " + " | ".join(_cell(row[k]) for k in
                         ("id", "name", "url", "source_url", "license", "evidence")) + " |")
        if not rows:
            lines += ["", "해당 사진 0건."]
    lines += ["", "## NONE·UNKNOWN 재확인 목록", "",
              "| 구분 | ID | 이름 | 유형 | 대상 URL | 판단 근거 |", "|---|---|---|---|---|---|"]
    unconfirmed = [row for row in originals + photos + observed if row["license"] in ("NONE", "UNKNOWN")]
    for row in unconfirmed:
        lines.append("| " + " | ".join(_cell(row[k]) for k in
                     ("scope", "id", "name", "license", "url", "evidence")) + " |")
    if not unconfirmed:
        lines += ["", "NONE·UNKNOWN 항목 0건."]
    lines += ["", "재확인 방법: 항목의 원문 URL과 저장된 HTML에서 본문 주변의 공공누리 이미지 "
              "alt·파일명·문구를 확인합니다. 사이트 공통 푸터를 개별 콘텐츠의 허용 근거로 쓰지 않습니다. "
              "사진은 사진별 캡션·권리 표기를 따로 확인하고, 확인되지 않으면 담당 부서에 이용조건을 "
              "문의합니다. 회신이나 구체적 표기 확인 전에는 원문 링크와 사진 미게재 처리를 유지합니다.", "",
              "## 오류·경고", "",
              f"오류 {len(report['errors'])}건 / 경고 {len(report['warnings'])}건.", ""]
    lines += [f"- 오류: {_cell(value)}" for value in report["errors"]]
    lines += [f"- 경고: {_cell(value)}" for value in report["warnings"]]
    return "\n".join(lines) + "\n"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--data", required=True, type=Path)
    parser.add_argument("--raw", type=Path)
    parser.add_argument("--out", default=Path("reports/rights_report.md"), type=Path)
    args = parser.parse_args(argv)
    report = inventory(args.data, args.raw)
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(render(report), "utf-8")
    print(json.dumps({"report": str(args.out), "originals": len(report["originals"]),
                      "registered_photos": len(report["photos"]),
                      "observed_photos": len(report["observed_photos"]),
                      "errors": len(report["errors"]), "warnings": len(report["warnings"])}, ensure_ascii=False))
    return 1 if report["errors"] else 0


if __name__ == "__main__":
    sys.exit(main())
