"""Places that belong together (data part_of, pipeline/relations.py, operator decision 2026-10-16): a feature inside
another place (군산 동국사 대웅전 in 동국사, a pier on 장자도) or two pages for one building (구 조선은행 군산지점 /
군산근대건축관). The evidence codes recompute from the records, so a relation cannot be invented; the child page names
its parent, the parent lists its parts, same-building pages name each other the same way, nearby and similar-name
rows never show the page's own family, JSON-LD says part/whole only for 'inside', and the index criteria and the list
counts do not change."""
import json
import re
import shutil
from pathlib import Path

import pytest

from pipeline import jsonld, locales as LC, present, relations
from pipeline.build import State, build, entity_ctx, make_env
from pipeline.schema import index_status
from pipeline.en_source import _name_table, place_item
from pipeline.validate import PageScan, _graph_nodes, relation_page_problems, scan_file, validate

ROOT = Path(__file__).resolve().parent.parent
SAMPLE, GUNSAN = ROOT / "data" / "sample", ROOT / "data" / "gunsan"
HANGUL = re.compile(r"[가-힣]")


def rec(id_, name, address="", geo=None, cid="", summary="", homepage="", source="", alt=None, part_of=None):
    r = {"id": id_, "name": name, "slug": id_, "kind": "attraction", "status": "published", "summary": summary,
         "facts": {"address": address, **({"homepage": homepage} if homepage else {})},
         "tourapi": {"contentid": cid} if cid else {}, "alternate_names": alt or []}
    if geo:
        r["geo"] = {"lat": geo[0], "lng": geo[1]}
    if source:
        r["original"] = {"source_url": source}
    if part_of:
        r["part_of"] = part_of
    return r


# ---------------------------------------------------------------- evidence
def test_norm_address_and_numbered():
    a = relations.norm_address("전라북도 군산시 조촌1길 21 (경장동)")
    assert a == relations.norm_address("전북특별자치도 군산시 조촌1길 21(경장동)") == "군산시조촌1길21"
    assert relations.numbered(a)
    assert not relations.numbered(relations.norm_address("전북특별자치도 군산시 옥도면 대장도리"))


def test_evidence_codes():
    hall = rec("p", "군산근대건축관", "전북특별자치도 군산시 해망로 214", (35.98942, 126.71416), "2469034",
               summary="군산근대건축관은 옛 조선은행 건물입니다.", source="https://www.gunsan.go.kr/tour/m2338/view/1379526",
               alt=["근대건축관 (구)조선은행군산지점"])
    bank = rec("c", "구 조선은행 군산지점", "전라북도 군산시 해망로 214", (35.98942, 126.71416), "2469034",
               summary="구 조선은행 군산지점은 2013년 군산 근대건축관이 됐습니다.", alt=["근대건축관 (구)조선은행군산지점"])
    assert relations.evidence(bank, hall) == {"contentid", "address", "geo", "alt_name", "text"}
    # a bare 리 address shared by a whole island is no evidence, neither is a road named after a 리 with a lot number
    peak = rec("x", "대장봉", "전북특별자치도 군산시 옥도면 대장도리", (35.817354, 126.394605),
               summary="대장봉은 옥도면 대장도리에 있습니다.")
    isle = rec("y", "대장도", "전북특별자치도 군산시 옥도면 대장도리", (35.8180980694, 126.3944972601))
    assert relations.evidence(peak, isle) == set()
    light = rec("z", "선유도항방파제등대", "전북특별자치도 군산시 옥도면 선유도리 474-1")
    assert "address_name" not in relations.evidence(light, rec("s", "선유도", "전북특별자치도 군산시 옥도면 선유남길 34-22"))
    # a road address named after the parent, a homepage that is the parent's own page, a summary that names it
    pier = rec("a", "장자도선착장", "전북특별자치도 군산시 옥도면 장자도1길 10", summary="문의는 장자도 매표소로 합니다.")
    assert relations.evidence(pier, rec("b", "장자도", "전북특별자치도 군산시 옥도면 장자도리")) == {"address_name", "text"}
    lake = rec("l", "월명호수", homepage="https://www.gunsan.go.kr/tour/m2094/view/305373")
    park = rec("m", "월명공원", source="https://www.gunsan.go.kr/tour/m2094/view/305373?s_idx=2")
    assert relations.evidence(lake, park) == {"homepage"}
    portal = rec("n", "어느 섬", source="https://www.gunsan.go.kr/tour")   # a site's front page names nothing
    assert relations.evidence(rec("o", "등대", homepage="https://www.gunsan.go.kr/tour"), portal) == set()
    # the child's own name does not count as naming the parent ('은파호수공원 물빛다리는'), the place itself does
    bridge = rec("q", "은파호수공원 물빛다리", summary="은파호수공원 물빛다리는 은파호수공원에 놓인 다리입니다.")
    assert relations.evidence(bridge, rec("r", "은파호수공원")) == {"text"}
    assert relations.evidence(rec("q", "은파호수공원 물빛다리", summary="은파호수공원 물빛다리는 다리입니다."),
                              rec("r", "은파호수공원")) == set()
    assert relations.names_in("옥도면 어청도에 있는 등대", "어청도") and not relations.names_in("옥도면 대장도리에", "대장도")


