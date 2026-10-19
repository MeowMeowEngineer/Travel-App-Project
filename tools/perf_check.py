"""모바일 체감 속도 점검 — 느린 4G·저사양 폰을 흉내 내 LCP·CLS·전송량을 잰다.

    python tools/perf_check.py --out public                      # 기본 페이지 3개, 모션 켬/끔 비교
    python tools/perf_check.py --out dist-preview --pages / /places/<장소-slug>/ --json
    python tools/perf_check.py --out public --block-external      # 외부 사진·지도 타일 없이(재현성 우선)
    python tools/perf_check.py --out dist-preview --pages "/places/?type=박물관·전시" "/map/#r-<권역>"   # 필터 주소·앵커도

- 필요: pip install playwright && python -m playwright install chromium
- 로컬 정적 서버로 --out 폴더를 띄우고 측정한다. 서버는 Vercel처럼 글(HTML·CSS·JS·JSON·SVG)을 gzip으로 보낸다
  (Vercel은 br도 쓴다 — 실제 전송량은 이보다 조금 작다). 기준선과 전/후 비교용이며, 공개 후에는 PageSpeed Insights
  실측으로 다시 확인한다.
- 목표(이 사이트 기준): 모바일 LCP ≤ 2.5초(느린 4G·CPU 4배 감속), CLS ≤ 0.1, 첫 화면 제목이 스크립트 때문에 숨지 않을 것.
"""
from __future__ import annotations

import argparse
import functools
import gzip
import http.server
import json
import os
import socket
import sys
import threading
import time
import urllib.parse
from pathlib import Path

DEFAULT_PAGES = ["/", "/places/"]   # + the first place page the build has (first_place_page)


def first_place_page(out: Path) -> list[str]:
    """The first place page in the built folder (by name), so a place's first screen is measured too."""
    first = next(iter(sorted((Path(out) / "places").glob("*/index.html"))), None)
    return [f"/places/{first.parent.name}/"] if first else []
PROBE = """() => new Promise(res => {
  let lcp = 0, el = '', cls = 0;
  new PerformanceObserver(l => { for (const e of l.getEntries()) { lcp = e.startTime;
      el = e.element ? (e.element.tagName + (e.element.className ? '.' + String(e.element.className).split(' ')[0] : '')) : (e.url || '').slice(-40); } })
    .observe({type: 'largest-contentful-paint', buffered: true});
  new PerformanceObserver(l => { for (const e of l.getEntries()) if (!e.hadRecentInput) cls += e.value; })
    .observe({type: 'layout-shift', buffered: true});
  setTimeout(() => {
    const fcp = (performance.getEntriesByName('first-contentful-paint')[0] || {}).startTime || 0;
    const res2 = performance.getEntriesByType('resource');
    const by = t => res2.filter(r => r.initiatorType === t || (t === 'font' && /\\.woff2?$/.test(r.name))).reduce((a, r) => a + (r.decodedBodySize || 0), 0);
    // the home's first news slide picture (its LCP on a real visit): really loaded, from where, when it arrived
    const fs = document.querySelector('[data-hcar-item] img'), src = fs ? fs.currentSrc || fs.src : '';
    const fe = src && res2.find(r => r.name === src);
    res({lcp_ms: Math.round(lcp), lcp_element: el, cls: +cls.toFixed(3), fcp_ms: Math.round(fcp),
         font_kb: Math.round(by('font') / 1024), script_kb: Math.round(by('script') / 1024), requests: res2.length,
         slide: src ? (src.startsWith(location.origin) ? 'local ' : 'outside ') + src.split('/').pop() : '',
         slide_ms: fe ? Math.round(fe.responseEnd) : 0, slide_ok: !!(fs && fs.complete && fs.naturalWidth)});
  }, 9000); })"""


# what Vercel sends compressed (QA 2026-10-19 QA-29: the plain http.server sent everything raw, so FCP = LCP and the
# home measured 2.9 s, /places/ 3.7 s — a slower network than the site's own). Fonts, pictures and video are sent
# as they are, as Vercel does.
GZIP_TYPES = (".html", ".css", ".js", ".mjs", ".json", ".svg", ".txt", ".xml", ".webmanifest")


class GzipHandler(http.server.SimpleHTTPRequestHandler):
    """A static file server that gzips text files for a client that accepts it (Content-Encoding: gzip), each file
    compressed once."""
    cache: dict = {}

    def log_message(self, *args):   # quiet
        pass

    def do_GET(self):
        path = self.translate_path(self.path)
        if os.path.isdir(path):
            if not self.path.split("?", 1)[0].endswith("/"):
                return super().do_GET()   # the redirect to the slash
            path = os.path.join(path, "index.html")
        if not (os.path.isfile(path) and path.endswith(GZIP_TYPES) and "gzip" in self.headers.get("Accept-Encoding", "")):
            return super().do_GET()
        key = (path, os.path.getmtime(path))
        body = self.cache.get(key)
        if body is None:
            with open(path, "rb") as f:
                body = self.cache[key] = gzip.compress(f.read(), 6)
        self.send_response(200)
        self.send_header("Content-Type", self.guess_type(path))
        self.send_header("Content-Encoding", "gzip")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Vary", "Accept-Encoding")
        self.end_headers()
        self.wfile.write(body)


