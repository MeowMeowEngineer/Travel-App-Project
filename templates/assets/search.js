/* /search/: a static index (search/index.json, built with the site by pipeline/present.search_index)
   fetched on the first focus of the box, or at once when the page opens with ?q=. No server.
   Index rows: n name, a other names (course: its stops), o the names in the other versions (the English name on the
   Korean index, the Korean name on the others; QA 2026-10-15 U10), v a course's stops in the other versions, m 대표
   메뉴·취급 메뉴, g official designations ('○○맛집(2026, ○○시 지정) · 모범음식점(○○시 지정)'), d 동 (or road), r 권역,
   t type, k kind, p path, s the status line as text.
   Ranking: name (exact, prefix, inside) > other names (a, o, v) > menu > designation > 동·권역·type. Spaces and
   ·-()[]|, are ignored when matching. A row says why it matched when it was not the name ("메뉴: 짜장면", "다른 이름: …",
   "경유: …", "지정: 모범음식점(○○시 지정)").
   Query words (evaluation 2026-10-18: '비 오는 날 아이랑' found nothing although the site has a rainy-day guide and a
   guide for travelling with children; review round 3, 2026-10-18: the rows found are never fewer than this matching
   alone finds). The rows found are the rows the query finds whole (as above), then the rows that have every part of
   it, ranked by how many of the parts' words they have. A part is a word of the query, matched as above (inside the
   row's text, without spaces: 'cafe' finds 'Cafes', 'gyeongam dong' 'Gyeongam-dong'; '빵', '섬', '마을' stay
   conditions), or a concept word of form[data-concepts] (present.SEARCH_CONCEPTS) with what follows it — the row has
   it as typed or has any of the concept's words ('아이랑' also 아이와·어린이·가족, '주차할 곳' also 주차): a concept
   only adds rows. The city's name (form[data-region]) is no condition next to another part: every row is in the city.
   A concept word (or the city's name) is read where it stands as a word or at a word start and is followed by nothing
   more than particles, verb endings ('주차할', '주차 가능한'), the nouns and conversational endings a question ends
   with ('비 오는 날', '아이랑 놀만한곳 추천해줘'; these may be words of their own) and another concept word
   ('비오는날아이랑'); '아이스크림', '버스킹', '가족사진관' are no 아이·버스·가족 and find as typed. The words a concept
   was also searched as, those the rows shown have, follow the count line, or the 'nothing' line above the related
   guides ("함께 찾은 말: 아이랑 → 아이와·가족").
   Nothing found (QA 2026-10-15 F08): one line, then — a diet word (halal, vegan, 채식, アレルギー …): the site has no
   such information, ask the restaurant (no place is named); else up to three names of the index one or two letters
   away (a typed name with two letters swapped → the name; Hangul compared letter by letter), each a link that
   searches it — and [data-none-help]: the list pages, the AI chat asked this query, and the whole directory only on
   request.
   Before that help (not after the diet note), '관련 가이드': up to five guides that have a part of the query — only
   those that have two or more parts of a query of two or more while any does —, those with the most parts first,
   then the most concepts, then those it is the topic of — '비 오는 날 아이랑' → the rainy-day guide, the guide for
   travelling with children (each found by one concept; no row has both). Only here
   a word is no part when it is a filler word, a conversational ending, a particle or a verb ending of its own, the
   city's name, digits, a Latin (or Cyrillic) word of one or two letters or a stop word of the versions' languages
   ('things to do in the rain' asks for 'rain', 'que faire quand il pleut' for 'pleut'); a word the index does not
   have as typed is tried without its conversational ending and final particle ('○○섬가볼만한곳' → ○○섬);
   a Latin word is found at a word start ('rain' → 'Rainy day', not 'Training'). A query that plans a trip (a date,
   N박, 당일, 하루, 코스, 일정, 동선, 계획, 주말) links to the AI course planner (form[data-planner], Korean only) under
   the count line, or under the related guides.

   MARKUP
     form[data-search]          action="/search/"; data-index overrides the index URL; its input[name=q]
     [data-results]             results go here (aria-live="polite" in the markup)
     [data-directory]           the no-JS answer (가나다 directory): hidden while results are shown or nothing was
                                found (shown again by [data-show-all]; it stays when the index did not load)
     [data-none-help] [hidden]  shown when nothing matches: list links, button[data-chat-open][data-chat-q] (site.js
                                asks the chat that question), button[data-show-all] (shows the directory, focus #h-dir)
   Result markup (style hooks): p.f-result (count line), p.res-syn (the words also searched), p.res-plan (the
   planner's link), section.res-g > h2 (+ .tn count) > ol > li > a > span.res-nm (with <mark>), span.res-meta,
   span.res-why, span.res-st; p.res-none when nothing matches, p.res-sug (a[data-sug] links), p.res-diet,
   section.res-g.res-rel (the related guides, rows as above).
   Without JS the form reloads this page and the directory answers.
   The other language versions (<home>search/, owner 2026-10-14): form[data-words] carries that version's words —
   {kinds, none ('{q}'), menu, other, via, des, of ('{n}', '{m}'), sug, diet, related, syn} — and the index its rows;
   Korean is the default. form[data-concepts], [data-region], [data-planner]: present.search_form_data. */
