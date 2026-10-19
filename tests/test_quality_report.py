"""tools/quality_report.py — counts only what is shown, flags thin pages and hygiene issues."""
import importlib.util
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
spec = importlib.util.spec_from_file_location("quality_report", ROOT / "tools" / "quality_report.py")
qr = importlib.util.module_from_spec(spec)
spec.loader.exec_module(qr)


def test_report_counts_shown_pages_and_flags(tmp_path):
    data, out = tmp_path / "data", tmp_path / "out"
    data.mkdir()
    places = [
        {"slug": "a", "name": "가게", "kind": "food", "status": "draft", "summary": "가게는 군산시 신창동에 있는 한식 음식점입니다.",
         "facts": {"address": "전북특별자치도  군산시 구영3길 70  70", "menu": "꽃게장"}, "images": []},
        {"slug": "b", "name": "박물관", "kind": "attraction", "status": "draft", "summary": "박물관은 근대 전시관입니다. 월요일에 쉽니다.",
         "facts": {"address": "군산시 해망로 240", "usetime": "09:00~18:00", "restdate": "월요일", "infocenter": "063-000-0000"},
         "images": [{"license": "KOGL-1"}], "geo": {"lat": 1, "lng": 2},
         "faq": [{"q": "무료로 들어갈 수 있나요?", "a": "-"}, {"q": "주차 돼?", "a": "-"}]},
        {"slug": "hidden", "name": "아리랑 코스", "kind": "attraction", "status": "draft", "facts": {}},
    ]
    (data / "places.json").write_text(json.dumps(places, ensure_ascii=False), "utf-8")
    (data / "site.json").write_text("{}", "utf-8")
    for slug in ("a", "b"):
        (out / "places" / slug).mkdir(parents=True)
        (out / "places" / slug / "index.html").write_text("<html></html>", "utf-8")
    rep = qr.analyse(data, out, "2026-10-08")
    assert rep["shown_places"] == 2 and rep["data_places"] == 3
    food, attr = rep["kinds"]["food"], rep["kinds"]["attraction"]
    assert food["summary_tautology_first"] == 1 and food["thin"] == 1        # 상투구 한 문장 + 실용 정보 부족
    assert attr["phone"] == 1 and attr["photo"] == 1 and attr["thin"] == 0
    assert rep["hygiene"]["address_multiple_spaces"] == 1 and rep["hygiene"]["address_repeated_number"] == 1
    assert rep["faq"]["style"] == {"존댓말": 1, "반말": 1}
    assert "suspected_non_place" not in rep["hygiene"]                      # 화면에 없는 장소는 세지 않는다
    assert "| food |" in qr.to_md(rep)
