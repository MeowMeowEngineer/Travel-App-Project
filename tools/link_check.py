"""External link check for the homepage / booking addresses the site links (QA 2026-10-15 SRC-02c).

    python tools/link_check.py --data data/incheon [--max 150] [--timeout 15] [--guides] [--apply]

Run it by hand about once a month from a Korean network, before tools/build_public.py: many Korean government and
hotel sites reset connections or show a firewall page to foreign addresses, which says nothing about the site.

What it reads: published places' facts.homepage / facts.reservationurl / official.homepage and the same keys'
fact_alternatives, published events' homepage, the booking pages of data/<region>/booking.json (예약하기 buttons:
each service's Korean page and its pages in other languages), and with --guides each published guide's sources[].url. Addresses
data/<region>/dead_links.json already lists are skipped. At most --max addresses per run (the rest next time).

A status code alone cannot see a dead site: modoo! answers HTTP 200 with its shutdown notice, a lapsed domain answers
200 for whoever bought it. So each address gets one class (classify()):
  dead     the domain does not exist (NXDOMAIN), or HTTP 404 / 410
  ended    HTTP 200 with a 'service ended' / parked-domain page (ENDED_PATTERNS)
  moved    the final address after redirects, or a short page's meta refresh / location.replace target, is on
           another site (http→https and www. changes are not a move)
  blocked  HTTP 403, a firewall / '접근 제한' page, errdoc.gabia.io, a reset or a timeout: re-check from Korea
  ok       anything else
The report goes to reports/link_check.md (id, name, field, url, class, evidence, date). --apply adds only dead,
ended and moved rows to dead_links.json 'urls' (reason + checked_at) for a person to review in git diff; blocked
and ok rows are never written. Nothing is stored about a page but those few words of evidence.
If the DNS lookup of a well-known host (CONTROL_HOST) fails, the network cannot tell dead from unreachable: the
run stops with exit code 2 and writes nothing.
"""
from __future__ import annotations

import argparse
import datetime as dt
import json
import re
import socket
import sys
import urllib.error
import urllib.request
from pathlib import Path
from urllib.parse import urljoin, urlsplit

if __package__ in (None, ""):
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from pipeline.textutil import DEAD_LINK_KEYS, dead_reason, link_url, squash_ws, url_domain  # noqa: E402

CONTROL_HOST = "www.naver.com"
UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0 Safari/537.36")
BODY_MAX = 200_000
SCRIPT_BODY_MAX = 5_000       # a scripted redirect counts only on a short page (not a site's own analytics code)
ENDED_PATTERNS = [re.compile(p, re.I) for p in (
    r"modoo!가 \d{4}년 \d{1,2}월 \d{1,2}일", r"서비스(?:를|가)?\s*종료", r"(?:service|site) (?:has been )?(?:terminated|discontinued|closed)",
    r"(?:domain|도메인).{0,20}(?:for sale|판매|만료|expired)", r"sedoparking|parkingcrew|bodis\.com|hugedomains|dan\.com")]
BLOCKED_PATTERNS = [re.compile(p, re.I) for p in (r"ninjafirewall", r"접근\s*제한", r"errdoc\.gabia\.io", r"access denied")]
REDIRECT = [re.compile(p, re.I) for p in (
    r"<meta[^>]+http-equiv=[\"']?refresh[\"']?[^>]+content=[\"'][^\"']*url=([^\"'>\s]+)",
    r"location\.replace\(\s*[\"']([^\"']+)[\"']", r"location\.href\s*=\s*[\"']([^\"']+)[\"']",
    r"window\.location\s*=\s*[\"']([^\"']+)[\"']")]
SECOND_LEVEL = {"co", "or", "go", "ac", "ne", "re", "pe", "ms", "hs", "es", "sc", "kg", "com", "net", "org"}
APPLY_CLASSES = {"dead": "도메인 없음 또는 없는 페이지", "ended": "서비스 종료·주차 도메인 안내만 보임",
                 "moved": "다른 사이트로 넘어감"}


def site_key(host: str) -> str:
    """The registrable part of a host: 'hotelrg2581.modoo.at' -> 'modoo.at', 'www.sunu.co.kr' -> 'sunu.co.kr'."""
    labels = [x for x in (host or "").lower().removeprefix("www.").split(".") if x]
    n = 3 if len(labels) >= 3 and labels[-2] in SECOND_LEVEL and len(labels[-1]) == 2 else 2
    return ".".join(labels[-n:])


