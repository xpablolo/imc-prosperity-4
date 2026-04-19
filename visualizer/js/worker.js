import { buildStrategy, parseActivitiesCsv, parseAnyInputText } from "./parser.js";

self.addEventListener("message", (ev) => {
  const msg = ev.data;
  if (!msg || msg.type !== "parse") return;
  const { reqId, text, meta } = msg;
  try {
    const post = (pct, message) =>
      self.postMessage({ type: "progress", reqId, pct, message });
    post(5, "Detecting format…");
    const raw = parseAnyInputText(text);
    post(25, "Parsing market data…");
    const rows = parseActivitiesCsv(raw.activitiesLog);
    post(60, "Computing series & metrics…");
    const strategy = buildStrategy(raw, rows, meta);
    post(95, "Finalizing…");
    self.postMessage({ type: "done", reqId, strategy });
  } catch (e) {
    self.postMessage({
      type: "error",
      reqId,
      error: e instanceof Error ? e.message : String(e),
    });
  }
});
