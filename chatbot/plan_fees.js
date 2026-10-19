// The course planner's admission fees, priced by the code from the site's data — review 2026-10-17 (AI 코스 만들기
// 집중 평가 CE01·CE02·CE03·CE10). The model used to hand over the fees: one plan added the same 박물관 통합권 twice
// (9,000 + 9,000), another left a paid museum out, a third priced three people of four and called the budget kept.
// Now every visit of the plan is priced here, for every person of the party, from what the site has:
//   - a place's own fee value read as a table at build time (docs.json f.fee, pipeline/fee_table.py): free, a
//     visitor's price per category, who enters free (ages, a weekday), the ages of a category when the value says;
//   - the combined tickets (docs.json tickets, data/<region>/tickets.json): the places each opens, its prices and rules.
// Each person at each visit is one of three: paid (a price the data gives for them), free (the data says so), or
// unknown (the data has no price for them — a child's age the table gives no category for, a place with no fee, a
// value that is not a table). A day's combined ticket is bought once per person and opens the places it covers that
// day; the code picks, for each day, the way to pay that leaves the fewest people unknown and then costs least. The
// total is a total only when nobody is unknown; the budget is kept only then — otherwise 'open' with the known part.
// Meals, cafes and stays are not admissions: the page says so (식비·숙박비는 사이트에 확인된 값이 없음).

import { bornCategory, bornWords } from "./knowledge.js";

const won = (n) => `${n.toLocaleString("en-US")}원`;
const SENIOR_AGE = 65;   // the form's '65세 이상' counter: a rule 'N세 이상' applies when N ≤ 65

/** The party as groups of people priced alike: [{key, label, kind: 'adult'|'senior'|'kid', age?, count}]. */
export function partyGroups({ adults = 0, seniors = 0, kids = [] } = {}) {
  const out = [];
  const plain = Math.max(0, adults - seniors);
  if (plain) out.push({ key: "adult", label: "어른", kind: "adult", count: plain });
  if (seniors) out.push({ key: "senior", label: "65세 이상 어른", kind: "senior", count: seniors });
  const byAge = new Map();
  for (const a of kids) byAge.set(a, (byAge.get(a) || 0) + 1);
  for (const [age, count] of [...byAge].sort((x, y) => y[0] - x[0])) {
    out.push({ key: `kid${age}`, label: `아이 ${age}살`, kind: "kid", age, count });
  }
  return out;
}

const monthIn = (text, month) => {
  const m = /(1[0-2]|[1-9])\s*~\s*(1[0-2]|[1-9])\s*월/u.exec(text || "");
  if (!m) return null;
  const x = +m[1], y = +m[2];
  return x <= y ? month >= x && month <= y : month >= x || month <= y;
};

/** One group at one place, by the place's own table: {status, won?, basis} — status 'paid' | 'free' | 'unknown'. */
function placePrice(fee, g, date) {
  if (!fee || (!fee.free && !fee.tab)) {
    return { status: "unknown", basis: fee && fee.t ? `요금 값이 표가 아님('${fee.t.slice(0, 40)}')` : "사이트에 요금 정보 없음" };
  }
  if (fee.free) return { status: "free", basis: `무료${fee.note ? ` (${fee.note})` : ""}` };
  const day = new Date(`${date}T12:00:00Z`);
  const wd = day.getUTCDay(), month = day.getUTCMonth() + 1;
  for (const r of fee.fr || []) {
    if (r.wd === undefined || r.wd !== wd) continue;
    // '2026년 4~12월 매주 수요일 무료 관람' written by another source: the weekday rule holds in those months only
    const months = [r.w, ...(fee.alt || []).map((a) => a.t)].map((t) => monthIn(t, month)).find((v) => v !== null);
    if (months !== false) return { status: "free", basis: `${r.w}${months === null ? "" : ` (${month}월)`}` };
  }
  if (g.kind === "kid") {
    const freeAge = (fee.fr || []).find((r) => r.max !== undefined && g.age <= r.max);
    if (freeAge) return { status: "free", basis: `무료 '${freeAge.w}'` };
    const cat = Object.entries(fee.ag || {}).find(([, [a, b]]) => g.age >= a && g.age <= b);
    if (cat && fee.tab[cat[0]] !== undefined) return { status: "paid", won: fee.tab[cat[0]], basis: `요금표 '${cat[0]}(${cat[1][0]}~${cat[1][1]}세)'` };
    return { status: "unknown", basis: `${g.age}살이 어느 요금 구분인지 요금표에 나이 기준이 없음` };
  }
  if (g.kind === "senior") {
    const freeOld = (fee.fr || []).find((r) => r.min !== undefined && r.min <= SENIOR_AGE);
    if (freeOld) return { status: "free", basis: `무료 '${freeOld.w}'` };
    return { status: "unknown", basis: "65세 이상 요금(경로 할인·무료)이 요금표에 없음" };
  }
  return { status: "paid", won: fee.tab["성인"], basis: `요금표 '성인'${fee.tl ? ` (${fee.tl})` : ""}` };
}