def collect(data: Path, guides: bool = False) -> list[dict]:
    """The external addresses the published pages link: one row per address, {url, ids, names, field}."""
    load = lambda name: json.loads((data / name).read_text("utf-8")) if (data / name).exists() else []
    rows: dict[str, dict] = {}

    def add(url, rec_id: str, name: str, field: str):
        link = link_url(url)
        if link:
            row = rows.setdefault(link, {"url": link, "ids": [], "names": [], "field": field})
            if rec_id not in row["ids"]:
                row["ids"].append(rec_id)
                row["names"].append(name)

    for p in load("places.json"):
        if p.get("status") != "published" or p.get("duplicate_of"):
            continue
        for key in DEAD_LINK_KEYS:
            add((p.get("facts") or {}).get(key), p["id"], p.get("name", ""), f"facts.{key}")
            for a in (p.get("fact_alternatives") or {}).get(key) or []:
                add(a.get("value"), p["id"], p.get("name", ""), f"fact_alternatives.{key}")
        add((p.get("official") or {}).get("homepage"), p["id"], p.get("name", ""), "official.homepage")
    for e in load("events.json"):
        if e.get("status") == "published":
            add(e.get("homepage"), e.get("id", ""), e.get("name", ""), "event.homepage")
    if guides:
        for g in load("guides.json"):
            if g.get("status") == "published":
                for s in g.get("sources") or []:
                    add(s.get("url"), g["id"], g.get("title", ""), "guide.sources")
    # 예약하기 (pipeline/booking.py): every official booking page the buttons open, Korean and each language's
    booking = json.loads((data / "booking.json").read_text("utf-8")) if (data / "booking.json").exists() else {}
    for key, s in (booking.get("services") or {}).items():
        for u in [s.get("url"), *(s.get("pages") or {}).values()]:
            add(u, f"booking:{key}", key, "booking.services")
    return list(rows.values())


def fetch(url: str, timeout: float = 15) -> dict:
    """{status, final, body, err} for one address: a DNS pre-check (NXDOMAIN -> err 'nxdomain'), then one GET that
    follows redirects. Only the first BODY_MAX characters are read; nothing in the page is run."""
    host = urlsplit(url).hostname or ""
    try:
        socket.getaddrinfo(host, 443)
    except socket.gaierror as err:
        return {"status": None, "final": url, "body": "",
                "err": "nxdomain" if err.errno == socket.EAI_NONAME else f"dns {err}"}
    req = urllib.request.Request(url, headers={"User-Agent": UA, "Accept-Language": "ko-KR,ko;q=0.9"})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            body = resp.read(BODY_MAX).decode("utf-8", "replace")
            return {"status": resp.status, "final": resp.geturl(), "body": body, "err": ""}
    except urllib.error.HTTPError as err:
        try:
            body = err.read(BODY_MAX).decode("utf-8", "replace")
        except (OSError, AttributeError):
            body = ""
        return {"status": err.code, "final": err.geturl() or url, "body": body, "err": ""}
    except (urllib.error.URLError, TimeoutError, OSError) as err:
        return {"status": None, "final": url, "body": "", "err": f"{type(err).__name__}: {err}"}


def classify(url: str, status, final: str, body: str, err: str) -> tuple[str, str]:
    """(class, evidence of at most 80 characters) — see the module docstring."""
    body = body or ""
    clip = lambda s: squash_ws(s)[:80]
    if err == "nxdomain":
        return "dead", "도메인 없음(NXDOMAIN)"
    if err:
        return "blocked", clip(f"연결 실패 — 한국에서 다시 확인: {err}")
    if status in (404, 410):
        return "dead", f"HTTP {status}"
    for rx in BLOCKED_PATTERNS:
        m = rx.search(f"{final} {body[:20000]}")
        if m:
            return "blocked", clip(f"HTTP {status} 차단 화면({m.group(0)}) — 한국에서 다시 확인")
    if status == 403:
        return "blocked", "HTTP 403 — 한국에서 다시 확인"
    if status == 200:
        for rx in ENDED_PATTERNS:
            m = rx.search(body)
            if m:
                return "ended", clip(f"HTTP 200 종료 안내: {m.group(0)}")
    targets = [final] + ([urljoin(final or url, m.group(1)) for rx in REDIRECT for m in [rx.search(body)] if m]
                         if len(body) <= SCRIPT_BODY_MAX else [])
    home = site_key(url_domain(url))
    for t in targets:
        there = site_key(url_domain(t))
        if there and home and there != home:
            return "moved", clip(f"다른 사이트로 감: {url_domain(t)}")
    return "ok", f"HTTP {status}"


