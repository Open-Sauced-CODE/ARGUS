"""A_val evaluation wrapper for RFT-v2 (H4). It IMPORTS the frozen Phase 5 scorer and gate; it never edits them.

Scores candidate files against the Phase 5 A_val examples and prints, per generator and per rule:
pass@1, pass@8, mean distinct canonical answers, unsafe count, escalate precision and recall, schema-valid rate.

    # from a harvest folder (the harvest tool already wrote 8 samples per input):
    python -m ml.train_m1.v2.eval_v2 --harvest ml\\train_m2\\harvest_out\\sft\\A --label sft
    # from Phase 5 candidate logs (to prove this wrapper reproduces SFT's 349/361):
    python -m ml.train_m1.v2.eval_v2 --candidates ml\\train_m1\\eval\\runs\\sft\\A_val.candidates.jsonl --label sft-phase5 --expect-pass1 349 --expect-n 361

pass@1 is the greedy sample (index 0) judged by the frozen scorer (hidden checks included, as in Phase 5).
"""

from __future__ import annotations

import argparse
import json
import sys
from collections import defaultdict
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Sequence

from ml.train_m1.v2.escalate_stats import is_escalate
from ml.train_m2.harvest.paths import PATCH_IR_SCHEMA, REPO_ROOT
from ml.train_m2.harvest.pilot import distinct_count, schema_valid_share
from ml.train_m2.harvest.store import iter_lines

DEFAULT_DATASET = REPO_ROOT / "ml" / "mutation_engine" / "dataset" / "val.jsonl"


def example_input_key(record: Dict[str, Any]) -> str:
    """Same canonical JSON as the harvest input_key: fields, resource_ref, rule_id."""
    return json.dumps({"fields": record["fields"], "resource_ref": record["resource_ref"], "rule_id": record["rule_id"]},
                      sort_keys=True, separators=(",", ":"))


def read_jsonl(path: Path) -> List[Dict[str, Any]]:
    return [json.loads(raw) for raw in Path(path).read_bytes().decode("utf-8").splitlines() if raw.strip()]


def candidates_from_harvest(folder: Path) -> Dict[str, List[str]]:
    """input_key -> contents ordered by sample_idx (a failed generation becomes an empty string)."""
    by_key: Dict[str, Dict[int, str]] = defaultdict(dict)
    for _path, line in iter_lines(Path(folder)):
        by_key[line["input_key"]][line["sample_idx"]] = "" if line["error"] is not None else line["content"]
    return {k: [v[i] for i in sorted(v)] for k, v in by_key.items()}


def candidates_from_phase5(paths: Sequence[Path]) -> Dict[str, List[str]]:
    out: Dict[str, List[str]] = {}
    for path in paths:
        for item in read_jsonl(Path(path)):
            if isinstance(item.get("input_key"), str):
                if isinstance(item.get("contents"), list):
                    out.setdefault(item["input_key"], item["contents"])
                elif isinstance(item.get("content"), str):
                    out.setdefault(item["input_key"], [item["content"]])
    return out


def _parse_patch(text: str) -> Optional[Dict[str, Any]]:
    try:
        data = json.loads(text)
    except ValueError:
        return None
    return data if isinstance(data, dict) else None


