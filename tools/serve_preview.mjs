// 시나리오 QA용 로컬 미리보기 — 미리보기 빌드를 만들어 127.0.0.1에 띄우고, /api/chat/(사이트 도우미)과 /api/plan/(AI 코스
// 만들기)을 Vercel이 배포하는 바로 그 함수 모듈 api/chat.js·api/plan.js로 답한다. 함수는 배포 때처럼 public/chat/을 읽는데,
// 여기서는 그 자리가 이번 빌드 폴더다(임시 폴더의 public → 빌드 폴더 연결, 함수 모듈을 부르기 전에 그 폴더로 옮겨 감).
//
//   node tools/serve_preview.mjs                          # 빌드 후 http://127.0.0.1:8788 (npm run preview)
//   node tools/serve_preview.mjs --no-build               # 이미 만든 dist-preview를 그대로
//   node tools/serve_preview.mjs --data data/incheon --out dist-qa --port 8790
//
// 빌드: python -m pipeline.build --data <data> --out <out> --mode preview (draft까지 보이고 전부 noindex). 파이썬 명령은
// 환경 변수 PYTHON(없으면 python). 다시 빌드하면 이 서버도 다시 띄운다(함수가 지식을 처음 읽을 때 기억한다).
// 키: 환경 변수 ANTHROPIC_API_KEY, 없으면 저장소 루트의 .env(--dotenv로 다른 파일)에서 ANTHROPIC_API_KEY 한 줄만 읽는다 —
// 다른 줄(TOURAPI_KEY 등)은 읽지 않고, 키 값은 어디에도 출력하지 않는다. 키가 없으면 페이지는 키 없는 배포와 똑같이
// 'AI 도우미 준비 중'과 사이트 검색을 보이고 /api/plan/은 503 not_configured로 답한다. 키가 있으면 질문·코스 만들기마다
// 실제 API를 부르고 비용이 든다. 함수 로그(요청마다 JSON 한 줄, 숫자만 — 질문·답·키 없음)는 이 터미널에 나온다.
// 지도: site.json kakao_js_key는 카카오 개발자 콘솔에 등록한 웹 도메인에서만 동작한다 — http://127.0.0.1:<포트>를
// 콘솔에 더하지 않으면 지도 상자는 글과 '지도를 불러오지 못했습니다' 줄만 보인다(SDK 401).
import { spawnSync } from "node:child_process";
import { existsSync, mkdtempSync, readFileSync, rmSync, symlinkSync } from "node:fs";
import { tmpdir } from "node:os";
import path from "node:path";
import { fileURLToPath, pathToFileURL } from "node:url";

import { createDevServer } from "./chat_dev.mjs";

const ROOT = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "..");
export const DEFAULTS = { data: "data/incheon", out: "dist-preview", port: 8788, host: "127.0.0.1", build: true,
  envFile: ".env" };

/** ANTHROPIC_API_KEY from a dotenv file: only that one line (`KEY=value`, `export KEY=value`, quoted or not), '' when
 *  the file or the line is missing. Nothing else in the file is read into the process. */
