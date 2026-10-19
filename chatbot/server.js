// /api/chat/ — the site assistant's request handler (owner decision 2026-10-13, CLAUDE.md 3절 11항). createHandler(deps)
// takes everything it uses from outside — {client, makeClient, knowledge, env, now, log, limiter, site} — so the tests
// run it with a fake client that replays scripted stream events; the deployed function (api/chat.js) passes nothing
// and gets the real Anthropic client (made on the first question, with the key from ANTHROPIC_API_KEY only), the
// knowledge bundled from public/chat/ and the site it answers for (public/chat/site.json, chatbot/site.js: its public
// address, name and the city's names — nothing city-specific is written in this file).
//
// Key-ready: without ANTHROPIC_API_KEY every question is answered 503 {code: 'not_configured'} at once and
// GET /api/chat/ says the same ({ready: false}); the page (templates/assets/chat.js) asks GET first and shows a calm
// 'AI 도우미 준비 중' state with the site search instead of a question box. With the key set (Vercel: Settings →
// Environment Variables, then a redeploy) GET answers 200 {ready: true} and questions are answered — nothing else
// changes. The key is never logged, never put in a response, and ANTHROPIC_AUTH_TOKEN or a profile on disk is never
// used in its place (makeClient).
//
// POST: one question = one request: the browser sends the conversation (it keeps it in sessionStorage; nothing is
// stored here). The model answers from the cached catalog and two tools in a manual streaming loop (the Claude API
// skill's "Streaming Manual Loop"): at most LIMITS.toolRounds rounds of tool calls, then one answer without tools, all
// calls of the question sharing one output budget (LIMITS.outputTokens). An answer cut at max_tokens is continued once
// in the same request while that budget lasts; one still cut ends with done.cut, and the browser can then ask to go on
// — {continue: true} with the cut answer as the last assistant message — and the stream carries only the rest of the
// answer (cleanRequest, trimOverlap).
//
// SSE events: {type:'status', text} while a tool runs · {type:'text', delta} · {type:'done', links, fix, cut?} ·
// {type:'error', code, message}. Logs: one JSON line per request with status, tool names and token numbers — never
// the user's text, the answer, the address or the key.
//
// What a question has to pass, cheapest first (README '사이트 도우미'): POST · an Origin from the allow-list and no
// 'Sec-Fetch-Site: cross-site' (this only stops other websites' pages: a script sets any header it likes) · a key is
// configured · not already at a rate limit (looked at, nothing counted) · a body of at most 64KB that parses ·
// plain-text user/assistant messages · then the question is counted (per client per minute and per day, the whole
// instance per minute and per day). Only a question that passed every check counts, so a body the checks refuse
// uses up no one's share. The bounds across instances are the owner's two settings: a Vercel Firewall rate-limit rule
// and the Anthropic Console spend limit.
import { isIP } from "node:net";

import { QUERY_CHARS, defaultKnowledge } from "./knowledge.js";
import {
  EFFORT, LANGS, MODEL, NO_THINKING_NOTE, TOOLS, TOOLS_PLAIN, buildSystem, continueText, dataBlock, errorText, questionLang,
  neutralise, statusText,
} from "./prompt.js";
import { loadSite } from "./site.js";

export const LIMITS = {
  bodyBytes: 64 * 1024,
  messages: 13,          // the new question and the 12 messages before it
  userChars: 800,
  assistantChars: 2000,  // an earlier answer is cut to this length (the browser sends at most 2,000: chat.js ANSWER_CHARS)
  partialChars: 6000,    // the cut answer a continue request carries (its start and its end are kept)
  pageChars: 300,
  // questions counted in this function instance's memory (no ledger: a new instance starts at zero)
  perMinute: 8,          // per client (an IP address; IPv6: its /64) per minute
  perDay: 60,            // per client per 24 hours
  allPerMinute: 30,      // all clients together per minute
  allPerDay: 1000,       // all clients together per 24 hours
  toolRounds: 4,
  // output tokens (thinking counts: Haiku 5.5 thinks by default, and its thinking is part of max_tokens). One call may
  // use up to maxTokens; all calls of one question share outputTokens, and the call that must answer always gets at
  // least lastCallTokens (6,000 + 1,500 = 7,500, the bound the old 5 calls × 1,500 had — no call goes past it). A call
  // that only thought (no text, no tool call) is asked once more without thinking, with maxTokens: one question writes
  // at most 11,500 tokens. An answer cut at max_tokens while the 7,500 still has moreTokens left is continued once in
  // the same request (the rest of the 7,500, at most maxTokens), when moreMs of the request's time is left.
  maxTokens: 4000,
  outputTokens: 6000,
  lastCallTokens: 1500,
  answerReserve: 2500,   // below this many tokens left, the next call answers (no more tools)
  moreTokens: 400,
  moreMs: 30000,
  toolChars: 20000,      // all tool results of one question together
  requestMs: 90000,      // the whole answer (vercel.json maxDuration is 120)
  callMs: 45000,         // one API call (4,000 output tokens take about 27 s at the measured ~150 tokens/s)
  jsonRetries: 2,
};

