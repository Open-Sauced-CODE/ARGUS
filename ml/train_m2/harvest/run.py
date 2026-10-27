"""Harvest runner: generate candidates with logprobs for the M2 trust engine.

Usage (PowerShell, repo root):
    python -m ml.train_m2.harvest.run --generator sft --model argus-m1-sft --profile A --threads 4 --top-logprobs 5

Output: ml/train_m2/harvest_out/<generator>/<profile>/part-NNNN.jsonl  (+ MANIFEST.json, and a copy of the
manifest in ml/train_m2/harvest_manifests/<generator>_<profile>.json).

Properties (contract m2.harvest.v1):
  * one line per (input_key, sample_idx), validated against harvest_line.schema.json BEFORE it is written
  * failures are recorded as error lines (content "", tokens []), never dropped
  * RESUMABLE: finished (input_key, sample_idx) pairs are skipped; run the same command again after any stop
  * one writer thread (flush + fsync per line); worker threads only call Ollama
"""

from __future__ import annotations

import argparse
import json
import logging
import platform
import queue
import subprocess
import sys
import threading
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from importlib import metadata
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Sequence, Tuple

from ml.train_m2.harvest.client import (DEFAULT_HOST, DEFAULT_NUM_PREDICT, DEFAULT_TIMEOUT, chat_once_v2,
                                         ollama_meta)
from ml.train_m2.harvest.paths import DEFAULT_MANIFEST_DIR, DEFAULT_OUT, INPUTS_PATH, REPO_ROOT, SCHEMA_PATH
from ml.train_m2.harvest.profiles import GENERATORS, N_SAMPLES, PROFILES, SCHEMA_VERSION, sample_params
from ml.train_m2.harvest.schema import validate_line
from ml.train_m2.harvest.store import (DEFAULT_PART_SIZE, SHARD_STRIDE, PartWriter, drop_error_lines,
                                       part_files, repair_truncated_tail, scan_folder, sha256_file, write_json,
                                       count_lines)

logger = logging.getLogger("harvest")

ERROR_RATE_WARNING = 0.02


class HarvestError(RuntimeError):
    """A problem the operator must fix (bad arguments, mixed models in one folder, too many errors)."""


@dataclass
class HarvestConfig:
    generator: str
    model: str
    profile: str
    out_root: Path = DEFAULT_OUT
    manifest_dir: Path = DEFAULT_MANIFEST_DIR
    host: str = DEFAULT_HOST
    threads: int = 1
    top_logprobs: int = 0
    num_predict: int = DEFAULT_NUM_PREDICT
    timeout: float = DEFAULT_TIMEOUT
    limit: Optional[int] = None
    stratify: bool = False
    shard: Tuple[int, int] = (0, 1)
    n_samples: int = N_SAMPLES
    temperature_override: Optional[float] = None
    retry_errors: bool = False
    strip_pattern: bool = False
    part_size: int = DEFAULT_PART_SIZE
    max_consecutive_errors: int = 20
    progress_every: int = 50


@dataclass
class RunSummary:
    folder: Path
    manifest_path: Path
    jobs_total: int = 0
    lines_written: int = 0
    errors_this_run: int = 0
    wall_seconds: float = 0.0
    gens_per_hour: float = 0.0
    folder_stats: Dict[str, Any] = field(default_factory=dict)
    complete: bool = False
    dropped_error_lines: int = 0
    repaired_bytes: int = 0


# ---------------------------------------------------------------------------------------------------------
# inputs
# ---------------------------------------------------------------------------------------------------------

def load_inputs(path: Path = INPUTS_PATH) -> List[Dict[str, Any]]:
    """Read harvest_inputs.jsonl (never edited). Returns list of dicts with input_key, record, sets."""
    inputs: List[Dict[str, Any]] = []
    seen = set()
    with open(path, "rb") as handle:
        for number, raw in enumerate(handle, 1):
            if not raw.strip():
                continue
            item = json.loads(raw.decode("utf-8"))
            for name in ("input_key", "record"):
                if name not in item:
                    raise HarvestError("%s line %d has no %r" % (path, number, name))
            if item["input_key"] in seen:
                raise HarvestError("%s line %d repeats input_key %s" % (path, number, item["input_key"][:60]))
            seen.add(item["input_key"])
            inputs.append(item)
    if not inputs:
        raise HarvestError("%s is empty" % path)
    return inputs


