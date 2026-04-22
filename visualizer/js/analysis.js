import { decodeLambdaLog } from "./parser.js";

export const MARKOUT_HORIZONS = [1, 5, 10];
const EPS = 1e-9;

export function computeDrawdown(values) {
  let peak = -Infinity;
  return (values ?? []).map((value) => {
    if (value > peak) peak = value;
    return Math.min(0, value - peak);
  });
}

export function deriveStrategyAnalytics(strategy) {
  if (!strategy) return null;
  const tickIndexByKey = new Map(
    (strategy.timestamps ?? []).map((tickKey, idx) => [tickKey, idx])
  );
  const productStats = buildProductStats(strategy);
  const fills = buildDetailedFills(strategy, tickIndexByKey, productStats);
  const observedOrders = extractObservedOrders(strategy, tickIndexByKey, productStats);
  const lifecycle = buildOrderLifecycle(strategy, fills, observedOrders);
  const closedTrades = buildClosedTrades(fills);
  const pnlBreakdown = buildPnlBreakdown(strategy, fills, closedTrades, lifecycle, productStats);
  const execution = buildExecutionMetrics(fills, lifecycle, closedTrades);
  const diagnostics = buildDiagnostics(strategy, fills, closedTrades, pnlBreakdown, execution, productStats);

  return {
    version: 2,
    productStats,
    fills,
    observedOrders,
    lifecycle,
    closedTrades,
    pnlBreakdown,
    execution,
    diagnostics,
    insights: buildInsightCards({ strategy, fills, lifecycle, pnlBreakdown, execution, diagnostics }),
    metadata: {
      fillCount: fills.length,
      observedOrderCount: observedOrders.length,
      lifecycleMode: observedOrders.length > 0 ? "observed+inferred" : "inferred-only",
    },
  };
}

export function computeWindowStats(strategy, options = {}) {
  if (!strategy) return null;
  const analysis = strategy.analysis ?? deriveStrategyAnalytics(strategy);
  const startIdx = clampIndex(options.startIdx ?? 0, strategy.timestamps?.length ?? 0);
  const endIdx = clampIndex(
    options.endIdx ?? (strategy.timestamps?.length ?? 1) - 1,
    strategy.timestamps?.length ?? 0
  );
  const lo = Math.min(startIdx, endIdx);
  const hi = Math.max(startIdx, endIdx);
  const totalPnl = strategy.totalPnl ?? [];
  const pnlStart = totalPnl[lo - 1] ?? 0;
  const pnlEnd = totalPnl[hi] ?? totalPnl[totalPnl.length - 1] ?? 0;
  const pnlSeries = totalPnl.slice(lo, hi + 1).map((value) => value - pnlStart);
  const drawdown = computeDrawdown(pnlSeries);
  const fills = (analysis?.fills ?? []).filter((fill) => fill.tickIdx >= lo && fill.tickIdx <= hi);
  const lifecycle = (analysis?.lifecycle?.orders ?? []).filter(
    (order) => order.endTickIdx >= lo && order.startTickIdx <= hi
  );
  const closedTrades = (analysis?.closedTrades ?? []).filter(
    (trade) => trade.exitTickIdx >= lo && trade.entryTickIdx <= hi
  );

  const byProduct = {};
  for (const product of strategy.products ?? []) {
    const pnl = strategy.series?.[product]?.pnl ?? [];
    const start = pnl[lo - 1] ?? 0;
    const end = pnl[hi] ?? pnl[pnl.length - 1] ?? 0;
    byProduct[product] = {
      pnlDelta: end - start,
      maxAbsPosition: maxAbs((strategy.series?.[product]?.position ?? []).slice(lo, hi + 1)),
      fillQty: sum(fills.filter((fill) => fill.product === product).map((fill) => fill.quantity)),
      fills: fills.filter((fill) => fill.product === product).length,
    };
  }

  const fillMetrics = aggregateFillMetrics(fills);
  const tradePnls = closedTrades.map((trade) => trade.pnl);
  const firstFillByProductSide = {};
  for (const fill of fills) {
    const key = `${fill.product}:${fill.side}`;
    const ts = fill.timestamp ?? 0;
    if (!firstFillByProductSide[key] || ts < firstFillByProductSide[key]) {
      firstFillByProductSide[key] = ts;
    }
  }

  return {
    startIdx: lo,
    endIdx: hi,
    startTickKey: strategy.timestamps?.[lo] ?? 0,
    endTickKey: strategy.timestamps?.[hi] ?? 0,
    startRawTs: strategy.rawTimestamps?.[lo] ?? 0,
    endRawTs: strategy.rawTimestamps?.[hi] ?? 0,
    pnlDelta: pnlEnd - pnlStart,
    maxDrawdown: Math.abs(Math.min(...drawdown, 0)),
    fillCount: fills.length,
    tradeCount: closedTrades.length,
    hitRate: ratio(closedTrades.filter((trade) => trade.pnl > 0).length, closedTrades.length),
    expectancy: mean(tradePnls),
    passiveFillPct: fillMetrics.passiveFillPct,
    aggressiveFillPct: fillMetrics.aggressiveFillPct,
    averageMarkout5: fillMetrics.averageMarkout?.[5] ?? NaN,
    averageShortfall: fillMetrics.averageShortfall,
    maxAbsInventory: maxObjectValue(byProduct, (row) => row.maxAbsPosition),
    byProduct,
    firstFillByProductSide,
  };
}

export function compareStrategies(reference, other, options = {}) {
  if (!reference || !other) return null;
  const refWindow = computeWindowStats(reference, options);
  const otherWindow = computeWindowStats(other, options);
  const refAnalysis = reference.analysis ?? deriveStrategyAnalytics(reference);
  const otherAnalysis = other.analysis ?? deriveStrategyAnalytics(other);

  const metrics = [
    metricDelta("PnL", refWindow?.pnlDelta, otherWindow?.pnlDelta, true),
    metricDelta("Max drawdown", refWindow?.maxDrawdown, otherWindow?.maxDrawdown, false),
    metricDelta("Passive fill %", refWindow?.passiveFillPct, otherWindow?.passiveFillPct, true),
    metricDelta("Aggressive fill %", refWindow?.aggressiveFillPct, otherWindow?.aggressiveFillPct, false),
    metricDelta("Avg markout (5)", refWindow?.averageMarkout5, otherWindow?.averageMarkout5, true),
    metricDelta("Shortfall", refWindow?.averageShortfall, otherWindow?.averageShortfall, false),
    metricDelta(
      "Fragility score",
      refAnalysis?.diagnostics?.scores?.fragility ?? NaN,
      otherAnalysis?.diagnostics?.scores?.fragility ?? NaN,
      false
    ),
    metricDelta(
      "Consistency score",
      refAnalysis?.diagnostics?.scores?.consistency ?? NaN,
      otherAnalysis?.diagnostics?.scores?.consistency ?? NaN,
      true
    ),
    metricDelta(
      "Max |inventory|",
      refAnalysis?.diagnostics?.inventory?.maxAbs ?? NaN,
      otherAnalysis?.diagnostics?.inventory?.maxAbs ?? NaN,
      false
    ),
  ].filter(Boolean);

  const productNames = Array.from(new Set([...(reference.products ?? []), ...(other.products ?? [])])).sort();
  const byProduct = productNames.map((product) => {
    const refRow = refWindow?.byProduct?.[product] ?? { pnlDelta: NaN, maxAbsPosition: NaN, fills: 0, fillQty: 0 };
    const otherRow = otherWindow?.byProduct?.[product] ?? { pnlDelta: NaN, maxAbsPosition: NaN, fills: 0, fillQty: 0 };
    return {
      product,
      ref: refRow,
      other: otherRow,
      pnlGap: diff(refRow.pnlDelta, otherRow.pnlDelta),
      fillsGap: diff(refRow.fills, otherRow.fills),
      inventoryGap: diff(refRow.maxAbsPosition, otherRow.maxAbsPosition),
    };
  });

  const leadLag = [];
  const allLeadKeys = Array.from(
    new Set([
      ...Object.keys(refWindow?.firstFillByProductSide ?? {}),
      ...Object.keys(otherWindow?.firstFillByProductSide ?? {}),
    ])
  ).sort();
  for (const key of allLeadKeys) {
    const refTs = refWindow?.firstFillByProductSide?.[key];
    const otherTs = otherWindow?.firstFillByProductSide?.[key];
    if (Number.isFinite(refTs) && Number.isFinite(otherTs) && refTs !== otherTs) {
      leadLag.push({
        key,
        refTs,
        otherTs,
        leader: refTs < otherTs ? reference.name : other.name,
        gap: Math.abs(refTs - otherTs),
      });
    }
  }

  const bullets = buildComparisonBullets(reference, other, metrics, byProduct, leadLag);

  return {
    reference: reference.name,
    other: other.name,
    window: {
      startIdx: refWindow?.startIdx ?? 0,
      endIdx: refWindow?.endIdx ?? 0,
      startRawTs: refWindow?.startRawTs ?? 0,
      endRawTs: refWindow?.endRawTs ?? 0,
    },
    metrics,
    byProduct,
    leadLag,
    bullets,
  };
}

