// The scenario QA of 2026-10-19 (QA lead's merged list, 'fix now' items) for the course planner and the assistant's
// knowledge: made-up places on a small knowledge base (no network, no model). QA-01 lunch with no restaurant data,
// QA-09 islands, QA-10 edits in words, QA-30 fees in the reader's words, QA-31 directions and hours notes.
import assert from "node:assert/strict";
import test from "node:test";

import { Knowledge, tokens } from "../../chatbot/knowledge.js";
import { planFees } from "../../chatbot/plan_fees.js";
import { useSite } from "../../chatbot/plan_prompt.js";
import { eatsElsewhere } from "../../chatbot/plan_state.js";
import { SEA_M, onIsland, stayRadii } from "../../chatbot/plan_geo.js";
import { align, askedLines, directionsUrl, namedIn, preflight, seaLegs, validConditions, withEditNeeds } from "../../chatbot/planner.js";
import { siteFrom } from "../../chatbot/site.js";

const SITE = "https://test.example.kr";
useSite(siteFrom({ url: SITE, name: "테스트각", city: { ko: "테스트", en: "Test" } }));
const NOW = new Date("2026-10-17T01:00:00Z");

function indexOf(docs) {
  const out = {};
  for (const [key, d] of Object.entries(docs)) out[key] = [tokens(`${d.t} ${key}`).join(" "), tokens(d.x).join(" ")];
  return { v: 1, docs: out };
}
const kbOf = (docs) => new Knowledge({ catalog: "# catalog", docs: { v: 1, site: SITE, docs, alias: {}, ext: [], tickets: [] }, index: indexOf(docs) });
const place = (name, region, f, ty = "박물관·전시") => [`/places/${name}/`, { t: name, k: "place",
  x: `${name} — 관광지 · ${ty}\n위치: 가상동 · ${region} 권역`, f: { kd: "attraction", ty, ...f } }];

// eight museums a few hundred metres apart, open every day 09:00–18:00, and no restaurant at all
const TOWN = Object.fromEntries([...Array(8).keys()].map((i) => place(`가상박물관${i + 1}`, "원도심",
  { g: [37.45 + i * 0.001, 126.60 + i * 0.001], c: [{ p: "한국관광공사 TourAPI", t: "연중무휴" }], h: [{ p: "한국관광공사 TourAPI", t: "09:00~18:00" }] })));

test("QA-01: lunch left out in the reader's own words — 알아서, 도시락, 챙겨, a longer sentence", () => {
  for (const t of ["점심은 알아서 먹을게요", "도시락 싸 가요", "점심 식당은 일정에서 빼 주세요", "점심은 도시락으로 해결할게요"]) {
    assert.equal(eatsElsewhere("lunch", t), true, t);
  }
  for (const t of ["점심은 알아서 골라 주세요", "점심 꼭 챙겨 주세요", "빼놓을 수 없는 점심", "아이 간식 챙겨 갈게요"]) {
    assert.equal(eatsElsewhere("lunch", t), false, t);
  }
  assert.equal(eatsElsewhere("dinner", "도시락 싸 가요"), false);
  assert.equal(eatsElsewhere("dinner", "저녁 도시락 싸 가요"), true);
});

test("QA-01: no restaurant in the data — the cause is the data, and '점심 빼고 짜기' leaves the lunch out", () => {
  const kb = kbOf(TOWN);
  const c = validConditions({ date: "2026-10-19", days: 1, start: "10:00", end: "18:00", move: "car", with: "couple", adults: 2,
    kids: [], prefs: [], needs: [], budget: null }, NOW);
  const problems = preflight(c, kb, NOW, null, { today: "2026-10-17" });
  assert.ok(problems.length, "refused");
  assert.equal(problems[0].field, "note");
  assert.match(problems[0].text, /음식점 이용시간 자료가 아직 없어 점심을 넣을 수 없어요\.$/);
  const fix = problems[0].fixes[0];
  assert.equal(fix.label, "점심 빼고 짜기");
  assert.ok(eatsElsewhere("lunch", fix.set.note));
  assert.deepEqual(preflight({ ...c, ...fix.set }, kb, NOW, null, { today: "2026-10-17" }), []);   // the fix makes a plan
});