/** The key: ANTHROPIC_API_KEY only (Vercel Settings → Environment Variables; a local test: the environment), trimmed
 *  — a value pasted with a trailing newline still works; '' when it is unset or blank. Never logged, never put in a
 *  response: the SDK sends it to the Anthropic API and nowhere else. */
export function apiKey(env = {}) {
  return String(env?.ANTHROPIC_API_KEY ?? "").trim();
}

/** The real client for one key. authToken null: with apiKey set the SDK reads no ANTHROPIC_AUTH_TOKEN and no profile
 *  on disk, so the key in ANTHROPIC_API_KEY is the only credential this function ever uses. */
export async function makeClient(key) {
  const { default: Anthropic } = await import("@anthropic-ai/sdk");
  return new Anthropic({ apiKey: key, authToken: null, maxRetries: 1, timeout: LIMITS.callMs });
}

const SSE_HEADERS = {
  "Content-Type": "text/event-stream; charset=utf-8",
  "Cache-Control": "no-cache, no-transform",
  "X-Accel-Buffering": "no",
  "X-Content-Type-Options": "nosniff",
  "X-Robots-Tag": "noindex",
};

function json(status, body, headers = {}) {
  return new Response(JSON.stringify(body), {
    status,
    headers: { "Content-Type": "application/json; charset=utf-8", "Cache-Control": "no-store",
      "X-Robots-Tag": "noindex", ...headers },
  });
}

// ------------------------------------------------------------------ request checks
const LOCAL = new Set(["localhost", "127.0.0.1", "[::1]"]);
const DAY = 24 * 60 * 60 * 1000;
/** The origins a page may ask from — configuration only, never the request's own Host or X-Forwarded-Host (a proxy
 *  in front of this function sets those): the public site (site.url) and the further origins the owner lists
 *  (site.origins — a previous address whose pages redirect but whose /api/chat/ stays, the project's Vercel production
 *  alias '<project>-<scope>.vercel.app', which no system variable carries), and this deployment's own addresses from
 *  Vercel's system environment variables (host names without https://): VERCEL_URL (this deployment),
 *  VERCEL_BRANCH_URL (its Git branch address) and VERCEL_PROJECT_PRODUCTION_URL (the production domain; set in
 *  previews too). */
export function allowedOrigins(env = {}, site = {}) {
  const out = new Set([site.url, ...(site.origins || [])].filter(Boolean));
  for (const name of ["VERCEL_URL", "VERCEL_BRANCH_URL", "VERCEL_PROJECT_PRODUCTION_URL"]) {
    const host = String(env[name] || "").trim().toLowerCase();
    if (/^[a-z0-9-]+(\.[a-z0-9-]+)+$/.test(host)) out.add(`https://${host}`);
  }
  return out;
}

/** A browser asks from an allowed origin: not a cross-site request by its own Sec-Fetch-Site, an Origin on the
 *  allow-list, or — only when this is not production (VERCEL_ENV) — a local test page: localhost, 127.0.0.1, [::1],
 *  or a LAN address (vercel dev opened from a phone on the same Wi-Fi), that is an Origin whose host is an IP
 *  address and the very host the request was sent to. Never a host name the request names for itself: a
 *  DNS-rebinding page (its name pointed at the developer's machine) sends its own name as both Origin and Host. */
export function originAllowed(request, env = {}, site = {}) {
  if ((request.headers.get("sec-fetch-site") || "").toLowerCase() === "cross-site") return false;
  const origin = request.headers.get("origin");
  if (!origin) return false;
  let o;
  try {
    o = new URL(origin);
  } catch {
    return false;
  }
  if (allowedOrigins(env, site).has(o.origin)) return true;
  if (env.VERCEL_ENV === "production" || !/^https?:$/.test(o.protocol)) return false;
  if (LOCAL.has(o.hostname)) return true;
  return isIP(o.hostname.replace(/^\[(.*)\]$/, "$1")) !== 0 && o.host === requestHost(request);
}

/** The host the request was sent to (Host, else the URL's host), lower case; '' when there is none. */
function requestHost(request) {
  try {
    return (request.headers.get("host") || new URL(request.url).host).trim().toLowerCase();
  } catch {
    return "";
  }
}

/** The client's address as the platform gives it (Vercel docs, Request headers): Vercel overwrites x-forwarded-for
 *  "to prevent IP spoofing", and x-real-ip — what @vercel/functions ipAddress() reads — and x-vercel-forwarded-for
 *  are "identical to" it. Elsewhere (a local test) there is no platform header to trust. */
export function clientIp(request) {
  const h = request.headers;
  for (const v of [h.get("x-real-ip"), h.get("x-vercel-forwarded-for"), (h.get("x-forwarded-for") || "").split(",")[0]]) {
    const ip = String(v || "").trim();
    if (ip) return ip;
  }
  return "unknown";
}

