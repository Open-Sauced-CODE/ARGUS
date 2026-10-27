"""Pilot for handoff H1: prove the harvest works on this machine, measure speed, check replication.

Sub-commands (PowerShell, repo root):
    python -m ml.train_m2.harvest.pilot a            profile A, 20 stratified inputs, zeroshot+sft+rft, replication + diversity
    python -m ml.train_m2.harvest.pilot throughput --label parallel4     60 generations at 1, 2 and 4 threads
    python -m ml.train_m2.harvest.pilot b            profile B (T=1.0 contract, plus local T=1.2 and T=1.4) for sft and rft
    python -m ml.train_m2.harvest.pilot report       writes docs/phase6_prabhav/pilot_report.md from the saved numbers

All pilot data goes to ml/train_m1/v2/out/pilot/ (git-ignored). Nothing here writes to the contract folders.
Numbers are saved in pilot_results.json so each step can be run on its own and the report is built from facts.
"""

from __future__ import annotations

import argparse
import json
import logging
import shutil
import sys
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Sequence, Tuple

import jsonschema

from ml.train_m2.harvest.client import DEFAULT_HOST, DEFAULT_NUM_PREDICT, DEFAULT_TIMEOUT, chat_once_v2, ollama_meta
from ml.train_m2.harvest.paths import (DOCS_DIR, INPUTS_PATH, PATCH_IR_SCHEMA, PHASE5_RUNS, PILOT_DIR,
                                       SCHEMA_PATH)
from ml.train_m2.harvest.run import HarvestConfig, default_prompt_tools, run_harvest
from ml.train_m2.harvest.store import iter_lines

logger = logging.getLogger("pilot")

GENERATOR_MODELS = {"zeroshot": "qwen3.5:4b", "sft": "argus-m1-sft", "rft": "argus-m1-rft"}
PHASE5_DIVERSITY = {"rft": "1.00-1.06", "sft": "1.1-1.9", "zeroshot": "5.7-7.8"}
PILOT_INPUTS = 20
TEMPERATURES_B = (1.0, 1.2, 1.4)
THROUGHPUT_THREADS = (1, 2, 4)
THROUGHPUT_JOBS_PER_INPUT = 3  # 20 inputs x 3 samples = 60 generations


# ---------------------------------------------------------------------------------------------------------
# pure functions (unit tested)
# ---------------------------------------------------------------------------------------------------------

def canonical_answer(content: str) -> str:
    """Canonical form of an answer: ops plus rationale_ref, finding_id ignored. Invalid JSON -> 'INVALID:<text>'."""
    try:
        data = json.loads(content)
        if not isinstance(data, dict):
            raise ValueError("not an object")
        return json.dumps({"ops": data.get("ops"), "rationale_ref": data.get("rationale_ref")}, sort_keys=True,
                          separators=(",", ":"))
    except ValueError:
        return "INVALID:" + content


def distinct_count(contents: Sequence[str]) -> int:
    return len({canonical_answer(c) for c in contents})


def mean_distinct(by_input: Dict[str, Dict[int, str]]) -> float:
    """Mean number of distinct canonical answers per input (over the samples that exist)."""
    if not by_input:
        return 0.0
    return sum(distinct_count(list(v.values())) for v in by_input.values()) / len(by_input)


def match_rates(new: Dict[str, Dict[int, str]], phase5: Dict[str, List[str]]) -> Dict[str, Any]:
    """Compare new contents with the Phase 5 candidate logs, per sample index.

    new: input_key -> {sample_idx: content}; phase5: input_key -> [content x 8].
    exact = identical text; canonical = identical ops + rationale_ref (finding_id ignored).
    """
    exact_by: Dict[int, List[bool]] = {}
    canon_by: Dict[int, List[bool]] = {}
    for key, samples in new.items():
        old = phase5.get(key)
        if not old:
            continue
        for idx, content in samples.items():
            if idx >= len(old):
                continue
            exact_by.setdefault(idx, []).append(content == old[idx])
            canon_by.setdefault(idx, []).append(canonical_answer(content) == canonical_answer(old[idx]))

    def rate(values: List[bool]) -> Optional[float]:
        return round(sum(values) / len(values), 4) if values else None

    all_exact = [v for vs in exact_by.values() for v in vs]
    all_canon = [v for vs in canon_by.values() for v in vs]
    return {
        "n_compared": len(all_exact),
        "exact_overall": rate(all_exact),
        "canonical_overall": rate(all_canon),
        "exact_by_idx": {str(i): rate(v) for i, v in sorted(exact_by.items())},
        "canonical_by_idx": {str(i): rate(v) for i, v in sorted(canon_by.items())},
        "inputs_without_phase5_log": sum(1 for k in new if k not in phase5),
    }


