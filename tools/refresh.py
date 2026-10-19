"""주간 갱신 한 번에 — TourAPI 다시 받기 → 공식 페이지 확인값 → 공개 사이트 빌드(public/, production) → 품질 리포트.

    python tools/refresh.py                 # 캐시 우선: 캐시에 없는 응답만 호출(실행당 상한 400회)
    python tools/refresh.py --fresh         # 응답을 새로 받는다(TourAPI 캐시 refresh 모드, 상한 --max-calls)
    python tools/refresh.py --offline       # 네트워크 없이 캐시로만
    python tools/refresh.py --dry-run       # 할 일만 출력하고 아무것도 실행하지 않는다

단계(모두 저장소 루트에서 실행)
0. TourAPI 연결 확인: `python tools/tourapi_doctor.py --json`. 안 되면 공급자 메시지를 키만 가려 그대로 보여 주고,
   1단계를 캐시 전용(--offline)으로 돌린다(--offline이면 건너뜀).
1. `python tools/tourapi_bulk.py --data <data> --details --add-new --events --max-calls 400 [--refresh | --offline]`
   — --fresh일 때만 --refresh(캐시 무시). 확인일은 응답을 받은 날짜라 캐시로 다시 돌려도 바뀌지 않는다.
   캐시 우선은 캐시에 없는 응답만 받는다: 행사 목록(searchFestival2)은 연도별로 캐시되므로 새 행사·바뀐 일정과
   바뀐 운영 정보를 받으려면 --fresh(행사 먼저, 그다음 대표·질문 장소 순으로 상한까지).
   실패해도 멈추지 않고 지금 데이터(마지막으로 받은 캐시 결과)로 2~4단계를 계속한다.
2. `python tools/round3_official.py --data <data>` — 시설 공식 페이지에서 확인한 값 재적용(멱등).
3. `python tools/build_public.py --data <data> --out public` — 공개(production) 빌드·검증·IndexNow 키 파일
   (2026-10-08 공개 전환 뒤. 새로 들어온 장소는 draft라 공개 승인 전까지 나가지 않는다 — tools/approve_publication.py).
4. `python tools/quality_report.py --data <data> --out public --md reports/quality_latest.md`.
끝나면 요약을 출력한다. git·push·배포·IndexNow 전송은 하지 않는다 — 사람이 `git diff`와 reports/를 보고 정한다.

종료 코드: 0 모두 정상 · 1 2~4단계 실패(미리보기 QA 오류 포함) · 2 TourAPI 단계만 실패·건너뜀(캐시로 재빌드는 완료)
"""
from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
from pathlib import Path

if __package__ in (None, ""):
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from pipeline.enrich import load_dotenv
from pipeline.tourapi import normalize_key, redact

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_MAX_CALLS = 400


def _python(args: list[str]) -> subprocess.CompletedProcess:
    """Run `python <args>` from the repository root (tests replace this)."""
    return subprocess.run([sys.executable, *args], cwd=ROOT, capture_output=True, text=True)


def _secrets() -> list[str]:
    """Every form of TOURAPI_KEY, for masking output (the key itself is never printed)."""
    load_dotenv(ROOT / ".env")
    raw = os.environ.get("TOURAPI_KEY", "").strip().strip('"').strip("'")
    return [k for k in dict.fromkeys((raw, normalize_key(raw))) if k]


def mask(text: str, secrets: list[str]) -> str:
    out = str(text or "")
    for key in secrets:
        out = redact(out, key)
    return out


def _json_line(text: str) -> dict:
    """The last line of a tool's stdout that is a JSON object (its summary), else {}."""
    for line in reversed((text or "").splitlines()):
        line = line.strip()
        if line.startswith("{"):
            try:
                return json.loads(line)
            except json.JSONDecodeError:
                continue
    return {}


def _json_out(text: str) -> dict:
    """A tool's whole stdout as one JSON object (tourapi_doctor --json prints it indented), else its summary line."""
    try:
        value = json.loads(text or "")
    except json.JSONDecodeError:
        return _json_line(text)
    return value if isinstance(value, dict) else {}


