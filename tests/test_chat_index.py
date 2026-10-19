"""Site assistant knowledge (pipeline/chat_index.py), exported from the real data the way the public build does:
every published place, guide, course, event series, /abroad/ article and video is there; place lines carry the
first-screen key facts with both values where sources differ; every fact names its source, the exact address the value
came from and the date this site checked it, and the link check allows that address; dates are named for what they
are (출처 확인, 페이지 검수, 운영자 공개 승인, 원문 수집, 시행); a timetable chain is spelled out stop by stop with its
direction and kind of time; the about page says what the chat sends where; no TourAPI overview or 군산시 original text;
the bytes do not depend on the build date; the catalog stays under its token budget."""
import datetime as dt
import json
import re
from pathlib import Path
from types import SimpleNamespace

import pytest

from pipeline import build as B
from pipeline import chat_index, en_site, present
from pipeline.build import State, build
from pipeline.schema import FACT_ORDER, FIT_ORDER

ROOT = Path(__file__).resolve().parent.parent
GUNSAN = ROOT / "data" / "gunsan"
SAMPLE = ROOT / "data" / "sample"
LETTERS = ("P ", "G ", "C ", "E ", "A ", "V ", "T ", "S ")


def _state(data: Path, mode: str = "production") -> State:
    S = State(data, mode)
    S.en = en_site.load(S, data)
    return S


@pytest.fixture(scope="module")
def real(tmp_path_factory):
    S = _state(GUNSAN)
    out = tmp_path_factory.mktemp("chat")
    stats = chat_index.export(S, out)
    d = out / "chat"
    return {"S": S, "stats": stats, "dir": d, "catalog": (d / "catalog.txt").read_text("utf-8"),
            "docs": json.loads((d / "docs.json").read_text("utf-8")), "index": json.loads((d / "index.json").read_text("utf-8"))}


def _lines(catalog: str) -> dict[str, str]:
    """catalog line by its path / id (the second field)."""
    return {line.split(" | ")[0][2:]: line for line in catalog.splitlines() if line[:2] in LETTERS}


def test_chain_lines_spell_out_stop_direction_and_kind_of_time():
    text = ("99번은 A역을 떠나 섬을 돌아옵니다. 시간표의 기준 시각은 A역 06:10, 09:10~20:10 매시 10분(13회) → B(환) 06:35~20:35 "
            "→ C섬 07:15~21:15 → D섬 07:20~21:20 → B(환) 07:45~21:45입니다. 평일과 같습니다.")
    lines = chat_index._chain_lines(text)
    assert lines[1] == "- A역 — 출발 시각(첫 정류장), 가는 길(D섬 쪽): 06:10, 09:10~20:10 매시 10분(13회) (첫 06:10, 마지막 20:10)"
    assert lines[3] == ("- C섬 — 버스가 그 정류장에 오는 시각(거기서 타고 내림), 가는 길(D섬 쪽): 07:15~21:15 "
                        "(첫 07:15, 마지막 21:15)")
    assert lines[4] == ("- D섬 — 버스가 그 정류장에 오는 시각(거기서 타고 내림), 가는 길의 끝(D섬, 여기서 돌아 나옴): 07:20~21:20 "
                        "(첫 07:20, 마지막 21:20)")
    assert lines[5] == ("- B(환) — 버스가 그 정류장에 오는 시각(거기서 타고 내림), 돌아오는 길(A역 쪽): 07:45~21:45 "
                        "(첫 07:45, 마지막 21:45)")
    # a stop time is the time to get on there — not a departure toward it
    assert ("정류장에 붙은 시각은 버스가 그 정류장에 오는 시각이라 그 정류장에서 타는 시각이고, A역에서 그 시각에 출발하는 차라는 "
            "뜻이 아니다.") in lines[6]
    assert "C섬 21:15" not in lines[6]   # live check 2026-10-14: a named example made the model deny the way back
    assert lines[6].endswith("D섬 쪽으로 가는 마지막 차는 A역 20:10 출발이다.")
    # the way back (the review: '선유도에서 군산대 쪽으로 가는 막차' answered 'not on the site'): a stop the way back passes
    # again has its own times; a stop it does not list is served by the same bus, which goes on to the end and returns
    assert lines[7] == "돌아오는 길: D섬까지 간 차가 돌아 나와 B(환) 07:45~21:45 순으로 지난다. 이 표에는 A역에 닿는 시각이 없다."
    assert lines[8] == "B(환)에서 A역 쪽으로 가는 차: 돌아오는 길의 B(환) 07:45~21:45 (마지막 21:45)."
    assert lines[9] == ("C섬에서 A역 쪽으로 가는 막차: C섬에 21:15에 오는 차를 타고 그대로 있으면 된다(D섬 21:20 → B(환) 21:45 → "
                        "A역 쪽, A역 도착 시각은 이 표에 없음). C섬에 오는 차(07:15~21:15)는 모두 D섬까지 갔다가 돌아 나와 B(환) 순으로 "
                        "지난다. 돌아오는 차가 C섬 정류장을 다시 지나는 시각은 이 표에 없다.")
    assert lines[10] == "D섬에서 A역 쪽으로 가는 차: D섬에 오는 차(07:20~21:20)가 그대로 돌아 나간다(마지막 21:20)."
    assert len(lines) == 11
    # a route that does not come back: no way-back lines
    one_way = chat_index._chain_lines("기준 시각은 A역 06:10 → B역 06:35 → C역 07:00입니다.")
    assert one_way[1].endswith("가는 길: 06:10 (첫 06:10, 마지막 06:10)") and not any("돌아" in x for x in one_way)
    # no chain, a chain without times, or two stops only: nothing is added
    assert chat_index._chain_lines("기준 시각은 없습니다.") == []
    assert chat_index._chain_lines("기준 시각은 A역 → B역입니다.") == []
    assert chat_index._chain_lines("기준 시각은 A역 06:10 → B역 06:35입니다.") == []


