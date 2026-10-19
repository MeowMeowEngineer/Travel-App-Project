"""tools/en_content.py for the seven other languages (--lang): the translation check per language (parity with the
language's money, separators, weekdays and months; promotional words; conflict notes; script and language), names
from the language's TourAPI service (fake responses: an official name, and resultCode=30 with the key masked),
prepare and merge. Fixtures are tiny and written in tmp folders here."""
import io
import json
from pathlib import Path
from urllib.parse import parse_qs, urlsplit

import pytest

from pipeline import intl_text, tourapi
from pipeline import locales as LC
from tools import en_content as C

ROOT = Path(__file__).resolve().parent.parent
NEW = ("ja", "zh-hans", "zh-hant", "de", "fr", "es", "ru")
ITEM = {"id": "p1", "slug": "근대건축관", "kind": "attraction", "category": "관광지", "indexable": True,
        "name": "군산근대건축관", "alternate_names": [],
        "facts": [{"key": "address", "label": "주소", "value": "전북특별자치도 군산시 해망로 214",
                   "address_en_candidate": "214 Haemang-ro, Gunsan-si, Jeonbuk State"},
                  {"key": "usetime", "label": "이용시간", "value": "09:00–18:00",
                   "alternatives": [{"value": "상시 개방", "provider": "한국관광공사 TourAPI"}]},
                  {"key": "restdate", "label": "쉬는 날", "value": "매주 월요일"},
                  {"key": "usefee", "label": "이용요금", "value": "성인 500원, 단체 1만원"},
                  {"key": "infocenter", "label": "문의", "value": "063-454-7870"}],
        "summary": "군산근대건축관은 옛 조선은행 군산지점 건물로, 2008년에 복원을 마쳤습니다.",
        "details": [], "faq": [{"q": "군산근대건축관은 언제 쉬나요?", "a": "매주 월요일에 쉽니다."}],
        "mentions": [], "ko_hash": "x"}
GOOD = {
    "ja": {"name": "グンサン近代建築館", "summary": "グンサン近代建築館は旧朝鮮銀行群山支店の建物で、2008年に復元を終えました。",
           "alt": "常時開放", "rest": "毎週月曜日", "fee": "大人500ウォン、団体10,000ウォン",
           "q": "グンサン近代建築館の休みはいつですか？", "a": "毎週月曜日が休みです。"},
    "zh-hans": {"name": "群山近代建筑馆", "summary": "群山近代建筑馆是旧朝鲜银行群山分行的建筑，2008年完成修复。",
                "alt": "全天开放", "rest": "每周一", "fee": "成人500韩元、团体10,000韩元",
                "q": "群山近代建筑馆什么时候休息？", "a": "每周一休息。"},
    "zh-hant": {"name": "群山近代建築館", "summary": "群山近代建築館是舊朝鮮銀行群山分行的建築，2008年完成修復。",
                "alt": "全天開放", "rest": "每週一", "fee": "成人500韓元、團體10,000韓元",
                "q": "群山近代建築館什麼時候休息？", "a": "每週一休息。"},
    "de": {"name": "Gunsan-Museum für moderne Architektur",
           "summary": "Das Gunsan-Museum für moderne Architektur ist das frühere Gebäude der Gunsan-Filiale der "
                      "Chosun-Bank. Die Restaurierung wurde 2008 abgeschlossen.",
           "alt": "Immer geöffnet", "rest": "Jeden Montag", "fee": "Erwachsene 500 Won, Gruppen 10.000 Won",
           "q": "Wann ist das Gunsan-Museum für moderne Architektur geschlossen?", "a": "Es ist jeden Montag geschlossen."},
    "fr": {"name": "Musée de l'architecture moderne de Gunsan",
           "summary": "Le musée de l'architecture moderne de Gunsan occupe l'ancien bâtiment de la succursale de Gunsan "
                      "de la banque de Chosun. Sa restauration a été achevée en 2008.",
           "alt": "Toujours ouvert", "rest": "Tous les lundis", "fee": "Adultes 500 wons, groupes 10\u202f000 wons",
           "q": "Quand le musée de l'architecture moderne de Gunsan est-il fermé ?", "a": "Il est fermé tous les lundis."},
    "es": {"name": "Museo de Arquitectura Moderna de Gunsan",
           "summary": "El Museo de Arquitectura Moderna de Gunsan ocupa el antiguo edificio de la sucursal de Gunsan del "
                      "Banco de Chosun. Su restauración terminó en 2008.",
           "alt": "Siempre abierto", "rest": "Todos los lunes", "fee": "Adultos 500 wones, grupos 10.000 wones",
           "q": "¿Cuándo cierra el Museo de Arquitectura Moderna de Gunsan?", "a": "Cierra todos los lunes."},
    "ru": {"name": "Музей современной архитектуры Кунсана",
           "summary": "Музей современной архитектуры Кунсана — бывшее здание кунсанского отделения Чосон-банка. "
                      "Реставрацию завершили в 2008 году.",
           "alt": "Открыт всегда", "rest": "Каждый понедельник", "fee": "Взрослые 500 вон, группы 10\u202f000 вон",
           "q": "Когда закрыт Музей современной архитектуры Кунсана?", "a": "Он закрыт каждый понедельник."},
}


