/* Maps (progressive enhancement; attached by site.js when the page has a map box). Kakao Maps JavaScript
   SDK (map provider: owner decision 2026-10-14; the key is site.json kakao_js_key, which the build writes into each box
   as data-kakao-sdk) is fetched only when a box comes within 400px of the viewport, or when a folded map opens
   (gs:showmap), and never before the window 'load' event: nothing of it is on the first screen's critical path, and
   a page without a map box loads neither this file nor the SDK. Markers, labels and controls are the site's own
   (CustomOverlay elements styled by css/30-info.css); Kakao draws its own logo in the map's corner. Scroll-wheel zoom
   off; 44px zoom buttons; the map itself takes the focus (arrow keys move it, + and − zoom). Every map has a text
   equivalent on the page; without JS the box is not shown (css/10-base.css), and when the SDK fails (a page served
   from a domain the key is not registered for answers HTTP 401) the box keeps its text with the failure line.

   MARKUP
     <div class="map" data-map='JSON' data-kakao-sdk="https://dapi.kakao.com/v2/maps/sdk.js?appkey=…&autoload=false"
          role="region" aria-label="…">                   (data-points='JSON' is accepted too)
       optional <p class="map-off">…</p> inside: its own text says the page lists the same places (what a reader
       without the map gets); 'loading' once drawing starts, replaced by the map, the failure line if the SDK fails
     JSON shapes (pipeline/present.py and build.map_points make them):
       [{lat, lng, name, url, kind?, n?}, …]      a list of places; with data-numbered="1" a numbered route
       {self: {lat, lng, name}, near: [{lat, lng, name, url, d, kind}], anchors: [{lat, lng, label}],
        radius?: metres}                          a place (or event) with its neighbours / a radius circle
       {course: [{lat, lng, name, url, n, extra?}]}   numbered stops (n = the stop list's number; ui.coursemap)
                                                  joined in order by a thin straight line; every stop keeps its
                                                  own marker (touching ones pushed apart, a hairline to the true
                                                  point); opens on the most stops that stand alone, the others
                                                  pointed at from the edge; '전체 보기' frames all (see COURSE
                                                  MAPS below); the blue progress line is drawn for course.js
                                                  (reg.progressTo)
       {guide: [...], route: bool}                numbered places (id: the place, gs:focus), joined only when route is true
       {list: [{lat, lng, name, url, id, kind, r}]}   a list page's places (id = the row's id: row ↔ marker); only the
                                                  places the list's filter keeps (window.GSFilter / gs:filter), framed
                                                  on their main body (body(): a group a sea away is left to a
                                                  '지도 밖 n곳도 보기' control that frames them all); beside the shown
                                                  list in the box's part in the window, framed again as the page
                                                  scrolls more of it in (until the reader moves the map); each marker a
                                                  link named by the place (quiet beside the shown list, in the tab
                                                  order where the list is hidden: phones' 지도)
       {all: [...same...], anchor_pts: [{name, n, geo}]}   the map page: 권역 labels, '먼 섬' edge control; a chosen 권역
                                                  (gs:region) framed on its main body as a list's filter
       {anchors: [{lat, lng, name, n, url, place}]}  the home: the 권역 anchors labelled with their counts, each a
                                                  link to its region on /map/ (present.home_vm region_map)
     Every box gets data-lenis-prevent (wheel and touch on the map stay the map's).

   ZOOM: Kakao levels (1 = street, 14 = the whole country; one level is twice the scale; level 3 ≈ 1 m per pixel, a
   web-map zoom z ≈ level 20 − z): street-level stops 4, a place 5. The zoom buttons and keys zoom on the middle of the
   part of the box in the window (setLevel's anchor), not on the middle of a box partly below it.

   API: window.GSMaps (registry: {el, map (the kakao.maps.Map), g (the adapter below), markers, data, frame, line,
   progress, lls, activeN, paint, showHome, showAround, whenIdle, progressTo}): a numbered map marks stop activeN .on
   and the earlier ones .past when paint() is called; a course map's showHome(fly) returns to its first view and
   showAround(n) moves to stop n when it is out of view (course.js; true when it moves); whenIdle(fn) runs fn once the
   map has stopped moving and returns a function that cancels it; progressTo(from, n) draws the blue line through stop
   n (the part after stop `from` grows along the straight lines unless motion is reduced). Numbered markers are links
   (Enter or Space opens them). Every built map dispatches gs:mapready {detail: registry entry} (bubbles to document).
   Listens to gs:hl, gs:filter, gs:focus, gs:region, gs:showmap (see site.js). window.GSMapStart(el) builds a box
   a script added after load (plan.js). */
