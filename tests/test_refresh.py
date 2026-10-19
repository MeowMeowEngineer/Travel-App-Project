"""tools/refresh.py (주간 갱신)과 확인일 정직성. 하위 명령·네트워크는 모두 가짜로 바꾼다 — 실제 API를 부르지 않는다."""
import datetime as dt
import io
import json
import os
import subprocess

import pytest

from pipeline import tourapi
from pipeline.tourapi import TourAPI
from tools import refresh
from tools.tourapi_bulk import compute_nearby, fetched_on

KEY = "SECRETKEY1234567890"
DOCTOR_OK = json.dumps({"verdict": "정상 — KorService2/searchKeyword2 응답 OK", "attempts": []}, ensure_ascii=False, indent=2)
DOCTOR_FAIL = json.dumps({
    "verdict": f"실패 — 등록되지 않은 키 serviceKey={KEY}",
    "attempts": [{"service": "KorService2", "op": "searchKeyword2", "http_status": 200,
                  "result": {"code": "30", "message": f"SERVICE_KEY_IS_NOT_REGISTERED_ERROR ({KEY})"}}]},
    ensure_ascii=False, indent=2)
BULK_OK = json.dumps({"live_calls": 3, "cache_hits": 650, "details": {"done": 300, "errors": 0},
                      "new_places": {"added": 1, "errors": 0}, "events": {"added": 2, "updated": 5, "errors": 0}})


class Fake:
    """Stands in for refresh._python: records each command and answers by script name."""

    def __init__(self, **answers):
        self.calls = []
        self.answers = {"tourapi_doctor.py": (0, DOCTOR_OK, ""), "tourapi_bulk.py": (0, "목록\n" + BULK_OK + "\n", ""),
                        "round3_official.py": (0, "근대역사박물관 usetime\n금강미래체험관 usetime\n", ""),
                        "build_public.py": (0, json.dumps({"status": "built", "selected": 416, "qa_errors": 0}) + "\n", ""),
                        "quality_report.py": (0, "", ""), **answers}

    def __call__(self, args):
        self.calls.append(list(args))
        rc, out, err = self.answers[args[0].split("/")[-1]]
        return subprocess.CompletedProcess(args, rc, out, err)

    def names(self):
        return [c[0].split("/")[-1] for c in self.calls]

    def args(self, name):
        return next(c for c in self.calls if c[0].endswith(name))


@pytest.fixture(autouse=True)
def isolated(monkeypatch):
    monkeypatch.setattr(refresh, "load_dotenv", lambda path: None)   # never read the repository .env in tests
    monkeypatch.delenv("TOURAPI_KEY", raising=False)

    def refuse(*a, **k):
        raise AssertionError("tests must not start real commands")
    monkeypatch.setattr(refresh.subprocess, "run", refuse)


def test_dry_run_prints_plan_and_runs_nothing(monkeypatch, capsys):
    monkeypatch.setattr(refresh, "_python", lambda args: pytest.fail("dry run must not run anything"))
    assert refresh.main(["--dry-run"]) == 0
    out = capsys.readouterr().out
    assert ("python tools/tourapi_bulk.py --data data/gunsan --details --add-new --events --max-calls 400" in out
            and "--refresh" not in out)
    assert "tools/round3_official.py" in out and "build_public.py --data data/gunsan --out public" in out
    assert "--md reports/quality_latest.md" in out
    assert refresh.main(["--dry-run", "--fresh", "--max-calls", "50"]) == 0
    assert "--max-calls 50 --refresh" in capsys.readouterr().out


def test_cache_first_runs_every_step_in_order_without_git(monkeypatch, capsys):
    fake = Fake()
    monkeypatch.setattr(refresh, "_python", fake)
    assert refresh.main([]) == 0
    assert fake.names() == ["tourapi_doctor.py", "tourapi_bulk.py", "round3_official.py", "build_public.py",
                            "quality_report.py"]
    bulk = fake.args("tourapi_bulk.py")
    assert bulk[bulk.index("--max-calls") + 1] == "400" and {"--details", "--add-new", "--events"} <= set(bulk)
    assert "--refresh" not in bulk and "--offline" not in bulk
    assert fake.args("quality_report.py")[-2:] == ["--md", os.path.join("reports", "quality_latest.md")]
    flat = " ".join(" ".join(c) for c in fake.calls)
    assert "git" not in flat and "indexnow" not in flat and "vercel" not in flat
    out = capsys.readouterr().out
    assert "실호출 3 · 캐시 650" in out and "행사 추가 2·갱신 5" in out and "QA 오류 0" in out


