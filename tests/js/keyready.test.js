// node --test — the site assistant is key-ready: with no ANTHROPIC_API_KEY it says so at once (503 not_configured on
// GET and POST, no client made, nothing counted); with the key in the environment — and no other change — it answers
// from this site's data with checked page links, made with that key only. The knowledge below is an Incheon-shaped
// FAKE (every name, path and value is invented and marked [테스트]; nothing of it is published) and the model is a
// scripted stream (tests/js/fake_model.js): no network, no key.
import assert from "node:assert/strict";
import { test } from "node:test";

import { Knowledge, tokens } from "../../chatbot/knowledge.js";
import { MODEL, errorText, rules } from "../../chatbot/prompt.js";
import { apiKey, createHandler, createLimiter, makeClient } from "../../chatbot/server.js";
import { siteFrom } from "../../chatbot/site.js";
import { fakeClient, sseEvents, textRound, toolRound } from "./fake_model.js";

const SITE = "https://incheon.example.com";
const site = siteFrom({ url: SITE, name: "인천 여행의 모든 것", city: { ko: "인천", en: "Incheon" } });
const FAKE_KEY = "sk-ant-test-0000-not-a-real-key";

const DOCS = {
  "/places/test-beach-a/": { t: "[테스트] 가상 해변 A", k: "place",
    x: "[테스트] 가상 해변 A — 관광지\n위치: 중구 운서동 · 영종·용유 권역\n정보(값 — 출처):\n"
      + "- 이용시간: [테스트] 이용시간 값 — 한국관광공사 TourAPI (출처 확인 2026-10-19)\n"
      + "- 주차: [테스트] 주차 값 — 한국관광공사 TourAPI (출처 확인 2026-10-19)\n사이트에 없는 값(확인 필요): 쉬는 날·요금·전화" },
  "/places/test-food-b/": { t: "[테스트] 가상 식당 B", k: "place",
    x: "[테스트] 가상 식당 B — 음식점\n위치: 연수구\n- 대표 메뉴: [테스트] 메뉴 값 — 한국관광공사 TourAPI (출처 확인 2026-10-19)" },
  "/about/": { t: "소개·출처", k: "page", x: "인천 여행의 모든 것 — 소개·출처\n사이트 안내 챗봇: 모델은 Anthropic의 Claude Haiku 5.5." },
};
const CATALOG = "# Site catalog (test)\nP /places/test-beach-a/ | [테스트] 가상 해변 A | 관광지 | 중구·운서동 | 시간 [테스트] 이용시간 값\n"
  + "P /places/test-food-b/ | [테스트] 가상 식당 B | 음식점 | 연수구 | 메뉴 [테스트] 메뉴 값\nS /about/ | 소개·출처";

function indexOf(docs) {   // pipeline/chat_index.py index_json, as chat.test.js builds it
  const out = {};
  for (const [key, d] of Object.entries(docs)) {
    const head = tokens(`${d.t} ${key}`);
    for (const t of tokens(d.x.split("\n")[0])) if (!head.includes(t)) head.push(t);
    out[key] = [head.join(" "), tokens(d.x).filter((t) => !head.includes(t)).join(" ")];
  }
  return { v: 1, docs: out };
}
const kb = () => new Knowledge({ catalog: CATALOG, docs: { v: 1, site: SITE, docs: DOCS, alias: {}, ext: [] }, index: indexOf(DOCS) });

const ANSWER = "[테스트] 가상 해변 A의 이용시간은 [테스트] 이용시간 값입니다(한국관광공사 TourAPI). 쉬는 날은 사이트에 없음 — "
  + "방문 전 확인이 필요합니다.\n\n[가상 해변 A](/places/test-beach-a/) · [없는 페이지](/places/nowhere/)";

function request({ method = "POST", origin = SITE, body, headers = {} } = {}) {
  const h = { "content-type": "application/json", "x-real-ip": "203.0.113.7", ...headers };
  if (origin) h.origin = origin;
  return new Request(`${SITE}/api/chat/`, { method, headers: h,
    body: method === "POST" ? JSON.stringify(body ?? { messages: [{ role: "user", content: "가상 해변 A 몇 시까지 해?" }], lang: "ko",
      page: "/places/test-beach-a/" }) : undefined });
}

