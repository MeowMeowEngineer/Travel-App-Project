"""해외에서 본 <지역> — 하이라이트 인용문 확인: 원문을 다시 받아 저장한 인용문이 글자 그대로 들어 있는지 본다 (아무것도 고치지 않는다).

    python tools/abroad_quotes.py                       # data/incheon/abroad_highlights.json의 quote 전부
    python tools/abroad_quotes.py --id <highlight id> --data data/incheon
    python tools/abroad_quotes.py --show <id>           # 그 항목 원문의 보이는 글을 출력(인용문을 고를 때)

운영자 결정 2026-10-14(CLAUDE.md 3절 10항): /abroad/ 하이라이트와 기사 카드에는 원문의 짧은 대목(연속한 1~2문장,
300자·45단어 이하)을 원문 언어 그대로 따옴표 대신 <blockquote>로 싣고, 매체·필자와 원문 링크를 함께 단다.
- 기사: 원문 페이지의 HTML을 그대로 받아(요약·재작성 도구를 쓰지 않는다) 보이는 글(script·style·head 등 제외)을
  뽑고, 공백을 한 칸으로 줄인 뒤 인용문이 그 안에 그대로 있는지 본다.
- SNS 게시물: 서비스의 공식 oEmbed가 돌려준 게시물 글(캡션)에서 같은 방법으로 본다. 캡션을 주지 않으면 인용하지 않는다.
- 받지 못한 원문(403·451·연결 실패)은 '확인 불가'로, 원문에 없는 인용문은 '불일치'로 보고하고 0이 아닌 값으로 끝난다.
"""
from __future__ import annotations

import argparse
import html as htmllib
import json
import re
import sys
import unicodedata
import urllib.error
import urllib.parse
import urllib.request
from html.parser import HTMLParser
from pathlib import Path
from typing import Callable

if __package__ in (None, ""):
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

ROOT = Path(__file__).resolve().parents[1]
UA = "Mozilla/5.0 (compatible; WebforAI-abroad-check/1.0)"
# some outlets answer the tool's own name with 403 and a browser's with the page; the second try says it is a browser
UA_BROWSER = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/128.0 Safari/537.36"
X_OEMBED = "https://publish.twitter.com/oembed"

SKIP = {"script", "style", "noscript", "template", "svg", "head", "iframe", "object", "canvas", "select", "textarea"}
BLOCK = {"address", "article", "aside", "blockquote", "br", "dd", "details", "div", "dl", "dt", "figcaption", "figure",
         "footer", "form", "h1", "h2", "h3", "h4", "h5", "h6", "header", "hr", "li", "main", "nav", "ol", "p", "pre",
         "section", "summary", "table", "td", "th", "tr", "ul", "button", "label", "option", "caption", "tbody",
         "thead", "tfoot"}
INVISIBLE = dict.fromkeys(map(ord, "­​‌‍⁠﻿"))   # soft hyphen and zero-width characters


def norm(text: str) -> str:
    """Whitespace (no-break spaces included) to one space, invisible characters out, NFC — the form a quote and the
    page text are compared in. Nothing else changes: quotation marks, dashes and letters stay as written."""
    return re.sub(r"\s+", " ", unicodedata.normalize("NFC", (text or "").translate(INVISIBLE))).strip()


