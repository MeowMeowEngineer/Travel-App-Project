"""해외에서 본 <지역> — 사람이 고른 기사·SNS 게시물 주소를 확인해 data/<region>/abroad.json에 넣는다 (기본은 미리보기).

    python tools/abroad_check.py                      # data/incheon/abroad_queue.csv를 확인만 하고 결과를 출력
    python tools/abroad_check.py --apply              # 확인된 행을 abroad.json에 넣는다
    python tools/abroad_check.py --queue my.csv --data data/incheon --apply

큐 CSV 열: url, note, place_slugs(;로 구분), event_slugs(;), date(YYYY-MM-DD 또는 YYYY-MM), approve(Y면 공개),
          image(선택: 비우면 기사의 og:image, '-'면 사진 없음)
- note는 우리가 쓴 한 줄 소개다(원문을 옮기지 않는다). note가 없으면 넣지 않는다.
- 게시물(Instagram·Threads·X·Facebook)은 각 서비스의 oEmbed로 공개 게시물인지 확인한다. 메타(Instagram·Facebook)와
  Threads는 2026년부터 토큰 없이 부를 수 있고, META_OEMBED_TOKEN이 있으면 붙인다(.env 또는 환경 변수, 로그에는 가린다).
  oEmbed로 받은 값은 화면 표시(작성자 이름)에만 쓴다 — 메타 이용 조건.
- 기사는 주소가 열리는지(200)와 제목·매체 이름·대표 이미지(og:image)를 확인한다. 제목은 원문 그대로 인용한다.
  대표 이미지는 복사하지 않고 그 주소를 기사 옆 미리보기로만 쓴다. 그 지역을 찍은 사진이 아니면(다른 지역·필자 얼굴·
  매체 로고) image 열에 '-'를 적는다 — 미리보기 출력에 나온 주소를 열어 보고 고른다. 로고·아이콘 주소는 자동으로 뺀다.
- approve가 Y이고 확인을 통과한 행만 status=published, 나머지는 draft. 이미 있는 주소는 note·장소·승인만 갱신한다.
- 공급자 오류 메시지는 그대로 보여 준다(토큰 문자열만 가린다).
"""
from __future__ import annotations

import argparse
import csv
import datetime as dt
import hashlib
import html
import json
import os
import re
import sys
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

if __package__ in (None, ""):
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from pipeline.enrich import load_dotenv

ROOT = Path(__file__).resolve().parents[1]
UA = "Mozilla/5.0 (compatible; WebforAI-abroad-check/1.0)"
OEMBED = {
    "instagram": "https://graph.facebook.com/v23.0/instagram_oembed",
    "facebook": "https://graph.facebook.com/v23.0/oembed_post",
    "threads": "https://graph.threads.net/v1.0/oembed",
    "x": "https://publish.twitter.com/oembed",
}


def platform_of(url: str) -> str:
    """'post' services by host; anything else is an article."""
    host = urllib.parse.urlsplit(url).netloc.lower().removeprefix("www.").removeprefix("m.")
    if host in ("instagram.com",):
        return "instagram"
    if host in ("threads.net", "threads.com"):
        return "threads"
    if host in ("x.com", "twitter.com", "mobile.twitter.com"):
        return "x"
    if host in ("facebook.com", "fb.com", "fb.watch"):
        return "facebook"
    return ""


def mask(text: str, secret: str) -> str:
    return text.replace(secret, "***") if secret else text


def fetch(url: str, timeout: int = 20) -> tuple[int, str]:
    req = urllib.request.Request(url, headers={"User-Agent": UA})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return r.status, r.read().decode("utf-8", "replace")
    except urllib.error.HTTPError as e:
        return e.code, e.read().decode("utf-8", "replace")
    except (urllib.error.URLError, TimeoutError, OSError) as e:
        return 0, f"{type(e).__name__}: {e}"


def check_post(url: str, platform: str, token: str) -> dict:
    q = {"url": url, "omitscript": "true"}
    if platform == "x":
        q = {"url": url, "omit_script": "1"}
    elif token:
        q["access_token"] = token
    status, body = fetch(f"{OEMBED[platform]}?{urllib.parse.urlencode(q)}")
    if status != 200:
        return {"ok": False, "why": mask(f"{platform} oEmbed HTTP {status}: {body[:300]}", token)}
    try:
        data = json.loads(body)
    except json.JSONDecodeError:
        return {"ok": False, "why": f"{platform} oEmbed: JSON이 아닌 응답"}
    return {"ok": True, "author": data.get("author_name") or "", "platform": platform}


NOT_A_PHOTO = re.compile(r"favicon|apple-touch-icon|logo|/icons?/|\.svg(\?|$)", re.I)