/** The key the rate limits count by: an IPv4 address as it is, an IPv6 address by its /64 (one home or phone gets a
 *  whole /64, so single IPv6 addresses would let one client rotate past the limits), anything else 'unknown'. */
export function clientKey(raw) {
  const ip = String(raw || "").trim().replace(/%.*$/, "");
  const v = isIP(ip);
  if (v === 4) return ip;
  if (v !== 6) return "unknown";
  const mapped = /^::ffff:(\d{1,3}(?:\.\d{1,3}){3})$/i.exec(ip);
  if (mapped) return mapped[1];
  const groups = (s) => (s ? s.split(":") : []).flatMap((g) => (g.includes(".") ? ["0", "0"] : [g]));
  const [head, tail] = ip.toLowerCase().split("::");
  const h = groups(head);
  const t = tail === undefined ? [] : groups(tail);
  const all = tail === undefined ? h : [...h, ...Array(Math.max(0, 8 - h.length - t.length)).fill("0"), ...t];
  return `${all.slice(0, 4).map((g) => g.replace(/^0+(?=.)/, "")).join(":")}::/64`;
}

/** The rate limits, sliding windows in this instance's memory only (no ledger: a new instance starts at zero, and
 *  Vercel may run several): per client per minute and per 24 hours, and all clients together per minute and per 24
 *  hours. check(key, t) only looks — the handler asks it before reading a body, so a client already at a limit is
 *  refused at once and nothing is counted; take(key, t) counts a question, and only when every window has room, so
 *  a refused request uses nothing up. The handler takes only a question that passed every check of its body.
 *  Both → {ok: true} or {ok: false, limit: 'ip_minute'|'ip_day'|'all_minute'|'all_day', retry: seconds}. */
export function createLimiter(perMinute = LIMITS.perMinute, windowMs = 60000, caps = {}) {
  const perDay = caps.perDay ?? LIMITS.perDay;
  const allPerMinute = caps.allPerMinute ?? LIMITS.allPerMinute;
  const allPerDay = caps.allPerDay ?? LIMITS.allPerDay;
  const keep = Math.max(windowMs, DAY);
  const hits = new Map();   // client key → times of its counted questions, oldest first
  let all = [];             // times of every counted question, oldest first
  const full = (times, t, max, ms, limit) => {
    const inside = times.filter((x) => t - x < ms);
    if (inside.length < max) return null;
    const free = max > 0 ? inside[inside.length - max] + ms - t : ms;   // when the oldest counted one leaves the window
    return { ok: false, limit, retry: Math.max(1, Math.ceil(free / 1000)) };
  };
  // the client's counted questions still inside the longest window, and the first limit that has no room (or null)
  const look = (key, t) => {
    all = all.filter((x) => t - x < keep);
    const mine = (hits.get(key) || []).filter((x) => t - x < keep);
    if (mine.length) hits.set(key, mine);
    else hits.delete(key);
    const no = full(mine, t, perMinute, windowMs, "ip_minute") || full(mine, t, perDay, DAY, "ip_day")
      || full(all, t, allPerMinute, 60000, "all_minute") || full(all, t, allPerDay, DAY, "all_day");
    return { mine, no };
  };
  return {
    check(key, t = Date.now()) {
      return look(key, t).no || { ok: true };
    },
    take(key, t = Date.now()) {
      const { mine, no } = look(key, t);
      if (no) return no;
      mine.push(t);
      all.push(t);
      hits.set(key, mine);
      if (hits.size > allPerDay) {   // more keys than counted questions in a day: some have aged out
        for (const [k, v] of hits) if (!v.length || t - v[v.length - 1] >= keep) hits.delete(k);
      }
      return { ok: true };
    },
  };
}

/** What a refused question tells the browser (chat.js shows a text per code): the client's minute 'rate_limited'
 *  ('ask again in a minute' — the Vercel Firewall rule's 429 reads the same), the client's 24 hours 'daily_limit',
 *  and the whole instance at its limit 'busy' — the visitor did nothing wrong ('cannot answer right now'). */
export function limitCode(limit) {
  if (limit === "ip_minute") return "rate_limited";
  if (limit === "ip_day") return "daily_limit";
  return "busy";
}

class HttpError extends Error {
  constructor(status, code) {
    super(code);
    this.status = status;
    this.code = code;
  }
}

async function readBody(request, max) {
  const declared = Number(request.headers.get("content-length") || 0);
  if (declared > max) throw new HttpError(413, "too_large");
  if (!request.body) throw new HttpError(400, "bad_request");
  const reader = request.body.getReader();
  const chunks = [];
  let size = 0;
  for (;;) {
    const { done, value } = await reader.read();
    if (done) break;
    size += value.byteLength;
    if (size > max) {
      await reader.cancel();
      throw new HttpError(413, "too_large");
    }
    chunks.push(value);
  }
  const bytes = new Uint8Array(size);
  let at = 0;
  for (const c of chunks) {
    bytes.set(c, at);
    at += c.byteLength;
  }
  try {
    return JSON.parse(new TextDecoder().decode(bytes));
  } catch {
    throw new HttpError(400, "bad_request");
  }
}

