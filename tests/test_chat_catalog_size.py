"""The assistant's catalog after the operator's decision of 2026-10-20 (docs/qa/2026-10-19_scenario_qa.md 9-5, B + D + H),
on this site's configuration (data/incheon/site.json) with the fake tiny dataset (tests/fixtures/incheon_tiny, its food
place given hours, a closed day, parking and a phone in a temporary copy):

  B  a food or café line keeps the name, path, type, 구·군 and menu — its hours, closed days, parking and phone stay
     on the page (docs.json), which get_pages reads;
  D  shops and markets have no line; their section head stays and says search_site finds them — the search tool does,
     and get_pages reads the shop's page;
  H  a place line's location is its 구·군 alone, and one head line gives each 구·군's 권역 (a 구·군 split between 권역
     names its 권역 on the line);

docs.json and the search index keep every place whole, and the build and validate warn — never fail — when the
catalog's estimate passes chat_index.CATALOG_BUDGET. The model is a scripted fake (tests/js/fake_model.js): no network,
no key."""
import json
import os
import re
import shutil
import subprocess
from pathlib import Path

import pytest

from pipeline import chat_index
from pipeline.build import build
from pipeline.validate import validate

ROOT = Path(__file__).resolve().parent.parent
INCHEON = ROOT / "data" / "incheon"
TINY = Path(__file__).resolve().parent / "fixtures" / "incheon_tiny"
RECORDS = ("places.json", "events.json", "courses.json", "guides.json", "themes.json", "videos.json")
SITE = "https://incheon.webforai.kr"
NODE = shutil.which("node")
SRC = {"provider": "한국관광공사 TourAPI", "checked_at": "2026-10-19", "contentid": ""}
# the food place's visit facts (made up, test only): none of them may reach its catalog line
FOOD_FACTS = {"usetime": "11:00–21:00", "restdate": "매주 월요일", "parking": "가능", "infocenter": "032-000-1111"}


def _data(tmp: Path) -> Path:
    data = tmp / "data"
    data.mkdir()
    for f in INCHEON.glob("*.json"):
        if f.name not in RECORDS:
            shutil.copy(f, data / f.name)
    for f in TINY.glob("*.json"):
        shutil.copy(f, data / f.name)
    places = json.loads((data / "places.json").read_text("utf-8"))
    food = next(p for p in places if p["slug"] == "test-food-b")
    food["facts"].update(FOOD_FACTS)
    food["fact_sources"].update({k: dict(SRC) for k in FOOD_FACTS})
    (data / "places.json").write_text(json.dumps(places, ensure_ascii=False, indent=1), "utf-8")
    return data


@pytest.fixture(scope="module")
def built(tmp_path_factory):
    tmp = tmp_path_factory.mktemp("catalogsize")
    data = _data(tmp)
    out = tmp / "out"
    stats = build(data, out, "preview")
    chat = out / "chat"
    catalog = (chat / "catalog.txt").read_text("utf-8")
    return {"data": data, "out": out, "stats": stats, "chat": chat, "catalog": catalog,
            "lines": {ln.split(" | ")[0][2:]: ln for ln in catalog.splitlines() if ln.startswith("P ")},
            "docs": json.loads((chat / "docs.json").read_text("utf-8"))["docs"],
            "index": json.loads((chat / "index.json").read_text("utf-8"))["docs"]}


def test_b_food_and_cafe_lines_keep_only_name_path_type_district_and_menu(built):
    lines, docs = built["lines"], built["docs"]
    assert lines["/places/test-food-b/"] == "P /places/test-food-b/ | [테스트] 가상 식당 B | 음식점 | 연수구 | 메뉴 [테스트] 메뉴 값"
    assert lines["/places/test-cafe-f/"] == "P /places/test-cafe-f/ | [테스트] 가상 카페 F | 카페·디저트 | 미추홀구 | 메뉴 [테스트] 메뉴 값"
    # the values the line leaves out are on the page get_pages reads, with their source
    food = docs["/places/test-food-b/"]["x"]
    for value in FOOD_FACTS.values():
        assert value in food, value
        assert value not in built["catalog"], value
    assert re.search(r"^- [^:\n]+: 032-000-1111 — 한국관광공사 TourAPI$", food, re.M), food
    assert "[테스트] 영업시간 값" in docs["/places/test-cafe-f/"]["x"] and "영업시간 값" not in lines["/places/test-cafe-f/"]
    # the other kinds keep their first-screen key facts
    assert lines["/places/test-beach-a/"].endswith(" | 시간 이용시간 값; 주차 [테스트] 주차 값")
    assert "체크인 15:00" in lines["/places/test-stay-c/"]
    # the head tells the model so, and where to read them
    head = next(ln for ln in built["catalog"].splitlines() if ln.startswith("# Place lines"))
    assert "lines carry only 메뉴 (signature dishes): their hours, closed days, parking and phone are on the page — read " \
           "it with get_pages before stating them." in head