function setup(env, rounds = []) {
  const made = [];
  const logs = [];
  const handle = createHandler({
    env, site, knowledge: () => kb(), log: (r) => logs.push(r), limiter: createLimiter(100),
    now: () => new Date("2026-10-19T03:00:00Z"),
    makeClient: async (key) => {
      made.push(key);
      const c = fakeClient(rounds);
      made.client = c;
      return c;
    },
  });
  return { handle, made, logs };
}

// ------------------------------------------------------------------ no key
test("no key: POST and GET answer 503 not_configured at once — no client is made, nothing counted, codes only in the log", async () => {
  for (const env of [{}, { ANTHROPIC_API_KEY: "" }, { ANTHROPIC_API_KEY: "  \n" }, { ANTHROPIC_AUTH_TOKEN: "only-a-token" }]) {
    const { handle, made, logs } = setup(env);
    const post = await handle(request());
    assert.equal(post.status, 503, JSON.stringify(env));
    const pj = await post.json();
    assert.equal(pj.code, "not_configured");
    assert.equal(pj.message, errorText("en", "not_configured"));
    const get = await handle(request({ method: "GET", origin: null }));   // a same-origin GET carries no Origin
    assert.equal(get.status, 503);
    assert.deepEqual(await get.json(), { ready: false, code: "not_configured", message: errorText("en", "not_configured") });
    assert.equal(get.headers.get("cache-control"), "no-store");
    const head = await handle(request({ method: "HEAD", origin: null }));
    assert.equal(head.status, 503);
    assert.equal(await head.text(), "");
    assert.deepEqual(made, []);                                             // the SDK is never even loaded
    assert.deepEqual(logs.map((l) => l.status), ["not_configured", "not_configured", "not_configured"]);
    assert.ok(logs.every((l) => Object.keys(l).every((k) => ["evt", "status", "ms", "probe"].includes(k))), JSON.stringify(logs));
  }
  assert.equal(apiKey({}), "");
  assert.equal(apiKey({ ANTHROPIC_API_KEY: ` ${FAKE_KEY}\n` }), FAKE_KEY);
});

// ------------------------------------------------------------------ with the key, nothing else changed
test("with the key: GET says ready; a question streams its answer with the checked page link — the client made once, with that key", async () => {
  const rounds = [toolRound([["search_site", { query: "가상 해변 이용시간" }]]), textRound(ANSWER),
    textRound("[테스트] 가상 식당 B의 대표 메뉴는 [테스트] 메뉴 값입니다. [가상 식당 B](/places/test-food-b/)")];
  const { handle, made, logs } = setup({ ANTHROPIC_API_KEY: ` ${FAKE_KEY}\n` }, rounds);
  const get = await handle(request({ method: "GET", origin: null }));
  assert.equal(get.status, 200);
  assert.deepEqual(await get.json(), { ready: true });

  const res = await handle(request());
  assert.equal(res.status, 200);
  assert.match(res.headers.get("content-type"), /^text\/event-stream/);
  const evs = await sseEvents(res);
  assert.ok(evs.some((e) => e.type === "status" && e.text.includes("가상 해변 이용시간")), JSON.stringify(evs));
  assert.equal(evs.filter((e) => e.type === "text").map((e) => e.delta).join(""), ANSWER);
  const done = evs.at(-1);
  assert.equal(done.type, "done");
  assert.deepEqual(done.links, [{ title: "[테스트] 가상 해변 A", url: `${SITE}/places/test-beach-a/`, ext: false }]);
  assert.equal(done.fix["/places/test-beach-a/"], `${SITE}/places/test-beach-a/`);
  assert.equal(done.fix["/places/nowhere/"], null);                          // a page that does not exist stays text

  // the request the model got: Haiku 5.5, this site's rules and catalog (cached), the search result as site data
  const calls = made.client.calls;
  assert.equal(calls.length, 2);
  assert.equal(calls[0].params.model, "claude-haiku-5-5");
  assert.equal(MODEL, "claude-haiku-5-5");
  const sys = calls[0].params.system[0];
  assert.ok(sys.text.startsWith("You are 인천 여행 도우미 (the Incheon travel helper)") && sys.text.includes(SITE), sys.text.slice(0, 200));
  assert.deepEqual(sys.cache_control, { type: "ephemeral" });
  assert.ok(sys.text.includes("P /places/test-beach-a/"));
  const result = calls[1].params.messages.at(-1).content[0];
  assert.equal(result.type, "tool_result");
  assert.match(result.content, /^<site_data source="search_site">[\s\S]*가상 해변 A[\s\S]*<\/site_data>$/);

  // the next question reuses the client: made once, with the trimmed key and nothing else
  const again = await sseEvents(await handle(request({ body: { messages: [{ role: "user", content: "식당 B 메뉴는?" }], lang: "ko" } })));
  assert.equal(again.at(-1).links[0].url, `${SITE}/places/test-food-b/`);
  assert.deepEqual([...made], [FAKE_KEY]);
  const seen = JSON.stringify(logs) + JSON.stringify(evs) + JSON.stringify(again);
  assert.ok(!seen.includes(FAKE_KEY), "the key never reaches a log or a response");
  assert.deepEqual(logs.map((l) => l.status), ["ready", "ok", "ok"]);
});

