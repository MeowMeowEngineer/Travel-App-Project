"""Generate a read-only human review checklist for draft preview pages.

    python tools/make_review_list.py --data data/incheon --out reports/review_list.md
    python tools/make_review_list.py --data data/incheon --base-url https://preview.example

Only an explicitly supplied --base-url creates absolute preview links. The
configured production site_url is never used as an inferred preview address.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys
from urllib.parse import quote, urlsplit

if __package__ in (None, ""):
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from pipeline.build import State, guide_has_content
from pipeline.schema import FACT_LABELS, KEY_FACTS, LICENSE_LABELS
from pipeline.textutil import sha256_text


def _cell(value) -> str:
    return str(value).replace("|", "\\|").replace("\r", "").replace("\n", "<br>")


def _rights_checks(item: dict, state: State, errors: list[str]) -> list[str]:
    original = item.get("original") or {}
    code = original.get("license") or "UNKNOWN"
    allowed = code in (state.site.get("publish_rules") or {}).get("allowed_original_licenses", [])
    checks = [f"원문 유형 {code}: {'전문 게재 가능 유형; 출처·원문 무수정 조건 확인' if allowed else '원문 링크 처리 유지; 유형 확인 또는 사전 협의 필요'}."]
    if code not in LICENSE_LABELS:
        checks.append("이용조건 코드 오류: 추측으로 유형을 바꾸지 말고 수집 근거를 재확인.")
    if code == "KOGL-3":
        checks.append("KOGL-3 변경 금지: 원문 전문과 사진이 변경·재작성·자르기 없이 표시되는지 확인.")
    text, expected = original.get("text"), original.get("sha256")
    if expected and isinstance(text, str):
        if sha256_text(text) == expected:
            checks.append("원문 SHA-256 일치: 저장 원문은 무결성 검사를 통과. 화면의 원문 처리도 확인.")
        else:
            error = f"{item.get('id', '')} 원문 SHA-256 불일치"
            errors.append(error)
            checks.append(f"{error}: 원문 대조 후 해결하기 전 승인 보류.")
    elif expected:
        errors.append(f"{item.get('id', '')} 원문 SHA-256은 있으나 본문 누락")
        checks.append("원문 SHA-256 검증 실패: 원문 본문 누락. 승인 보류.")
    else:
        checks.append("원문 SHA-256 미기록: 수집 원문과 대조 후 무결성 확인 필요.")
    url = original.get("source_url") or (item.get("official") or {}).get("source_url")
    checks.append(f"근거 원문: {url}" if url else "근거 원문 URL 누락: 원문 확보 전 승인 보류.")
    allowed_images = (state.site.get("publish_rules") or {}).get("allowed_image_licenses", [])
    photos = item.get("images") or []
    permitted = sum(image.get("license") in allowed_images for image in photos)
    checks.append(f"사진 {len(photos)}건: 허용 유형 {permitted}건 / 미게재 {len(photos) - permitted}건. 사진별 권리·출처·대체텍스트 확인; 원문 유형을 사진에 적용하지 않음.")
    return checks


def _place_checks(item: dict, state: State, errors: list[str]) -> list[str]:
    checks = _rights_checks(item, state, errors)
    facts = item.get("facts") or {}
    needed = ("address",) + KEY_FACTS.get(item.get("kind", "attraction"), ())
    missing = [FACT_LABELS[key] for key in needed if not facts.get(key)]
    checks.append("방문 전 정보 부족: " + "·".join(missing) + "; 공식 원문 또는 TourAPI 보강 필요." if missing else "주소·방문 전 정보: 표시값이 원문 또는 TourAPI 값과 같은지 확인.")
    if facts and not (item.get("facts_source") or {}).get("checked_at"):
        checks.append("실용 정보 확인일 미기록: 원문 수집일을 대신 넣지 말고 실제 확인 근거를 기록.")
    checks.append("요약 미작성: 근거 안에서 작성 필요." if not item.get("summary") else "요약: 모든 문장을 원문·TourAPI와 대조; 위치·수식어·운영정보 추정이 없는지 확인.")
    faq = item.get("faq") or []
    if item.get("tier") == "full":
        if not 3 <= len(faq) <= 5:
            checks.append(f"full FAQ {len(faq)}개: 표준의 3~5개 범위와 답변별 source 확인.")
        if not item.get("nearby"):
            checks.append("full 주변 장소 미작성: 근거 있는 볼거리·숙소·음식점 후보 확인. 코스·가이드 역참조와 구분.")
        media = item.get("media") or {}
        if not media.get("videos") and not media.get("news"):
            checks.append("full 영상·소식 미작성: 공식 채널 확인 전 비워 두고, 확보 후 출처·제목·날짜 확인.")
    if any(not row.get("source") for row in faq):
        checks.append("FAQ source 누락: 답변마다 실제 근거 또는 정보 부재를 판단한 원문 URL 기록 필요.")
    checks.append("지도·길찾기: 모바일에서 정확한 장소를 가리키는지 확인; 좌표·Place ID 없으면 검색 링크임을 확인.")
    return checks


def _linked_checks(items: list[dict], state: State, noun: str) -> list[str]:
    checks = []
    for item in items:
        slug, name = item.get("place_slug"), item.get("name")
        if slug:
            target = state.ent_by_slug.get(slug)
            if not target:
                checks.append(f"{noun} 연결 대상 없음: {slug}; 연결 또는 미리보기 포함 여부 재확인.")
            elif name and name != target.get("name"):
                checks.append(f"{noun} 명칭 불일치: {name!r} → {target.get('name')!r} ({slug}); 정확한 일치 확인 전 연결 승인 보류.")
            elif name:
                checks.append(f"{noun} 명칭 정확히 일치: {name} → {slug}; 원문의 순서와 대상 확인.")
            else:
                checks.append(f"{noun} 연결: {slug}; 저장 명칭이 없어 원문 명칭과 대상 {target.get('name')}의 정확한 일치를 사람이 확인.")
        elif name:
            matches = [p["slug"] for p in state.entities if p.get("name") == name]
            checks.append(f"{noun} 이름만 유지: {name}; " + (f"정확히 일치하는 후보 {', '.join(matches)} (자동 연결하지 않음)." if matches else "등록 장소명과 정확히 일치하지 않아 연결하지 않음."))
    return checks


def make_report(data_dir: Path, base_url: str = "") -> tuple[str, list[str], dict]:
    state = State(data_dir, "preview")  # Reads JSON; generated slugs stay in memory.
    errors, sections, counts = [], [], {}
    groups = [("장소", state.entities, "name"), ("가이드", state.guides_all, "title"),
              ("코스", state.courses, "name"), ("행사", state.events, "name")]
    for label, items, title_key in groups:
        drafts = [item for item in items if item.get("status") == "draft"]
        counts[label] = len(drafts)
        for item in drafts:
            path = item.get("_path") or (f"/guides/{item['slug']}/" if label == "가이드" else "/events/")
            link = base_url.rstrip("/") + quote(path, safe="/") if base_url else path
            name = _cell(item.get(title_key) or "명칭 없음")
            preview = (f"- 미리보기 미생성: 내용 작성 전 초안 (예정 경로: `{_cell(path)}`)"
                       if label == "가이드" and not guide_has_content(item)
                       else f"- 미리보기: [{_cell(path)}]({link})")
            section = [f"### {label}: {name}", "", f"- ID: {_cell(item.get('id') or '미기록')} / status: draft", preview]
            if label == "장소":
                checks = _place_checks(item, state, errors)
            elif label == "코스":
                checks = _rights_checks(item, state, errors)
                checks += _linked_checks(item.get("stops") or [], state, "경유지")
                checks.append("코스: 원문 순서 유지·명칭 완전 일치 시에만 연결. 줄바꿈 제거·약칭 확장으로 임의 매칭하지 않음.")
                if not item.get("summary"):
                    checks.append("코스 요약 미작성: 권리·근거 확인 후 작성 여부 결정.")
            elif label == "가이드":
                checks = _linked_checks(item.get("items") or [], state, "가이드 장소")
                checks.append("가이드 본문 미작성: 후보와 근거를 먼저 검토; 본문 작성·공개 결정은 별도 진행." if not item.get("body") else "가이드 본문: 조건별 추천이 원문·TourAPI 근거 안에 있는지 확인.")
                if not item.get("sources"):
                    checks.append("가이드 sources 미작성: 장소·교통·실내 여부 등 주장별 근거 URL 필요.")
                if not item.get("items"):
                    checks.append("가이드 후보 미연결: reports/guide_candidates.md와 후보 원문부터 검토.")
            else:
                checks = ["행사는 /events/ 목록에서 검수하며 개별 상세 URL은 생성되지 않음."]
                for key, text in [("source_url", "주최 측·정보 제공 출처 URL"), ("start_date", "시작일"),
                                  ("end_date", "종료일"), ("place_name", "행사 장소"), ("checked_at", "정보 확인일")]:
                    checks.append(f"{text}: {item.get(key) or '미기록 — 출처 확인 필요'}")
                checks.append("일정·장소·요금은 출처 확인 후 판단; 예정·취소 상태를 추정하지 않음.")
            section += [f"- 확인: {_cell(check)}" for check in checks]
            section += ["- 권장: 자료·이용조건·모바일 동작을 확인할 때까지 draft 유지. 사람 검수 후 승인 여부 결정.", ""]
            sections += section
    lines = ["# 미리보기 검수 목록", "", "**검수용 draft 목록입니다. 미리보기는 noindex이며 검색 수집을 차단합니다. "
             "이 목록 생성은 공개 승인이나 검수일 기입이 아닙니다.**", "",
             f"데이터: `{data_dir}` / 미리보기 기준 주소: `{base_url or '미지정 — 상대경로만 표시'}`", "",
             "미리보기 생성: `python -m pipeline.build --data " + str(data_dir) + " --out dist-preview --mode preview`", "",
             "| 구분 | draft 항목 수 |", "|---|---:|"]
    lines += [f"| {label} | {count} |" for label, count in counts.items()]
    lines += ["", "검수 순서: 원문·사진 이용조건 → 원문 무결성 → 사실·출처 → 관련 연결 → 모바일 화면. "
              "미작성 항목을 추정으로 채우지 않습니다. 원문·상태·slug·검수일·게재 규칙을 수정하지 않았습니다.", ""]
    lines += sections or ["draft 항목 0건.", ""]
    lines += ["## 무결성 오류", "", f"{len(errors)}건.", ""] + [f"- {_cell(error)}" for error in errors]
    return "\n".join(lines) + "\n", errors, counts


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--data", required=True, type=Path)
    parser.add_argument("--out", default=Path("reports/review_list.md"), type=Path)
    parser.add_argument("--base-url", default="")
    args = parser.parse_args(argv)
    if args.base_url:
        parsed = urlsplit(args.base_url)
        if parsed.scheme not in ("http", "https") or not parsed.netloc or parsed.username or parsed.password or parsed.query or parsed.fragment:
            parser.error("--base-url은 인증정보·쿼리·fragment 없는 http(s) 미리보기 주소여야 합니다")
    report, errors, counts = make_report(args.data, args.base_url)
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(report, "utf-8")
    print(json.dumps({"report": str(args.out), "draft": counts, "integrity_errors": len(errors)}, ensure_ascii=False))
    return 1 if errors else 0


if __name__ == "__main__":
    sys.exit(main())