test("QA-31: directions on foot under 500 m whatever the way the reader moves", () => {
  const a = { name: "가", lat: 37.45, lng: 126.6 }, b = { name: "나", lat: 37.45007, lng: 126.6 };
  assert.equal(directionsUrl(a, b, "car", 8).mode, "walk");
  assert.equal(directionsUrl(a, b, "car", 2000).mode, "car");
  assert.equal(directionsUrl(a, b, "transit", 900).mode, "walk");
  assert.equal(directionsUrl(a, b, "transit", 3000).mode, "traffic");
});

test("QA-31: an hours value without a time is the site's word, not '이용시간이 사이트에 없음'", () => {
  const docs = Object.fromEntries([place("가상체육공원", "원도심", { g: [37.5, 126.6], c: [{ p: "한국관광공사 TourAPI", t: "연중무휴" }],
    h: [{ p: "한국관광공사 TourAPI", t: "※ 시설별 상이하므로 홈페이지 참고" }] }), place("가상해변", "원도심",
    { g: [37.51, 126.6], c: [{ p: "한국관광공사 TourAPI", t: "연중무휴" }], h: [{ p: "한국관광공사 TourAPI", t: "상시 개방" }] }, "자연·야외")]);
  const r = kbOf(docs).checkPlan({ date: "2026-10-19", stops: [{ page: "/places/가상체육공원/", start: "10:00", end: "11:00" },
    { page: "/places/가상해변/", start: "11:30", end: "12:00" }] });
  assert.ok(!r.stops[0].checks.some((x) => /사이트에 없음/.test(x)), r.stops[0].checks.join(" / "));
  assert.ok(r.stops[0].checks.some((x) => x.includes("이용시간은 '시설별 상이하므로 홈페이지 참고'")), r.stops[0].checks.join(" / "));
  assert.deepEqual(r.stops[1].checks, []);   // '상시 개방' says it is always open: nothing to add
});

test("QA-09: on the islands a long leg may cross the sea — said, and a stay is never looked for without limit", () => {
  const docs = Object.fromEntries([
    place("가상섬마을", "가상 섬", { g: [37.25, 126.4], c: [{ p: "T", t: "연중무휴" }], h: [{ p: "T", t: "09:00~18:00" }] }),
    place("가상섬해변", "가상 섬", { g: [37.252, 126.402], c: [{ p: "T", t: "연중무휴" }], h: [{ p: "T", t: "09:00~18:00" }] }),
    place("다른섬산", "가상 섬", { g: [37.3, 126.45], c: [{ p: "T", t: "연중무휴" }], h: [{ p: "T", t: "09:00~18:00" }] }),
    place("뭍박물관", "원도심", { g: [37.45, 126.6], c: [{ p: "T", t: "연중무휴" }], h: [{ p: "T", t: "09:00~18:00" }] })]);
  const kb = kbOf(docs);
  assert.equal(onIsland(docs["/places/가상섬마을/"]), true);
  assert.equal(onIsland(docs["/places/뭍박물관/"]), false);
  assert.ok(!stayRadii(docs["/places/가상섬마을/"]).includes(Infinity) && stayRadii(docs["/places/가상섬마을/"])[0] === SEA_M);
  assert.ok(stayRadii(docs["/places/뭍박물관/"]).includes(Infinity));
  const st = (name) => ({ page: `/places/${name}/`, name, role: "visit" });
  const plan = { days: [{ date: "2026-10-24", stops: [st("가상섬마을"), st("가상섬해변"), st("다른섬산")] }] };
  const sea = seaLegs(plan, kb);
  assert.deepEqual([...sea.legs], ["0|1"]);   // 가상섬해변 → 다른섬산 (about 7 km); the 280 m leg is a walk
  assert.match(sea.aware[0].t, /^가상섬해변 → 다른섬산\(직선 [\d.]+km\): 배로 건너야 할 수 있음 — 배편은 사이트에 없음$/);
});

