"""
ARGUS Phase 5, Step 9 - build, check and freeze the synthetic dataset (Tier A train and validation, Tier B1, Tier B2).

    python -m ml.mutation_engine.build_dataset --seed 1337

Sizes (defaults): train 5000, validation 500, B1 400, B2 250. Every set comes from ONE bucket of repositories:
train from train-bucket bases, validation from val-bucket bases, B1 and B2 from test-bucket bases.

  Tier A train / val : every mutator gets at least --min-per-mutator examples (fewer if its bases or distinct inputs run out;
                       the shortfall is printed and written to the card). Resources that contain a HELD-OUT mutator pair
                       are never produced.
  Tier B1            : resources that contain a held-out pair of mutators (never seen in train or validation).
  Tier B2            : the encryption-at-rest family only (examples of its three rules).
  train_ablation_no_encryption : train without any resource that used an encryption-at-rest mutator (for the B2 ablation model).

Nothing is written to MANIFEST.sha256 unless all eight QA checks pass.
"""

import argparse
import json
import math
import random
import subprocess
import sys
from collections import Counter
from dataclasses import dataclass, field
from pathlib import Path

from ml.mutation_engine.compose import load_violation_counts, mutator_weights
from ml.mutation_engine.dataset_io import canon, full_hash, input_key, read_jsonl, sha256_text, target_key, write_jsonl
from ml.mutation_engine.examples import build_from_base
from ml.mutation_engine.model import Resource
from ml.mutation_engine.mutators import ALL_MUTATORS, BY_ID
from ml.mutation_engine.project import throwaway_vault
from ml.mutation_engine.synth_bases import BASES_DIR, load_all_bases

ME_DIR = Path(__file__).resolve().parent
REPO_ROOT = ME_DIR.parents[1]
DATASET_DIR = ME_DIR / "dataset"
HELD_OUT_DIR = ME_DIR / "held_out"
QA_DIR = ME_DIR / "qa"
VIOLATIONS_CSV = REPO_ROOT / "ml" / "real_data" / "out" / "violation_counts_train.csv"

HELD_OUT_PAIRS = (
    ("m_s3_sse_off", "m_s3_versioning_off"),
    ("m_s3_sse_algo", "m_s3_public_block_off"),
    ("m_s3_lifecycle_off", "m_s3_logging_off"),
    ("m_account_detection_off", "m_account_mfa_off"),
    ("m_rds_unencrypted", "m_region_outside_approved"),
)
FAMILY_NAME = "encryption-at-rest"
FAMILY_MUTATORS = ("m_s3_sse_off", "m_s3_sse_algo", "m_rds_unencrypted")
FAMILY_RULES = tuple(sorted({r for m in FAMILY_MUTATORS for r in BY_ID[m].rules}))
K_DIST = {1: 0.60, 2: 0.30, 3: 0.07, 4: 0.03}


def has_held_out_pair(mutator_ids):
    ids = set(mutator_ids)
    return any(set(pair) <= ids for pair in HELD_OUT_PAIRS)


@dataclass
class Spec:
    name: str            # train, val, B1, B2
    tier: str
    bucket: str
    total: int
    min_per_mutator: int
    cap: int             # at most this many examples with the same (input, target) per rule
    k_dist: dict = field(default_factory=lambda: dict(K_DIST))
    combo_mode: str = "avoid"   # avoid (no held-out pair), pairs (only held-out pairs), any
    mutator_ids: tuple = None
    rule_filter: tuple = None


def applicable_indexes(bases, mutator):
    out = []
    for i, base in enumerate(bases):
        if base["resource_type"] not in mutator.resource_types:
            continue
        res = Resource.from_base(base)
        if any(mutator.prepare(res, v) is not None for v in mutator.variants):
            out.append(i)
    return out


def _pick_k(rng, k_dist):
    ks = sorted(k_dist)
    return rng.choices(ks, weights=[k_dist[k] for k in ks], k=1)[0]