def stratified_pick(inputs: Sequence[Dict[str, Any]], n: int) -> List[Dict[str, Any]]:
    """Deterministic round-robin across rule_id (rules sorted, inputs sorted by input_key inside each rule)."""
    by_rule: Dict[str, List[Dict[str, Any]]] = {}
    for item in inputs:
        by_rule.setdefault(str(item["record"].get("rule_id", "")), []).append(item)
    for rule in by_rule:
        by_rule[rule].sort(key=lambda x: x["input_key"])
    rules = sorted(by_rule)
    picked: List[Dict[str, Any]] = []
    depth = 0
    deepest = max(len(v) for v in by_rule.values())
    while len(picked) < n and depth < deepest:
        for rule in rules:
            if len(picked) >= n:
                break
            if depth < len(by_rule[rule]):
                picked.append(by_rule[rule][depth])
        depth += 1
    return picked


def select_inputs(inputs: Sequence[Dict[str, Any]], limit: Optional[int], stratify: bool,
                  shard: Tuple[int, int]) -> List[Dict[str, Any]]:
    """Apply --limit/--stratify first, then --shard i/n (inputs sorted by key; index % n == i)."""
    index, count = shard
    if count < 1 or not 0 <= index < count:
        raise HarvestError("--shard must look like i/n with 0 <= i < n, got %d/%d" % (index, count))
    chosen = list(inputs)
    if limit is not None:
        if limit < 1:
            raise HarvestError("--limit must be at least 1")
        chosen = stratified_pick(chosen, limit) if stratify else chosen[:limit]
    chosen.sort(key=lambda x: x["input_key"])
    return [item for i, item in enumerate(chosen) if i % count == index]


# ---------------------------------------------------------------------------------------------------------
# prompt tools (frozen Phase 5 module)
# ---------------------------------------------------------------------------------------------------------

def strip_pattern(obj: Any) -> Any:
    """Return a copy of a JSON schema without `pattern` keywords (fallback if the server rejects them)."""
    if isinstance(obj, dict):
        return {k: strip_pattern(v) for k, v in obj.items() if not (k == "pattern" and isinstance(v, str))}
    if isinstance(obj, list):
        return [strip_pattern(v) for v in obj]
    return obj


def default_prompt_tools(strip: bool = False) -> Tuple[Callable[[Dict[str, Any]], List[Dict[str, Any]]], Dict[str, Any]]:
    """(chat_messages, schema) from the frozen ml.train_m1.prompt module."""
    try:
        from ml.train_m1.prompt import chat_messages, load_schema
    except ImportError as exc:
        raise HarvestError("cannot import chat_messages/load_schema from ml.train_m1.prompt: %s" % exc)
    schema = load_schema()
    return chat_messages, (strip_pattern(schema) if strip else schema)


# ---------------------------------------------------------------------------------------------------------
# helpers
# ---------------------------------------------------------------------------------------------------------

def _utc_now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _git(*args: str) -> Optional[str]:
    try:
        out = subprocess.run(["git"] + list(args), cwd=str(REPO_ROOT), capture_output=True, text=True, timeout=20)
        return out.stdout.strip() if out.returncode == 0 else None
    except (OSError, subprocess.SubprocessError):
        return None


def _version(package: str) -> Optional[str]:
    try:
        return metadata.version(package)
    except metadata.PackageNotFoundError:
        return None


def _is_inside(path: Path, parent: Path) -> bool:
    try:
        Path(path).resolve().relative_to(Path(parent).resolve())
        return True
    except ValueError:
        return False


def _put(q: "queue.Queue[Any]", item: Any, stop: threading.Event) -> bool:
    """Put with back-pressure; give up (False) only if a fatal error asked everyone to stop."""
    while True:
        try:
            q.put(item, timeout=0.2)
            return True
        except queue.Full:
            if stop.is_set():
                return False


