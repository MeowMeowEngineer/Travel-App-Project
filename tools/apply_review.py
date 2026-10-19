"""검수 시트 반영 — 사람이 판정 칸에 OK라고 적은 행만 status=reviewed·reviewed_at=날짜로 바꾼다.

    python tools/apply_review.py --sheet docs/handover/review_round3.csv                # 미리 보기(기본, 쓰지 않음)
    python tools/apply_review.py --sheet docs/handover/review_round3.csv --apply        # 반영
    python tools/apply_review.py --sheet ... --data data/incheon --date 2026-10-20 --apply

- 판정이 OK(앞뒤 공백·대소문자 무시)인 행: 지금 status가 draft·reviewed일 때만 reviewed + reviewed_at(기본 오늘).
  published는 건드리지 않고, 어떤 행도 published로 바꾸지 않는다(공개는 사람이 정한다 — CLAUDE.md 3절 7항).
- 판정이 '수정'인 행: 메모와 함께 할 일 목록으로 보여 주기만 한다.
- 판정이 비어 있으면 건너뛴다. 그 밖의 값은 '읽지 않은 판정'으로 보여 주고 건너뛴다.
- 시트가 지금 데이터와 맞지 않으면(알 수 없는 구분·ID, 겹친 ID, 바뀐 이름) 아무것도 쓰지 않고 종료 코드 1로 끝낸다.
  시트를 다시 만들려면 tools/make_review_sheet.py.
- --apply는 해당 레코드의 status·reviewed_at만 바꾸고 파일을 저장소 형식(ensure_ascii=False, indent=2, 끝 줄바꿈)으로 쓴다.
- 엑셀이 CP949로 다시 저장한 시트도 읽는다.
"""
from __future__ import annotations

import argparse
import csv
import datetime as dt
import io
import json
import re
import sys
import unicodedata
from pathlib import Path

if __package__ in (None, ""):
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from tools.make_review_sheet import KINDS

EDITABLE = ("draft", "reviewed")
REQUIRED = ("구분", "ID", "이름", "판정")


class SheetError(Exception):
    """The sheet does not match the data; nothing was written."""


def _norm(value) -> str:
    return re.sub(r"\s+", " ", unicodedata.normalize("NFC", str(value or ""))).strip()


def dump(data) -> str:
    return json.dumps(data, ensure_ascii=False, indent=2) + "\n"


def read_sheet(path: Path) -> list[tuple[int, dict]]:
    raw = path.read_bytes()
    for encoding in ("utf-8-sig", "cp949"):
        try:
            text = raw.decode(encoding)
            break
        except UnicodeDecodeError:
            continue
    else:
        raise SheetError(f"{path}: UTF-8이나 CP949로 읽을 수 없습니다. CSV UTF-8로 다시 저장해 주세요.")
    reader = csv.DictReader(io.StringIO(text, newline=""))
    reader.fieldnames = [_norm(h) for h in reader.fieldnames or []]
    missing = [h for h in REQUIRED if h not in reader.fieldnames]
    if missing:
        raise SheetError(f"{path}: 필요한 열이 없습니다: {', '.join(missing)}")
    rows = []
    for number, row in enumerate(reader, start=2):  # 1행은 머리글 — 엑셀의 행 번호와 같다
        if any(_norm(v) for v in row.values() if isinstance(v, str)):
            rows.append((number, {k: (v if isinstance(v, str) else "") for k, v in row.items() if k}))
    return rows


def plan(rows: list[tuple[int, dict]], data: Path, date: str) -> dict:
    """Check every row against the data and work out the changes. Raises SheetError listing all problems."""
    texts = {kind: (data / KINDS[kind][0]).read_text("utf-8") for kind in KINDS if (data / KINDS[kind][0]).exists()}
    loaded = {kind: json.loads(text) for kind, text in texts.items()}
    errors, seen = [], {}
    result = {"changes": [], "todo": [], "skipped": [], "unchanged": [], "unread": [], "pending": 0, "loaded": loaded,
              "texts": texts}
    for number, row in rows:
        kind, rid, name = _norm(row.get("구분")), _norm(row.get("ID")), _norm(row.get("이름"))
        where = f"{number}행({kind or '구분 없음'} {rid or 'ID 없음'})"
        if kind not in KINDS:
            errors.append(f"{where}: 알 수 없는 구분 '{kind}' — {'/'.join(KINDS)} 중 하나여야 합니다")
            continue
        if not rid:
            errors.append(f"{where}: ID가 비어 있습니다")
            continue
        if (kind, rid) in seen:
            errors.append(f"{where}: 같은 ID가 {seen[(kind, rid)]}행에도 있습니다")
            continue
        seen[(kind, rid)] = number
        hits = [i for i, item in enumerate(loaded.get(kind, [])) if _norm(item.get("id")) == rid]
        if not hits:
            errors.append(f"{where}: {KINDS[kind][0]}에 없는 ID입니다")
            continue
        if len(hits) > 1:
            errors.append(f"{where}: {KINDS[kind][0]}에 같은 ID가 {len(hits)}개 있습니다")
            continue
        record = loaded[kind][hits[0]]
        current = _norm(record.get(KINDS[kind][1]))
        if name != current:
            errors.append(f"{where}: 이름이 데이터와 다릅니다 — 시트 '{name}' / 데이터 '{current}'")
            continue
        verdict, memo = _norm(row.get("판정")), _norm(row.get("메모"))
        entry = {"row": number, "kind": kind, "id": rid, "name": current, "index": hits[0], "memo": memo,
                 "status": record.get("status"), "reviewed_at": record.get("reviewed_at")}
        if not verdict:
            result["pending"] += 1
        elif verdict.lower() == "ok":
            if record.get("status") not in EDITABLE:
                result["skipped"].append(entry)
            elif record.get("status") == "reviewed" and record.get("reviewed_at") == date:
                result["unchanged"].append(entry)
            else:
                result["changes"].append(entry)
        elif verdict == "수정":
            result["todo"].append(entry)
        else:
            result["unread"].append({**entry, "verdict": verdict})
    if errors:
        raise SheetError("시트가 지금 데이터와 맞지 않아 아무것도 쓰지 않았습니다:\n" + "\n".join(f"  - {e}" for e in errors)
                         + "\n시트를 고치거나 tools/make_review_sheet.py로 다시 만든 뒤 판정을 옮겨 적어 주세요.")
    return result