test("the real SDK client is made with ANTHROPIC_API_KEY only — never ANTHROPIC_AUTH_TOKEN — and sends nothing when made", async (t) => {
  try {
    await import("@anthropic-ai/sdk");
  } catch (err) {
    t.skip(`@anthropic-ai/sdk not installed (npm ci): ${err.code || err.name}`);
    return;
  }
  const saved = process.env.ANTHROPIC_AUTH_TOKEN;
  process.env.ANTHROPIC_AUTH_TOKEN = "token-that-must-not-be-used";
  try {
    const client = await makeClient(FAKE_KEY);
    assert.equal(client.apiKey, FAKE_KEY);
    assert.equal(client.authToken, null);
    assert.equal(client.maxRetries, 1);
    assert.equal(typeof client.messages.stream, "function");
  } finally {
    if (saved === undefined) delete process.env.ANTHROPIC_AUTH_TOKEN;
    else process.env.ANTHROPIC_AUTH_TOKEN = saved;
  }
});

test("a rejected key (401): the reader gets a calm 'cannot answer now', the log says to check ANTHROPIC_API_KEY — never the key", async () => {
  const err = Object.assign(new Error(`401 invalid x-api-key ${FAKE_KEY}`), { status: 401 });
  const { handle, logs } = setup({ ANTHROPIC_API_KEY: FAKE_KEY }, [{ reject: err }]);
  const evs = await sseEvents(await handle(request()));
  // the stream opens with the answer's language and direction (server.js 'meta'), then the calm error
  assert.deepEqual(evs, [{ type: "meta", dir: "", site: "ko", lang: "ko" },
    { type: "error", code: "unavailable", message: errorText("ko", "busy") }]);
  assert.equal(logs.at(-1).status, "unavailable");
  assert.equal(logs.at(-1).api_status, 401);
  assert.equal(logs.at(-1).hint, "check ANTHROPIC_API_KEY");
  assert.ok(!JSON.stringify(logs).includes(FAKE_KEY) && !JSON.stringify(evs).includes(FAKE_KEY));
});

test("the status: another website's page is refused; the knowledge files missing is 503 unavailable", async () => {
  const { handle } = setup({ ANTHROPIC_API_KEY: FAKE_KEY });
  assert.equal((await handle(request({ method: "GET", origin: null, headers: { "sec-fetch-site": "cross-site" } }))).status, 403);
  assert.equal((await handle(request({ method: "GET", origin: "https://evil.example" }))).status, 403);
  assert.equal((await handle(request({ method: "GET", origin: SITE }))).status, 200);
  const logs = [];
  const broken = createHandler({ env: { ANTHROPIC_API_KEY: FAKE_KEY }, site, log: (r) => logs.push(r),
    knowledge: () => Promise.reject(Object.assign(new Error("no file"), { code: "ENOENT" })) });
  const res = await broken(request({ method: "GET", origin: null }));
  assert.equal(res.status, 503);
  assert.deepEqual(await res.json(), { ready: false, code: "unavailable", message: errorText("en", "busy") });
  assert.equal(logs[0].reason, "ENOENT");
});

test("the rules name this site and its city from site.json — no other city", () => {
  const r = rules(site);
  assert.ok(r.includes("인천 여행 도우미") && r.includes("travel in Incheon") && r.includes(`[page name](${SITE}/places/`));
  for (const word of ["군산", "Gunsan", "群山"]) assert.ok(!r.includes(word), word);
});
