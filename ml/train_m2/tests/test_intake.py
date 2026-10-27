"""Tests for the Phase 6 intake report: a synthetic mini repository with known answers, plus a real-data check."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pytest

from ml.train_m2 import intake
from ml.train_m2.common import cluster_key, repo_root
from ml.train_m2.labels.canon import canonical_answer, distinct_answers, is_escalate_only

ESC_OPS = [{"op": "escalate", "reason": "needs a human"}]
FIX_OPS = [{"op": "set_attr", "attr": "a", "value": True}]
RULE = "dpdp.rule6a_rds"


def make_row(i: int, x: int, route: str = "fix") -> dict:
    ops = ESC_OPS if route == "escalate" else FIX_OPS
    return {
        "id": f"ex-{i:03d}",
        "input": {"fields": {"x": x}, "finding_id": f"F-{i}", "resource_id": "R", "resource_ref": "RESOURCE_1", "rule_id": RULE},
        "meta": {"route": route}, "rule_id": RULE,
        "target": {"finding_id": f"F-{i}", "ops": ops, "rationale_ref": RULE, "resource_ref": "RESOURCE_1"},
    }


# input x -> a..f
SETS = {
    "train": [(1, "fix")] * 4 + [(2, "fix")] * 2 + [(3, "escalate")],      # a x4, b x2, c x1 (escalate)
    "val": [(1, "fix"), (4, "fix"), (4, "fix")],                           # a, d x2
    "tierB1": [(1, "fix"), (2, "fix")],                                    # a, b
    "tierB2": [(5, "fix")] * 3,                                            # e x3
    "tierC_verifier": [(4, "fix"), (4, "fix"), (6, "escalate")],           # d x2, f
    "gold": [(6, "escalate")],                                             # f
}
FILES = {
    "train": "dataset/train.jsonl", "val": "dataset/val.jsonl", "tierB1": "held_out/tierB1.jsonl", "tierB2": "held_out/tierB2.jsonl",
    "tierC_verifier": "held_out/tierC_verifier.jsonl", "gold": "held_out/gold.jsonl",
}
CAND_INPUTS = {"A_val": [1, 4], "train300": [1, 2], "B1": [1, 2], "B2": [5], "C_verifier": [4, 6], "gold": [6]}


def key_of(x: int) -> str:
    return cluster_key(make_row(0, x))


def answer(i: int, extra: str = "") -> str:
    return json.dumps({"finding_id": "F-0", "ops": [{"op": "set_attr", "attr": "a", "value": i}], "rationale_ref": RULE + extra})


def candidate_row(generator: str, set_name: str, x: int) -> dict:
    n_ids = 2 if (set_name == "B1" and x == 1) else 1
    if generator == "zeroshot":
        contents = [answer(i) for i in range(8)]
    elif generator == "sft":
        contents = [answer(i % 2) for i in range(8)]
    else:
        contents = [answer(0)] * 8
    if generator == "rft" and set_name == "gold":
        contents[7] = ""
    cands = [{"correct": True, "escalated": False, "gate_passed": True, "hidden": {}, "hidden_ok": True, "outcome": "fixed",
              "reasons": [], "status": "ok", "unsafe": False} for _ in range(8)]
    pass_at = {str(k): True for k in range(1, 9)}
    if generator == "zeroshot":                      # first two candidates fail the gate
        for c in cands[:2]:
            c.update(gate_passed=False, correct=False, hidden_ok=None)
        pass_at["1"] = False
    if (generator, set_name, x) == ("zeroshot", "A_val", 4):
        cands[3].update(hidden_ok=False)             # gate-passing but wrong -> natural negative
    if (generator, set_name, x) == ("zeroshot", "B1", 2):
        cands[5].update(hidden_ok=False)
    if (generator, set_name, x) == ("sft", "B1", 1):
        cands[0].update(hidden_ok=False, correct=False)
        pass_at["1"] = False
    return {"input_key": key_of(x), "example_ids": [f"e{j}" for j in range(n_ids)], "contents": contents,
            "scored": {"candidates": cands, "pass_at": pass_at}}


def build_root(tmp: Path, *, alter_summary: tuple[str, str] | None = None, logprobs: bool = False) -> Path:
    me = tmp / "ml" / "mutation_engine"
    (me / "dataset").mkdir(parents=True)
    (me / "held_out").mkdir(parents=True)
    (me / "bases").mkdir(parents=True)
    manifest_lines = []
    for name, rel in FILES.items():
        text = "".join(json.dumps(make_row(i, x, route), sort_keys=True) + "\n" for i, (x, route) in enumerate(SETS[name]))
        (me / rel).write_text(text, encoding="utf-8", newline="\n")
        manifest_lines.append(f"{hashlib.sha256(text.encode()).hexdigest()}  {rel}")
    (me / "held_out" / "tierC_mined.jsonl").write_text("", encoding="utf-8")
    (me / "MANIFEST.sha256").write_text("\n".join(manifest_lines) + "\n", encoding="utf-8")
    (me / "bases" / "manifest.csv").write_text(
        "base_id,license\n1,MIT\n2,MIT\n3,Apache-2.0\n4,GPL-3.0\n5,MPL-2.0\n6,AGPL-3.0\n", encoding="utf-8")
    runs = tmp / "ml" / "train_m1" / "eval" / "runs"
    for generator in intake.GENERATORS:
        (runs / generator).mkdir(parents=True)
        for set_name, xs in CAND_INPUTS.items():
            rows = [candidate_row(generator, set_name, x) for x in xs]
            if logprobs and generator == "sft" and set_name == "gold":
                rows[0]["tokens"] = []
            (runs / generator / f"{set_name}.candidates.jsonl").write_text(
                "".join(json.dumps(r) + "\n" for r in rows), encoding="utf-8", newline="\n")
            p1 = sum(len(r["example_ids"]) for r in rows if r["scored"]["pass_at"]["1"])
            p8 = sum(len(r["example_ids"]) for r in rows if r["scored"]["pass_at"]["8"])
            if alter_summary == (generator, set_name):
                p1 += 1
            summary = {"examples": sum(len(r["example_ids"]) for r in rows), "pass_at": {"1": p1, "8": p8}}
            (runs / generator / f"{set_name}.summary.json").write_text(json.dumps(summary), encoding="utf-8")
    contract = tmp / "ml" / "train_m2" / "contract"
    contract.mkdir(parents=True)
    keys = sorted({key_of(x) for xs in ([x for x, _ in v] for v in SETS.values()) for x in xs})
    (contract / "harvest_inputs.jsonl").write_text(
        "".join(json.dumps({"input_key": k, "record": json.loads(k), "sets": {}}) + "\n" for k in keys), encoding="utf-8")
    return tmp


# ------------------------------------------------------------------------------------------------ canon helpers
def test_canonical_answer_ignores_finding_id_and_resource_ref() -> None:
    a = json.dumps({"finding_id": "F-1", "resource_ref": "R1", "ops": FIX_OPS, "rationale_ref": "r"})
    b = json.dumps({"finding_id": "F-9", "resource_ref": "R9", "ops": FIX_OPS, "rationale_ref": "r"})
    c = json.dumps({"finding_id": "F-1", "resource_ref": "R1", "ops": ESC_OPS, "rationale_ref": "r"})
    assert canonical_answer(a) == canonical_answer(b) != canonical_answer(c)
    assert canonical_answer("") == "EMPTY" and canonical_answer(None) == "EMPTY"
    assert canonical_answer("not json") == "INVALID" and canonical_answer("[1]") == "INVALID"
    assert distinct_answers([a, b, c, "", None]) == 2


def test_is_escalate_only() -> None:
    assert is_escalate_only(ESC_OPS) and is_escalate_only(ESC_OPS * 2)
    assert not is_escalate_only(FIX_OPS) and not is_escalate_only(FIX_OPS + ESC_OPS)
    assert not is_escalate_only([]) and not is_escalate_only(None)


# ------------------------------------------------------------------------------------------------ manifest and sets
def test_verify_manifest_ok_mismatch_and_missing(tmp_path: Path) -> None:
    root = build_root(tmp_path)
    me = root / "ml" / "mutation_engine"
    assert intake.verify_manifest(me) == {"present": True, "results": intake.verify_manifest(me)["results"], "ok": 6, "problems": 0}
    (me / "dataset" / "val.jsonl").write_text("changed\n", encoding="utf-8")
    (me / "held_out" / "gold.jsonl").unlink()
    result = intake.verify_manifest(me)
    status = {r["file"]: r["status"] for r in result["results"]}
    assert status["dataset/val.jsonl"] == "mismatch" and status["held_out/gold.jsonl"] == "missing"
    assert result["ok"] == 4 and result["problems"] == 2
    assert intake.verify_manifest(tmp_path / "nowhere")["present"] is False


def test_dataset_sets_distinct_inputs_routes_and_escalate_rows(tmp_path: Path) -> None:
    root = build_root(tmp_path)
    sets, missing = intake.load_dataset_sets(root / "ml" / "mutation_engine")
    assert missing == []
    assert (sets["train"]["rows"], len(sets["train"]["keys"]), sets["train"]["escalate_rows"]) == (7, 3, 1)
    assert max(sets["train"]["keys"].values()) == 4
    assert sets["C_verifier"]["routes"] == {"fix": 2, "escalate": 1} and sets["C_verifier"]["escalate_rows"] == 1
    assert sets["C_mined"]["rows"] == 0
    assert {n: len(s["keys"]) for n, s in sets.items()} == {"train": 3, "A_val": 2, "B1": 2, "B2": 1, "C_verifier": 2, "gold": 1, "C_mined": 0}
    assert sets["train"]["rules"][RULE] == set(sets["train"]["keys"])


def test_missing_dataset_files_are_listed(tmp_path: Path) -> None:
    root = build_root(tmp_path)
    (root / "ml" / "mutation_engine" / "held_out" / "tierB2.jsonl").unlink()
    sets, missing = intake.load_dataset_sets(root / "ml" / "mutation_engine")
    assert "held_out/tierB2.jsonl" in missing and "B2" not in sets


def test_overlap_and_share_in_train(tmp_path: Path) -> None:
    sets, _ = intake.load_dataset_sets(build_root(tmp_path) / "ml" / "mutation_engine")
    report = intake.overlap_report(sets)
    assert report["pairs"]["train&A_val"] == 1 and report["pairs"]["A_val&C_verifier"] == 1 and report["pairs"]["C_verifier&gold"] == 1
    share = report["share_in_train"]
    assert share["B1"] == {"distinct": 2, "also_in_train": 2, "share": 1.0}
    assert share["A_val"]["share"] == 0.5 and share["B2"]["also_in_train"] == 0 and "C_mined" not in share


# ------------------------------------------------------------------------------------------------ candidates
def cell(stats: dict, generator: str, set_name: str) -> dict:
    return next(c for c in stats["cells"] if c["generator"] == generator and c["set"] == set_name)


def test_candidate_cells_and_natural_negatives(tmp_path: Path) -> None:
    stats, missing = intake.candidate_stats(build_root(tmp_path) / "ml" / "train_m1" / "eval" / "runs")
    assert missing == [] and len(stats["cells"]) == 18
    c = cell(stats, "sft", "B1")
    assert (c["inputs"], c["examples"], c["candidates"], c["gate_passing"], c["gate_passing_hidden_fail"]) == (2, 3, 16, 16, 1)
    assert c["mean_distinct_answers"] == 2.0
    z = cell(stats, "zeroshot", "A_val")
    assert z["gate_passing"] == 12 and z["gate_passing_hidden_fail"] == 1 and z["mean_distinct_answers"] == 8.0
    r = cell(stats, "rft", "gold")
    assert r["empty_replies"] == 1 and r["mean_distinct_answers"] == 1.0
    assert stats["natural_negative_clusters"] == {"zeroshot": 2, "sft": 1, "rft": 0, "union": 3}
    assert stats["logprobs_present"] is False


def test_pass_at_recomputed_with_example_weights_and_only_altered_summary_is_flagged(tmp_path: Path) -> None:
    stats, _ = intake.candidate_stats(build_root(tmp_path, alter_summary=("rft", "B2")) / "ml" / "train_m1" / "eval" / "runs")
    flagged = [(c["generator"], c["set"], c["k"]) for c in stats["pass_at_checks"] if c["flag"]]
    assert flagged == [("rft", "B2", 1)]
    sft_b1 = next(c for c in stats["pass_at_checks"] if (c["generator"], c["set"], c["k"]) == ("sft", "B1", 1))
    assert sft_b1["recomputed"] == 1 and sft_b1["summary"] == 1 and sft_b1["examples"] == 3   # weight 2 input failed, weight 1 passed
    assert len(stats["pass_at_checks"]) == 36
    clean, _ = intake.candidate_stats(build_root(tmp_path / "clean") / "ml" / "train_m1" / "eval" / "runs")
    assert not any(c["flag"] for c in clean["pass_at_checks"])


def test_logprobs_flag_turns_on_when_a_row_carries_tokens(tmp_path: Path) -> None:
    stats, _ = intake.candidate_stats(build_root(tmp_path, logprobs=True) / "ml" / "train_m1" / "eval" / "runs")
    assert stats["logprobs_present"] is True


def test_missing_candidate_files_are_listed(tmp_path: Path) -> None:
    root = build_root(tmp_path)
    (root / "ml" / "train_m1" / "eval" / "runs" / "rft" / "gold.candidates.jsonl").unlink()
    stats, missing = intake.candidate_stats(root / "ml" / "train_m1" / "eval" / "runs")
    assert missing == ["rft/gold.candidates.jsonl"] and len(stats["cells"]) == 17


# ------------------------------------------------------------------------------------------------ inputs, licences, CLI
def test_harvest_inputs_check_equal_and_unequal(tmp_path: Path) -> None:
    root = build_root(tmp_path)
    sets, _ = intake.load_dataset_sets(root / "ml" / "mutation_engine")
    path = root / "ml" / "train_m2" / "contract" / "harvest_inputs.jsonl"
    ok = intake.harvest_inputs_check(path, sets)
    assert ok["equal"] and ok["harvest_inputs"] == 6 == ok["distinct_inputs_all_sets"]
    lines = path.read_text(encoding="utf-8").splitlines()
    path.write_text("\n".join(lines[:-1]) + "\n", encoding="utf-8")
    bad = intake.harvest_inputs_check(path, sets)
    assert not bad["equal"] and bad["missing_from_list"] == 1 and bad["extra_in_list"] == 0
    assert intake.harvest_inputs_check(tmp_path / "none.jsonl", sets) == {"present": False}


def test_licence_summary_counts_copyleft_including_weak(tmp_path: Path) -> None:
    lic = intake.licence_summary(build_root(tmp_path) / "ml" / "mutation_engine")
    assert lic["bases"] == 6 and lic["copyleft_bases"] == 3
    assert set(lic["copyleft_by_licence"]) == {"GPL-3.0", "MPL-2.0", "AGPL-3.0"} and lic["copyleft_share"] == 0.5
    assert intake.licence_summary(tmp_path / "nowhere") == {"present": False}


def test_main_writes_reports_and_exit_codes(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    root = build_root(tmp_path)
    out = tmp_path / "rep" / "intake"
    assert intake.main(["--root", str(root), "--out", str(out)]) == 0
    text = Path(str(out) + ".md").read_text(encoding="utf-8")
    assert "# Phase 6 intake report" in text and "union 3" in text and "identical sets: **True**" in text
    data = json.loads(Path(str(out) + ".json").read_text(encoding="utf-8"))
    assert data["missing"] == [] and data["report"]["sets"]["train"]["distinct_inputs"] == 3
    assert Path(str(out) + ".json.provenance.json").is_file()
    Path(str(out) + ".md").read_bytes().decode("ascii")
    (root / "ml" / "train_m1" / "eval" / "runs" / "sft" / "B1.candidates.jsonl").unlink()
    assert intake.main(["--root", str(root), "--out", str(out)]) == 3
    assert "MISSING 1 required file" in capsys.readouterr().out
    assert intake.main(["--root", str(root), "--out", str(out), "--allow-missing"]) == 0


# ------------------------------------------------------------------------------------------------ the real files
REAL = repo_root()
HAVE_REAL = (REAL / "ml/mutation_engine/dataset/train.jsonl").is_file() and (REAL / "ml/train_m1/eval/runs/sft/B1.candidates.jsonl").is_file()


@pytest.mark.skipif(not HAVE_REAL, reason="the git-ignored Phase 5 data is not in this checkout (copy it from ml.zip)")
def test_real_phase5_numbers_are_reproduced() -> None:
    report, missing = intake.build_report(REAL)
    assert missing == []
    assert report["manifest"]["ok"] == 10 and report["manifest"]["problems"] == 0
    distinct = {n: s["distinct_inputs"] for n, s in report["sets"].items()}
    assert distinct == {"train": 230, "A_val": 70, "B1": 36, "B2": 10, "C_verifier": 108, "gold": 30, "C_mined": 0}
    assert report["sets"]["train"]["rows"] == 2507 and report["sets"]["train"]["escalate_rows"] == 360
    assert report["sets"]["C_verifier"]["escalate_rows"] == 51 and report["sets"]["gold"]["escalate_rows"] == 9
    share = report["overlap"]["share_in_train"]
    assert (share["B1"]["share"], share["B2"]["share"]) == (1.0, 1.0)
    assert share["C_verifier"]["also_in_train"] == 32 and share["A_val"]["also_in_train"] == 55
    cand = report["candidates"]
    assert cand["natural_negative_clusters"] == {"zeroshot": 21, "sft": 4, "rft": 1, "union": 22}
    assert cand["logprobs_present"] is False and not any(c["flag"] for c in cand["pass_at_checks"])
    assert report["harvest_inputs"]["equal"] and report["harvest_inputs"]["harvest_inputs"] == 321
    rft_gold = next(c for c in cand["cells"] if (c["generator"], c["set"]) == ("rft", "A_val"))
    assert rft_gold["mean_distinct_answers"] == 1.0
