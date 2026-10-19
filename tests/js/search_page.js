/* The site search (templates/assets/search.js) run in Node without a browser: just the page parts search.js reads
   (form[data-search] with its data attributes and input, [data-results], [data-directory], [data-none-help],
   [data-empty-art]) and fetch answering the index rows. search(q) loads /search/?q=… afresh and resolves with what
   the page shows: the results' HTML, the rows' names in order, the count line, the '함께 찾은 말' line, the
   [data-more] button's text and click(event) (the results' click handler). session() answers many queries from one
   page (the before/after measure over a whole index). Used by tests/js/search.test.js. */
import { readFileSync } from "node:fs";
import vm from "node:vm";

const SEARCH_JS = readFileSync(new URL("../../templates/assets/search.js", import.meta.url), "utf8");

function el(attrs = {}) {
  const ev = {};
  return {
    attrs, hidden: false, innerHTML: "", value: "",
    getAttribute(k) { return k in this.attrs ? this.attrs[k] : null; },
    setAttribute(k, v) { this.attrs[k] = String(v); },
    addEventListener(t, f) { (ev[t] = ev[t] || []).push(f); },
    fire(t, e) { (ev[t] || []).forEach((f) => f(e)); },
    querySelector() { return null; },
    focus() {},
  };
}

const text = (h) => h.replace(/<[^>]+>/g, "").replace(/&amp;/g, "&").replace(/&#39;/g, "'").replace(/&quot;/g, '"')
  .replace(/&lt;/g, "<").replace(/&gt;/g, ">");

export function read(html) {
  const names = [...html.matchAll(/<span class="res-nm">(.*?)<\/span>/g)].map((m) => text(m[1]));
  const one = (re) => { const m = html.match(re); return m ? text(m[1]) : ""; };
  return { html, names, count: one(/<p class="f-result">(.*?)<\/p>/), syn: one(/<p class="res-syn">(.*?)<\/p>/),
    more: one(/(<button[^>]*data-more[^>]*>.*?<\/button>)/) };
}

/* page({rows, concepts, region, planner, words, lang, script}) → {search(q)}; script: another search.js's text */
export function page({ rows, concepts = [], region = "", planner = "", words = null, lang = "ko", script = SEARCH_JS }) {
  let out = null;
  async function search(q) {
    const input = el({ name: "q" });
    const formAttrs = { "data-concepts": JSON.stringify(concepts), "data-region": region };
    if (planner) formAttrs["data-planner"] = planner;
    if (words) formAttrs["data-words"] = JSON.stringify(words);
    const form = el(formAttrs);
    form.querySelector = (s) => (/input/.test(s) ? input : null);
    out = el();
    let clickMore = null;
    out.addEventListener = (t, f) => { if (t === "click") clickMore = f; };
    const dir = el(), help = el(), art = el();
    const nodes = { "[data-search]": form, "[data-results]": out, "[data-directory]": dir, "[data-none-help]": help,
      "[data-empty-art]": art };
    const document = { querySelector: (s) => nodes[s] || null, getElementById: () => null,
      documentElement: { lang, classList: { remove() {}, add() {} } } };
    let done;
    const settled = new Promise((r) => { done = r; });
    const fetch = () => Promise.resolve({ json: () => { setTimeout(done, 0); return Promise.resolve(JSON.parse(JSON.stringify(rows))); } });
    const ctx = { document, window: {}, fetch, setTimeout, clearTimeout, URLSearchParams, JSON, Math, String, Array, Object,
      RegExp, Promise, Infinity, encodeURIComponent, history: { replaceState() {} },
      location: { search: "?q=" + encodeURIComponent(q), pathname: "/search/" } };
    vm.runInNewContext(script, ctx);
    await settled;
    await new Promise((r) => setTimeout(r, 0));
    const shown = read(out.innerHTML);
    shown.dirHidden = dir.hidden;
    shown.click = (target) => clickMore && clickMore(target);
    shown.out = out;
    shown.input = input;
    shown.form = form;
    return shown;
  }
  // one page for many queries: each typed and sent (the form's submit), answered from the index loaded once
  async function session() {
    const first = await search("\u0000");
    const input = first.input, form = first.form;
    return {
      async ask(q) {
        input.value = q;
        form.fire("submit", { preventDefault() {} });
        for (let i = 0; i < 3; i++) await new Promise((r) => setTimeout(r, 0));
        return read(out.innerHTML);
      },
    };
  }
  return { search, session };
}
