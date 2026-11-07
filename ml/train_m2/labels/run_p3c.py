"""P3c push-button checks on real data (Shaurya-owned). No Ollama, no network, no held-out scoring.

Sub-commands (python -m ml.train_m2.labels.run_p3c <cmd> ...):
  cf-eval    confusion matrix of the reference-free counterfactual labeler vs the reference oracle
  lengths    harvest output lengths vs Phase 5 num_predict, and gate-pass vs Phase 5 on COMMON keys only
  (gap22 moved to its own module: python -m ml.train_m2.labels.gap22 --gen sft)
  corruptor  build the generator-independent, de-duplicated, capped corruptor store
  shortcut   per-type single-feature separability of corruptor negatives vs natural minimal_correct
  audit      leak audit of label files (hard error on any violation)
Every output goes under ml/train_m2/out/reports/ (or out/labels/ for data) with a provenance file.
"""
from __future__ import annotations

import argparse
import glob
import json
import logging
from collections import Counter
from pathlib import Path
from typing import Any, Iterator

from ml.mutation_engine.dataset_io import input_key as example_key
from ml.train_m2 import common
from ml.train_m2.labels import corruptor_store as cs
from ml.train_m2.labels import harvest_checks as hc
from ml.train_m2.labels import shortcut_by_type as sb
from ml.train_m2.labels.leakguard import audit_label_rows, load_key_sets, raise_if_violations

LOG = logging.getLogger("run_p3c")
ROOT = common.repo_root()
REPORTS = ROOT / "ml" / "train_m2" / "out" / "reports"
LABELS = ROOT / "ml" / "train_m2" / "out" / "labels"
DATASET = ROOT / "ml" / "mutation_engine" / "dataset"
GENS = ("zeroshot", "sft", "rft", "rft_v2")


def _write(stem: Path, md: str, obj: Any, inputs: list[str]) -> None:
    stem.parent.mkdir(parents=True, exist_ok=True)
    Path(str(stem) + ".md").write_text(md, encoding="utf-8", newline="\n")
    Path(str(stem) + ".json").write_text(json.dumps(obj, indent=2, sort_keys=True, default=str) + "\n",
                                         encoding="utf-8", newline="\n")
    common.write_provenance(str(stem) + ".json", inputs=inputs)


def _examples(names=("train", "val")) -> Iterator[dict]:
    for n in names:
        p = DATASET / f"{n}.jsonl"
        if p.exists():
            yield from common.jsonl_iter(p)


def _is_fix_ref(ex: dict) -> bool:
    return bool(ex.get("target")) and (ex.get("meta") or {}).get("route") == "fix" and \
        any(o.get("op") != "escalate" for o in ex["target"].get("ops", []))


def _ref_items() -> list[tuple[str, dict, dict]]:
    seen: dict[str, tuple[str, dict, dict]] = {}
    for ex in _examples():
        if _is_fix_ref(ex):
            k = example_key(ex)
            seen.setdefault(k, (k, ex["input"], ex["target"]))
    return [seen[k] for k in sorted(seen)]


def cmd_cf_eval(a: argparse.Namespace) -> None:
    from ml.train_m2.labels.cf_eval import evaluate_cf
    items = _ref_items()
    rep = evaluate_cf(items, seed=a.seed)
    rep["n_fix_route_inputs"] = len(items)
    L = ["# Counterfactual labeler vs reference oracle", "", f"fix-route inputs with a reference: {len(items)}", "",
         "Population: reference patches (truth = correct) + every gate-passing corruption (truth = reference oracle).", "",
         "| variant | correct->correct | correct->wrong | wrong->correct | wrong->wrong | recall of wrong | "
         "precision of 'wrong' | false-wrong rate on correct |", "|---|---|---|---|---|---|---|---|"]
    for m in ("strict", "lenient"):
        r = rep[m]
        f = lambda x: "n/a" if x is None else f"{x:.3f}"
        L.append(f"| {m} | {r['correct_called_correct']} | {r['correct_called_wrong']} | {r['wrong_called_correct']} | "
                 f"{r['wrong_called_wrong']} | {f(r['recall_of_wrong'])} | {f(r['precision_of_wrong'])} | "
                 f"{f(r['false_wrong_rate_on_correct'])} |")
    L += ["", "## By corruption type (truth, counterfactual label) -> n", ""]
    for t, d in rep["by_type"].items():
        L.append(f"- {t}: " + ", ".join(f"{k}: {v}" for k, v in d.items()))
    L += ["", "Reading: STRICT (label == minimal_correct) is the only usable reference-free rule; LENIENT mostly "
          "re-states the gate. Reference-free labels are WEAK and must never be used for calibration or evaluation.", ""]
    _write(REPORTS / "cf_confusion", "\n".join(L), rep, ["ml/mutation_engine/dataset/train.jsonl"])


