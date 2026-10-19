// POST /api/plan/ → text/event-stream: the AI course planner (the engine's first site's operator 2026-10-17: 'AI 여행 코스
// 생성기', its own page /plan/, the site's own city only — its name, address and hubs from public/chat/site.json,
// chatbot/site.js, set by useSite). The reader picks conditions (dates, hours, how they move, who comes, likes, needs, a fee
// budget); the model reads the site's catalog and pages and hands the plan over with submit_plan; the code then checks
// every day against the data (knowledge.js checkPlan: closed days, notices, hours, last entry, legs with no time left)
// and the conditions (the day's hours, a stay each night, the fee budget), adds the fees up once (feeTotal), and sends
// back what is wrong for one fix. The page draws the plan from the site's own place data (/plan/places.json): the
// model's words are only the title, the summary, a reason per stop and the notes.
//
// SSE events: {type:'status', step, text} while it works · {type:'plan', plan} at the end · {type:'error', code,
// message}. Logs: one JSON line per request with numbers only (rounds, tools, submits, flags, tokens) — never the
// reader's words or the plan. The same request checks as the assistant (chatbot/server.js): POST, an allowed Origin,
// a key, a rate limit of its own (a plan costs several calls), a small body that parses, then the conditions.
import { QUERY_CHARS, defaultKnowledge } from "./knowledge.js";
import {
  HUBS, MOVE, NEEDS, PLAN_STATUS, PLAN_TOOLS, PREFS, WITH, buildPlanSystem, conditionsText, titleCity, tripDates, useSite,
} from "./plan_prompt.js";
import {
  CUT, HUB_MARGIN, IDLE, MEALS, PREF_LABEL, PREF_TYPES, checksList, dropSentences, eatsElsewhere, endsDay, grounded, hm, idleGaps,
  isCafe, isMeal, mealIn, needAt, needsTable, prefFits, readerDay, span, spans, statusOf,
} from "./plan_state.js";
import {
  CAMP, CHECK_WORDS, FILL_MAX, FILL_MIN, HARD, KEEP_MIN, MEAL_MIN, STAY_NEAR, STOPS_MAX, SWAP_MIN, WEEK, codeFits, dateWords, dayInfo, eul, freeRank, gOf,
  hardState, hhmm, hubLegs as hubLegsOf, inBreak, isOutdoor, jong, keepOf, km, knownFees, lastPoint, legFloor, legMargin, marginOf, metres, mins, near,
  nearestOpen, openWords, overBudget, placesOf, rainRank, ro, stretchMax,
} from "./plan_geo.js";
import { buildDay, buildPlan, changed, codeText, planFlags, preflight, problemsOf, windowOf } from "./plan_build.js";
import { MODEL, dataBlock, neutralise, seoulNow } from "./prompt.js";
import {
  HttpError, SSE_HEADERS, apiKey, clientIp, clientKey, createLimiter, json, limitCode, originAllowed, readBody, validInput,
} from "./server.js";
import { loadSite } from "./site.js";

export { legMargin, preflight };

export const PLAN_LIMITS = {
  bodyBytes: 16 * 1024,
  noteChars: 200,
  requestChars: 300,
  daysAhead: 180,        // a trip starts today (in Korea) or within this many days
  perMinute: 3,          // per client per minute (a plan is several model calls)
  perDay: 20,            // per client per 24 hours
  allPerMinute: 15,
  allPerDay: 400,
  // speed (operator 2026-10-17: '늦어도 1분 안에는 돼야', a plan took 160 s, an edit longer): no thinking — the code
  // checks every plan anyway —, the facts the reader's needs ask for handed over with the conditions, one reading
  // round at most, then submit_plan is forced; one fix only while there is time for it
  rounds: 4,             // model calls of one plan: one reading round, the plan, one fix, a forced last hand-over
  reads: 1,              // calls that only read (search_site / get_pages) before submit_plan is forced
  submits: 2,            // submit_plan calls the code checks: the first, and one fix
  maxTokens: 6000,       // one call
  outputTokens: 20000,   // all calls of one plan — a ceiling: each call asks for no more than what is left
  submitTokens: 6000,    // kept back for the last call, which must hand the plan over
  toolChars: 24000,      // all reading results of one plan
  requestMs: 55000,      // the whole plan (vercel.json maxDuration 60; the page gives up at 70 s)
  fixBy: 32000,          // a plan the check finds wrong is sent back for its fix only before this; later it is
                         // finished as it is, its flags shown (status 'unmet')
  readBy: 18000,         // after this the next call must hand the plan over
  callMs: 40000,
  refusedPerMinute: 10,  // conditions refused at the button (preflight), per client — not the plan's quota
  refusedPerDay: 100,
  refusedAllPerMinute: 120,
  refusedAllPerDay: 4000,
  stopsPerDay: STOPS_MAX,   // a day's stops, its night's stay counted (plan_geo.STOPS_MAX: the code adds no more)
};

const ERRORS = {
  not_configured: "코스 만들기가 아직 연결되지 않았습니다.",
  rate_limited: "요청이 너무 잦습니다. 1분 뒤에 다시 만들어 주세요.",
  daily_limit: "오늘 만들 수 있는 코스 수를 넘었습니다. 내일 다시 만들어 주세요.",
  busy: "지금은 코스를 만들 수 없습니다. 잠시 뒤 다시 시도해 주세요.",
  bad_request: "조건을 다시 골라 주세요.",
  bad_date: "여행 날짜는 오늘부터 180일 안에서 골라 주세요.",
  too_large: "요청이 너무 깁니다.",
  timeout: "코스를 만드는 데 너무 오래 걸려 멈췄습니다. 다시 시도해 주세요.",
  refusal: "이 요청으로는 코스를 만들 수 없습니다.",
  empty: "코스를 만들지 못했습니다. 조건을 조금 바꿔 다시 시도해 주세요.",
  conditions: "이 조건으로는 코스를 끝까지 짤 수 없어요. 아래를 바꿔 주세요.",
  edit_failed: "요청한 변경으로는 코스를 끝까지 맞출 수 없어 보던 일정을 그대로 두었습니다. 요청을 조금 바꿔 다시 시도해 주세요.",
  error: "코스를 만들지 못했습니다. 다시 시도해 주세요.",
};
export const planError = (code) => ERRORS[code] || ERRORS.error;

const str = (v, max) => (typeof v === "string" ? v.replace(/\s+/g, " ").trim().slice(0, max) : "");
const isInt = (v, lo, hi) => Number.isInteger(v) && v >= lo && v <= hi;
const set = (v, keys, max) => Array.isArray(v) && v.length <= max && v.every((x) => keys.includes(x)) && new Set(v).size === v.length;

/** The reader's conditions, checked (every field from a fixed list or a bounded number; the note is text, cut and
 *  neutralised where it reaches the model). Throws HttpError 400 otherwise; a date in the past or too far: bad_date. */
export function validConditions(c, now) {
  if (!c || typeof c !== "object" || Array.isArray(c)) throw new HttpError(400, "bad_request");
  const today = seoulNow(now).date;
  if (typeof c.date !== "string" || !/^\d{4}-\d{2}-\d{2}$/.test(c.date) || Number.isNaN(Date.parse(`${c.date}T12:00:00Z`))
    || new Date(`${c.date}T12:00:00Z`).toISOString().slice(0, 10) !== c.date) {   // 2027-02-30 is not a date
    throw new HttpError(400, "bad_request");
  }
  const ahead = (Date.parse(`${c.date}T12:00:00Z`) - Date.parse(`${today}T12:00:00Z`)) / 86400000;
  if (ahead < 0 || ahead > PLAN_LIMITS.daysAhead) throw new HttpError(400, "bad_date");
  const start = mins(c.start), end = mins(c.end);
  const ok = isInt(c.days, 1, 3) && start !== null && end !== null && start >= 6 * 60 && end <= 23 * 60 && end - start >= 180
    && Object.hasOwn(MOVE, c.move) && Object.hasOwn(WITH, c.with) && isInt(c.adults, 0, 10)
    && Array.isArray(c.kids) && c.kids.length <= 6 && c.kids.every((a) => isInt(a, 0, 17)) && c.adults + c.kids.length >= 1
    && (c.seniors === undefined || isInt(c.seniors, 0, c.adults))
    && (c.from === undefined || c.from === "" || Object.hasOwn(HUBS, c.from))
    && (c.to === undefined || c.to === "" || Object.hasOwn(HUBS, c.to))
    && set(c.prefs ?? [], Object.keys(PREFS), 4) && set(c.needs ?? [], Object.keys(NEEDS), 6)
    && (c.budget === null || c.budget === undefined || isInt(c.budget, 0, 1000000))
    && (c.note === undefined || (typeof c.note === "string" && [...c.note].length <= PLAN_LIMITS.noteChars));
  if (!ok) throw new HttpError(400, "bad_request");
  return { date: c.date, days: c.days, start: c.start, end: c.end, move: c.move, with: c.with, adults: c.adults,
    seniors: c.seniors || 0, kids: [...c.kids], from: c.from || "", to: c.to || "", prefs: [...(c.prefs || [])],
    needs: [...(c.needs || [])], budget: c.budget ?? null, note: str(c.note, PLAN_LIMITS.noteChars) };
}

/** An edit: the plan the page shows (pages and times only) and the change the reader asks for. */
export function validEdit(plan, request, c) {
  if (plan === undefined && request === undefined) return null;
  if (!plan || typeof plan !== "object" || !Array.isArray(plan.days) || plan.days.length !== c.days) throw new HttpError(400, "bad_request");
  if (typeof request !== "string" || !request.trim() || [...request].length > PLAN_LIMITS.requestChars) throw new HttpError(400, "bad_request");
  const dates = tripDates(c.date, c.days);
  const days = plan.days.map((d, i) => {
    if (!d || d.date !== dates[i] || !Array.isArray(d.stops) || d.stops.length > PLAN_LIMITS.stopsPerDay) throw new HttpError(400, "bad_request");
    return { date: d.date, stops: d.stops.map((s) => {
      if (!s || typeof s.page !== "string" || s.page.length > 300 || mins(s.start) === null || mins(s.end) === null) throw new HttpError(400, "bad_request");
      // the role and the reason ride along, so the stops an edit keeps are copied, not read and written again
      return { page: s.page, start: s.start, end: s.end, role: ["visit", "meal", "cafe", "stay"].includes(s.role) ? s.role : "visit",
        why: str(s.why, 120) };
    }) };
  });
  return { plan: { days }, request: str(request, PLAN_LIMITS.requestChars) };
}

const STAY_AFTER = 30;   // minutes between the day's last stop and the night's stay when the model's stay starts earlier

/** submit_plan's input checked against the conditions and the site: {plan, errors, salvaged, fixes} — errors (Korean,
 *  for the model) when a day, a page, a time or a field is not what it must be; the plan is trimmed to its bounds.
 *  salvaged: the same plan with what cannot stand taken out (a page the site lacks, times that are not times, more
 *  stops than a day holds) and every role made what the place is — finished as it is when the model has no turn left
 *  to fix it (a 1박 2일 plan sent back three times was thrown away whole: operator 2026-10-17, '코스를 만들지
 *  못했습니다'); fixes says, for the reader, what was taken out or changed. null when a day would have no stop.
 *  A night's stay is where the day ends: one that starts before the stop ahead of it is over (the page's check-in
 *  time, a review rule) starts after it, and an end before its start or past midnight is the start plus an hour. */
export function readSubmit(input, c, kb) {
  const errors = [];
  const fixes = [];
  if (!input || typeof input !== "object") return { plan: null, errors: ["submit_plan의 입력이 객체가 아니다"], salvaged: null, fixes };
  const dates = tripDates(c.date, c.days);
  const days = Array.isArray(input.days) ? input.days : [];
  if (days.length !== c.days) errors.push(`days는 ${c.days}일이어야 한다(${dates.join(", ")})`);
  const plan = { title: str(input.title, 60), summary: str(input.summary, 300), days: [],
    notes: (Array.isArray(input.notes) ? input.notes : []).map((x) => str(x, 160)).filter(Boolean).slice(0, 3) };
  if (!plan.title) errors.push("title이 비어 있다");
  const safe = [];
  days.slice(0, c.days).forEach((d, i) => {
    const date = d && d.date;
    if (date !== dates[i]) errors.push(`${i + 1}일차 date는 ${dates[i]}이어야 한다`);
    const stops = Array.isArray(d && d.stops) ? d.stops : [];
    if (!stops.length) errors.push(`${i + 1}일차에 장소가 없다`);
    if (stops.length > PLAN_LIMITS.stopsPerDay) {
      errors.push(`${i + 1}일차 장소는 ${PLAN_LIMITS.stopsPerDay}곳까지`);
      fixes.push(`${i + 1}일차: 하루 ${PLAN_LIMITS.stopsPerDay}곳을 넘는 장소를 뺐습니다`);
    }
    const out = [];
    const kept = [];
    let prevEnd = null;
    stops.slice(0, PLAN_LIMITS.stopsPerDay).forEach((s, j) => {
      const where = `${i + 1}일차 ${j + 1}번`;
      const key = s && typeof s.page === "string" ? kb.keyFor(s.page) : "";
      const doc = key ? kb.docs[key] : null;
      if (!doc || doc.k !== "place") {
        errors.push(`${where}: '${str(s && s.page, 80)}'은 이 사이트의 장소 페이지가 아니다 — 카탈로그의 P 줄 경로를 쓴다`);
        fixes.push(`${i + 1}일차: 이 사이트에 장소 페이지가 없는 곳 하나를 뺐습니다`);
        return;
      }
      const role = ["visit", "meal", "cafe", "stay"].includes(s.role) ? s.role : "visit";
      const kind = (doc.f || {}).kd;
      let a = mins(s.start), b = mins(s.end);
      let start = s.start, end = s.end;
      if (role === "stay" && kind === "stay" && a !== null) {
        if (prevEnd !== null && a < prevEnd) a = prevEnd + STAY_AFTER;
        if (a <= 23 * 60 + 29 && (b === null || b <= a)) b = Math.min(a + 60, 23 * 60 + 59);
        if (a <= 23 * 60 + 29) [start, end] = [hhmm(a), hhmm(b)];
      }
      if (a === null || b === null || b <= a) {
        errors.push(`${where} ${doc.t}: start·end는 HH:MM이고 end가 start보다 늦어야 한다`);
        fixes.push(`${i + 1}일차 ${doc.t}: 시각이 올바르지 않아 뺐습니다`);
        return;
      }
      if (prevEnd !== null && a < prevEnd) errors.push(`${where} ${doc.t}: 앞 장소가 끝나기 전에 시작한다`);
      prevEnd = b;
      // a role is what the place is (review CE05: a park handed over as the night's stay passed)
      let fit = role;
      if (role === "stay" && kind !== "stay") {
        errors.push(`${where} ${doc.t}: role stay인데 숙소 페이지가 아니다 — 카탈로그의 숙소를 쓴다`);
        fixes.push(`${i + 1}일차 ${doc.t}: 숙소가 아니라서 묵는 곳이 아닌 방문지로 두었습니다`);
        fit = "visit";
      }
      if ((role === "meal" || role === "cafe") && kind !== "food") {
        errors.push(`${where} ${doc.t}: role ${role}인데 음식점 페이지가 아니다`);
        if (kind !== "stay") fixes.push(`${i + 1}일차 ${doc.t}: 음식점 페이지가 아니라서 ${role === "meal" ? "식사" : "카페"}가 아닌 방문지로 두었습니다`);
        fit = "visit";
      }
      // (a stay handed over as a meal or a café too: round-5 verifier, a motel as a 'cafe' became a visit)
      if (role !== "stay" && kind === "stay") {
        if (role === "visit") errors.push(`${where} ${doc.t}: 숙소는 role stay로만 넣는다`);
        fixes.push(`${i + 1}일차 ${doc.t}: 숙소라서 묵는 곳으로 두었습니다`);
        fit = "stay";
      }
      const stop = { page: key, name: doc.t, start, end, role, why: str(s.why, 120) };
      out.push(stop);
      kept.push({ ...stop, role: fit });
    });
    plan.days.push({ date: dates[i], stops: out });
    safe.push({ date: dates[i], stops: kept });
  });
  const whole = safe.length === c.days && safe.every((d) => d.stops.length);
  const salvaged = whole ? { ...plan, title: plan.title || `${titleCity()}${c.days > 1 ? `${c.days - 1}박 ${c.days}일` : "하루"} 코스`, days: safe } : null;
  return { plan, errors, salvaged, fixes };
}

