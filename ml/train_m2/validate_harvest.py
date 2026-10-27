"""Validate a Phase 6 harvest delivery (schema m2.harvest.v1). This is the gatekeeper for Prabhav's files.

    py -m ml.train_m2.validate_harvest --root ml/train_m2/harvest_out [--allow-partial] [--require-manifests]

Layout it expects:  <root>/<generator>/<profile>/part-NNNN.jsonl  (generator: zeroshot sft rft rft_v2; profile: A B).
Every (generator, profile) folder gets the checks below. A check is PASS, WARN, FAIL or INFO; any FAIL rejects the delivery.

    SCHEMA          every line is valid JSON and matches contract/harvest_line.schema.json
    FOLDER_FIELDS   the generator and profile written on each line match the folder it sits in
    DUPLICATES      exactly one line per (input_key, sample_idx)
    KEYS            every input_key is one of the 321 inputs in contract/harvest_inputs.jsonl
    COMPLETENESS    all inputs x 8 samples present (a gap fails, unless --allow-partial, which only reports coverage)
    TEXT_EQ_TOKENS  the concatenated token texts equal the content (WARN up to 0.5 percent of lines, FAIL above)
    PROFILE         temperature, top_p and seed follow the profile rules of the contract
    LOGPROB         mean log-probability per line is above -5 (FAIL if more than 2 percent of lines are below)
    ERRORS          error-line rate (WARN above 2 percent, FAIL above 10 percent; judged only with 50 or more lines)
    VERSIONS        one ollama_version and at most one model_digest per folder
    MANIFEST        sha256 and line counts of each part match the manifest (missing manifest: WARN, or FAIL with
                    --require-manifests)
    REPLICATION     profile A only, information only: how often the new text equals the Phase 5 candidate logs

Exit code 0 = ACCEPTED, 1 = REJECTED, 2 = nothing to validate or bad usage. The last line of the report is always
ACCEPTED or REJECTED with the reasons, ready to paste into chat.
"""

from __future__ import annotations

import argparse
import json
import sys
from collections import Counter
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, Iterator, Mapping, Sequence

from jsonschema import Draft202012Validator

from ml.train_m2.common import load_inputs, repo_root, sha256_file, write_provenance

PASS, WARN, FAIL, INFO = "PASS", "WARN", "FAIL", "INFO"
GENERATORS = ("zeroshot", "sft", "rft", "rft_v2")
PROFILES = ("A", "B")
N_SAMPLES = 8
TEXT_MISMATCH_FAIL = 0.005
ERROR_WARN, ERROR_FAIL, ERROR_RATE_MIN_LINES = 0.02, 0.10, 50
MEAN_LP_FLOOR, MEAN_LP_BAD_SHARE_FAIL = -5.0, 0.02
COLLAPSE_LP = -0.001
SCHEMA_RELPATH = Path("ml") / "train_m2" / "contract" / "harvest_line.schema.json"
DEFAULT_ROOT = Path("ml") / "train_m2" / "harvest_out"
DEFAULT_MANIFESTS = Path("ml") / "train_m2" / "harvest_manifests"
DEFAULT_RUNS = Path("ml") / "train_m1" / "eval" / "runs"
DEFAULT_OUT = Path("ml") / "train_m2" / "out" / "reports" / "harvest_validation"


@dataclass
class Check:
    name: str
    status: str
    message: str
    examples: list[str] = field(default_factory=list)


@dataclass
class FolderReport:
    generator: str
    profile: str
    n_files: int
    n_lines: int
    stats: dict[str, Any]
    checks: list[Check]

    @property
    def failed(self) -> list[Check]:
        return [c for c in self.checks if c.status == FAIL]


# ----------------------------------------------------------------------------------------- helpers
def expected_params(profile: str, sample_idx: int) -> tuple[float, tuple[float | None, ...], int]:
    """(temperature, allowed top_p values, seed) the contract requires for a sample of a profile."""
    if sample_idx == 0:
        return 0.0, ((None, 0.95) if profile == "B" else (None,)), 0
    if profile == "A":
        return 0.7, (None,), sample_idx
    return 1.0, (0.95,), 1000 + sample_idx


