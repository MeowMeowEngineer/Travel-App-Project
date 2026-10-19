// The site assistant's knowledge: the three files pipeline/chat_index.py writes under public/chat/ (catalog.txt,
// docs.json, index.json), and what the two tools do with them — search_site (token match over every page),
// get_pages (the full text of up to six pages) — plus the check of every link an answer carries (fixLinks): a link
// to this site must name a page that exists (and is turned into the reader's language version when there is one),
// an outside link must be an address the site's data itself links to, a phone link must be a phone number.
//
// Page paths, ids, queries and addresses come from the model (and so, indirectly, from the user): they are only ever
// looked up in the loaded maps — which have no prototype, so 'constructor' or '__proto__' is simply not a page — and
// matched with fixed patterns; never used as a file path or turned into a RegExp. The files are read once, by name.
import { readFile } from "node:fs/promises";
import path from "node:path";

const table = (obj) => Object.assign(Object.create(null), obj && typeof obj === "object" ? obj : {});

// tokens(): pipeline/chat_index.py tokens() for queries — Hangul / kana / CJK runs as bigrams (one syllable alone as
// itself), Latin, Cyrillic and digit runs as words (one-letter Latin words dropped), NFKC, lower case. Keep in step.
const TOKEN_RX = /[가-힣]+|[\u3040-\u30ff\u3400-\u9fff]+|[a-z0-9\u00c0-\u024f\u0400-\u04ff]+/gu;
const WIDE_START = 0x3040;

export function tokens(text) {
  const t = String(text ?? "").normalize("NFKC").toLowerCase();
  const out = [];
  const seen = new Set();
  for (const [run] of t.matchAll(TOKEN_RX)) {
    let grams;
    if (run.codePointAt(0) >= WIDE_START) {
      const chars = [...run];
      grams = chars.length === 1 ? [run] : chars.slice(0, -1).map((c, i) => c + chars[i + 1]);
    } else {
      grams = run.length > 1 || /^\d+$/.test(run) ? [run] : [];
    }
    for (const g of grams) {
      if (!seen.has(g)) {
        seen.add(g);
        out.push(g);
      }
    }
  }
  return out;
}

const KIND_LABEL = {
  place: "장소", guide: "가이드", section: "가이드 본문", course: "코스", event: "행사", abroad: "해외 기사",
  video: "영상", page: "페이지",
};
// a video title matches many words, a guide section repeats its guide: both rank a little below a page of their own
const KIND_WEIGHT = { place: 1, guide: 1, course: 1, event: 1, page: 0.95, abroad: 0.9, section: 0.85, video: 0.6 };
const KIND_FILTER = { place: ["place"], guide: ["guide", "section"], course: ["course"], event: ["event"],
  abroad: ["abroad"], video: ["video"], page: ["page"] };
export const PAGE_LIMIT = 6;       // pages per get_pages call
export const DOC_CHARS = 6000;     // characters of one page in a get_pages result
export const SNIPPET_CHARS = 150;
export const QUERY_CHARS = 200;    // a search query is read up to this length (server.js refuses longer tool input)

function decode(s) {
  try {
    return decodeURI(s);
  } catch {
    return s;
  }
}

