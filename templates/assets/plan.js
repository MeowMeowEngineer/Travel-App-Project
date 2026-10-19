/* The AI course planner (/plan/, the engine's first site's operator 2026-10-17), attached by site.js for [data-plan].
   The site's values come from the page (templates/plan.html.j2, from site.json): data-site (the public address),
   data-site-name (the export's and the file's name), data-hubs ({key: name}, site.json city.plan.hubs: none, no hub).

   FORM      the cards are real radio / check boxes; the counters (어른, 그중 65세 이상, 어린이·유아) add an age select per
             child; where the trip starts and ends (a station or a terminal, by name); the date starts on the coming
             Saturday (never before today); 좋아하는 것 keeps at most 4 ticked; a summary line says what will be asked.
             Submit → POST /api/plan/ {conditions}. A reload puts the conditions of the plan shown back in the form.
             The assistant hands a reader over with conditions in the address (/plan/?date=…&days=…&move=…): on the
             form's defaults (a plan the tab kept is not shown under them), each value only when it is one of the
             form's own choices, who comes and how many as the form's buttons keep them; the page opens at the form
             under a line saying so ('대화에서 말한 조건을 채웠어요 …', role=status); nothing is sent until the reader
             presses the button.
   WORKING   the steps the server reports (SSE status {step}) light up in order; '멈추기' aborts the request.
   RESULT    drawn from the server's checked plan (chatbot/planner.js finish, v 2) and the site's own place data
             (/plan/places.json, fetched once). The code's statements come first (review 2026-10-17: a '6/6 확인' badge
             stood above two unconfirmed places): the plan's status (완성된 코스 / 조건을 다 맞추지 못함), regular
             hours, that day's own checks, the reader's needs at each stop and the fees each as its own
             state; then the course at a glance, the day clock, the needs table, per day the stops (TourAPI photo or 3D
             picture, the model's one-line reason marked AI, the facts, what to check), the legs (straight line, the
             margin the plan keeps — never a travel time — and a Kakao Map link), the start and end hubs, a numbered map,
             the fees person by person, everything to check; copy, share, print, save as a text file; after an edit,
             what changed. Charts sit in <details>, open from 900px, closed on phones. Outside evaluation 2026-10-18:
             the status panel says how complete the day is (meals, likings, empty time, what an edit kept — planner
             finish 'complete'), an 'unmet' plan offers one-tap fixes for what is left (finish 'todo', sent as an
             edit), a distance total only when every leg has one, and a draft still unmet is marked so in its text.
             Operator 2026-10-18 ('이런 거 좀 안 뜨게 할 수 없어? 무조건 완성된 결과가 나오게'): what holds for any plan
             (planned margins, hubs, a stay's booking — finish 'aware') and what the data does not say (a place's closed
             days, a fee — finish 'checks') never make it a draft and never sit on top as '확인할 것': they are an
             information mark (i) in the status rows and one closed box, '가기 전에 알아 둘 것'. What the site put right
             itself (finish 'fixed') is not listed. Conditions no plan can meet come back before any model call
             (HTTP 422 / SSE error 'conditions' with problems and fixes): a box right above the button says why and
             offers the fixes as buttons that set the form; a plan the site built itself when the AI gave none (one
             'fixed' line starting '일정 전체:') says so above the course; a change that cannot be finished keeps the
             plan ('edit_failed').
   STATE     sessionStorage 'gs-plan' (this tab only): the conditions, the plan and the last change. Nothing is stored
             anywhere else. GA4 (window.siteTrack): plan_submit, plan_done, plan_edit, plan_error, plan_export,
             plan_fix, plan_conditions with fixed parameters only (days, move, with, status, code, how, kind, fields)
             — never the reader's words. */
