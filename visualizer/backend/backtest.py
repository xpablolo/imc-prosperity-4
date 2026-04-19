from __future__ import annotations

import bisect
import csv
import math
import re
from collections import defaultdict
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from .limits import build_limits

DAY_STRIDE = 1_000_000
PRICE_HEADER = (
    "day;timestamp;product;bid_price_1;bid_volume_1;bid_price_2;bid_volume_2;bid_price_3;"
    "bid_volume_3;ask_price_1;ask_volume_1;ask_price_2;ask_volume_2;ask_price_3;ask_volume_3;"
    "mid_price;profit_and_loss"
)
TRADE_HEADER = "timestamp;buyer;seller;symbol;currency;price;quantity"
ROUND0_RESULTS_HEADER = "day,timestamp,global_ts,equity_total,pnl_total,pnl_TOMATOES,pnl_EMERALDS"
ROUND0_FILLS_HEADER = "day,timestamp,product,side,price,quantity,source"
STANDARD_RESULTS_HEADER = "day,timestamp,global_ts,mid_price,cash,position,equity,pnl"
SIMPLE_RESULTS_HEADER = "day,timestamp,pnl,position"
STANDARD_FILLS_HEADER = "day,timestamp,global_ts,product,side,price,quantity,source"

PRODUCT_ALIASES = {
    "ash": "ASH_COATED_OSMIUM",
    "osmium": "ASH_COATED_OSMIUM",
    "pepper": "INTARIAN_PEPPER_ROOT",
    "root": "INTARIAN_PEPPER_ROOT",
    "emerald": "EMERALDS",
    "emeralds": "EMERALDS",
    "tomato": "TOMATOES",
    "tomatoes": "TOMATOES",
}


@dataclass
class RunBundle:
    id: str
    name: str
    round_name: str
    root: Path
    result_files: list[Path]
    fill_files: list[Path]
    primary_path: Path
    meta: dict[str, Any]


@dataclass
class ActivityRow:
    day: int
    timestamp: int
    product: str
    bids: list[dict[str, float]]
    asks: list[dict[str, float]]
    mid_price: float
    pnl: float


def tick_key(day: int | float | None, ts: int | float | None) -> int:
    d = int(day) if day is not None and not math.isnan(day) else 0
    t = int(ts) if ts is not None and not math.isnan(ts) else 0
    return d * DAY_STRIDE + t


# ---------- numeric helpers ----------


def _to_float(value: Any) -> float:
    if value is None:
        return math.nan
    s = str(value).strip()
    if s == "":
        return math.nan
    try:
        return float(s)
    except Exception:
        return math.nan



def _to_int(value: Any) -> int | None:
    f = _to_float(value)
    if math.isnan(f):
        return None
    return int(f)



def _finite(value: float) -> bool:
    return not math.isnan(value) and math.isfinite(value)


# ---------- price / trade parsing ----------


def parse_price_file(path: Path, warnings: list[str]) -> list[ActivityRow]:
    rows: list[ActivityRow] = []
    bad_rows = 0
    try:
        with path.open("r", encoding="utf-8", errors="replace") as fh:
            reader = csv.DictReader(fh, delimiter=";")
            for raw in reader:
                day = _to_int(raw.get("day"))
                ts = _to_int(raw.get("timestamp"))
                product = (raw.get("product") or "").strip()
                if day is None or ts is None or not product:
                    bad_rows += 1
                    continue
                bids = []
                asks = []
                for lvl in range(1, 4):
                    bp = _to_float(raw.get(f"bid_price_{lvl}"))
                    bv = _to_float(raw.get(f"bid_volume_{lvl}"))
                    if _finite(bp) and _finite(bv):
                        bids.append({"price": bp, "volume": bv})
                for lvl in range(1, 4):
                    ap = _to_float(raw.get(f"ask_price_{lvl}"))
                    av = _to_float(raw.get(f"ask_volume_{lvl}"))
                    if _finite(ap) and _finite(av):
                        asks.append({"price": ap, "volume": av})
                rows.append(
                    ActivityRow(
                        day=day,
                        timestamp=ts,
                        product=product,
                        bids=bids,
                        asks=asks,
                        mid_price=_to_float(raw.get("mid_price")),
                        pnl=_to_float(raw.get("profit_and_loss")),
                    )
                )
    except Exception as exc:
        warnings.append(f"No pude leer {path.name}: {exc}")
        return []
    if bad_rows:
        warnings.append(f"{path.name}: {bad_rows} filas de precios incompletas fueron ignoradas.")
    return rows