def item_for(code: str) -> dict:
    """The batch item prepare --lang writes for ITEM (no official name: the translator writes it)."""
    loc = LC.get(code)
    return {**{k: v for k, v in ITEM.items()}, loc.name_key: "", f"{loc.name_key}_source": "translated",
            "name_rr": "Gunsangeundaegeonchukgwan"}


def good(code: str, **change) -> dict:
    g = {**GOOD[code], **change}
    loc = LC.get(code)
    return {"id": "p1", loc.name_key: g["name"], "summary": g["summary"],
            "facts": [{"key": "address", "value": "214 Haemang-ro, Gunsan-si, Jeonbuk State"},
                      {"key": "usetime", "value": g.get("time", "09:00–18:00"), "alternatives": [{"value": g["alt"]}],
                       **({"note": loc.conflict} if g.get("note", True) else {})},
                      {"key": "restdate", "value": g["rest"]},
                      {"key": "usefee", "value": g["fee"]},
                      {"key": "infocenter", "value": g.get("tel", "063-454-7870")}],
            "details": [], "faq": [{"q": g["q"], "a": g["a"]}]}


def run(tmp_path, code: str, out: dict) -> list[str]:
    (tmp_path / f"{code}-01.input.json").write_text(json.dumps({"type": "places", "lang": code, "items": [item_for(code)]},
                                                               ensure_ascii=False), "utf-8")
    path = tmp_path / f"{code}-01.output.json"
    path.write_text(json.dumps({"items": [out]}, ensure_ascii=False), "utf-8")
    return C.check([path])


@pytest.mark.parametrize("code", NEW)
def test_a_faithful_translation_passes(tmp_path, code):
    assert run(tmp_path, code, good(code)) == []


@pytest.mark.parametrize("code,change,finding", [
    ("ja", {"summary": "군산近代建築館は旧朝鮮銀行の建物で、2008年に復元を終えました。"}, "Korean script left"),
    ("de", {"tel": "063-454-7871"}, "phone 063-454-7870 missing"),
    ("ru", {"time": "09:00–19:00"}, "time 18:00 missing"),
    ("zh-hant", {"fee": "成人600韓元、團體10,000韓元"}, "amount 500韓元 missing"),
    ("de", {"fee": "Erwachsene 500 Won, Gruppen 1.000 Won"}, "amount 10.000 Won missing"),
    ("ja", {"summary": "グンサン近代建築館は人気の建物で、2008年に復元を終えました。"}, "promotional word: '人気'"),
    ("de", {"summary": "Das beliebte Museum ist das frühere Gebäude der Bank. Die Restaurierung wurde 2008 abgeschlossen."},
     "promotional word: 'beliebte'"),
    ("ru", {"summary": "Популярный музей — бывшее здание банка. Реставрацию завершили в 2008 году."},
     "promotional word: 'Популярный'"),
    ("zh-hant", {"summary": "群山近代建築館是推薦的舊建築，2008年完成修復。"}, "promotional word: '推薦'"),
    ("de", {"note": False}, "note must be"),
    ("ja", {"note": False}, "情報源によって値が異なります"),
    ("zh-hans", {"summary": GOOD["zh-hant"]["summary"]}, "Traditional characters in Simplified Chinese"),
    ("zh-hant", {"summary": GOOD["zh-hans"]["summary"]}, "Simplified characters in Traditional Chinese"),
    ("ja", {"summary": GOOD["zh-hans"]["summary"]}, "Chinese text in Japanese"),
    ("ru", {"summary": "The museum is the former Gunsan branch of the Bank of Chosun. Its restoration was finished in 2008."},
     "Latin text in Russian"),
    ("de", {"summary": "The museum is the former Gunsan branch of the Bank of Chosun. Its restoration was finished in 2008."},
     "English left in German"),
    ("fr", {"summary": "The museum is the former Gunsan branch of the Bank of Chosun. Its restoration was finished in 2008."},
     "English left in French"),
    ("es", {"summary": "The museum is the former Gunsan branch of the Bank of Chosun. Its restoration was finished in 2008."},
     "English left in Spanish"),
    ("es", {"summary": "Das Museum ist das frühere Gebäude der Bank und die Halle ist offen. Die Restaurierung wurde 2008 "
                       "abgeschlossen."}, "German left in Spanish"),
    ("ru", {"rest": "Каждый вторник"}, "weekday понедельник missing"),
    ("de", {"fee": "Erwachsene 500 Won, Gruppen 10,000 Won"}, "thousands as '3.000 Won'"),
    ("fr", {"time": "9h–18h"}, "write 24-hour HH:MM"),
    ("ja", {"a": "毎週月曜日が休みです.  "}, "ASCII period"),
    ("ru", {"name": "Gunsan Modern Architecture Museum"}, "a Russian name is written in Cyrillic"),
])
def test_check_catches(tmp_path, code, change, finding):
    found = run(tmp_path, code, good(code, **change))
    assert any(finding in x for x in found), found


