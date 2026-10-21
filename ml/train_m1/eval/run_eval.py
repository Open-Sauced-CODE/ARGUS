"""
ARGUS Phase 5, Steps 15 and 21 - generate with an Ollama model, score, and summarise ONE (model, set) pair.

    python -m ml.train_m1.eval.run_eval --model qwen3.5:4b --set A_val --samples 8 --threads 4 --label zeroshot
    python -m ml.train_m1.eval.run_eval --model argus-m1-sft --set B1 --samples 8 --label sft

Sets: A_val, train300, B1, B2, C_verifier, C_mined, gold. B1, B2, C_*, gold are HELD OUT: each (label, set) may be scored ONCE
(EXPERIMENT_PLAN rule 5.1); a repeat needs --repeat-reason "text" and is logged. Before any run the dataset manifest must verify.
Prompts are de-duplicated by model input (the gate depends only on the input), samples: #1 greedy, the rest at --temperature.
Output: ml/train_m1/eval/runs/<label>/<set>.summary.json and <set>.candidates.jsonl; one line is added to eval/RUN_LOG.md.
"""

import argparse
import datetime
import json
import statistics
import sys
from collections import defaultdict
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from ml.mutation_engine.dataset_io import canon, input_key, read_jsonl, sha256_file
from ml.tools.verify_manifest import verify_manifest
from ml.train_m1.eval.ollama_client import chat_once
from ml.train_m1.eval.score import score_inputs
from ml.train_m1.stats import fmt_rate, wilson

ROOT = Path(__file__).resolve().parents[3]
ME = ROOT / "ml" / "mutation_engine"
EVAL_DIR = Path(__file__).resolve().parent
RUN_LOG = EVAL_DIR / "RUN_LOG.md"
SETS = {"A_val": ME / "dataset" / "val.jsonl", "train300": ROOT / "ml" / "train_m1" / "data" / "train_sample300.jsonl",
        "B1": ME / "held_out" / "tierB1.jsonl", "B2": ME / "held_out" / "tierB2.jsonl",
        "C_verifier": ME / "held_out" / "tierC_verifier.jsonl", "C_mined": ME / "held_out" / "tierC_mined.jsonl",
        "gold": ME / "held_out" / "gold.jsonl"}
HELD_OUT = {"B1", "B2", "C_verifier", "C_mined", "gold"}


def logged_pairs():
    pairs = set()
    if RUN_LOG.exists():
        for line in RUN_LOG.read_text(encoding="utf-8").splitlines():
            cells = [c.strip() for c in line.strip().strip("|").split("|")]
            if len(cells) >= 4 and cells[0][:2] == "20":
                pairs.add((cells[1], cells[2]))
    return pairs


def log_run(label, set_name, n, file_hash, note):
    if not RUN_LOG.exists():
        RUN_LOG.write_text("# Run log (one line per scored (model, set) pair)\n\n| date | label | set | examples | file sha256 | note |\n|---|---|---|---:|---|---|\n", encoding="ascii")
    with open(RUN_LOG, "a", encoding="ascii", newline="\n") as h:
        h.write("| {} | {} | {} | {} | {} | {} |\n".format(datetime.date.today().isoformat(), label, set_name, n, file_hash[:16], note.replace("|", "/")))


def generate(model, records, samples, temperature, threads, host, limit=None):
    jobs = [(i, s) for i in range(len(records)) for s in range(samples)]
    out = defaultdict(dict)

    def work(job):
        i, s = job
        return i, s, chat_once(model, records[i], 0.0 if s == 0 else temperature, seed=s, host=host)

    done = 0
    with ThreadPoolExecutor(max_workers=threads) as pool:
        for i, s, res in pool.map(work, jobs):
            out[i][s] = res
            done += 1
            if done % 50 == 0:
                print("  generated {}/{}".format(done, len(jobs)), flush=True)
    return out


def summarise(examples, groups, scored, gen, samples):
    pass_k = {k: 0 for k in range(1, samples + 1)}
    n_cand = valid = unsafe = gate_pass = hidden_ok = 0
    esc_tp = esc_fp = esc_fn = 0
    first_pass_times = []
    group_pass = {}
    for key, idxs in groups.items():
        res = scored[key]
        group_pass[key] = res["pass_at"]
    for ex in examples:
        key = input_key(ex)
        res = scored[key]
        for k in pass_k:
            pass_k[k] += 1 if res["pass_at"].get(k) else 0
        c0 = res["candidates"][0]
        if ex["meta"]["route"] == "escalate":
            esc_tp += c0["escalated"]
            esc_fn += not c0["escalated"]
        else:
            esc_fp += c0["escalated"]
        t = 0.0
        for j, c in enumerate(res["candidates"]):
            t += gen[key][j]["seconds"]
            if c["correct"]:
                first_pass_times.append(t)
                break
    for key, res in scored.items():
        for c in res["candidates"]:
            n_cand += 1
            valid += c["status"] == "ok"
            unsafe += c["unsafe"]
            gate_pass += c["gate_passed"]
            hidden_ok += 1 if c["hidden_ok"] else 0
    n = len(examples)
    return {"examples": n, "distinct_inputs": len(groups), "samples": samples,
            "pass_at": {str(k): v for k, v in pass_k.items()}, "pass_at_1_text": fmt_rate(pass_k[1], n),
            "pass_at_k_text": fmt_rate(pass_k[samples], n), "schema_valid_candidates": [valid, n_cand], "unsafe_candidates": [unsafe, n_cand],
            "gate_passing_candidates": gate_pass, "hidden_ok_among_gate_passing": [hidden_ok, gate_pass],
            "escalate": {"tp": esc_tp, "fp": esc_fp, "fn": esc_fn,
                         "precision": esc_tp / (esc_tp + esc_fp) if esc_tp + esc_fp else None,
                         "recall": esc_tp / (esc_tp + esc_fn) if esc_tp + esc_fn else None},
            "median_seconds_to_first_pass": statistics.median(first_pass_times) if first_pass_times else None,
            "never_passed": n - len(first_pass_times)}


