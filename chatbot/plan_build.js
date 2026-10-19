// The course planner's own ground rules, day builder and the check before the model (operator 2026-10-18: '이런 거 좀
// 안 뜨게 할 수 없어? 무조건 완성된 결과가 나오게 하라니까. 문제가 있으면 아예 생성 버튼 누르는 단계에서 지적을 하고'):
//   - planFlags: what is wrong with a plan, each with the day and stop it is at (planner.verify's flags, word for word);
//   - buildDay: a whole day from the site's data alone — or around the stops a day already has (the model's, kept in
//     their order) — that passes every check: places open that date by the data, inside their hours and the reader's,
//     the picked needs the data says fit (a visit's data 'ok'), at most one outdoor visit on a rainy day, a meal in its
//     window, no empty stretch, the code's margin on every leg, the station's margins, a stay at the end of a night;
//   - buildPlan: every day of the trip that way, no place twice;
//   - preflight: before any model call, whether such a plan exists; if not, the reasons in the reader's words and the
//     changes to the conditions that make one (each change checked).
// Facts only from the site's data: a stop is a place page; a time is a margin from straight-line distance, never a
// travel time; a place's day and hours are knowledge.checkPlan's reading (plan_geo.dayInfo).
import { HUBS, NEEDS, titleCity, tripDates } from "./plan_prompt.js";
import { planFees } from "./plan_fees.js";
import {
  CAMP, HARD, KEEP_MIN, MEAL_KEEP, MEAL_MIN, STAY_NEAR, STOPS_MAX, SWAP_MIN, dateWords, dayInfo, eul, fitsHours, gOf, hardState, hhmm, hubLegs, iga, ro,
  inBreak, isOutdoor, lastPoint, legFloor, stretchMax, marginOf, metres, mins, placesOf, regionOf, stayRadii,
} from "./plan_geo.js";
import {
  HUB_MARGIN, IDLE, MEALS, PREF_TYPES, completeness, eatsElsewhere, hm, isCafe, isMeal, mealIn, needAt, prefFits, readerDay, span, spans,
} from "./plan_state.js";

// a stop the code put in (by: 'site'), swapped in (by: 'swap') or moved (a night's stay: moved)
export const changed = (s) => !!(s.by || s.moved);

/** What is wrong with a plan by the site's data and the reader's conditions — the same rules and words as
 *  planner.verify: {days: [checkPlan result], list: [{day, kind, text, j?, meal?}], fees, hubs, complete}. kind:
 *  'closed' | 'hours' (a stop, j), 'leg' (the leg from stop j), 'start' | 'end' (a stop before the reader's start
 *  or after their end, j), 'stay-missing', 'stay-mid' | 'stay-ci' | 'stay-last' (j: a stay on the trip's last day),
 *  'stay-two' (j: a second stay that night), 'role' (j: a role that is not what the place is), 'need' (j: the data
 *  says 'no' to a hard need the reader picked), 'many' (more than STOPS_MAX stops), 'rain',
 *  'budget', 'hub-from' | 'hub-to' (less than HUB_MARGIN), 'meal' (meal: lunch | dinner), 'gap'. day: the day's
 *  index, or -1 for the whole trip. */
export function planFlags(plan, c, kb, edit = null) {
  const list = [];
  const days = plan.days.map((d, i) => {
    const r = kb.checkPlan({ date: d.date, stops: d.stops.map((s) => ({ page: s.page, start: s.start, end: s.end })), move: c.move });
    // checkPlan's flags in its own order: each stop's, then each leg's
    let n = 0;
    r.stops.forEach((st, j) => {
      for (const t of st.flags || []) {
        list.push({ day: i, j, kind: st.day === "closed" || /격주/u.test(t) ? "closed" : "hours", text: `${i + 1}일차 ${r.flags[n]}` });
        n += 1;
      }
    });
    for (const l of r.legs) {
      if (!l.flag) continue;
      list.push({ day: i, j: l.from, kind: "leg", text: `${i + 1}일차 ${r.flags[n]}` });
      n += 1;
    }
    const first = i === 0, lastDay = i === plan.days.length - 1;
    d.stops.forEach((s, j) => {
      if (s.role === "stay") return;
      if ((first || c.days === 1) && mins(s.start) < mins(c.start)) list.push({ day: i, j, kind: "start", text: `${i + 1}일차 ${s.name}: 독자가 정한 시작 ${c.start}보다 이르다` });
      if ((lastDay || c.days === 1) && mins(s.end) > mins(c.end)) list.push({ day: i, j, kind: "end", text: `${i + 1}일차 ${s.name}: 독자가 정한 끝 ${c.end}보다 늦다` });
    });
    // the hard needs the reader picked: a stop the data says does not fit one (round-5 verifier: a paid museum the
    // code put in for '입장료 없는 곳' was sent)
    if (c.needs.some((n) => HARD.includes(n))) {
      d.stops.forEach((s, j) => {
        const f = (kb.docs[s.page] || {}).f || {};
        if (hardState(c, f, s.role) !== "no") return;
        const need = c.needs.find((n) => HARD.includes(n) && hardState({ ...c, needs: [n] }, f, s.role) === "no");
        list.push({ day: i, j, kind: "need", text: `${i + 1}일차 ${s.name}: 고른 조건 '${NEEDS[need]}'에 맞지 않는다고 자료에 있다 — 맞는 곳으로 바꾼다` });
      });
    }
    if (d.stops.length > STOPS_MAX) list.push({ day: i, kind: "many", text: `${i + 1}일차: 장소가 ${d.stops.length}곳 — 하루 ${STOPS_MAX}곳까지로 줄인다` });
    // a stay on the trip's last day: no night follows it (round-5 verifier: a hotel at 17:30–19:30 after an 18:00 end)
    if (lastDay) {
      d.stops.forEach((s, j) => {
        if (s.role === "stay") list.push({ day: i, j, kind: "stay-last", text: `${i + 1}일차 ${s.name}: 마지막 날에는 묵는 곳이 없다 — 일정에서 뺀다` });
      });
    }
    if (!lastDay && !d.stops.some((s) => s.role === "stay")) list.push({ day: i, kind: "stay-missing", text: `${i + 1}일차: 묵을 숙소(role stay)가 없다` });
    // one stay a night; a role that is what the place is (a stay page as the stay, a meal or a café at a food page)
    d.stops.forEach((s, j) => {
      const kd = ((kb.docs[s.page] || {}).f || {}).kd;
      if (s.role === "stay" && d.stops.slice(0, j).some((x) => x.role === "stay")) list.push({ day: i, j, kind: "stay-two", text: `${i + 1}일차 ${s.name}: 그날 밤 숙소가 이미 있다 — 일정에서 뺀다` });
      if ((kd === "stay") !== (s.role === "stay") || ((s.role === "meal" || s.role === "cafe") && kd !== "food")) {
        list.push({ day: i, j, kind: "role", text: `${i + 1}일차 ${s.name}: role ${s.role}이 장소의 종류와 맞지 않는다 — 일정에서 뺀다` });
      }
    });
    // a night's stay is where the day ends: never ahead of another stop, never before its check-in time (repair 0
    // moves it when it can)
    d.stops.forEach((s, j) => {
      if (lastDay || s.role !== "stay") return;
      const ci = ((kb.docs[s.page] || {}).f || {}).ci;
      if (d.stops.slice(j + 1).some((x) => x.role !== "stay")) list.push({ day: i, j, kind: "stay-mid", text: `${i + 1}일차 ${s.name}: 밤 숙소인데 그날 마지막 장소가 아니다 — 그날 마지막에 둔다` });
      else if (ci && mins(s.start) < mins(ci)) list.push({ day: i, j, kind: "stay-ci", text: `${i + 1}일차 ${s.name}: 밤 숙소가 체크인 ${ci}보다 이른 ${s.start}에 시작한다 — 체크인 뒤로 둔다` });
    });
    // a leg next to a stop the code put in, swapped in or moved holds the code's own margin (marginOf; repair 7 widens
    // it when it can)
    for (const l of r.legs) {
      const a = d.stops[l.from], b = d.stops[l.to];
      if (l.flag || l.gap === null || a.role === "stay" || (!changed(a) && !changed(b))) continue;
      const need = marginOf(a.page, b.page, c, kb);
      if (l.gap >= need) continue;
      l.flag = `사이트가 넣거나 옮긴 곳이 있는 구간인데 여유 ${l.gap}분 — 계획 여유 ${need}분보다 짧음`;
      list.push({ day: i, j: l.from, kind: "leg", text: `${i + 1}일차 ${l.from + 1}→${l.to + 1}번 ${a.name} → ${b.name}: ${l.flag} — 여유를 늘리거나 가까운 곳으로 바꾼다` });
    }
    if (c.needs.includes("rain")) {
      const out = d.stops.filter((s) => s.role === "visit" && isOutdoor((kb.docs[s.page] || {}).f || {}));
      if (out.length > 1) list.push({ day: i, kind: "rain", text: `${i + 1}일차: '비 와도 실내 위주'인데 야외 장소가 ${out.length}곳(${out.map((s) => s.name).join("·")}) — 짧은 야외는 하루 한 곳까지` });
    }
    return r;
  });
  const fees = planFees(plan.days, c, kb, c.budget);
  if (fees.verdict === "over") {
    list.push({ day: -1, kind: "budget", text: `입장료(확인된 것만) ${fees.known.toLocaleString("en-US")}원이 예산 ${c.budget.toLocaleString("en-US")}원을 넘는다 — 무료이거나 더 싼 곳으로 바꾼다` });
  }
  const hubs = hubLegs(plan, c, HUBS);
  // the station or terminal: HUB_MARGIN after the start, before the end (round-5 verifier: a first stop a minute after
  // the train passed)
  for (const h of hubs) {
    if (h.gap >= HUB_MARGIN) continue;
    list.push(h.dir === "from"
      ? { day: 0, kind: "hub-from", text: `${h.name} ${h.at} 출발인데 첫 장소 ${h.stop}${iga(h.stop)} ${h.at} 뒤 ${HUB_MARGIN}분 안에 시작한다(${h.gap}분) — 출발지에서 오는 여유를 둔다` }
      : { day: plan.days.length - 1, kind: "hub-to", text: `${h.name}에 ${h.at}까지 가야 하는데 마지막 장소 ${h.stop}${iga(h.stop)} ${h.at} 전 ${HUB_MARGIN}분 안에 끝난다(${h.gap}분) — 돌아갈 여유를 둔다` });
  }
  const complete = completeness(plan, c, kb, edit);
  for (const m of complete.meals.filter((x) => x.state === "missing")) {
    const w = MEALS[m.kind];
    list.push({ day: m.day, kind: "meal", meal: m.kind,
      text: `${m.day + 1}일차: ${w.label} 시간(${hhmm(w.from)}~${hhmm(w.to)})이 일정 안인데 식사할 곳이 없다${m.note ? `(${m.note})` : ""} — 그 시간에 여는 음식점을 넣는다` });
  }
  for (const g of complete.gaps) {
    list.push({ day: g.day, kind: "gap", from: hm(g.from), to: hm(g.to), text: `${g.day + 1}일차: ${g.from}~${g.to} ${span(g.minutes)} 동안 들르는 곳이 없다 — 가까운 장소를 넣거나 앞뒤 장소를 늘린다` });
  }
  return { days, list, fees, hubs, complete };
}

