from __future__ import annotations

import hashlib
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from .backtest import (
    ROUND0_FILLS_HEADER,
    ROUND0_RESULTS_HEADER,
    SIMPLE_RESULTS_HEADER,
    STANDARD_FILLS_HEADER,
    STANDARD_RESULTS_HEADER,
    RunBundle,
    load_backtest_strategy,
)

EXCLUDED_DIRS = {
    ".git",
    ".venv",
    ".venv_backtest",
    "node_modules",
    "target",
    "visualizer",
    "__pycache__",
}


@dataclass
class RunMeta:
    id: str
    kind: str
    load_mode: str
    name: str
    round_name: str | None
    rel_path: str
    mtime: float
    details: dict[str, Any]

    def to_json(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "kind": self.kind,
            "loadMode": self.load_mode,
            "name": self.name,
            "round": self.round_name,
            "path": self.rel_path,
            "mtime": self.mtime,
            **self.details,
        }


class RunRegistry:
    def __init__(self, root: Path):
        self.root = root
        self._runs: dict[str, RunMeta] = {}
        self._bundles: dict[str, RunBundle] = {}
        self._scan_cache_ts = 0.0
        self._normalized_cache: dict[str, dict[str, Any]] = {}

    def ensure_scanned(self, force: bool = False) -> list[RunMeta]:
        if force or (time.time() - self._scan_cache_ts) > 3:
            self._scan()
        return sorted(self._runs.values(), key=lambda meta: meta.mtime, reverse=True)

    def get_run(self, run_id: str) -> RunMeta | None:
        self.ensure_scanned(False)
        return self._runs.get(run_id)

    def load_source_text(self, run_id: str) -> str:
        meta = self.get_run(run_id)
        if not meta or meta.load_mode != "source-text":
            raise KeyError(run_id)
        return (self.root / meta.rel_path).read_text(encoding="utf-8", errors="replace")

    def load_normalized(self, run_id: str) -> dict[str, Any]:
        meta = self.get_run(run_id)
        bundle = self._bundles.get(run_id)
        if not meta or not bundle or meta.load_mode != "normalized":
            raise KeyError(run_id)
        cache = self._normalized_cache.get(run_id)
        if cache is not None:
            return cache
        strategy = load_backtest_strategy(bundle)
        self._normalized_cache[run_id] = strategy
        return strategy

    def _scan(self) -> None:
        self._runs = {}
        self._bundles = {}
        self._normalized_cache = {}
        backtest_groups: dict[tuple[str, str], dict[str, Any]] = {}

        for path in self._iter_files():
            suffix = path.suffix.lower()
            rel = str(path.relative_to(self.root))
            if suffix in {".log", ".json"}:
                meta = self._classify_logish(path)
                if meta:
                    self._runs[meta.id] = meta
                continue
            if suffix == ".csv":
                header = self._read_header(path)
                if header in {
                    ROUND0_RESULTS_HEADER,
                    STANDARD_RESULTS_HEADER,
                    SIMPLE_RESULTS_HEADER,
                    ROUND0_FILLS_HEADER,
                    STANDARD_FILLS_HEADER,
                }:
                    parent_rel = str(path.parent.relative_to(self.root))
                    run_key = derive_run_key(path.stem)
                    group = backtest_groups.setdefault(
                        (parent_rel, run_key),
                        {
                            "dir": path.parent,
                            "run_key": run_key,
                            "result_files": [],
                            "fill_files": [],
                            "round_name": infer_round_name(path),
                            "mtime": 0.0,
                        },
                    )
                    if header in {ROUND0_RESULTS_HEADER, STANDARD_RESULTS_HEADER, SIMPLE_RESULTS_HEADER}:
                        group["result_files"].append(path)
                    if header in {ROUND0_FILLS_HEADER, STANDARD_FILLS_HEADER}:
                        group["fill_files"].append(path)
                    group["mtime"] = max(group["mtime"], path.stat().st_mtime)

        for (parent_rel, run_key), group in backtest_groups.items():
            if not group["result_files"]:
                continue
            run_id = stable_id(f"backtest::{parent_rel}::{run_key}")
            name = prettify_run_name(run_key, group["dir"].name, group["round_name"])
            primary = sorted(group["result_files"])[0]
            meta = RunMeta(
                id=run_id,
                kind="backtest",
                load_mode="normalized",
                name=name,
                round_name=group["round_name"],
                rel_path=str(primary.relative_to(self.root)),
                mtime=group["mtime"],
                details={
                    "directory": parent_rel,
                    "resultCount": len(group["result_files"]),
                    "fillCount": len(group["fill_files"]),
                },
            )
            self._runs[run_id] = meta
            self._bundles[run_id] = RunBundle(
                id=run_id,
                name=name,
                round_name=group["round_name"] or "unknown_round",
                root=self.root,
                result_files=sorted(group["result_files"]),
                fill_files=sorted(group["fill_files"]),
                primary_path=primary,
                meta={"loadedAt": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())},
            )

        self._scan_cache_ts = time.time()

    def _iter_files(self):
        stack = [self.root]
        while stack:
            current = stack.pop()
            try:
                entries = list(current.iterdir())
            except Exception:
                continue
            for entry in entries:
                if entry.name in EXCLUDED_DIRS:
                    continue
                if entry.is_dir():
                    stack.append(entry)
                elif entry.is_file():
                    yield entry

    def _read_header(self, path: Path) -> str:
        try:
            with path.open("r", encoding="utf-8", errors="replace") as fh:
                return fh.readline().strip()
        except Exception:
            return ""

    def _classify_logish(self, path: Path) -> RunMeta | None:
        try:
            with path.open("r", encoding="utf-8", errors="replace") as fh:
                head = fh.read(4096)
        except Exception:
            return None
        rel = str(path.relative_to(self.root))
        round_name = infer_round_name(path)
        if head.startswith("Sandbox logs:"):
            kind = "replay-log"
            load_mode = "source-text"
        elif "\"activitiesLog\"" in head and head.lstrip().startswith("{"):
            kind = "imc-log"
            load_mode = "source-text"
        else:
            return None

        label = prettify_source_name(path)
        run_id = stable_id(f"{kind}::{rel}")
        return RunMeta(
            id=run_id,
            kind=kind,
            load_mode=load_mode,
            name=label,
            round_name=round_name,
            rel_path=rel,
            mtime=path.stat().st_mtime,
            details={},
        )