export function normLang(v) {
  const s = String(v || "").trim().toLowerCase();
  const alias = { "zh": "zh-Hans", "zh-cn": "zh-Hans", "zh-sg": "zh-Hans", "zh-tw": "zh-Hant", "zh-hk": "zh-Hant" };
  return LANGS.find((l) => l.toLowerCase() === s) || alias[s] || LANGS.find((l) => l === s.split("-")[0]) || "ko";
}

// a link into this site as the browser checked it (https://<site>/places/%EA…/): read back as the page path
// (/places/장소/) — the path the catalog gives, a third of the length
const MD_LINK = /\[[^\]\n]{1,200}\]\(\s*<?[^)\s>]+>?\s*\)/g;

function readablePaths(text, siteUrl) {
  if (!siteUrl) return text;
  const rx = new RegExp(`${siteUrl.replace(/[.*+?^${}()|[\]\\/]/g, "\\$&")}(/[^\\s)\\]>"'<]*)`, "g");
  return text.replace(rx, (all, p) => {
    try {
      return decodeURI(p);
    } catch {
      return p;
    }
  });
}

/** An earlier answer as the model reads it: site links as paths, cut to LIMITS.assistantChars — and when the cut drops
 *  links, the links of the dropped part follow the cut (within the same length), so the pages the answer used stay
 *  readable with get_pages. */
export function priorAnswer(text, siteUrl = "") {
  const s = readablePaths(text, siteUrl);
  const chars = [...s];
  const cap = LIMITS.assistantChars;
  if (chars.length <= cap) return s;
  const links = [];
  for (const [md] of chars.slice(cap - 400).join("").matchAll(MD_LINK)) {
    if (!links.includes(md) && links.length < 6 && links.join("\n").length + md.length < 600) links.push(md);
  }
  const tail = links.length ? `\n${links.join("\n")}` : "";
  return `${chars.slice(0, cap - [...tail].length).join("")} …${tail}`;
}

/** The cut answer of a continue request: whole up to LIMITS.partialChars, else its start and its end (where it
 *  stopped — what the continuation must follow). */
function partialAnswer(text) {
  const chars = [...text];
  const cap = LIMITS.partialChars;
  if (chars.length <= cap) return text;
  return `${chars.slice(0, 1200).join("")}\n…\n${chars.slice(-(cap - 1200)).join("")}`;
}

/** {messages, lang, page, cont} from the browser, checked: plain-text messages only (no tool, system or other blocks —
 *  an earlier answer is the browser's copy, plain text), user/assistant alternating from a user message to the new
 *  question (≤ userChars), the last LIMITS.messages kept, earlier answers cut (their links kept), the data delimiter
 *  neutralised. Two questions in a row: the earlier one got no answer (the reader stopped it, or it failed) and the
 *  reader moved on — only the newer one is asked. With continue: true the conversation ends with the cut answer to the
 *  last question, and the server adds the request to go on (prompt.js continueText) as the last, user, message;
 *  cont.partial is that cut answer. `language` is the language the question is written in (prompt.js questionLang),
 *  the one every request to go on is written in. */
