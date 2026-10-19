#!/usr/bin/env bash
# HTTP access and crawl policy checks. Requires Python 3 (python3, or the interpreter in $PYTHON) and curl;
# never disables TLS checks.
set -euo pipefail
# Git Bash/MSYS2 on Windows would rewrite arguments such as "--path /places/" into Windows paths for python.exe.
export MSYS_NO_PATHCONV=1 MSYS2_ARG_CONV_EXCL='*'
exec "${PYTHON:-python3}" - "$@" <<'PY'
import argparse
import shutil
import subprocess
import sys
import tempfile
import xml.etree.ElementTree as ET
from html.parser import HTMLParser
from pathlib import Path
from urllib.parse import quote, urlsplit
from urllib.robotparser import RobotFileParser

BOTS = ("OAI-SearchBot", "ChatGPT-User", "PerplexityBot", "Googlebot", "Bingbot", "Yeti")


class MetaRobots(HTMLParser):
    def __init__(self):
        super().__init__()
        self.directives = []

    def handle_starttag(self, tag, attrs):
        values = {k.lower(): v for k, v in attrs}
        if tag.lower() == "meta":
            name = (values.get("name") or "").lower()
            if name == "robots" or name in {bot.lower() for bot in BOTS}:
                self.directives.append((name, values.get("content") or ""))


def prevents_indexing(body, headers, agent):
    parser = MetaRobots()
    parser.feed(body)
    contents = [content for name, content in parser.directives
                if name in ("robots", agent.lower())]
    for line in headers.splitlines():
        if not line.lower().startswith("x-robots-tag:"):
            continue
        content = line.split(":", 1)[1].strip()
        if ":" in content:
            scope, content = content.split(":", 1)
            if scope.strip().lower() != agent.lower():
                continue
        contents.append(content)
    return any({word.strip().lower() for word in text.split(",")} & {"noindex", "none"}
               for text in contents)


def main():
    ap = argparse.ArgumentParser(description="주요 URL의 HTTP 상태·robots·noindex 점검")
    ap.add_argument("url", help="예: site.json의 site_url")
    ap.add_argument("--mode", choices=("preview", "production"), default="production")
    ap.add_argument("--path", action="append", default=[], help="추가 HTML 경로(반복 가능)")
    ap.add_argument("--timeout", type=float, default=20, help="각 요청의 제한 시간(초)")
    args = ap.parse_args()
    parsed = urlsplit(args.url)
    if (parsed.scheme not in ("http", "https") or not parsed.hostname or parsed.username
            or parsed.password or parsed.query or parsed.fragment or parsed.path not in ("", "/")):
        ap.error("URL은 인증 정보·쿼리 없이 http(s)://호스트[:포트] 형태여야 합니다")
    if args.timeout <= 0:
        ap.error("--timeout은 양수여야 합니다")
    paths = list(dict.fromkeys(["/", "/places/", "/about/", *args.path]))
    if any(not path.startswith("/") or path.startswith("//") or "?" in path or "#" in path
           for path in paths):
        ap.error("--path는 /로 시작하는 같은 사이트의 HTML 경로여야 합니다")
    if not shutil.which("curl"):
        ap.error("curl을 설치해야 합니다")
    base = args.url.rstrip("/")
    expected_noindex = args.mode == "preview"
    errors = []
    print(f"모드: {args.mode} / URL: {base}")
    print("| User-Agent | 경로 | HTTP | 판정 |")
    print("|---|---|---:|---|")
    with tempfile.TemporaryDirectory(prefix="site-access-") as folder:
        body_file, header_file = Path(folder) / "body", Path(folder) / "headers"

        def fetch(agent, path):
            body_file.unlink(missing_ok=True)
            header_file.unlink(missing_ok=True)
            run = subprocess.run(
                ["curl", "--silent", "--show-error", "--location", "--max-redirs", "5",
                 "--proto", "=http,https", "--proto-redir", "=http,https",
                 "--connect-timeout", str(min(10, args.timeout)), "--max-time", str(args.timeout),
                 "--user-agent", agent, "--dump-header", str(header_file), "--output", str(body_file),
                 "--write-out", "%{http_code}", base + quote(path, safe="/%")],
                capture_output=True, text=True)
            status = run.stdout.strip() or "000"
            if run.returncode or status != "200":
                reason = f"HTTP {status}" if not run.returncode else f"curl 오류 {run.returncode} (HTTP {status})"
                errors.append(f"{agent} {path}: {reason}")
                print(f"| {agent} | {path} | {status} | 실패: {reason} |")
                return None
            body = body_file.read_text("utf-8", errors="replace")
            # curl -L saves every redirect header. Only the final response controls indexing.
            header_blocks = header_file.read_text("utf-8", errors="replace").split("\n\n")
            headers = next((block for block in reversed(header_blocks) if block.strip()), "")
            return status, body, headers

        for agent in BOTS:
            robots_result = fetch(agent, "/robots.txt")
            robots = None
            if robots_result:
                _, text, _ = robots_result
                robots = RobotFileParser()
                robots.parse(text.splitlines())
                has_groups = any(line.partition(":")[0].strip().lower() == "user-agent"
                                 for line in text.splitlines())
                allowed = robots.can_fetch(agent, base + "/")
                passed = has_groups and allowed != expected_noindex
                verdict = "허용" if allowed else "차단"
                print(f"| {agent} | /robots.txt | 200 | {'통과' if passed else '실패'}: {verdict} |")
                if not passed:
                    errors.append(f"{agent} robots.txt: {args.mode} 모드의 수집 정책과 다름")
                if agent == BOTS[0] and has_groups:
                    training = "허용" if robots.can_fetch("GPTBot", base + "/") else "차단"
                    print(f"GPTBot(학습용) robots 정책: {training} — 검색용 크롤러와 별도 판정")

            for path in paths + ["/sitemap.xml", "/llms.txt"]:
                result = fetch(agent, path)
                if not result:
                    continue
                _, body, headers = result
                reasons = []
                if path == "/sitemap.xml":
                    try:
                        tree = ET.fromstring(body)
                        namespace = "{http://www.sitemaps.org/schemas/sitemap/0.9}"
                        if tree.tag != namespace + "urlset" or not list(tree.iter(namespace + "loc")):
                            reasons.append("유효한 sitemap URL 목록 없음")
                    except ET.ParseError:
                        reasons.append("sitemap XML 파싱 실패")
                elif path == "/llms.txt":
                    if not body.lstrip().startswith("# "):
                        reasons.append("llms.txt 본문 없음 또는 HTML 응답")
                else:
                    blocked = prevents_indexing(body, headers, agent)
                    if blocked != expected_noindex:
                        reasons.append("미리보기 noindex 없음" if expected_noindex else "공개 페이지에 noindex")
                    if robots and robots.can_fetch(agent, base + path) == expected_noindex:
                        reasons.append("페이지 robots 정책 불일치")
                    if "<html" not in body.lower():
                        reasons.append("HTML 본문 없음")
                print(f"| {agent} | {path} | 200 | {'실패: ' + '; '.join(reasons) if reasons else '통과'} |")
                errors.extend(f"{agent} {path}: {reason}" for reason in reasons)
    print(f"접근 점검 오류: {len(errors)}건")
    if errors:
        print("\n".join(errors), file=sys.stderr)
    return 1 if errors else 0


raise SystemExit(main())
PY