(function () {
  "use strict";
  var doc = document, form = doc.querySelector("[data-search]"), out = doc.querySelector("[data-results]");
  if (!form || !out) return;
  var input = form.querySelector('input[name="q"]') || form.querySelector("input");
  var dir = doc.querySelector("[data-directory]");
  var help = doc.querySelector("[data-none-help]");
  var emptyArt = doc.querySelector("[data-empty-art]");   // the small picture shown with no result
  var W = null;
  try { W = JSON.parse(form.getAttribute("data-words") || "null"); } catch (e) { W = null; }
  var LANG = doc.documentElement.lang || "ko";
  var KIND = (W && W.kinds) || { attraction: "관광지", stay: "숙소", food: "음식점", cafe: "카페·디저트", shopping: "쇼핑",
    course: "코스", guide: "가이드", event: "행사" };
  // the result groups in this order (카페·디저트 after 음식점, operator 2026-10-19); PLACES: the kinds of place pages
  var ORDER = ["attraction", "food", "cafe", "stay", "shopping", "course", "guide", "event"];
  var PLACES = ["attraction", "stay", "food", "cafe", "shopping"];
  var STRIP = /[\s·\-()（）\[\]|,]/g, LIMIT = 80, DOT = /\s*·\s*/;
  // query words (present.SEARCH_CONCEPTS): SAY [a word said (normalised), its concept]; SHOWN a normalised word as
  // the table writes it; the city's names; the planner's path (the Korean page only)
  var CONCEPTS = [], SAY = [], SHOWN = {};
  try { CONCEPTS = JSON.parse(form.getAttribute("data-concepts") || "[]"); } catch (e) { CONCEPTS = []; }
  var CITY = String(form.getAttribute("data-region") || "").split(/\s+/).map(norm).filter(Boolean);
  var PLANNER = form.getAttribute("data-planner") || "", RELATED = 5;
  // particles ('밤에', '아이들과', '○○도에서'); TAIL: a final one, dropped by related() from a word the index does
  // not have as typed (never 이·가·도·로, the last syllables of names: ○○도, ○○로)
  var JOSAS = ["에서", "에는", "에도", "으로", "이랑", "하고", "까지", "부터", "에", "엔", "로", "랑", "과", "와", "은", "는",
    "이", "가", "을", "를", "의", "도", "만"];
  var TAIL = /(?:에서|에는|에도|으로|이랑|하고|까지|부터|에|랑|과|와|은|는|을|를|의)$/;
  // verb endings after a concept word ('주차할 곳', '주차 가능한', '야경 보러')
  var ENDINGS = ["할", "하는", "하기", "하러", "하면", "되는", "될", "가능", "가능한", "있는", "볼", "보러", "보기"];
  // the nouns and conversational endings a question ends with ('비 오는 날', '갈만한곳 추천해줘'). END: the endings
  // related() drops from a word the index does not have as typed ('○○군도가볼만한곳' → ○○군도)
  var FILL = ["날", "때", "곳", "데", "것", "거", "좀", "수", "뭐", "갈", "할", "놀", "추천", "추천해", "추천해줘", "해줘",
    "알려줘", "알려", "주세요", "어디", "어디서", "어디가", "어디로", "어디야", "좋은", "갈곳", "갈데", "가볼", "가볼곳",
    "가볼만한", "볼만한", "갈만한", "놀곳", "놀만한", "할만한", "만한", "있는", "있을까", "여행", "하기", "하면"];
  var END = new RegExp("(?:" + FILL.filter(function (w) { return w.length > 1 || w === "곳" || w === "데"; })
    .sort(function (x, y) { return y.length - x.length; }).join("|") + ")+$");
  // what may follow a concept word in the query (concept detection): the particles, verb endings, nouns and endings
  // above, not 거·것·수·데 ('버스데이' is no 버스 + 데 + 이), the longest first
  var AFTER = JOSAS.concat(ENDINGS, FILL.filter(function (w) { return !/^[거것수데]$/.test(w); }))
    .sort(function (x, y) { return y.length - x.length; });
  // a word that is no part of the related guides' search (related() only; never of the rows found): those words on
  // their own, digits only, a Latin (or Cyrillic) word of one or two letters, a stop word of the versions' languages
  // (en, de, fr, es, ru: 'things to do in the rain' asks for 'rain', 'que faire quand il pleut' for 'pleut') — 'day'
  // among them, as 날 is ('rainy day with kids' asks for rain and kids; UI review 2026-10-19: 'day' was a part)
  var NOISE = new RegExp("^(?:" + JOSAS.concat(ENDINGS, FILL).join("|") + ")$");
  var LETTER = "a-z0-9\\u00c0-\\u024f\\u0400-\\u04ff";   // a Latin or Cyrillic letter, a digit
  var ALPHA = new RegExp("^(?=.*[a-z\\u00c0-\\u024f\\u0400-\\u04ff])[" + LETTER + "'’]+$");   // a word of them
  var STOP = new RegExp("^(?:" + [
    "the|and|for|with|from|into|about|near|under|during|what|where|when|whenever|while|which|how|are|can|you|any" +
      "|some|best|good|top|thing|things|place|places|visit|see|get|there|here|this|that|day|days",
    "der|die|das|den|dem|des|ein|eine|einen|einem|einer|und|mit|für|von|vom|bei|beim|nach|bis|unter|über|zum|zur" +
      "|auf|aus|was|wie|gibt|kann|man|tun|machen|sehen|wenn|wann|während|dort|hier|auch|aber|tag|tage|tagen|tages",
    "les|des|une|pour|avec|dans|sur|sous|chez|vers|aux|par|que|quoi|quel|quelle|quels|quelles|comment|est|qui|faire" +
      "|voir|choses|quand|lorsque|pendant|puis|alors|aussi|mais|ici|jour|jours|journée|journées",
    "los|las|una|unos|unas|para|con|por|del|bajo|desde|hasta|qué|que|dónde|donde|cómo|como|hay|hacer|ver|cosas" +
      "|cuando|cuándo|mientras|durante|también|pero|aquí|allí|día|días|dia|dias",
    "что|где|как|для|при|это|или|чем|куда|можно|посмотреть|делать|когда|если|пока|там|тут|здесь|день|дня|дни|днём|днем" +
      "|дней"].join("|") + ")$");
  // a query that plans a trip: a date ('10월 18일', '2026-10-18', '10/18'), N박, 당일, 하루, 코스, 일정, 동선, 계획, 주말
  var PLAN = /\d\s*박|당일|하루|코스|일정|동선|계획|주말|\d{1,2}\s*월\s*\d{1,2}\s*일|\d{4}\s*[-.\/년]\s*\d{1,2}\s*[-.\/월]\s*\d{1,2}|(?:^|\s)\d{1,2}\s*[\/.]\s*\d{1,2}(?:\s|$)/;
  // words of food rules the site has no data on (tests/test_intl_site.py keeps the index and the chat's knowledge free
  // of them, so the note stays true); the Latin ones only at a word start ('navegan' is no 'vegan')
  var DIET = /\b(?:halal|kosher|koscher|casher|vegetari|végétari|vegan|végan|gluten|allerg|alerg|muslim|musulm)|할랄|코셔|채식|비건|글루텐|알레르기|알러지|무슬림|ハラール|ハラル|ベジタリアン|ヴィーガン|ビーガン|グルテン|アレルギー|ムスリム|菜食|清真|素食|纯素|純素|麸质|麩質|过敏|過敏|穆斯林|حلال|халял|веган|вегетари|глютен|аллерг|мусульм/i;
  var index = null, loading = null;

  function norm(s) { return String(s || "").toLowerCase().replace(STRIP, ""); }
  CONCEPTS.forEach(function (c, i) {
    c.f = (c.find || []).map(function (w) { var k = norm(w); SHOWN[k] = w; return k; });
    (c.say || []).forEach(function (w) { var k = norm(w); if (k) { SAY.push([k, i]); if (!SHOWN[k]) SHOWN[k] = w; } });
  });
  // the words parse() reads as a concept: [a word, its concept | -1 the city's name], the longest first
  var PIECES = SAY.concat(CITY.map(function (w) { return [w, -1]; }))
    .sort(function (x, y) { return y[0].length - x[0].length; });
  function load() {
    if (index) return Promise.resolve(index);
    if (!loading) {
      loading = fetch(form.getAttribute("data-index") || "/search/index.json")
        .then(function (r) { return r.json(); })
        .then(function (rows) {
          index = rows.map(function (row) {
            row._n = norm(row.n); row._a = norm(row.a); row._o = norm(row.o); row._v = norm(row.v);
            row._m = norm(row.m); row._g = norm(row.g);
            row._d = norm([row.d, row.r, row.t].join(" "));
            row._w = [row._n, row._a, row._o, row._v, row._m, row._g, row._d].join("\n");   // every word it is found by
            row._l = [row.n, row.a, row.o, row.v, row.m, row.g, row.d, row.r, row.t].join("\n").toLowerCase();   // with its spaces
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
      if (row.k === "course") return [3, (W ? W.via : "경유: ") + piece(row.a, W ? DOT : /\s+/, q)];
      return [3, row.k === "guide" || row.k === "event" ? "" : (W ? W.other : "다른 이름: ") + (W ? row.a : piece(row.a, /\s+/, q))];
    }
    if (row.o && row._o.indexOf(q) > -1) return [3, (W ? W.other : "다른 이름: ") + piece(row.o, DOT, q)];
    if (row.v && row._v.indexOf(q) > -1) return [3, (W ? W.via : "경유: ") + piece(row.v, DOT, q)];
    if (row.m && row._m.indexOf(q) > -1) return [4, (W ? W.menu : "메뉴: ") + piece(row.m, /\s*[,\/·、，]\s*/, q)];
    if (row.g && row._g.indexOf(q) > -1) return [5, (W ? W.des : "지정: ") + piece(row.g, /\s+·\s+/, q)];
    if (row._d.indexOf(q) > -1) return [6, ""];
    return null;
  }

  // ---- 'did you mean': names of the index one letter away (two from 8 letters), Hangul split into its letters
  function keyOf(s) {
    var o = "";
    for (var i = 0; i < s.length; i++) {
      var c = s.charCodeAt(i) - 0xac00;
      if (c >= 0 && c < 11172) {
        o += String.fromCharCode(0x1100 + Math.floor(c / 588), 0x1161 + Math.floor((c % 588) / 28));
        if (c % 28) o += String.fromCharCode(0x11a7 + c % 28);
      } else o += s[i];
    }
    return o;
  }
  // optimal string alignment distance (a swap of two neighbours counts 1), max + 1 as soon as it is above max
  function osa(a, b, max) {
    if (Math.abs(a.length - b.length) > max) return max + 1;
    var p2 = null, p = [], c, i, j;
    for (j = 0; j <= b.length; j++) p.push(j);
    for (i = 1; i <= a.length; i++) {
      c = [i];
      var lo = i;
      for (j = 1; j <= b.length; j++) {
        var v = Math.min(p[j] + 1, c[j - 1] + 1, p[j - 1] + (a[i - 1] === b[j - 1] ? 0 : 1));
        if (p2 && j > 1 && a[i - 1] === b[j - 2] && a[i - 2] === b[j - 1]) v = Math.min(v, p2[j - 2] + 1);
        c.push(v);
        if (v < lo) lo = v;
      }
      if (lo > max) return max + 1;
      p2 = p; p = c;
    }
    return p[b.length];
  }
  var SPLIT = /[\s·\-()（）\[\]|,\/、，:：—–]+/;
  // a row's words: each word of its names and dishes, each pair of neighbours, the first 2–4 syllables of a Korean
  // compound ('○○도해수욕장' → ○○, ○○도, ○○도해), and a name of several words whole ('○○ Lake Park');
  // [shown, key, the compound of a part] once per row
  function terms(row) {
    if (row._t) return row._t;
    var t = [];
    [row.n].concat(String(row.o || "").split(DOT)).forEach(function (w) {
      w = String(w || "").trim();
      if (SPLIT.test(w)) t.push([w, ""]);
    });
    ["n", "a", "o", "m"].forEach(function (f) {
      var ws = String(row[f] || "").split(SPLIT).filter(Boolean);
      ws.forEach(function (w, i) {
        t.push([w, ""]);
        if (i + 1 < ws.length) t.push([w + " " + ws[i + 1], ""]);
        if (/^[가-힣]{3,}$/.test(w)) for (var k = 2; k < Math.min(w.length, 5); k++) t.push([w.slice(0, k), w]);
      });
    });
    row._t = t.map(function (w) { return [w[0], keyOf(norm(w[0])), w[1]]; });
    return row._t;
  }
  function suggest(rows, raw) {
    var q = keyOf(norm(raw));
    if (q.length < 4) return [];
    var max = q.length >= 8 ? 2 : 1, best = {}, all = [];
    rows.forEach(function (row) {
      var seen = {};
      terms(row).forEach(function (tk) {
        var k = tk[1], b = best[k];
        if (k.length < 3) return;
        if (b && !tk[2]) b.whole = true;   // the part is a word of its own somewhere
        if (seen[k]) return;
        seen[k] = 1;
        var d = b ? b.d : osa(q, k, max);
        if (d > max || d === 0) return;
        if (!b) { b = best[k] = { t: tk[0], d: d, n: 0, whole: !tk[2], of: tk[2] }; all.push(b); }
        b.n++;
      });
    });
    var dmin = Math.min.apply(null, all.map(function (x) { return x.d; })), out = [];
    all.filter(function (x) { return x.d === dmin; })
      .sort(function (x, y) { return y.n - x.n || x.t.length - y.t.length; })
      .forEach(function (x) {   // a part that is no word of its own ('○○대' of ○○대교) shows its whole word
        var t = x.whole ? x.t : x.of;
        if (out.length < 3 && out.indexOf(t) < 0) out.push(t);
      });
    return out;
  }

  // ---- query words: the query in parts, in its order — each concept said ({c, at, say: the words said, typed: as
  // typed with what follows them, f: those and the concept's words}), the city's name ({city, f}) and each other word
  // as typed ({c: -1, at, f: [the word]}). A concept word (or the city's name) is read at a word start, or right after
  // another one, when what follows it to the end of a word is nothing, AFTER pieces (those other than a particle may
  // also start the words after it: '비 오는 날', '주차할 곳', '아이랑 놀만한곳 추천해줘'; not '카페 도로') or another
  // concept word ('비오는날아이랑'); otherwise the word is a plain word ('아이스크림', '버스킹', '가족사진관', '밤바다').
  function parse(raw) {
    var words = String(raw || "").split(SPLIT).map(norm).filter(Boolean), flat = words.join(""), L = flat.length,
      cut = {}, memo = {}, parts = [], byC = {}, at = 0, i, j, r;
    words.forEach(function (w) { cut[at] = 1; at += w.length; });
    cut[L] = 1;
    function from(i, w) { return flat.slice(i, i + w.length) === w; }
    // a concept word at i and what follows it: [the end, [[concept, from, to, the word said] …]] or null
    function said(i) {
      if (!(("s" + i) in memo)) {
        memo["s" + i] = null;
        for (var n = 0, x; n < PIECES.length && !memo["s" + i]; n++) {
          x = from(i, PIECES[n][0]) && after(i + PIECES[n][0].length);
          if (x) memo["s" + i] = [x[0], [[PIECES[n][1], i, x[1].length ? x[1][0][1] : x[0], PIECES[n][0]]].concat(x[1])];
        }
      }
      return memo["s" + i];
    }
    // after a concept word, from e: AFTER pieces, then another concept word or a word end
    function after(e) {
      if (!(("a" + e) in memo)) {
        var x = null;
        for (var n = 0; n < AFTER.length && !x; n++) {
          if (from(e, AFTER[n]) && !(cut[e] && JOSAS.indexOf(AFTER[n]) > -1)) x = after(e + AFTER[n].length);
        }
        if (!x && e < L) x = said(e);
        if (!x && cut[e]) x = [e, []];
        memo["a" + e] = x;
      }
      return memo["a" + e];
    }
    function push(list, w) { if (w && list.indexOf(w) < 0) list.push(w); }
    for (i = 0; i < L; i = j) {
      r = said(i);
      if (r) {
        r[1].forEach(function (x) {
          var typed = flat.slice(x[1], x[2]), p;
          if (x[0] < 0) { parts.push({ city: true, c: -1, at: x[1], f: [typed] }); return; }
          p = byC[x[0]];
          if (!p) { p = byC[x[0]] = { c: x[0], at: x[1], say: [], typed: [], f: [] }; parts.push(p); }
          push(p.say, x[3]);
          push(p.typed, typed);
          push(p.f, typed);
          if (x[3].length > 1) push(p.f, x[3]);   // '밤' of '밤에' only as typed: alone it is inside ○○밤, 밤빵
          CONCEPTS[x[0]].f.forEach(function (w) { push(p.f, w); });
        });
        j = r[0];
      } else {
        for (j = i + 1; !cut[j]; j++) { /* to the end of the word */ }
        parts.push({ c: -1, at: i, f: [flat.slice(i, j)] });
      }
    }
    return parts;
  }
  // the words of a part a row has (inside the row's text, as score() matches)
  function has(row, p) {
    return p.f.filter(function (w) { return row._w.indexOf(w) > -1; });
  }
  // hits [tier, row, why, the word to mark, 0 | 1 (found by its parts), how many words]: the rows the query finds
  // whole (score), then the rows that have every part — the city's name no condition next to another part —, the
  // most words first
  function find(rows, raw) {
    var q = norm(raw), parts = parse(raw), hits = [];
    var need = parts.filter(function (p) { return !p.city; });
    rows.forEach(function (row) {
      var s = score(row, q), ws = [], best = null, k, h;
      if (s) { hits.push([s[0], row, s[1], q, 0, 0]); return; }
      if (!need.length) return;
      for (k = 0; k < need.length; k++) {
        h = has(row, need[k]);
        if (!h.length) return;
        ws = ws.concat(h);
      }
      ws.forEach(function (w) { var s = score(row, w); if (s && (!best || s[0] < best[0])) best = [s[0], s[1], w]; });
      if (best) hits.push([best[0], row, best[1], best[2], 1, ws.length]);
    });
    hits.sort(function (x, y) {
      return x[4] - y[4] || y[5] - x[5] || x[0] - y[0] || x[1].n.localeCompare(y[1].n, LANG);
    });
    return { hits: hits, parts: parts };
  }
  // a plain word that is no part of the related guides' search
  function idle(w) {
    return !w || NOISE.test(w) || CITY.indexOf(w) > -1 || /^\d+$/.test(w) || ALPHA.test(w) && (w.length < 3 || STOP.test(w));
  }
  // the words of a part a guide has for related(): a Latin (or Cyrillic) word at a word start of its text ('rain' →
  // 'Rainy day', not 'Training'), any other inside it
  var RX = {};
  function near(row, p) {
    return p.f.filter(function (w) {
      if (!ALPHA.test(w)) return row._w.indexOf(w) > -1;
      if (!RX[w]) RX[w] = new RegExp("(?:^|[^" + LETTER + "])" + w);
      return RX[w].test(row._l);
    });
  }
  // nothing found whole: up to RELATED guides that have a part of the query — its concepts, and its other words that
  // are no noise (idle), each as typed or, when the index does not have it, without its conversational ending and
  // final particle; [row, the words it has]. A query of two or more parts lists only the guides that have two or more
  // of them while any does (review 2026-10-18, fourth round: 'rainy day with kids' listed 'A car-free day trip …' and
  // 'Raw fish restaurants … closing days' for one word each), else those that have one. The most parts first, concepts
  // and plain words alike, then the most concepts — among guides of one part, a plain word its title names counts as a
  // concept (UI review 2026-10-19: '빵집 주차' listed five guides with 주차 and none titled with 빵집) —, then the
  // guides a part is the topic of — the earliest in the title ('○○도 맛집 …' before a list of stops that ends with
  // ○○도), then in the label (a) —, then the most words, then the query's order
  function related(rows, parts) {
    var use = [], rel = [];
    parts.forEach(function (p) {
      var w = p.f[0], stem;
      if (p.city || p.c < 0 && idle(w)) return;
      if (p.c < 0 && !rows.some(function (r) { return r._w.indexOf(w) > -1; })) {
        stem = w.replace(END, "").replace(TAIL, "");
        if (stem.length > 1 && !idle(stem)) p = { c: -1, at: p.at, f: [stem] };
      }
      use.push(p);
    });
    rows.forEach(function (row) {
      if (row.k !== "guide") return;
      var x = { row: row, c: 0, n: 0, lab: 0, pos: Infinity, ws: [], first: Infinity, named: 0 };
      use.forEach(function (p) {
        var h = near(row, p);
        if (!h.length) return;
        if (p.c > -1) x.c++;
        else if (h.some(function (w) { return row._n.indexOf(w) > -1; })) x.named = 1;
        x.n++;
        x.ws = x.ws.concat(h);
        x.first = Math.min(x.first, p.at);
        if (h.some(function (w) { return row._a.indexOf(w) > -1; })) x.lab++;
        h.forEach(function (w) { var i = row._n.indexOf(w); if (i > -1) x.pos = Math.min(x.pos, i); });
      });
      if (x.n) rel.push(x);
    });
    if (use.length > 1 && rel.some(function (x) { return x.n > 1; })) rel = rel.filter(function (x) { return x.n > 1; });
    var cs = function (x) { return x.n === 1 ? Math.max(x.c, x.named) : x.c; };
    return rel.sort(function (x, y) {
      return y.n - x.n || cs(y) - cs(x) || x.pos - y.pos || y.lab - x.lab || y.ws.length - x.ws.length ||
        x.first - y.first || x.row.n.localeCompare(y.row.n, LANG);
    }).slice(0, RELATED).map(function (x) { return [x.row, x.ws]; });
  }
  // the words a concept was also searched as, those the rows shown have: '함께 찾은 말: 아이랑 → 아이와·가족'
  function synLine(parts, rows) {
    var bits = [];
    parts.forEach(function (p) {
      if (p.c < 0) return;
      var also = p.f.filter(function (w) {
        return p.say.indexOf(w) < 0 && p.typed.indexOf(w) < 0 && rows.some(function (r) { return r._w.indexOf(w) > -1; });
      });
      if (also.length) bits.push(p.say.map(shown).join("·") + " → " + also.map(shown).join("·"));
    });
    return bits.length ? '<p class="res-syn">' + esc(((W && W.syn) || "함께 찾은 말: ") + bits.join(", ")) + "</p>" : "";
  }
  function shown(w) { return SHOWN[w] || w; }
  // a query that plans a trip: the AI course planner (the Korean page only)
  function planLine(raw) {
    if (!PLANNER || !PLAN.test(raw)) return "";
    return '<p class="res-plan"><a href="' + esc(PLANNER) + '" data-track="plan_cta">AI 코스 만들기</a> ' +
      "날짜·이동 수단·동행을 고르면 이 사이트의 장소 정보로 일정을 짜 드려요.</p>";
  }
  // one result row; hl: the word to mark in its name and in why
  function item(row, why, hl) {
    var meta = [row.t, row.d, row.r].filter(Boolean);
    return '<li><a href="' + esc(row.p) + '"><span class="res-nm">' + mark(row.n, hl) + "</span>" +
      '<span class="res-meta">' + esc(meta.join(" · ")) + "</span>" +
      (why ? '<span class="res-why">' + mark(why, hl) + "</span>" : "") +
      (row.s ? '<span class="res-st">' + esc(row.s) + "</span>" : "") + "</a></li>";
  }

  // nothing found: the line, then the diet note, or the names it may have meant and the related guides (a diet word
  // names no place and no guide: '할랄 맛집' lists no 맛집 guide), then the planner, and the help below
  function none(rows, raw, parts) {
    var q = raw.trim(), html = '<p class="res-none">' + (W ? esc(W.none).replace("{q}", esc(q)) :
      "‘" + esc(q) + "’" + josaWa(q) + " 맞는 곳이 없습니다.") + "</p>", rel = [];
    if (DIET.test(raw)) html += diet();
    else {
      var sug = rows.length ? suggest(rows, raw) : [];
      if (sug.length) html += '<p class="res-sug">' + esc(W ? W.sug : "혹시 이것을 찾으셨나요? ") +
        sug.map(function (t) { return '<a href="?q=' + encodeURIComponent(t) + '" data-sug>' + esc(t) + "</a>"; }).join(" ") + "</p>";
      if (rows.length) rel = related(rows, parts);
    }
    if (rel.length) {
      html += synLine(parts, rel.map(function (x) { return x[0]; })) + '<section class="res-g res-rel"><h2>' +
        esc((W && W.related) || "관련 가이드") + ' <span class="tn">' + rel.length + "</span></h2><ol>" +
        rel.map(function (x) {   // the longest of its words in the title is marked
          var hl = x[1].filter(function (w) { return x[0]._n.indexOf(w) > -1; })
            .sort(function (a, b) { return b.length - a.length; })[0];
          return item(x[0], "", hl || "");
        }).join("") + "</ol></section>";
    }
    html += planLine(raw);
    out.innerHTML = html;
    if (dir) dir.hidden = rows.length > 0;   // an index that did not load: the directory stays the answer
    if (help) {
      help.hidden = false;
      var ask = help.querySelector("[data-chat-q]"), all = help.querySelector("[data-show-all]");
      if (ask) ask.setAttribute("data-chat-q", q);
      if (all) all.hidden = !dir || !dir.hidden;
    }
  }
  function diet() {
    return '<p class="res-diet">' + esc(W ? W.diet : "이 사이트에는 음식점의 할랄·채식·알레르기 정보가 없습니다. " +
      "방문 전에 음식점에 직접 확인하세요. 전화번호가 있으면 장소 페이지에 있습니다.") + "</p>";
  }
  function render(raw) {
    var q = norm(raw);
    if (help) help.hidden = true;
    if (!q) { out.innerHTML = ""; if (dir) dir.hidden = false; if (emptyArt) emptyArt.hidden = true; return; }
    load().then(function (rows) {
      if (norm(input.value) !== q) return; // a newer query is on its way
      var found = find(rows, raw), hits = found.hits;
      if (emptyArt) emptyArt.hidden = hits.length > 0;
      if (!hits.length) { none(rows, raw, found.parts); return; }
      if (dir) dir.hidden = true;
      var cut = hits.slice(0, LIMIT), groups = {};
      cut.forEach(function (h) { (groups[h[1].k] = groups[h[1].k] || []).push(h); });
      var counts = ORDER.filter(function (k) { return groups[k]; }).map(function (k) { return KIND[k] + " " + groups[k].length; });
      var places = hits.every(function (h) { return PLACES.indexOf(h[1].k) > -1; });
      var unit = places ? "곳" : "건";
      // '‘짜장면’ 12곳', or with several kinds '‘○○’ 25건 · 관광지 10 · 숙소 3 · 코스 12' (the kind counts only
      // when there is more than one kind; '중 20건' when the list is cut at LIMIT)
      var html = W ? '<p class="f-result">‘' + esc(raw.trim()) + "’ " +
          (hits.length > LIMIT ? esc(W.of).replace("{n}", LIMIT).replace("{m}", hits.length) : hits.length) +
          (counts.length > 1 ? " · " + esc(counts.join(" · ")) : "") + "</p>"
        : '<p class="f-result">‘' + esc(raw.trim()) + "’ " + hits.length + unit +
        (hits.length > LIMIT ? " 중 " + LIMIT + unit : "") + (counts.length > 1 ? " · " + esc(counts.join(" · ")) : "") + "</p>";
      html += synLine(found.parts, cut.map(function (h) { return h[1]; })) + planLine(raw);
      if (DIET.test(raw)) html += diet();
      ORDER.forEach(function (k) {
        if (!groups[k]) return;
        html += '<section class="res-g"><h2>' + KIND[k] + ' <span class="tn">' + groups[k].length + "</span></h2><ol>";
        groups[k].forEach(function (h) { html += item(h[1], h[2], h[3]); });
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
  // a suggested name searches at once (with a modifier key it stays a link: the same search in a new tab)
  out.addEventListener("click", function (ev) {
    var a = ev.target.closest && ev.target.closest("a[data-sug]");
    if (!a || ev.button || ev.metaKey || ev.ctrlKey || ev.shiftKey || ev.altKey) return;
    ev.preventDefault();
    input.value = a.textContent;
    render(input.value);
    remember(input.value);
  });
  var showAll = help && help.querySelector("[data-show-all]");
  if (showAll && dir) showAll.addEventListener("click", function () {
    dir.hidden = false;
    showAll.hidden = true;
    var h = doc.getElementById("h-dir");
    if (h) h.focus();
  });
  var q0 = new URLSearchParams(location.search).get("q");
  if (q0) { input.value = q0; render(q0); }
})();
