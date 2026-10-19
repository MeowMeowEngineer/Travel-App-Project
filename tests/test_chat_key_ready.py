"""The site assistant is key-ready on this site's own configuration (data/incheon/site.json) with the clearly fake
tiny dataset (tests/fixtures/incheon_tiny — never data/incheon, never published): the build writes the knowledge the
function answers from (pipeline/chat_index.py → <out>/chat/: site.json, catalog.txt, docs.json, index.json) with each
fact's source and check date and nothing of another city; the launcher offers the Korean site search only where the
build has one; and the function itself (chatbot/*.js, under Node) reads that very output — no key: 503 not_configured;
with ANTHROPIC_API_KEY set and nothing else changed: a scripted model's question is answered with the built page as a
checked link. No network, no key."""
import json
import os
import re
import shutil
import subprocess
from pathlib import Path

import pytest

from pipeline.build import build

ROOT = Path(__file__).resolve().parent.parent
INCHEON = ROOT / "data" / "incheon"
# the files a collection or a writer adds to data/incheon (TourAPI writes places·events): left out of a copy that
# stands for this site's configuration before collection
RECORDS = ("places.json", "events.json", "courses.json", "guides.json", "themes.json", "videos.json")
TINY = Path(__file__).resolve().parent / "fixtures" / "incheon_tiny"
SITE = "https://incheon.webforai.kr"   # site_url (operator 2026-10-19)
NODE = shutil.which("node")
# the sample city's names in every script the engine has used (tests/test_city.py FOREIGN)
FOREIGN = re.compile(r"군산|gunsan|Gunsan|GUNSAN|群山|Кунсан|선유도|Seonyudo|고군산")
PLACES = {f"/places/{s}/" for s in ("test-beach-a", "test-food-b", "test-stay-c", "test-park-d", "test-market-e",
                                    "test-cafe-f", "test-shop-g")}


def _data(tmp_path: Path, fixture: bool = True) -> Path:
    data = tmp_path / "data"
    data.mkdir()
    for f in INCHEON.glob("*.json"):
        if f.name not in RECORDS:
            shutil.copy(f, data / f.name)
    if fixture:
        for f in TINY.glob("*.json"):
            shutil.copy(f, data / f.name)
    return data


@pytest.fixture(scope="module")
def built(tmp_path_factory):
    tmp = tmp_path_factory.mktemp("chatready")
    data = _data(tmp)
    out = tmp / "out"
    stats = build(data, out, "preview")
    return {"data": data, "out": out, "stats": stats, "chat": out / "chat"}


def test_the_build_writes_this_site_s_knowledge_with_sources_and_no_other_city(built):
    chat = built["chat"]
    assert sorted(p.name for p in chat.iterdir()) == ["catalog.txt", "docs.json", "index.json", "site.json"]
    assert json.loads((chat / "site.json").read_text("utf-8")) == {
        "url": SITE, "name": "인천각", "city": {"ko": "인천", "en": "Incheon"}, "origins": [], "hubs": {}}
    catalog = (chat / "catalog.txt").read_text("utf-8")
    assert catalog.startswith(f"# Site catalog of 인천각 ({SITE}).")
    lines = {line.split(" | ")[0][2:]: line for line in catalog.splitlines() if line.startswith("P ")}
    assert set(lines) == PLACES and built["stats"]["chat"]["places"] == 7
    assert "주차 [테스트] 주차 값" in lines["/places/test-beach-a/"]               # the first screen's key facts
    assert "메뉴 [테스트] 메뉴 값" in lines["/places/test-food-b/"]
    assert "정정 요청 ," not in catalog                                           # no contact yet: not named at all
    docs = json.loads((chat / "docs.json").read_text("utf-8"))
    assert docs["site"] == SITE and PLACES <= set(docs["docs"])
    beach = docs["docs"]["/places/test-beach-a/"]["x"]
    # every fact with its provider, and the date this site checked it once, on the record's 날짜 line (a fact line
    # names its date only when it differs — QA 2026-10-19 QA-35); what the site lacks, said once
    assert "- 이용시간: [테스트] 이용시간 값 — 한국관광공사 TourAPI\n" in beach
    assert "- 주차: [테스트] 주차 값 — 한국관광공사 TourAPI\n" in beach
    assert "\n날짜: 출처 확인 2026-10-19 · " in beach and "(출처 확인 2026-10-19)" not in beach
    assert "사이트에 없는 값(확인 필요): 쉬는 날·요금·전화" in beach
    about = docs["docs"]["/about/"]["x"]
    assert "Claude Haiku 5.5" in about and "대화를 저장하지 않고" in about and "인천각" in about
    for f in chat.iterdir():
        hit = FOREIGN.search(f.read_text("utf-8"))
        assert not hit, f"{f.name}: {hit and hit.group(0)}"
    index = json.loads((chat / "index.json").read_text("utf-8"))
    assert "해변" in index["docs"]["/places/test-beach-a/"][0].split()          # the name finds its page


def test_the_knowledge_is_the_same_bytes_when_built_again(built, tmp_path):
    again = tmp_path / "again"
    build(built["data"], again, "preview")
    for name in ("catalog.txt", "docs.json", "index.json", "site.json"):
        assert (again / "chat" / name).read_bytes() == (built["chat"] / name).read_bytes(), name