// ------------------------------------------------------------------ the day builder
const VISIT_MIN = 45;      // a visit the code puts in: at least this, 90 when there is more to fill, up to 120 to fill a stretch whole
const VISIT_WANT = 90;
const VISIT_MAX = 120;
const CAFE_MIN = 30;
const CAFE_MAX = 60;
const FILL_FROM = 70;      // an empty stretch longer than this gets a place when one fits (the check allows IDLE)
const STAY_LATEST = 23 * 60 + 29;
const ceil5 = (x) => Math.ceil(x / 5) * 5;
const floor5 = (x) => Math.floor(x / 5) * 5;
// straight lines a place the builder adds is looked for in, nearest first: [without a car, by car]
const RADII = { transit: [1500, 3000, 6000], car: [3000, 6000, 15000] };
const radii = (c) => RADII[c.move === "car" ? "car" : "transit"];

// the hours a place keeps that date: the latest opening, the earliest closing (a line that closes the same day), the
// earliest last entry
export function windowOf(info) {
  let open = 0, close = 24 * 60, last = Infinity;
  for (const h of info.hours) {
    open = Math.max(open, h.open);
    if (h.close > h.open) close = Math.min(close, h.close);
    if (h.last !== null) last = Math.min(last, h.last);
  }
  return { open, close, last };
}
// the places a day may use on a date, once per knowledge base and date: open or to check by the data, hours read
const POOLS = new WeakMap();
function poolOf(kb, date) {
  if (!POOLS.has(kb)) POOLS.set(kb, new Map());
  const byDate = POOLS.get(kb);
  if (byDate.has(date)) return byDate.get(date);
  const pool = { visits: [], meals: [], cafes: [], stays: [] };
  for (const { page, doc } of placesOf(kb)) {
    const f = doc.f;
    if (f.kd === "stay") {
      pool.stays.push({ page, doc, f, g: f.g, camp: CAMP.test(f.ty || "") });
      continue;
    }
    const info = dayInfo(kb, date, page);
    if (!info.state || info.state === "closed" || !info.read) continue;
    const x = { page, doc, f, g: f.g, info, win: windowOf(info), region: regionOf(doc) };
    if (f.kd === "attraction") pool.visits.push(x);
    else if (f.kd === "food" && isMeal(doc)) pool.meals.push(x);
    else if (f.kd === "food" && isCafe(doc)) pool.cafes.push(x);
  }
  byDate.set(date, pool);
  return pool;
}
const fits = (x, a, b) => a >= x.win.open && b <= x.win.close && a <= x.win.last && b > a && !inBreak(x.f, a, b);

// the least a seed may be shortened to (plan_geo.keepOf, in minutes): a meal MEAL_KEEP, a place the code put in
// SWAP_MIN, else KEEP_MIN
const keepSeed = (s) => (s.role === "meal" ? Math.min(MEAL_KEEP, s.b - s.a) : s.by ? SWAP_MIN[s.role] || SWAP_MIN.visit : KEEP_MIN);
// the stops a day may still take before its night's stay (STOPS_MAX counts the stay)
const roomLeft = (ctx, stops) => STOPS_MAX - (ctx.lastDay ? 0 : 1) - stops.filter((s) => s.role !== "stay").length;

/** The stops a day already has, cleaned so that each holds on its own and with the ones next to it: a place closed
 *  that day, a stay on the trip's last day ahead of a stop, a need the data says 'no', a second outdoor visit in the
 *  rain go; times are cut to the place's hours and the reader's, then each leg gets its margin — the earlier stop
 *  ends sooner, the later starts later, each keeping keepSeed — or, when it cannot, the stop the code put in goes
 *  first, else the one farther from the rest. Returns [{...stop, a, b}] in minutes, and what went. */