function buildProductStats(strategy) {
  const stats = {};
  for (const product of strategy.products ?? []) {
    const series = strategy.series?.[product] ?? {};
    const fairSeries = buildFairSeries(series);
    const spreads = finiteValues(series.spread ?? []);
    const absReturns = [];
    for (let i = 1; i < fairSeries.length; i++) {
      const diffValue = fairSeries[i] - fairSeries[i - 1];
      if (Number.isFinite(diffValue)) absReturns.push(Math.abs(diffValue));
    }
    const imbalances = finiteValues(series.imbalance ?? []);
    stats[product] = {
      fairSeries,
      spreadQ25: quantile(spreads, 0.25),
      spreadMedian: quantile(spreads, 0.5),
      spreadQ75: quantile(spreads, 0.75),
      absReturnMedian: quantile(absReturns, 0.5),
      absReturnQ75: quantile(absReturns, 0.75),
      imbalanceQ25: quantile(imbalances, 0.25),
      imbalanceQ75: quantile(imbalances, 0.75),
      averageSpread: mean(spreads),
      averageImbalance: mean(imbalances),
    };
  }
  return stats;
}

function buildFairSeries(series) {
  const len = Math.max(
    series?.midPrice?.length ?? 0,
    series?.microPrice?.length ?? 0,
    series?.wallMid?.length ?? 0,
    series?.bestBid?.length ?? 0,
    series?.bestAsk?.length ?? 0
  );
  const out = new Array(len).fill(NaN);
  let last = NaN;
  for (let i = 0; i < len; i++) {
    const mid = series?.midPrice?.[i];
    const micro = series?.microPrice?.[i];
    const wallMid = series?.wallMid?.[i];
    const bestBid = series?.bestBid?.[i];
    const bestAsk = series?.bestAsk?.[i];
    let fair = firstFinite(
      mid,
      micro,
      wallMid,
      Number.isFinite(bestBid) && Number.isFinite(bestAsk) ? (bestBid + bestAsk) / 2 : NaN
    );
    if (!Number.isFinite(fair) && Number.isFinite(last)) fair = last;
    out[i] = fair;
    if (Number.isFinite(fair)) last = fair;
  }
  return out;
}

function buildDetailedFills(strategy, tickIndexByKey, productStats) {
  const fills = [...(strategy.ownFills ?? [])]
    .map((fill, index) => normalizeFill(fill, index, strategy, tickIndexByKey, productStats))
    .filter(Boolean)
    .sort((a, b) => (a.tickKey ?? 0) - (b.tickKey ?? 0) || a.index - b.index);

  return fills;
}

function normalizeFill(fill, index, strategy, tickIndexByKey, productStats) {
  const product = fill.product;
  if (!product || !strategy.series?.[product]) return null;
  const tickKey = Number.isFinite(fill.tickKey)
    ? fill.tickKey
    : compositeTickKey(fill.day, fill.timestamp);
  const tickIdx = tickIndexByKey.has(tickKey)
    ? tickIndexByKey.get(tickKey)
    : nearestTickIndex(strategy.timestamps ?? [], tickKey);
  const rawTs = fill.timestamp ?? strategy.rawTimestamps?.[tickIdx] ?? 0;
  const day = fill.day ?? strategy.days?.[tickIdx] ?? 0;
  const side = fill.side === "sell" ? "sell" : "buy";
  const sideSign = side === "buy" ? 1 : -1;
  const ps = strategy.series[product];
  const book = ps.books?.[tickIdx] ?? { bids: [], asks: [] };
  const fairSeries = productStats?.[product]?.fairSeries ?? [];
  const fair = fairSeries[tickIdx];
  const context = classifyAgainstBook(side, fill.price, book);
  const horizons = {};
  for (const horizon of MARKOUT_HORIZONS) {
    const futureFair = fairSeries[Math.min(fairSeries.length - 1, tickIdx + horizon)];
    const markout = Number.isFinite(futureFair)
      ? sideSign * (futureFair - fill.price)
      : NaN;
    horizons[horizon] = {
      futureFair,
      markout,
      realizedSpread: Number.isFinite(futureFair)
        ? 2 * sideSign * (fill.price - futureFair)
        : NaN,
    };
  }
  const arrivalRef = Number.isFinite(fair)
    ? fair
    : firstFinite(ps.microPrice?.[tickIdx], ps.wallMid?.[tickIdx], midpoint(ps.bestBid?.[tickIdx], ps.bestAsk?.[tickIdx]));
  const shortfall = Number.isFinite(arrivalRef)
    ? sideSign * (fill.price - arrivalRef)
    : NaN;
  const spreadCapture = Number.isFinite(arrivalRef)
    ? -sideSign * (fill.price - arrivalRef)
    : NaN;
  const expectedPrice = estimateExpectedPrice(side, book, context);
  const slippage = Number.isFinite(expectedPrice)
    ? sideSign * (fill.price - expectedPrice)
    : NaN;

  return {
    ...fill,
    index,
    day,
    tickKey,
    tickIdx,
    timestamp: rawTs,
    side,
    sideSign,
    arrivalRef,
    expectedPrice,
    shortfall,
    slippage,
    spreadCapture,
    context: {
      bestBid: book.bids?.[0]?.price ?? NaN,
      bestAsk: book.asks?.[0]?.price ?? NaN,
      spread: computeSpread(book.bids?.[0]?.price, book.asks?.[0]?.price),
      mid: midpoint(book.bids?.[0]?.price, book.asks?.[0]?.price),
      microprice: ps.microPrice?.[tickIdx] ?? NaN,
      wallMid: ps.wallMid?.[tickIdx] ?? NaN,
      imbalance: ps.imbalance?.[tickIdx] ?? NaN,
      bidDepth: sum(book.bids?.map((level) => level.volume) ?? []),
      askDepth: sum(book.asks?.map((level) => level.volume) ?? []),
      book,
      ...context,
    },
    horizons,
  };
}

function extractObservedOrders(strategy, tickIndexByKey, productStats) {
  const orders = [];
  const rawLogs = strategy.rawLogs ?? [];
  let nextId = 1;
  for (let i = 0; i < rawLogs.length; i++) {
    const entry = rawLogs[i] ?? {};
    const decoded = decodeLambdaLog(entry.lambdaLog ?? "");
    if (!decoded?.ok || !decoded.orders) continue;
    const timestamp = entry.timestamp ?? strategy.rawTimestamps?.[i] ?? 0;
    const day = strategy.days?.[i] ?? 0;
    const tickKey = strategy.timestamps?.[i] ?? compositeTickKey(day, timestamp);
    const tickIdx = tickIndexByKey.get(tickKey) ?? i;
    for (const [product, items] of Object.entries(decoded.orders)) {
      for (const item of normalizeObservedOrderItems(product, items)) {
        const side = item.quantity < 0 ? "sell" : "buy";
        const ps = strategy.series?.[product];
        const book = ps?.books?.[tickIdx] ?? { bids: [], asks: [] };
        orders.push({
          id: `obs-${nextId++}`,
          source: "observed",
          observed: true,
          inferred: false,
          product,
          side,
          price: item.price,
          quantity: Math.abs(item.quantity),
          timestamp,
          day,
          tickKey,
          tickIdx,
          context: classifyAgainstBook(side, item.price, book),
          fair: productStats?.[product]?.fairSeries?.[tickIdx] ?? NaN,
        });
      }
    }
  }
  return orders;
}

