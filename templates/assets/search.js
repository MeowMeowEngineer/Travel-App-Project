/* 군산 여행 — /search/: a static index (search/index.json, built with the site by pipeline/present.search_index)
   fetched on the first focus of the box, or at once when the page opens with ?q=. No server.
   Index rows: n name, a other names (course: its stops), m 대표 메뉴·취급 메뉴, g official designations ('군산맛집(2026,
   군산시 지정) · 모범음식점(군산시 지정)'), d 동 (or road), r 권역, t type, k kind, p path, s the status line as text.
   Ranking: name (exact, prefix, inside) > other names > menu > designation > 동·권역·type. Spaces and ·-()[]|, are
   ignored when matching. A row says why it matched when it was not the name ("메뉴: 짜장면", "다른 이름: …",
   "경유: …", "지정: 모범음식점(군산시 지정)").

   MARKUP
     form[data-search]          action="/search/"; data-index overrides the index URL; its input[name=q]
     [data-results]             results go here (aria-live="polite" in the markup)
     [data-directory]           the no-JS answer (가나다 directory): hidden while results are shown
   Result markup (style hooks): p.f-result (count line), section.res-g > h2 (+ .tn count) > ol > li > a >
   span.res-nm (with <mark>), span.res-meta, span.res-why, span.res-st; p.res-none when nothing matches.
   Without JS the form reloads this page and the directory answers. */