/** What the code puts right itself before a plan is checked — each a plain rule on the site's data, each said in the
 *  'fixed' list ('사이트가 바로잡은 것') in words for the reader (operator 2026-10-18: a 2박 3일 plan shown as '조건을
 *  다 맞추지 못한 초안' for a gallery closed that Monday and two nights without a stay; outside evaluation the same day:
 *  a Monday plan with five of six stops closed, then an edit left with one stop, no lunch and 340 minutes empty):
 *  0. a night's stay the model put ahead of another stop of its day, or before its check-in time, goes to the end of
 *     the day: after the last stop with the leg's margin (marginOf), not before its check-in time (final check
 *     2026-10-18: a stay at 11:40 ahead of a whole afternoon passed); past 23:29 it stays, flagged (verify);
 *  1. closed: a stop closed that day (its regular closed days or a dated notice: checkPlan 'closed') becomes the
 *     nearest place of its kind — the same type first; for rain an indoor type first and never an outdoor one — that
 *     is open that day within the same times, kept short of the stops next to it by the legs' margins (KEEP_MIN at
 *     least; opensAt: one that leaves that day to check, a holiday, only when no other fits, and said so), not in the
 *     plan, within NEAR.swap; taken out only when nothing fits (or the site has no point for it to search from, said
 *     so), and never the day's last stop;
 *  2. the station or terminal: HUB_MARGIN after the start, before the end;
 *  3. legs: a leg with no time left, or too little for its straight line (checkPlan's flags), and every leg next to a
 *     stop swapped in, gets its margin (widen);
 *  4. meals: a day that spans lunch or dinner (plan_state.readerDay, MEALS) with no meal stop in its window
 *     (plan_state.mealIn: never a café) gets the nearest restaurant (plan_state.isMeal: never a café, only a menu that
 *     names a meal) to the stop before the slot, open then, within NEAR.meal, for MEAL_MIN minutes, in a gap with the
 *     legs' margins or by shortening the stop next to it (KEEP_MIN); a day with no such slot gives the meal the place
 *     of a stop the code put in itself (mealInstead) — unless the reader wrote that they eat elsewhere; on an edit, a
 *     day that had a meal gets it back the same way;
 *  5. empty time: a stretch of the reader's day longer than IDLE gets the nearest place open then that fits what they
 *     like (plan_state.PREF_TYPES, the islands' 권역; a café for 카페·빵집) and what they need (rain: indoor), for
 *     FILL_MIN–FILL_MAX minutes with the margins, until no such stretch is left or nothing fits;
 *  6. stays, after the meals and the empty hours — so a stay never ends the reader's day before its meal and its
 *     hours are filled unless it says when (plan_state.endsDay, review 2026-10-18): a night with no stay gets the
 *     stay the plan has for another night when it can start by 23:29 after the leg's margin, else the nearest stay to
 *     the day's last stop that can (straight line, within STAY_NEAR; hotels, motels and guesthouses before camps),
 *     after that stop with the leg's margin and not before its check-in time; a stay that does not end the day (no
 *     check-in time on its page) and that the day's stops now run into starts the leg's margin after the last of them;
 *  7. last, every leg next to a stop the code put in, swapped in or moved gets its margin (widen); one that cannot
 *     keep it is flagged (verify).
 *  The plan is changed in place; a stop the code adds carries by: 'site', one it swaps in by: 'swap', a stay it moves
 *  moved: true. edit: the plan before the change and the request (makePlan's edit). Returns what was changed, in words
 *  for the reader. */
export function repair(plan, c, kb, edit = null) {
  const out = [];
  const many = plan.days.length > 1;
  const dayW = (i) => (many ? `${i + 1}일차 ` : "");
  const check = (d) => kb.checkPlan({ date: d.date, stops: d.stops.map((s) => ({ page: s.page, start: s.start, end: s.end })), move: c.move });
  const ciOf = (page) => mins(((kb.docs[page] || {}).f || {}).ci);
  // the start a night's stay gets after the day's last stop: the leg's margin after it, not before its check-in
  // time; null past 23:29
  const stayAt = (last, page) => {
    const a = Math.max(mins(last.end) + marginOf(last.page, page, c, kb), ciOf(page) ?? 0);
    return a <= 23 * 60 + 29 ? a : null;
  };
  const putStay = (d, s, a) => {
    d.stops.splice(d.stops.indexOf(s), 1);
    d.stops.push(Object.assign(s, { start: hhmm(a), end: hhmm(Math.min(a + 60, 23 * 60 + 59)) }));
  };
  // 0. a night's stay ahead of its day's stops, or before its check-in time
  plan.days.forEach((d, i) => {
    if (i === plan.days.length - 1) return;
    for (const s of d.stops.filter((x) => x.role === "stay" && !x.by)) {
      const own = d.stops.filter((x) => x.role !== "stay");
      const last = own.at(-1);
      const ahead = !!last && d.stops.indexOf(s) < d.stops.indexOf(last);
      const ci = ciOf(s.page);
      if (!ahead && !(ci !== null && mins(s.start) < ci)) continue;
      const a = last ? stayAt(last, s.page) : ci;
      if (a === null) continue;
      out.push(ahead ? `${dayW(i)}밤 숙소 ${s.name}: 그날 다른 장소보다 앞에 있어 마지막 장소 ${last.name} 뒤 ${hhmm(a)}${ro(hhmm(a))} 옮겼습니다`
        : `${dayW(i)}밤 숙소 ${s.name}: 체크인 ${hhmm(ci)} 전이라 시작을 ${s.start}에서 ${hhmm(a)}${ro(hhmm(a))} 늦췄습니다`);
      putStay(d, s, a);
      s.moved = true;
    }
  });
  // 1. closed stops
  plan.days.forEach((d, i) => {
    const r = check(d);
    const closed = r.stops.map((x, j) => (x.day === "closed" && d.stops[j].role !== "stay" ? j : -1)).filter((j) => j >= 0);
    if (!closed.length) return;
    const when = dateWords(d.date);
    const gone = new Map();   // the stops taken out: index → whether the site has a point to search from
    for (const j of closed) {
      const said = swapIn(plan, d, j, c, kb, { why: `${when}은 쉬는 날이라` });
      if (said) out.push(`${dayW(i)}${said}`);
      else gone.set(j, !!gOf(kb, d.stops[j].page));
    }
    // nothing fits: taken out, as long as the day keeps a stop of its own (the stop's flag then says it is closed)
    if (!gone.size || gone.size >= d.stops.filter((s) => s.role !== "stay").length) return;
    for (const [j, point] of gone) {
      out.push(`${dayW(i)}${d.stops[j].name}: ${when}은 쉬는 날이고, ${point
        ? `직선 ${near(c, "swap") / 1000}km 안에 그 시각에 여는 같은 종류의 곳 가운데 고른 조건과 앞뒤 이동 여유에 맞는 곳이 없어`
        : "사이트에 이곳의 좌표가 없어 가까운 곳을 찾을 수 없어"} 일정에서 뺐습니다`);
    }
    d.stops = d.stops.filter((_, j) => !gone.has(j));
  });
  // 2. the station or terminal the reader starts from or goes back to: HUB_MARGIN after the start, before the end —
  // before the legs, which then make room around it
  const first = (plan.days[0] || { stops: [] }).stops[0];
  if (c.from && first && mins(first.start) - mins(c.start) < HUB_MARGIN && mins(first.end) - (mins(c.start) + HUB_MARGIN) >= keepOf(first)) {
    const at = hhmm(mins(c.start) + HUB_MARGIN);
    out.push(`${many ? "1일차 " : ""}${first.name}: ${HUBS[c.from]}에서 출발하는 여유 30분을 두려고 시작을 ${first.start}에서 ${at}${ro(at)} 늦췄습니다`);
    first.start = at;
  }
  const lastDay = plan.days[plan.days.length - 1] || { stops: [] };
  const last = [...lastDay.stops].reverse().find((s) => s.role !== "stay");
  if (c.to && last && mins(c.end) - mins(last.end) < HUB_MARGIN && mins(c.end) - HUB_MARGIN - mins(last.start) >= keepOf(last)) {
    const at = hhmm(mins(c.end) - HUB_MARGIN);
    out.push(`${many ? `${plan.days.length}일차 ` : ""}${last.name}: ${HUBS[c.to]}${ro(HUBS[c.to])} 돌아가는 여유 30분을 두려고 끝을 ${last.end}에서 ${at}${ro(at)} 당겼습니다`);
    last.end = at;
  }
  // 3. a leg with no time left, or too little for its straight line (checkPlan's leg flags), and the legs next to a
  // stop swapped in: widen
  plan.days.forEach((d, i) => {
    const flagged = new Set(check(d).legs.filter((x) => x.flag).map((x) => x.from));
    for (let j = 0; j + 1 < d.stops.length; j += 1) {
      const a = d.stops[j], b = d.stops[j + 1];
      // (a leg into the model's own stay too: the stay moves whole, by 23:29 — round-4 verifier)
      if (a.role === "stay" || (b.role === "stay" && b.by) || a.page === b.page || (!flagged.has(j) && !changed(a) && !changed(b))) continue;
      const said = widen(d, j, c, kb, flagged.has(j) && !changed(a) && !changed(b));
      if (said) out.push(`${dayW(i)}${said}`);
    }
  });
  // 4. meals
  plan.days.forEach((d, i) => {
    for (const kind of ["lunch", "dinner"]) {
      const m = MEALS[kind];
      const day = readerDay(plan, c, i, kb);
      if (!day || mealIn(d.stops, m, kb) || eatsElsewhere(kind, c.note, edit && edit.request)) continue;
      const had = edit && edit.plan.days[i] && mealIn(edit.plan.days[i].stops, m, kb);
      if (!spans(day, m) && !had) continue;
      // a day the edit kept a meal on but no longer spans it (a day between the first and the last): the meal's
      // window is part of that day again
      const dayOf = () => {
        const x = readerDay(plan, c, i, kb);
        if (x && had && !spans(x, m)) {
          if (i > 0) x.lo = Math.min(x.lo, m.first);
          if (i < plan.days.length - 1) x.hi = Math.max(x.hi, m.last + MEAL_MIN);
        }
        return x;
      };
      const said = addMeal(plan, d, dayOf(), m, c, kb) || mealInstead(plan, d, dayOf, m, c, kb);
      if (said) out.push(`${dayW(i)}${said}`);
    }
  });
  // 5. empty time
  plan.days.forEach((d, i) => {
    for (let n = 0; n < PLAN_LIMITS.stopsPerDay && d.stops.length < PLAN_LIMITS.stopsPerDay; n += 1) {
      const day = readerDay(plan, c, i, kb);
      if (!day) break;
      let said = "";
      for (const g of idleGaps(day).filter((x) => x.minutes > IDLE)) {
        said = fillGap(plan, d, day, g, c, kb);
        if (said) break;
      }
      if (!said) break;
      out.push(`${dayW(i)}${said}`);
    }
  });
  // 6. a stay each night — after the meals and the empty hours, so a stay never ends the reader's day before them
  // unless it says when (plan_state.endsDay: the model's, with a check-in time; review 2026-10-18: one with no
  // check-in time put in at 13:00 after a stop ending at 12:30 left the day without its lunch). The one the code puts
  // in carries by: 'site'; one that does not end the day and that the day's stops now run into starts after them.
  plan.days.forEach((d, i) => {
    if (i === plan.days.length - 1) return;
    const last = [...d.stops].reverse().find((s) => s.role !== "stay");
    if (!last) return;
    const has = d.stops.find((s) => s.role === "stay");
    if (has) {
      const a = stayAt(last, has.page);
      if (endsDay(has, kb) || a === null || mins(has.start) >= a) return;
      out.push(`${dayW(i)}밤 숙소 ${has.name}: 그날 마지막 장소 ${last.name} 뒤로 시작을 ${has.start}에서 ${hhmm(a)}${ro(hhmm(a))} 늦췄습니다`);
      putStay(d, has, a);
      return;
    }
    // the stay of another night, when it can start in the evening after the leg's margin (final check 2026-10-18: a
    // stay 22 km away put in 30 minutes after an island's last stop); else the nearest that can
    const other = [...plan.days.slice(0, i).reverse(), ...plan.days.slice(i + 1, -1)]
      .map((x) => x.stops.find((s) => s.role === "stay" && codeFits(c, (kb.docs[s.page] || {}).f || {}, "stay"))).find(Boolean);
    if (makeRoom(d, (x) => out.push(`${dayW(i)}${x.name}: 밤 숙소를 넣을 자리를 내려고 일정에서 뺐습니다`)) === null) return;
    let pick = null;
    let a = other ? stayAt(last, other.page) : null;
    let how = "";
    if (a !== null) {
      pick = { page: other.page, name: other.name };
      how = `다른 밤과 같은 숙소 ${other.name}${eul(other.name)} 넣었습니다`;
    } else {
      const at = lastPoint(kb, d.stops);
      if (!at) return;
      const near = kb.keys.map((k) => [k, kb.docs[k]])
        .filter(([, x]) => x && x.k === "place" && (x.f || {}).kd === "stay" && (x.f || {}).g && codeFits(c, x.f, "stay"))
        .map(([k, x]) => ({ page: k, name: x.t, m: metres(at, x.f.g), camp: CAMP.test(x.f.ty || "") }))
        .filter((x) => x.m <= STAY_NEAR)
        .sort((x, y) => x.camp - y.camp || x.m - y.m || (x.name < y.name ? -1 : 1));
      const k = near.findIndex((x) => (a = stayAt(last, x.page)) !== null);
      if (k < 0) return;
      pick = near[k];
      how = `${last.name}에서 ${k ? "" : "가장 "}가까운 숙소 ${pick.name}(직선 ${km(pick.m)})${eul(pick.name)} 넣었습니다 — 객실·요금은 숙소에 확인`;
    }
    d.stops.push({ page: pick.page, name: pick.name, start: hhmm(a), end: hhmm(Math.min(a + 60, 23 * 60 + 59)), role: "stay", why: "", by: "site" });
    out.push(`${dayW(i)}밤 숙소: 일정에 없어 ${how}`);
  });
  // 7. every leg next to a stop the code put in, swapped in or moved (final check 2026-10-18: legs next to a place
  // swapped in were left under the code's own margin)
  plan.days.forEach((d, i) => {
    for (let j = 0; j + 1 < d.stops.length; j += 1) {
      const a = d.stops[j], b = d.stops[j + 1];
      if (a.role === "stay" || a.page === b.page || (!changed(a) && !changed(b))) continue;
      const said = widen(d, j, c, kb);
      if (said) out.push(`${dayW(i)}${said}`);
    }
  });
  return out;
}


