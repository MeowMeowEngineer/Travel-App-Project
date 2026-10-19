// node --test — tools/chat_dev.mjs, the local server for trying the assistant with a real key: it serves a build
// folder and answers /api/chat/ with the Vercel function's own handler over that folder's chat/ files. Here with a
// FAKE built folder (Incheon-shaped, every value invented) and a scripted model: no network, no key.
import assert from "node:assert/strict";
import { mkdir, mkdtemp, writeFile } from "node:fs/promises";
import { tmpdir } from "node:os";
import path from "node:path";
import { test } from "node:test";

import { tokens } from "../../chatbot/knowledge.js";
import { createDevServer, devHandler } from "../../tools/chat_dev.mjs";
import { fakeClient, sseEvents, textRound } from "./fake_model.js";

const SITE = "https://incheon.example.com";

async function builtFolder() {
  const dir = await mkdtemp(path.join(tmpdir(), "chat-dev-"));
  await mkdir(path.join(dir, "chat"));
  await mkdir(path.join(dir, "places", "test-beach-a"), { recursive: true });
  await writeFile(path.join(dir, "index.html"), "<!doctype html><title>home</title>");
  await writeFile(path.join(dir, "places", "test-beach-a", "index.html"), "<!doctype html><title>beach</title>");
  const docs = { "/places/test-beach-a/": { t: "[테스트] 가상 해변 A", k: "place", x: "[테스트] 가상 해변 A — 관광지" } };
  const index = { v: 1, docs: { "/places/test-beach-a/": [tokens("[테스트] 가상 해변 A /places/test-beach-a/").join(" "), ""] } };
  await writeFile(path.join(dir, "chat", "catalog.txt"), "P /places/test-beach-a/ | [테스트] 가상 해변 A\n");
  await writeFile(path.join(dir, "chat", "docs.json"), JSON.stringify({ v: 1, site: SITE, docs, alias: {}, ext: [] }));
  await writeFile(path.join(dir, "chat", "index.json"), JSON.stringify(index));
  await writeFile(path.join(dir, "chat", "site.json"), JSON.stringify({ url: SITE, name: "인천 여행의 모든 것",
    city: { ko: "인천", en: "Incheon" }, origins: [] }));
  return dir;
}

async function serve(dir, deps) {
  const server = createDevServer({ dir, handler: devHandler(dir, { log: () => {}, ...deps }) });
  await new Promise((ok) => server.listen(0, "127.0.0.1", ok));
  const base = `http://127.0.0.1:${server.address().port}`;
  return { base, close: () => new Promise((ok) => server.close(ok)) };
}

test("chat_dev: the build's pages, and /api/chat/ resting without a key", async () => {
  const dir = await builtFolder();
  const { base, close } = await serve(dir, { env: {} });
  try {
    const home = await fetch(`${base}/`);
    assert.equal(home.status, 200);
    assert.match(home.headers.get("content-type"), /^text\/html/);
    const bare = await fetch(`${base}/places/test-beach-a`, { redirect: "manual" });
    assert.equal(bare.status, 308);
    assert.equal(bare.headers.get("location"), "/places/test-beach-a/");
    assert.equal((await fetch(`${base}/%2e%2e/%2e%2e/package.json`)).status, 404);   // nothing outside the folder
    assert.equal((await fetch(`${base}/../package.json`)).status, 404);
    const status = await fetch(`${base}/api/chat/`);
    assert.equal(status.status, 503);
    assert.equal((await status.json()).code, "not_configured");
    const post = await fetch(`${base}/api/chat/`, { method: "POST", headers: { "content-type": "application/json", origin: base },
      body: JSON.stringify({ messages: [{ role: "user", content: "가상 해변?" }] }) });
    assert.equal(post.status, 503);
  } finally {
    await close();
  }
});

test("chat_dev: with a key in the environment the page's own origin asks and gets the answer with its page link", async () => {
  const dir = await builtFolder();
  const made = [];
  const client = fakeClient([textRound("[테스트] 가상 해변 A입니다. [가상 해변 A](/places/test-beach-a/)")]);
  const { base, close } = await serve(dir, { env: { ANTHROPIC_API_KEY: "sk-ant-test-not-a-real-key" },
    makeClient: async (key) => { made.push(key); return client; } });
  try {
    assert.deepEqual(await (await fetch(`${base}/api/chat/`)).json(), { ready: true });
    const res = await fetch(`${base}/api/chat/`, { method: "POST", headers: { "content-type": "application/json", origin: base },
      body: JSON.stringify({ messages: [{ role: "user", content: "가상 해변 A 알려 줘" }], lang: "ko", page: "/" }) });
    assert.equal(res.status, 200);
    const evs = await sseEvents(res);
    assert.deepEqual(evs.at(-1).links, [{ title: "[테스트] 가상 해변 A", url: `${SITE}/places/test-beach-a/`, ext: false }]);
    assert.deepEqual(made, ["sk-ant-test-not-a-real-key"]);
    assert.match(client.calls[0].params.system[0].text, /^You are 인천 여행 도우미/);
  } finally {
    await close();
  }
});