def _ticket_kb(monkeypatch, entities, guides, fees):
    from pipeline import build as B
    monkeypatch.setattr(B, "fact_row", lambda e, k: {"value": fees[e["id"]], "alternatives": []}
                        if k == "usefee" and e["id"] in fees else None)
    k = chat_index.Knowledge.__new__(chat_index.Knowledge)
    k.S = SimpleNamespace(site_url="https://x.example", entities=entities, guides=guides)
    k._names, k._sentences, k._tickets = None, None, {}
    return k


def test_tickets_align_the_lists_the_guides_give(monkeypatch):
    """A ticket's places come from the guides' sentences about it, one per place however each sentence names it
    ('근대미술관' = '군산근대미술관', '위봉함' = '진포해양공원 위봉함'); a sentence whose list adds a place that is not
    the ticket's ('금강권 통합권은 … 채만식문학관을 더한') is never used; a place with no page says so."""
    ents = [{"id": "m", "name": "근대역사박물관", "_path": "/places/m/"},
            {"id": "b", "name": "구 일본 제18은행 군산지점", "alternate_names": ["군산근대미술관"], "_path": "/places/b/"},
            {"id": "c", "name": "군산근대건축관", "_path": "/places/c/"},
            {"id": "j", "name": "진포해양공원", "_path": "/places/j/"},
            {"id": "x", "name": "채만식문학관", "_path": "/places/x/"}]
    guides = [
        {"id": "g1", "_path": "/guides/g1/", "body": [{"text": "박물관 통합권은 근대역사박물관·군산근대미술관·군산근대건축관·위봉함 "
         "네 곳을 묶은 표로 성인 3,000원입니다. 금강권 통합권은 박물관 통합권 네 곳에 채만식문학관·금강미래체험관을 더한 표로 "
         "성인 5,000원입니다."}]},
        {"id": "g2", "_path": "/guides/g2/", "body": [{"text": "박물관 통합권은 근대역사박물관, 근대미술관, 근대건축관, 진포해양공원 "
         "위봉함을 묶은 표로 성인 3,000원입니다. 박물관 통합권은 박물관·미술관·건축관·위봉함·채만식문학관을 묶은 표입니다."}]}]
    fees = {"m": "[박물관 통합권] - 성인 3,000원 [개별권] - 성인 2,000원",
            "b": "[통합권]인근 전시장(박물관+미술관+건축관+위봉함) - 성인 3,000원", "c": "성인 500원"}
    k = _ticket_kb(monkeypatch, ents, guides, fees)
    want = [("근대역사박물관", "m", "name"), ("군산근대미술관", "b", "other"), ("군산근대건축관", "c", "name"),
            ("진포해양공원 위봉함", "j", "name")]
    for pid, label, n_said in (("m", "박물관 통합권", 2), ("b", "통합권", 1)):
        [t] = k.tickets(next(e for e in ents if e["id"] == pid))
        assert t["label"] == label and len(t["said"]) == n_said, pid
        assert [(p["written"], p["e"]["id"], p["by"]) for p in t["places"]] == want, pid
        assert not any("채만식" in s for _, s in t["said"]), pid
    assert k.tickets(ents[2]) == []   # no combined ticket in the fee table
    assert k.ticket_lines(ents[0])[1] == ("  '박물관 통합권' 시설 4곳(가이드가 쓴 이름 — 장소 페이지): 근대역사박물관 /places/m/ "
                                          "(이 페이지); 군산근대미술관 = 구 일본 제18은행 군산지점 /places/b/; 군산근대건축관 "
                                          "/places/c/; 진포해양공원 위봉함 /places/j/")
    # without a page for 진포해양공원 the 위봉함 is still one of the four, said to have no page
    k2 = _ticket_kb(monkeypatch, [e for e in ents if e["id"] != "j"], guides, fees)
    assert k2.ticket_lines(ents[0])[1].endswith("; 군산근대건축관 /places/c/; 위봉함 (장소 페이지 없음)")


