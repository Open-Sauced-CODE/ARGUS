"""Push-button M2 pipeline (Shaurya-owned): spec | splits | train | tau | eval.   python -m ml.train_m2.run_m2 <cmd>

Reads label rows from ml/train_m2/out/labels/harvest/<generator>.jsonl and drafts from ml/train_m2/harvest_out.
Nothing here reads a held-out set except `eval`, which goes through eval.run_once.
"""
from __future__ import annotations

import argparse
import json
import logging
from pathlib import Path

import numpy as np
import pandas as pd

from ml.train_m2 import common, splits as S
from ml.train_m2.eval import run_once as RO
from ml.train_m2.features import registry as R
from ml.train_m2.labels.leakguard import load_key_sets
from ml.train_m2.models import dataset as DS
from ml.train_m2.models import diagnostics as DG
from ml.train_m2.models import train_m2 as T
from ml.train_m2.risk import calibrate_tau as CT
from ml.train_m2.risk.decisions import select_decisions

LOG = logging.getLogger("run_m2")
ROOT = common.repo_root()
OUT = ROOT / "ml" / "train_m2" / "out"
M2 = OUT / "m2"
REPORTS = OUT / "reports"
GENS = ("zeroshot", "sft", "rft", "rft_v2")


def _clusters() -> dict[str, str]:
    out = {}
    for r in common.jsonl_iter(ROOT / "ml" / "train_m2" / "contract" / "harvest_inputs.jsonl"):
        out[r["input_key"]] = r["record"]["rule_id"]
    return out


def _frame(gens, partition: str | None, splits: dict):
    label_rows = []
    for g in gens:
        p = OUT / "labels" / "harvest" / f"{g}.jsonl"
        if p.exists():
            label_rows += [r for r in common.jsonl_iter(p) if r.get("source") != "corruptor"]
    hv = {g: DS.load_harvest(ROOT, g) for g in gens}
    X, meta = DS.build_frame(label_rows, hv, DS.load_routes_and_rules(ROOT))
    if partition is not None:
        X, meta = DS.load_partition(X, meta, splits, partition)
    return X, meta


def cmd_spec(a):
    REPORTS.mkdir(parents=True, exist_ok=True)
    (REPORTS / "m2_feature_spec.md").write_text(R.feature_spec_md(), encoding="utf-8", newline="\n")
    print("spec hash", R.spec_hash())


def cmd_splits(a):
    ks = load_key_sets(ROOT)
    forced = ks.a_val - ks.phase5_train - ks.held_out_union          # inputs SFT never trained on, not held-out
    s = S.build_splits(_clusters(), ks.held_out_union, forced, seed=a.seed)
    M2.mkdir(parents=True, exist_ok=True)
    S.write_splits(M2 / "splits.json", s)
    REPORTS.mkdir(parents=True, exist_ok=True)
    (REPORTS / "m2_splits.md").write_text(f"# M2 splits (sha256 {s['sha256'][:16]})\n\n" + S.cell_table(s), encoding="utf-8", newline="\n")
    print({p: len(v) for p, v in s["parts"].items()}, "forced to cal:", len(forced), "sha", s["sha256"][:12])


def cmd_train(a):
    s = S.read_splits(M2 / "splits.json")
    gens = a.generators.split(",")
    Xtr, mtr = _frame(gens, "train", s)
    Xva, mva = _frame(gens, "val", s)
    LOG.info("train rows %d (clusters %d, neg %d); val rows %d (clusters %d, neg %d)", len(Xtr), mtr.input_key.nunique(),
             int((1 - mtr.y).sum()), len(Xva), mva.input_key.nunique(), int((1 - mva.y).sum()))
    art, rep = T.fit_m2(Xtr, mtr["y"].to_numpy(), Xva, mva["y"].to_numpy(), mva, s["sha256"], a.seed)
    rep["train_rows"], rep["train_clusters"], rep["generators"] = int(len(Xtr)), int(mtr.input_key.nunique()), gens
    T.save(art, rep, M2)
    print(json.dumps({k: rep[k] for k in ("selected_model", "selected_calibrator", "calibrated", "val_n", "val_neg")}))


def cmd_tau(a):
    s = S.read_splits(M2 / "splits.json")
    art = T.joblib.load(M2 / "m2.joblib")
    X, meta = _frame(a.generators.split(","), "cal", s)
    fr = meta.assign(score=T.predict(art, X))
    out = CT.run(fr, art, s["sha256"], a.alpha, a.delta, a.deployment)
    CT.write(out, OUT / "tau_star.json")
    print(json.dumps({k: out[k] for k in ("certified", "tau", "n_total", "n_min", "n_errors", "ucb", "coverage")}, default=str))


