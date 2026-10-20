// The scenario QA of 2026-10-19, second round (docs/qa/2026-10-19_scenario_qa.md 7-4) for the site assistant: what a
// scripted model receives (no network, no key). QA-35: the assistant wrote '(출처: 한국관광공사 TourAPI, 출처 확인
// 2026-10-19)' in 3 of 6 answers nobody asked about dates in — rule 11 says, with an example, that a page's '날짜:' line
// and a value's check date are for the question about them only, and the page text the model reads says the same on
// that line (pipeline/chat_index.py; the built text is checked in tests/test_chat_key_ready.py). Nothing on the screen
// takes text out of an answer (CLAUDE.md 4절). QA-76: a Korean answer wrote '자월도行 배 시간표' — a Korean answer and a
// plan are written in Hangul, Chinese characters only in a name the data writes with them.
import assert from "node:assert/strict";
import test from "node:test";

import { Knowledge, tokens } from "../../chatbot/knowledge.js";
import { rules } from "../../chatbot/prompt.js";
import { buildPlanSystem, useSite } from "../../chatbot/plan_prompt.js";
import { createHandler, createLimiter } from "../../chatbot/server.js";
import { siteFrom } from "../../chatbot/site.js";
import { fakeClient, textRound, toolRound } from "./fake_model.js";

const SITE = "https://test.example.kr";
const SITE_CFG = siteFrom({ url: SITE, name: "테스트각", city: { ko: "테스트", en: "Test" } });
// a place's text as pipeline/chat_index.py writes it (the values and the date line; made-up place)
const DATE_LINE = "날짜: 출처 확인 2026-10-19 · 페이지 검수 전(검수일 없음) — 이용자가 확인 날짜·최신 여부를 물을 때만 답에 씀"
  + "(출처 표기에도 붙이지 않음)";
const DOCS = {
  "/places/가상사찰/": { t: "가상사찰", k: "place",
    x: "가상사찰 — 관광지\n위치: 가상군 가상면 · 가상 권역\n"
      + "정보(값 — 출처, 그 값을 가져온 주소, 출처 확인일 = 이 사이트가 그 출처를 확인한 날 — 아래 '날짜:' 줄의 날과 다를 때만 값 옆에):\n"
      + "- 주차: 가능, 요금 소형 1,000원 — 한국관광공사 TourAPI\n" + DATE_LINE },
};
function indexOf(docs) {
  const out = {};
  for (const [key, d] of Object.entries(docs)) out[key] = [tokens(`${d.t} ${key}`).join(" "), tokens(d.x).join(" ")];
  return { v: 1, docs: out };
}
const kb = () => new Knowledge({ catalog: "# catalog\nP /places/가상사찰/ | 가상사찰 | 관광지 | 가상군·가상면 | 주차 가능, 요금 소형 1,000원",
  docs: { v: 1, site: SITE, docs: DOCS, alias: {}, ext: [], tickets: [] }, index: indexOf(DOCS) });

async function askModel(question, lang = "ko") {
  const client = fakeClient([
    toolRound([["get_pages", { ids: ["/places/가상사찰/"] }]]),
    textRound("가상사찰은 주차할 수 있고 소형 요금은 1,000원입니다(출처: 한국관광공사 TourAPI).\n\n[가상사찰](/places/가상사찰/)"),
  ]);
  const handle = createHandler({ client, knowledge: kb, site: SITE_CFG, log: () => {}, env: {}, limiter: createLimiter(100),
    now: () => new Date("2026-10-19T03:00:00Z") });
  const res = await handle(new Request(`${SITE}/api/chat/`, { method: "POST",
    headers: { "content-type": "application/json", origin: SITE, "x-real-ip": "203.0.113.9" },
    body: JSON.stringify({ messages: [{ role: "user", content: question }], lang, page: "/" }) }));
  await res.text();
  return client.calls;
}