function normalizeObservedOrderItems(product, items) {
  if (!Array.isArray(items)) return [];
  const normalized = [];
  for (const item of items) {
    if (Array.isArray(item) && item.length >= 3) {
      normalized.push({ product: item[0] ?? product, price: Number(item[1]), quantity: Number(item[2]) });
      continue;
    }
    if (item && typeof item === "object") {
      normalized.push({
        product: item.symbol ?? item.product ?? product,
        price: Number(item.price),
        quantity: Number(item.quantity),
      });
    }
  }
  return normalized.filter((item) => item.product && Number.isFinite(item.price) && Number.isFinite(item.quantity) && item.quantity !== 0);
}

function buildOrderLifecycle(strategy, fills, observedOrders) {
  const orders = [];
  const coverage = {
    observedOrders: observedOrders.length,
    inferredOrders: 0,
    observedLifecycle: observedOrders.length > 0,
  };

  const groupedFills = groupInferredOrderEpisodes(fills);
  for (const episode of groupedFills) {
    orders.push(episode);
  }
  coverage.inferredOrders = groupedFills.length;

  // If observed order submissions exist, surface them first and attempt a loose match to fills.
  for (const order of observedOrders) {
    const matchingFills = fills.filter(
      (fill) =>
        fill.product === order.product &&
        fill.side === order.side &&
        fill.tickIdx >= order.tickIdx &&
        fill.tickIdx <= order.tickIdx + 10 &&
        almostEqual(fill.price, order.price)
    );
    const executedQty = sum(matchingFills.map((fill) => fill.quantity));
    const remainingQty = Math.max(0, order.quantity - executedQty);
    const firstFill = matchingFills[0] ?? null;
    const lastFill = matchingFills[matchingFills.length - 1] ?? null;
    orders.push({
      id: order.id,
      observed: true,
      inferred: false,
      product: order.product,
      side: order.side,
      type: order.context.mode,
      status: remainingQty <= EPS ? "filled" : executedQty > 0 ? "partially filled" : "active / cancelled?",
      statusLabel: remainingQty <= EPS ? "filled" : executedQty > 0 ? "partial" : "unfilled",
      startTimestamp: order.timestamp,
      endTimestamp: lastFill?.timestamp ?? order.timestamp,
      startTickIdx: order.tickIdx,
      endTickIdx: lastFill?.tickIdx ?? order.tickIdx,
      startTickKey: order.tickKey,
      endTickKey: lastFill?.tickKey ?? order.tickKey,
      quantity: order.quantity,
      executedQty,
      remainingQty,
      fillCount: matchingFills.length,
      vwap: weightedAverage(matchingFills, (fill) => fill.price, (fill) => fill.quantity),
      minPrice: min(matchingFills.map((fill) => fill.price)),
      maxPrice: max(matchingFills.map((fill) => fill.price)),
      lifetime: (lastFill?.timestamp ?? order.timestamp) - order.timestamp,
      crossesSpread: order.context.crossesSpread,
      bookRelation: order.context.bookRelation,
      queueAheadEstimate: order.context.queueAheadEstimate,
      queueAheadInferred: order.context.queueAheadEstimate != null,
      hadQueueEstimate: order.context.queueAheadEstimate != null,
      improving: order.context.bookRelation === "improving",
      insideSpread: order.context.bookRelation === "inside-spread",
      observedContext: true,
      exactness: {
        quantity: "observed",
        executedQty: matchingFills.length ? "observed" : "unknown",
        queueAhead: order.context.queueAheadEstimate != null ? "inferred" : "unknown",
        lifetime: matchingFills.length ? "observed-ish" : "unknown",
      },
      averageMarkout: Object.fromEntries(
        MARKOUT_HORIZONS.map((horizon) => [horizon, weightedAverage(matchingFills, (fill) => fill.horizons[horizon]?.markout, (fill) => fill.quantity)])
      ),
      fills: matchingFills.map((fill) => fill.index),
      source: "observed-order",
      summary: summarizeLifecycleContext(order.context, matchingFills[0] ?? null),
    });
  }

  orders.sort((a, b) => (a.startTickKey ?? 0) - (b.startTickKey ?? 0) || String(a.id).localeCompare(String(b.id)));
  return {
    coverage,
    orders,
  };
}

function groupInferredOrderEpisodes(fills) {
  const orders = [];
  let nextId = 1;
  const byProductSide = new Map();
  for (const fill of fills) {
    const key = `${fill.product}:${fill.side}`;
    if (!byProductSide.has(key)) byProductSide.set(key, []);
    byProductSide.get(key).push(fill);
  }

  for (const group of byProductSide.values()) {
    group.sort((a, b) => (a.tickKey ?? 0) - (b.tickKey ?? 0) || a.index - b.index);
    let current = null;
    for (const fill of group) {
      if (!current || shouldStartNewEpisode(current, fill)) {
        if (current) orders.push(finalizeInferredEpisode(current, nextId++));
        current = {
          fills: [fill],
          product: fill.product,
          side: fill.side,
        };
      } else {
        current.fills.push(fill);
      }
    }
    if (current) orders.push(finalizeInferredEpisode(current, nextId++));
  }
  return orders;
}

function shouldStartNewEpisode(current, fill) {
  const last = current.fills[current.fills.length - 1];
  if (!last) return true;
  if (fill.day !== last.day) return true;
  const tsGap = Math.abs((fill.timestamp ?? 0) - (last.timestamp ?? 0));
  if (tsGap > 500) return true;
  if (Math.abs((fill.price ?? 0) - (last.price ?? 0)) > 2) return true;
  if (fill.context.mode !== last.context.mode && tsGap > 100) return true;
  return false;
}

function finalizeInferredEpisode(current, id) {
  const fills = current.fills;
  const first = fills[0];
  const last = fills[fills.length - 1];
  const executedQty = sum(fills.map((fill) => fill.quantity));
  const vwap = weightedAverage(fills, (fill) => fill.price, (fill) => fill.quantity);
  const avgShortfall = weightedAverage(fills, (fill) => fill.shortfall, (fill) => fill.quantity);
  const avgSlippage = weightedAverage(fills, (fill) => fill.slippage, (fill) => fill.quantity);
  const type = dominantType(fills.map((fill) => fill.context.mode));
  const status = fills.length > 1 ? "filled (multi-fill)" : "filled";
  return {
    id: `inf-${id}`,
    observed: false,
    inferred: true,
    product: first.product,
    side: first.side,
    type,
    status,
    statusLabel: fills.length > 1 ? "multi-fill" : "filled",
    startTimestamp: first.timestamp,
    endTimestamp: last.timestamp,
    startTickIdx: first.tickIdx,
    endTickIdx: last.tickIdx,
    startTickKey: first.tickKey,
    endTickKey: last.tickKey,
    quantity: executedQty,
    executedQty,
    remainingQty: null,
    fillCount: fills.length,
    vwap,
    minPrice: min(fills.map((fill) => fill.price)),
    maxPrice: max(fills.map((fill) => fill.price)),
    lifetime: (last.timestamp ?? 0) - (first.timestamp ?? 0),
    crossesSpread: fills.some((fill) => fill.context.crossesSpread),
    bookRelation: first.context.bookRelation,
    queueAheadEstimate: first.context.queueAheadEstimate,
    queueAheadInferred: first.context.queueAheadEstimate != null,
    hadQueueEstimate: first.context.queueAheadEstimate != null,
    improving: first.context.bookRelation === "improving",
    insideSpread: first.context.bookRelation === "inside-spread",
    observedContext: true,
    exactness: {
      quantity: "inferred-from-fills",
      executedQty: "observed",
      queueAhead: first.context.queueAheadEstimate != null ? "inferred" : "unknown",
      lifetime: fills.length > 1 ? "observed fill span" : "unknown",
    },
    fills: fills.map((fill) => fill.index),
    avgShortfall,
    avgSlippage,
    averageMarkout: Object.fromEntries(
      MARKOUT_HORIZONS.map((horizon) => [horizon, weightedAverage(fills, (fill) => fill.horizons[horizon]?.markout, (fill) => fill.quantity)])
    ),
    source: "inferred-from-fills",
    summary: summarizeLifecycleContext(first.context, first),
  };
}