def mark_reviewed(record: dict, date: str) -> dict:
    """status -> reviewed, reviewed_at -> date. A new reviewed_at key goes right after status; nothing else moves."""
    if "reviewed_at" in record:
        return {**record, "status": "reviewed", "reviewed_at": date}
    out = {}
    for key, value in record.items():
        out[key] = "reviewed" if key == "status" else value
        if key == "status":
            out["reviewed_at"] = date
    return out


def write_changes(result: dict, data: Path, date: str) -> list[str]:
    kinds = sorted({c["kind"] for c in result["changes"]}, key=list(KINDS).index)
    for kind in kinds:  # check every file before writing any
        if dump(json.loads(result["texts"][kind])) != result["texts"][kind]:
            raise SheetError(f"{KINDS[kind][0]}이 저장소 형식(indent=2, ensure_ascii=False)과 달라 다시 쓰면 다른 줄까지 바뀝니다. "
                             "아무것도 쓰지 않았습니다.")
    written = []
    for kind in kinds:
        items = result["loaded"][kind]
        for change in (c for c in result["changes"] if c["kind"] == kind):
            items[change["index"]] = mark_reviewed(items[change["index"]], date)
        (data / KINDS[kind][0]).write_text(dump(items), "utf-8")
        written.append(KINDS[kind][0])
    return written


def report(result: dict, date: str, applied: bool) -> list[str]:
    def label(e: dict) -> str:
        return f"{e['row']}행 {e['kind']} {e['id']} {e['name']}"

    lines = [f"{'반영' if applied else '반영 예정(미리 보기)'} {len(result['changes'])}건 — status reviewed, reviewed_at {date}:"]
    lines += [f"  - {label(e)}: {e['status']}" + (f" (reviewed_at {e['reviewed_at']})" if e["reviewed_at"] else "") + " → reviewed"
              for e in result["changes"]] or ["  (없음)"]
    if result["todo"]:
        lines += [f"수정 요청 {len(result['todo'])}건 — 할 일:"]
        lines += [f"  - {label(e)}: {e['memo'] or '메모 없음'}" for e in result["todo"]]
    if result["skipped"]:
        lines += [f"OK지만 바꾸지 않음 {len(result['skipped'])}건(draft·reviewed만 바꾼다):"]
        lines += [f"  - {label(e)}: status {e['status']}" for e in result["skipped"]]
    if result["unchanged"]:
        lines += [f"이미 reviewed {date}: {len(result['unchanged'])}건"]
    if result["unread"]:
        lines += [f"읽지 않은 판정 {len(result['unread'])}건(OK 또는 수정만 읽는다):"]
        lines += [f"  - {label(e)}: '{e['verdict']}'" for e in result["unread"]]
    lines += [f"판정 없음 {result['pending']}건."]
    return lines


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--sheet", default=Path("docs/handover/review_round3.csv"), type=Path)
    parser.add_argument("--data", default=Path("data/incheon"), type=Path)
    parser.add_argument("--date", default=dt.date.today().isoformat(), help="reviewed_at 값(YYYY-MM-DD, 기본 오늘)")
    parser.add_argument("--apply", action="store_true", help="파일에 쓴다(없으면 미리 보기만)")
    args = parser.parse_args(argv)
    try:
        if not re.fullmatch(r"\d{4}-\d{2}-\d{2}", args.date):
            raise ValueError
        dt.date.fromisoformat(args.date)
    except ValueError:
        parser.error(f"--date는 YYYY-MM-DD 형식이어야 합니다: {args.date}")
    try:
        result = plan(read_sheet(args.sheet), args.data, args.date)
        written = write_changes(result, args.data, args.date) if args.apply and result["changes"] else []
    except (SheetError, FileNotFoundError) as exc:
        print(f"반영 거부: {exc}", file=sys.stderr)
        return 1
    print("\n".join(report(result, args.date, args.apply)))
    if args.apply:
        print("저장: " + (", ".join(str(args.data / name) for name in written) if written else "바뀐 파일 없음"))
    else:
        print("미리 보기만 했습니다. 파일에 쓰려면 --apply를 붙입니다.")
    print("published 전환은 이 스크립트가 하지 않습니다(사람 결정).")
    return 0


if __name__ == "__main__":
    sys.exit(main())