def _fmt_eta(seconds: float) -> str:
    seconds = int(max(0, seconds))
    return "%dh%02dm" % (seconds // 3600, (seconds % 3600) // 60)


def _check_config(cfg: HarvestConfig) -> None:
    if cfg.generator not in GENERATORS:
        raise HarvestError("--generator must be one of %s" % (GENERATORS,))
    if cfg.profile not in PROFILES:
        raise HarvestError("--profile must be one of %s" % (PROFILES,))
    if cfg.threads < 1:
        raise HarvestError("--threads must be at least 1")
    if not 1 <= cfg.n_samples <= N_SAMPLES:
        raise HarvestError("--samples must be between 1 and %d" % N_SAMPLES)
    if cfg.top_logprobs < 0 or cfg.top_logprobs > 20:
        raise HarvestError("--top-logprobs must be between 0 and 20")
    if cfg.temperature_override is not None and _is_inside(cfg.out_root, DEFAULT_OUT):
        raise HarvestError("--temp-override is a local experiment: use an --out folder outside %s" % DEFAULT_OUT)
    if cfg.shard[1] > 9:
        raise HarvestError("at most 9 shards are supported")


# ---------------------------------------------------------------------------------------------------------
# manifest
# ---------------------------------------------------------------------------------------------------------

def write_manifest(cfg: HarvestConfig, folder: Path, meta: Dict[str, Any], all_inputs: Sequence[Dict[str, Any]],
                   run_record: Dict[str, Any], inputs_path: Path, schema_path: Path) -> Tuple[Path, Dict[str, Any]]:
    """Write MANIFEST.json (in the data folder) and a copy in the manifest dir. Reflects the WHOLE folder."""
    stats = scan_folder(folder)
    expected = {(item["input_key"], i) for item in all_inputs for i in range(N_SAMPLES)}
    previous: List[Dict[str, Any]] = []
    existing = folder / "MANIFEST.json"
    if existing.exists():
        try:
            previous = list(json.loads(existing.read_text(encoding="utf-8")).get("runs", []))
        except ValueError:
            previous = []
    parts = [{"file": p.name, "lines": count_lines(p), "sha256": sha256_file(p)} for p in part_files(folder)]
    manifest = {
        "schema_version": SCHEMA_VERSION,
        "generator": cfg.generator,
        "profile": cfg.profile,
        "model": cfg.model,
        "model_digest": meta.get("model_digest"),
        "model_digests_seen_in_files": stats["digests"],
        "ollama_version": meta.get("version"),
        "ollama_versions_seen_in_files": stats["ollama_versions"],
        "top_logprobs_requested": cfg.top_logprobs,
        "num_predict": cfg.num_predict,
        "inputs_in_contract": len(all_inputs),
        "samples_per_input": N_SAMPLES,
        "lines_expected": len(expected),
        "lines_total": stats["lines"],
        "errors": stats["errors"],
        "error_rate": round(stats["errors"] / stats["lines"], 6) if stats["lines"] else 0.0,
        "text_token_mismatches": stats["text_token_mismatches"],
        "success_lines_without_top_alternatives": stats["lines_without_top"],
        "success_lines_cut_by_num_predict": stats["truncated_by_length"],
        "duplicate_keys": stats["duplicates"],
        "complete": expected <= stats["done"] and stats["duplicates"] == 0,
        "parts": parts,
        "runs": previous + [run_record],
        "provenance": {
            "git_commit": _git("rev-parse", "HEAD"),
            "git_dirty": bool(_git("status", "--porcelain")),
            "python": platform.python_version(),
            "platform": platform.platform(),
            "requests": _version("requests"),
            "jsonschema": _version("jsonschema"),
            "inputs_sha256": sha256_file(inputs_path) if inputs_path.exists() else None,
            "schema_sha256": sha256_file(schema_path) if schema_path.exists() else None,
        },
    }
    write_json(existing, manifest)
    copy_path = cfg.manifest_dir / ("%s_%s.json" % (cfg.generator, cfg.profile))
    write_json(copy_path, manifest)
    return copy_path, manifest


# ---------------------------------------------------------------------------------------------------------
# the run
# ---------------------------------------------------------------------------------------------------------

def run_harvest(
    cfg: HarvestConfig,
    *,
    inputs_path: Path = INPUTS_PATH,
    schema_path: Path = SCHEMA_PATH,
    messages_fn: Optional[Callable[[Dict[str, Any]], List[Dict[str, Any]]]] = None,
    schema: Optional[Dict[str, Any]] = None,
    chat_fn: Callable[..., Dict[str, Any]] = chat_once_v2,
    meta_fn: Callable[..., Dict[str, Any]] = ollama_meta,
    command: Optional[str] = None,
) -> RunSummary:
    """Generate every missing (input, sample) for this (generator, profile). See the module docstring."""
    _check_config(cfg)
    if messages_fn is None or schema is None:
        default_messages, default_schema = default_prompt_tools(cfg.strip_pattern)
        messages_fn = messages_fn or default_messages
        schema = schema if schema is not None else default_schema

    all_inputs = load_inputs(inputs_path)
    selected = select_inputs(all_inputs, cfg.limit, cfg.stratify, cfg.shard)
    folder = Path(cfg.out_root) / cfg.generator / cfg.profile
    folder.mkdir(parents=True, exist_ok=True)

    repaired = sum(repair_truncated_tail(p) for p in part_files(folder))
    if repaired:
        logger.warning("removed %d bytes of an unfinished last line left by an earlier stop", repaired)
    dropped = drop_error_lines(folder) if cfg.retry_errors else 0
    if dropped:
        logger.info("--retry-errors: removed %d earlier error lines so they are generated again", dropped)

    before = scan_folder(folder)
    if before["duplicates"]:
        raise HarvestError("%s already has %d duplicate (input_key, sample_idx) lines; fix them first" % (folder, before["duplicates"]))
    if before["models"] and set(before["models"]) != {cfg.model}:
        raise HarvestError("%s holds lines from model(s) %s but you asked for %r. One folder = one model."
                           % (folder, before["models"], cfg.model))

    meta = meta_fn(cfg.host, cfg.model)
    if before["digests"] and meta.get("model_digest") and meta["model_digest"] not in before["digests"]:
        logger.warning("model digest changed since earlier lines (%s -> %s). The files mix two builds of %s.",
                       before["digests"], meta["model_digest"], cfg.model)

    done = before["done"]
    jobs: "queue.Queue[Tuple[str, Dict[str, Any], int]]" = queue.Queue()
    total_jobs = 0
    for item in selected:
        for idx in range(cfg.n_samples):
            if (item["input_key"], idx) not in done:
                jobs.put((item["input_key"], item["record"], idx))
                total_jobs += 1
    logger.info("%s/%s: %d inputs selected, %d generations to do (%d already done), threads=%d",
                cfg.generator, cfg.profile, len(selected), total_jobs, len(done), cfg.threads)

    started_utc = _utc_now()
    t0 = time.monotonic()
    results: "queue.Queue[Dict[str, Any]]" = queue.Queue(maxsize=max(8, cfg.threads * 4))
    stop = threading.Event()
    workers_done = threading.Event()
    fatal: List[BaseException] = []
    fatal_lock = threading.Lock()
    counters = {"written": 0, "errors": 0}

    def set_fatal(exc: BaseException) -> None:
        with fatal_lock:
            fatal.append(exc)
        stop.set()

    def make_line(key: str, record: Dict[str, Any], idx: int) -> Dict[str, Any]:
        params = sample_params(cfg.profile, idx, cfg.temperature_override)
        result = chat_fn(
            cfg.model, record, temperature=params.temperature, top_p=params.top_p, seed=params.seed, host=cfg.host,
            num_predict=cfg.num_predict, top_logprobs=cfg.top_logprobs, timeout=cfg.timeout,
            messages=messages_fn(record), schema=schema,
        )
        failed = result.get("error") is not None
        return {
            "schema_version": SCHEMA_VERSION,
            "input_key": key,
            "generator": cfg.generator,
            "profile": cfg.profile,
            "sample_idx": idx,
            "temperature": params.temperature,
            "top_p": params.top_p,
            "seed": params.seed,
            "model": cfg.model,
            "model_digest": meta.get("model_digest"),
            "ollama_version": meta.get("version") or "unknown",
            "content": "" if failed else result["content"],
            "error": result.get("error"),
            "eval_count": int(result.get("eval_count") or 0),
            "seconds": round(float(result.get("seconds") or 0.0), 3),
            "done_reason": result.get("done_reason"),
            "tokens": [] if failed else result["tokens"],
        }

    def worker() -> None:
        while not stop.is_set():
            try:
                key, record, idx = jobs.get_nowait()
            except queue.Empty:
                return
            try:
                line = make_line(key, record, idx)
                validate_line(line, schema_path)  # a failure here is a bug in the tool: raise, never skip
            except Exception as exc:  # noqa: BLE001 - includes LogprobsUnavailable and schema errors
                set_fatal(exc)
                return
            if not _put(results, line, stop):
                return

    def writer() -> None:
        part_writer = PartWriter(folder, base_index=cfg.shard[0] * SHARD_STRIDE, part_size=cfg.part_size)
        consecutive = 0
        try:
            while True:
                try:
                    line = results.get(timeout=0.2)
                except queue.Empty:
                    if workers_done.is_set():
                        break
                    continue
                part_writer.write(line)
                counters["written"] += 1
                if line["error"] is not None:
                    counters["errors"] += 1
                    consecutive += 1
                    if consecutive >= cfg.max_consecutive_errors:
                        set_fatal(HarvestError(
                            "%d errors in a row (last: %s). Ollama is probably down, stuck or out of memory. "
                            "Fix it, then run the same command again with --retry-errors."
                            % (consecutive, line["error"][:120])))
                        consecutive = 0
                else:
                    consecutive = 0
                if counters["written"] % cfg.progress_every == 0:
                    elapsed = max(time.monotonic() - t0, 1e-6)
                    rate = counters["written"] / elapsed * 3600.0
                    remaining = total_jobs - counters["written"]
                    logger.info("progress %d/%d | errors %d | %.0f generations/hour | ETA %s",
                                counters["written"], total_jobs, counters["errors"], rate,
                                _fmt_eta(remaining / rate * 3600.0) if rate > 0 else "?")
        except Exception as exc:  # noqa: BLE001
            set_fatal(exc)
        finally:
            part_writer.close()

    worker_threads = [threading.Thread(target=worker, name="worker-%d" % i, daemon=True) for i in range(cfg.threads)]
    writer_thread = threading.Thread(target=writer, name="writer", daemon=True)
    interrupted = False
    writer_thread.start()
    try:
        for t in worker_threads:
            t.start()
        while any(t.is_alive() for t in worker_threads):
            for t in worker_threads:
                t.join(timeout=0.5)
    except KeyboardInterrupt:
        interrupted = True
        stop.set()
        logger.warning("Ctrl+C: finishing in-flight requests, then stopping. Press Ctrl+C again to abort now.")
    finally:
        while any(t.is_alive() for t in worker_threads):
            for t in worker_threads:
                t.join(timeout=0.5)
        workers_done.set()
        while writer_thread.is_alive():
            writer_thread.join(timeout=0.5)

    wall = time.monotonic() - t0
    rate = counters["written"] / wall * 3600.0 if wall > 0 else 0.0
    run_record = {
        "started_utc": started_utc,
        "finished_utc": _utc_now(),
        "command": command or "python -m ml.train_m2.harvest.run (called from code)",
        "lines_written": counters["written"],
        "errors": counters["errors"],
        "threads": cfg.threads,
        "wall_seconds": round(wall, 1),
        "generations_per_hour": round(rate, 1),
        "stopped_early": bool(fatal) or interrupted,
        "removed_error_lines_before_run": dropped,
        "shard": "%d/%d" % cfg.shard,
        "limit": cfg.limit,
        "stratify": cfg.stratify,
        "temperature_override": cfg.temperature_override,
    }
    manifest_path, manifest = write_manifest(cfg, folder, meta, all_inputs, run_record, inputs_path, schema_path)

    summary = RunSummary(
        folder=folder, manifest_path=manifest_path, jobs_total=total_jobs, lines_written=counters["written"],
        errors_this_run=counters["errors"], wall_seconds=wall, gens_per_hour=rate,
        folder_stats={k: v for k, v in manifest.items() if k in
                      ("lines_total", "errors", "error_rate", "text_token_mismatches", "complete")},
        complete=bool(manifest["complete"]), dropped_error_lines=dropped, repaired_bytes=repaired,
    )
    if fatal:
        raise fatal[0]
    if interrupted:
        raise KeyboardInterrupt()
    return summary


# ---------------------------------------------------------------------------------------------------------
# command line
# ---------------------------------------------------------------------------------------------------------

def _parse_shard(text: str) -> Tuple[int, int]:
    try:
        left, right = text.split("/")
        return int(left), int(right)
    except ValueError:
        raise argparse.ArgumentTypeError("--shard must look like 0/1 or 1/2")


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="python -m ml.train_m2.harvest.run", description=__doc__.split("\n")[0])
    p.add_argument("--generator", required=True, choices=GENERATORS)
    p.add_argument("--model", required=True, help="Ollama model name, e.g. argus-m1-sft")
    p.add_argument("--profile", required=True, choices=PROFILES)
    p.add_argument("--threads", type=int, default=1)
    p.add_argument("--top-logprobs", type=int, default=0, help="alternatives per token to record (contract run uses 5)")
    p.add_argument("--out", type=Path, default=DEFAULT_OUT)
    p.add_argument("--manifest-dir", type=Path, default=None, help="default: ml/train_m2/harvest_manifests (or <out>/manifests if --out is not the default)")
    p.add_argument("--limit", type=int, default=None)
    p.add_argument("--stratify", action="store_true", help="with --limit: round-robin across rule_id")
    p.add_argument("--shard", type=_parse_shard, default=(0, 1), help="i/n: process only the i-th of n slices of the inputs")
    p.add_argument("--samples", type=int, default=N_SAMPLES, help="samples per input (contract: 8)")
    p.add_argument("--num-predict", type=int, default=DEFAULT_NUM_PREDICT)
    p.add_argument("--timeout", type=float, default=DEFAULT_TIMEOUT, help="seconds per request")
    p.add_argument("--host", default=DEFAULT_HOST)
    p.add_argument("--temp-override", type=float, default=None, help="LOCAL EXPERIMENT ONLY: temperature for samples 1-7")
    p.add_argument("--retry-errors", action="store_true", help="delete earlier error lines and generate them again")
    p.add_argument("--strip-pattern", action="store_true", help="remove `pattern` from the Patch-IR schema sent to Ollama")
    p.add_argument("--max-consecutive-errors", type=int, default=20)
    return p