/** A day that holds STOPS_MAX stops (its night's stay counted) gives up a stop for one the code must add (a night's
 *  stay): the shortest the code put in that is not a meal — said through `said(stop)`. Returns '' when there was room,
 *  the stop taken out, or null when nothing can go (round-5 verifier: days of 13 stops). */
function makeRoom(d, said = () => {}) {
  if (d.stops.length < STOPS_MAX) return "";
  const mine = d.stops.filter((s) => s.by === "site" && s.role !== "meal" && s.role !== "stay")
    .sort((a, b) => hm(a.end) - hm(a.start) - (hm(b.end) - hm(b.start)));
  if (!mine.length) return null;
  d.stops.splice(d.stops.indexOf(mine[0]), 1);
  said(mine[0]);
  return mine[0];
}

// a place's kind within its kd: its type; a restaurant's cuisine, or 카페
const kindOf = (x) => ((x.f || {}).kd === "food" ? (isCafe(x) ? "카페" : x.f.ty || "") : (x.f || {}).ty || "");

/** Stop j of day d becomes the nearest place of its kind — the same type first; for rain an indoor type first and never
 *  an outdoor one — that is open that day within the same times, kept short of the stops next to it by the legs'
 *  margins (it gives way first, to SWAP_MIN — a visit 30 minutes, a meal 45; a slot shorter is no slot: round-4
 *  verifier, prefer dropping to a short visit; then the stops next to it, each keeping keepOf and its hours), not in the
 *  plan, within NEAR.swap (or `max`), not pushing the known fees over the budget (repair 1, planner.settle). opts: why
 *  (the reason, in the reader's words: '10월 19일(월)은 쉬는 날이라'), fits(doc, page) (more the place must be), rank (ranks it
 *  first: a number, lower first), max. Changes the stop and its neighbours; returns the reader's words, or ''. */
function swapIn(plan, d, j, c, kb, { why, fits = () => true, rank = () => 0, max = near(c, "swap") } = {}) {
  const st = d.stops[j];
  const doc = kb.docs[st.page] || {};
  const f = doc.f || {};
  if (!f.g) return "";
  const taken = new Set(plan.days.flatMap((x) => x.stops.map((s) => s.page)));
  const fees = knownFees(plan, c, kb);
  const prev = d.stops[j - 1], next = d.stops[j + 1];
  const pick = nearestOpen({ kb, c, date: d.date, at: f.g, max, taken,
    // a meal stays a meal (a place that serves one: isMeal), a café stays a café; the hard needs the reader picked as
    // the code holds every place it puts in (plan_geo.codeFits: a visit the data says fits, else not 'no')
    fits: (x, page) => x.f.kd === f.kd && (st.role === "meal" ? isMeal(x) : st.role === "cafe" ? isCafe(x) : true) && codeFits(c, x.f, st.role) && fits(x, page),
    rank: (x) => { const rr = rainRank(c, x.f); return rr === null ? null : [rank(x), rr, kindOf(x.doc) === kindOf(doc) ? 0 : 1, freeRank(c, x.f)]; },
    // within the stop's times, short of the stops next to it by the legs' margins: the place swapped in gives way
    // first (to SWAP_MIN), then the stops next to it (cutP, cutN: each keeping keepOf and its hours) — final check
    // 2026-10-18: a place swapped in 2.8 km away kept the 10 minutes left for one 500 m away
    slot: (x) => {
      const P = prev && prev.role !== "stay" ? prev : null, N = next && next.role !== "stay" ? next : null;
      const a0 = hm(st.start), b0 = hm(st.end);
      const least = SWAP_MIN[st.role] || SWAP_MIN.visit;
      if (b0 - a0 < least) return [];
      const d1 = P ? Math.max(0, hm(P.end) + marginOf(P.page, x.page, c, kb) - a0) : 0;
      const d2 = N ? Math.max(0, b0 + marginOf(x.page, N.page, c, kb) - hm(N.start)) : 0;
      const slack = b0 - a0 - least;
      const s1 = Math.min(d1, slack), s2 = Math.min(d2, slack - s1);
      const cutP = d1 - s1, cutN = d2 - s2;
      if ((P && hm(P.end) - cutP - hm(P.start) < keepOf(P)) || (N && hm(N.end) - hm(N.start) - cutN < keepOf(N))) return [];
      if (cutN && !holds(N, d.date, hm(N.start) + cutN, hm(N.end), c, kb)) return [];
      return [{ a: a0 + s1, b: b0 - s2, cutP, cutN }];
    },
    put: (x) => {
      const was = { ...st };
      Object.assign(st, { page: x.page, name: x.name });
      const bad = overBudget(plan, c, kb, fees);
      Object.assign(st, was);
      return !bad;
    } });
  if (!pick) return "";
  const what = rainRank(c, pick.f) === 0 && c.needs.includes("rain") && f.kd === "attraction" ? `실내 유형 '${pick.f.ty}'`
    : kindOf(pick.doc) === kindOf(doc) && kindOf(doc) ? `같은 유형 '${kindOf(doc)}'` : "곳";
  // a place with something to check that day (a public holiday, a 명절 rule) is said to be no more than it is
  const said = pick.open === "open" ? `그날 여는 ${what}` : `${what === "곳" ? "" : `${what}, `}${CHECK_WORDS}`;
  const bits = pick.a !== hm(st.start) || pick.b !== hm(st.end) ? [`${hhmm(pick.a)}~${hhmm(pick.b)}에 두었습니다`] : [];
  if (pick.cutP) {
    const to = hhmm(hm(prev.end) - pick.cutP);
    bits.push(`${prev.name} 끝을 ${prev.end}에서 ${to}${ro(to)} 당겼습니다`);
    prev.end = to;
  }
  if (pick.cutN) {
    const to = hhmm(hm(next.start) + pick.cutN);
    bits.push(`${next.name} 시작을 ${next.start}에서 ${to}${ro(to)} 늦췄습니다`);
    next.start = to;
  }
  const line = `${st.name}: ${why} 가까운 ${pick.name}(직선 ${km(pick.m)}, ${said})${ro(pick.name)} 바꿨습니다`
    + `${bits.length ? ` — 앞뒤 장소와의 이동 여유를 두려고 ${bits.join(", ")}` : ""}`;
  Object.assign(st, { page: pick.page, name: pick.name, start: hhmm(pick.a), end: hhmm(pick.b), why: "", by: "swap" });
  return line;
}

// whether a stop at the times x–y keeps to its hours that day as well as at its own times (checkPlan's flags, a
// restaurant's break)
function holds(s, date, x, y, c, kb) {
  const flags = (p, q) => kb.checkPlan({ date, stops: [{ page: s.page, start: hhmm(p), end: hhmm(q) }], move: c.move }).flags.length;
  const f = (kb.docs[s.page] || {}).f || {};
  return flags(x, y) <= flags(hm(s.start), hm(s.end)) && (!inBreak(f, x, y) || inBreak(f, hm(s.start), hm(s.end)));
}

/** A leg of a day (stops j and j + 1) with less than its margin (marginOf) gets it: a stop the code put in, swapped
 *  in or moved gives way first, then the other — the stop before ends earlier, the stop after starts later (a night's
 *  stay moves whole, by 23:29) —, each keeping KEEP_MIN minutes and, starting later, its hours that day. least: a leg
 *  of the model's own that checkPlan flags, which gets at least the bound it is held to (knowledge.legBound) when the
 *  whole margin does not fit. Returns the reader's words; '' when the leg has its margin or when it cannot get it
 *  (verify flags such a leg next to a stop the code changed). */
function widen(d, j, c, kb, least = false) {
  const a = d.stops[j], b = d.stops[j + 1];
  const ga = gOf(kb, a.page), gb = gOf(kb, b.page);
  const m = ga && gb ? metres(ga, gb) : null;
  const need = marginOf(a.page, b.page, c, kb);
  const ae = hm(a.end), bs = hm(b.start);
  const to = `${b.name}${m !== null ? `(직선 ${km(m)})` : ""}`;
  // from the margin down, 5 minutes at a time, to the least it may have: a leg of the model's own the check flags,
  // its bound (legFloor); any other, the whole margin (round-4 verifier: only the margin and the bound were tried)
  const floor = least ? Math.min(need, legFloor(a.page, b.page, c, kb)) : need;
  for (let gap = need; gap >= floor; gap -= 5) {
    if (bs - ae >= gap) return "";
    const pull = () => {
      if (a.role === "stay" || bs - gap - hm(a.start) < keepOf(a)) return "";
      const was = a.end;
      a.end = hhmm(bs - gap);
      return `${a.name}: 다음 장소 ${to}까지 여유 ${gap}분을 두려고 끝을 ${was}에서 ${a.end}${ro(a.end)} 당겼습니다`;
    };
    const push = () => {
      const x = ae + gap;
      if (b.role === "stay" ? x > 23 * 60 + 29 : hm(b.end) - x < keepOf(b) || !holds(b, d.date, x, hm(b.end), c, kb)) return "";
      const was = b.start;
      b.start = hhmm(x);
      if (b.role === "stay") b.end = hhmm(Math.min(x + 60, 23 * 60 + 59));
      return `${b.role === "stay" ? "밤 숙소 " : ""}${b.name}: 앞 장소 ${a.name}에서 여유 ${gap}분을 두려고 시작을 ${was}에서 ${b.start}${ro(b.start)} 늦췄습니다`;
    };
    for (const f of changed(b) && !changed(a) ? [push, pull] : [pull, push]) {
      const said = f();
      if (said) return said;
    }
  }
  return "";
}

// the latest a stop the code adds after the day's last stop may end: `to` (the reader's end), or the night's stay
// less the leg's margin to it from `page` (the added place)
function endBefore(day, to, page, c, kb) {
  if (!day.stay) return to;
  return Math.min(to, hm(day.stay.start) - marginOf(page, day.stay.page, c, kb));
}

// where a stop the code adds goes in d.stops: before `next` (a stop of day.own), else after `prev`, else at the end
// (a night's stay stays last)
function insertAt(d, prev, next, stop) {
  const j = next ? d.stops.indexOf(next) : prev ? d.stops.indexOf(prev) + 1 : d.stops.findIndex((s) => s.role === "stay");
  d.stops.splice(j < 0 ? d.stops.length : j, 0, stop);
}

/** A meal for one day that lacks it (repair 4): the slots between two stops (or the day's ends) nearest the meal's
 *  aim first; at each, the restaurants nearest the stop before it (then the one after it). A slot keeps the legs'
 *  margins and may shorten the stop before it (its end) or after it (its start), each keeping KEEP_MIN minutes; a
 *  start with nothing to shorten comes first, then the one nearest the aim. freed: the stop mealInstead took out for
 *  it. Returns the reader's words, or '' when nothing fits. */
function addMeal(plan, d, day, m, c, kb, freed = null, max = near(c, "meal")) {
  if (d.stops.length >= STOPS_MAX) return "";   // a full day: mealInstead makes room
  const own = day.own;
  const at = (s) => ((kb.docs[s.page] || {}).f || {}).g;
  const slots = [];
  for (let p = 0; p <= own.length; p += 1) {
    const P = own[p - 1] || null, N = own[p] || null;
    const a = P ? hm(P.end) : day.lo, b = N ? hm(N.start) : day.hi;
    slots.push({ P, N, gap: a > m.at ? a - m.at : b < m.at + MEAL_MIN ? m.at + MEAL_MIN - b : 0 });
  }
  slots.sort((x, y) => x.gap - y.gap);
  const tries = slots.flatMap(({ P, N }) => [P, N].filter((s) => s && at(s)).map((anchor) => ({ P, N, anchor })));
  for (const { P, N, anchor } of tries) {
    const pick = nearestOpen({ kb, c, date: d.date, at: at(anchor), max, taken: new Set(plan.days.flatMap((x) => x.stops.map((st) => st.page))),
      fits: (x) => isMeal(x) && codeFits(c, x.f, "meal"),
      slot: (x) => {
        const mP = P ? marginOf(P.page, x.page, c, kb) : 0;
        const mN = N ? marginOf(x.page, N.page, c, kb) : 0;
        const by = endBefore(day, day.hi, x.page, c, kb);
        const starts = [];
        for (let s = m.first; s <= m.last; s += 5) {
          const cutP = P ? Math.max(0, hm(P.end) + mP - s) : 0, cutN = N ? Math.max(0, s + MEAL_MIN + mN - hm(N.start)) : 0;
          if (P ? hm(P.end) - cutP - hm(P.start) < keepOf(P) : s < day.lo) continue;
          if (N ? hm(N.end) - hm(N.start) - cutN < keepOf(N) : s + MEAL_MIN > by) continue;
          starts.push({ a: s, b: s + MEAL_MIN, cutP, cutN, score: (cutP + cutN ? 1000 + cutP + cutN : 0) + Math.abs(s - m.at) });
        }
        return starts.sort((x, y) => x.score - y.score).slice(0, 8);
      } });
    if (!pick) continue;
    const bits = [];
    if (pick.cutP) {
      const to = hhmm(hm(P.end) - pick.cutP);
      bits.push(`${P.name} 끝을 ${P.end}에서 ${to}${ro(to)} 당겼습니다`);
      P.end = hhmm(hm(P.end) - pick.cutP);
    }
    if (pick.cutN) {
      const to = hhmm(hm(N.start) + pick.cutN);
      bits.push(`${N.name} 시작을 ${N.start}에서 ${to}${ro(to)} 늦췄습니다`);
      N.start = hhmm(hm(N.start) + pick.cutN);
    }
    insertAt(d, P, N, { page: pick.page, name: pick.name, start: hhmm(pick.a), end: hhmm(pick.b), role: "meal", why: "", by: "site" });
    const room = freed ? `자리를 내려고 ${freed.by ? `사이트가 ${freed.by === "swap" ? "쉬는 곳 대신" : "빈 시간에"} 넣었던 ` : ""}${freed.name}${eul(freed.name)} 빼고 ` : "";
    return `${m.label}: 식사할 곳이 없어 ${room}${anchor === P ? "앞" : "다음"} 장소 ${anchor.name}에서 가까운 음식점 ${pick.name}(직선 ${km(pick.m)}, ${openWords(pick.open)})${eul(pick.name)} `
      + `${hhmm(pick.a)}~${hhmm(pick.b)}에 넣었습니다${bits.length ? ` — ${bits.join(", ")}` : ""}`;
  }
  return "";
}

