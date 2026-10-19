// The course planner's shared ground (chatbot/planner.js repairs, chatbot/plan_build.js builds): times, straight
// lines, the margin a leg gets, the places with a point, and whether a place opens on a date at given times by the
// site's own data (knowledge.checkPlan's reading, cached per date). Moved out of planner.js (2026-10-18, fifth round)
// so the day builder and the repairs read the same rules.
import { iga, eul, jong, legBound, regionFloor, regionOf, ro } from "./knowledge.js";
import { planFees } from "./plan_fees.js";
import { needAt } from "./plan_state.js";

export { eul, iga, jong, legBound, regionOf, ro };

const HM = /^([01]\d|2[0-3]):([0-5]\d)$/;
export const mins = (t) => {
  const m = HM.exec(t || "");
  return m ? +m[1] * 60 + +m[2] : null;
};
export const hhmm = (x) => `${String(Math.floor(x / 60)).padStart(2, "0")}:${String(x % 60).padStart(2, "0")}`;

export const metres = (a, b) => {
  const rad = (x) => (x * Math.PI) / 180;
  const h = Math.sin(rad(b[0] - a[0]) / 2) ** 2 + Math.cos(rad(a[0])) * Math.cos(rad(b[0])) * Math.sin(rad(b[1] - a[1]) / 2) ** 2;
  return Math.round(2 * 6371000 * Math.asin(Math.sqrt(h)));
};
export const km = (m) => (m >= 1000 ? `${(m / 1000).toFixed(1)}km` : `${m}m`);
export const STAY_NEAR = 5000;   // a stay the code adds for a night is within this straight-line distance of the day's last stop
// island areas — the 권역 a page names: site.json city.plan.island_regions (docs.json f.isl), or a 권역 whose name says
// 섬 —: two places farther apart than SEA_M may be across the sea, and the site has no ferries (QA 2026-10-19 QA-09: a
// plan hopped between islands as if by road and put the night's stay on another island)
export const SEA_M = 3000;
export const onIsland = (doc) => !!doc && (((doc.f || {}).isl === 1) || /섬/u.test(regionOf(doc)));
/** The straight lines a night's stay is looked for in after a day's last stop (doc: that stop's page), nearest first:
 *  STAY_NEAR, then farther, without limit at the end — but on an island SEA_M first and never without limit. */
export const stayRadii = (doc) => (onIsland(doc) ? [SEA_M, STAY_NEAR, 10000, 20000] : [STAY_NEAR, 10000, 20000, Infinity]);
// a place the code puts in — for a stop closed that day, a missing meal, an empty stretch — is within this straight
// line of the stop it goes next to: [without a car, by car]
export const NEAR = { swap: [3000, 5000], meal: [1500, 5000], fill: [3000, 5000] };
export const KEEP_MIN = 20;      // a stop the code shortens for a leg's margin keeps at least this many minutes
export const MEAL_KEEP = 45;     // a meal the code shortens keeps at least this (one the model gave shorter is not shortened)
// the least a place the code swaps in for a stop gets (round-4 verifier: a place swapped in kept 20 minutes — the
// stop goes instead): a visit or a café 30 minutes, a meal MEAL_KEEP
export const SWAP_MIN = { visit: 30, meal: 45, cafe: 30 };
/** The least a stop may be shortened to: KEEP_MIN, a meal MEAL_KEEP (or its own length when that is shorter) —
 *  round-4 verifier: a lunch cut to 20 minutes for a leg's margin —, a place the code put in or swapped in SWAP_MIN
 *  (round-5 verifier: a visit swapped in was cut to 20 minutes; it goes instead). */
export const keepOf = (s) => (s.role === "meal" ? Math.min(MEAL_KEEP, mins(s.end) - mins(s.start))
  : s.by && s.role !== "stay" ? SWAP_MIN[s.role] || SWAP_MIN.visit : KEEP_MIN);