(function () {
  "use strict";
  var doc = document, form = doc.querySelector("[data-search]"), out = doc.querySelector("[data-results]");
  if (!form || !out) return;
  var input = form.querySelector('input[name="q"]') || form.querySelector("input");
  var dir = doc.querySelector("[data-directory]");
  var emptyArt = doc.querySelector("[data-empty-art]");   // the small picture shown with no result
  var KIND = { attraction: "관광지", stay: "숙소", food: "음식점", course: "코스", guide: "가이드", event: "행사" };
  var ORDER = ["attraction", "food", "stay", "course", "guide", "event"];
  var PLACES = ["attraction", "stay", "food"];
  var STRIP = /[\s·\-()（）\[\]|,]/g, LIMIT = 80;
  var index = null, loading = null;

  function norm(s) { return String(s || "").toLowerCase().replace(STRIP, ""); }
  function load() {
    if (index) return Promise.resolve(index);
    if (!loading) {
      loading = fetch(form.getAttribute("data-index") || "/search/index.json")
        .then(function (r) { return r.json(); })
        .then(function (rows) {
          index = rows.map(function (row) {
            row._n = norm(row.n); row._a = norm(row.a); row._m = norm(row.m); row._g = norm(row.g);
            row._d = norm([row.d, row.r, row.t].join(" "));
            return row;
          });
          return index;
        })
        .catch(function () { loading = null; return []; });
    }
    return loading;
  }
  function esc(s) {
    return String(s || "").replace(/[&<>"']/g, function (c) { return { "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]; });
  }
  // highlight the matched run once (not every syllable of the query), mapping normalised positions back to the text
  function mark(text, q) {
    var s = String(text || ""), pos = [], flat = "";
    for (var i = 0; i < s.length; i++) {
      var c = s[i].toLowerCase();
      if (!c.match(STRIP)) { pos.push(i); flat += c; }
    }
    var at = q ? flat.indexOf(q) : -1;
    if (at < 0) return esc(s);
    var a = pos[at], b = pos[at + q.length - 1] + 1;
    return esc(s.slice(0, a)) + "<mark>" + esc(s.slice(a, b)) + "</mark>" + esc(s.slice(b));
  }
  // the dish, stop or other name that matched, shown whole
  function piece(list, sep, q) {
    var parts = String(list || "").split(sep);
    for (var i = 0; i < parts.length; i++) if (norm(parts[i]).indexOf(q) > -1) return parts[i].trim();
    return "";
  }
  function josaWa(word) {
    var c = String(word).trim().slice(-1).charCodeAt(0) - 0xac00;
    return c >= 0 && c < 11172 && c % 28 ? "과" : "와";
  }
  function score(row, q) {
    if (row._n === q) return [0, ""];
    if (row._n.indexOf(q) === 0) return [1, ""];
    if (row._n.indexOf(q) > -1) return [2, ""];
    if (row._a.indexOf(q) > -1) {
      if (row.k === "course") return [3, "경유: " + piece(row.a, /\s+/, q)];
      return [3, row.k === "guide" ? "" : "다른 이름: " + piece(row.a, /\s+/, q)];
    }
    if (row.m && row._m.indexOf(q) > -1) return [4, "메뉴: " + piece(row.m, /\s*[,\/·]\s*/, q)];
    if (row.g && row._g.indexOf(q) > -1) return [5, "지정: " + piece(row.g, /\s+·\s+/, q)];
    if (row._d.indexOf(q) > -1) return [6, ""];
    return null;
  }
  function render(raw) {
    var q = norm(raw);
    if (!q) { out.innerHTML = ""; if (dir) dir.hidden = false; if (emptyArt) emptyArt.hidden = true; return; }
    load().then(function (rows) {
      if (norm(input.value) !== q) return; // a newer query is on its way
      var hits = [];
      rows.forEach(function (row) { var s = score(row, q); if (s) hits.push([s[0], row, s[1]]); });
      hits.sort(function (x, y) { return x[0] - y[0] || x[1].n.localeCompare(y[1].n, "ko"); });
      if (emptyArt) emptyArt.hidden = hits.length > 0;
      if (!hits.length) {
        if (dir) dir.hidden = false;
        out.innerHTML = '<p class="res-none">‘' + esc(raw.trim()) + "’" + josaWa(raw) + " 맞는 곳이 없습니다. 아래 가나다 목록에서 찾아 보세요.</p>";
        return;
      }
      if (dir) dir.hidden = true;
      var shown = hits.slice(0, LIMIT), groups = {};
      shown.forEach(function (h) { (groups[h[1].k] = groups[h[1].k] || []).push(h); });
      var counts = ORDER.filter(function (k) { return groups[k]; }).map(function (k) { return KIND[k] + " " + groups[k].length; });
      var places = hits.every(function (h) { return PLACES.indexOf(h[1].k) > -1; });
      var unit = places ? "곳" : "건";
      // '‘짜장면’ 12곳', or with several kinds '‘선유도’ 25건 · 관광지 10 · 숙소 3 · 코스 12' (the kind counts only
      // when there is more than one kind; '중 20건' when the list is cut at LIMIT)
      var html = '<p class="f-result">‘' + esc(raw.trim()) + "’ " + hits.length + unit +
        (hits.length > LIMIT ? " 중 " + LIMIT + unit : "") + (counts.length > 1 ? " · " + esc(counts.join(" · ")) : "") + "</p>";
      ORDER.forEach(function (k) {
        if (!groups[k]) return;
        html += '<section class="res-g"><h2>' + KIND[k] + ' <span class="tn">' + groups[k].length + "</span></h2><ol>";
        groups[k].forEach(function (h) {
          var row = h[1], meta = [row.t, row.d, row.r].filter(Boolean);
          html += '<li><a href="' + esc(row.p) + '"><span class="res-nm">' + mark(row.n, q) + "</span>" +
            '<span class="res-meta">' + esc(meta.join(" · ")) + "</span>" +
            (h[2] ? '<span class="res-why">' + mark(h[2], q) + "</span>" : "") +
            (row.s ? '<span class="res-st">' + esc(row.s) + "</span>" : "") + "</a></li>";
        });
        html += "</ol></section>";
      });
      out.innerHTML = html;
    });
  }
  function remember(value) {
    try { history.replaceState(null, "", value ? "?q=" + encodeURIComponent(value) : location.pathname); } catch (e) { /* file:// */ }
  }
  var timer = null;
  input.addEventListener("focus", load, { once: true });
  input.addEventListener("input", function () {
    clearTimeout(timer);
    timer = setTimeout(function () { render(input.value); remember(input.value.trim()); }, 120);
  });
  form.addEventListener("submit", function (ev) {
    ev.preventDefault();
    render(input.value);
    remember(input.value.trim());
  });
  var q0 = new URLSearchParams(location.search).get("q");
  if (q0) { input.value = q0; render(q0); }
})();