def schema_valid_share(contents: Sequence[str], patch_schema: Dict[str, Any]) -> float:
    """Share of contents that are JSON and validate against the Patch-IR schema."""
    if not contents:
        return 0.0
    validator = jsonschema.Draft202012Validator(patch_schema) if hasattr(jsonschema, "Draft202012Validator") \
        else jsonschema.Draft7Validator(patch_schema)
    good = 0
    for text in contents:
        try:
            if not list(validator.iter_errors(json.loads(text))):
                good += 1
        except ValueError:
            pass
    return round(good / len(contents), 4)


def contents_from_folder(folder: Path) -> Tuple[Dict[str, Dict[int, str]], Dict[str, Any]]:
    """Success contents by input and sample index, plus simple stats of the folder."""
    by_input: Dict[str, Dict[int, str]] = {}
    lines = errors = 0
    seconds: List[float] = []
    evals: List[int] = []
    for _path, line in iter_lines(folder):
        lines += 1
        if line["error"] is not None:
            errors += 1
            continue
        by_input.setdefault(line["input_key"], {})[line["sample_idx"]] = line["content"]
        seconds.append(float(line["seconds"]))
        evals.append(int(line["eval_count"]))
    return by_input, {
        "lines": lines, "errors": errors, "error_rate": round(errors / lines, 6) if lines else 0.0,
        "mean_seconds_per_generation": round(sum(seconds) / len(seconds), 3) if seconds else None,
        "mean_eval_count": round(sum(evals) / len(evals), 1) if evals else None,
    }


def load_phase5_contents(generator: str, runs_dir: Path = PHASE5_RUNS) -> Tuple[Dict[str, List[str]], int]:
    """input_key -> contents[8] from ml/train_m1/eval/runs/<generator>/*.candidates.jsonl.

    Returns (mapping, number of inputs whose logs disagree between files). First file wins.
    """
    mapping: Dict[str, List[str]] = {}
    conflicts = 0
    folder = Path(runs_dir) / generator
    for path in sorted(folder.glob("*.candidates.jsonl")) if folder.is_dir() else []:
        with open(path, "rb") as handle:
            for raw in handle:
                if not raw.strip():
                    continue
                item = json.loads(raw.decode("utf-8"))
                key, contents = item.get("input_key"), item.get("contents")
                if not isinstance(key, str) or not isinstance(contents, list):
                    continue
                if key in mapping:
                    if mapping[key] != contents:
                        conflicts += 1
                else:
                    mapping[key] = contents
    return mapping, conflicts


# ---------------------------------------------------------------------------------------------------------
# results file
# ---------------------------------------------------------------------------------------------------------

def load_results(pilot_dir: Path) -> Dict[str, Any]:
    path = Path(pilot_dir) / "pilot_results.json"
    if path.exists():
        return json.loads(path.read_text(encoding="utf-8"))
    return {"profile_a": {}, "throughput": [], "profile_b": {}}


def save_results(pilot_dir: Path, results: Dict[str, Any]) -> Path:
    path = Path(pilot_dir) / "pilot_results.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes((json.dumps(results, indent=2, sort_keys=True, ensure_ascii=True) + "\n").encode("ascii"))
    return path


# ---------------------------------------------------------------------------------------------------------
# experiments (talk to Ollama)
# ---------------------------------------------------------------------------------------------------------