// the most stops a day has, its night's stay counted: what readSubmit takes from the model and validEdit takes back
// from the page (planner.PLAN_LIMITS.stopsPerDay) — the code adds no more (round-5 verifier: days of 13 stops, the
// 13th beyond checkPlan's reading and none of them editable)
export const STOPS_MAX = 10;
// the longest a stop the code lengthens to close an empty stretch gets: a visit 3 hours, a meal or a café 90 minutes
// (2026-10-18: a lunch stretched to three hours to close an afternoon)
export const stretchMax = (s) => (s.role === "meal" || s.role === "cafe" ? 90 : 180);
export const MEAL_MIN = 60;      // a meal the code adds
export const FILL_MIN = 60;      // a place the code adds to an empty stretch: 60–90 minutes
export const FILL_MAX = 90;
export const CANDIDATES = 20;    // places read (each one's day checked) for one stop the code puts in
export const CAMP = /캠핑|야영|글램핑|카라반|찜질방/u;
export const WEEK = "일월화수목금토";
export const near = (c, what) => NEAR[what][c.move === "car" ? 1 : 0];
export const dateWords = (date) => {
  const dt = new Date(`${date}T12:00:00Z`);
  return `${dt.getUTCMonth() + 1}월 ${dt.getUTCDate()}일(${WEEK[dt.getUTCDay()]})`;
};

/** The margin the code leaves for a leg — a planned allowance, never a travel time (the page says so): by car 1.5 ×
 *  the straight line at 60 km/h and 5 minutes to park; without one 1.5 × the faster of walking (100 m a minute) and
 *  a bus (10 minutes' wait, then 400 m a minute); at least 10 minutes, rounded up to 5. It never shrinks as a leg
 *  grows (final check 2026-10-18: 1.2 km on foot had 20 minutes, 1.3 km by bus 10). m: metres, or null when a point
 *  is missing (10 minutes; marginOf reads the 권역 then). */
export function legMargin(m, move) {
  if (m === null) return 10;
  const t = move === "car" ? (1.5 * m) / 1000 + 5 : 1.5 * Math.min(m / 100, 10 + m / 400);
  return Math.ceil(Math.max(10, t) / 5) * 5;
}
export const gOf = (kb, page) => ((kb.docs[page] || {}).f || {}).g;
/** The point of the last of `stops` (a night's stay left out) the site has one for, or null — where a stay or a place
 *  the code adds after them is looked for when the last stop has no point (2026-10-18: a day ending at a place with no
 *  point got no stay). */
export function lastPoint(kb, stops) {
  for (let j = stops.length - 1; j >= 0; j -= 1) if (stops[j].role !== "stay" && gOf(kb, stops[j].page)) return gOf(kb, stops[j].page);
  return null;
}
/** The margin between two places (pages): legMargin of their straight line; with a point missing, at least the floor
 *  between two 권역 (knowledge.regionFloor, the one checkPlan holds such a leg to). */
export function marginOf(pa, pb, c, kb) {
  const ga = gOf(kb, pa), gb = gOf(kb, pb);
  return ga && gb ? legMargin(metres(ga, gb), c.move) : Math.max(legMargin(null, c.move), regionFloor(kb.docs[pa], kb.docs[pb], c.move));
}
/** The least a leg between two places the model put next to each other may have and pass the check (checkPlan: more
 *  than nothing, not under the straight line's bound, not under the floor between two 권역 with no point), in 5s and
 *  never under 10 minutes (what widen held a flagged leg to before). */
export function legFloor(pa, pb, c, kb) {
  const ga = gOf(kb, pa), gb = gOf(kb, pb);
  const bound = ga && gb ? legBound(metres(ga, gb), c.move) : regionFloor(kb.docs[pa], kb.docs[pb], c.move);
  return Math.max(10, Math.ceil(bound / 5) * 5);
}
// the places with a point, once per knowledge base: [{page, doc}]
const PLACES = new WeakMap();
export function placesOf(kb) {
  if (!PLACES.has(kb)) {
    PLACES.set(kb, kb.keys.filter((k) => kb.docs[k] && kb.docs[k].k === "place" && (kb.docs[k].f || {}).g)
      .map((k) => ({ page: k, doc: kb.docs[k] })));
  }
  return PLACES.get(kb);
}
// a restaurant's break in the day ('준비시간 14:00~16:30', '브레이크타임 15:00~17:00'): a meal the code adds stays out of it
const BREAK = /(?:준비\s*시간|브레이크\s*타임|break\s*time)\s*[:：]?\s*(\d{1,2}):(\d{2})\s*[~–-]\s*(\d{1,2}):(\d{2})/giu;
export function inBreak(f, a, b) {
  for (const h of f.h || []) {
    for (const m of String(h.t || "").matchAll(BREAK)) if (a < +m[3] * 60 + +m[4] && b > +m[1] * 60 + +m[2]) return true;
  }
  return false;
}
export const ALWAYS = /상시\s*(?:개방|이용)|24\s*시간/u;

