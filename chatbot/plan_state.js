// What a checked plan states about itself — review 2026-10-17 (AI 코스 만들기 집중 평가 CE05·CE06, R09·R13): the
// result said '휴무·운영시간 확인 6/6곳 · 걸리는 것 없음' above a list that left two places' New Year's Day unconfirmed,
// and a summary said a wheelchair route was confirmed where the list below did not know. The code now writes every
// such statement itself, from the site's data, and the model's words carry none of them:
//   - needsTable: each need the reader picked, at each stop — the data's own words, and one of ok (the data says it
//     fits), near (parking: none of its own, a public lot close by), no (the data says it does not), unknown;
//   - checksList: everything the reader is to check before going, one line each, by kind;
//   - grounded: a number in the model's sentences that the place pages do not have, and words that claim a check;
//   - status: 'ready' (nothing flagged, nothing to check), 'check' (nothing flagged, things to check), 'unmet'
//     (flags left after the fix the model had);
//   - completeness (outside evaluation 2026-10-18, a Monday by train 10:00→17:00 in the rain: after an edit one stop
//     was left at 10:20–11:20, the lunch gone and 340 minutes with nothing before the train): the reader's day as
//     they set it, a meal when it spans lunch or dinner, no stretch of more than IDLE minutes without a stop, each
//     liking they picked against the stops, and on an edit what the plan had and must keep.
import { regionOf } from "./knowledge.js";
import { HUBS } from "./plan_prompt.js";

export { regionOf };

export const NEED_LABEL = { rain: "실내", stroller: "유모차", wheelchair: "휠체어", parking: "주차", free: "입장료", lesswalk: "걷기" };
const INDOOR = /박물관|전시|문화시설|미술관/u;
const OUTDOOR = /자연·야외|레포츠/u;
const ROUTE_OK = /턱이\s*없|단차가?\s*없|경사로|휠체어\s*접근\s*가능|평지/u;
const ROUTE_NO = /계단만|접근\s*불가|턱이\s*있/u;
const RENT = /대여\s*가능/u;

const access = (f, key) => (f.ac || []).filter((a) => a.k === key);

/** One stop against one need: {state, text}. role: the stop's role in the plan; fee: plan_fees per-visit entry. */
export function needAt(need, f, role, fee) {
  if (need === "rain") {
    if (role !== "visit" || f.kd === "food" || f.kd === "stay") return { state: "ok", text: "실내(음식점·숙소)" };
    if (INDOOR.test(f.ty || "")) return { state: "ok", text: `실내(${f.ty})` };
    if (OUTDOOR.test(f.ty || "")) return { state: "no", text: `야외(${f.ty})` };
    return { state: "unknown", text: `실내인지 자료 없음${f.ty ? `(${f.ty})` : ""}` };
  }
  if (need === "stroller" || need === "wheelchair") {
    const route = access(f, "accessible_route");
    const extra = need === "wheelchair"
      ? [...access(f, "wheelchair").filter((a) => RENT.test(a.t)).map((a) => `휠체어 ${a.t}`),
        ...access(f, "accessible_toilet").filter((a) => a.t !== "없음").map((a) => a.t)]
      : access(f, "babycarriage").filter((a) => RENT.test(a.t)).map((a) => `유모차 ${a.t}`);
    const tail = extra.length ? ` · ${extra.join(" · ")}` : "";
    if (route.some((a) => ROUTE_OK.test(a.t))) return { state: "ok", text: `출입구: ${route.find((a) => ROUTE_OK.test(a.t)).t}${tail}` };
    if (route.some((a) => ROUTE_NO.test(a.t))) return { state: "no", text: `출입구: ${route[0].t}${tail}` };
    return { state: "unknown", text: `출입구 접근 정보 없음${tail}` };
  }
  if (need === "parking") {
    const near = f.pkn && f.pkn.m !== undefined ? `근처 공영주차장 ${f.pkn.n} 직선 ${f.pkn.m}m` : "";
    if (f.pk && /불가/u.test(f.pk)) return near ? { state: "near", text: `자체 주차 불가 · ${near}` } : { state: "no", text: "자체 주차 불가" };
    if (f.pk && /가능|구비|있음|무료/u.test(f.pk)) return { state: "ok", text: `주차 ${f.pk.split("\n")[0].slice(0, 30)}` };
    return near ? { state: "near", text: `주차 정보 없음 · ${near}` } : { state: "unknown", text: "주차 정보 없음" };
  }
  if (need === "free") {
    if (role !== "visit") return { state: "na", text: "입장료 없음(식사·카페·숙소)" };
    if (!fee) return { state: "unknown", text: "요금 정보 없음" };
    if (fee.how === "again") return { state: "ok", text: "같은 날 두 번째 방문" };
    if (fee.how !== "own") return { state: "no", text: "통합권으로 입장(유료)" };
    const st = fee.states || {};
    if (st.paid) return { state: "no", text: "입장료 있음" };
    if (st.unknown) return { state: "unknown", text: "요금 정보 없음·일부 확인 필요" };
    return { state: "ok", text: "무료" };
  }
  return { state: "unknown", text: "" };
}