function cleanSeeds(ctx, seeds) {
  const { c, kb, date } = ctx;
  const out = [];
  const gone = [];
  let outdoor = 0;
  for (const s of seeds) {
    const f = (kb.docs[s.page] || {}).f || {};
    if (s.role === "stay") continue;
    let a = hm(s.start), b = hm(s.end);
    const info = dayInfo(kb, date, s.page);
    if (info.state === "closed" || ctx.taken.has(s.page) || out.some((x) => x.page === s.page) || hardState(c, f, s.role) === "no") {
      gone.push(s);
      continue;
    }
    if (c.needs.includes("rain") && s.role === "visit" && isOutdoor(f) && (outdoor += 1) > 1) {
      gone.push(s);
      continue;
    }
    // the place's hours that date (only the lines the check reads) and the reader's bounds
    const w = windowOf(info);
    a = Math.max(a, w.open, ctx.first ? ctx.lo : 0);
    b = Math.min(b, w.close, ctx.lastDay ? ctx.hi : 24 * 60);
    if (a > w.last) a = b;   // past the last entry
    const keep = s.role === "meal" ? MEAL_KEEP : s.by ? SWAP_MIN[s.role] || SWAP_MIN.visit : KEEP_MIN;
    if (b - a < Math.min(keep, hm(s.end) - hm(s.start)) || b - a < (s.by ? keep : KEEP_MIN) || inBreak(f, a, b)) {
      gone.push(s);
      continue;
    }
    out.push({ ...s, a, b });
  }
  // no more than the day holds with its night's stay (STOPS_MAX): the code's own shortest go first, then the shortest
  while (roomLeft(ctx, out) < 0) {
    const k = out.reduce((best, x, n) => (best < 0 || Number(!!x.by) > Number(!!out[best].by)
      || (!!x.by === !!out[best].by && x.role !== "meal" && (out[best].role === "meal" || x.b - x.a < out[best].b - out[best].a)) ? n : best), -1);
    gone.push(...out.splice(k, 1));
  }
  // the legs: from the margin down to what the check allows (the code's own stops keep the whole margin)
  for (let j = 0; j + 1 < out.length;) {
    const x = out[j], y = out[j + 1];
    const need = marginOf(x.page, y.page, c, kb);
    const least = changed(x) || changed(y) ? need : legFloor(x.page, y.page, c, kb);
    let ok = y.a - x.b >= least;
    for (let g = need; !ok && g >= least; g -= 5) {
      if (y.a - x.b >= g) { ok = true; break; }
      const wy = windowOf(dayInfo(kb, date, y.page));
      // the earlier one ends sooner, then the later one starts later
      if (y.a - g - x.a >= keepSeed(x)) { x.b = Math.min(x.b, y.a - g); ok = true; break; }
      const ny = x.b + g;
      if (y.b - ny >= keepSeed(y) && ny <= wy.last && !inBreak((kb.docs[y.page] || {}).f || {}, ny, y.b)) { y.a = ny; ok = true; break; }
    }
    if (ok) { j += 1; continue; }
    // one of them goes: the code's own first, else the one farther from its other neighbour
    const far = (s, other) => (gOf(kb, s.page) && other && gOf(kb, other.page) ? metres(gOf(kb, s.page), gOf(kb, other.page)) : 0);
    const dropY = changed(y) && !changed(x) ? true : changed(x) && !changed(y) ? false : far(y, out[j + 2]) >= far(x, out[j - 1]);
    gone.push(...out.splice(dropY ? j + 1 : j, 1));
    if (j > 0) j -= 1;
  }
  return { stops: out, gone };
}

// a place for the reader's likings: 0 fits one they picked (the data can tell), 1 not
const likeRank = (ctx, x) => {
  const likes = ctx.c.prefs.filter((p) => PREF_TYPES[p] || p === "islands");
  return likes.length && likes.some((p) => prefFits(p, x.doc)) ? 0 : likes.length ? 1 : 0;
};
// rain: an indoor type first, a typed place next, a place with no type, an outdoor one last
const rainRank = (ctx, x) => {
  if (!ctx.c.needs.includes("rain")) return 0;
  const st = needAt("rain", x.f, "visit").state;
  return st === "ok" ? 0 : st === "unknown" ? (x.f.ty ? 1 : 2) : 3;
};
const feeKnown = (x) => (x.f.fee && (x.f.fee.free || x.f.fee.tab) ? 0 : 1);
function rank(ctx, x) {
  return [likeRank(ctx, x), x.info.state === "open" ? 0 : 1, rainRank(ctx, x), feeKnown(x)];
}
const byRank = (p, q) => {
  for (let k = 0; k < p.r.length; k += 1) if (p.r[k] !== q.r[k]) return p.r[k] - q.r[k];
  return p.m - q.m || (p.x.page < q.x.page ? -1 : 1);
};

// the day as checkPlan reads it: the builder's stops in minutes → the plan's stops
const asStops = (stops) => stops.map((s) => {
  const { a, b, ...rest } = s;
  return { ...rest, start: hhmm(a), end: hhmm(b) };
});
// a plan with day i as the builder has it (for the fee and the check)
const withDay = (ctx, stops) => ({ ...ctx.plan, days: ctx.plan.days.map((d, k) => (k === ctx.i ? { date: ctx.date, stops: asStops(stops) } : d)) });
function feeOk(ctx, stops) {
  const { c, kb } = ctx;
  if (c.budget === null || c.budget === undefined) return true;
  const f = planFees(withDay(ctx, stops).days, c, kb, c.budget);
  return f.verdict !== "over";
}
function outdoorUsed(ctx, stops) {
  return stops.some((s) => s.role === "visit" && isOutdoor((ctx.kb.docs[s.page] || {}).f || {}));
}
// whether a place may go in as a visit the code adds: not in the trip, every hard need the data says fits, the
// rain's one outdoor visit, its fee within the budget (checked when placed)
function visitOk(ctx, stops, x) {
  if (ctx.taken.has(x.page) || stops.some((s) => s.page === x.page)) return false;
  if (hardState(ctx.c, x.f, "visit") !== "ok") return false;
  if (ctx.c.needs.includes("rain") && isOutdoor(x.f) && outdoorUsed(ctx, stops)) return false;
  return true;
}
// a restaurant may go in when it is in no day of the trip and the data does not say 'no' to a need (round-5: a
// restaurant of another day is no longer a last resort — the spec's 'no repeats across days')
const mealOk = (ctx, stops, x) => !ctx.taken.has(x.page) && !stops.some((s) => s.page === x.page) && hardState(ctx.c, x.f, "meal") !== "no";

/** A visit for the stretch between stops k-1 and k (P, N; either may be missing — the day's ends): the place nearest
 *  the stop next to it that fits, open from the leg's margin after P (or from the stretch's start) until the margin
 *  before N (or the stretch's end) for VISIT_MIN–VISIT_MAX minutes. dir 'before': it ends at the margin before N. */
function pickVisit(ctx, stops, k, from, until, cafe = false) {
  const { c, kb } = ctx;
  const P = stops[k - 1] || null, N = stops[k] || null;
  const at = (P && gOf(kb, P.page)) || (N && gOf(kb, N.page)) || ctx.anchor;
  const dir = P ? "after" : "before";
  const list = cafe ? ctx.pool.cafes : ctx.pool.visits;
  const role = cafe ? "cafe" : "visit";
  for (const R of at ? radii(c) : [Infinity]) {
    const cands = list.filter((x) => (cafe ? mealOk(ctx, stops, x) : visitOk(ctx, stops, x)))
      .map((x) => ({ x, m: at ? metres(at, x.g) : 0 }))
      .filter((y) => y.m <= R)
      .map((y) => ({ ...y, r: at ? rank(ctx, y.x) : [...rank(ctx, y.x), -density(ctx, y.x)] }))
      .sort(byRank)
      .slice(0, 40);
    for (const { x } of cands) {
      const mP = P ? marginOf(P.page, x.page, c, kb) : 0;
      const mN = N ? marginOf(x.page, N.page, c, kb) : 0;
      const a0 = ceil5(Math.max(from + mP, x.win.open));
      const bMax = floor5(Math.min(until - mN, x.win.close));
      const room = bMax - a0;
      const min = cafe ? CAFE_MIN : VISIT_MIN;
      if (room < min || a0 > x.win.last) continue;
      // (frugal: a trip whose later days run short of places spends fewer — longer visits, 2 hours, up to 3 to fill)
      let d = cafe ? Math.min(CAFE_MAX, room) : ctx.frugal ? Math.min(room, room <= 180 ? room : 120) : room <= VISIT_MAX ? room : VISIT_WANT;
      d = floor5(d);
      let a = a0, b = a0 + d;
      if (dir === "before") { b = bMax; a = Math.max(a0, b - d); }
      if (!fits(x, a, b)) continue;
      const stop = { page: x.page, name: x.doc.t, a, b, role, why: "", by: "site" };
      const next = [...stops.slice(0, k), stop, ...stops.slice(k)];
      if (x.f.fee && x.f.fee.tab && !feeOk(ctx, next)) continue;
      return { stop, next };
    }
  }
  return null;
}
// how many places to visit or eat at are near a place (where a day without a stop of its own starts)
function density(ctx, x) {
  const R = radii(ctx.c)[0];
  return [...ctx.pool.visits, ...ctx.pool.meals].filter((y) => metres(x.g, y.g) <= R).length;
}

/** The stretches of the day with no stop, as the check reads them (plan_state.idleGaps on the reader's day). */
function stretches(ctx, stops) {
  const out = [];
  let t = ctx.lo;
  stops.forEach((s, k) => {
    if (s.a > t) out.push({ k, from: t, to: s.a });
    t = Math.max(t, s.b);
  });
  if (ctx.hi > t) out.push({ k: stops.length, from: t, to: ctx.hi });
  return out;
}