def test_fresh_uses_the_client_refresh_mode(monkeypatch):
    fake = Fake()
    monkeypatch.setattr(refresh, "_python", fake)
    assert refresh.main(["--fresh"]) == 0
    assert "--refresh" in fake.args("tourapi_bulk.py")


def test_unreachable_tourapi_shows_provider_message_masked_and_rebuilds_from_cache(monkeypatch, capsys):
    monkeypatch.setenv("TOURAPI_KEY", KEY)
    fake = Fake(**{"tourapi_doctor.py": (1, DOCTOR_FAIL, "")})
    monkeypatch.setattr(refresh, "_python", fake)
    assert refresh.main(["--fresh"]) == 2
    out = capsys.readouterr().out
    assert "SERVICE_KEY_IS_NOT_REGISTERED_ERROR" in out and KEY not in out and "«KEY»" in out
    bulk = fake.args("tourapi_bulk.py")
    assert "--offline" in bulk and "--refresh" not in bulk
    assert fake.names()[2:] == ["round3_official.py", "build_public.py", "quality_report.py"]


def test_bulk_failure_keeps_going_with_current_data(monkeypatch, capsys):
    monkeypatch.setenv("TOURAPI_KEY", KEY)
    trace = ("Traceback (most recent call last):\n  File \"x.py\", line 1, in <module>\n"
             f"pipeline.tourapi.TourAPIError: areaBasedList2: 네트워크 오류 URLError: refused serviceKey={KEY}\n")
    fake = Fake(**{"tourapi_bulk.py": (1, "", trace)})
    monkeypatch.setattr(refresh, "_python", fake)
    assert refresh.main([]) == 2
    out = capsys.readouterr().out
    assert "areaBasedList2: 네트워크 오류" in out and KEY not in out and "File \"x.py\"" not in out
    assert fake.names()[-3:] == ["round3_official.py", "build_public.py", "quality_report.py"]


def test_preview_qa_errors_fail_but_quality_report_still_runs(monkeypatch):
    fake = Fake(**{"build_public.py": (1, json.dumps({"status": "built_with_qa_errors", "selected": 3, "qa_errors": 2}), "")})
    monkeypatch.setattr(refresh, "_python", fake)
    assert refresh.main(["--offline"]) == 1
    assert fake.names() == ["tourapi_bulk.py", "round3_official.py", "build_public.py", "quality_report.py"]


def test_official_step_failure_stops_the_build(monkeypatch):
    fake = Fake(**{"round3_official.py": (1, "", "KeyError: '근대역사박물관'\n")})
    monkeypatch.setattr(refresh, "_python", fake)
    assert refresh.main([]) == 1
    assert "build_public.py" not in fake.names()


# ---- 확인일: 캐시에서 다시 합쳐도 날짜가 오르지 않는다(aeo_geo_spec P0-4)
class FakeResp(io.BytesIO):
    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False


def test_client_records_the_fetch_date_and_cache_keeps_its_own(tmp_path, monkeypatch):
    body = json.dumps({"response": {"header": {"resultCode": "0000"}, "body": {"items": {"item": [{"contentid": "1"}]}}}})
    monkeypatch.setattr(tourapi.urllib.request, "urlopen", lambda req, timeout=20: FakeResp(body.encode()))
    live = TourAPI("k", cache_dir=tmp_path, min_interval=0)
    live.detail_common("1")
    assert live.fetched_dates == [dt.date.today().isoformat()]
    old = dt.datetime(2026, 1, 2, 12).timestamp()
    for f in tmp_path.iterdir():
        os.utime(f, (old, old))
    cached = TourAPI("k", cache_dir=tmp_path, min_interval=0)
    cached.detail_common("1")
    assert cached.live_calls == 0 and cached.fetched_dates == ["2026-01-02"]
    assert fetched_on(cached, 0, "2026-10-08") == "2026-01-02"
    assert fetched_on(cached, 1, "2026-10-08") == "2026-10-08"     # nothing answered since -> today


def test_nearby_date_moves_only_when_the_list_changes():
    places = [{"name": n, "slug": n, "kind": "attraction", "geo": {"lat": 35.98 + d, "lng": 126.71}}
              for n, d in (("a", 0), ("b", 0.001), ("c", 0.002))]
    compute_nearby(places, "2026-10-01")
    compute_nearby(places, "2026-10-08")
    assert {p["nearby_source"]["checked_at"] for p in places} == {"2026-10-01"}
    places[2]["geo"] = {"lat": 36.5, "lng": 126.71}                  # c moves out of range
    compute_nearby(places, "2026-10-09")
    assert places[0]["nearby_source"]["checked_at"] == "2026-10-09"