/** {key, label, rows: [{day, i, name, state, text}]} for each need but lesswalk (no data reads walking). */
export function needsTable(plan, c, kb, fees) {
  return c.needs.filter((n) => n !== "lesswalk").map((need) => ({
    key: need, label: NEED_LABEL[need],
    rows: plan.days.flatMap((d, di) => d.stops.map((s, i) => {
      const f = ((kb.docs[s.page] || {}).f) || {};
      const fee = ((fees.days[di] || {}).per || []).find((p) => p.i === i);
      return { day: di, i, name: s.name, ...needAt(need, f, s.role, fee) };
    })),
  }));
}

/** What the reader is told about the plan, from the code's own checks (operator 2026-10-18: '이런 거 좀 안 뜨게 할 수
 *  없어? 무조건 완성된 결과가 나오게' — a finished plan's standing notes read as things left undone): {aware, checks}.
 *  aware: [{k, t}] — what holds for any plan of its kind and never makes it less finished: k 'move' (one line: the times
 *  between places are margins from straight-line distance, with the legs the site has no distance for), 'hub' (one line
 *  naming the station or terminal legs the site has no distance for), 'stay' (one line a stay: its check-in by the
 *  data, rooms and booking for the stay to confirm), 'walk' (걷기 적게: no data measures walking).
 *  checks: [{k, t}] — this plan's own gaps in the data, shown at the stop: k 'day' (no closed days or hours on the
 *  site, a date rule the code cannot resolve, a public holiday, a second visit), 'fee' (a person or a place with no
 *  price), 'need' (a need the reader picked that the data at a stop does not say). */