def parse_trade_file(path: Path, day: int, warnings: list[str]) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    bad_rows = 0
    try:
        with path.open("r", encoding="utf-8", errors="replace") as fh:
            reader = csv.DictReader(fh, delimiter=";")
            for raw in reader:
                ts = _to_int(raw.get("timestamp"))
                price = _to_float(raw.get("price"))
                qty = _to_float(raw.get("quantity"))
                symbol = (raw.get("symbol") or "").strip()
                if ts is None or not symbol or not _finite(price) or not _finite(qty):
                    bad_rows += 1
                    continue
                rows.append(
                    {
                        "timestamp": ts,
                        "buyer": (raw.get("buyer") or "").strip(),
                        "seller": (raw.get("seller") or "").strip(),
                        "symbol": symbol,
                        "currency": (raw.get("currency") or "SEASHELLS").strip(),
                        "price": price,
                        "quantity": qty,
                        "day": day,
                        "tickKey": tick_key(day, ts),
                    }
                )
    except Exception as exc:
        warnings.append(f"No pude leer {path.name}: {exc}")
        return []
    if bad_rows:
        warnings.append(f"{path.name}: {bad_rows} filas de trades incompletas fueron ignoradas.")
    return rows


# ---------- fills / results parsing ----------


def parse_fill_file(path: Path, warnings: list[str]) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    bad_rows = 0
    try:
        with path.open("r", encoding="utf-8", errors="replace") as fh:
            reader = csv.DictReader(fh)
            for raw in reader:
                day = _to_int(raw.get("day"))
                ts = _to_int(raw.get("timestamp"))
                product = (raw.get("product") or "").strip()
                side = (raw.get("side") or "").strip().upper()
                price = _to_float(raw.get("price"))
                qty = _to_float(raw.get("quantity"))
                if day is None or ts is None or not product or side not in {"BUY", "SELL"} or not _finite(price) or not _finite(qty):
                    bad_rows += 1
                    continue
                sign = 1 if side == "BUY" else -1
                rows.append(
                    {
                        "day": day,
                        "timestamp": ts,
                        "tickKey": tick_key(day, ts),
                        "product": product,
                        "side": side.lower(),
                        "price": price,
                        "quantity": qty,
                        "cashFlow": -sign * price * qty,
                        "source": (raw.get("source") or "").strip() or None,
                    }
                )
    except Exception as exc:
        warnings.append(f"No pude leer {path.name}: {exc}")
        return rows
    if bad_rows:
        warnings.append(f"{path.name}: {bad_rows} fills incompletos fueron ignorados.")
    return rows



def _guess_product_from_name(filename: str) -> str | None:
    tokens = re.split(r"[^a-zA-Z0-9]+", filename.lower())
    for token in tokens:
        if token in PRODUCT_ALIASES:
            return PRODUCT_ALIASES[token]
    return None



def _infer_product_for_results_file(result_path: Path, fill_paths: list[Path], fills_cache: dict[Path, list[dict[str, Any]]]) -> str | None:
    stem = result_path.stem
    candidate_stems = []
    if "_results_" in stem:
        candidate_stems.append(stem.replace("_results_", "_fills_"))
    if stem.endswith("_results"):
        candidate_stems.append(stem[: -len("_results")] + "_fills")
    fill_map = {p.stem: p for p in fill_paths}
    for cand in candidate_stems:
        fill_path = fill_map.get(cand)
        if not fill_path:
            continue
        products = sorted({row["product"] for row in fills_cache.get(fill_path, []) if row.get("product")})
        if len(products) == 1:
            return products[0]
    all_products = sorted(
        {
            row["product"]
            for path in fill_paths
            for row in fills_cache.get(path, [])
            if row.get("product")
        }
    )
    if len(all_products) == 1:
        return all_products[0]
    return _guess_product_from_name(result_path.name)



