// A fake Anthropic client for the site assistant's tests: it replays scripted stream events the way the SDK's
// client.messages.stream() yields them, and records every request. No network, no key. (Not a test file itself:
// node --test runs tests/js/*.test.js.)
export const usage = { input_tokens: 120, output_tokens: 30, cache_read_input_tokens: 0, cache_creation_input_tokens: 0 };

/** One model turn that writes `text` (after an empty thinking block, as Haiku 5.5 streams by default). */
export function textRound(text, stop = "end_turn") {
  const chunks = text.match(/[\s\S]{1,9}/g) || [];
  return {
    events: [
      { type: "message_start", message: { usage } },
      { type: "content_block_start", index: 0, content_block: { type: "thinking", thinking: "", signature: "" } },
      { type: "content_block_stop", index: 0 },
      { type: "content_block_start", index: 1, content_block: { type: "text", text: "" } },
      ...chunks.map((c) => ({ type: "content_block_delta", index: 1, delta: { type: "text_delta", text: c } })),
      { type: "content_block_stop", index: 1 },
      { type: "message_delta", delta: { stop_reason: stop } },
    ],
    message: { role: "assistant", content: [{ type: "thinking", thinking: "", signature: "s" }, { type: "text", text }],
      stop_reason: stop, usage },
  };
}

/** One model turn that calls tools: uses = [[name, input], …]. */
export function toolRound(uses, stop = "tool_use") {
  const content = [{ type: "thinking", thinking: "", signature: "s" }];
  const events = [{ type: "message_start", message: { usage } }];
  uses.forEach(([name, input], i) => {
    const id = `toolu_${i}_${name}`;
    content.push({ type: "tool_use", id, name, input });
    events.push({ type: "content_block_start", index: i + 1, content_block: { type: "tool_use", id, name, input: {} } });
    events.push({ type: "content_block_delta", index: i + 1, delta: { type: "input_json_delta", partial_json: JSON.stringify(input) } });
    events.push({ type: "content_block_stop", index: i + 1 });
  });
  events.push({ type: "message_delta", delta: { stop_reason: stop } });
  return { events, message: { role: "assistant", content, stop_reason: stop, usage } };
}

/** A client whose n-th messages.stream() call replays rounds[n] (or throws round.reject). */
export function fakeClient(rounds) {
  const calls = [];
  return {
    calls,
    messages: {
      stream(params, opts) {
        calls.push({ params: structuredClone(params), opts });
        const r = rounds[calls.length - 1];
        if (!r) throw new Error(`no scripted round ${calls.length}`);
        if (r.reject) throw r.reject;
        return {
          abort() {},
          async *[Symbol.asyncIterator]() {
            for (const ev of r.events || []) {
              if (opts?.signal?.aborted) throw Object.assign(new Error("Request was aborted."), { name: "APIUserAbortError" });
              await new Promise((res) => setTimeout(res, 0));
              yield ev;
            }
          },
          async finalMessage() {
            return r.message;
          },
        };
      },
    },
  };
}

/** The SSE body of a response as a list of events. */
export async function sseEvents(res) {
  const text = await res.text();
  return text.split("\n\n").filter(Boolean).map((block) => {
    if (!block.startsWith("data: ")) throw new Error(`not an SSE data block: ${block.slice(0, 80)}`);
    return JSON.parse(block.slice(6));
  });
}