/** A meal for a day with no slot left for it (repair 4, when addMeal finds none — a packed day whose closed stops were
 *  all swapped): a stop the code put in itself (swapped in for a closed one, or added to an empty stretch; never a
 *  meal), inside the meal's window and nearest its aim, gives up its place when the meal then fits; the stops the
 *  model chose stay — unless `any` (planner.settle, the code's own first). dayOf: the reader's day, read again after
 *  the stop is out. Returns the reader's words, or ''. */
function mealInstead(plan, d, dayOf, m, c, kb, { max = near(c, "meal"), any = false } = {}) {
  const own = dayOf().own;
  if (own.length < 2) return "";
  const mine = own.filter((s) => (any || s.by === "site" || s.by === "swap") && s.role !== "meal" && hm(s.start) < m.near[1] && hm(s.end) > m.near[0])
    .sort((a, b) => Number(!a.by) - Number(!b.by) || Math.abs(hm(a.start) - m.at) - Math.abs(hm(b.start) - m.at));
  for (const x of mine) {
    const j = d.stops.indexOf(x);
    d.stops.splice(j, 1);
    const said = addMeal(plan, d, dayOf(), m, c, kb, x, max);
    if (said) return said;
    d.stops.splice(j, 0, x);
  }
  return "";
}

/** One place for one empty stretch (repair 5): after the stop before it (or from the day's start), the places
 *  nearest that stop (then the one after it) that fit the reader's likings and needs, FILL_MAX minutes when the
 *  stretch holds them with the margins, else no fewer than FILL_MIN. Returns the reader's words, or '' when nothing
 *  fits. */
function fillGap(plan, d, day, g, c, kb, max = near(c, "fill")) {
  const at = (s) => ((kb.docs[s.page] || {}).f || {}).g;
  const P = day.own[g.at - 1] || null, N = day.own[g.at] || null;
  for (const anchor of [P, N].filter((s) => s && at(s))) {
    const said = fillFrom(plan, d, day, g, P, N, anchor, c, kb, max);
    if (said) return said;
  }
  return "";
}
function fillFrom(plan, d, day, g, P, N, anchor, c, kb, max = near(c, "fill")) {
  const at = (s) => ((kb.docs[s.page] || {}).f || {}).g;
  // the likings the data can read as places to visit (history, nature, islands, alleys, experience); none picked:
  // any place to visit. 카페·빵집 adds the cafés.
  const likes = c.prefs.filter((p) => PREF_TYPES[p] || p === "islands");
  const cafe = c.prefs.includes("cafe");
  const fees = knownFees(plan, c, kb);
  const pick = nearestOpen({ kb, c, date: d.date, at: at(anchor), max, taken: new Set(plan.days.flatMap((x) => x.stops.map((st) => st.page))),
    fits: (x) => ((x.f.kd === "attraction" && (!likes.length || likes.some((p) => prefFits(p, x)))) || (cafe && isCafe(x)))
      && codeFits(c, x.f, x.f.kd === "food" ? "cafe" : "visit"),
    rank: (x) => { const rr = rainRank(c, x.f); return rr === null ? null : [rr, freeRank(c, x.f)]; },
    slot: (x) => {
      const mP = P ? marginOf(P.page, x.page, c, kb) : 0;
      const mN = N ? marginOf(x.page, N.page, c, kb) : 0;
      const a = Math.ceil((P ? hm(P.end) + mP : g.from) / 5) * 5;
      const room = Math.floor(((N ? hm(N.start) - mN : endBefore(day, g.to, x.page, c, kb)) - a) / 5) * 5;
      const long = isCafe(x.doc) ? FILL_MIN : FILL_MAX;
      return [...new Set([Math.min(long, room), FILL_MIN])].filter((n) => n >= FILL_MIN && n <= room).map((n) => ({ a, b: a + n }));
    },
    put: (x) => {
      const stop = { page: x.page, name: x.name, start: hhmm(x.a), end: hhmm(x.b), role: x.f.kd === "food" ? "cafe" : "visit" };
      insertAt(d, P, N, stop);
      const bad = overBudget(plan, c, kb, fees);
      d.stops.splice(d.stops.indexOf(stop), 1);
      return !bad;
    } });
  if (!pick) return "";
  const role = pick.f.kd === "food" ? "cafe" : "visit";
  insertAt(d, P, N, { page: pick.page, name: pick.name, start: hhmm(pick.a), end: hhmm(pick.b), role, why: "", by: "site" });
  const why = [...likes.filter((p) => prefFits(p, pick.doc)).map((p) => PREF_LABEL[p]), ...(role === "cafe" ? [PREF_LABEL.cafe] : []),
    ...(c.needs.includes("rain") && rainRank(c, pick.f) === 0 && pick.f.kd === "attraction" ? ["실내"] : []), openWords(pick.open)];
  return `빈 시간 ${hhmm(g.from)}~${hhmm(g.to)}(${span(g.minutes)}): ${anchor === P ? "앞" : "다음"} 장소 ${anchor.name}에서 가까운 ${pick.name}(직선 ${km(pick.m)}, `
    + `${why.join(" · ")})${eul(pick.name)} ${hhmm(pick.a)}~${hhmm(pick.b)}에 넣었습니다`;
}

// a plan the code made whole from the site's data (no stop of the model's): its one line in 'fixed', always first and
// always alone, starting '일정 전체:' — and every stop of it added: true (the page tells such a plan by these;
// docs/handover/planner.md '화면과의 계약')
export const CODE_PLAN_LINE = "일정 전체: AI가 조건에 맞는 일정을 내지 못해 사이트 자료로 일정을 짰습니다";
export const CODE_PLAN_BUSY = "일정 전체: AI 응답을 받지 못해 사이트 자료로 일정을 짰습니다";
export const CODE_PLAN_SETTLE = "일정 전체: AI가 고른 곳으로는 조건을 다 맞출 수 없어 사이트 자료로 일정을 새로 짰습니다";

// ------------------------------------------------------------------ settle: every plan the page gets is finished
// (operator 2026-10-18: '이런 거 좀 안 뜨게 할 수 없어? 무조건 완성된 결과가 나오게 하라니까' — a 1-day result showed
// '확인할 것이 남은 초안이에요'; before it '조건을 다 맞추지 못한 초안' and '코스를 만들지 못했습니다')
const STAY_LATEST = 23 * 60 + 29;
const NEED_WORD = { wheelchair: "휠체어", stroller: "유모차", parking: "주차", free: "입장료 없는 곳" };

/** The last step of every plan, after repair, align and the check: what the check still finds is put right by the
 *  code, the targeted fix of each kind first, until nothing is left —
 *  0. once, before the check: a night's stay on the trip's last day ahead of a stop goes; the same place twice in a
 *     row overlapping becomes one; a stop whose data says 'no' to a hard need the reader picked (휠체어, 유모차, 입장료
 *     없는 곳, 주차) becomes the nearest place of its kind the data says fits (swapIn) or goes; a visit whose data says
 *     nothing of such a need becomes one nearby the data says fits, when there is one; a stop a date rule may close
 *     that day (a 설·추석·공휴일 rule) becomes a place sure to be open nearby, when there is one;
 *  then, up to three rounds while the check finds something, by kind:
 *  1. closed that day: swapped (swapIn), else out; hours: cut to the hours that date, else swapped, else out;
 *  2. rain with a second outdoor visit: swapped for one that is not outdoor, else out; the budget: the dearest paid
 *     visit swapped for a free or cheaper one, else out;
 *  3. before the reader's start or after their end, and the station's margins: cut, else out;
 *  4. a night's stay: moved after the day's last stop (its leg's margin, its check-in, by 23:29), the last stop cut
 *     to the reader's end to make room; a night with none gets another night's or the nearest that can start by 23:29;
 *  5. a leg: its margin, from the whole margin down to the least the check allows, the earlier stop ending sooner or
 *     the later starting later (a stay moving whole) — else the stop the code put in goes, else the farther one;
 *  6. a meal: a restaurant the model gave as a visit or a café becomes the meal; else one is added nearer, then
 *     farther, then in place of a stop the code put in, then of a visit of the model's;
 *  7. an empty stretch: filled (NEAR.fill, then twice it), else the stop before it longer (its hours, 3 hours at most),
 *     else the one after it sooner;
 *  last, a day still flagged is built again around its own stops (plan_build.buildDay, the model's kept in order),
 *  else built again whole; a trip still flagged is the code's own plan (plan_build.buildPlan), which preflight has
 *  shown exists. stats: counts (rounds, rebuilt days, the code's plan). Changes plan; returns the reader's lines. */
export function settle(plan, c, kb, edit = null, stats = {}) {
  const out = [];
  const many = plan.days.length > 1;
  const dayW = (i) => (many ? `${i + 1}일차 ` : "");
  stats.rounds = 0;
  stats.rebuilt = stats.rebuilt || 0;
  out.push(...settleFit(plan, c, kb, dayW));
  for (let round = 0; round < 3; round += 1) {
    if (!planFlags(plan, c, kb, edit).list.length) break;
    stats.rounds += 1;
    const said = settleRound(plan, c, kb, edit, dayW);
    out.push(...said);
    if (!said.length) break;
  }
  // a day still flagged: built again around its stops, else whole
  let left = planFlags(plan, c, kb, edit).list;
  stats.left = left.map((x) => x.kind);
  for (const i of [...new Set(left.map((x) => x.day))].filter((x) => x >= 0)) {
    const d = plan.days[i];
    const others = plan.days.filter((_, k) => k !== i);
    const taken = new Set(others.flatMap((x) => x.stops.map((s) => s.page)));
    const prevStay = i > 0 ? plan.days[i - 1].stops.find((s) => s.role === "stay") : null;
    const opts = { taken, plan, edit, anchor: prevStay ? gOf(kb, prevStay.page) : null,
      stay: d.stops.find((s) => s.role === "stay" && !s.by) || null, otherStay: others.map((x) => x.stops.find((s) => s.role === "stay")).find(Boolean) || null };
    if (stats.trace) opts.trace = stats.trace;   // a debugging aid: why each try of the day builder failed
    // an edit keeps the day the model changed, or nothing: a day built anew would be a change the reader never asked
    // for (round-5 verifier: an edit came back as an unrelated trip)
    const built = buildDay(c, kb, i, d.date, { ...opts, seed: d.stops }) || (edit ? null : buildDay(c, kb, i, d.date, opts));
    if (!built) continue;
    const before = d.stops;
    d.stops = built.stops;
    stats.rebuilt += 1;
    out.push(`${dayW(i)}${rebuiltWords(before, d.stops)}`);
  }
  // the budget across the days, or anything else left: the trip as the code makes it (preflight's) — never on an edit
  // (makePlan then keeps the reader's plan and says the change could not be made)
  left = planFlags(plan, c, kb, edit).list;
  if (left.length && !edit) {
    const built = buildPlan(c, kb);
    if (built.plan) {
      // the model's words were for its own places: the code's title and summary, no notes (the code's plan alone)
      Object.assign(plan, { days: built.plan.days, title: built.plan.title, summary: built.plan.summary, notes: [] });
      stats.codePlan = 1;
      out.length = 0;
      out.push(CODE_PLAN_SETTLE);
    }
  }
  return out;
}

// the reader's line for a day built again: the places that went and came, and the night's stay when it moved
function rebuiltWords(was, after) {
  const before = was.filter((s) => s.role !== "stay");
  const now = new Set(after.map((s) => s.page));
  const had = new Set(before.map((s) => s.page));
  const kept = before.filter((s) => now.has(s.page)).map((s) => s.name);
  const gone = before.filter((s) => !now.has(s.page)).map((s) => s.name);
  const added = after.filter((s) => s.role !== "stay" && !had.has(s.page)).map((s) => s.name);
  const list = (xs) => `${xs.join("·")}${eul(xs.at(-1))}`;
  const stayWas = was.find((s) => s.role === "stay"), stay = after.find((s) => s.role === "stay");
  const moved = stay && stayWas && stay.page === stayWas.page && stay.start !== stayWas.start ? `밤 숙소 ${stay.name}${eul(stay.name)} ${stay.start}${ro(stay.start)} 옮기고 ` : "";
  // only what changed: the places that went and came (all of the day's own kept: what was added)
  if (!gone.length) return `조건을 모두 맞추려고 이날 일정에 사이트 자료로 ${added.length ? `${list(added)} 넣고 ` : ""}${moved}시각을 맞췄습니다`;
  return `조건을 모두 맞추려고 이날 일정을 사이트 자료로 다시 짰습니다 — ${list(gone)} 빼고 ${added.length ? `${list(added)} 넣고 ` : ""}${moved}시각을 맞췄습니다`
    + `${kept.length ? ` (${kept.length}곳은 그대로)` : ""}`;
}