/** Each stretch longer than FILL_FROM gets the visits that fit, nearest the stop before it first; a stretch longer
 *  than IDLE that nothing fits gets a café, then the stop next to it lengthened (within its hours, under
 *  plan_geo.stretchMax). Changes stops; returns whether every stretch is within IDLE. */
function fillStretches(ctx, stops) {
  const dead = new Set();
  // frugal: the stops lengthen first (to FILL_FROM), then the places go in
  if (ctx.frugal) lengthen(ctx, stops, FILL_FROM);
  for (let guard = 0; guard < 24 && roomLeft(ctx, stops) > 0; guard += 1) {
    const g = stretches(ctx, stops).find((x) => x.to - x.from > FILL_FROM && !dead.has(`${x.from}-${x.to}`));
    if (!g) break;
    const pick = pickVisit(ctx, stops, g.k, g.from, g.to) || (g.to - g.from > IDLE ? pickVisit(ctx, stops, g.k, g.from, g.to, true) : null);
    if (pick) stops.splice(0, stops.length, ...pick.next);
    else dead.add(`${g.from}-${g.to}`);
  }
  // what is still longer than IDLE: lengthen the stop before it (then the one after it)
  lengthen(ctx, stops);
  return stretches(ctx, stops).every((x) => x.to - x.from <= IDLE);
}
// each stretch longer than `most` (IDLE): the stop before it ends later (its hours, plan_geo.stretchMax), then the one
// after it starts sooner
function lengthen(ctx, stops, most = IDLE) {
  for (const g of stretches(ctx, stops).filter((x) => x.to - x.from > most)) {
    const P = stops[g.k - 1], N = stops[g.k];
    let need = g.to - g.from - most;
    if (P && P.role !== "stay") {
      const w = windowOf(dayInfo(ctx.kb, ctx.date, P.page));
      const lim = Math.min(w.close, P.a + stretchMax(P), N ? N.a - marginOf(P.page, N.page, ctx.c, ctx.kb) : g.to);
      const nb = Math.min(lim, P.b + need);
      if (nb > P.b && !inBreak((ctx.kb.docs[P.page] || {}).f || {}, P.a, nb)) { need -= nb - P.b; P.b = nb; }
    }
    if (need > 0 && N && N.role !== "stay") {
      const w = windowOf(dayInfo(ctx.kb, ctx.date, N.page));
      const lim = Math.max(w.open, N.b - stretchMax(N), P ? P.b + marginOf(P.page, N.page, ctx.c, ctx.kb) : g.from, ctx.first ? ctx.lo : 0);
      const na = Math.max(lim, N.a - need);
      if (na < N.a && na <= w.last && !inBreak((ctx.kb.docs[N.page] || {}).f || {}, na, N.b)) N.a = na;
    }
  }
}

/** A meal for the day (MEALS[kind]) where none is: every place between two stops (or the day's ends) the meal's window
 *  reaches, the restaurants nearest the stop before it (then after it), each start from the window's first to its
 *  last, nearest the aim first; the stop before may end sooner and the one after start later (each keeping its
 *  least: KEEP_MIN, a meal 45, one the code added VISIT_MIN). When no place has room, a visit inside the window — the
 *  code's own first — gives up its place. Changes stops; returns whether the meal went in. */
function placeMeal(ctx, stops, kind, depth = 0) {
  const { c, kb } = ctx;
  const m = MEALS[kind];
  const least = (s) => (s.role === "meal" ? Math.min(MEAL_KEEP, s.b - s.a) : s.by ? VISIT_MIN : Math.min(KEEP_MIN, s.b - s.a));
  // the starts a meal may take: its window (m.first–m.last), then any whose middle falls where the check counts that
  // meal (m.near) — an edit's dinner on a day that ends at 18:00 (round-5 verifier: such edits were refused)
  const early = ceil5(m.near[0] - MEAL_KEEP / 2), late = floor5(m.near[1] - MEAL_KEEP / 2 - 1);
  let best = null;
  for (let k = 0; k <= stops.length && roomLeft(ctx, stops) > 0; k += 1) {
    const P = stops[k - 1] || null, N = stops[k] || null;
    // the day's ends: the reader's start on the first day (else the day may start earlier) and their end on the last
    // (else it runs to ctx.top — a night's stay follows it), as the check reads them
    const pLo = P ? P.a + least(P) : ctx.bottom;
    const nHi = N ? N.b - least(N) : ctx.top;
    if (Math.min(late, nHi - MEAL_KEEP) < Math.max(early, pLo)) continue;
    // the restaurants nearest the stop before the slot or the one after it (either may be far out)
    const pts = [P && gOf(kb, P.page), N && gOf(kb, N.page)].filter(Boolean);
    if (!pts.length && ctx.anchor) pts.push(ctx.anchor);
    const wN = N ? windowOf(dayInfo(kb, ctx.date, N.page)) : null;
    for (const R of pts.length ? radii(c) : [Infinity]) {
      const cands = ctx.pool.meals.filter((x) => mealOk(ctx, stops, x)).map((x) => ({ x, m: pts.length ? Math.min(...pts.map((g) => metres(g, x.g))) : 0 }))
        .filter((y) => y.m <= R).sort((p, q) => p.m - q.m || (p.x.page < q.x.page ? -1 : 1)).slice(0, 25);
      for (const { x, m: dist } of cands) {
        const mP = P ? marginOf(P.page, x.page, c, kb) : 0;
        const mN = N ? marginOf(x.page, N.page, c, kb) : 0;
        // an hour, or 45 minutes where an hour does not fit
        for (const len of [MEAL_MIN, MEAL_KEEP]) {
          for (let s = early; s <= late; s += 5) {
            const mid = s + len / 2;
            if (mid < m.near[0] || mid >= m.near[1] || !fits(x, s, s + len)) continue;
            const pEnd = P ? Math.min(P.b, s - mP) : null;
            if (P ? pEnd < pLo : s < ctx.bottom) continue;
            const nStart = N ? Math.max(N.a, s + len + mN) : null;
            if (N ? nStart > nHi || nStart > wN.last || inBreak(((kb.docs[N.page] || {}).f) || {}, nStart, N.b) : s + len > ctx.top) continue;
            const cut = (P ? P.b - pEnd : 0) + (N ? nStart - N.a : 0);
            const out = s < m.first || s > m.last ? 2000 : 0;   // outside the meal's own window: only when nothing inside fits
            const cost = out + (cut ? 1000 + cut : 0) + (len < MEAL_MIN ? 500 : 0) + Math.abs(s - m.at) + dist / 100;
            if (!best || cost < best.cost) best = { cost, k, x, s, len, pEnd, nStart };
          }
        }
      }
      if (best && best.k === k) break;   // the nearest ring that has one
    }
  }
  if (best) {
    const P = stops[best.k - 1], N = stops[best.k];
    if (P) P.b = best.pEnd;
    if (N) N.a = best.nStart;
    stops.splice(best.k, 0, { page: best.x.page, name: best.x.doc.t, a: best.s, b: best.s + best.len, role: "meal", why: "", by: "site" });
    return true;
  }
  if (depth >= 2) return false;
  // a visit inside the meal's window gives up its place: the code's own first, nearest the aim
  const inWin = stops.map((s, k) => ({ s, k })).filter(({ s }) => s.role !== "stay" && s.role !== "meal" && s.a < m.near[1] && s.b > m.near[0])
    .sort((p, q) => Number(!p.s.by) - Number(!q.s.by) || Math.abs(p.s.a - m.at) - Math.abs(q.s.a - m.at));
  for (const { k } of inWin) {
    const was = stops.splice(k, 1)[0];
    if (placeMeal(ctx, stops, kind, depth + 1)) return true;
    stops.splice(k, 0, was);
  }
  return false;
}

/** A night's stay after the day's last stop: the stay given (the plan's, kept when it can start by 23:29 after the
 *  leg's margin and not before its check-in time), else the other nights' stay when near enough, else the nearest
 *  that can (hotels, motels and guesthouses before camps), within STAY_NEAR first and farther only when none can. */