class Common:
    """Settings shared by the experiments (so tests can point everything at a fake server)."""

    def __init__(self, host: str = DEFAULT_HOST, pilot_dir: Path = PILOT_DIR, phase5_dir: Path = PHASE5_RUNS,
                 inputs_path: Path = INPUTS_PATH, schema_path: Path = SCHEMA_PATH, patch_schema_path: Path = PATCH_IR_SCHEMA,
                 messages_fn: Optional[Callable[..., Any]] = None, schema: Optional[Dict[str, Any]] = None,
                 num_predict: int = DEFAULT_NUM_PREDICT, timeout: float = DEFAULT_TIMEOUT, threads: int = 4,
                 generators: Optional[Dict[str, str]] = None, limit: int = PILOT_INPUTS) -> None:
        self.host, self.pilot_dir, self.phase5_dir = host, Path(pilot_dir), Path(phase5_dir)
        self.inputs_path, self.schema_path, self.patch_schema_path = inputs_path, schema_path, patch_schema_path
        self.messages_fn, self.schema = messages_fn, schema
        self.num_predict, self.timeout, self.threads, self.limit = num_predict, timeout, threads, limit
        self.generators = generators or dict(GENERATOR_MODELS)
        if self.messages_fn is None or self.schema is None:
            self.messages_fn, self.schema = default_prompt_tools()

    def harvest(self, generator: str, profile: str, out: Path, **kw: Any):
        params = dict(generator=generator, model=self.generators[generator], profile=profile, out_root=out,
                      manifest_dir=Path(out) / "manifests", host=self.host, threads=self.threads, top_logprobs=5,
                      num_predict=self.num_predict, timeout=self.timeout, limit=self.limit, stratify=True)
        params.update(kw)
        return run_harvest(HarvestConfig(**params), inputs_path=self.inputs_path, schema_path=self.schema_path,
                           messages_fn=self.messages_fn, schema=self.schema, chat_fn=chat_once_v2,
                           command="pilot " + generator + " " + profile)


def run_profile_a(c: Common) -> Dict[str, Any]:
    results = load_results(c.pilot_dir)
    results["environment"] = ollama_meta(c.host)
    out = c.pilot_dir / "harvest_out"
    for generator in c.generators:
        summary = c.harvest(generator, "A", out)
        by_input, stats = contents_from_folder(out / generator / "A")
        phase5, conflicts = load_phase5_contents(generator, c.phase5_dir)
        entry = {
            "model": c.generators[generator], "inputs": len(by_input), **stats,
            "text_token_mismatches": summary.folder_stats["text_token_mismatches"],
            "mean_distinct_of_8": round(mean_distinct(by_input), 3),
            "replication": match_rates(by_input, phase5) if phase5 else None,
            "phase5_log_conflicts": conflicts, "folder": str(summary.folder),
            "model_digest": ollama_meta(c.host, c.generators[generator])["model_digest"],
        }
        results["profile_a"][generator] = entry
        save_results(c.pilot_dir, results)
        logger.info("%s: %d lines, errors %d, mean distinct %.2f", generator, stats["lines"], stats["errors"],
                    entry["mean_distinct_of_8"])
    return results


def run_throughput(c: Common, label: str, generator: str = "sft") -> Dict[str, Any]:
    results = load_results(c.pilot_dir)
    model = c.generators[generator]
    warm = chat_once_v2(model, {}, messages=[{"role": "user", "content": "Reply with the single word OK."}],
                        schema=c.schema, host=c.host, num_predict=8, timeout=c.timeout)
    if warm.get("error"):
        raise RuntimeError("warm-up request failed: %s" % warm["error"])
    for threads in THROUGHPUT_THREADS:
        out = c.pilot_dir / "throughput" / ("%s_t%d" % (label, threads))
        if out.exists():
            shutil.rmtree(out)
        summary = c.harvest(generator, "A", out, threads=threads, n_samples=THROUGHPUT_JOBS_PER_INPUT, top_logprobs=5)
        row = {"label": label, "model": model, "threads": threads, "generations": summary.lines_written,
               "errors": summary.errors_this_run, "wall_seconds": round(summary.wall_seconds, 1),
               "generations_per_hour": round(summary.gens_per_hour, 0)}
        results["throughput"] = [r for r in results["throughput"] if not (r["label"] == label and r["threads"] == threads)]
        results["throughput"].append(row)
        save_results(c.pilot_dir, results)
        logger.info("threads %d: %.0f generations/hour", threads, row["generations_per_hour"])
    return results


def run_profile_b(c: Common, generators: Sequence[str] = ("sft", "rft")) -> Dict[str, Any]:
    results = load_results(c.pilot_dir)
    patch_schema = json.loads(Path(c.patch_schema_path).read_text(encoding="utf-8-sig"))
    for generator in generators:
        results["profile_b"].setdefault(generator, {})
        for temperature in TEMPERATURES_B:
            out = c.pilot_dir / "profileB" / ("T%s" % temperature)
            override = None if temperature == 1.0 else temperature  # T=1.0 is the real contract profile
            c.harvest(generator, "B", out, temperature_override=override)
            by_input, stats = contents_from_folder(out / generator / "B")
            texts = [t for v in by_input.values() for t in v.values()]
            results["profile_b"][generator][str(temperature)] = {
                "mean_distinct_of_8": round(mean_distinct(by_input), 3),
                "schema_valid_share": schema_valid_share(texts, patch_schema),
                "error_rate": stats["error_rate"], "lines": stats["lines"],
            }
            save_results(c.pilot_dir, results)
            logger.info("%s B T=%s: distinct %.2f", generator, temperature, results["profile_b"][generator][str(temperature)]["mean_distinct_of_8"])
    return results


