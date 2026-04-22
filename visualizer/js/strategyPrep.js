import { buildLimits } from "./positionLimits.js";
import { computeSummary, decodeLambdaLog } from "./parser.js";
import { computeDrawdown, deriveStrategyAnalytics } from "./analysis.js";

export function prepareStrategy(strategy) {
  if (!strategy) return strategy;

  strategy.products = Array.isArray(strategy.products)
    ? strategy.products
    : Object.keys(strategy.series ?? {}).sort();
  strategy.series = strategy.series ?? {};
  strategy.timestamps = Array.isArray(strategy.timestamps) ? strategy.timestamps : [];
  strategy.rawTimestamps = Array.isArray(strategy.rawTimestamps)
    ? strategy.rawTimestamps
    : [...strategy.timestamps];
  strategy.days = Array.isArray(strategy.days)
    ? strategy.days
    : new Array(strategy.timestamps.length).fill(0);
  strategy.rawLogs = Array.isArray(strategy.rawLogs) ? strategy.rawLogs : [];
  strategy.ownFills = Array.isArray(strategy.ownFills) ? strategy.ownFills : [];
  strategy.trades = Array.isArray(strategy.trades) ? strategy.trades : [];
  strategy.logIndexByTick = strategy.logIndexByTick ?? {};
  strategy.warnings = Array.isArray(strategy.warnings) ? strategy.warnings : [];
  strategy.positionLimits = strategy.positionLimits ?? buildLimits(strategy.products);

  for (const product of strategy.products) {
    const s = strategy.series[product] ?? (strategy.series[product] = {});
    s.product = product;
    s.timestamps = Array.isArray(s.timestamps) ? s.timestamps : strategy.timestamps;
    s.midPrice = ensureArray(s.midPrice, strategy.timestamps.length, NaN);
    s.microPrice = ensureArray(s.microPrice, strategy.timestamps.length, NaN);
    s.wallMid = ensureArray(s.wallMid, strategy.timestamps.length, NaN);
    s.spread = ensureArray(s.spread, strategy.timestamps.length, NaN);
    s.bestBid = ensureArray(s.bestBid, strategy.timestamps.length, NaN);
    s.bestAsk = ensureArray(s.bestAsk, strategy.timestamps.length, NaN);
    s.bidVol = ensureArray(s.bidVol, strategy.timestamps.length, NaN);
    s.askVol = ensureArray(s.askVol, strategy.timestamps.length, NaN);
    s.imbalance = ensureArray(s.imbalance, strategy.timestamps.length, NaN);
    s.pnl = forwardFill(ensureArray(s.pnl, strategy.timestamps.length, NaN));
    s.position = ensureArray(s.position, strategy.timestamps.length, 0);
    s.cumOwnVolume = ensureArray(s.cumOwnVolume, strategy.timestamps.length, 0);
    s.books = ensureArray(s.books, strategy.timestamps.length, { bids: [], asks: [] });
    s.ownFillIndices = ensureArray(s.ownFillIndices, strategy.timestamps.length, []);
    s.bidPrices = normalizeLevelArrays(s.bidPrices, strategy.timestamps.length);
    s.askPrices = normalizeLevelArrays(s.askPrices, strategy.timestamps.length);
  }

  if (!Array.isArray(strategy.totalPnl) || strategy.totalPnl.length !== strategy.timestamps.length) {
    strategy.totalPnl = computeTotalPnl(strategy);
  } else {
    strategy.totalPnl = strategy.totalPnl.map((v) => (Number.isFinite(v) ? v : 0));
  }

  strategy.drawdown = computeDrawdown(strategy.totalPnl);
  strategy.drawdownByProduct = Object.fromEntries(
    strategy.products.map((product) => [
      product,
      computeDrawdown(forwardFill(strategy.series[product]?.pnl ?? [])),
    ])
  );

  if (!strategy.summary) {
    strategy.summary = computeSummary(
      strategy.totalPnl,
      strategy.series,
      strategy.ownFills,
      strategy.products
    );
  }

  strategy.events = buildEvents(strategy);
  strategy.analysis = deriveStrategyAnalytics(strategy);
  return strategy;
}

function ensureArray(value, length, fallback) {
  if (!Array.isArray(value)) {
    return Array.from({ length }, () => cloneFallback(fallback));
  }
  if (value.length === length) return value;
  const out = value.slice(0, length);
  while (out.length < length) out.push(cloneFallback(fallback));
  return out;
}

function cloneFallback(fallback) {
  if (Array.isArray(fallback)) return [];
  if (fallback && typeof fallback === "object") return { ...fallback };
  return fallback;
}