def test_d_shops_have_no_lines_but_their_pages_stay_in_the_knowledge(built):
    catalog, docs = built["catalog"], built["docs"]
    assert "/places/test-shop-g/" not in catalog and "가상 상점 G" not in catalog
    assert re.search(r"^## 쇼핑 1곳 — 목록 /shopping/ \(장소 줄 없음 — search_site로 이름·브랜드·구·군·시장 이름을 찾는다\)\n\n",
                     catalog, re.M)
    assert catalog.startswith(f"# Site catalog of 인천각 ({SITE}). One line = one page of this site (shops and markets "
                              "excepted: search_site).")
    shop = docs["/places/test-shop-g/"]
    assert shop["k"] == "place" and "[테스트] 영업시간 값" in shop["x"] and "[테스트] 주차 값" in shop["x"]
    assert "상점" in built["index"]["/places/test-shop-g/"][0].split()
    stats = built["stats"]["chat"]
    assert (stats["places"], stats["place_lines"]) == (7, 6)
    assert set(built["lines"]) == {f"/places/{s}/" for s in ("test-beach-a", "test-food-b", "test-stay-c", "test-park-d",
                                                             "test-market-e", "test-cafe-f")}


def test_h_a_line_names_its_district_and_one_head_line_gives_each_district_its_region(built):
    catalog, docs = built["catalog"], built["docs"]
    heads = [ln for ln in catalog.splitlines() if ln.startswith("# 권역 ")]
    assert heads == ["# 권역 (travel region) of each 구·군: 개항장·월미 = 제물포구; 송도·연수 = 연수구; 강화 = 강화군; "
                     "도심·소래 = 미추홀구"]
    region_of = {d: r for r, ds in (g.split(" = ") for g in heads[0].split(": ", 1)[1].split("; ")) for d in ds.split("·")}
    site = json.loads((INCHEON / "site.json").read_text("utf-8"))
    districts = {*site["districts"], *site["districts_former"]}
    seen = {}
    for path, line in built["lines"].items():
        where = line.split(" | ")[3]
        seen[path] = where
        place = docs[path]["x"]
        pos = next(x for x in place.split("\n") if x.startswith("위치: "))
        m = re.fullmatch(r"(\S+) \((.+) 권역\)", where)
        if m:   # a 구·군 split between 권역 (old 중구 by its 법정동): the line names the place's own
            assert m.group(1) in districts and m.group(1) not in region_of and f"{m.group(2)} 권역" in pos, (where, pos)
            continue
        assert where in districts, where                                        # no 동, road or address
        if where in region_of:                                                  # the head's 권역 is the page's
            assert pos.endswith(f" · {region_of[where]} 권역"), (where, pos)
        else:                                                                   # 권역 미정: none on the page either
            assert " 권역" not in pos, pos
    assert seen["/places/test-food-b/"] == "연수구" and seen["/places/test-beach-a/"] == "중구 (영종·용유 권역)"
    assert seen["/places/test-park-d/"] == "중구" and seen["/places/test-market-e/"] == "제물포구"
    # the address detail the old lines carried ('테스트대로') is on the page only
    assert "테스트대로" not in catalog and "테스트대로" in docs["/places/test-food-b/"]["x"]


def test_the_build_and_validate_warn_above_the_design_budget_and_do_not_fail(built, tmp_path, monkeypatch, capsys):
    assert chat_index.CATALOG_BUDGET == 72_000
    assert chat_index.budget_warning(72_000) == ""
    over = chat_index.budget_warning(72_001)
    assert over.startswith("도우미 카탈로그(chat/catalog.txt) 추정 72,001토큰 — 설계 예산 72,000토큰보다 1 많음")
    est = built["stats"]["chat"]["catalog_tokens_est"]
    assert built["stats"]["chat"]["catalog_budget"] == 72_000 and 0 < est < 72_000
    assert est == chat_index.estimate_tokens(built["catalog"])
    errors, warns, stats = validate(built["data"], built["out"], "preview")
    assert stats["catalog_tokens_est"] == est and not any("chat/catalog.txt" in w for w in warns)
    # the same data over a (lowered) budget: the build prints the warning and finishes, validate lists it as a warning
    monkeypatch.setattr(chat_index, "CATALOG_BUDGET", est - 1)
    capsys.readouterr()
    stats2 = build(built["data"], tmp_path / "out", "preview")
    err = capsys.readouterr().err
    assert f"경고: 도우미 카탈로그(chat/catalog.txt) 추정 {est:,}토큰 — 설계 예산 {est - 1:,}토큰보다 1 많음" in err, err
    assert stats2["chat"]["catalog_tokens_est"] == est and (tmp_path / "out" / "chat" / "catalog.txt").exists()
    errors2, warns2, _ = validate(built["data"], tmp_path / "out", "preview")
    assert [w for w in warns2 if w.startswith("[chat/catalog.txt] ")] == [f"[chat/catalog.txt] {chat_index.budget_warning(est)}"]
    assert errors2 == errors                                                    # a warning only: no new error


