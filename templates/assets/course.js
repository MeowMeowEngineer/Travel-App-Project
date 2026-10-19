/* 군산 여행 — course page: the one motion that carries data (attached by site.js when [data-course] exists).
   The stop being read (the one crossing a band 40–55% down the viewport) drives:
   - the stop band: [data-fill] grows to that stop (vertical on desktop ≥1024px, to n / N of a thin bar on phones);
     GSAP .5s power2.out when motion is allowed (fetched here, after load), set directly otherwise;
   - the live line [data-live]: "지금 보는 경유지 B05" (desktop only) + "5 / 11 · 동국사" (its first markup returns
     above stop 1);
   - the active stop: .is-active on [data-stop], aria-current="step" on its [data-step] link;
   - the map (map.js course map, Kakao Maps): the active marker .on, the passed ones .past (reg.paint); on desktop
     the map stays while that marker is in view and otherwise moves to the view that holds it (reg.showAround), then
     the passed part of the straight-line route draws itself (reg.progressTo: the blue line grows along it). Reduced
     motion: no flight, no drawing — the state is set at once.

   MARKUP
     [data-course]                     the course article
       [data-stop="n"]                 each stop block (n = 1..N); inside: .code and .board-name (or
                                       [data-stop-code] / [data-stop-name]) for the live line
       a[data-step="n"]                band links; their <li> carries --y (0–1: straight-line distance share on
                                       desktop; phones space them evenly). On phones the band is a progress
                                       display, not a tab stop (tabindex=-1 below 1024px)
       [data-fill]                     the band's fill
       [data-live]                     the live line (aria-live="polite" in the markup)
   Without JS the page is complete: the stops, the band links and the map's text equivalent. */
(function () {
  "use strict";
  var doc = document, win = window, root = doc.querySelector("[data-course]");
  if (!root || !("IntersectionObserver" in win)) return;
  var reduce = win.matchMedia("(prefers-reduced-motion: reduce)").matches;
  var wideQ = win.matchMedia("(min-width: 1024px)");
  var VENDOR = ((doc.currentScript && doc.currentScript.src) || "/assets/course.js").replace(/[^/]*$/, "") + "vendor/";
  var stops = Array.prototype.slice.call(root.querySelectorAll("[data-stop]"));
  var links = Array.prototype.slice.call(root.querySelectorAll("[data-step]"));
  var fill = root.querySelector("[data-fill]"), live = root.querySelector("[data-live]");
  var initial = live ? live.innerHTML : "", total = stops.length, active = 0, drawn = 0, gsapReady = null, mapReg = null;
  if (!total) return;

  // phones: the band is a progress display, not a row of tab stops
  var syncBand = function () { links.forEach(function (a) { if (wideQ.matches) a.removeAttribute("tabindex"); else a.setAttribute("tabindex", "-1"); }); };
  syncBand();
  if (wideQ.addEventListener) wideQ.addEventListener("change", syncBand);

  function getGsap() {
    if (reduce) return Promise.resolve(null);
    if (win.gsap) return Promise.resolve(win.gsap);
    if (gsapReady) return gsapReady;
    gsapReady = new Promise(function (res) {
      var go = function () {
        if (win.gsap) return res(win.gsap);
        var s = doc.createElement("script");
        s.src = VENDOR + "gsap/gsap.min.js";
        s.onload = function () { res(win.gsap || null); };
        s.onerror = function () { res(null); };
        doc.head.appendChild(s);
      };
      if (doc.readyState === "complete") go(); else win.addEventListener("load", go); // never before the page
    });
    return gsapReady;
  }
  function setFill(frac) {
    if (!fill) return;
    var prop = wideQ.matches ? "height" : "width", val = (frac * 100).toFixed(2) + "%";
    fill.style[wideQ.matches ? "width" : "height"] = "";
    if (reduce || !win.gsap) { fill.style[prop] = val; if (!reduce) getGsap(); return; }
    var o = { duration: 0.5, ease: "power2.out", overwrite: true };
    o[prop] = val;
    win.gsap.to(fill, o);
  }

  function mapTo(n) {
    var r = mapReg;
    if (!r) return;
    r.activeN = n;
    if (r.paint) r.paint(); // map.js: the marker .on, the earlier ones .past
    var from = drawn;
    drawn = n;
    // the passed part of the straight-line route draws itself from the previous stop to the one being read, after
    // the map has settled (map.js progressTo)
    var draw = function () { if (r.progressTo) r.progressTo(from, n); };
    if (!wideQ.matches || !r.showAround) { draw(); return; } // phones: the map follows the stops; it is not chased
    // desktop: the map stays while the stop being read is in view, and moves to the view that holds it otherwise
    // (map.js showAround); above stop 1 it returns to its first view
    var cancel = r.whenIdle(draw);
    var moves = n === 0 ? (from > 0 && (r.showHome(true), true)) : r.showAround(n);
    if (!moves) { cancel(); draw(); }
  }
  function onMap(r) {
    if (!r || !r.data || !r.data.course) return;
    if (mapReg && root.contains(mapReg.el)) return; // the course's own map wins over any other course map
    mapReg = r;
    if (active) mapTo(active);
  }
  (win.GSMaps || []).forEach(onMap);
  doc.addEventListener("gs:mapready", function (e) { onMap(e.detail); });

  function activate(n) {
    if (n === active) return;
    active = n;
    links.forEach(function (a) { if (+a.getAttribute("data-step") === n) a.setAttribute("aria-current", "step"); else a.removeAttribute("aria-current"); });
    stops.forEach(function (s) { s.classList.toggle("is-active", +s.getAttribute("data-stop") === n); });
    var li = n && links[n - 1] ? links[n - 1].parentNode : null;
    var y = li ? (wideQ.matches ? parseFloat(getComputedStyle(li).getPropertyValue("--y")) || (n - 1) / Math.max(1, total - 1)
      : n / total) : 0;
    setFill(n ? y : 0);
    if (live) {
      if (!n) live.innerHTML = initial;
      else {
        var st = stops[n - 1], code = st.querySelector("[data-stop-code], .code"), name = st.querySelector("[data-stop-name], .board-name");
        var el = function (tag, cls, text) { var e = doc.createElement(tag); e.className = cls; e.textContent = text; return e; };
        live.textContent = "";
        live.appendChild(el("span", "bl-k", "지금 보는 경유지" + (code ? " " + code.textContent.trim() : "")));
        live.appendChild(el("b", "bl-n tn", n + " / " + total));
        live.appendChild(doc.createTextNode(" · "));
        live.appendChild(el("span", "bl-nm", name ? name.textContent.trim() : ""));
      }
    }
    mapTo(n);
  }
  var seen = {};
  var io = new IntersectionObserver(function (es) {
    es.forEach(function (en) { seen[en.target.getAttribute("data-stop")] = en.isIntersecting; });
    var on = Object.keys(seen).filter(function (k) { return seen[k]; }).map(Number);
    if (on.length) activate(Math.min.apply(null, on));
    else if (stops[0].getBoundingClientRect().top > win.innerHeight * 0.45) activate(0);
  }, { rootMargin: "-40% 0px -55% 0px" });
  stops.forEach(function (s) { io.observe(s); });
})();