def test_official_name_must_be_copied(tmp_path):
    item = {**item_for("ja"), "name_ja": "群山近代建築館", "name_ja_source": "TourAPI JpnService2"}
    (tmp_path / "ja-01.input.json").write_text(json.dumps({"type": "places", "lang": "ja", "items": [item]},
                                                          ensure_ascii=False), "utf-8")
    path = tmp_path / "ja-01.output.json"
    path.write_text(json.dumps({"items": [good("ja")]}, ensure_ascii=False), "utf-8")
    assert any("name_ja must be exactly '群山近代建築館'" in x for x in C.check([path]))


def test_strings_rows_keep_placeholders_and_plural_forms(tmp_path):
    items = [{"id": "FACT_LABELS.usetime", "ko": "이용시간"},
             {"id": "chrome.h_photos", "en": "{name} photos"},
             {"id": "chrome.lede_near.few", "en": "The first {n} stops are within 1 km of the start in a straight line"}]
    (tmp_path / "ru-02.input.json").write_text(json.dumps({"type": "strings", "lang": "ru", "items": items},
                                                          ensure_ascii=False), "utf-8")
    path = tmp_path / "ru-02.output.json"
    ok = [{"id": "FACT_LABELS.usetime", "ru": "Часы работы"}, {"id": "chrome.h_photos", "ru": "{name}: фотографии"},
          {"id": "chrome.lede_near.few", "ru": "Первые {n} остановки находятся в пределах 1 km от начала по прямой"}]
    path.write_text(json.dumps({"items": ok}, ensure_ascii=False), "utf-8")
    assert C.check([path]) == []
    bad = [{"id": "FACT_LABELS.usetime", "ru": "Hours"}, {"id": "chrome.h_photos", "ru": "фотографии"},
           {"id": "chrome.lede_near.few", "ru": "Первые {n} остановки рядом"}]
    path.write_text(json.dumps({"items": bad}, ensure_ascii=False), "utf-8")
    found = C.check([path])
    assert any("placeholders must stay ['{name}']" in x for x in found)
    assert any("number 1 missing" in x for x in found)


class FakeResp(io.BytesIO):
    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False


def _ok(items):
    return json.dumps({"response": {"header": {"resultCode": "0000", "resultMsg": "OK"},
                                    "body": {"items": {"item": items}}}}).encode("utf-8")