def test_problems_block_invented_or_broken_relations():
    p = rec("p", "동국사", "전북특별자치도 군산시 동국사길 16(금광동)", (35.98290, 126.70757), "129509")
    c = rec("c", "군산 동국사 대웅전", "전북특별자치도 군산시 동국사길 16 (금광동)", (35.98290, 126.70757), "129509",
            part_of={"id": "p", "rel": "inside", "basis": ["contentid", "address", "geo", "address_name"],
                     "checked_at": "2026-10-16"})
    assert relations.problems([p, c], [p, c]) == []
    # a code the records do not support, an unknown rel, a missing date, a parent outside the build, a loop
    bad = dict(c, part_of={**c["part_of"], "basis": ["homepage"], "rel": "near", "checked_at": ""})
    msgs = [m for _, m in relations.problems([p, bad], [p, bad])]
    assert any("'homepage'가 데이터에서 재현되지 않음" in m for m in msgs)
    assert any("rel 값 오류" in m for m in msgs) and any("checked_at" in m for m in msgs)
    assert any("부모 장소가 이 빌드에 없음" in m for m in (m for _, m in relations.problems([p, c], [c])))
    loop_p = dict(p, part_of={"id": "c", "rel": "inside", "basis": ["contentid"], "checked_at": "2026-10-16"})
    assert any("순환" in m for _, m in relations.problems([loop_p, c], [loop_p, c]))
    # two built pages for one TourAPI content without a relation
    lone = {k: v for k, v in c.items() if k != "part_of"}
    assert any("관계(part_of)가 없음" in m for _, m in relations.problems([p, lone], [p, lone]))


def test_family_rows_and_one_per_building():
    p, c, a, d, x = (rec(i, i.upper()) for i in "pcadx")
    c["part_of"] = {"id": "p", "rel": "inside"}
    a["part_of"] = {"id": "p", "rel": "same_building"}
    d["part_of"] = {"id": "c", "rel": "same_building"}
    built = [p, c, a, d, x]
    assert relations.resolve(built, built) == []
    assert p["_parts"] == [c] and p["_same"] == [a] and a["_alias_of"] is p and c["_parent"] is p
    assert relations.family(p) == {"c", "a", "d"} and relations.family(c) == {"p", "a", "d"}
    assert relations.family(a) == {"p"} and relations.family(x) == set()
    # x's list: the alias goes when its parent is there, each place once, a place without a page stays
    rows = [{"t": a}, {"t": p}, {"t": None}, {"t": p}, {"t": x}]
    assert [r["t"] for r in relations.keep_rows(x, rows, lambda r: r["t"])] == [p, None]
    assert [r["t"] for r in relations.keep_rows(c, rows, lambda r: r["t"])] == [None, x]
    assert relations.one_per_building([p, a, x]) == [p, x] and relations.one_per_building([a, x]) == [a, x]
    fam, alias = relations.raw_family([p, c, a, d, x])
    assert fam["p"] == {"c", "a", "d"} and alias == {"a": "p", "d": "c"}
    # a relation to a place outside the build is dropped with a warning
    lone = rec("k", "K", part_of={"id": "zz", "rel": "inside"})
    assert relations.resolve([lone], [lone]) and lone["_parent"] is None


def test_relation_macro_every_language():
    nb = make_env().get_template("_near.html.j2").module
    for code in ("ko",) + LC.ORDER:
        w = LC.NEAR_WORDS[code]
        h = str(nb.relation([{"rel": "inside", "word": w["part_of"], "places": [{"name": "Alpha", "path": "/a/"}]},
                             {"rel": "same_building", "word": w["same_building"],
                              "places": [{"name": "동국사", "path": "", "ko": True}]}], ", "))
        assert 'data-block="rel-inside"' in h and '<a href="/a/">Alpha</a>' in h and "{name}" not in h
        assert '<span lang="ko">동국사</span>' in h   # no page in that version: the Korean name, no link
        assert bool(HANGUL.search(re.sub(r'<span lang="ko">.*?</span>', "", h))) == (code == "ko")