def apply_rows(dead: dict, rows: list[dict], today: str) -> int:
    """Add the dead / ended / moved rows to dead_links.json 'urls'; returns how many were added."""
    urls = dead.setdefault("urls", {})
    n = 0
    for r in rows:
        if r["class"] in APPLY_CLASSES and r["url"] not in urls:
            urls[r["url"]] = {"reason": f"{APPLY_CLASSES[r['class']]} — {r['evidence']}", "checked_at": today}
            n += 1
    return n


def run(data: Path, max_n: int = 150, timeout: float = 15, guides: bool = False, apply: bool = False,
        report_dir: Path = Path("reports"), today: str | None = None) -> int:
    today = today or dt.date.today().isoformat()
    try:
        socket.getaddrinfo(CONTROL_HOST, 443)
    except OSError:
        print(f"네트워크/DNS 사용 불가({CONTROL_HOST} 조회 실패) — 아무것도 쓰지 않고 멈춥니다", file=sys.stderr)
        return 2
    path = data / "dead_links.json"
    dead = json.loads(path.read_text("utf-8")) if path.exists() else {}
    todo = [r for r in collect(data, guides) if not dead_reason(r["url"], dead)]
    rows = []
    for r in todo[:max_n]:
        got = fetch(r["url"], timeout)
        cls, evidence = classify(r["url"], got["status"], got["final"], got["body"], got["err"])
        rows.append({**r, "class": cls, "evidence": evidence})
    counts = {c: sum(r["class"] == c for r in rows) for c in ("dead", "ended", "moved", "blocked", "ok")}
    lines = [f"# 외부 링크 점검 ({today})", "", f"- 대상 {len(todo)}건 중 {len(rows)}건 확인 · {counts}"
             + (f" · 남은 {len(todo) - len(rows)}건은 다음 실행" if len(todo) > len(rows) else ""),
             "- blocked는 해외에서 막힌 것일 수 있어 한국 네트워크에서 다시 확인한다. dead·ended·moved만 --apply 대상.", "",
             "| id | 이름 | 필드 | 주소 | 판정 | 근거 | 확인일 |", "|---|---|---|---|---|---|---|"]
    order = {"dead": 0, "ended": 1, "moved": 2, "blocked": 3, "ok": 4}
    for r in sorted(rows, key=lambda r: (order[r["class"]], r["url"])):
        lines.append(f"| {', '.join(r['ids'])} | {', '.join(r['names'])} | {r['field']} | {r['url']} | {r['class']} | "
                     f"{r['evidence'].replace('|', '/')} | {today} |")
    report_dir.mkdir(parents=True, exist_ok=True)
    (report_dir / "link_check.md").write_text("\n".join(lines) + "\n", "utf-8")
    added = 0
    if apply:
        added = apply_rows(dead, rows, today)
        if added:
            path.write_text(json.dumps(dead, ensure_ascii=False, indent=2) + "\n", "utf-8")
    print(json.dumps({"checked": len(rows), "remaining": len(todo) - len(rows), **counts, "added": added},
                     ensure_ascii=False))
    return 0


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--data", type=Path, default=Path("data/incheon"))
    ap.add_argument("--max", type=int, default=150, help="이번 실행에서 확인할 주소 수 상한")
    ap.add_argument("--timeout", type=float, default=15)
    ap.add_argument("--guides", action="store_true", help="공개 가이드의 출처 주소도 확인")
    ap.add_argument("--apply", action="store_true", help="dead·ended·moved를 dead_links.json에 추가(사람이 git diff로 확인)")
    a = ap.parse_args(argv)
    return run(a.data, a.max, a.timeout, a.guides, a.apply)


if __name__ == "__main__":
    sys.exit(main())
