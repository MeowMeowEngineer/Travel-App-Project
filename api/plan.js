// Vercel Node.js function at /api/plan/ (vercel.json: functions."api/plan.js" — includeFiles public/chat/**,
// maxDuration, supportsCancellation): the AI course planner of /plan/ (chatbot/planner.js, operator 2026-10-17). It
// reads the same knowledge as the assistant and uses the same key, ANTHROPIC_API_KEY; without it the function answers
// 503 {code: "not_configured"}. See docs/handover/planner.md.
import { createPlanHandler } from "../chatbot/planner.js";

const handle = createPlanHandler();

export default {
  fetch(request) {
    return handle(request);
  },
};