# ---------------------------------------------------------------------------------------------------------
# report
# ---------------------------------------------------------------------------------------------------------

def _pct(value: Optional[float]) -> str:
    return "n/a" if value is None else "%.1f%%" % (100.0 * value)


def verdict(results: Dict[str, Any]) -> Tuple[bool, List[str]]:
    """(ready, reasons). Ready means: every check passed."""
    reasons: List[str] = []
    ok = True
    pa = results.get("profile_a", {})
    for generator in ("zeroshot", "sft", "rft"):
        entry = pa.get(generator)
        if not entry:
            ok = False
            reasons.append("profile A has not been run for %s." % generator)
            continue
        if entry["error_rate"] > 0.02:
            ok = False
            reasons.append("%s error rate %s is above 2%%." % (generator, _pct(entry["error_rate"])))
        if entry["text_token_mismatches"]:
            ok = False
            reasons.append("%s has %d lines where the token texts do not add up to the content." % (generator, entry["text_token_mismatches"]))
        rep = entry.get("replication")
        if generator in ("sft", "rft"):
            greedy = (rep or {}).get("canonical_by_idx", {}).get("0")
            if greedy is None:
                reasons.append("%s: no Phase 5 log to compare the greedy sample with." % generator)
            elif greedy < 0.95:
                ok = False
                reasons.append("%s greedy sample matches Phase 5 on only %s (below 95%%): check the payload in ollama_client.py." % (generator, _pct(greedy)))
    if not results.get("throughput"):
        ok = False
        reasons.append("throughput has not been measured.")
    sft_b = results.get("profile_b", {}).get("sft", {}).get("1.0")
    if sft_b is None:
        reasons.append("profile B check has not been run.")
    elif sft_b["mean_distinct_of_8"] < 1.5:
        reasons.append("SFT at T=1.0 gives only %.2f distinct answers (below 1.5): propose a profile B change to Shaurya by pull request." % sft_b["mean_distinct_of_8"])
    if ok and not reasons:
        reasons.append("every automatic check passed.")
    return ok, reasons