# ---------------------------------------------------------------- a built site (sample data + relations)
@pytest.fixture(scope="module")
def rel_site(tmp_path_factory):
    tmp = tmp_path_factory.mktemp("rel")
    data = tmp / "data"
    shutil.copytree(SAMPLE, data)
    places = json.loads((data / "places.json").read_text("utf-8"))
    by = {p["id"]: p for p in places}
    addr = "전북특별자치도 군산시 경암동 철길1길 10"
    for pid, lat in (("sample-0001", 35.9870443), ("sample-0002", 35.9870443), ("sample-0003", 35.9872443)):
        by[pid]["facts"]["address"] = addr
        by[pid]["geo"] = {"lat": lat, "lng": 126.7111681, "source": "TourAPI"}
    # 은파 sample (0003) inside the village (0001, 22 m); 초원사진관 sample (0002) the same building as the village
    by["sample-0003"]["part_of"] = {"id": "sample-0001", "rel": "inside", "basis": ["address", "geo"], "checked_at": "2026-10-16"}
    by["sample-0002"]["part_of"] = {"id": "sample-0001", "rel": "same_building", "basis": ["address", "geo"],
                                    "checked_at": "2026-10-16"}
    (data / "places.json").write_text(json.dumps(places, ensure_ascii=False), "utf-8")
    out = tmp / "site"
    build(data, out, "sample")
    return {"data": data, "out": out}


def page(site, slug):
    return (site["out"] / "places" / slug / "index.html").read_text("utf-8")


def test_built_relation_lines_parts_and_family(rel_site):
    village, studio, park = (page(rel_site, s) for s in ("gyeongam-railroad-village", "chowon-photo-studio", "eunpa-lake-park"))
    pv, ps, pp = (PageScan() for _ in range(3))
    pv.feed(village), ps.feed(studio), pp.feed(park)
    assert pp.block_hrefs["rel-inside"] == ["/places/gyeongam-railroad-village/"] and "속한 곳:" in pp.blocks["rel-inside"]
    assert pv.block_hrefs["parts"] == ["/places/eunpa-lake-park/"]
    assert "rel-inside" not in pv.blocks and pv.block_hrefs["rel-same_building"] == ["/places/chowon-photo-studio/"]
    assert ps.block_hrefs["rel-same_building"] == ["/places/gyeongam-railroad-village/"]
    assert "같은 건물: " in ps.blocks["rel-same_building"] and "같은 건물: " in pv.blocks["rel-same_building"]
    # the village's nearby list held the studio (0 m): its own family is gone from the nearby rows, kept as a twin
    assert "/places/chowon-photo-studio/" not in pv.block_hrefs.get("near-rows", [])
    assert "/places/chowon-photo-studio/" in pv.block_hrefs["twins"] and "/places/eunpa-lake-park/" not in pv.block_hrefs.get("near-rows", [])
    assert "이름이 이어진 곳" not in village + studio + park
    node = lambda h: next(n for n in _graph_nodes(PageScan_jsonld(h))[0] if str(n.get("@id", "")).endswith("#place"))  # noqa: E731
    assert node(park)["containedInPlace"][0]["@id"].endswith("/places/gyeongam-railroad-village/#place")
    assert [x["@id"] for x in node(village)["containsPlace"]][0].endswith("/places/eunpa-lake-park/#place")
    assert isinstance(node(studio)["containedInPlace"], dict) and "containsPlace" not in node(studio)
    errors, _, _ = validate(rel_site["data"], rel_site["out"], "sample")
    assert errors == [], errors[:5]


def PageScan_jsonld(html: str) -> list[str]:
    p = PageScan()
    p.feed(html)
    return p.jsonld_raw


def test_validate_catches_a_missing_parent_link_and_a_family_nearby_row(rel_site):
    S = State(rel_site["data"], "sample")
    by = {e["id"]: e for e in S.entities}
    ref = lambda x: (x["_path"], x["_url"])  # noqa: E731
    park = page(rel_site, "eunpa-lake-park")
    broken = park.replace('<a href="/places/gyeongam-railroad-village/">', '<a href="/places/x/">', 1)
    p = PageScan()
    p.feed(broken)
    assert any("속한 곳 줄에" in m for m in relation_page_problems(S, by["sample-0003"], p, None, ref))
    village = page(rel_site, "gyeongam-railroad-village")
    i = village.index('data-block="near-rows"')
    planted = village[:i] + village[i:].replace('<a class="nr-nm" href="', '<a class="nr-nm" href="/places/eunpa-lake-park/" x="', 1)
    p = PageScan()
    p.feed(planted)
    msgs = relation_page_problems(S, by["sample-0001"], p, None, ref)
    assert any("가족" in m for m in msgs), msgs
    p = PageScan()
    p.feed(village.replace('data-block="parts"', 'data-block="parts-x"'))
    assert any("안에 있는 곳 목록에" in m for m in relation_page_problems(S, by["sample-0001"], p, None, ref))
    nodes = _graph_nodes(PageScan_jsonld(village))[0]
    node = next(n for n in nodes if str(n.get("@id", "")).endswith("#place"))
    assert relation_page_problems(S, by["sample-0001"], scan_file(rel_site["out"] / "places" / "gyeongam-railroad-village" / "index.html"), node, ref) == []
    node.pop("containsPlace")
    assert any("containsPlace" in m for m in relation_page_problems(S, by["sample-0001"], PageScan(), node, ref))