export function checksList(plan, c, check, needs, fees, hubs, kb) {
  const aware = [];
  const checks = [];
  const many = plan.days.length > 1;
  const stays = new Set();
  plan.days.forEach((d, di) => {
    const r = check.days[di];
    d.stops.forEach((s, i) => {
      const st = r.stops[i] || {};
      for (const t of st.checks || []) checks.push({ k: "day", t: `${many ? `${di + 1}일차 ` : ""}${s.name}: ${t}` });
      if (s.role === "stay" && !stays.has(s.page)) {
        stays.add(s.page);
        const ci = (((kb.docs[s.page] || {}).f) || {}).ci;
        aware.push({ k: "stay", t: `${s.name}: ${ci ? `체크인 ${ci}(사이트 값)` : "체크인 시각은 사이트에 없어요"} — 객실·예약은 숙소에 확인하세요` });
      }
    });
  });
  for (const t of fees.open) checks.push({ k: "fee", t: `입장료 ${t}` });
  for (const n of needs) {
    for (const row of n.rows.filter((x) => x.state === "unknown" || x.state === "no")) {
      checks.push({ k: "need", t: `${n.label}: ${many ? `${row.day + 1}일차 ` : ""}${row.name} — ${row.text}` });
    }
  }
  if (c.needs.includes("lesswalk")) aware.push({ k: "walk", t: "걷기: 걷는 거리는 사이트 자료로 잴 수 없어요 — 구간마다 직선거리를 적었어요" });
  if (hubs.length) {
    aware.push({ k: "hub", t: `${hubs.map((h) => (h.dir === "from" ? `${h.name} → ${h.stop}` : `${h.stop} → ${h.name}`)).join(", ")}: 사이트에 거리가 없는 구간이에요 — 지도 앱으로 확인하세요` });
  }
  if (plan.days.some((d) => d.stops.length > 1)) {
    // the legs the site has no distance for (a place without a point), named once in the same line
    const blind = plan.days.flatMap((d, di) => ((check.days[di] || {}).legs || []).filter((l) => l.m === null)
      .map((l) => `${many ? `${di + 1}일차 ` : ""}${d.stops[l.from].name} → ${d.stops[l.to].name}`));
    aware.push({ k: "move", t: `장소 사이 시간은 직선거리로 잡은 계획상 여유예요 — 실제 이동 시간은 지도 앱 길찾기로 확인하세요${blind.length ? ` (좌표가 없어 거리를 모르는 구간: ${blind.join(", ")})` : ""}` });
  }
  return { aware, checks };
}

const NUM = /\d[\d,]*(?:\.\d+)?/gu;
const CLAIM = /확인(?:된|됐|했|되었|됨|해\s*두)|보장|문제\s*없|걸리는\s*것\s*없|모두\s*(?:가능|열)/u;

/** The numbers of `text` (100 and up: years, prices, counts of rooms, distances in metres) that `source` does not
 *  have, and whether it claims a check. Numbers under 100 (people, ages, hours, minutes, days) are not read. */
export function grounded(text, source) {
  const src = String(source || "").replace(/(\d),(?=\d{3})/gu, "$1");
  const bad = [];
  for (const [raw] of String(text || "").matchAll(NUM)) {
    const n = raw.replace(/,/gu, "").replace(/\.$/u, "");
    if (Number(n) < 100) continue;
    if (!new RegExp(`(?<![\\d.])${n.replace(".", "\\.")}(?![\\d])`, "u").test(src)) bad.push(raw);
  }
  return { bad, claim: CLAIM.test(String(text || "")) };
}

/** The sentences of a text without the ones a test rejects. */
export function dropSentences(text, keep) {
  return String(text || "").split(/(?<=[.!?。])\s+/u).filter((s) => s && keep(s)).join(" ").trim();
}

// what holds for any plan of its kind — the times between places are planned margins, a hub's leg has no distance
// on the site, a stay's room is the stay's to confirm, walking cannot be measured — never makes a plan a draft: the
// page keeps these apart ('가기 전에 알아 둘 것'), not as something left to fix (operator 2026-10-18: '이런 거 좀 안
// 뜨게 할 수 없어? 무조건 완성된 결과가 나오게'). checksList returns them as 'aware'.
export const AWARE = new Set(["move", "hub", "stay", "walk"]);

/** A plan the page gets is 'ready' (operator 2026-10-18): its checks and standing notes never make it less so. A plan
 *  with flags left is never sent (planner.makePlan: an error 'conditions' instead) — 'unmet' names it in the log. */
export function statusOf(flags) {
  return flags.length ? "unmet" : "ready";
}