def _close(a: float | None, b: float | None) -> bool:
    if a is None or b is None:
        return a is None and b is None
    return abs(a - b) < 1e-9


def discover(root: Path) -> tuple[list[tuple[str, str, list[Path]]], list[str]]:
    """Find (generator, profile, part files) folders under root, plus complaints about odd folders."""
    if not root.is_dir():
        return [], [f"root folder not found: {root}"]
    found: list[tuple[str, str, list[Path]]] = []
    odd: list[str] = []
    for gdir in sorted(p for p in root.iterdir() if p.is_dir()):
        if gdir.name not in GENERATORS:
            odd.append(f"unknown generator folder {gdir.name!r} (allowed: {', '.join(GENERATORS)})")
            continue
        for pdir in sorted(p for p in gdir.iterdir() if p.is_dir()):
            if pdir.name not in PROFILES:
                odd.append(f"unknown profile folder {gdir.name}/{pdir.name!r} (allowed: A, B)")
                continue
            found.append((gdir.name, pdir.name, sorted(pdir.glob("part-*.jsonl"))))
    return found, odd


def read_lines(paths: Sequence[Path]) -> Iterator[tuple[str, int, Any, str | None]]:
    """Yield (file name, line number, parsed object or None, json error or None) for every non-blank line."""
    for path in paths:
        with open(path, "r", encoding="utf-8", errors="replace") as handle:
            for lineno, raw in enumerate(handle, start=1):
                if not raw.strip():
                    continue
                try:
                    yield path.name, lineno, json.loads(raw), None
                except json.JSONDecodeError as exc:
                    yield path.name, lineno, None, f"invalid JSON ({exc.msg})"


def count_nonblank_lines(path: Path) -> int:
    with open(path, "r", encoding="utf-8", errors="replace") as handle:
        return sum(1 for line in handle if line.strip())


def load_phase5_contents(runs_dir: Path | None) -> dict[str, dict[str, list[str]]]:
    """generator -> input_key -> the 8 raw texts from the Phase 5 candidate logs (first occurrence wins)."""
    out: dict[str, dict[str, list[str]]] = {}
    if runs_dir is None or not runs_dir.is_dir():
        return out
    for generator in ("zeroshot", "sft", "rft"):
        table: dict[str, list[str]] = {}
        for path in sorted((runs_dir / generator).glob("*.candidates.jsonl")):
            with open(path, "r", encoding="utf-8") as handle:
                for line in handle:
                    if not line.strip():
                        continue
                    row = json.loads(line)
                    table.setdefault(row["input_key"], list(row.get("contents", [])))
        if table:
            out[generator] = table
    return out


class _Examples:
    """Counts occurrences and keeps the first few examples."""

    def __init__(self, limit: int) -> None:
        self.limit, self.count, self.items = limit, 0, []

    def add(self, text: str) -> None:
        self.count += 1
        if len(self.items) < self.limit:
            self.items.append(text)


def _manifest_parts(manifest: Mapping[str, Any]) -> dict[str, tuple[str | None, int | None]]:
    parts = manifest.get("parts") or manifest.get("files") or []
    if isinstance(parts, Mapping):
        parts = [{"file": k, **(v if isinstance(v, Mapping) else {"sha256": v})} for k, v in parts.items()]
    out: dict[str, tuple[str | None, int | None]] = {}
    for part in parts:
        if not isinstance(part, Mapping):
            continue
        name = part.get("file") or part.get("name") or part.get("path")
        if not name:
            continue
        lines = part.get("lines", part.get("line_count", part.get("n_lines")))
        out[Path(str(name)).name] = (part.get("sha256") or part.get("sha"), lines)
    return out


