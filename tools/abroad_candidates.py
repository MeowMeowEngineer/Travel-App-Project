"""해외에서 본 군산 — Threads·X에서 군산 관련 공개 게시물 후보를 찾아 사람이 고를 표로 만든다 (아무것도 공개하지 않는다).

    python tools/abroad_candidates.py                       # 키가 있는 서비스만 검색 → reports/abroad_candidates.csv
    python tools/abroad_candidates.py --max 30 --keywords "Gunsan,群山,군산 여행"

키(.env 또는 환경 변수, 커밋 금지 · 로그에서는 가린다):
- THREADS_ACCESS_TOKEN: Threads 앱의 사용자 토큰. 남의 게시물까지 찾으려면 threads_keyword_search 권한 승인이 필요하다
  (승인 전에는 토큰 주인의 게시물만 나온다). 하루 2,200회 한도.
- X_BEARER_TOKEN: X API 앱의 Bearer 토큰. 2026년 종량제라 돌려받은 게시물 1건마다 요금이 붙는다(약 $0.005) —
  --max로 실행당 건수를 제한한다(기본 20, 최근 7일 검색).
결과 표의 preview(본문 앞부분)는 고르는 사람이 보라고 넣은 것이고 사이트에는 싣지 않는다. 고른 게시물은 주소와 우리가
쓴 한 줄 소개를 data/<region>/abroad_queue.csv에 옮긴 뒤 tools/abroad_check.py로 확인해 넣는다.
"""
from __future__ import annotations

import argparse
import csv
import json
import os
import sys
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

if __package__ in (None, ""):
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from pipeline.enrich import load_dotenv

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_KEYWORDS = ["Gunsan", "群山", "군산 여행", "Seonyudo", "선유도"]


def get_json(url: str, headers: dict, secret: str) -> tuple[dict | None, str]:
    req = urllib.request.Request(url, headers={"User-Agent": "WebforAI-abroad/1.0", **headers})
    try:
        with urllib.request.urlopen(req, timeout=25) as r:
            return json.loads(r.read().decode("utf-8", "replace")), ""
    except urllib.error.HTTPError as e:
        return None, f"HTTP {e.code}: {e.read().decode('utf-8', 'replace')[:300]}".replace(secret, "***")
    except (urllib.error.URLError, TimeoutError, OSError, json.JSONDecodeError) as e:
        return None, f"{type(e).__name__}: {e}".replace(secret, "***")


def threads(keyword: str, token: str, limit: int) -> tuple[list[dict], str]:
    q = urllib.parse.urlencode({"q": keyword, "search_type": "RECENT", "limit": limit, "access_token": token,
                                "fields": "id,text,permalink,username,timestamp"})
    data, err = get_json(f"https://graph.threads.net/v1.0/keyword_search?{q}", {}, token)
    rows = [{"platform": "threads", "url": p.get("permalink", ""), "author": p.get("username", ""),
             "date": (p.get("timestamp") or "")[:10], "lang": "", "metrics": "", "preview": (p.get("text") or "")[:120]}
            for p in (data or {}).get("data") or []]
    return rows, err


def x_recent(keyword: str, token: str, limit: int) -> tuple[list[dict], str]:
    q = urllib.parse.urlencode({"query": f"{keyword} -is:retweet", "max_results": max(10, min(limit, 100)),
                                "tweet.fields": "created_at,lang,public_metrics", "expansions": "author_id",
                                "user.fields": "username"})
    data, err = get_json(f"https://api.x.com/2/tweets/search/recent?{q}", {"Authorization": f"Bearer {token}"}, token)
    users = {u["id"]: u.get("username", "") for u in ((data or {}).get("includes") or {}).get("users") or []}
    rows = []
    for t in (data or {}).get("data") or []:
        name = users.get(t.get("author_id"), "")
        m = t.get("public_metrics") or {}
        rows.append({"platform": "x", "url": f"https://x.com/{name or 'i'}/status/{t['id']}", "author": name,
                     "date": (t.get("created_at") or "")[:10], "lang": t.get("lang", ""),
                     "metrics": f"좋아요 {m.get('like_count', 0)} · 재게시 {m.get('retweet_count', 0)}",
                     "preview": (t.get("text") or "")[:120]})
    return rows, err


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--keywords", default=",".join(DEFAULT_KEYWORDS))
    ap.add_argument("--max", type=int, default=20, help="서비스·검색어마다 받을 최대 건수 (X는 건당 과금)")
    ap.add_argument("--out", default=str(ROOT / "reports" / "abroad_candidates.csv"))
    args = ap.parse_args(argv)
    load_dotenv(ROOT / ".env")
    keys = {"threads": os.environ.get("THREADS_ACCESS_TOKEN", ""), "x": os.environ.get("X_BEARER_TOKEN", "")}
    if not any(keys.values()):
        print("키가 없어 검색하지 않았습니다. .env에 THREADS_ACCESS_TOKEN(스레드, keyword_search 권한) 또는 "
              "X_BEARER_TOKEN(X, 종량제)을 넣으세요. 키 없이는 abroad_queue.csv에 직접 주소를 넣고 abroad_check.py를 쓰면 됩니다.")
        return 0
    rows, seen = [], set()
    for kw in [k.strip() for k in args.keywords.split(",") if k.strip()]:
        for name, fn in (("threads", threads), ("x", x_recent)):
            if not keys[name]:
                continue
            found, err = fn(kw, keys[name], args.max)
            print(f"[{name}] '{kw}': {len(found)}건" + (f" — {err}" if err else ""))
            for r in found:
                if r["url"] and r["url"] not in seen:
                    seen.add(r["url"])
                    rows.append({**r, "keyword": kw})
    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    with out.open("w", encoding="utf-8-sig", newline="") as f:
        w = csv.DictWriter(f, ["platform", "keyword", "url", "author", "date", "lang", "metrics", "preview"])
        w.writeheader()
        w.writerows(rows)
    print(f"후보 {len(rows)}건 → {out} (본문 미리보기는 고를 때만 보고 사이트에는 싣지 않습니다)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