class Server:
    """The folder served on 127.0.0.1:port in a thread (terminate() stops it)."""

    def __init__(self, folder: Path, port: int):
        handler = functools.partial(GzipHandler, directory=str(folder))
        self.httpd = http.server.ThreadingHTTPServer(("127.0.0.1", port), handler)
        self.thread = threading.Thread(target=self.httpd.serve_forever, daemon=True)
        self.thread.start()

    def terminate(self):
        self.httpd.shutdown()
        self.httpd.server_close()


def serve(folder: Path, port: int) -> Server:
    srv = Server(folder, port)
    for _ in range(100):
        try:
            socket.create_connection(("127.0.0.1", port), 0.2).close()
            return srv
        except OSError:
            time.sleep(0.1)
    srv.terminate()
    raise RuntimeError("로컬 서버를 띄우지 못했습니다")


def measure(out: Path, pages: list[str], block_external: bool, port: int = 8790) -> list[dict]:
    from playwright.sync_api import sync_playwright  # imported here so --help works without playwright
    srv = serve(out, port)
    rows = []
    try:
        with sync_playwright() as p:
            browser = p.chromium.launch()
            for path in pages:
                for motion in ("no-preference", "reduce"):
                    ctx = browser.new_context(viewport={"width": 390, "height": 844}, is_mobile=True, has_touch=True,
                                              reduced_motion=motion)
                    if block_external:
                        ctx.route("http*://**/*", lambda r: r.continue_() if r.request.url.startswith(f"http://127.0.0.1:{port}") else r.abort())
                    page = ctx.new_page()
                    cdp = ctx.new_cdp_session(page)
                    cdp.send("Network.enable")
                    cdp.send("Network.emulateNetworkConditions", {"offline": False, "latency": 150,
                                                                  "downloadThroughput": 1.6 * 1024 * 1024 / 8,
                                                                  "uploadThroughput": 750 * 1024 / 8})
                    cdp.send("Emulation.setCPUThrottlingRate", {"rate": 4})
                    page.goto(f"http://127.0.0.1:{port}" + urllib.parse.quote(path, safe="/?=&#"), wait_until="domcontentloaded", timeout=90000)
                    r = page.evaluate(PROBE)
                    r.update(page=path, motion="on" if motion == "no-preference" else "off(reduced)")
                    rows.append(r)
                    ctx.close()
            browser.close()
    finally:
        srv.terminate()
    return rows


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--out", type=Path, default=Path("public"))
    ap.add_argument("--pages", nargs="*", default=None, help="기본: / · /places/ · 첫 장소 페이지")
    ap.add_argument("--block-external", action="store_true")
    ap.add_argument("--json", action="store_true")
    a = ap.parse_args(argv)
    rows = measure(a.out, a.pages or DEFAULT_PAGES + first_place_page(a.out), a.block_external)
    if a.json:
        print(json.dumps(rows, ensure_ascii=False, indent=1))
    else:
        print("| 페이지 | 모션 | LCP(ms) | LCP 요소 | FCP(ms) | CLS | 글꼴 KB | 스크립트 KB | 요청 수 |")
        print("|---|---|---|---|---|---|---|---|---|")
        for r in rows:
            lcp = r["lcp_ms"] or "> 9000(측정 창 안에 LCP 없음)"
            print(f"| {r['page']} | {r['motion']} | {lcp} | {r['lcp_element']} | {r['fcp_ms']} | {r['cls']} | "
                  f"{r['font_kb']} | {r['script_kb']} | {r['requests']} |")
            if r.get("slide"):   # the home: its first slide picture really loaded (not blocked), and when
                print(f"|  | 첫 소식 그림 | {r['slide_ms'] or '-'} | {r['slide']} | {'불러옴' if r['slide_ok'] else '못 불러옴'} | | | | |")
    # lcp_ms 0 = the largest element (usually a big photo) had not painted within the 9 s window: a failure, not a pass.
    # The home's first slide picture counts too: it must load, and by 2.5 s (a blocked outside photo hid a 5.8 s LCP).
    bad = [r for r in rows if r["motion"] == "on" and (r["lcp_ms"] > 2500 or not r["lcp_ms"]
                                                       or (r.get("slide") and not (r["slide_ok"] and 0 < r["slide_ms"] <= 2500)))]
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())