def check_manifest(
    generator: str, profile: str, paths: Sequence[Path], manifests_dir: Path | None, versions: set[str],
    digests: set[str], require: bool,
) -> Check:
    path = (manifests_dir / f"{generator}_{profile}.json") if manifests_dir else None
    if path is None or not path.is_file():
        status = FAIL if require else WARN
        return Check("MANIFEST", status, f"no manifest at {path} (required: {require})")
    try:
        manifest = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        return Check("MANIFEST", FAIL, f"manifest unreadable: {exc}")
    parts = _manifest_parts(manifest)
    if not parts:
        return Check("MANIFEST", FAIL if require else WARN, "manifest has no readable list of parts (expected 'parts': [{file, sha256, lines}])")
    problems: list[str] = []
    on_disk = {p.name: p for p in paths}
    for name in sorted(set(parts) - set(on_disk)):
        problems.append(f"{name}: listed in the manifest but not on disk")
    for name in sorted(set(on_disk) - set(parts)):
        problems.append(f"{name}: on disk but not in the manifest")
    for name, (sha, lines) in sorted(parts.items()):
        if name not in on_disk:
            continue
        if sha and sha256_file(on_disk[name]) != sha:
            problems.append(f"{name}: sha256 differs from the manifest")
        if lines is not None and count_nonblank_lines(on_disk[name]) != int(lines):
            problems.append(f"{name}: {count_nonblank_lines(on_disk[name])} lines on disk, manifest says {lines}")
    if problems:
        return Check("MANIFEST", FAIL, f"{len(problems)} manifest problem(s)", problems[:5])
    notes = []
    mver, mdig = manifest.get("ollama_version"), manifest.get("model_digest")
    if mver and versions and versions != {mver}:
        notes.append(f"ollama_version in lines {sorted(versions)} differs from manifest {mver}")
    if mdig and digests and digests != {mdig}:
        notes.append(f"model_digest in lines {sorted(digests)} differs from manifest {mdig}")
    if notes:
        return Check("MANIFEST", WARN, "hashes and line counts match, but versions differ", notes)
    return Check("MANIFEST", PASS, f"{len(parts)} part(s): sha256 and line counts match")


