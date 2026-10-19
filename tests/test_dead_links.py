"""Dead homepage links (QA 2026-10-15 SRC-02/02b/02d): data/<region>/dead_links.json, dropped in build.State,
checked by validate."""
import json
import shutil
from pathlib import Path

import pytest

from pipeline import schema
from pipeline.build import State, build
from pipeline.textutil import dead_reason, dead_tokens, drop_dead_links
from pipeline.validate import validate

ROOT = Path(__file__).resolve().parent.parent
SAMPLE = ROOT / "data" / "sample"
DATA = ROOT / "data" / "gunsan"
DEAD = {"hosts": {"modoo.at": {"reason": "modoo 종료", "checked_at": "2026-10-15"}},
        "urls": {"http://www.sunu.co.kr/": {"reason": "다른 사이트로 넘어감", "checked_at": "2026-10-15"},
                 "https://blog.naver.com/chunulumi": {"reason": "다른 업체 블로그", "checked_at": "2026-10-15"}}}


def test_dead_reason_matches_hosts_and_single_urls():
    assert dead_reason("https://guesthousiut.modoo.at", DEAD) == "modoo 종료"
    assert dead_reason("http://www.x.modoo.at/", DEAD) == "modoo 종료"
    assert dead_reason("modoo.at", DEAD) == "modoo 종료"
    for other in ("https://notmodoo.at", "https://modoo.at.example.com", "", None, "전화 문의"):
        assert dead_reason(other, DEAD) == "", other
    for same in ("https://www.sunu.co.kr", "http://www.sunu.co.kr", "http://sunu.co.kr/", "www.sunu.co.kr"):
        assert dead_reason(same, DEAD) == "다른 사이트로 넘어감", same
    assert dead_reason("http://www.sunu.co.kr/rooms", DEAD) == ""          # one URL, not the whole site
    assert dead_reason("https://blog.naver.com/chunulumi/", DEAD) == "다른 업체 블로그"
    assert dead_reason("https://blog.naver.com/other", DEAD) == ""
    assert dead_tokens(DEAD) == ["modoo.at", "sunu.co.kr", "blog.naver.com/chunulumi"]


def test_drop_dead_links_removes_values_and_promotes_a_live_alternative():
    tour = {"provider": "한국관광공사 TourAPI", "checked_at": "2026-10-08", "contentid": "7"}
    recs = [
        {"id": "a", "facts": {"homepage": "https://a.modoo.at", "parking": "가능"},
         "fact_sources": {"homepage": {"provider": "군산시 문화관광"}},
         "fact_alternatives": {"homepage": [{"value": "https://blog.naver.com/chunulumi", **tour, "relation": "also"}]}},
        {"id": "b", "facts": {"homepage": "http://www.sunu.co.kr/"},
         "fact_alternatives": {"homepage": [{"value": "https://b.example.kr", **tour, "relation": "also"}],
                               "usetime": [{"value": "09:00~18:00", **tour}]},
         "official": {"homepage": "http://www.sunu.co.kr/", "source_url": "https://www.gunsan.go.kr/x"}},
        {"id": "c", "facts": {"homepage": "https://c.example.kr"}, "official": {"homepage": "https://c.example.kr"}},
        {"id": "ev", "name": "축제", "homepage": "https://fest.modoo.at"},
    ]
    rows = drop_dead_links(recs, DEAD)
    a, b, c, ev = recs
    assert a["facts"] == {"parking": "가능"} and a["fact_sources"] == {} and "fact_alternatives" not in a
    assert b["facts"]["homepage"] == "https://b.example.kr"                    # the live 'also' value takes over
    assert b["fact_sources"]["homepage"] == tour
    assert "homepage" not in b["fact_alternatives"] and b["fact_alternatives"]["usetime"]
    assert b["official"] == {"source_url": "https://www.gunsan.go.kr/x"}
    assert c["facts"]["homepage"] == "https://c.example.kr" and c["official"]["homepage"] == "https://c.example.kr"
    assert "homepage" not in ev
    assert [(r["id"], r["key"]) for r in rows] == [("a", "fact_alternatives.homepage"), ("a", "facts.homepage"),
                                                   ("b", "facts.homepage"), ("b", "official.homepage"), ("ev", "homepage")]
    assert all(r["reason"] and r["url"] for r in rows)
    assert drop_dead_links([{"id": "x", "facts": {"homepage": "https://a.modoo.at"}}], {}) == []


def _stay(slug, homepage):
    return {"id": slug, "slug": slug, "name": "바다호텔", "kind": "stay", "tier": "basic", "status": "published",
            "reviewed_at": "2026-10-08", "themes": [], "summary": "바다호텔은 객실 30개와 주차장 40면을 갖춘 숙소입니다.",
            "facts": {"address": "전북특별자치도 군산시 해망로 240", "parking": "가능", "homepage": homepage},
            "facts_source": {"provider": "군산시 문화관광", "checked_at": "2026-10-08"},
            "original": {"source_name": "군산시 문화관광", "source_url": "https://www.gunsan.go.kr/tour",
                         "license": "NONE", "collected_at": "2026-10-05"}}


@pytest.fixture()
def built(tmp_path):
    data = tmp_path / "data"
    shutil.copytree(SAMPLE, data)
    places = json.loads((data / "places.json").read_text("utf-8")) + [_stay("sea-hotel", "https://seahotel.modoo.at")]
    (data / "places.json").write_text(json.dumps(places, ensure_ascii=False), "utf-8")
    (data / "dead_links.json").write_text(json.dumps(DEAD, ensure_ascii=False), "utf-8")
    out = tmp_path / "prod"
    stats = build(data, out, "production")
    return data, out, stats


def test_build_drops_the_dead_homepage_and_the_page_falls_below_the_index_rule(built):
    data, out, stats = built
    S = State(data, "production")
    e = S.ent_by_slug["sea-hotel"]
    assert "homepage" not in e["facts"] and stats["dead_links"] == 1
    assert e["_index_ok"] is False and e["_noindex"] is True
    assert e["_index_reasons"] == [schema.INDEX_REASONS["groups"]]
    texts = [f.read_text("utf-8") for f in out.rglob("*") if f.is_file() and f.suffix in (".html", ".txt", ".json")]
    assert texts and not any("modoo.at" in t for t in texts)
    assert not [x for x in validate(data, out, "production")[0] if "종료·없는 주소" in x]


def test_validate_fails_a_dead_address_left_in_prose_or_a_link(built):
    data, out, _ = built
    page = out / "places" / "sea-hotel" / "index.html"
    html = page.read_text("utf-8")
    page.write_text(html.replace("</main>", '<p>홈페이지는 https://y.modoo.at 입니다.</p>'
                                            '<a href="http://www.sunu.co.kr">x</a></main>', 1), "utf-8")
    (out / "llms-full.txt").write_text((out / "llms-full.txt").read_text("utf-8") + "\nblog.naver.com/chunulumi\n", "utf-8")
    errors = [x for x in validate(data, out, "production")[0] if "종료·없는 주소" in x]
    assert any("/places/sea-hotel/index.html" in x and "글에 남음: modoo.at" in x for x in errors)
    assert any("링크: http://www.sunu.co.kr" in x for x in errors)
    assert any(x.startswith("[llms-full.txt]") and "blog.naver.com/chunulumi" in x for x in errors)