export function cleanRequest(body, site = {}) {
  if (!body || typeof body !== "object" || !Array.isArray(body.messages)) throw new HttpError(400, "bad_request");
  const cont = body.continue === true;
  const merged = [];
  for (const m of body.messages.slice(-60)) {
    if (!m || (m.role !== "user" && m.role !== "assistant") || typeof m.content !== "string") {
      throw new HttpError(400, "bad_request");
    }
    const content = m.content.replace(/\r\n?/g, "\n").trim();
    if (!content) continue;
    const last = merged[merged.length - 1];
    if (last && last.role === m.role) {
      if (m.role === "user") last.content = content;   // the unanswered earlier question is dropped
      else last.content += `\n\n${content}`;
    } else merged.push({ role: m.role, content });
  }
  while (merged.length && merged[0].role !== "user") merged.shift();
  if (!merged.length || merged[merged.length - 1].role !== (cont ? "assistant" : "user")) {
    throw new HttpError(400, "bad_request");
  }
  const question = merged[merged.length - (cont ? 2 : 1)];
  if (!question || question.role !== "user") throw new HttpError(400, "bad_request");
  if ([...question.content].length > LIMITS.userChars) throw new HttpError(413, "too_long");
  let messages = merged.slice(-(LIMITS.messages + (cont ? 1 : 0)));
  while (messages[0].role !== "user") messages = messages.slice(1);
  messages = messages.map((m, i) => {
    let content;
    if (m.role === "user") {
      const chars = [...m.content];
      content = chars.length > LIMITS.userChars ? `${chars.slice(0, LIMITS.userChars).join("")} …` : m.content;
    } else {
      content = cont && i === messages.length - 1 ? partialAnswer(m.content) : priorAnswer(m.content, site.url);
    }
    return { role: m.role, content: neutralise(content) };
  });
  const lang = normLang(typeof body.lang === "string" ? body.lang : "");
  const language = questionLang(question.content, lang);
  let partial = "";
  if (cont) {
    partial = messages[messages.length - 1].content;
    const chars = [...partial];
    messages.push({ role: "user", content: neutralise(continueText(chars.slice(-160).join(""), language, site)) });
  }
  let page = typeof body.page === "string" ? body.page.trim() : "";
  page = page.startsWith("/") && page.length <= LIMITS.pageChars ? page.split(/[?#]/)[0] : "";
  return { messages, lang, page, language, cont: cont ? { partial } : null };
}

/** A continuation as the reader should see it after the cut answer: when it begins by writing again the end of the cut
 *  answer (its unfinished last line, or the last words), that repeat is dropped; a word cut in two is joined. When the
 *  cut fell right after a sentence and the rest starts a new one, they are kept apart: a list item, table row or heading
 *  on its own line, a sentence after a space (measured: '…노선이 없습니다.' + '- ○○박물관은 …'). */
export function trimOverlap(prev, next) {
  const tail = String(prev).slice(-400);
  let rest = next;
  let k = Math.min(tail.length, next.length);
  for (; k >= 6; k -= 1) {
    if (tail.endsWith(next.slice(0, k))) break;
  }
  if (k >= 6) rest = next.slice(k);
  else {
    const frag = /(?:^|[\s(|·,])([^\s(|·,]{1,12})$/.exec(tail);   // a word the cut split ('…무' + '무료입니다')
    if (frag && next.startsWith(frag[1]) && next.length > frag[1].length) rest = next.slice(frag[1].length);
  }
  if (rest && /[.!?。]$/u.test(tail) && !/^\s/u.test(rest)) {
    // not a sentence end: a cut inside an address ('(https://www.example.go.' + 'kr/…', '…view/12345?' + 's_idx=2)')
    // or a decimal number ('약 12.' + '5km')
    if (/(?:https?:\/\/|\]\()[^\s)]*$/u.test(tail)) return rest;
    if (/^(?:[-*•]\s|\d+\.\s|#{1,6}\s|\|)/u.test(rest)) return `\n${rest}`;
    if (/\d\.$/u.test(tail) && /^\d/u.test(rest)) return rest;
    return ` ${rest}`;
  }
  return rest;
}

// ------------------------------------------------------------------ the answer loop
function validInput(name, input) {
  if (!input || typeof input !== "object" || Array.isArray(input)) return null;
  if (name === "search_site") {
    const q = typeof input.query === "string" ? input.query.trim() : "";
    if (!q || q.length > QUERY_CHARS) return null;
    const kind = input.kind === undefined ? "any" : input.kind;
    if (!["any", "place", "guide", "course", "event", "abroad", "video", "page"].includes(kind)) return null;
    if (input.lang !== undefined && !LANGS.includes(input.lang)) return null;
    return { query: q, kind, lang: input.lang };
  }
  if (name === "get_pages") {
    const ids = input.ids;
    if (!Array.isArray(ids) || !ids.length || ids.length > 20) return null;
    if (!ids.every((x) => typeof x === "string" && x.trim() && x.length <= 300)) return null;
    return { ids: ids.map((x) => x.trim()) };
  }
  return null;
}

function apiStatus(err) {
  return typeof err?.status === "number" ? err.status : 0;
}

/** Runs one question to the end, writing SSE events through send(). Returns the log record's numbers. */
export async function answer({ client, kb, messages, lang, page, send, signal, now, cont = null, language = "", site = {} }) {
  // the language a request to go on is written in: the question's (cleanRequest), else the interface's
  const qlang = language || lang;
  const t0 = Date.now();
  const system = buildSystem(kb.catalog, { now, page: kb.describePage(page), lang, site });
  const convo = messages.map((m) => ({ role: m.role, content: m.content }));
  const rec = { rounds: 0, tools: [], in: 0, out: 0, cache_read: 0, cache_write: 0, stop: "", fallback: false,
    cont: !!cont, rescue: false, more: false };
  let tools = TOOLS;
  let toolChars = LIMITS.toolChars;
  let outUsed = 0;   // output tokens of this question's calls so far (thinking included)
  let text = "";     // what this request has streamed
  let jsonRetries = 0;
  const before = cont ? cont.partial : "";   // a continue request: the cut answer the reader already has
  // a continuation's first characters — a continue request's, or the rest this request asks for after a call of its
  // own stopped at max_tokens — wait until a repeat of the end of what the reader has can be seen and dropped. A
  // continuation may begin with a tool call: the waiting goes on until its text comes (or the answer ends).
  let pending = cont ? "" : null;
  const emit = (t) => {
    if (!t) return;
    text += t;
    send({ type: "text", delta: t });
  };
  const flush = (end = false) => {
    if (pending === null || (!pending && !end)) return;
    const t = trimOverlap(before + text, pending);
    pending = null;
    emit(t);
  };
  let rescue = false;   // this call follows one that only thought: no thinking, a full call's output
  let more = false;     // this call goes on with the answer the call before it left cut at max_tokens
  for (let call = 0; call <= LIMITS.toolRounds; call += 1) {
    // every call of the question together writes at most outputTokens + lastCallTokens (one rescue call adds maxTokens)
    const cap = LIMITS.outputTokens + LIMITS.lastCallTokens + (rec.rescue ? LIMITS.maxTokens : 0);
    const left = LIMITS.outputTokens - outUsed;
    const going = more;
    // the last round, a continuation (it only writes: what it read is in the conversation), or too little of the
    // question's output left for another tool round: this call answers
    const last = going || call === LIMITS.toolRounds || (!rescue && left < LIMITS.answerReserve);
    let maxTokens = last ? Math.max(left, LIMITS.lastCallTokens) : Math.min(LIMITS.maxTokens, left);
    if (rescue || going) maxTokens = LIMITS.maxTokens;
    maxTokens = Math.min(maxTokens, cap - outUsed);
    const params = { model: MODEL, max_tokens: maxTokens, system, tools, messages: convo,
      output_config: { effort: going ? "low" : EFFORT } };
    if (rec.rescue) {
      // thinking off (accepted at effort low to high) and the earlier turns' thinking blocks left out with it, so the
      // whole output goes to the answer; the uncached context asks for the answer only (the cached part is unchanged)
      params.thinking = { type: "disabled" };
      params.output_config = { effort: "low" };
      params.system = [system[0], { type: "text", text: `${system[1].text}\n${NO_THINKING_NOTE}` }];
      params.messages = convo.map((m) => (Array.isArray(m.content)
        ? { ...m, content: m.content.filter((b) => b.type !== "thinking" && b.type !== "redacted_thinking") } : m));
    }
    if (last) params.tool_choice = { type: "none" };
    rescue = false;
    more = false;
    let roundText = "";
    let message;
    try {
      const stream = client.messages.stream(params, { signal, timeout: LIMITS.callMs });
      for await (const ev of stream) {
        if (ev.type === "content_block_start" && ev.content_block?.type === "tool_use") {
          send({ type: "status", text: statusText(lang, "think") });
        } else if (ev.type === "content_block_delta" && ev.delta?.type === "text_delta" && ev.delta.text) {
          // a new round's text after a tool round starts a new paragraph; a continuation joins the text it goes on with
          if (!roundText && pending === null && text && !/\n\s*$/.test(text)) emit("\n\n");
          roundText += ev.delta.text;
          if (pending !== null) {
            pending += ev.delta.text;
            if (pending.length >= 160) flush();
          } else {
            emit(ev.delta.text);
          }
        }
      }
      message = await stream.finalMessage();
      flush();
      jsonRetries = 0;
    } catch (err) {
      // eager input streaming: a tool input the SDK could not parse at all rejects the stream with a SyntaxError
      // (an API error is rethrown) — the turn is sent again, at most LIMITS.jsonRetries times in a row, unless this
      // turn already streamed text the reader has seen
      if (err instanceof SyntaxError && !signal.aborted && !roundText && jsonRetries < LIMITS.jsonRetries) {
        jsonRetries += 1;
        call -= 1;
        continue;
      }
      // the continuation of a cut answer failed, before it wrote anything or partway: the answer ends as the reader has
      // it (the rest still held back is let out after the loop), marked cut — the browser's 'continue' button asks
      // again — instead of an error under text the reader already has
      if (going && !signal.aborted) {
        rec.more_error = apiStatus(err) || err?.name || "error";
        break;
      }
      // the first call rejected as a bad request: once more with plain tool definitions (no strict, no eager)
      if (apiStatus(err) === 400 && call === 0 && !rec.fallback && !roundText) {
        rec.fallback = true;
        tools = TOOLS_PLAIN;
        call -= 1;
        continue;
      }
      throw err;
    }
    rec.rounds += 1;
    const u = message.usage || {};
    rec.in += u.input_tokens || 0;
    rec.out += u.output_tokens || 0;
    rec.cache_read += u.cache_read_input_tokens || 0;
    rec.cache_write += u.cache_creation_input_tokens || 0;
    rec.stop = message.stop_reason || "";
    outUsed += u.output_tokens || params.max_tokens;
    if (message.stop_reason === "refusal") {
      send({ type: "error", code: "refusal", message: errorText(lang, "refusal") });
      return { ...rec, status: "refusal" };
    }
    if (message.stop_reason === "pause_turn") {
      convo.push({ role: "assistant", content: message.content });
      continue;
    }
    const uses = (message.content || []).filter((b) => b.type === "tool_use");
    // the model thought through the whole call and wrote nothing (a long plan: measured at medium and at low effort):
    // the same turn once more without thinking, with a full call's output — the thinking-only message is not kept. Not
    // after a continuation in this request that only thought: the reader has the answer so far, which ends marked cut
    if (message.stop_reason === "max_tokens" && !roundText && !uses.length && !rec.rescue && !going) {
      rec.rescue = true;
      rescue = true;
      call -= 1;
      continue;
    }
    // the answer stopped at max_tokens with part of the question's output still unused (measured: a Monday itinerary
    // spent 4,000 of the 4,905 tokens left on thinking and stopped mid-sentence): it is continued once, in this
    // request — the cut message goes back as it came (thinking kept: the conversation stays append-only), the request
    // to go on is a user turn (no prefill on this model), and the rest joins what the reader already has
    if (message.stop_reason === "max_tokens" && roundText && !uses.length && !rec.rescue && !rec.more
        && cap - outUsed >= LIMITS.moreTokens && Date.now() - t0 < LIMITS.requestMs - LIMITS.moreMs) {
      flush(true);
      rec.more = true;
      more = true;
      convo.push({ role: "assistant", content: message.content });
      convo.push({ role: "user", content: neutralise(continueText([...(before + text)].slice(-160).join(""), qlang, site)) });
      pending = "";
      call -= 1;   // not a tool round
      continue;
    }
    if (!uses.length) break;   // end_turn, or max_tokens on a text answer (kept, marked cut)
    // a tool input cut off at max_tokens can parse as a valid partial object: never run it
    if (message.stop_reason === "max_tokens") {
      send({ type: "error", code: "truncated", message: errorText(lang, "truncated") });
      return { ...rec, status: "truncated" };
    }
    if (message.stop_reason !== "tool_use") break;
    convo.push({ role: "assistant", content: message.content });
    const results = [];
    for (const use of uses) {
      rec.tools.push(use.name);
      const input = validInput(use.name, use.input);
      if (!input) {
        results.push({ type: "tool_result", tool_use_id: use.id, is_error: true,
          content: JSON.stringify({ INVALID_JSON: neutralise(JSON.stringify(use.input ?? null)) }) });
        continue;
      }
      let out;
      if (use.name === "search_site") {
        send({ type: "status", text: statusText(lang, "search", input.query) });
        out = kb.searchText(input.query, { kind: input.kind, lang: input.lang || lang });
      } else {
        send({ type: "status", text: statusText(lang, "read", input.ids.map((id) => kb.titleOf(id)).join(", ")) });
        out = kb.pagesText(input.ids, { lang, budget: Math.max(0, toolChars) }).text;
      }
      if (out.length > toolChars) {
        out = toolChars > 200 ? `${out.slice(0, toolChars)}\n… (cut here: this question's reading limit)`
          : "This question's reading limit is used up: answer now with what you have.";
      }
      toolChars -= out.length;
      results.push({ type: "tool_result", tool_use_id: use.id, content: dataBlock(use.name, out) });
    }
    convo.push({ role: "user", content: results });
  }
  flush(true);
  if (!text.trim() && !cont) {   // thinking used the whole turn, or the model said nothing
    send({ type: "error", code: "empty", message: errorText(lang, "error") });
    return { ...rec, status: "empty" };
  }
  // a continuation's links are checked together with the cut answer it follows (the browser shows them as one answer)
  const { links, fix } = kb.fixLinks(cont ? `${cont.partial}\n${text}` : text, lang);
  send({ type: "done", links, fix, ...(rec.stop === "max_tokens" ? { cut: true } : {}) });
  return { ...rec, status: "ok", links: links.length };
}

// ------------------------------------------------------------------ the handler
export function createHandler(deps = {}) {
  const env = deps.env ?? process.env;
  const now = deps.now ?? (() => new Date());
  const log = deps.log ?? ((rec) => console.log(JSON.stringify(rec)));
  const limiter = deps.limiter ?? createLimiter();
  const knowledge = deps.knowledge ?? defaultKnowledge;
  const site = deps.site ?? loadSite();   // the public address, the site's and the city's names (chatbot/site.js)
  const newClient = deps.makeClient ?? makeClient;
  let client = deps.client ?? null;
  // a key is set (read on every request: nothing about the key is kept but the client made with it)
  const configured = () => !!(deps.client || apiKey(env));

  async function getClient() {
    if (!client) client = await newClient(apiKey(env));
    return client;
  }

  /** GET /api/chat/: is the assistant ready? 200 {ready: true}, or 503 {ready: false, code} — 'not_configured' (no
   *  key) or 'unavailable' (the knowledge files did not load). The page asks this once before it shows a question box
   *  (chat.js). No model call, nothing counted; a same-origin GET carries no Origin, so only another website's page
   *  (Sec-Fetch-Site: cross-site, or an Origin off the allow-list) is refused. HEAD: the same status, no body. */
  async function status(request, done) {
    const origin = request.headers.get("origin");
    if ((request.headers.get("sec-fetch-site") || "").toLowerCase() === "cross-site"
        || (origin && !originAllowed(request, env, site))) {
      done("forbidden_origin");
      return json(403, { code: "forbidden_origin" });
    }
    let res;
    if (!configured()) {
      done("not_configured", { probe: true });
      res = json(503, { ready: false, code: "not_configured", message: errorText("en", "not_configured") });
    } else {
      try {
        await knowledge();
        done("ready", { probe: true });
        res = json(200, { ready: true });
      } catch (err) {
        done("unavailable", { probe: true, reason: err?.code || err?.name || "load" });
        res = json(503, { ready: false, code: "unavailable", message: errorText("en", "busy") });
      }
    }
    return request.method === "HEAD" ? new Response(null, { status: res.status, headers: res.headers }) : res;
  }

  return async function handle(request) {
    const t0 = Date.now();
    const done = (status, extra = {}) => log({ evt: "chat", status, ms: Date.now() - t0, ...extra });
    if (request.method === "GET" || request.method === "HEAD") return status(request, done);
    if (request.method !== "POST") {
      done("method");
      return json(405, { code: "method_not_allowed" }, { Allow: "GET, HEAD, POST" });
    }
    if (!originAllowed(request, env, site)) {
      done("forbidden_origin");
      return json(403, { code: "forbidden_origin" });
    }
    if (!configured()) {
      done("not_configured");
      return json(503, { code: "not_configured", message: errorText("en", "not_configured") });
    }
    const key = clientKey(clientIp(request));
    const refuse = (gate) => {
      const code = limitCode(gate.limit);
      done("rate_limited", { limit: gate.limit });
      return json(429, { code, message: errorText("en", code) }, { "Retry-After": String(gate.retry) });
    };
    // a client (or the instance) already at a limit is refused before its body is read; nothing is counted yet
    let gate = limiter.check(key, now().getTime());
    if (!gate.ok) return refuse(gate);
    let req;
    try {
      req = cleanRequest(await readBody(request, LIMITS.bodyBytes), site);
    } catch (err) {
      // anything else a body can make fail here (the client gone mid-upload, a value no check foresaw) is still the
      // request's fault: 400, never an unhandled error — and never counted against anyone's limit
      const e = err instanceof HttpError ? err : new HttpError(400, "bad_request");
      done(e.code, e === err ? {} : { reason: err?.name || "error" });
      return json(e.status, { code: e.code, message: errorText("en", e.code) });
    }
    // a question that passed every check: counted now (refused if a request alongside took the last place)
    gate = limiter.take(key, now().getTime());
    if (!gate.ok) return refuse(gate);
    let kb;
    let api;
    try {
      [kb, api] = await Promise.all([knowledge(), getClient()]);
    } catch (err) {
      done("unavailable", { reason: err?.code || err?.name || "load" });
      return json(503, { code: "unavailable", message: errorText("en", "busy") });
    }
    const ac = new AbortController();
    let timedOut = false;
    const timer = setTimeout(() => {
      timedOut = true;
      ac.abort();
    }, LIMITS.requestMs);
    const stop = () => ac.abort();
    request.signal?.addEventListener("abort", stop);
    const enc = new TextEncoder();
    let open = true;   // false once the reader has gone (cancel) or the stream is closed
    const body = new ReadableStream({
      async start(controller) {
        const send = (ev) => {
          if (!open || (ac.signal.aborted && ev.type !== "error")) return;
          controller.enqueue(enc.encode(`data: ${JSON.stringify(ev)}\n\n`));
        };
        try {
          const rec = await answer({ client: api, kb, ...req, send, signal: ac.signal, now: now(), site });
          done(rec.status, { rounds: rec.rounds, tools: rec.tools, in: rec.in, out: rec.out,
            cache_read: rec.cache_read, cache_write: rec.cache_write, stop: rec.stop, fallback: rec.fallback || undefined,
            cont: rec.cont || undefined, rescue: rec.rescue || undefined, more: rec.more || undefined,
            more_error: rec.more_error, links: rec.links, lang: req.lang });
        } catch (err) {
          const status = apiStatus(err);
          let code = "error";
          if (timedOut) code = "timeout";
          else if (ac.signal.aborted) code = "client_gone";
          else if (status === 429 || status === 529 || status >= 500 || !status) code = "busy";
          else if (status === 401 || status === 403) code = "unavailable";
          if (code !== "client_gone") send({ type: "error", code, message: errorText(req.lang, code === "unavailable" ? "busy" : code) });
          // 401/403: the Anthropic API refused the key (a wrong or revoked ANTHROPIC_API_KEY) — the log says which, the
          // reader only that no answer can be made now
          done(code, { api_status: status || undefined, lang: req.lang,
            hint: status === 401 || status === 403 ? "check ANTHROPIC_API_KEY" : undefined });
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