# ----------------------------------------------------------------------------------------- one folder
def validate_folder(
    generator: str, profile: str, paths: Sequence[Path], input_keys: set[str], validator: Draft202012Validator,
    *, allow_partial: bool = False, require_manifests: bool = False, manifests_dir: Path | None = None,
    phase5: Mapping[str, Mapping[str, list[str]]] | None = None, max_examples: int = 5, n_samples: int = N_SAMPLES,
) -> FolderReport:
    schema_bad, folder_bad, dups = _Examples(max_examples), _Examples(max_examples), _Examples(max_examples)
    key_bad, prof_bad = _Examples(max_examples), _Examples(max_examples)
    text_bad, lp_bad = _Examples(max_examples), _Examples(max_examples)
    seen: Counter[tuple[str, int]] = Counter()
    valid_pairs: set[tuple[str, int]] = set()
    versions: set[str] = set()
    digests: set[str] = set()
    models: set[str] = set()
    n_lines = n_err = n_success = n_collapse = n_topk = 0
    repl_match: Counter[int] = Counter()
    repl_total: Counter[int] = Counter()
    ref_table = (phase5 or {}).get(generator) if profile == "A" else None

    for fname, lineno, obj, json_error in read_lines(paths):
        n_lines += 1
        where = f"{fname}:{lineno}"
        if json_error:
            schema_bad.add(f"{where} {json_error}")
            continue
        problem = next(validator.iter_errors(obj), None)
        if problem is not None:
            location = "/".join(str(p) for p in problem.absolute_path) or "<line>"
            schema_bad.add(f"{where} {location}: {problem.message[:110]}")
            continue
        key = (obj["input_key"], obj["sample_idx"])
        seen[key] += 1
        if seen[key] == 2:
            dups.add(f"{where} repeats input_key {obj['input_key'][:50]}... sample {obj['sample_idx']}")
        if obj["generator"] != generator or obj["profile"] != profile:
            folder_bad.add(f"{where} says generator={obj['generator']} profile={obj['profile']}, folder is {generator}/{profile}")
        if obj["input_key"] not in input_keys:
            key_bad.add(f"{where} unknown input_key {obj['input_key'][:60]}...")
        else:
            valid_pairs.add(key)
        versions.add(obj["ollama_version"])
        models.add(obj["model"])
        if obj["model_digest"]:
            digests.add(obj["model_digest"])
        temperature, top_ps, seed = expected_params(profile, obj["sample_idx"])
        if not _close(obj["temperature"], temperature) or not any(_close(obj["top_p"], t) for t in top_ps) or obj["seed"] != seed:
            prof_bad.add(
                f"{where} sample {obj['sample_idx']}: T={obj['temperature']} top_p={obj['top_p']} seed={obj['seed']}; "
                f"contract wants T={temperature} top_p in {list(top_ps)} seed={seed}"
            )
        if obj["error"] is not None:
            n_err += 1
            continue
        n_success += 1
        tokens = obj["tokens"]
        if "".join(t["t"] for t in tokens) != obj["content"]:
            text_bad.add(where)
        mean_lp = sum(t["lp"] for t in tokens) / len(tokens)
        if mean_lp < MEAN_LP_FLOOR:
            lp_bad.add(f"{where} mean logprob {mean_lp:.2f}")
        if mean_lp > COLLAPSE_LP:
            n_collapse += 1
        if all(t["top"] is not None for t in tokens):
            n_topk += 1
        if ref_table is not None:
            ref = ref_table.get(obj["input_key"])
            idx = obj["sample_idx"]
            if ref and idx < len(ref) and ref[idx]:
                repl_total[idx] += 1
                repl_match[idx] += int(ref[idx] == obj["content"])

    expected = len(input_keys) * n_samples
    have = len(valid_pairs)
    checks: list[Check] = []

    def add(name: str, status: str, message: str, examples: list[str] | None = None) -> None:
        checks.append(Check(name, status, message, examples or []))

    add("SCHEMA", FAIL if schema_bad.count else PASS,
        f"{schema_bad.count} of {n_lines} lines invalid" if schema_bad.count else f"all {n_lines} lines valid", schema_bad.items)
    add("FOLDER_FIELDS", FAIL if folder_bad.count else PASS,
        f"{folder_bad.count} lines disagree with their folder" if folder_bad.count else "generator and profile match the folder",
        folder_bad.items)
    add("DUPLICATES", FAIL if dups.count else PASS,
        f"{dups.count} (input_key, sample_idx) pairs appear more than once" if dups.count else "no duplicate (input_key, sample_idx)",
        dups.items)
    add("KEYS", FAIL if key_bad.count else PASS,
        f"{key_bad.count} lines have an input_key that is not in harvest_inputs.jsonl" if key_bad.count else "all input_keys are known",
        key_bad.items)
    coverage = have / expected if expected else 0.0
    if n_lines == 0:
        add("COMPLETENESS", FAIL, "the folder has no lines")
    elif have == expected:
        add("COMPLETENESS", PASS, f"all {expected} (input, sample) pairs present")
    else:
        message = f"{have} of {expected} pairs present ({coverage:.1%}); {expected - have} missing"
        add("COMPLETENESS", WARN if allow_partial else FAIL, message + (" (allowed by --allow-partial)" if allow_partial else ""))
    rate_text = text_bad.count / n_success if n_success else 0.0
    if text_bad.count == 0:
        add("TEXT_EQ_TOKENS", PASS, f"tokens spell the content on all {n_success} successful lines")
    else:
        add("TEXT_EQ_TOKENS", WARN if rate_text <= TEXT_MISMATCH_FAIL else FAIL,
            f"{text_bad.count} of {n_success} lines ({rate_text:.2%}) where the tokens do not spell the content "
            "(byte-level tokenizer pieces can legitimately differ; above 0.5 percent fails)", text_bad.items)
    add("PROFILE", FAIL if prof_bad.count else PASS,
        f"{prof_bad.count} lines break the profile {profile} rules" if prof_bad.count else f"all lines follow profile {profile}",
        prof_bad.items)
    bad_share = lp_bad.count / n_success if n_success else 0.0
    if lp_bad.count == 0:
        add("LOGPROB", PASS, "no line has mean logprob below -5")
    else:
        add("LOGPROB", FAIL if bad_share > MEAN_LP_BAD_SHARE_FAIL else WARN,
            f"{lp_bad.count} lines ({bad_share:.1%}) have mean logprob below -5", lp_bad.items)
    err_rate = n_err / n_lines if n_lines else 0.0
    if n_lines < ERROR_RATE_MIN_LINES:
        add("ERRORS", INFO, f"{n_err} error line(s) of {n_lines}; rate not judged below {ERROR_RATE_MIN_LINES} lines")
    elif err_rate > ERROR_FAIL:
        add("ERRORS", FAIL, f"error-line rate {err_rate:.1%} is above {ERROR_FAIL:.0%}")
    elif err_rate > ERROR_WARN:
        add("ERRORS", WARN, f"error-line rate {err_rate:.1%} is above {ERROR_WARN:.0%}")
    else:
        add("ERRORS", PASS, f"error-line rate {err_rate:.2%}")
    if len(versions) > 1 or len(digests) > 1 or len(models) > 1:
        add("VERSIONS", FAIL, f"mixed values: ollama_version {sorted(versions)}, model_digest {sorted(digests)}, model {sorted(models)}")
    else:
        add("VERSIONS", PASS, f"ollama_version {sorted(versions) or '-'}, model_digest {sorted(digests) or '-'}")
    checks.append(check_manifest(generator, profile, paths, manifests_dir, versions, digests, require_manifests))
    if ref_table is None:
        add("REPLICATION", INFO, "not applicable (only profile A of zeroshot, sft and rft has Phase 5 logs to compare with)")
    else:
        total = sum(repl_total.values())
        if total == 0:
            add("REPLICATION", INFO, "no comparable lines")
        else:
            per_idx = {i: f"{repl_match[i]}/{repl_total[i]}" for i in sorted(repl_total)}
            add("REPLICATION", INFO,
                f"{sum(repl_match.values())}/{total} = {sum(repl_match.values()) / total:.1%} of lines equal the Phase 5 text; "
                f"by sample index: {per_idx} (information only; seeded samples may differ across Ollama versions)")
    stats = {
        "lines": n_lines, "success_lines": n_success, "error_lines": n_err, "expected_pairs": expected,
        "present_pairs": have, "coverage": round(coverage, 4),
        "collapse_share": round(n_collapse / n_success, 4) if n_success else None,
        "topk_share": round(n_topk / n_success, 4) if n_success else None,
        "ollama_versions": sorted(versions), "model_digests": sorted(digests), "models": sorted(models),
    }
    return FolderReport(generator, profile, len(paths), n_lines, stats, checks)


