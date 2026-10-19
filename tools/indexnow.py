"""IndexNow 알림 — production 빌드의 sitemap URL을 IndexNow(빙·네이버·얀덱스 등 공유)에 알린다. 사람이 실행한다.

    python -m pipeline.build --data data/incheon --out dist-prod --mode production
    python -m pipeline.validate --data data/incheon --out dist-prod --mode production
    python tools/indexnow.py --out dist-prod                     # 미리 보기: 키 파일을 쓰고 보낼 내용을 출력
    (dist-prod를 배포하고 https://<도메인>/<키>.txt 가 열리는지 확인한 뒤)
    python tools/indexnow.py --out dist-prod --send              # 실제 전송, 공급자 응답을 그대로 출력
    python tools/indexnow.py --out dist-prod --since 2026-10-20  # sitemap lastmod가 이 날짜 이후인 URL만

준비(사람이 정한다 — CLAUDE.md 9절):
- data/incheon/site.json에 `site_url`(공개 도메인)과 `"indexnow_key"`를 넣는다. 키는 8~128자의 영문·숫자·'-'이다.
  예: `python -c "import secrets; print(secrets.token_hex(16))"`. 이 스크립트는 site.json을 고치지 않는다.
- 배포 설정의 noindex(예: vercel.json의 X-Robots-Tag)를 푸는 것도 사람이 한다. 남아 있으면 알림이 소용없다.

동작:
- --out이 production 빌드가 아니면 거부한다: robots.txt의 `User-agent: *`에 `Disallow: /`가 있거나,
  첫 화면(index.html)이 전체 noindex이거나, sitemap URL이 site_url 도메인이 아니면(빈 site_url로 빌드) 종료 코드 1.
- --out에 `<키>.txt`(내용: 키)를 쓴다. pipeline.build는 --out을 지우고 다시 만들므로 빌드할 때마다 다시 실행한다.
- --send가 없으면 보내지 않는다. --send는 https://api.indexnow.org/indexnow 에 JSON(host·key·keyLocation·urlList)을
  POST하고(1만 개씩), 응답 코드와 본문을 그대로 보여 준다. 200·202가 아니면 종료 코드 1.
"""
from __future__ import annotations

import argparse
import datetime as dt
import json
import re
import sys
import urllib.error
import urllib.request
import xml.etree.ElementTree as ET
from pathlib import Path
from urllib.parse import urlsplit

ROOT = Path(__file__).resolve().parents[1]
ENDPOINT = "https://api.indexnow.org/indexnow"
KEY_RE = re.compile(r"[A-Za-z0-9-]{8,128}")
BATCH = 10_000  # IndexNow: 한 요청에 URL 1만 개까지
MARKER = ".webforai-build"  # pipeline.build가 --out에 남기는 표시
SITEMAP_NS = "{http://www.sitemaps.org/schemas/sitemap/0.9}"
META_ROBOTS = re.compile(r"<meta\s+[^>]*name=[\"']robots[\"'][^>]*>", re.I)


class Refused(Exception):
    pass


def robots_blocks_all(text: str) -> bool:
    """True when the `User-agent: *` group has `Disallow: /` (the preview/sample robots.txt)."""
    agents, in_rules, blocked = [], False, False
    for raw in text.splitlines():
        line = raw.split("#", 1)[0].strip()
        if ":" not in line:
            continue
        field, value = (part.strip() for part in line.split(":", 1))
        field = field.lower()
        if field == "user-agent":
            if in_rules:
                agents, in_rules = [], False
            agents.append(value)
        elif field in ("allow", "disallow"):
            in_rules = True
            if field == "disallow" and value == "/" and "*" in agents:
                blocked = True
    return blocked


def check_production(out: Path) -> None:
    if not (out / MARKER).exists():
        raise Refused(f"{out}: pipeline.build 결과가 아닙니다({MARKER} 없음). production으로 먼저 빌드하세요.")
    robots = out / "robots.txt"
    if not robots.exists():
        raise Refused(f"{robots} 없음 — production 빌드가 아닙니다.")
    if robots_blocks_all(robots.read_text("utf-8")):
        raise Refused(f"{robots}에 'User-agent: * / Disallow: /'가 있습니다 — 미리보기·샘플 빌드입니다. --mode production으로 빌드하세요.")
    home = out / "index.html"
    if not home.exists():
        raise Refused(f"{home} 없음 — 빌드가 끝나지 않았습니다.")
    for tag in META_ROBOTS.findall(home.read_text("utf-8")):
        if "noindex" in tag.lower():
            raise Refused(f"{home}가 noindex입니다({tag}) — 전체 noindex 빌드에는 알리지 않습니다.")