// ------------------------------------------------------------ the day as the reader lives it
export const HUB_MARGIN = 30;   // minutes kept after the station or terminal the trip starts from, and before the one it ends at
export const IDLE = 120;        // a stretch longer than this with no stop inside the reader's day is empty time
// lunch and dinner: the hours a day must span to need one (from–to), the window a meal stop anywhere in counts
// (near), the start the code aims a meal it adds at, and the earliest and latest start it gives one
export const MEALS = {
  lunch: { label: "점심", from: 690, to: 810, near: [660, 870], at: 720, first: 690, last: 780 },
  dinner: { label: "저녁", from: 1050, to: 1170, near: [1020, 1230], at: 1080, first: 1050, last: 1140 },
};
// 빼다 as leaving something out: 빼고, 빼서, 빼기로, 빼었·뺐, 빼놓았, 빼 주세요, 빼 드렸습니다 — never 빼놓을 수 없는,
// 빼놓지 말고, 빼지 마, 빼먹지, 빼어난, 빼곡 (review 2026-10-18). Read here and in planner.align.
// a form of leaving something out: any form of 빼다 except those that keep it (빼먹지 마, 빼놓을 수 없는, 빼지 마) or are other words (빼어나다, 빼곡하다) — listing the forms that drop it missed
// '빼줘', '빼요', '빼도', '빼면' (review 2026-10-18, third round)
export const CUT = /빼(?!먹|놓(?:을|지)|\s*지\s*(?:마|말|않)|어|곡)|뺐|뺀|뺄|뺍/u;
// the reader wrote that they eat elsewhere ('점심은 빼 주세요', '저녁은 따로 먹어요', '점심·저녁은 따로'): conservative — the
// meal words and a word of leaving them out within a few characters, no other meal word between. 점심 is the lunch and
// 저녁 the dinner (아침 neither); 식사·밥·끼니 are both only on their own — next to a meal word they are that meal's
// ('저녁 식사는 따로' leaves the lunch in), and inside a word they are no meal ('비빔밥은 빼'). Only a form of leaving it
// out counts: '빼먹지 말아', '빼지 마', '없이는 안 돼', '제외하지 마' want the meal.
const SAID_OUT = new RegExp(String.raw`(?:((?:점심|저녁|아침)(?:\s*(?:과|와|이랑|하고|및|[,·])\s*(?:점심|저녁|아침))*)\s*(?:식사|밥|끼니)?|(?<!(?:점심|저녁|아침)[^.!?\n]{0,4})(?<![가-힣])(?:식사|밥|끼니))(?:(?!점심|저녁|아침)[^.!?\n]){0,8}?`
  + String.raw`(?:${CUT.source}|없이(?!는?\s*(?:안|못))|안\s*먹|따로|제외(?!하지)|생략(?!하지))`, "gu");
export function eatsElsewhere(kind, ...texts) {
  const word = MEALS[kind].label;
  return texts.some((t) => [...String(t || "").matchAll(SAID_OUT)].some((m) => (m[1] ? m[1].includes(word) : true)));
}

export const hm = (t) => {
  const m = /^(\d{1,2}):(\d{2})$/.exec(t || "");
  return m ? +m[1] * 60 + +m[2] : null;
};
export const hhmm = (x) => `${String(Math.floor(x / 60)).padStart(2, "0")}:${String(x % 60).padStart(2, "0")}`;
/** 340 → '5시간 40분' */
export const span = (n) => [Math.floor(n / 60) ? `${Math.floor(n / 60)}시간` : "", n % 60 ? `${n % 60}분` : ""].filter(Boolean).join(" ") || "0분";

/** The stop of `stops` that is the day's lunch or dinner, or undefined: one with the role meal whose middle falls in
 *  the meal's window (one only touching the window is not that meal) at a place that is not a café or a bakery
 *  (isCafe, read with kb) — final check 2026-10-18: a 'meal' at a bakery counted as the day's lunch. */
export const mealIn = (stops, meal, kb = null) => (stops || []).find((s) => s.role === "meal" && !(kb && isCafe(kb.docs[s.page]))
  && (hm(s.start) + hm(s.end)) / 2 >= meal.near[0] && (hm(s.start) + hm(s.end)) / 2 < meal.near[1]);

