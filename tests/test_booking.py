"""예약하기, step 1 (pipeline/booking.py, data/<region>/booking.json, templates/_ui.html.j2 book()): the official booking
pages a page links as buttons. The words exist for Korean and every version (locales.BOOK_WORDS: the national services;
a city's own services name themselves in its registry, booking.json services.<key>.names) and the chat's cards use the
same word (chat.js kinds.book). The registry tests that read the engine's first site's booking.json, places and guides
stay there (tests/excluded_gunsan_tests.txt); this site's registry is checked by pipeline.validate."""
import re
from pathlib import Path
from types import SimpleNamespace

from pipeline import booking
from pipeline import locales as LC
from pipeline.textutil import drop_dead_links

ROOT = Path(__file__).resolve().parent.parent
HANGUL = re.compile(r"[가-힣]")


def _ids(targets):
    return [t["key"] for t in targets]


def test_book_words_cover_every_version_hand_written():
    assert set(LC.BOOK_WORDS) == {"ko", *LC.ORDER}
    ko = LC.BOOK_WORDS["ko"]
    for code, w in LC.BOOK_WORDS.items():
        assert set(w) == set(ko) and set(w["svc"]) == set(ko["svc"]) == {"bus", "rail", "ferry", "forest"}, code
        assert all(str(v).strip() for k, v in w.items() if k != "svc") and all(v.strip() for v in w["svc"].values()), code
        if code != "ko":
            text = " ".join([*(v for k, v in w.items() if k != "svc"), *w["svc"].values()])
            assert not HANGUL.search(text), code
            assert w["book"] != ko["book"] and w["note"] != ko["note"], code   # no Korean stand-in


def test_the_chat_cards_use_the_same_word():
    js = (ROOT / "templates" / "assets" / "chat.js").read_text("utf-8")
    blocks = dict(re.findall(r'\n    "?([a-zA-Z-]+)"?: \{\n(.*?)\n    \},', js, re.S))
    for code in ("ko", *LC.ORDER):
        html = "ko" if code == "ko" else LC.get(code).html
        kinds = re.search(r"kinds: \{([^}]*)\}", blocks[html]).group(1)
        assert f'book: "{LC.BOOK_WORDS[code]["book"]}"' in kinds, code


def test_a_dead_contested_or_excluded_reservationurl_is_no_button():
    reg = {"services": {}, "places": {}, "exclude_hosts": ["airbnb.com"]}
    dead = {"hosts": {"modoo.at": {"reason": "종료", "checked_at": "2026-10-15"}}, "urls": {}}
    fake = SimpleNamespace(booking=reg, dead_links=dead)
    e = {"id": "x", "facts": {"reservationurl": "http://hotel.modoo.at/"}}
    assert _ids(booking.place_targets(SimpleNamespace(booking=reg, dead_links=None), e)) == ["reservationurl"]
    assert booking.place_targets(fake, e) == []          # listed in dead_links.json
    drop_dead_links([e], dead)                           # as build.State does first
    assert "reservationurl" not in e["facts"] and booking.place_targets(fake, e) == []
    assert booking.place_targets(fake, {"id": "y", "facts": {"reservationurl": "https://www.airbnb.com/rooms/1"}}) == []
    assert booking.place_targets(fake, {"id": "y", "facts": {"reservationurl": "https://m.airbnb.com/rooms/1"}}) == []
    two = {"id": "z", "facts": {"reservationurl": "http://a-hotel.kr/"},
           "fact_alternatives": {"reservationurl": [{"value": "http://b-hotel.kr/", "provider": "공식 홈페이지"}]}}
    assert booking.place_targets(fake, two) == []        # sources differ: the facts card shows both, no button picks one
    assert [t["url"] for t in booking.place_targets(fake, {"id": "w", "facts": {"reservationurl": "a-hotel.kr"}})] \
        == ["https://a-hotel.kr"]


def test_the_prompt_and_tracking_name_the_booking_links():
    rules = (ROOT / "chatbot" / "prompt.js").read_text("utf-8")
    assert rules.count("'예약하기'") == 2 and "never link a booking or travel-agency site the data does not list" in rules
    track = (ROOT / "templates" / "assets" / "track.js").read_text("utf-8")
    assert "params.link_lang = a.getAttribute('hreflang')" in track


def test_a_city_service_names_itself_in_the_registry():
    """A city's own service (a city tour, a campground) is named by the registry in each version; a version without a
    name is a data problem, never a blank button."""
    names = {code: f"Tour {code}" for code in LC.ORDER} | {"ko": "시티투어"}
    reg = {"services": {"citytour": {"url": "https://tour.example.kr/", "basis": "places.json facts.homepage",
                                     "checked_at": "2026-10-19", "names": names}},
           "places": {}}
    S = SimpleNamespace(booking=reg, entities_all=[], entities=[], dead_links=None)
    t = booking._svc(reg, "citytour")
    assert booking.view([t], "ko")[0]["name"] == "시티투어"
    assert booking.view([t], "de", lambda n: n)[0]["name"] == "Tour de"
    assert booking.data_problems(S) == []
    del names["ja"]
    assert any("ja 이름" in x for x in booking.data_problems(S))
    national = booking._svc({"services": {"rail": {"url": "https://www.korail.com/"}}}, "rail")
    assert booking.view([national], "ko")[0]["name"] == LC.BOOK_WORDS["ko"]["svc"]["rail"]