function normalizeLevelArrays(levels, length) {
  const src = Array.isArray(levels) ? levels : [];
  const out = [];
  for (let i = 0; i < 3; i++) out.push(ensureArray(src[i], length, NaN));
  return out;
}

function forwardFill(values) {
  const out = new Array(values.length);
  let last = 0;
  for (let i = 0; i < values.length; i++) {
    if (Number.isFinite(values[i])) last = values[i];
    out[i] = last;
  }
  return out;
}

function computeTotalPnl(strategy) {
  const total = new Array(strategy.timestamps.length).fill(0);
  for (const product of strategy.products) {
    const arr = forwardFill(strategy.series[product]?.pnl ?? []);
    strategy.series[product].pnl = arr;
    for (let i = 0; i < total.length; i++) total[i] += arr[i] ?? 0;
  }
  return total;
}

function buildEvents(strategy) {
  const events = [];
  let nextId = 1;

  for (const warning of strategy.warnings ?? []) {
    events.push({
      id: `warn-${nextId++}`,
      type: "warning",
      timestamp: strategy.rawTimestamps[0] ?? 0,
      day: strategy.days[0] ?? 0,
      tickKey: strategy.timestamps[0] ?? 0,
      product: null,
      side: null,
      price: null,
      quantity: null,
      detail: warning,
      raw: warning,
    });
  }

  for (const fill of strategy.ownFills ?? []) {
    events.push({
      id: `fill-${nextId++}`,
      type: "fill",
      timestamp: fill.timestamp,
      day: fill.day ?? 0,
      tickKey: fill.tickKey ?? fill.timestamp,
      product: fill.product ?? null,
      side: fill.side ?? null,
      price: fill.price ?? null,
      quantity: fill.quantity ?? null,
      detail: [
        fill.side ? fill.side.toUpperCase() : null,
        fill.product,
        Number.isFinite(fill.price) ? `@ ${fill.price}` : null,
        Number.isFinite(fill.quantity) ? `qty ${fill.quantity}` : null,
        fill.source ? `· ${fill.source}` : null,
      ]
        .filter(Boolean)
        .join(" "),
      raw: fill.source ?? "",
    });
  }

  for (const trade of strategy.trades ?? []) {
    const isOwn = trade.buyer === "SUBMISSION" || trade.seller === "SUBMISSION";
    if (isOwn) continue;
    events.push({
      id: `trade-${nextId++}`,
      type: "trade",
      timestamp: trade.timestamp,
      day: trade.day ?? 0,
      tickKey: trade.tickKey ?? trade.timestamp,
      product: trade.symbol ?? null,
      side: null,
      price: trade.price ?? null,
      quantity: trade.quantity ?? null,
      detail: `Market trade ${trade.symbol ?? ""}`.trim(),
      raw: "",
    });
  }

  const logs = strategy.rawLogs ?? [];
  for (let i = 0; i < logs.length; i++) {
    const entry = logs[i] ?? {};
    const timestamp = entry.timestamp ?? strategy.rawTimestamps[i] ?? 0;
    const day = strategy.days[i] ?? 0;
    const tickKey = strategy.timestamps[i] ?? timestamp;
    const sandbox = typeof entry.sandboxLog === "string" ? entry.sandboxLog.trim() : "";
    const lambda = typeof entry.lambdaLog === "string" ? entry.lambdaLog.trim() : "";

    if (sandbox) {
      events.push({
        id: `sandbox-${nextId++}`,
        type: "sandbox",
        timestamp,
        day,
        tickKey,
        product: null,
        side: null,
        price: null,
        quantity: null,
        detail: firstLine(sandbox),
        raw: sandbox,
      });
    }
    if (lambda) {
      events.push({
        id: `algo-${nextId++}`,
        type: "algorithm",
        timestamp,
        day,
        tickKey,
        product: null,
        side: null,
        price: null,
        quantity: null,
        detail: firstLine(lambda),
        raw: lambda,
      });
      const decoded = decodeLambdaLog(lambda);
      if (decoded?.ok && decoded.orders && Object.keys(decoded.orders).length > 0) {
        events.push({
          id: `order-${nextId++}`,
          type: "order",
          timestamp,
          day,
          tickKey,
          product: null,
          side: null,
          price: null,
          quantity: null,
          detail: `Orders emitted in ${Object.keys(decoded.orders).length} product(s)`,
          raw: JSON.stringify(decoded.orders, null, 2),
        });
      }
    }
  }

  events.sort((a, b) => (a.tickKey ?? 0) - (b.tickKey ?? 0) || a.id.localeCompare(b.id));
  return events;
}

function firstLine(text) {
  const line = String(text).split(/\r?\n/, 1)[0].trim();
  return line.length > 140 ? line.slice(0, 137) + "…" : line;
}