# ----------------------------------------------------------------------------------------- whole delivery
def validate_root(
    root: Path, *, inputs_path: Path | None = None, schema_path: Path | None = None, manifests_dir: Path | None = None,
    phase5_runs: Path | None = None, allow_partial: bool = False, require_manifests: bool = False, max_examples: int = 5,
) -> dict[str, Any]:
    """Validate every (generator, profile) folder under root. Returns a JSON-ready dict with an `accepted` flag."""
    inputs = load_inputs(inputs_path)
    input_keys = {row["input_key"] for row in inputs}
    schema = json.loads((schema_path or (repo_root() / SCHEMA_RELPATH)).read_text(encoding="utf-8"))
    validator = Draft202012Validator(schema)
    phase5 = load_phase5_contents(phase5_runs)
    folders, odd = discover(root)
    global_checks: list[Check] = [Check("LAYOUT", FAIL, message) for message in odd]
    if not folders and not odd:
        global_checks.append(Check("LAYOUT", FAIL, f"no <generator>/<profile> folders found under {root}"))
    reports = [
        validate_folder(g, p, paths, input_keys, validator, allow_partial=allow_partial, require_manifests=require_manifests,
                        manifests_dir=manifests_dir, phase5=phase5, max_examples=max_examples)
        for g, p, paths in folders
    ]
    reasons = [f"{c.name}: {c.message}" for c in global_checks if c.status == FAIL]
    for rep in reports:
        reasons += [f"{rep.generator}/{rep.profile} {c.name}: {c.message}" for c in rep.failed]
    accepted = not reasons
    summary = "ACCEPTED" if accepted else "REJECTED: " + "; ".join(reasons)
    return {
        "accepted": accepted, "summary_line": summary, "allow_partial": allow_partial, "require_manifests": require_manifests,
        "inputs": len(input_keys), "global": [asdict(c) for c in global_checks], "folders": [asdict(r) for r in reports],
    }