def test_places_in_reads_longer_names_first():
    S = SimpleNamespace(site_url="https://x.example", entities=[
        {"id": "a", "name": "근대역사박물관", "alternate_names": ["군산근대역사박물관"], "_path": "/places/a/"},
        {"id": "b", "name": "구 일본 제18은행 군산지점", "alternate_names": ["군산근대미술관"], "_path": "/places/b/"},
        {"id": "c", "name": "연도", "_path": "/places/c/"}], guides=[])
    k = chat_index.Knowledge.__new__(chat_index.Knowledge)
    k.S, k._names, k._sentences, k._tickets = S, None, None, {}
    found = k.places_in("군산 근대미술관과 군산근대역사박물관, 연도별 요금")
    assert [(w, e["id"]) for w, e in found] == [("군산근대미술관", "b"), ("군산근대역사박물관", "a")]
    assert k.places_in("군산근대미술관", skip={"b"}) == []


def test_effective_dates_come_from_the_source_title():
    srcs = [{"name": "군산시내버스시간표(2024.10.21 시행) — 군산시", "url": "https://x.example/t.xlsx"},
            {"name": "시내버스 — 군산시 문화관광", "url": "https://x.example/bus"}]
    assert chat_index._effective(srcs) == ["군산시내버스시간표 — 군산시, 시행 2024-10-21, https://x.example/t.xlsx"]
    assert chat_index._effective([]) == []


def test_estimate_and_tokens():
    assert chat_index.estimate_tokens("가나다") == 3
    assert chat_index.estimate_tokens("abcde") == 2
    assert chat_index.estimate_tokens("월명공원 09:00") == 4 + 3   # 4 Hangul + ceil(6 ASCII / 2.5)
    # the same vector as tests/js/chat.test.js (chatbot/knowledge.js tokens)
    assert chat_index.tokens("선유도 가는 법 Seonyudo 063-454-3337 a 群山 カフェ Кунсан café") == [
        "선유", "유도", "가는", "법", "seonyudo", "063", "454", "3337", "群山", "カフ", "フェ", "кунсан", "café"]


def test_the_build_writes_the_knowledge_in_every_mode(tmp_path):
    stats = build(SAMPLE, tmp_path / "out", "sample")
    chat = tmp_path / "out" / "chat"
    assert stats["chat"]["places"] == stats["entities"]
    assert all((chat / n).exists() for n in ("catalog.txt", "docs.json", "index.json"))
    assert json.loads((chat / "docs.json").read_text("utf-8"))["site"]