def build_split(spec, all_bases, weights, used_hashes, seed, log=print):
    """Returns (examples, stats). `used_hashes` is shared between splits and updated here."""
    rng = random.Random("{}|{}".format(seed, spec.name))
    bases = [b for b in all_bases if b["source"]["bucket"] == spec.bucket]
    stats = {"bases": len(bases), "attempts": 0, "rejected": Counter(), "shortfall": {}, "quota": {}}
    examples, caps = [], Counter()
    group_no = 0

    if spec.combo_mode == "pairs":
        units = [(pair, [BY_ID[pair[0]], BY_ID[pair[1]]]) for pair in HELD_OUT_PAIRS]
        quota = {"+".join(pair): int(math.ceil(spec.total / len(units))) for pair, _ in units}
        app = {"+".join(pair): sorted(set(applicable_indexes(bases, ms[0])) & set(applicable_indexes(bases, ms[1])))
               for pair, ms in units}
    else:
        ids = list(spec.mutator_ids) if spec.mutator_ids else [m.mutator_id for m in ALL_MUTATORS]
        app = {mid: applicable_indexes(bases, BY_ID[mid]) for mid in ids}
        live = [mid for mid in ids if app[mid]]
        soft = {mid: math.sqrt(weights.get(mid, 1.0)) for mid in live}
        total_w = sum(soft.values()) or 1.0
        quota = {mid: max(spec.min_per_mutator, int(round(spec.total * soft[mid] / total_w))) for mid in live}
        for mid in ids:
            if not app[mid]:
                stats["shortfall"][mid] = "no applicable base in the {} bucket".format(spec.bucket)
    stats["quota"] = dict(quota)
    counts = Counter()

    for unit in sorted(quota):
        if not app.get(unit):
            stats["shortfall"][unit] = "no applicable base in the {} bucket".format(spec.bucket)
            continue
        idle = 0
        while counts[unit] < quota[unit] and idle < 400:
            stats["attempts"] += 1
            idle += 1
            base = bases[rng.choice(app[unit])]
            if spec.combo_mode == "pairs":
                pair = unit.split("+")
                mutators = [BY_ID[pair[0]], BY_ID[pair[1]]]
                k, force = 2, {}
            else:
                mutators = None
                k, force = _pick_k(rng, spec.k_dist), {unit: 1000.0}
            with throwaway_vault() as vault:
                made = build_from_base(base, rng, k, vault, "F", weights=force, mutators=mutators)
            if not made:
                stats["rejected"]["nothing_built"] += 1
                continue
            used_mutators = made[0]["meta"]["mutators"]
            if spec.combo_mode == "pairs":
                if set(used_mutators) != set(unit.split("+")):
                    stats["rejected"]["pair_not_complete"] += 1
                    continue
            else:
                if unit not in used_mutators:
                    stats["rejected"]["mutator_not_chosen"] += 1
                    continue
                if spec.combo_mode == "avoid" and has_held_out_pair(used_mutators):
                    stats["rejected"]["held_out_pair"] += 1
                    continue
            if spec.rule_filter:
                made = [e for e in made if e["rule_id"] in spec.rule_filter]
                if not made:
                    stats["rejected"]["rule_filtered"] += 1
                    continue
            fresh = Counter()
            hashes = []
            ok = True
            for ex in made:
                h = full_hash(ex["rule_id"], ex["qa"]["mutated"])
                key = (ex["rule_id"], input_key(ex), target_key(ex))
                fresh[key] += 1
                if h in used_hashes or h in hashes or caps[key] + fresh[key] > spec.cap:
                    ok = False
                    break
                hashes.append(h)
            if not ok:
                stats["rejected"]["duplicate_or_cap"] += 1
                continue
            group_no += 1
            for ex, h in zip(made, hashes):
                ex["meta"]["group_id"] = "g-{}-{:05d}".format(spec.name, group_no)
                ex["meta"]["full_hash"] = h
                ex["meta"]["input_hash"] = sha256_text(input_key(ex))
                ex["meta"]["tier"] = spec.tier
                ex["meta"]["split"] = spec.name
                used_hashes.add(h)
                caps[(ex["rule_id"], input_key(ex), target_key(ex))] += 1
                counts[unit] += 1 if spec.combo_mode == "pairs" else 0
                if spec.combo_mode != "pairs":
                    counts[ex["meta"]["responsible_mutator"]] += 1
                examples.append(ex)
            idle = 0
        if counts[unit] < quota[unit]:
            stats["shortfall"][unit] = "got {} of {} examples".format(counts[unit], quota[unit])
    rng.shuffle(examples)
    stats["examples"] = len(examples)
    log("  {:<5} {:>6} examples   (shortfalls: {})".format(spec.name, len(examples), len(stats["shortfall"])))
    stats["rejected"] = dict(stats["rejected"])
    return examples, stats


def specs(args):
    return [
        Spec("train", "A-train", "train", args.train, args.min_per_mutator, args.cap_train, combo_mode="avoid"),
        Spec("val", "A-val", "val", args.val, args.min_per_mutator_val, args.cap_val, combo_mode="avoid"),
        Spec("B1", "B1", "test", args.b1, 0, args.cap_b1, combo_mode="pairs"),
        Spec("B2", "B2", "test", args.b2, args.min_per_mutator_b2, args.cap_b2, k_dist={1: 0.8, 2: 0.2},
             combo_mode="any", mutator_ids=FAMILY_MUTATORS, rule_filter=FAMILY_RULES),
    ]


def _git_head():
    try:
        out = subprocess.run(["git", "-C", str(REPO_ROOT), "rev-parse", "--short", "HEAD"], capture_output=True, text=True, timeout=20)
        return out.stdout.strip() or "unknown"
    except Exception:
        return "unknown"