(function () {
  "use strict";
  var doc = document, win = window, maps = win.GSMaps = win.GSMaps || [], loading = null, K = null;
  var reduce = win.matchMedia("(prefers-reduced-motion: reduce)").matches;
  var INK = "#1d1d1f", BLUE = "#0071e3";   // the Apple skin: ink for lines, the one blue for progress
  var MINLV = 1, MAXLV = 14;
  // the few words this file writes (zoom buttons, 'whole course', the off-map chips, the failure line): Korean on
  // Korean pages, English on the other versions — whose map boxes may carry their own (data-words, en/_en.html.j2)
  var EN = !/^ko/i.test(doc.documentElement.lang || "ko");
  var W = (function () {
    var el = doc.querySelector(".map[data-words]");
    try { return el ? JSON.parse(el.getAttribute("data-words")) || {} : {}; } catch (e) { return {}; }
  })();

  // ------------------------------------------------------------ the SDK: once per page, after 'load'
  function afterLoad(fn) { if (doc.readyState === "complete") fn(); else win.addEventListener("load", fn); }
  function load(el) {
    if (K) return Promise.resolve();
    if (loading) return loading;
    var src = el.getAttribute("data-kakao-sdk") || (doc.querySelector(".map[data-kakao-sdk]") || { getAttribute: function () { return ""; } }).getAttribute("data-kakao-sdk");
    if (!src) return Promise.reject(new Error("no Kakao SDK"));
    loading = new Promise(function (res, rej) {
      var t = setTimeout(rej, 20000); // the SDK fetches its main file inside kakao.maps.load: never wait for ever
      var ready = function () { kakao.maps.load(function () { clearTimeout(t); K = kakao.maps; res(); }); };
      if (win.kakao && win.kakao.maps && win.kakao.maps.load) { ready(); return; }
      var s = doc.createElement("script");
      s.src = src;
      s.onload = function () { if (win.kakao && win.kakao.maps && win.kakao.maps.load) ready(); else { clearTimeout(t); rej(); } };
      s.onerror = function () { clearTimeout(t); rej(); };
      doc.head.appendChild(s);
    });
    loading.catch(function () { loading = null; });
    return loading;
  }

  // ------------------------------------------------------------ small helpers
  function Pt(x, y) { this.x = x; this.y = y; }
  Pt.prototype.distanceTo = function (p) { var dx = p.x - this.x, dy = p.y - this.y; return Math.sqrt(dx * dx + dy * dy); };
  function pt(x, y) { return new Pt(x, y); }
  function LL(a) { return new K.LatLng(a[0], a[1]); }
  function clampLv(lv) { return Math.max(MINLV, Math.min(MAXLV, Math.round(lv))); }
  function esc(t) { return String(t).replace(/[&<>"]/g, function (c) { return { "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" }[c]; }); }
  function div(cls, html) { var n = doc.createElement("div"); n.className = cls; if (html != null) n.innerHTML = html; return n; }
  // a marker: an outer element (a link when it goes somewhere) round the styled dot (inner: .mk-num, .mk-dot …); the
  // state classes (.on .past .dim .mk-hl) go on the inner element
  function pin(cls, html, url, label, quiet) {
    var a = doc.createElement(url ? "a" : "span");
    a.className = "mk-a";
    if (url) a.href = url;
    if (label && !quiet) a.title = label;
    if (label && url) a.setAttribute("aria-label", label);
    // a list map's dots (quiet) are named links too (the place's name; the map's tooltip shows it on hover and focus).
    // Beside the shown list they start out of the tab order and hidden from screen readers — the rows are the same
    // links — and listQuiet() lets them in while the list is not shown (phones' 지도 view)
    if (quiet) { a.tabIndex = -1; a.setAttribute("aria-hidden", "true"); a.className += " mk-li"; }
    else if (!url) a.setAttribute("aria-hidden", "true");
    if (url) a.addEventListener("keydown", function (e) { if (e.key === " ") { e.preventDefault(); location.href = url; } });
    a.appendChild(div(cls, html));
    return a;
  }
  // a place's marker by its kind: 관광지 dot, 숙소 ring, 음식점 square, 카페·디저트 hollow square, 쇼핑 bar (the map page's
  // toggles draw the same shapes, css .mk-a/s/f/c/h)
  var KIND_MK = { stay: "mk-ring", food: "mk-sq", cafe: "mk-sqr", shopping: "mk-bar" };
  function kindPin(kind, url, label, quiet) { return pin(KIND_MK[kind] || "mk-dot", "", url, label, quiet); }
  function textW(t) { return Math.min(280, 13.4 * String(t).length + 8); }
  function idOf(p) { return p.id || decodeURIComponent((p.url || "").split("/")[2] || ""); }
  // the middle of the points (outliers stay on the map, one zoom-out away)
  function robust(pts, f) {
    if (pts.length < 8) return pts;
    var la = pts.map(function (p) { return p[0]; }).sort(function (a, b) { return a - b; });
    var ln = pts.map(function (p) { return p[1]; }).sort(function (a, b) { return a - b; });
    var q = function (a, x) { return a[Math.min(a.length - 1, Math.max(0, Math.round((a.length - 1) * x)))]; };
    return [[q(la, f), q(ln, f)], [q(la, 1 - f), q(ln, 1 - f)]];
  }
  // a selection's main body: its places joined by steps of at most GAP_M (the groups that hold a quarter of them or
  // more; all of them when there are fewer than 8, or when those groups hold less than half). A group a sea away is
  // left to the '지도 밖' control (rest) — robust() cannot leave it: 백령도·대청도 are 15% of 옹진 섬, 160 km from
  // 영흥도, and robust(pts, 0.08) kept them (QA 2026-10-19 QA-41: 옹진 섬 opened at 64 km on a phone, 32 km at 1440).
  // In every other 권역 the widest gap between a group of places and the rest is 7 km (a few stray coordinates
  // thousands of km off aside); 옹진's island groups lie 25–80 km apart.
  var GAP_M = 20000;
  function body(lls) {
    var n = lls.length;
    if (n < 8) return lls;
    var lat = lls.map(function (a) { return a[0]; }).sort(function (a, b) { return a - b; })[n >> 1];
    var kx = 111320 * Math.cos(lat * Math.PI / 180), xy = lls.map(function (a) { return [a[1] * kx, a[0] * 111320]; });
    var up = lls.map(function (a, i) { return i; }), cell = {};
    var find = function (i) { while (up[i] !== i) { up[i] = up[up[i]]; i = up[i]; } return i; };
    xy.forEach(function (p, i) { // grid cells GAP_M wide: a point meets only the points in its own and the 8 cells round it
      var cx = Math.floor(p[0] / GAP_M), cy = Math.floor(p[1] / GAP_M);
      for (var dx = -1; dx <= 1; dx++) for (var dy = -1; dy <= 1; dy++) (cell[(cx + dx) + "," + (cy + dy)] || []).forEach(function (j) {
        var ex = xy[j][0] - p[0], ey = xy[j][1] - p[1];
        if (ex * ex + ey * ey <= GAP_M * GAP_M) up[find(i)] = find(j);
      });
      (cell[cx + "," + cy] = cell[cx + "," + cy] || []).push(i);
    });
    var size = {};
    lls.forEach(function (a, i) { var k = find(i); size[k] = (size[k] || 0) + 1; });
    var keep = lls.filter(function (a, i) { return size[find(i)] * 4 >= n; });
    return keep.length * 2 >= n ? keep : lls;
  }
  // a tall sticky map whose lower part is below the window at first view: frame the points in the visible part
  function hiddenBelow(el) {
    var r = el.getBoundingClientRect(), vh = win.innerHeight;
    return r.top < vh && r.bottom > vh ? Math.min(r.height - 160, r.bottom - vh) : 0;
  }
  // b framed in the box less its lower hb px (the part below the window); top: a larger top padding
  function frameIn(g, b, pad, minLv, hb, top) {
    if (b.length === 1) return { c: b[0], lv: 5 };
    return g.fitView(b, [Math.max(pad, top || 0), pad, pad + hb, pad], minLv);
  }
  function visibleView(g, b, pad, minLv) { return frameIn(g, b, pad, minLv || 2, Math.max(0, hiddenBelow(g.el))); }
  function fitVisible(g, b, pad, minLv) { var v = visibleView(g, b, pad, minLv); g.view(v.c, v.lv, false); }
  function visible(el) { return el.offsetParent !== null && el.getBoundingClientRect().height > 0; }
  // the places of lls outside view v's part above hb (container pixels worked out on the plane: no map needed)
  function outside(g, v, lls, hb) {
    var sz = g.size(), c = g.project(v.c, v.lv);
    return lls.filter(function (a) {
      var p = g.project(a, v.lv), x = p.x - c.x + sz.x / 2, y = p.y - c.y + sz.y / 2;
      return x < 0 || y < 0 || x > sz.x || y > sz.y - hb;
    }).length;
  }
  // a selection (a list's filter, a 권역 on /map/) framed on its main body (all of it once the '지도 밖' control has
  // been pressed: r.wide, until the selection changes)
  function selView(r, sel, pad, minLv, hb) {
    var key = sel.join(";");
    if (key !== r.selKey) { r.selKey = key; r.wide = false; }
    var b = r.wide ? sel : body(sel), v = frameIn(r.g, b, pad, minLv, hb), n = b.length < sel.length ? outside(r.g, v, sel, hb) : 0;
    if (n && n * 10 >= sel.length) { // the control's row (top right, 44px) kept clear of the markers
      v = frameIn(r.g, b, pad, minLv, hb, 64);
      n = outside(r.g, v, sel, hb);
    }
    rest(r, n, sel.length);
    return v;
  }
  // '지도 밖 n곳도 보기' (top right, the far-ctl look): the places the main body leaves out of the view, when they are a
  // tenth of the selection or more (a stray coordinate or two stay one zoom-out away, as before); a press frames them
  // all. Hidden otherwise
  function rest(r, n, of) {
    if (!n || n * 10 < of) { if (r.restBtn) r.restBtn.hidden = true; return; }
    if (!r.restBtn) {
      var b = r.restBtn = doc.createElement("button");
      b.type = "button";
      b.className = "far-ctl map-all map-rest";
      b.addEventListener("click", function () {
        r.wide = true;
        b.hidden = true;
        if (r.data.list) { var v = listView(r); r.g.view(v.c, v.lv, true); } else if (lastRegion) applyRegion(r, lastRegion);
      });
      r.g.ctl.tr.appendChild(b);
    }
    r.restBtn.textContent = (W.rest || (EN ? "Show the {n} off the map" : "지도 밖 {n}곳도 보기")).replace("{n}", n);
    r.restBtn.hidden = false;
  }
  function besideList() { return Array.prototype.some.call(doc.querySelectorAll("[data-ledger]"), visible); }
  // a list map's filter (site.js keeps the list's shown row ids in window.GSFilter and sends gs:filter): the kept
  // points ({keep: {id: 1}, lls}), or null when every point is kept (the map then shows its whole frame)
  function picked(list, ids) {
    if (!ids) return null;
    var keep = {}, lls = [];
    ids.forEach(function (id) { keep[id] = 1; });
    list.forEach(function (p) { if (keep[idOf(p)]) lls.push([p.lat, p.lng]); });
    return lls.length === list.length ? null : { keep: keep, lls: lls };
  }
  // the view of a list map: the filtered places with coordinates — their main body (selView), else the whole frame.
  // Where the list is not shown (phones' 지도), framed in the whole box; beside the shown list (desktop: a sticky box
  // whose lower part may be below the window) in its part in the window — r.hb, framed again when the page scrolls
  // more of it in or out (listRefit); the zoom buttons zoom on the middle of that part (g.seen). QA 2026-10-19 QA-40:
  // the markers sat in the top third of the box once it was all in view, and two zoom-ins on the box's middle, below
  // the window, left none in view
  function listView(r) {
    var s = r.picked, hb = r.hb = besideList() ? Math.max(0, hiddenBelow(r.g.el)) : 0;
    if (s && s.lls.length) return selView(r, s.lls, 36, 5, hb);
    rest(r, 0);
    return frameIn(r.g, r.frame, 28, 2, hb);
  }
  // beside a shown list a list map's markers are quiet (out of the tab order, hidden from screen readers: the rows
  // are the same links); where the list is not shown (phones' 지도 view) they are named links in the tab order. The
  // list of /map/ (data.all) is its 권역 sections: quiet while one of them is shown
  function listQuiet(r) {
    if (!r.data.list && !r.data.all) return;
    var rows = r.data.list ? doc.querySelectorAll("[data-ledger]") : doc.querySelectorAll("[data-region-sec]");
    var quiet = Array.prototype.some.call(rows, visible);
    if (r.quiet === quiet) return;
    r.quiet = quiet;
    Object.keys(r.markers).forEach(function (id) {
      var a = r.markers[id]._a;
      a.tabIndex = quiet ? -1 : 0;
      if (quiet) a.setAttribute("aria-hidden", "true"); else a.removeAttribute("aria-hidden");
    });
  }

  // ------------------------------------------------------------ the adapter: one Kakao map in a box
  // Positions are worked out on Kakao's own plane (WCONGNAMUL: LatLng.toCoords(), 0.4 m a unit, y to the north), which
  // its tiles are cut from: at level lv a pixel is 2.5 × 2^(lv − 3) units, so g.project(ll, lv) / g.unproject(p, lv)
  // are exact, in fractions of a pixel, and need no map — every view is known before the map is made (g.open(view)
  // creates it right there: no tiles are fetched for a throwaway first view). After open: g.cp(ll) / g.ll(p) container
  // pixels ↔ [lat, lng]; g.view(c, lv, fly); g.fit(lls, [top, right, bottom, left], minLv, fly): the closest level that
  // holds the points in the padded box (a web map's fitBounds); g.on(type, fn) → off
  function unitsPerPx(lv) { return 2.5 * Math.pow(2, lv - 3); }
  function base(el) {
    el.innerHTML = "";
    var box = div("kmap");
    box.tabIndex = 0;
    box.setAttribute("role", "group");
    // the map takes the focus: its name is the box's, with how to move it (Korean and English; the other versions
    // give their words in data-words.keys when they have them)
    var keys = W.keys || (!EN ? "화살표 키로 이동, + − 키로 확대·축소" : /^en/i.test(doc.documentElement.lang) ? "arrow keys move it, + and − zoom" : "");
    box.setAttribute("aria-label", (el.getAttribute("aria-label") || (EN ? "Map" : "지도")) + (keys ? " · " + keys : ""));
    var tl = div("map-ctl map-tl"), tr = div("map-ctl map-tr"), bl = div("map-ctl map-bl");
    el.appendChild(box); el.appendChild(tl); el.appendChild(tr); el.appendChild(bl);
    var g = { k: null, el: el, box: box, ctl: { tl: tl, tr: tr, bl: bl } };
    g.size = function () { return pt(box.clientWidth, box.clientHeight); };
    g.project = function (a, lv) { var c = LL(a).toCoords(), u = unitsPerPx(lv); return pt(c.getX() / u, -c.getY() / u); };
    g.unproject = function (p, lv) { var u = unitsPerPx(lv), l = new K.Coords(p.x * u, -p.y * u).toLatLng(); return [l.getLat(), l.getLng()]; };
    g.fitView = function (lls, pad, minLv) {
      minLv = minLv || MINLV;
      if (lls.length === 1) return { c: lls[0], lv: Math.max(minLv, 5) };
      var sz = g.size(), x0 = Infinity, x1 = -Infinity, y0 = Infinity, y1 = -Infinity;
      lls.forEach(function (a) { var p = g.project(a, 1); x0 = Math.min(x0, p.x); x1 = Math.max(x1, p.x); y0 = Math.min(y0, p.y); y1 = Math.max(y1, p.y); });
      var w = Math.max(1, sz.x - pad[1] - pad[3]), h = Math.max(1, sz.y - pad[0] - pad[2]);
      var need = Math.max((x1 - x0) / w, (y1 - y0) / h); // at level 1
      var lv = clampLv(Math.max(minLv, need > 0 ? Math.ceil(1 + Math.log(need) / Math.LN2 - 1e-9) : minLv));
      var f = Math.pow(2, lv - 1); // level-1 pixels per pixel at lv
      return { c: g.unproject(pt((x0 + x1) / 2 + (pad[1] - pad[3]) / 2 * f, (y0 + y1) / 2 + (pad[2] - pad[0]) / 2 * f), 1), lv: lv };
    };
    // zoom buttons (44px, top left; also the + − keys while the map has the focus): made now, so a first view
    // worked out before the map exists keeps clear of them
    var zb = div("map-zoom");
    var zin = doc.createElement("button"), zout = doc.createElement("button");
    zin.type = zout.type = "button";
    zin.className = "mz-in"; zout.className = "mz-out";
    zin.textContent = "+"; zout.textContent = "−";
    zin.setAttribute("aria-label", W.in || (EN ? "Zoom in" : "확대"));
    zout.setAttribute("aria-label", W.out || (EN ? "Zoom out" : "축소"));
    zin.title = zin.getAttribute("aria-label"); zout.title = zout.getAttribute("aria-label");
    zb.appendChild(zin); zb.appendChild(zout); tl.appendChild(zb);
    g.resized = []; // fns to run after the box has changed size (course maps: the edge chips)
    g.open = function (v) {
      var k = g.k = new K.Map(box, { center: LL(v.c), level: clampLv(v.lv == null ? v.z : v.lv), scrollwheel: false,
        keyboardShortcuts: false, tileAnimation: !reduce });
      k.setCopyrightPosition(K.CopyrightPosition.BOTTOMRIGHT, true);
      g.centre = function () { var c = k.getCenter(); return [c.getLat(), c.getLng()]; };
      g.cp = function (a) {
        var lv = k.getLevel(), p = g.project(a, lv), c = g.project(g.centre(), lv), sz = g.size();
        return pt(p.x - c.x + sz.x / 2, p.y - c.y + sz.y / 2);
      };
      g.ll = function (p) {
        var lv = k.getLevel(), c = g.project(g.centre(), lv), sz = g.size();
        return g.unproject(pt(p.x - sz.x / 2 + c.x, p.y - sz.y / 2 + c.y), lv);
      };
      g.on = function (type, fn) { K.event.addListener(k, type, fn); return function () { K.event.removeListener(k, type, fn); }; };
      g.view = function (c, lv, fly) {
        lv = clampLv(lv);
        g.moved = false;
        if (!fly || reduce) { k.setLevel(lv); k.setCenter(LL(c)); return; }
        if (lv === k.getLevel()) { k.panTo(LL(c)); return; }
        k.setCenter(LL(c));
        k.setLevel(lv, { animate: { duration: 350 } });
      };
      g.fit = function (lls, pad, minLv, fly) { var w = g.fitView(lls, pad, minLv); g.view(w.c, w.lv, fly); return w; };
      g.relayout = function () { k.relayout(); g.resized.forEach(function (fn) { fn(); }); };
      // a marker / label (CustomOverlay with our element; anchor fractions of its box; clickable: the map does not
      // start a drag on it, so its link works)
      g.add = function (a, node, o) {
        o = o || {};
        var ov = new K.CustomOverlay({ position: LL(a), content: node, xAnchor: o.xa == null ? 0.5 : o.xa, yAnchor: o.ya == null ? 0.5 : o.ya,
          zIndex: o.z || 1, clickable: !!o.click });
        if (!o.off) ov.setMap(k);
        return ov;
      };
      g.shown = function (ov) { return !!ov.getMap(); };
      g.line = function (lls, o) {
        var l = new K.Polyline({ path: lls.map(LL), strokeWeight: o.w, strokeColor: o.c || INK, strokeOpacity: o.o == null ? 1 : o.o,
          strokeStyle: o.dash || "solid", zIndex: o.z || 0 });
        l.setMap(k);
        return l;
      };
      // the middle of the part of the box in the window (null when the box is all in it): the buttons and keys zoom on
      // it, so what the reader sees stays in view (QA 2026-10-19 QA-40: a sticky list map with its lower half below
      // the window zoomed on the box's middle, out of sight — two zoom-ins left no marker in view)
      g.seen = function () {
        var r = box.getBoundingClientRect(), t = Math.max(r.top, 0), b = Math.min(r.bottom, win.innerHeight);
        return b <= t || (t === r.top && b === r.bottom) ? null : g.ll(pt(r.width / 2, (t + b) / 2 - r.top));
      };
      // the reader moved the map (a drag, a double click, the zoom buttons, the keys) since the page last framed it
      // (g.view): a list map is then not framed again on its own (listRefit)
      g.moved = false;
      var moved = function () { g.moved = true; };
      g.on("dragstart", moved);
      g.on("dblclick", moved);
      var zoom = function (d) {
        var lv = clampLv(k.getLevel() + d), a = g.seen(), o = { animate: !reduce };
        if (lv === k.getLevel()) return;
        moved();
        if (a) o.anchor = LL(a);
        k.setLevel(lv, o);
      };
      zin.addEventListener("click", function () { zoom(-1); });
      zout.addEventListener("click", function () { zoom(1); });
      var zstate = function () { zin.disabled = k.getLevel() <= MINLV; zout.disabled = k.getLevel() >= MAXLV; };
      g.on("zoom_changed", zstate);
      zstate();
      box.addEventListener("keydown", function (e) {
        if (e.target !== box || e.altKey || e.ctrlKey || e.metaKey) return;
        var d = { ArrowLeft: [-1, 0], ArrowRight: [1, 0], ArrowUp: [0, -1], ArrowDown: [0, 1] }[e.key];
        if (d) { moved(); k.panBy(d[0] * 96, d[1] * 96); }
        else if (e.key === "+" || e.key === "=") zoom(-1);
        else if (e.key === "-" || e.key === "_") zoom(1);
        else return;
        e.preventDefault();
      });
      // the box changes size (a folded map opens, the window turns): Kakao needs to be told
      if ("ResizeObserver" in win) {
        var last = "";
        new ResizeObserver(function () {
          var sz = box.clientWidth + "x" + box.clientHeight;
          if (sz !== last && box.clientWidth) { var first = !last; last = sz; if (!first) g.relayout(); }
        }).observe(box);
      }
      return g;
    };
    return g;
  }
  // a stretch of the box a control or Kakao's logo covers ([x0, y0, x1, y1] in the box, 6px margin)
  function boxOf(el, host) {
    var a = el.getBoundingClientRect(), b = host.getBoundingClientRect();
    return [a.left - b.left - 6, a.top - b.top - 6, a.right - b.left + 6, a.bottom - b.top + 6];
  }
  function hits(a, b) { return !(a[2] <= b[0] || a[0] >= b[2] || a[3] <= b[1] || a[1] >= b[3]); }
  function controls(g, top) {
    var els = Array.prototype.slice.call(g.el.querySelectorAll(top ? ".map-tl > *, .map-tr > *" : ".map-ctl > *"));
    if (!top) { // Kakao's logo and copyright line (bottom right): the edge chips keep clear of it
      var logo = g.box.querySelector('img[src*="m_bi"]'), e = logo;
      for (var i = 0; e && i < 3 && e.parentNode && e.parentNode !== g.box; i++) e = e.parentNode; // logo › link › box › the line with the scale
      if (e) els.push(e);
    }
    return els.filter(function (el) { return el.offsetWidth > 0 && !el.hidden; }).map(function (el) { return boxOf(el, g.box); });
  }

  // labels: nearest first; each tries right then left of its marker and is dropped when it would overlap a shown
  // label or another marker
  function labelNode(html, cls, side, off) {
    var n = div("mk-label " + (cls || ""), html);
    n.setAttribute("aria-hidden", "true");
    n.style.transform = "translate(" + (side === "l" ? "calc(-100% - " + off + "px)" : off + "px") + ",-50%)";
    return n;
  }
  function declutter(g, items, markers) {
    var size = g.size(), shown = [];
    (markers || []).forEach(function (mk) {
      var p = g.cp(mk.ll), r = (mk.r || 6) + 2;
      shown.push([p.x - r, p.y - r, p.x + r, p.y + r]);
    });
    items.forEach(function (it) {
      var p = g.cp(it.ll), w = (it.w || 120) + 6, h = 20, gap = (it.r || 6) + 6, ok = null;
      ["r", "l"].some(function (side) {
        var box = side === "r" ? [p.x + gap, p.y - h / 2, p.x + gap + w, p.y + h / 2] : [p.x - gap - w, p.y - h / 2, p.x - gap, p.y + h / 2];
        if (box[0] < 50 || box[2] > size.x - 4 || box[1] < 4 || box[3] > size.y - 22) return false;
        var hit = shown.some(function (b) { return !(box[2] < b[0] || box[0] > b[2] || box[3] < b[1] || box[1] > b[3]); });
        if (!hit) { ok = side; shown.push(box); }
        return !hit;
      });
      if (ok) {
        if (it.side !== ok) { it.side = ok; it.lab.setContent(labelNode(it.html, it.cls, ok, gap)); }
        if (!g.shown(it.lab)) it.lab.setMap(g.k);
      } else if (g.shown(it.lab)) it.lab.setMap(null);
    });
  }
  // one tooltip per map (a list map's names on hover)
  function tip(g) {
    var n = div("tt-map"), ov = g.add([0, 0], n, { xa: 0.5, ya: 1, z: 2000, off: true });
    n.setAttribute("aria-hidden", "true");
    return {
      show: function (a, text) { n.textContent = text; ov.setPosition(LL(a)); ov.setMap(g.k); },
      hide: function () { ov.setMap(null); }
    };
  }

  /* COURSE MAPS (ui.coursemap). Every stop keeps its own numbered marker — nothing is merged into a range:
     - spread(): markers that would touch at this level are pushed apart from their true points as little as needed
       (stops at one spot ring round it in number order); a hairline joins a moved marker to its true point;
     - bestFrame(): the first view is the box at the level (street level outwards) that holds the most stops whose
       markers stand alone (no marker moved more than MAXOFF px) — so a course in two places opens on the place
       with more stops, never on a few dots joined by one long line;
     - edge chips: the stops outside the view are pointed at from the box edge (an arrow towards them and their
       numbers); pressing one moves the map to them. '전체 보기' frames every stop. */
  // marker, centre gap, largest move; box padding (left: clear of the zoom buttons, top: of '전체 보기'); edge chip
  // thickness and margin (its hit area is 44px: css .mk-edge::before)
  var MK = 28, MIN = MK + 3, MAXOFF = 22, CPAD = [68, 62, 54, 54], CHIP_T = 32, CHIP_M = 8;
  var DIRS = EN ? ["east", "south-east", "south", "south-west", "west", "north-west", "north", "north-east"]
    : ["동쪽", "남동쪽", "남쪽", "남서쪽", "서쪽", "북서쪽", "북쪽", "북동쪽"];
  function spread(P, rings) {
    var n = P.length, pos = P.map(function (p) { return [p.x, p.y]; }), max = 0, seen = {}, i, j, it;
    // piles: markers that would sit on one another (chained: centres closer than MIN). Stops at one spot are set
    // round it in number order, clockwise from the top (two: side by side); with rings, so is a pile whose points
    // lie closer together than its ring would be (a zoomed-out view); the rest are pushed apart where they touch.
    for (i = 0; i < n; i++) {
      if (seen[i]) continue;
      var g = [i], q = 0;
      seen[i] = 1;
      while (q < g.length) { var a = g[q++]; for (j = 0; j < n; j++) if (!seen[j] && P[a].distanceTo(P[j]) < MIN) { seen[j] = 1; g.push(j); } }
      if (g.length < 2) continue;
      g.sort(function (x, y) { return x - y; }); // items come in course order
      var cx = 0, cy = 0, ext = 0, R = g.length === 2 ? MIN / 2 : MIN / (2 * Math.sin(Math.PI / g.length));
      g.forEach(function (k) { cx += P[k].x / g.length; cy += P[k].y / g.length; });
      g.forEach(function (k) { ext = Math.max(ext, Math.sqrt(Math.pow(P[k].x - cx, 2) + Math.pow(P[k].y - cy, 2))); });
      if (ext > (rings ? R * 0.8 : 0.5)) continue;
      g.forEach(function (k, r) {
        var ang = g.length === 2 ? (r ? 0 : Math.PI) : -Math.PI / 2 + r * 2 * Math.PI / g.length;
        pos[k] = [cx + Math.cos(ang) * R, cy + Math.sin(ang) * R];
      });
    }
    for (it = 0; it < 150; it++) {
      var moved = false;
      for (i = 0; i < n; i++) for (j = i + 1; j < n; j++) {
        var dx = pos[j][0] - pos[i][0], dy = pos[j][1] - pos[i][1], dd = Math.sqrt(dx * dx + dy * dy);
        if (dd >= MIN - 0.05) continue;
        if (dd < 1e-6) { dx = 1; dy = 0; dd = 1; }
        var k = (MIN - dd) / 2 / dd;
        pos[i][0] -= dx * k; pos[i][1] -= dy * k; pos[j][0] += dx * k; pos[j][1] += dy * k;
        moved = true;
      }
      if (!moved) break;
    }
    for (i = 0; i < n; i++) max = Math.max(max, Math.sqrt(Math.pow(pos[i][0] - P[i].x, 2) + Math.pow(pos[i][1] - P[i].y, 2)));
    return { pos: pos, max: max };
  }
  // the view {c: centre, z: level} that shows the most stops of pool (indices; default all) standing alone; with
  // must, a view that holds that stop. A view is judged as it will be drawn (the closest level that fits the stops,
  // centred in the padded box, slid a little when that clears an edge): every stop it shows must stand alone, and
  // none may sit cut at an edge or under a control — each is well inside or off the view, where an edge chip points
  // at it.
  function bestFrame(g, items, pool, must) {
    pool = pool || items.map(function (it, q) { return q; });
    var sz = g.size(), w = sz.x - CPAD[0] - CPAD[2], h = sz.y - CPAD[1] - CPAD[3], best = null, tried = {};
    var E = MK / 2 + 6, R = MK / 2 + 2, BOT = 22; // BOT: Kakao's logo line
    var ctl = controls(g, true);
    var off = function (x, y) { return x < -R || y < -R || x > sz.x + R || y > sz.y + R; };
    var clear = function (x, y) {
      return x >= E && y >= E && x <= sz.x - E && y <= sz.y - E - BOT && !ctl.some(function (a) { return x + R > a[0] && x - R < a[2] && y + R > a[1] && y - R < a[3]; });
    };
    function judge(P, S, lv) {
      var x0 = Infinity, x1 = -Infinity, y0 = Infinity, y1 = -Infinity;
      S.forEach(function (q) { x0 = Math.min(x0, P[q].x); x1 = Math.max(x1, P[q].x); y0 = Math.min(y0, P[q].y); y1 = Math.max(y1, P[q].y); });
      var one = S.length === 1, lf = one ? 5 : Math.max(4, lv - Math.floor(Math.log(Math.min(x1 > x0 ? w / (x1 - x0) : 1e9, y1 > y0 ? h / (y1 - y0) : 1e9)) / Math.LN2 + 1e-9));
      var f = Math.pow(2, lv - lf), Q = P.map(function (p) { return pt(p.x * f, p.y * f); });
      var cx = (x0 + x1) / 2 * f + (one ? 0 : (CPAD[2] - CPAD[0]) / 2), cy = (y0 + y1) / 2 * f + (one ? 0 : (CPAD[3] - CPAD[1]) / 2);
      // slides to try: none, then each that moves a stop caught at an edge fully in or fully out
      var dxs = [0], dys = [0];
      Q.forEach(function (p) {
        var x = p.x - cx + sz.x / 2, y = p.y - cy + sz.y / 2;
        if (off(x, y) || clear(x, y)) return;
        dxs.push(E - x, sz.x - E - x, -R - 1 - x, sz.x + R + 1 - x);
        dys.push(E - y, sz.y - E - BOT - y, -R - 1 - y, sz.y + R + 1 - y);
      });
      var tries = [];
      dxs.forEach(function (dx) { dys.forEach(function (dy) { if (Math.abs(dx) <= 48 && Math.abs(dy) <= 48) tries.push([dx, dy]); }); });
      tries.sort(function (a, b) { return Math.abs(a[0]) + Math.abs(a[1]) - Math.abs(b[0]) - Math.abs(b[1]); });
      for (var t = 0; t < tries.length && t < 40; t++) {
        var vx = cx - tries[t][0], vy = cy - tries[t][1], ok = true, V = [];
        for (var q = 0; q < Q.length && ok; q++) {
          var x = Q[q].x - vx + sz.x / 2, y = Q[q].y - vy + sz.y / 2;
          if (off(x, y)) { if (S.indexOf(q) >= 0) ok = false; continue; }
          if (!clear(x, y)) ok = false; else V.push(Q[q]);
        }
        if (ok && spread(V, false).max <= MAXOFF) return { S: S, z: lf, c: g.unproject(pt(vx, vy), lf) };
      }
      return null;
    }
    for (var lv = 4; lv <= MAXLV; lv++) { // street level outwards
      var P = items.map(function (it) { return g.project(it.ll, lv); });
      for (var i = 0; i < pool.length; i++) for (var j = 0; j < pool.length; j++) {
        var S = pool.filter(function (k) { return P[k].x >= P[pool[i]].x - 1e-6 && P[k].x <= P[pool[i]].x + w && P[k].y >= P[pool[j]].y - 1e-6 && P[k].y <= P[pool[j]].y + h; });
        if ((best && S.length <= best.S.length) || (must != null && S.indexOf(must) < 0)) continue;
        var key = S.join(",");
        if (tried[key]) continue;
        tried[key] = 1;
        best = judge(P, S, lv) || best;
      }
      if (best && best.S.length === pool.length) break;
    }
    if (!best) { var q0 = must != null ? must : pool[0]; best = { S: [q0], z: 5, c: items[q0].ll }; }
    return best;
  }
  // a view from bestFrame ({c, z}), or every stop (fitted in the padded box); fly when asked (the markers are then
  // spread for the new level once the map has settled: the idle handler in courseMap)
  function showStops(reg, g, view, fly) {
    if (view.c) g.view(view.c, view.z, fly);
    else g.fit(reg.lls, [CPAD[1], CPAD[2], CPAD[3], CPAD[0]], 4, fly);
    if (fly && !reduce) reg.placed = null;
    else placeStops(reg, g);
  }
  // markers at this level: pushed apart where they would touch, a hairline from each moved marker to its point
  function placeStops(reg, g) {
    var P = reg.items.map(function (it) { return g.cp(it.ll); }), r = spread(P, false);
    if (r.max > MAXOFF) r = spread(P, true); // piled up (zoomed out): rings in number order read better
    reg.placed = g.k.getLevel();
    reg.legs.forEach(function (x) { x.setMap(null); });
    reg.legs = [];
    reg.items.forEach(function (it, i) {
      var q = pt(r.pos[i][0], r.pos[i][1]);
      it.at = g.ll(q);
      it.mk.setPosition(LL(it.at));
      if (q.distanceTo(P[i]) > 5) {
        reg.legs.push(g.line([it.ll, it.at], { w: 1, o: 0.6 }));
        reg.legs.push(g.add(it.ll, div("mk-foot"), { z: 0 }));
      }
    });
  }
  // the stops outside the view, pointed at from the box edge in their direction (8 directions from the centre);
  // chips that would overlap are joined. '전체 보기' shows only while some stop is outside.
  function edgeChips(reg, g) {
    var sz = g.size(), c = pt(sz.x / 2, sz.y / 2), groups = [], by = {};
    if (!sz.x) return;
    reg.items.forEach(function (it) {
      var p = g.cp(it.at || it.ll);
      if (p.x >= 0 && p.y >= 0 && p.x <= sz.x && p.y <= sz.y) return;
      var s = (Math.round(Math.atan2(p.y - c.y, p.x - c.x) / (Math.PI / 4)) + 8) % 8;
      if (!by[s]) groups.push(by[s] = { items: [], ps: [] });
      by[s].items.push(it); by[s].ps.push(p);
    });
    if (reg.allBtn) reg.allBtn.hidden = !groups.length;
    var avoid = controls(g, false);
    var place = function (gr) {
      var x = 0, y = 0;
      gr.ps.forEach(function (p) { x += p.x / gr.ps.length; y += p.y / gr.ps.length; });
      x -= c.x; y -= c.y;
      gr.ang = Math.atan2(y, x);
      var k = gr.items.length > 6 ? 5 : gr.items.length, len = 34 + k * 24 + (gr.items.length > k ? 26 : 0);
      var tx = Math.abs(x) > 1e-6 ? (sz.x / 2) / Math.abs(x) : 1e9, ty = Math.abs(y) > 1e-6 ? (sz.y / 2) / Math.abs(y) : 1e9;
      gr.vert = tx < ty; // through a side: a vertical pill on it; through the top or bottom: a horizontal one
      var t = Math.min(tx, ty), px = c.x + x * t, py = c.y + y * t, b;
      if (gr.vert) { var bx = x > 0 ? sz.x - CHIP_M - CHIP_T : CHIP_M; b = [bx, py - len / 2, bx + CHIP_T, py + len / 2]; }
      else { var byy = y > 0 ? sz.y - CHIP_M - CHIP_T : CHIP_M; b = [px - len / 2, byy, px + len / 2, byy + CHIP_T]; }
      var clamp = function () {
        var dx = Math.max(0, CHIP_M - b[0]) - Math.max(0, b[2] - (sz.x - CHIP_M)), dy = Math.max(0, CHIP_M - b[1]) - Math.max(0, b[3] - (sz.y - CHIP_M));
        b = [b[0] + dx, b[1] + dy, b[2] + dx, b[3] + dy];
      };
      clamp();
      for (var pass = 0; pass < 3; pass++) avoid.forEach(function (a) { // slide along the edge, away from the control
        if (!hits(b, a)) return;
        var d = gr.vert ? ((b[1] + b[3]) / 2 < (a[1] + a[3]) / 2 && a[1] - (b[3] - b[1]) >= CHIP_M ? a[1] - b[3] : a[3] - b[1])
          : ((b[0] + b[2]) / 2 < (a[0] + a[2]) / 2 && a[0] - (b[2] - b[0]) >= CHIP_M ? a[0] - b[2] : a[2] - b[0]);
        if (gr.vert) { b[1] += d; b[3] += d; } else { b[0] += d; b[2] += d; }
        clamp();
      });
      gr.b = b;
    };
    groups.forEach(place);
    for (var again = true; again;) { // two chips that touch become one
      again = false;
      for (var i = 0; i < groups.length && !again; i++) for (var j = i + 1; j < groups.length && !again; j++) {
        if (!hits(groups[i].b, groups[j].b)) continue;
        groups[i].items = groups[i].items.concat(groups[j].items); groups[i].ps = groups[i].ps.concat(groups[j].ps);
        groups.splice(j, 1); place(groups[i]); again = true;
      }
    }
    var box = reg.chips, had = box.contains(doc.activeElement);
    box.innerHTML = "";
    groups.forEach(function (gr) {
      gr.items.sort(function (a, b) { return a.n - b.n; });
      var ns = gr.items.map(function (it) { return it.n; }), shown = gr.items.length > 6 ? ns.slice(0, 5) : ns;
      var dir = DIRS[(Math.round(gr.ang / (Math.PI / 4)) + 8) % 8];
      var b = doc.createElement("button");
      b.type = "button"; b.className = "mk-edge" + (gr.vert ? " vert" : "");
      b.style.left = Math.round(gr.b[0]) + "px"; b.style.top = Math.round(gr.b[1]) + "px";
      b.setAttribute("aria-label", W.off ? W.off + " (" + ns.join(", ") + ": " + gr.items[0].name + ")" : EN ? "Stops " + ns.join(", ") + " (" + gr.items[0].name + (ns.length > 1 ? " and " + (ns.length - 1) + " more" : "") + ") lie off the map to the " + dir + " · show them"
        : ns.join(", ") + "번 경유지(" + gr.items[0].name + (ns.length > 1 ? " 외 " + (ns.length - 1) + "곳" : "") + ")가 지도 밖 " + dir + "에 있습니다 · 눌러서 보기");
      b.title = gr.items.map(function (it) { return it.n + ". " + it.name; }).join("\n");
      b.innerHTML = '<svg class="me-arr" viewBox="0 0 16 16" aria-hidden="true" style="transform:rotate(' + (gr.ang * 180 / Math.PI).toFixed(1) +
        'deg)"><path d="M2 8h11M9 4l4 4-4 4"/></svg>' + shown.map(function (n) { return '<span class="me-n" aria-hidden="true">' + n + "</span>"; }).join("") +
        (ns.length > shown.length ? '<span class="me-more" aria-hidden="true">+' + (ns.length - shown.length) + "</span>" : "");
      b.addEventListener("click", function () { showStops(reg, g, bestFrame(g, reg.items, gr.items.map(function (it) { return reg.items.indexOf(it); })), true); });
      box.appendChild(b);
    });
    if (had) (box.firstChild || reg.allBtn || g.box).focus();
  }
  // before the map: the edge chips' layer, '전체 보기' and the first view (bestFrame needs only the plane and the
  // controls); after it: the markers spread, the chips, and the moves course.js asks for
  function courseHome(reg, g) {
    reg.legs = [];
    reg.chips = div("mk-edges");
    g.el.appendChild(reg.chips);
    var b = doc.createElement("button");
    b.type = "button";
    b.className = "far-ctl map-all";
    b.textContent = W.all || (EN ? "Whole course" : "전체 보기");
    b.addEventListener("click", function () { showStops(reg, g, {}, true); });
    g.ctl.tr.appendChild(b);
    reg.allBtn = b;
    reg.home = bestFrame(g, reg.items);
    return reg.home;
  }
  function courseMap(reg, g) {
    reg.showHome = function (fly) { showStops(reg, g, reg.home, fly); };
    reg.showAround = function (n) { // course.js: the view that holds stop n (the current one when n is in it)
      var it = reg.items.filter(function (x) { return x.n === n; })[0];
      if (!it) return false;
      var p = g.cp(it.at || it.ll), sz = g.size();
      if (p.x > CPAD[0] - 10 && p.y > CPAD[1] - 10 && p.x < sz.x - CPAD[2] + 10 && p.y < sz.y - CPAD[3] + 10) return false;
      showStops(reg, g, bestFrame(g, reg.items, null, reg.items.indexOf(it)), true);
      return true;
    };
    // after any move: the markers spread for the level they are now seen at, the chips for what is out of view
    g.on("idle", function () { if (reg.placed !== g.k.getLevel()) placeStops(reg, g); edgeChips(reg, g); });
    g.resized.push(function () { edgeChips(reg, g); });
    placeStops(reg, g);
    edgeChips(reg, g);
  }
  // the blue progress line of a course map (course.js): through stop n; the part after stop `from` grows along the
  // straight lines in 1.1s (ease in-out) unless motion is reduced
  function progress(reg, g) {
    var line = reg.progress, anim = 0;
    // the points up to stop n on n's own seg (a line never joins two options of a day: present.course_map)
    var segOf = function (n) { var k = 0; reg.data.course.forEach(function (p) { if (!p.extra && p.n <= n) k = p.seg || 0; }); return k; };
    var upto = function (n, k) { var out = []; if (k == null) k = segOf(n); reg.data.course.forEach(function (p) { if (!p.extra && p.n <= n && (p.seg || 0) === k) out.push([p.lat, p.lng]); }); return out; };
    return function (from, n) {
      if (anim) { win.cancelAnimationFrame(anim); anim = 0; }
      var done = upto(n);
      if (n <= 0 || done.length < 2) { line.setMap(null); return; }
      line.setMap(g.k);
      var start = upto(from, segOf(n));
      if (reduce || n <= from) { line.setPath(done.map(LL)); return; }
      if (!start.length) start = done.slice(0, 1); // from the first stop
      var rest = done.slice(start.length - 1), lens = [], tot = 0;
      for (var i = 1; i < rest.length; i++) { var d = g.cp(rest[i - 1]).distanceTo(g.cp(rest[i])); lens.push(d); tot += d; }
      if (!tot) { line.setPath(done.map(LL)); return; }
      var t0 = 0;
      var step = function (now) {
        if (!t0) t0 = now;
        var t = Math.min(1, (now - t0) / 1100), e = t < 0.5 ? 4 * t * t * t : 1 - Math.pow(-2 * t + 2, 3) / 2;
        var want = e * tot, path = start.slice(), acc = 0;
        for (var i = 0; i < lens.length; i++) {
          if (acc + lens[i] <= want) { path.push(rest[i + 1]); acc += lens[i]; continue; }
          var f = (want - acc) / lens[i];
          path.push([rest[i][0] + (rest[i + 1][0] - rest[i][0]) * f, rest[i][1] + (rest[i + 1][1] - rest[i][1]) * f]);
          break;
        }
        line.setPath(path.map(LL));
        anim = t < 1 ? win.requestAnimationFrame(step) : 0;
      };
      line.setPath(start.map(LL));
      anim = win.requestAnimationFrame(step);
    };
  }

  function normalise(raw, el) {
    if (Array.isArray(raw)) return el.hasAttribute("data-numbered") ? { course: raw } : { list: raw };
    return raw || {};
  }

  function build(el) {
    var d;
    try { d = normalise(JSON.parse(el.getAttribute("data-points") || el.getAttribute("data-map")), el); } catch (e) { return null; }
    var pts0 = d.self ? [d.self] : (d.course || d.guide || d.list || d.all || d.anchors || []);
    if (!pts0.length) return null; // nothing to draw: the box keeps its text
    var g = base(el), reg = { el: el, map: null, g: g, markers: {}, items: [], data: d };
    if (d.self) { // a place or an event: itself, its neighbours, labelled straight-line anchors, or a radius
      var c = [d.self.lat, d.self.lng], bounds = [c];
      (d.near || []).forEach(function (n, i) { if (i < 8) bounds.push([n.lat, n.lng]); });
      (d.anchors || []).forEach(function (a) { bounds.push([a.lat, a.lng]); });
      if (d.radius) {
        var dla = d.radius * 1.125 / 111320, dln = dla / Math.cos(c[0] * Math.PI / 180);
        g.open(g.fitView([[c[0] - dla, c[1] - dln], [c[0] + dla, c[1] + dln]], [0, 0, 0, 0], 1));
        new K.Circle({ center: LL(c), radius: d.radius, strokeWeight: 1, strokeColor: INK, strokeOpacity: 1, strokeStyle: "shortdash", fillOpacity: 0 }).setMap(g.k);
      } else g.open(bounds.length > 1 ? g.fitView(bounds, [40, 40, 40, 40], 4) : { c: c, lv: 5 });
      g.add(c, pin("mk-self", "", "", d.self.name), { z: 30 });
      var items = [{ ll: c, html: esc(d.self.name), cls: "self", w: textW(d.self.name) + 6, r: 11 }], mks = [];
      (d.near || []).forEach(function (n, i) {
        var ll = [n.lat, n.lng];
        g.add(ll, kindPin(n.kind, n.url, n.name + (n.d ? " " + n.d : "")), { z: 10, click: true });
        mks.push({ ll: ll, r: 6 });
        if (i < 6) items.push({ ll: ll, html: esc(n.name) + (n.d ? "<small>" + esc(n.d) + "</small>" : ""), w: textW(n.name + (n.d || "")), r: 6 });
      });
      (d.anchors || []).forEach(function (a) {
        var ll = [a.lat, a.lng];
        g.line([c, ll], { w: 1.5, o: 0.7, dash: "shortdot" });
        g.add(ll, pin("mk-anchor", "", "", a.label || a.name), { z: 10 });
        mks.push({ ll: ll, r: 7 });
        items.push({ ll: ll, html: esc(a.label || a.name), w: textW(a.label || a.name), r: 7 });
      });
      items.forEach(function (it) { it.lab = g.add(it.ll, labelNode(it.html, it.cls, "r", (it.r || 6) + 6), { xa: 0, ya: 0, z: 5, off: true }); it.side = "r"; });
      var redraw = function () { declutter(g, items, mks); };
      g.on("idle", redraw);
      redraw();
    } else if (d.course || d.guide) { // numbered stops; a straight line in order (course: thin solid; routed guide: dashed)
      var pts = d.course || d.guide, route = !!d.course || !!d.route, lls = [];
      reg.byId = {}; // a guide's places by id (gs:focus)
      pts.forEach(function (p) { if (!p.extra) { lls.push([p.lat, p.lng]); reg.items.push({ n: +p.n, ll: [p.lat, p.lng], name: p.name }); } });
      reg.lls = lls;
      var frame = lls.length ? lls : pts.map(function (p) { return [p.lat, p.lng]; });
      reg.frame = route ? frame : robust(frame, 0.03);
      // a course map opens on the most stops that stand alone in the whole box (sticky on desktop: framing only the
      // part above the fold would shrink it); the rest are pointed at from the edge
      var course = d.course && reg.items.length > 1;
      g.open(course ? courseHome(reg, g) : visibleView(g, reg.frame, 44, 4));
      var q = 0;
      pts.forEach(function (p) {
        var ll = [p.lat, p.lng], extra = !!p.extra;
        var node = pin("mk-num" + (extra ? " extra" : ""), extra ? "" : esc(p.n), p.url, (extra ? "" : p.n + ". ") + p.name);
        var mk = g.add(ll, node, { z: extra ? 15 : 20, click: true });
        mk._el = node.firstChild;
        mk._ll = ll;
        if (p.id) reg.byId[p.id] = mk;
        if (extra) {
          if (!reg.tip) reg.tip = tip(g);
          node.addEventListener("mouseenter", function () { reg.tip.show(ll, p.name); });
          node.addEventListener("mouseleave", function () { reg.tip.hide(); });
        } else { reg.markers[p.n] = mk; reg.items[q++].mk = mk; }
      });
      reg.paint = function () { // the stop being read (.on) and the stops before it (.past)
        var n = reg.activeN || 0;
        Object.keys(reg.markers).forEach(function (k) {
          var mk = reg.markers[k];
          mk._el.classList.toggle("on", +k === n); mk._el.classList.toggle("past", n > 0 && +k < n);
          mk.setZIndex(+k === n ? 1000 : 20);
        });
      };
      if (route && lls.length > 1) {
        if (d.course) { // one line per seg: no line between two options of a day (present.course_map, QA 2026-10-15)
          var segs = {};
          pts.forEach(function (p) { if (!p.extra) (segs[p.seg || 0] = segs[p.seg || 0] || []).push([p.lat, p.lng]); });
          Object.keys(segs).forEach(function (k) { if (segs[k].length > 1) g.line(segs[k], { w: 2, o: 0.55 }); });
        } else g.line(lls, { w: 2, o: 0.5, dash: "dash" });
        reg.progress = g.line([], { w: 4.5, c: BLUE, o: 1, z: 2 });
        reg.progress.setMap(null);
      }
      if (course) courseMap(reg, g);
      if (reg.progress) reg.progressTo = progress(reg, g);
    } else if (d.list || d.all) { // a list page, or the map page with its 권역
      var list = d.list || d.all;
      var main = list.filter(function (p) { return p.r !== "먼 섬" && p.r !== "권역 미정"; }).map(function (p) { return [p.lat, p.lng]; });
      if (!main.length) main = list.map(function (p) { return [p.lat, p.lng]; });
      reg.frame = robust(main, d.all ? 0.03 : 0.08);
      // a list page's filter set before this map was built (phones build it at the first 지도): only those places,
      // framed from the first view
      reg.picked = d.list ? picked(list, win.GSFilter && win.GSFilter.ids) : null;
      g.open(d.list ? listView(reg) : visibleView(g, reg.frame, 28));
      var tt = tip(g);
      list.forEach(function (p) {
        var ll = [p.lat, p.lng], id = idOf(p), node = kindPin(p.kind, p.url, p.name, true);
        var mk = g.add(ll, node, { z: 10, click: true, off: !!reg.picked && !reg.picked.keep[id] });
        var on = function () { tt.show(ll, p.name); doc.dispatchEvent(new CustomEvent("gs:hlrow", { detail: { id: id, on: true } })); };
        var off = function () { tt.hide(); doc.dispatchEvent(new CustomEvent("gs:hlrow", { detail: { id: id, on: false } })); };
        node.addEventListener("mouseenter", on); node.addEventListener("mouseleave", off);
        node.addEventListener("focus", on); node.addEventListener("blur", off);
        mk._gs = p; mk._el = node.firstChild; mk._a = node;
        reg.markers[id] = mk;
      });
      listQuiet(reg);
      if (d.anchor_pts) regions(reg, g, list, main, d.anchor_pts);
    } else if (d.anchors) { // the home: the 권역 anchors labelled with their counts; each links to its region on /map/
      var alls = d.anchors.map(function (a) { return [a.lat, a.lng]; }), labs = [];
      reg.frame = alls;
      g.open(g.fitView(alls, [40, 56, 40, 56], 1));
      d.anchors.forEach(function (a, i) {
        var ll = alls[i];
        g.add(ll, pin("mk-anchor", "", a.url, a.name + " " + a.n + "곳 · 기준점 " + a.place), { z: 10, click: true });
        var lab = div("mk-region", esc(a.name) + "<small>" + a.n + "곳</small>");
        lab.setAttribute("aria-hidden", "true");
        labs.push({ ll: ll, n: a.n, node: lab, w: textW(a.name) + 44, ov: g.add(ll, lab, { xa: 0, ya: 0, z: 5 }) });
      });
      // the labels, largest region first: above the anchor, else below, right or left of it — never over another
      // label, and over another anchor's square only when no side is clear (then the side that covers least)
      var SIDES = [["translate(-50%,calc(-100% - 10px))", function (p, w, h) { return [p.x - w / 2, p.y - 10 - h, p.x + w / 2, p.y - 10]; }],
        ["translate(-50%,10px)", function (p, w, h) { return [p.x - w / 2, p.y + 10, p.x + w / 2, p.y + 10 + h]; }],
        ["translate(12px,-50%)", function (p, w, h) { return [p.x + 12, p.y - h / 2, p.x + 12 + w, p.y + h / 2]; }],
        ["translate(calc(-100% - 12px),-50%)", function (p, w, h) { return [p.x - 12 - w, p.y - h / 2, p.x - 12, p.y + h / 2]; }]];
      var cover = function (b, o) { return Math.max(0, Math.min(b[2], o[2]) - Math.max(b[0], o[0])) * Math.max(0, Math.min(b[3], o[3]) - Math.max(b[1], o[1])); };
      var place = function () {
        var dots = labs.map(function (l) { var p = g.cp(l.ll); return [p.x - 9, p.y - 9, p.x + 9, p.y + 9]; }), shown = [];
        labs.slice().sort(function (x, y) { return y.n - x.n; }).forEach(function (l) {
          var p = g.cp(l.ll), w = l.node.offsetWidth || l.w, h = l.node.offsetHeight || 22, best = null;
          SIDES.forEach(function (sd) {
            var b = sd[1](p, w, h);
            if (shown.some(function (o) { return hits(b, o); })) return;
            var c = dots.reduce(function (t, o) { return t + cover(b, o); }, 0);
            if (!best || c < best.c) best = { sd: sd, b: b, c: c };
          });
          if (best) { shown.push(best.b); l.node.style.transform = best.sd[0]; if (!g.shown(l.ov)) l.ov.setMap(g.k); }
          else if (g.shown(l.ov)) l.ov.setMap(null);
        });
      };
      g.on("idle", place);
      place();
    } else {
      return null;
    }
    reg.map = g.k;
    reg.g = g;
    reg.whenIdle = function (fn) { // course.js: fn once the map stops moving (or after 1.6s), cancellable
      var done = false, off, t;
      var run = function () { if (done) return; done = true; off(); clearTimeout(t); fn(); };
      off = g.on("idle", run);
      t = setTimeout(run, 1600);
      return function () { if (!done) { done = true; off(); clearTimeout(t); } };
    };
    maps.push(reg);
    el.dispatchEvent(new CustomEvent("gs:mapready", { bubbles: true, detail: reg }));
    return reg;
  }

  // the map page: 권역 labels above each region's points (collision-checked) and an edge control for 먼 섬
  function regions(reg, g, list, main, anchors) {
    reg.regions = anchors.map(function (a) {
      var ps = list.filter(function (p) { return p.r === a.name; });
      var la = ps.map(function (p) { return p.lat; }).sort(function (x, y) { return x - y; });
      var ln = ps.map(function (p) { return p.lng; }).sort(function (x, y) { return x - y; });
      var ll = ps.length ? [la[Math.floor((la.length - 1) * 0.9)], ln[ln.length >> 1]] : [a.geo.lat, a.geo.lng];
      var n = div("mk-region");
      n.setAttribute("aria-hidden", "true");
      n.style.transform = "translate(-50%,calc(-100% - 10px))";
      return { name: a.name, n: a.n, ll: ll, node: n, lab: g.add(ll, n, { xa: 0, ya: 0, z: 40, off: true }) };
    });
    reg.drawRegions = function (sel) {
      var shown = [];
      reg.regions.slice().sort(function (x, y) { return y.n - x.n; }).forEach(function (r) {
        var on = !sel || sel === r.name, p = g.cp(r.ll), w = textW(r.name) + 50, h = 24;
        var box = [p.x - w / 2, p.y - h - 10, p.x + w / 2, p.y - 10];
        var hit = shown.some(function (b) { return !(box[2] < b[0] || box[0] > b[2] || box[3] < b[1] || box[1] > b[3]); });
        if (on && !hit) {
          shown.push(box);
          r.node.className = "mk-region" + (sel ? " sel" : "");
          r.node.innerHTML = esc(r.name) + "<small>" + r.n + "곳</small>";
          if (!g.shown(r.lab)) r.lab.setMap(g.k);
        } else if (g.shown(r.lab)) r.lab.setMap(null);
      });
    };
    g.on("idle", function () { reg.drawRegions(reg.sel); });
    reg.drawRegions("");
    var far = list.filter(function (p) { return p.r === "먼 섬"; });
    if (!far.length) return;
    var b = doc.createElement("button");
    b.type = "button";
    b.className = "far-ctl";
    var names = far.map(function (p) { return p.name; }).slice(0, 2).join("·");
    b.textContent = "← 먼 섬 " + far.length + "곳 (" + names + (far.length > 2 ? " 등" : "") + ")";
    b.addEventListener("click", function () {
      g.fit(far.map(function (p) { return [p.lat, p.lng]; }).concat(main.slice(0, 1)), [40, 40, 40, 40], 1, true);
    });
    g.ctl.bl.appendChild(b);
  }

  // a row lights its marker (state change only, nothing moves)
  doc.addEventListener("gs:hl", function (e) {
    maps.forEach(function (r) {
      var mk = r.markers[e.detail.id] || r.markers[decodeURIComponent(e.detail.id)];
      if (!mk || !mk._el) return;
      mk._el.classList.toggle("mk-hl", e.detail.on);
      mk.setZIndex(e.detail.on ? 1000 : 10);
    });
  });
  // the list's filter (site.js; also sent when only the 목록 | 지도 view changes): the kept markers shown, the others
  // taken off, and the map framed on the kept ones when the set has changed and the map is on screen (a hidden map
  // is framed when it is shown: gs:showmap)
  doc.addEventListener("gs:filter", function (e) {
    maps.forEach(function (r) {
      if (!r.data.list) return;
      var was = r.picked ? r.picked.lls.join(";") : "", s = r.picked = picked(r.data.list, e.detail.ids);
      Object.keys(r.markers).forEach(function (id) {
        var mk = r.markers[id];
        if (!s || s.keep[id]) { if (!r.g.shown(mk)) mk.setMap(r.map); } else if (r.g.shown(mk)) mk.setMap(null);
      });
      listQuiet(r);
      if ((s ? s.lls.join(";") : "") !== was && visible(r.el)) { var v = listView(r); r.g.view(v.c, v.lv, true); }
    });
  });
  var lastRegion = win.GSRegion || null;   // a 권역 chosen before this file loaded (site.js, the address's #r-…)
  function applyRegion(r, det) {
    if (!r.data.all) return;
    var pts = [];
    Object.keys(r.markers).forEach(function (id) {
      var mk = r.markers[id], p = mk._gs, ok = (!det.region || p.r === det.region) && det.kinds[p.kind || "attraction"] !== false;
      if (ok) { if (!r.g.shown(mk)) mk.setMap(r.map); pts.push([p.lat, p.lng]); } else if (r.g.shown(mk)) mk.setMap(null);
    });
    r.sel = det.region;
    // the 권역's main body: a group of islands a sea away is left to the '지도 밖' control (body(), QA 2026-10-19 QA-41)
    if (det.region && pts.length) { var v = selView(r, pts, 36, 5, 0); r.g.view(v.c, v.lv, true); }
    else { rest(r, 0); if (!det.region) r.g.fit(r.frame, [28, 28, 28, 28], 2, true); }
    if (r.drawRegions) r.drawRegions(det.region);
  }
  doc.addEventListener("gs:region", function (e) { lastRegion = e.detail; maps.forEach(function (r) { applyRegion(r, e.detail); }); });
  doc.addEventListener("gs:mapready", function (e) { if (lastRegion) applyRegion(e.detail, lastRegion); });
  // a guide's map beside its text follows the section being read (site.js gs:focus {ids}): that section's places
  // are lit (.on), the others step back (.dim), and the map moves to them; no ids = every place, the whole frame.
  // Reduced motion: the same view, without the flight.
  var lastFocus = null;
  function applyFocus(r, ids) {
    if (!r.byId || !r.data.guide) return;
    var lls = [];
    Object.keys(r.byId).forEach(function (id) {
      var mk = r.byId[id], on = ids.indexOf(id) > -1;
      mk._el.classList.toggle("on", on); mk._el.classList.toggle("dim", ids.length > 0 && !on);
      mk.setZIndex(on ? 1000 : 20);
      if (on) lls.push(mk._ll);
    });
    var target = lls.length ? lls : r.frame;
    if (target && target.length) r.g.fit(target, [56, 56, 56, 56], 5, true);
  }
  doc.addEventListener("gs:focus", function (e) { lastFocus = (e.detail && e.detail.ids) || []; maps.forEach(function (r) { applyFocus(r, lastFocus); }); });
  doc.addEventListener("gs:mapready", function (e) { if (lastFocus && lastFocus.length) applyFocus(e.detail, lastFocus); });
  win.addEventListener("resize", function () { maps.forEach(listQuiet); }); // the list shows or hides beside the map at 1024px
  // listRefit: a list map beside its list was framed in its part in the window (listView, r.hb); once the page has
  // scrolled more of the box in (the sticky box all in view), its places are framed again in what is seen now — unless
  // the reader has moved the map since (g.moved). QA 2026-10-19 QA-40: framed while the box's lower half was below the
  // window, the markers stayed in its top third once the box was all in view
  var refitT = 0;
  win.addEventListener("scroll", function () {
    clearTimeout(refitT);
    refitT = setTimeout(function () {
      maps.forEach(function (r) {
        if (!r.data.list || r.hb == null || r.g.moved || !visible(r.el) || r.el.getBoundingClientRect().top < 0) return;
        var hb = besideList() ? Math.max(0, hiddenBelow(r.el)) : 0;
        if (r.hb - hb < 48) return;   // more of it in view (scrolled back out, it keeps its frame: the zoom anchor)
        var v = listView(r);
        r.g.view(v.c, v.lv, true);
      });
    }, 200);
  }, { passive: true });
  win.GSMapsReady = function (fn) { maps.forEach(fn); doc.addEventListener("gs:mapready", function (e) { fn(e.detail); }); };
  // a map box a script adds later (the course planner's day map, plan.js): built at once, the SDK after 'load'
  win.GSMapStart = function (el) { el.setAttribute("data-lenis-prevent", ""); start(el); };

  var els = Array.prototype.slice.call(doc.querySelectorAll(".map[data-points], .map[data-map]"));
  if (!els.length) return;
  els.forEach(function (el) { el.setAttribute("data-lenis-prevent", ""); });
  function fail(el) {
    el._gs = 0;
    el.classList.add("map-failed");
    doc.dispatchEvent(new CustomEvent("gs:mapfail", { detail: { el: el } }));   // a list page goes back to its list
    var o = el.querySelector(".map-off");
    if (o) o.textContent = W.fail || (EN ? "The map could not be loaded." : "지도를 불러오지 못했습니다.");
  }
  function start(el) {
    if (el._gs) return;
    el._gs = 1;
    // the box's own text says the page lists the same places (for a reader without the map); drawing starts now
    var o = el.querySelector(".map-off");
    if (o) o.textContent = W.load || (EN ? "Loading the map." : "지도를 불러오는 중입니다.");
    afterLoad(function () {
      load(el).then(function () { if (!build(el)) el._gs = 0; }).catch(function () { fail(el); });
    });
  }
  if ("IntersectionObserver" in win) {
    var io = new IntersectionObserver(function (es) {
      es.forEach(function (en) { if (en.isIntersecting && visible(en.target)) { io.unobserve(en.target); start(en.target); } });
    }, { rootMargin: "400px 0px" });
    els.forEach(function (el) { io.observe(el); });
  } else els.forEach(start);
  doc.addEventListener("gs:showmap", function () {
    setTimeout(function () {
      els.forEach(function (el) { if (visible(el)) start(el); });
      maps.forEach(function (r) {
        listQuiet(r);
        if (!visible(r.el)) return;
        r.g.relayout();
        if (r.showHome) r.showHome(false);
        else if (r.data.list) { var v = listView(r); r.g.view(v.c, v.lv, false); }
        else if (r.data.all && lastRegion && lastRegion.region) applyRegion(r, lastRegion); // /map/: the chosen 권역 stays framed
        else if (r.frame) fitVisible(r.g, r.frame, 28);
      });
    }, 30);
  });
})();