function placeStay(ctx, stops) {
  const { c, kb } = ctx;
  const last = stops.at(-1);
  if (!last) return null;
  const startOf = (page) => {
    const ci = mins(((kb.docs[page] || {}).f || {}).ci);
    const a = Math.max(last.b + marginOf(last.page, page, c, kb), ci ?? 0);
    return a <= STAY_LATEST ? a : null;
  };
  const okStay = (page) => hardState(c, (kb.docs[page] || {}).f || {}, "stay") !== "no";
  for (const s of [ctx.stay, ctx.otherStay].filter(Boolean)) {
    const a = startOf(s.page);
    const lp = lastPoint(kb, stops);
    const near = !lp || !gOf(kb, s.page) || metres(lp, gOf(kb, s.page)) <= STAY_NEAR;
    if (a !== null && okStay(s.page) && (s === ctx.stay || near)) {
      return { page: s.page, name: s.name, a, b: Math.min(a + 60, 23 * 60 + 59), role: "stay", why: s.why || "", ...(s === ctx.stay && !s.by ? { moved: true } : { by: "site" }) };
    }
  }
  const at = lastPoint(kb, stops);
  if (!at) return null;
  const list = ctx.pool.stays.filter((x) => okStay(x.page)).map((x) => ({ x, m: metres(at, x.g) }))
    .sort((p, q) => p.x.camp - q.x.camp || p.m - q.m || (p.x.page < q.x.page ? -1 : 1));
  for (const R of stayRadii(kb.docs[last.page])) {   // never unlimited on an island (QA 2026-10-19 QA-09)
    for (const { x } of list.filter((y) => y.m <= R)) {
      const a = startOf(x.page);
      if (a !== null) return { page: x.page, name: x.doc.t, a, b: Math.min(a + 60, 23 * 60 + 59), role: "stay", why: "", by: "site" };
    }
  }
  return null;
}

/** The flags of day i of a plan with that day as the builder has it — the trip-wide budget too. */
function dayFlags(ctx, stops) {
  const plan = withDay(ctx, stops);
  const r = planFlags(plan, ctx.c, ctx.kb, ctx.edit);
  return r.list.filter((x) => x.day === ctx.i || x.day === -1);
}

/** The meals day i must have: each lunch or dinner its reader's day spans (or, on an edit, the plan before had), unless
 *  the reader eats elsewhere. */
function mealsFor(ctx, stops) {
  const plan = withDay(ctx, stops);
  const day = readerDay(plan, ctx.c, ctx.i, ctx.kb) || { lo: ctx.lo, hi: ctx.hi };
  const lo = Math.min(day.lo, ctx.lo), hi = Math.max(day.hi, ctx.hi);
  const before = ctx.edit && ctx.edit.plan.days[ctx.i] ? ctx.edit.plan.days[ctx.i].stops : [];
  return ["lunch", "dinner"].filter((kind) => (spans({ lo, hi }, MEALS[kind]) || mealIn(before, MEALS[kind], ctx.kb))
    && !eatsElsewhere(kind, ctx.c.note, ctx.edit && ctx.edit.request));
}

// the latest a stop before a night's stay may end (the stay itself starts by 23:29)
const NIGHT_TOP = 21 * 60;
/** A day's bounds as the check reads them (planner.verify, plan_state.readerDay): the reader's start holds on the first
 *  day only and their end on the last only (round-5 verifier: the builder held every day to both, and refused edits
 *  the check passes). lo–hi: the stretch the builder fills (the first day from the start after the station's margin,
 *  a later day from opts.lo when given, the last day to the end before the station's margin, any other to the end);
 *  bottom–top: where a stop may go at all (a later day may start before lo, a day before a night end after hi, up to
 *  NIGHT_TOP). */
function makeCtx(c, kb, i, date, opts) {
  const lastDay = i === c.days - 1;
  const lo = i === 0 ? hm(c.start) + (c.from ? HUB_MARGIN : 0) : Math.max(hm(c.start), opts.lo || 0);
  const hi = hm(c.end) - (lastDay && c.to ? HUB_MARGIN : 0);
  return {
    c, kb, i, date, lastDay, first: i === 0, edit: opts.edit || null,
    lo, hi, bottom: i === 0 ? lo : 6 * 60, top: lastDay ? hi : Math.max(hi, NIGHT_TOP),
    pool: poolOf(kb, date), taken: opts.taken || new Set(), anchor: opts.anchor || null,
    stay: opts.stay || null, otherStay: opts.otherStay || null,
    plan: opts.plan || { days: tripDates(c.date, c.days).map((d) => ({ date: d, stops: [] })) }, frugal: !!opts.frugal,
  };
}

// the first stop of a day with none of its own: at the day's start (or the place's opening), 90 minutes or what the
// place's hours and the day leave; null when that is under VISIT_MIN, past its last entry or over the budget
function firstStop(ctx, x) {
  const a = ceil5(Math.max(ctx.lo, x.win.open));
  const room = floor5(Math.min(x.win.close, ctx.hi) - a);
  if (room < VISIT_MIN || a > x.win.last || inBreak(x.f, a, a + Math.min(VISIT_WANT, room))) return null;
  const stop = { page: x.page, name: x.doc.t, a, b: a + Math.min(VISIT_WANT, room), role: "visit", why: "", by: "site" };
  if (x.f.fee && x.f.fee.tab && !feeOk(ctx, [stop])) return null;
  return stop;
}
// how many restaurants that serve a meal are open that date within the first ring of a place
function mealsNear(ctx, x) {
  const R = radii(ctx.c)[1];
  return ctx.pool.meals.filter((y) => metres(x.g, y.g) <= R).length;
}
/** The places a day with no stop of its own may start at, best first and each another 권역 (or place with none) while
 *  there are: the reader's likings first, near the night's stay before it (else where most places are), with a
 *  restaurant near, sure to be open, indoors on a rainy day, a known fee; then the same without the likings, then the
 *  places where most others are (the town's centre) — so a day the likings or the night's stay lead nowhere still
 *  gets its tries. Each can start there (firstStop). */
function firstsOf(base, tries) {
  const ok = base.pool.visits.filter((x) => visitOk(base, [], x) && firstStop(base, x));
  const near = (x) => (base.anchor ? Math.floor(metres(base.anchor, x.g) / 3000) : 0);
  const dense = new Map(ok.map((x) => [x.page, density(base, x)]));
  const fed = new Map(ok.map((x) => [x.page, mealsNear(base, x) ? 0 : 1]));
  const order = (keys) => ok.map((x) => ({ x, m: 0, r: keys(x) })).sort(byRank).map((y) => y.x);
  const r = (x) => rank(base, x);
  const lists = [
    order((x) => [r(x)[0], fed.get(x.page), near(x), ...r(x).slice(1), -dense.get(x.page)]),
    order((x) => [fed.get(x.page), near(x), ...r(x).slice(1), -dense.get(x.page)]),
    order((x) => [fed.get(x.page), -dense.get(x.page), ...r(x).slice(1)]),
  ];
  const out = [];
  const per = [Math.ceil(tries / 2), Math.ceil(tries / 4), tries];
  lists.forEach((list, t) => {
    const regions = new Set(out.map((x) => x.region));
    let n = 0;
    for (const x of list) {
      if (out.length >= tries || n >= per[t]) break;
      if (out.includes(x) || (regions.has(x.region) && list.some((y) => !out.includes(y) && !regions.has(y.region)))) continue;
      regions.add(x.region);
      out.push(x);
      n += 1;
    }
  });
  return out;
}

/** One day built in code: {stops, kept, gone} — stops as the plan has them (start/end), kept: the seeds still in it,
 *  gone: the seeds taken out — or null when no such day passes the check. opts: seed (the day's stops, kept as far
 *  as they hold), taken (the pages of the trip's other days), plan (the trip, for the budget and the check), edit,
 *  anchor (where the day starts: the night's stay before it), stay (the night's stay to keep), otherStay (the
 *  trip's other stay), tries (first stops tried when the day has none). */