def license_table(bases_dir):
    counts = Counter()
    for name in ("manifest.csv",):
        path = Path(bases_dir) / name
        if path.exists():
            import csv
            with open(path, newline="", encoding="utf-8") as handle:
                for row in csv.DictReader(handle):
                    counts[row["license"]] += 1
    return counts


def write_card(path, args, split_stats, qa_stats, shortfalls, licenses):
    s = qa_stats["splits"]
    lines = [
        "# ARGUS Phase 5 - dataset card",
        "",
        "Built by `python -m ml.mutation_engine.build_dataset --seed {}` at commit `{}`. Do not edit by hand.".format(args.seed, _git_head()),
        "",
        "## What it is",
        "Synthetic (broken resource, reference Patch-IR fix) pairs made by the mutation engine from clean base resources taken from real",
        "public Terraform (TerraDS) plus documented synthetic bases. The model input is exactly what the Phase 4 airlock returns for one",
        "(resource, rule) pair; the target is the Patch-IR fix. No paid API was used anywhere.",
        "",
        "## Splits",
        "| split | examples | distinct inputs | ambiguous inputs | source bucket |",
        "|---|---:|---:|---:|---|",
    ]
    bucket = {"train": "train", "val": "val", "B1": "test", "B2": "test"}
    for name in ("train", "val", "B1", "B2"):
        if name in s:
            lines.append("| {} | {} | {} | {} | {} |".format(name, s[name]["examples"], s[name]["distinct_inputs"], s[name]["ambiguous_inputs"], bucket[name]))
    lines += ["", "Distinct inputs are far fewer than examples (decision D10): the airlock shows the model only the fields of one rule, so many",
              "examples are identical to the model. Report both numbers in the paper. An ambiguous input is one input with more than one",
              "reference patch (for example the CIS encryption rule cannot show whether the algorithm was cleared).", "",
              "## Examples per mutator", "| mutator | " + " | ".join(n for n in ("train", "val", "B1", "B2") if n in s) + " |",
              "|---|" + "---:|" * len([n for n in ("train", "val", "B1", "B2") if n in s])]
    for m in ALL_MUTATORS:
        lines.append("| {} | {} |".format(m.mutator_id, " | ".join(str(s[n]["by_mutator"].get(m.mutator_id, 0)) for n in ("train", "val", "B1", "B2") if n in s)))
    lines += ["", "## Routes (fix versus escalate)"]
    for name in ("train", "val", "B1", "B2"):
        if name in s:
            lines.append("- {}: {}".format(name, s[name]["by_route"]))
    lines += ["", "## Overlap of inputs with train (not a leak by the full-hash rule, see D10)"]
    for name, v in qa_stats["input_overlap_with_train"].items():
        lines.append("- {}: {} of {} examples have an input that also appears in train".format(name, v["examples_with_input_seen_in_train"], v["examples"]))
    lines += ["", "## Shortfalls against the quota (not errors; the data ran out)"]
    any_short = False
    for name, st in split_stats.items():
        for unit, why in sorted(st["shortfall"].items()):
            lines.append("- {} / {}: {}".format(name, unit, why))
            any_short = True
    if not any_short:
        lines.append("- none")
    lines += ["", "## Held-out design",
              "- Held-out mutator pairs (never in train or validation): " + "; ".join("+".join(p) for p in HELD_OUT_PAIRS),
              "- B2 family: {} (rules {}). `train_ablation_no_encryption.jsonl` has no resource that used a family mutator.".format(FAMILY_NAME, ", ".join(FAMILY_RULES)),
              "- Honest note on B1 (decision D17): the airlock shows only one rule's fields, so a combination of mutators is invisible to the",
              "  model. B1 therefore measures generalisation to unseen repositories and decoys, plus resource-level success (all findings of",
              "  one resource fixed), not 'unseen combinations' in the model's own view.",
              "- Validation has no bases for the personal-data S3 rules (versioning, lifecycle) because no validation-bucket repository gave a",
              "  clean personal-data bucket; those rules are T0-covered and are checked by the T0 tests instead.",
              "", "## Known limitations",
              "- Synthetic completed S3 bases are only as diverse as the real extras they inherit (decision D9).",
              "- Operations add_policy_statement, remove_policy_statement and enable_feature are unused (decision D13).",
              "- Security-group fixes use the placeholder INTERNAL_CIDR, resolved by the Phase 7 compiler (decision D12).",
              "- Escalate share is about {:.1f}% of train because every mutator gets a minimum number of examples.".format(
                  100.0 * s["train"]["by_route"].get("escalate", 0) / max(1, s["train"]["examples"])),
              "", "## Source repositories by licence (Tier A bases, from bases/manifest.csv)"]
    for lic, n in sorted(licenses.items(), key=lambda kv: (-kv[1], kv[0])):
        lines.append("- {}: {} bases".format(lic, n))
    lines += ["", "## Intended use", "Training and evaluating the M1 remediation model of ARGUS. Not for any other purpose.", ""]
    Path(path).write_text("\n".join(lines), encoding="ascii", errors="replace")


