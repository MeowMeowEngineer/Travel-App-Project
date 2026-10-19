"""우리가 쓴 문장 검사 — 장소 요약·자주 묻는 질문·자세히, 가이드·코스 글, 행사 요약을 그 레코드에 저장된 출처 글과 사실 값에
대어 본다(pipeline/content_check.py). 네트워크를 쓰지 않고 아무 파일도 바꾸지 않는다.

    python tools/content_check.py --data data/incheon            # 걸린 곳마다 한 줄, 걸리면 종료 코드 1
    python tools/content_check.py --data data/incheon --json     # 기계용

요약·FAQ를 places.json에 넣은 뒤, 공개 선별(tools/build_review.py)·운영자 공개 승인 전에 돌린다. 걸린 문장은 고쳐 쓴다
(규칙을 완화하지 않는다).
- 원문 베끼기(CLAUDE.md 3절 3항): TourAPI overview(tourapi.overview, 사실 확인용으로만 저장)나 원문(original.text)과
  15자 이상 연속 일치(이름·사실 값은 빼고 센다). 이 검사는 빌드 검증(pipeline/validate.py)도 모든 페이지에 한다.
- 숫자 대조: 요약·FAQ 답·자세히의 숫자가 사실 값·다른 출처 값·이름·분류·출처 글에 있다.
- 출처 대조: FAQ의 source가 그 장소의 출처(원문·공식 홈페이지·값의 출처 주소, 값의 제공자 이름) 중 하나다.
- 표현(3절 5항): 출처 해설체('원문은…', '~라고 합니다'), '확인 필요' 문구, 근거 없는 수식어.
- FAQ(3절 6항): 질문은 존댓말 '~나요?/~인가요?', 같은 질문을 여러 장소에 두지 않는다.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

if __package__ in (None, ""):
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from pipeline.content_check import data_issues


def _load(path: Path) -> list:
    if not path.exists():
        return []
    value = json.loads(path.read_text("utf-8"))
    return value if isinstance(value, list) else []


def run(data: Path) -> dict[str, list[str]]:
    return data_issues(_load(data / "places.json"), _load(data / "guides.json"), _load(data / "courses.json"),
                       _load(data / "events.json"))


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--data", type=Path, default=Path("data/incheon"))
    ap.add_argument("--json", action="store_true", help="결과를 JSON으로")
    a = ap.parse_args(argv)
    if not (a.data / "site.json").exists():
        print(f"중단: {a.data / 'site.json'}이 없습니다 — --data에 지역 데이터 폴더(예: data/incheon)를 주세요.", file=sys.stderr)
        return 2
    found = run(a.data)
    n = sum(len(v) for v in found.values())
    if a.json:
        print(json.dumps({"records": len(found), "issues": n, "found": found}, ensure_ascii=False, indent=1))
    else:
        for rid, issues in found.items():
            for issue in issues:
                print(f"{rid} {issue}")
        print(f"검사: 걸린 레코드 {len(found)}곳 · 문제 {n}건" + ("" if n else " — 통과"))
    return 1 if n else 0


if __name__ == "__main__":
    sys.exit(main())