export function buildDay(c, kb, i, date, opts = {}) {
  const seed = (opts.seed || []).filter((s) => s.role !== "stay");
  // a later day keeps no start of the reader's (the check holds it to the first day): its seeds' own start, else the
  // reader's start, then 09:00, 10:00, 11:00 — a long day that the places that fit cannot fill from 07:00 may from 10:00
  // (round-5 verifier: such conditions were refused)
  const s0 = hm(c.start), e0 = hm(c.end);
  if (seed.length) {
    // the seeds as they are, then without the one farthest from the rest (up to three tries, one left out each): a
    // place across the city from the others leaves a leg whose margin is itself longer than an empty stretch may be
    // (an edit that left 불주사 대웅전 30 km from the rest of its day could not be settled otherwise)
    const far = (x) => {
      const g = gOf(kb, x.page);
      if (!g) return 0;
      const d = seed.filter((y) => y !== x && gOf(kb, y.page)).map((y) => metres(g, gOf(kb, y.page)));
      return d.length ? Math.min(...d) : 0;
    };
    const lone = seed.filter((x) => far(x) > radii(c)[0]).sort((x, y) => far(y) - far(x)).slice(0, 3);
    for (const sd of [seed, ...lone.map((x) => seed.filter((y) => y !== x))]) {
      const lo = i === 0 ? 0 : Math.min(...sd.map((s) => hm(s.start)));
      const day = buildFrom(c, kb, i, date, { ...opts, lo }, sd);
      if (day) {
        const kept = seed.filter((s) => day.stops.some((x) => x.page === s.page));
        return { ...day, kept, gone: seed.filter((s) => !kept.includes(s)) };
      }
    }
    return null;
  }
  for (const lo of i === 0 ? [0] : [s0, ...[540, 600, 660].filter((t) => t > s0 && e0 - t >= 180)]) {
    const day = buildFrom(c, kb, i, date, { ...opts, lo }, seed);
    if (day) return day;
  }
  return null;
}
function buildFrom(c, kb, i, date, opts, seed) {
  const base = makeCtx(c, kb, i, date, opts);
  // opts.trace: an array the tries that fail are said in (a debugging aid)
  const trace = (first, why, stops, flags = [], meal = "") => opts.trace && opts.trace.push({ first: first ? first.doc.t : "(seed)", why, meal, lo: hhmm(base.lo),
    stops: asStops(stops).map((s) => `${s.start}-${s.end} ${s.role} ${s.name}`), flags: flags.map((x) => x.text), kinds: flags.map((x) => x.kind) });
  const firsts = seed.length ? [null] : firstsOf(base, opts.tries || 8);
  if (!firsts.length) {
    if (opts.trace) opts.trace.push({ first: "", why: "none", lo: hhmm(base.lo), stops: [], flags: [], kinds: [] });
    return null;
  }
  for (const first of seed.length ? [null] : firsts) {
    const ctx = { ...base };
    const stops = first ? [firstStop(ctx, first)] : cleanSeeds(ctx, seed).stops;
    // meals first (their windows are fixed), then the empty stretches, then the night's stay
    let ok = "";
    for (const kind of mealsFor(ctx, stops)) {
      if (!mealIn(asStops(stops), MEALS[kind], kb) && !placeMeal(ctx, stops, kind)) { ok = kind; break; }
    }
    if (ok) { trace(first, "meal", stops, [], ok); continue; }
    if (!stops.length) { trace(first, "empty", stops); continue; }
    fillStretches(ctx, stops);
    // a meal the stretches made needed (a day that now spans it)
    for (const kind of mealsFor(ctx, stops)) if (!mealIn(asStops(stops), MEALS[kind], kb)) placeMeal(ctx, stops, kind);
    if (!ctx.lastDay) {
      const stay = placeStay(ctx, stops);
      if (!stay) { trace(first, "stay", stops); continue; }
      stops.push(stay);
    }
    let flags = dayFlags(ctx, stops);
    // what the check still finds: a stretch (lengthen, fill), a stop the code put in that it flags (out, then fill)
    for (let n = 0; flags.length && n < 3; n += 1) {
      const bad = new Set(flags.filter((x) => x.j !== undefined && ["closed", "hours", "leg"].includes(x.kind)).map((x) => stops[x.j]).filter((s) => s && s.by && s.role !== "stay"));
      if (bad.size) stops.splice(0, stops.length, ...stops.filter((s) => !bad.has(s)));
      const stay = stops.at(-1) && stops.at(-1).role === "stay" ? stops.pop() : null;
      for (const kind of mealsFor(ctx, stops)) if (!mealIn(asStops(stops), MEALS[kind], kb)) placeMeal(ctx, stops, kind);
      fillStretches(ctx, stops);
      if (stay || !ctx.lastDay) {
        const again = placeStay(ctx, stops);
        if (again) stops.push(again);
      }
      flags = dayFlags(ctx, stops);
    }
    if (flags.length) { trace(first, "flags", stops, flags); continue; }
    const kept = seed.filter((s) => stops.some((x) => x.page === s.page));
    return { stops: asStops(stops), kept, gone: seed.filter((s) => !kept.includes(s)) };
  }
  return null;
}

/** Every day of a trip built in code (buildDay with no seed): {plan, failed: null} or {plan: null, failed: day index,
 *  taken: the pages of the days before it}; trace (an array): the failing day's tries, why each failed.
 *  No place twice; a day after a night starts near that night's stay; the trip's nights share a stay when it is near
 *  enough. title and summary are the code's, from the data only (codeText). */
export function buildPlan(c, kb, edit = null, trace = null, frugal = false) {
  const dates = tripDates(c.date, c.days);
  const plan = { title: "", summary: "", notes: [], days: dates.map((date) => ({ date, stops: [] })) };
  for (let i = 0; i < dates.length; i += 1) {
    const taken = new Set(plan.days.flatMap((d) => d.stops.map((s) => s.page)));
    const prevStay = i > 0 ? plan.days[i - 1].stops.find((s) => s.role === "stay") : null;
    if (trace) trace.length = 0;   // the failing day's tries only
    const day = buildDay(c, kb, i, dates[i], { taken, plan, edit, anchor: prevStay ? gOf(kb, prevStay.page) : null, otherStay: prevStay, trace, frugal });
    // a later day that runs short of places: the trip again, spending fewer places a day (longer visits)
    if (!day) return i > 0 && !frugal ? buildPlan(c, kb, edit, trace, true) : { plan: null, failed: i, taken };
    plan.days[i] = { date: dates[i], stops: day.stops };
  }
  Object.assign(plan, codeText(plan, c, kb));
  return { plan, failed: null };
}

/** A title and a summary the code writes from the data alone (a plan with no words of the model's): the date, the
 *  trip's length, the 권역 its pages name and the places' own names. */
export function codeText(plan, c, kb) {
  const title = `${dateWords(c.date)} ${titleCity()}${c.days > 1 ? `${c.days - 1}박 ${c.days}일` : "하루"} 코스`;
  const parts = plan.days.map((d, i) => {
    const own = d.stops.filter((s) => s.role !== "stay");
    const visits = own.filter((s) => s.role === "visit").map((s) => s.name);
    const meals = own.filter((s) => s.role === "meal").map((s) => s.name);
    const cafes = own.filter((s) => s.role === "cafe").map((s) => s.name);
    const regions = [...new Set(own.map((s) => regionOf(kb.docs[s.page])).filter(Boolean))];
    const where = regions.length ? `${regions.join(", ")} 권역에서 ` : "";   // ('○○·△△' may be one 권역's name)
    const head = plan.days.length > 1 ? `${i + 1}일차는 ` : "";
    const seen = visits.slice(0, 3);
    const what = `${seen.join("·")}${visits.length > 3 ? " 등" : ""}`;
    // each clause [joined, last]: what is seen, where they eat, the café (round-5 verifier: a day of one café had no
    // summary)
    const bits = [visits.length && [`${what}${visits.length > 3 ? "을" : eul(seen.at(-1))} 둘러보고`, `${what}${visits.length > 3 ? "을" : eul(seen.at(-1))} 둘러봐요`],
      meals.length && [`${meals.join("·")}에서 식사하고`, `${meals.join("·")}에서 식사해요`],
      cafes.length && [`${cafes.join("·")}에서 쉬고`, `${cafes.join("·")}에서 쉬어요`]].filter(Boolean);
    if (!bits.length) return "";
    return `${head}${where}${[...bits.slice(0, -1).map((b) => b[0]), bits.at(-1)[1]].join(" ")}.`;
  }).filter(Boolean);
  const summary = parts.join(" ").slice(0, 300) || `${title}예요.`;
  return { title, summary };
}

// ------------------------------------------------------------------ before the model: the conditions themselves
const md = dateWords;
const shift = (iso, n) => new Date(Date.parse(`${iso}T12:00:00Z`) + n * 86400000).toISOString().slice(0, 10);
const won = (n) => `${n.toLocaleString("en-US")}원`;

