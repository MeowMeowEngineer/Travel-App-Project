// Vercel Node.js function at /api/chat/ (vercel.json: functions."api/chat.js" — includeFiles public/chat/**,
// maxDuration, supportsCancellation). The handler and everything it uses live in chatbot/ (server.js: limits, the
// answer loop, SSE; knowledge.js: the site data and the two tools; prompt.js: rules, tools, model). The key is the
// environment variable ANTHROPIC_API_KEY (Vercel Settings → Environment Variables); without it the function answers
// 503 {code: "not_configured"}. See docs/handover/chatbot.md.
import { createHandler } from "../chatbot/server.js";

const handle = createHandler();

export default {
  fetch(request) {
    return handle(request);
  },
};