def parse_result_file(path: Path, product: str | None, warnings: list[str]) -> tuple[str | None, list[dict[str, Any]], str]:
    rows: list[dict[str, Any]] = []
    bad_rows = 0
    result_kind = "unknown"

    with path.open("r", encoding="utf-8", errors="replace") as fh:
        header = fh.readline().strip()
        fh.seek(0)
        if header == ROUND0_RESULTS_HEADER:
            result_kind = "round0-combined"
            reader = csv.DictReader(fh)
            for raw in reader:
                day = _to_int(raw.get("day"))
                ts = _to_int(raw.get("timestamp"))
                if day is None or ts is None:
                    bad_rows += 1
                    continue
                pnl_by_product = {
                    key[4:]: _to_float(value)
                    for key, value in raw.items()
                    if key.startswith("pnl_") and key != "pnl_total"
                }
                rows.append(
                    {
                        "day": day,
                        "timestamp": ts,
                        "tickKey": tick_key(day, ts),
                        "totalPnl": _to_float(raw.get("pnl_total")),
                        "perProductPnl": pnl_by_product,
                    }
                )
        elif header == STANDARD_RESULTS_HEADER:
            result_kind = "standard-product"
            reader = csv.DictReader(fh)
            for raw in reader:
                day = _to_int(raw.get("day"))
                ts = _to_int(raw.get("timestamp"))
                if day is None or ts is None:
                    bad_rows += 1
                    continue
                rows.append(
                    {
                        "day": day,
                        "timestamp": ts,
                        "tickKey": tick_key(day, ts),
                        "product": product,
                        "midPrice": _to_float(raw.get("mid_price")),
                        "position": _to_float(raw.get("position")),
                        "pnl": _to_float(raw.get("pnl")),
                    }
                )
        elif header == SIMPLE_RESULTS_HEADER:
            result_kind = "simple-product"
            reader = csv.DictReader(fh)
            for raw in reader:
                day = _to_int(raw.get("day"))
                ts = _to_int(raw.get("timestamp"))
                if day is None or ts is None:
                    bad_rows += 1
                    continue
                rows.append(
                    {
                        "day": day,
                        "timestamp": ts,
                        "tickKey": tick_key(day, ts),
                        "product": product,
                        "midPrice": math.nan,
                        "position": _to_float(raw.get("position")),
                        "pnl": _to_float(raw.get("pnl")),
                    }
                )
        else:
            warnings.append(f"{path.name}: header de resultados no soportado, se ignora.")
            return product, [], result_kind

    if bad_rows:
        warnings.append(f"{path.name}: {bad_rows} filas de resultados incompletas fueron ignoradas.")
    return product, rows, result_kind


# ---------- series building ----------


def micro_price_of(bids: list[dict[str, float]], asks: list[dict[str, float]]) -> float:
    if not bids or not asks:
        return math.nan
    bb = bids[0]
    ba = asks[0]
    denom = bb["volume"] + ba["volume"]
    if denom <= 0:
        return (bb["price"] + ba["price"]) / 2
    return (bb["price"] * ba["volume"] + ba["price"] * bb["volume"]) / denom



def wall_mid_of(bids: list[dict[str, float]], asks: list[dict[str, float]]) -> float:
    if not bids or not asks:
        return math.nan
    b_wall = max(bids, key=lambda level: level["volume"])
    a_wall = max(asks, key=lambda level: level["volume"])
    return (b_wall["price"] + a_wall["price"]) / 2



def total_vol(levels: list[dict[str, float]]) -> float:
    return sum(level["volume"] for level in levels)



def load_round_market_data(root: Path, round_name: str, days: list[int], warnings: list[str]) -> tuple[list[ActivityRow], list[dict[str, Any]]]:
    prices: list[ActivityRow] = []
    trades: list[dict[str, Any]] = []
    data_dir = root / "data" / round_name
    if not data_dir.exists():
        warnings.append(f"No existe {data_dir.relative_to(root)}; se cargarán solo métricas derivadas de resultados.")
        return prices, trades

    for day in sorted(set(days)):
        prices_path = data_dir / f"prices_{round_name}_day_{day}.csv"
        if prices_path.exists():
            prices.extend(parse_price_file(prices_path, warnings))
        else:
            warnings.append(f"Falta {prices_path.relative_to(root)}; no habrá order book para day {day}.")

        trades_path = data_dir / f"trades_{round_name}_day_{day}.csv"
        if trades_path.exists():
            trades.extend(parse_trade_file(trades_path, day, warnings))
        else:
            warnings.append(f"Falta {trades_path.relative_to(root)}; no habrá market trades para day {day}.")

    prices.sort(key=lambda row: (tick_key(row.day, row.timestamp), row.product))
    trades.sort(key=lambda row: (row["tickKey"], row["symbol"], row["price"], row["quantity"]))
    return prices, trades