def load_site(data: Path) -> tuple[str, str]:
    site = json.loads((data / "site.json").read_text("utf-8"))
    site_url, key = str(site.get("site_url") or "").strip().rstrip("/"), str(site.get("indexnow_key") or "").strip()
    if not site_url:
        raise Refused(f"{data / 'site.json'}의 site_url이 비어 있습니다(공개 도메인은 사람이 정한다).")
    parsed = urlsplit(site_url)
    if parsed.scheme not in ("http", "https") or not parsed.hostname:
        raise Refused(f"site_url이 http(s) 주소가 아닙니다: {site_url}")
    if not key:
        raise Refused(f"{data / 'site.json'}에 indexnow_key가 없습니다. 8~128자 영문·숫자·'-' 키를 사람이 넣어 주세요.")
    if not KEY_RE.fullmatch(key):
        raise Refused("indexnow_key 형식이 맞지 않습니다(8~128자, 영문·숫자·'-'만).")
    return site_url, key


def sitemap_urls(out: Path, site_url: str, since: str = "") -> list[str]:
    path = out / "sitemap.xml"
    if not path.exists():
        raise Refused(f"{path} 없음.")
    host = urlsplit(site_url).netloc.lower()
    urls, foreign = [], []
    for node in ET.parse(path).getroot().iter(f"{SITEMAP_NS}url"):
        loc = (node.findtext(f"{SITEMAP_NS}loc") or "").strip()
        lastmod = (node.findtext(f"{SITEMAP_NS}lastmod") or "").strip()
        if not loc:
            continue
        if urlsplit(loc).netloc.lower() != host:
            foreign.append(loc)
        elif not since or lastmod[:10] >= since:
            urls.append(loc)
    if foreign:
        raise Refused(f"sitemap에 site_url({site_url}) 도메인이 아닌 URL이 {len(foreign)}개 있습니다(예: {foreign[0]}). "
                      "site_url을 넣은 뒤 다시 빌드하세요.")
    return list(dict.fromkeys(urls))


def payloads(site_url: str, key: str, urls: list[str]) -> list[dict]:
    host = urlsplit(site_url).hostname
    location = f"{site_url}/{key}.txt"
    return [{"host": host, "key": key, "keyLocation": location, "urlList": urls[i:i + BATCH]}
            for i in range(0, len(urls), BATCH)]


def post_json(url: str, payload: dict, timeout: float = 30) -> tuple[int, str]:
    """POST; returns (status, body) as the provider sent them, including error statuses."""
    body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
    request = urllib.request.Request(url, data=body, method="POST",
                                     headers={"Content-Type": "application/json; charset=utf-8"})
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            return response.status, response.read().decode("utf-8", "replace")
    except urllib.error.HTTPError as exc:
        return exc.code, f"{exc.reason} {exc.read().decode('utf-8', 'replace')}".strip()


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--out", required=True, type=Path, help="production 빌드 폴더(예: dist-prod)")
    parser.add_argument("--data", default=ROOT / "data" / "incheon", type=Path)
    parser.add_argument("--since", default="", help="sitemap lastmod가 이 날짜(YYYY-MM-DD) 이후인 URL만")
    parser.add_argument("--endpoint", default=ENDPOINT)
    parser.add_argument("--send", action="store_true", help="실제로 보낸다(없으면 미리 보기)")
    args = parser.parse_args(argv)
    if args.since:
        try:
            dt.date.fromisoformat(args.since)
        except ValueError:
            parser.error("--since는 YYYY-MM-DD 형식이어야 합니다")
    try:
        check_production(args.out)
        site_url, key = load_site(args.data)
        urls = sitemap_urls(args.out, site_url, args.since)
    except (Refused, ET.ParseError, json.JSONDecodeError, FileNotFoundError) as exc:
        print(f"IndexNow 거부: {exc}", file=sys.stderr)
        return 1
    (args.out / f"{key}.txt").write_text(key, "utf-8")
    print(f"키 파일: {args.out / (key + '.txt')} → 배포 후 {site_url}/{key}.txt 에서 열려야 합니다.")
    if not urls:
        print("알릴 URL이 없습니다(sitemap이 비었거나 --since 이후 바뀐 URL 없음).")
        return 0
    batches = payloads(site_url, key, urls)
    if not args.send:
        for payload in batches:
            print(json.dumps(payload, ensure_ascii=False, indent=2))
        print(f"미리 보기: URL {len(urls)}개, 요청 {len(batches)}회. 보내려면 --send(키 파일을 먼저 배포).")
        return 0
    ok = True
    for n, payload in enumerate(batches, 1):
        try:
            status, body = post_json(args.endpoint, payload)
        except (urllib.error.URLError, OSError) as exc:
            print(f"요청 {n}/{len(batches)}: 연결 실패 — {exc}", file=sys.stderr)
            return 1
        print(f"요청 {n}/{len(batches)}: URL {len(payload['urlList'])}개 → {status} {body}".rstrip())
        ok = ok and status in (200, 202)
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