def _harvest_rows(gen: str) -> Iterator[dict]:
    for f in sorted(glob.glob(str(ROOT / "ml" / "train_m2" / "harvest_out" / gen / "A" / "part-*.jsonl"))):
        yield from common.jsonl_iter(f)


def _phase5_greedy_gate(gen: str) -> dict[str, bool]:
    out: dict[str, bool] = {}
    for f in sorted(glob.glob(str(ROOT / "ml" / "train_m1" / "eval" / "runs" / gen / "*.candidates.jsonl"))):
        for row in common.jsonl_iter(f):
            cands = (row.get("scored") or {}).get("candidates") or []
            if cands:
                c = cands[0]
                out[row["input_key"]] = bool(c.get("gate_passed", c.get("pass_gate", False)))
    return out


def cmd_lengths(a: argparse.Namespace) -> None:
    rep: dict[str, Any] = {}
    L = ["# Harvest vs Phase 5: lengths and common-key gate-pass", ""]
    for g in GENS:
        rows = list(_harvest_rows(g))
        if not rows:
            continue
        stats = hc.length_stats(rows, a.limit)
        lab = LABELS / "harvest" / f"{g}.jsonl"
        gp: dict[str, bool] = {}
        if lab.exists():
            for r in common.jsonl_iter(lab):
                if r.get("sample_idx") == 0:
                    gp[r["input_key"]] = bool(r.get("gate_pass"))
        cmp_ = hc.compare_common(gp, _phase5_greedy_gate(g)) if gp else None
        rep[g] = {"lengths": stats, "harvest_vs_phase5_common": cmp_}
        L.append(f"- {g}: greedy outputs over {a.limit} tokens: {stats['greedy_over_limit']}/{stats['greedy_rows']}; "
                 f"cut off (done_reason=length): {stats['greedy_done_length']}")
        if cmp_ and cmp_["n_common"] > 0:
            L.append(f"  common keys {cmp_['n_common']}: harvest pass {cmp_['a_pass']} ({cmp_['a_rate']:.3f}) vs "
                     f"Phase 5 {cmp_['b_pass']} ({cmp_['b_rate']:.3f}); harvest-only {cmp_['a_only_pass']}, "
                     f"Phase 5-only {cmp_['b_only_pass']}")
    L += ["", "Rates over different input sets are not comparable; only the common-key line counts."]
    _write(REPORTS / "harvest_vs_phase5", "\n".join(L) + "\n", rep,
           sorted(str(Path(f).relative_to(ROOT).as_posix()) for f in glob.glob(str(ROOT / "ml" / "train_m2" / "harvest_out" / "*" / "A" / "MANIFEST.json"))))


def _natural_rows(paths: list[str]) -> Iterator[dict]:
    for p in sorted({f for g in paths for f in glob.glob(g)}):
        for r in common.jsonl_iter(p):
            if r.get("source") != "corruptor":
                yield r