/** Whether a night's stay ends the reader's day: one the model put in whose page gives a check-in time. A stay the
 *  code put in (by, planner.repair 6) or one with no check-in time says nothing of when the day ends (review
 *  2026-10-18: a stay with no check-in time put in at 13:00 after a stop ending at 12:30 left the day without its
 *  lunch). Without kb, every stay the model put in. */
export const endsDay = (s, kb = null) => !s.by && (!kb || !!(((kb.docs[s.page] || {}).f || {}).ci));

/** Day i as the reader lives it: {lo, hi, own, stay} in minutes — the first day from the start they set (after the
 *  station's margin), the last day to the end they set (before the station's margin), a day before a night to the
 *  night's stay when it ends the day (endsDay; no later than the end they set) and else to that end, as with no stay
 *  (a first day ending at 12:30 with the stay at 15:00 spans the lunch, as a last day would), every day at least its
 *  first stop's start to its last stop's end (a stay that ends the day before that: the last stop's end, as nothing
 *  can go after it); own: the stops but the night's stay, in order; stay: that night's stay after them when it ends
 *  the day (else null, and always on the last day). null when there are no stops. */
export function readerDay(plan, c, i, kb = null) {
  const own = plan.days[i].stops.filter((s) => s.role !== "stay");
  if (!own.length) return null;
  const lastDay = i === plan.days.length - 1;
  const a = hm(own[0].start), z = Math.max(...own.map((s) => hm(s.end)));
  const stays = lastDay ? [] : plan.days[i].stops.filter((s) => s.role === "stay" && endsDay(s, kb));
  const stay = stays.find((s) => hm(s.start) >= z) || null;
  const lo = i === 0 ? hm(c.start) + (c.from ? HUB_MARGIN : 0) : a;
  const hi = lastDay ? hm(c.end) - (c.to ? HUB_MARGIN : 0) : stays.length && !stay ? z : Math.min(hm(c.end), stay ? hm(stay.start) : hm(c.end));
  return { lo: Math.min(lo, a), hi: Math.max(hi, z), own, stay };
}
export const spans = (day, meal) => day.lo <= meal.from && day.hi >= meal.to;

/** The stretches of the reader's day with no stop: [{from, to, minutes, at}] — at: the index in day.own the stretch
 *  ends before (day.own.length: after the last stop). */
export function idleGaps(day) {
  const out = [];
  let t = day.lo;
  day.own.forEach((s, j) => {
    const a = hm(s.start);
    if (a > t) out.push({ from: t, to: a, minutes: a - t, at: j });
    t = Math.max(t, hm(s.end));
  });
  if (day.hi > t) out.push({ from: t, to: day.hi, minutes: day.hi - t, at: day.own.length });
  return out;
}

// ------------------------------------------------------------ what the reader likes, read from the data
export const PREF_LABEL = { history: "역사·문화", food: "맛집", islands: "섬·바다", nature: "자연·힐링", alleys: "골목 산책",
  cafe: "카페·빵집", experience: "체험", night: "야경", photo: "사진 명소" };
// the place types (docs.json f.ty, the site's own classes) a liking reads as; islands by the 권역 the page names (docs.json
// f.isl: the build marks an island 권역 — site.json city.plan.island_regions, or a 권역 whose name says 섬)
export const PREF_TYPES = { history: ["문화유산", "박물관·전시", "골목과 문화", "문화시설"], nature: ["자연·야외"], alleys: ["골목과 문화"],
  experience: ["체험"] };