def test_names_official_and_provider_error_masks_key(tmp_path, monkeypatch):
    data = tmp_path / "data"
    data.mkdir()
    (data / "site.json").write_text(json.dumps({"region": "군산", "locality": "군산시"}, ensure_ascii=False), "utf-8")
    # p1: one candidate within the radius, no name or photo in common — it stands because the item's address carries
    # the place's building number (review 2026-10-14: without it the match is dropped, see test_vet_matches_…)
    places = [{"id": "p1", "name": "월명공원", "status": "published", "kind": "attraction",
               "geo": {"lat": 35.99, "lng": 126.71}, "tourapi": {"contenttypeid": "12"},
               "facts": {"address": {"value": "전북특별자치도 군산시 공원길 21"}}},
              {"id": "p2", "name": "바다식당", "status": "published", "kind": "food", "geo": {"lat": 35.9, "lng": 126.6}}]
    (data / "places.json").write_text(json.dumps(places, ensure_ascii=False), "utf-8")
    key = "secret-key-123456"
    monkeypatch.setenv("TOURAPI_KEY", key)

    def fake_urlopen(req, timeout=20):
        url = req.full_url
        if "/ldongCode" in url:
            if "lDongRegnCd" in parse_qs(urlsplit(url).query):
                return FakeResp(_ok([{"code": "130", "name": "군산시"}]))
            return FakeResp(_ok([{"code": "52", "name": "전북특별자치도"}]))
        if "/JpnService2/areaBasedList" in url:
            return FakeResp(_ok([{"contentid": "9", "contenttypeid": "76", "title": "月明公園", "mapx": "126.7101",
                                  "mapy": "35.9901", "addr1": "全羅北道群山市コンウォンギル21"}]))
        return FakeResp(("<OpenAPI_ServiceResponse><cmmMsgHeader><returnAuthMsg>SERVICE_KEY_IS_NOT_REGISTERED_ERROR "
                         f"{key}</returnAuthMsg><returnReasonCode>30</returnReasonCode></cmmMsgHeader>"
                         "</OpenAPI_ServiceResponse>").encode("utf-8"))
    monkeypatch.setattr(tourapi.urllib.request, "urlopen", fake_urlopen)
    monkeypatch.setattr(tourapi.time, "sleep", lambda s: None)
    st = C.names(data, 10, False, "ja")
    rows = json.loads((data / "ja" / "names.json").read_text("utf-8"))
    assert st["error"] == "" and st["matched"] == 1
    assert rows["p1"]["name_ja"] == "月明公園" and rows["p1"]["name_ja_source"] == "TourAPI JpnService2"
    assert rows["p2"]["name_ja"] == "" and rows["p2"]["name_ja_source"] == "translated"
    st = C.names(data, 10, False, "ru")
    assert "resultCode=30" in st["error"] and key not in st["error"] and "«KEY»" in st["error"]
    rows = json.loads((data / "ru" / "names.json").read_text("utf-8"))
    assert {r["name_ru_source"] for r in rows.values()} == {"translated"}


def test_merge_lang_writes_records_the_engine_reads(tmp_path):
    data = tmp_path / "data"
    data.mkdir()
    (data / "places.json").write_text(json.dumps([{"id": "p1", "name": "군산근대건축관", "faq": [{"source": "x"}]}],
                                                 ensure_ascii=False), "utf-8")
    (data / "guides.json").write_text("[]", "utf-8")
    out = tmp_path / "b"
    out.mkdir()
    item = {**item_for("de"), "slug": "근대건축관", "ko_hash": "abc"}
    (out / "de-01.input.json").write_text(json.dumps({"type": "places", "lang": "de", "items": [item]},
                                                     ensure_ascii=False), "utf-8")
    (out / "de-01.output.json").write_text(json.dumps({"items": [good("de")]}, ensure_ascii=False), "utf-8")
    (out / "de-02.input.json").write_text(json.dumps({"type": "strings", "lang": "de", "items": [
        {"id": "FACT_LABELS.usetime", "ko": "이용시간"}, {"id": "chrome.h_photos", "en": "{name} photos"}]},
        ensure_ascii=False), "utf-8")
    (out / "de-02.output.json").write_text(json.dumps({"items": [{"id": "FACT_LABELS.usetime", "de": "Öffnungszeiten"},
                                                                 {"id": "chrome.h_photos", "de": "Fotos: {name}"}]},
                                                      ensure_ascii=False), "utf-8")
    counts = C.merge([out / "de-01.output.json", out / "de-02.output.json"], data)
    assert counts["lang"] == "de" and counts["places"] == 1 and counts["strings"] == 2
    rec = json.loads((data / "de" / "places.json").read_text("utf-8"))["p1"]
    assert rec["name_de"] == GOOD["de"]["name"] and rec["name_de_source"] == "translated" and "name_en" not in rec
    assert rec["facts"]["usetime"]["note"] == LC.get("de").conflict and rec["ko_hash"] == "abc"
    strings = json.loads((data / "de" / "strings.json").read_text("utf-8"))
    assert strings["FACT_LABELS.usetime"] == {"ko": "이용시간", "de": "Öffnungszeiten"}
    assert strings["chrome.h_photos"] == {"en": "{name} photos", "de": "Fotos: {name}"}
    assert not (data / "en").exists()


