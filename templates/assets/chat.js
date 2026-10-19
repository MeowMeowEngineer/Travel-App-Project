/* The site assistant (owner decision 2026-10-13, CLAUDE.md 3.10). site.js loads this file and chat.css on
   the first press of [data-chat-open] (or after load when this tab left the chat open), or — on a page with the centre
   question card — when the reader touches the card: never in the first paint.
   window.gsChat = {open(opener), restore(), close(), ask(q, from), stop(), busy(), ready(), dock}.

   - Key-ready (README '사이트 도우미'): on load the module asks GET /api/chat/ once — 200 {ready: true}, or 503
     {code: 'not_configured'} while the site has no ANTHROPIC_API_KEY. The answer is kept for this tab for five minutes
     (sessionStorage 'gs-chat-ready'); the panel waits for it up to 1.2 s before it opens. Not configured: the panel
     shows a calm 'AI 도우미 준비 중' block instead of the question box — in Korean with the site search
     (data-chat-search on the launcher: /search/ when the build has a search page) — and the homes' card
     ([data-chat-dock]) gets data-chat-off (site.js: its box searches, its starters stay links) and resting words in
     its line (_ask.html.j2 data-ask-line), placeholder and button ('검색하기'); a card with nothing to search rests
     read-only. A question that
     still meets 503 not_configured (the key was removed) turns the view the same way, with the question in the search
     box. Any other answer, or none, leaves the assistant as it is: a failed question says why.

   - Asks /api/chat/ (POST {messages, lang, page}) and reads its text/event-stream: meta {dir, site, lang?} · status ·
     text · done {links, fix, cut} · error {code}. meta: the answer is drawn with its own lang (when the server is sure
     of it) and direction (an Arabic answer right to left, its phone numbers and dates as left-to-right runs), and its
     cards name their kind in the language of the pages they open (site). Text is drawn once per animation frame.
     Links in an answer stay plain while it is written and
     become links when 'done' has checked them (fix: a page that does not exist, or an outside address the site's data
     does not carry, stays plain text). Model text is only ever put in the page as text nodes, never as HTML.
   - The course planner's door (Korean pages of a site that has /plan/, the header's data-track="plan_cta" link): a
     question that clearly states trip conditions — a date, 당일·1박 2일, 차 없이 or 자가용, a child, 비·유모차·휠체어·
     주차·덜 걷기, a time it arrives at or leaves one of the city's hubs (data-chat-hubs; planQuery: a conservative reader that leaves out what it
     is not sure of) — gets under its finished answer (not a stopped or cut one) one link, '이 조건으로 AI 코스
     만들기', to /plan/ with those conditions, over the ones its earlier questions in the conversation stated, as URL
     parameters (GA4 plan_cta, chat_where).
   - Errors in the page's language, one text per code (err; every code the server sends reads as one of them: ERR_AS).
   - A cut answer (done.cut) offers 'continue' on the last answer: POST {…, continue: true} with the cut answer as the
     last message; the rest streams into the same answer. Earlier answers go back with their checked links as page
     paths, cut to 2,000 characters keeping the links of the cut part; a question the reader stopped is left out.
   - The conversation and the open state live in sessionStorage 'gs-chat' (this tab only); 'new chat' clears it.
     Nothing is stored on the server: the conversation stays in this tab (sessionStorage) and each question goes to
     Anthropic to be answered — the notice under the box says so in every language (operator 2026-10-18).
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
   - UI strings in nine languages from <html lang>; the assistant answers in the language of the question. The city's
     words come from the launcher (_chat.html.j2, from site.json): data-chat-site (the public address: a link to it
     opens on the deployment the reader is on), data-chat-city ({lang: the city's name}, which fills the title and the
     box's placeholder; a language without a name uses the city-free wording) and data-chat-chips ({lang: [starter
     questions]}, none: no starters).
   - GA4 like track.js (gtag, else the GTM dataLayer): chat_open, chat_send (no text), chat_link_click (data-track) —
     booking_click for a card of an official booking page (the server's link.book, kinds.book '예약하기 · host') —
     each with chat_where 'panel' | 'dock'. */
