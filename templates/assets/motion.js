/* Motion layer, Apple direction: restrained, 0.5–1.1s, cubic-bezier(.28,.11,.32,1); progressive
   enhancement. site.js attaches this file after the window 'load' event (or 4s), never under reduced motion; a page
   may also load it with `defer` (it then waits for 'load' itself). The HTML is complete and in its final state
   without it. Libraries (GSAP + ScrollTrigger, SplitText only when a split heading exists, Lenis only on a desktop
   fine pointer) are fetched only then, so they never compete with the first screen.

   RULES
   - prefers-reduced-motion: this file returns at once — nothing loads, nothing moves (the CSS stills itself).
   - First screen: no element whose top is inside the first viewport when the libraries arrive ever gets a
     starting state (offset, clip, opacity, zero). The only first-screen motion is the home opening's cross-fade
     (one photo is always fully visible; pause button), its KOGL-1 photo pushing in 1 → 1.06 with the reader's own
     scroll (identity at the top), and the island row's KOGL-1 drift, which also moves only with the reader's own
     horizontal scroll (identity at rest). Text is never moved, faded or blurred over a photo.
   - Licence: only KOGL-1 photos (data-kogl="1" on the image or an ancestor; class t1 also counts) are scaled,
     zoomed or panned. A tile holding any other photo only fades (it never rises: the photo would move).
   - No pins, no scroll-jacking: the home story is a CSS sticky stage (css/40-showcase.css .is-staged) and the
     scroll position picks its chapter; Lenis smooths the wheel but never changes the distance; keyboard, anchors
     and maps stay native.

   HOOKS (templates opt in with these attributes or classes)
   Below the fold only:
     [data-split]                 heading, opt-in: masked line rise (SplitText, fetched only when such a heading is
                                  below the first screen; yPercent 110 → 0, 0.5s, 40ms stagger). A first-screen
                                  heading carrying it is left alone
     REVEAL (list in init) and [data-reveal]
                                  tiles and rows fade in and rise 28px in batches (0.9s, 60ms stagger; a guide's
                                  paragraphs rise 12px, each paragraph as one); a tile holding a photo that is not
                                  KOGL-1 only fades. Rows moved on screen by a filter
                                  (gs:filter / gs:showmap / gs:region) are revealed at once (sweep)
     [data-reveal-ph]             photo figure outside a REVEAL tile and outside the story: fades in; a KOGL-1
                                  picture inside its frame ([data-ph-frame], .ph-frame, .pc-frame, .st-frame)
                                  settles 1.06 → 1 at the same time
     [data-numroll]               a figure (guide answer card, present.rich): its own digits roll into place once it
                                  scrolls in (never a count from 0); the plain text is restored afterwards
   Home opening (first screen; ui.showcase):
     [data-hero]                  section; gets .is-live after load, .is-paused when paused (site.js)
       [data-slide]               slides; the first has class is-on in the HTML. Slides 2..n use data-src /
                                  data-srcset (_media.html.j2 picture(..., lazy_src=true)); loaded after 'load'
       [data-dot]                 one dot per slide (.is-on), [data-hero-i] counter text ("1", or "01" when the
                                  HTML prints two digits); [data-hero-bars] > * progress marks work the same way
       [data-cap]                 one credit line per slide outside the slides, .is-on with its slide (a caption
                                  inside the slide, .op-cap, follows it by itself)
       [data-hero-zoom]           frame whose KOGL-1 img pushes in 1 → 1.06 with the scroll (scrubbed)
       [data-hero-pause]          button: site.js toggles [data-hero].is-paused + aria-pressed from the first
                                  paint; this file only reads .is-paused (no cross-fade while it is set)
   Home story (below the fold; desktop ≥1024px):
     [data-story]                 section; gets .is-staged. Inside: [data-stage] (the 250vh sticky stage),
                                  [data-ch] chapters (.st-ph photo, .is-on for the chapter read; photo k fades in over
                                  the first 20% of its segment over the previous one, which stays fully visible;
                                  KOGL-1 photos settle 1.08 → 1, any other photo never scales), [data-roll] the big
                                  year (digit roll), [data-roll-fig] figures that roll in with their chapter,
                                  [data-rail] button (aria-current="step"; a press scrolls to that chapter).
                                  Phones / first screen: the story stays a plain list
   Carousels:
     [data-gallery] [data-gal-view] [data-drift] img
                                  KOGL-1 images translate ±4% inside their frames as the row is scrolled
                                  (the buttons, [data-gal-nav], are site.js's)
   Scrolling:
     [data-lenis-prevent]         Lenis leaves wheel/touch inside alone (maps get it from map.js; the menu panel and
                                  the filter rows .f-row are left alone too). In-page anchors scroll below the
                                  masthead (--mh-s, default 52px) and move the focus to the target.

   STATE CLASSES on <html>: has-motion (libraries running), cv-off (content-visibility lifted for measuring),
   lenis (Lenis active). Events: listens to gs:menu {open} from site.js (Lenis stops while the menu is open). */
