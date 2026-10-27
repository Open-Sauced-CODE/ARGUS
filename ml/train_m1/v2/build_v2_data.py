"""Build the RFT-v2 training set (H4, recipe a: REPLAY MIX).

    python -m ml.train_m1.v2.build_v2_data

Recipe: about 50% original SFT pairs (the replay, so nothing learned is lost) and 50% DIVERSE VERIFIED candidates.
  * Candidates come from the harvest tool (default: sft/B and zeroshot/A) and only for inputs that already have a
    TRAIN example. A candidate is kept only if the Phase 5 GATE accepts it (never the hidden checks), and its outcome
    matches the rule's route: 'fixed' for T0/M1 rules, 'escalated' for ESC rules.
  * Answers are deduplicated by canonical answer (ops + rationale_ref); at most 4 distinct answers per input,
    and the reference answer of the SFT data is always one of them.
  * Optional --extra-dir: a second dataset built with another seed; only ESC examples with a NEW input are added.
  * Hard leak check: the build aborts if any row's full_hash is in held_out_hashes.txt or heldout_hashes.txt.
Output (ml/train_m1/v2/data/, git-ignored):  v2_train.jsonl (training rows), v2_train.meta.jsonl, v2_train.manifest.json
The build is deterministic: same inputs and same --seed give byte-identical files.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import random
import sys
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any, Callable, Dict, Iterable, List, Optional, Sequence, Set, Tuple

from ml.train_m2.harvest.paths import DEFAULT_OUT, REPO_ROOT
from ml.train_m2.harvest.pilot import canonical_answer
from ml.train_m2.harvest.store import iter_lines, sha256_file

ME_DIR = REPO_ROOT / "ml" / "mutation_engine"
V2_DIR = REPO_ROOT / "ml" / "train_m1" / "v2"
DEFAULT_TRAIN = ME_DIR / "dataset" / "train.jsonl"
DEFAULT_HELD = (ME_DIR / "held_out" / "held_out_hashes.txt", REPO_ROOT / "ml" / "train_m1" / "data" / "heldout_hashes.txt")
DEFAULT_POOL = ("sft/B", "zeroshot/A")
DEFAULT_SEED = 20261029
CAP = 4
GATE_CHUNK = 200


class BuildError(RuntimeError):
    """The data cannot be built safely (leak, key mismatch, missing file)."""


def example_input_key(record: Dict[str, Any]) -> str:
    return json.dumps({"fields": record["fields"], "resource_ref": record["resource_ref"], "rule_id": record["rule_id"]},
                      sort_keys=True, separators=(",", ":"))


def read_jsonl(path: Path) -> List[Dict[str, Any]]:
    return [json.loads(raw) for raw in Path(path).read_bytes().decode("utf-8").splitlines() if raw.strip()]


def load_held_hashes(paths: Iterable[Path]) -> Set[str]:
    held: Set[str] = set()
    for path in paths:
        if not Path(path).exists():
            raise BuildError("held-out hash file not found: %s (it must exist so the leak check can run)" % path)
        held.update(Path(path).read_text(encoding="utf-8").split())
    return held


def canon_of_patch(patch: Dict[str, Any] | str | Any) -> str:
    if isinstance(patch, str):
        return canonical_answer(patch)
    return canonical_answer(json.dumps(patch))


def load_pool(folders: Sequence[Path], allowed_keys: Set[str]) -> Dict[str, List[Tuple[str, int, str]]]:
    """input_key -> [(folder label, sample_idx, content)] for successful generations on allowed inputs."""
    pool: Dict[str, List[Tuple[str, int, str]]] = defaultdict(list)
    for folder in folders:
        label = "/".join(Path(folder).parts[-2:])
        if not Path(folder).is_dir():
            raise BuildError("pool folder not found: %s" % folder)
        for _p, line in iter_lines(Path(folder)):
            if line["error"] is None and line["input_key"] in allowed_keys:
                pool[line["input_key"]].append((label, line["sample_idx"], line["content"]))
    return pool


def gate_accepts(result: Any, route: str) -> bool:
    """Gate verdict plus route consistency (an escalation is only right for ESC rules, a fix only for fix rules)."""
    if getattr(result, "unsafe", False) or not getattr(result, "passed", False):
        return False
    return getattr(result, "outcome", None) == ("escalated" if route == "ESC" else "fixed")


def build_rows(
    train: Sequence[Dict[str, Any]],
    pool: Dict[str, List[Tuple[str, int, str]]],
    gate_many_fn: Callable[[List[Any]], List[Any]],
    *,
    seed: int = DEFAULT_SEED,
    cap: int = CAP,
    held: Set[str] = frozenset(),  # type: ignore[assignment]
    extra: Sequence[Dict[str, Any]] = (),
) -> Tuple[List[Dict[str, Any]], Dict[str, Any]]:
    """Return (rows, stats). A row is {kind, example_id, input_key, rule_id, route, full_hash, record, patch}."""
    kept_train = [ex for ex in train if ex["meta"]["full_hash"] not in held]
    dropped_held = len(train) - len(kept_train)
    by_key: Dict[str, List[Dict[str, Any]]] = defaultdict(list)
    for ex in sorted(kept_train, key=lambda e: e["id"]):
        by_key[example_input_key(ex["input"])].append(ex)
    keys = sorted(by_key)
    anchors = {k: by_key[k][0] for k in keys}
    refs: Dict[str, Set[str]] = {k: {canon_of_patch(e["target"]) for e in by_key[k]} for k in keys}

    # 1. candidate patches per input, deterministic order, deduplicated, references removed
    staged: List[Tuple[str, str, Dict[str, Any], str]] = []  # (key, canon, patch, source)
    for key in keys:
        seen: Set[str] = set(refs[key])
        for label, idx, content in sorted(pool.get(key, []), key=lambda t: (t[0], t[1])):
            try:
                patch = json.loads(content)
            except ValueError:
                continue
            if not isinstance(patch, dict):
                continue
            canon = canon_of_patch(patch)
            if canon in seen:
                continue
            seen.add(canon)
            staged.append((key, canon, patch, "%s#%d" % (label, idx)))

    # 2. verify with the gate (never the hidden checks)
    accepted: Dict[str, List[Tuple[str, Dict[str, Any], str]]] = defaultdict(list)
    for start in range(0, len(staged), GATE_CHUNK):
        chunk = staged[start:start + GATE_CHUNK]
        results = gate_many_fn([(anchors[key]["input"], patch) for key, _c, patch, _s in chunk])
        if len(results) != len(chunk):
            raise BuildError("gate returned %d results for %d candidates" % (len(results), len(chunk)))
        for (key, canon, patch, source), result in zip(chunk, results):
            if gate_accepts(result, anchors[key]["meta"]["route"]):
                accepted[key].append((canon, patch, source))

    # 3. cap at `cap` distinct answers per input, references included
    cand_rows: List[Dict[str, Any]] = []
    for key in keys:
        room = max(0, cap - len(refs[key]))
        options = list(accepted.get(key, []))
        random.Random("%s:%s" % (seed, key)).shuffle(options)
        for canon, patch, source in options[:room]:
            ex = anchors[key]
            cand_rows.append({"kind": "cand", "example_id": ex["id"], "input_key": key, "rule_id": ex["rule_id"],
                              "route": ex["meta"]["route"], "full_hash": ex["meta"]["full_hash"], "record": ex["input"],
                              "patch": patch, "source": source})

    # 4. replay side: every input's reference first, then more SFT examples until the two sides are equal
    ref_rows = [{"kind": "sft", "example_id": anchors[k]["id"], "input_key": k, "rule_id": anchors[k]["rule_id"],
                 "route": anchors[k]["meta"]["route"], "full_hash": anchors[k]["meta"]["full_hash"],
                 "record": anchors[k]["input"], "patch": anchors[k]["target"], "source": "sft_train"} for k in keys]
    used = {r["example_id"] for r in ref_rows}
    others = [ex for ex in sorted(kept_train, key=lambda e: e["id"]) if ex["id"] not in used]
    random.Random("%s:replay" % seed).shuffle(others)
    need = max(0, len(cand_rows) - len(ref_rows))
    sft_rows = ref_rows + [{"kind": "sft", "example_id": ex["id"], "input_key": example_input_key(ex["input"]),
                            "rule_id": ex["rule_id"], "route": ex["meta"]["route"], "full_hash": ex["meta"]["full_hash"],
                            "record": ex["input"], "patch": ex["target"], "source": "sft_train"} for ex in others[:need]]

    # 5. extra ESC variety: only examples whose INPUT is new
    known_keys = set(keys)
    esc_rows: List[Dict[str, Any]] = []
    for ex in sorted(extra, key=lambda e: e["id"]):
        key = example_input_key(ex["input"])
        if ex["meta"]["route"] != "ESC" or key in known_keys or ex["meta"]["full_hash"] in held:
            continue
        known_keys.add(key)
        esc_rows.append({"kind": "esc_extra", "example_id": ex["id"], "input_key": key, "rule_id": ex["rule_id"], "route": "ESC",
                         "full_hash": ex["meta"]["full_hash"], "record": ex["input"], "patch": ex["target"], "source": "extra_dir"})

    rows = sft_rows + cand_rows + esc_rows
    random.Random("%s:final" % seed).shuffle(rows)
    check_no_leak(rows, held)
    seen_pairs: Set[Tuple[str, str]] = set()
    for r in rows:
        pair = (r["input_key"], canon_of_patch(r["patch"]))
        if pair in seen_pairs and r["kind"] != "sft":
            raise BuildError("duplicate (input, answer) pair in the build for input %s" % r["input_key"][:60])
        seen_pairs.add(pair)
    per_input = Counter(len({canon_of_patch(r["patch"]) for r in rows if r["input_key"] == k}) for k in keys)
    stats = {
        "train_examples": len(train), "train_examples_dropped_as_held_out": dropped_held, "distinct_train_inputs": len(keys),
        "pool_candidates_staged": len(staged), "pool_candidates_gate_accepted": sum(len(v) for v in accepted.values()),
        "rows_total": len(rows), "rows_by_kind": dict(Counter(r["kind"] for r in rows)),
        "rows_by_route": dict(Counter(r["route"] for r in rows)),
        "rows_by_rule": dict(sorted(Counter(r["rule_id"] for r in rows).items())),
        "distinct_answers_per_input_histogram": {str(k): v for k, v in sorted(per_input.items())},
        "esc_distinct_inputs_before": len({k for k in keys if anchors[k]["meta"]["route"] == "ESC"}),
        "esc_distinct_inputs_added": len(esc_rows),
        "sft_share": round(len(sft_rows) / len(rows), 4) if rows else 0.0,
    }
    return rows, stats


def check_no_leak(rows: Sequence[Dict[str, Any]], held: Set[str]) -> None:
    bad = sorted({r["full_hash"] for r in rows if r["full_hash"] in held})
    if bad:
        raise BuildError("LEAK: %d training row hash(es) appear in a held-out hash file, first: %s" % (len(bad), bad[0]))


def to_training_row(row: Dict[str, Any], messages_fn: Callable[[Dict[str, Any]], List[Dict[str, Any]]],
                    patch_json_fn: Callable[[Dict[str, Any]], str], flat: bool = False) -> Dict[str, Any]:
    if flat:
        msgs = list(messages_fn(row["record"]))
        sys_msg = next((m["content"] for m in msgs if m["role"] == "system"), "")
        user_msg = next((m["content"] for m in msgs if m["role"] == "user"), "")
        rec_canon = json.dumps(row["record"], sort_keys=True, separators=(",", ":"))
        input_hash = hashlib.sha256(rec_canon.encode("utf-8")).hexdigest()
        return {
            "assistant": patch_json_fn(row["patch"]),
            "full_hash": row["full_hash"],
            "id": row["example_id"],
            "input_hash": input_hash,
            "input_key": row["input_key"],
            "system": sys_msg,
            "user": user_msg,
        }
    return {"messages": list(messages_fn(row["record"])) + [{"role": "assistant", "content": patch_json_fn(row["patch"])}]}


def write_outputs(rows: Sequence[Dict[str, Any]], stats: Dict[str, Any], out_dir: Path, messages_fn, patch_json_fn,
                  seed: int, extra_info: Dict[str, Any], flat: bool = False) -> Dict[str, Path]:
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    train_path, meta_path, manifest_path = out_dir / "v2_train.jsonl", out_dir / "v2_train.meta.jsonl", out_dir / "v2_train.manifest.json"
    train_path.write_bytes("".join(json.dumps(to_training_row(r, messages_fn, patch_json_fn, flat=flat), sort_keys=True, ensure_ascii=True) + "\n" for r in rows).encode("ascii"))
    meta_path.write_bytes("".join(json.dumps({k: r[k] for k in ("kind", "example_id", "input_key", "rule_id", "route", "full_hash", "source")},
                                             sort_keys=True, ensure_ascii=True) + "\n" for r in rows).encode("ascii"))
    manifest = {"seed": seed, "stats": stats, "train_sha256": sha256_file(train_path), "meta_sha256": sha256_file(meta_path), **extra_info}
    manifest_path.write_bytes((json.dumps(manifest, indent=2, sort_keys=True, ensure_ascii=True) + "\n").encode("ascii"))
    return {"train": train_path, "meta": meta_path, "manifest": manifest_path}


def main(argv: Optional[Sequence[str]] = None) -> int:
    p = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    p.add_argument("--train", type=Path, default=DEFAULT_TRAIN)
    p.add_argument("--harvest-root", type=Path, default=DEFAULT_OUT)
    p.add_argument("--pool", nargs="+", default=list(DEFAULT_POOL), help="harvest sub-folders, e.g. sft/B zeroshot/A (profile letter last)")
    p.add_argument("--held-out", nargs="+", type=Path, default=list(DEFAULT_HELD))
    p.add_argument("--extra-dir", type=Path, default=None, help="a second dataset folder (with train.jsonl) built with another seed")
    p.add_argument("--seed", type=int, default=DEFAULT_SEED)
    p.add_argument("--cap", type=int, default=CAP)
    p.add_argument("--out", type=Path, default=V2_DIR / "data")
    p.add_argument("--format-from", type=Path, default=REPO_ROOT / "ml" / "train_m1" / "data" / "sft_train.jsonl",
                   help="existing Phase 5 SFT file; the build aborts if its row format differs from ours")
    args = p.parse_args(list(sys.argv[1:] if argv is None else argv))
    try:
        from ml.mutation_engine.qa.gate_stub import gate_many
        from ml.train_m1.prompt import chat_messages, patch_json
    except ImportError as exc:
        print("cannot import the frozen gate/prompt modules: %s" % exc)
        return 2
    try:
        held = load_held_hashes(args.held_out)
        train = read_jsonl(args.train)
        keys = {example_input_key(ex["input"]) for ex in train}
        folders = [args.harvest_root / Path(*sub.split("/")) for sub in args.pool]
        from ml.train_m2.harvest.store import part_files
        pool_inputs = {line["input_key"] for f in folders for _p, line in iter_lines(f)} if folders else set()
        coverage = len(keys & pool_inputs) / len(keys) if keys else 0.0
        if coverage < 0.95:
            raise BuildError("only %.0f%% of the train inputs appear in the harvest pool: the input_key function does not match "
                             "(check ml.mutation_engine.dataset_io.input_key) or the harvest is incomplete" % (100 * coverage))
        pool = load_pool(folders, keys)
        extra = read_jsonl(args.extra_dir / "train.jsonl") if args.extra_dir else []
        rows, stats = build_rows(train, pool, gate_many, seed=args.seed, cap=args.cap, held=held, extra=extra)
        use_flat = False
        if args.format_from and Path(args.format_from).exists():
            first = read_jsonl(args.format_from)[0]
            if "system" in first and "user" in first and "assistant" in first and "messages" not in first:
                use_flat = True
            mine = to_training_row(rows[0], chat_messages, patch_json, flat=use_flat)
            if set(first) != set(mine):
                raise BuildError("row format differs from %s: it has keys %s, we write %s. Tell me; the notebook expects the old format."
                                 % (args.format_from, sorted(first), sorted(mine)))
        info = {"pool_folders": args.pool, "pool_file_hashes": {str(f): [sha256_file(p_) for p_ in part_files(f)] for f in folders},
                "train_file": str(args.train), "train_sha256": sha256_file(args.train), "held_out_files": [str(h) for h in args.held_out],
                "extra_dir": str(args.extra_dir) if args.extra_dir else None}
        paths = write_outputs(rows, stats, args.out, chat_messages, patch_json, args.seed, info, flat=use_flat)
    except BuildError as exc:
        print("BUILD STOPPED: %s" % exc)
        return 2
    print(json.dumps(stats, indent=2, sort_keys=True))
    print("Wrote %s" % paths["train"])
    return 0


if __name__ == "__main__":
    sys.exit(main())