def main(argv: Optional[Sequence[str]] = None, *, messages_fn=None, schema=None, chat_fn=None, meta_fn=None) -> int:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(message)s", datefmt="%H:%M:%S", stream=sys.stdout)
    args_list = list(sys.argv[1:] if argv is None else argv)
    args = build_parser().parse_args(args_list)
    out = Path(args.out)
    manifest_dir = args.manifest_dir
    if manifest_dir is None:
        manifest_dir = DEFAULT_MANIFEST_DIR if out.resolve() == DEFAULT_OUT.resolve() else out / "manifests"
    cfg = HarvestConfig(
        generator=args.generator, model=args.model, profile=args.profile, out_root=out, manifest_dir=Path(manifest_dir),
        host=args.host, threads=args.threads, top_logprobs=args.top_logprobs, num_predict=args.num_predict,
        timeout=args.timeout, limit=args.limit, stratify=args.stratify, shard=args.shard, n_samples=args.samples,
        temperature_override=args.temp_override, retry_errors=args.retry_errors, strip_pattern=args.strip_pattern,
        max_consecutive_errors=args.max_consecutive_errors,
    )
    kwargs: Dict[str, Any] = {"messages_fn": messages_fn, "schema": schema,
                              "command": "python -m ml.train_m2.harvest.run " + " ".join(args_list)}
    if chat_fn is not None:
        kwargs["chat_fn"] = chat_fn
    if meta_fn is not None:
        kwargs["meta_fn"] = meta_fn
    try:
        summary = run_harvest(cfg, **kwargs)
    except KeyboardInterrupt:
        print("Stopped. Run the same command again to resume.")
        return 130
    except Exception as exc:  # noqa: BLE001 - show a clean message, keep the exit code non-zero
        print("HARVEST STOPPED: %s: %s" % (type(exc).__name__, exc))
        print("Finished lines are saved. Fix the problem, then run the same command again to resume.")
        return 2
    stats = summary.folder_stats
    print("")
    print("Folder           : %s" % summary.folder)
    print("Lines written now: %d (errors %d) in %.0f s = %.0f generations/hour"
          % (summary.lines_written, summary.errors_this_run, summary.wall_seconds, summary.gens_per_hour))
    print("Folder total     : %d lines, error rate %.2f%%, text/token mismatches %d, complete=%s"
          % (stats["lines_total"], 100.0 * stats["error_rate"], stats["text_token_mismatches"], stats["complete"]))
    print("Manifest         : %s" % summary.manifest_path)
    if stats["error_rate"] > ERROR_RATE_WARNING:
        print("WARNING: error rate above 2%%. Stop and check Ollama, then re-run with --retry-errors.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
