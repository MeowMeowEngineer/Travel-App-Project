"""Access checks use local HTTP fixtures; no real crawler or external service is contacted."""
import contextlib
import os
import subprocess
import sys
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

SCRIPT = Path(__file__).resolve().parents[1] / "tools" / "check_access.sh"


@contextlib.contextmanager
def server(mode="preview", status=200, header_noindex=False, robots=None):
    seen = []

    class Handler(BaseHTTPRequestHandler):
        def do_GET(self):
            seen.append((self.path, self.headers.get("User-Agent")))
            self.send_response(status)
            if header_noindex:
                self.send_header("X-Robots-Tag", "noindex, nofollow")
            self.end_headers()
            if self.path == "/robots.txt":
                text = robots or ("User-agent: *\nDisallow: /\n" if mode == "preview"
                                  else "User-agent: GPTBot\nDisallow: /\n\nUser-agent: *\nAllow: /\n")
            elif self.path == "/sitemap.xml":
                text = ('<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">'
                        '<url><loc>https://example.test/</loc></url></urlset>')
            elif self.path == "/llms.txt":
                text = "# 군산 여행\n\n독립 사이트\n"
            else:
                meta = '<meta content="noindex, nofollow" name="robots">' if mode == "preview" else ""
                text = f"<!doctype html><html><head>{meta}</head><body>군산 여행 미리보기</body></html>"
            self.wfile.write(text.encode("utf-8"))

        def log_message(self, *args):
            pass

    http = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    worker = threading.Thread(target=http.serve_forever, daemon=True)
    worker.start()
    try:
        yield f"http://127.0.0.1:{http.server_port}", seen
    finally:
        http.shutdown()
        worker.join()
        http.server_close()


def check(url, *args, limit="2"):
    # The interpreter running the tests (python3 may be missing or a store stub on Windows), its output in UTF-8.
    env = {**os.environ, "PYTHON": sys.executable, "PYTHONIOENCODING": "utf-8"}
    return subprocess.run(["bash", str(SCRIPT), url, "--timeout", limit, *args],
                          capture_output=True, encoding="utf-8", timeout=25, env=env)


def test_preview_access_includes_all_agents_and_added_page():
    with server() as (url, seen):
        run = check(url, "--mode", "preview", "--path", "/places/test-place/")
    assert run.returncode == 0, run.stdout + run.stderr
    assert "오류: 0건" in run.stdout
    assert {agent for _, agent in seen} == {
        "OAI-SearchBot", "ChatGPT-User", "PerplexityBot", "Googlebot", "Bingbot", "Yeti"}
    assert ("/places/test-place/", "OAI-SearchBot") in seen


def test_production_rejects_preview_noindex_and_blocked_robots():
    with server() as (url, _):
        run = check(url)
    assert run.returncode == 1
    assert "공개 페이지에 noindex" in run.stderr
    assert "수집 정책과 다름" in run.stderr


def test_production_allows_search_bots_with_separately_blocked_training():
    with server(mode="production") as (url, _):
        run = check(url)
    assert run.returncode == 0, run.stdout + run.stderr
    assert "GPTBot(학습용) robots 정책: 차단" in run.stdout


def test_production_rejects_header_noindex_even_without_meta():
    with server(mode="production", header_noindex=True) as (url, _):
        run = check(url)
    assert run.returncode == 1
    assert "공개 페이지에 noindex" in run.stderr


def test_http_401_is_a_failure_in_preview_too():
    with server(status=401) as (url, _):
        run = check(url, "--mode", "preview")
    assert run.returncode == 1
    assert "HTTP 401" in run.stderr


def test_preview_rejects_missing_noindex_with_correct_blocked_robots():
    with server(mode="production", robots="User-agent: *\nDisallow: /\n") as (url, _):
        run = check(url, "--mode", "preview")
    assert run.returncode == 1
    assert "미리보기 noindex 없음" in run.stderr


def test_rejects_foreign_path_and_credentials_before_requests():
    with server() as (url, seen):
        run = check(url, "--path", "//different.example/")
    assert run.returncode == 2 and not seen
    run = check("https://user:password@example.test")
    assert run.returncode == 2


def test_curl_connection_failure_is_not_reported_as_access():
    with server() as (url, _):
        pass
    # Windows answers a closed local port only after ~2 s of SYN retries; a short limit keeps all 36 requests in time.
    run = check(url, "--mode", "preview", limit="0.1")
    assert run.returncode == 1
    assert "curl 오류" in run.stderr