E2E = r"""
import { loadKnowledge } from "./chatbot/knowledge.js";
import { loadSite } from "./chatbot/site.js";
import { createHandler } from "./chatbot/server.js";
import { fakeClient, sseEvents, textRound, toolRound } from "./tests/js/fake_model.js";

const dir = process.env.CHAT_DIR;
const site = loadSite(dir);
const knowledge = () => loadKnowledge(dir);
const ask = (h, q, page) => h(new Request(`${site.url}/api/chat/`, { method: "POST",
  headers: { origin: site.url, "content-type": "application/json", "x-real-ip": "203.0.113.5" },
  body: JSON.stringify({ messages: [{ role: "user", content: q }], lang: "ko", page }) }));
const run = async (rounds, q, page) => {
  const client = fakeClient(rounds);
  const h = createHandler({ env: { ANTHROPIC_API_KEY: "sk-ant-test-not-a-real-key" }, site, knowledge, log: () => {},
    makeClient: async () => client });
  const events = await sseEvents(await ask(h, q, page));
  return { client, events };
};
const out = {};
// D: a shop the catalog does not list — search_site finds it, get_pages reads it, the answer links it
let r = await run([
  toolRound([["search_site", { query: "가상 상점 G" }]]),
  toolRound([["get_pages", { ids: ["/places/test-shop-g/"] }]]),
  textRound("영업시간은 [테스트] 영업시간 값입니다(한국관광공사 TourAPI).\n\n[가상 상점 G](/places/test-shop-g/)"),
], "가상 상점 G 몇 시에 열어?", "/shopping/");
out.shop = { system: r.client.calls[0].params.system[0].text, search: r.client.calls[1].params.messages.at(-1).content[0].content,
  read: r.client.calls[2].params.messages.at(-1).content[0].content, done: r.events.at(-1) };
// B: a restaurant's hours — not in its line; the page has them
r = await run([
  toolRound([["get_pages", { ids: ["/places/test-food-b/"] }]]),
  textRound("11:00–21:00에 열고 매주 월요일에 쉽니다(한국관광공사 TourAPI).\n\n[가상 식당 B](/places/test-food-b/)"),
], "가상 식당 B 몇 시까지 해?", "/food/");
out.food = { read: r.client.calls[1].params.messages.at(-1).content[0].content, done: r.events.at(-1) };
console.log(JSON.stringify(out));
"""


@pytest.mark.skipif(NODE is None, reason="Node.js is not installed")
def test_the_fake_model_finds_a_shop_with_search_and_reads_a_restaurants_hours_from_its_page(built):
    env = {k: v for k, v in os.environ.items() if k not in ("ANTHROPIC_API_KEY", "ANTHROPIC_AUTH_TOKEN", "CHAT_KB_DIR")}
    env["CHAT_DIR"] = str(built["chat"])
    r = subprocess.run([NODE, "--input-type=module", "-e", E2E], cwd=ROOT, env=env, capture_output=True, text=True,
                       encoding="utf-8", timeout=120)
    assert r.returncode == 0, r.stderr[-3000:]
    out = json.loads(r.stdout.strip().splitlines()[-1])
    shop = out["shop"]
    rules, catalog = shop["system"].split("\n\n<site_data source=\"catalog\">\n", 1)
    # the cached prefix: the rules say how to read the short catalog, and the catalog has no shop line
    assert "food and café lines give only the menu — read the page before you state their hours, closed days, parking " \
           "or phone; shops and markets have no lines — find them with search_site" in rules
    assert "the catalog's 권역 line gives each one's 권역" in rules
    assert catalog.startswith("# Site catalog of 인천각") and "/places/test-shop-g/" not in catalog
    assert "## 쇼핑 1곳 — 목록 /shopping/ (장소 줄 없음" in catalog
    assert "032-000-1111" not in catalog and "P /places/test-food-b/ | [테스트] 가상 식당 B | 음식점 | 연수구 | 메뉴 [테스트] 메뉴 값\n" in catalog
    # the search tool finds the shop first, and its page has the hours and parking the catalog left out
    assert "/places/test-shop-g/" in shop["search"].split("\n")[1], shop["search"]
    assert "[테스트] 영업시간 값" in shop["read"] and "[테스트] 주차 값" in shop["read"]
    assert shop["done"]["type"] == "done"
    assert shop["done"]["links"] == [{"title": "[테스트] 가상 상점 G", "url": f"{SITE}/places/test-shop-g/", "ext": False}]
    food = out["food"]
    assert all(v in food["read"] for v in FOOD_FACTS.values()), food["read"]
    assert food["done"]["links"] == [{"title": "[테스트] 가상 식당 B", "url": f"{SITE}/places/test-food-b/", "ext": False}]