(function () {
  "use strict";
  var doc = document, win = window;
  var root = doc.querySelector("[data-plan]");
  if (!root) return;
  var form = root.querySelector("[data-plan-form]"), work = root.querySelector("[data-plan-work]");
  var result = root.querySelector("[data-plan-result]"), sumEl = root.querySelector("[data-plan-sum]");
  var formErr = root.querySelector("[data-plan-formerr]"), live = root.querySelector("[data-plan-live]");
  var API = root.getAttribute("data-api"), PLACES = root.getAttribute("data-places");
  var KEY = "gs-plan", WEEK = "일월화수목금토", MAX_PREFS = 4;
  var BASE = (doc.currentScript && doc.currentScript.src || "").replace(/[^/]*$/, "") || "/assets/";
  var places = null, placesLoading = null, ctrl = null, state = null;
  var HUBS = {};
  try { HUBS = JSON.parse(root.getAttribute("data-hubs") || "{}") || {}; } catch (e) { HUBS = {}; }
  var SITE = (root.getAttribute("data-site") || "").replace(/\/+$/, "") || (win.location && win.location.origin) || "";
  var SITE_NAME = root.getAttribute("data-site-name") || "";
  // the pages to plan from without the planner: the official courses and the guides the build has, else the places
  var HAS_COURSES = +(root.getAttribute("data-courses") || 0) > 0, HAS_GUIDES = +(root.getAttribute("data-guides") || 0) > 0;
  function fallbackHint() {
    var links = [];
    if (HAS_COURSES) links.push(h("a", { href: "/courses/", text: "공식 코스" }));
    if (HAS_GUIDES) links.push(h("a", { href: "/guides/", text: "가이드" }));
    if (!links.length) return h("p", { class: "trp-hint" }, ["그동안 ", h("a", { href: "/places/", text: "가볼만한 곳" }), "에서 장소를 골라 볼 수 있어요."]);
    return h("p", { class: "trp-hint" }, ["그동안 ", links[0]].concat(links[1] ? ["나 ", links[1]] : []).concat(["에서 일정을 찾아볼 수 있어요."]));
  }
  var LABEL = {
    move: { car: "자가용", transit: "대중교통·걷기" },
    with: { solo: "혼자", couple: "연인·친구", kids: "아이와 가족", parents: "부모님과" },
    role: { visit: "둘러보기", meal: "식사", cafe: "카페", stay: "숙소" },
    day: { open: "그날 운영", closed: "그날 휴무", unknown: "그날 운영 확인 필요" },
    mode: { car: "자동차", walk: "걷기", traffic: "대중교통" },
  };

  function track(name, params) { try { if (win.siteTrack) win.siteTrack(name, params || {}); } catch (e) { /* no analytics */ } }
  function h(tag, attrs, kids) {
    var el = doc.createElement(tag);
    Object.keys(attrs || {}).forEach(function (k) {
      var v = attrs[k];
      if (v === null || v === undefined || v === false) return;
      if (k === "text") el.textContent = v;
      else if (k === "class") el.className = v;
      else el.setAttribute(k, v === true ? "" : v);
    });
    (kids || []).forEach(function (c) { if (c !== null && c !== undefined && c !== false) el.append(c); });
    return el;
  }
  function pic(id) {
    var t = doc.getElementById("trp-pics"), s = t && t.content.querySelector('[data-id="' + id + '"]');
    return s ? s.firstElementChild.cloneNode(true) : h("span", { class: "pic pic-tmp" });
  }
  function mascot(id) {
    // a city without its mascot's pictures yet (templates/assets/mascot) leaves the slot empty: no mascot, nothing breaks
    var t = doc.getElementById("trp-mascots"), s = t && t.content.querySelector('[data-id="' + id + '"]');
    return s && s.firstElementChild ? s.firstElementChild.cloneNode(true) : null;
  }
  function pad(n) { return (n < 10 ? "0" : "") + n; }
  function iso(d) { return d.getFullYear() + "-" + pad(d.getMonth() + 1) + "-" + pad(d.getDate()); }
  function dayName(s) { var d = new Date(s + "T12:00:00"); return (d.getMonth() + 1) + "월 " + d.getDate() + "일(" + WEEK[d.getDay()] + ")"; }
  function won(n) { return n.toLocaleString("ko-KR") + "원"; }
  function dist(m) { return m === null || m === undefined ? "" : m >= 1000 ? "직선 " + (m / 1000).toFixed(1) + "km" : "직선 " + m + "m"; }
  function save() { try { win.sessionStorage.setItem(KEY, JSON.stringify(state)); } catch (e) { /* private mode */ } }
  function load() { try { return JSON.parse(win.sessionStorage.getItem(KEY) || "null"); } catch (e) { return null; } }
  function getPlaces() {
    if (places) return Promise.resolve(places);
    if (!placesLoading) {
      placesLoading = fetch(PLACES).then(function (r) { if (!r.ok) throw new Error("places"); return r.json(); })
        .then(function (p) { places = p; return p; }).catch(function () { placesLoading = null; return {}; });
    }
    return placesLoading;
  }

  // ------------------------------------------------------------ the form
  var dateIn = form.querySelector("[data-plan-date]"), today = new Date();
  dateIn.min = iso(today);
  var last = new Date(today.getTime() + 180 * 86400000);
  dateIn.max = iso(last);
  var sat = new Date(today.getTime() + ((6 - today.getDay() + 7) % 7 || 7) * 86400000);
  dateIn.value = iso(sat);
  var counts = { adults: 2, seniors: 0, kids: 0 }, ages = [];
  function setCount(key, n) {
    counts[key] = n;
    form.querySelector('[data-count="' + key + '"] [data-count-value]').textContent = String(n);
  }
  function drawAges() {
    var box = form.querySelector("[data-ages]");
    box.textContent = "";
    ages.forEach(function (a, i) {
      var sel = h("select", { "aria-label": (i + 1) + "번째 아이 나이" });
      for (var y = 0; y <= 17; y += 1) sel.append(h("option", { value: String(y), text: y === 0 ? "1살 미만" : y + "살", selected: y === a }));
      sel.addEventListener("change", function () { ages[i] = +sel.value; summary(); });
      box.append(h("label", { class: "trp-age" }, [h("span", { text: "아이 " + (i + 1) }), sel]));
    });
  }
  form.querySelectorAll("[data-count]").forEach(function (c) {
    var key = c.getAttribute("data-count"), out = c.querySelector("[data-count-value]");
    c.addEventListener("click", function (e) {
      var b = e.target.closest("[data-step]");
      if (!b) return;
      var n = counts[key] + +b.getAttribute("data-step");
      var max = key === "adults" ? 10 : key === "seniors" ? counts.adults : 6;
      if (n < 0 || n > max || (key === "adults" ? n + counts.kids : key === "kids" ? counts.adults + n : 1) < 1) return;
      counts[key] = n;
      out.textContent = String(n);
      if (key === "adults" && counts.seniors > n) setCount("seniors", n);
      if (key === "kids") {
        while (ages.length < n) ages.push(7);
        ages.length = n;
        drawAges();
        if (n && !form.querySelector('input[name="with"][value="kids"]').checked) form.querySelector('input[name="with"][value="kids"]').checked = true;
      }
      summary();
    });
  });
  form.querySelector('input[name="with"][value="kids"]').addEventListener("change", function () {
    if (!counts.kids) form.querySelector('[data-count="kids"] [data-step="1"]').click();
  });
  form.querySelector('input[name="with"][value="solo"]').addEventListener("change", function () {
    if (counts.adults > 1) { setCount("adults", 1); if (counts.seniors > 1) setCount("seniors", 1); summary(); }
  });
  form.addEventListener("change", function (e) {
    if (e.target.name === "prefs") {
      var on = form.querySelectorAll('input[name="prefs"]:checked');
      if (on.length > MAX_PREFS) {
        e.target.checked = false;
        sumEl.textContent = "좋아하는 것은 " + MAX_PREFS + "개까지 고를 수 있어요.";
        return;
      }
    }
    summary();
  });
  form.querySelectorAll("[data-budget]").forEach(function (b) {
    b.addEventListener("click", function () { form.budget.value = b.getAttribute("data-budget"); summary(); });
  });
  form.addEventListener("focusin", function () { getPlaces(); }, { once: true });

  function picked(name) { return Array.prototype.map.call(form.querySelectorAll('input[name="' + name + '"]:checked'), function (i) { return i.value; }); }
  function conditions() {
    var budget = form.budget.value === "" ? null : Math.max(0, Math.min(1000000, Math.round(+form.budget.value)));
    return { date: dateIn.value, days: +picked("days")[0], start: form.start.value, end: form.end.value,
      from: (form.elements.from && form.elements.from.value) || "", to: (form.elements.to && form.elements.to.value) || "",
      move: picked("move")[0], with: picked("with")[0], adults: counts.adults, seniors: counts.seniors, kids: ages.slice(),
      prefs: picked("prefs"), needs: picked("needs"), budget: isNaN(budget) ? null : budget,
      note: form.note.value.trim() || undefined };
  }
  // the form shows the conditions of the plan on screen after a reload (review 2026-10-17: the result came back, the
  // form went back to its defaults)
  function setForm(c) {
    if (c.date >= dateIn.min && c.date <= dateIn.max) dateIn.value = c.date;
    [["start", c.start], ["end", c.end], ["from", c.from || ""], ["to", c.to || ""]].forEach(function (x) {
      var el = form.elements[x[0]];
      if (el && Array.prototype.some.call(el.options, function (o) { return o.value === x[1]; })) el.value = x[1];
    });
    [["days", String(c.days)], ["move", c.move], ["with", c.with]].forEach(function (x) {
      var i = form.querySelector('input[name="' + x[0] + '"][value="' + x[1] + '"]');
      if (i) i.checked = true;
    });
    ["prefs", "needs"].forEach(function (name) {
      form.querySelectorAll('input[name="' + name + '"]').forEach(function (i) { i.checked = (c[name] || []).indexOf(i.value) >= 0; });
    });
    setCount("adults", c.adults);
    setCount("seniors", Math.min(c.seniors || 0, c.adults));
    ages = (c.kids || []).slice();
    setCount("kids", ages.length);
    drawAges();
    form.budget.value = c.budget === null || c.budget === undefined ? "" : String(c.budget);
    form.note.value = c.note || "";
    summary();
  }
  function label(name, value) {
    var i = form.querySelector('input[name="' + name + '"][value="' + value + '"]');
    return i ? i.closest(".trp-card").querySelector("b").textContent : value;
  }
  function describe(c) {
    var who = "어른 " + c.adults + (c.seniors ? "(65세 이상 " + c.seniors + ")" : "")
      + (c.kids.length ? ", 아이 " + c.kids.map(function (a) { return a ? a + "살" : "1살 미만"; }).join("·") : "");
    var bits = [c.date ? dayName(c.date) : "날짜 미정", label("days", c.days), LABEL.move[c.move], LABEL.with[c.with] + "(" + who + ")"];
    if (c.from || c.to) bits.push((c.from ? HUBS[c.from] + " " + c.start + " 출발" : "") + (c.from && c.to ? " → " : "") + (c.to ? HUBS[c.to] + " " + c.end + " 도착" : ""));
    if (c.prefs.length) bits.push(c.prefs.map(function (p) { return label("prefs", p); }).join("·"));
    if (c.needs.length) bits.push(c.needs.map(function (p) { return label("needs", p); }).join("·"));
    if (c.budget !== null) bits.push("입장료 " + won(c.budget) + " 이내");
    return bits.join(" · ");
  }
  function summary() { sumEl.textContent = describe(conditions()); if (!applying) hideProblems(); }
  summary();

  // conditions in the address (/plan/?date=2026-10-24&days=2&start=10:00&move=transit&with=kids&adults=2&kids=8,5&
  // needs=rain&prefs=history,food&from=station&to=station&note=…): the assistant's hand-over, put on the form's
  // defaults. Each value is checked against the form's own choices (a radio or check box with that value, a select's
  // option, the date's range, the counters' bounds); an unknown value is left out, the form's default stays. Then the
  // rules the form's own buttons keep between who comes and how many (people()), so the form never shows what it
  // could not. Returns whether anything was put in.
  function fromAddress() {
    var q;
    try { q = new URLSearchParams(win.location.search); } catch (e) { return false; }
    var any = false;
    var get = function (k) { var v = q.get(k); return v === null ? "" : v.trim(); };
    var list = function (k) { return get(k).split(",").map(function (x) { return x.trim(); }).filter(Boolean); };
    var d = get("date");
    if (/^\d{4}-\d{2}-\d{2}$/.test(d) && d >= dateIn.min && d <= dateIn.max) { dateIn.value = d; any = true; }
    var box = function (name, v) {   // the radio or check box of that value, or null (only plain values are looked up)
      return /^[a-z0-9]+$/.test(v) ? form.querySelector('input[name="' + name + '"][value="' + v + '"]') : null;
    };
    ["days", "move", "with"].forEach(function (name) {
      var i = box(name, get(name));
      if (i) { i.checked = true; any = true; }
    });
    ["start", "end", "from", "to"].forEach(function (name) {
      var v = get(name), el = form.elements[name];
      if (v && el && Array.prototype.some.call(el.options, function (o) { return o.value === v; })) { el.value = v; any = true; }
    });
    var count = function (k, max) { var v = get(k); return /^\d{1,2}$/.test(v) && +v <= max ? +v : null; };
    var adults = count("adults", 10), seniors = count("seniors", 10);
    var kids = list("kids");
    kids = kids.length && kids.length <= 6 && kids.every(function (x) { return /^\d{1,2}$/.test(x) && +x <= 17; }) ? kids.map(Number) : null;
    if ((adults === null ? counts.adults : adults) + (kids ? kids.length : counts.kids) >= 1) {
      if (adults !== null) { setCount("adults", adults); any = true; }
      if (kids) { ages = kids; setCount("kids", kids.length); drawAges(); any = true; }
    }
    if (seniors !== null) { setCount("seniors", Math.min(seniors, counts.adults)); any = true; }
    else if (counts.seniors > counts.adults) setCount("seniors", counts.adults);
    ["prefs", "needs"].forEach(function (name) {
      var want = list(name).filter(function (v) { return box(name, v); });
      if (name === "prefs") want = want.slice(0, MAX_PREFS);
      if (!want.length) return;
      form.querySelectorAll('input[name="' + name + '"]').forEach(function (i) { i.checked = want.indexOf(i.value) >= 0; });
      any = true;
    });
    var note = get("note");
    if (note) { form.note.value = Array.from(note).slice(0, +form.note.getAttribute("maxlength") || 200).join(""); any = true; }
    if (any) { people(); summary(); }
    return any;
  }
  // who comes and how many, as the form's buttons keep them: a child makes it 아이와 가족 (the child counter), 아이와
  // 가족 has a child (the card adds one of 7), 혼자 is one adult (the card), 65세 이상 are among the adults
  function people() {
    var w = picked("with")[0];
    if (counts.kids && w !== "kids") { form.querySelector('input[name="with"][value="kids"]').checked = true; w = "kids"; }
    if (w === "kids" && !counts.kids) { ages = [7]; setCount("kids", 1); drawAges(); }
    if (w === "solo" && counts.adults !== 1) setCount("adults", 1);
    if (counts.seniors > counts.adults) setCount("seniors", counts.adults);
  }

  form.addEventListener("submit", function (e) {
    e.preventDefault();
    var c = conditions();
    var err = "";
    if (!c.date || c.date < dateIn.min || c.date > dateIn.max) err = "여행 날짜는 오늘부터 180일 안에서 골라 주세요.";
    else if (+c.end.slice(0, 2) - +c.start.slice(0, 2) < 3) err = "하루 일정은 3시간 이상으로 골라 주세요.";
    formErr.hidden = !err;
    formErr.textContent = err;
    if (err) return;
    track("plan_submit", { days: c.days, move: c.move, with: c.with });
    hideProblems();
    ask({ conditions: c }, c, false);
  });

  // ------------------------------------------------------------ asking the server
  var STEPS = ["search", "read", "check", "submit", "fix"];
  function setStep(step) {
    var at = STEPS.indexOf(step === "fees" ? "submit" : step);
    work.querySelectorAll("[data-step]").forEach(function (li) {
      var i = STEPS.indexOf(li.getAttribute("data-step"));
      li.classList.toggle("on", i === at);
      li.classList.toggle("done", i < at);
      if (li.getAttribute("data-step") === "fix") li.hidden = step !== "fix";
    });
  }
  function busy(on) {
    work.hidden = !on;
    form.querySelector(".trp-submit").disabled = on;
    if (on) {
      setStep("search");
      live.textContent = "";
      work.scrollIntoView({ block: "start", behavior: "smooth" });
      work.querySelector("h2").focus({ preventScroll: true });
    }
  }
  var t0 = 0, tick = null, LIMIT_S = 70;   // the page gives up after 70 s (the server's own limit is 55 s)
  function ask(body, c, edit) {
    if (ctrl) ctrl.abort();
    ctrl = new AbortController();
    var mine = ctrl;
    busy(true);
    t0 = Date.now();
    clearInterval(tick);
    tick = setInterval(function () {
      var sec = Math.round((Date.now() - t0) / 1000);
      live.textContent = sec + "초째 " + (edit ? "고치고" : "만들고") + " 있어요" + (sec >= 40 ? " · 거의 다 됐어요" : "");
      if (sec >= LIMIT_S && mine === ctrl) { mine.late = true; mine.abort(); }
    }, 1000);
    getPlaces();
    fetch(API, { method: "POST", headers: { "content-type": "application/json" }, body: JSON.stringify(body), signal: mine.signal })
      .then(function (res) {
        if (!res.ok || !res.body) {
          return res.json().catch(function () { return {}; }).then(function (j) { throw { code: j.code || "error", message: j.message, problems: j.problems }; });
        }
        var reader = res.body.getReader(), dec = new TextDecoder(), buf = "", done = null;
        function pump() {
          return reader.read().then(function (r) {
            if (r.done) { if (!done) throw { code: "error" }; return done; }
            buf += dec.decode(r.value, { stream: true });
            var parts = buf.split("\n\n");
            buf = parts.pop();
            parts.forEach(function (p) {
              if (p.indexOf("data: ") !== 0) return;
              var ev;
              try { ev = JSON.parse(p.slice(6)); } catch (x) { return; }
              if (ev.type === "status") setStep(ev.step);
              else if (ev.type === "plan") done = ev.plan;
              else if (ev.type === "error") throw { code: ev.code, message: ev.message, problems: ev.problems };
            });
            return pump();
          });
        }
        return pump();
      })
      .then(function (plan) {
        if (mine !== ctrl) return;
        if (!fits(plan)) throw { code: "error" };
        // after an edit: what changed against the plan it was made from (review 2026-10-17: a café added, the fees
        // and the access facts changed unasked)
        var diff = edit && state && fits(state.plan) ? diffPlans(state.plan, plan) : null;
        state = { conditions: c, plan: plan, diff: diff };
        save();
        track(edit ? "plan_edit" : "plan_done", { days: c.days, flags: (plan.flags || []).length, status: plan.status, code: codeBuilt(plan) ? 1 : 0 });
        return getPlaces().then(function () { show(true); });
      })
      .catch(function (err) {
        if (mine !== ctrl) return;
        if (err && err.name === "AbortError" && !mine.late) { busy(false); return; }
        if (mine.late) err = { code: "timeout", message: "1분 넘게 걸려 멈췄어요. 다시 시도하거나, 기간을 줄이거나 조건을 덜 골라 주세요." };
        // conditions no plan can meet (planner preflight): back to the form, the causes and their fixes by the button
        if (err && err.code === "conditions" && Array.isArray(err.problems) && err.problems.length && !edit) {
          track("plan_conditions", { fields: err.problems.map(function (x) { return String(x.field || ""); }).join(",") });
          showProblems(err, c);
          return;
        }
        track("plan_error", { code: (err && err.code) || "error" });
        // the server's own messages only; a script error is never shown as it is
        failed((err && err.code && err.message) || "코스를 만들지 못했습니다. 다시 시도해 주세요.", body, c, edit);
      })
      .then(function () { if (mine === ctrl) { clearInterval(tick); busy(false); ctrl = null; } });
  }
  work.querySelector("[data-plan-cancel]").addEventListener("click", function () { if (ctrl) ctrl.abort(); });

  // ------------------------------------------------------------ conditions no plan can meet (planner preflight)
  // {message, problems: [{field, text, fixes: [{label, set?, focus?}]}]}: the server's own words, a fix that sets the
  // form (the same controls the reader uses, so the summary and the counters follow) or puts the cursor on a field.
  // A change by hand makes the box stale and it goes.
  var applying = false;
  var goBox = form.querySelector(".trp-go");
  var prob = h("div", { class: "trp-prob", role: "alert", hidden: true });
  goBox.parentNode.insertBefore(prob, goBox);   // above the button's bar (on phones that bar stays at the screen's foot)
  function hideProblems() { if (prob && !prob.hidden) { prob.hidden = true; prob.textContent = ""; } }
  var FOCUS = { date: function () { return dateIn; }, days: "days", move: "move", with: "with", prefs: "prefs", needs: "needs",
    adults: '[data-count="adults"] [data-step="1"]', seniors: '[data-count="seniors"] [data-step="1"]', kids: '[data-count="kids"] [data-step="1"]' };
  function fieldEl(name) {
    var f = FOCUS[name];
    if (typeof f === "function") return f();
    if (f && f.charAt(0) === "[") return form.querySelector(f);
    if (f) return form.querySelector('input[name="' + f + '"]:checked') || form.querySelector('input[name="' + f + '"]');
    return form.elements[name] || null;
  }
  function showProblems(err, c) {
    formErr.hidden = true;
    prob.textContent = "";
    var done = h("p", { class: "trp-prob-done", role: "status" });
    var list = h("ul", { class: "trp-prob-l" }, err.problems.map(function (x) {
      var fixes = (x.fixes || []).filter(function (f) { return f && f.label && (f.set || f.focus); }).map(function (f) {
        var b = h("button", { type: "button", class: "btn btn-ol trp-prob-fix", text: f.label });
        b.addEventListener("click", function () {
          track("plan_fix", { kind: "conditions" });
          if (f.set) {
            var next = Object.assign(conditions(), f.set);
            applying = true;
            try { setForm(next); } finally { applying = false; }
            done.textContent = "조건을 바꿨어요. 바꾼 조건은 아래 요약 줄에 있어요.";
            go.hidden = false;
            go.scrollIntoView({ block: "center" });   // clear of the button's bar at the foot of a phone's screen
            go.focus({ preventScroll: true });
          } else {
            var el = fieldEl(f.focus);
            if (el) { el.scrollIntoView({ block: "center", behavior: "smooth" }); el.focus({ preventScroll: true }); }
          }
        });
        return b;
      });
      return h("li", {}, [h("p", { text: x.text })].concat(fixes.length ? [h("div", { class: "trp-prob-fixes" }, fixes)] : []));
    }));
    var go = h("button", { type: "submit", class: "btn trp-prob-go", text: "바꾼 조건으로 코스 만들기", hidden: true });
    prob.append(h("h3", { tabindex: "-1", text: "이 조건으로는 코스를 끝까지 짤 수 없어요" }),
      h("p", { class: "trp-prob-m", text: (err.message || "").replace(/^이 조건으로는 코스를 끝까지 짤 수 없어요\.\s*/, "") || "아래를 바꿔 주세요." }), list, done, go);
    prob.hidden = false;
    prob.scrollIntoView({ block: "center" });
    prob.querySelector("h3").focus({ preventScroll: true });
  }

  function failed(message, body, c, edit) {
    var again = h("button", { type: "button", class: "btn", text: "다시 시도" });
    again.addEventListener("click", function () { ask(body, c, edit); });
    if (edit && state) {   // a change that failed: the plan stays, the message sits above the edit box
      draw(false);
      var box = result.querySelector(".trp-edit");
      var note = h("div", { class: "trp-fail trp-fail-edit", role: "alert" }, [mascot("sorry"), h("div", {}, [
        h("h3", { tabindex: "-1", text: "바꾸지 못했어요" }), h("p", { text: message }), again])]);
      box.prepend(note);
      note.querySelector("h3").focus();
      return;
    }
    result.hidden = false;
    result.textContent = "";
    result.append(h("div", { class: "wrap trp-fail", role: "alert" }, [mascot("sorry"), h("div", {}, [
      h("h2", { id: "h-result", tabindex: "-1", text: "코스를 만들지 못했어요" }), h("p", { text: message }), again,
      fallbackHint()])]));
    result.querySelector("h2").focus();
  }


  // ------------------------------------------------------------ the result
  var curDay = 0;
  // a plan this page can draw: the server's checked plan (planner.js finish v 2); an older shape kept in the tab or a
  // reply missing a part is not drawn (review 2026-10-17 CE10: a fee object without amounts broke the page)
  function fits(p) {
    return !!(p && p.v === 2 && Array.isArray(p.days) && p.days.length && p.days.every(function (d) { return d && Array.isArray(d.stops); })
      && p.fees && typeof p.fees === "object" && Array.isArray(p.checks) && Array.isArray(p.needs));
  }
  function num(n) { return typeof n === "number" && isFinite(n); }
  // a plan the site built from its own data when the AI gave none it could use (planner codePlan): one 'fixed' line
  // starting '일정 전체:', every stop put in by the site
  function codeBuilt(p) { return !!(p && (p.fixed || []).length === 1 && /^일정 전체:/.test(p.fixed[0])); }
  function codeLine(p) { return p.fixed[0].replace(/^일정 전체:\s*/, "").replace(/짰습니다$/, "짰어요"); }
  function money(n) { return num(n) ? won(n) : "—"; }
  function factRow(label, value, cls) {
    if (!value) return null;
    return h("li", { class: cls || "" }, [h("span", { class: "trp-fl", text: label }), h("span", { text: value })]);
  }
  function stopCard(s, n) {
    var p = (places || {})[s.path] || {};
    var ph;
    if (p.img) {
      var img = h("img", { src: p.img.u, alt: p.img.alt || p.n || s.name, loading: "lazy", decoding: "async",
        width: p.img.w || null, height: p.img.h || null, "data-kogl": String(p.img.t) });
      if (p.img.s && p.img.sw && p.img.w) { img.setAttribute("srcset", p.img.s + " " + p.img.sw + "w, " + p.img.u + " " + p.img.w + "w"); img.setAttribute("sizes", "(min-width: 768px) 200px, 112px"); }
      ph = h("figure", { class: "trp-ph" + (p.img.t === 3 ? " t3" : " t1") }, [img, h("figcaption", { text: "출처: 한국관광공사" })]);
    } else {
      ph = h("div", { class: "trp-ph trp-ph-pic" }, [pic(p.ic || "kind-attraction")]);
    }
    var st = s.day || "unknown";
    var facts = h("ul", { class: "trp-facts" }, [
      h("li", { class: "trp-day trp-day-" + st }, [h("span", { class: "trp-fl", text: "그날" }), h("span", { text: LABEL.day[st].replace("그날 ", "") })]),
      factRow("시간", p.h), factRow("쉬는 날", p.c, "trp-closed"),
      factRow(p.k === "food" || p.k === "cafe" ? "메뉴" : "요금", p.k === "food" || p.k === "cafe" ? p.m : p.f), factRow("주차", p.p),
      s.role === "stay" ? factRow("체크인", p.ci) : null]);
    var notes = (s.flags || []).map(function (f) { return h("li", { class: "bad", text: f }); })
      .concat((s.checks || []).map(function (f) { return h("li", { text: "확인: " + f }); }));
    var kind = [LABEL.role[s.role] || "", p.t, p.r ? p.r + " 권역" : ""].filter(Boolean).join(" · ");
    // a stop the site put in itself (planner.repair): said so, where the AI's reason would be
    var by = state && codeBuilt(state.plan) ? "" : s.added ? (s.role === "meal" ? "식사할 곳이 없어 사이트가 넣은 가까운 음식점이에요"
      : s.role === "stay" ? "묵을 곳이 없어 사이트가 넣은 숙소예요" : "빈 시간이 길어 사이트가 넣은 가까운 곳이에요")
      : s.swapped ? "그날 쉬는 곳 대신 사이트가 고른 가까운 곳이에요" : "";
    return h("li", { class: "trp-stop", "data-day": st, "data-role": s.role, "data-by": s.added ? "site" : s.swapped ? "swap" : null }, [
      h("div", { class: "trp-time" }, [h("span", { class: "trp-num", text: String(n) }), h("b", { class: "tn", text: s.start }), h("span", { class: "tn", text: "~" + s.end })]),
      h("article", { class: "trp-card2" }, [ph, h("div", { class: "trp-body" }, [
        h("p", { class: "trp-kind", text: kind }),
        h("h3", {}, [h("a", { href: s.path, text: s.name })]),
        s.why ? h("p", { class: "trp-why" }, [h("span", { class: "trp-ai", text: "AI" }), h("span", { text: s.why })]) : null,
        by ? h("p", { class: "trp-why trp-by" }, [h("span", { class: "trp-site", text: "사이트" }), h("span", { text: by })]) : null,
        facts, notes.length ? h("ul", { class: "trp-warn" }, notes) : null])])]);
  }
  // a leg: its straight line, the margin the plan keeps, shared bus routes, a directions link; the line that the real
  // travel time is not known is said once above the day (legNote), and under a leg only when the leg is flagged
  function legRow(l, move) {
    var icon = l.mode === "car" ? "fact-parking" : l.mode === "walk" ? "sit-walk" : "transit-bus";
    var bits = [h("span", { class: "trp-leg-d tn", text: dist(l.m) || "거리 모름" })];
    bits.push(h("span", { class: "trp-leg-g", text: l.gap > 0 ? "계획상 여유 " + l.gap + "분" : "여유 없음" }));
    if (move === "transit" && l.routes && l.routes.length) bits.push(h("span", { class: "trp-leg-r", text: "근처 정류장에 같은 번호 노선 " + l.routes.join("·") + "번(방향·시각 확인)" }));
    var go = l.url ? h("a", { class: "trp-leg-go", href: l.url, target: "_blank", rel: "noopener", text: "카카오맵 " + LABEL.mode[l.mode] + " 길찾기" }) : null;
    return h("li", { class: "trp-leg" + (l.flag ? " trp-leg-bad" : "") }, [pic(icon), h("div", { class: "trp-leg-in" }, [
      h("p", {}, bits), l.flag ? h("p", { class: "trp-leg-note", text: l.flag + " — 지도 앱에서 실제 시간을 확인하세요" }) : null, go])]);
  }
  function legNote(day) {
    return (day.legs || []).length ? h("p", { class: "trp-tl-note" }, [pic("transit-bus"),
      h("span", { text: "장소 사이 거리는 직선거리이고, 시간은 계획에 둔 여유예요. 실제 이동 시간은 확인되지 않았어요 — 구간마다 있는 카카오맵 길찾기로 확인하세요." })]) : null;
  }
  function hubRow(hb) {   // the trip's start or end at a station or a terminal: no point on the site, a link by names
    var from = hb.dir === "from";
    return h("li", { class: "trp-leg trp-hub" + (hb.gap > 0 ? "" : " trp-leg-bad") }, [pic("transit-bus"), h("div", { class: "trp-leg-in" }, [
      h("p", {}, [h("span", { class: "trp-leg-d", text: from ? hb.name + " " + hb.at + " 출발" : hb.name + " " + hb.at + "까지 도착" }),
        h("span", { class: "trp-leg-g", text: (from ? "첫 장소까지 계획상 여유 " : "마지막 장소 뒤 계획상 여유 ") + Math.max(0, hb.gap) + "분" })]),
      h("p", { class: "trp-leg-note", text: "이동 시간·거리는 사이트에 없어요 — 지도 앱에서 확인하세요" }),
      h("a", { class: "trp-leg-go", href: hb.url, target: "_blank", rel: "noopener", text: "카카오맵 길찾기" })])]);
  }
  function dayMap(day) {
    var pts = [];
    day.stops.forEach(function (s, i) {
      var p = (places || {})[s.path];
      if (p && p.g) pts.push({ lat: p.g[0], lng: p.g[1], name: s.name, url: s.path, n: i + 1 });
    });
    if (pts.length < 1) return h("p", { class: "trp-nomap", text: "이 날의 장소에는 지도 좌표가 없어요." });
    var box = h("div", { class: "map", role: "region", "aria-label": day.label + " 지도", "data-map": JSON.stringify({ course: pts }),
      "data-kakao-sdk": root.getAttribute("data-kakao-sdk") || null }, [h("p", { class: "map-off", text: "지도를 불러오는 중입니다." })]);
    var fig = h("figure", { class: "trp-map" }, [box, h("figcaption", { text: "번호는 일정 순서 · 지도: 카카오맵" + (pts.length < day.stops.length ? " · 좌표가 있는 " + pts.length + "곳만 표시" : "") })]);
    setTimeout(function () { startMap(box); }, 0);
    return fig;
  }
  function startMap(box) {
    if (!box.getAttribute("data-kakao-sdk")) return;
    if (win.GSMapStart) { win.GSMapStart(box); return; }
    var s = doc.querySelector('script[src$="map.js"]');
    if (!s) { s = h("script", { src: BASE + "map.js" }); doc.body.append(s); }
    s.addEventListener("load", function () { if (win.GSMapStart) win.GSMapStart(box); });
  }

  // ------------------------------------------------------------ what the code says about the plan
  // 'check' is a plan made before 2026-10-18 kept in the tab: it broke nothing either (its checks were notes)
  var STATUS = {
    ready: ["ok", "완성된 코스예요"],
    check: ["ok", "완성된 코스예요"],
    unmet: ["bad", "조건을 다 맞추지 못한 초안이에요"],
  };
  var MARK = { ok: "✓", info: "i", bad: "!", na: "–" };
  // finish 'aware' (2026-10-18 on); for a plan kept from before, the same kinds out of its checks
  var AWARE_K = { move: 1, hub: 1, stay: 1, walk: 1 };
  function awareOf(plan) {
    return Array.isArray(plan.aware) ? plan.aware : plan.checks.filter(function (x) { return AWARE_K[x.k]; });
  }
  function checksOf(plan) {
    return plan.checks.filter(function (x) { return !AWARE_K[x.k] && !/^걷기: /.test(x.t); });
  }
  var FEE_STATE = { none: "입장료를 내는 방문지 없음", free: "모두 무료(요금 값 기준)", known: "", partial: "", unknown: "요금 확인 필요" };
  function feeHead(f) {   // [the amount as shown, a short line]: never a number the server did not give
    if (f.state === "none") return ["—", FEE_STATE.none];
    if (f.state === "free") return ["0원", FEE_STATE.free];
    if (f.state === "known") return [money(f.total), "모든 사람·방문지 계산됨"];
    if (f.state === "partial") return [money(f.known) + " + 확인 필요", "확인 필요 " + (f.open || []).length + "건 — 합계 확정 안 됨"];
    return ["확인 필요", "요금 정보 없음 " + (f.open || []).length + "건"];
  }
  function verdictText(f) {
    return { within: "예산 안", over: "예산 넘음", open: "예산 충족 확정 못 함(확인 필요 남음)", none: "" }[f.verdict] || "";
  }
  function counted(plan) {
    var n = { all: 0, closed: 0, timeBad: 0, dayCheck: 0 };
    plan.days.forEach(function (d) {
      d.stops.forEach(function (s) {
        n.all += 1;
        if (s.day === "closed") n.closed += 1;
        else if ((s.flags || []).length) n.timeBad += 1;
        if (s.day === "unknown" || (s.checks || []).length) n.dayCheck += 1;
      });
    });
    var need = { ok: 0, check: 0, bad: 0, any: false };
    plan.needs.forEach(function (x) {
      need.any = true;
      x.rows.forEach(function (r) { if (r.state === "ok" || r.state === "near") need.ok += 1; else if (r.state === "no") need.bad += 1; else if (r.state === "unknown") need.check += 1; });
    });
    n.need = need;
    return n;
  }
  // how complete the day is (planner finish 'complete'): [state, words] — '점심 포함 · 역사·문화 반영 / 섬·바다 미반영 ·
  // 13:00~16:30 3시간 30분 비어 있음'; null for a plan made before it was there
  var MEAL = { lunch: "점심", dinner: "저녁" };
  var MEAL_STATE = { ok: "포함", added: "사이트가 넣음", skip: "따로(적은 대로)", missing: "빠짐" };
  var EDIT_STATE = { kept: "유지", restored: "사이트가 다시 넣음", dropped: "요청대로 뺌", lost: "빠짐" };
  function completeLine(plan) {
    var cp = plan.complete;
    if (!cp || !Array.isArray(cp.meals) || !Array.isArray(cp.gaps) || !Array.isArray(cp.prefs)) return null;
    var many = plan.days.length > 1, bad = false, check = false, parts = [], meals = [];
    // per meal: '1·2·3일차 점심 포함' when the days agree, else day by day
    ["lunch", "dinner"].forEach(function (kind) {
      var ms = cp.meals.filter(function (m) { return m.kind === kind; });
      if (ms.some(function (m) { return m.state === "missing"; })) bad = true;
      var one = ms.length > 1 && ms.every(function (m) { return m.state === ms[0].state; });
      (one ? [ms[0]] : ms).forEach(function (m) {
        var days = one ? ms.map(function (x) { return x.day + 1; }).join("·") : String(m.day + 1);
        meals.push((many ? days + "일차 " : "") + MEAL[kind] + " " + (MEAL_STATE[m.state] || m.state));
      });
    });
    if (meals.length) parts.push(meals.join(", "));
    var met = cp.prefs.filter(function (p) { return p.met === true; }).map(function (p) { return p.label; });
    var unmet = cp.prefs.filter(function (p) { return p.met === false; }).map(function (p) { return p.label; });
    var unknown = cp.prefs.filter(function (p) { return p.met === null; }).map(function (p) { return p.label; });
    if (unmet.length || unknown.length) check = true;   // shown as information: a liking is not a condition
    var likes = [met.length ? met.join("·") + " 반영" : "", unmet.length ? unmet.join("·") + " 미반영" : "",
      unknown.length ? "자료로 판단 못 함: " + unknown.join("·") : ""].filter(Boolean);
    if (likes.length) parts.push(likes.join(" / "));
    if (cp.gaps.length) {
      bad = true;
      parts.push(cp.gaps.map(function (g) { return (many ? (g.day + 1) + "일차 " : "") + g.from + "~" + g.to + " " + hm(g.minutes) + " 비어 있음"; }).join(", "));
    } else parts.push("2시간 넘게 빈 시간 없음");
    (cp.edit || []).forEach(function (x) {
      if (x.state === "lost") bad = true;
      parts.push("고치기 전 일정의 " + x.what + ": " + (EDIT_STATE[x.state] || x.state));
    });
    return [bad ? "bad" : check ? "info" : "ok", parts.join(" · ")];
  }
  // the quick fixes of an 'unmet' plan (planner finish 'todo'): each sends the edit request below with fixed words
  var FIX = {
    closed: ["휴무 장소 바꾸기", "그날 쉬는 장소를 그날 여는 가까운 장소로 바꿔 주세요"],
    legs: ["이동 구간 다시 짜기", "이동이 빠듯한 구간은 여유를 두고, 가까운 곳끼리 이어지게 다시 짜 주세요"],
    meal: ["빠진 점심 넣기", "빠진 점심을 그 시간에 여는 가까운 음식점으로 넣어 주세요"],
    gaps: ["빈 시간 채우기", "비어 있는 시간에 가까운 장소를 넣어 주세요"],
  };
  function quickFixes(plan) {
    var todo = (plan.todo || []).filter(function (k) { return FIX[k]; });
    if (plan.status !== "unmet" || !todo.length) return null;
    var missing = ((plan.complete || {}).meals || []).filter(function (m) { return m.state === "missing"; }).map(function (m) { return m.kind; });
    var meal = missing.indexOf("lunch") < 0 && missing.indexOf("dinner") >= 0 ? "저녁" : missing.indexOf("dinner") >= 0 ? "식사" : "점심";
    return h("div", { class: "trp-qfix", role: "group", "aria-label": "남은 문제 바로 고치기" }, [h("p", { class: "trp-qfix-h", text: "남은 문제를 AI에게 다시 맡기기" })].concat(todo.map(function (k) {
      var label = FIX[k][0].replace("점심", meal), ask = FIX[k][1].replace("점심", meal);
      var b = h("button", { type: "button", class: "btn btn-ol trp-qf", "data-fix": k, text: label });
      b.addEventListener("click", function () { track("plan_fix", { kind: k }); sendEdit(ask); });
      return b;
    })));
  }
  function statusPanel(plan) {
    var n = counted(plan), f = plan.fees, st = STATUS[plan.status] || STATUS.ready;
    var done = completeLine(plan);
    var rows = [
      ["fact-hours", "정기 휴무·운영시간",
        n.closed ? ["bad", "그날 휴무인 곳 " + n.closed + "곳"] : n.timeBad ? ["bad", "시간이 맞지 않는 곳 " + n.timeBad + "곳"]
          : ["ok", "정기 규칙상 " + (n.all - n.closed) + "/" + n.all + "곳 방문 가능"]],
      // a holiday or a date's rule (review 2026-10-18: '날짜 규칙에 걸리는 곳 없음' beside '정기 휴무 5곳'): never
      // all-clear while a stop is closed that day
      ["fact-closed", "공휴일·특별 운영",
        n.dayCheck ? ["info", "그날 운영 자료가 없는 곳 " + n.dayCheck + "곳 — 장소 칸에 적어 두었어요"]
          : n.closed ? ["bad", "그날 쉬는 곳 " + n.closed + "곳이 남아 있음 · 그 밖에 공휴일·날짜별 공지로 걸리는 곳은 없음"]
            : ["ok", "공휴일·날짜별 공지에 걸리는 곳 없음"]],
      ["cond-wheelchair", "필요한 조건",
        !n.need.any ? ["na", "고른 조건 없음"]
          : [n.need.bad ? "bad" : n.need.check ? "info" : "ok", "자료 있음 " + n.need.ok + " · 정보 없음 " + n.need.check + " · 맞지 않음 " + n.need.bad]],
      ["plan-budget", "입장료",
        [f.verdict === "over" ? "bad" : f.state === "partial" || f.state === "unknown" ? "info" : "ok",
          feeHead(f)[0] + (verdictText(f) ? " · " + verdictText(f) : f.state === "partial" || f.state === "unknown" ? " · 요금 자료 없는 곳은 빼고 셈" : "")]],
      ["transit-bus", "이동", ["info", "구간마다 계획상 여유를 두었어요 · 실제 이동 시간은 지도 앱에서"]],
    ];
    if (done) rows.push(["kind-food", "일정 완성도", done]);
    var list = h("ul", { class: "trp-st4" }, rows.map(function (r) {
      return h("li", { class: "is-" + r[2][0] }, [pic(r[0]), h("span", { class: "trp-st4-l", text: r[1] }),
        h("span", { class: "trp-st4-v" }, [h("i", { class: "trp-mark", "aria-hidden": "true", text: MARK[r[2][0]] }), r[2][1]])]);
    }));
    return h("section", { class: "trp-status is-" + st[0], "aria-labelledby": "h-status" }, [
      h("h3", { id: "h-status" }, [h("i", { class: "trp-mark", "aria-hidden": "true", text: MARK[st[0]] }), st[1]]),
      (plan.flags || []).length ? h("ul", { class: "trp-flags" }, plan.flags.map(function (x) { return h("li", { text: x }); })) : null,
      list,
      quickFixes(plan)]);
  }
  function feeCard(f) {
    var head = feeHead(f), lines = [];
    (f.days || []).forEach(function (d, i) {
      d.lines.forEach(function (l) {
        var v = l.status === "paid" && num(l.won) ? won(l.won) + " × " + l.count + " = " + money(l.sub) : l.status === "free" ? "0원" : "확인 필요";
        lines.push(h("li", { class: "is-" + l.status }, [h("b", { text: ((f.days.length > 1) ? (i + 1) + "일차 " : "") + l.what + " · " + l.who + " " + l.count + "명: " }),
          h("span", { class: "tn", text: v }), h("small", { text: " (" + l.basis + ")" })]));
      });
    });
    return h("section", { class: "trp-box trp-budget-c", id: "trp-fees" }, [
      h("div", { class: "trp-box-h" }, [pic("plan-budget"), h("h3", { text: "입장료" })]),
      h("p", { class: "trp-total tn", text: head[0] }),
      h("p", { class: "trp-verdict trp-v-" + (f.verdict === "over" ? "over" : f.state === "partial" || f.state === "unknown" ? "partial" : "ok"),
        text: head[1] + (verdictText(f) ? " · " + verdictText(f) + (num(f.limit) ? " (예산 " + won(f.limit) + ")" : "") : "") }),
      lines.length ? h("ul", { class: "trp-lines" }, lines) : null,
      (f.conds || []).length ? h("ul", { class: "trp-lines trp-conds" }, f.conds.map(function (x) { return h("li", { text: x }); })) : null,
      h("p", { class: "trp-hint", text: "사이트가 장소 요금표와 통합권 요금표로 사람마다 계산했어요(통합권은 하루에 한 번, 더 싼 쪽). 식비·교통비·숙박비는 들어 있지 않아요." })]);
  }
  // what the data does not say (finish 'checks') and what holds for any plan (finish 'aware'), in one closed box —
  // information for the day, never a list of problems (operator 2026-10-18)
  var KLABEL = { day: "그날 운영", fee: "입장료", need: "필요한 조건", hub: "출발·도착", stay: "숙소", move: "이동", walk: "걷기" };
  function knowList(plan) {
    var all = checksOf(plan).concat(awareOf(plan));
    if (plan.checks.some(function (x) { return /^걷기: /.test(x.t); }) && !awareOf(plan).some(function (x) { return x.k === "walk"; })) {
      all = all.concat(plan.checks.filter(function (x) { return /^걷기: /.test(x.t); }).map(function (x) { return { k: "walk", t: x.t }; }));
    }
    return all;
  }
  function checkBox(plan) {
    var groups = {}, all = knowList(plan);
    all.forEach(function (x) { (groups[x.k] = groups[x.k] || []).push(x.t); });
    var kids = [];
    if ((plan.flags || []).length) kids.push(h("div", { class: "trp-qg bad" }, [h("h4", { text: "맞지 않는 것" }), h("ul", { class: "trp-qs" }, plan.flags.map(function (x) { return h("li", { class: "trp-q-flag", text: x }); }))]));
    Object.keys(KLABEL).forEach(function (k) {
      if (groups[k]) kids.push(h("div", { class: "trp-qg" }, [h("h4", { text: KLABEL[k] }), h("ul", { class: "trp-qs" }, groups[k].map(function (x) { return h("li", { text: x }); }))]));
    });
    if (!kids.length) return null;
    return h("details", { class: "trp-box trp-check-c", id: "trp-checks", open: (plan.flags || []).length ? true : null }, [
      h("summary", { class: "trp-box-h" }, [pic("fact-closed"), h("h3", { text: "가기 전에 알아 둘 것" })])].concat(kids));
  }
  function needsTable(plan) {   // the needs the reader picked × the stops: the data's own words in each cell
    if (!plan.needs.length) return null;
    var SYM = { ok: ["✓", "자료 있음"], near: ["△", "근처 주차장"], no: ["✕", "맞지 않음"], unknown: ["?", "정보 없음"], na: ["–", "해당 없음"] };
    var many = plan.days.length > 1;
    var rows = [];
    plan.days.forEach(function (d, di) {
      d.stops.forEach(function (s, i) {
        var cells = plan.needs.map(function (x) {
          var r = x.rows.filter(function (y) { return y.day === di && y.i === i; })[0] || { state: "na", text: "" };
          var sym = SYM[r.state] || SYM.na;
          var mark = h("span", { class: "trp-nd is-" + r.state }, [h("i", { "aria-hidden": "true", text: sym[0] }), h("span", { text: sym[1] })]);
          return h("td", {}, [r.text ? tooltip(mark, x.label + " — " + s.name + ": " + r.text) : mark]);
        });
        rows.push(h("tr", {}, [h("th", { scope: "row", text: (many ? (di + 1) + "일차 " : "") + (i + 1) + ". " + s.name })].concat(cells)));
      });
    });
    var table = h("table", { class: "trp-ndt" }, [h("thead", {}, [h("tr", {}, [h("th", { scope: "col", text: "장소" })].concat(plan.needs.map(function (x) { return h("th", { scope: "col", text: x.label }); })))]),
      h("tbody", {}, rows)]);
    return h("figure", { class: "trp-chart trp-needs" }, [h("figcaption", {}, [h("b", { text: "필요한 조건, 장소마다" }), h("span", { text: "칸을 누르면 사이트 자료의 내용이 보여요" })]),
      h("div", { class: "trp-ndt-w", "data-lenis-prevent": "" }, [table]),
      h("p", { class: "trp-hint", text: "✓ 자료에 맞는 내용이 있음(출입구 등 일부만 확인된 것일 수 있어요) · △ 자체 주차는 없고 근처 공영주차장 · ✕ 자료상 맞지 않음 · ? 사이트에 정보 없음" })]);
  }
  // ------------------------------------------------------------ the diagrams (operator: '답변을 여러 도식과 함께 화려하게')
  // Every number comes from the plan the server checked: times, roles, legs' straight-line distances, the fee state,
  // the day states. Colours (the dataviz skill's validator, adjacent CVD ΔE 9.1): 관람 sea blue · 식사 orange · 카페
  // aqua · 숙소 yellow, in that fixed order; the margins between places neutral grey. Aqua and yellow sit under 3:1 on
  // white, so every chart keeps visible labels (legend with values) and the stop list below is the table.
  var ROLES = [["visit", "관람", "#2F6FC9"], ["meal", "식사", "#eb6834"], ["cafe", "카페", "#1baf7a"], ["stay", "숙소", "#eda100"]];
  function mins(t) { var m = /^(\d{1,2}):(\d{2})$/.exec(t || ""); return m ? +m[1] * 60 + +m[2] : null; }
  function hm(n) { var hh = Math.floor(n / 60), m = n % 60; return (hh ? hh + "시간" : "") + (m ? (hh ? " " : "") + m + "분" : (hh ? "" : "0분")); }
  function km(m) { return m >= 1000 ? (m / 1000).toFixed(1) + "km" : m + "m"; }
  var tip = null;
  function tooltip(el, text) {
    el.setAttribute("tabindex", "0");
    if (!el.getAttribute("role")) el.setAttribute("role", "img");
    el.setAttribute("aria-label", text);
    var show = function () {
      if (!tip) { tip = h("div", { class: "trp-tip", role: "tooltip" }); doc.body.append(tip); }
      tip.textContent = text;
      tip.hidden = false;
      var r = el.getBoundingClientRect(), t = tip.getBoundingClientRect();
      var x = Math.max(8, Math.min(win.innerWidth - t.width - 8, r.left + r.width / 2 - t.width / 2));
      var y = r.top - t.height - 8 < 8 ? r.bottom + 8 : r.top - t.height - 8;
      tip.style.left = Math.round(x + win.scrollX) + "px";
      tip.style.top = Math.round(y + win.scrollY) + "px";
    };
    var hide = function () { if (tip) tip.hidden = true; };
    // a mouse shows it on hover; a finger taps (the tap focuses the mark) and it stays until the focus moves on
    el.addEventListener("pointerenter", function (e) { if (e.pointerType === "mouse") show(); });
    el.addEventListener("pointerleave", function (e) { if (e.pointerType === "mouse" && doc.activeElement !== el) hide(); });
    el.addEventListener("focus", show); el.addEventListener("click", show); el.addEventListener("blur", hide);
    return el;
  }
  function svg(tag, attrs) {
    var el = doc.createElementNS("http://www.w3.org/2000/svg", tag);
    Object.keys(attrs || {}).forEach(function (k) { el.setAttribute(k, attrs[k]); });
    return el;
  }
  function ring(part, whole) {   // a meter as a ring: the filled arc on a lighter track of the same blue
    var r = 26, c = 2 * Math.PI * r, f = whole ? part / whole : 0;
    var s = svg("svg", { viewBox: "0 0 64 64", width: "64", height: "64", class: "trp-ring", "aria-hidden": "true" });
    s.append(svg("circle", { cx: "32", cy: "32", r: String(r), fill: "none", stroke: "#D9E7F8", "stroke-width": "8" }));
    s.append(svg("circle", { cx: "32", cy: "32", r: String(r), fill: "none", stroke: "#2F6FC9", "stroke-width": "8", "stroke-linecap": "round",
      "stroke-dasharray": (c * f).toFixed(1) + " " + c.toFixed(1), transform: "rotate(-90 32 32)" }));
    return s;
  }
  function tile(picId, label, value, note, extra) {
    return h("li", { class: "trp-kpi" }, [h("div", { class: "trp-kpi-h" }, [pic(picId), h("span", { class: "trp-kpi-l", text: label })]),
      h("p", { class: "trp-kpi-v" }, [value]), note ? h("p", { class: "trp-kpi-n", text: note }) : null, extra || null]);
  }
  // the straight lines of the legs added up only when every leg has one (outside evaluation 2026-10-18: '구간 직선거리
  // 합 971m' over three legs of which one had a distance): {legs, known, metres, all}
  function lineSum(days) {
    var out = { legs: 0, known: 0, metres: 0 };
    days.forEach(function (d) { (d.legs || []).forEach(function (l) { out.legs += 1; if (num(l.m)) { out.known += 1; out.metres += l.m; } }); });
    out.all = out.legs > 0 && out.known === out.legs;
    return out;
  }
  function overview(plan) {
    var cnt = { visit: 0, meal: 0, cafe: 0, stay: 0 }, n = counted(plan), sum = lineSum(plan.days);
    plan.days.forEach(function (d) { d.stops.forEach(function (s) { cnt[s.role] = (cnt[s.role] || 0) + 1; }); });
    var mix = ROLES.filter(function (r) { return cnt[r[0]]; }).map(function (r) { return r[1] + " " + cnt[r[0]]; }).join(" · ");
    var f = plan.fees, head = feeHead(f), meter = null;
    if (num(f.limit) && num(f.known) && f.state !== "none") {
      var pct = f.limit ? Math.min(100, Math.round(f.known / f.limit * 100)) : 100;
      meter = h("div", { class: "trp-meter" + (f.verdict === "over" ? " over" : f.verdict === "open" ? " open" : ""), role: "img",
        "aria-label": "확인된 입장료 " + won(f.known) + " / 예산 " + won(f.limit) + (f.verdict === "open" ? ", 확인 필요가 남아 예산 충족 미확정" : "") }, [h("span", { style: "width:" + pct + "%" })]);
    }
    var ok = n.all - n.closed;
    var rowCheck = h("div", { class: "trp-kpi-ring" }, [ring(ok, n.all), h("span", { class: "tn", text: ok + "/" + n.all })]);
    return h("ul", { class: "trp-kpis", "aria-label": "코스 요약" }, [
      tile("icon-course", "들르는 곳", h("span", { class: "tn", text: n.all + "곳" }), mix),
      tile("transit-bus", "구간 직선거리 합", !sum.legs ? h("span", { class: "tn", text: "—" }) : sum.all ? h("span", { class: "tn", text: km(sum.metres) })
        : h("span", { class: "trp-kpi-x", text: "전체 이동거리 계산 안 됨" }),
        !sum.legs ? "구간 없음" : sum.all ? "구간 " + sum.legs + "개 · 실제 길 거리·시간 아님" : sum.legs + "개 구간 중 " + sum.known + "개만 거리 있음"),
      tile("plan-budget", "입장료", h("span", { class: "tn", text: head[0] }),
        num(f.limit) ? "예산 " + won(f.limit) + (verdictText(f) ? " · " + verdictText(f) : "") : head[1], meter),
      tile("fact-closed", "정기 규칙상 방문 가능", rowCheck, n.closed ? "그날 휴무 " + n.closed + "곳" + (n.dayCheck ? " · 운영 확인 필요 " + n.dayCheck + "곳" : "")
        : n.dayCheck ? "그날 운영 확인 필요 " + n.dayCheck + "곳" : "공휴일·날짜별 공지에 걸리는 곳 없음"),
    ]);
  }
  function timeline(plan) {   // one row per day on a shared clock: stops by role, margins grey, a mark where no time is left
    var lo = 24 * 60, hi = 0;
    plan.days.forEach(function (d) { d.stops.forEach(function (s) { lo = Math.min(lo, mins(s.start)); hi = Math.max(hi, mins(s.end)); }); });
    lo = Math.floor(lo / 60) * 60; hi = Math.ceil(hi / 60) * 60;
    var span = Math.max(60, hi - lo), pct = function (t) { return ((t - lo) / span * 100).toFixed(2) + "%"; };
    var totals = { gap: 0 }, tight = 0;
    var rows = plan.days.map(function (d, di) {
      var track = h("div", { class: "trp-tlx-track" });
      d.stops.forEach(function (s, i) {
        var a = mins(s.start), z = mins(s.end), role = ROLES.filter(function (r) { return r[0] === s.role; })[0] || ROLES[0];
        totals[s.role] = (totals[s.role] || 0) + (z - a);
        var seg = h("span", { class: "trp-seg", style: "left:" + pct(a) + ";width:calc(" + ((z - a) / span * 100).toFixed(2) + "% - 2px);background:" + role[2] },
          [h("span", { class: "trp-seg-n", text: String(i + 1) })]);
        track.append(tooltip(seg, (i + 1) + ". " + s.name + " · " + role[1] + " " + s.start + "~" + s.end + " (" + hm(z - a) + ")"));
        var next = d.stops[i + 1];
        if (next) {
          var g = mins(next.start) - z;
          var leg = (d.legs || []).filter(function (x) { return x.from === i; })[0];
          if (g > 0) {
            totals.gap += g;
            track.append(tooltip(h("span", { class: "trp-seg trp-seg-gap", style: "left:" + pct(z) + ";width:calc(" + (g / span * 100).toFixed(2) + "% - 2px)" }),
              "계획상 여유 " + hm(g) + " (" + s.name + " → " + next.name + ", 이동 시간 확인 안 됨)"));
          }
          if ((g <= 0 && next.path !== s.path) || (leg && leg.flag)) {
            tight += 1;
            track.append(tooltip(h("span", { class: "trp-seg-flag", style: "left:" + pct(z) }, [h("span", { text: "!" })]),
              (leg && leg.flag ? leg.flag : "이동할 틈이 없음") + ": " + s.name + " → " + next.name));
          }
        }
      });
      return h("div", { class: "trp-tlx-row" }, [h("span", { class: "trp-tlx-day", text: (di + 1) + "일차" }), track]);
    });
    var ticks = h("div", { class: "trp-tlx-ticks", "aria-hidden": "true" });
    for (var t = lo; t <= hi; t += 60) {
      if ((t - lo) % (span > 600 ? 120 : 60)) continue;
      ticks.append(h("span", { style: "left:" + pct(t), text: (t / 60) + "시" }));
    }
    var legend = h("ul", { class: "trp-legend" }, ROLES.filter(function (r) { return totals[r[0]]; }).map(function (r) {
      return h("li", {}, [h("i", { style: "background:" + r[2] }), h("span", { text: r[1] + " " + hm(totals[r[0]]) })]);
    }).concat(totals.gap ? [h("li", {}, [h("i", { class: "gap" }), h("span", { text: "계획상 여유 " + hm(totals.gap) })])] : [],
      tight ? [h("li", {}, [h("i", { class: "flag" }), h("span", { text: "이동이 빠듯한 곳 " + tight + "곳" })])] : []));
    return h("figure", { class: "trp-chart trp-tlx" }, [h("figcaption", {}, [h("b", { text: "하루 시간표" }), h("span", { text: "막대에 손가락이나 마우스를 대면 자세히 보여요" })]),
      h("div", { class: "trp-tlx-body", "data-lenis-prevent": "" }, [h("div", { class: "trp-tlx-grid" }, [ticks].concat(rows))]), legend]);
  }
  function metro(day) {   // the day as a line of stations: numbered stops, each link with its distance and how to go
    var line = h("ol", { class: "trp-metro", "aria-label": day.label + " 경로" });
    var hubs = day.hubs || [];
    var hubSt = function (hb) {
      return h("li", { class: "trp-st trp-st-hub" }, [h("span", { class: "trp-st-dot", text: hb.dir === "from" ? "출" : "도" }),
        h("span", { class: "trp-st-n", text: hb.name }), h("span", { class: "trp-st-t tn", text: hb.at })]);
    };
    var hubLink = function () { return h("li", { class: "trp-link trp-link-hub", "aria-label": "이동 거리·시간 모름" }, [h("span", { class: "tn", text: "?" })]); };
    hubs.filter(function (x) { return x.dir === "from"; }).forEach(function (hb) { line.append(hubSt(hb), hubLink()); });
    day.stops.forEach(function (s, i) {
      var role = ROLES.filter(function (r) { return r[0] === s.role; })[0] || ROLES[0];
      line.append(h("li", { class: "trp-st" + (s.day === "closed" ? " closed" : "") }, [
        h("span", { class: "trp-st-dot", style: "--c:" + role[2], text: String(i + 1) }),
        h("span", { class: "trp-st-n", text: s.name }), h("span", { class: "trp-st-t tn", text: s.start })]));
      var l = (day.legs || []).filter(function (x) { return x.from === i; })[0];
      if (l) {
        line.append(h("li", { class: "trp-link" + (l.flag ? " bad" : ""), "aria-label": dist(l.m) + (l.flag ? ", " + l.flag : ", 계획상 여유 " + l.gap + "분") }, [
          pic(l.mode === "car" ? "fact-parking" : l.mode === "walk" ? "sit-walk" : "transit-bus"),
          h("span", { class: "tn", text: num(l.m) ? km(l.m) : "?" })]));
      }
    });
    hubs.filter(function (x) { return x.dir === "to"; }).forEach(function (hb) { line.append(hubLink(), hubSt(hb)); });
    return h("figure", { class: "trp-chart trp-metro-f" }, [h("figcaption", {}, [h("b", { text: "경로 한눈에" }), h("span", { text: "숫자는 직선거리예요" })]),
      h("div", { class: "trp-metro-w", "data-lenis-prevent": "" }, [line])]);
  }
  function legBars(day) {   // each leg's straight-line distance, one blue
    var legs = (day.legs || []).filter(function (l) { return num(l.m); });
    if (!legs.length) return null;
    var max = Math.max.apply(null, legs.map(function (l) { return l.m; })) || 1;
    var rows = legs.map(function (l) {
      var a = day.stops[l.from], b = day.stops[l.to];
      var bar = h("span", { class: "trp-bar" + (l.flag ? " bad" : ""), style: "width:" + Math.max(3, l.m / max * 100).toFixed(1) + "%" });
      return h("li", {}, [h("span", { class: "trp-bar-l", text: (l.from + 1) + "→" + (l.to + 1) }),
        h("span", { class: "trp-bar-t" }, [tooltip(bar, a.name + " → " + b.name + " 직선 " + km(l.m) + (l.flag ? " · " + l.flag : " · 계획상 여유 " + l.gap + "분")),
          h("span", { class: "trp-bar-v tn", text: km(l.m) + (l.flag ? " ⚠" : "") })])]);
    });
    var missing = (day.legs || []).length - legs.length;
    return h("figure", { class: "trp-chart trp-bars" }, [h("figcaption", {}, [h("b", { text: "구간별 직선거리" }), h("span", { text: "실제 이동 시간은 지도 앱에서" })]),
      h("ul", {}, rows), missing ? h("p", { class: "trp-hint", text: "좌표가 없어 거리를 모르는 구간 " + missing + "개는 막대에 없어요." }) : null]);
  }
  // a chart in a box that opens: open from 900px, closed on phones (review 2026-10-17: on a phone the schedule and
  // the map come first, the rest one tap away)
  var wide = win.matchMedia ? win.matchMedia("(min-width: 900px)").matches : true;
  function fold(label, node) {
    if (!node) return null;
    return h("details", { class: "trp-fold", open: wide }, [h("summary", { text: label }), node]);
  }

  // ------------------------------------------------------------ keeping and passing the plan on
  // the plan as text: copy, share, a saved file, the printed page — a draft still unmet says so on its first line, so
  // a copy passed on is never read as a finished itinerary
  function planText(plan, c) {
    var L = [(plan.status === "unmet" ? "[수정이 필요한 초안] " : "") + plan.title, "", plan.summary, "", "조건: " + describe(c),
      "상태: " + (STATUS[plan.status] || STATUS.ready)[1]];
    var done = completeLine(plan);
    if (done) L.push("일정 완성도: " + done[1]);
    var sum = lineSum(plan.days);
    if (sum.legs) L.push("구간 직선거리: " + (sum.all ? "합 " + km(sum.metres) + "(실제 길 거리·시간 아님)" : "전체 이동거리 계산 안 됨(" + sum.legs + "개 구간 중 " + sum.known + "개만 거리 있음)"));
    L.push("만든 때: " + new Date(plan.made || Date.now()).toLocaleString("ko-KR"), "");
    plan.days.forEach(function (d) {
      L.push("■ " + d.label);
      (d.hubs || []).filter(function (x) { return x.dir === "from"; }).forEach(function (hb) { L.push("  " + hb.at + " " + hb.name + " 출발 (길찾기 " + hb.url + ")"); });
      d.stops.forEach(function (s, i) {
        L.push("  " + s.start + "~" + s.end + " " + (i + 1) + ". " + s.name + " [" + (LABEL.role[s.role] || "") + " · " + LABEL.day[s.day || "unknown"]
          + (codeBuilt(plan) ? "" : s.added ? " · 사이트가 넣음" : s.swapped ? " · 쉬는 곳 대신 사이트가 고름" : "") + "] " + SITE + encodeURI(s.path));
        (s.checks || []).forEach(function (x) { L.push("     확인: " + x); });
        var l = (d.legs || []).filter(function (x) { return x.from === i; })[0];
        if (l) L.push("     → " + (dist(l.m) || "거리 모름") + " · 계획상 여유 " + Math.max(0, l.gap) + "분" + (l.url ? " · 길찾기 " + l.url : ""));
      });
      (d.hubs || []).filter(function (x) { return x.dir === "to"; }).forEach(function (hb) { L.push("  " + hb.at + "까지 " + hb.name + " (길찾기 " + hb.url + ")"); });
      L.push("");
    });
    var f = plan.fees, head = feeHead(f);
    L.push("입장료: " + head[0] + " — " + head[1] + (verdictText(f) ? " · " + verdictText(f) : ""));
    if ((plan.flags || []).length) { L.push("", "맞지 않는 것:"); plan.flags.forEach(function (x) { L.push("- " + x); }); }
    var know = knowList(plan);
    if (know.length) { L.push("", "가기 전에 알아 둘 것:"); know.forEach(function (x) { L.push("- " + x.t); }); }
    if ((plan.notes || []).length) { L.push("", "메모(AI):"); plan.notes.forEach(function (x) { L.push("- " + x); }); }
    var by = (SITE_NAME ? SITE_NAME + "(" : "이 사이트(") + SITE + "/plan/)";
    L.push("", (codeBuilt(plan) ? codeLine(plan) + ". " + by + " 자료로 검사했어요."
      : "AI(Claude)가 고른 일정을 " + by + " 자료로 검사했어요.") + " 장소 정보의 출처는 각 장소 페이지에 있어요. 실제 운영·이동 시간·예약은 장소와 지도 앱에서 확인하세요.");
    return L.join("\n");
  }
  function exportBar(plan, c) {
    var msg = h("p", { class: "trp-x-msg", role: "status" });
    var say = function (t) { msg.textContent = t; };
    var text = function () { return planText(plan, c); };
    var b = function (label, how, fn) {
      var el = h("button", { type: "button", class: "btn btn-ol trp-x", text: label });
      el.addEventListener("click", function () { track("plan_export", { how: how }); fn(); });
      return el;
    };
    var copy = b("일정 복사", "copy", function () {
      var done = function () { say("일정을 복사했어요. 메시지나 메모에 붙여 넣으세요."); };
      if (navigator.clipboard && navigator.clipboard.writeText) navigator.clipboard.writeText(text()).then(done, function () { say("복사하지 못했어요. 파일로 저장해 주세요."); });
      else say("이 브라우저는 복사를 지원하지 않아요. 파일로 저장해 주세요.");
    });
    var share = navigator.share ? b("공유", "share", function () {
      navigator.share({ title: plan.title, text: text() }).catch(function () { /* closed */ });
    }) : null;
    var save = b("파일로 저장", "file", function () {
      var blob = new Blob([text()], { type: "text/plain;charset=utf-8" });
      var a = h("a", { href: URL.createObjectURL(blob), download: (SITE_NAME ? SITE_NAME.replace(/[\\/:*?"<>|\s]+/g, "-") + "-" : "") + "코스-" + c.date + ".txt" });
      doc.body.append(a); a.click(); a.remove();
      setTimeout(function () { URL.revokeObjectURL(a.href); }, 2000);
      say("텍스트 파일로 저장했어요.");
    });
    var print = b("인쇄·PDF", "print", function () { win.print(); });
    return h("div", { class: "trp-x-bar" }, [h("div", { class: "trp-x-row", role: "group", "aria-label": "일정 보관·전달" }, [copy, share, save, print]), msg,
      h("p", { class: "trp-hint", text: "일정은 이 탭에만 있어요. 동행에게 보내거나 여행 날 다시 보려면 복사·저장해 두세요." })]);
  }
  function diffPlans(a, b) {   // what an edit changed: stops, times, the fee state, the plan's status
    var out = [];
    b.days.forEach(function (d, i) {
      var was = (a.days[i] || { stops: [] }).stops, now = d.stops;
      var key = function (s) { return s.path; };
      var wasKeys = was.map(key), nowKeys = now.map(key);
      now.forEach(function (s) { if (wasKeys.indexOf(s.path) < 0) out.push((i + 1) + "일차: " + s.name + " 추가(" + s.start + "~" + s.end + ")"); });
      was.forEach(function (s) { if (nowKeys.indexOf(s.path) < 0) out.push((i + 1) + "일차: " + s.name + " 뺌"); });
      now.forEach(function (s) {
        var o = was.filter(function (x) { return x.path === s.path; })[0];
        if (o && (o.start !== s.start || o.end !== s.end)) out.push((i + 1) + "일차: " + s.name + " " + o.start + "~" + o.end + " → " + s.start + "~" + s.end);
      });
    });
    var fa = feeHead(a.fees)[0], fb = feeHead(b.fees)[0];
    if (fa !== fb) out.push("입장료: " + fa + " → " + fb);
    var sa = (STATUS[a.status] || STATUS.ready)[1], sb = (STATUS[b.status] || STATUS.ready)[1];
    if (sa !== sb) out.push("상태: " + sa + " → " + sb);
    return out.length ? out : ["장소와 시각은 그대로예요."];
  }
  // an edit: the plan on screen and the change asked for. The stops go with their role and reason: the server hands
  // them over as they are, so the stops the change keeps are copied, not read and written again (operator
  // 2026-10-17: an edit took too long). false when there is nothing to send.
  function sendEdit(req) {
    if (!req || !state || !state.plan) return false;
    var compact = { days: state.plan.days.map(function (d) { return { date: d.date, stops: d.stops.map(function (s) {
      return { page: s.path, start: s.start, end: s.end, role: s.role, why: s.why || "" }; }) }; }) };
    ask({ conditions: state.conditions, plan: compact, request: req }, state.conditions, true);
    return true;
  }
  function editBox() {
    var ta = h("textarea", { id: "trp-ask", rows: "2", maxlength: "300", placeholder: "예: 둘째 날 비가 온대요. 실내 위주로, 주차하기 편한 곳으로 바꿔 주세요." });
    var go = h("button", { type: "submit", class: "btn" }, [pic("plan-swap"), h("span", { text: "이렇게 바꾸기" })]);
    var f = h("form", { class: "trp-edit-f" }, [h("label", { for: "trp-ask", class: "vh", text: "바꾸고 싶은 점" }), ta, go]);
    var quick = h("div", { class: "trp-qes", role: "group", "aria-label": "빠르게 바꾸기" });
    var tq = doc.getElementById("trp-quick");
    if (tq) Array.prototype.forEach.call(tq.content.children, function (b) {
      var c = b.cloneNode(true);
      c.addEventListener("click", function () { ta.value = c.getAttribute("data-ask"); ta.focus(); });
      quick.append(c);
    });
    f.addEventListener("submit", function (e) {
      e.preventDefault();
      if (!sendEdit(ta.value.trim())) ta.focus();
    });
    return h("section", { class: "trp-edit", "aria-labelledby": "h-edit" }, [
      h("div", { class: "trp-edit-h" }, [mascot("rain"), h("div", {}, [h("h3", { id: "h-edit", text: "바꾸고 싶은 점이 있나요?" }),
        h("p", { text: "말로 적으면 조건은 그대로 두고 그 부분만 다시 짜요. 날짜·인원·예산을 바꾸려면 위에서 조건을 다시 골라 주세요." })])]), quick, f]);
  }

  // ------------------------------------------------------------ drawing it
  function draw(focus) {
    var plan = state.plan, c = state.conditions;
    result.textContent = "";
    result.hidden = false;
    if (curDay >= plan.days.length || curDay < 0) curDay = 0;   // a plan with fewer days than the tab shown before
    var head = h("header", { class: "trp-r-head" }, [h("span", { class: "trp-r-art" }, [mascot("done")]), h("div", { class: "trp-r-t" }, [
      h("p", { class: "trp-eyebrow" }, [h("span", { text: plan.status === "unmet" ? "AI가 고른 초안 · 사이트 자료와 코드로 검사함"
        : codeBuilt(plan) ? "사이트 자료로 짜고 코드로 검사한 코스" : "AI가 짜고 사이트 자료와 코드로 검사한 코스" })]),
      h("h2", { id: "h-result", tabindex: "-1", text: plan.title }),
      codeBuilt(plan) ? h("p", { class: "trp-r-code" }, [h("span", { class: "trp-site", text: "사이트" }), " " + codeLine(plan)]) : null,
      plan.summary ? h("p", { class: "trp-r-sum" }, [h("span", { class: "trp-ai", text: "AI" }), " " + plan.summary]) : null,
      h("p", { class: "trp-r-cond", text: describe(c) })])]);
    var diff = state.diff ? h("section", { class: "trp-diff", "aria-labelledby": "h-diff" }, [h("h3", { id: "h-diff", text: "바꾼 뒤 달라진 것" }),
      h("ul", {}, state.diff.map(function (x) { return h("li", { text: x }); }))]) : null;
    var again = h("button", { type: "button", class: "btn btn-ol", text: "조건 다시 고르기" });
    again.addEventListener("click", function () { form.scrollIntoView({ behavior: "smooth" }); form.querySelector("input,select").focus({ preventScroll: true }); });
    var tabs = null;
    if (plan.days.length > 1) {
      tabs = h("div", { class: "trp-days", role: "tablist", "aria-label": "일차" });
      plan.days.forEach(function (d, i) {
        var b = h("button", { type: "button", role: "tab", id: "trp-tab-" + i, "aria-selected": String(i === curDay), "aria-controls": "trp-day-" + i,
          tabindex: i === curDay ? "0" : "-1", text: d.label });
        b.addEventListener("click", function () { curDay = i; draw(false); doc.getElementById("trp-tab-" + i).focus(); });
        b.addEventListener("keydown", function (e) {
          var k = e.key === "ArrowRight" ? 1 : e.key === "ArrowLeft" ? -1 : 0;
          if (!k) return;
          curDay = (i + k + plan.days.length) % plan.days.length;
          draw(false);
          doc.getElementById("trp-tab-" + curDay).focus();
        });
        tabs.append(b);
      });
    }
    var day = plan.days[curDay];
    var tl = h("ol", { class: "trp-tl" });
    (day.hubs || []).filter(function (x) { return x.dir === "from"; }).forEach(function (hb) { tl.append(hubRow(hb)); });
    day.stops.forEach(function (s, i) {
      tl.append(stopCard(s, i + 1));
      var l = (day.legs || []).filter(function (x) { return x.from === i; })[0];
      if (l) tl.append(legRow(l, c.move));
    });
    (day.hubs || []).filter(function (x) { return x.dir === "to"; }).forEach(function (hb) { tl.append(hubRow(hb)); });
    var panel = h("div", { class: "trp-grid", id: "trp-day-" + curDay, role: tabs ? "tabpanel" : null, "aria-labelledby": tabs ? "trp-tab-" + curDay : null }, [
      h("div", { class: "trp-main" }, [h("h3", { class: "trp-day-h", text: day.label }), fold("경로 한눈에 보기", metro(day)), legNote(day), tl]),
      h("aside", { class: "trp-side" }, [dayMap(day), fold("구간별 직선거리 보기", legBars(day)), feeCard(plan.fees), checkBox(plan)])]);
    var notes = (plan.notes || []).length ? h("ul", { class: "trp-notes" }, plan.notes.map(function (n) { return h("li", {}, [h("span", { class: "trp-ai", text: "AI" }), " " + n]); })) : null;
    var glance = h("section", { class: "trp-glance", "aria-labelledby": "h-glance" }, [h("h3", { id: "h-glance", text: "한눈에 보는 코스" }),
      overview(plan), fold("하루 시간표 보기", timeline(plan)), fold("필요한 조건 표 보기", needsTable(plan))]);
    var printed = h("pre", { class: "trp-print", "aria-hidden": "true", text: planText(plan, c) });
    result.append(h("div", { class: "wrap" }, [head, statusPanel(plan), diff, h("div", { class: "trp-r-acts" }, [exportBar(plan, c), again]), glance, tabs, panel, notes, editBox(),
      h("p", { class: "trp-foot", text: (codeBuilt(plan) ? "사이트 자료로 고른" : "AI가 고른") + " 순서와 시각을 이 사이트 자료로 휴무·운영시간·입장마감·입장료·조건까지 검사했지만, 그날의 실제 운영·이동 시간·예약은 각 장소와 지도 앱에서 확인하세요. 장소 사진: 한국관광공사." }), printed]));
    if (focus) {
      result.scrollIntoView({ behavior: "smooth", block: "start" });
      result.querySelector("#h-result").focus({ preventScroll: true });
    }
  }
  function show(focus) {   // a plan that cannot be drawn is let go; the conditions stay in the form
    try {
      draw(focus);
    } catch (e) {
      var c = state && state.conditions;
      state = c ? { conditions: c, plan: null } : null;
      save();
      failed("일정을 그리지 못했어요. 같은 조건으로 다시 만들어 주세요.", { conditions: c }, c, false);
    }
  }

  // conditions handed over in the address start from the form's defaults — never from the conditions or the plan this
  // tab kept, which is not shown under them —, are kept for this tab without a plan and leave the address, so a
  // reload comes back to them (and to the plan made from them); never sent by themselves. The reader lands on the
  // form (review 2026-10-18, fourth round: the hand-over opened on the page's top, the filled form out of sight): a
  // line above it says where the values came from — a status region (plan.html.j2), empty until its words come, so
  // it is read out; its room is there from the first paint (html.trp-handing), so nothing moves — and the form comes
  // into view under it. A plain visit has neither. Otherwise a plan made
  // earlier in this tab comes back with its conditions in the form.
  var handed = false;
  try { handed = fromAddress(); } catch (e) { /* the form stays as it is */ }
  if (handed) {
    root.setAttribute("data-prefilled", "");
    state = { conditions: conditions(), plan: null };
    save();
    try { win.history.replaceState(win.history.state, "", win.location.pathname + win.location.hash); } catch (e) { /* the address stays */ }
    var said = root.querySelector("[data-plan-handed]"), saidBox = said && said.closest(".trp-handed-w");
    doc.documentElement.classList.add("trp-handing");
    if (said) setTimeout(function () {
      said.textContent = saidBox.querySelector(".trp-handed-ghost").textContent;
      saidBox.scrollIntoView({ block: "start" });
    }, 60);
  } else {
    doc.documentElement.classList.remove("trp-handing");   // keys the form has no choice for: no line, no room
    var kept = load();
    if (kept && kept.conditions && kept.conditions.date >= iso(today)) {
      try { setForm(kept.conditions); } catch (e) { /* the defaults stay */ }
      if (fits(kept.plan)) {
        state = kept;
        getPlaces().then(function () { show(false); });
      } else {
        state = { conditions: kept.conditions, plan: null };
      }
    }
  }
})();
