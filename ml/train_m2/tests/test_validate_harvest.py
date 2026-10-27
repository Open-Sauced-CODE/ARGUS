"""Tests for validate_harvest: a valid delivery passes and each defect trips exactly the check it should."""

from __future__ import annotations

import copy
import json
import tempfile
from pathlib import Path

import pytest

from ml.train_m2 import validate_harvest as vh
from ml.train_m2.common import load_inputs, repo_root, sha256_file

CONTRACT = repo_root() / "ml" / "train_m2" / "contract"
INPUTS = load_inputs()
SMALL = INPUTS[:40]  # most tests use 40 inputs x 8 samples = 320 lines per folder, so the suite stays fast
OP = [{"op": "set_attr", "attr": "a", "value": True}]
_SMALL_DIR = Path(tempfile.mkdtemp(prefix="small_inputs_"))
SMALL_PATH = _SMALL_DIR / "small_inputs.jsonl"
SMALL_PATH.write_text("".join(json.dumps(x, sort_keys=True) + "\n" for x in SMALL), encoding="utf-8", newline="\n")


def _tokens(text: str, lp: float = -0.01) -> list[dict]:
    return [{"t": text[i:i + 4], "lp": lp, "top": None} for i in range(0, len(text), 4)]


def make_line(inp: dict, generator: str, profile: str, idx: int, ollama: str = "0.40.10") -> dict:
    rec = inp["record"]
    content = json.dumps(
        {"finding_id": rec["finding_id"], "resource_ref": rec["resource_ref"], "ops": OP, "rationale_ref": rec["rule_id"]},
        separators=(",", ":"),
    )
    temperature, top_ps, seed = vh.expected_params(profile, idx)
    toks = _tokens(content)
    return {
        "schema_version": "m2.harvest.v1", "input_key": inp["input_key"], "generator": generator, "profile": profile,
        "sample_idx": idx, "temperature": temperature, "top_p": top_ps[0], "seed": seed, "model": f"argus-m1-{generator}",
        "model_digest": "sha256:abc", "ollama_version": ollama, "content": content, "error": None,
        "eval_count": len(toks), "seconds": 1.5, "done_reason": "stop", "tokens": toks,
    }


@pytest.fixture(scope="module")
def base_a() -> list[dict]:
    return [make_line(inp, "sft", "A", idx) for inp in SMALL for idx in range(8)]


@pytest.fixture(scope="module")
def base_b() -> list[dict]:
    return [make_line(inp, "sft", "B", idx) for inp in SMALL for idx in range(8)]


def VR(tmp: Path, **kwargs) -> dict:
    """validate_root on tmp/out with the 40-input list unless told otherwise."""
    kwargs.setdefault("manifests_dir", tmp / "man")
    kwargs.setdefault("inputs_path", SMALL_PATH)
    return vh.validate_root(tmp / "out", **kwargs)


