// The scenario QA of 2026-10-19, second round, QA-67: a course stop's hours of the trip day. The build gives an hours
// value by weekday (pipeline present.day_hours → chat docs f.h[].w, Sunday first); checkPlan reads that day's group,
// not the first range of the whole text (a Saturday read the 평일 11:30 opening). Made-up places, no network.
import assert from "node:assert/strict";
import test from "node:test";

import { Knowledge, tokens } from "../../chatbot/knowledge.js";

const SITE = "https://test.example.kr";
const RAW = "[평일] - 11:30~23:00 - 준비시간 15:00~17:00 - 마지막 주문 22:30 [금요일] - 12:00~24:00 - 마지막 주문 23:30 "
  + "[토요일] - 12:00~24:00 - 마지막 주문 23:30 [일요일] - 11:30~23:00";
// day_hours of RAW, as the build writes it
const W = ["일요일 11:30–23:00", "평일 11:30–23:00 · 준비시간 15:00–17:00 · 마지막 주문 22:30",
  "평일 11:30–23:00 · 준비시간 15:00–17:00 · 마지막 주문 22:30", "평일 11:30–23:00 · 준비시간 15:00–17:00 · 마지막 주문 22:30",
  "평일 11:30–23:00 · 준비시간 15:00–17:00 · 마지막 주문 22:30", "금요일 12:00–24:00 · 마지막 주문 23:30",
  "토요일 12:00–24:00 · 마지막 주문 23:30"];

function kbOf(h) {
  const docs = { "/places/가상식당/": { t: "가상식당", k: "place", x: "가상식당 — 음식점", f: { kd: "food", ty: "한식", g: [37.45, 126.6],
    c: [{ p: "한국관광공사", t: "연중무휴" }], h } } };
  const index = { v: 1, docs: Object.fromEntries(Object.entries(docs).map(([k, d]) => [k, [tokens(`${d.t} ${k}`).join(" "), tokens(d.x).join(" ")]])) };
  return new Knowledge({ catalog: "# catalog", docs: { v: 1, site: SITE, docs, alias: {}, ext: [], tickets: [] }, index });
}
const at = (kb, date, start, end) => kb.checkPlan({ date, stops: [{ page: "/places/가상식당/", start, end }] });

test("QA-67: a Saturday reads the 토요일 group — an 11:30 start is before its 12:00 opening", () => {
  const r = at(kbOf([{ p: "한국관광공사 TourAPI", t: RAW, w: W }]), "2026-10-24", "11:30", "12:20");
  assert.match(r.text, /그날 시간 — 한국관광공사 TourAPI: 토요일 12:00–24:00/u);
  assert.equal(r.flags.length, 1);
  assert.match(r.flags[0], /여는 시각 12:00보다 이름/u);
  assert.deepEqual(r.stops[0].hours.map((x) => [x.open, x.close]), [[720, 1440]]);
  // a weekday reads the 평일 group, the same start fits
  const mon = at(kbOf([{ p: "한국관광공사 TourAPI", t: RAW, w: W }]), "2026-10-26", "11:30", "12:20");
  assert.deepEqual(mon.flags, []);
  assert.match(mon.text, /그날 시간 — 한국관광공사 TourAPI: 평일 11:30–23:00/u);
});

test("QA-67: the day's own group is not read again by its label ('평일 / 일요일' on a Monday)", () => {
  const w = ["평일 / 일요일 11:30–23:00", "평일 / 일요일 11:30–23:00", "평일 / 일요일 11:30–23:00", "평일 / 일요일 11:30–23:00",
    "평일 / 일요일 11:30–23:00", "평일 / 일요일 11:30–23:00", "토요일 11:30–24:00"];
  const r = at(kbOf([{ p: "한국관광공사 TourAPI", t: "- 평일 / 일요일 11:30~23:00 - 토요일 11:30~24:00", w }]), "2026-10-26", "12:00", "13:00");
  assert.deepEqual(r.flags, []);
  assert.deepEqual(r.stops[0].hours.map((x) => [x.open, x.close]), [[690, 1380]]);
});

test("QA-67: a weekday no group names is a thing to check, not the first range", () => {
  const w = ["목요일~일요일 10:00–19:00", "", "", "수요일 13:00–19:00", "목요일~일요일 10:00–19:00", "목요일~일요일 10:00–19:00",
    "목요일~일요일 10:00–19:00"];
  const r = at(kbOf([{ p: "한국관광공사 TourAPI", t: "- 목요일~일요일 10:00~19:00 - 수요일 13:00~19:00", w }]), "2026-10-27", "10:00", "11:00");
  assert.deepEqual(r.stops[0].hours, []);
  assert.match(r.text, /화요일 시간이 이 값에 없음/u);
  assert.ok(r.stops[0].checks.some((x) => /그 시각에 여는지 확인 필요/u.test(x)));
});

test("QA-67: a value without weekday groups reads as before", () => {
  const r = at(kbOf([{ p: "한국관광공사 TourAPI", t: "11:00~21:00" }]), "2026-10-24", "11:30", "12:20");
  assert.deepEqual(r.flags, []);
  assert.deepEqual(r.stops[0].hours.map((x) => [x.open, x.close]), [[660, 1260]]);
});