// one place's day by the site's data, once per knowledge base, date and page (a checkPlan reading with no times):
// {state: 'open' | 'check' | 'closed' | null, day, checks, hours: [{open, close, last}], read, always}
const DAYS = new WeakMap();
export function dayInfo(kb, date, page) {
  if (!DAYS.has(kb)) DAYS.set(kb, new Map());
  const byDate = DAYS.get(kb);
  if (!byDate.has(date)) byDate.set(date, new Map());
  const cache = byDate.get(date);
  if (cache.has(page)) return cache.get(page);
  const r = kb.checkPlan({ date, stops: [{ page, start: "", end: "" }] });
  const s = r.stops[0] || { day: "unknown", checks: [], hours: [] };
  const f = (kb.docs[page] || {}).f || {};
  const always = (f.h || []).some((h) => ALWAYS.test(h.t || ""));
  // flags with no times: closed that day (a closed day, a notice) or a fortnightly rule — never a stop to put in
  const state = r.flags.length || s.day === "closed" ? "closed"
    : s.day === "open" && !s.checks.length ? "open"
      : (s.day === "open" || s.day === "unknown") && (f.c || []).length ? "check" : null;
  const info = { state, day: s.day, checks: s.checks || [], hours: s.hours || [], read: (s.hours || []).length > 0 || always, always };
  cache.set(page, info);
  return info;
}
/** Whether a–b keeps to every hours line the site gives for that date (checkPlan's own test: not before opening, not
 *  after closing when it closes the same day, not starting after the last entry) and, for a restaurant, its break. */
export function fitsHours(kb, info, page, a, b) {
  for (const h of info.hours) {
    if (a < h.open || (h.close > h.open && b > h.close) || (h.last !== null && a > h.last)) return false;
  }
  return !inBreak((kb.docs[page] || {}).f || {}, a, b);
}

/** Whether a place opens that day at those times by the site's data — nothing flagged (a closed day, a notice, hours,
 *  the last entry), hours the check could read for that date holding the times (or a value that says it is always
 *  open — '상시 개방', '24시간'; never '내부 관람 불가' or a season with no months), and for a restaurant outside its
 *  break — and then how far the data goes: 'open' (checkPlan 'open', nothing to check that day), 'check' (not a regular
 *  closed day, but the day leaves something to check: a public holiday, a 설·추석·명절 or 공휴일 rule), or null (not
 *  that, or no closed days on the site at all). The reader's words say only what is known (openWords). */
export function opensAt(kb, date, page, a, b) {
  const info = dayInfo(kb, date, page);
  if (!info.state || info.state === "closed" || !info.read || b <= a || !fitsHours(kb, info, page, a, b)) return null;
  return info.state;
}
// what the code says of a place it puts in, by opensAt: 'open' — it opens then; 'check' — only what is known
export const CHECK_WORDS = "정기 휴무가 아닌 곳 — 그날 운영은 확인 필요";
export const openWords = (open) => (open === "open" ? "그날 그 시각에 여는 곳" : CHECK_WORDS);
// a change that would push the admissions the code prices over the reader's budget (and above what they were) is
// not made: before = the known total before the change (knownFees)
export function overBudget(plan, c, kb, before) {
  if (c.budget === null || c.budget === undefined) return false;
  const f = planFees(plan.days, c, kb, c.budget);
  return f.verdict === "over" && f.known > before;
}
export const knownFees = (plan, c, kb) => (c.budget === null || c.budget === undefined ? 0 : planFees(plan.days, c, kb, c.budget).known);
// rain (비 와도 실내 위주): an indoor type first (plan_state.needAt 'ok'), then a typed place that is not outdoor;
// never an outdoor type (자연·야외·레포츠) and never a place with no type — whether it is indoors is not known
export function rainRank(c, f) {
  if (!c.needs.includes("rain") || f.kd !== "attraction") return 0;
  const st = needAt("rain", f, "visit").state;
  return st === "ok" ? 0 : st === "unknown" && f.ty ? 1 : null;
}
export const freeRank = (c, f) => (c.needs.includes("free") && !(f.fee && f.fee.free) ? 1 : 0);
// the needs a stop must not fail (the data says 'no'): wheelchair, stroller, free (a visit), parking
export const HARD = ["wheelchair", "stroller", "free", "parking"];
/** A place's state for each hard need the reader picked: 'ok' (or 'near' for parking), 'unknown', 'no' — the worst.
 *  fee: a free page is 'ok', a table 'no', anything else 'unknown' (needHints' reading; plan_fees prices the plan). */