def cmd_diag(a):
    """TRAIN/VAL/CAL only. Writes out/reports/m2_diagnostics.{md,json}. Never opens a held-out set."""
    s = S.read_splits(M2 / "splits.json")
    art = T.joblib.load(M2 / "m2.joblib")
    gens = a.generators.split(",")
    parts = {p: _frame(gens, p, s) for p in ("train", "val", "cal")}
    meta_all = pd.concat([m.assign(partition=p) for p, (X, m) in parts.items()], ignore_index=True)
    (Xtr, mtr), (Xva, mva), (Xca, mca) = parts["train"], parts["val"], parts["cal"]
    prev = DG.prevalence_table(meta_all)
    p_val = T.predict(art, Xva)
    pooled = DG.M.auroc(p_val, mva["y"].to_numpy())
    gonly = DG.generator_only_baseline(Xtr, mtr["y"].to_numpy(), Xva, mva["y"].to_numpy())
    within = DG.within_generator(p_val, mva["y"].to_numpy(), mva)
    abl = DG.ablation(Xtr, mtr["y"].to_numpy(), Xva, mva["y"].to_numpy(),
                      {"no_generator": DG.GEN_COLS, "no_consensus": R.names(("C",)), "no_logprob": R.names(("U",)),
                       "structure_and_rule_only": [n for n in R.names() if n not in R.names(("S", "R"))]})
    oos = DG.out_of_sample_calibration(art, Xca, mca["y"].to_numpy(), mca)
    single = DG.single_feature_aurocs(Xtr, mtr["y"].to_numpy())
    neg = meta_all[meta_all["y"] == 0].groupby(["generator", "rule_id"])["input_key"].nunique().reset_index(name="negative_clusters")
    rep = {"prevalence": prev.to_dict("records"), "negative_clusters_by_rule": neg.to_dict("records"), "pooled_val_auroc": pooled, "generator_only": gonly, "within_generator_val": within,
           "ablation": abl, "calibration_on_cal": oos, "top_single_feature_auroc_train": single,
           "verdict": DG.verdict(pooled, gonly["auroc"], within, a.deployment)}
    REPORTS.mkdir(parents=True, exist_ok=True)
    md = ["# M2 diagnostics (TRAIN/VAL/CAL only)", "", f"**{rep['verdict']}**", "", "## Prevalence", "", "```\n" + prev.to_string(index=False) + "\n```",
          "", "## Negative clusters by generator and rule (train+val+cal)", "", "```\n" + neg.to_string(index=False) + "\n```", "", "## Ablation (val)", ""] + [f"- {k}: AUROC {v['auroc']:.4f}, log-loss {v['log_loss']:.4f}, features {v['n_features']}" for k, v in abl.items()] + \
         ["", "## Within-generator val AUROC", ""] + [f"- {g}: {json.dumps(v)}" for g, v in within.items()] + \
         ["", "## Calibration on CAL (calibrator fitted on VAL)", ""] + [f"- {g}: {json.dumps(v)}" for g, v in oos.items()] + \
         ["", "## Top single-feature AUROC (train)", ""] + [f"- {n}: {v:.3f}" for n, v in single]
    (REPORTS / "m2_diagnostics.md").write_text("\n".join(md) + "\n", encoding="utf-8", newline="\n")
    (REPORTS / "m2_diagnostics.json").write_text(json.dumps(rep, indent=1, sort_keys=True, default=str) + "\n", encoding="utf-8", newline="\n")
    print(rep["verdict"])