(function () {
  "use strict";
  var win = window, doc = document, root = doc.documentElement;
  if (!win.matchMedia || win.matchMedia("(prefers-reduced-motion: reduce)").matches) return;
  var self = doc.currentScript && doc.currentScript.src;
  var VENDOR = self ? self.replace(/[^/]*$/, "") + "vendor/" : "/assets/vendor/";
  var wideQ = win.matchMedia("(min-width: 1024px)");
  var fine = win.matchMedia("(hover: hover) and (pointer: fine)").matches;

  function all(sel, el) { return Array.prototype.slice.call((el || doc).querySelectorAll(sel)); }
  // strictly below the first screen right now: anything already seen is never touched (no tolerance: a row whose
  // top edge shows even 2px at the bottom of the window is on the first screen and keeps its final state)
  function below(el) { return el.getBoundingClientRect().top >= win.innerHeight; }
  function k1(el) {
    var x = el && el.closest ? el.closest("[data-kogl]") : null;
    if (x) return x.getAttribute("data-kogl") === "1";
    var img = el && el.querySelector ? el.querySelector("[data-kogl]") : null;
    if (img) return img.getAttribute("data-kogl") === "1";
    return !!(el && el.closest && el.closest(".t1"));
  }
  function load(files, done) {
    var left = files.length;
    if (!left) return done();
    files.forEach(function (f) {
      var s = doc.createElement("script");
      s.src = VENDOR + f; s.async = false; // keeps order without blocking the parser
      s.onload = s.onerror = function () { if (--left === 0) done(); };
      doc.head.appendChild(s);
    });
  }
  function mastH() { return parseFloat(getComputedStyle(root).getPropertyValue("--mh-s")) || 52; }
  function bez(x1, y1, x2, y2) { // a cubic-bezier easing for GSAP without CustomEase
    return function (t) {
      var lo = 0, hi = 1, x, m;
      for (var i = 0; i < 24; i++) { m = (lo + hi) / 2; x = 3 * (1 - m) * (1 - m) * m * x1 + 3 * (1 - m) * m * m * x2 + m * m * m; if (x < t) lo = m; else hi = m; }
      m = (lo + hi) / 2; return 3 * (1 - m) * (1 - m) * m * y1 + 3 * (1 - m) * m * m * y2 + m * m * m;
    };
  }
  var easeApple = bez(.28, .11, .32, 1), easeLine = bez(.16, 1, .3, 1);

  // ------------------------------------------------------------ home opening: cross-fade (no library)
  function hero() {
    var box = doc.querySelector("[data-hero]");
    if (!box) return;
    var slides = all("[data-slide]", box), bars = all("[data-hero-bars] > *, .hero-bars > i", box);
    var dots = all("[data-dot]", box);
    var caps = all("[data-cap]", box); // one credit line per slide, outside the slides
    var counter = box.querySelector("[data-hero-i]");
    var two = counter && counter.textContent.trim().length > 1;
    var HOLD = 7000, FADE = 1800, idx = 0, inView = true, busy = false;
    var paused = function () { return box.classList.contains("is-paused"); }; // site.js owns the pause button
    box.style.setProperty("--hero-hold", HOLD / 1000 + "s");
    box.classList.add("is-live");
    slides.slice(1).forEach(function (s) { // photos 2..n start loading only now
      all("[data-srcset]", s).forEach(function (x) { x.srcset = x.getAttribute("data-srcset"); x.removeAttribute("data-srcset"); });
      all("img[data-src]", s).forEach(function (x) { x.src = x.getAttribute("data-src"); x.removeAttribute("data-src"); });
    });
    function ready(slide) {
      var img = slide.querySelector("img");
      if (!img) return Promise.resolve(true);
      if (img.complete && img.naturalWidth) return Promise.resolve(true);
      return img.decode ? img.decode().then(function () { return true; }, function () { return false; }) : Promise.resolve(img.complete);
    }
    function step() {
      if (busy || paused() || !inView || doc.hidden || slides.length < 2) return;
      var prev = slides[idx], nIdx = (idx + 1) % slides.length, next = slides[nIdx];
      busy = true;
      ready(next).then(function (ok) {
        if (!ok || paused()) { busy = false; return; } // a photo that failed to load is skipped this round
        // the new slide fades in OVER the current one, which stays fully opaque underneath
        next.classList.add("is-in");
        next.getBoundingClientRect();
        win.requestAnimationFrame(function () { next.classList.add("is-show"); });
        idx = nIdx;
        bars.forEach(function (b, k) { b.classList.toggle("is-on", k === idx); });
        dots.forEach(function (d, k) { d.classList.toggle("is-on", k === idx); });
        caps.forEach(function (c, k) { c.classList.toggle("is-on", k === idx); }); // the credit follows its photo
        if (counter) counter.textContent = two ? ("0" + (idx + 1)).slice(-2) : String(idx + 1);
        setTimeout(function () {
          next.classList.add("is-on"); next.classList.remove("is-in", "is-show");
          prev.classList.remove("is-on");
          busy = false;
        }, FADE + 50);
      });
    }
    if ("IntersectionObserver" in win) {
      new IntersectionObserver(function (es) { inView = es[0].isIntersecting; box.classList.toggle("is-offscreen", !inView); }).observe(box);
    }
    if (slides.length > 1) setInterval(step, HOLD);
  }

  // ------------------------------------------------------------ 1. headings: masked line rise
  function splitHeads(g, els) {
    if (!win.SplitText || !els.length) return;
    g.registerPlugin(win.SplitText);
    els.forEach(function (el) {
      win.SplitText.create(el, {
        type: "lines", mask: "lines", linesClass: "split-line", autoSplit: true,
        onSplit: function (s) {
          return g.from(s.lines, { yPercent: 110, duration: 0.5, ease: easeLine, stagger: 0.04,
            scrollTrigger: { trigger: el, start: "top 85%", once: true } });
        }
      });
    });
  }

  // ------------------------------------------------------------ 2. tiles rise into place in batches
  var pending = [];
  function show(g, batch) {
    batch = batch.filter(function (el) { return pending.indexOf(el) > -1; }); // each element is revealed once
    if (!batch.length) return;
    pending = pending.filter(function (el) { return batch.indexOf(el) < 0; });
    g.to(batch, { opacity: 1, y: 0, duration: 0.9, ease: easeApple, stagger: Math.min(0.06, 0.5 / batch.length),
      overwrite: true, clearProps: "transform,opacity" });
  }
  function reveals(g, ST, els) {
    if (!els.length) return;
    pending = pending.concat(els);
    // a tile holding a photo that is not KOGL-1 only fades: the photo itself is never moved
    var still = function (el) { return !!el.querySelector('img[data-kogl]:not([data-kogl="1"])'); };
    // a guide's paragraphs and bullets rise 12px (text: a short way), tiles 28px
    var rise = function (el) { return still(el) ? 0 : el.matches(".gd-pts, .gd-p, .gd-sec-n") ? 12 : 28; };
    els.forEach(function (el) { g.set(el, { opacity: 0, y: rise(el) }); });
    ST.batch(els, { start: "top 94%", once: true, onEnter: function (batch) { show(g, batch); } });
  }
  // rows moved by a filter (or a layout change) onto or above the screen are revealed now: a refresh alone does
  // not fire their onEnter, and a row must never be left invisible
  function sweep(g) {
    var due = pending.filter(function (el) {
      if (el.hidden || !el.getClientRects().length) return false;
      return el.getBoundingClientRect().top < win.innerHeight * 0.94;
    });
    if (due.length) show(g, due);
  }

  // ------------------------------------------------------------ 3. photos outside tiles: fade, KOGL-1 settles
  function photos(g, els) {
    els.forEach(function (fig) {
      var frame = fig.querySelector("[data-ph-frame], .ph-frame, .pc-frame, .st-frame") || fig;
      var img = frame.querySelector("img");
      var tl = g.timeline({ scrollTrigger: { trigger: fig, start: "top 96%", once: true } });
      tl.fromTo(fig, { opacity: 0 }, { opacity: 1, duration: 0.8, ease: easeApple, clearProps: "opacity" });
      if (img && k1(img)) tl.fromTo(img, { scale: 1.06 }, { scale: 1, duration: 1.1, ease: easeApple, clearProps: "transform" }, 0);
    });
  }

  // ------------------------------------------------------------ 4. the home photo pushes in with the scroll (KOGL-1)
  function heroZoom(g) {
    var imgs = all("[data-hero-zoom] img").filter(k1);
    if (!imgs.length) return;
    var box = imgs[0].closest("[data-hero]") || imgs[0].parentNode;
    // identity at the top of the page; 880px × 1.06 stays under the 940px source
    g.fromTo(imgs, { scale: 1 }, { scale: 1.06, ease: "none",
      scrollTrigger: { trigger: box, start: 0, end: "bottom top", scrub: 0.6 } });
  }

  // ------------------------------------------------------------ 5. the story stage (desktop): CSS sticky pins it,
  // the scroll position picks the chapter
  function roller(el) { // digit roll: only changed positions move (0.7s, 40ms stagger); a year never passes
    var cur = el.textContent;            // through a value it does not have
    el.setAttribute("aria-hidden", "true");
    function span(text, cls) { var c = doc.createElement("span"); c.className = cls; var i = doc.createElement("span"); i.textContent = text; c.appendChild(i); return c; }
    function render(text) { el.innerHTML = ""; text.split("").forEach(function (ch) { el.appendChild(span(ch, "rd")); }); }
    function slide(old, nw, delay) {
      nw.style.position = "absolute"; nw.style.left = "0"; nw.style.top = "0"; nw.style.transform = "translateY(100%)";
      win.requestAnimationFrame(function () {
        old.style.transition = nw.style.transition = "transform .7s cubic-bezier(.65,0,.35,1) " + delay;
        old.style.transform = "translateY(-100%)"; nw.style.transform = "translateY(0)";
      });
    }
    render(cur);
    return function (next) {
      if (next === cur) return;
      var a = cur.split(""), b = next.split("");
      if (!/^\d+$/.test(next) || !/^\d+$/.test(cur) || a.length !== b.length) { // a year to a word: one token rolls
        el.innerHTML = "";
        var c = span(cur, "rd" + (/^\d+$/.test(next) ? "" : " rd-word")), n = doc.createElement("span");
        n.textContent = next; c.style.position = "relative"; c.appendChild(n); el.appendChild(c);
        slide(c.firstChild, n, "0ms");
        setTimeout(function () { render(next); if (!/^\d+$/.test(next)) el.firstChild.className = "rd rd-word"; }, 760);
        cur = next; return;
      }
      var boxes = all(".rd", el), k = 0;
      b.forEach(function (ch, i) {
        if (a[i] === ch) return;
        var box = boxes[i], old = box.firstChild, nw = doc.createElement("span");
        nw.textContent = ch; box.style.position = "relative"; box.appendChild(nw);
        slide(old, nw, (k++ * 40) + "ms");
        setTimeout(function () { if (old.parentNode) old.remove(); nw.style.position = ""; nw.style.transform = ""; nw.style.transition = ""; }, 760 + k * 40);
      });
      cur = next;
    };
  }
  function story(g, ST, lenis) {
    var box = doc.querySelector("[data-story]");
    if (!box || !wideQ.matches || !below(box)) return;
    var stage = box.querySelector("[data-stage]"), chs = all("[data-ch]", box), n = chs.length;
    if (!stage || n < 2) return;
    box.classList.add("is-staged");
    var phs = chs.map(function (c) { return c.querySelector(".st-ph"); });
    // only a KOGL-1 photo scales; any other photo only fades
    var imgs = phs.map(function (p) { var i = p && p.querySelector("img"); return i && k1(i) ? i : null; });
    var bigEl = box.querySelector("[data-roll]"), roll = bigEl ? roller(bigEl) : null;
    var rail = all("[data-rail] button", box), active = -1;
    var blank = function (s) { return s.replace(/./g, " "); };
    var figs = chs.map(function (c) { return all("[data-roll-fig]", c).map(function (el) { var fin = el.textContent; return { r: roller(el), fin: fin }; }); });
    figs.forEach(function (arr) { arr.forEach(function (f) { f.r(blank(f.fin)); }); });
    var bigs = chs.map(function (c) { var y = c.querySelector(".st-year .num"); return y ? y.textContent.trim() : ""; });
    function setActive(i) {
      if (i === active) return;
      var prev = active; active = i;
      chs.forEach(function (c, k) { c.classList.toggle("is-on", k === i); });
      rail.forEach(function (b, k) { if (k === i) b.setAttribute("aria-current", "step"); else b.removeAttribute("aria-current"); });
      if (roll && bigs[i]) roll(bigs[i]);
      figs[i].forEach(function (f, k) { setTimeout(function () { f.r(f.fin); }, 120 + k * 80); });
      if (prev >= 0 && prev !== i) figs[prev].forEach(function (f) { f.r(blank(f.fin)); });
    }
    phs.forEach(function (ph, k) { if (ph) ph.style.zIndex = String(k + 1); });
    function apply(p) {
      var seg = 1 / n, i = Math.min(n - 1, Math.floor(p / seg + 1e-6)), capAt = 0;
      phs.forEach(function (ph, k) {
        if (!ph) return;
        var o = k === 0 ? 1 : Math.max(0, Math.min(1, (p - k * seg) / (seg * 0.2)));
        ph.style.opacity = o.toFixed(3);
        if (o >= 0.5) capAt = k; // the credit belongs to the photo (mostly) in view, never to one fading out
        if (imgs[k]) {
          var q = Math.max(0, Math.min(1, (p - (k - 0.2) * seg) / (seg * 1.2)));
          imgs[k].style.transform = "scale(" + (1.08 - 0.08 * q).toFixed(4) + ")";
        }
      });
      phs.forEach(function (ph, k) { if (ph) ph.classList.toggle("cap-on", k === capAt); });
      setActive(i);
    }
    var trig = ST.create({ trigger: stage, start: "top top", end: "bottom bottom", onUpdate: function (s) { apply(s.progress); } });
    apply(0);
    rail.forEach(function (b, k) {
      b.addEventListener("click", function () {
        var y = trig.start + (trig.end - trig.start) * (k / n + 0.02) + 1;
        if (lenis) lenis.scrollTo(y, { duration: 0.9 }); else win.scrollTo({ top: y, behavior: "smooth" });
      });
    });
  }

  // ------------------------------------------------------------ 6. key figures roll in (the guide's answer card)
  // [data-numroll] below the first screen (present.rich marks the figures that have digits): once the figure scrolls
  // in, each of its own digits rises into place from its baseline (0.6s, 40ms stagger), an odometer settling on the
  // value. Only the figure's own digits are ever drawn — never a count from 0, which would show numbers that are not
  // in the data — and the DOM text stays the figure (the digits are only wrapped). Nothing around it moves: the
  // figure does not wrap while it rolls (white-space: nowrap — the wrapped digits would otherwise open line breaks
  // inside it: '만 3 / 6개월'), each digit is clipped to its own band (.rl, css/72-guide.css: never below the
  // baseline), and a figure whose wrapping would move it to another line, or move the text after it more than the
  // kerning lost around its digits, is left as plain text (measured before and after). A figure broken over two
  // lines is left as it is; the plain text is put back when the roll ends. ([data-roll] is the home story's year,
  // section 5.)
  function numRolls(g, els) {
    var range = doc.createRange();
    var at = function (el) { // where the figure and the first character after it sit
      var r = el.getBoundingClientRect(), n = el.nextSibling, q = null;
      while (n && n.nodeType === 3 && !n.data.length) n = n.nextSibling;
      if (n) {
        if (n.nodeType === 3) { range.setStart(n, 0); range.setEnd(n, 1); } else range.selectNode(n);
        q = range.getClientRects()[0] || null;
      }
      return [r.left, r.top, r.width, q ? q.left : 0, q ? q.top : 0, el.parentNode.getBoundingClientRect().height];
    };
    els.forEach(function (el) {
      if (el.getClientRects().length !== 1) return;
      var text = el.textContent, digits = [], before = at(el);
      var plain = function () { el.textContent = text; el.style.whiteSpace = ""; };
      el.style.whiteSpace = "nowrap";
      el.textContent = "";
      text.split("").forEach(function (ch) {
        if (!/\d/.test(ch)) { el.appendChild(doc.createTextNode(ch)); return; }
        var o = doc.createElement("span"), i = doc.createElement("span");
        o.className = "rl"; i.className = "rl-i"; i.textContent = ch;
        o.appendChild(i); el.appendChild(o); digits.push(i);
      });
      // the same line, the same place, the same paragraph height; only a sliver of width may change (the kerning
      // around the wrapped digits, ≤1.5px: '20,900원' is ~1px wider) — anything more and the figure stays plain
      var after = at(el), tol = [0.5, 0.5, 1.5, 1.5, 0.5, 0.5];
      if (el.getClientRects().length !== 1 || before.some(function (v, k) { return Math.abs(v - after[k]) > tol[k]; })) { plain(); return; }
      g.set(digits, { yPercent: 110 });
      g.to(digits, { yPercent: 0, duration: 0.6, ease: easeLine, stagger: 0.04,
        scrollTrigger: { trigger: el, start: "top 90%", once: true }, onComplete: plain });
    });
  }

  // ------------------------------------------------------------ 7. carousels: KOGL-1 photos drift with the row
  // (no library). Each image is at rest where the page put it and moves only with the reader's own scroll of the
  // row (at most ±4%, inside the 112%-wide KOGL-1 frame of css/40-showcase.css)
  function drift() {
    all("[data-gallery] [data-gal-view]").forEach(function (view) {
      var imgs = all("[data-drift] img", view).filter(k1);
      if (!imgs.length) return;
      var tick = false;
      var pos = function (img) {
        var vr = view.getBoundingClientRect(), r = img.closest("[data-drift]").getBoundingClientRect(); // <picture> is display: contents
        return (r.left + r.width / 2 - (vr.left + vr.width / 2)) / (vr.width || 1);
      };
      var rest = imgs.map(pos);
      var run = function () {
        tick = false;
        imgs.forEach(function (img, k) {
          var d = Math.max(-4, Math.min(4, -(pos(img) - rest[k]) * 4));
          img.style.transform = d ? "translate3d(" + d.toFixed(2) + "%,0,0)" : "";
        });
      };
      view.addEventListener("scroll", function () { if (!tick) { tick = true; win.requestAnimationFrame(run); } }, { passive: true });
      win.addEventListener("resize", function () { // a new layout is a new rest position
        imgs.forEach(function (img) { img.style.transform = ""; });
        rest = imgs.map(pos);
      });
    });
  }

  // ------------------------------------------------------------ smooth wheel scrolling (desktop fine pointer only)
  function smooth(g, ST) {
    if (!win.Lenis) return null;
    var lenis = new win.Lenis({ lerp: 0.12, smoothWheel: true, syncTouch: false,
      prevent: function (n) { return !!(n.closest && n.closest(".map, [data-lenis-prevent], .menu-panel, .f-row")); } });
    lenis.on("scroll", ST.update);
    g.ticker.add(function (t) { lenis.raf(t * 1000); });
    g.ticker.lagSmoothing(0);
    // in-page anchors: to the target below the masthead, then the focus moves there (keyboard users land on it)
    doc.addEventListener("click", function (e) {
      var a = e.target.closest && e.target.closest('a[href^="#"]');
      if (!a || e.defaultPrevented || e.button || e.metaKey || e.ctrlKey || e.shiftKey || e.altKey) return;
      var id = decodeURIComponent(a.getAttribute("href").slice(1)), t = id && doc.getElementById(id);
      if (!t) return;
      e.preventDefault();
      lenis.scrollTo(t, { offset: -(mastH() + 16), duration: 0.9, onComplete: function () {
        if (!t.hasAttribute("tabindex") && !/^(A|BUTTON|INPUT|SELECT|TEXTAREA|SUMMARY)$/.test(t.tagName)) t.setAttribute("tabindex", "-1");
        t.focus({ preventScroll: true });
      } });
      try { history.pushState(null, "", "#" + encodeURIComponent(id)); } catch (err) { /* file:// */ }
    });
    doc.addEventListener("gs:menu", function (e) { if (e.detail && e.detail.open) lenis.stop(); else lenis.start(); });
    win.__lenis = lenis;
    return lenis;
  }

  function init() {
    if (init.done) return;
    init.done = true;
    hero();
    drift();
    root.classList.add("cv-off"); // lift content-visibility so ScrollTrigger measures true heights
    var REVEAL = ".answers > li, .cards > li, .evrows > .evr, .regs, .reg-map, .co-teaser, .v-feat, .v-rows, " +
      ".v-chips, .gal-track > li, .gitem, .board, .stop-body, .week-scroll, .near-cols2 > .tile, .facts-more, .pl-side, " +
      ".place-map, .faq .qa, .vids > .vid, .ev-annual, .tickets > li, .prog, .src-dl, .lines > .line-row, .strip-line, " +
      ".map-side, .co-map, .gd-map, .ans-more, .gd-sec-n, .gd-pts, .gd-p, .gd-sec .mcs-box, .gd-sec .mcr, [data-reveal]";
    var outside = function (el) { return !el.closest("[data-story]"); };
    var T = {
      split: all("[data-split]").filter(below),
      reveal: all(REVEAL).filter(below).filter(outside),
      photo: all("[data-reveal-ph]").filter(below).filter(function (el) { return outside(el) && !el.parentNode.closest(REVEAL); }),
      numroll: all("[data-numroll]").filter(below)
    };
    var zoom = all("[data-hero-zoom] img").filter(k1).length > 0;
    var staged = wideQ.matches && !!doc.querySelector("[data-story] [data-stage] [data-ch]");
    var useLenis = fine && wideQ.matches;
    var need = T.split.length || T.reveal.length || T.photo.length || T.numroll.length || zoom || staged;
    var files = [];
    if (need || useLenis) files.push("gsap/gsap.min.js", "gsap/ScrollTrigger.min.js");
    if (T.split.length) files.push("gsap/SplitText.min.js");
    if (useLenis) {
      var css = doc.createElement("link");
      css.rel = "stylesheet"; css.href = VENDOR + "lenis/lenis.css";
      doc.head.appendChild(css);
      files.push("lenis/lenis.min.js");
    }
    if (!files.length) return;
    load(files, function () {
      var g = win.gsap, ST = win.ScrollTrigger;
      if (!g || !ST) return;
      g.registerPlugin(ST);
      var go = function () {
        var keep = function (arr) { return arr.filter(below); }; // re-check: the reader may have scrolled meanwhile
        root.classList.add("has-motion");
        var lenis = useLenis ? smooth(g, ST) : null;
        story(g, ST, lenis);
        var off = function (el) { return !el.closest(".is-staged"); };
        splitHeads(g, keep(T.split));
        reveals(g, ST, keep(T.reveal).filter(off));
        photos(g, keep(T.photo).filter(off));
        if (zoom) heroZoom(g);
        numRolls(g, keep(T.numroll));
        ST.refresh();
        // filters, the list map and 권역 tabs move rows: measure again, so a row waiting for its reveal that is now
        // on screen is revealed (and never left invisible)
        var again = null;
        ["gs:filter", "gs:showmap", "gs:region"].forEach(function (ev) {
          doc.addEventListener(ev, function () {
            cancelAnimationFrame(again);
            again = requestAnimationFrame(function () { ST.refresh(); sweep(g); });
          });
        });
      };
      if (doc.fonts && doc.fonts.ready) doc.fonts.ready.then(go); else go();
    });
  }
  if (doc.readyState === "complete") init();
  else { win.addEventListener("load", init); setTimeout(init, 4000); }
})();
