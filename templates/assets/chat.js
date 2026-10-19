/* 군산 여행 — the site assistant (owner decision 2026-10-13, CLAUDE.md 3.10). site.js loads this file and chat.css on
   the first press of [data-chat-open] (or after load when this tab left the chat open), or — on a page with the centre
   question card — when the reader touches the card: never in the first paint.
   window.gsChat = {open(opener), restore(), close(), ask(q), stop(), busy(), dock}.

   - Asks /api/chat/ (POST {messages, lang, page}) and reads its text/event-stream: status · text · done {links, fix,
     cut} · error {code}. Text is drawn once per animation frame. Links in an answer stay plain while it is written and
     become links when 'done' has checked them (fix: a page that does not exist, or an outside address the site's data
     does not carry, stays plain text). Model text is only ever put in the page as text nodes, never as HTML.
   - A cut answer (done.cut) offers 'continue' on the last answer: POST {…, continue: true} with the cut answer as the
     last message; the rest streams into the same answer. Earlier answers go back with their checked links as page
     paths, cut to 2,000 characters keeping the links of the cut part; a question the reader stopped is left out.
   - The conversation and the open state live in sessionStorage 'gs-chat' (this tab only); 'new chat' clears it.
     Nothing is stored on the server.
   - Two views, one per page. The panel: wide screens a card at the bottom right, non-modal; phones a full-height
     sheet, modal (the page behind is inert, Tab stays inside); Esc closes and focus returns to the launcher; Enter
     sends, Shift+Enter breaks the line. The dock (a page with [data-chat-dock] — the Korean home's centre card with
     its conversation panel under the card, the English home's centre card; templates/_ask.html.j2; the panel is
     never built there): the page's own box, button and starters ask (site.js routes them here through ask / stop /
     busy) and the conversation is drawn inside its [data-ask-log] — a head row ('대화' · '새 대화'), the messages
     scrolling inside a box whose fixed height is first-paint CSS (css/46-home-open.css, css/49-ask.css), so a
     streaming answer never moves the page. A panel of its own ([data-ask-log][data-ask-more], the Korean home) also
     gets its own follow-up box at its foot (Enter sends, never while an input method composes; its button stops an
     answer) and one plain line on what the answers are (data-note). The page's button turns into the stop button
     while an answer comes (its two labels share one grid cell). No restore on load: an old conversation shows when the
     reader uses the box. Korean + not_configured (no API key yet): the failed exchange is dropped and the question goes to the site
     search (/search/?q=), so the card keeps working as search; other languages show the message and their starters
     then follow their links. In both views a completed answer is announced once (polite; the message list itself is
     not a live region) and nothing is sent by an Enter the input method keeps (imeEnter: Korean, Japanese, Chinese).
   - UI strings in nine languages from <html lang>; the assistant answers in the language of the question.
   - GA4 like track.js (gtag, else the GTM dataLayer): chat_open, chat_send (no text), chat_link_click (data-track),
     each with chat_where 'panel' | 'dock'. */