/** One group with a combined ticket on `date`: the ticket's own prices (개인, 그 도시 시민 아님) and its own rules only. A
 *  child's category comes from the table's ages and its birth years (that year's table only); when they do not give
 *  one category — two sources apart, or a birthday deciding — the child is unknown, with both readings. */
function ticketPrice(t, g, date) {
  const rules = t.rules || [];
  const table = (t.prices || {})["개인"] || {};
  if (g.kind === "kid") {
    const freeAge = rules.find((r) => r.kind === "free" && r.age_max !== undefined && g.age <= r.age_max);
    if (freeAge) return { status: "free", basis: `무료 '${freeAge.who}' (${freeAge.src})` };
    const year = +String(date || "").slice(0, 4);
    const reads = rules.filter((r) => r.kind === "age" && g.age >= r.from && g.age <= r.to)
      .map((r) => ({ cat: r.category, what: `'${r.text}' (${r.src})` }));
    const born = bornCategory(rules, g.age, year);
    if (born && born.rule) reads.push({ cat: born.rule.category, what: `'${born.rule.category} ${born.rule.text}' (${born.rule.src})` });
    if (born && born.split) return { status: "unknown", basis: bornWords(born, g.age, year) };
    const cats = new Set(reads.map((x) => x.cat));
    if (cats.size > 1) return { status: "unknown", basis: `요금 구분이 출처마다 다름: ${reads.map((x) => x.what).join(" / ")} — 방문 전 확인` };
    if (cats.size === 1 && table[reads[0].cat]) {
      return { status: "paid", won: table[reads[0].cat][0], basis: `요금표 ${reads.map((x) => x.what).join(" · ")}` };
    }
    if (born && (born.stale || born.none)) return { status: "unknown", basis: bornWords(born, g.age, year) };
    return { status: "unknown", basis: `${g.age}살이 어느 요금 구분인지 이 통합권 요금표에 나이 기준이 없음` };
  }
  if (g.kind === "senior") {
    const freeOld = rules.find((r) => r.kind === "free" && r.age_min !== undefined && r.age_min <= SENIOR_AGE);
    if (freeOld) return { status: "free", basis: `무료 '${freeOld.who}' (${freeOld.src})` };
    return { status: "unknown", basis: "65세 이상 요금(경로 할인·무료)이 이 통합권 요금표에 없음" };
  }
  return table["성인"] ? { status: "paid", won: table["성인"][0], basis: "요금표 '성인'" }
    : { status: "unknown", basis: "이 통합권 요금표에 성인 요금이 없음" };
}

/** A day priced one way: tickets (ids, may be empty) and every other visit one by one. */
function priceDay(day, groups, kb, use) {
  const lines = [];
  const per = [];   // per visit: {i, path, name, how: 'own' | ticket id | 'again', states: {status: count}}
  const covered = new Map();   // path → ticket id
  for (const id of use) {
    const t = kb.tickets.find((x) => x.id === id);
    const paths = new Set(t.places.map((p) => p.path));
    const visits = day.stops.filter((s) => paths.has(s.page));
    if (!visits.length) return null;
    for (const s of visits) if (!covered.has(s.page)) covered.set(s.page, id);
    const names = [...new Set(visits.map((s) => s.name))];
    for (const g of groups) {
      const p = ticketPrice(t, g, day.date);
      lines.push({ what: `${t.name} — ${names.join("·")}`, ticket: t.id, who: g.label, count: g.count, ...p,
        sub: p.status === "paid" ? p.won * g.count : 0, src: t.src });
    }
  }
  const seen = new Set();
  day.stops.forEach((s, i) => {
    if (s.role !== "visit") return;
    if (seen.has(s.page)) {
      per.push({ i, path: s.page, name: s.name, how: "again" });
      return;
    }
    seen.add(s.page);
    if (covered.has(s.page)) {
      per.push({ i, path: s.page, name: s.name, how: covered.get(s.page) });
      return;
    }
    const doc = kb.docs[s.page] || {};
    const fee = (doc.f || {}).fee;
    const states = {};
    for (const g of groups) {
      const p = placePrice(fee, g, day.date);
      states[p.status] = (states[p.status] || 0) + g.count;
      lines.push({ what: s.name, path: s.page, who: g.label, count: g.count, ...p, sub: p.status === "paid" ? p.won * g.count : 0,
        src: fee && fee.p ? fee.p : "" });
    }
    per.push({ i, path: s.page, name: s.name, how: "own", states, tickets: kb.tickets.filter((t) => t.places.some((p) => p.path === s.page)).map((t) => t.name) });
  });
  const unknown = lines.filter((l) => l.status === "unknown").reduce((a, l) => a + l.count, 0);
  const known = lines.reduce((a, l) => a + l.sub, 0);
  return { lines, per, unknown, known, use };
}

