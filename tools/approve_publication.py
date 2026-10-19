"""운영자 공개 승인 반영 — 운영자가 공개를 결정한 레코드를 status=published로 바꾸고 approved_at·approved_by를 남긴다.

    python tools/approve_publication.py --date 2026-10-08                       # 미리 보기(기본, 쓰지 않음)
    python tools/approve_publication.py --date 2026-10-08 --apply               # 반영
    python tools/approve_publication.py --date 2026-10-08 --hold <id> ... --apply  # 이 ID들은 공개하지 않음(draft로 둠)

- 장소: 미리보기 선별(reports/review_build_selection.json의 selected — 요약과 주소 외 실용 정보가 있는 곳, 코스·가이드가
  가리키는 곳)만. 가이드·코스·행사: 제외(exclude)·중복이 아닌 것 전부.
- reviewed_at(사람 검수일)은 건드리지 않는다. approved_at은 '운영자가 공개를 승인한 날'이며 화면에 검수일로 보이지 않는다.
  색인은 그래도 색인 기준(유형별 필수 정보 2개 이상·요약 규칙)을 통과한 장소만 된다(pipeline/schema.index_status).
- 2026-10-08 운영자 결정(site.json publication)으로 만든 도구다. 새로 들어온 레코드는 draft로 남으므로, 다음 공개 때 다시 실행한다.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def _dump(path: Path, data) -> None:
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", "utf-8")


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--data", type=Path, default=ROOT / "data" / "incheon")
    ap.add_argument("--selection", type=Path, default=ROOT / "reports" / "review_build_selection.json")
    ap.add_argument("--date", required=True)
    ap.add_argument("--by", default="운영자 공개 승인(페이지별 검수 전)")
    ap.add_argument("--hold", nargs="*", default=[], help="공개하지 않을 레코드 ID")
    ap.add_argument("--apply", action="store_true")
    a = ap.parse_args(argv)

    selected = {x["id"] for x in json.loads(a.selection.read_text("utf-8"))["selected"]}
    hold = set(a.hold)
    counts = {}
    for name, pick in (("places", lambda r: r["id"] in selected), ("guides", lambda r: True),
                       ("courses", lambda r: True), ("events", lambda r: True)):
        path = a.data / f"{name}.json"
        if not path.exists():   # a region right after its first collection has no guides or courses yet
            counts[name] = {"published_now": 0, "held": 0, "published_total": 0, "file": "없음"}
            continue
        rows = json.loads(path.read_text("utf-8"))
        n = held = 0
        for r in rows:
            if r.get("exclude") or r.get("duplicate_of") or not pick(r):
                continue
            if r.get("id") in hold:
                if r.get("status") == "published" and r.get("approved_at"):
                    r["status"] = "draft"
                    r.pop("approved_at", None)
                    r.pop("approved_by", None)
                held += 1
                continue
            if r.get("status") != "published" or not r.get("approved_at"):
                r["status"] = "published"
                r["approved_at"] = r.get("approved_at") or a.date
                r["approved_by"] = r.get("approved_by") or a.by
                n += 1
        counts[name] = {"published_now": n, "held": held,
                        "published_total": sum(1 for r in rows if r.get("status") == "published")}
        if a.apply:
            _dump(path, rows)
    print(json.dumps({"apply": a.apply, **counts}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    sys.exit(main())