test("QA-10: an edit names a place it could not put in — the data's reason, and the AI's sentence that says so stays", () => {
  const docs = { ...TOWN, ...Object.fromEntries([place("가상도서관", "원도심", { g: [37.451, 126.601],
    c: [{ p: "한국관광공사 TourAPI", t: "매주 토요일~일요일" }], h: [{ p: "한국관광공사 TourAPI", t: "09:00~17:00" }] })]) };
  const kb = kbOf(docs);
  const asked = namedIn("가상도서관도 꼭 넣어 주세요", kb);
  assert.deepEqual([...asked], ["/places/가상도서관/"]);
  const plan = { title: "토요일 코스", summary: "가상도서관은 토요일 휴관이라 넣지 않았습니다. 박물관을 돕니다.", notes: [],
    days: [{ date: "2026-10-24", stops: [{ page: "/places/가상박물관1/", name: "가상박물관1", start: "10:00", end: "11:00", role: "visit", why: "" }] }] };
  assert.deepEqual(askedLines(plan, kb, asked), ["요청: 가상도서관은 그날(토) 정기 휴무라 넣지 못했어요"]);
  const said = align(plan, {}, kb, new Set(["/places/가상박물관1/"]), { final: true, asked });
  assert.match(plan.summary, /가상도서관은 토요일 휴관이라 넣지 않았습니다/);
  assert.ok(!said.some((x) => x.startsWith("AI 설명")), said.join(" / "));
  // a sentence that says it is in when it is not goes
  const p2 = { ...plan, summary: "가상도서관을 넣었습니다. 박물관을 돕니다." };
  align(p2, {}, kb, new Set(["/places/가상박물관1/"]), { final: true, asked });
  assert.equal(p2.summary, "박물관을 돕니다.");
  // '걷는 거 줄여줘' is the 걷기 적게 need
  const c = { needs: [] };
  assert.deepEqual(withEditNeeds(c, { request: "아이랑 가니까 걷는 거 줄여줘" }).needs, ["lesswalk"]);
  assert.deepEqual(withEditNeeds(c, { request: "덜 걷게 바꿔 주세요" }).needs, ["lesswalk"]);
  assert.equal(withEditNeeds(c, { request: "카페 하나 넣어줘" }), c);
});

test("QA-30: a fee that is no table is said in the reader's words, the table's own word is quoted, places are counted", () => {
  const docs = Object.fromEntries([
    place("가상목장", "원도심", { g: [37.45, 126.6], fee: { t: "- 동물먹이주기 3,500원 - 승마체험 10,000원", p: "T" } }, "체험"),
    place("가상기념관", "원도심", { g: [37.451, 126.601], fee: { tab: { 성인: 3000 }, aw: "일반", tl: "개인", t: "[개인] 일반 3,000원", p: "T" } })]);
  const kb = kbOf(docs);
  const f = planFees([{ date: "2026-10-24", stops: [{ page: "/places/가상목장/", name: "가상목장", role: "visit" },
    { page: "/places/가상기념관/", name: "가상기념관", role: "visit" }] }], { adults: 2, seniors: 0, kids: [5, 8] }, kb);
  const lines = f.days[0].lines;
  const farm = lines.filter((l) => l.what === "가상목장");
  assert.ok(farm.every((l) => l.status === "unknown" && !/표가 아님/.test(l.basis) && /인원별로 셀 수 없음/.test(l.basis)), JSON.stringify(farm));
  assert.equal(lines.find((l) => l.what === "가상기념관" && l.who === "어른").basis, "요금표 '일반' (개인)");
  assert.ok(f.open.length >= 3 && f.openPlaces === 2);
});
