// node --test — tools/serve_preview.mjs, the local preview for scenario QA: it serves a build folder and answers
// /api/chat/ and /api/plan/ with the function modules Vercel deploys (api/chat.js, api/plan.js) over that folder's chat/
// files, the key read from the environment or from ANTHROPIC_API_KEY alone in a .env file — never printed. Here with a
// FAKE built folder (every value invented), a fake key and no model call: no network.
import assert from "node:assert/strict";
import { spawn } from "node:child_process";
import { mkdir, mkdtemp, writeFile } from "node:fs/promises";
import { tmpdir } from "node:os";
import path from "node:path";
import { test } from "node:test";
import { fileURLToPath } from "node:url";

import { tokens } from "../../chatbot/knowledge.js";
import { envFileKey, parseArgs } from "../../tools/serve_preview.mjs";

const ROOT = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "..", "..");
const SITE = "https://incheon.webforai.kr";
const FAKE = "sk-ant-TEST-ONLY-not-a-real-key-0123456789";
const OTHER = "TEST-ONLY-other-secret-9876";

async function builtFolder() {
  const dir = await mkdtemp(path.join(tmpdir(), "serve-preview-"));
  await mkdir(path.join(dir, "chat"));
  await writeFile(path.join(dir, "index.html"), "<!doctype html><title>home</title>");
  const docs = { "/places/test-beach-a/": { t: "[테스트] 가상 해변 A", k: "place", x: "[테스트] 가상 해변 A — 관광지" } };
  const index = { v: 1, docs: { "/places/test-beach-a/": [tokens("[테스트] 가상 해변 A /places/test-beach-a/").join(" "), ""] } };
  await writeFile(path.join(dir, "chat", "catalog.txt"), "P /places/test-beach-a/ | [테스트] 가상 해변 A\n");
  await writeFile(path.join(dir, "chat", "docs.json"), JSON.stringify({ v: 1, site: SITE, docs, alias: {}, ext: [] }));
  await writeFile(path.join(dir, "chat", "index.json"), JSON.stringify(index));
  await writeFile(path.join(dir, "chat", "site.json"), JSON.stringify({ url: SITE, name: "인천각",
    city: { ko: "인천", en: "Incheon" }, origins: [] }));
  return dir;
}

/** The harness on a free port over `dir` without building; resolves with its address and everything it printed. */
function start(dir, envFile) {
  const env = { ...process.env };
  delete env.ANTHROPIC_API_KEY;
  const child = spawn(process.execPath, [path.join(ROOT, "tools", "serve_preview.mjs"), "--no-build", "--out", dir,
    "--port", "0", "--dotenv", envFile], { cwd: ROOT, env });
  const log = { text: "" };
  child.stdout.on("data", (b) => { log.text += b; });
  child.stderr.on("data", (b) => { log.text += b; });
  return new Promise((ok, fail) => {
    const timer = setTimeout(() => { child.kill(); fail(new Error(`no address: ${log.text}`)); }, 15000);
    child.stdout.on("data", () => {
      const m = log.text.match(/http:\/\/127\.0\.0\.1:(\d+)\//u);
      if (!m) return;
      clearTimeout(timer);
      ok({ base: `http://127.0.0.1:${m[1]}`, log,
        stop: () => new Promise((done) => { child.once("exit", done); child.kill("SIGTERM"); }) });
    });
    child.once("exit", (code) => { clearTimeout(timer); fail(new Error(`exited ${code}: ${log.text}`)); });
  });
}

test("serve_preview: the key line alone is read from the env file", async () => {
  const dir = await mkdtemp(path.join(tmpdir(), "serve-preview-env-"));
  const file = path.join(dir, ".env");
  await writeFile(file, `# comment\nTOURAPI_KEY=${OTHER}\nexport ANTHROPIC_API_KEY="${FAKE}"\n`);
  assert.equal(envFileKey(file), FAKE);
  await writeFile(file, `ANTHROPIC_API_KEY=${FAKE}   # note\n`);
  assert.equal(envFileKey(file), FAKE);
  await writeFile(file, `TOURAPI_KEY=${OTHER}\nANTHROPIC_API_KEY=\n`);
  assert.equal(envFileKey(file), "");
  assert.equal(envFileKey(path.join(dir, "missing.env")), "");
  assert.deepEqual(parseArgs([]), { data: "data/incheon", out: "dist-preview", port: 8788, host: "127.0.0.1", build: true,
    envFile: ".env" });
  assert.equal(parseArgs(["--no-build", "--dir", "dist-qa", "--port", "8790"]).out, "dist-qa");
  assert.throws(() => parseArgs(["--port", "x"]));
  assert.throws(() => parseArgs(["--mode", "production"]));
});

test("serve_preview: with the key in .env both function paths answer through api/, the key never printed", async () => {
  const dir = await builtFolder();
  const envFile = path.join(dir, ".env");
  await writeFile(envFile, `TOURAPI_KEY=${OTHER}\nANTHROPIC_API_KEY=${FAKE}\n`);
  const s = await start(dir, envFile);
  try {
    assert.match(s.log.text, /키 있음\(\.env의 ANTHROPIC_API_KEY\)/u);
    const home = await fetch(`${s.base}/`);
    assert.equal(home.status, 200);
    assert.deepEqual(await (await fetch(`${s.base}/api/chat/`)).json(), { ready: true });   // no model call
    assert.equal((await fetch(`${s.base}/api/chat`)).status, 200);
    assert.equal((await fetch(`${s.base}/api/plan/`)).status, 405);                        // the planner: POST only
    const bad = await fetch(`${s.base}/api/plan/`, { method: "POST", headers: { "content-type": "application/json",
      origin: s.base }, body: "{}" });
    assert.equal(bad.status, 400);                                                          // checked before any model call
    assert.equal((await bad.json()).code, "bad_request");
    const foreign = await fetch(`${s.base}/api/plan/`, { method: "POST", headers: { "content-type": "application/json",
      origin: "https://example.invalid" }, body: "{}" });
    assert.equal(foreign.status, 403);
  } finally {
    await s.stop();
  }
  assert.ok(!s.log.text.includes(FAKE) && !s.log.text.includes(OTHER), "a key reached the output");
});

test("serve_preview: without a key the functions rest (503 not_configured)", async () => {
  const dir = await builtFolder();
  const s = await start(dir, path.join(dir, "no.env"));
  try {
    assert.match(s.log.text, /키 없음/u);
    const chat = await fetch(`${s.base}/api/chat/`);
    assert.equal(chat.status, 503);
    assert.equal((await chat.json()).code, "not_configured");
    const plan = await fetch(`${s.base}/api/plan/`, { method: "POST", headers: { "content-type": "application/json",
      origin: s.base }, body: JSON.stringify({ conditions: {} }) });
    assert.equal(plan.status, 503);
    assert.equal((await plan.json()).code, "not_configured");
  } finally {
    await s.stop();
  }
});