/** Whether a plan can be made for these conditions at all, before any model call (operator 2026-10-18: '문제가 있으면
 *  아예 생성 버튼 누르는 단계에서 지적을 하고'): [] when buildPlan makes every day — then the pipeline always ends with a
 *  plan that has nothing flagged (planner.settle falls back to buildDay and buildPlan) —; else [{field, text, fixes:
 *  [{label, set?, focus?}]}]: field, the condition to change (a key of the conditions); text, the cause in the reader's
 *  words (해요체) for that date and the site's data; each fix's set (full new values of condition fields, as
 *  validConditions reads them) makes buildPlan pass — checked here, and by opts.valid (planner.validConditions) when
 *  given; focus, the field the reader is to choose. Pure code: buildPlan once when it passes. opts: today (YYYY-MM-DD
 *  in Korea), daysAhead (the dates a fix may offer), valid. The handler runs it for a new plan only (an edit changes a
 *  plan made for these conditions). */
export function preflight(c, kb, now = new Date(), edit = null, opts = {}) {
  const trace = [];
  const built = buildPlan(c, kb, edit, trace);
  if (built.plan) return [];
  return diagnose(c, kb, now, edit, built, trace, opts);
}

// a refusal's reasons build the trip again for each change they offer: no more than this many builds or this long
// (round-5 verifier: up to a second of the server's time for one refusal); a change not checked is not offered
const DIAG_RUNS = 24;
const NOTE_MAX = 200;   // planner PLAN_LIMITS.noteChars: a fix's note stays a note the server takes
const eun = (w) => (jongOf(w) ? "은" : "는");
const jongOf = (w) => { const c = String(w).slice(-1).charCodeAt(0) - 0xac00; return c >= 0 && c < 11172 ? c % 28 : 0; };
// the note leaves out every meal it is for (eatsElsewhere reads it as the planner will)
const eatsAll = (note, kinds) => kinds.every((k) => eatsElsewhere(k, note));
const DIAG_MS = 300;
const BUDGET_MAX = 1000000;