export function hardState(c, f, role) {
  let worst = "ok";
  for (const need of c.needs.filter((n) => HARD.includes(n))) {
    const fee = need === "free" ? { how: "own", states: f.fee && f.fee.free ? { free: 1 } : f.fee && f.fee.tab ? { paid: 1 } : { unknown: 1 } } : null;
    const st = needAt(need, f, role, fee).state;
    if (st === "no") return "no";
    if (st === "unknown") worst = "unknown";
  }
  return worst;
}
export const isOutdoor = (f) => /자연·야외|레포츠/u.test(f.ty || "");
/** Whether a place may go in where the code puts one, for the hard needs the reader picked: a visit only when the data
 *  says it fits every one ('ok' — what buildDay adds), a meal, a café or a stay when the data does not say 'no'
 *  (round-5 verifier: a paid museum and a place the data says nothing of for the wheelchair went in as fills). */
export function codeFits(c, f, role) {
  if (!c.needs.some((n) => HARD.includes(n))) return true;
  const st = hardState(c, f, role);
  return role === "visit" ? st === "ok" : st !== "no";
}

/** The place nearest a stop that fits `fits`, open that day at the times `slot` gives it: {page, name, m, f, open,
 *  ...slot} or null — fits(doc, page); open: opensAt's 'open' or 'check'; one with nothing to check comes first, one with something to
 *  check only when no other fits. Candidates: places of the site with a point, not in the plan, within `max` metres
 *  of `at`; ranked by rank() then distance; each one's day checked (opensAt) and, with a budget, its fee (overBudget
 *  after put()). */
export function nearestOpen({ kb, c, date, at, max, fits, rank = () => [0], slot, taken, put, limit = CANDIDATES }) {
  const list = placesOf(kb).filter((p) => !taken.has(p.page) && fits(p.doc, p.page))
    .map((p) => ({ page: p.page, name: p.doc.t, f: p.doc.f, doc: p.doc, m: metres(at, p.doc.f.g) }))
    .filter((x) => x.m <= max)
    .map((x) => ({ ...x, r: rank(x) }))
    .filter((x) => x.r !== null)
    .sort((a, b) => {
      for (let k = 0; k < a.r.length; k += 1) if (a.r[k] !== b.r[k]) return a.r[k] - b.r[k];
      return a.m - b.m || (a.name < b.name ? -1 : 1);
    })
    .slice(0, limit);
  let checked = null;
  for (const x of list) {
    for (const t of slot(x)) {
      const open = opensAt(kb, date, x.page, t.a, t.b);
      if (!open || (open === "check" && checked)) continue;
      if (put && !put({ ...x, ...t })) continue;
      if (open === "open") return { ...x, ...t, open };
      checked = { ...x, ...t, open };
    }
  }
  return checked;
}

/** Where the trip starts and ends when the reader named a station or a terminal: [{dir, name, stop, gap, url}] —
 *  gap = minutes between the hub's time (the first day's start, the last day's end) and the first or last stop. The
 *  site has no point for a hub, so its leg is a directions link by names only. hubs: plan_prompt.HUBS. */
export function hubLegs(plan, c, hubs) {
  const out = [];
  const q = encodeURIComponent;
  const first = (plan.days[0] || { stops: [] }).stops[0];
  const lastDay = plan.days[plan.days.length - 1] || { stops: [] };
  const last = [...lastDay.stops].reverse().find((s) => s.role !== "stay");
  if (c.from && first) {
    out.push({ dir: "from", name: hubs[c.from], stop: first.name, at: c.start, gap: mins(first.start) - mins(c.start),
      url: `https://map.kakao.com/?sName=${q(hubs[c.from])}&eName=${q(first.name)}` });
  }
  if (c.to && last) {
    out.push({ dir: "to", name: hubs[c.to], stop: last.name, at: c.end, gap: mins(c.end) - mins(last.end),
      url: `https://map.kakao.com/?sName=${q(last.name)}&eName=${q(hubs[c.to])}` });
  }
  return out;
}