def build_report(results: Dict[str, Any]) -> str:
    """Markdown text of docs/phase6_prabhav/pilot_report.md, built only from saved numbers."""
    env = results.get("environment", {})
    out: List[str] = ["# Phase 6 pilot report (handoff H1)", "",
                      "Ollama version: %s. Generated from `pilot_results.json`; every number below is measured, none estimated." % env.get("version", "unknown"), ""]
    out += ["## Profile A pilot (20 stratified inputs, top-5 logprobs)", "",
            "| Generator | Model | Model digest | Inputs | Lines | Errors | Error rate | Text/token mismatches | Mean s per generation | Mean tokens |",
            "|---|---|---|---|---|---|---|---|---|---|"]
    for g, e in results.get("profile_a", {}).items():
        out.append("| %s | %s | %s | %d | %d | %d | %s | %d | %s | %s |" % (
            g, e["model"], (e.get("model_digest") or "n/a")[:19], e["inputs"], e["lines"], e["errors"], _pct(e["error_rate"]),
            e["text_token_mismatches"], e["mean_seconds_per_generation"], e["mean_eval_count"]))
    out += ["", "## Throughput", "", "| Label | Model | Threads | Generations | Errors | Wall seconds | Generations per hour |", "|---|---|---|---|---|---|---|"]
    for r in sorted(results.get("throughput", []), key=lambda r: (r["label"], r["threads"])):
        out.append("| %s | %s | %d | %d | %d | %s | %.0f |" % (r["label"], r["model"], r["threads"], r["generations"], r["errors"], r["wall_seconds"], r["generations_per_hour"]))
    out += ["", "Full job: 7,704 lines (profile A, three generators) plus 5,136 (profile B, sft and rft). Divide by the best generations-per-hour above to plan the overnight runs.", ""]
    out += ["## Replication against the Phase 5 candidate logs", "",
            "Exact = identical text. Canonical = same ops and rationale_ref (finding_id ignored). Sample 0 is greedy.", "",
            "| Generator | Compared | Exact (all) | Canonical (all) | Exact sample 0 | Canonical sample 0 |", "|---|---|---|---|---|---|"]
    for g, e in results.get("profile_a", {}).items():
        rep = e.get("replication")
        if not rep:
            out.append("| %s | no Phase 5 log found | | | | |" % g)
            continue
        out.append("| %s | %d | %s | %s | %s | %s |" % (g, rep["n_compared"], _pct(rep["exact_overall"]), _pct(rep["canonical_overall"]),
                                                       _pct(rep["exact_by_idx"].get("0")), _pct(rep["canonical_by_idx"].get("0"))))
    out += ["", "Per sample index (canonical match):", "", "| Generator | " + " | ".join(str(i) for i in range(8)) + " |", "|---|" + "---|" * 8]
    for g, e in results.get("profile_a", {}).items():
        rep = e.get("replication")
        if rep:
            out.append("| %s | " % g + " | ".join(_pct(rep["canonical_by_idx"].get(str(i))) for i in range(8)) + " |")
    out += ["", "## Diversity (mean distinct canonical answers out of 8, profile A)", "",
            "| Generator | Measured now | Phase 5 |", "|---|---|---|"]
    for g, e in results.get("profile_a", {}).items():
        out.append("| %s | %.2f | %s |" % (g, e["mean_distinct_of_8"], PHASE5_DIVERSITY.get(g, "n/a")))
    out += ["", "## Profile B check (local experiment for 1.2 and 1.4; only 1.0 is the contract)", "",
            "| Generator | Temperature | Mean distinct of 8 | Schema-valid share | Error rate |", "|---|---|---|---|---|"]
    for g, temps in results.get("profile_b", {}).items():
        for t, e in sorted(temps.items()):
            out.append("| %s | %s | %.2f | %s | %s |" % (g, t, e["mean_distinct_of_8"], _pct(e["schema_valid_share"]), _pct(e["error_rate"])))
    ready, reasons = verdict(results)
    out += ["", "## Verdict", "", ("READY for the full harvest. " if ready else "NOT READY yet. ") + " ".join(reasons), ""]
    return "\n".join(out) + "\n"


# ---------------------------------------------------------------------------------------------------------
# command line
# ---------------------------------------------------------------------------------------------------------

def main(argv: Optional[Sequence[str]] = None, *, common: Optional[Common] = None) -> int:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(message)s", datefmt="%H:%M:%S", stream=sys.stdout)
    p = argparse.ArgumentParser(prog="python -m ml.train_m2.harvest.pilot")
    p.add_argument("step", choices=["a", "throughput", "b", "report"])
    p.add_argument("--label", default="run", help="throughput: a name such as parallel4 or default")
    p.add_argument("--threads", type=int, default=4)
    p.add_argument("--host", default=DEFAULT_HOST)
    p.add_argument("--num-predict", type=int, default=DEFAULT_NUM_PREDICT)
    p.add_argument("--timeout", type=float, default=DEFAULT_TIMEOUT)
    args = p.parse_args(list(sys.argv[1:] if argv is None else argv))
    try:
        if args.step == "report":
            pilot_dir = common.pilot_dir if common else PILOT_DIR
            docs = (common.pilot_dir / "docs") if common else DOCS_DIR
            results = load_results(pilot_dir)
            if not results.get("profile_a"):
                print("No pilot numbers yet. Run the steps a, throughput and b first.")
                return 1
            docs.mkdir(parents=True, exist_ok=True)
            path = docs / "pilot_report.md"
            path.write_bytes(build_report(results).encode("ascii", "replace"))
            print("Wrote %s" % path)
            ready, reasons = verdict(results)
            print(("READY: " if ready else "NOT READY: ") + " ".join(reasons))
            return 0
        c = common or Common(host=args.host, threads=args.threads, num_predict=args.num_predict, timeout=args.timeout)
        if args.step == "a":
            run_profile_a(c)
        elif args.step == "throughput":
            run_throughput(c, args.label)
        else:
            run_profile_b(c)
    except Exception as exc:  # noqa: BLE001 - clean message for the operator
        print("PILOT STOPPED: %s: %s" % (type(exc).__name__, exc))
        return 2
    print("Saved to %s" % (Path(c.pilot_dir) / "pilot_results.json"))
    return 0


if __name__ == "__main__":
    sys.exit(main())