function buildClosedTrades(fills) {
  const closed = [];
  const inventory = new Map();
  let nextId = 1;

  for (const fill of fills) {
    const key = fill.product;
    const queue = inventory.get(key) ?? [];
    let qty = fill.quantity;
    while (qty > EPS && queue.length > 0 && queue[0].side !== fill.side) {
      const head = queue[0];
      const matched = Math.min(qty, head.remainingQty);
      const pnl =
        head.side === "buy"
          ? (fill.price - head.price) * matched
          : (head.price - fill.price) * matched;
      closed.push({
        id: `ct-${nextId++}`,
        product: fill.product,
        entryFillIndex: head.fillIndex,
        exitFillIndex: fill.index,
        entryTickIdx: head.tickIdx,
        exitTickIdx: fill.tickIdx,
        entryTimestamp: head.timestamp,
        exitTimestamp: fill.timestamp,
        entrySide: head.side,
        exitSide: fill.side,
        entryPrice: head.price,
        exitPrice: fill.price,
        quantity: matched,
        pnl,
        holdingTicks: fill.tickIdx - head.tickIdx,
        holdingTime: (fill.timestamp ?? 0) - (head.timestamp ?? 0),
      });
      head.remainingQty -= matched;
      qty -= matched;
      if (head.remainingQty <= EPS) queue.shift();
    }
    if (qty > EPS) {
      queue.push({
        fillIndex: fill.index,
        tickIdx: fill.tickIdx,
        timestamp: fill.timestamp,
        side: fill.side,
        price: fill.price,
        remainingQty: qty,
      });
    }
    inventory.set(key, queue);
  }

  return closed;
}

function buildPnlBreakdown(strategy, fills, closedTrades, lifecycle, productStats) {
  const overall = {
    totalPnl: strategy.summary?.totalPnl ?? last(strategy.totalPnl) ?? 0,
    realizedPnl: sum(closedTrades.map((trade) => trade.pnl)),
    unrealizedPnl: 0,
    inventoryPnlApprox: 0,
    markToMarketPnl: strategy.summary?.totalPnl ?? last(strategy.totalPnl) ?? 0,
    spreadCaptureApprox: 0,
    executionCostApprox: 0,
    adverseSelectionApprox: 0,
    bySide: { buy: { pnl: 0, qty: 0 }, sell: { pnl: 0, qty: 0 } },
  };
  const byProduct = {};
  const perFill = [];
  const fillMap = new Map(fills.map((fill) => [fill.index, fill]));

  for (const product of strategy.products ?? []) {
    const ps = strategy.series?.[product] ?? {};
    const fairSeries = productStats?.[product]?.fairSeries ?? [];
    let inventoryPnl = 0;
    const positions = ps.position ?? [];
    for (let i = 1; i < fairSeries.length; i++) {
      const prev = fairSeries[i - 1];
      const cur = fairSeries[i];
      const prevPos = positions[i - 1] ?? 0;
      if (Number.isFinite(prev) && Number.isFinite(cur) && Number.isFinite(prevPos)) {
        inventoryPnl += prevPos * (cur - prev);
      }
    }
    byProduct[product] = {
      totalPnl: strategy.summary?.perProductPnl?.[product] ?? last(ps.pnl) ?? 0,
      realizedPnl: 0,
      unrealizedPnl: 0,
      inventoryPnlApprox: inventoryPnl,
      spreadCaptureApprox: 0,
      executionCostApprox: 0,
      adverseSelectionApprox: 0,
      bySide: { buy: { qty: 0, pnl: 0 }, sell: { qty: 0, pnl: 0 } },
    };
    overall.inventoryPnlApprox += inventoryPnl;
  }

  for (const trade of closedTrades) {
    const productRow = byProduct[trade.product];
    if (!productRow) continue;
    productRow.realizedPnl += trade.pnl;
    overall.realizedPnl += 0; // already included globally; keep product rollups only.
    productRow.bySide[trade.entrySide].pnl += trade.pnl;
    overall.bySide[trade.entrySide].pnl += trade.pnl;
  }

  for (const fill of fills) {
    const productRow = byProduct[fill.product];
    const sideRow = productRow?.bySide?.[fill.side];
    const spreadCaptureTotal = Number.isFinite(fill.spreadCapture)
      ? fill.spreadCapture * fill.quantity
      : 0;
    const executionCostTotal = Number.isFinite(fill.shortfall)
      ? -fill.shortfall * fill.quantity
      : 0;
    const adverseSelectionTotal = Number.isFinite(fill.horizons[5]?.markout)
      ? Math.min(0, fill.horizons[5].markout * fill.quantity)
      : 0;

    if (productRow) {
      productRow.spreadCaptureApprox += spreadCaptureTotal;
      productRow.executionCostApprox += executionCostTotal;
      productRow.adverseSelectionApprox += adverseSelectionTotal;
      if (sideRow) sideRow.qty += fill.quantity;
    }
    overall.spreadCaptureApprox += spreadCaptureTotal;
    overall.executionCostApprox += executionCostTotal;
    overall.adverseSelectionApprox += adverseSelectionTotal;
    overall.bySide[fill.side].qty += fill.quantity;

    perFill.push({
      fillIndex: fill.index,
      product: fill.product,
      side: fill.side,
      timestamp: fill.timestamp,
      price: fill.price,
      quantity: fill.quantity,
      spreadCaptureApprox: spreadCaptureTotal,
      executionCostApprox: executionCostTotal,
      markout5: fill.horizons[5]?.markout ?? NaN,
      adverseSelectionApprox: adverseSelectionTotal,
    });
  }

  // Unrealized PnL from open lots at the last fair price.
  const openLots = computeOpenLots(fills);
  for (const [product, lots] of Object.entries(openLots)) {
    const fairSeries = productStats?.[product]?.fairSeries ?? [];
    const fair = lastFinite(fairSeries);
    let unrealized = 0;
    for (const lot of lots) {
      const sideSign = lot.side === "buy" ? 1 : -1;
      if (Number.isFinite(fair)) {
        unrealized += sideSign * (fair - lot.price) * lot.remainingQty;
      }
    }
    if (!byProduct[product]) continue;
    byProduct[product].unrealizedPnl = unrealized;
    overall.unrealizedPnl += unrealized;
  }

  const episodes = (lifecycle.orders ?? []).map((order) => ({
    id: order.id,
    product: order.product,
    side: order.side,
    startTimestamp: order.startTimestamp,
    endTimestamp: order.endTimestamp,
    quantity: order.executedQty ?? order.quantity ?? 0,
    vwap: order.vwap ?? NaN,
    averageMarkout5: order.averageMarkout?.[5] ?? NaN,
    avgShortfall: order.avgShortfall ?? NaN,
    fillCount: order.fillCount ?? 0,
    pnlApprox: sum((order.fills ?? []).map((fillIndex) => {
      const fill = fillMap.get(fillIndex);
      return fill && Number.isFinite(fill.horizons[5]?.markout)
        ? fill.horizons[5].markout * fill.quantity
        : 0;
    })),
  }));

  return {
    overall,
    byProduct,
    perFill,
    closedTrades,
    episodes,
  };
}