def test_script_checks():
    assert LC.traditional_only("群山旅遊全攻略") == ["遊"] and LC.traditional_only("群山旅游全攻略") == []
    assert LC.simplified_only("群山旅游全攻略") == []   # 游 is also a Traditional character
    assert LC.simplified_only("韩国") == ["韩", "国"] and LC.simplified_only("群山旅遊全攻略") == []
    assert LC.script_problems("これは群山の博物館です。", "ja") == []
    assert LC.script_problems("这是群山的博物馆，二零零八年完成修复。", "ja")
    assert LC.script_problems("Это музей.", "ru") == [] and LC.script_problems("This museum is open.", "ru")


def test_parity_reads_grouped_decimals_and_room_lists():
    """Review 2026-10-14: '1,868.7㎡' is one decimal number in every language ('1.868,7 m²' in German, '1 868,7' in
    Russian), and '203,204호' lists two rooms; neither may make a faithful translation fail."""
    from tools.en_content import parity_l
    assert parity_l("면적은 1,868.7㎡입니다.", "Die Fläche beträgt 1.868,7 m².", "de") == []
    assert parity_l("면적은 1,868.7㎡입니다.", "La superficie es de 1.868,7 m².", "es") == []
    assert parity_l("면적은 1,868.7㎡입니다.", "Площадь — 1\u202f868,7 м².", "ru") == []
    assert parity_l("면적은 1,868.7㎡입니다.", "面積は1,868.7㎡です。", "ja") == []
    assert parity_l("면적은 1,868.7㎡입니다.", "Die Fläche beträgt 1.868 m².", "de")       # a dropped decimal still fails
    assert parity_l("2층 203,204호", "2. Stock, Nr. 203 und 204", "de") == []
    assert parity_l("2층 203,204호", "2. Stock, Nr. 203", "de")                            # a dropped room still fails


def test_vet_matches_needs_the_building_number_or_a_name_and_one_item_per_place():
    """Review 2026-10-14: a coordinate-only match gave 이성당's Japanese title to six restaurants. A weak match stands
    only with the place's building number in the item's address; an item shared by several places goes to the ones
    matched by name or photo."""
    from tools.en_content import vet_matches
    loc = LC.get("ja")
    places = {"p1": {"facts": {"address": "전북특별자치도 군산시 중앙로 177"}},
              "p2": {"facts": {"address": {"value": "전북특별자치도 군산시 구영7길 59"}}},
              "p3": {"facts": {"address": "전북특별자치도 군산시 해망로 244-7"}},
              "p4": {"facts": {"address": "전북특별자치도 군산시 해망로 244-7"}}}

    def row(name, cid, addr, basis):
        return {"name_ja": name, "name_ja_source": "TourAPI JpnService2", "ja_contentid": cid, "addr_ja": addr,
                "match_m": 50.0, "match_basis": basis}
    rows = {"p1": row("李盛堂", "1", "チョンブク特別自治道クンサン市チュンアンロ177", "coordinates_type"),
            "p2": row("李盛堂", "1", "チョンブク特別自治道クンサン市チュンアンロ177", "coordinates_type"),
            "p3": row("旧群山税関", "2", "ヘマンロ244-7", "coordinates_type_same_photo"),
            "p4": row("旧群山税関", "2", "ヘマンロ244-7", "coordinates_type_korean_title")}
    assert vet_matches(rows, places, loc) == ["p2"]
    assert rows["p1"]["name_ja"] == "李盛堂" and rows["p2"]["name_ja"] == "" and rows["p2"]["name_ja_source"] == "translated"
    assert rows["p2"]["match_basis"].startswith("rejected") and rows["p3"]["name_ja"] == rows["p4"]["name_ja"] == "旧群山税関"