def article_meta(body: str, url: str) -> dict:
    """Title, outlet, date and the og:image (https, not a logo/icon) of an article page."""
    def meta(pattern: str) -> str:
        m = re.search(pattern, body, re.I | re.S)
        return html.unescape(m.group(1)).strip() if m else ""
    title = meta(r'<meta property="og:title" content="([^"]+)"') or meta(r"<title>(.*?)</title>")
    image = (meta(r'<meta[^>]+property=["\']og:image["\'][^>]+content=["\']([^"\']+)')
             or meta(r'<meta[^>]+content=["\']([^"\']+)["\'][^>]+property=["\']og:image["\']'))
    image = urllib.parse.urljoin(url, image) if image else ""
    if image.startswith("http://"):
        image = "https://" + image[len("http://"):]
    if not urllib.parse.urlsplit(image).path.strip("/") or NOT_A_PHOTO.search(image):
        image = ""                                   # a bare host or a logo is not a picture of the place
    return {"title": title, "outlet": meta(r'<meta property="og:site_name" content="([^"]+)"'),
            "date": meta(r'<meta property="article:published_time" content="(\d{4}-\d{2}-\d{2})'), "image": image}


def check_article(url: str) -> dict:
    status, body = fetch(url)
    if status != 200:
        return {"ok": False, "why": f"기사 HTTP {status}"}
    return {"ok": True, **article_meta(body, url)}


def split(cell: str) -> list[str]:
    return [x.strip() for x in (cell or "").split(";") if x.strip()]


def item_from(row: dict, result: dict, today: str) -> dict:
    url = row["url"].strip()
    platform = result.get("platform", "")
    out = {"id": ("post-" if platform else "article-") + hashlib.sha1(url.encode()).hexdigest()[:10],
           "kind": "post" if platform else "article", "url": url, "note": (row.get("note") or "").strip(),
           "place_slugs": split(row.get("place_slugs")), "date": (row.get("date") or result.get("date") or "").strip(),
           "status": "published" if (row.get("approve") or "").strip().upper() == "Y" and result["ok"] else "draft",
           "checked_at": today}
    if split(row.get("event_slugs")):
        out["event_slugs"] = split(row.get("event_slugs"))
    if platform:
        out.update(platform=platform, author=result.get("author", ""))
    else:
        out.update(source_type=(row.get("source_type") or "press").strip(), outlet=(row.get("outlet") or result.get("outlet") or "").strip(),
                   title=(row.get("title") or result.get("title") or "").strip(), lang=(row.get("lang") or "en").strip())
        image = (row.get("image") or "").strip() or result.get("image", "")
        if image.startswith("https://"):             # '-' (or anything else) = no picture
            out["image"] = image
    return out


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--data", default=str(ROOT / "data" / "incheon"))
    ap.add_argument("--queue", default="")
    ap.add_argument("--apply", action="store_true", help="abroad.json에 쓴다 (없으면 미리보기)")
    args = ap.parse_args(argv)
    load_dotenv(ROOT / ".env")
    token = os.environ.get("META_OEMBED_TOKEN", "")
    data = Path(args.data)
    queue = Path(args.queue) if args.queue else data / "abroad_queue.csv"
    if not queue.exists():
        print(f"큐 파일이 없습니다: {queue}\n열: url,note,place_slugs,event_slugs,date,approve (approve=Y면 공개)")
        return 0
    store_path = data / "abroad.json"
    store = json.loads(store_path.read_text("utf-8")) if store_path.exists() else {"items": []}
    by_url = {it["url"]: it for it in store.get("items") or []}
    today = dt.date.today().isoformat()
    added = updated = failed = 0
    for row in csv.DictReader(queue.open(encoding="utf-8-sig")):
        url = (row.get("url") or "").strip()
        if not url:
            continue
        if not (row.get("note") or "").strip():
            print(f"건너뜀(note 없음): {url}")
            continue
        platform = platform_of(url)
        result = check_post(url, platform, token) if platform else check_article(url)
        print(("확인" if result["ok"] else "실패") + f" [{platform or 'article'}] {url}" + ("" if result["ok"] else f" — {result['why']}")
              + (f"\n    대표 이미지: {result['image']} (그 지역 사진이 아니면 image 열에 '-')" if result.get("image") else ""))
        if not result["ok"]:
            failed += 1
        item = item_from(row, result, today)
        if url in by_url:
            old = by_url[url]
            old.update({k: item[k] for k in ("note", "place_slugs", "status", "checked_at", "image") if k in item})
            if (row.get("image") or "").strip() == "-":
                old.pop("image", None)
            if item.get("event_slugs"):
                old["event_slugs"] = item["event_slugs"]
            updated += 1
        else:
            store.setdefault("items", []).append(item)
            by_url[url] = item
            added += 1
    print(f"추가 {added} · 갱신 {updated} · 확인 실패 {failed}" + ("" if args.apply else " (미리보기 — --apply로 저장)"))
    if args.apply:
        store_path.write_text(json.dumps(store, ensure_ascii=False, indent=2) + "\n", "utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