def evaluate(examples: Sequence[Dict[str, Any]], cands: Dict[str, List[str]], score_fn: Callable[[List[Dict[str, Any]]], List[Dict[str, Any]]],
             gate_fn: Callable[[List[Any]], List[Any]], patch_schema: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    """Pure evaluation. score_fn is ml.train_m1.eval.score.score_inputs, gate_fn is gate_stub.gate_many (or fakes in tests)."""
    usable = [ex for ex in examples if example_input_key(ex["input"]) in cands]
    missing = len(examples) - len(usable)
    by_key: Dict[str, Dict[str, Any]] = {}
    for ex in usable:
        k = example_input_key(ex["input"])
        if k not in by_key:
            by_key[k] = ex
    keys = list(by_key.keys())
    key_items = [{"record": by_key[k]["input"], "route": by_key[k]["meta"]["route"], "reference": by_key[k]["target"],
                  "contents": cands[k]} for k in keys]
    key_results = score_fn(key_items) if key_items else []
    scored_by_key = dict(zip(keys, key_results))
    results = [scored_by_key[example_input_key(ex["input"])] for ex in usable]
    items = [{"record": by_key[example_input_key(ex["input"])]["input"], "route": ex["meta"]["route"], "reference": ex["target"],
              "contents": cands[example_input_key(ex["input"])]} for ex in usable]
    gate_cases: List[Any] = []
    for ex in usable:
        k = example_input_key(ex["input"])
        for text in cands[k]:
            patch = _parse_patch(text)
            if patch is not None:
                gate_cases.append((by_key[k]["input"], patch))
    gate_results = gate_fn(gate_cases) if gate_cases else []
    unsafe = sum(1 for r in gate_results if getattr(r, "unsafe", False))
    per_rule: Dict[str, Dict[str, float]] = defaultdict(lambda: defaultdict(float))
    tp = fn = fp = tn = 0
    all_texts: List[str] = []
    for ex, item, res in zip(usable, items, results):
        rule = ex["rule_id"]
        pa = res["pass_at"]
        p1 = bool(pa[1])
        pk = bool(pa[max(pa)])
        row = per_rule[rule]
        row["n"] += 1
        row["pass1"] += p1
        row["passk"] += pk
        row["distinct"] += distinct_count(item["contents"])
        row["escalate_ref"] = 1.0 if ex["meta"]["route"] == "ESC" else 0.0
        all_texts.extend(item["contents"])
        ref_esc = ex["meta"]["route"] == "ESC"
        ans_esc = is_escalate(item["contents"][0] if item["contents"] else "")
        tp += ref_esc and ans_esc
        fn += ref_esc and not ans_esc
        fp += (not ref_esc) and ans_esc
        tn += (not ref_esc) and not ans_esc
    n = len(usable)
    total = lambda k: sum(r[k] for r in per_rule.values())  # noqa: E731
    return {
        "n_examples": n, "examples_without_candidates": missing,
        "pass_at_1": total("pass1") / n if n else None, "pass_at_1_count": int(total("pass1")),
        "pass_at_8": total("passk") / n if n else None,
        "mean_distinct": total("distinct") / n if n else None,
        "unsafe_candidates": unsafe,
        "escalate": {"tp": tp, "fn": fn, "fp": fp, "tn": tn,
                     "precision": tp / (tp + fp) if tp + fp else None, "recall": tp / (tp + fn) if tp + fn else None},
        "schema_valid_rate": schema_valid_share(all_texts, patch_schema) if patch_schema and all_texts else None,
        "per_rule": {rule: {"n": int(r["n"]), "pass_at_1": r["pass1"] / r["n"], "pass_at_8": r["passk"] / r["n"],
                            "mean_distinct": r["distinct"] / r["n"], "route_is_esc": bool(r["escalate_ref"])}
                     for rule, r in sorted(per_rule.items())},
    }


def _f(x: Optional[float], pct: bool = True) -> str:
    return "n/a" if x is None else ("%.1f%%" % (100 * x) if pct else "%.2f" % x)


def to_markdown(label: str, r: Dict[str, Any]) -> str:
    e = r["escalate"]
    out = ["## %s on A_val" % label, "",
           "| Metric | Value |", "|---|---|",
           "| examples scored | %d (without candidates: %d) |" % (r["n_examples"], r["examples_without_candidates"]),
           "| pass@1 (greedy) | %s (%d/%d) |" % (_f(r["pass_at_1"]), r["pass_at_1_count"], r["n_examples"]),
           "| pass@8 | %s |" % _f(r["pass_at_8"]),
           "| mean distinct canonical answers of 8 | %s |" % _f(r["mean_distinct"], False),
           "| unsafe candidates | %d |" % r["unsafe_candidates"],
           "| escalate precision / recall | %s / %s (tp %d, fn %d, fp %d) |" % (_f(e["precision"]), _f(e["recall"]), e["tp"], e["fn"], e["fp"]),
           "| schema-valid rate | %s |" % _f(r["schema_valid_rate"]), "",
           "| Rule | n | pass@1 | pass@8 | mean distinct | ESC route |", "|---|---|---|---|---|---|"]
    for rule, row in r["per_rule"].items():
        out.append("| %s | %d | %s | %s | %s | %s |" % (rule, row["n"], _f(row["pass_at_1"]), _f(row["pass_at_8"]),
                                                       _f(row["mean_distinct"], False), "yes" if row["route_is_esc"] else "no"))
    return "\n".join(out) + "\n"


def main(argv: Optional[Sequence[str]] = None) -> int:
    p = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    src = p.add_mutually_exclusive_group(required=True)
    src.add_argument("--harvest", type=Path, help="a harvest folder such as ml/train_m2/harvest_out/sft/A")
    src.add_argument("--candidates", type=Path, nargs="+", help="Phase 5 *.candidates.jsonl files")
    p.add_argument("--label", required=True)
    p.add_argument("--dataset", type=Path, default=DEFAULT_DATASET, help="A_val examples (default ml/mutation_engine/dataset/val.jsonl)")
    p.add_argument("--out", type=Path, default=None, help="markdown output (default ml/train_m1/v2/eval/<label>_A_val.md)")
    p.add_argument("--expect-pass1", type=int, default=None)
    p.add_argument("--expect-n", type=int, default=None)
    args = p.parse_args(list(sys.argv[1:] if argv is None else argv))
    try:
        from ml.mutation_engine.qa.gate_stub import gate_many
        from ml.train_m1.eval.score import score_inputs
    except ImportError as exc:
        print("cannot import the frozen scorer/gate: %s" % exc)
        return 2
    cands = candidates_from_harvest(args.harvest) if args.harvest else candidates_from_phase5(args.candidates)
    schema = json.loads(PATCH_IR_SCHEMA.read_text(encoding="utf-8-sig")) if PATCH_IR_SCHEMA.exists() else None
    result = evaluate(read_jsonl(args.dataset), cands, score_inputs, gate_many, schema)
    text = to_markdown(args.label, result)
    out = args.out or (REPO_ROOT / "ml" / "train_m1" / "v2" / "eval" / ("%s_A_val.md" % args.label))
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_bytes(text.encode("ascii", "replace"))
    out.with_suffix(".json").write_bytes((json.dumps(result, indent=2, sort_keys=True) + "\n").encode("ascii"))
    print(text)
    print("Saved to %s" % out)
    if args.expect_pass1 is not None:
        ok = result["pass_at_1_count"] == args.expect_pass1 and (args.expect_n is None or result["n_examples"] == args.expect_n)
        print("REPRODUCTION %s: got %d/%d, expected %d/%s" % ("MATCH" if ok else "MISMATCH", result["pass_at_1_count"],
                                                              result["n_examples"], args.expect_pass1, args.expect_n))
        return 0 if ok else 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
