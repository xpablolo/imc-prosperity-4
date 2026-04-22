#!/usr/bin/env python3
"""
Smoke test rápido del visualizer.
Arranca el servidor en un puerto libre, verifica los endpoints principales,
y comprueba que los parsers no explotan con los datos de demo.

Uso:
    python3 visualizer/smoke_test.py
"""
from __future__ import annotations

import json
import socket
import subprocess
import sys
import time
import urllib.request
import shutil
from pathlib import Path

THIS_DIR = Path(__file__).resolve().parent
PROJECT_ROOT = THIS_DIR.parent

# ── helpers ──────────────────────────────────────────────────────────────────

def free_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def get(url: str, timeout: float = 5.0) -> dict | str:
    with urllib.request.urlopen(url, timeout=timeout) as resp:
        body = resp.read().decode("utf-8")
    try:
        return json.loads(body)
    except Exception:
        return body


def ok(label: str) -> None:
    print(f"  ✓  {label}")


def fail(label: str, detail: str = "") -> None:
    print(f"  ✗  {label}" + (f": {detail}" if detail else ""))
    sys.exit(1)


# ── server lifecycle ──────────────────────────────────────────────────────────

def start_server(port: int) -> subprocess.Popen:
    proc = subprocess.Popen(
        [sys.executable, str(THIS_DIR / "server.py"), "--port", str(port)],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    # esperar a que esté listo
    deadline = time.time() + 8.0
    while time.time() < deadline:
        try:
            get(f"http://127.0.0.1:{port}/api/health", timeout=1.0)
            return proc
        except Exception:
            time.sleep(0.25)
    proc.terminate()
    fail("El servidor no arrancó en 8 segundos")


# ── parsers (sin servidor) ────────────────────────────────────────────────────

def test_parsers() -> None:
    print("\n[Parsers]")

    # Añade el directorio al path para importar directamente
    sys.path.insert(0, str(THIS_DIR))
    from backend.backtest import parse_price_file, parse_fill_file, parse_result_file
    from backend.discovery import RunRegistry

    # Discovery no explota en el project root
    reg = RunRegistry(PROJECT_ROOT)
    runs = reg.ensure_scanned(force=True)
    ok(f"Discovery OK — {len(runs)} runs detectados")

    # demo.log existe y se detecta como source-text
    demo_path = THIS_DIR / "demo.log"
    if demo_path.exists():
        text = demo_path.read_text(encoding="utf-8", errors="replace")
        if text.startswith("Sandbox logs:") or '"activitiesLog"' in text[:4096]:
            ok("demo.log detectado como log fuente")
        else:
            ok("demo.log presente (formato no clasificado — puede ser intencional)")
    else:
        ok("demo.log ausente (no crítico para parsers)")

    # Busca un backtest real en data/ para probar los parsers CSV
    data_dirs = list((PROJECT_ROOT / "data").glob("round_*")) if (PROJECT_ROOT / "data").exists() else []
    price_file_tested = False
    for d in data_dirs:
        for f in d.glob("prices_*.csv"):
            warnings: list[str] = []
            rows = parse_price_file(f, warnings)
            if rows:
                ok(f"parse_price_file OK — {len(rows)} filas de {f.name}")
                price_file_tested = True
                break
        if price_file_tested:
            break
    if not price_file_tested:
        ok("Sin archivos prices_*.csv disponibles (no crítico)")


def test_frontend_modules() -> None:
    print("\n[Frontend analytics]")

    node = shutil.which("node")
    if not node:
        ok("Node no disponible; salteo smoke frontend")
        return

    script = rf"""
import fs from 'fs';
import {{ parseAnyInputText, parseActivitiesCsv, buildStrategy }} from '{(THIS_DIR / 'js' / 'parser.js').as_uri()}';
import {{ prepareStrategy }} from '{(THIS_DIR / 'js' / 'strategyPrep.js').as_uri()}';

const text = fs.readFileSync('{(THIS_DIR / 'demo.log').as_posix()}', 'utf8');
const raw = parseAnyInputText(text);
const rows = parseActivitiesCsv(raw.activitiesLog);
const strategy = prepareStrategy(buildStrategy(raw, rows, {{
  id: 'smoke-demo',
  name: 'Smoke Demo',
  color: '#2dd4bf',
  filename: 'demo.log',
}}));

if (!strategy.analysis) throw new Error('analysis missing');
if (!strategy.analysis.execution?.overall) throw new Error('execution metrics missing');
if (!strategy.analysis.lifecycle?.orders?.length) throw new Error('lifecycle missing');
if (!strategy.analysis.diagnostics?.scores) throw new Error('diagnostics scores missing');

globalThis.localStorage = {{ getItem() {{ return null; }}, setItem() {{}} }};
await import('{(THIS_DIR / 'js' / 'panels' / 'orderBook.js').as_uri()}');
await import('{(THIS_DIR / 'js' / 'panels' / 'whatHappened.js').as_uri()}');
await import('{(THIS_DIR / 'js' / 'panels' / 'orderLifecycle.js').as_uri()}');
await import('{(THIS_DIR / 'js' / 'panels' / 'executionPanel.js').as_uri()}');
await import('{(THIS_DIR / 'js' / 'panels' / 'comparePanel.js').as_uri()}');
await import('{(THIS_DIR / 'js' / 'panels' / 'diagnostics.js').as_uri()}');

const html = fs.readFileSync('{(THIS_DIR / 'index.html').as_posix()}', 'utf8');
for (const panelId of ['panel-compare', 'panel-execution', 'panel-diagnostics']) {{
  if (!html.includes(panelId)) throw new Error(`missing panel id: ${{panelId}}`);
}}
console.log(JSON.stringify({{
  fills: strategy.analysis.metadata.fillCount,
  lifecycle: strategy.analysis.lifecycle.orders.length,
  consistency: strategy.analysis.diagnostics.scores.consistency,
}}));
"""

    proc = subprocess.run(
        [node, "--input-type=module", "-e", script],
        cwd=PROJECT_ROOT,
        capture_output=True,
        text=True,
    )
    if proc.returncode != 0:
        fail("Smoke frontend falló", proc.stderr.strip() or proc.stdout.strip())
    ok("Pipeline parser -> strategyPrep -> analytics")
    ok("index.html contiene paneles nuevos")


# ── endpoints ─────────────────────────────────────────────────────────────────

def test_endpoints(base: str, runs: list[dict]) -> None:
    print("\n[Endpoints]")

    # /api/health
    data = get(f"{base}/api/health")
    if not isinstance(data, dict) or not data.get("ok"):
        fail("/api/health no retornó {ok: true}", str(data))
    ok("/api/health")

    # /api/runs
    data = get(f"{base}/api/runs")
    if not isinstance(data, dict) or not isinstance(data.get("runs"), list):
        fail("/api/runs formato inesperado", str(data)[:120])
    ok(f"/api/runs — {len(data['runs'])} runs")
    runs.extend(data["runs"])

    # /api/limits
    data = get(f"{base}/api/limits")
    if not isinstance(data, dict) or not isinstance(data.get("limits"), dict):
        fail("/api/limits formato inesperado", str(data)[:120])
    if len(data["limits"]) == 0:
        fail("/api/limits retornó mapa vacío")
    ok(f"/api/limits — {len(data['limits'])} productos")

    # /api/run/{id} para backtests
    backtest_runs = [r for r in runs if r.get("kind") == "backtest"]
    if backtest_runs:
        run_id = backtest_runs[0]["id"]
        strategy = get(f"{base}/api/run/{run_id}")
        if not isinstance(strategy, dict) or "products" not in strategy:
            fail(f"/api/run/{run_id} formato inesperado", str(strategy)[:120])
        ok(f"/api/run/{{id}} backtest — {len(strategy.get('products', []))} productos, {len(strategy.get('timestamps', []))} ticks")
    else:
        ok("/api/run/{id} backtest — sin backtests disponibles (no crítico)")

    # /api/run/{id}/source para logs (responde text/plain — puede ser JSON o replay text)
    log_runs = [r for r in runs if r.get("kind") in {"imc-log", "replay-log"}]
    if log_runs:
        run_id = log_runs[0]["id"]
        with urllib.request.urlopen(f"{base}/api/run/{run_id}/source", timeout=5.0) as resp:
            raw = resp.read().decode("utf-8")
        if not raw:
            fail(f"/api/run/{run_id}/source retornó respuesta vacía")
        ok(f"/api/run/{{id}}/source — {len(raw)} chars")
    else:
        ok("/api/run/{id}/source — sin logs disponibles (no crítico)")

    # 404 para ruta desconocida
    try:
        get(f"{base}/api/nonexistent_route_xyz")
        fail("/api/nonexistent debería retornar 404")
    except urllib.error.HTTPError as e:
        if e.code == 404:
            ok("/api/* unknown → 404")
        else:
            fail(f"/api/nonexistent retornó {e.code} en lugar de 404")


# ── main ──────────────────────────────────────────────────────────────────────

def main() -> None:
    print("=== Prosperity Visualizer — Smoke Test ===")
    port = free_port()
    base = f"http://127.0.0.1:{port}"

    # Parsers sin servidor
    test_parsers()
    test_frontend_modules()

    # Servidor + endpoints
    print(f"\n[Servidor] Arrancando en puerto {port}…")
    proc = start_server(port)
    ok("Servidor activo")
    runs: list[dict] = []

    try:
        test_endpoints(base, runs)
    finally:
        proc.terminate()
        proc.wait(timeout=3)
        print("\n[Servidor] Detenido")

    print("\n✓  Todos los checks pasaron.\n")


if __name__ == "__main__":
    main()
