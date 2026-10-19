"""tools/link_check.py (QA 2026-10-15 SRC-02c): classes from canned answers, no network."""
import json
import socket

import pytest

from tools import link_check as LK

MODOO = ("<html><body><h1>네이버 modoo!가 2025년 6월 26일 종료 되었습니다</h1>"
         "<p>그동안 modoo!를 이용해 주셔서 감사합니다.</p></body></html>")


def test_classes_from_canned_answers():
    assert LK.classify("https://guesthousiut.modoo.at", 200, "https://guesthousiut.modoo.at", MODOO, "")[0] == "ended"
    moved = LK.classify("http://www.sunu.co.kr/", 200, "https://www.sunu.co.kr/",
                        "<script>location.replace('https://dreamwas.com/x')</script>", "")
    assert moved[0] == "moved" and "dreamwas.com" in moved[1] and len(moved[1]) <= 80
    assert LK.classify("http://www.gunsandal.kr/", None, "http://www.gunsandal.kr/", "", "nxdomain")[0] == "dead"
    assert LK.classify("http://thegroove.jalib.site/", 404, "http://thegroove.jalib.site/", "Not Found.", "")[0] == "dead"
    assert LK.classify("https://h-eunpapalace.com", 403, "https://h-eunpapalace.com",
                       "<title>NinjaFirewall: 403 Forbidden</title>", "")[0] == "blocked"
    assert LK.classify("http://www.ritzplaza.co.kr", 200, "https://errdoc.gabia.io/403.html", "", "")[0] == "blocked"
    assert LK.classify("http://x.kr", None, "http://x.kr", "", "ConnectionResetError: reset")[0] == "blocked"
    assert LK.classify("http://ex.co.kr", 200, "https://www.ex.co.kr/main", "<p>객실 안내</p>", "") == ("ok", "HTTP 200")
    # a long page's own scripts are not a redirect
    long_page = "<p>객실</p>" * 2000 + "<script>location.href='https://ads.example.net/'</script>"
    assert LK.classify("http://ex.co.kr", 200, "http://ex.co.kr", long_page, "")[0] == "ok"
    assert LK.site_key("hotelrg2581.modoo.at") == "modoo.at" and LK.site_key("www.sunu.co.kr") == "sunu.co.kr"


def _data(tmp_path, n_places=3):
    data = tmp_path / "data"
    data.mkdir()
    places = [{"id": f"p{i}", "name": f"곳{i}", "status": "published", "facts": {"homepage": f"http://site{i}.kr"}}
              for i in range(n_places)]
    places.append({"id": "d", "name": "초안", "status": "draft", "facts": {"homepage": "http://draft.kr"}})
    places.append({"id": "m", "name": "모두", "status": "published", "facts": {"homepage": "https://x.modoo.at"}})
    (data / "places.json").write_text(json.dumps(places, ensure_ascii=False), "utf-8")
    dead = {"hosts": {"modoo.at": {"reason": "종료", "checked_at": "2026-10-15"}}, "urls": {}}
    (data / "dead_links.json").write_text(json.dumps(dead, ensure_ascii=False), "utf-8")
    return data


def test_apply_writes_only_dead_ended_moved_and_respects_max(tmp_path, monkeypatch):
    data = _data(tmp_path, 4)
    answers = {"http://site0.kr": {"status": None, "final": "", "body": "", "err": "nxdomain"},
               "http://site1.kr": {"status": 403, "final": "http://site1.kr", "body": "접근 제한", "err": ""},
               "http://site2.kr": {"status": 200, "final": "https://www.site2.kr/", "body": "<p>안내</p>", "err": ""},
               "http://site3.kr": {"status": 200, "final": "http://site3.kr", "body": MODOO, "err": ""}}
    seen = []
    monkeypatch.setattr(LK, "fetch", lambda url, timeout=15: seen.append(url) or answers[url])
    monkeypatch.setattr(LK.socket, "getaddrinfo", lambda *a, **k: [("ok",)])
    assert LK.run(data, max_n=3, apply=True, report_dir=tmp_path / "r", today="2026-11-01") == 0
    assert seen == ["http://site0.kr", "http://site1.kr", "http://site2.kr"]      # --max; modoo/draft skipped
    dead = json.loads((data / "dead_links.json").read_text("utf-8"))
    assert list(dead["urls"]) == ["http://site0.kr"]
    assert dead["urls"]["http://site0.kr"]["checked_at"] == "2026-11-01"
    report = (tmp_path / "r" / "link_check.md").read_text("utf-8")
    assert "| p1 | 곳1 | facts.homepage | http://site1.kr | blocked |" in report and "남은 1건" in report
    LK.run(data, max_n=10, apply=True, report_dir=tmp_path / "r", today="2026-11-02")
    dead = json.loads((data / "dead_links.json").read_text("utf-8"))
    assert sorted(dead["urls"]) == ["http://site0.kr", "http://site3.kr"]         # ended added; blocked/ok never


def test_no_dns_stops_without_writing(tmp_path, monkeypatch):
    data = _data(tmp_path)
    before = (data / "dead_links.json").read_text("utf-8")

    def no_dns(*a, **k):
        raise socket.gaierror(socket.EAI_NONAME, "Name or service not known")

    monkeypatch.setattr(LK.socket, "getaddrinfo", no_dns)
    monkeypatch.setattr(LK, "fetch", lambda *a, **k: pytest.fail("no fetch without DNS"))
    assert LK.run(data, apply=True, report_dir=tmp_path / "r") == 2
    assert (data / "dead_links.json").read_text("utf-8") == before and not (tmp_path / "r").exists()
