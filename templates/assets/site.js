/* Site behaviour (progressive enhancement). Loaded with `defer` on every page; every page is complete without
   it. <html class="js"> is set inline in <head>, so JS-only furniture is laid out from the first paint (style.css:
   css/65-states.css and the class rules of the shared macros) and nothing shifts when this runs. Scroll-linked motion lives in motion.js, which this file attaches after
   the window 'load' event (or 4s) unless the reader prefers reduced motion.

   HOOKS (templates opt in with these attributes)
   Page furniture
     html.is-scrolled               set while the page is scrolled (> 8px): the masthead CSS compacts itself
     details[data-menu]             menu (also details.menu): Escape closes it and returns focus to its summary,
                                    an outside click or a followed link closes it; html.menu-open while open;
                                    dispatches gs:menu {open}
     details[data-langmenu]         the language menu: an outside click, a followed link or Escape closes it
     form[data-hs] + [data-hs-open] the site search in the bar: phones open the form over the bar (html.hs-open)
                                    from the '검색' link (a link to /search/ without JS); [data-hs-close], Escape or
                                    an outside press closes it
     [data-show-map]                masthead context link (e.g. '지도'): on screens < 1024px switches the list
                                    to its map view instead of jumping
     [data-sticky]                  desktop sticky column taller than the window: sticks by its bottom edge
     [data-hero-pause] in [data-hero], [data-mq-pause] in [data-marquee]
                                    pause buttons (WCAG 2.2.2), working from the first paint: toggle .is-paused on
                                    the box and aria-pressed; label in [data-lbl] or .lbl (texts from
                                    data-label-play / data-label-pause). CSS stops the CSS motion, motion.js reads
                                    .is-paused (the opening's slides and their credit lines [data-cap] are motion.js's)
   Lists (filters with URL state: ?type=…&region=…&theme=…&check=1&view=map)
     [data-filters]                 filter bar (a `hidden` attribute on it is removed: shown only with JS)
       button[data-f=K][data-v=V]   toggle (aria-pressed); V="" means all. K is any key (type, region, theme …)
       select[data-f=K]             the same as a list
       input[type=checkbox][data-f=check][value=FLAG]   keep items that carry data-FLAG
       button[data-view=list|map]   view switch: [data-view-root] (or .list-grid) gets .show-map
       [data-result]                "label N곳" kept up to date ("(전체 M곳 중)" while filtered)
       [data-filter-count]          the number alone
     items                          [data-filter-item] (or the children of [data-filter-items], or .rec), each
                                    with data-K: one value, a "|a|b|" list or a space-separated list
                                    (data-Ks, e.g. data-themes, also answers key K)
     [data-filter-group]            group (or .lg-group) hidden when none of its items is shown
     [data-empty]                   shown when nothing matches
     [data-f-more] + [data-f-panel] the '필터' button opens the panel of further filters (aria-expanded); the panel
                                    starts open when the URL sets one of its filters; [data-f-badge] counts them
     details[data-map-fold]         folded list map (also .map-fold): opening it draws the map
     row ↔ marker                   an item's id equals its map point's id: hovering/focusing the row lights the
                                    marker (gs:hl); hovering the marker lights the row (.hl, from gs:hlrow)
   Map page
     [data-region-tabs] a[data-region]   (also .region-tabs) 권역 tabs; [data-region-sec=NAME] sections
     [data-kinds] button[data-kind]      kind toggles; rows [data-kind-row=KIND]; [data-dong] (or .dong) groups
     [data-segmap] button[data-view]     list | map on narrow screens: [data-map-grid] (or .map-grid) .show-map
     [data-pt=ID]                        rows that light their marker
   Carousels (Apple galleries: home answers / places / islands, place photos, guide mini cards)
     [data-gallery] [data-gal-view] a native scroll-snap row (.car-track > li, .gal-track > li or .mcs > li); the round
       [data-gal-nav] button[data-dir=-1|1]   buttons move it by one item and are disabled at the ends; a row that
                                    fits gets .no-scroll on [data-gallery]. Without JS the row still scrolls and snaps
                                    (the buttons are hidden: html:not(.js) .car-nav). [data-gal-nav][data-gal-make=
                                    "previous|next"] (empty): this file makes the two buttons (guide section rows)
   Home news (templates/home.html.j2, present.home_news; WAI-ARIA carousel with auto-rotation; one card in view)
     [data-hcar] > [data-hcar-view] a native scroll-snap row of [data-hcar-item] cards (it scrolls without JS; the
                                    controls are hidden then: html:not(.js) .hv-ctl). This file advances it by one card
                                    every 6 s and wraps at the end. Autoplay never runs with reduced motion (the pause
                                    button is then removed: a manual row); it waits while the pointer is over the row,
                                    the tab is hidden or the row is off screen, and stops for good — until the play
                                    button — when focus enters the row, the reader swipes or scrolls it, or presses a
                                    control. [data-hcar-pause] (the first control: label from data-label-pause /
                                    data-label-play, .is-stopped on the box), [data-hcar-dir=-1|1] previous / next
                                    (wrapping), [data-hcar-cur] the number of the card at the row's start; the counter
                                    [data-hcar-count] is aria-live="polite" only while autoplay is stopped. A row that
                                    fits gets .no-scroll (the controls keep their room, hidden). An article's preview
                                    picture (.nc-og) that does not load is removed with its credit line (.nc-cr)
   Guides
     [data-sec=ID][data-pts="a b"]  body sections: the current one marks [data-toc-link=ID] (aria-current) inside
     [data-toc]                     the table of contents, and on ≥1024px tells the map its places (gs:focus {ids}).
                                    html.gd-open after the first painted frame: the sections and the table of contents
                                    stop being skipped (content-visibility, css/72-guide.css), then the tracking starts
     .mcs-view, .gd-toc-l, .mcr     sideways rows: a card or chip reached with Tab is scrolled wholly into its row
   Videos
     [data-v-official] in [data-videos]   '공식 채널만' toggle: .only-official on the box (aria-pressed); the folded
                                    rest of each topic (details.v-more) opens so nothing official stays hidden
     [data-video] > [data-yt=ID]    YouTube facade (button or link): nothing loads from YouTube until it is
                                    pressed; then a youtube-nocookie player replaces it and takes the focus.
                                    data-title gives the player its title. A link keeps working without JS
     [data-embed=SERVICE][data-url] > [data-embed-load], [data-embed-slot]   social posts (/abroad/, place
                                    pages): the service's official embed loads when the card nears the screen
                                    (or the button is pressed: no IntersectionObserver, or Save-Data)
     [data-hl=URL] a[data-hl-open=N]   the highlights row (/abroad/): the circles' pictures (data-src) arrive after
                                    'load'; the first press fetches the viewer's markup (URL) and attaches
                                    highlights.js, which opens card N; each link goes to the original without JS
   Page transitions (cross-document View Transitions; css/60-motion.css holds @view-transition)
     [data-vt]                      the name element inside a link (or the link): it morphs into the next
                                    page's [data-vt-title] / .vt-title (one per page: the place / course / event H1).
                                    Inside a [data-vt-scope] card, a link in .rec-name / .gal-name / .pc-name /
                                    .stop-go is the name when the card marks none
     [data-vt-scope]                card or row: its KOGL-1 image (img[data-kogl="1"]) morphs into the next
                                    page's img[data-vt-photo] / .vt-photo (KOGL-1 hero). KOGL-3 images never morph
                                    (an image carrying any other data-kogl is never named)
   Modules: motion.js (every page, after load, not with reduced motion); map.js (.map[data-points] /
   .map[data-map]; at once when a map is near the first screen, else after load); course.js ([data-course]);
   search.js ([data-search]). Each is skipped when the page already loads it. chat.js + chat.css (the site assistant):
   on the first press of [data-chat-open], or after load when sessionStorage 'gs-chat' says the chat was open; on a
   page that asks in place ([data-chat-dock] > [data-ask-form] [data-ask-q], [data-ask-go], a[data-ask],
   [data-ask-log]: the Korean home's centre card with its conversation panel below, the English home's centre card)
   when the reader touches the box — focus in it loads them in the background, a question asks in place, and the
   launcher there goes to the box (or the open conversation) instead of opening the panel.

   EVENTS (document): gs:filter {ids}, gs:hl {id, on}, gs:hlrow {id, on}, gs:showmap, gs:region {region, kinds},
   gs:menu {open}, gs:focus {ids}. html.cv-off is added at 'load' (lifts content-visibility for scroll measurements). */