/** The plan's admission fees: {days: [{date, lines, per}], open: [text], conds: [text], total, known, state, limit,
 *  verdict, text}. days = [{date, stops: [{page (a doc key), name, role}]}]; party = {adults, seniors, kids};
 *  limit = the reader's budget (null: none). */
export function planFees(days, party, kb, limit = null) {
  const groups = partyGroups(party);
  const out = { days: [], open: [], conds: [], total: null, known: 0, state: "none", limit, verdict: "none" };
  let visits = 0;
  let unknown = 0;
  let paid = 0;
  for (const day of days) {
    visits += day.stops.filter((s) => s.role === "visit").length;
    const options = [[]];
    for (const t of kb.tickets) {
      if (day.stops.some((s) => s.role === "visit" && t.places.some((p) => p.path === s.page))) options.push([t.id]);
    }
    // the way to pay is chosen as for one adult (every table has an adult's price, a child's often has no ages): the
    // fewest visits with no adult price, then the cheapest for an adult, then the fewest people unknown — so a ticket
    // whose table happens to name children's ages is never picked over a cheaper one only for that
    const one = [{ key: "adult", label: "어른", kind: "adult", count: 1 }];
    const priced = options.map((use) => ({ full: priceDay(day, groups, kb, use), adult: priceDay(day, one, kb, use) }))
      .filter((x) => x.full);
    priced.sort((a, b) => a.adult.unknown - b.adult.unknown || a.adult.known - b.adult.known || a.full.unknown - b.full.unknown
      || a.full.use.length - b.full.use.length);
    const best = priced[0].full;
    out.days.push({ date: day.date, lines: best.lines, per: best.per });
    out.known += best.known;
    unknown += best.unknown;
    paid += best.lines.filter((l) => l.status === "paid").length;
    for (const l of best.lines.filter((x) => x.status === "unknown")) out.open.push(`${l.what}: ${l.who} ${l.count}명 — ${l.basis}`);
  }
  const rules = new Set();
  for (const d of out.days) {
    for (const p of d.per.filter((x) => x.how === "own")) {
      const fee = ((kb.docs[p.path] || {}).f || {}).fee || {};
      for (const r of (fee.fr || []).filter((x) => /장애인|유공자/u.test(x.w))) rules.add(`${p.name}: ${r.w} 무료(증빙 필요) — 해당하면 줄어듦`);
      for (const a of fee.alt || []) rules.add(`${p.name}: 다른 출처의 요금 값 '${a.t.slice(0, 60)}'(${a.p}) — 방문 전 확인`);
    }
    for (const id of new Set(d.per.map((x) => x.how).filter((h) => h !== "own" && h !== "again"))) {
      const t = kb.tickets.find((x) => x.id === id);
      for (const r of (t.rules || []).filter((x) => x.kind === "free" && x.age_max === undefined && x.age_min === undefined)) {
        rules.add(`${t.name}: ${r.who} 무료(증빙 필요) — 해당하면 줄어듦`);
      }
      for (const r of (t.rules || []).filter((x) => x.kind === "note")) rules.add(`${t.name}: ${r.text}`);
    }
  }
  out.conds = [...rules];
  if (!visits) {
    out.state = "none";
  } else if (unknown) {
    out.state = paid || out.known ? "partial" : "unknown";
  } else {
    out.total = out.known;
    out.state = out.known ? "known" : "free";
  }
  if (limit !== null && limit !== undefined) {
    if (out.known > limit) out.verdict = "over";
    else if (out.total !== null) out.verdict = "within";
    else if (out.state === "none") out.verdict = "within";
    else out.verdict = "open";
  }
  const T = [];
  for (const [i, d] of out.days.entries()) {
    for (const l of d.lines) {
      T.push(`${days.length > 1 ? `${i + 1}일차 ` : ""}${l.what} · ${l.who} ${l.count}명: ${l.status === "paid" ? `${won(l.won)} × ${l.count} = ${won(l.sub)}`
        : l.status === "free" ? "0원" : "확인 필요"} (${l.basis})`);
    }
  }
  T.push(out.state === "none" ? "입장료를 내는 방문지가 없다(식사·카페·숙소는 입장료 계산에 넣지 않는다)"
    : out.total !== null ? `입장료 합계 ${won(out.total)}` : `확인된 입장료 ${won(out.known)} + 확인 필요 ${out.open.length}건(합계 확정 안 됨)`);
  out.text = T.join("\n");
  return out;
}