function buildExecutionMetrics(fills, lifecycle, closedTrades) {
  const overall = aggregateFillMetrics(fills);
  const byProduct = aggregateByKey(fills, (fill) => fill.product);
  const bySide = aggregateByKey(fills, (fill) => fill.side);
  const observedOnly = (lifecycle.orders ?? []).filter((order) => order.observed);
  const inferredOnly = (lifecycle.orders ?? []).filter((order) => order.inferred);
  const holdTimes = closedTrades.map((trade) => trade.holdingTime).filter(Number.isFinite);

  return {
    overall: {
      ...overall,
      averageHoldingTime: mean(holdTimes),
      averageHoldingTicks: mean(closedTrades.map((trade) => trade.holdingTicks)),
      observedOrderFillRatio: observedOnly.length
        ? mean(observedOnly.map((order) => ratio(order.executedQty, order.quantity)))
        : NaN,
      observedCancelRatio: observedOnly.length
        ? ratio(observedOnly.filter((order) => String(order.status).includes("active / cancelled")).length, observedOnly.length)
        : NaN,
      inferredEpisodeSpan: inferredOnly.length
        ? mean(inferredOnly.map((order) => order.lifetime))
        : NaN,
      coverage: {
        observedOrders: observedOnly.length,
        inferredOrders: inferredOnly.length,
      },
    },
    byProduct,
    bySide,
  };
}

function aggregateByKey(fills, keyFn) {
  const map = new Map();
  for (const fill of fills) {
    const key = keyFn(fill);
    if (!map.has(key)) map.set(key, []);
    map.get(key).push(fill);
  }
  return Array.from(map.entries()).map(([key, group]) => ({ key, ...aggregateFillMetrics(group) }));
}

function aggregateFillMetrics(fills) {
  const classified = fills.filter((fill) => fill.context.mode !== "unknown");
  const totalQty = sum(fills.map((fill) => fill.quantity));
  const classifiedQty = sum(classified.map((fill) => fill.quantity));
  const passiveQty = sum(classified.filter((fill) => fill.context.mode === "passive").map((fill) => fill.quantity));
  const aggressiveQty = sum(classified.filter((fill) => fill.context.mode === "aggressive").map((fill) => fill.quantity));
  const insideSpreadQty = sum(classified.filter((fill) => fill.context.bookRelation === "inside-spread").map((fill) => fill.quantity));
  const queueEstimateQty = fills.filter((fill) => fill.context.queueAheadEstimate != null);

  return {
    totalFills: fills.length,
    totalQty,
    passiveFillPct: ratio(passiveQty, classifiedQty),
    aggressiveFillPct: ratio(aggressiveQty, classifiedQty),
    insideSpreadPct: ratio(insideSpreadQty, classifiedQty),
    averageQueueAheadEstimate: weightedAverage(queueEstimateQty, (fill) => fill.context.queueAheadEstimate, (fill) => fill.quantity),
    averageShortfall: weightedAverage(fills, (fill) => fill.shortfall, (fill) => fill.quantity),
    averageSlippage: weightedAverage(fills, (fill) => fill.slippage, (fill) => fill.quantity),
    averageSpreadCapture: weightedAverage(fills, (fill) => fill.spreadCapture, (fill) => fill.quantity),
    averageMarkout: Object.fromEntries(
      MARKOUT_HORIZONS.map((horizon) => [horizon, weightedAverage(fills, (fill) => fill.horizons[horizon]?.markout, (fill) => fill.quantity)])
    ),
    averageRealizedSpread: Object.fromEntries(
      MARKOUT_HORIZONS.map((horizon) => [horizon, weightedAverage(fills, (fill) => fill.horizons[horizon]?.realizedSpread, (fill) => fill.quantity)])
    ),
    adverseSelectionScore: computeAdverseSelectionScore(fills),
  };
}

function buildDiagnostics(strategy, fills, closedTrades, pnlBreakdown, execution, productStats) {
  const totalPnl = strategy.totalPnl ?? [];
  const totalPnlDiffs = diffSeries(totalPnl);
  const drawdown = computeDrawdown(totalPnl);
  const tradePnls = closedTrades.map((trade) => trade.pnl);
  const sliceStats = buildSliceStats(strategy, fills, totalPnl, 8);
  const regimeStats = buildRegimeStats(strategy, productStats);
  const concentration = buildConcentration(strategy, fills, pnlBreakdown);
  const timeUnderWater = computeTimeUnderWater(drawdown);
  const recovery = computeRecoveryStats(drawdown);
  const inventory = computeInventoryStats(strategy, fills);
  const scores = buildHeuristicScores({
    strategy,
    sliceStats,
    execution,
    concentration,
    inventory,
    timeUnderWater,
  });

  return {
    sharpeLike: strategy.summary?.sharpe ?? 0,
    pnlPerTrade: ratio(strategy.summary?.totalPnl ?? 0, Math.max(1, strategy.summary?.tradeCount ?? 0)),
    hitRate: ratio(closedTrades.filter((trade) => trade.pnl > 0).length, closedTrades.length),
    expectancy: mean(tradePnls),
    tradePnlSkewness: skewness(tradePnls),
    maxDrawdown: Math.abs(Math.min(...drawdown, 0)),
    timeUnderWater,
    recovery,
    inventory,
    concentration,
    sliceStats,
    regimeStats,
    scores,
    labels: buildDiagnosticLabels({ scores, execution, inventory, concentration }),
  };
}

function buildSliceStats(strategy, fills, totalPnl, sliceCount) {
  const len = totalPnl.length;
  if (!len) return [];
  const out = [];
  for (let i = 0; i < sliceCount; i++) {
    const startIdx = Math.floor((i * len) / sliceCount);
    const endIdx = Math.max(startIdx, Math.floor(((i + 1) * len) / sliceCount) - 1);
    const startBase = totalPnl[startIdx - 1] ?? 0;
    const endValue = totalPnl[endIdx] ?? startBase;
    const pnl = endValue - startBase;
    const sliceFills = fills.filter((fill) => fill.tickIdx >= startIdx && fill.tickIdx <= endIdx);
    out.push({
      index: i,
      startIdx,
      endIdx,
      startRawTs: strategy.rawTimestamps?.[startIdx] ?? 0,
      endRawTs: strategy.rawTimestamps?.[endIdx] ?? 0,
      pnl,
      fillCount: sliceFills.length,
      qty: sum(sliceFills.map((fill) => fill.quantity)),
      aggressiveFillPct: aggregateFillMetrics(sliceFills).aggressiveFillPct,
    });
  }
  return out;
}

function buildRegimeStats(strategy, productStats) {
  const regimes = {
    spread: new Map(),
    volatility: new Map(),
    imbalance: new Map(),
    flow: new Map(),
  };

  for (const product of strategy.products ?? []) {
    const ps = strategy.series?.[product] ?? {};
    const fair = productStats?.[product]?.fairSeries ?? [];
    const pnl = forwardDiff(ps.pnl ?? []);
    for (let i = 1; i < fair.length; i++) {
      const spread = ps.spread?.[i];
      const imb = ps.imbalance?.[i];
      const absRet = Number.isFinite(fair[i]) && Number.isFinite(fair[i - 1]) ? Math.abs(fair[i] - fair[i - 1]) : NaN;
      const spreadRegime = classifySpread(spread, productStats?.[product]);
      const volRegime = classifyVol(absRet, productStats?.[product]);
      const imbalanceRegime = classifyImbalance(imb, productStats?.[product]);
      const flowRegime = classifyFlow(fair, i);
      addRegime(regimes.spread, spreadRegime, pnl[i] ?? 0);
      addRegime(regimes.volatility, volRegime, pnl[i] ?? 0);
      addRegime(regimes.imbalance, imbalanceRegime, pnl[i] ?? 0);
      addRegime(regimes.flow, flowRegime, pnl[i] ?? 0);
    }
  }

  return Object.fromEntries(
    Object.entries(regimes).map(([name, map]) => [
      name,
      Array.from(map.entries())
        .map(([key, value]) => ({ key, ...value, avgPnlPerTick: ratio(value.pnl, value.ticks) }))
        .sort((a, b) => String(a.key).localeCompare(String(b.key))),
    ])
  );
}

