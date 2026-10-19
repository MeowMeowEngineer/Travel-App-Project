"""The closed day inside an hours value in the language versions (QA 2026-10-15 SRC-04): found at the place the
Korean parse finds it (pipeline/en_site.closed_span), never 'not listed' when the Korean has one, never cut, and
not repeated in the hours tile; pipeline.validate reports a version that cannot show it."""
import pytest

from pipeline import en_site
from pipeline import locales as LC
from pipeline.validate import list_closed_problems

CASES = [  # (Korean, translation, code, closed part, hours part)
    ("11:30~21:00/둘째,넷째주 일요일 휴무", "11:30–21:00／第二・第四日曜日休み", "ja", "第二・第四日曜日休み", "11:30–21:00"),
    ("11:30~21:00/둘째,넷째주 일요일 휴무", "11:30–21:00/每月第二、第四个周日休息", "zh-hans", "每月第二、第四个周日休息", "11:30–21:00"),
    ("11:30~21:00/둘째,넷째주 일요일 휴무", "11:30–21:00 / fermé les deuxième et quatrième dimanches du mois", "fr",
     "fermé les deuxième et quatrième dimanches du mois", "11:30–21:00"),
    ("10:00~21:00 매주 화요일 휴무", "10:00–21:00 毎週火曜日休み", "ja", "毎週火曜日休み", "10:00–21:00"),
    ("10:30 ~ 20:00,  휴무일 : 매주 화요일", "10:30–20:00，公休日：每週二", "zh-hant", "每週二", "10:30–20:00"),
    ("10:30 ~ 20:00,  휴무일 : 매주 화요일", "10:30–20:00, días de cierre: todos los martes", "es", "todos los martes", "10:30–20:00"),
    ("11:00~20:30 (마지막 주문 20:00) / 연중무휴", "11:00–20:30（ラストオーダー20:00）／年中無休", "ja", "年中無休",
     "11:00–20:30（ラストオーダー20:00）"),
    ("24시간영업 / 연중무휴", "24時間営業／年中無休", "ja", "年中無休", "24時間営業"),
    ("11:00~20:00 / 동절기(일요일 휴무)", "11:00–20:00／冬季（日曜日休み）", "ja", "冬季（日曜日休み）", "11:00–20:00"),
]


@pytest.mark.parametrize("ko,tr,code,closed,hours", CASES)
def test_closed_span_follows_the_korean_parse(ko, tr, code, closed, hours):
    loc = LC.get(code)
    assert en_site.closed_span(ko, tr, loc)["text"] == closed
    assert en_site.hours_part(ko, tr, loc) == hours


def test_closed_span_reports_what_it_cannot_align():
    loc = LC.get("ja")
    assert en_site.closed_span("11:30~21:00", "11:30–21:00", loc) is None            # no closed day in the Korean
    sp = en_site.closed_span("11:30~21:00/둘째,넷째주 일요일 휴무", "11:30–21:00 第二・第四日曜日休み 12:00", loc)
    assert sp["start"] == -1 and "times" in sp["why"]
    sp = en_site.closed_span("예약제 / 특별한 휴무없음", "予約制、特に休みなし", loc)
    assert sp["start"] == -1


def _row(pid, cell):
    return (f'<li class="rec" id="r1"><a class="rec-link" data-place="{pid}">x</a><dl class="rec-cells">'
            f'{cell}</dl></li>')


def test_list_closed_problems():
    ko = _row("p1", '<div class="c-closed"><dt>쉬는 날</dt><dd><span class="kf-main tn">매주 월요일</span></dd></div>') + \
        _row("p2", '<div class="c-closed is-conflict"><dt>쉬는 날</dt><dd>…</dd></div>') + \
        _row("p3", '<div class="c-closed"><dt>쉬는 날</dt><dd><span class="kf-na">확인 필요</span></dd></div>')
    ja = _row("p1", '<div class="c-closed"><dt>休業日</dt><dd><span class="kf-na">記載なし</span></dd></div>') + \
        _row("p2", '<div class="c-closed"><dt>休業日</dt><dd><span class="kf-main tn">毎週月曜日</span></dd></div>') + \
        _row("p3", '<div class="c-closed"><dt>休業日</dt><dd><span class="kf-na">記載なし</span></dd></div>')
    problems = list_closed_problems(ko, ja)
    assert len(problems) == 2 and problems[0].startswith("p1:") and problems[1].startswith("p2:")
    assert list_closed_problems(ko, ko) == []


# a closed-day field ('restdate', SRC-04-restdate-cut): whole where the Korean tile shows it whole
RESTDATE = [  # (Korean, translation, code, the tile)
    ("매월 첫째 / 셋째 일요일", "jeden ersten / dritten Sonntag im Monat", "de", "Jeden ersten / dritten Sonntag im Monat"),
    ("매달 셋째, 다섯째 수요일", "The third and fifth Wednesday of every month", "en",
     "The third and fifth Wednesday of every month"),
    ("연중무휴\n※ 단, 우천시 휴무", "Open all year ※ Closed on rainy days", "en", "Open all year"),       # the note goes
    ("매달 2, 4번째 화요일 (전화 문의)", "2nd and 4th Tuesday of every month (call for details)", "en",
     "2nd and 4th Tuesday of every month"),                                                           # the aside goes
    ("초원사진관(매주 첫째/셋째 월요일)", "Chowon Photo Studio (every first and third Monday)", "en",
     "Chowon Photo Studio (every first and third Monday)"),        # the Korean tile writes '첫째, 셋째': still whole
]


@pytest.mark.parametrize("ko,tr,code,tile", RESTDATE)
def test_closed_day_field_is_whole_where_the_korean_is(ko, tr, code, tile):
    assert en_site.ko_closed_whole(ko)
    assert en_site.closed_brief(ko, tr, LC.get(code)) == {"main": tile, "sub": "", "more": False}


def test_closed_day_field_the_korean_shortens_stays_shortened():
    ko, tr, loc = "매주 월요일, 1월 1일, 설날 및 추석 당일", "Every Monday, January 1, Seollal and Chuseok", LC.get("en")
    assert not en_site.ko_closed_whole(ko)
    assert en_site.closed_brief(ko, tr, loc) == en_site.brief_en("restdate", tr, loc)


def test_key_fact_problems_reports_a_cut_closed_day():
    """validate.key_fact_problems: the Korean tile shows '매월 첫째 / 셋째 일요일' whole, so a version's tile showing
    only 'Jeden ersten' (the old cut) is an error, the whole value is none, and a missing tile is the first error."""
    from pipeline.validate import key_fact_problems
    e = {"id": "p1", "kind": "attraction", "facts": {"restdate": "매월 첫째 / 셋째 일요일"}}
    p = {"e": e, "rec": {"facts": {"restdate": {"value": "jeden ersten / dritten Sonntag im Monat"}}}}

    class FakeSite:
        def __init__(self, slot):
            self._slot = slot

        def slot(self, p, name):
            return self._slot

    def tile(main):
        return {"key": "closed", "src_key": "restdate", "main": main, "sub": "", "more": False, "vals": []}

    problems = key_fact_problems(FakeSite(tile("Jeden ersten")), p)
    assert problems and problems[0].startswith("쉬는 날이 잘림")
    assert key_fact_problems(FakeSite(tile("Jeden ersten / dritten Sonntag im Monat")), p) == []
    gone = key_fact_problems(FakeSite({"skip": True, "why": "test"}), p)
    assert gone and gone[0].startswith("쉬는 날: 한국어 첫 화면·목록에 있는데")