function normUrl(u) {
  // outside addresses compare without the scheme's case, a trailing slash, a 'www.' or a '#fragment' (the same page);
  // the link itself is always the address exactly as the data has it
  return String(u).trim().replace(/#.*$/, "").replace(/^https?:\/\//i, "").replace(/^www\./i, "").replace(/\/+$/, "")
    .toLowerCase();
}

/** A place's other names as docs.json gives them (a: [names]); [] for any other doc. */
function otherNames(d) {
  return Array.isArray(d && d.a) ? d.a.filter((x) => typeof x === "string" && x) : [];
}

/** A doc's title as the model reads it in search_site and get_pages results: with the place's other names, so a
 *  building and the museum in it read as one place ('구 ○○은행 지점 (다른 이름 ○○미술관)'). Link
 *  titles the reader sees stay the page's own title. */
function shownTitle(d) {
  const a = otherNames(d);
  return a.length ? `${d.t} (다른 이름 ${a.join(", ")})` : d.t;
}

export class Knowledge {
  constructor({ catalog, docs, index }) {
    this.catalog = String(catalog || "");
    this.site = String((docs && docs.site) || "").replace(/\/+$/, "");   // the public address (site.json site_url)
    this.docs = table(docs && docs.docs);
    this.alias = table(docs && docs.alias);
    // outside addresses the data links to, by their compared form → the address as the data has it (https first)
    this.ext = new Map();
    for (const u of (docs && docs.ext) || []) {
      const k = normUrl(u);
      const had = this.ext.get(k);
      if (!had || (/^http:/i.test(had) && /^https:/i.test(u))) this.ext.set(k, u);
    }
    this.keys = Object.keys(this.docs).sort();
    this.byTitle = new Map();
    for (const k of this.keys) {
      const t = this.docs[k].t;
      this.byTitle.set(t, this.byTitle.has(t) ? null : k);   // a title two pages share names neither
    }
    // a place's other names find its page too (a museum's name → the building it is in), unless a title or another
    // place's other name is the same
    const other = new Map();
    for (const k of this.keys) {
      for (const a of otherNames(this.docs[k])) other.set(a, other.has(a) ? null : k);
    }
    for (const [a, k] of other) if (k && !this.byTitle.has(a)) this.byTitle.set(a, k);
    const idx = (index && index.docs) || {};
    this.head = new Map();
    this.body = new Map();
    const df = new Map();
    for (const k of this.keys) {
      const [h = "", b = ""] = idx[k] || [];
      const hs = new Set(h ? h.split(" ") : tokens(this.docs[k].t));
      const bs = new Set(b ? b.split(" ") : []);
      this.head.set(k, hs);
      this.body.set(k, bs);
      for (const t of new Set([...hs, ...bs])) df.set(t, (df.get(t) || 0) + 1);
    }
    this.df = df;
  }

  idf(t) {
    return Math.log(1 + this.keys.length / (1 + (this.df.get(t) || 0)));
  }

  /** The doc key a page path, an English path, an absolute site URL or an exact page title refers to; '' if none. */
  keyFor(raw) {
    let s = decode(String(raw ?? "").trim()).normalize("NFC");
    if (!s) return "";
    if (this.site && s.startsWith(this.site)) {
      const rest = s.slice(this.site.length);
      if (rest && !"/?#".includes(rest[0])) return "";   // <site host>.example.com is another site
      s = rest || "/";
    }
    if (this.docs[s]) return s;
    if (this.byTitle.get(s)) return this.byTitle.get(s);
    let [base, frag = ""] = s.split("#");
    base = base.split("?")[0];
    if (base.startsWith("/") && !base.endsWith("/")) base += "/";
    const tries = [base, base.toLowerCase()];
    for (const b of tries) {
      const k = this.docs[b] ? b : this.alias[b] || "";
      if (!k) continue;
      if (frag && this.docs[`${k}#${frag}`]) return `${k}#${frag}`;
      return k;
    }
    return "";
  }

  /** The path a reader of `lang` should open for a doc key: the English page for every language but Korean when
   *  there is one (until the other language editions exist), else the Korean page; an article or a video opens the
   *  page that lists it. */
  pathFor(key, lang = "ko") {
    const d = this.docs[key];
    if (!d) return "";
    const [base, frag] = key.split("#");
    if (!base.startsWith("/")) return d.u || "/";
    if (lang !== "ko" && d.e) return frag && !d.e.includes("#") ? `${d.e}#${frag}` : d.e;
    return frag ? `${base}#${frag}` : base;
  }

  url(pathname) {
    return this.site + encodeURI(pathname);
  }

  /** The reader's page for the prompt, from the site's own data; '' when it is not a catalog page (the browser's text
   *  never reaches the prompt). */
  describePage(page) {
    const key = this.keyFor(page);
    if (!key) return "";
    const d = this.docs[key];
    return `${key} — ${shownTitle(d)} (${KIND_LABEL[d.k] || d.k})`;
  }

  /** search_site: pages ranked by matched query tokens (idf-weighted; a title / first-line match counts three times),
   *  scaled by the share of query tokens found and by kind. */
  search(query, { kind = "any", limit = 8 } = {}) {
    const q = tokens(String(query ?? "").slice(0, QUERY_CHARS));
    if (!q.length) return [];
    const kinds = KIND_FILTER[kind] || null;
    const hits = [];
    for (const k of this.keys) {
      const d = this.docs[k];
      if (kinds && !kinds.includes(d.k)) continue;
      const head = this.head.get(k);
      const body = this.body.get(k);
      let score = 0;
      let found = 0;
      for (const t of q) {
        if (head.has(t)) {
          score += 3 * this.idf(t);
          found += 1;
        } else if (body.has(t)) {
          score += this.idf(t);
          found += 1;
        }
      }
      if (!found) continue;
      score *= (0.4 + 0.6 * (found / q.length)) * (KIND_WEIGHT[d.k] ?? 1);
      hits.push({ key: k, score });
    }
    hits.sort((a, b) => b.score - a.score || (a.key < b.key ? -1 : 1));
    return hits.slice(0, limit).map((h) => ({ ...h, title: this.docs[h.key].t, kind: this.docs[h.key].k,
      snippet: this.snippet(h.key, q) }));
  }

  snippet(key, q) {
    const lines = this.docs[key].x.split("\n");
    let best = lines[0];
    let bestN = -1;
    for (const line of lines.slice(1)) {
      const ts = new Set(tokens(line));
      const n = q.filter((t) => ts.has(t)).length;
      if (n > bestN) {
        best = line;
        bestN = n;
      }
    }
    return best.length > SNIPPET_CHARS ? `${best.slice(0, SNIPPET_CHARS)}…` : best;
  }

  /** search_site's result as the model reads it. */
  searchText(query, opts = {}) {
    const hits = this.search(query, opts);
    if (!hits.length) return `No page of this site matches "${String(query ?? "").slice(0, QUERY_CHARS)}". Try other words (Korean place names or dishes), or say the site has no information on it.`;
    return hits.map((h, i) => {
      const d = this.docs[h.key];
      const where = h.key.startsWith("/") ? h.key : `${h.key} (on ${d.u || "/"})`;
      const en = opts.lang && opts.lang !== "ko" && d.e ? ` · English page ${d.e}` : "";
      return `${i + 1}. ${shownTitle(d)} — ${KIND_LABEL[d.k] || d.k} — ${where}${en}\n   ${h.snippet}`;
    }).join("\n");
  }

  /** get_pages: the full text of up to PAGE_LIMIT pages, each cut at DOC_CHARS, all of it within `budget`
   *  characters. Returns {text, keys, missing}. */
  pagesText(ids, { lang = "ko", budget = Infinity } = {}) {
    const keys = [];
    const missing = [];
    const parts = [];
    let left = budget;
    for (const raw of ids.slice(0, PAGE_LIMIT)) {
      const key = this.keyFor(raw);
      if (!key) {
        missing.push(String(raw).slice(0, 120));
        continue;
      }
      if (keys.includes(key)) continue;
      keys.push(key);
      const d = this.docs[key];
      const where = key.startsWith("/") ? key : `${key} (listed on ${d.u || "/"})`;
      const en = d.e ? ` · English page ${d.e}` : "";
      let text = d.x.length > DOC_CHARS ? `${d.x.slice(0, DOC_CHARS)}\n… (cut here: the rest is on the page)` : d.x;
      let part = `### ${shownTitle(d)}\nPath: ${where}${en}\n${text}`;
      if (part.length > left) {
        if (left < 400) {
          parts.push(`### ${shownTitle(d)}\n(not read: this question's reading limit is used up — answer with what you have)`);
          continue;
        }
        part = `${part.slice(0, left)}\n… (cut here: reading limit)`;
      }
      left -= part.length;
      parts.push(part);
    }
    if (ids.length > PAGE_LIMIT) parts.push(`(only the first ${PAGE_LIMIT} pages were read)`);
    if (missing.length) parts.push(`Not pages of this site: ${missing.join(", ")} — use paths from the catalog or search_site.`);
    return { text: parts.join("\n\n"), keys, missing };
  }

  titleOf(raw) {
    const key = this.keyFor(raw);
    return key ? this.docs[key].t : String(raw).slice(0, 40);
  }

  /** Every link in an answer, checked: {links: [{title, url, ext}] (site pages first seen first, then outside
   *  addresses; at most 8), fix: {as written: final address | null}}. null = not a page of this site, not an address
   *  the data links to: the reader sees its text without a link. An outside link becomes the address exactly as the
   *  data has it (the comparison ignores the scheme, 'www.', a trailing slash and case — the link never does). */
  fixLinks(text, lang = "ko") {
    const found = [];
    const md = /\[([^\]\n]{1,200})\]\(\s*<?([^)\s>]+)>?\s*\)/g;
    for (const m of String(text).matchAll(md)) found.push({ label: m[1].trim(), raw: m[2] });
    const bare = String(text).replace(md, " ");
    for (const m of bare.matchAll(/https?:\/\/[^\s<>()[\]"'`]+/g)) found.push({ label: "", raw: m[0].replace(/[.,;:!?。、]+$/u, "") });
    const fix = Object.create(null);
    const links = [];
    const seen = new Set();
    for (const { label, raw } of found) {
      if (raw in fix) continue;
      let url = null;
      let title = label;
      let ext = false;
      if (/^tel:\+?[\d-]{7,16}$/.test(raw)) {
        url = raw;
      } else if (raw.startsWith("/") || raw.startsWith(this.site)) {
        const key = this.keyFor(raw);
        if (key) {
          url = this.url(this.pathFor(key, lang));
          // Korean readers get the page's own title (a guide section: its heading); others keep the answer's words
          if (lang === "ko" || !label) title = this.docs[key].h || this.docs[key].t;
        }
      } else if (/^https?:\/\//i.test(raw) && this.ext.has(normUrl(raw))) {
        url = this.ext.get(normUrl(raw));
        ext = true;
        if (!title) title = url.replace(/^https?:\/\/(www\.)?/i, "").split("/")[0];
      }
      fix[raw] = url;
      if (url && !url.startsWith("tel:") && !seen.has(url) && links.length < 8) {
        seen.add(url);
        links.push({ title: title || url, url, ext });
      }
    }
    links.sort((a, b) => Number(a.ext) - Number(b.ext));
    return { links, fix };
  }
}

export async function loadKnowledge(dir) {
  const read = (name) => readFile(path.join(dir, name), "utf8");
  const [catalog, docs, index] = await Promise.all([read("catalog.txt"), read("docs.json"), read("index.json")]);
  return new Knowledge({ catalog, docs: JSON.parse(docs), index: JSON.parse(index) });
}

// The deployed function reads the files bundled from public/chat/ (vercel.json functions."api/chat.js".includeFiles);
// one load per instance.
let cached = null;
export function defaultKnowledge() {
  if (!cached) {
    cached = loadKnowledge(path.join(process.cwd(), "public", "chat")).catch((err) => {
      cached = null;
      throw err;
    });
  }
  return cached;
}