def main(argv=None):
    p = argparse.ArgumentParser(description="Generate and score one (model, set) pair")
    p.add_argument("--model", required=True, help="Ollama model name")
    p.add_argument("--label", required=True, help="short row name in the results grid, e.g. zeroshot, sft, rft")
    p.add_argument("--set", required=True, choices=sorted(SETS))
    p.add_argument("--samples", type=int, default=8)
    p.add_argument("--temperature", type=float, default=0.7)
    p.add_argument("--threads", type=int, default=2)
    p.add_argument("--host", default="http://127.0.0.1:11434")
    p.add_argument("--limit", type=int, default=None, help="only the first N distinct inputs (pilot run; not allowed on held-out sets)")
    p.add_argument("--repeat-reason", default=None)
    o = p.parse_args(argv)

    problems = verify_manifest()
    if problems:
        print("MANIFEST CHECK FAILED, not running:", problems[:5])
        return 1
    path = SETS[o.set]
    examples = read_jsonl(path)
    if not examples:
        print("No examples in {}".format(path))
        return 2
    if o.set in HELD_OUT:
        if o.limit:
            print("--limit is not allowed on a held-out set.")
            return 1
        if (o.label, o.set) in logged_pairs() and not o.repeat_reason:
            print("({}, {}) was already scored. Use --repeat-reason \"why\" to repeat it (the repeat is logged).".format(o.label, o.set))
            return 1
    keys_all = sorted({input_key(ex) for ex in examples})
    if o.limit:
        keep = set(keys_all[: o.limit])
        examples = [ex for ex in examples if input_key(ex) in keep]
    groups = {}
    for i, ex in enumerate(examples):
        groups.setdefault(input_key(ex), []).append(i)
    keys = sorted(groups)
    first = {k: examples[groups[k][0]] for k in keys}
    records = [first[k]["input"] for k in keys]
    print("{} examples, {} distinct inputs, {} samples each -> {} requests".format(len(examples), len(keys), o.samples, len(keys) * o.samples))
    gen_by_idx = generate(o.model, records, o.samples, o.temperature, o.threads, o.host)
    gen = {k: [gen_by_idx[i][s] for s in range(o.samples)] for i, k in enumerate(keys)}
    errors = sum(1 for k in gen for g in gen[k] if g["error"])
    if errors:
        print("WARNING: {} requests failed (is Ollama running and the model installed?). First: {}".format(
            errors, next(g["error"] for k in gen for g in gen[k] if g["error"])))
    items = [{"record": first[k]["input"], "route": first[k]["meta"]["route"], "reference": first[k].get("target"),
              "contents": [g["content"] for g in gen[k]]} for k in keys]
    results = score_inputs(items)
    scored = dict(zip(keys, results))
    summary = summarise(examples, groups, scored, gen, o.samples)
    summary.update({"label": o.label, "model": o.model, "set": o.set, "temperature": o.temperature, "request_errors": errors})
    out_dir = EVAL_DIR / "runs" / o.label
    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / (o.set + ".summary.json")).write_text(json.dumps(summary, indent=2, sort_keys=True) + "\n", encoding="ascii")
    with open(out_dir / (o.set + ".candidates.jsonl"), "w", encoding="ascii", newline="\n") as h:
        for k in keys:
            h.write(json.dumps({"input_key": k, "example_ids": [examples[i]["id"] for i in groups[k]],
                                "contents": [g["content"] for g in gen[k]], "scored": scored[k]}, sort_keys=True, ensure_ascii=True) + "\n")
    if o.set in HELD_OUT:
        log_run(o.label, o.set, len(examples), sha256_file(path), o.repeat_reason or "first scoring")
    print("pass@1 {}   pass@{} {}".format(summary["pass_at_1_text"], o.samples, summary["pass_at_k_text"]))
    print("schema-valid {}  unsafe {}  median s to first pass {}".format(summary["schema_valid_candidates"], summary["unsafe_candidates"], summary["median_seconds_to_first_pass"]))
    return 0


if __name__ == "__main__":
    sys.exit(main())
