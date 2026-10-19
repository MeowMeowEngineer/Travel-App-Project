"""Build a curated noindex preview without editing source data.

A place is selected when its summary is written and it has visit information beyond the address
(full-tier places are always kept). Places that a course stop or a guide item points to (place_slug) are
always selected too, so the preview's course/guide links equal the data links; only duplicate records are
left out. Selection is not a person's review or approval. Courses are retained; the normal builder
decides whether draft guides have content. QA findings remain unchanged.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import sys
import tempfile

if __package__ in (None, ""):
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from pipeline.build import EMPTY_HINT, build
from pipeline.validate import validate, write_report


def _write_json(path, value):
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def run(data: Path, out: Path, report_dir: Path):
    data, out, report_dir = data.resolve(), out.resolve(), report_dir.resolve()
    if out.is_relative_to(data) or data.is_relative_to(out) or report_dir.is_relative_to(data):
        raise ValueError("Output/report directories must not overlap source data")
    snapshots = {path.name: path.read_bytes() for path in data.glob("*.json")}
    originals = json.loads(snapshots["places.json"])
    by_slug = {}
    for place in originals:
        slug = place.get("slug")
        if not slug or slug in by_slug:
            raise ValueError("Source place slugs must be present and unique")
        by_slug[slug] = place
    # Places a course stop or guide item links to: kept so the preview's course/guide links match the data.
    linked_from: dict[str, list[str]] = {}
    for filename, field in (("courses.json", "stops"), ("guides.json", "items")):
        if filename not in snapshots:
            continue
        for entry in json.loads(snapshots[filename]):
            for reference in entry.get(field) or []:
                target = reference.get("place_slug")
                where = f"{filename.removesuffix('.json')}:{entry.get('slug', entry.get('id', ''))}"
                if target and where not in linked_from.setdefault(target, []):
                    linked_from[target].append(where)

    def exclusion(place):
        if place.get("duplicate_of"):
            return "duplicate_record"
        if place["slug"] in linked_from:
            return ""
        if not (isinstance(place.get("summary"), str) and place["summary"].strip()):
            return "summary_not_written"
        practical = any(v and k not in ("address", "homepage") for k, v in (place.get("facts") or {}).items())
        if place.get("tier") != "full" and not practical:
            return "no_practical_info"
        return ""

    def selection_reason(place):
        if place.get("tier") == "full":
            return "full_tier"
        if (isinstance(place.get("summary"), str) and place["summary"].strip()
                and any(v and k not in ("address", "homepage") for k, v in (place.get("facts") or {}).items())):
            return "summary_and_practical_info"
        return "linked_from_course_or_guide"

    selected = [p for p in originals if not exclusion(p)]
    selected_slugs = {p["slug"] for p in selected}
    rendered_slugs = {p["slug"] for p in selected if p.get("status") in {"draft", "reviewed", "published"}}
    report = {"mode": "preview", "noindex": True,
              "selection_rule": "summary_and_practical_info_or_full_tier_or_linked_from_course_or_guide",
              "selection_meaning": "작성 준비 상태이며 사람 검수·게재 승인이 아님; status는 변경하지 않음",
              "data": str(data), "out": str(out), "source_place_count": len(originals),
              "selected": [{"id": p["id"], "slug": p["slug"], "name": p["name"], "status": p.get("status"),
                            "reason": selection_reason(p), "linked_from": linked_from.get(p["slug"], [])}
                           for p in selected],
              "excluded": [{"id": p["id"], "slug": p["slug"], "name": p["name"], "reason": exclusion(p)}
                           for p in originals if p["slug"] not in selected_slugs],
              "staging_link_changes": [], "private_files_omitted": [],
              "source_json_sha256": {name: hashlib.sha256(content).hexdigest() for name, content in snapshots.items()}}

    def unlink(reference, key, context):
        target = reference.get(key)
        if not target or target in rendered_slugs:
            return
        if not reference.get("name"):
            if target not in by_slug or not by_slug[target].get("name"):
                raise ValueError(f"Cannot preserve the name of unresolved reference: {context}/{target}")
            reference["name"] = by_slug[target]["name"]
        reference.pop(key)
        report["staging_link_changes"].append({"context": context, "removed_key": key, "target": target,
                                                "name": reference["name"], "reason": "target_not_in_curated_preview"})

    with tempfile.TemporaryDirectory(prefix="site-review-") as temporary:
        staged = Path(temporary)
        for name, content in snapshots.items():
            if name == "source_documents.json":
                report["private_files_omitted"].append(name)
                continue
            (staged / name).write_bytes(content)
        # Every object below comes from the decoded snapshot, never live files.
        for place in selected:
            for nearby in place.get("nearby") or []:
                unlink(nearby, "internal_slug", f"place:{place['slug']}/nearby")
        _write_json(staged / "places.json", selected)
        for filename, field in (("courses.json", "stops"), ("guides.json", "items")):
            path = staged / filename
            if not path.exists():
                continue
            entries = json.loads(path.read_bytes())
            for entry in entries:
                for reference in entry.get(field) or []:
                    unlink(reference, "place_slug", f"{filename}:{entry.get('slug', entry.get('id', ''))}/{field}")
            _write_json(path, entries)
            report[filename.removesuffix(".json") + "_retained"] = len(entries)
        # no place selected: say why in terms of the real data folder (never the temporary copy's path)
        empty = (EMPTY_HINT.format(places=data / "places.json", data=data) if not originals else
                 f"선별 0곳 — {data / 'places.json'}의 장소 {len(originals)}곳 가운데 요약과 주소 외 실용 정보가 함께 있는 "
                 "곳이 없습니다. 요약을 먼저 쓰세요(CLAUDE.md 3절 5항, 쓴 뒤 python tools/content_check.py --data "
                 f"{data}).")
        report["build"] = build(staged, out, "preview", empty_hint=empty)
        errors, warnings, stats = validate(staged, out, "preview")
        report.update(qa={"errors": errors, "warnings": warnings, "stats": stats},
                      status="built_with_qa_errors" if errors else "built")
        report_dir.mkdir(parents=True, exist_ok=True)
        write_report(errors, warnings, stats, report_dir / "review_build_qa.md")
    if {p.name: p.read_bytes() for p in data.glob("*.json")} != snapshots:
        raise RuntimeError("Source data changed during build; output must be regenerated from the new snapshot")
    report["source_data_unchanged"] = True
    _write_json(report_dir / "review_build_selection.json", report)
    by_link = [p for p in report["selected"] if p["reason"] == "linked_from_course_or_guide"]
    lines = ["# 검토 사이트 빌드 범위", "", report["selection_meaning"], "",
             f"- 장소: 원본 {len(originals)} / 선택 {len(selected)} / 제외 {len(report['excluded'])}",
             f"- 코스·가이드가 가리켜서 포함: {len(by_link)}곳(요약·실용 정보 기준으로는 제외 대상)",
             f"- 코스 유지: {report.get('courses_retained', 0)}", "- preview 모드: noindex 및 robots 수집 차단",
             f"- QA: 오류 {len(errors)} / 경고 {len(warnings)} (검증 규칙 변경 없음)",
             "- 원본 JSON·status·site 설정·original 변경 없음", "", "## 코스·가이드 연결로 포함한 장소", ""]
    lines += [f"- {p['slug']} — {p['name']}: {', '.join(p['linked_from'])}" for p in by_link] or ["- 없음"]
    lines += ["", "## 제외 장소", ""]
    reasons = {"summary_not_written": "요약 미작성", "no_practical_info": "주소 외 실용 정보 없음",
               "duplicate_record": "중복 기록"}
    lines += [f"- {p['slug']} — {p['name']}: {reasons[p['reason']]}" for p in report["excluded"]]
    (report_dir / "review_build_selection.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
    return report


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--data", type=Path, default=Path("data/incheon"))
    parser.add_argument("--out", type=Path, default=Path("public"))
    parser.add_argument("--report-dir", type=Path, default=Path("reports"))
    args = parser.parse_args(argv)
    report = run(args.data, args.out, args.report_dir)
    print(json.dumps({"status": report["status"], "selected": len(report["selected"]),
                      "selected_by_course_or_guide_link": sum(p["reason"] == "linked_from_course_or_guide"
                                                              for p in report["selected"]),
                      "excluded": len(report["excluded"]), "qa_errors": len(report["qa"]["errors"])}, ensure_ascii=False))
    return 1 if report["qa"]["errors"] else 0


if __name__ == "__main__":
    raise SystemExit(main())