function buildConcentration(strategy, fills, pnlBreakdown) {
  const pnlEntries = Object.entries(strategy.summary?.perProductPnl ?? {}).map(([product, pnl]) => ({ product, value: Math.abs(pnl) }));
  const volumeByProduct = groupSum(fills, (fill) => fill.product, (fill) => fill.quantity);
  const pnlTotal = sum(pnlEntries.map((entry) => entry.value));
  const volumeTotal = sum(Object.values(volumeByProduct));
  const byProduct = Array.from(new Set([...(strategy.products ?? []), ...Object.keys(volumeByProduct)])).map((product) => ({
    product,
    pnlShare: ratio(Math.abs(strategy.summary?.perProductPnl?.[product] ?? 0), pnlTotal),
    volumeShare: ratio(volumeByProduct[product] ?? 0, volumeTotal),
    pnl: strategy.summary?.perProductPnl?.[product] ?? 0,
  }));
  byProduct.sort((a, b) => (b.pnlShare ?? 0) - (a.pnlShare ?? 0));
  return {
    byProduct,
    herfindahlPnl: sum(byProduct.map((row) => (row.pnlShare ?? 0) ** 2)),
    herfindahlVolume: sum(byProduct.map((row) => (row.volumeShare ?? 0) ** 2)),
    topProduct: byProduct[0] ?? null,
  };
}

function computeTimeUnderWater(drawdown) {
  let underwaterTicks = 0;
  let longest = 0;
  let current = 0;
  for (const value of drawdown) {
    if (value < 0) {
      underwaterTicks += 1;
      current += 1;
      if (current > longest) longest = current;
    } else {
      current = 0;
    }
  }
  return {
    pct: ratio(underwaterTicks, drawdown.length),
    longestTicks: longest,
  };
}

function computeRecoveryStats(drawdown) {
  let current = 0;
  let longest = 0;
  for (const value of drawdown) {
    if (value < 0) {
      current += 1;
      if (current > longest) longest = current;
    } else {
      current = 0;
    }
  }
  return {
    maxRecoveryTicks: longest,
  };
}

function computeInventoryStats(strategy, fills) {
  const maxAbsInventory = max(
    (strategy.products ?? []).map((product) =>
      maxAbs(strategy.series?.[product]?.position ?? [])
    )
  );
  const productAverages = (strategy.products ?? []).map((product) => {
    const avgAbs = mean((strategy.series?.[product]?.position ?? []).map((value) => Math.abs(value)));
    const tradedQty = sum((fills ?? []).filter((fill) => fill.product === product).map((fill) => fill.quantity));
    return {
      product,
      avgAbs,
      maxAbs: maxAbs(strategy.series?.[product]?.position ?? []),
      turnover: ratio(tradedQty, Math.max(1, avgAbs)),
    };
  });
  return {
    maxAbs: maxAbsInventory,
    averageAbs: mean(productAverages.map((row) => row.avgAbs)),
    perProduct: productAverages,
  };
}

function buildHeuristicScores({ strategy, sliceStats, execution, concentration, inventory, timeUnderWater }) {
  const positiveSliceRatio = ratio(sliceStats.filter((slice) => slice.pnl > 0).length, sliceStats.length);
  const topSliceShare = ratio(max(sliceStats.map((slice) => Math.abs(slice.pnl))), sum(sliceStats.map((slice) => Math.abs(slice.pnl))));
  const drawdownRatio = ratio(strategy.summary?.maxDrawdown ?? 0, Math.max(1, Math.abs(strategy.summary?.totalPnl ?? 0)));
  const inventoryStress = ratio(inventory.maxAbs, Math.max(1, mean(Object.values(strategy.positionLimits ?? {}))));
  const adverse = clamp((execution.overall?.adverseSelectionScore ?? 0) / 100, 0, 1);
  const fragility = clamp01(
    0.30 * topSliceShare +
      0.25 * drawdownRatio +
      0.20 * inventoryStress +
      0.15 * (1 - positiveSliceRatio) +
      0.10 * adverse
  );
  const consistency = clamp01(
    0.35 * positiveSliceRatio +
      0.20 * (1 - topSliceShare) +
      0.20 * (1 - drawdownRatio) +
      0.15 * (1 - timeUnderWater.pct) +
      0.10 * clamp01((strategy.summary?.sharpe ?? 0) / 3)
  );
  return {
    fragility: fragility * 100,
    consistency: consistency * 100,
    stability: clamp01(0.5 * consistency + 0.5 * (1 - fragility)) * 100,
  };
}

function buildDiagnosticLabels({ scores, execution, inventory, concentration }) {
  const labels = [];
  labels.push(labelFromScore("consistency", scores.consistency, "higher is better"));
  labels.push(labelFromScore("fragility", 100 - scores.fragility, "lower risk is better"));
  if ((execution.overall?.aggressiveFillPct ?? 0) > 0.6) labels.push({ tone: "risk", text: "agresiva" });
  if ((inventory.maxAbs ?? 0) > Math.max(20, 1.75 * (inventory.averageAbs ?? 0))) labels.push({ tone: "risk", text: "inventario alto" });
  if ((execution.overall?.adverseSelectionScore ?? 0) > 55) labels.push({ tone: "risk", text: "adverse selection" });
  if ((concentration.topProduct?.pnlShare ?? 0) > 0.65) labels.push({ tone: "warn", text: "dependencia por producto" });
  return labels;
}

function buildInsightCards({ strategy, execution, diagnostics }) {
  const cards = [];
  const passive = execution.overall?.passiveFillPct ?? 0;
  const aggressive = execution.overall?.aggressiveFillPct ?? 0;
  const markout5 = execution.overall?.averageMarkout?.[5] ?? NaN;
  const dd = diagnostics.maxDrawdown ?? 0;
  const pnl = strategy.summary?.totalPnl ?? 0;
  const topShare = diagnostics?.concentration?.topProduct?.pnlShare ?? 0;

  if (passive > 0.6 && markout5 < 0) {
    cards.push({ tone: "warn", title: "Captura spread, pero sufre adverse selection", body: "La mezcla de fills es mayormente pasiva, pero el markout a 5 ticks es negativo. Eso sugiere que muchas ejecuciones descansan donde el mercado sigue en contra después del fill." });
  }
  if (aggressive > 0.55 && (execution.overall?.averageShortfall ?? 0) > 0) {
    cards.push({ tone: "risk", title: "La estrategia paga por entrar", body: "La proporción de fills agresivos es alta y el shortfall promedio es positivo. Está entrando rápido, pero a costa de peor precio de ejecución." });
  }
  if (dd > Math.abs(pnl) * 0.7) {
    cards.push({ tone: "risk", title: "PnL con drawdown exigente", body: "El drawdown máximo consume una parte grande del PnL final. Ojo: quizá el edge existe, pero la ruta para llegar es frágil." });
  }
  if (topShare > 0.6) {
    cards.push({ tone: "warn", title: "Dependencia fuerte de pocos episodios / productos", body: `Más del ${(topShare * 100).toFixed(0)}% del PnL absoluto se concentra en un solo producto. Eso huele a estrategia menos diversificada y más sensible a cambios de régimen.` });
  }
  if ((diagnostics.scores?.consistency ?? 0) > 70 && (diagnostics.scores?.fragility ?? 0) < 40) {
    cards.push({ tone: "good", title: "Perfil bastante robusto", body: "La distribución temporal del PnL es relativamente pareja, el score de consistencia es alto y la fragilidad heurística es contenida." });
  }
  if (cards.length === 0) {
    cards.push({ tone: "neutral", title: "Perfil mixto", body: "No hay una señal dominante única. Conviene leer execution quality, inventario y mejor/peor episodios juntos antes de juzgar el edge." });
  }
  return cards;
}