def _make_empty_series(products: list[str], timestamps: list[int]) -> dict[str, Any]:
    series = {}
    for product in products:
        series[product] = {
            "product": product,
            "timestamps": timestamps,
            "midPrice": [math.nan] * len(timestamps),
            "microPrice": [math.nan] * len(timestamps),
            "wallMid": [math.nan] * len(timestamps),
            "spread": [math.nan] * len(timestamps),
            "bidPrices": [[math.nan] * len(timestamps) for _ in range(3)],
            "askPrices": [[math.nan] * len(timestamps) for _ in range(3)],
            "bestBid": [math.nan] * len(timestamps),
            "bestAsk": [math.nan] * len(timestamps),
            "bidVol": [math.nan] * len(timestamps),
            "askVol": [math.nan] * len(timestamps),
            "imbalance": [math.nan] * len(timestamps),
            "pnl": [math.nan] * len(timestamps),
            "position": [0] * len(timestamps),
            "cumOwnVolume": [0] * len(timestamps),
            "books": [{"bids": [], "asks": []} for _ in range(len(timestamps))],
            "ownFillIndices": [[] for _ in range(len(timestamps))],
        }
    return series



def _index_ticks(price_rows: list[ActivityRow], fallback_ticks: list[tuple[int, int]], products: list[str]) -> tuple[list[int], list[int], list[int], dict[int, int], dict[tuple[int, int, str], ActivityRow]]:
    tick_to_idx: dict[int, int] = {}
    timestamps: list[int] = []
    raw_ts: list[int] = []
    days: list[int] = []
    price_lookup: dict[tuple[int, int, str], ActivityRow] = {}

    for row in price_rows:
        key = tick_key(row.day, row.timestamp)
        if key not in tick_to_idx:
            tick_to_idx[key] = len(timestamps)
            timestamps.append(key)
            raw_ts.append(row.timestamp)
            days.append(row.day)
        price_lookup[(row.day, row.timestamp, row.product)] = row

    for day, ts in sorted(set(fallback_ticks), key=lambda item: tick_key(item[0], item[1])):
        key = tick_key(day, ts)
        if key not in tick_to_idx:
            tick_to_idx[key] = len(timestamps)
            timestamps.append(key)
            raw_ts.append(ts)
            days.append(day)

    return timestamps, raw_ts, days, tick_to_idx, price_lookup



def _forward_fill_zero(values: list[float]) -> list[float]:
    out = []
    last = 0.0
    for value in values:
        if _finite(value):
            last = value
        out.append(last)
    return out



def _load_fills(bundle: RunBundle, warnings: list[str]) -> tuple[dict[Path, list[dict[str, Any]]], list[dict[str, Any]]]:
    """Parsea todos los fill files y retorna (fills_cache, own_fills ordenados)."""
    fills_cache: dict[Path, list[dict[str, Any]]] = {}
    own_fills: list[dict[str, Any]] = []
    for fill_path in bundle.fill_files:
        fills = parse_fill_file(fill_path, warnings)
        fills_cache[fill_path] = fills
        own_fills.extend(fills)
    own_fills.sort(key=lambda row: (row["tickKey"], row["product"], row["price"], row["quantity"]))
    return fills_cache, own_fills


def _load_results(
    bundle: RunBundle,
    fills_cache: dict[Path, list[dict[str, Any]]],
    own_fills: list[dict[str, Any]],
    warnings: list[str],
) -> tuple[dict[str, list[dict[str, Any]]], list[dict[str, Any]], list[str], list[str]]:
    """Parsea result files, infiere productos y retorna (result_rows_by_product, total_pnl_rows, products, result_kinds)."""
    result_rows_by_product: dict[str, list[dict[str, Any]]] = defaultdict(list)
    total_pnl_rows: list[dict[str, Any]] = []
    result_kinds: set[str] = set()
    products_from_results: set[str] = set()

    for result_path in bundle.result_files:
        product = _infer_product_for_results_file(result_path, bundle.fill_files, fills_cache)
        parsed_product, rows, result_kind = parse_result_file(result_path, product, warnings)
        if result_kind != "unknown":
            result_kinds.add(result_kind)
        if not rows:
            continue
        if result_kind == "round0-combined":
            total_pnl_rows.extend(rows)
            for row in rows:
                products_from_results.update(row["perProductPnl"].keys())
        else:
            if parsed_product:
                products_from_results.add(parsed_product)
                result_rows_by_product[parsed_product].extend(rows)
            else:
                warnings.append(f"No pude inferir el producto de {result_path.name}; ese archivo se ignora.")

    products = sorted(
        products_from_results
        | {fill["product"] for fill in own_fills if fill.get("product")}
    )
    return result_rows_by_product, total_pnl_rows, products, sorted(result_kinds)