test("QA-35: the rules keep a check date for the question about it, with an example; the page line the model reads says so", async () => {
  const calls = await askModel("가상사찰 주차 돼?");
  const [cached, context] = calls[0].params.system;
  const r11 = cached.text.split("\n").find((l) => l.startsWith("11. "));
  for (const words of [
    "Mention the source check date or the page review only when the reader asks how current or checked the information is",
    "A page's '날짜:' line and a check date next to a value are there for that question only",
    "out of the sentences, the bullet points and the source notes alike",
    // the example: the source note without the date, and the two forms the QA saw
    "write \"주차 요금: 소형 ○원 (출처: 한국관광공사 TourAPI)\"",
    "never \"(출처: 한국관광공사 TourAPI, 출처 확인 2026-10-19)\" or a line \"출처 확인일 2026-10-19\"",
  ]) assert.ok(r11.includes(words), words);
  // a timetable keeps its dates (rule 12 unchanged)
  assert.ok(cached.text.includes("the timetable's effective date (in a Korean answer 시행일) with the date this site checked it"));
  // the example names no value of a real place
  assert.doesNotMatch(r11, /\d,\d{3}원/);
  // the page text the model reads: the date line says what it is for, the values carry no date of the same day
  const read = calls[1].params.messages.at(-1).content[0].content;
  assert.ok(read.includes(DATE_LINE), read);
  assert.ok(read.includes("- 주차: 가능, 요금 소형 1,000원 — 한국관광공사 TourAPI\n"), read);
  assert.ok(!context.text.includes("출처 확인"), "the per-request context names no check date");
});

test("QA-76: a Korean answer and a plan are written in Hangul — Chinese characters only in a name the data writes so", async () => {
  const r4 = rules(SITE_CFG).split("\n").find((l) => l.startsWith("4. "));
  assert.ok(r4.includes("A Korean answer is written in Hangul: never Hanja (Chinese characters) for a Korean word or ending"), r4);
  assert.ok(r4.includes("a destination is \"공항행 버스\", the syllable 행 written in Hangul, never as its Chinese character"), r4);
  // review 2026-10-20: the rule's own wrong example ('공항行 버스 시간표') was the only '○○行 … 시간표' the model read, and an
  // answer wrote '자월도行 배 시간표' again — the error is described in words, its character never shown
  assert.doesNotMatch(rules(SITE_CFG), /行/);
  assert.ok(r4.includes("Chinese characters only inside a name exactly as the data writes it"), r4);
  // the rules name no place of a city (the engine is the same for every city)
  assert.doesNotMatch(rules(SITE_CFG), /자월도/);
  // the per-request context of a Korean question says it again; an English or a Japanese one does not
  const ko = (await askModel("가상사찰 주차 돼?"))[0].params.system[1].text;
  assert.match(ko, /write the whole answer in Korean \(한국어\), [^\n]* Write it in Hangul: no Hanja outside a name the data writes with them \(rule 4\)\./);
  for (const [q, lang] of [["Is there parking at 가상사찰?", "en"], ["가상사찰に駐車場はありますか？", "ja"]]) {
    const other = (await askModel(q, lang))[0].params.system[1].text;
    assert.doesNotMatch(other, /Hanja/, q);
  }
  // the course planner's plan (all Korean) too
  useSite(SITE_CFG);
  const plan = buildPlanSystem("# catalog", new Date("2026-10-19T03:00:00Z"));
  assert.match(plan[1].text, /Write every word of the plan in Korean, in Hangul: no Hanja \(Chinese characters\) outside a name the page writes with them\./);
});

test("review 2026-10-20: the planner's own words claim no 권역 or walking the stops contradict", () => {
  // a Saturday plan with '점심은 경방식당에서' said '모든 장소가 개항장·월미 권역 안에서 걸어서 이어집니다' while that stop was in
  // 도심·소래 and its legs 5.6 km and 6.9 km by transit
  useSite(SITE_CFG);
  const r4 = buildPlanSystem("# catalog", new Date("2026-10-19T03:00:00Z"))[0].text.split("\n").find((l) => l.startsWith("4. "));
  assert.ok(r4.includes("name a 권역 only when every stop the sentence speaks of is in that 권역 by its catalog line"), r4);
  assert.ok(r4.includes("never say how the stops connect (걸어서, 도보로, 가까이 이어진다, 이동이 짧다)"), r4);
});
