"""Dated facility notices (operator decision 2026-10-15, QA): special openings, substitute closures and changed hours
that a facility posts on its own homepage, e.g. a museum's notice board.

data/<region>/notices.json is a list, kept apart from places.json so a notice never changes a place record (nor its
translations' ko_hash). One entry:

    {"id": "museum-2026-10-06",                      unique, used as data-notice on the pages
     "place_ids": ["<place id>", "<place id>"],      the museum and each branch the post names (published places)
     "kind": "closed",                               open | closed | hours
     "date": "2026-10-06"  — or "start" / "end"      ISO dates (a range: start ≤ end)
     "from": "18:00", "to": "22:00", "last_entry": "21:40"   kind 'hours' only (last_entry optional)
     "provider": "○○박물관 홈페이지", "url": "<the post>", "checked_at": "<date we read it>",
     "until": "2026-10-06"}                          the last day the notice is shown (usually its last date)

Pages print only fixed words (pipeline/intl_text.py notice_*; the Korean below) with the dates, times, provider and
the link — no text of the post, so nothing needs translating and nothing of the facility's text is republished.
A notice whose `until` is before the build date is dropped automatically (active()). A person reads the facility's
board and writes the entries here.
"""
from __future__ import annotations

import datetime as dt
import json
import re
from pathlib import Path

KINDS = ("open", "closed", "hours")
HHMM = re.compile(r"^(?:[01]\d|2[0-4]):[0-5]\d$")
KO_WD = "월화수목금토일"
KO_WORD = {"open": "개관", "closed": "휴관"}
REQUIRED = ("provider", "url", "checked_at", "until")


def load(data_dir: Path) -> list[dict]:
    path = Path(data_dir) / "notices.json"
    if not path.exists():
        return []
    data = json.loads(path.read_text("utf-8"))
    return data if isinstance(data, list) else []


def _iso(value) -> dt.date | None:
    try:
        return dt.date.fromisoformat(str(value or ""))
    except ValueError:
        return None


def span(n: dict) -> tuple[str, str]:
    """(start, end) ISO dates of a notice ('date' is a one-day notice)."""
    start = str(n.get("start") or n.get("date") or "")
    return start, str(n.get("end") or start)


def problems(items: list[dict], places: dict[str, dict]) -> list[str]:
    """What is wrong with notices.json: every notice needs its provider, url, checked_at and until, a known kind,
    valid dates, times for 'hours', and only places this site publishes."""
    out, seen = [], set()
    for i, n in enumerate(items):
        nid = str(n.get("id") or "")
        w = nid or f"#{i}"
        if not nid:
            out.append(f"{w}: id 없음")
        elif nid in seen:
            out.append(f"{w}: id 중복")
        seen.add(nid)
        for f in REQUIRED:
            if not str(n.get(f) or "").strip():
                out.append(f"{w}: {f} 없음")
        if n.get("url") and not str(n["url"]).startswith(("https://", "http://")):
            out.append(f"{w}: url이 주소가 아님")
        if n.get("kind") not in KINDS:
            out.append(f"{w}: kind는 {'/'.join(KINDS)} 가운데 하나")
        start, end = span(n)
        if not (_iso(start) and _iso(end)) or start > end:
            out.append(f"{w}: 날짜(date 또는 start·end)가 올바르지 않음")
        for f in ("checked_at", "until"):
            if n.get(f) and not _iso(n[f]):
                out.append(f"{w}: {f} 날짜 형식(YYYY-MM-DD) 아님")
        if n.get("kind") == "hours":
            for f in ("from", "to"):
                if not HHMM.match(str(n.get(f) or "")):
                    out.append(f"{w}: hours에는 {f} 시각(HH:MM)이 필요")
            if n.get("last_entry") and not HHMM.match(str(n["last_entry"])):
                out.append(f"{w}: last_entry 시각(HH:MM) 아님")
        ids = n.get("place_ids") or []
        if not ids:
            out.append(f"{w}: place_ids 없음")
        for pid in ids:
            p = places.get(pid)
            if not p:
                out.append(f"{w}: 없는 장소 {pid}")
            elif p.get("status") != "published" or p.get("duplicate_of"):
                out.append(f"{w}: 공개하지 않는 장소 {pid}")
    return out


def active(items: list[dict], today: str) -> list[dict]:
    """Notices still to show on `today` (until ≥ today), complete ones only, by start date."""
    ok = [n for n in items if not problems([n], {pid: {"status": "published"} for pid in n.get("place_ids") or []})
          and str(n["until"]) >= today]
    return sorted(ok, key=lambda n: (span(n)[0], str(n.get("id"))))


def ko_date(iso: str, year: bool = True) -> str:
    d = dt.date.fromisoformat(iso)
    return f"{f'{d.year}년 ' if year else ''}{d.month}월 {d.day}일({KO_WD[d.weekday()]})"


def ko_dates(n: dict) -> str:
    start, end = span(n)
    if start == end:
        return ko_date(start)
    return f"{ko_date(start)}–{ko_date(end, year=end[:4] != start[:4])}"


def ko_text(n: dict) -> str:
    """'2026년 10월 6일(화) 휴관', '2026년 10월 9일(금)–10월 11일(일) 18:00–22:00 운영(입장 마감 21:40)'."""
    if n["kind"] == "hours":
        last = f"(입장 마감 {n['last_entry']})" if n.get("last_entry") else ""
        return f"{ko_dates(n)} {n['from']}–{n['to']} 운영{last}"
    return f"{ko_dates(n)} {KO_WORD[n['kind']]}"


def for_place(items: list[dict], place_id: str) -> list[dict]:
    return [n for n in items if place_id in (n.get("place_ids") or [])]