def _tail(proc: subprocess.CompletedProcess, n: int = 3) -> list[str]:
    """The message worth showing: a traceback's final line (the provider/network message), else the last lines."""
    errs = [x.strip() for x in (proc.stderr or "").splitlines() if x.strip()]
    if errs and any(x.startswith("Traceback") for x in errs):
        return errs[-1:]
    return (errs or [x.strip() for x in (proc.stdout or "").splitlines() if x.strip()])[-n:]


def plan(a) -> list[tuple[str, list[str]]]:
    data = str(a.data)
    bulk = ["tools/tourapi_bulk.py", "--data", data, "--details", "--add-new", "--events", "--max-calls", str(a.max_calls)]
    if a.offline:
        bulk.append("--offline")
    elif a.fresh:
        bulk.append("--refresh")
    steps = [] if a.offline else [("doctor", ["tools/tourapi_doctor.py", "--json"])]
    return steps + [
        ("tourapi", bulk),
        ("official", ["tools/round3_official.py", "--data", data]),
        ("preview", ["tools/build_public.py", "--data", data, "--out", str(a.out)]),
        ("quality", ["tools/quality_report.py", "--data", data, "--out", str(a.out),
                     "--md", str(Path(a.report_dir) / "quality_latest.md")]),
    ]


LABELS = {"doctor": "TourAPI 연결 확인", "tourapi": "TourAPI 갱신", "official": "공식 페이지 확인값",
          "preview": "공개 사이트 빌드(production)", "quality": "품질 리포트"}


def print_plan(a, steps) -> None:
    mode = "캐시 전용(--offline)" if a.offline else "새로 받기(--fresh → --refresh)" if a.fresh else "캐시 우선"
    print(f"[계획] 주간 갱신 — TourAPI {mode}, 실행당 호출 상한 {a.max_calls}회. 실행하지 않음(--dry-run).")
    for i, (key, args) in enumerate(steps, 1):
        note = ""
        if key == "doctor":
            note = "  ← 연결이 안 되면 다음 단계를 --offline(캐시 전용)으로 바꾼다"
        elif key == "tourapi":
            note = "  ← 실패해도 지금 데이터로 다음 단계를 계속한다"
        print(f"{i}. {LABELS[key]}: python {' '.join(args).replace(os.sep, '/')}{note}")
    print("git·push·배포·IndexNow 전송은 하지 않는다.")