def write_folder(root: Path, generator: str, profile: str, lines: list[dict], parts: int = 2) -> list[Path]:
    folder = root / generator / profile
    folder.mkdir(parents=True, exist_ok=True)
    size = max(1, (len(lines) + parts - 1) // parts)
    paths = []
    for i in range(0, len(lines), size):
        path = folder / f"part-{i // size:04d}.jsonl"
        path.write_text("".join(json.dumps(x, sort_keys=True) + "\n" for x in lines[i:i + size]), encoding="utf-8", newline="\n")
        paths.append(path)
    return paths


def write_manifest(mdir: Path, generator: str, profile: str, paths: list[Path], **extra) -> Path:
    mdir.mkdir(parents=True, exist_ok=True)
    parts = [{"file": p.name, "sha256": sha256_file(p), "lines": sum(1 for x in open(p, encoding="utf-8") if x.strip())} for p in paths]
    target = mdir / f"{generator}_{profile}.json"
    target.write_text(json.dumps({"parts": parts, **extra}), encoding="utf-8")
    return target


def run(tmp: Path, lines: list[dict], generator: str = "sft", profile: str = "A", **kwargs) -> dict:
    paths = write_folder(tmp / "out", generator, profile, lines)
    if kwargs.pop("manifest", False):
        write_manifest(tmp / "man", generator, profile, paths)
    return VR(tmp, **kwargs)


def statuses(result: dict, generator: str = "sft", profile: str = "A") -> dict[str, str]:
    for folder in result["folders"]:
        if folder["generator"] == generator and folder["profile"] == profile:
            return {c["name"]: c["status"] for c in folder["checks"]}
    raise AssertionError("folder not in result")


def failed(result: dict, generator: str = "sft", profile: str = "A") -> set[str]:
    return {name for name, status in statuses(result, generator, profile).items() if status == vh.FAIL}


def mutated(lines: list[dict], fn) -> list[dict]:
    lines = copy.deepcopy(lines)
    fn(lines)
    return lines


# --------------------------------------------------------------------------------------------- the good paths
def test_expected_params_follow_the_contract() -> None:
    assert vh.expected_params("A", 0) == (0.0, (None,), 0)
    assert vh.expected_params("A", 3) == (0.7, (None,), 3)
    assert vh.expected_params("B", 0) == (0.0, (None, 0.95), 0)
    assert vh.expected_params("B", 5) == (1.0, (0.95,), 1005)


def test_contract_fixture_lines_all_match_the_schema() -> None:
    from jsonschema import Draft202012Validator

    validator = Draft202012Validator(json.loads((CONTRACT / "harvest_line.schema.json").read_text(encoding="utf-8")))
    lines = [json.loads(x) for x in (CONTRACT / "harvest_fixture.jsonl").read_text(encoding="utf-8").splitlines() if x.strip()]
    assert len(lines) >= 3
    for line in lines:
        assert list(validator.iter_errors(line)) == []


def test_valid_delivery_is_accepted_with_manifest_required(tmp_path: Path, base_a: list[dict]) -> None:
    result = run(tmp_path, base_a, manifest=True, require_manifests=True)
    assert result["accepted"], result["summary_line"]
    assert result["summary_line"] == "ACCEPTED"
    st = statuses(result)
    assert all(v in (vh.PASS, vh.INFO) for v in st.values()), st
    assert st["COMPLETENESS"] == vh.PASS and st["MANIFEST"] == vh.PASS


def test_full_size_delivery_on_the_real_321_inputs(tmp_path: Path) -> None:
    lines = [make_line(inp, "zeroshot", "A", idx) for inp in INPUTS for idx in range(8)]
    paths = write_folder(tmp_path / "out", "zeroshot", "A", lines, parts=3)
    write_manifest(tmp_path / "man", "zeroshot", "A", paths)
    result = vh.validate_root(tmp_path / "out", manifests_dir=tmp_path / "man", require_manifests=True)  # real 321-input list
    assert result["accepted"], result["summary_line"]
    assert result["folders"][0]["stats"]["expected_pairs"] == 321 * 8 == result["folders"][0]["stats"]["present_pairs"]


def test_valid_profile_b_is_accepted(tmp_path: Path, base_b: list[dict]) -> None:
    result = run(tmp_path, base_b, profile="B")
    assert result["accepted"], result["summary_line"]
    assert failed(result, profile="B") == set()


def test_contract_fixture_is_accepted_only_with_allow_partial(tmp_path: Path) -> None:
    lines = [json.loads(x) for x in (CONTRACT / "harvest_fixture.jsonl").read_text(encoding="utf-8").splitlines() if x.strip()]
    for gen, prof in {(x["generator"], x["profile"]) for x in lines}:
        write_folder(tmp_path / "out", gen, prof, [x for x in lines if (x["generator"], x["profile"]) == (gen, prof)], parts=1)
    strict = VR(tmp_path)
    assert not strict["accepted"] and "COMPLETENESS" in strict["summary_line"]
    partial = vh.validate_root(tmp_path / "out", manifests_dir=tmp_path / "man", allow_partial=True)
    assert partial["accepted"], partial["summary_line"]


# --------------------------------------------------------------------------------------------- one defect, one failing check
def test_schema_failure(tmp_path: Path, base_a: list[dict]) -> None:
    result = run(tmp_path, mutated(base_a, lambda L: L[5].pop("model")), allow_partial=True)
    assert failed(result) == {"SCHEMA"}
    assert not result["accepted"]


def test_invalid_json_line_is_a_schema_failure(tmp_path: Path, base_a: list[dict]) -> None:
    paths = write_folder(tmp_path / "out", "sft", "A", base_a)
    with open(paths[0], "a", encoding="utf-8") as handle:
        handle.write("{not json\n")
    result = VR(tmp_path)
    assert "SCHEMA" in failed(result)
    folder = result["folders"][0]
    assert any("invalid JSON" in e for c in folder["checks"] if c["name"] == "SCHEMA" for e in c["examples"])


def test_duplicate_failure(tmp_path: Path, base_a: list[dict]) -> None:
    result = run(tmp_path, mutated(base_a, lambda L: L.append(copy.deepcopy(L[7]))))
    assert failed(result) == {"DUPLICATES"}


def test_unknown_input_key_failure(tmp_path: Path, base_a: list[dict]) -> None:
    result = run(tmp_path, mutated(base_a, lambda L: L[9].__setitem__("input_key", '{"unknown":1}')), allow_partial=True)
    assert failed(result) == {"KEYS"}


def test_completeness_failure_and_allow_partial(tmp_path: Path, base_a: list[dict]) -> None:
    lines = mutated(base_a, lambda L: L.pop(100))
    strict = run(tmp_path / "s", lines)
    assert failed(strict) == {"COMPLETENESS"}
    partial = run(tmp_path / "p", lines, allow_partial=True)
    assert partial["accepted"] and statuses(partial)["COMPLETENESS"] == vh.WARN
    folder = partial["folders"][0]
    assert folder["stats"]["present_pairs"] == folder["stats"]["expected_pairs"] - 1


def test_empty_folder_fails_completeness(tmp_path: Path) -> None:
    (tmp_path / "out" / "sft" / "A").mkdir(parents=True)
    result = VR(tmp_path)
    assert not result["accepted"] and failed(result) == {"COMPLETENESS"}


def test_folder_fields_failure(tmp_path: Path, base_a: list[dict]) -> None:
    def fn(L):
        for x in L[:3]:
            x["generator"] = "rft"

    assert failed(run(tmp_path, mutated(base_a, fn))) == {"FOLDER_FIELDS"}


def test_text_tokens_mismatch_above_threshold_fails(tmp_path: Path, base_a: list[dict]) -> None:
    def fn(L):
        for x in L[:5]:  # 5 of 320 lines = 1.6 percent
            x["content"] = x["content"] + " "

    assert failed(run(tmp_path, mutated(base_a, fn))) == {"TEXT_EQ_TOKENS"}


def test_text_tokens_mismatch_below_threshold_warns(tmp_path: Path, base_a: list[dict]) -> None:
    def fn(L):
        for x in L[:1]:  # 1 of 320 lines = 0.31 percent
            x["content"] = x["content"] + " "

    result = run(tmp_path, mutated(base_a, fn))
    assert result["accepted"] and statuses(result)["TEXT_EQ_TOKENS"] == vh.WARN


def test_profile_a_wrong_temperature_fails(tmp_path: Path, base_a: list[dict]) -> None:
    result = run(tmp_path, mutated(base_a, lambda L: L[3].__setitem__("temperature", 1.0)))
    assert failed(result) == {"PROFILE"}


def test_profile_b_missing_top_p_fails(tmp_path: Path, base_b: list[dict]) -> None:
    result = run(tmp_path, mutated(base_b, lambda L: L[2].__setitem__("top_p", None)), profile="B")
    assert failed(result, profile="B") == {"PROFILE"}


def test_profile_wrong_seed_fails(tmp_path: Path, base_a: list[dict]) -> None:
    result = run(tmp_path, mutated(base_a, lambda L: L[4].__setitem__("seed", 99)))
    assert failed(result) == {"PROFILE"}


def test_logprob_failure_and_warning(tmp_path: Path, base_a: list[dict]) -> None:
    def bad(n):
        def fn(L):
            for x in L[:n]:
                for t in x["tokens"]:
                    t["lp"] = -9.0
        return fn

    assert failed(run(tmp_path / "f", mutated(base_a, bad(10)))) == {"LOGPROB"}  # 3.1 percent
    warn = run(tmp_path / "w", mutated(base_a, bad(2)))                           # 0.6 percent
    assert warn["accepted"] and statuses(warn)["LOGPROB"] == vh.WARN


def test_collapse_share_is_reported(tmp_path: Path, base_a: list[dict]) -> None:
    result = run(tmp_path, mutated(base_a, lambda L: [t.__setitem__("lp", -0.0001) for x in L[:32] for t in x["tokens"]]))
    stats = result["folders"][0]["stats"]
    assert stats["collapse_share"] == pytest.approx(32 / 320, abs=1e-3)


def _make_errors(n: int):
    def fn(L):
        for x in L[:n]:
            x.update({"content": "", "tokens": [], "error": "timeout", "eval_count": 0, "done_reason": None})
    return fn


def test_error_rate_fail_and_warn(tmp_path: Path, base_a: list[dict]) -> None:
    assert failed(run(tmp_path / "f", mutated(base_a, _make_errors(39)))) == {"ERRORS"}   # 12 percent
    warn = run(tmp_path / "w", mutated(base_a, _make_errors(16)))                          # 5 percent
    assert warn["accepted"] and statuses(warn)["ERRORS"] == vh.WARN


def test_error_rate_is_not_judged_for_tiny_folders(tmp_path: Path, base_a: list[dict]) -> None:
    lines = mutated(base_a[:10], _make_errors(10))
    result = run(tmp_path, lines, allow_partial=True)
    assert statuses(result)["ERRORS"] == vh.INFO and result["accepted"]


def test_mixed_versions_fail(tmp_path: Path, base_a: list[dict]) -> None:
    def fn(L):
        for x in L[:5]:
            x["ollama_version"] = "0.1.0"

    assert failed(run(tmp_path, mutated(base_a, fn))) == {"VERSIONS"}


# --------------------------------------------------------------------------------------------- manifests
def test_manifest_wrong_sha_fails(tmp_path: Path, base_a: list[dict]) -> None:
    paths = write_folder(tmp_path / "out", "sft", "A", base_a)
    target = write_manifest(tmp_path / "man", "sft", "A", paths)
    data = json.loads(target.read_text(encoding="utf-8"))
    data["parts"][0]["sha256"] = "0" * 64
    target.write_text(json.dumps(data), encoding="utf-8")
    result = VR(tmp_path)
    assert failed(result) == {"MANIFEST"}


def test_manifest_wrong_line_count_fails(tmp_path: Path, base_a: list[dict]) -> None:
    paths = write_folder(tmp_path / "out", "sft", "A", base_a)
    target = write_manifest(tmp_path / "man", "sft", "A", paths)
    data = json.loads(target.read_text(encoding="utf-8"))
    data["parts"][1]["lines"] += 1
    target.write_text(json.dumps(data), encoding="utf-8")
    assert failed(VR(tmp_path)) == {"MANIFEST"}


def test_manifest_missing_is_a_warning_unless_required(tmp_path: Path, base_a: list[dict]) -> None:
    write_folder(tmp_path / "out", "sft", "A", base_a)
    soft = VR(tmp_path)
    assert soft["accepted"] and statuses(soft)["MANIFEST"] == vh.WARN
    hard = VR(tmp_path, require_manifests=True)
    assert failed(hard) == {"MANIFEST"} and not hard["accepted"]


def test_manifest_file_not_listed_or_missing_on_disk_fails(tmp_path: Path, base_a: list[dict]) -> None:
    paths = write_folder(tmp_path / "out", "sft", "A", base_a, parts=3)
    target = write_manifest(tmp_path / "man", "sft", "A", paths[:2])
    assert failed(VR(tmp_path)) == {"MANIFEST"}
    data = json.loads(target.read_text(encoding="utf-8"))
    data["parts"] = [{"file": p.name, "sha256": sha256_file(p), "lines": 1} for p in paths[:1]]
    data["parts"].append({"file": "part-0099.jsonl", "sha256": "0" * 64, "lines": 1})
    target.write_text(json.dumps(data), encoding="utf-8")
    assert "MANIFEST" in failed(VR(tmp_path))


def test_manifest_alternative_formats_are_understood(tmp_path: Path, base_a: list[dict]) -> None:
    paths = write_folder(tmp_path / "out", "sft", "A", base_a)
    target = tmp_path / "man" / "sft_A.json"
    target.parent.mkdir(parents=True)
    as_dict = {"files": {p.name: {"sha256": sha256_file(p), "line_count": sum(1 for x in open(p, encoding="utf-8") if x.strip())} for p in paths}}
    target.write_text(json.dumps(as_dict), encoding="utf-8")
    assert statuses(VR(tmp_path))["MANIFEST"] == vh.PASS
    as_list = {"parts": [{"name": p.name, "sha256": sha256_file(p), "n_lines": sum(1 for x in open(p, encoding="utf-8") if x.strip())} for p in paths]}
    target.write_text(json.dumps(as_list), encoding="utf-8")
    assert statuses(VR(tmp_path))["MANIFEST"] == vh.PASS


def test_manifest_version_mismatch_is_only_a_warning(tmp_path: Path, base_a: list[dict]) -> None:
    paths = write_folder(tmp_path / "out", "sft", "A", base_a)
    write_manifest(tmp_path / "man", "sft", "A", paths, ollama_version="9.9.9")
    result = VR(tmp_path)
    assert result["accepted"] and statuses(result)["MANIFEST"] == vh.WARN


# --------------------------------------------------------------------------------------------- layout, replication, CLI
def test_unknown_folders_and_missing_root_are_layout_failures(tmp_path: Path, base_a: list[dict]) -> None:
    write_folder(tmp_path / "out", "sft", "A", base_a)
    (tmp_path / "out" / "foo" / "A").mkdir(parents=True)
    (tmp_path / "out" / "sft" / "C").mkdir(parents=True)
    result = VR(tmp_path)
    assert not result["accepted"]
    layout = [c["message"] for c in result["global"]]
    assert any("foo" in m for m in layout) and any("sft/'C'" in m for m in layout)
    missing = vh.validate_root(tmp_path / "nothing", manifests_dir=tmp_path / "man")
    assert not missing["accepted"] and missing["folders"] == []


def test_replication_is_reported_but_never_fails(tmp_path: Path, base_a: list[dict]) -> None:
    runs = tmp_path / "runs" / "sft"
    runs.mkdir(parents=True)
    rows = []
    for inp in INPUTS[:5]:
        contents = [x["content"] for x in base_a if x["input_key"] == inp["input_key"]]
        rows.append({"input_key": inp["input_key"], "contents": contents, "example_ids": ["e"], "scored": {"candidates": [], "pass_at": {}}})
    rows[0]["contents"][3] = "different"
    rows[1]["contents"][0] = "different"
    (runs / "A_val.candidates.jsonl").write_text("".join(json.dumps(r) + "\n" for r in rows), encoding="utf-8")
    result = run(tmp_path, base_a, phase5_runs=tmp_path / "runs")
    assert result["accepted"]
    repl = next(c for c in result["folders"][0]["checks"] if c["name"] == "REPLICATION")
    assert repl["status"] == vh.INFO and "38/40" in repl["message"]


def test_replication_not_applicable_for_profile_b(tmp_path: Path, base_b: list[dict]) -> None:
    result = run(tmp_path, base_b, profile="B", phase5_runs=tmp_path / "runs")
    assert statuses(result, profile="B")["REPLICATION"] == vh.INFO


def test_cli_exit_codes_reports_and_last_line(tmp_path: Path, base_a: list[dict], capsys: pytest.CaptureFixture[str]) -> None:
    write_folder(tmp_path / "good", "sft", "A", base_a)
    out = tmp_path / "rep" / "validation"
    code = vh.main(["--root", str(tmp_path / "good"), "--inputs", str(SMALL_PATH), "--manifests", str(tmp_path / "man"), "--phase5-runs", str(tmp_path / "none"), "--out", str(out)])
    printed = capsys.readouterr().out.strip().splitlines()
    assert code == 0 and printed[-1] == "ACCEPTED"
    assert Path(str(out) + ".md").is_file() and Path(str(out) + ".json").is_file()
    assert Path(str(out) + ".json.provenance.json").is_file()
    assert json.loads(Path(str(out) + ".json").read_text(encoding="utf-8"))["accepted"] is True
    write_folder(tmp_path / "bad", "sft", "A", mutated(base_a, lambda L: L.pop(0)))
    code = vh.main(["--root", str(tmp_path / "bad"), "--inputs", str(SMALL_PATH), "--manifests", str(tmp_path / "man"), "--phase5-runs", str(tmp_path / "none"), "--out", str(out)])
    last = capsys.readouterr().out.strip().splitlines()[-1]
    assert code == 1 and last.startswith("REJECTED:") and "COMPLETENESS" in last
    code = vh.main(["--root", str(tmp_path / "empty"), "--inputs", str(SMALL_PATH), "--manifests", str(tmp_path / "man"), "--phase5-runs", str(tmp_path / "none"), "--out", str(out)])
    assert code == 2


def test_report_files_are_ascii(tmp_path: Path, base_a: list[dict]) -> None:
    write_folder(tmp_path / "out", "sft", "A", mutated(base_a, lambda L: L.pop(0)))
    out = tmp_path / "r"
    vh.main(["--root", str(tmp_path / "out"), "--inputs", str(SMALL_PATH), "--manifests", str(tmp_path / "m"), "--phase5-runs", str(tmp_path / "n"), "--out", str(out)])
    for ext in (".md", ".json"):
        Path(str(out) + ext).read_bytes().decode("ascii")