function buildComparisonBullets(reference, other, metrics, byProduct, leadLag) {
  const bullets = [];
  const topMetrics = [...metrics].sort((a, b) => Math.abs(b.delta ?? 0) - Math.abs(a.delta ?? 0)).slice(0, 4);
  for (const metric of topMetrics) {
    if (!Number.isFinite(metric.delta) || Math.abs(metric.delta) < EPS) continue;
    const winner = metric.referenceBetter ? reference.name : other.name;
    bullets.push(`${winner} sale mejor en ${metric.label.toLowerCase()} (${reference.name}: ${formatComparisonNumber(metric.ref)}, ${other.name}: ${formatComparisonNumber(metric.other)}).`);
  }
  const topProduct = [...byProduct].sort((a, b) => Math.abs(b.pnlGap ?? 0) - Math.abs(a.pnlGap ?? 0))[0];
  if (topProduct && Number.isFinite(topProduct.pnlGap) && Math.abs(topProduct.pnlGap) > EPS) {
    const winner = topProduct.pnlGap > 0 ? reference.name : other.name;
    bullets.push(`${winner} explica la mayor diferencia en ${topProduct.product}, donde la brecha de PnL en la ventana es ${formatComparisonNumber(topProduct.pnlGap)}.`);
  }
  const lead = leadLag.sort((a, b) => b.gap - a.gap)[0];
  if (lead && lead.gap > 0) {
    bullets.push(`${lead.leader} entra antes en ${lead.key.replace(":", " / ")} por ${lead.gap} unidades de timestamp dentro de la ventana seleccionada.`);
  }
  if (bullets.length === 0) {
    bullets.push("Las dos estrategias están bastante parejas en la ventana elegida. Mirá el detalle por producto y los markouts para encontrar diferencias finas.");
  }
  return bullets;
}

function metricDelta(label, ref, other, higherIsBetter) {
  if (!Number.isFinite(ref) && !Number.isFinite(other)) return null;
  const delta = diff(ref, other);
  return {
    label,
    ref,
    other,
    delta,
    higherIsBetter,
    referenceBetter: higherIsBetter ? ref >= other : ref <= other,
  };
}

function classifyAgainstBook(side, price, book) {
  const bids = Array.isArray(book?.bids) ? book.bids : [];
  const asks = Array.isArray(book?.asks) ? book.asks : [];
  const bestBid = bids[0]?.price;
  const bestAsk = asks[0]?.price;
  const spread = computeSpread(bestBid, bestAsk);
  if (!Number.isFinite(price)) {
    return { mode: "unknown", bookRelation: "unknown", crossesSpread: false, queueAheadEstimate: null };
  }

  if (side === "buy") {
    if (Number.isFinite(bestAsk) && price >= bestAsk - EPS) {
      return {
        mode: "aggressive",
        bookRelation: "crossed-spread",
        crossesSpread: true,
        queueAheadEstimate: 0,
        queueSameSideEstimate: 0,
      };
    }
    const ownLevel = bids.findIndex((level) => almostEqual(level.price, price));
    if (ownLevel >= 0) {
      return {
        mode: "passive",
        bookRelation: ownLevel === 0 ? "joining-best" : "deeper-passive",
        crossesSpread: false,
        queueAheadEstimate: sum(bids.slice(0, ownLevel + 1).map((level) => level.volume)),
        queueSameSideEstimate: bids[ownLevel]?.volume ?? null,
      };
    }
    if (Number.isFinite(bestBid) && price > bestBid && (!Number.isFinite(bestAsk) || price < bestAsk)) {
      return {
        mode: "passive",
        bookRelation: "inside-spread",
        crossesSpread: false,
        queueAheadEstimate: 0,
        queueSameSideEstimate: 0,
      };
    }
    return {
      mode: "passive",
      bookRelation: "off-screen-bid",
      crossesSpread: false,
      queueAheadEstimate: sum(bids.map((level) => level.volume)),
      queueSameSideEstimate: null,
    };
  }

  if (Number.isFinite(bestBid) && price <= bestBid + EPS) {
    return {
      mode: "aggressive",
      bookRelation: "crossed-spread",
      crossesSpread: true,
      queueAheadEstimate: 0,
      queueSameSideEstimate: 0,
    };
  }
  const ownLevel = asks.findIndex((level) => almostEqual(level.price, price));
  if (ownLevel >= 0) {
    return {
      mode: "passive",
      bookRelation: ownLevel === 0 ? "joining-best" : "deeper-passive",
      crossesSpread: false,
      queueAheadEstimate: sum(asks.slice(0, ownLevel + 1).map((level) => level.volume)),
      queueSameSideEstimate: asks[ownLevel]?.volume ?? null,
    };
  }
  if (Number.isFinite(bestAsk) && price < bestAsk && (!Number.isFinite(bestBid) || price > bestBid)) {
    return {
      mode: "passive",
      bookRelation: "improving",
      crossesSpread: false,
      queueAheadEstimate: 0,
      queueSameSideEstimate: 0,
    };
  }
  return {
    mode: "passive",
    bookRelation: "off-screen-ask",
    crossesSpread: false,
    queueAheadEstimate: sum(asks.map((level) => level.volume)),
    queueSameSideEstimate: null,
  };
}

function estimateExpectedPrice(side, book, context) {
  const bids = Array.isArray(book?.bids) ? book.bids : [];
  const asks = Array.isArray(book?.asks) ? book.asks : [];
  if (context.mode === "aggressive") {
    return side === "buy" ? asks[0]?.price ?? NaN : bids[0]?.price ?? NaN;
  }
  if (context.bookRelation === "joining-best") {
    return side === "buy" ? bids[0]?.price ?? NaN : asks[0]?.price ?? NaN;
  }
  if (context.bookRelation === "inside-spread") {
    return midpoint(bids[0]?.price, asks[0]?.price);
  }
  return side === "buy" ? bids[0]?.price ?? NaN : asks[0]?.price ?? NaN;
}

function summarizeLifecycleContext(context, fill) {
  const bits = [];
  if (context.mode === "aggressive") bits.push("cruzó el spread");
  else if (context.bookRelation === "inside-spread") bits.push("mejoró dentro del spread");
  else if (context.bookRelation === "joining-best") bits.push("se unió al mejor precio");
  else bits.push("pasiva / inferida");
  if (context.queueAheadEstimate != null) bits.push(`cola visible ~${Math.round(context.queueAheadEstimate)}`);
  if (fill && Number.isFinite(fill.horizons?.[5]?.markout)) {
    bits.push(fill.horizons[5].markout >= 0 ? "markout 5t favorable" : "markout 5t adverso");
  }
  return bits.join(" · ");
}

function classifySpread(spread, stats) {
  if (!Number.isFinite(spread)) return "unknown";
  if (spread >= (stats?.spreadQ75 ?? Infinity)) return "wide";
  if (spread <= (stats?.spreadQ25 ?? -Infinity)) return "narrow";
  return "mid";
}

function classifyVol(absRet, stats) {
  if (!Number.isFinite(absRet)) return "unknown";
  if (absRet >= (stats?.absReturnQ75 ?? Infinity)) return "high-vol";
  if (absRet <= (stats?.absReturnMedian ?? -Infinity)) return "low-vol";
  return "mid-vol";
}

function classifyImbalance(imbalance, stats) {
  if (!Number.isFinite(imbalance)) return "unknown";
  if (imbalance >= Math.max(0.58, stats?.imbalanceQ75 ?? 0.58)) return "bid-heavy";
  if (imbalance <= Math.min(0.42, stats?.imbalanceQ25 ?? 0.42)) return "ask-heavy";
  return "balanced";
}