def run(a) -> int:
    steps = plan(a)
    if a.dry_run:
        print_plan(a, steps)
        return 0
    secrets = _secrets()
    say = lambda text: print(mask(text, secrets), flush=True)
    summary: list[str] = []
    tourapi_ok, build_ok = True, True
    by_key = dict(steps)

    if "doctor" in by_key:
        proc = _python(by_key["doctor"])
        rep = _json_out(proc.stdout) or {"verdict": "진단 실패: " + " / ".join(_tail(proc))}
        verdict = str(rep.get("verdict") or "")
        say(f"[TourAPI 연결] {verdict}")
        if not verdict.startswith("정상"):
            tourapi_ok = False
            for at in rep.get("attempts") or []:
                r = at.get("result") or {}
                line = at.get("network_error") or (f"HTTP {at.get('http_status')} · code={r.get('code', '')} · "
                                                   f"{r.get('message', '')}")
                say(f"  - {at.get('service', '')}/{at.get('op', '')}: {line}")
            say("  → TourAPI 호출 없이 캐시로만 갱신하고 재빌드를 계속한다.")
            summary.append(f"TourAPI 연결 안 됨: {verdict} — 캐시 전용으로 전환")
            args = [x for x in by_key["tourapi"] if x != "--refresh"]
            by_key["tourapi"] = args + ([] if "--offline" in args else ["--offline"])

    proc = _python(by_key["tourapi"])
    res = _json_line(proc.stdout)
    if proc.returncode != 0 or not res:
        tourapi_ok = False
        say("[TourAPI 갱신] 중단 — 지금 데이터(마지막으로 받은 결과)로 재빌드를 계속한다.")
        for line in _tail(proc):
            say(f"  {line}")
        summary.append("TourAPI: 갱신 못 함(위 메시지) — 기존 데이터로 재빌드")
    else:
        ev = res.get("events") or {}
        new = res.get("new_places") or {}
        det = res.get("details") or {}
        mode = "캐시 전용" if "--offline" in by_key["tourapi"] else "새로 받기" if "--refresh" in by_key["tourapi"] else "캐시 우선"
        line = (f"TourAPI({mode}): 실호출 {res.get('live_calls', 0)} · 캐시 {res.get('cache_hits', 0)} · 상세 {det.get('done', 0)}곳"
                f" · 새 장소 {new.get('added', 0)} · 행사 추가 {ev.get('added', 0)}·갱신 {ev.get('updated', 0)}")
        if res.get("stopped"):
            line += f" · 중단: {res['stopped']}"
        errors = sum(int(x.get("errors", 0) or 0) for x in (det, new, ev) if isinstance(x, dict))
        if errors:
            line += f" · 항목 오류 {errors}(reports/tourapi_bulk.md)"
        summary.append(line)
        say(f"[TourAPI 갱신] {line}")

    proc = _python(by_key["official"])
    if proc.returncode != 0:
        build_ok = False
        say("[공식 페이지 확인값] 실패 — 이후 단계를 멈춘다.")
        for line in _tail(proc):
            say(f"  {line}")
        summary.append("공식 페이지 확인값: 실패 — 미리보기·품질 리포트를 만들지 않음")
    else:
        n = len([x for x in (proc.stdout or "").splitlines() if x.strip()])
        summary.append(f"공식 페이지 확인값: {n}줄 재적용(tools/round3_official.py)")
        say(f"[공식 페이지 확인값] {n}줄 재적용")

        proc = _python(by_key["preview"])
        rep = _json_line(proc.stdout)
        if not rep:
            build_ok = False
            say("[공개 사이트 빌드] 빌드 실패")
            for line in _tail(proc):
                say(f"  {line}")
            summary.append("공개 사이트: 빌드 실패")
        else:
            qa = int(rep.get("qa_errors", 0) or 0)
            build_ok = qa == 0
            line = (f"공개 사이트({a.out}/, production): 장소 {rep.get('selected', 0)}곳 · 색인 {rep.get('indexable', 0)}곳"
                    f" · QA 오류 {qa}")
            summary.append(line + ("" if qa == 0 else " — 위 ERROR 줄 확인, 오류가 있으면 배포하지 않는다"))
            say(f"[공개 사이트 빌드] {line}")
            proc = _python(by_key["quality"])
            md = Path(a.report_dir) / "quality_latest.md"
            if proc.returncode != 0:
                build_ok = False
                summary.append("품질 리포트: 실패")
                for line in _tail(proc):
                    say(f"  {line}")
            else:
                summary.append(f"품질 리포트: {md}")
            say(f"[품질 리포트] {'실패' if proc.returncode else md}")

    say("")
    say("== 주간 갱신 요약 ==")
    for line in summary:
        say(f"- {line}")
    say("- 다음(사람): `git diff --stat`으로 data/·public/ 변경 확인 → 커밋·push(=배포)는 사람이 정한다. "
        "production 배포 뒤에는 `python tools/indexnow.py --out <prod> --send`.")
    if not build_ok:
        return 1
    return 0 if tourapi_ok else 2


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--data", type=Path, default=Path("data/gunsan"))
    ap.add_argument("--out", type=Path, default=Path("public"))
    ap.add_argument("--report-dir", type=Path, default=Path("reports"))
    ap.add_argument("--max-calls", type=int, default=DEFAULT_MAX_CALLS)
    mode = ap.add_mutually_exclusive_group()
    mode.add_argument("--fresh", action="store_true", help="TourAPI 응답을 새로 받는다(캐시 refresh 모드)")
    mode.add_argument("--offline", action="store_true", help="네트워크 없이 캐시로만")
    ap.add_argument("--dry-run", action="store_true", help="할 일만 출력")
    a = ap.parse_args(argv)
    if a.max_calls < 1:
        ap.error("--max-calls는 1 이상")
    return run(a)


if __name__ == "__main__":
    sys.exit(main())
