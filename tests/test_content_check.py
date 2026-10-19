"""The checks on the sentences this site writes (pipeline/content_check.py, tools/content_check.py) on made-up data:
a summary that copies 15+ characters of the stored TourAPI overview, source commentary and unsourced modifiers, a
number no fact or source text holds, an FAQ question that is not 존댓말, an FAQ source that is not the place's, and
the same question on two places are caught; a sentence written from the facts passes. validate runs the copy check
on every built page (CLAUDE.md 3절 3항). Every name, text and value below is invented."""
import json
import shutil
from pathlib import Path

from pipeline import content_check as cc
from pipeline.build import build
from pipeline.validate import validate
from tools import content_check as tool

ROOT = Path(__file__).resolve().parent.parent
INCHEON = ROOT / "data" / "incheon"
TINY = Path(__file__).resolve().parent / "fixtures" / "incheon_tiny"
RECORDS = ("places.json", "events.json", "courses.json", "guides.json", "themes.json", "videos.json")
OVERVIEW = "[테스트] 가상 전망대는 1999년 바닷가 언덕 위에 세운 둥근 지붕의 전망 시설로, 맑은 날에는 서쪽 섬들이 보인다."


def _place(**over) -> dict:
    p = {"id": "test-1", "slug": "test-1", "name": "[테스트] 가상 전망대", "kind": "attraction", "category": "관광지",
         "facts": {"usetime": "09:00~18:00", "address": "인천광역시 연수구 테스트로 1"},
         "facts_source": {"provider": "한국관광공사 TourAPI", "contentid": "1", "checked_at": "2026-10-19"},
         "fact_sources": {"usetime": {"provider": "한국관광공사 TourAPI", "contentid": "1", "checked_at": "2026-10-19"}},
         "tourapi": {"contentid": "1", "overview": OVERVIEW}, "original": {}, "summary": ""}
    p.update(over)
    return p


def test_copy_commentary_numbers_and_faq_are_caught_and_a_fact_sentence_passes():
    copied = _place(summary="바닷가 언덕 위에 세운 둥근 지붕의 전망 시설이라 서쪽이 트여 있습니다.")
    assert any("overview와" in i and "연속 일치" in i for i in cc.place_issues(copied))
    commentary = cc.place_issues(_place(summary="원문은 이곳을 최고의 전망대로 소개합니다."))
    assert any("해설체" in i for i in commentary) and any("수식어" in i for i in commentary)
    assert any("숫자 ['2005']" in i for i in cc.place_issues(_place(summary="[테스트] 가상 전망대는 2005년에 문을 열었습니다.")))
    faq = [{"q": "주차할 수 있어요?", "a": "주차 정보는 확인이 필요합니다.", "source": "어느 블로그"}]
    found = cc.place_issues(_place(summary="[테스트] 가상 전망대는 09:00~18:00에 여는 전망 시설입니다.", faq=faq))
    assert any("존댓말" in i for i in found) and any("faq[0].source" in i for i in found)
    assert any("확인 필요" in i for i in found)
    ok = _place(summary="[테스트] 가상 전망대는 1999년에 지은 둥근 지붕 아래에서 서쪽 섬을 볼 수 있는 전망 시설입니다.",
                faq=[{"q": "[테스트] 가상 전망대는 몇 시에 여나요?", "a": "09:00~18:00에 엽니다.",
                      "source": "한국관광공사 TourAPI"}])
    assert cc.place_issues(ok) == []
    # a name or a fact value may be written as the source writes it
    assert cc.longest_copy("[테스트] 가상 전망대는 인천광역시 연수구 테스트로 1에 있습니다.",
                           "[테스트] 가상 전망대는 인천광역시 연수구 테스트로 1에 있는 전망 시설",
                           ["[테스트] 가상 전망대", "인천광역시 연수구 테스트로 1"]) == ""
    # the same question on two place pages
    q = {"q": "[테스트] 가상 전망대는 몇 시에 여나요?", "a": "09:00~18:00에 엽니다.", "source": "한국관광공사 TourAPI"}
    twice = cc.data_issues([_place(summary=ok["summary"], faq=[q]),
                            _place(id="test-2", slug="test-2", summary=ok["summary"], faq=[q])])
    assert any("같은 질문" in i for i in twice.get("test-2", []))


def test_the_tool_reads_a_data_folder_and_exits_1_on_a_finding(tmp_path, capsys):
    data = tmp_path / "data"
    data.mkdir()
    shutil.copy(INCHEON / "site.json", data / "site.json")
    (data / "places.json").write_text(json.dumps([_place(summary="1999년 바닷가 언덕 위에 세운 둥근 지붕의 전망 시설입니다.")],
                                                 ensure_ascii=False), "utf-8")
    assert tool.main(["--data", str(data)]) == 1
    assert "연속 일치" in capsys.readouterr().out
    (data / "places.json").write_text(json.dumps([_place()], ensure_ascii=False), "utf-8")   # nothing written yet
    assert tool.main(["--data", str(data)]) == 0
    assert "통과" in capsys.readouterr().out


def test_validate_flags_a_built_summary_that_copies_the_overview(tmp_path):
    data = tmp_path / "data"
    data.mkdir()
    for f in INCHEON.glob("*.json"):
        if f.name not in RECORDS:
            shutil.copy(f, data / f.name)
    for f in TINY.glob("*.json"):
        shutil.copy(f, data / f.name)
    places = json.loads((data / "places.json").read_text("utf-8"))
    places[0]["tourapi"] = {**(places[0].get("tourapi") or {}), "overview": OVERVIEW}
    places[0]["summary"] = "바닷가 언덕 위에 세운 둥근 지붕의 전망 시설이라 서쪽이 트여 있습니다."
    (data / "places.json").write_text(json.dumps(places, ensure_ascii=False), "utf-8")
    out = tmp_path / "out"
    build(data, out, "preview")
    errors, _, _ = validate(data, out, "preview")
    assert len(errors) == 1 and "원문 베끼기" in errors[0] and places[0]["id"] in errors[0], errors[:5]
    assert OVERVIEW not in (out / "places" / places[0]["slug"] / "index.html").read_text("utf-8")