function classifyFlow(fairSeries, idx) {
  const prev = fairSeries[idx - 1];
  const prev5 = fairSeries[Math.max(0, idx - 5)];
  const prev10 = fairSeries[Math.max(0, idx - 10)];
  const cur = fairSeries[idx];
  if (![cur, prev, prev5, prev10].every(Number.isFinite)) return "unknown";
  const recentMove = cur - prev5;
  const olderMove = prev5 - prev10;
  const path = sumAbs(diffSeries(fairSeries.slice(Math.max(0, idx - 5), idx + 1)));
  const trendiness = path > 0 ? Math.abs(recentMove) / path : 0;
  if (trendiness > 0.65 && Math.sign(recentMove) === Math.sign(olderMove) && Math.sign(recentMove) !== 0) {
    return recentMove > 0 ? "trend-up" : "trend-down";
  }
  if (Math.sign(recentMove) !== 0 && Math.sign(recentMove) !== Math.sign(olderMove)) {
    return "mean-reverting";
  }
  return "choppy";
}

function addRegime(map, key, pnl) {
  if (!map.has(key)) map.set(key, { pnl: 0, ticks: 0 });
  const row = map.get(key);
  row.pnl += pnl;
  row.ticks += 1;
}

function computeOpenLots(fills) {
  const inventory = new Map();
  for (const fill of fills) {
    const key = fill.product;
    const queue = inventory.get(key) ?? [];
    let qty = fill.quantity;
    while (qty > EPS && queue.length > 0 && queue[0].side !== fill.side) {
      const head = queue[0];
      const matched = Math.min(qty, head.remainingQty);
      head.remainingQty -= matched;
      qty -= matched;
      if (head.remainingQty <= EPS) queue.shift();
    }
    if (qty > EPS) {
      queue.push({ side: fill.side, price: fill.price, remainingQty: qty });
    }
    inventory.set(key, queue);
  }
  return Object.fromEntries(Array.from(inventory.entries()));
}

function computeAdverseSelectionScore(fills) {
  const markouts = fills
    .map((fill) => fill.horizons?.[5]?.markout)
    .filter((value) => Number.isFinite(value));
  if (!markouts.length) return NaN;
  const negative = mean(markouts.map((value) => Math.max(0, -value)));
  const positive = mean(markouts.map((value) => Math.max(0, value)));
  const denom = Math.max(0.01, positive + negative);
  return clamp01(negative / denom) * 100;
}

function labelFromScore(label, value, description) {
  let tone = "neutral";
  if (value >= 70) tone = "good";
  else if (value < 45) tone = "risk";
  return { tone, text: label, description };
}

function forwardDiff(values) {
  const out = new Array(values.length).fill(0);
  let last = values[0] ?? 0;
  for (let i = 1; i < values.length; i++) {
    const cur = Number.isFinite(values[i]) ? values[i] : last;
    out[i] = cur - last;
    last = cur;
  }
  return out;
}

function diffSeries(values) {
  const out = [];
  for (let i = 1; i < values.length; i++) {
    if (Number.isFinite(values[i]) && Number.isFinite(values[i - 1])) {
      out.push(values[i] - values[i - 1]);
    }
  }
  return out;
}

function groupSum(items, keyFn, valueFn) {
  const out = {};
  for (const item of items) {
    const key = keyFn(item);
    out[key] = (out[key] ?? 0) + valueFn(item);
  }
  return out;
}

function dominantType(values) {
  const counts = new Map();
  for (const value of values) counts.set(value, (counts.get(value) ?? 0) + 1);
  let best = "unknown";
  let bestCount = -1;
  for (const [value, count] of counts.entries()) {
    if (count > bestCount) {
      best = value;
      bestCount = count;
    }
  }
  return best;
}

function formatComparisonNumber(value) {
  if (!Number.isFinite(value)) return "—";
  return Math.abs(value) >= 1000 ? value.toFixed(0) : value.toFixed(2);
}

function clampIndex(index, length) {
  if (length <= 0) return 0;
  return Math.max(0, Math.min(length - 1, index));
}

function nearestTickIndex(timestamps, tickKey) {
  if (!timestamps?.length) return 0;
  let lo = 0;
  let hi = timestamps.length - 1;
  while (lo < hi) {
    const mid = (lo + hi) >> 1;
    if (timestamps[mid] < tickKey) lo = mid + 1;
    else hi = mid;
  }
  return lo;
}

function compositeTickKey(day, timestamp) {
  return (Number.isFinite(day) ? day : 0) * 1_000_000 + (Number.isFinite(timestamp) ? timestamp : 0);
}

function midpoint(a, b) {
  return Number.isFinite(a) && Number.isFinite(b) ? (a + b) / 2 : NaN;
}

function computeSpread(bestBid, bestAsk) {
  return Number.isFinite(bestBid) && Number.isFinite(bestAsk) ? bestAsk - bestBid : NaN;
}

function firstFinite(...values) {
  for (const value of values) if (Number.isFinite(value)) return value;
  return NaN;
}

function last(values) {
  return Array.isArray(values) && values.length ? values[values.length - 1] : undefined;
}

function lastFinite(values) {
  if (!Array.isArray(values)) return NaN;
  for (let i = values.length - 1; i >= 0; i--) {
    if (Number.isFinite(values[i])) return values[i];
  }
  return NaN;
}

function finiteValues(values) {
  return (values ?? []).filter(Number.isFinite);
}

function mean(values) {
  const arr = (values ?? []).filter(Number.isFinite);
  if (!arr.length) return NaN;
  return sum(arr) / arr.length;
}

function weightedAverage(items, valueFn, weightFn) {
  let num = 0;
  let den = 0;
  for (const item of items ?? []) {
    const value = valueFn(item);
    const weight = weightFn(item);
    if (!Number.isFinite(value) || !Number.isFinite(weight)) continue;
    num += value * weight;
    den += weight;
  }
  return den > EPS ? num / den : NaN;
}

function ratio(num, den) {
  return Number.isFinite(num) && Number.isFinite(den) && den > EPS ? num / den : NaN;
}

function quantile(values, q) {
  const arr = [...(values ?? [])].filter(Number.isFinite).sort((a, b) => a - b);
  if (!arr.length) return NaN;
  if (arr.length === 1) return arr[0];
  const pos = (arr.length - 1) * q;
  const lo = Math.floor(pos);
  const hi = Math.ceil(pos);
  if (lo === hi) return arr[lo];
  const t = pos - lo;
  return arr[lo] * (1 - t) + arr[hi] * t;
}

function skewness(values) {
  const arr = (values ?? []).filter(Number.isFinite);
  if (arr.length < 3) return NaN;
  const mu = mean(arr);
  const sigma = Math.sqrt(mean(arr.map((v) => (v - mu) ** 2)));
  if (!Number.isFinite(sigma) || sigma <= EPS) return NaN;
  return mean(arr.map((v) => ((v - mu) / sigma) ** 3));
}

function sum(values) {
  return (values ?? []).reduce((acc, value) => acc + (Number.isFinite(value) ? value : 0), 0);
}

function sumAbs(values) {
  return (values ?? []).reduce((acc, value) => acc + (Number.isFinite(value) ? Math.abs(value) : 0), 0);
}

function min(values) {
  const arr = (values ?? []).filter(Number.isFinite);
  return arr.length ? Math.min(...arr) : NaN;
}

function max(values) {
  const arr = (values ?? []).filter(Number.isFinite);
  return arr.length ? Math.max(...arr) : NaN;
}

function maxAbs(values) {
  return max((values ?? []).map((value) => Math.abs(value)));
}

function maxObjectValue(obj, getter) {
  return max(Object.values(obj ?? {}).map((value) => getter(value)));
}

function diff(a, b) {
  return Number.isFinite(a) && Number.isFinite(b) ? a - b : NaN;
}

function almostEqual(a, b) {
  return Number.isFinite(a) && Number.isFinite(b) && Math.abs(a - b) < EPS;
}

function clamp(minValue, value, maxValue) {
  return Math.max(minValue, Math.min(maxValue, value));
}

function clamp01(value) {
  return clamp(0, value, 1);
}