/** settle 0: what the data says does not fit, said once — see settle. */
function settleFit(plan, c, kb, dayW) {
  const out = [];
  const hard = c.needs.filter((n) => HARD.includes(n));
  // the same kind as the stop (its type; a restaurant's cuisine, 카페): what a stop that may stay as it is becomes
  const same = (doc) => (x) => !kindOf(doc) || kindOf(x) === kindOf(doc);
  plan.days.forEach((d, i) => {
    const lastDay = i === plan.days.length - 1;
    // a stay on the trip's last day: no night follows it (round-5 verifier: a hotel at 17:30–19:30, after the reader's
    // 18:00 end, was sent)
    if (lastDay) {
      for (const s of d.stops.filter((x) => x.role === "stay")) {
        d.stops.splice(d.stops.indexOf(s), 1);
        out.push(`${dayW(i)}${s.name}: 마지막 날이라 묵지 않아 일정에서 뺐습니다`);
      }
    }
    // one stay a night: the first the day has (round-5 verifier: two stays on one night were sent)
    for (const s of d.stops.filter((x) => x.role === "stay").slice(1)) {
      d.stops.splice(d.stops.indexOf(s), 1);
      out.push(`${dayW(i)}밤 숙소 ${s.name}: 그날 묵을 곳이 이미 있어 일정에서 뺐습니다`);
    }
    // a role is what the place is (readSubmit's rule, for any stop that reached here otherwise)
    for (const s of d.stops) {
      const kd = ((kb.docs[s.page] || {}).f || {}).kd;
      const fit = kd === "stay" ? "stay" : s.role === "stay" || ((s.role === "meal" || s.role === "cafe") && kd !== "food") ? "visit" : s.role;
      if (fit !== s.role) s.role = fit;
    }
    // a night's stay the data says does not fit a hard need the reader picked: out (step 4 puts in one that does)
    for (const s of d.stops.filter((x) => x.role === "stay" && hard.length && hardState(c, (kb.docs[x.page] || {}).f || {}, "stay") === "no")) {
      const f = (kb.docs[s.page] || {}).f || {};
      const need = hard.find((n) => hardState({ ...c, needs: [n] }, f, "stay") === "no");
      d.stops.splice(d.stops.indexOf(s), 1);
      out.push(`${dayW(i)}밤 숙소 ${s.name}: '${NEED_WORD[need]}' 조건에 맞지 않는다고 자료에 있어 일정에서 뺐습니다`);
    }
    // the same place twice in a row, overlapping: one stop
    for (let j = 0; j + 1 < d.stops.length; j += 1) {
      const a = d.stops[j], b = d.stops[j + 1];
      if (a.page !== b.page || hm(b.start) >= hm(a.end)) continue;
      if (hm(b.end) - hm(a.end) >= KEEP_MIN) b.start = a.end;
      else {
        a.end = hhmm(Math.max(hm(a.end), hm(b.end)));
        d.stops.splice(j + 1, 1);
        j -= 1;
      }
    }
    for (let j = d.stops.length - 1; j >= 0; j -= 1) {
      const s = d.stops[j];
      if (s.role === "stay") continue;
      const doc = kb.docs[s.page] || {};
      const f = doc.f || {};
      // a meal at a café or a bakery is a café stop (plan_state.mealIn never counts it as the day's meal; the check
      // then asks for a meal and settle adds one)
      if (s.role === "meal" && isCafe(doc)) {
        s.role = "cafe";
        out.push(`${dayW(i)}${s.name}: 카페·빵집이라 식사가 아닌 카페로 두었습니다`);
      }
      const state = hard.length ? hardState(c, f, s.role) : "ok";
      if (state === "no") {
        const need = hard.find((n) => hardState({ ...c, needs: [n] }, f, s.role) === "no");
        const why = `'${NEED_WORD[need]}' 조건에 맞지 않는다고 자료에 있어`;
        const said = swapIn(plan, d, j, c, kb, { why, fits: (x) => hardState(c, x.f, s.role) !== "no", rank: (x) => (hardState(c, x.f, s.role) === "ok" ? 0 : 1) });
        if (said) out.push(`${dayW(i)}${said}`);
        else {
          d.stops.splice(j, 1);
          out.push(`${dayW(i)}${s.name}: ${why} 일정에서 뺐습니다`);
        }
        continue;
      }
      // a visit the data says nothing of for a need the reader picked: one of the same kind nearby the data says
      // fits, when there is one; else it stays (its line to check stays at the stop)
      if (state === "unknown" && s.role === "visit") {
        const need = hard.find((n) => hardState({ ...c, needs: [n] }, f, s.role) === "unknown");
        const said = swapIn(plan, d, j, c, kb, { why: `'${NEED_WORD[need]}' 자료가 없어`, fits: (x) => hardState(c, x.f, "visit") === "ok" && same(doc)(x) });
        if (said) { out.push(`${dayW(i)}${said}`); continue; }
      }
      // a date rule that may close it that day (a 설·추석·공휴일 rule): a place of the same kind sure to be open, when
      // one is near; else it stays with its line to check
      const info = dayInfo(kb, d.date, s.page);
      if (info.state === "check" && info.checks.some((t) => /규칙/u.test(t))) {
        const said = swapIn(plan, d, j, c, kb, { why: "그날 쉬는지 규칙만으로 알 수 없어", fits: (x, page) => dayInfo(kb, d.date, page).state === "open"
          && same(doc)(x) && (!hard.length || hardState(c, x.f, s.role) !== "no") });
        if (said) out.push(`${dayW(i)}${said}`);
      }
    }
  });
  return out;
}

/** One round of settle 1–7 — see settle. Returns the reader's lines (none: nothing more it can do). */
function settleRound(plan, c, kb, edit, dayW) {
  const out = [];
  const flags = () => planFlags(plan, c, kb, edit).list;
  const drop = (i, j, why) => {
    const s = plan.days[i].stops.splice(j, 1)[0];
    out.push(`${dayW(i)}${s.name}: ${why} 일정에서 뺐습니다`);
  };
  // 0. a stay on the last day, a stay or a stop the data says does not fit a hard need, a day of more than STOPS_MAX
  const WHY0 = { "stay-last": "마지막 날이라 묵지 않아", "stay-two": "그날 묵을 곳이 이미 있어", role: "장소의 종류와 맞지 않아", need: "고른 조건에 맞지 않는다고 자료에 있어" };
  const at0 = new Map();   // one drop a stop
  for (const x of flags().filter((y) => ["stay-last", "stay-two", "role"].includes(y.kind) || (y.kind === "need" && plan.days[y.day].stops[y.j].role === "stay"))) {
    at0.set(`${x.day}|${x.j}`, x);
  }
  for (const x of [...at0.values()].sort((p, q) => q.day - p.day || q.j - p.j)) drop(x.day, x.j, WHY0[x.kind]);
  for (const x of flags().filter((y) => y.kind === "need").sort((p, q) => q.day - p.day || q.j - p.j)) {
    const d = plan.days[x.day];
    if (!d.stops[x.j] || d.stops[x.j].role === "stay") continue;
    const why = "고른 조건에 맞지 않는다고 자료에 있어";
    const said = swapIn(plan, d, x.j, c, kb, { why });
    if (said) out.push(`${dayW(x.day)}${said}`);
    else drop(x.day, x.j, why);
  }
  for (const x of flags().filter((y) => y.kind === "many")) {
    const d = plan.days[x.day];
    while (d.stops.length > STOPS_MAX) {
      const own = d.stops.filter((y) => y.role !== "stay" && y.role !== "meal");
      const k = own.sort((p, q) => Number(!q.by) - Number(!p.by) || hm(p.end) - hm(p.start) - (hm(q.end) - hm(q.start)))[0];
      if (!k) break;
      drop(x.day, d.stops.indexOf(k), `하루 ${STOPS_MAX}곳을 넘어`);
    }
  }
  // 1. closed, hours — the stops from the last, so the indexes hold
  for (const x of flags().filter((y) => y.kind === "closed" || y.kind === "hours").sort((p, q) => q.day - p.day || q.j - p.j)) {
    const d = plan.days[x.day];
    const s = d.stops[x.j];
    if (!s || s.role === "stay") continue;
    if (x.kind === "hours") {
      const w = windowOf(dayInfo(kb, d.date, s.page));
      const a = Math.max(hm(s.start), w.open), b = Math.min(hm(s.end), w.close);
      // (a cut that changes nothing is no fix: the stop is swapped — round-5 verifier, '10:00~13:53에서 10:00~13:53으로')
      if ((a !== hm(s.start) || b !== hm(s.end)) && b - a >= keepOf(s) && a <= w.last && !inBreak((kb.docs[s.page] || {}).f || {}, a, b)) {
        out.push(`${dayW(x.day)}${s.name}: 그날 이용시간에 맞춰 ${s.start}~${s.end}에서 ${hhmm(a)}~${hhmm(b)}${ro(hhmm(b))} 줄였습니다`);
        Object.assign(s, { start: hhmm(a), end: hhmm(b) });
        continue;
      }
    }
    const why = x.kind === "closed" ? `${dateWords(d.date)}은 쉬는 날이라` : "그 시각에 열지 않는다고 자료에 있어";
    const said = swapIn(plan, d, x.j, c, kb, { why });
    if (said) out.push(`${dayW(x.day)}${said}`);
    else drop(x.day, x.j, why);
  }
  // 2. rain, budget
  for (const x of flags().filter((y) => y.kind === "rain")) {
    const d = plan.days[x.day];
    const outdoor = d.stops.map((s, j) => ({ s, j })).filter(({ s }) => s.role === "visit" && isOutdoor((kb.docs[s.page] || {}).f || {}));
    for (const { j } of outdoor.slice(1).reverse()) {
      const why = "비 오는 날 야외는 하루 한 곳까지라";
      const said = swapIn(plan, d, j, c, kb, { why, fits: (y) => !isOutdoor(y.f) });
      if (said) out.push(`${dayW(x.day)}${said}`);
      else drop(x.day, j, why);
    }
  }
  const dear = (fee) => Math.max(0, ...Object.values((fee && fee.tab) || {}).filter(Number.isFinite));
  // what a visit adds to the known admissions (its own table, or a combined ticket that opens it): the known total
  // with it less the known total without it
  const costOf = (i, j) => {
    const total = knownFees(plan, c, kb);
    const st = plan.days[i].stops.splice(j, 1)[0];
    const without = knownFees(plan, c, kb);
    plan.days[i].stops.splice(j, 0, st);
    return total - without;
  };
  // each turn swaps the visit that costs most for a free or cheaper one or takes it out: at most one turn a stop
  const all = plan.days.reduce((n, d) => n + d.stops.length, 0);
  for (let n = 0; n < all && flags().some((y) => y.kind === "budget"); n += 1) {
    const paid = plan.days.flatMap((d, i) => d.stops.map((s, j) => ({ s, i, j })))
      .filter(({ s }) => s.role === "visit")
      .map((y) => ({ ...y, won: costOf(y.i, y.j) }))
      .filter((y) => y.won > 0)
      .sort((p, q) => q.won - p.won || q.i - p.i || q.j - p.j);
    if (!paid.length) break;
    const { s, i, j, won } = paid[0];
    const why = "입장료 예산을 넘어";
    const own = dear(((kb.docs[s.page] || {}).f || {}).fee) || won;
    const cheaper = (y) => !!(y.f.fee && (y.f.fee.free || (y.f.fee.tab && dear(y.f.fee) < own)));
    const said = swapIn(plan, plan.days[i], j, c, kb, { why, fits: cheaper, rank: (y) => (y.f.fee && y.f.fee.free ? 0 : 1) });
    if (said) out.push(`${dayW(i)}${said}`);
    else drop(i, j, why);
  }
  // 3. the reader's start and end, the station's margins
  for (const x of flags().filter((y) => ["start", "end", "hub-from", "hub-to"].includes(y.kind)).sort((p, q) => q.day - p.day || (q.j ?? 0) - (p.j ?? 0))) {
    const d = plan.days[x.day];
    const own = d.stops.filter((s) => s.role !== "stay");
    const s = x.j !== undefined ? d.stops[x.j] : x.kind === "hub-from" ? own[0] : own.at(-1);
    if (!s || !d.stops.includes(s)) continue;
    const j = d.stops.indexOf(s);
    if (x.kind === "start" || x.kind === "hub-from") {
      const a = hm(c.start) + (x.kind === "hub-from" || (c.from && x.day === 0) ? HUB_MARGIN : 0);
      if (hm(s.start) >= a) continue;
      if (hm(s.end) - a >= keepOf(s)) {
        out.push(`${dayW(x.day)}${s.name}: ${c.from ? `${HUBS[c.from]}에서 출발하는 여유를 두려고` : `고른 시작 ${c.start}에 맞춰`} 시작을 ${s.start}에서 ${hhmm(a)}${ro(hhmm(a))} 늦췄습니다`);
        s.start = hhmm(a);
      } else drop(x.day, j, c.from ? `${HUBS[c.from]}에서 출발하는 여유를 두면 시간이 남지 않아` : `고른 시작 ${c.start} 전이라`);
    } else {
      const b = hm(c.end) - (x.kind === "hub-to" || (c.to && x.day === plan.days.length - 1) ? HUB_MARGIN : 0);
      if (hm(s.end) <= b) continue;
      if (b - hm(s.start) >= keepOf(s)) {
        out.push(`${dayW(x.day)}${s.name}: ${c.to ? `${HUBS[c.to]}${ro(HUBS[c.to])} 돌아가는 여유를 두려고` : `고른 끝 ${c.end}에 맞춰`} 끝을 ${s.end}에서 ${hhmm(b)}${ro(hhmm(b))} 당겼습니다`);
        s.end = hhmm(b);
      } else drop(x.day, j, c.to ? `${HUBS[c.to]}${ro(HUBS[c.to])} 돌아가는 여유를 두면 시간이 남지 않아` : `고른 끝 ${c.end} 뒤라`);
    }
  }
  // 4. stays
  for (const x of flags().filter((y) => ["stay-mid", "stay-ci", "stay-missing"].includes(y.kind))) {
    const said = settleStay(plan, plan.days[x.day], x, c, kb);
    if (said) out.push(`${dayW(x.day)}${said}`);
  }
  // 5. legs
  for (const x of flags().filter((y) => y.kind === "leg").sort((p, q) => q.day - p.day || q.j - p.j)) {
    const d = plan.days[x.day];
    const a = d.stops[x.j], b = d.stops[x.j + 1];
    if (!a || !b) continue;
    const said = widen(d, x.j, c, kb, !changed(a) && !changed(b));
    if (said) { out.push(`${dayW(x.day)}${said}`); continue; }
    // the stop that cannot be reached goes: the code's own first, else the one farther from its other neighbour
    const far = (s, o) => (o && gOf(kb, s.page) && gOf(kb, o.page) ? metres(gOf(kb, s.page), gOf(kb, o.page)) : 0);
    let k = changed(b) && !changed(a) ? x.j + 1 : changed(a) && !changed(b) ? x.j : far(b, d.stops[x.j + 2]) >= far(a, d.stops[x.j - 1]) ? x.j + 1 : x.j;
    if (d.stops[k].role === "stay") k = x.j;
    if (d.stops[k].role === "stay") continue;
    drop(x.day, k, "앞뒤 장소와 이동 여유를 둘 수 없어");
  }
  // 6. meals
  for (const x of flags().filter((y) => y.kind === "meal")) {
    const d = plan.days[x.day];
    const m = MEALS[x.meal];
    // a restaurant given as a visit or a café inside the window: the meal
    const as = d.stops.find((s) => s.role !== "meal" && s.role !== "stay" && isMeal(kb.docs[s.page]) && (hm(s.start) + hm(s.end)) / 2 >= m.near[0]
      && (hm(s.start) + hm(s.end)) / 2 < m.near[1] && hm(s.end) - hm(s.start) >= 30);
    if (as) {
      as.role = "meal";
      out.push(`${dayW(x.day)}${as.name}: ${m.label} 시간의 음식점이라 식사 장소로 두었습니다`);
      continue;
    }
    const dayOf = () => readerDay(plan, c, x.day, kb);
    if (!dayOf()) continue;
    // nearer first, then twice as far, then as far as the day builder looks (plan_build RADII: 6 km without a car,
    // 15 km by car)
    const far = 2 * near(c, "meal") + (c.move === "car" ? 0 : 1500);
    const farthest = c.move === "car" ? 15000 : 6000;
    const said = addMeal(plan, d, dayOf(), m, c, kb) || addMeal(plan, d, dayOf(), m, c, kb, null, far)
      || mealInstead(plan, d, dayOf, m, c, kb, { max: far }) || addMeal(plan, d, dayOf(), m, c, kb, null, farthest)
      || mealInstead(plan, d, dayOf, m, c, kb, { max: farthest, any: true });
    if (said) out.push(`${dayW(x.day)}${said}`);
  }
  // 7. empty stretches
  for (const x of flags().filter((y) => y.kind === "gap")) {
    const d = plan.days[x.day];
    const day = readerDay(plan, c, x.day, kb);
    if (!day) continue;
    const g = idleGaps(day).find((y) => y.from === x.from && y.to === x.to) || idleGaps(day).find((y) => y.minutes > IDLE);
    if (!g) continue;
    const said = fillGap(plan, d, day, g, c, kb) || fillGap(plan, d, day, g, c, kb, 2 * near(c, "fill"));
    if (said) { out.push(`${dayW(x.day)}${said}`); continue; }
    // the stop before it stays longer (its hours, 3 hours at most — a meal or a café 90 minutes), else the one after it
    // starts sooner
    const P = day.own[g.at - 1], N = day.own[g.at];
    const need = g.minutes - IDLE;
    if (P) {
      const w = windowOf(dayInfo(kb, d.date, P.page));
      const lim = Math.min(w.close, hm(P.start) + stretchMax(P), N ? hm(N.start) - marginOf(P.page, N.page, c, kb) : g.to);
      const nb = Math.min(lim, hm(P.end) + need);
      if (nb - hm(P.end) >= need && !inBreak((kb.docs[P.page] || {}).f || {}, hm(P.start), nb)) {
        out.push(`${dayW(x.day)}${P.name}: 빈 시간을 줄이려고 끝을 ${P.end}에서 ${hhmm(nb)}${ro(hhmm(nb))} 늦췄습니다`);
        P.end = hhmm(nb);
        continue;
      }
    }
    if (N) {
      const w = windowOf(dayInfo(kb, d.date, N.page));
      const lim = Math.max(w.open, hm(N.end) - stretchMax(N), P ? hm(P.end) + marginOf(P.page, N.page, c, kb) : g.from);
      const na = Math.max(lim, hm(N.start) - need);
      if (hm(N.start) - na >= need && na <= w.last && !inBreak((kb.docs[N.page] || {}).f || {}, na, hm(N.end))) {
        out.push(`${dayW(x.day)}${N.name}: 빈 시간을 줄이려고 시작을 ${N.start}에서 ${hhmm(na)}${ro(hhmm(na))} 당겼습니다`);
        N.start = hhmm(na);
      }
    }
  }
  return out;
}