// a café or bakery: a food page with no cuisine type whose menu lines (대표 메뉴·취급 메뉴) name coffee, tea, bread or a
// sweet — TourAPI files cafés under 음식점 like any restaurant (a bakery's 단팥빵, a café's 사워도우 or 크레마); the code
// never adds one as a meal. 차 is a tea at the end of a word ('대추차', '탱자차'), never '차돌' or '녹차밥'.
const CAFE_MENU = /커피|아메리카노|라떼|에스프레소|콜드브루|카푸치노|크레마|베이커리|빵|케이크|디저트|와플|스콘|크루아상|크로와상|마카롱|빙수|사워도우|바게트|베이글|타르트|호떡|간식|말차|에이드|찻집|차(?![가-힣])/u;
// a meal on an untyped food page's menu: a dish of rice, soup, noodles, grilled or raw fish and meat, a set meal
const MEAL_MENU = /밥|국|탕|면|정식|찌개|구이|회|짜장|짬뽕|돈까스|돈가스|카츠|국수|냉면|덮밥|백반|해장|찜|전골|소바|우동|라멘|피자|파스타|버거|리조또|스테이크|커리|카레|치킨|갈비|불고기|삼겹|곱창|막창|족발|보쌈|샤브|초밥|스시|게장|텐동|수제비/u;

// a food page's menu lines (대표 메뉴·취급 메뉴), each without its source
const menuLines = (doc) => String((doc && doc.x) || "").split("\n").filter((l) => /^- (?:대표|취급) 메뉴/u.test(l)).map((l) => l.split(" — ")[0]);
// each page read once (the planner asks of every place many times a plan)
const CAFE = new WeakMap();
const MEAL = new WeakMap();
const once = (cache, doc, read) => {
  if (!doc || typeof doc !== "object") return read(doc);
  if (!cache.has(doc)) cache.set(doc, read(doc));
  return cache.get(doc);
};
export function isCafe(doc) {
  return once(CAFE, doc, (d) => {
    const f = (d && d.f) || {};
    if (f.kc === "cafe") return true;   // the site's own 카페·디저트 kind (TourAPI's café and bakery classes; docs.json kc)
    if (f.kd !== "food" || f.ty) return false;
    return CAFE_MENU.test(menuLines(d).join(" "));
  });
}
/** Whether the code may give a food page as a meal: not a café, and a cuisine type or a menu line that names a meal
 *  (MEAL_MENU) — an untyped page with no menu (a tea house in a temple) or a menu of other things (a brunch's 세트,
 *  샌드위치) says nothing of a meal. */
export function isMeal(doc) {
  return once(MEAL, doc, (d) => {
    const f = (d && d.f) || {};
    if (f.kd !== "food" || isCafe(d)) return false;
    return !!f.ty || menuLines(d).some((l) => MEAL_MENU.test(l));
  });
}
/** Whether a place fits a liking by its data: true, false, or null when the data cannot tell (night views, photo
 *  spots: no field says so). */
export function prefFits(key, doc) {
  const f = (doc && doc.f) || {};
  if (key === "night" || key === "photo") return null;
  if (key === "food") return f.kd === "food" && !isCafe(doc);
  if (key === "cafe") return isCafe(doc);
  if (f.kd !== "attraction") return false;
  if (key === "islands") return f.isl === 1 || /섬/u.test(regionOf(doc));
  return (PREF_TYPES[key] || []).includes(f.ty || "");
}
/** Whether the plan holds a liking: a meal for 맛집, a café for 카페·빵집, a stop of the liking's types for the rest;
 *  null for what the data cannot tell. */
export function prefMet(key, plan, kb) {
  if (key === "night" || key === "photo") return null;
  const stops = plan.days.flatMap((d) => d.stops).filter((s) => s.role !== "stay");
  if (key === "food") return stops.some((s) => s.role === "meal");
  if (key === "cafe") return stops.some((s) => s.role === "cafe" || isCafe(kb.docs[s.page]));
  return stops.some((s) => s.role === "visit" && prefFits(key, kb.docs[s.page]));
}

/** The plan read as an itinerary the reader can follow, after the code's repairs: {meals: [{day, kind, state, note?}],
 *  gaps: [{day, from, to, minutes}], prefs: [{key, label, met}], edit?: [{what, state}]}.
 *  meals — each day that spans lunch or dinner (or, on an edit, had one): ok (the plan's own meal), added (the site
 *  added it), skip (the reader eats elsewhere), missing — with a note when a 'meal' in the window is not one (mealIn:
 *  a café or a bakery, or one only touching the window). gaps — the empty stretches left; a day with no stop of its
 *  own (a night's stay alone) is empty from the reader's start to their end. edit — what the plan before
 *  the change had and must keep: its lunch and dinner (kept, restored by the site, dropped as asked, lost) and the
 *  margins at the station or terminal (kept, lost). */