(function () {
  "use strict";
  if (window.gsChat) return;
  var doc = document, root = doc.documentElement, win = window;
  var KEY = "gs-chat", API = "/api/chat/", MAX_Q = 800, KEEP = 24, SEND_PRIOR = 12, ANSWER_CHARS = 2000;
  var READY_KEY = "gs-chat-ready", READY_MS = 5 * 60 * 1000, READY_WAIT = 1200;
  var FAB = doc.querySelector("[data-chat-site]");
  var SITE = (FAB && FAB.getAttribute("data-chat-site")) || win.location.origin;
  // the Korean site search (the launcher says whether the build has one; an older page without the attribute: yes)
  var SEARCH = FAB && FAB.hasAttribute("data-chat-search") ? FAB.getAttribute("data-chat-search") : "/search/";
  function pageJSON(name) {
    try { return JSON.parse((FAB && FAB.getAttribute(name)) || "{}") || {}; } catch (e) { return {}; }
  }

  var STR = {
    ko: {
      offH: "AI 도우미 준비 중", offP: "준비가 끝나면 여기서 이 사이트의 정보로 답해 드립니다.",
      offS: "지금은 사이트 검색을 이용해 주세요. 장소·음식점·숙소 이름이나 대표 메뉴, 동 이름으로 찾을 수 있습니다.",
      offPh: "장소·메뉴·동 이름", offGo: "검색", offLine: "AI 도우미 준비 중 — 지금은 질문을 사이트 검색으로 찾아 드립니다.",
      offBtn: "검색하기",
      title: ["{c} 여행 도우미", "여행 도우미"], note: "AI가 이 사이트 정보로 답합니다 · 방문 전 확인", about: "/about/#chatbot",
      intro: "장소·맛집·숙소·코스·행사를 이 사이트에 실린 정보로 찾아 드려요. 답마다 해당 페이지를 링크합니다.",
      chips: [],
      placeholder: ["{c} 여행, 무엇이 궁금하세요?", "여행, 무엇이 궁금하세요?"], label: "질문", send: "보내기", stop: "멈추기", newChat: "새 대화", conv: "대화",
      close: "닫기", retry: "다시 시도", stopped: "답을 멈췄습니다.", cut: "답이 길어 여기서 끊겼습니다.", more: "이어서 보기",
      thinking: "답을 찾는 중…", you: "질문", ai: "답", pages: "관련 페이지", newTab: "(새 창)",
      foot: "이름·전화번호 같은 개인정보는 쓰지 마세요. 대화는 이 탭에만 임시 보관되고, 질문은 답을 만들기 위해 Anthropic으로 전송됩니다.", search: "/search/", searchLabel: "사이트 검색으로 찾기",
      plan: "이 조건으로 AI 코스 만들기",
      kinds: { place: "장소", guide: "가이드", course: "코스", event: "행사", video: "영상", abroad: "해외 기사", page: "페이지", book: "예약하기" },
      err: { not_configured: "AI 도우미가 아직 준비 중입니다.", rate_limited: "질문이 너무 잦습니다. 1분 뒤 다시 물어보세요.",
        daily_limit: "하루에 물을 수 있는 질문 수를 넘었습니다. 내일 다시 물어보세요.",
        too_long: "질문은 800자까지 쓸 수 있습니다.", busy: "지금은 답을 만들 수 없습니다. 잠시 뒤 다시 시도해 주세요.",
        timeout: "답이 너무 오래 걸려 멈췄습니다.", refusal: "이 질문에는 답할 수 없습니다.",
        truncated: "답이 너무 길어 멈췄습니다. 질문을 나눠 물어보세요.", network: "연결이 끊겼습니다. 인터넷 연결을 확인해 주세요.",
        error: "답을 가져오지 못했습니다." },
    },
    en: {
      offH: "The AI helper is getting ready", offS: "", offPh: "", offGo: "", offLine: "", offBtn: "",
      offP: "Once it is set up, it will answer here from this site's information.",
      title: ["{c} travel helper", "Travel helper"], note: "AI answers from this site's information · check before you go",
      about: "/en/about/#chatbot",
      intro: "Ask about places, food, stays, courses and events. Answers come from this site's pages, with links to them.",
      chips: [],
      placeholder: ["Ask about travelling in {c}", "Ask about your trip"], label: "Question", send: "Send", stop: "Stop", newChat: "New chat", conv: "Conversation",
      close: "Close", retry: "Try again", stopped: "Answer stopped.", cut: "The answer was cut off here.", more: "Continue",
      thinking: "Looking it up…", you: "You", ai: "Answer", pages: "Pages", newTab: "(new tab)",
      foot: "Don't type personal details such as names or phone numbers. Chats stay only in this tab, and questions are sent to Anthropic to be answered.", search: "", searchLabel: "",
      kinds: { place: "Place", guide: "Guide", course: "Course", event: "Event", video: "Video", abroad: "Article", page: "Page", book: "Book" },
      err: { not_configured: "The AI helper is not set up yet.", rate_limited: "Too many questions. Please wait a minute.",
        daily_limit: "You have reached the daily number of questions. Please ask again tomorrow.",
        too_long: "A question can be up to 800 characters.", busy: "The assistant cannot answer right now. Please try again shortly.",
        timeout: "The answer took too long and was stopped.", refusal: "This question cannot be answered.",
        truncated: "The answer was cut off. Try a narrower question.", network: "The connection was lost. Check your internet connection.",
        error: "Could not get an answer." },
    },
    ja: {
      offH: "AIアシスタントは準備中です", offP: "準備ができしだい、ここでこのサイトの情報をもとにお答えします。",
      title: ["{c}旅行アシスタント", "旅行アシスタント"], note: "AIがこのサイトの情報で答えます・訪問前にご確認を",
      intro: "観光地・グルメ・宿・コース・イベントを、このサイトの情報で探します。答えには該当ページのリンクが付きます。",
      chips: [],
      placeholder: ["{c}旅行について質問してください", "旅行について質問してください"], label: "質問", send: "送信", stop: "停止", newChat: "新しい会話", conv: "会話", close: "閉じる",
      retry: "もう一度", stopped: "回答を停止しました。", cut: "回答はここで途切れました。", more: "続きを表示", thinking: "調べています…", you: "質問",
      ai: "回答", pages: "関連ページ", newTab: "（新しいタブ）",
      foot: "名前や電話番号などの個人情報は入力しないでください。会話はこのタブにだけ一時保存され、質問は回答のためAnthropicに送信されます。",
      kinds: { place: "スポット", guide: "ガイド", course: "コース", event: "イベント", video: "動画", abroad: "記事", page: "ページ", book: "予約する" },
      err: { not_configured: "アシスタントはまだ接続されていません。", rate_limited: "質問が多すぎます。1分ほどお待ちください。",
        daily_limit: "1日に質問できる回数を超えました。明日またお試しください。",
        too_long: "質問は800文字までです。", busy: "現在回答できません。しばらくしてからお試しください。",
        timeout: "時間がかかりすぎたため停止しました。", refusal: "この質問にはお答えできません。",
        truncated: "回答が長すぎて止まりました。質問を分けてください。", network: "接続が切れました。インターネット接続を確認してください。", error: "回答を取得できませんでした。" },
    },
    "zh-Hans": {
      offH: "AI助手正在准备中", offP: "准备好后，将在这里根据本站信息回答。",
      title: ["{c}旅行助手", "旅行助手"], note: "AI根据本站信息回答 · 出发前请确认",
      intro: "用本站的信息查找景点、美食、住宿、路线和活动，每个回答都附有相关页面链接。",
      chips: [],
      placeholder: ["关于{c}旅行，想问什么？", "关于旅行，想问什么？"], label: "问题", send: "发送", stop: "停止", newChat: "新对话", conv: "对话", close: "关闭",
      retry: "重试", stopped: "已停止回答。", cut: "回答在这里被截断。", more: "继续回答", thinking: "正在查找…", you: "提问", ai: "回答",
      pages: "相关页面", newTab: "（新标签页）", foot: "请勿输入姓名、电话号码等个人信息。对话只临时保存在此标签页，提问会发送给Anthropic以生成回答。",
      kinds: { place: "景点", guide: "指南", course: "路线", event: "活动", video: "视频", abroad: "文章", page: "页面", book: "预订" },
      err: { not_configured: "助手尚未连接。", rate_limited: "提问过于频繁，请一分钟后再试。",
        daily_limit: "已达到每天可提问的次数上限，请明天再问。", too_long: "问题最多800个字符。",
        busy: "现在无法回答，请稍后再试。", timeout: "回答时间过长，已停止。", refusal: "无法回答这个问题。",
        truncated: "回答过长被截断，请把问题拆开提问。", network: "连接已断开，请检查网络连接。", error: "未能获取回答。" },
    },
    "zh-Hant": {
      offH: "AI助手正在準備中", offP: "準備好後，將在這裡根據本站資訊回答。",
      title: ["{c}旅行助手", "旅行助手"], note: "AI根據本站資訊回答 · 出發前請確認",
      intro: "用本站的資訊查找景點、美食、住宿、路線和活動，每個回答都附有相關頁面連結。",
      chips: [],
      placeholder: ["關於{c}旅行，想問什麼？", "關於旅行，想問什麼？"], label: "問題", send: "傳送", stop: "停止", newChat: "新對話", conv: "對話", close: "關閉",
      retry: "重試", stopped: "已停止回答。", cut: "回答在這裡被截斷。", more: "繼續回答", thinking: "正在查找…", you: "提問", ai: "回答",
      pages: "相關頁面", newTab: "（新分頁）", foot: "請勿輸入姓名、電話號碼等個人資訊。對話只暫存在此分頁，提問會傳送給Anthropic以產生回答。",
      kinds: { place: "景點", guide: "指南", course: "路線", event: "活動", video: "影片", abroad: "文章", page: "頁面", book: "預訂" },
      err: { not_configured: "助手尚未連線。", rate_limited: "提問過於頻繁，請一分鐘後再試。",
        daily_limit: "已達到每天可提問的次數上限，請明天再問。", too_long: "問題最多800個字元。",
        busy: "現在無法回答，請稍後再試。", timeout: "回答時間過長，已停止。", refusal: "無法回答這個問題。",
        truncated: "回答過長被截斷，請把問題拆開提問。", network: "連線已中斷，請檢查網路連線。", error: "未能取得回答。" },
    },
    de: {
      offH: "Der KI-Helfer wird gerade eingerichtet", offP: "Sobald er bereit ist, antwortet er hier mit den Angaben dieser Website.",
      title: ["{c}-Reisehelfer", "Reisehelfer"], note: "KI antwortet mit den Angaben dieser Website · vor dem Besuch prüfen",
      intro: "Fragen Sie nach Orten, Essen, Unterkünften, Routen und Veranstaltungen. Die Antworten stammen von den Seiten dieser Website, mit Links.",
      chips: [],
      placeholder: ["Ihre Frage zu {c}", "Ihre Frage zur Reise"], label: "Frage", send: "Senden", stop: "Stopp", newChat: "Neuer Chat", conv: "Unterhaltung",
      close: "Schließen", retry: "Erneut versuchen", stopped: "Antwort gestoppt.", cut: "Die Antwort wurde hier abgeschnitten.", more: "Weiterschreiben",
      thinking: "Suche …", you: "Frage", ai: "Antwort", pages: "Seiten", newTab: "(neuer Tab)",
      foot: "Bitte keine persönlichen Daten wie Namen oder Telefonnummern eingeben. Chats bleiben nur vorübergehend in diesem Tab, und Fragen werden zur Beantwortung an Anthropic gesendet.",
      kinds: { place: "Ort", guide: "Ratgeber", course: "Route", event: "Veranstaltung", video: "Video", abroad: "Artikel", page: "Seite", book: "Buchen" },
      err: { not_configured: "Der Assistent ist noch nicht verbunden.", rate_limited: "Zu viele Fragen. Bitte warten Sie eine Minute.",
        daily_limit: "Die Zahl der Fragen für heute ist erreicht. Bitte fragen Sie morgen wieder.",
        too_long: "Eine Frage darf höchstens 800 Zeichen haben.", busy: "Gerade ist keine Antwort möglich. Bitte später erneut versuchen.",
        timeout: "Die Antwort dauerte zu lange und wurde abgebrochen.", refusal: "Diese Frage kann nicht beantwortet werden.",
        truncated: "Die Antwort wurde abgeschnitten. Bitte fragen Sie enger.", network: "Die Verbindung wurde unterbrochen. Bitte prüfen Sie Ihre Internetverbindung.",
        error: "Keine Antwort erhalten." },
    },
    fr: {
      offH: "L'assistant IA est en préparation", offP: "Dès qu'il sera prêt, il répondra ici avec les informations de ce site.",
      title: ["Assistant voyage {c}", "Assistant voyage"], note: "L'IA répond avec les informations de ce site · vérifiez avant de partir",
      intro: "Posez vos questions sur les lieux, restaurants, hébergements, circuits et événements : les réponses viennent des pages de ce site, avec des liens.",
      chips: [],
      placeholder: ["Votre question sur {c}", "Votre question sur le voyage"], label: "Question", send: "Envoyer", stop: "Arrêter", newChat: "Nouvelle conversation", conv: "Conversation",
      close: "Fermer", retry: "Réessayer", stopped: "Réponse arrêtée.", cut: "La réponse a été coupée ici.", more: "Continuer", thinking: "Recherche…",
      you: "Question", ai: "Réponse", pages: "Pages", newTab: "(nouvel onglet)",
      foot: "N'indiquez pas de données personnelles (nom, téléphone). Les conversations restent seulement dans cet onglet, et les questions sont envoyées à Anthropic pour la réponse.",
      kinds: { place: "Lieu", guide: "Guide", course: "Circuit", event: "Événement", video: "Vidéo", abroad: "Article", page: "Page", book: "Réserver" },
      err: { not_configured: "L'assistant n'est pas encore connecté.", rate_limited: "Trop de questions. Patientez une minute.",
        daily_limit: "Vous avez atteint le nombre de questions pour aujourd'hui. Revenez demain.",
        too_long: "Une question compte au plus 800 caractères.", busy: "Impossible de répondre pour le moment. Réessayez plus tard.",
        timeout: "La réponse a pris trop de temps et a été arrêtée.", refusal: "Impossible de répondre à cette question.",
        truncated: "La réponse a été coupée. Posez une question plus précise.", network: "La connexion a été interrompue. Vérifiez votre connexion Internet.",
        error: "Aucune réponse reçue." },
    },
    es: {
      offH: "El asistente de IA se está preparando", offP: "Cuando esté listo, responderá aquí con la información de este sitio.",
      title: ["Asistente de viaje de {c}", "Asistente de viaje"], note: "La IA responde con la información de este sitio · confirme antes de ir",
      intro: "Pregunte por lugares, comida, alojamiento, rutas y eventos: las respuestas salen de las páginas de este sitio, con enlaces.",
      chips: [],
      placeholder: ["Su pregunta sobre {c}", "Su pregunta sobre el viaje"], label: "Pregunta", send: "Enviar", stop: "Detener", newChat: "Nueva conversación", conv: "Conversación",
      close: "Cerrar", retry: "Reintentar", stopped: "Respuesta detenida.", cut: "La respuesta se cortó aquí.", more: "Continuar", thinking: "Buscando…",
      you: "Pregunta", ai: "Respuesta", pages: "Páginas", newTab: "(nueva pestaña)",
      foot: "No escriba datos personales como nombres o teléfonos. Las conversaciones solo quedan en esta pestaña, y las preguntas se envían a Anthropic para responder.",
      kinds: { place: "Lugar", guide: "Guía", course: "Ruta", event: "Evento", video: "Vídeo", abroad: "Artículo", page: "Página", book: "Reservar" },
      err: { not_configured: "El asistente aún no está conectado.", rate_limited: "Demasiadas preguntas. Espere un minuto.",
        daily_limit: "Ha alcanzado el número de preguntas de hoy. Vuelva a preguntar mañana.",
        too_long: "Una pregunta puede tener hasta 800 caracteres.", busy: "Ahora no es posible responder. Inténtelo más tarde.",
        timeout: "La respuesta tardó demasiado y se detuvo.", refusal: "No se puede responder a esta pregunta.",
        truncated: "La respuesta se cortó. Haga una pregunta más concreta.", network: "Se perdió la conexión. Compruebe su conexión a internet.",
        error: "No se obtuvo respuesta." },
    },
    ru: {
      offH: "ИИ-помощник готовится к работе", offP: "Когда он будет готов, он ответит здесь по данным этого сайта.",
      title: ["Помощник в поездке: {c}", "Помощник в поездке"], note: "ИИ отвечает по данным этого сайта · проверьте перед поездкой",
      intro: "Спрашивайте о местах, еде, жилье, маршрутах и событиях — ответы берутся со страниц этого сайта, со ссылками.",
      chips: [],
      placeholder: ["Ваш вопрос о поездке", "Ваш вопрос о поездке"], label: "Вопрос", send: "Отправить", stop: "Остановить", newChat: "Новый чат", conv: "Диалог",
      close: "Закрыть", retry: "Повторить", stopped: "Ответ остановлен.", cut: "Ответ оборвался здесь.", more: "Продолжить", thinking: "Ищу…",
      you: "Вопрос", ai: "Ответ", pages: "Страницы", newTab: "(новая вкладка)",
      foot: "Не вводите личные данные, например имя или телефон. Переписка временно хранится только в этой вкладке, а вопросы отправляются в Anthropic для ответа.",
      kinds: { place: "Место", guide: "Гид", course: "Маршрут", event: "Событие", video: "Видео", abroad: "Статья", page: "Страница", book: "Забронировать" },
      err: { not_configured: "Помощник ещё не подключён.", rate_limited: "Слишком много вопросов. Подождите минуту.",
        daily_limit: "Лимит вопросов на сегодня исчерпан. Спросите снова завтра.",
        too_long: "Вопрос — не длиннее 800 символов.", busy: "Сейчас ответить нельзя. Попробуйте позже.",
        timeout: "Ответ занял слишком много времени и был остановлен.", refusal: "На этот вопрос ответить нельзя.",
        truncated: "Ответ оборвался. Задайте вопрос уже.", network: "Соединение прервано. Проверьте подключение к интернету.", error: "Не удалось получить ответ." },
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
  if (lang === "ko") T.search = SEARCH;
  (function cityWords() {   // [with the city's name, without] -> one string; the starters from the page
    var names = pageJSON("data-chat-city"), city = names[lang] || "";
    ["title", "placeholder"].forEach(function (k) {
      var v = T[k];
      if (Array.isArray(v)) T[k] = city ? v[0].replace("{c}", city) : v[1];
    });
    var chips = pageJSON("data-chat-chips")[lang];
    T.chips = Array.isArray(chips) ? chips.filter(function (q) { return typeof q === "string" && q; }) : [];
  })();
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
      return m.r === "u" ? { r: "u", t: m.t } : { r: "a", t: m.t, l: m.l || [], f: m.f || null, e: m.e || "", s: !!m.s, c: !!m.c, p: !!m.p,
        lg: m.lg || "", dr: m.dr || "", ls: m.ls || "", pq: m.pq || "" };
    });
    try { win.sessionStorage.setItem(KEY, JSON.stringify({ v: 1, open: !!state.open, msgs: msgs })); } catch (e) { storageOff = true; }
  }

  // ------------------------------------------------------------ is the assistant set up? (GET /api/chat/)
  // ready: true — it answers; false — not configured (no API key yet); null — not known yet. Only a clear answer is
  // kept for this tab (READY_MS): 200 {ready: true} or 503 {code: 'not_configured'}. No answer, or another one, is
  // taken as ready — a question then says what went wrong.
  var ready = null, readyWait = null;
  function remembered() {
    try {
      var r = JSON.parse(win.sessionStorage.getItem(READY_KEY) || "null"), age = r ? Date.now() - r.t : -1;
      if (r && typeof r.ok === "boolean" && age >= 0 && age < READY_MS) return r.ok;
    } catch (e) { /* storage off: ask again */ }
    return null;
  }
  function remember(ok) {
    try { win.sessionStorage.setItem(READY_KEY, JSON.stringify({ ok: ok, t: Date.now() })); } catch (e) { /* off */ }
  }
  function probe() {
    if (readyWait) return readyWait;
    var known = remembered();
    if (known !== null) {
      ready = known;
      readyWait = Promise.resolve(known);
      return readyWait;
    }
    readyWait = win.fetch(API, { method: "GET", headers: { Accept: "application/json" }, credentials: "same-origin", cache: "no-store" })
      .then(function (res) {
        return res.json().then(function (j) { return j; }, function () { return null; }).then(function (j) {
          var off = res.status === 503 && !!j && j.code === "not_configured";
          if (ready === null) ready = !off;   // a question answered meanwhile has already said
          if (res.ok || off) remember(ready);
          return ready;
        });
      }, function () {
        if (ready === null) ready = true;
        return ready;
      });
    return readyWait;
  }
  function probeSoon() {   // the panel waits for the answer, but not long
    return Promise.race([probe(), new Promise(function (ok) { win.setTimeout(ok, READY_WAIT); })]);
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
  // book: an official booking page (예약하기, the server's link.book = the service): GA4 booking_click with the service
  // as data-provider, and the page's language (link.hl) as hreflang, as on the site's own booking buttons
  function anchor(url, label, cls, book, hl) {
    var href = toLocal(url);
    var a = h("a", { href: href, class: cls || null, "data-track": "chat_link_click", "data-chat-where": WHERE, text: label });
    if (book) {
      a.setAttribute("data-track", "booking_click");
      a.setAttribute("data-provider", book);
      if (hl) a.setAttribute("hreflang", hl);
    }
    if (external(href)) {
      a.target = "_blank";
      a.rel = "noopener";
    }
    return a;
  }

  // ------------------------------------------------------------ answer text: paragraphs, lists, bold, links
  // An answer written right to left (Arabic, Hebrew: the server's meta event): a phone number or a date is one
  // left-to-right run of its own (else its groups come out reversed: 063-454-3303 as 3303-454-063), and a link, a
  // pending link, bold or code text takes the direction of its own first letter (dir=auto); without rtl nothing changes.
  var INLINE = /\[([^\]\n]+)\]\(\s*<?([^)\s>]+)>?\s*\)|\*\*([^*\n]+)\*\*|(https?:\/\/[^\s<>()[\]"'`]+)|`([^`\n]+)`/g;
  var LTR_RUN = /\+\d{1,3}(?:[- ]\d{1,4}){1,4}|\d{2,4}-\d{3,4}(?:-\d{4})?|\d{4}-\d{1,2}-\d{1,2}|\d{4}\.\d{1,2}\.\d{1,2}\.?/g;
  function runs(parent, s, rtl) {
    if (!rtl) {
      parent.append(s);
      return;
    }
    var at = 0, m;
    LTR_RUN.lastIndex = 0;
    while ((m = LTR_RUN.exec(s)) !== null) {
      if (m.index > at) parent.append(s.slice(at, m.index));
      parent.append(h("span", { dir: "ltr", class: "chat-num", text: m[0] }));
      at = m.index + m[0].length;
    }
    if (at < s.length) parent.append(s.slice(at));
  }
  function inline(parent, s, fix, rtl) {
    var at = 0, m;
    INLINE.lastIndex = 0;
    var parts = [];
    while ((m = INLINE.exec(s)) !== null) parts.push({ m: m, i: m.index });
    parts.forEach(function (p) {
      var x = p.m;
      if (p.i < at) return;
      if (p.i > at) runs(parent, s.slice(at, p.i), rtl);
      if (x[1] !== undefined) parent.append(link(x[1], x[2], fix, rtl));
      else if (x[3] !== undefined) {
        var b = h("strong", { dir: rtl ? "auto" : null });
        inline(b, x[3], fix, rtl);
        parent.append(b);
      } else if (x[4] !== undefined) {
        var u = x[4].replace(/[.,;:!?。、]+$/, "");
        parent.append(link(u, u, fix, rtl));
        if (u.length < x[4].length) parent.append(x[4].slice(u.length));
      } else parent.append(rtl ? h("code", { dir: "auto", text: x[5] }) : x[5]);
      at = p.i + x[0].length;
    });
    if (at < s.length) runs(parent, s.slice(at), rtl);
  }
  function link(label, raw, fix, rtl) {
    var dir = rtl ? "auto" : null;
    if (!fix) return h("span", { class: "chat-lk", dir: dir, text: label });   // still being written: not a link yet
    var url = Object.prototype.hasOwnProperty.call(fix, raw) ? fix[raw] : null;
    if (!url) return doc.createTextNode(label);
    var a = anchor(url, label);
    if (dir) a.setAttribute("dir", dir);
    if (a.target === "_blank") a.append(h("span", { class: "vh", text: " " + T.newTab }));
    return a;
  }
  function md(text, fix, rtl) {
    var wrap = h("div", { class: "chat-md" });
    var para = [], list = null, listType = "";
    function flushPara() {
      if (!para.length) return;
      var p = h("p");
      para.forEach(function (ln, i) {
        if (i) p.append(h("br"));
        inline(p, ln, fix, rtl);
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
        inline(li, (bullet || num)[1], fix, rtl);
        list.append(li);
        return;
      }
      flushList();
      if (head) {
        flushPara();
        var strong = h("strong");
        inline(strong, head[1], fix, rtl);
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
  // a card's kind, in `kinds` (the answer's language): by its path on any language version; an event opens its series
  // on the events page (/<v>/events/#anchor)
  function kindOf(l, kinds) {
    if (l.ext && l.book) {   // an official booking page: '예약하기 · island.theksa.co.kr'
      try { return kinds.book + " · " + new URL(l.url).host.replace(/^www\./, ""); } catch (e) { return kinds.book; }
    }
    if (l.ext) {
      try { return new URL(l.url).host.replace(/^www\./, ""); } catch (e) { return kinds.page; }
    }
    var p = "/", u = null;
    try {
      u = new URL(l.url, win.location.href);
      p = decodeURIComponent(u.pathname).replace(/^\/(?:en|ja|zh-hans|zh-hant|de|fr|es|ru)\//, "/");
    } catch (e) { p = "/"; }
    if (p === "/events/" && u && u.hash.length > 1) return kinds.event;
    var map = [["/places/", "place"], ["/stays/", "place"], ["/food/", "place"], ["/guides/", "guide"], ["/courses/", "course"],
      ["/events/", "event"], ["/videos/", "video"], ["/abroad/", "abroad"]];
    for (var i = 0; i < map.length; i += 1) if (p.indexOf(map[i][0]) === 0 && p !== map[i][0]) return kinds[map[i][1]];
    return kinds.page;
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
    var hello = h("div", { class: "chat-hello" }, T.chips.length ? [h("p", { text: T.intro }), chips] : [h("p", { text: T.intro })]);
    var list = h("ol", { class: "chat-msgs" });
    var off = offBlock();
    var log = h("div", { class: "chat-log" }, [hello, list, off.box]);
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
    return { panel: panel, title: title, log: log, list: list, hello: hello, live: live, input: input, send: send,
      form: form, foot: foot, btnNew: btnNew, off: off.box, offInput: off.input };
  }
  // the panel while the assistant is not set up: what is going on, and — in Korean, when the build has one — the site
  // search (a plain GET form: it works like the search page's own)
  function offBlock() {
    var kids = [h("p", { class: "chat-off-h", text: T.offH }), h("p", { text: T.search ? T.offS : T.offP })];
    var input = null;
    if (T.search) {
      input = h("input", { type: "search", id: "chat-s", name: "q", maxlength: "100", placeholder: T.offPh,
        enterkeyhint: "search", autocomplete: "off" });
      var form = h("form", { class: "chat-off-form", action: T.search, method: "get", role: "search" }, [
        h("label", { class: "vh", for: "chat-s", text: T.searchLabel }), input,
        h("button", { type: "submit", class: "chat-off-go", text: T.offGo })]);
      form.addEventListener("submit", function () {   // the results page opens without the panel over it
        state.open = false;
        save();
      });
      kids.push(form);
    }
    return { box: h("div", { class: "chat-off", "data-chat-offbox": true, hidden: true }, kids), input: input };
  }
  // not set up: the panel shows its resting block (q: a question that met 503, put in the search box), the card on a
  // dock page its resting words — focus that was in a box now hidden goes to the search box or the title
  function applyOff(q) {
    if (dockEl) offDock();
    if (!ui || ui.dock) return;
    var had = ui.form.contains(doc.activeElement);
    ui.panel.setAttribute("data-chat-off", "");
    ui.off.hidden = false;
    ui.hello.hidden = true;
    ui.form.hidden = true;
    ui.foot.hidden = true;
    ui.btnNew.hidden = !state.msgs.length;
    if (q && ui.offInput) ui.offInput.value = q;
    if (had) (ui.offInput || ui.title).focus({ preventScroll: true });
  }
  function offDock() {
    if (dockEl.hasAttribute("data-chat-off-shown")) return;
    dockEl.setAttribute("data-chat-off", "");          // site.js: the box goes to the search page, starters are links
    dockEl.setAttribute("data-chat-off-shown", "");
    var form = dockEl.querySelector("[data-ask-form]");
    var q = dockEl.querySelector("[data-ask-q]"), go = dockEl.querySelector("[data-ask-go]");
    var search = !!form && form.getAttribute("data-ask-form") === "search" && !!T.offLine;
    // the card's line on how it answers (_ask.html.j2 data-ask-line) says what is going on, read out once it changes;
    // the line keeps its place and about its length, so nothing below it moves
    Array.prototype.forEach.call(dockEl.querySelectorAll("[data-ask-line]"), function (el) {
      el.setAttribute("role", "status");
      win.setTimeout(function () { el.textContent = search ? T.offLine : T.offH; }, 60);
    });
    if (q) q.setAttribute("placeholder", search ? T.offPh : T.offH);
    if (search) {   // the box searches now: its button says so (the stop label beside it keeps the button's width)
      var label = go && go.querySelector(".ask-go-l:not(.ask-go-s)");
      if (label) label.textContent = T.offBtn;
    } else {        // nothing to search instead: the box rests
      if (q) q.readOnly = true;
      if (go) go.disabled = true;
    }
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
    var f = Array.prototype.slice.call(ui.panel.querySelectorAll("a[href], button:not([disabled]), textarea, input, [tabindex]:not([tabindex='-1'])"))
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
    return Promise.all([cssReady(), probeSoon()]).then(function () {
      view();
      render();
      if (ready === false) applyOff();
      ui.panel.hidden = false;
      root.classList.add("chat-open");
      state.open = true;
      save();
      setModal(sheetMQ.matches);
      mode(busy ? "stop" : "send");
      grow();
      var first = ready === false ? ui.offInput || ui.title : ui.input;
      if (!quiet || sheetMQ.matches) (sheetMQ.matches ? ui.title : first).focus({ preventScroll: true });
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
      if (ready === false) applyOff();
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
    if (ready === false && !ui.dock) {   // resting: nothing to clear any more, the focus to the search (or the title)
      ui.btnNew.hidden = true;
      (ui.offInput || ui.title).focus({ preventScroll: true });
      return;
    }
    ui.input.focus({ preventScroll: !ui.input2 });   // a panel of its own closes: back to the question field, in view
  }
  function stop() {
    if (ctrl) ctrl.abort();
  }

  // ------------------------------------------------------------ messages
  function render() {
    ui.list.replaceChildren();
    state.msgs.forEach(function (m) { ui.list.append(msgEl(m)); });
    ui.hello.hidden = state.msgs.length > 0 || (ready === false && !ui.dock);
  }
  function msgEl(m) {
    if (m.r === "u") {
      // the question takes the direction of its own first letter (an Arabic question on a Korean page: right to left);
      // the read-out prefix stays outside it, in the page's language
      m.el = h("li", { class: "chat-m chat-u" }, [h("span", { class: "vh", text: T.you + ": " }), h("p", { dir: "auto", text: m.t })]);
      return m.el;
    }
    m.el = h("li", { class: "chat-m chat-a" });
    fill(m);
    return m.el;
  }
  function fill(m) {
    var li = m.el;
    li.replaceChildren(h("span", { class: "vh", text: T.ai + ": " }));
    if (m.t) {
      // the answer in its own language and direction (the server's meta event); the notes and buttons around it stay
      // in the page's language
      var body = md(m.t, m.p ? null : m.f || {}, m.dr === "rtl");
      if (m.lg) body.setAttribute("lang", m.lg);
      if (m.dr === "rtl") body.setAttribute("dir", "rtl");
      li.append(body);
    }
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
    if (!m.p && m.l && m.l.length) li.append(linksEl(m.l, m));
    // the question stated trip conditions: the planner with the conversation's, under a finished answer — not one the
    // reader stopped, nor one cut that may still go on
    if (m.pq && PLAN && !m.p && !m.s && !m.c && m.t && !m.e) li.append(planEl(m.pq));
  }
  // every code the server can send (chatbot/server.js) reads as one of these, in the page's language: the knowledge or
  // the key failing is 'busy' (not the reader's doing), a body over 64KB a question too long, the rest a plain failure
  var ERR_AS = { unavailable: "busy", too_large: "too_long", empty: "error", bad_request: "error", forbidden_origin: "error",
    method_not_allowed: "error" };
  function errText(code) {
    return T.err[ERR_AS[code] || code] || T.err.error;
  }
  function errEl(m) {
    var box = h("div", { class: "chat-err" }, [h("p", { text: errText(m.e) })]);
    if (m.e === "not_configured" || m.e === "daily_limit") {   // no retry that would be refused again: the site search
      if (T.search) box.append(h("p", {}, [h("a", { href: T.search, text: T.searchLabel })]));
    } else if (m.e !== "too_long" && m.e !== "too_large" && m.e !== "refusal") {
      var b = h("button", { type: "button", class: "chat-retry", text: T.retry });
      b.addEventListener("click", function () { retry(m); });
      box.append(b);
    }
    return box;
  }
  // the cards open the pages in the answer's language (its site language, else English: meta.site) and name their kind
  // in it; an answer of an older stored conversation without one keeps the page's language
  function linksEl(links, m) {
    var kl = m && (m.ls || m.lg) ? pickLang(m.ls || m.lg) : lang;
    var kinds = Object.assign({}, STR.en.kinds, (STR[kl] || {}).kinds);
    var ul = h("ul", { class: "chat-links", "aria-label": T.pages, dir: m && m.dr === "rtl" ? "rtl" : null });
    links.forEach(function (l) {
      var a = anchor(l.url, "", "chat-card", typeof l.book === "string" ? l.book : "", typeof l.hl === "string" ? l.hl : "");
      a.append(h("span", { class: "chat-card-k", lang: kl !== lang ? kl : null, text: kindOf(l, kinds) }),
        h("span", { class: "chat-card-t", dir: m && m.dr === "rtl" ? "auto" : null, text: l.title }),
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
    var text = m.e ? errText(m.e) : plain(m.t) + (m.s ? " " + T.stopped : "");
    ui.live.textContent = "";
    ui.live.lang = !m.e && m.lg ? m.lg : lang;   // read out in the answer's language
    win.setTimeout(function () { ui.live.textContent = (T.ai + ": " + text).slice(0, 700); }, 60);
  }

  // ------------------------------------------------------------ the course planner's door under an answer
  /* plan-query: begin — pure functions; tests/js/chat.test.js reads them from between these two marks */
  // The trip conditions a Korean question clearly states, as the course planner's URL parameters (the contract
  // templates/assets/plan.js reads: date=YYYY-MM-DD & days=1..3 & start=HH:MM & end=HH:MM & move=car|transit & with=…
  // & kids=8,5 & needs=… & from=… & to=station|bus|express|airport). A conservative reader (review 2026-10-18, third
  // round): it fills only the keys below and leaves out what it is not sure of; the reader picks the rest on /plan/.
  //   date      one explicit date ('2026-10-19', '2026년 10월 19일', '10월 19일': this year's, else next year's), real,
  //             from today to the planner's last day (180 days on), and the weekday written after it (if any) that
  //             day's. Two different dates, or a bare day joined to it by 이나·또는·,·~·부터 ('10월 19일이나 20일'), are
  //             no date; so is a day said relatively (내일·모레·글피·오늘·이번 주(말)·다음 주(말)·이번·다음 달·주말에) in a
  //             question that writes no date, which clears the date an earlier question gave (review 2026-10-18, fourth
  //             round); a question that writes one keeps it ('10월 31일 주말에', '내일(10월 19일)'). 내일로 (Korail's
  //             pass) is not 내일 — unless the day is moved to it ('내일로 바꿀게요·미룰게요')
  //   days      당일치기·당일 여행/코스 1, 'N박 M일' M (1–3)
  //   start/end only a time attached to one of the city's hubs (hubPatterns of the launcher's data-chat-hubs, site.json
  //             city.plan.hubs; none: no time is read): '<time> <hub> 도착' or '<hub> <time> 도착' starts the day there
  //             (from), '<time> <hub> 출발' or '<hub>에서 <time> 출발' ends it (to) — the reader leaves the city there.
  //             오전·아침·새벽 and 오후·낮·저녁·밤 are read; a bare 1–6 o'clock is left out, and no other time is read
  //             ('5시까지 하나요?', '서울에서 8시 출발'). After the conversation is merged, as the planner's form offers
  //             them (templates/plan.html.j2: a start on the hour 07:00–14:00, an end on the hour 15:00–22:00): a start
  //             rounded up to its hour, an end down to its (the day never begins before the reader is there nor ends
  //             after they leave), else left out, and the two three hours or more apart. A later question that changes
  //             the way of moving (car to transit or back, not one that leaves it unclear) drops the hubs and times the
  //             earlier ones gave
  //   move · with=kids (and kids, the ages written as N살·N세, 0–17, not a rule's '5세 이하') · needs (rain, stroller,
  //             wheelchair, parking, lesswalk): a mention counts only in a clause (cut at . , ? ! 그리고 하지만 는데)
  //             with no negation (없이 없어 없는 필요 없 빼고 말고 안 않 못 제외); with one the key is left out ('아이
  //             없이', '유모차는 필요 없어요', '대중교통 말고 자차로'). Said 'without' in themselves: '차 없이' (자차·자가용
  //             ·렌터카 … 없이·없어) is transit, as are 뚜벅이·대중교통; '많이 못 걷는' is lesswalk. 자가용·자차·렌터카·
  //             차로 are car. A child: 아이·아기·유아·초등학생·유치원생·자녀·아들·딸·딸내미 (not 딸린·딸기·아기자기·아이스·유아차)
  // Two readings of one key (two dates, 차 없이 and 자가용, 당일치기 and 1박 2일) leave it out. `today` is Korea's date
  // (YYYY-MM-DD). planParams gives one question's keys: a value, or null where it speaks of a key but not clearly —
  // which clears what an earlier question said of it.
  // A hub's name as a pattern: any spacing between its syllables ('○○ 시외버스 터미널'); a station's '역' never the
  // start of '역사' (history)
  function hubPatterns(names) {
    var out = {};
    Object.keys(names || {}).forEach(function (k) {
      var chars = String(names[k] || "").replace(/\s+/g, "").split("");
      if (!chars.length) return;
      out[k] = chars.map(function (c) { return c.replace(/[.*+?^${}()|[\]\\]/g, "\\$&"); }).join("\\s*")
        + (chars[chars.length - 1] === "역" ? "(?!사)" : "");
    });
    return out;
  }
  function planParams(q, today, hubs) {
    var s = String(q || "").replace(/\s+/g, " "), said = {}, m, i;
    var put = function (key, v) { said[key] = key in said && said[key] !== v ? null : v; };
    var pad = function (n) { return (n < 10 ? "0" : "") + n; };
    var iso = function (y, mo, d) {
      var t = new Date(Date.UTC(y, mo - 1, d));
      return t.getUTCFullYear() === y && t.getUTCMonth() === mo - 1 && t.getUTCDate() === d ? y + "-" + pad(mo) + "-" + pad(d) : "";
    };
    // the date: up to the planner's last day (plan.js: 180 days on); a relative day is none — only where the question
    // writes no date ('10월 31일 주말에', '내일(10월 19일)' are that date); 내일로 is Korail's pass, not tomorrow, unless
    // the day is moved to it
    var t0 = today.split("-"), last = new Date(Date.UTC(+t0[0], +t0[1] - 1, +t0[2] + 180)).toISOString().slice(0, 10);
    var dated = false;
    var drx = /(?:(20\d{2})\s*년\s*)?(\d{1,2})\s*월\s*(\d{1,2})\s*일|(20\d{2})[-./](\d{1,2})[-./](\d{1,2})(?!\d)/g;
    while ((m = drx.exec(s)) !== null) {
      dated = true;
      var year = m[1] || m[4], mo = +(m[2] || m[5]), d = +(m[3] || m[6]);
      var date = iso(+(year || today.slice(0, 4)), mo, d);
      if (date && date < today && !year) date = iso(+today.slice(0, 4) + 1, mo, d);
      var after = s.slice(m.index + m[0].length);
      var w = /^\s*(?:\(\s*([일월화수목금토])(?:요일)?\s*\)|([일월화수목금토])요일)/.exec(after);
      if (w && date && "일월화수목금토".indexOf(w[1] || w[2]) !== new Date(date + "T12:00:00Z").getUTCDay()) date = "";
      if (/^\s*(?:\([^)]*\)\s*|[일월화수목금토]요일\s*)?(?:이나|또는|,|~|∼|～|-|부터)\s*\d{1,2}\s*일/.test(after)) date = "";
      put("date", date && date >= today && date <= last ? date : null);
    }
    if (!dated && /내일(?!로(?!\s*(?:바꾸|바꿀|바꿔|바꾼|미루|미룰|미뤄|미룬|옮기|옮길|옮겨|옮긴|변경|당기|당길|당겨|당긴)))|모레|글피|오늘(?!날)|주말에|(?:이번|다음)\s*(?:주말?|달)(?=$|[^가-힣]|[에엔은는도쯤부까중이로])/.test(s)) put("date", null);
    // how many days
    if (/당일(?:치기|\s*(?:여행|코스|일정|나들이|투어)|로)/.test(s)) put("days", 1);
    var nrx = /(\d{1,2})\s*박\s*(\d{1,2})\s*일/g;
    while ((m = nrx.exec(s)) !== null) put("days", +m[2] >= 1 && +m[2] <= 3 ? +m[2] : null);
    // the day's start and end: an arrival at one of the city's hubs starts it there, a departure from one ends it there
    var T = "(?:(오전|오후|아침|낮|저녁|밤|새벽)(?:\\s*에)?\\s*)?(\\d{1,2})(?:\\s*시(?!간)(?:\\s*(\\d{1,2})\\s*분|\\s*(반))?|:([0-5]\\d))";
    var AT = "(?:\\s*(?:쯤|경))?(?:\\s*에)?\\s*";
    var HUBS = hubs || {};
    var clock = function (x) {   // the minutes of a time T matched, or null when its hour is not sure
      var ap = x[1] || "", h = +x[2], min = x[3] ? +x[3] : x[4] ? 30 : x[5] ? +x[5] : 0;
      if (/오전|아침|새벽/.test(ap)) h = h <= 11 ? h : -1;
      else if (ap === "낮") h = h === 12 || h === 10 || h === 11 ? h : h >= 1 && h <= 5 ? h + 12 : -1;
      else if (ap === "오후") h = h === 12 ? 12 : h >= 1 && h <= 11 ? h + 12 : -1;
      else if (ap) h = h >= 1 && h <= 11 ? h + 12 : -1;   // 저녁·밤: 12시 is midnight
      else if (h <= 6) h = -1;   // a bare 1–6 o'clock: the morning or the afternoon
      if (ap === "밤" && h >= 0 && h < 18) h = -1;   // 밤 1–5시 and 밤 12시 are the small hours
      return h >= 0 && h <= 23 && min <= 59 ? h * 60 + min : null;
    };
    Object.keys(HUBS).forEach(function (hub) {
      var H = HUBS[hub];
      // '오후 5시까지 <station>에 도착' is when the reader must be back at the hub: the day's end there, not its start
      [[T + AT + H + "\\s*(?:에|으로|로)?\\s*도착", "start", "from"],
        [H + "\\s*(?:에\\s*)?" + T + AT + "도착", "start", "from"],
        [T + AT + "까지\\s*" + H + "\\s*(?:에|으로|로)?\\s*(?:도착|돌아)", "end", "to"],
        [H + "\\s*(?:에\\s*|으로\\s*|로\\s*)?" + T + AT + "까지\\s*(?:도착|돌아)", "end", "to"],
        [T + AT + H + "\\s*(?:에서\\s*)?출발", "end", "to"],
        [H + "\\s*(?:에서\\s*)?" + T + AT + "출발", "end", "to"]].forEach(function (x) {
        var rx = new RegExp(x[0], "g"), t;
        while ((t = rx.exec(s)) !== null) {
          put(x[1], clock(t));
          put(x[2], hub);
        }
      });
    });
    // car or not, a child, what the trip needs: each clause that mentions one, unless the clause has a negation
    var NEG = /없이|없어|없는|필요\s*없|빼고|말고|않|제외|(?:^|[^가-힣])안(?=\s|$)|(?:^|[^가-힣])못|지\s*못/;
    var NO_CAR = /(?:자가용|자차|자동차|렌터카|렌트카|(?:^|[^가-힣])차)\s*(?:[이가은는도]\s*)?없[가-힣]*/g;
    var LESS = /(?:(?:많이|오래|멀리)\s*(?:못|안)\s*(?:걷|걸(?:어|을|으|었))|걷기\s*(?:가\s*)?(?:힘|어려|불편|싫)|(?:덜|적게|조금만)\s*(?:걷|걸(?:어|을|으|었)))[가-힣]*/g;
    var CAR = /자가용|자차|렌터카|렌트카|(?:^|[^가-힣])(?:자동)?차로/;
    var KIDS = /아이(?=[와랑하들가를는도의만에()·\s\d]|$)|아기(?!자기)|유아(?!차)|초등학?생|유치원생|자녀|아들|딸(?![린려리릴렸기꾹깍랑])/;
    var NEEDS = [["rain", /(?:^|[^가-힣])비\s*(?:가\s*|도\s*)?(?:오|와|올|내리|예보|소식)|우천|장마/], ["stroller", /유모차|유아차/],
      ["wheelchair", /휠체어/], ["parking", /주차장?\s*(?:이\s*|가\s*|하기\s*)?(?:편|쉬|넉넉|여유|넓)/], ["lesswalk", LESS]];
    var clauses = String(q || "").split(/[.,?!\n]|그리고|하지만|는데/);
    for (i = 0; i < clauses.length; i += 1) {
      var c = clauses[i].replace(/\s+/g, " ");
      var no = NEG.test(c.replace(NO_CAR, " ").replace(LESS, " "));   // '차 없이', '많이 못 걷는' say no 'no'
      var transit = c.search(NO_CAR) >= 0 || /대중교통|뚜벅이/.test(c), car = CAR.test(c.replace(NO_CAR, " "));
      if (transit || car) put("move", no || (transit && car) ? null : transit ? "transit" : "car");
      if (KIDS.test(c)) put("child", no ? null : true);
      for (var n = 0; n < NEEDS.length; n += 1) if (c.search(NEEDS[n][1]) >= 0) put(NEEDS[n][0], no ? null : true);
    }
    // the children's ages, as written: '8살', '5세' (not a rule's '5세 이하', '3~12세')
    if (said.child === true) {
      var ages = [], arx = /(^|\D)(\d{1,2})\s*(?:살|세(?![기대트]))/g;
      while ((m = arx.exec(s)) !== null) {
        var at = m.index + m[1].length;
        var rule = /^\s*(?:이하|이상|미만|초과|부터|까지)/.test(s.slice(m.index + m[0].length)) || /[~∼-]\s*$/.test(s.slice(0, at));
        if (!rule && +m[2] <= 17 && ages.length < 6) ages.push(+m[2]);
      }
      if (ages.length) said.ages = ages.join(",");
    } else if (said.child === null) said.ages = null;
    return said;
  }
  // The conversation's conditions for the planner: its questions (oldest first, or one question) merged key by key, a
  // later one over the earlier ones (null clears; another way of moving drops the hubs and times said before it), then
  // the day put in the planner's form. Returns the query without '?', '' when the last question says nothing of any key.
  function planQuery(qs, today, hubs) {
    var list = [].concat(qs), p = {}, own = {}, i, k;
    for (i = 0; i < list.length; i += 1) {
      own = planParams(list[i], today, hubs);
      if (own.move && p.move && own.move !== p.move) p.from = p.to = p.start = p.end = null;
      for (k in own) if (Object.prototype.hasOwnProperty.call(own, k)) p[k] = own[k];
    }
    if (p.child !== true) p.ages = null;
    // the planner's form (templates/plan.html.j2): a start on the hour (rounded up: the reader is there by then) and an
    // end on the hour (rounded down: still there), three hours or more apart (plan.js) — else neither —, each kept only
    // where the form offers it: a start 07:00–14:00, an end 15:00–22:00
    var on = function (x) { return typeof x === "number"; };
    if (on(p.start)) p.start = Math.ceil(p.start / 60) * 60;
    if (on(p.end)) p.end = Math.floor(p.end / 60) * 60;
    if (on(p.start) && on(p.end) && p.end - p.start < 180) p.start = p.end = null;
    if (on(p.start) && (p.start < 7 * 60 || p.start > 14 * 60)) p.start = null;
    if (on(p.end) && (p.end < 15 * 60 || p.end > 22 * 60)) p.end = null;
    var pad = function (n) { return (n < 10 ? "0" : "") + n; };
    var hm = function (x) { return on(x) ? pad(Math.floor(x / 60)) + ":" + pad(x % 60) : null; };
    var needs = ["rain", "stroller", "wheelchair", "parking", "lesswalk"].filter(function (x) { return p[x] === true; });
    var out = [["date", p.date], ["days", p.days], ["start", hm(p.start)], ["end", hm(p.end)], ["move", p.move],
      ["with", p.child === true ? "kids" : null], ["kids", p.ages], ["needs", needs.join(",")], ["from", p.from], ["to", p.to]]
      .filter(function (x) { return x[1] !== null && x[1] !== undefined && x[1] !== ""; })
      .map(function (x) { return x[0] + "=" + x[1]; });
    return Object.keys(own).length && out.length ? out.join("&") : "";
  }
  /* plan-query: end */

  // the planner is on this site's Korean pages only: the header links it (base.html.j2, data-track="plan_cta") when
  // the site has it — then a Korean question that states trip conditions gets the door under its answer
  var planNav = lang === "ko" ? doc.querySelector('a[data-track="plan_cta"][href]') : null;
  var PLAN = planNav ? planNav.getAttribute("href").split(/[?#]/)[0] : "";
  var PLAN_HUBS = hubPatterns(pageJSON("data-chat-hubs"));   // the city's start and end points (site.json city.plan.hubs)
  function seoulToday() {
    try {
      return new Intl.DateTimeFormat("en-CA", { timeZone: "Asia/Seoul", year: "numeric", month: "2-digit", day: "2-digit" }).format(new Date());
    } catch (e) {
      return new Date(Date.now() + 9 * 3600000).toISOString().slice(0, 10);
    }
  }
  function planEl(pq) {
    return h("p", { class: "chat-plan-w" }, [h("a", { href: PLAN + "?" + pq, class: "chat-plan", "data-track": "plan_cta",
      "data-chat-where": WHERE }, [h("span", { text: T.plan }), svg("arrow")])]);
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
    var keep = SEND_PRIOR + (more ? 2 : 1), sent = msgs.slice(-keep);
    // a long conversation: its first question and answer go along in place of the oldest two of the rest — the trip's
    // conditions (date, people and ages, car or not, budget, a wheelchair or a pram) are usually set there
    if (msgs.length > keep && msgs[0].role === "user" && msgs[1].role === "assistant") sent = msgs.slice(0, 2).concat(msgs.slice(-(keep - 2)));
    var body = { messages: sent, lang: lang, page: win.location.pathname };
    if (more) body["continue"] = true;
    return body;
  }
  function ask(q) {
    q = String(q || "").trim();
    if (!q || busy) return;
    if (ready === false) {   // not set up: the Korean search with the question, else the resting view
      if (T.search) win.location.assign(T.search + "?q=" + encodeURIComponent(q));
      else applyOff();
      return;
    }
    if (Array.from(q).length > MAX_Q) {
      flashErr("too_long");
      return;
    }
    // the box empties when its own text was asked (a starter leaves what the reader was typing)
    [ui.input, ui.input2].forEach(function (el) { if (el && (!ui.dock || el.value.trim() === q)) el.value = ""; });
    grow();
    state.msgs.push({ r: "u", t: q });
    // the trip conditions of this question, over those its earlier questions in this conversation stated
    var asked = state.msgs.filter(function (x) { return x.r === "u"; }).map(function (x) { return x.t; });
    var m = { r: "a", t: "", p: true, st: T.thinking, l: [], f: null, e: "", pq: PLAN ? planQuery(asked, seoulToday(), PLAN_HUBS) : "" };
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
  function dropFailed(m) {
    // a question that met 503 not_configured (no API key yet) and its empty answer leave the conversation; returns the
    // question
    var i = state.msgs.indexOf(m), u = i > 0 && state.msgs[i - 1].r === "u" ? state.msgs[i - 1] : null;
    if (i >= 0) state.msgs.splice(u ? i - 1 : i, u ? 2 : 1);
    save();
    if (!state.msgs.length) root.classList.remove("chat-has");
    mode("send");
    render();
    return u ? u.t : "";
  }
  function toSearch(m) {
    // the Korean card while the assistant is not set up: it keeps working as the site search
    win.location.assign(T.search + "?q=" + encodeURIComponent(dropFailed(m)));
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
  // a refusal with no code of ours in it (the platform's own page): the Vercel Firewall's 429 is the minute's limit, a
  // 504 the function running out of time, any other 5xx the service being down for now — never 'not configured', which
  // the function always says in JSON (else the home's card would turn into the search for the rest of the page)
  function httpCode(status) {
    if (status === 429) return "rate_limited";
    if (status === 413) return "too_long";
    if (status === 504) return "timeout";
    if (status >= 500) return "busy";
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
        if (m.e === "not_configured") {   // the key is not (or no longer) there: the resting view from now on
          ready = false;
          remember(false);
          if (ui && ui.dock) {   // the card: its starters go back to being links (site.js), in Korean to the search
            if (T.search) {
              dockEl.setAttribute("data-chat-off", "");
              toSearch(m);
              return;
            }
            applyOff();
          } else if (ui) {
            applyOff(dropFailed(m));
            announce({ e: "not_configured" });
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
    if (ev.type === "meta") {   // the answer's language (when the server is sure of it), direction and link language
      m.lg = typeof ev.lang === "string" && /^[A-Za-z]{2,3}(?:-[A-Za-z]{4})?$/.test(ev.lang) ? ev.lang : "";
      m.dr = ev.dir === "rtl" ? "rtl" : "";
      m.ls = typeof ev.site === "string" && /^[A-Za-z]{2}(?:-[A-Za-z]{4})?$/.test(ev.site) ? ev.site : "";
    } else if (ev.type === "status") {
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
      // an answer in another language: a link the model labelled with a Korean page title takes the name its checked
      // card has in that language (the card list is in the answer's language: meta.site)
      if (m.ls && m.ls !== "ko") {
        m.t = m.t.replace(/\[([^\]]*[가-힣][^\]]*)\]\(([^)\s]+)\)/g, function (all, label, raw) {
          var u = Object.prototype.hasOwnProperty.call(m.f, raw) ? m.f[raw] : null;
          var l = u && (m.l || []).filter(function (x) { return x.url === u; })[0];
          return l && l.title && !/[가-힣]/.test(l.title) ? "[" + l.title + "](" + raw + ")" : all;
        });
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
    // a question from outside (site.js: the centre card's box and starters; a [data-chat-open][data-chat-q] button,
    // `from`, which gets the focus back when the panel closes): in the card on a dock page — its box is shown at once,
    // inside the caller's input event — else in the panel
    ask: function (q, from) {
      if (!dockEl) return open(from || null, false).then(function () { ask(q); });
      showDock();
      return cssReady().then(function () {
        view();
        ask(q);
      });
    },
    stop: stop,
    busy: function () { return busy; },
    ready: function () { return ready; },
    dock: !!dockEl,
  };
  // asked once, now: the module loads only when the reader turns to the assistant
  probe().then(function (ok) { if (ok === false) applyOff(); });
})();
