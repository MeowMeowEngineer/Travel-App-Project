// 로컬에서 사이트 도우미(챗봇)를 실제 키로 시험하는 서버 — Vercel 없이.
// 빌드 폴더(기본 dist-preview)를 그대로 보여 주고, /api/chat/은 Vercel 함수와 같은 처리기(chatbot/server.js)가
// 그 폴더의 chat/(빌드가 쓴 지식 파일·site.json)을 읽어 답한다. 키는 환경 변수 ANTHROPIC_API_KEY에서만 읽고 출력하지 않는다.
//
//   python -m pipeline.build --data data/incheon --out dist-preview --mode preview
//   ANTHROPIC_API_KEY=… node tools/chat_dev.mjs                      # http://127.0.0.1:8787
//   node --env-file=.env tools/chat_dev.mjs --dir public --port 8787  # 키를 .env에 둔 경우(Node가 읽는다)
//   npm run chat:dev -- --dir dist-preview
//
// 키가 없으면 페이지는 키 없는 배포와 똑같이 'AI 도우미 준비 중'과 사이트 검색을 보인다. --host 0.0.0.0이면 같은
// 와이파이의 휴대폰에서도 열린다(키로 답하는 주소가 그 망에 열리므로 시험할 때만).
import { createReadStream, existsSync, statSync } from "node:fs";
import { createServer } from "node:http";
import path from "node:path";
import { Readable } from "node:stream";
import { fileURLToPath } from "node:url";

import { loadKnowledge } from "../chatbot/knowledge.js";
import { apiKey, createHandler } from "../chatbot/server.js";
import { loadSite } from "../chatbot/site.js";

const TYPES = {
  ".html": "text/html; charset=utf-8", ".css": "text/css; charset=utf-8", ".js": "text/javascript; charset=utf-8",
  ".mjs": "text/javascript; charset=utf-8", ".json": "application/json; charset=utf-8", ".txt": "text/plain; charset=utf-8",
  ".xml": "application/xml; charset=utf-8", ".svg": "image/svg+xml", ".png": "image/png", ".jpg": "image/jpeg",
  ".jpeg": "image/jpeg", ".webp": "image/webp", ".avif": "image/avif", ".ico": "image/x-icon", ".woff2": "font/woff2",
  ".webmanifest": "application/manifest+json",
};

/** The handler the Vercel function uses, reading the knowledge and the site from <dir>/chat/. */
export function devHandler(dir, deps = {}) {
  const chat = path.join(dir, "chat");
  let kb = null;
  const knowledge = () => {
    if (!kb) kb = loadKnowledge(chat).catch((err) => { kb = null; throw err; });
    return kb;
  };
  return createHandler({ knowledge, site: loadSite(chat), ...deps });
}

/** The file a path names inside dir (a folder: its index.html), or null — never anything outside dir. */
function fileFor(dir, pathname) {
  let rel;
  try {
    rel = decodeURIComponent(pathname);
  } catch {
    return null;
  }
  const full = path.resolve(dir, `.${path.posix.normalize(`/${rel}`)}`);
  if (full !== path.resolve(dir) && !full.startsWith(path.resolve(dir) + path.sep)) return null;
  if (!existsSync(full)) return null;
  const st = statSync(full);
  if (st.isDirectory()) return existsSync(path.join(full, "index.html")) ? { dir: true, file: path.join(full, "index.html") } : null;
  return st.isFile() ? { dir: false, file: full } : null;
}

/** An http.Server: /api/chat/ (and /api/chat) through `handler` (a fetch-style function), every other path a file of
 *  dir — a folder without its trailing slash is redirected to it, as on Vercel (trailingSlash: true). */
export function createDevServer({ dir, handler }) {
  return createServer(async (req, res) => {
    const url = new URL(req.url, `http://${req.headers.host || "127.0.0.1"}`);
    if (url.pathname === "/api/chat/" || url.pathname === "/api/chat") {
      const ac = new AbortController();
      res.on("close", () => { if (!res.writableFinished) ac.abort(); });
      const hasBody = req.method !== "GET" && req.method !== "HEAD";
      const request = new Request(url, { method: req.method, headers: req.headers, signal: ac.signal,
        body: hasBody ? Readable.toWeb(req) : undefined, duplex: hasBody ? "half" : undefined });
      let out;
      try {
        out = await handler(request);
      } catch (err) {
        res.writeHead(500, { "content-type": "text/plain; charset=utf-8" }).end(String(err?.name || "error"));
        return;
      }
      res.writeHead(out.status, Object.fromEntries(out.headers));
      if (!out.body) {
        res.end();
        return;
      }
      try {
        for await (const chunk of out.body) res.write(chunk);
      } catch { /* the reader went away */ }
      res.end();
      return;
    }
    if (req.method !== "GET" && req.method !== "HEAD") {
      res.writeHead(405, { allow: "GET, HEAD" }).end();
      return;
    }
    const hit = fileFor(dir, url.pathname);
    if (!hit) {
      const missing = fileFor(dir, "/404.html");
      res.writeHead(404, { "content-type": TYPES[".html"] });
      if (missing && req.method === "GET") createReadStream(missing.file).pipe(res);
      else res.end();
      return;
    }
    if (hit.dir && !url.pathname.endsWith("/")) {
      res.writeHead(308, { location: `${url.pathname}/${url.search}` }).end();
      return;
    }
    res.writeHead(200, { "content-type": TYPES[path.extname(hit.file).toLowerCase()] || "application/octet-stream",
      "cache-control": "no-cache" });
    if (req.method === "HEAD") res.end();
    else createReadStream(hit.file).pipe(res);
  });
}

function args(argv) {
  const out = { dir: "dist-preview", port: 8787, host: "127.0.0.1" };
  for (let i = 0; i < argv.length; i += 1) {
    const [k, v] = [argv[i], argv[i + 1]];
    if (k === "--dir") out.dir = v;
    else if (k === "--port") out.port = Number(v);
    else if (k === "--host") out.host = v;
    else continue;
    i += 1;
  }
  return out;
}

if (process.argv[1] && path.resolve(process.argv[1]) === fileURLToPath(import.meta.url)) {
  const opt = args(process.argv.slice(2));
  const dir = path.resolve(opt.dir);
  if (!existsSync(path.join(dir, "chat", "docs.json"))) {
    console.error(`${dir}/chat/ 이 없습니다. 먼저 빌드하세요: python -m pipeline.build --data data/incheon --out ${opt.dir} --mode preview`);
    process.exit(2);
  }
  const server = createDevServer({ dir, handler: devHandler(dir) });
  server.listen(opt.port, opt.host, () => {
    const key = apiKey(process.env) ? "키 있음(ANTHROPIC_API_KEY) — 질문하면 실제 API를 부르고 비용이 듭니다"
      : "키 없음 — 페이지는 'AI 도우미 준비 중' 상태로 보입니다";
    const rel = path.relative(process.cwd(), dir);
    console.log(`http://${opt.host}:${server.address().port}/  ·  ${rel && !rel.startsWith("..") ? rel : dir}  ·  챗봇: ${key}`);
  });
}
