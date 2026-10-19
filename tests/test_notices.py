"""Dated facility notices (operator decision 2026-10-15): data/<region>/notices.json, pipeline/notices.py, the place
page line under the key facts, the assistant's docs and validate (no network). The engine's first site's board reader
(tools/museum_notices.py) and its real notices file stay there (tests/excluded_gunsan_tests.txt)."""
import datetime as dt
import json
import shutil
from pathlib import Path

import pytest

from pipeline import notices
from pipeline.build import State, build
from pipeline.validate import validate

ROOT = Path(__file__).resolve().parent.parent
SAMPLE = ROOT / "data" / "sample"
POST = "https://museum.gunsan.go.kr/new/board/index.do?act=view&bbs_id=1&id=9999"
CURRENT = {"id": "museum-2099-night", "place_ids": ["sample-0001"], "kind": "hours", "start": "2099-10-09",
           "end": "2099-10-11", "from": "18:00", "to": "22:00", "last_entry": "21:40",
           "provider": "군산근대역사박물관 홈페이지", "url": POST, "checked_at": "2026-10-15", "until": "2099-10-11"}
PAST = {"id": "museum-2000-closed", "place_ids": ["sample-0001"], "kind": "closed", "date": "2000-01-03",
        "provider": "군산근대역사박물관 홈페이지", "url": POST, "checked_at": "1999-12-30", "until": "2000-01-03"}


def test_problems_name_every_missing_field_and_unpublished_place():
    places = {"a": {"status": "published"}, "d": {"status": "draft"}}
    assert notices.problems([dict(CURRENT, place_ids=["a"])], places) == []
    bad = {"id": "x", "place_ids": ["a", "d", "zz"], "kind": "hours", "date": "2026-13-01", "from": "6pm"}
    found = notices.problems([bad, {"id": "x", "kind": "open"}], places)
    for word in ("provider 없음", "url 없음", "checked_at 없음", "until 없음", "날짜", "from 시각", "to 시각",
                 "공개하지 않는 장소 d", "없는 장소 zz", "id 중복", "place_ids 없음"):
        assert any(word in x for x in found), word
    assert notices.problems([dict(CURRENT, place_ids=["a"], kind="moved")], places)
    assert notices.problems([dict(CURRENT, place_ids=["a"], url="museum board")], places)


def test_active_drops_notices_after_until_and_formats_fixed_korean_words():
    items = [PAST, CURRENT, dict(CURRENT, id="no-url", url="")]
    assert [n["id"] for n in notices.active(items, "2026-10-15")] == ["museum-2099-night"]
    assert [n["id"] for n in notices.active([PAST], "2000-01-03")] == ["museum-2000-closed"]   # its last day
    assert notices.active([PAST], "2000-01-04") == []
    wd = "월화수목금토일"
    d = lambda iso: f"{dt.date.fromisoformat(iso).month}월 {dt.date.fromisoformat(iso).day}일({wd[dt.date.fromisoformat(iso).weekday()]})"
    assert notices.ko_text(PAST) == f"2000년 {d('2000-01-03')} 휴관"
    assert notices.ko_text(CURRENT) == f"2099년 {d('2099-10-09')}–{d('2099-10-11')} 18:00–22:00 운영(입장 마감 21:40)"
    assert notices.ko_text(dict(PAST, kind="open")).endswith(" 개관")


@pytest.fixture()
def built(tmp_path):
    data = tmp_path / "data"
    shutil.copytree(SAMPLE, data)
    (data / "notices.json").write_text(json.dumps([PAST, CURRENT], ensure_ascii=False), "utf-8")
    out = tmp_path / "sample"
    build(data, out, "sample")
    return data, out


def test_current_notice_is_shown_with_its_post_and_in_the_assistant_docs(built):
    data, out = built
    S = State(data, "sample")
    e = S.ent_by_slug["gyeongam-railroad-village"]
    page = (out / "places" / e["slug"] / "index.html").read_text("utf-8")
    hero = page.split('class="kf-notes"', 1)[1].split("</div>", 1)[0]
    assert 'data-notice="museum-2099-night"' in hero and notices.ko_text(CURRENT) in hero
    assert f'href="{POST.replace("&", "&amp;")}"' in hero and "군산근대역사박물관 홈페이지" in hero
    assert "museum-2000-closed" not in page
    docs = (out / "chat" / "docs.json").read_text("utf-8")
    assert notices.ko_text(CURRENT) in docs and "2099-10-11까지 표시" in docs and notices.ko_text(PAST) not in docs
    assert not [x for x in validate(data, out, "sample")[0] if "공지" in x or "notices.json" in x]


def test_validate_catches_an_expired_notice_on_a_page_a_missing_one_and_bad_data(built):
    data, out = built
    f = out / "places" / "gyeongam-railroad-village" / "index.html"
    html = f.read_text("utf-8")
    f.write_text(html.replace('data-notice="museum-2099-night"', 'data-notice="museum-2000-closed"'), "utf-8")
    errors = [x for x in validate(data, out, "sample")[0] if "공지" in x]
    assert any("끝난" in x and "museum-2000-closed" in x for x in errors)
    assert any("현재 공지가 화면에 없음: museum-2099-night" in x for x in errors)
    (data / "notices.json").write_text(json.dumps([dict(PAST, provider="", place_ids=["sample-0999"])],
                                                  ensure_ascii=False), "utf-8")
    errors = [x for x in validate(data, out, "sample")[0] if x.startswith("[notices.json]")]
    assert any("provider 없음" in x for x in errors) and any("공개하지 않는 장소 sample-0999" in x for x in errors)