def cmd_diag2(a):
    """TRAIN/VAL/CAL only. Does M2 beat a (generator, rule) base-rate predictor? Writes out/reports/m2_diagnostics2.{md,json}."""
    s = S.read_splits(M2 / "splits.json")
    art = T.joblib.load(M2 / "m2.joblib")
    gens = a.generators.split(",")
    Xtr, mtr = _frame(gens, "train", s)
    Xva, mva = _frame(gens, "val", s)
    Xca, mca = _frame(gens, "cal", s)
    Xev = pd.concat([Xva, Xca], ignore_index=True)
    mev = pd.concat([mva, mca], ignore_index=True)
    p_m2 = T.predict(art, Xev)
    p_prior = DG.cell_prior_scores(mtr, mev)
    y = mev["y"].to_numpy()
    pooled = DG.beats_prior(p_m2, p_prior, y, mev["input_key"].to_numpy())
    by_gen = {}
    for g in sorted(mev["generator"].unique()):
        m = (mev["generator"] == g).to_numpy()
        if len(set(y[m])) == 2:
            by_gen[g] = DG.beats_prior(p_m2[m], p_prior[m], y[m], mev["input_key"].to_numpy()[m], reps=500)
        else:
            by_gen[g] = {"note": "single class", "rows": int(m.sum())}
    strat = DG.stratified_auroc(p_m2, y, mev)
    strat_prior = DG.stratified_auroc(p_prior, y, mev)
    ncls = DG.negative_class_table(pd.concat([mtr, mev], ignore_index=True))
    rep = {"eval_rows": int(len(mev)), "eval_clusters": int(mev["input_key"].nunique()), "eval_negative_clusters": int(mev[mev["y"] == 0]["input_key"].nunique()),
           "pooled": pooled, "by_generator": by_gen, "stratified_m2": strat, "stratified_prior": strat_prior,
           "negatives_by_class": ncls.to_dict("records"), "verdict": DG.verdict_prior(pooled)}
    L = ["# M2 vs the (generator, rule) base-rate predictor (VAL + CAL pooled; prior fitted on TRAIN only)", "", f"**{rep['verdict']}**", "",
         f"eval rows {rep['eval_rows']}, clusters {rep['eval_clusters']}, negative clusters {rep['eval_negative_clusters']}", "",
         "## By generator (model AUROC, prior AUROC, difference CI)", ""] + [f"- {g}: {json.dumps(v)}" for g, v in by_gen.items()] + \
        ["", "## Within (generator, rule) cells (M2); AUROC only where >= 3 positive and >= 3 negative clusters", ""] + [f"- {json.dumps(r)}" for r in strat] + \
        ["", "## Same cells, base-rate predictor", ""] + [f"- {json.dumps(r)}" for r in strat_prior if r["auroc"] is not None] + \
        ["", "## Negatives by oracle class (train+val+cal)", "", "```\n" + ncls.to_string(index=False) + "\n```"]
    REPORTS.mkdir(parents=True, exist_ok=True)
    (REPORTS / "m2_diagnostics2.md").write_text("\n".join(L) + "\n", encoding="utf-8", newline="\n")
    (REPORTS / "m2_diagnostics2.json").write_text(json.dumps(rep, indent=1, sort_keys=True, default=str) + "\n", encoding="utf-8", newline="\n")
    print(rep["verdict"])


def cmd_eval(a):
    s = S.read_splits(M2 / "splits.json")
    art = T.joblib.load(M2 / "m2.joblib")
    tau_info = json.loads((OUT / "tau_star.json").read_text(encoding="utf-8"))
    ks = load_key_sets(ROOT)
    X, meta = _frame(a.generators.split(","), "test", s)
    sets = {n: keys for n, keys in ks.held_out.items()}
    for name, keys in sorted(sets.items()):
        def evaluator(keys=keys):
            m = meta["input_key"].isin(set(keys)) & (meta["generator"] == a.deployment)
            fr = meta[m].assign(score=T.predict(art, X[m.to_numpy()]))
            sel = select_decisions(fr)
            res = RO.evaluate_selected(sel["score"], sel["y"], sel["input_key"], tau_info.get("tau") if tau_info.get("certified") else None)
            res["generator"] = a.deployment
            return res
        print(name, json.dumps(RO.run_once(f"{art['kind']}+{art['calibrator_name']}", name, evaluator, a.repeat_reason), default=str))


def main(argv=None) -> int:
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    ap = argparse.ArgumentParser()
    sub = ap.add_subparsers(dest="cmd", required=True)
    sub.add_parser("spec").set_defaults(fn=cmd_spec)
    p = sub.add_parser("splits"); p.add_argument("--seed", type=int, default=1337); p.set_defaults(fn=cmd_splits)
    for n, fn in (("train", cmd_train), ("tau", cmd_tau), ("diag", cmd_diag), ("diag2", cmd_diag2), ("eval", cmd_eval)):
        p = sub.add_parser(n)
        p.add_argument("--generators", default=",".join(GENS)); p.add_argument("--deployment", default="sft")
        p.add_argument("--seed", type=int, default=1337); p.add_argument("--alpha", type=float, default=0.05)
        p.add_argument("--delta", type=float, default=0.05); p.add_argument("--repeat-reason", default=None)
        p.set_defaults(fn=fn)
    a = ap.parse_args(argv)
    a.fn(a)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