def main(argv=None):
    p = argparse.ArgumentParser(description="Build, QA-check and freeze the Phase 5 dataset")
    p.add_argument("--seed", type=int, default=1337)
    p.add_argument("--train", type=int, default=5000)
    p.add_argument("--val", type=int, default=500)
    p.add_argument("--b1", type=int, default=400)
    p.add_argument("--b2", type=int, default=250)
    p.add_argument("--min-per-mutator", type=int, default=100)
    p.add_argument("--min-per-mutator-val", type=int, default=8)
    p.add_argument("--min-per-mutator-b2", type=int, default=40)
    p.add_argument("--cap-train", type=int, default=40)
    p.add_argument("--cap-val", type=int, default=10)
    p.add_argument("--cap-b1", type=int, default=10)
    p.add_argument("--cap-b2", type=int, default=20)
    p.add_argument("--bases-dir", default=str(BASES_DIR))
    p.add_argument("--out", default=str(ME_DIR), help="folder that receives dataset/, held_out/ and qa/ (default: ml/mutation_engine)")
    p.add_argument("--skip-airlock-recheck", action="store_true", help="skip QA check 7 (faster, for trial runs only)")
    options = p.parse_args(argv)

    out = Path(options.out)
    dataset_dir, held_dir, qa_dir = out / "dataset", out / "held_out", out / "qa"
    bases = load_all_bases(options.bases_dir)
    if not bases:
        print("No bases found in {}. Run Step 4 and synth_bases first.".format(options.bases_dir))
        return 2
    weights = mutator_weights(load_violation_counts(VIOLATIONS_CSV))
    print("Loaded {} bases. Building (this can take several minutes) ...".format(len(bases)))

    used, built, split_stats = set(), {}, {}
    for spec in specs(options):
        built[spec.name], split_stats[spec.name] = build_split(spec, bases, weights, used, options.seed)

    n = 0
    for name in ("train", "val", "B1", "B2"):
        for ex in built[name]:
            n += 1
            ex["id"] = "ex-{:06d}".format(n)
    ablation = [ex for ex in built["train"] if not set(ex["meta"]["mutators"]) & set(FAMILY_MUTATORS)]

    write_jsonl(dataset_dir / "train.jsonl", built["train"])
    write_jsonl(dataset_dir / "val.jsonl", built["val"])
    write_jsonl(dataset_dir / "train_ablation_no_encryption.jsonl", ablation)
    write_jsonl(held_dir / "tierB1.jsonl", built["B1"])
    write_jsonl(held_dir / "tierB2.jsonl", built["B2"])
    hashes = sorted({ex["meta"]["full_hash"] for name in ("val", "B1", "B2") for ex in built[name]})
    (held_dir / "held_out_hashes.txt").write_text("\n".join(hashes) + "\n", encoding="ascii", newline="\n")

    from ml.mutation_engine.qa.checks import CHECK_LABELS, run_checks
    from ml.mutation_engine.qa.run_all import write_report

    print("Running the eight QA checks ...")
    report = run_checks(built, recheck_airlock=not options.skip_airlock_recheck, log=lambda m: print("  " + m))
    qa_dir.mkdir(parents=True, exist_ok=True)
    write_report(qa_dir / "report.md", report, built)
    if report["failures"]:
        print("QA FAILED: {} problem(s). First ones:".format(len(report["failures"])))
        for f in report["failures"][:10]:
            print("  check {} [{}] {}: {}".format(f["check"], CHECK_LABELS[f["check"]], f["id"], f["detail"]))
        print("Nothing was frozen. See {}".format(qa_dir / "report.md"))
        return 1

    write_card(dataset_dir / "DATASET_CARD.md", options, split_stats, report["stats"],
               {k: v["shortfall"] for k, v in split_stats.items()}, license_table(options.bases_dir))
    (dataset_dir / "build_report.json").write_text(json.dumps({"seed": options.seed, "params": vars(options), "splits": split_stats,
                                                              "qa": report["stats"]}, indent=2, sort_keys=True, default=str) + "\n", encoding="ascii")
    from ml.tools.verify_manifest import write_manifest
    write_manifest(out)
    print("OK. Frozen: train {} / val {} / B1 {} / B2 {} / train-ablation {}".format(
        len(built["train"]), len(built["val"]), len(built["B1"]), len(built["B2"]), len(ablation)))
    print("Next: python -m ml.mutation_engine.qa.run_all   (readable report and the 50-example hand inspection)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
