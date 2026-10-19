// Vercel Node.js function at /api/chat/ (vercel.json: functions."api/chat.js" — includeFiles public/chat/**,
// maxDuration, supportsCancellation). The handler and everything it uses live in chatbot/ (server.js: limits, the
// answer loop, SSE, GET status; knowledge.js: the site data and the two tools; prompt.js: rules, tools, model
// claude-haiku-5-5; site.js: the site it answers for, from public/chat/site.json). The key is the environment
// variable ANTHROPIC_API_KEY only (Vercel Settings → Environment Variables, then redeploy); without it GET and POST
// answer 503 {code: "not_configured"} and the pages show 'AI 도우미 준비 중' with the site search. README '사이트 도우미'.
import { createHandler } from "../chatbot/server.js";

const handle = createHandler();

export default {
  fetch(request) {
    return handle(request);
  },
};
