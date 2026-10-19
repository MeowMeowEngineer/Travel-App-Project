// The site this assistant answers for: public/chat/site.json, written by the build (pipeline/chat_index.py export,
// from data/<region>/site.json) next to the knowledge files and bundled with the function the same way
// (vercel.json includeFiles public/chat/**). Nothing city-specific is written in chatbot/*.js: the public address
// (the origin pages ask from, the address its links start with), the site's name, the city's name in each language
// (the assistant's name and its 'travel in …' scope) and any further origins the owner allows (site.json
// city.chat.origins: a previous address, the project's Vercel production alias).
import { readFileSync } from "node:fs";
import path from "node:path";

const clean = (v) => String(v ?? "").trim();

/** {url, name, city: {lang: name}, origins: [https origins], hubs: {key: name}} from the file's object; unknown or
 *  odd values are dropped (an origin must be a plain https://host address). */
export function siteFrom(raw) {
  const o = raw && typeof raw === "object" ? raw : {};
  const url = clean(o.url).replace(/\/+$/, "");
  const city = {};
  for (const [k, v] of Object.entries(o.city && typeof o.city === "object" ? o.city : {})) {
    if (clean(v)) city[k] = clean(v);
  }
  const origins = (Array.isArray(o.origins) ? o.origins : []).map(clean)
    .filter((u) => /^https:\/\/[a-z0-9-]+(\.[a-z0-9-]+)+$/.test(u));
  // the AI course planner's start and end points ({key: name}; site.json city.plan.hubs): a key of plain letters
  const hubs = {};
  for (const [k, v] of Object.entries(o.hubs && typeof o.hubs === "object" ? o.hubs : {})) {
    if (/^[a-z][a-z0-9_]{0,23}$/.test(k) && clean(v)) hubs[k] = clean(v);
  }
  return { url: /^https?:\/\/[^\s/]+$/.test(url) ? url : "", name: clean(o.name), city, origins, hubs };
}

/** The city's name in `lang`, else in Korean or English, else '' (the wording then leaves the name out). */
export function cityName(site, lang = "ko") {
  const c = (site && site.city) || {};
  return c[lang] || (lang === "ko" ? "" : c.en) || c.ko || "";
}

/** site.json from `dir` (default: public/chat under the working directory, where the deployed function finds the
 *  bundled files); an empty site when it is missing or unreadable — then only this deployment's own addresses may ask. */
export function loadSite(dir = path.join(process.cwd(), "public", "chat")) {
  try {
    return siteFrom(JSON.parse(readFileSync(path.join(dir, "site.json"), "utf8")));
  } catch {
    return siteFrom({});
  }
}