def cmd_corruptor(a: argparse.Namespace) -> None:
    from ml.train_m2.labels import corruptor as cor
    ks = load_key_sets(ROOT)
    elig = ks.corruptor_eligible()
    items = [(k, rec, ref, "fix") for (k, rec, ref) in _ref_items() if k in elig]
    LOG.info("eligible fix-route seeds: %d", len(items))
    # type filter measured on the seed partition only: keep a type iff it yields gate-passing wrong rows
    probe: dict[str, int] = Counter()
    for k, rec, ref, route in items:
        for row in cor.make_corrupted_rows(rec, ref, route, k, a.seed):
            if row.get("gate_pass") and row.get("oracle_class") == "wrong":
                probe[row["corruption_type"]] += 1
    keep = sorted(t for t, n in probe.items() if n > 0)
    if a.n_natural is not None:
        n_nat = a.n_natural
    else:
        seen: set[tuple] = set()
        from ml.train_m2.labels.accounting import is_scored_candidate
        for r in _natural_rows(a.natural):
            if is_scored_candidate(r) and not ks.heldout_sets_of(r["input_key"]):
                seen.add((r["input_key"], r.get("answer_key")))
        n_nat = len(seen)
    rows, rep = cs.build_store(items, cor.make_corrupted_rows, keep, n_nat, a.frac, a.seed)
    rep["kept_types"] = keep
    rep["dropped_types"] = sorted({"C1", "C2", "C3", "C4", "C5", "C6", "C7", "C8"} - set(keep))
    rep["hard_negative_rows_per_type_before_dedupe"] = dict(probe)
    LABELS.mkdir(parents=True, exist_ok=True)
    cs.write_store(LABELS / "corruptor_train.jsonl", rows)
    common.write_provenance(str(LABELS / "corruptor_train.jsonl"), inputs=["ml/mutation_engine/dataset/train.jsonl"])
    _write(REPORTS / "corruptor_store", "# Corruptor store\n\n```\n" + json.dumps(rep, indent=2, sort_keys=True) + "\n```\n",
           rep, [])


def cmd_shortcut(a: argparse.Namespace) -> None:
    cor = [r for r in common.jsonl_iter(LABELS / "corruptor_train.jsonl") if r.get("gate_pass") and
           r.get("oracle_class") == "wrong"]
    nat = [r for r in _natural_rows(a.natural) if r.get("gate_pass") and r.get("oracle_class") == "minimal_correct"
           and r.get("patch")]
    rep = sb.separability(cor, nat)
    L = ["# Corruptor shortcut diagnostic (AUC; 0.5 = no shortcut, > 0.95 trivially separable)", "",
         f"natural minimal_correct candidates: {len(nat)}", "", "| type | n | n_ops | patch_json_len | trivially separable |",
         "|---|---|---|---|---|"]
    for t, v in rep.items():
        L.append(f"| {t} | {v['n']} | {v['n_ops']:.3f} | {v['patch_json_len']:.3f} | {v['trivially_separable']} |")
    _write(REPORTS / "shortcut_by_type", "\n".join(L) + "\n", rep, ["ml/train_m2/out/labels/corruptor_train.jsonl"])


def cmd_audit(a: argparse.Namespace) -> None:
    ks = load_key_sets(ROOT)
    files = sorted({f for g in a.labels for f in glob.glob(g)})
    rows = [r for f in files for r in common.jsonl_iter(f)]
    rep = audit_label_rows(rows, ks)
    _write(REPORTS / "leak_audit", "# Leak audit\n\n```\n" + json.dumps(rep, indent=2, sort_keys=True) + "\n```\n", rep, files)
    raise_if_violations(rep)


def main(argv: list[str] | None = None) -> int:
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    p = sub.add_parser("cf-eval"); p.add_argument("--seed", type=int, default=1337); p.set_defaults(fn=cmd_cf_eval)
    p = sub.add_parser("lengths"); p.add_argument("--limit", type=int, default=400); p.set_defaults(fn=cmd_lengths)
    p = sub.add_parser("corruptor"); p.add_argument("--seed", type=int, default=1337)
    p.add_argument("--frac", type=float, default=0.35); p.add_argument("--n-natural", type=int, default=None)
    p.add_argument("--natural", nargs="*", default=[str(LABELS / "*.jsonl"), str(LABELS / "harvest" / "*.jsonl")])
    p.set_defaults(fn=cmd_corruptor)
    p = sub.add_parser("shortcut")
    p.add_argument("--natural", nargs="*", default=[str(LABELS / "*.jsonl"), str(LABELS / "harvest" / "*.jsonl")])
    p.set_defaults(fn=cmd_shortcut)
    p = sub.add_parser("audit")
    p.add_argument("--labels", nargs="+", default=[str(LABELS / "*.jsonl"), str(LABELS / "harvest" / "*.jsonl")])
    p.set_defaults(fn=cmd_audit)
    a = ap.parse_args(argv)
    a.fn(a)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