/** settle 4: a night's stay out of place or missing — see settle. */
function settleStay(plan, d, x, c, kb) {
  const own = d.stops.filter((s) => s.role !== "stay");
  const last = own.at(-1);
  const ciOf = (page) => mins(((kb.docs[page] || {}).f || {}).ci);
  const at = (page) => {
    if (!last) return null;
    const a = Math.max(hm(last.end) + marginOf(last.page, page, c, kb), ciOf(page) ?? 0);
    return a <= STAY_LATEST ? a : null;
  };
  const put = (s, a) => {
    if (d.stops.includes(s)) d.stops.splice(d.stops.indexOf(s), 1);
    d.stops.push(Object.assign(s, { start: hhmm(a), end: hhmm(Math.min(a + 60, 23 * 60 + 59)) }));
  };
  const s = x.kind === "stay-missing" ? null : d.stops[x.j];
  if (s && s.role === "stay") {
    const a = at(s.page);
    if (a !== null) {
      const was = s.start;
      put(s, a);
      s.moved = true;
      return `밤 숙소 ${s.name}: 그날 마지막 장소 ${last.name} 뒤로 시작을 ${was}에서 ${hhmm(a)}${ro(hhmm(a))} 옮겼습니다`;
    }
  }
  if (!last) return "";
  // the day runs too late for any stay (none can start by 23:29 after it): the last stop is cut to the reader's end
  if (at(last.page) === null && hm(last.end) > hm(c.end) && hm(c.end) - hm(last.start) >= keepOf(last)) {
    const was = last.end;
    last.end = c.end;
    return `${last.name}: 밤 숙소에 들어갈 여유를 두려고 끝을 ${was}에서 ${c.end}${ro(c.end)} 당겼습니다`;
  }
  // another night's stay, else the nearest that can start by 23:29 (STAY_NEAR, then farther); a full day first gives
  // up a stop the code put in
  if (!s && makeRoom(d) === null) return "";
  const other = plan.days.filter((y) => y !== d).map((y) => y.stops.find((z) => z.role === "stay" && codeFits(c, (kb.docs[z.page] || {}).f || {}, "stay"))).find(Boolean);
  let pick = null;
  if (other && at(other.page) !== null) pick = { page: other.page, name: other.name, how: `다른 밤과 같은 숙소 ${other.name}${eul(other.name)} 넣었습니다` };
  const g = lastPoint(kb, d.stops);
  if (!pick && g) {
    const stays = placesOf(kb).filter((p) => p.doc.f.kd === "stay" && codeFits(c, p.doc.f, "stay"))
      .map((p) => ({ page: p.page, name: p.doc.t, m: metres(g, p.doc.f.g), camp: CAMP.test(p.doc.f.ty || "") }))
      .sort((p, q) => p.camp - q.camp || p.m - q.m || (p.name < q.name ? -1 : 1));
    for (const R of [STAY_NEAR, 10000, 20000, Infinity]) {
      const y = stays.find((z) => z.m <= R && at(z.page) !== null);
      if (y) { pick = { ...y, how: `${gOf(kb, last.page) ? last.name : "그날 장소"}에서 가까운 숙소 ${y.name}(직선 ${km(y.m)})${eul(y.name)} 넣었습니다 — 객실·요금은 숙소에 확인` }; break; }
    }
  }
  if (!pick) return "";
  if (s && d.stops.includes(s)) d.stops.splice(d.stops.indexOf(s), 1);
  put({ page: pick.page, name: pick.name, start: "", end: "", role: "stay", why: "", by: "site" }, at(pick.page));
  return `밤 숙소: ${s ? `${s.name}에 그날 들어갈 수 없어 ` : "일정에 없어 "}${pick.how}`;
}

// the check's words for the model, as the reader reads them: no field names, no instruction to the planner
const FOR_MODEL = / — (?:일정에서 뺀다|출발지에서 오는 여유를 둔다|돌아갈 여유를 둔다|무료이거나 더 싼 곳으로 바꾼다|여유를 늘리거나 가까운 곳으로 바꾼다|이 구간을 따로 한 줄.*|그 시간에 여는 음식점을 넣는다|가까운 장소를 넣거나 앞뒤 장소를 늘린다|그날 마지막에 둔다|체크인 뒤로 둔다|맞는 곳으로 바꾼다|하루 \d+곳까지로 줄인다)$/u;
export const readerFlag = (t) => String(t).replace(/\(role stay\)/gu, "").replace(/독자가 정한 /gu, "고른 ").replace(FOR_MODEL, "")
  .replace(/\s{2,}/gu, " ").trim();

/** Where the trip starts and ends when the reader named a station or a terminal (plan_geo.hubLegs with the form's
 *  stations and terminals). */
export const hubLegs = (plan, c) => hubLegsOf(plan, c, HUBS);

/** The model's sentences read against the pages: numbers the pages do not have, words that claim a check. Returns
 *  errors (Korean, for the model). */
export function textIssues(plan, c, kb, fees) {
  const errors = [];
  const own = (key) => ((kb.docs[key] || {}).x || "");
  const plain = [c.date, c.start, c.end, String(c.budget ?? ""), c.note, ...plan.days.flatMap((d) => d.stops.flatMap((s) => [s.start, s.end])),
    String(fees.known), String(fees.total ?? "")].join(" ");
  const all = `${plan.days.flatMap((d) => d.stops.map((s) => own(s.page))).join("\n")}\n${plain}`;
  plan.days.forEach((d, i) => d.stops.forEach((s, j) => {
    const g = grounded(s.why, `${own(s.page)}\n${plain}`);
    if (g.bad.length) errors.push(`${i + 1}일차 ${j + 1}번 ${s.name} why의 숫자 ${g.bad.join("·")}가 그 장소 페이지에 없다 — 페이지에 있는 사실만 쓴다`);
    if (g.claim) errors.push(`${i + 1}일차 ${j + 1}번 ${s.name} why: '확인됐다·보장·문제없다'는 말은 쓰지 않는다(확인 상태는 사이트가 보여 준다)`);
  }));
  for (const [what, text] of [["summary", plan.summary], ...plan.notes.map((n, k) => [`notes ${k + 1}`, n])]) {
    const g = grounded(text, all);
    if (g.bad.length) errors.push(`${what}의 숫자 ${g.bad.join("·")}가 일정의 장소 페이지에 없다 — 요금·합계·연도·거리는 쓰지 않는다(사이트가 계산해 보여 준다)`);
    if (g.claim) errors.push(`${what}: '확인됐다·보장·문제없다·모두 가능'은 쓰지 않는다 — 확인 상태는 사이트가 따로 보여 준다`);
  }
  return errors;
}

/** The last word on the model's sentences after its one fix: a reason, a note or a summary sentence that still has a
 *  number the pages lack or claims a check is left out. */
export function trimText(plan, c, kb, fees) {
  const own = (key) => ((kb.docs[key] || {}).x || "");
  const plain = [c.date, c.start, c.end, String(c.budget ?? ""), c.note, ...plan.days.flatMap((d) => d.stops.flatMap((s) => [s.start, s.end])),
    String(fees.known), String(fees.total ?? "")].join(" ");
  const all = `${plan.days.flatMap((d) => d.stops.map((s) => own(s.page))).join("\n")}\n${plain}`;
  const ok = (text, src) => { const g = grounded(text, src); return !g.bad.length && !g.claim; };
  for (const d of plan.days) for (const s of d.stops) if (!ok(s.why, `${own(s.page)}\n${plain}`)) s.why = "";
  plan.summary = dropSentences(plan.summary, (x) => ok(x, all));
  plan.notes = plan.notes.filter((n) => ok(n, all));
  return plan;
}

// a place said to be out of the plan: its name — alone or in a list ('A와 B는') — with a form of leaving it out a few
// characters after it ('A 대신', 'A는 빼고', 'A는 뺐습니다', 'A는 일정에서 제외했습니다', 'A는 제외하고 짰습니다', 'A는
// 월요일 휴관이라'; no comma or full stop between) or a closed-day word right before it ('휴관인 A', '쉬는 날인 A'). Only
// such forms: '빼놓을 수 없는', '빼어난', '빼곡', '월요일을 제외하고 매일', '쉬는 날 없이', '휴관이 없다' say nothing of
// the kind (review 2026-10-18), and neither does a bare 쉬는·쉬어 ('쉬어 가는', '쉬는 시간').
const LOST = "\u0001";
const OUT_AFTER = new RegExp(String.raw`^[^.!?,。\u0001]{0,10}?(?:대신|${CUT.source}|제외(?:했|하였|됐|되었)|일정에서\s*제외`
  + String.raw`|제외하고\s*(?:[^\s.!?,。\u0001]+\s+)?(?:넣|바꾸|바꿔|바꿨|짰|짜)|(?:휴관|휴무|쉬는\s*날)(?!\s*일?\s*[이가은는도]?\s*(?:없|아[니닙닌님])))`, "u");
const OUT_BEFORE = /(?:휴관|휴무|쉬는\s*날)\s*(?:중)?인\s*$/u;
// a place that went is masked as LOST and a mark of its own (a private-use character: the n-th place that went)
const LOST_RUN = /\u0001[\uE000-\uF8FF](?:\s*(?:과|와|이랑|하고|및|[,·])\s*\u0001[\uE000-\uF8FF])*/gu;
/** The model's words read against the plan the code made of them (outside evaluation 2026-10-18: after an edit took
 *  the lunch out, the title still promised it): a sentence of the summary or a note, or a stop's reason, that names a
 *  place the plan had (`had`: the pages of every plan the model handed over in the run, and on an edit the plan before
 *  it — makePlan's `seen`) and no longer has is left
 *  out — unless every such name in it is said to be out (OUT_AFTER, OUT_BEFORE: 'A는 월요일 휴관이라 B로 바꿨습니다'
 *  stays, 'A 대신 C' goes when C went too); a summary or note sentence that names 점심 or 저녁 when the plan has no meal
 *  of that kind goes too, unless it says that meal is left out; a title that names a place that went, or promises a
 *  lunch or a dinner the plan lacks, becomes a plain one the code writes. The names are the site's own (each place's
 *  title and other names, kb.placeNames); the longer name is read first, a kept place's before a gone one's of the
 *  same length. Changes the plan in place; returns what it changed, in words for the reader. */
export function align(plan, c, kb, had, { final = false } = {}) {
  const out = [];
  const now = new Set(plan.days.flatMap((d) => d.stops.map((s) => s.page)));
  // final (the last reading, after settle): a place of the site the words name that no plan of the run had (round-5
  // verifier: '점심은 한일옥에서' for a plan that never had it) is read as one that went, and said to be out or not, its
  // sentence goes (the model cannot have left out what it never had) — names of three characters or more, so a word
  // is not read as one
  const words = [plan.title, plan.summary, ...plan.notes, ...plan.days.flatMap((d) => d.stops.map((s) => s.why))].join("\n");
  const never = new Set(final ? kb.placeNames.filter(([n, k]) => [...n].length >= 3 && !now.has(k) && !had.has(k) && kb.docs[k] && words.includes(n)).map(([, k]) => k) : []);
  const gone = [...new Set([...had, ...never].filter((k) => !now.has(k) && kb.docs[k]))];
  const names = (keys) => [...new Set([...[...keys].map((k) => kb.docs[k].t), ...kb.placeNames.filter(([, k]) => keys.has(k)).map(([n]) => n)])];
  const marks = [...names(new Set([...now].filter((k) => kb.docs[k]))).map((n) => [n, " "]),
    ...gone.flatMap((k, i) => names(new Set([k])).map((n) => [n, `${LOST}${String.fromCharCode(0xe000 + (i % 6400))}`]))]
    .sort((a, b) => b[0].length - a[0].length);
  const masked = (text) => marks.reduce((t, [n, to]) => t.split(n).join(to), String(text || ""));
  const mentions = (text) => masked(text).includes(LOST);
  // every place that went, named in the text, is said to be out
  const saysOut = (text) => {
    const t = masked(text);
    return [...t.matchAll(LOST_RUN)].every((m) => OUT_AFTER.test(t.slice(m.index + m[0].length)) || OUT_BEFORE.test(t.slice(0, m.index)));
  };
  const noMeal = ["lunch", "dinner"].filter((kind) => !plan.days.some((d) => mealIn(d.stops, MEALS[kind], kb)));
  let dropped = 0;
  const named = new Set();   // the places that went named in the sentences left out
  const meals = new Map();   // kind → sentences left out for promising it
  const keep = (s) => {
    if (mentions(s) && (!saysOut(s) || [...masked(s).matchAll(/\u0001([\uE000-\uF8FF])/gu)].some((m) => never.has(gone[m[1].charCodeAt(0) - 0xe000])))) {
      dropped += 1;
      for (const m of masked(s).matchAll(/\u0001([\uE000-\uF8FF])/gu)) named.add(gone[m[1].charCodeAt(0) - 0xe000]);
      return false;
    }
    return true;
  };
  // a sentence of the summary or a note that promises a meal the plan does not have
  const keepMeal = (s) => {
    const kinds = noMeal.filter((kind) => s.includes(MEALS[kind].label) && !eatsElsewhere(kind, s));
    for (const kind of kinds) meals.set(kind, (meals.get(kind) || 0) + 1);
    return !kinds.length;
  };
  if (gone.length) {
    plan.summary = dropSentences(plan.summary, keep);
    plan.notes = plan.notes.map((n) => dropSentences(n, keep)).filter(Boolean);
    for (const d of plan.days) for (const s of d.stops) if (s.why && !keep(s.why)) s.why = "";
    // the line names the places of the sentences left out, not every place that went: those the plan had, then those
    // it never had
    const went = gone.filter((k) => named.has(k) && !never.has(k)).map((k) => kb.docs[k].t);
    const not = gone.filter((k) => named.has(k) && never.has(k)).map((k) => kb.docs[k].t);
    const parts = [went.length ? `일정에서 빠진 ${went.join("·")}` : "", not.length ? `일정에 없는 ${not.join("·")}` : ""].filter(Boolean);
    const lastName = (not.length ? not : went).at(-1);
    if (dropped) out.push(`AI 설명: ${parts.length > 1 ? `${parts[0]}${jong(went.at(-1)) > 0 ? "과" : "와"} ${parts[1]}` : parts[0]}${eul(lastName)} 말하는 문장 ${dropped}개를 뺐습니다`);
  }
  if (noMeal.length) {
    plan.summary = dropSentences(plan.summary, keepMeal);
    plan.notes = plan.notes.map((n) => dropSentences(n, keepMeal)).filter(Boolean);
    for (const [kind, n] of meals) out.push(`AI 설명: 일정에 ${MEALS[kind].label}이 없어 ${MEALS[kind].label}${eul(MEALS[kind].label)} 말하는 문장 ${n}개를 뺐습니다`);
  }
  const lacks = (word, meal) => word.test(plan.title) && !plan.days.some((d) => mealIn(d.stops, meal, kb));
  if (mentions(plan.title) || lacks(/점심/u, MEALS.lunch) || lacks(/저녁/u, MEALS.dinner)) {
    const title = `${dateWords(c.date)} ${titleCity()}${c.days > 1 ? `${c.days - 1}박 ${c.days}일` : "하루"} 코스`;
    out.push(`제목: 바뀐 일정과 맞지 않아 '${plan.title}'에서 '${title}'${ro(title)} 바꿨습니다`);
    plan.title = title;
  }
  return out;
}