class _Text(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.parts: list[str] = []
        self.skip = 0

    def handle_starttag(self, tag, attrs):
        if tag in SKIP:
            self.skip += 1
        elif tag in BLOCK:
            self.parts.append("\n")

    def handle_startendtag(self, tag, attrs):
        if tag in BLOCK:
            self.parts.append("\n")

    def handle_endtag(self, tag):
        if tag in SKIP:
            self.skip = max(0, self.skip - 1)
        elif tag in BLOCK:
            self.parts.append("\n")

    def handle_data(self, data):
        if not self.skip:
            self.parts.append(data)


def visible_text(page: str) -> str:
    """The text a reader sees: no script / style / head / svg / iframe, a break between blocks (so two paragraphs never
    run into one sentence), inline elements (links, emphasis) joined as written; then norm()."""
    p = _Text()
    p.feed(page)
    p.close()
    return norm("".join(p.parts))


def decode(raw: bytes, content_type: str = "") -> str:
    """The page's charset from the HTTP header or its <meta>, else UTF-8 (a broken byte becomes U+FFFD)."""
    m = re.search(r"charset=[\"']?([\w-]+)", content_type or "", re.I)
    if not m:
        m = re.search(rb"<meta[^>]+charset=[\"']?([\w-]+)", raw[:8192], re.I)
    enc = (m.group(1).decode() if isinstance(m.group(1), bytes) else m.group(1)) if m else "utf-8"
    try:
        return raw.decode(enc, "replace")
    except LookupError:
        return raw.decode("utf-8", "replace")


def fetch(url: str, timeout: int = 30) -> tuple[int, str]:
    """(status, decoded body); on a 403 once more with a browser's User-Agent."""
    status, body = 0, ""
    for ua in (UA, UA_BROWSER):
        req = urllib.request.Request(url, headers={"User-Agent": ua, "Accept": "text/html,application/xhtml+xml,*/*",
                                                   "Accept-Language": "en,ja;q=0.8,zh;q=0.7,ko;q=0.5"})
        try:
            with urllib.request.urlopen(req, timeout=timeout) as r:
                return r.status, decode(r.read(), r.headers.get("Content-Type", ""))
        except urllib.error.HTTPError as e:
            status, body = e.code, decode(e.read(), e.headers.get("Content-Type", ""))
            if e.code != 403:
                break
        except (urllib.error.URLError, TimeoutError, OSError) as e:
            return 0, f"{type(e).__name__}: {e}"
    return status, body


def post_text(oembed_html: str) -> str:
    """The post's own words in an X oEmbed answer: the <p> of its blockquote (links, mentions and tags as shown)."""
    m = re.search(r"<blockquote[^>]*>(.*?)</blockquote>", oembed_html or "", re.S)
    p = re.search(r"<p[^>]*>(.*?)</p>", m.group(1), re.S) if m else None
    return visible_text(p.group(1)) if p else ""


def source_text(item: dict, get: Callable[[str], tuple[int, str]] | None = None) -> tuple[str, str]:
    """(text, why-not): the visible text of an article, or the caption an X post's oEmbed returns. Instagram's and
    Threads' oEmbed give the embed markup only (no caption), so their posts are not quoted."""
    get = get or fetch
    if item.get("kind") == "post":
        if item.get("platform") != "x":
            return "", f"{item.get('platform')} oEmbed는 게시물 글을 주지 않음 — 인용하지 않는다"
        status, body = get(f"{X_OEMBED}?{urllib.parse.urlencode({'url': item['url'], 'omit_script': '1'})}")
        if status != 200:
            return "", f"x oEmbed HTTP {status}: {body[:200]}"
        try:
            text = post_text(json.loads(body).get("html") or "")
        except ValueError:
            return "", "x oEmbed: JSON이 아닌 응답"
        return (text, "") if text else ("", "x oEmbed에 게시물 글이 없음")
    status, body = get(item["url"])
    if status != 200:
        return "", f"HTTP {status}" + (f": {body[:120]}" if status == 0 else "")
    return visible_text(body), ""


def load(data_dir: Path) -> tuple[list[dict], dict]:
    hl = json.loads((data_dir / "abroad_highlights.json").read_text("utf-8")).get("items") or []
    items = json.loads((data_dir / "abroad.json").read_text("utf-8")).get("items") or []
    return hl, {a.get("id"): a for a in items}


def check(data_dir: Path, ids: list[str] | None = None,
          get: Callable[[str], tuple[int, str]] | None = None) -> list[tuple[str, str, str]]:
    """[(id, 'ok' | 'mismatch' | 'unreadable' | 'missing', detail)] for every highlight with a quote (or the ids): the
    original fetched again (once per address), its visible text, the stored quote looked for in it verbatim."""
    hl, by_id = load(data_dir)
    out, cache = [], {}
    for h in hl:
        q = norm(h.get("quote"))
        if not q or (ids and h.get("id") not in ids):
            continue
        a = by_id.get(h.get("id"))
        if not a or not a.get("url"):
            out.append((h.get("id"), "missing", "abroad.json에 없는 id 또는 원문 주소 없음"))
            continue
        if a["url"] not in cache:
            cache[a["url"]] = source_text(a, get)
        text, why = cache[a["url"]]
        if why:
            out.append((a["id"], "unreadable", why))
        elif q in text:
            out.append((a["id"], "ok", q[:60]))
        else:
            out.append((a["id"], "mismatch", f"원문에 없음: {q[:60]}…"))
    return out


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--data", default=str(ROOT / "data" / "incheon"))
    ap.add_argument("--id", action="append", default=[], help="이 id만 (여러 번 줄 수 있음)")
    ap.add_argument("--show", default="", help="이 id의 원문에서 뽑은 보이는 글을 출력하고 끝낸다")
    args = ap.parse_args(argv)
    data = Path(args.data)
    if args.show:
        _, by_id = load(data)
        if args.show not in by_id:
            print(f"abroad.json에 없는 id: {args.show}")
            return 2
        text, why = source_text(by_id[args.show])
        print(why or text)
        return 1 if why else 0
    rows = check(data, args.id or None)
    labels = {"ok": "일치", "mismatch": "불일치", "unreadable": "확인 불가", "missing": "항목 없음"}
    for hid, state, detail in rows:
        print(f"{labels[state]:<5} {hid} — {detail}")
    bad = sum(state != "ok" for _, state, _ in rows)
    print(f"인용문 {len(rows)}개 · 일치 {len(rows) - bad} · 그 밖 {bad}")
    return 1 if bad else 0


if __name__ == "__main__":
    raise SystemExit(main())
