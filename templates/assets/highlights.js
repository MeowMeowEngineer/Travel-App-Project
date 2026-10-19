/* 해외에서 본 <city> — the highlights viewer (/abroad/, owner 2026-10-13; templates/_abroad_hl.html.j2). site.js attaches
   this file on the first press of a [data-hl-open=N] link in the [data-hl=URL] row (without JS the link goes to the
   original) and has already started fetching the viewer's markup (window.gsHlData: {"html": "<dialog …>"} from URL,
   written by the build); this file puts the dialog in the page and opens card N (window.gsHlWant); later presses call
   window.gsHl(link). If the markup cannot be had, the link is followed.
     [data-hl-dialog]   <dialog hidden>, opened with showModal(): the page behind is inert, the focus stays inside,
                        Escape closes it. The focus starts on the card and goes back to the link on close.
     [data-hl-slide]    one card at a time (the others hidden); [data-hl-bar] marks how far along, [data-hl-cur]
                        the number. [data-hl-dir=-1|1] previous / next (aria-disabled at the ends, so the focus never
                        drops), the ← → keys and a sideways swipe on a touch screen; [data-hl-close] or a press on the
                        backdrop closes. Card changes are announced (aria-live) after the first one; a card that
                        held the focus hands it to the next.
   CSS slides a new card in, never with reduced motion. A social post's card carries [data-embed]: site.js loads the
   service's official embed when the card is shown (window.gsEmbedWatch) or, with Save-Data, on its button. Lenis
   (motion.js, desktop) stops while the viewer is open. */
(function () {
  "use strict";
  var doc = document, win = window, root = doc.documentElement;
  var row = doc.querySelector("[data-hl]");
  var data = win.gsHlData || (row && win.fetch && win.fetch(row.getAttribute("data-hl")).then(function (r) {
    if (!r.ok) throw new Error("HTTP " + r.status);
    return r.json();
  }));
  function follow() { if (win.gsHlWant) location.href = win.gsHlWant.href; }
  if (!data) return;
  data.then(setup, follow);

  function setup(d) {
    var holder = doc.createElement("div");
    holder.innerHTML = (d && d.html) || "";   // this site's own build output (escaped by the templates), same origin
    var dlg = holder.querySelector("[data-hl-dialog]");
    if (!dlg || typeof dlg.showModal !== "function") { follow(); return; }
    doc.body.appendChild(dlg);
    function all(sel) { return Array.prototype.slice.call(dlg.querySelectorAll(sel)); }
    var slides = all("[data-hl-slide]"), bars = all("[data-hl-bar]");
    var stage = dlg.querySelector("[data-hl-stage]"), cur = dlg.querySelector("[data-hl-cur]");
    var prev = dlg.querySelector('[data-hl-dir="-1"]'), next = dlg.querySelector('[data-hl-dir="1"]');
    if (!slides.length || !stage || !prev || !next) { follow(); return; }
    var at = 0, opener = null;
    all("[data-embed][data-url]").forEach(function (c) { if (win.gsEmbedWatch) win.gsEmbedWatch(c); });

    function show(n, dir) {
      // the focus inside the card being hidden would drop out of the dialog: it moves to the new card
      var refocus = slides.some(function (s) { return !s.hidden && s.contains(doc.activeElement); });
      at = Math.max(0, Math.min(slides.length - 1, n));
      slides.forEach(function (s, k) {
        s.hidden = k !== at;
        s.classList.remove("hl-from-r", "hl-from-l");
      });
      if (dir) slides[at].classList.add(dir > 0 ? "hl-from-r" : "hl-from-l");
      bars.forEach(function (b, k) { b.classList.toggle("is-on", k <= at); });
      if (cur) cur.textContent = String(at + 1);
      prev.setAttribute("aria-disabled", String(at === 0));
      next.setAttribute("aria-disabled", String(at === slides.length - 1));
      stage.scrollTop = 0;
      if (refocus) slides[at].focus();
    }
    function step(d) {
      if (at + d >= 0 && at + d < slides.length) show(at + d, d);
    }
    function open(n, link) {
      opener = link || null;
      stage.setAttribute("aria-live", "off");
      dlg.hidden = false;
      show(n, 0);
      if (!dlg.open) dlg.showModal();
      root.classList.add("hl-open");
      if (win.__lenis) win.__lenis.stop();
      slides[at].focus();
      stage.setAttribute("aria-live", "polite");
    }

    dlg.addEventListener("close", function () {
      dlg.hidden = true;
      root.classList.remove("hl-open");
      if (win.__lenis) win.__lenis.start();
      if (opener && opener.focus) opener.focus();
    });
    dlg.addEventListener("click", function (ev) {
      if (ev.target === dlg) { dlg.close(); return; }        // the box fills the dialog: only the backdrop is the dialog
      var t = ev.target.closest ? ev.target : null;
      if (!t) return;
      if (t.closest("[data-hl-close]")) { dlg.close(); return; }
      var b = t.closest("[data-hl-dir]");
      if (b) step(Number(b.getAttribute("data-hl-dir")));
    });
    doc.addEventListener("keydown", function (ev) {
      if (!dlg.open || ev.altKey || ev.ctrlKey || ev.metaKey || ev.shiftKey) return;
      if (ev.key === "ArrowRight" || ev.key === "ArrowLeft") {
        ev.preventDefault();
        step(ev.key === "ArrowRight" ? 1 : -1);
      }
    });
    // a sideways swipe on a touch screen (the stage is touch-action: pan-y, so up and down still scroll it)
    var x0 = null, y0 = 0;
    stage.addEventListener("pointerdown", function (ev) {
      if (ev.pointerType !== "mouse") { x0 = ev.clientX; y0 = ev.clientY; }
    });
    stage.addEventListener("pointerup", function (ev) {
      if (x0 === null) return;
      var dx = ev.clientX - x0, dy = ev.clientY - y0;
      x0 = null;
      if (Math.abs(dx) > 48 && Math.abs(dx) > Math.abs(dy) * 1.5) step(dx < 0 ? 1 : -1);
    });
    stage.addEventListener("pointercancel", function () { x0 = null; });

    win.gsHl = function (link) { open(Number(link.getAttribute("data-hl-open")) || 0, link); };
    if (win.gsHlWant) {
      var want = win.gsHlWant;
      win.gsHlWant = null;
      win.gsHl(want);
    }
  }
})();