def render_markdown(result: Mapping[str, Any]) -> str:
    lines = ["# Harvest validation report", "",
             f"Inputs expected: {result['inputs']}; allow-partial: {result['allow_partial']}; "
             f"require-manifests: {result['require_manifests']}", ""]
    if result["global"]:
        lines += ["## Layout problems", ""] + [f"- **{c['status']}** {c['name']}: {c['message']}" for c in result["global"]] + [""]
    if result["folders"]:
        lines += ["## Summary", "", "| generator | profile | lines | coverage | errors | collapse share | verdict |", "|---|---|---|---|---|---|---|"]
        for f in result["folders"]:
            s = f["stats"]
            verdict = "FAIL" if any(c["status"] == FAIL for c in f["checks"]) else ("WARN" if any(c["status"] == WARN for c in f["checks"]) else "PASS")
            collapse = "-" if s["collapse_share"] is None else f"{s['collapse_share']:.1%}"
            lines.append(f"| {f['generator']} | {f['profile']} | {s['lines']} | {s['coverage']:.1%} | {s['error_lines']} | {collapse} | {verdict} |")
        lines.append("")
    for f in result["folders"]:
        lines += [f"## {f['generator']} / profile {f['profile']}", "", "| check | status | detail |", "|---|---|---|"]
        for c in f["checks"]:
            lines.append(f"| {c['name']} | {c['status']} | {c['message'].replace('|', '/')} |")
        for c in f["checks"]:
            if c["examples"] and c["status"] in (FAIL, WARN):
                lines += ["", f"First examples for {c['name']}:"] + [f"- `{e}`" for e in c["examples"]]
        lines.append("")
    lines += ["## Verdict", "", result["summary_line"], ""]
    return "\n".join(lines)


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    root = repo_root()
    parser.add_argument("--root", type=Path, default=root / DEFAULT_ROOT)
    parser.add_argument("--inputs", type=Path, default=None)
    parser.add_argument("--schema", type=Path, default=None)
    parser.add_argument("--manifests", type=Path, default=root / DEFAULT_MANIFESTS)
    parser.add_argument("--phase5-runs", type=Path, default=root / DEFAULT_RUNS)
    parser.add_argument("--out", type=Path, default=root / DEFAULT_OUT, help="output path without extension")
    parser.add_argument("--allow-partial", action="store_true")
    parser.add_argument("--require-manifests", action="store_true")
    parser.add_argument("--max-examples", type=int, default=5)
    args = parser.parse_args(argv)
    result = validate_root(
        args.root, inputs_path=args.inputs, schema_path=args.schema, manifests_dir=args.manifests,
        phase5_runs=args.phase5_runs, allow_partial=args.allow_partial, require_manifests=args.require_manifests,
        max_examples=args.max_examples,
    )
    args.out.parent.mkdir(parents=True, exist_ok=True)
    md_path, json_path = Path(str(args.out) + ".md"), Path(str(args.out) + ".json")
    md_path.write_text(render_markdown(result), encoding="utf-8", newline="\n")
    json_path.write_text(json.dumps(result, indent=2, sort_keys=True, ensure_ascii=True) + "\n", encoding="utf-8", newline="\n")
    write_provenance(json_path, extra={"tool": "validate_harvest", "accepted": result["accepted"]})
    print(render_markdown(result))
    print(f"report written: {md_path} and {json_path}")
    layout_only = bool(result["global"]) and not result["folders"]
    if layout_only:
        print(result["summary_line"])
        return 2
    print(result["summary_line"])
    return 0 if result["accepted"] else 1


if __name__ == "__main__":
    sys.exit(main())