export function completeness(plan, c, kb, edit = null) {
  const meals = [];
  const gaps = [];
  const request = edit ? edit.request : "";
  plan.days.forEach((d, i) => {
    const day = readerDay(plan, c, i, kb);
    if (!day) {
      // no stop of its own (final check 2026-10-18: a day with a night's stay alone passed)
      const lo = hm(c.start) + (i === 0 && c.from ? HUB_MARGIN : 0), hi = hm(c.end) - (i === plan.days.length - 1 && c.to ? HUB_MARGIN : 0);
      if (hi > lo) gaps.push({ day: i, from: hhmm(lo), to: hhmm(hi), minutes: hi - lo });
      return;
    }
    const before = edit && edit.plan.days[i] ? edit.plan.days[i].stops : [];
    for (const kind of ["lunch", "dinner"]) {
      const m = MEALS[kind];
      if (!spans(day, m) && !mealIn(before, m, kb)) continue;
      const meal = mealIn(d.stops, m, kb);
      const state = meal ? (meal.by === "site" ? "added" : "ok") : eatsElsewhere(kind, c.note, request) ? "skip" : "missing";
      // a 'meal' in the window that is not the day's meal says why
      const not = state === "missing" && d.stops.find((s) => s.role === "meal" && hm(s.start) < m.near[1] && hm(s.end) > m.near[0]);
      meals.push({ day: i, kind, state, ...(not ? { note: `${not.name}: ${isCafe(kb.docs[not.page]) ? "카페·빵집이라" : `${m.label} 시간에 걸치기만 해`} 식사로 세지 않음` } : {}) });
    }
    for (const g of idleGaps(day)) if (g.minutes > IDLE) gaps.push({ day: i, from: hhmm(g.from), to: hhmm(g.to), minutes: g.minutes });
  });
  const out = { meals, gaps, prefs: c.prefs.map((key) => ({ key, label: PREF_LABEL[key], met: prefMet(key, plan, kb) })) };
  if (edit) {
    const many = plan.days.length > 1;
    out.edit = [];
    plan.days.forEach((d, i) => {
      const was = (edit.plan.days[i] || { stops: [] }).stops;
      for (const kind of ["lunch", "dinner"]) {
        if (!mealIn(was, MEALS[kind], kb)) continue;
        const now = mealIn(d.stops, MEALS[kind], kb);
        out.edit.push({ what: `${many ? `${i + 1}일차 ` : ""}${MEALS[kind].label}`,
          state: now ? (now.by === "site" ? "restored" : "kept") : eatsElsewhere(kind, request) ? "dropped" : "lost" });
      }
    });
    // the station or terminal: the margin after the start and before the end the plan kept before the change
    const gapAt = (stops, dir) => {
      const own = stops.filter((s) => s.role !== "stay");
      if (!own.length) return null;
      return dir === "from" ? hm(own[0].start) - hm(c.start) : hm(c.end) - Math.max(...own.map((s) => hm(s.end)));
    };
    for (const [dir, key, i, at] of [["from", c.from, 0, c.start], ["to", c.to, plan.days.length - 1, c.end]]) {
      if (!key) continue;
      const was = gapAt((edit.plan.days[i] || { stops: [] }).stops, dir), now = gapAt(plan.days[i].stops, dir);
      if (was === null || now === null) continue;
      out.edit.push({ what: dir === "from" ? `${HUBS[key]} ${at} 출발 뒤 여유` : `${HUBS[key]} ${at} 도착 전 여유`,
        state: now >= Math.min(HUB_MARGIN, was) ? "kept" : "lost" });
    }
  }
  return out;
}