/** The plan read against the data and the conditions: each day's checkPlan, the day's hours the reader set, a stay
 *  each night but the last — the day's last stop, not before its check-in time —, the code's own margin on every leg
 *  next to a stop it put in, swapped in or moved, the fee total against the budget, a meal when a day spans one and
 *  no empty stretch (plan_state.completeness). {days: [checkPlan result], flags, fees, complete, ...}. edit:
 *  makePlan's. */
export function verify(plan, c, kb, edit = null) {
  const r = planFlags(plan, c, kb, edit);
  const needs = needsTable(plan, c, kb, r.fees);
  const { aware, checks } = checksList(plan, c, { days: r.days }, needs, r.fees, r.hubs, kb);
  return { days: r.days, flags: r.list.map((x) => x.text), list: r.list, fees: r.fees, hubs: r.hubs, needs, checks, aware, complete: r.complete,
    text: textIssues(plan, c, kb, r.fees) };
}

/** What is still wrong with a finished plan, by the kind of fix it needs (the page's quick fixes): closed (a stop
 *  closed that day), legs (a leg with no time or too little for its line), meal, gaps. */
export function todoOf(check) {
  const out = [];
  if (check.days.some((r) => r.stops.some((s) => s.day === "closed"))) out.push("closed");
  if (check.days.some((r) => r.legs.some((l) => l.flag))) out.push("legs");
  if (check.complete.meals.some((m) => m.state === "missing")) out.push("meal");
  if (check.complete.gaps.length) out.push("gaps");
  return out;
}

/** The reader's list of what the site put right, read against the plan they get (round-5 verifier: it was a running
 *  log — places put in that a later step took out again, cuts that changed nothing): a line that puts in a place no
 *  longer in the plan goes, and so does a later line of that place's; a swap whose place went says the stop it
 *  replaced was taken out; a time changed to itself goes; the same line twice is said once. */
export function tidyFixed(fixed, plan) {
  const names = new Set(plan.days.flatMap((d) => d.stops.map((s) => s.name)));
  const PUT = /가까운 (?:음식점 |숙소 )?(.+?)\(직선 [^)]*\)/u;
  const SAME = /같은 숙소 (.+?)[을를] 넣었습니다/u;
  const SWAP = /^((?:\d일차 )?)(.+?): (.+?) 가까운 (.+?)\(직선 [^)]*\)(?:으로|로|\(으\)로) 바꿨습니다/u;
  const ours = new Set();   // places the code put in that went again
  for (const t of fixed) {
    const m = PUT.exec(t) || SAME.exec(t);
    if (m && !names.has(m[1])) ours.add(m[1]);
  }
  const out = [];
  for (const t of fixed) {
    if (/(\d\d:\d\d~\d\d:\d\d)에서 \1(?:으로|로)/u.test(t) || /(?<![~\d])(\d\d:\d\d)에서 \1(?:으로|로) /u.test(t)) continue;
    const head = /^(?:\d일차 )?(?:밤 숙소 )?(.+?): /u.exec(t);
    if (head && ours.has(head[1])) continue;
    const sw = SWAP.exec(t);
    if (sw && ours.has(sw[4])) {
      if (!names.has(sw[2])) out.push(`${sw[1]}${sw[2]}: ${sw[3]} 일정에서 뺐습니다`);
      continue;
    }
    const m = PUT.exec(t) || SAME.exec(t);
    if (m && ours.has(m[1])) continue;
    if (!out.includes(t)) out.push(t);
  }
  return out;
}

/** Kakao Map directions between two points (the reader's map app works out the route and its time; pipeline/maplinks.py
 *  kakao_transit_url is the same address for 'traffic'): by car, on foot under 1.2 km for a reader without a car,
 *  else public transport. */
export function directionsUrl(a, b, move, m) {
  const mode = move === "car" ? "car" : m !== null && m <= 1200 ? "walk" : "traffic";
  const q = (s) => encodeURIComponent(s).replace(/%2C/gi, " ");
  return { mode, url: `https://map.kakao.com/link/by/${mode}/${q(a.name)},${a.lat},${a.lng}/${q(b.name)},${b.lat},${b.lng}` };
}

/** What the page gets: the plan with each stop's day state and notes from checkPlan (added: a stop the site put in;
 *  swapped: one the site chose for a stop closed that day),
 *  each leg's distance, routes and directions link, the fee lines and total against the budget, what is still
 *  flagged, the completeness (plan_state.completeness) and what is left to fix by kind (todoOf). */
export function finish(plan, check, c, now = new Date(), fixed = []) {
  const days = plan.days.map((d, i) => {
    const r = check.days[i];
    const dt = new Date(`${d.date}T12:00:00Z`);
    return {
      date: d.date, label: `${i + 1}일차 · ${dt.getUTCMonth() + 1}월 ${dt.getUTCDate()}일 (${WEEK[dt.getUTCDay()]})`,
      stops: d.stops.map((s, j) => {
        const st = r.stops[j] || { day: "unknown", notes: [], flags: [] };
        return { path: s.page, name: s.name, start: s.start, end: s.end, role: s.role, why: s.why, day: st.day,
          notes: st.notes, flags: (st.flags || []).map(readerFlag), checks: st.checks || [],
          ...(s.by === "site" ? { added: true } : s.by === "swap" ? { swapped: true } : {}) };
      }),
      legs: r.legs.map((l) => ({ from: l.from, to: l.to, m: l.m, gap: l.gap, routes: l.routes, flag: l.flag,
        ...(l.a && l.b ? directionsUrl(l.a, l.b, c.move, l.m) : {}) })),
      hubs: (check.hubs || []).filter((h) => (h.dir === "from" ? i === 0 : i === plan.days.length - 1)),
    };
  });
  const f = check.fees;
  const fees = { state: f.state, total: f.total, known: f.known, limit: f.limit, verdict: f.verdict, open: f.open,
    conds: f.conds, days: f.days.map((d) => ({ date: d.date, lines: d.lines.map((l) => ({ what: l.what, who: l.who,
      count: l.count, status: l.status, won: l.won ?? null, sub: l.sub, basis: l.basis })) })) };
  // status 'ready' and flags [] for every plan the page gets (makePlan never sends one with flags: operator
  // 2026-10-18); todo stays for pages of the old payload, always empty
  return { v: 2, made: now.toISOString(), title: plan.title, summary: plan.summary, notes: plan.notes, conditions: c,
    days, fees, needs: check.needs, checks: check.checks, aware: check.aware || [], flags: check.flags.map(readerFlag), fixed,
    status: statusOf(check.flags), complete: check.complete, todo: [] };
}

/** The places closed on each date of the trip by their regular closed days or a dated notice — checkPlan's own
 *  reading, places to visit and restaurants — handed over with the conditions so the model does not pick them
 *  (outside evaluation 2026-10-18: five of six stops of a Monday plan were closed that day). One line a date: names
 *  and paths (the path alone when it is the name). */
export function closedHints(c, kb) {
  const keys = kb.keys.filter((k) => kb.docs[k] && kb.docs[k].k === "place" && ["attraction", "food"].includes((kb.docs[k].f || {}).kd));
  return tripDates(c.date, c.days).map((date) => {
    const shut = [];
    for (let k = 0; k < keys.length; k += 12) {   // checkPlan reads twelve stops a call
      const r = kb.checkPlan({ date, stops: keys.slice(k, k + 12).map((page) => ({ page, start: "", end: "" })) });
      r.stops.forEach((s, j) => { if (s.day === "closed") shut.push(keys[k + j]); });
    }
    const label = (key) => (key === `/places/${kb.docs[key].t.replace(/\s+/gu, "-")}/` ? key : `${kb.docs[key].t} ${key}`);
    return `${date}(${WEEK[new Date(`${date}T12:00:00Z`).getUTCDay()]}) 쉬는 곳 ${shut.length}곳 — 이날 일정에 넣지 않는다: ${shut.map(label).join("; ") || "없음"}`;
  }).join("\n");
}

/** The places whose site data fits each need the reader picked (plan_state.needAt 'ok' or, for parking, 'near'),
 *  as catalog paths — handed over with the conditions so the model needs no reading round to find them. At most
 *  30 a need; the facts behind them are the pages' own (the page shows each in the needs table). */
export function needHints(c, kb, max = 30) {
  const needs = c.needs.filter((n) => n !== "lesswalk");
  if (!needs.length) return "고른 조건이 없다.";
  const L = [];
  for (const need of needs) {
    const fit = [];
    for (const key of kb.keys) {
      const d = kb.docs[key];
      if (!d || d.k !== "place" || !d.f) continue;
      if (need !== "parking" && d.f.kd !== "attraction") continue;   // the places to visit; parking matters everywhere
      const r = needAt(need, d.f, d.f.kd === "food" ? "meal" : d.f.kd === "stay" ? "stay" : "visit",
        need === "free" ? { how: "own", states: d.f.fee && d.f.fee.free ? { free: 1 } : d.f.fee && d.f.fee.tab ? { paid: 1 } : { unknown: 1 } } : null);
      if (r.state === "ok" || r.state === "near") fit.push(`${d.t} ${key}`);
      if (fit.length >= max) break;
    }
    L.push(`${NEEDS[need]} — 사이트 자료가 맞다고 하는 곳${fit.length >= max ? `(앞 ${max}곳)` : ""}: ${fit.join("; ") || "없음"}`);
  }
  return L.join("\n");
}

