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
    for n, fn in (("train", cmd_train), ("tau", cmd_tau), ("eval", cmd_eval)):
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
