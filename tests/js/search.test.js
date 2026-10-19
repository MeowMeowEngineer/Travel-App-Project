// The site search (templates/assets/search.js) run in Node (tests/js/search_page.js) over made-up rows: the scenario
// QA of 2026-10-19 — QA-24 a two-syllable word the site sorts places by is no run inside another word ('전시' found
// 작전시장, '숙소' a sight named …합숙소) while every right match stays, QA-72 '함께 찾은 말' names each word once,
// QA-70 the rows past the first 80 are one press away.
import { test } from "node:test";
import assert from "node:assert/strict";
import { page } from "./search_page.js";

// the stay and rain rows of present.SEARCH_CONCEPTS (the words this test needs)
const CONCEPTS = [
  { say: ["비 오는", "실내"], find: ["비 오는", "실내", "박물관", "미술관", "과학관", "전시관", "박물관·전시", "문화시설"] },
  { say: ["숙소", "숙박", "잘 곳"], find: ["숙소", "숙박", "펜션", "민박"] },
];
const row = (n, k, t, d = "", extra = {}) => ({ n, a: "", k, t, d, r: "", p: `/places/${encodeURIComponent(n)}/`, ...extra });
const ROWS = [
  row("[테스트] 작전시장", "shopping", "쇼핑", "작전동"),
  row("[테스트] 대불호텔전시관", "attraction", "박물관·전시", "중앙동"),
  row("[테스트] 디지털전시체험관", "attraction", "체험", "운서동"),
  row("[테스트] 가상 박물관", "attraction", "박물관·전시", "가상동"),
  row("[테스트] 바다낚시터", "attraction", "레포츠", "가상동"),
  row("[테스트] 송도콩나물해장국", "food", "음식점", "가상동"),
  row("[테스트] 고인돌캠핑장", "attraction", "자연·야외", "가상동"),
  row("[테스트] 복지관(여선교사합숙소)", "attraction", "관광지", "가상동"),
  row("[테스트] 바다펜션", "stay", "숙박업소", "가상동"),
  row("[테스트] 자전거 관광코스", "attraction", "관광지", "가상동"),
  row("[테스트] 한옥카페 도솔", "attraction", "문화시설", "가상동"),
];

test("QA-24: '전시' and '숙소' are no runs inside another word, and every right match stays", async () => {
  const p = page({ rows: ROWS, concepts: CONCEPTS, region: "인천" });
  const shown = async (q) => (await p.search(q)).names;
  const exhibit = await shown("전시");
  assert.ok(!exhibit.includes("[테스트] 작전시장"), exhibit.join(" / "));   // 작전 + 시장
  for (const n of ["[테스트] 대불호텔전시관", "[테스트] 디지털전시체험관", "[테스트] 가상 박물관"]) assert.ok(exhibit.includes(n), n);
  const stay = await shown("숙소");
  assert.ok(!stay.includes("[테스트] 복지관(여선교사합숙소)"), stay.join(" / "));   // a sight
  assert.deepEqual(stay, ["[테스트] 바다펜션"]);
  assert.ok(!(await shown("잘 곳")).includes("[테스트] 복지관(여선교사합숙소)"));
  // words the site does not sort by still find inside a word; a kind's name the search does not read as a concept too
  assert.deepEqual(await shown("낚시"), ["[테스트] 바다낚시터"]);
  assert.deepEqual(await shown("해장국"), ["[테스트] 송도콩나물해장국"]);
  assert.deepEqual(await shown("캠핑"), ["[테스트] 고인돌캠핑장"]);
  assert.deepEqual(await shown("코스"), ["[테스트] 자전거 관광코스"]);
  assert.deepEqual(await shown("카페"), ["[테스트] 한옥카페 도솔"]);
  assert.deepEqual(await shown("작전"), ["[테스트] 작전시장"]);   // the place's own name
});

test("QA-72: the words also searched are each named once", async () => {
  const p = page({ rows: ROWS, concepts: CONCEPTS, region: "인천" });
  const r = await p.search("비 오는 날");
  assert.match(r.syn, /^함께 찾은 말: 비 오는 → /);
  const words = r.syn.split(" → ")[1].split("·");
  assert.equal(new Set(words).size, words.length, r.syn);
  assert.ok(!words.includes("전시") && words.includes("박물관") && words.includes("전시관"), r.syn);
});

test("QA-70: past the first 80 rows a button shows 80 more, the count line follows", async () => {
  const rows = Array.from({ length: 170 }, (_, i) => row(`[테스트] 가상식당 ${String(i + 1).padStart(3, "0")}`, "food", "음식점"));
  const p = page({ rows, concepts: CONCEPTS, region: "인천" });
  const r = await p.search("가상식당");
  assert.equal(r.names.length, 80);
  assert.equal(r.count, "‘가상식당’ 170곳 중 80곳");
  assert.equal(r.more, "80곳 더 보기");
  assert.equal(r.out.attrs["aria-live"], "polite");
  // the button: its data-more is how many show now
  const button = r.html.match(/<button[^>]*data-more="(\d+)"/);
  assert.equal(button[1], "80");
  const press = async (had) => {
    r.click({ target: { closest: (sel) => (/data-more/.test(sel) ? { getAttribute: () => String(had) } : null) } });
    for (let i = 0; i < 3; i++) await new Promise((res) => setTimeout(res, 0));
    return r.out;
  };
  let out = await press(80);
  assert.equal((out.innerHTML.match(/<li/g) || []).length, 160);
  assert.equal((out.innerHTML.match(/<li data-new>/g) || []).length, 80);   // the rows it added (they take the focus)
  assert.match(out.innerHTML, /170곳 중 160곳/);
  assert.match(out.innerHTML, /10곳 더 보기/);
  assert.equal(out.attrs["aria-live"], "off");   // the update does not read every row out again
  out = await press(160);
  assert.equal((out.innerHTML.match(/<li/g) || []).length, 170);
  assert.ok(!/data-more/.test(out.innerHTML) && /‘가상식당’ 170곳</.test(out.innerHTML));
  // the other versions' words
  const en = page({ rows, concepts: [], words: { kinds: { food: "Restaurants" }, of: "{n} of {m}", more: "Show {n} more" } });
  const e = await en.search("가상식당");
  assert.equal(e.more, "Show 80 more");
});