/** Runs one plan to the end through send(). Returns the log record's numbers. */
export async function makePlan({ client, kb, conditions, edit = null, send, signal, now, clock = () => Date.now() }) {
  const c = conditions;
  const t0 = clock();
  const system = buildPlanSystem(kb.catalog, now);
  const convo = [{ role: "user", content: `${neutralise(conditionsText(c, edit))}\n\n${dataBlock("needs", needHints(c, kb))}\n\n`
    + `${dataBlock("closed", closedHints(c, kb))}` }];
  // the places the plan had, which align reads the words against: every page of every plan the model handed over in
  // this run, and on an edit the plan the reader saw (final check 2026-10-18: a fix kept the first answer's words on
  // a lunch it no longer had)
  const seen = new Set();
  const saw = (days) => {
    for (const d of Array.isArray(days) ? days : []) {
      for (const st of Array.isArray(d && d.stops) ? d.stops : []) {
        const key = st && typeof st.page === "string" ? kb.keyFor(st.page) : "";
        if (key && kb.docs[key] && kb.docs[key].k === "place") seen.add(key);
      }
    }
  };
  if (edit) saw(edit.plan.days);
  let reads = 0;
  const rec = { rounds: 0, tools: [], submits: 0, flags: 0, text: 0, in: 0, out: 0, cache_read: 0, cache_write: 0, stop: "", status_plan: "" };
  let outUsed = 0;
  let toolChars = PLAN_LIMITS.toolChars;
  let best = null;   // the latest submit_plan with what cannot stand taken out (readSubmit salvaged), for the end
  // every plan ends here (operator 2026-10-18: '무조건 완성된 결과가 나오게'): settled until the check finds nothing
  // (settle), its words read against it again (align, trimText — a summary left empty is the code's), checked,
  // finished 'ready' — or, should anything still be flagged (preflight has shown a plan exists: never), not sent: an
  // error 'conditions' with the reasons. Returns {plan} or {error}.
  const conclude = (plan, fixed) => {
    const st = {};
    const settled = settle(plan, c, kb, edit, st);
    // the code's own plan: its one line alone (what was put right in the model's plan is of a plan not shown)
    if (st.codePlan) fixed.length = 0;
    fixed.push(...settled, ...(st.codePlan ? [] : align(plan, c, kb, seen, { final: true })));
    rec.settled = settled.length;
    rec.rebuilt = st.rebuilt || 0;
    if (st.codePlan) rec.code_plan = 1;
    if (!plan.summary) plan.summary = codeText(plan, c, kb).summary;
    let check = verify(plan, c, kb, edit);
    if (check.text.length) {
      trimText(plan, c, kb, check.fees);
      if (!plan.summary) plan.summary = codeText(plan, c, kb).summary;
      check = verify(plan, c, kb, edit);
    }
    rec.flags = check.flags.length;
    rec.text = check.text.length;
    fixed.splice(0, fixed.length, ...tidyFixed(fixed, plan));
    if (check.flags.length) {
      rec.status_plan = "unmet";
      // an edit: the reader's plan stays on the page, with the words that the change could not be made
      if (edit) return { error: { type: "error", code: "edit_failed", message: planError("edit_failed") } };
      const problems = preflight(c, kb, now);
      return { error: { type: "error", code: "conditions", message: planError("conditions"), problems: problems.length ? problems : problemsOf(check.list) } };
    }
    const done = finish(plan, check, c, now, fixed);
    rec.status_plan = done.status;
    return { plan: done };
  };
  // a plan the model could not fix in time: finished as it is — what readSubmit took out or changed said first, in
  // the list of what the site put right (never as flags: operator 2026-10-18) — and settled like any other
  const finishAsIs = (b) => {
    step("fees");
    const fixed = [...b.fixes, ...(b.fixed || []), ...repair(b.plan, c, kb, edit)];   // a plan repaired already keeps what was done
    fixed.push(...align(b.plan, c, kb, seen));
    rec.salvaged = 1;
    return conclude(b.plan, fixed);
  };
  const deliver = (r) => {
    send(r.plan ? { type: "plan", plan: r.plan } : r.error, true);
    return { ...rec, status: r.plan ? "ok" : r.error.code };
  };
  const step = (key) => send({ type: "status", step: key, text: PLAN_STATUS[key] });
  step("search");
  // a model call that fails once a plan is in hand (a timeout or the API in the fix round): that plan is finished, not
  // thrown away for the code's own (round-5 verifier) — unless the reader left
  try {
    for (let call = 0; call < PLAN_LIMITS.rounds; call += 1) {
      // the output budget is a ceiling (review CE08): a call asks for what is left after the share kept for the last
      // call, and the last call — forced to hand the plan over — gets that share and no more
      const left = PLAN_LIMITS.outputTokens - outUsed;
      const last = call === PLAN_LIMITS.rounds - 1 || left - PLAN_LIMITS.submitTokens < 2000;
      if (left < 1000) break;
      // the plan must come now: the last call, the reading round spent, or the time for reading gone
      const handOver = last || reads >= PLAN_LIMITS.reads || clock() - t0 > PLAN_LIMITS.readBy;
      const params = { model: MODEL, max_tokens: last ? Math.min(PLAN_LIMITS.maxTokens, left) : Math.min(PLAN_LIMITS.maxTokens, left - PLAN_LIMITS.submitTokens),
        system, tools: PLAN_TOOLS, messages: convo, thinking: { type: "disabled" }, output_config: { effort: "low" },
        tool_choice: handOver ? { type: "tool", name: "submit_plan" } : { type: "any" } };
      const stream = client.messages.stream(params, { signal, timeout: PLAN_LIMITS.callMs });
      for await (const ev of stream) {
        if (ev.type === "content_block_start" && ev.content_block?.type === "tool_use") {
          const name = ev.content_block.name;
          step(name === "search_site" ? "search" : name === "get_pages" ? "read" : rec.submits ? "fix" : "submit");
        }
      }
      const message = await stream.finalMessage();
      rec.rounds += 1;
      const u = message.usage || {};
      rec.in += u.input_tokens || 0;
      rec.out += u.output_tokens || 0;
      rec.cache_read += u.cache_read_input_tokens || 0;
      rec.cache_write += u.cache_creation_input_tokens || 0;
      rec.stop = message.stop_reason || "";
      outUsed += u.output_tokens || params.max_tokens;
      if (message.stop_reason === "refusal") {
        send({ type: "error", code: "refusal", message: planError("refusal") });
        return { ...rec, status: "refusal" };
      }
      const uses = (message.content || []).filter((b) => b.type === "tool_use");
      if (!uses.length) {
        // wrote text instead of handing the plan over (or ran out of tokens): asked once more
        if (message.stop_reason === "max_tokens" || (message.content || []).some((b) => b.type === "text")) {
          if (message.stop_reason !== "max_tokens") convo.push({ role: "assistant", content: message.content });
          if (message.stop_reason !== "max_tokens") convo.push({ role: "user", content: "일정은 글로 쓰지 말고 submit_plan으로 낸다." });
          continue;
        }
        break;
      }
      if (message.stop_reason === "max_tokens") continue;   // a tool input cut off: never run it
      convo.push({ role: "assistant", content: message.content });
      const results = [];
      let done = null;
      if (!uses.some((u) => u.name === "submit_plan")) reads += 1;
      for (const use of uses) {
        rec.tools.push(use.name);
        if (use.name === "submit_plan") {
          rec.submits += 1;
          saw(use.input && use.input.days);
          const { plan, errors, salvaged, fixes } = readSubmit(use.input, c, kb);
          if (errors.length) {
            if (salvaged && (!best || best.fixes.length)) best = { plan: salvaged, fixes };   // never over a whole plan
            // no turn left for a fix (the last call, or the time for fixing gone): the plan as it is
            if (best && (last || clock() - t0 >= PLAN_LIMITS.fixBy)) {
              done = finishAsIs(best);
              break;
            }
            results.push({ type: "tool_result", tool_use_id: use.id, is_error: true,
              content: `고칠 것:\n- ${errors.join("\n- ")}\n고친 일정으로 submit_plan을 다시 부른다.` });
            continue;
          }
          step("fees");
          const fixed = repair(plan, c, kb, edit);
          fixed.push(...align(plan, c, kb, seen));
          rec.repaired = fixed.length;
          best = { plan, fixes: [], fixed };
          const check = verify(plan, c, kb, edit);
          rec.flags = check.flags.length;
          rec.text = check.text.length;
          const wrong = [...check.flags, ...check.text];
          if (wrong.length && rec.submits < PLAN_LIMITS.submits && !last && clock() - t0 < PLAN_LIMITS.fixBy) {
            step("fix");
            results.push({ type: "tool_result", tool_use_id: use.id, is_error: true,
              content: dataBlock("check_plan", `사이트 자료로 확인하니 고칠 것 ${wrong.length}건:\n- ${wrong.join("\n- ")}\n`
                + "고쳐서 submit_plan을 다시 부른다(바꿀 필요 없는 부분은 그대로).") });
            continue;
          }
          done = conclude(plan, fixed);
          break;
        }
        const input = validInput(use.name, use.input);
        if (!input) {
          results.push({ type: "tool_result", tool_use_id: use.id, is_error: true, content: "INVALID_INPUT" });
          continue;
        }
        let out;
        if (use.name === "search_site") out = kb.searchText(input.query.slice(0, QUERY_CHARS), { kind: input.kind, lang: "ko", nameLang: "ko" });
        else if (use.name === "get_pages") out = kb.pagesText(input.ids, { lang: "ko", budget: Math.max(0, toolChars) }).text;
        else out = "check_plan은 쓰지 않는다: submit_plan이 같은 검사를 한다.";
        if (out.length > toolChars) out = toolChars > 200 ? `${out.slice(0, toolChars)}\n… (읽기 한도)` : "읽기 한도를 다 썼다: 지금 아는 것으로 submit_plan을 낸다.";
        toolChars -= out.length;
        results.push({ type: "tool_result", tool_use_id: use.id, content: dataBlock(use.name, out) });
      }
      if (done) return deliver(done);
      convo.push({ role: "user", content: results });
    }
  } catch (err) {
    if (!best || (signal && signal.aborted && signal.reason !== "timeout")) throw err;
    rec.cut = signal && signal.aborted ? "timeout" : typeof err?.status === "number" ? err.status : err?.name || "error";
    return deliver(finishAsIs(best));
  }
  if (best) return deliver(finishAsIs(best));
  // an edit the model handed nothing usable for: the reader's plan stays, said so (as when the model is busy) — the
  // code cannot make the change asked for (round-5 verifier: an unrelated trip came back as the edit)
  if (edit) {
    rec.status_plan = "unmet";
    return deliver({ error: { type: "error", code: "edit_failed", message: planError("edit_failed") } });
  }
  // the model never handed over a plan that holds (operator 2026-10-17: '코스를 만들지 못했습니다'): the trip as the
  // code makes it from the site's data (plan_build.buildPlan — what preflight found), its title and summary the
  // code's, from the data alone
  step("fees");
  const built = buildPlan(c, kb);
  if (built.plan) {
    rec.code_plan = 1;
    return deliver(conclude(built.plan, [CODE_PLAN_LINE]));
  }
  rec.status_plan = "unmet";
  return deliver({ error: { type: "error", code: "conditions", message: planError("conditions"), problems: preflight(c, kb, now) } });
}

/** The trip as the code makes it from the site's data alone (plan_build.buildPlan, preflight's), finished for the page:
 *  its title and summary the code's, no notes, `line` the one thing the site says it did — or null when no such plan
 *  exists (preflight refuses those conditions). */
export function codePlan(c, kb, now, line) {
  const built = buildPlan(c, kb);
  if (!built.plan) return null;
  const check = verify(built.plan, c, kb);
  return check.flags.length ? null : finish(built.plan, check, c, now, [line]);
}

// ------------------------------------------------------------------ the handler
export function createPlanHandler(deps = {}) {
  const env = deps.env ?? process.env;
  // the site it plans for (public/chat/site.json): its name and address in the rules, the city in the titles, the hubs
  // the form offers, the origins that may ask
  const site = deps.site ?? loadSite();
  useSite(site);
  const now = deps.now ?? (() => new Date());
  const log = deps.log ?? ((rec) => console.log(JSON.stringify(rec)));
  const limiter = deps.limiter ?? createLimiter(PLAN_LIMITS.perMinute, 60000,
    { perDay: PLAN_LIMITS.perDay, allPerMinute: PLAN_LIMITS.allPerMinute, allPerDay: PLAN_LIMITS.allPerDay });
  // the conditions refused at the button: free of the plan's quota, counted in a looser one of their own (round-5
  // verifier: a refusal's reasons cost up to a second of the server's time)
  const refusals = deps.refusals ?? createLimiter(PLAN_LIMITS.refusedPerMinute, 60000,
    { perDay: PLAN_LIMITS.refusedPerDay, allPerMinute: PLAN_LIMITS.refusedAllPerMinute, allPerDay: PLAN_LIMITS.refusedAllPerDay });
  const knowledge = deps.knowledge ?? defaultKnowledge;
  let client = deps.client ?? null;

  async function getClient() {
    if (!client) {
      const { default: Anthropic } = await import("@anthropic-ai/sdk");
      // the key in ANTHROPIC_API_KEY is the only credential (chatbot/server.js apiKey: trimmed; no auth token, no profile)
      client = new Anthropic({ apiKey: apiKey(env), authToken: null, maxRetries: 1, timeout: PLAN_LIMITS.callMs });
    }
    return client;
  }

  return async function handle(request) {
    const t0 = Date.now();
    const done = (status, extra = {}) => log({ evt: "plan", status, ms: Date.now() - t0, ...extra });
    const fail = (status, code) => json(status, { code, message: planError(code) });
    if (request.method !== "POST") {
      done("method");
      return json(405, { code: "method_not_allowed" }, { Allow: "POST" });
    }
    if (!originAllowed(request, env, site)) {
      done("forbidden_origin");
      return json(403, { code: "forbidden_origin" });
    }
    if (!deps.client && !apiKey(env)) {
      done("not_configured");
      return fail(503, "not_configured");
    }
    const key = clientKey(clientIp(request));
    const refuse = (gate) => {
      done("rate_limited", { limit: gate.limit });
      const code = limitCode(gate.limit);
      return json(429, { code, message: planError(code) }, { "Retry-After": String(gate.retry) });
    };
    let gate = limiter.check(key, now().getTime());
    if (!gate.ok) return refuse(gate);
    let conditions;
    let edit;
    try {
      const body = await readBody(request, PLAN_LIMITS.bodyBytes);
      if (!body || typeof body !== "object") throw new HttpError(400, "bad_request");
      conditions = validConditions(body.conditions, now());
      edit = validEdit(body.plan, body.request, conditions);
    } catch (err) {
      const e = err instanceof HttpError ? err : new HttpError(400, "bad_request");
      done(e.code);
      return fail(e.status, e.code);
    }
    let kb;
    try {
      kb = await knowledge();
    } catch (err) {
      done("unavailable", { reason: err?.code || err?.name || "load" });
      return fail(503, "busy");
    }
    // conditions no plan can meet are said at the button, before the quota and any model call (operator 2026-10-18:
    // '문제가 있으면 아예 생성 버튼 누르는 단계에서 지적을 하고'): the reasons and the changes that make a plan. Not for
    // an edit: the plan on the page was made for these conditions, and a change that cannot be settled keeps it, said
    // so (makePlan 'edit_failed') — the button never refuses a change for the plan it changes (round-5 verifier: 7%
    // of the edits of sent plans were refused, with a date to change that an edit cannot change)
    if (!edit) {
      const pre = refusals.check(key, now().getTime());
      if (!pre.ok) return refuse(pre);
      let problems = [];
      try {
        problems = preflight(conditions, kb, now(), null, { today: seoulNow(now()).date, daysAhead: PLAN_LIMITS.daysAhead, valid: (x) => validConditions(x, now()) });
      } catch (err) {
        log({ evt: "plan", status: "preflight_error", reason: err?.name || "error" });   // the model path still runs
      }
      if (problems.length) {
        refusals.take(key, now().getTime());
        done("conditions", { problems: problems.length, fields: [...new Set(problems.map((p) => p.field))] });
        return json(422, { code: "conditions", message: planError("conditions"), problems });
      }
    }
    gate = limiter.take(key, now().getTime());
    if (!gate.ok) return refuse(gate);
    let api;
    try {
      api = await getClient();
    } catch (err) {
      done("unavailable", { reason: err?.code || err?.name || "load" });
      return fail(503, "busy");
    }
    const ac = new AbortController();
    let timedOut = false;
    // the reason rides on the signal: makePlan finishes the plan it has on a timeout, never for a reader who left
    const timer = setTimeout(() => {
      timedOut = true;
      ac.abort("timeout");
    }, PLAN_LIMITS.requestMs);
    const stop = () => ac.abort("client");
    request.signal?.addEventListener("abort", stop);
    const enc = new TextEncoder();
    let open = true;
    const body = new ReadableStream({
      async start(controller) {
        // after the time is up only the end may go out: an error, or the plan (`final`: makePlan's last event)
        let last = false;
        const send = (ev, final = false) => {
          if (!open || (ac.signal.aborted && ev.type !== "error" && !last && !final)) return;
          controller.enqueue(enc.encode(`data: ${JSON.stringify(ev)}\n\n`));
        };
        try {
          const rec = await makePlan({ client: api, kb, conditions, edit, send, signal: ac.signal, now: now() });
          done(rec.status, { rounds: rec.rounds, tools: rec.tools, submits: rec.submits, flags: rec.flags, text: rec.text,
            plan: rec.status_plan || undefined, salvaged: rec.salvaged || undefined, repaired: rec.repaired || undefined, settled: rec.settled || undefined,
            rebuilt: rec.rebuilt || undefined, code_plan: rec.code_plan || undefined, cut: rec.cut || undefined, in: rec.in, out: rec.out, cache_read: rec.cache_read,
            cache_write: rec.cache_write, stop: rec.stop, edit: !!edit, days: conditions.days });
        } catch (err) {
          const status = typeof err?.status === "number" ? err.status : 0;
          // the API's own errors (the SDK's: a status, or a connection that failed) apart from the code's
          const api = !!status || /^(?:APIConnection|APIUserAbort|APIConnectionTimeout|Anthropic|APIError)/u.test(err?.name || "") || err?.name === "AbortError";
          let code = "error";
          if (timedOut) code = "timeout";
          else if (ac.signal.aborted) code = "client_gone";
          else if (status === 429 || status === 529 || status >= 500 || (api && !status)) code = "busy";
          else if (!api) code = "exception";
          // the model did not answer in time or is busy for a while (timeout, 429, 529, 5xx, a connection that
          // failed): a new plan is still finished — the code's own, from the site's data (operator 2026-10-18: '무조건
          // 완성된 결과가 나오게'). Not for a fault that stays (400, 401, 403, 404: a key or a request the API refuses)
          // nor one of the code's own: those show, so they are fixed (round-5 verifier). An edit keeps the error: the
          // code cannot make the change asked for.
          const own = (code === "timeout" || code === "busy") && !edit ? codePlan(conditions, kb, now(), CODE_PLAN_BUSY) : null;
          last = true;
          if (own) send({ type: "plan", plan: own });
          else if (code !== "client_gone") send({ type: "error", code, message: planError(code) });
          done(code, { api_status: status || undefined, ...(code === "exception" ? { reason: err?.name || "error" } : {}), ...(own ? { plan: own.status, code_plan: 1 } : {}) });
        } finally {
          clearTimeout(timer);
          request.signal?.removeEventListener("abort", stop);
          if (open) {
            open = false;
            controller.close();
          }
        }
      },
      cancel() {
        open = false;
        ac.abort();
      },
    });
    return new Response(body, { status: 200, headers: SSE_HEADERS });
  };
}