# ---------- naming helpers ----------


def stable_id(value: str) -> str:
    return hashlib.sha1(value.encode("utf-8")).hexdigest()[:12]



def infer_round_name(path: Path) -> str | None:
    for part in path.parts:
        if part.startswith("round_"):
            return part
    return None



def derive_run_key(stem: str) -> str:
    if "_results_" in stem:
        return stem.split("_results_", 1)[0]
    if stem.endswith("_results"):
        return stem[: -len("_results")]
    if "_fills_" in stem:
        return stem.split("_fills_", 1)[0]
    if stem.endswith("_fills"):
        return stem[: -len("_fills")]
    return stem



def prettify_run_name(run_key: str, dir_name: str, round_name: str | None) -> str:
    base = run_key
    if base.startswith("backtest_"):
        base = base[len("backtest_") :]
    if base == dir_name:
        label = dir_name
    elif dir_name.startswith("eval_"):
        label = f"{dir_name} · {base}"
    else:
        label = f"{dir_name} · {base}" if dir_name != base else base
    label = label.replace("__", "_").strip("_")
    return f"{round_name} · {label}" if round_name else label



def prettify_source_name(path: Path) -> str:
    stem = path.stem
    parent = path.parent.name
    if parent and parent not in {"results", "logs", "data", path.anchor}:
        return f"{parent} · {stem}"
    return stem