function diagnose(c, kb, now, edit, built, trace, opts) {
  const t0 = Date.now();
  const memo = new Map();
  let runs = 0;
  const passes = (patch) => {
    const key = JSON.stringify(patch);
    if (memo.has(key)) return memo.get(key);
    if (runs >= DIAG_RUNS || Date.now() - t0 > DIAG_MS) return false;
    const next = { ...c, ...patch };
    let ok = true;
    if (opts.valid) { try { opts.valid(next); } catch { ok = false; } }
    if (ok) { runs += 1; ok = !!buildPlan(next, kb, edit).plan; }
    memo.set(key, ok);
    return ok;
  };
  const failed = built.failed;
  const dates = tripDates(c.date, c.days);
  const date = dates[failed];
  const when = c.days > 1 ? `${failed + 1}일차 ${md(date)}` : md(date);
  const today = opts.today || new Date(now.getTime() + 9 * 3600e3).toISOString().slice(0, 10);
  const lastDate = shift(today, opts.daysAhead ?? 180);
  const pool = poolOf(kb, date);
  const rain = c.needs.includes("rain");
  const hard = c.needs.filter((n) => HARD.includes(n));
  const why = new Set(trace.flatMap((t) => (t.why === "flags" ? t.kinds : [t.why])));
  const taken = built.taken || new Set();
  // the places to visit open that date the builder may use for the needs picked: the data says each hard need fits,
  // and in the rain not outdoors — one outdoor place a day still may (round-5 verifier: the count left it out)
  const okHard = pool.visits.filter((x) => hardState(c, x.f, "visit") === "ok");
  const fitAll = okHard.filter((x) => !rain || !isOutdoor(x.f));
  const fitN = fitAll.length + (rain && okHard.some((x) => isOutdoor(x.f)) ? 1 : 0);
  const used = fitAll.filter((x) => taken.has(x.page)).length;
  const theDay = failed > 0 ? `${failed + 1}일차를` : "하루를";
  const hardWords = hard.map((n) => `'${NEEDS[n]}'`).join("·");
  const needWords = [...hard, ...(rain ? ["rain"] : [])].map((n) => `'${NEEDS[n]}'`).join("·");
  const span = failed === 0 ? `${c.start}~${c.end}` : `${c.end}까지`;
  const fix = (label, set) => ({ label, set });
  const groups = [];   // [{field, fixes}] in the order offered
  const group = (field, fixes) => { if (fixes.length) groups.push({ field, fixes }); };

  // the changes, each checked: the needs, the budget, the way they move, the trip's length, the hours, the stations
  if (hard.length || rain) {
    const all = [...hard, ...(rain ? ["rain"] : [])];
    const fixes = all.filter((n) => passes({ needs: c.needs.filter((x) => x !== n) }))
      .map((n) => fix(`'${NEEDS[n]}' 조건 빼기`, { needs: c.needs.filter((x) => x !== n) }));
    if (!fixes.length && all.length > 1 && passes({ needs: c.needs.filter((x) => !all.includes(x)) })) {
      fixes.push(fix(`${needWords} 조건 빼기`, { needs: c.needs.filter((x) => !all.includes(x)) }));
    }
    group("needs", fixes);
  }
  if (c.budget !== null && c.budget !== undefined) {
    const up = [...new Set([c.budget * 2, c.budget + 10000, c.budget + 30000].map((x) => Math.min(BUDGET_MAX, Math.max(5000, Math.ceil(x / 5000) * 5000))))]
      .filter((x) => x > c.budget);
    const ok = up.find((b) => passes({ budget: b }));
    group("budget", [...(ok ? [fix(`예산 ${won(ok)}으로`, { budget: ok })] : []), ...(passes({ budget: null }) ? [fix("예산 정하지 않기", { budget: null })] : [])]);
  }
  if (c.move === "transit") group("move", passes({ move: "car" }) ? [fix("자가용으로 바꾸기", { move: "car" })] : []);
  if (c.days > 1 && failed > 0) {
    for (let days = failed; days >= 1; days -= 1) {
      if (passes({ days })) { group("days", [fix(`${days > 1 ? `${days - 1}박 ${days}일` : "당일"}로 줄이기`, { days })]); break; }
    }
  }
  {
    const s0 = hm(c.start), e0 = hm(c.end);
    const starts = [], ends = [];
    for (const start of ["09:00", "10:00", "11:00", "12:00"].filter((t) => hm(t) > s0 && e0 - hm(t) >= 180)) {
      if (passes({ start })) { starts.push(fix(`시작을 ${start}${ro(start)}`, { start })); break; }
    }
    for (const end of ["20:00", "19:00", "18:00", "17:00", "16:00"].filter((t) => hm(t) < e0 && hm(t) >= 15 * 60 && hm(t) - s0 >= 180)) {
      if (passes({ end })) { ends.push(fix(`끝을 ${end}${ro(end)}`, { end })); break; }
    }
    group("start", starts);
    group("end", ends);
    if (c.from) group("from", passes({ from: "" }) ? [fix(`출발을 ${HUBS[c.from]}${ro(HUBS[c.from])} 두지 않기`, { from: "" })] : []);
    if (c.to) group("to", passes({ to: "" }) ? [fix(`도착을 ${HUBS[c.to]}${ro(HUBS[c.to])} 두지 않기`, { to: "" })] : []);
  }

  // the cause, in the reader's words: one field — that field's reason from the data and the builder's own failure;
  // several — the conditions together, as none of them alone is the cause (round-5 verifier: '25곳뿐이라' beside a
  // budget and an hours problem, each of which alone made a plan)
  const missed = [...new Set(trace.filter((t) => t.why === "meal").map((t) => MEALS[t.meal].label))].join("·");
  const one = {
    needs: () => (why.has("stay") && !why.has("meal") && failed < c.days - 1 && hard.length
      ? `${when} 밤에 ${hardWords} 조건에 맞지 않는다고 자료에 있는 숙소를 빼면 그날 마지막 장소 뒤에 묵을 곳이 없어요.`
      : `${when}에 여는 곳 가운데 ${hard.length ? `${hardWords}${hard.length > 1 ? "에 모두" : "에"} 맞는다고 자료에 있${rain ? "고 " : "는 "}` : ""}`
        + `${rain ? "야외가 아닌 " : ""}곳이 ${fitN ? `${fitN}곳뿐이라` : "없어"}${rain ? "(비 오는 날 야외는 하루 한 곳까지)" : ""}`
        + `${used ? ` 앞선 날에 넣은 ${used}곳을 빼면` : ""} ${theDay} 채울 수 없어요.`),
    budget: () => `입장료 예산 ${won(c.budget)}으로는 ${when}에 무료라고 자료에 있는 곳(${pool.visits.filter((x) => x.f.fee && x.f.fee.free).length}곳)과 예산 안에 드는 곳만으로 ${theDay} 채울 수 없어요.`,
    move: () => `대중교통·걷기로는 ${when}에 고른 조건에 맞는 곳이 서로 멀어 가까운 곳만으로 ${theDay} 채울 수 없어요.`,
    days: () => `고른 조건에 맞는 곳을 앞선 날에 넣고 나면 ${when}에 넣을 곳이 모자라요.`,
    hours: () => (why.has("stay") && failed < c.days - 1 ? `${when} 밤에 묵을 숙소를 그날 마지막 장소 뒤 23:29까지 넣을 수 없어요.`
      : missed && !why.has("gap") ? `${when}의 ${span}에는 ${missed} 시간에 고른 곳 가까이에서 여는 음식점을 찾을 수 없어요.`
        : `${when}의 ${span}을 고른 조건에 맞는 곳만으로 채우면 2시간 넘게 비는 시간이 남아요.`),
    hubs: () => `${[c.from && `${HUBS[c.from]}에서 출발한 뒤`, c.to && `${HUBS[c.to]}에 도착하기 전`].filter(Boolean).join("와 ")}에 30분 여유를 두면 ${when}에 고른 조건에 맞는 곳을 넣을 시간이 모자라요.`,
  };
  const kindOf = (field) => (field === "start" || field === "end" ? "hours" : field === "from" || field === "to" ? "hubs" : field);
  // a condition the places must meet, as a clause: [joined, last] — '…에 맞는다고 자료에 있고', '…에 맞는다고 자료에 있는'
  const clause = {
    needs: () => (hard.length ? [`${hardWords}에 맞는다고 자료에 있${rain ? "고 야외가 아니" : ""}고`, `${hardWords}에 맞는다고 자료에 있${rain ? "고 야외가 아닌" : "는"}`]
      : ["야외가 아니고", "야외가 아닌"]),
    budget: () => [`입장료 예산 ${won(c.budget)} 안에 들고`, `입장료 예산 ${won(c.budget)} 안에 드는`],
    move: () => ["대중교통·걷기로 가까이 오갈 수 있고", "대중교통·걷기로 가까이 오갈 수 있는"],
    days: () => ["앞선 날과 겹치지 않고", "앞선 날과 겹치지 않는"],
  };
  const other = { needs: `${needWords} 조건을 빼도 짤 수 있어요.`, budget: "입장료 예산을 바꿔도 짤 수 있어요.", move: "자가용으로 바꿔도 짤 수 있어요.",
    days: "기간을 줄여도 짤 수 있어요.", start: "시작을 늦춰도 짤 수 있어요.", end: "끝을 당겨도 짤 수 있어요.",
    from: "출발 역·터미널을 두지 않아도 짤 수 있어요.", to: "도착 역·터미널을 두지 않아도 짤 수 있어요.",
    note: "식사를 빼도 짤 수 있어요." };
  const problems = [];
  // no restaurant the site can give for a meal that date (no 음식점 with hours yet — the daily collection fills them):
  // the cause is the data, not the distance, and leaving the meal out is the first fix (QA 2026-10-19 QA-01: the
  // default 10:00–18:00 was refused with '… 가까이에서 여는 음식점을 찾을 수 없어요' and only '시작을 12:00로')
  if (missed && !pool.meals.length) {
    const kindsOut = [...new Set(trace.filter((t) => t.why === "meal").map((t) => t.meal))];
    const said = kindsOut.map((k) => MEALS[k].label).join("·");
    const note = [c.note, `${said}${eun(said)} 빼 주세요`].filter(Boolean).join(" ");
    const set = { note: [...note].slice(0, NOTE_MAX).join("") };
    if (eatsAll(set.note, kindsOut) && passes(set)) groups.unshift({ field: "note", fixes: [fix(`${said} 빼고 짜기`, set)] });
    if (groups.length && groups[0].field === "note") {
      for (const g of groups) {
        problems.push({ field: g.field, text: problems.length ? other[g.field]
          : `${when}에는 음식점 이용시간 자료가 아직 없어 ${said}${eul(said)} 넣을 수 없어요.`, fixes: g.fixes });
      }
    }
  }
  const kinds = [...new Set(groups.map((g) => kindOf(g.field)))];
  if (problems.length) {
    // said above
  } else if (kinds.length === 1) {
    for (const g of groups) problems.push({ field: g.field, text: problems.length ? other[g.field] : one[kinds[0]](), fixes: g.fixes });
  } else if (kinds.length > 1) {
    const places = kinds.filter((k) => clause[k]).map((k) => clause[k]());
    const where = places.length ? `${[...places.slice(0, -1).map((x) => x[0]), places.at(-1)[1]].join(" ")} 곳만으로 ` : "고른 조건에 맞는 곳만으로 ";
    const time = kinds.includes("hours") ? `${span}을 ` : "";
    const hubs = kinds.includes("hubs") ? `${[c.from && HUBS[c.from], c.to && HUBS[c.to]].filter(Boolean).join("·")}에 30분 여유를 두고 ` : "";
    const cause = `${when}에는 ${where}${hubs}${time || theDay + " "}채울 수 없어요 — 아래 조건 가운데 하나를 바꾸면 짤 수 있어요.`;
    for (const g of groups) problems.push({ field: g.field, text: problems.length ? other[g.field] : cause, fixes: g.fixes });
  }
  // nothing else does it: the nearest dates that do (설·추석 당일 and the like), and the date to choose
  if (!problems.length) {
    const near = [];
    for (let n = 1; n <= 7 && near.length < 2; n += 1) {
      for (const d of [shift(c.date, n), shift(c.date, -n)]) {
        if (d < today || d > lastDate || near.includes(d)) continue;
        if (passes({ date: d })) near.push(d);
        if (near.length >= 2) break;
      }
    }
    const few = pool.visits.length < 12;
    problems.push({ field: "date", text: few
      ? `${when}에는 여는 곳이 ${pool.visits.length ? `${pool.visits.length}곳뿐이라` : "없어"} ${theDay} 채울 수 없어요 — 다른 날을 골라 주세요.`
      : `${when}에는 고른 조건을 모두 맞추는 코스를 짤 수 없어요${hard.length || rain ? ` (그날 여는 곳 가운데 ${needWords}에 맞는 곳 ${fitN}곳)` : ""} — 다른 날을 고르거나 조건을 줄여 주세요.`,
    fixes: [...near.map((d) => fix(`${md(d)}${ro(md(d).slice(0, -1))}`, { date: d })), { label: "날짜 다시 고르기", focus: "date" }] });
  }
  // an edit keeps its dates and length: a change of either is the reader's to choose, never a button that sets it
  if (edit) {
    for (const p of problems) p.fixes = p.fixes.map((f) => (f.set && (f.set.date !== undefined || f.set.days !== undefined) ? { label: f.label, focus: f.set.date !== undefined ? "date" : "days" } : f));
  }
  return problems;
}

/** The reader's problems for a plan that still has flags after everything (planner.makePlan: never sent): the flags'
 *  kinds as fields, in the reader's words — what preflight would say when it can, else the flags themselves. */
export function problemsOf(list) {
  const FIELD = { closed: "date", hours: "start", leg: "move", start: "start", end: "end", "stay-missing": "days", "stay-mid": "days", "stay-ci": "days",
    rain: "needs", budget: "budget", "hub-from": "from", "hub-to": "to", meal: "start", gap: "prefs", need: "needs", "stay-last": "days", "stay-two": "days",
    role: "note", many: "note" };
  const seen = new Set();
  const out = [];
  for (const x of list) {
    const field = FIELD[x.kind] || "note";
    if (seen.has(field)) continue;
    seen.add(field);
    out.push({ field, text: `${x.text.replace(/ — [^—]*$/u, "")} — 이 조건으로는 사이트가 고칠 수 없어요.`, fixes: [{ label: "조건 다시 고르기", focus: field }] });
  }
  return out;
}

export { hubLegs, needAt, isCafe, fitsHours };