def _fill_price_series(
    series: dict[str, Any],
    timestamps: list[int],
    days: list[int],
    raw_timestamps: list[int],
    price_lookup: dict[tuple[int, int, str], ActivityRow],
    products: list[str],
) -> None:
    """Rellena las series de precios y order book desde los datos de mercado."""
    for product in products:
        s = series[product]
        for idx in range(len(timestamps)):
            day = days[idx]
            ts = raw_timestamps[idx]
            row = price_lookup.get((day, ts, product))
            if not row:
                continue
            s["bestBid"][idx] = row.bids[0]["price"] if row.bids else math.nan
            s["bestAsk"][idx] = row.asks[0]["price"] if row.asks else math.nan
            for lvl in range(3):
                s["bidPrices"][lvl][idx] = row.bids[lvl]["price"] if lvl < len(row.bids) else math.nan
                s["askPrices"][lvl][idx] = row.asks[lvl]["price"] if lvl < len(row.asks) else math.nan
            s["bidVol"][idx] = total_vol(row.bids)
            s["askVol"][idx] = total_vol(row.asks)
            total_ba = (s["bidVol"][idx] if _finite(s["bidVol"][idx]) else 0.0) + (
                s["askVol"][idx] if _finite(s["askVol"][idx]) else 0.0
            )
            s["imbalance"][idx] = (
                (s["bidVol"][idx] / total_ba) if total_ba > 0 and _finite(s["bidVol"][idx]) else math.nan
            )
            s["midPrice"][idx] = (
                row.mid_price
                if row.bids and row.asks and _finite(row.mid_price) and row.mid_price != 0
                else math.nan
            )
            s["microPrice"][idx] = micro_price_of(row.bids, row.asks)
            s["wallMid"][idx] = wall_mid_of(row.bids, row.asks)
            s["spread"][idx] = (
                s["bestAsk"][idx] - s["bestBid"][idx]
                if _finite(s["bestAsk"][idx]) and _finite(s["bestBid"][idx])
                else math.nan
            )
            s["books"][idx] = {"bids": row.bids, "asks": row.asks}


def _apply_result_rows(
    series: dict[str, Any],
    tick_to_idx: dict[int, int],
    total_pnl_rows: list[dict[str, Any]],
    result_rows_by_product: dict[str, list[dict[str, Any]]],
) -> None:
    """Aplica filas de resultados (PnL, posición) a las series."""
    for row in total_pnl_rows:
        idx = tick_to_idx.get(row["tickKey"])
        if idx is None:
            continue
        for product, value in row["perProductPnl"].items():
            if product in series:
                series[product]["pnl"][idx] = value

    for product, rows in result_rows_by_product.items():
        if product not in series:
            continue
        for row in rows:
            idx = tick_to_idx.get(row["tickKey"])
            if idx is None:
                continue
            if _finite(row.get("midPrice", math.nan)) and not _finite(series[product]["midPrice"][idx]):
                series[product]["midPrice"][idx] = row["midPrice"]
            series[product]["pnl"][idx] = row.get("pnl", math.nan)
            pos = row.get("position", math.nan)
            if _finite(pos):
                series[product]["position"][idx] = int(pos)