(function () {
  "use strict";
  var doc = document, root = doc.documentElement, win = window;
  var reduce = win.matchMedia("(prefers-reduced-motion: reduce)").matches;
  var narrow = win.matchMedia("(max-width: 1023px)");
  var BASE = ((doc.currentScript && doc.currentScript.src) || "/assets/site.js").replace(/[^/]*$/, "");
  function $all(sel, el) { return Array.prototype.slice.call((el || doc).querySelectorAll(sel)); }
  function emit(name, detail) { doc.dispatchEvent(new CustomEvent(name, { detail: detail })); }
  var ticking = false, onScrollFns = [];
  function onScroll(fn) { onScrollFns.push(fn); }
  function frame() { ticking = false; onScrollFns.forEach(function (fn) { fn(); }); }
  function kick() { if (!ticking) { ticking = true; win.requestAnimationFrame(frame); } }
  win.addEventListener("scroll", kick, { passive: true });
  win.addEventListener("resize", kick);
  win.addEventListener("pageshow", kick);
  function afterLoad(fn) { if (doc.readyState === "complete") fn(); else win.addEventListener("load", fn); }

  // ------------------------------------------------------------ modules: map.js, course.js, search.js
  function attach(name) {
    var src = BASE + name;
    if ($all("script[src]").some(function (s) { return s.src === src; })) return;
    var s = doc.createElement("script");
    s.src = src;
    doc.body.appendChild(s);
  }
  var maps = $all(".map[data-points], .map[data-map]");
  if (maps.length) {
    // a map on the first screen (course page sidebar) gets its module now; others after the page has loaded
    if (maps.some(function (m) { return m.getBoundingClientRect().top < win.innerHeight * 1.5; })) attach("map.js");
    else afterLoad(function () { attach("map.js"); });
  }
  if (doc.querySelector("[data-course]")) attach("course.js");
  if (doc.querySelector("[data-search]")) attach("search.js");
  afterLoad(function () { root.classList.add("cv-off"); });
  // the motion layer arrives after the page has loaded (or after 4s), never with reduced motion: nothing of it
  // competes with the first screen
  if (!reduce) {
    afterLoad(function () { attach("motion.js"); });
    setTimeout(function () { attach("motion.js"); }, 4000);
  }

  // ------------------------------------------------------------ site assistant: chat.js + chat.css (owner 2026-10-13)
  // The launcher (base.html.j2 → _chat.html.j2) or any [data-chat-open] loads the module and its stylesheet on the
  // first press; a tab that left the chat open on the previous page reopens it after this page has loaded
  // (sessionStorage 'gs-chat'). The launcher is there from the first paint on every page (owner 2026-10-13 night: '처음에
  // 아래로 스크롤을 안 하면 챗봇이 안 보이는데?'); the page's foot keeps its height free (css/49-chat.css). A page that
  // asks in place (the homes) answers there: the launcher goes to its box (askShow, in that section below) and nothing
  // is restored on load, so nothing moves while the page loads.
  var askShow = null;
  if (doc.querySelector("[data-chat-open]")) {
    var dock = doc.querySelector("[data-chat-dock]");
    var chatReady = null, chatCss = null;
    var chatLoad = function () {
      if (!chatCss) {
        chatCss = doc.createElement("link");
        chatCss.rel = "stylesheet";
        chatCss.href = BASE + "chat.css";
        doc.head.appendChild(chatCss);
      }
      if (!chatReady) {
        chatReady = new Promise(function (ok, fail) {
          var s = doc.createElement("script");
          s.src = BASE + "chat.js";
          s.onload = function () { ok(win.gsChat); };
          s.onerror = function () { chatReady = null; s.remove(); fail(new Error("chat.js did not load")); };
          doc.body.appendChild(s);
        });
      }
      return chatReady;
    };
    var chatFailed = function (err) { if (win.console) win.console.warn(err.message); };
    doc.addEventListener("click", function (e) {
      var b = e.target.closest && e.target.closest("[data-chat-open]");
      if (!b) return;
      e.preventDefault();
      if (dock && askShow) { askShow(b); return; }
      chatLoad().then(function (chat) { chat.open(b); }, chatFailed);
    });
    var chatState = null;
    try { chatState = JSON.parse(win.sessionStorage.getItem("gs-chat") || "null"); } catch (err) { chatState = null; }
    if (chatState && chatState.msgs && chatState.msgs.length) root.classList.add("chat-has");
    if (chatState && chatState.open && !dock) afterLoad(function () { chatLoad().then(function (chat) { chat.restore(); }, chatFailed); });
    // while the reader scrolls down the launcher folds to its round icon (html.chat-mini); scrolling up unfolds it
    var chatY = win.scrollY;
    onScroll(function () {
      var y = win.scrollY;
      if (Math.abs(y - chatY) < 8) return;
      root.classList.toggle("chat-mini", y > chatY && y > 8);
      chatY = y;
    });
  }

  // ------------------------------------------------------------ masthead: compact once the page moves
  var scrolled = null;
  var setMast = function () {
    var on = win.scrollY > 8;
    if (on === scrolled) return;
    scrolled = on;
    root.classList.toggle("is-scrolled", on);
  };
  onScroll(setMast); setMast();

  // ------------------------------------------------------------ asking in place ([data-chat-dock]: the homes)
  // The Korean home asks from its centre card (_ask.html.j2 box: the field, ONE button '물어보기', the starter
  // questions; owner 2026-10-14: the site search is the header's) and answers in the conversation panel right under
  // the card ([data-ask-log][data-ask-more]); the English home asks and answers inside its centre card (.ask-card). The
  // box is in the first paint; chat.js and chat.css are not: focus in the box ([data-ask-zone] / .ask-card) loads them
  // in the background. A question — Enter or the button with text in the field, or a plain click on a starter — asks
  // the assistant (chat.js dock mode, gsChat.ask / stop / busy): the conversation [data-ask-log] is shown at once,
  // inside this input event (its height is fixed in the first-paint CSS: the only shift, and the reader's own), a
  // panel of its own comes into view (smoothly unless the reader prefers reduced motion; on a touch screen the
  // keyboard closes first), then the module loads and asks. If it cannot load, the Korean box submits to the site
  // search (/search/?q=) and a starter follows its link; other languages say so in the box. While an answer comes the
  // button stops it (Enter in the field does not). An empty field only takes the focus (the button is never disabled).
  // Enter: the form's own submit — the browser submits only an Enter that the input method did not keep for itself.
  // The keydown below only marks the input method's own Enter (isComposing, or keyCode 229 where the composition has
  // already ended — Safari) so that a submit in that same task is dropped; a real Enter clears the mark. Chrome with a
  // Korean input method sends that real Enter a few ms after compositionend, when the Enter that ended the last
  // syllable is pressed: it asks at once. (The 2026-10-14 bug: a 50 ms guard after every compositionend swallowed
  // exactly that Enter, so a Korean question ending in a composed syllable never asked on Enter.) A starter pressed
  // with a modifier key or the middle button — or any starter once the assistant said it is not connected
  // (data-chat-off) — stays a link. The launcher on this page goes to the box: to the conversation's own box when it
  // is open or this tab keeps one (then it is shown), else to the question field; it never opens the floating panel.
  var askCard = doc.querySelector("[data-chat-dock]");
  var askForm = askCard && askCard.querySelector("[data-ask-form]");
  var askQ = askForm && askForm.querySelector("[data-ask-q]");
  if (askQ && chatLoad) {
    var askLog = askCard.querySelector("[data-ask-log]");
    var askSearch = askForm.getAttribute("data-ask-form") === "search";
    var askPanel = !!(askLog && askLog.hasAttribute("data-ask-more"));   // a conversation panel of its own
    var askZone = askCard.querySelector(".ask-card, [data-ask-zone]") || askCard;
    var imeKey = false, byEnter = false;
    var chatNow = function () { return win.gsChat && win.gsChat.dock ? win.gsChat : null; };
    var askFail = function () {   // no module and nothing to fall back on: one line in the box, read out
      if (!askLog) return;
      var p = doc.createElement("p");
      p.className = "ask-fail";
      p.setAttribute("role", "alert");
      p.textContent = askLog.getAttribute("data-fail") || "";
      askLog.replaceChildren(p);
    };
    var showLog = function () {   // the conversation, now; a panel of its own comes into view
      if (!askLog) return;
      askLog.hidden = false;
      if (!askPanel) return;
      if (win.matchMedia("(pointer: coarse)").matches && doc.activeElement === askQ) askQ.blur();
      askLog.scrollIntoView({ block: "nearest", behavior: reduce ? "auto" : "smooth" });
    };
    var askWith = function (q, fallback) {
      var chat = chatNow();
      showLog();
      if (chat) { chat.ask(q); return; }
      chatLoad().then(function (c) { c.ask(q); }, function (err) { chatFailed(err); fallback(); });
    };
    askZone.addEventListener("focusin", function () { chatLoad().then(null, function () {}); });   // warm-up
    askQ.addEventListener("keydown", function (e) {
      if (e.key !== "Enter") return;
      if (e.isComposing || e.keyCode === 229) {   // the input method's own Enter: it commits or converts the text
        imeKey = true;
        setTimeout(function () { imeKey = false; }, 0);
        return;
      }
      imeKey = false;   // the reader's Enter: the submit it makes (now, as the key's default action) is Enter's
      byEnter = true;
      setTimeout(function () { byEnter = false; }, 0);
    });
    askForm.addEventListener("submit", function (e) {
      if (imeKey) { e.preventDefault(); return; }   // a browser that submits on the input method's Enter
      if (e.submitter && e.submitter.hasAttribute("data-ask-search")) return;   // a '사이트 검색' button: the search page
      if (askSearch && askCard.hasAttribute("data-chat-off")) return;          // not connected: the search page
      e.preventDefault();
      var chat = chatNow();
      if (chat && chat.busy()) {
        if (!byEnter) chat.stop();   // the button (now '멈추기'); Enter in the field leaves the answer be
        return;
      }
      var q = askQ.value.trim();
      if (!q) { askQ.focus(); return; }
      askWith(q, function () { if (askSearch) askForm.submit(); else askFail(); });
    });
    askCard.addEventListener("click", function (e) {
      var a = e.target.closest && e.target.closest("a[data-ask]");
      if (!a || e.defaultPrevented) return;
      if (e.button || e.metaKey || e.ctrlKey || e.shiftKey || e.altKey || askCard.hasAttribute("data-chat-off")) return;
      e.preventDefault();
      var chat = chatNow();
      if (chat && chat.busy()) return;
      askWith(a.getAttribute("data-ask"), function () { win.location.href = a.href; });
    });
    // the launcher: the box instead of the panel (it is not a dialog here). It stays where it is, visible from the
    // first paint (owner 2026-10-14: '첫 화면부터 우측 하단에 챗봇 잘 보이게') — it never steps aside here
    $all("[data-chat-open]").forEach(function (b) { b.removeAttribute("aria-haspopup"); });
    askShow = function (b) {
      var has = root.classList.contains("chat-has");
      if (!askPanel) {   // the English card: into view with the focus in its field, and the conversation this tab keeps
        if (has && askLog) askLog.hidden = false;
        askQ.focus({ preventScroll: true });
        (askCard.querySelector(".ask-card") || askCard).scrollIntoView({ block: "start", behavior: reduce ? "auto" : "smooth" });
        chatLoad().then(function (c) { c.open(b); }, function (err) { chatFailed(err); if (has) askFail(); });
        return;
      }
      if (has || !askLog.hidden) {   // the conversation, in view; chat.js puts the focus in its own box
        showLog();
        chatLoad().then(function (c) { c.open(b); }, function (err) { chatFailed(err); askFail(); });
        return;
      }
      askQ.focus({ preventScroll: true });   // nothing asked yet: the question field of the opening
      askForm.scrollIntoView({ block: "center", behavior: reduce ? "auto" : "smooth" });
      chatLoad().then(null, function () {});
    };
  }

  // ------------------------------------------------------------ pause buttons: opening photos, festival marquee
  // the marquee moves (CSS) from the first paint, so its button must work before motion.js arrives
  [["[data-hero]", "[data-hero-pause]", "사진 움직임 다시 시작", "사진 움직임 멈추기"],
    ["[data-marquee]", "[data-mq-pause]", "흐름 다시 시작", "흐름 멈추기"]].forEach(function (d) {
    $all(d[0]).forEach(function (box) {
      var b = box.querySelector(d[1]);
      if (!b) return;
      b.addEventListener("click", function () {
        var on = !box.classList.contains("is-paused");
        box.classList.toggle("is-paused", on);
        b.setAttribute("aria-pressed", String(on));
        var text = on ? (b.getAttribute("data-label-play") || d[2]) : (b.getAttribute("data-label-pause") || d[3]);
        var lbl = b.querySelector("[data-lbl], .lbl");
        if (lbl) lbl.textContent = text; else b.setAttribute("aria-label", text);
      });
    });
  });

  // ------------------------------------------------------------ menu (<details>)
  $all("details[data-menu], details.menu").forEach(function (menu) {
    var summary = menu.querySelector("summary");
    menu.addEventListener("toggle", function () {
      root.classList.toggle("menu-open", menu.open);
      emit("gs:menu", { open: menu.open });
    });
    doc.addEventListener("click", function (e) { if (menu.open && !menu.contains(e.target)) menu.open = false; });
    menu.addEventListener("click", function (e) { if (e.target.closest("a[href]")) menu.open = false; });
    doc.addEventListener("keydown", function (e) {
      if (e.key === "Escape" && menu.open) { menu.open = false; if (summary) summary.focus(); }
    });
  });

  // ------------------------------------------------------------ language menu (<details data-langmenu>, _lang.html.j2)
  // works without JS; here only: an outside click, a followed link or Escape closes it (Escape returns focus)
  $all("details[data-langmenu]").forEach(function (lm) {
    var sum = lm.querySelector("summary");
    doc.addEventListener("click", function (e) { if (lm.open && !lm.contains(e.target)) lm.open = false; });
    lm.addEventListener("click", function (e) { if (e.target.closest("a[href]")) lm.open = false; });
    doc.addEventListener("keydown", function (e) { if (e.key === "Escape" && lm.open) { lm.open = false; if (sum) sum.focus(); } });
  });

  // ------------------------------------------------------------ the site search in the bar (base.html.j2 form.hs)
  // Owner 2026-10-14: the search lives in the bar of every Korean page. From 1024px the field is always there (CSS)
  // and works without JS. Phones: '검색' ([data-hs-open]) is a link to /search/ without JS; here it is a button that
  // opens the same form over the bar (html.hs-open: the field, the round search button, '닫기') with the focus in the
  // field — the bar keeps its height. '닫기', Escape or a press outside the bar closes it; the first two return the
  // focus to '검색'. The form itself is a plain GET to /search/?q= (search.js answers there).
  var hs = doc.querySelector("[data-hs]");
  var hsOpen = doc.querySelector("[data-hs-open]");
  if (hs && hsOpen) {
    var hsQ = hs.querySelector("input[name=q]");
    var hsOn = function () { return root.classList.contains("hs-open"); };
    var hsSet = function (on, back) {
      root.classList.toggle("hs-open", on);
      hsOpen.setAttribute("aria-expanded", String(on));
      if (on) hsQ.focus();
      else if (back) hsOpen.focus();
    };
    hsOpen.setAttribute("role", "button");
    hsOpen.setAttribute("aria-controls", hs.id);
    hsOpen.setAttribute("aria-expanded", "false");
    hsOpen.addEventListener("click", function (e) {
      if (e.button || e.metaKey || e.ctrlKey || e.shiftKey || e.altKey) return;   // a new tab: the search page
      e.preventDefault();
      hsSet(true);
    });
    hsOpen.addEventListener("keydown", function (e) {   // a button answers Space too
      if (e.key === " ") { e.preventDefault(); hsSet(true); }
    });
    var hsX = hs.querySelector("[data-hs-close]");
    if (hsX) hsX.addEventListener("click", function () { hsSet(false, true); });
    doc.addEventListener("keydown", function (e) {
      if (e.key === "Escape" && hsOn() && !e.isComposing) { e.preventDefault(); hsSet(false, true); }
    });
    doc.addEventListener("click", function (e) {
      if (hsOn() && !(e.target.closest && e.target.closest("[data-mast]"))) hsSet(false);
    });
  }

  // ------------------------------------------------------------ masthead context link on lists: '지도'
  var showMap = doc.querySelector("[data-show-map]");
  if (showMap) showMap.addEventListener("click", function (e) {
    var b = doc.querySelector('[data-filters] [data-view="map"], [data-segmap] [data-view="map"]');
    if (!b || !narrow.matches) return;
    e.preventDefault();
    b.click();
    var top = (doc.querySelector("[data-filters]") || doc.body).getBoundingClientRect().top + win.scrollY - 60;
    win.scrollTo(0, Math.max(0, top));
  });

  // ------------------------------------------------------------ sticky columns taller than the window
  var stickies = $all("[data-sticky]");
  if (stickies.length) {
    var fitSticky = function () {
      stickies.forEach(function (el) {
        el.style.top = "";
        if (narrow.matches) return;
        var top = parseFloat(getComputedStyle(el).top) || 16;
        var over = el.offsetHeight - (win.innerHeight - top - 16);
        if (over > 0) el.style.top = (top - over) + "px";
      });
    };
    win.addEventListener("resize", fitSticky); afterLoad(fitSticky); fitSticky();
  }

  // ------------------------------------------------------------ list filters, URL state, row ↔ marker
  var box = doc.querySelector("[data-filters]");
  if (box) {
    box.hidden = false;
    var scope = box.closest("[data-filter-scope]") || doc;
    var items = $all("[data-filter-item]", scope);
    if (!items.length) {
      var holder = scope.querySelector("[data-filter-items]");
      items = holder ? Array.prototype.slice.call(holder.children) : $all(".rec", scope);
    }
    var groups = $all("[data-filter-group]", scope);
    if (!groups.length) groups = $all(".lg-group", scope);
    var result = scope.querySelector("[data-result]"), countEl = box.querySelector("[data-filter-count], [data-count]");
    var empty = scope.querySelector("[data-empty]");
    var grid = scope.querySelector("[data-view-root]") || doc.querySelector(".list-grid");
    var label = result ? result.textContent.replace(/\s*[\d,]+곳.*$/, "") : "";
    var keyOf = function (c) { return c.getAttribute("data-f") || c.getAttribute("data-filter") || ""; };
    var valOf = function (c) {
      var v = c.getAttribute("data-v");
      return v === null ? (c.getAttribute("data-value") || "") : v;
    };
    var controls = $all("[data-f], [data-filter]", box).filter(function (c) { return c !== box && keyOf(c); });
    var check = controls.filter(function (c) { return c.type === "checkbox"; })[0];
    var keys = [];
    controls.forEach(function (c) { var k = keyOf(c); if (c !== check && keys.indexOf(k) < 0) keys.push(k); });
    var state = { check: false, view: "list" };
    var q = new URLSearchParams(location.search);
    keys.forEach(function (k) { state[k] = q.get(k) || ""; });
    state.check = q.get("check") === "1";
    state.view = q.get("view") === "map" ? "map" : "list";
    var attrOf = function (el, k) {
      var v = el.getAttribute("data-" + k);
      return v === null ? el.getAttribute("data-" + k + "s") : v;
    };
    var has = function (raw, v) {
      if (raw === null) return false;
      if (raw === v) return true;
      return raw.split("|").indexOf(v) > -1 || raw.split(/\s+/).indexOf(v) > -1;
    };
    // the '필터' panel: [data-f-more] toggles [data-f-panel]; [data-f-badge] counts the filters set inside the panel
    var moreBtn = box.querySelector("[data-f-more]"), panel = box.querySelector("[data-f-panel]"), badge = box.querySelector("[data-f-badge]");
    var inPanel = function (k) { return !!panel && controls.some(function (c) { return keyOf(c) === k && panel.contains(c); }); };
    var panelSet = function () {
      return keys.filter(function (k) { return state[k] && inPanel(k); }).length + (state.check && check && panel && panel.contains(check) ? 1 : 0);
    };
    var setBadge = function () {
      if (!badge) return;
      var n = panelSet();
      badge.hidden = !n;
      badge.textContent = n ? String(n) : "";
    };
    var apply = function (push) {
      var n = 0, flag = check ? check.value : "";
      items.forEach(function (it) {
        var ok = keys.every(function (k) { return !state[k] || has(attrOf(it, k), state[k]); }) &&
          (!state.check || !flag || it.hasAttribute("data-" + flag));
        it.hidden = !ok;
        if (ok) n++;
      });
      groups.forEach(function (g) { g.hidden = !items.some(function (it) { return !it.hidden && g.contains(it); }); });
      if (empty) empty.hidden = n > 0;
      if (result) result.textContent = label + " " + n + "곳" + (n === items.length ? "" : " (전체 " + items.length + "곳 중)");
      if (countEl) countEl.textContent = String(n);
      controls.forEach(function (c) {
        if (c === check) { c.checked = state.check; return; }
        if (c.tagName === "SELECT") { c.value = state[keyOf(c)]; return; }
        c.setAttribute("aria-pressed", String((state[keyOf(c)] || "") === valOf(c)));
      });
      $all("[data-view]", box).forEach(function (b) { b.setAttribute("aria-pressed", String(b.getAttribute("data-view") === state.view)); });
      if (grid) grid.classList.toggle("show-map", state.view === "map");
      emit("gs:filter", { ids: items.filter(function (it) { return !it.hidden && it.id; }).map(function (it) { return it.id; }) });
      setBadge();
      if (push) {
        var p = new URLSearchParams();
        keys.forEach(function (k) { if (state[k]) p.set(k, state[k]); });
        if (state.check) p.set("check", "1");
        if (state.view === "map") p.set("view", "map");
        try { history.replaceState(null, "", location.pathname + (p.toString() ? "?" + p : "") + location.hash); } catch (e) { /* file:// */ }
      }
    };
    box.addEventListener("click", function (e) {
      var b = e.target.closest("button");
      if (!b || !box.contains(b)) return;
      if (b.hasAttribute("data-view")) {
        state.view = b.getAttribute("data-view");
        apply(true);
        if (state.view === "map") emit("gs:showmap", {});
        return;
      }
      if (keyOf(b)) { state[keyOf(b)] = valOf(b); apply(true); }
    });
    controls.forEach(function (c) {
      if (c === check) c.addEventListener("change", function () { state.check = c.checked; apply(true); });
      else if (c.tagName === "SELECT") c.addEventListener("change", function () { state[keyOf(c)] = c.value; apply(true); });
    });
    apply(false);
    if (moreBtn && panel) {
      if (panelSet()) { panel.hidden = false; moreBtn.setAttribute("aria-expanded", "true"); }
      moreBtn.addEventListener("click", function () {
        var open = panel.hidden;
        panel.hidden = !open;
        moreBtn.setAttribute("aria-expanded", String(open));
      });
    }
    if (state.view === "map") emit("gs:showmap", {});
    items.forEach(function (it) {
      if (!it.id) return;
      var on = function () { emit("gs:hl", { id: it.id, on: true }); };
      var off = function () { emit("gs:hl", { id: it.id, on: false }); };
      it.addEventListener("mouseenter", on); it.addEventListener("mouseleave", off);
      it.addEventListener("focusin", on); it.addEventListener("focusout", off);
    });
  }
  doc.addEventListener("gs:hlrow", function (e) {
    var r = doc.getElementById(e.detail.id);
    if (r) r.classList.toggle("hl", e.detail.on);
  });
  $all("details[data-map-fold], details.map-fold").forEach(function (fold) {
    fold.addEventListener("toggle", function () { if (fold.open) emit("gs:showmap", {}); });
  });

  // ------------------------------------------------------------ map page: 권역 tabs, kinds, list | map
  var tabs = doc.querySelector("[data-region-tabs], .region-tabs");
  if (tabs) {
    var kinds = doc.querySelector("[data-kinds]"), seg = doc.querySelector("[data-segmap]");
    var mg = doc.querySelector("[data-map-grid], .map-grid");
    var cur = { region: "", kinds: { attraction: true, stay: true, food: true } };
    var draw = function () {
      $all("a[data-region]", tabs).forEach(function (a) { a.setAttribute("aria-current", String((a.getAttribute("data-region") || "") === cur.region)); });
      $all("[data-region-sec]").forEach(function (s) { s.hidden = !!cur.region && s.getAttribute("data-region-sec") !== cur.region; });
      $all("[data-kind-row]").forEach(function (li) { li.hidden = !cur.kinds[li.getAttribute("data-kind-row")]; });
      $all("[data-dong], .dong").forEach(function (d) { d.hidden = !d.querySelector("[data-kind-row]:not([hidden])"); });
      emit("gs:region", { region: cur.region, kinds: cur.kinds });
    };
    var byId = {};
    $all("[data-region-sec]").forEach(function (s) { if (s.id) byId[s.id] = s.getAttribute("data-region-sec"); });
    tabs.addEventListener("click", function (e) {
      var a = e.target.closest("a[data-region]");
      if (!a) return;
      e.preventDefault();
      cur.region = a.getAttribute("data-region") || "";
      draw();
      try { history.replaceState(null, "", cur.region ? a.getAttribute("href") : location.pathname); } catch (err) { /* file:// */ }
    });
    if (kinds) kinds.addEventListener("click", function (e) {
      var b = e.target.closest("button[data-kind]");
      if (!b) return;
      var k = b.getAttribute("data-kind");
      cur.kinds[k] = !cur.kinds[k];
      b.setAttribute("aria-pressed", String(cur.kinds[k]));
      draw();
    });
    if (seg) seg.addEventListener("click", function (e) {
      var b = e.target.closest("button[data-view]");
      if (!b) return;
      $all("button[data-view]", seg).forEach(function (x) { x.setAttribute("aria-pressed", String(x === b)); });
      if (mg) mg.classList.toggle("show-map", b.getAttribute("data-view") === "map");
      if (b.getAttribute("data-view") === "map") emit("gs:showmap", {});
    });
    var h = decodeURIComponent((location.hash || "").slice(1));
    if (byId[h]) cur.region = byId[h];
    draw();
  }
  $all("[data-pt]").forEach(function (li) {
    var id = li.getAttribute("data-pt");
    li.addEventListener("mouseenter", function () { emit("gs:hl", { id: id, on: true }); });
    li.addEventListener("mouseleave", function () { emit("gs:hl", { id: id, on: false }); });
    li.addEventListener("focusin", function () { emit("gs:hl", { id: id, on: true }); });
    li.addEventListener("focusout", function () { emit("gs:hl", { id: id, on: false }); });
  });

  // ------------------------------------------------------------ guide: the section being read
  // [data-sec] sections (id in the attribute, their map places in data-pts); the one whose top has passed 30% of the
  // window is current: its [data-toc-link] entries get aria-current (a state, not motion: it works with reduced
  // motion too), a scrolling side list keeps the entry in view (its own scroll, never the page's) and, where the map
  // sits beside the text (≥1024px), the map is told which places to show (gs:focus {ids}; none = all of them).
  var secs = $all("[data-sec]");
  if (secs.length) {
    var tocLinks = $all("[data-toc-link]"), toc = doc.querySelector("[data-toc]"), curSec;
    var beside = win.matchMedia("(min-width: 1024px)");
    var setSec = function (id) {
      if (id === curSec) return;
      curSec = id;
      tocLinks.forEach(function (a) {
        if (a.getAttribute("data-toc-link") === id) a.setAttribute("aria-current", "true"); else a.removeAttribute("aria-current");
      });
      var on = toc && toc.querySelector("[aria-current]");
      if (on && toc.scrollHeight > toc.clientHeight + 2) {
        var top = on.offsetTop - toc.clientHeight / 3;
        if (top < toc.scrollTop || on.offsetTop + on.offsetHeight > toc.scrollTop + toc.clientHeight) toc.scrollTo({ top: Math.max(0, top), behavior: reduce ? "auto" : "smooth" });
      }
      if (beside.matches) {
        var sec = id ? doc.querySelector('[data-sec="' + id + '"]') : null;
        emit("gs:focus", { ids: sec ? (sec.getAttribute("data-pts") || "").split(" ").filter(Boolean) : [] });
      }
    };
    var pickSec = function () {
      var line = win.innerHeight * 0.3, id = null;
      secs.forEach(function (s) { if (s.getBoundingClientRect().top <= line) id = s.getAttribute("data-sec"); });
      if (secs[secs.length - 1].getBoundingClientRect().bottom < line) id = null; // past the last section
      setSec(id);
    };
    // a card or chip reached with Tab inside a sideways row (the mini card rows, the chip table of contents) is
    // brought fully into the row (the browser only scrolls the focused link itself into view); the row's own
    // scroll, never the page's
    doc.addEventListener("focusin", function (ev) {
      var t = ev.target, row = t.closest && t.closest(".mcs-view, .gd-toc-l, .mcr"), li = row && t.closest("li");
      if (!li || !row.contains(li) || row.scrollWidth <= row.clientWidth + 1) return;
      var v = row.getBoundingClientRect(), r = li.getBoundingClientRect(), cs = getComputedStyle(row);
      var pl = parseFloat(cs.paddingLeft) || 0, pr = parseFloat(cs.paddingRight) || 0;
      // not wholly in view: its start goes to the row's start (a snap position of these rows: nothing re-snaps it)
      if (r.left < v.left + pl - 1 || r.right > v.right - pr + 1) row.scrollBy({ left: r.left - v.left - pl, behavior: reduce ? "auto" : "smooth" });
    });
    // the sections and the table of contents are skipped by content-visibility for the first paint (css/72-guide.css);
    // once a frame has been painted they are laid out for real (html.gd-open) and only then measured
    win.requestAnimationFrame(function () {
      setTimeout(function () {
        root.classList.add("gd-open");
        onScroll(pickSec);
        pickSec();
      }, 0);
    });
  }

  // ------------------------------------------------------------ YouTube facade
  doc.addEventListener("click", function (ev) {
    var btn = ev.target.closest && ev.target.closest("[data-yt]");
    if (!btn || ev.button || ev.metaKey || ev.ctrlKey || ev.shiftKey || ev.altKey) return;
    var id = btn.getAttribute("data-yt");
    var boxv = btn.closest("[data-video]");
    if (!/^[A-Za-z0-9_-]{11}$/.test(id || "") || !boxv) return;
    ev.preventDefault();
    var player = doc.createElement("iframe");
    player.src = "https://www.youtube-nocookie.com/embed/" + id + "?autoplay=1&rel=0";
    player.title = btn.getAttribute("data-title") || "YouTube 영상";
    player.allow = "accelerometer; autoplay; encrypted-media; gyroscope; picture-in-picture";
    player.allowFullscreen = true;
    boxv.classList.add("is-playing");
    boxv.innerHTML = "";
    boxv.appendChild(player);
    player.focus();
  });

  // ------------------------------------------------------------ article preview pictures (해외에서 본 <city>)
  // .ab-thumb holds the outlet's own og:image from its address; if the outlet stops serving it, the row falls back to
  // text only instead of showing a broken picture.
  function dropThumb(img) {
    var a = img.closest(".ab-thumb"), li = a && a.closest(".has-thumb");
    if (!a) return;
    a.remove();
    if (li) {
      li.classList.remove("has-thumb");
      var credit = li.querySelector(".ab-credit");
      if (credit) credit.remove();
    }
  }
  // the home news row's article cards (.nc-og) fall back to the card's type icon, without the credit line
  function dropNewsImg(img) {
    var card = img.closest(".nc"), cr = card && card.querySelector(".nc-cr");
    img.remove();
    if (cr) cr.remove();
  }
  doc.addEventListener("error", function (ev) {
    var t = ev.target;
    if (!t || t.tagName !== "IMG" || !t.closest) return;
    if (t.closest(".ab-thumb")) dropThumb(t);
    else if (t.classList.contains("nc-og")) dropNewsImg(t);
  }, true);
  $all(".ab-thumb img").forEach(function (im) { if (im.complete && !im.naturalWidth) dropThumb(im); });
  $all("img.nc-og").forEach(function (im) { if (im.complete && !im.naturalWidth) dropNewsImg(im); });

  // ------------------------------------------------------------ social post embeds (해외에서 본 <city>)
  // [data-embed=instagram|threads|x|facebook][data-url] holds our note and a link; nothing is requested from the
  // service until the card comes near the screen (or [data-embed-load] is pressed — no IntersectionObserver, or the
  // visitor asked to save data). Then the service's own embed markup — with the post's photo — goes into
  // [data-embed-slot] and its script loads once (Facebook: its post plugin iframe). The link works without JS.
  var EMBED_JS = {instagram: "https://www.instagram.com/embed.js", threads: "https://www.threads.com/embed.js",
                  x: "https://platform.twitter.com/widgets.js"};
  var embedLoaded = {};
  function embedPost(card) {
    if (card.classList.contains("is-embedded")) return true;
    var kind = card.getAttribute("data-embed"), url = card.getAttribute("data-url") || "";
    var slot = card.querySelector("[data-embed-slot]"), btn = card.querySelector("[data-embed-load]");
    if (!/^https:\/\//.test(url) || !slot) return false;
    var q = doc.createElement("blockquote"), a = doc.createElement("a");
    a.href = url; a.textContent = url;
    if (kind === "facebook") {
      var f = doc.createElement("iframe");
      f.src = "https://www.facebook.com/plugins/post.php?href=" + encodeURIComponent(url) + "&show_text=true&width=500";
      f.title = (btn && btn.getAttribute("data-title")) || "Facebook 게시물";
      f.width = "500"; f.height = "600"; f.loading = "lazy";
      slot.appendChild(f);
    } else if (EMBED_JS[kind]) {
      if (kind === "instagram") { q.className = "instagram-media"; q.setAttribute("data-instgrm-permalink", url); }
      if (kind === "threads") { q.className = "text-post-media"; q.setAttribute("data-text-post-permalink", url); }
      if (kind === "x") { q.className = "twitter-tweet"; }
      q.appendChild(a);
      slot.appendChild(q);
      var again = function () {
        if (kind === "instagram" && window.instgrm) window.instgrm.Embeds.process();
        if (kind === "x" && window.twttr && window.twttr.widgets) window.twttr.widgets.load(slot);
      };
      if (embedLoaded[kind]) { again(); }
      else {
        var s = doc.createElement("script");
        s.async = true; s.src = EMBED_JS[kind]; s.onload = again;
        doc.body.appendChild(s);
        embedLoaded[kind] = true;
      }
    } else return false;
    card.classList.add("is-embedded");
    if (btn) btn.remove();
    return true;
  }
  doc.addEventListener("click", function (ev) {
    var btn = ev.target.closest && ev.target.closest("[data-embed-load]");
    var card = btn && btn.closest("[data-embed]");
    if (card && embedPost(card)) ev.preventDefault();
  });
  var saveData = navigator.connection && navigator.connection.saveData;
  if ("IntersectionObserver" in window && !saveData) {
    var embedIO = new IntersectionObserver(function (entries) {
      entries.forEach(function (en) {
        if (en.isIntersecting) { embedIO.unobserve(en.target); embedPost(en.target); }
      });
    }, {rootMargin: "300px 0px"});
    $all("[data-embed][data-url]").forEach(function (c) { embedIO.observe(c); });
  }
  // cards added later (the highlights viewer) are watched the same way; with Save-Data their button does it
  win.gsEmbedWatch = function (card) { if (embedIO) embedIO.observe(card); };

  // ------------------------------------------------------------ highlights row (해외에서 본 <city>)
  // The circles' pictures wait in data-src / data-srcset until the page has loaded (never competing with its LCP); one
  // that fails is removed and the badge under it shows. The viewer arrives on the first press: its markup
  // (window.gsHlData, fetched from the row's data-hl address) and highlights.js load together, and highlights.js opens
  // the card asked for (window.gsHlWant, later window.gsHl(link)). A link pressed with a modifier key, or a browser
  // without <dialog> / fetch, keeps going to the original; so does the link when either part cannot load.
  var hlRow = doc.querySelector("[data-hl]");
  if (hlRow) afterLoad(function () {
    $all(".hl-pic img", hlRow).forEach(function (im) {
      var pic = im.closest("picture") || im;
      im.addEventListener("error", function () { pic.remove(); });
      $all("source[data-srcset]", pic.parentNode).forEach(function (x) { x.srcset = x.getAttribute("data-srcset"); });
      if (im.getAttribute("data-src")) im.src = im.getAttribute("data-src");
    });
  });
  if (hlRow && hlRow.getAttribute("data-hl") && win.HTMLDialogElement && win.fetch) {
    $all("[data-hl-open]", hlRow).forEach(function (a) { a.setAttribute("aria-haspopup", "dialog"); });
    hlRow.addEventListener("click", function (ev) {
      var a = ev.target.closest && ev.target.closest("[data-hl-open]");
      if (!a || ev.defaultPrevented || ev.button || ev.metaKey || ev.ctrlKey || ev.shiftKey || ev.altKey) return;
      ev.preventDefault();
      if (win.gsHl) { win.gsHl(a); return; }
      win.gsHlWant = a;
      if (win.gsHlData) return;   // already on its way
      win.gsHlData = win.fetch(hlRow.getAttribute("data-hl")).then(function (r) {
        if (!r.ok) throw new Error("HTTP " + r.status);
        return r.json();
      });
      var s = doc.createElement("script");
      s.src = BASE + "highlights.js";
      s.onerror = function () { location.href = (win.gsHlWant || a).href; };
      doc.body.appendChild(s);
    });
  }

  // ------------------------------------------------------------ carousels: round previous / next buttons
  $all("[data-gallery]").forEach(function (g) {
    // a row that leaves its buttons to this file ([data-gal-make="previous|next"]: the guide's section rows, below
    // the first screen; ui.shelf nav_js) gets them here, drawn from the page's icon sprite (#gi-prev / #gi-next)
    var make = g.querySelector("[data-gal-make]");
    if (make && !make.firstChild) {
      var words = make.getAttribute("data-gal-make").split("|");
      [-1, 1].forEach(function (d, i) {
        var b = doc.createElement("button"), t = doc.createElement("span");
        b.type = "button"; b.className = "gal-btn"; b.setAttribute("data-dir", String(d));
        b.innerHTML = '<svg class="icon" aria-hidden="true" focusable="false"><use href="#gi-' + (d < 0 ? "prev" : "next") + '"/></svg>';
        t.className = "vh"; t.textContent = words[i] || "";
        b.appendChild(t); make.appendChild(b);
      });
    }
    var view = g.querySelector("[data-gal-view]"), btns = $all("[data-gal-nav] button", g);
    if (!view || btns.length < 2) return;
    var step = function () {
      var c = view.querySelector(".car-track > li, .gal-track > li, .mcs > li");
      if (!c) return view.clientWidth * 0.8;
      var gap = parseFloat(getComputedStyle(c.parentNode).columnGap) || 0;
      return c.getBoundingClientRect().width + gap;
    };
    var sync = function () {
      var max = view.scrollWidth - view.clientWidth - 2;
      btns[0].disabled = view.scrollLeft <= 2;
      btns[1].disabled = view.scrollLeft >= max;
      g.classList.toggle("no-scroll", max <= 0); // a row that fits needs no buttons
    };
    btns.forEach(function (b) {
      b.addEventListener("click", function () {
        view.scrollBy({ left: step() * Number(b.getAttribute("data-dir")), behavior: reduce ? "auto" : "smooth" });
      });
    });
    view.addEventListener("scroll", sync, { passive: true });
    win.addEventListener("resize", sync);
    sync();
  });

  // ------------------------------------------------------------ home news row: autoplay, controls, counter
  $all("[data-hcar]").forEach(function (box) {
    var view = box.querySelector("[data-hcar-view]");
    var items = view ? $all("[data-hcar-item]", view) : [];
    if (!view || items.length < 2) return;
    var pause = box.querySelector("[data-hcar-pause]"), cur = box.querySelector("[data-hcar-cur]");
    var count = box.querySelector("[data-hcar-count]");
    var prog = box.querySelector("[data-hcar-prog]");   // the progress line of the current turn (css 46-home-open)
    var DELAY = 6000, timer = 0, ticking = false;
    var stopped = reduce, hover = false, away = false;
    // where each card sits when it is the first of the row (scroll-padding-left), clamped to the row's end
    var spots = function () {
      var max = view.scrollWidth - view.clientWidth;
      var pad = parseFloat(getComputedStyle(view).scrollPaddingLeft) || 0;
      var left = view.getBoundingClientRect().left;
      return items.map(function (it) {
        return Math.max(0, Math.min(max, Math.round(it.getBoundingClientRect().left - left + view.scrollLeft - pad)));
      });
    };
    var index = function (xs) {
      var x = view.scrollLeft, best = 0;
      xs.forEach(function (v, i) { if (Math.abs(v - x) < Math.abs(xs[best] - x)) best = i; });
      return best;
    };
    var go = function (dir) {   // one card on (wrapping to the start at the end) or one back (to the end at the start)
      var xs = spots(), max = view.scrollWidth - view.clientWidth, x = view.scrollLeft, to;
      if (dir > 0) {
        var ahead = xs.filter(function (v) { return v > x + 2; });
        to = x >= max - 2 || !ahead.length ? 0 : ahead[0];
      } else {
        var back = xs.filter(function (v) { return v < x - 2; });
        to = x <= 2 || !back.length ? max : back[back.length - 1];
      }
      view.scrollTo({ left: to, behavior: reduce ? "auto" : "smooth" });
    };
    var draw = function () {
      ticking = false;
      if (cur) cur.textContent = String(index(spots()) + 1);
      box.classList.toggle("no-scroll", view.scrollWidth - view.clientWidth <= 2);
    };
    var running = function () { return !stopped && !hover && !away && !doc.hidden && !box.classList.contains("no-scroll"); };
    var schedule = function () {
      clearTimeout(timer);
      var on = running();
      if (prog) {   // restart the line's 6 s fill with each turn; it rests empty while stopped
        prog.classList.remove("is-run");
        if (on) { void prog.offsetWidth; prog.classList.add("is-run"); }
      }
      if (on) timer = setTimeout(function () { if (running()) go(1); schedule(); }, DELAY);
    };
    var setStopped = function (on) {
      stopped = on;
      box.classList.toggle("is-stopped", on);
      if (pause) pause.setAttribute("aria-label", pause.getAttribute(on ? "data-label-play" : "data-label-pause") || "");
      if (count) count.setAttribute("aria-live", on ? "polite" : "off");
      schedule();
    };
    if (reduce && pause) pause.remove();
    if (pause) pause.addEventListener("click", function () { setStopped(!stopped); });
    $all("[data-hcar-dir]", box).forEach(function (b) {
      b.addEventListener("click", function () { setStopped(true); go(Number(b.getAttribute("data-hcar-dir"))); });
    });
    // the reader takes over: keyboard focus inside (the pause button handles itself), a swipe, a sideways wheel
    // (the Korean home's box also holds the opening's text and button: only focus on a card or a control counts)
    box.addEventListener("focusin", function (e) {
      if (e.target !== pause && !stopped && (view.contains(e.target) || e.target.closest("[data-hcar-dir]"))) setStopped(true);
    });
    view.addEventListener("pointerdown", function () { if (!stopped) setStopped(true); }, { passive: true });
    view.addEventListener("touchstart", function () { if (!stopped) setStopped(true); }, { passive: true });
    view.addEventListener("wheel", function (e) { if (Math.abs(e.deltaX) > Math.abs(e.deltaY) && !stopped) setStopped(true); }, { passive: true });
    view.addEventListener("pointerenter", function (e) { if (e.pointerType === "mouse") { hover = true; schedule(); } });
    view.addEventListener("pointerleave", function (e) { if (e.pointerType === "mouse") { hover = false; schedule(); } });
    // a hidden tab never advances (running() reads document.hidden); coming back to the tab gives the window focus
    win.addEventListener("focus", schedule);
    win.addEventListener("pageshow", schedule);
    if ("IntersectionObserver" in win) {
      new IntersectionObserver(function (es) { away = !es[0].isIntersecting; schedule(); }, { threshold: 0.25 }).observe(view);
    }
    view.addEventListener("scroll", function () { if (!ticking) { ticking = true; win.requestAnimationFrame(draw); } }, { passive: true });
    win.addEventListener("resize", draw);
    draw();
    setStopped(stopped);
  });

  // ------------------------------------------------------------ videos page: '공식 채널만'
  var vOff = doc.querySelector("[data-v-official]"), vWrap = doc.querySelector("[data-videos]");
  if (vOff && vWrap) vOff.addEventListener("click", function () {
    var on = vOff.getAttribute("aria-pressed") !== "true";
    vOff.setAttribute("aria-pressed", String(on));
    vWrap.classList.toggle("only-official", on);
    if (on) $all("details.v-more", vWrap).forEach(function (d) { d.open = true; });
  });

  // ------------------------------------------------------------ view transitions: name what morphs, on click
  if (!reduce) {
    var clearVT = function () {
      $all("[data-vt-on]").forEach(function (el) { el.style.viewTransitionName = ""; el.removeAttribute("data-vt-on"); });
    };
    var nameVT = function (el, name) { el.style.viewTransitionName = name; el.setAttribute("data-vt-on", ""); };
    win.addEventListener("pageshow", clearVT);
    doc.addEventListener("click", function (ev) {
      var a = ev.target.closest && ev.target.closest("a[href]");
      if (!a || ev.defaultPrevented || ev.button || ev.metaKey || ev.ctrlKey || ev.shiftKey || ev.altKey || a.target || a.hasAttribute("download")) return;
      if (a.origin !== location.origin || (a.pathname === location.pathname && a.hash)) return;
      clearVT();
      var t = a.matches("[data-vt]") ? a : a.querySelector("[data-vt]");
      var scope = a.closest("[data-vt-scope]");
      if (!t && scope && a.closest(".rec-name, .gal-name, .pc-name, .stop-go")) t = a; // the card's name link
      var ph = scope && scope.querySelector('img[data-kogl="1"], .t1 img:not([data-kogl]), img.t1:not([data-kogl])');
      if (!t && !ph) return;
      // names must be unique on the page being left: this page's own title / photo step aside
      $all("[data-vt-title], img[data-vt-photo], .vt-title, .vt-photo").forEach(function (el) { nameVT(el, "none"); });
      if (t) nameVT(t, "vt-title");
      if (ph) nameVT(ph, "vt-photo");
    });
  }
})();