export function envFileKey(file, name = "ANTHROPIC_API_KEY") {
  let text;
  try {
    text = readFileSync(file, "utf8");
  } catch {
    return "";
  }
  for (const raw of text.split(/\r?\n/u)) {
    const m = raw.match(/^\s*(?:export\s+)?([A-Za-z_][A-Za-z0-9_]*)\s*=\s*(.*?)\s*$/u);
    if (!m || m[1] !== name) continue;
    let v = m[2];
    if (/^(["']).*\1$/u.test(v)) v = v.slice(1, -1);
    else v = v.replace(/\s+#.*$/u, "");
    return v.trim();
  }
  return "";
}

export function parseArgs(argv) {
  const out = { ...DEFAULTS };
  for (let i = 0; i < argv.length; i += 1) {
    const [k, v] = [argv[i], argv[i + 1]];
    if (k === "--no-build") { out.build = false; continue; }
    if (k === "--data") out.data = v;
    else if (k === "--out" || k === "--dir") out.out = v;
    else if (k === "--port") out.port = Number(v);
    else if (k === "--host") out.host = v;
    else if (k === "--dotenv") out.envFile = v;   // not --env-file: Node 22 reads that flag itself even after the script
    else throw new Error(`모르는 옵션: ${k}`);
    i += 1;
  }
  if (!Number.isInteger(out.port) || out.port < 0 || out.port > 65535) throw new Error("--port는 0–65535");
  return out;
}

/** The key source for the message: the environment, the env file, or none (the value itself is never returned). */
export function loadKey(env, envFile) {
  if (String(env.ANTHROPIC_API_KEY ?? "").trim()) return "환경 변수";
  const key = envFileKey(envFile);
  if (!key) return "";
  env.ANTHROPIC_API_KEY = key;   // in this process only, for the function modules (they read process.env)
  return path.basename(envFile);
}

/** The function modules api/chat.js and api/plan.js answering from `dir`/chat: they read public/chat under the working
 *  directory (chatbot/site.js loadSite, knowledge.js defaultKnowledge), so the process moves to a scratch folder whose
 *  public is the build folder before it imports them. Returns {chat, plan, cleanup}. */
export async function functionsFor(dir) {
  const work = mkdtempSync(path.join(tmpdir(), "incheongak-preview-"));
  symlinkSync(path.resolve(dir), path.join(work, "public"), process.platform === "win32" ? "junction" : "dir");
  process.chdir(work);
  const chat = (await import(pathToFileURL(path.join(ROOT, "api", "chat.js")).href)).default;
  const plan = (await import(pathToFileURL(path.join(ROOT, "api", "plan.js")).href)).default;
  return { chat, plan, cleanup: () => rmSync(work, { recursive: true, force: true }) };
}

export async function main(argv = process.argv.slice(2)) {
  let opt;
  try {
    opt = parseArgs(argv);
  } catch (err) {
    console.error(err.message);
    return 2;
  }
  const out = path.resolve(ROOT, opt.out);
  if (opt.build) {
    const python = process.env.PYTHON || "python";
    const args = ["-m", "pipeline.build", "--data", opt.data, "--out", opt.out, "--mode", "preview"];
    console.log(`빌드: ${python} ${args.join(" ")}`);
    const r = spawnSync(python, args, { cwd: ROOT, stdio: "inherit" });
    if (r.status !== 0) {
      console.error(`빌드 실패(종료 코드 ${r.status ?? r.error?.code}) — 서버를 띄우지 않습니다.`);
      return 1;
    }
  }
  if (!existsSync(path.join(out, "chat", "docs.json"))) {
    console.error(`${out}/chat/ 이 없습니다. 먼저 빌드하세요(--no-build 없이): python -m pipeline.build --data ${opt.data} --out ${opt.out} --mode preview`);
    return 2;
  }
  const source = loadKey(process.env, path.resolve(ROOT, opt.envFile));
  const fns = await functionsFor(out);
  const server = createDevServer({ dir: out, routes: { "/api/chat": (r) => fns.chat.fetch(r), "/api/plan": (r) => fns.plan.fetch(r) } });
  const stop = () => {
    server.close(() => { fns.cleanup(); process.exit(0); });
    server.closeAllConnections();
  };
  process.on("SIGINT", stop);
  process.on("SIGTERM", stop);
  await new Promise((ok, fail) => server.once("error", fail).listen(opt.port, opt.host, ok)).catch((err) => {
    fns.cleanup();
    throw err;
  });
  const key = source ? `키 있음(${source}의 ANTHROPIC_API_KEY) — 질문·코스 만들기마다 실제 API를 부르고 비용이 듭니다`
    : "키 없음 — 도우미는 'AI 도우미 준비 중', /api/plan/은 503 not_configured";
  const rel = path.relative(ROOT, out);
  console.log(`http://${opt.host}:${server.address().port}/  ·  ${rel && !rel.startsWith("..") ? rel : out}  ·  /api/chat/·/api/plan/: ${key}`);
  return null;   // serving
}

if (process.argv[1] && path.resolve(process.argv[1]) === fileURLToPath(import.meta.url)) {
  main().then((code) => { if (code !== null) process.exit(code); }, (err) => {
    console.error(`중단: ${err?.code || err?.name || "error"} ${err?.message || ""}`.trim());
    process.exit(1);
  });
}
