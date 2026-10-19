"""공개 사이트 빌드 — public/(Vercel이 그대로 배포)을 production 모드로 다시 만들고 검증한다.

    python tools/build_public.py                       # data/gunsan → public/, production 검증, IndexNow 키 파일
    python tools/build_public.py --out /tmp/prod       # 다른 곳에 만들어 보기

- 2026-10-08 운영자 공개 전환 뒤로 public/은 production 빌드다(공개 레코드만, 색인 기준 미달은 noindex·sitemap 제외).
  이전의 선별 미리보기(tools/build_review.py, noindex)는 검수용으로만 쓴다.
- site.json에 indexnow_key가 있으면 <키>.txt를 함께 쓴다(IndexNow 전송은 tools/indexnow.py --send).
- 마지막 줄에 JSON 한 줄: selected(공개 장소 페이지 수)·indexable·qa_errors(검증 오류 수)·warnings.
  검증 오류가 있으면 종료 코드 1(배포하지 않는다).
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

if __package__ in (None, ""):
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from pipeline.build import build
from pipeline.validate import validate


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--data", type=Path, default=Path("data/gunsan"))
    ap.add_argument("--out", type=Path, default=Path("public"))
    a = ap.parse_args(argv)
    stats = build(a.data, a.out, "production")
    errors, warnings = validate(a.data, a.out, "production")[:2]
    for e in errors:
        print(f"ERROR {e}")
    site = json.loads((a.data / "site.json").read_text("utf-8"))
    key = site.get("indexnow_key") or ""
    if key:
        (a.out / f"{key}.txt").write_text(key, "utf-8")
    index = stats.get("index") or {}
    en = stats.get("en") or {}  # /en/ (pipeline/en_site.py): pages, indexable pages, stale translations skipped
    print(json.dumps({"selected": stats.get("entities", 0), "indexable": index.get("indexable", 0),
                      "pages": stats.get("pages", 0), "en_pages": en.get("pages", 0),
                      "en_indexable": en.get("indexable", 0),
                      "en_stale_skipped": sum((en.get("stale_skipped") or {}).values()),
                      # the other versions (/ja/ …) when data/<region>/<code> exists: pages each, and those not built
                      **({"intl_pages": {c: st.get("pages", 0) for c, st in stats["intl"].items()}} if stats.get("intl") else {}),
                      **({"intl_skipped": stats["intl_skipped"]} if stats.get("intl_skipped") else {}),
                      "qa_errors": len(errors), "warnings": len(warnings), "out": str(a.out)}, ensure_ascii=False))
    return 1 if errors else 0


if __name__ == "__main__":
    sys.exit(main())