def _reconstruct_positions(
    series: dict[str, Any],
    own_fills: list[dict[str, Any]],
    timestamps: list[int],
    tick_to_idx: dict[int, int],
    products: list[str],
    result_rows_by_product: dict[str, list[dict[str, Any]]],
) -> list[dict[str, Any]]:
    """Reconstruye posiciones y volumen acumulado desde fills; retorna total_pnl forward-filled."""
    own_fill_indices: dict[tuple[str, int], list[int]] = defaultdict(list)
    for fill_idx, fill in enumerate(own_fills):
        pos = tick_to_idx.get(fill["tickKey"])
        if pos is None:
            insert_pos = bisect.bisect_left(timestamps, fill["tickKey"])
            pos = min(max(insert_pos, 0), len(timestamps) - 1)
        own_fill_indices[(fill["product"], pos)].append(fill_idx)

    pos_running: dict[str, int] = defaultdict(int)
    volume_running: dict[str, int] = defaultdict(int)
    fills_ptr = 0
    fills_sorted = sorted(own_fills, key=lambda row: (row["tickKey"], row["product"], row["price"], row["quantity"]))
    for idx, upper in enumerate(timestamps):
        while fills_ptr < len(fills_sorted) and fills_sorted[fills_ptr]["tickKey"] <= upper:
            fill = fills_sorted[fills_ptr]
            sign = 1 if fill["side"] == "buy" else -1
            pos_running[fill["product"]] += int(sign * fill["quantity"])
            volume_running[fill["product"]] += int(fill["quantity"])
            fills_ptr += 1
        for product in products:
            s = series[product]
            if product not in result_rows_by_product:
                s["position"][idx] = pos_running[product]
            s["cumOwnVolume"][idx] = volume_running[product]
            s["ownFillIndices"][idx] = own_fill_indices.get((product, idx), [])

    total_pnl = [0.0] * len(timestamps)
    for product in products:
        pnl = _forward_fill_zero(series[product]["pnl"])
        series[product]["pnl"] = pnl
        for idx, value in enumerate(pnl):
            total_pnl[idx] += value
    return total_pnl


def load_backtest_strategy(bundle: RunBundle) -> dict[str, Any]:
    warnings: list[str] = []

    fills_cache, own_fills = _load_fills(bundle, warnings)
    result_rows_by_product, total_pnl_rows, products, result_kinds = _load_results(
        bundle, fills_cache, own_fills, warnings
    )

    if not products:
        raise ValueError("No encontré productos válidos para este run de backtest.")

    fallback_ticks = [
        (row["day"], row["timestamp"])
        for row in total_pnl_rows
        if row.get("day") is not None and row.get("timestamp") is not None
    ]
    for rows in result_rows_by_product.values():
        fallback_ticks.extend((row["day"], row["timestamp"]) for row in rows)
    fallback_ticks.extend((fill["day"], fill["timestamp"]) for fill in own_fills)

    days_in_run = sorted({day for day, _ in fallback_ticks})
    price_rows, market_trades = load_round_market_data(bundle.root, bundle.round_name, days_in_run, warnings)
    timestamps, raw_timestamps, days, tick_to_idx, price_lookup = _index_ticks(price_rows, fallback_ticks, products)

    if not timestamps:
        raise ValueError("No pude construir timestamps para este run.")

    series = _make_empty_series(products, timestamps)
    _fill_price_series(series, timestamps, days, raw_timestamps, price_lookup, products)
    _apply_result_rows(series, tick_to_idx, total_pnl_rows, result_rows_by_product)
    total_pnl = _reconstruct_positions(series, own_fills, timestamps, tick_to_idx, products, result_rows_by_product)

    submission_trades = [
        {
            "timestamp": fill["timestamp"],
            "buyer": "SUBMISSION" if fill["side"] == "buy" else "",
            "seller": "SUBMISSION" if fill["side"] == "sell" else "",
            "symbol": fill["product"],
            "currency": "SEASHELLS",
            "price": fill["price"],
            "quantity": fill["quantity"],
            "day": fill["day"],
            "tickKey": fill["tickKey"],
            "source": fill.get("source"),
        }
        for fill in own_fills
    ]
    trades = sorted(
        market_trades + submission_trades,
        key=lambda row: (row["tickKey"], row.get("symbol", ""), row.get("price", 0.0), row.get("quantity", 0.0)),
    )

    return {
        "id": bundle.id,
        "name": bundle.name,
        "color": bundle.meta.get("color") or "#2dd4bf",
        "filename": str(bundle.primary_path.relative_to(bundle.root)),
        "source": {
            "kind": "backtest",
            "round": bundle.round_name,
            "resultFiles": [str(path.relative_to(bundle.root)) for path in bundle.result_files],
            "fillFiles": [str(path.relative_to(bundle.root)) for path in bundle.fill_files],
            "resultKinds": result_kinds,
        },
        "timestamps": timestamps,
        "rawTimestamps": raw_timestamps,
        "days": days,
        "products": products,
        "series": series,
        "totalPnl": total_pnl,
        "rawLogs": [],
        "ownFills": own_fills,
        "trades": trades,
        "logIndexByTick": {},
        "positionLimits": build_limits(products),
        "warnings": warnings,
        "loadedAt": bundle.meta.get("loadedAt"),
    }