def test_the_launcher_offers_the_search_only_where_the_build_has_one(built, tmp_path):
    out = built["out"]
    assert (out / "search" / "index.html").exists()
    for page in ("index.html", "places/index.html", "places/test-beach-a/index.html", "about/index.html"):
        html = (out / page).read_text("utf-8")
        assert f'data-chat-site="{SITE}" data-chat-search="/search/"' in html, page
    home = (out / "index.html").read_text("utf-8")
    assert '<p class="hk-sub" data-ask-line>' in home                           # the card's line chat.js may rest
    empty = tmp_path / "empty"
    build(_data(tmp_path, fixture=False), empty, "preview")                     # before collection: no search page
    assert not (empty / "search").exists()
    pages = [p for p in empty.rglob("*.html") if 'class="chat-fab"' in p.read_text("utf-8")]
    assert pages and all('data-chat-search=""' in p.read_text("utf-8") for p in pages)


E2E = r"""
import { loadKnowledge } from "./chatbot/knowledge.js";
import { loadSite } from "./chatbot/site.js";
import { createHandler } from "./chatbot/server.js";
import { fakeClient, sseEvents, textRound, toolRound } from "./tests/js/fake_model.js";

const dir = process.env.CHAT_DIR;
const site = loadSite(dir);
const knowledge = () => loadKnowledge(dir);
const status = (h) => h(new Request(`${site.url}/api/chat/`, { method: "GET" }));
const ask = (h) => h(new Request(`${site.url}/api/chat/`, { method: "POST",
  headers: { origin: site.url, "content-type": "application/json", "x-real-ip": "203.0.113.5" },
  body: JSON.stringify({ messages: [{ role: "user", content: "가상 해변 A 주차 돼?" }], lang: "ko", page: "/places/test-beach-a/" }) }));
const out = { site };

const off = createHandler({ env: {}, site, knowledge, log: () => {} });
let r = await status(off);
out.off = { status: r.status, body: await r.json() };
r = await ask(off);
out.offAsk = { status: r.status, body: await r.json() };

const client = fakeClient([
  toolRound([["search_site", { query: "가상 해변 주차" }]]),
  toolRound([["get_pages", { ids: ["/places/test-beach-a/"] }]]),
  textRound("네, [테스트] 주차 값입니다(한국관광공사 TourAPI).\n\n[가상 해변 A](/places/test-beach-a/)"),
]);
const made = [];
const on = createHandler({ env: { ANTHROPIC_API_KEY: "sk-ant-test-not-a-real-key" }, site, knowledge, log: () => {},
  makeClient: async (key) => { made.push(key); return client; } });
r = await status(on);
out.on = { status: r.status, body: await r.json() };
out.events = await sseEvents(await ask(on));
out.made = made;
out.system = client.calls[0].params.system[0].text.slice(0, 200);
out.search = client.calls[1].params.messages.at(-1).content[0].content;
out.read = client.calls[2].params.messages.at(-1).content[0].content;
console.log(JSON.stringify(out));
"""


@pytest.mark.skipif(NODE is None, reason="Node.js is not installed")
def test_the_function_answers_from_the_built_knowledge_once_a_key_is_set(built):
    env = {k: v for k, v in os.environ.items() if k not in ("ANTHROPIC_API_KEY", "ANTHROPIC_AUTH_TOKEN", "CHAT_KB_DIR")}
    env["CHAT_DIR"] = str(built["chat"])
    r = subprocess.run([NODE, "--input-type=module", "-e", E2E], cwd=ROOT, env=env, capture_output=True, text=True,
                       encoding="utf-8", timeout=120)
    assert r.returncode == 0, r.stderr[-3000:]
    out = json.loads(r.stdout.strip().splitlines()[-1])
    assert out["site"]["url"] == SITE and out["site"]["city"] == {"ko": "인천", "en": "Incheon"}
    # no key: the status and a question both say not_configured
    assert out["off"] == {"status": 503, "body": {"ready": False, "code": "not_configured",
                                                  "message": "The site assistant is not set up yet."}}
    assert out["offAsk"]["status"] == 503 and out["offAsk"]["body"]["code"] == "not_configured"
    # the key set, nothing else changed: ready, and the answer comes from the built pages with a checked link
    assert out["on"] == {"status": 200, "body": {"ready": True}}
    assert out["made"] == ["sk-ant-test-not-a-real-key"]
    assert out["system"].startswith(f"You are 인천 여행 도우미 (the Incheon travel helper), the assistant of the travel "
                                    f"website 인천각 ({SITE})")
    assert "/places/test-beach-a/" in out["search"].split("\n")[1]              # search_site found the built page first
    assert "- 주차: [테스트] 주차 값 — 한국관광공사 TourAPI" in out["read"] and "날짜: 출처 확인 2026-10-19" in out["read"]
    done = out["events"][-1]
    assert done["type"] == "done"
    assert done["links"] == [{"title": "[테스트] 가상 해변 A", "url": f"{SITE}/places/test-beach-a/", "ext": False}]
    text = "".join(e["delta"] for e in out["events"] if e["type"] == "text")
    assert text.startswith("네, [테스트] 주차 값입니다") and text.endswith("[가상 해변 A](/places/test-beach-a/)")