(function () {
  "use strict";
  if (window.gsChat) return;
  var doc = document, root = doc.documentElement, win = window;
  var KEY = "gs-chat", API = "/api/chat/", MAX_Q = 800, KEEP = 24, SEND_PRIOR = 12, ANSWER_CHARS = 2000;
  var SITE = "https://gunsan.webforai.kr";

  var STR = {
    ko: {
      title: "군산 여행 도우미", note: "AI가 이 사이트 정보로 답합니다 · 방문 전 확인", about: "/about/#chatbot",
      intro: "장소·맛집·숙소·코스·행사를 이 사이트에 실린 정보로 찾아 드려요. 답마다 해당 페이지를 링크합니다.",
      chips: ["선유도 가는 법", "월요일에 여는 음식점", "비 오는 날 갈 곳", "군산 짬뽕 어디서 먹나요?", "이번 달 행사·축제"],
      placeholder: "군산 여행, 무엇이 궁금하세요?", label: "질문", send: "보내기", stop: "멈추기", newChat: "새 대화", conv: "대화",
      close: "닫기", retry: "다시 시도", stopped: "답을 멈췄습니다.", cut: "답이 길어 여기서 끊겼습니다.", more: "이어서 보기",
      thinking: "답을 찾는 중…", you: "질문", ai: "답", pages: "관련 페이지", newTab: "(새 창)",
      foot: "이름·전화번호 같은 개인정보는 쓰지 마세요. 대화는 저장하지 않습니다.", search: "/search/", searchLabel: "사이트 검색으로 찾기",
      kinds: { place: "장소", guide: "가이드", course: "코스", event: "행사", video: "영상", abroad: "해외 기사", page: "페이지" },
      err: { not_configured: "챗봇이 아직 연결되지 않았습니다.", rate_limited: "질문이 너무 잦습니다. 1분 뒤 다시 물어보세요.",
        daily_limit: "하루에 물을 수 있는 질문 수를 넘었습니다. 내일 다시 물어보세요.",
        too_long: "질문은 800자까지 쓸 수 있습니다.", busy: "지금은 답을 만들 수 없습니다. 잠시 뒤 다시 시도해 주세요.",
        timeout: "답이 너무 오래 걸려 멈췄습니다.", refusal: "이 질문에는 답할 수 없습니다.",
        truncated: "답이 너무 길어 멈췄습니다. 질문을 나눠 물어보세요.", network: "연결이 끊겼습니다. 인터넷 연결을 확인해 주세요.",
        error: "답을 가져오지 못했습니다." },
    },
    en: {
      title: "Gunsan travel helper", note: "AI answers from this site's information · check before you go",
      about: "/en/about/#chatbot",
      intro: "Ask about places, food, stays, courses and events. Answers come from this site's pages, with links to them.",
      chips: ["How do I get to Seonyudo?", "Restaurants open on Mondays", "Where to go on a rainy day",
        "Where can I eat jjamppong?", "Events this month"],
      placeholder: "Ask about travelling in Gunsan", label: "Question", send: "Send", stop: "Stop", newChat: "New chat", conv: "Conversation",
      close: "Close", retry: "Try again", stopped: "Answer stopped.", cut: "The answer was cut off here.", more: "Continue",
      thinking: "Looking it up…", you: "You", ai: "Answer", pages: "Pages", newTab: "(new tab)",
      foot: "Don't type personal details such as names or phone numbers. Chats are not stored.", search: "", searchLabel: "",
      kinds: { place: "Place", guide: "Guide", course: "Course", event: "Event", video: "Video", abroad: "Article", page: "Page" },
      err: { not_configured: "The assistant is not connected yet.", rate_limited: "Too many questions. Please wait a minute.",
        daily_limit: "You have reached the daily number of questions. Please ask again tomorrow.",
        too_long: "A question can be up to 800 characters.", busy: "The assistant cannot answer right now. Please try again shortly.",
        timeout: "The answer took too long and was stopped.", refusal: "This question cannot be answered.",
        truncated: "The answer was cut off. Try a narrower question.", network: "The connection was lost. Check your internet connection.",
        error: "Could not get an answer." },
    },
    ja: {
      title: "群山旅行アシスタント", note: "AIがこのサイトの情報で答えます・訪問前にご確認を",
      intro: "観光地・グルメ・宿・コース・イベントを、このサイトの情報で探します。答えには該当ページのリンクが付きます。",
      chips: ["仙遊島への行き方", "月曜日に開いている飲食店", "雨の日に行ける所", "群山のチャンポンはどこで食べられる？", "今月のイベント・祭り"],
      placeholder: "群山旅行について質問してください", label: "質問", send: "送信", stop: "停止", newChat: "新しい会話", conv: "会話", close: "閉じる",
      retry: "もう一度", stopped: "回答を停止しました。", cut: "回答はここで途切れました。", more: "続きを表示", thinking: "調べています…", you: "質問",
      ai: "回答", pages: "関連ページ", newTab: "（新しいタブ）",
      foot: "名前や電話番号などの個人情報は入力しないでください。会話は保存されません。",
      kinds: { place: "スポット", guide: "ガイド", course: "コース", event: "イベント", video: "動画", abroad: "記事", page: "ページ" },
      err: { not_configured: "アシスタントはまだ接続されていません。", rate_limited: "質問が多すぎます。1分ほどお待ちください。",
        daily_limit: "1日に質問できる回数を超えました。明日またお試しください。",
        too_long: "質問は800文字までです。", busy: "現在回答できません。しばらくしてからお試しください。",
        timeout: "時間がかかりすぎたため停止しました。", refusal: "この質問にはお答えできません。",
        truncated: "回答が長すぎて止まりました。質問を分けてください。", network: "接続が切れました。", error: "回答を取得できませんでした。" },
    },
    "zh-Hans": {
      title: "群山旅行助手", note: "AI根据本站信息回答 · 出发前请确认",
      intro: "用本站的信息查找景点、美食、住宿、路线和活动，每个回答都附有相关页面链接。",
      chips: ["怎么去仙游岛", "周一营业的餐厅", "下雨天去哪里", "群山炒码面在哪里吃？", "本月活动·节庆"],
      placeholder: "关于群山旅行，想问什么？", label: "问题", send: "发送", stop: "停止", newChat: "新对话", conv: "对话", close: "关闭",
      retry: "重试", stopped: "已停止回答。", cut: "回答在这里被截断。", more: "继续回答", thinking: "正在查找…", you: "提问", ai: "回答",
      pages: "相关页面", newTab: "（新标签页）", foot: "请勿输入姓名、电话号码等个人信息。对话不会被保存。",
      kinds: { place: "景点", guide: "指南", course: "路线", event: "活动", video: "视频", abroad: "文章", page: "页面" },
      err: { not_configured: "助手尚未连接。", rate_limited: "提问过于频繁，请一分钟后再试。",
        daily_limit: "已达到每天可提问的次数上限，请明天再问。", too_long: "问题最多800个字符。",
        busy: "现在无法回答，请稍后再试。", timeout: "回答时间过长，已停止。", refusal: "无法回答这个问题。",
        truncated: "回答过长被截断，请把问题拆开提问。", network: "连接已断开。", error: "未能获取回答。" },
    },
    "zh-Hant": {
      title: "群山旅行助手", note: "AI根據本站資訊回答 · 出發前請確認",
      intro: "用本站的資訊查找景點、美食、住宿、路線和活動，每個回答都附有相關頁面連結。",
      chips: ["怎麼去仙遊島", "週一營業的餐廳", "下雨天去哪裡", "群山炒碼麵在哪裡吃？", "本月活動·節慶"],
      placeholder: "關於群山旅行，想問什麼？", label: "問題", send: "傳送", stop: "停止", newChat: "新對話", conv: "對話", close: "關閉",
      retry: "重試", stopped: "已停止回答。", cut: "回答在這裡被截斷。", more: "繼續回答", thinking: "正在查找…", you: "提問", ai: "回答",
      pages: "相關頁面", newTab: "（新分頁）", foot: "請勿輸入姓名、電話號碼等個人資訊。對話不會被儲存。",
      kinds: { place: "景點", guide: "指南", course: "路線", event: "活動", video: "影片", abroad: "文章", page: "頁面" },
      err: { not_configured: "助手尚未連線。", rate_limited: "提問過於頻繁，請一分鐘後再試。",
        daily_limit: "已達到每天可提問的次數上限，請明天再問。", too_long: "問題最多800個字元。",
        busy: "現在無法回答，請稍後再試。", timeout: "回答時間過長，已停止。", refusal: "無法回答這個問題。",
        truncated: "回答過長被截斷，請把問題拆開提問。", network: "連線已中斷。", error: "未能取得回答。" },
    },
    de: {
      title: "Gunsan-Reisehelfer", note: "KI antwortet mit den Angaben dieser Website · vor dem Besuch prüfen",
      intro: "Fragen Sie nach Orten, Essen, Unterkünften, Routen und Veranstaltungen. Die Antworten stammen von den Seiten dieser Website, mit Links.",
      chips: ["Wie komme ich nach Seonyudo?", "Restaurants, die montags geöffnet haben", "Was tun bei Regen?",
        "Wo gibt es Jjamppong?", "Veranstaltungen in diesem Monat"],
      placeholder: "Ihre Frage zu Gunsan", label: "Frage", send: "Senden", stop: "Stopp", newChat: "Neuer Chat", conv: "Unterhaltung",
      close: "Schließen", retry: "Erneut versuchen", stopped: "Antwort gestoppt.", cut: "Die Antwort wurde hier abgeschnitten.", more: "Weiterschreiben",
      thinking: "Suche …", you: "Frage", ai: "Antwort", pages: "Seiten", newTab: "(neuer Tab)",
      foot: "Bitte keine persönlichen Daten wie Namen oder Telefonnummern eingeben. Chats werden nicht gespeichert.",
      kinds: { place: "Ort", guide: "Ratgeber", course: "Route", event: "Veranstaltung", video: "Video", abroad: "Artikel", page: "Seite" },
      err: { not_configured: "Der Assistent ist noch nicht verbunden.", rate_limited: "Zu viele Fragen. Bitte warten Sie eine Minute.",
        daily_limit: "Die Zahl der Fragen für heute ist erreicht. Bitte fragen Sie morgen wieder.",
        too_long: "Eine Frage darf höchstens 800 Zeichen haben.", busy: "Gerade ist keine Antwort möglich. Bitte später erneut versuchen.",
        timeout: "Die Antwort dauerte zu lange und wurde abgebrochen.", refusal: "Diese Frage kann nicht beantwortet werden.",
        truncated: "Die Antwort wurde abgeschnitten. Bitte fragen Sie enger.", network: "Die Verbindung wurde unterbrochen.",
        error: "Keine Antwort erhalten." },
    },
    fr: {
      title: "Assistant voyage Gunsan", note: "L'IA répond avec les informations de ce site · vérifiez avant de partir",
      intro: "Posez vos questions sur les lieux, restaurants, hébergements, circuits et événements : les réponses viennent des pages de ce site, avec des liens.",
      chips: ["Comment aller à Seonyudo ?", "Restaurants ouverts le lundi", "Où aller par temps de pluie",
        "Où manger du jjamppong ?", "Événements de ce mois-ci"],
      placeholder: "Votre question sur Gunsan", label: "Question", send: "Envoyer", stop: "Arrêter", newChat: "Nouvelle conversation", conv: "Conversation",
      close: "Fermer", retry: "Réessayer", stopped: "Réponse arrêtée.", cut: "La réponse a été coupée ici.", more: "Continuer", thinking: "Recherche…",
      you: "Question", ai: "Réponse", pages: "Pages", newTab: "(nouvel onglet)",
      foot: "N'indiquez pas de données personnelles (nom, téléphone). Les conversations ne sont pas enregistrées.",
      kinds: { place: "Lieu", guide: "Guide", course: "Circuit", event: "Événement", video: "Vidéo", abroad: "Article", page: "Page" },
      err: { not_configured: "L'assistant n'est pas encore connecté.", rate_limited: "Trop de questions. Patientez une minute.",
        daily_limit: "Vous avez atteint le nombre de questions pour aujourd'hui. Revenez demain.",
        too_long: "Une question compte au plus 800 caractères.", busy: "Impossible de répondre pour le moment. Réessayez plus tard.",
        timeout: "La réponse a pris trop de temps et a été arrêtée.", refusal: "Impossible de répondre à cette question.",
        truncated: "La réponse a été coupée. Posez une question plus précise.", network: "La connexion a été interrompue.",
        error: "Aucune réponse reçue." },
    },
    es: {
      title: "Asistente de viaje de Gunsan", note: "La IA responde con la información de este sitio · confirme antes de ir",
      intro: "Pregunte por lugares, comida, alojamiento, rutas y eventos: las respuestas salen de las páginas de este sitio, con enlaces.",
      chips: ["¿Cómo llegar a Seonyudo?", "Restaurantes abiertos los lunes", "Qué visitar si llueve",
        "¿Dónde comer jjamppong?", "Eventos de este mes"],
      placeholder: "Su pregunta sobre Gunsan", label: "Pregunta", send: "Enviar", stop: "Detener", newChat: "Nueva conversación", conv: "Conversación",
      close: "Cerrar", retry: "Reintentar", stopped: "Respuesta detenida.", cut: "La respuesta se cortó aquí.", more: "Continuar", thinking: "Buscando…",
      you: "Pregunta", ai: "Respuesta", pages: "Páginas", newTab: "(nueva pestaña)",
      foot: "No escriba datos personales como nombres o teléfonos. Las conversaciones no se guardan.",
      kinds: { place: "Lugar", guide: "Guía", course: "Ruta", event: "Evento", video: "Vídeo", abroad: "Artículo", page: "Página" },
      err: { not_configured: "El asistente aún no está conectado.", rate_limited: "Demasiadas preguntas. Espere un minuto.",
        daily_limit: "Ha alcanzado el número de preguntas de hoy. Vuelva a preguntar mañana.",
        too_long: "Una pregunta puede tener hasta 800 caracteres.", busy: "Ahora no es posible responder. Inténtelo más tarde.",
        timeout: "La respuesta tardó demasiado y se detuvo.", refusal: "No se puede responder a esta pregunta.",
        truncated: "La respuesta se cortó. Haga una pregunta más concreta.", network: "Se perdió la conexión.",
        error: "No se obtuvo respuesta." },
    },
    ru: {
      title: "Помощник по Кунсану", note: "ИИ отвечает по данным этого сайта · проверьте перед поездкой",
      intro: "Спрашивайте о местах, еде, жилье, маршрутах и событиях — ответы берутся со страниц этого сайта, со ссылками.",
      chips: ["Как добраться до Сонъюдо?", "Рестораны, открытые в понедельник", "Куда пойти в дождь",
        "Где поесть чжамппон?", "События в этом месяце"],
      placeholder: "Ваш вопрос о Кунсане", label: "Вопрос", send: "Отправить", stop: "Остановить", newChat: "Новый чат", conv: "Диалог",
      close: "Закрыть", retry: "Повторить", stopped: "Ответ остановлен.", cut: "Ответ оборвался здесь.", more: "Продолжить", thinking: "Ищу…",
      you: "Вопрос", ai: "Ответ", pages: "Страницы", newTab: "(новая вкладка)",
      foot: "Не вводите личные данные, например имя или телефон. Переписка не сохраняется.",
      kinds: { place: "Место", guide: "Гид", course: "Маршрут", event: "Событие", video: "Видео", abroad: "Статья", page: "Страница" },
      err: { not_configured: "Помощник ещё не подключён.", rate_limited: "Слишком много вопросов. Подождите минуту.",
        daily_limit: "Лимит вопросов на сегодня исчерпан. Спросите снова завтра.",
        too_long: "Вопрос — не длиннее 800 символов.", busy: "Сейчас ответить нельзя. Попробуйте позже.",
        timeout: "Ответ занял слишком много времени и был остановлен.", refusal: "На этот вопрос ответить нельзя.",
        truncated: "Ответ оборвался. Задайте вопрос уже.", network: "Соединение прервано.", error: "Не удалось получить ответ." },
    },
  };

  function pickLang(v) {
    var s = String(v || "").toLowerCase();
    var keys = Object.keys(STR);
    var hit = keys.filter(function (k) { return k.toLowerCase() === s; })[0];
    if (hit) return hit;
    if (s.indexOf("zh") === 0) return /(hant|tw|hk|mo)/.test(s) ? "zh-Hant" : "zh-Hans";
    return keys.indexOf(s.split("-")[0]) >= 0 ? s.split("-")[0] : "en";
  }
  var lang = pickLang(root.getAttribute("lang"));
  var T = Object.assign({}, STR.en, STR[lang]);
  if (lang !== "ko" && lang !== "en") T.about = STR.en.about;
  var sheetMQ = win.matchMedia("(max-width: 639px), (max-height: 520px)");
  // the centre question card (_ask.html.j2): on its page the conversation lives in the card, never in the panel
  var dockEl = doc.querySelector("[data-chat-dock]");
  var WHERE = dockEl ? "dock" : "panel";
  var reduce = win.matchMedia("(prefers-reduced-motion: reduce)");

  var ICON = {
    close: ["M6 6l12 12M18 6 6 18"],
    reset: ["M4.5 12a7.5 7.5 0 1 0 2.2-5.3", "M4.5 4.5v4h4"],
    send: ["M12 19V5", "m6 11 6-6 6 6"],
    stop: ["M8 8h8v8H8Z"],
    arrow: ["M5 12h14", "m13 6 6 6-6 6"],
    ext: ["M14 4h6v6", "M20 4l-9 9", "M18 14v5a1 1 0 0 1-1 1H5a1 1 0 0 1-1-1V7a1 1 0 0 1 1-1h5"],
  };

  // ------------------------------------------------------------ state (sessionStorage 'gs-chat', this tab only)
  var storageOff = false;
  function load() {
    var s = null;
    try { s = JSON.parse(win.sessionStorage.getItem(KEY) || "null"); } catch (e) { storageOff = true; s = null; }
    if (!s || s.v !== 1 || !Array.isArray(s.msgs)) s = { v: 1, open: false, msgs: [] };
    s.msgs = s.msgs.filter(function (m) { return m && (m.r === "u" || m.r === "a") && typeof m.t === "string"; });
    s.msgs.forEach(function (m) { if (m.r === "a" && m.p) { m.p = false; m.s = true; } });   // left the page mid-answer
    return s;
  }
  var state = load();
  function save() {
    if (storageOff) return;
    var msgs = state.msgs.slice(-KEEP).map(function (m) {
      return m.r === "u" ? { r: "u", t: m.t } : { r: "a", t: m.t, l: m.l || [], f: m.f || null, e: m.e || "", s: !!m.s, c: !!m.c, p: !!m.p };
    });
    try { win.sessionStorage.setItem(KEY, JSON.stringify({ v: 1, open: !!state.open, msgs: msgs })); } catch (e) { storageOff = true; }
  }

  // ------------------------------------------------------------ small DOM helpers (text only, never HTML)
  function h(tag, attrs, kids) {
    var el = doc.createElement(tag);
    Object.keys(attrs || {}).forEach(function (k) {
      var v = attrs[k];
      if (v === false || v === null || v === undefined) return;
      if (k === "text") el.textContent = v;
      else if (k === "class") el.className = v;
      else el.setAttribute(k, v === true ? "" : v);
    });
    (kids || []).forEach(function (c) { if (c) el.append(c); });
    return el;
  }
  function svg(name) {
    var NS = "http://www.w3.org/2000/svg";
    var s = doc.createElementNS(NS, "svg");
    [["class", "icon"], ["viewBox", "0 0 24 24"], ["fill", "none"], ["stroke", "currentColor"], ["stroke-width", "1.8"],
      ["stroke-linecap", "round"], ["stroke-linejoin", "round"], ["aria-hidden", "true"], ["focusable", "false"]].forEach(function (a) {
      s.setAttribute(a[0], a[1]);
    });
    ICON[name].forEach(function (d) {
      var p = doc.createElementNS(NS, "path");
      p.setAttribute("d", d);
      s.append(p);
    });
    return s;
  }
  function toLocal(url) {
    // a link to this site opens on the deployment the reader is on (production, a preview, a local test)
    return url.indexOf(SITE) === 0 ? url.slice(SITE.length) || "/" : url;
  }
  function external(url) {
    try {
      var u = new URL(url, win.location.href);
      return /^https?:$/.test(u.protocol) && u.host !== win.location.host;
    } catch (e) {
      return false;
    }
  }
  function anchor(url, label, cls) {
    var href = toLocal(url);
    var a = h("a", { href: href, class: cls || null, "data-track": "chat_link_click", "data-chat-where": WHERE, text: label });
    if (external(href)) {
      a.target = "_blank";
      a.rel = "noopener";
    }
    return a;
  }

  // ------------------------------------------------------------ answer text: paragraphs, lists, bold, links
  var INLINE = /\[([^\]\n]+)\]\(\s*<?([^)\s>]+)>?\s*\)|\*\*([^*\n]+)\*\*|(https?:\/\/[^\s<>()[\]"'`]+)|`([^`\n]+)`/g;
  function inline(parent, text, fix) {
    var at = 0, m;
    INLINE.lastIndex = 0;
    var parts = [];
    while ((m = INLINE.exec(text)) !== null) parts.push({ m: m, i: m.index });
    parts.forEach(function (p) {
      var x = p.m;
      if (p.i < at) return;
      if (p.i > at) parent.append(text.slice(at, p.i));
      if (x[1] !== undefined) parent.append(link(x[1], x[2], fix));
      else if (x[3] !== undefined) {
        var b = h("strong");
        inline(b, x[3], fix);
        parent.append(b);
      } else if (x[4] !== undefined) {
        var u = x[4].replace(/[.,;:!?。、]+$/, "");
        parent.append(link(u, u, fix));
        if (u.length < x[4].length) parent.append(x[4].slice(u.length));
      } else parent.append(x[5]);
      at = p.i + x[0].length;
    });
    if (at < text.length) parent.append(text.slice(at));
  }
  function link(label, raw, fix) {
    if (!fix) return h("span", { class: "chat-lk", text: label });   // still being written: not a link yet
    var url = Object.prototype.hasOwnProperty.call(fix, raw) ? fix[raw] : null;
    if (!url) return doc.createTextNode(label);
    var a = anchor(url, label);
    if (a.target === "_blank") a.append(h("span", { class: "vh", text: " " + T.newTab }));
    return a;
  }
  function md(text, fix) {
    var wrap = h("div", { class: "chat-md" });
    var para = [], list = null, listType = "";
    function flushPara() {
      if (!para.length) return;
      var p = h("p");
      para.forEach(function (ln, i) {
        if (i) p.append(h("br"));
        inline(p, ln, fix);
      });
      wrap.append(p);
      para = [];
    }
    function flushList() {
      if (list) wrap.append(list);
      list = null;
      listType = "";
    }
    String(text).replace(/\r/g, "").split("\n").forEach(function (raw) {
      var line = raw.replace(/\s+$/, "");
      if (!line.trim()) {
        flushPara();
        flushList();
        return;
      }
      var bullet = /^\s*[-*•·]\s+(.*)$/.exec(line);
      var num = /^\s*\d{1,2}[.)]\s+(.*)$/.exec(line);
      var head = /^\s*#{1,6}\s+(.*)$/.exec(line);
      if (bullet || num) {
        flushPara();
        var type = bullet ? "ul" : "ol";
        if (!list || listType !== type) {
          flushList();
          list = h(type);
          listType = type;
        }
        var li = h("li");
        inline(li, (bullet || num)[1], fix);
        list.append(li);
        return;
      }
      flushList();
      if (head) {
        flushPara();
        var strong = h("strong");
        inline(strong, head[1], fix);
        wrap.append(h("p", { class: "chat-h" }, [strong]));
        return;
      }
      para.push(line);
    });
    flushPara();
    flushList();
    return wrap;
  }
  function plain(text) {
    return String(text).replace(/\[([^\]\n]+)\]\([^)]*\)/g, "$1").replace(/\*\*|`|^#+\s*/gm, "").replace(/\s+/g, " ").trim();
  }
  function kindOf(l) {
    if (l.ext) {
      try { return new URL(l.url).host.replace(/^www\./, ""); } catch (e) { return T.kinds.page; }
    }
    var p = "/";
    try { p = decodeURIComponent(new URL(l.url, win.location.href).pathname).replace(/^\/en\//, "/"); } catch (e) { p = "/"; }
    var map = [["/places/", "place"], ["/stays/", "place"], ["/food/", "place"], ["/guides/", "guide"], ["/courses/", "course"],
      ["/events/", "event"], ["/videos/", "video"], ["/abroad/", "abroad"]];
    for (var i = 0; i < map.length; i += 1) if (p.indexOf(map[i][0]) === 0 && p !== map[i][0]) return T.kinds[map[i][1]];
    return T.kinds.page;
  }

  // ------------------------------------------------------------ the panel
  var ui = null, opener = null, busy = false, ctrl = null, raf = 0, inert = [];
  // An Enter that belongs to the input method (Korean, Japanese, Chinese): keydown while composing, or keyCode 229
  // where the composition has already ended (Safari). It commits or converts the text and never sends. The Enter Chrome
  // sends right after a Korean input method committed the last syllable is the reader's own: it sends at once (the
  // 2026-10-14 bug: a 50 ms guard after compositionend swallowed it, so such a question never sent on Enter).
  function imeEnter(e) { return e.isComposing || e.keyCode === 229; }
  function cssReady() {
    var l = doc.querySelector('link[href$="chat.css"]');
    if (!l || l.sheet) return Promise.resolve();
    return new Promise(function (ok) {
      l.addEventListener("load", ok, { once: true });
      l.addEventListener("error", ok, { once: true });
    });
  }
  function build() {
    var title = h("h2", { class: "chat-title", id: "chat-title", tabindex: "-1", text: T.title });
    var note = h("p", { class: "chat-note", id: "chat-note" }, [h("a", { href: T.about, text: T.note })]);
    var btnNew = h("button", { type: "button", class: "chat-ib", "aria-label": T.newChat, title: T.newChat }, [svg("reset")]);
    var btnClose = h("button", { type: "button", class: "chat-ib", "aria-label": T.close, title: T.close }, [svg("close")]);
    var head = h("div", { class: "chat-head" }, [h("div", { class: "chat-id" }, [title, note]), btnNew, btnClose]);
    var chips = h("ul", { class: "chat-chips" }, T.chips.map(function (q) {
      return h("li", {}, [h("button", { type: "button", class: "chat-chip", text: q })]);
    }));
    var hello = h("div", { class: "chat-hello" }, [h("p", { text: T.intro }), chips]);
    var list = h("ol", { class: "chat-msgs" });
    var log = h("div", { class: "chat-log" }, [hello, list]);
    var live = h("p", { class: "vh", "aria-live": "polite", "data-chat-live": true });
    var input = h("textarea", { id: "chat-q", rows: "1", maxlength: String(MAX_Q), placeholder: T.placeholder,
      enterkeyhint: "send", autocomplete: "off" });
    var send = h("button", { type: "submit", class: "chat-send", "aria-label": T.send, title: T.send }, [svg("send")]);
    var form = h("form", { class: "chat-form" }, [h("label", { class: "vh", for: "chat-q", text: T.label }), input, send]);
    var foot = h("p", { class: "chat-foot", text: T.foot });
    var panel = h("div", { class: "chat", id: "chat", role: "dialog", "aria-labelledby": "chat-title",
      "aria-describedby": "chat-note", "aria-modal": "false", lang: lang, hidden: true }, [head, log, live, form, foot]);
    doc.body.append(panel);

    btnClose.addEventListener("click", function () { close(); });
    btnNew.addEventListener("click", reset);
    chips.addEventListener("click", function (e) {
      var b = e.target.closest("button");
      if (b) ask(b.textContent);
    });
    form.addEventListener("submit", function (e) {
      e.preventDefault();
      if (busy) stop();
      else ask(input.value);
    });
    input.addEventListener("keydown", function (e) {
      if (e.key !== "Enter" || e.shiftKey || imeEnter(e)) return;
      e.preventDefault();
      if (!busy) ask(input.value);
    });
    input.addEventListener("input", function () { grow(); mode(busy ? "stop" : "send"); });
    panel.addEventListener("keydown", function (e) {
      if (e.key === "Escape" && !e.isComposing) {
        e.preventDefault();
        close();
      } else if (e.key === "Tab") trap(e);
    });
    panel.addEventListener("click", function (e) {
      var a = e.target.closest && e.target.closest("a[href]");
      // on a phone the sheet covers the page: leave it closed when a link opens a page in this tab
      if (a && a.target !== "_blank" && sheetMQ.matches) {
        state.open = false;
        save();
      }
    });
    return { panel: panel, title: title, log: log, list: list, hello: hello, live: live, input: input, send: send };
  }
  // the dock: the conversation inside the page's [data-ask-log] (its fixed height and frame: css/46-home-open.css,
  // css/49-ask.css; the box, the button and the starters are the page's own — site.js routes them to ask / stop /
  // busy). A panel of its own (data-ask-more, the Korean home) adds its follow-up box and the line in data-note.
  function buildDock() {
    var box = dockEl.querySelector("[data-ask-log]");
    var own = box.hasAttribute("data-ask-more");
    var btnNew = h("button", { type: "button", class: "ask-new" }, [svg("reset"), h("span", { text: T.newChat })]);
    var head = h("div", { class: "ask-log-head" }, [h(own ? "h2" : "h3", { class: "ask-log-h", id: "ask-log-h", text: T.conv }), btnNew]);
    var hello = h("p", { class: "ask-hello", text: T.intro });
    var list = h("ol", { class: "chat-msgs" });
    // a scrolling region: reachable with Tab even before an answer has a link in it
    var log = h("div", { class: "chat-log", role: "region", "aria-labelledby": "ask-log-h", tabindex: "0" }, [hello, list]);
    var live = h("p", { class: "vh", "aria-live": "polite", "data-chat-live": true });
    var more = own ? followUp(box.getAttribute("data-ask-more") || T.placeholder) : null;
    var note = box.getAttribute("data-note");
    box.replaceChildren(head, log, live);
    if (more) box.append(more.form);
    if (note) box.append(h("p", { class: "ask-note", text: note }));
    btnNew.addEventListener("click", reset);
    return { dock: true, box: box, log: log, list: list, hello: hello, live: live,
      input: dockEl.querySelector("[data-ask-q]"), send: dockEl.querySelector("[data-ask-go]"),
      input2: more && more.input, send2: more && more.send };
  }
  // the panel's own follow-up box: Enter sends (never while an input method composes); while an answer comes its
  // button stops it (Enter does not)
  function followUp(placeholder) {
    var input = h("input", { type: "text", id: "ask-q2", maxlength: String(MAX_Q), placeholder: placeholder,
      enterkeyhint: "send", autocomplete: "off" });
    var send = h("button", { type: "submit", class: "chat-send", "aria-label": T.send, title: T.send }, [svg("send")]);
    var form = h("form", { class: "chat-form ask-more" }, [h("label", { class: "vh", for: "ask-q2", text: T.label }), input, send]);
    var imeKey = false;
    input.addEventListener("keydown", function (e) {
      if (e.key !== "Enter") return;
      if (imeEnter(e)) {      // the input method's Enter: nothing is sent, nor a submit it makes in this same task
        imeKey = true;
        setTimeout(function () { imeKey = false; }, 0);
        return;
      }
      imeKey = false;
      e.preventDefault();     // Enter asks here, and leaves an answer that is coming be (the button stops it)
      if (!busy) ask(input.value);
    });
    input.addEventListener("input", function () { mode(busy ? "stop" : "send"); });
    form.addEventListener("submit", function (e) {   // the button
      e.preventDefault();
      if (imeKey) return;
      if (busy) stop();
      else ask(input.value);
    });
    return { form: form, input: input, send: send };
  }
  function view() {
    if (!ui) ui = dockEl ? buildDock() : build();
    return ui;
  }
  function showDock() {
    // shown at once (the reader's own input event: any shift is theirs); its height never changes after that
    dockEl.querySelector("[data-ask-log]").hidden = false;
  }
  function bringDock() {
    // the conversation in view after a question: the least scroll that shows the whole box (the page itself never
    // moves under the reader — this is a scroll, not a layout shift); a phone's keyboard closes so the answer shows
    if (!ui || !ui.dock) return;
    var typed = doc.activeElement;
    if (win.matchMedia("(pointer: coarse)").matches && typed && (typed === ui.input || typed === ui.input2)) typed.blur();
    ui.box.scrollIntoView({ block: "nearest", behavior: reduce.matches ? "auto" : "smooth" });   // nothing if it shows
  }
  function grow() {
    if (ui.dock) return;   // the card's box is one line
    var t = ui.input;
    t.style.height = "auto";
    t.style.height = Math.min(t.scrollHeight, 140) + "px";
  }
  function mode(m) {
    var b = ui.send;
    var want = m === "stop" ? "stop" : "send";
    if (ui.dock) {   // the page's button: both labels are in it, CSS shows the one for data-mode (its width stays)
      b.setAttribute("data-mode", want);
      if (ui.send2) iconMode(ui.send2, ui.input2, want);   // and the panel's own send button
      return;
    }
    iconMode(b, ui.input, want);
  }
  function iconMode(b, input, want) {   // a round send button: its icon and name follow the mode
    if (b.getAttribute("data-mode") !== want) {
      b.setAttribute("data-mode", want);
      b.setAttribute("aria-label", want === "stop" ? T.stop : T.send);
      b.title = want === "stop" ? T.stop : T.send;
      b.replaceChildren(svg(want));
    }
    b.disabled = want === "send" && !input.value.trim();
  }
  function trap(e) {
    if (ui.panel.getAttribute("aria-modal") !== "true") return;
    var f = Array.prototype.slice.call(ui.panel.querySelectorAll("a[href], button:not([disabled]), textarea, [tabindex]:not([tabindex='-1'])"))
      .filter(function (el) { return el.getClientRects().length; });
    if (!f.length) return;
    var first = f[0], last = f[f.length - 1];
    if (e.shiftKey && (doc.activeElement === first || !ui.panel.contains(doc.activeElement))) {
      e.preventDefault();
      last.focus();
    } else if (!e.shiftKey && doc.activeElement === last) {
      e.preventDefault();
      first.focus();
    }
  }
  function setModal(on) {
    ui.panel.setAttribute("aria-modal", on ? "true" : "false");
    root.classList.toggle("chat-lock", on);
    inert.forEach(function (el) { el.inert = false; });
    inert = [];
    if (on) {
      Array.prototype.forEach.call(doc.body.children, function (el) {
        if (el !== ui.panel && !el.inert && el.tagName !== "SCRIPT") {
          el.inert = true;
          inert.push(el);
        }
      });
      fit();
    } else {
      ui.panel.style.height = "";
      ui.panel.style.top = "";
    }
  }
  function fit() {
    // the sheet follows the visual viewport, so the on-screen keyboard never covers the input
    var v = win.visualViewport;
    if (!ui || !ui.panel || ui.panel.hidden || ui.panel.getAttribute("aria-modal") !== "true" || !v) return;
    ui.panel.style.height = v.height + "px";
    ui.panel.style.top = v.offsetTop + "px";
  }
  if (win.visualViewport) {
    win.visualViewport.addEventListener("resize", fit);
    win.visualViewport.addEventListener("scroll", fit);
  }
  sheetMQ.addEventListener("change", function () { if (ui && ui.panel && !ui.panel.hidden) setModal(sheetMQ.matches); });

  function open(from, quiet) {
    if (from) opener = from;
    if (dockEl) return quiet ? Promise.resolve() : openDock();   // no restore on a dock page: nothing moves on load
    return cssReady().then(function () {
      view();
      render();
      ui.panel.hidden = false;
      root.classList.add("chat-open");
      state.open = true;
      save();
      setModal(sheetMQ.matches);
      mode(busy ? "stop" : "send");
      grow();
      if (!quiet || sheetMQ.matches) (sheetMQ.matches ? ui.title : ui.input).focus({ preventScroll: true });
      if (!quiet) track("chat_open");
      ui.log.scrollTop = ui.log.scrollHeight;
    });
  }
  function openDock() {
    // the launcher on a dock page (site.js has brought the card into view and shown the box when this tab keeps a
    // conversation): draw that conversation into the card
    return cssReady().then(function () {
      view();
      render();
      if (state.msgs.length) showDock();
      mode(busy ? "stop" : "send");
      ui.log.scrollTop = ui.log.scrollHeight;
      if (ui.input2 && !ui.box.hidden) ui.input2.focus({ preventScroll: true });   // the conversation's own box
      track("chat_open");
    });
  }
  function close() {
    if (!ui || !ui.panel || ui.panel.hidden) return;
    ui.panel.hidden = true;
    root.classList.remove("chat-open");
    setModal(false);
    state.open = false;
    save();
    var back = opener && opener.isConnected ? opener : doc.querySelector(".chat-fab");
    if (back) back.focus({ preventScroll: true });
  }
  function reset() {
    if (busy) stop();
    state.msgs = [];
    save();
    root.classList.remove("chat-has");
    render();
    if (ui.dock) ui.box.hidden = true;   // the box as it was (the reader's own press: the shift is theirs)
    ui.input.focus({ preventScroll: !ui.input2 });   // a panel of its own closes: back to the question field, in view
  }
  function stop() {
    if (ctrl) ctrl.abort();
  }

  // ------------------------------------------------------------ messages
  function render() {
    ui.list.replaceChildren();
    state.msgs.forEach(function (m) { ui.list.append(msgEl(m)); });
    ui.hello.hidden = state.msgs.length > 0;
  }
  function msgEl(m) {
    if (m.r === "u") {
      m.el = h("li", { class: "chat-m chat-u" }, [h("p", {}, [h("span", { class: "vh", text: T.you + ": " }), doc.createTextNode(m.t)])]);
      return m.el;
    }
    m.el = h("li", { class: "chat-m chat-a" });
    fill(m);
    return m.el;
  }
  function fill(m) {
    var li = m.el;
    li.replaceChildren(h("span", { class: "vh", text: T.ai + ": " }));
    if (m.t) li.append(md(m.t, m.p ? null : m.f || {}));
    if (m.p && (m.st || !m.t)) li.append(h("p", { class: "chat-status", text: m.st || T.thinking }));
    if (m.c) {
      li.append(h("p", { class: "chat-note2", text: T.cut }));
      // the last answer, cut at the length limit: the server can write the rest ({continue: true})
      if (!busy && state.msgs[state.msgs.length - 1] === m) {
        var more = h("button", { type: "button", class: "chat-retry", text: T.more });
        more.addEventListener("click", function () { cont(m); });
        li.append(more);
      }
    }
    if (m.s) li.append(h("p", { class: "chat-note2", text: T.stopped }));
    if (m.e) li.append(errEl(m));
    if (!m.p && m.l && m.l.length) li.append(linksEl(m.l));
  }
  function errEl(m) {
    var box = h("div", { class: "chat-err" }, [h("p", { text: T.err[m.e] || T.err.error })]);
    if (m.e === "not_configured" || m.e === "daily_limit") {   // no retry that would be refused again: the site search
      if (T.search) box.append(h("p", {}, [h("a", { href: T.search, text: T.searchLabel })]));
    } else if (m.e !== "too_long" && m.e !== "refusal") {
      var b = h("button", { type: "button", class: "chat-retry", text: T.retry });
      b.addEventListener("click", function () { retry(m); });
      box.append(b);
    }
    return box;
  }
  function linksEl(links) {
    var ul = h("ul", { class: "chat-links", "aria-label": T.pages });
    links.forEach(function (l) {
      var a = anchor(l.url, "", "chat-card");
      a.append(h("span", { class: "chat-card-k", text: kindOf(l) }), h("span", { class: "chat-card-t", text: l.title }),
        svg(a.target === "_blank" ? "ext" : "arrow"));
      if (a.target === "_blank") a.append(h("span", { class: "vh", text: T.newTab }));
      ul.append(h("li", {}, [a]));
    });
    return ul;
  }
  function nearEnd() {
    var l = ui.log;
    return l.scrollHeight - l.scrollTop - l.clientHeight < 96;
  }
  function paint(m, now) {
    if (now) {
      if (raf) win.cancelAnimationFrame(raf);
      raf = 0;
      var stick = nearEnd();
      fill(m);
      if (stick) ui.log.scrollTop = ui.log.scrollHeight;
      return;
    }
    if (raf) return;
    raf = win.requestAnimationFrame(function () {
      raf = 0;
      var stick = nearEnd();
      fill(m);
      if (stick) ui.log.scrollTop = ui.log.scrollHeight;
    });
  }
  function announce(m) {
    var text = m.e ? T.err[m.e] || T.err.error : plain(m.t) + (m.s ? " " + T.stopped : "");
    ui.live.textContent = "";
    win.setTimeout(function () { ui.live.textContent = (T.ai + ": " + text).slice(0, 700); }, 60);
  }

  // ------------------------------------------------------------ asking
  var MDLINK = /\[([^\]\n]+)\]\(\s*<?([^)\s>]+)>?\s*\)/g;
  function readable(url) {
    // a page of this site as its path ('/places/근대역사박물관/'): what the catalog gives, a third of the length
    var u = toLocal(url);
    if (u.charAt(0) !== "/") return u;
    try { return decodeURI(u); } catch (e) { return u; }
  }
  function settle(text, fix) {
    // an earlier answer as the reader saw it: checked links with their final address, the rest as plain text
    return String(text).replace(MDLINK, function (all, label, raw) {
      return fix && fix[raw] ? "[" + label + "](" + readable(fix[raw]) + ")" : label;
    });
  }
  function prior(x) {
    // cut to ANSWER_CHARS; the links of the part a cut drops follow it, so the pages the answer used stay known
    var s = settle(x.t, x.f);
    if (s.length <= ANSWER_CHARS) return s;
    var links = [], m;
    var rest = s.slice(ANSWER_CHARS - 400);
    MDLINK.lastIndex = 0;
    while ((m = MDLINK.exec(rest)) !== null) {
      var md = "[" + m[1] + "](" + m[2] + ")";
      if (links.indexOf(md) < 0 && links.length < 6) links.push(md);
    }
    var tail = links.length ? "\n" + links.join("\n") : "";
    return s.slice(0, ANSWER_CHARS - tail.length - 2) + " …" + tail;
  }
  function payload(m, more) {
    // the conversation before m (with more: up to m, the cut answer to go on with — raw, as the model wrote it). A
    // question whose answer the reader stopped is left out with it: the reader moved on.
    var msgs = [];
    var upto = state.msgs.indexOf(m) + (more ? 1 : 0);
    state.msgs.slice(0, upto).forEach(function (x, i, all) {
      var next = all[i + 1];
      if (x.r === "u") {
        if (!(next && next.r === "a" && next.s)) msgs.push({ role: "user", content: x.t });
      } else if (x === m && more) msgs.push({ role: "assistant", content: x.t });
      else if (x.t && !x.e && !x.s) msgs.push({ role: "assistant", content: prior(x) });
    });
    var body = { messages: msgs.slice(-(SEND_PRIOR + (more ? 2 : 1))), lang: lang, page: win.location.pathname };
    if (more) body["continue"] = true;
    return body;
  }
  function ask(q) {
    q = String(q || "").trim();
    if (!q || busy) return;
    if (Array.from(q).length > MAX_Q) {
      flashErr("too_long");
      return;
    }
    // the box empties when its own text was asked (a starter leaves what the reader was typing)
    [ui.input, ui.input2].forEach(function (el) { if (el && (!ui.dock || el.value.trim() === q)) el.value = ""; });
    grow();
    state.msgs.push({ r: "u", t: q });
    var m = { r: "a", t: "", p: true, st: T.thinking, l: [], f: null, e: "" };
    state.msgs.push(m);
    root.classList.add("chat-has");
    save();
    render();
    if (ui.dock) showDock();
    ui.log.scrollTop = ui.log.scrollHeight;
    bringDock();
    track("chat_send");
    run(m);
  }
  function flashErr(code) {
    var m = { r: "a", t: "", p: false, e: code, l: [] };
    ui.list.append(msgEl(m));
    ui.hello.hidden = true;
    if (ui.dock) showDock();
    ui.log.scrollTop = ui.log.scrollHeight;
    announce(m);
  }
  function toSearch(m) {
    // the Korean card while the assistant is not connected (503 not_configured: no API key yet): it keeps working as
    // the site search — the failed exchange leaves the conversation and the question goes to /search/
    var i = state.msgs.indexOf(m), u = i > 0 && state.msgs[i - 1].r === "u" ? state.msgs[i - 1] : null;
    if (i >= 0) state.msgs.splice(u ? i - 1 : i, u ? 2 : 1);
    save();
    if (!state.msgs.length) root.classList.remove("chat-has");
    mode("send");
    render();
    win.location.assign(T.search + "?q=" + encodeURIComponent(u ? u.t : ""));
  }
  function retry(m) {
    if (busy) return;
    m.t = "";
    m.e = "";
    m.s = false;
    m.c = false;
    m.d = false;
    m.l = [];
    m.f = null;
    m.p = true;
    m.st = T.thinking;
    paint(m, true);
    run(m);
  }
  function cont(m) {
    // go on with a cut answer: the server writes only the rest, which is added to this same answer
    if (busy) return;
    m.c = false;
    m.d = false;
    m.p = true;
    m.st = T.thinking;
    paint(m, true);
    run(m, true);
  }
  function httpCode(status) {
    if (status === 503) return "not_configured";
    if (status === 429) return "rate_limited";
    if (status === 413) return "too_long";
    return "error";
  }
  function run(m, more) {
    busy = true;
    mode("stop");
    ctrl = new AbortController();
    var c = ctrl;
    return win.fetch(API, { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(payload(m, more)),
      signal: c.signal, credentials: "same-origin" })
      .then(function (res) {
        if (!res.ok || !res.body) {
          return res.json().then(function (j) { m.e = (j && j.code) || httpCode(res.status); }, function () { m.e = httpCode(res.status); });
        }
        return readSSE(res.body, function (ev) { onEvent(m, ev, more); }).then(function () { if (!m.d && !m.e) m.e = "error"; });
      })
      .catch(function (err) {
        if (err && err.name === "AbortError") m.s = true;
        else m.e = "network";
      })
      .then(function () {
        busy = false;
        ctrl = null;
        m.p = false;
        m.st = "";
        if (ui && ui.dock && m.e === "not_configured") {
          // the card: its starters go back to being links (site.js); in Korean the question goes to the search
          dockEl.setAttribute("data-chat-off", "");
          if (T.search) {
            toSearch(m);
            return;
          }
        }
        if (ui) {
          mode("send");
          paint(m, true);
          announce(m);
        }
        save();
      });
  }
  function onEvent(m, ev, more) {
    if (ev.type === "status") {
      m.st = String(ev.text || "");
      paint(m);
    } else if (ev.type === "text") {
      m.t += String(ev.delta || "");
      m.st = "";
      paint(m);
    } else if (ev.type === "done") {
      var links = Array.isArray(ev.links) ? ev.links : [];
      var fix = ev.fix && typeof ev.fix === "object" ? ev.fix : {};
      if (more) {   // the rest of a cut answer: its checked links join those of the part already shown
        m.f = Object.assign({}, m.f || {}, fix);
        if (!Array.isArray(m.l)) m.l = [];
        links.forEach(function (l) {
          if (!m.l.some(function (x) { return x.url === l.url; })) m.l.push(l);
        });
      } else {
        m.l = links;
        m.f = fix;
      }
      m.c = !!ev.cut;
      m.d = true;
    } else if (ev.type === "error") {
      m.e = String(ev.code || "error");
      m.d = true;
    }
  }
  function readSSE(body, cb) {
    var reader = body.getReader(), dec = new TextDecoder(), buf = "";
    function block(b) {
      var data = b.split("\n").filter(function (l) { return l.indexOf("data:") === 0; })
        .map(function (l) { return l.slice(5).replace(/^ /, ""); }).join("\n");
      if (!data) return;
      var ev = null;
      try { ev = JSON.parse(data); } catch (e) { ev = null; }
      if (ev) cb(ev);
    }
    function pump() {
      return reader.read().then(function (r) {
        if (r.done) {
          if (buf.trim()) block(buf);
          return undefined;
        }
        buf += dec.decode(r.value, { stream: true });
        var i;
        while ((i = buf.indexOf("\n\n")) >= 0) {
          block(buf.slice(0, i));
          buf = buf.slice(i + 2);
        }
        return pump();
      });
    }
    return pump();
  }

  // ------------------------------------------------------------ GA4 (like track.js: gtag, else the GTM dataLayer)
  function track(name) {
    var params = { page_kind: doc.body.getAttribute("data-page-kind") || "", chat_lang: lang, chat_where: WHERE };
    if (typeof win.gtag === "function") {
      win.gtag("event", name, params);
      return;
    }
    if (win.dataLayer && typeof win.dataLayer.push === "function") win.dataLayer.push(Object.assign({ event: name }, params));
  }

  win.gsChat = {
    open: function (from) { return open(from, false); },
    restore: function () { return open(null, true); },
    close: close,
    // a question from outside (site.js: the centre card's box and starters): in the card on a dock page — its box is
    // shown at once, inside the caller's input event — else in the panel
    ask: function (q) {
      if (!dockEl) return open(null, false).then(function () { ask(q); });
      showDock();
      return cssReady().then(function () {
        view();
        ask(q);
      });
    },
    stop: stop,
    busy: function () { return busy; },
    dock: !!dockEl,
  };
})();
