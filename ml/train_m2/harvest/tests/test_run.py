"""End-to-end tests of the harvest runner against a fake Ollama (no real Ollama, no GPU)."""

import json
import threading
from pathlib import Path

import pytest

from ml.train_m2.harvest import run as harvest_run
from ml.train_m2.harvest.client import LogprobsUnavailable, chat_once_v2
from ml.train_m2.harvest.paths import DEFAULT_OUT
from ml.train_m2.harvest.run import HarvestConfig, HarvestError, run_harvest, select_inputs, stratified_pick
from ml.train_m2.harvest.schema import text_equals_tokens, validate_line
from ml.train_m2.harvest.store import iter_lines, part_files, sha256_file
from ml.train_m2.harvest.tests.fake_ollama import FakeOllama

RULES = ["a.rule", "b.rule", "c.rule"]
SCHEMA = {"type": "object"}


def messages_fn(record):
    return [{"role": "user", "content": json.dumps(record, sort_keys=True)}]


def make_inputs(path: Path, per_rule=(3, 2, 1)):
    rows = []
    for rule, n in zip(RULES, per_rule):
        for i in range(n):
            record = {"fields": {"x": i}, "finding_id": "F-0", "resource_id": "R_1", "resource_ref": "R_1", "rule_id": rule}
            key = json.dumps({"fields": {"x": i}, "resource_ref": "R_1", "rule_id": rule}, sort_keys=True, separators=(",", ":"))
            rows.append({"input_key": key, "record": record, "sets": {"train": 1}})
    path.write_text("".join(json.dumps(r) + "\n" for r in rows), encoding="utf-8")
    return rows


@pytest.fixture
def env(tmp_path):
    inputs = tmp_path / "inputs.jsonl"
    rows = make_inputs(inputs)
    from ml.train_m2.harvest.paths import SCHEMA_PATH
    return {"inputs": inputs, "rows": rows, "out": tmp_path / "out", "mf": tmp_path / "manifests", "schema_path": SCHEMA_PATH}


def cfg_for(env, fake, **kw):
    base = dict(generator="sft", model="argus-m1-sft", profile="A", out_root=env["out"], manifest_dir=env["mf"],
                host=fake.host, threads=3, top_logprobs=3, num_predict=64, timeout=5.0)
    base.update(kw)
    return HarvestConfig(**base)


def go(env, fake, **kw):
    chat_fn = kw.pop("chat_fn", chat_once_v2)
    cfg = cfg_for(env, fake, **kw)
    return run_harvest(cfg, inputs_path=env["inputs"], schema_path=env["schema_path"], messages_fn=messages_fn,
                       schema=SCHEMA, chat_fn=chat_fn, command="test")


def all_lines(env):
    return [line for _p, line in iter_lines(env["out"] / "sft" / "A")]


def test_full_run_writes_valid_unique_lines_and_a_true_manifest(env):
    with FakeOllama() as fake:
        summary = go(env, fake)
    lines = all_lines(env)
    assert len(lines) == 6 * 8 == summary.lines_written
    assert len({(l["input_key"], l["sample_idx"]) for l in lines}) == 48
    for l in lines:
        validate_line(l)
        assert text_equals_tokens(l) and l["error"] is None
        assert l["model_digest"] == "sha256:abc123" and l["ollama_version"] == "0.0.0-test"
    # profile A parameters really reached the server
    seeds = sorted({(c["options"]["temperature"], c["options"]["seed"]) for c in fake.behavior.calls})
    assert seeds == [(0.0, 0)] + [(0.7, i) for i in range(1, 8)]
    assert all("top_p" not in c["options"] for c in fake.behavior.calls)
    # manifest
    manifest = json.loads((env["out"] / "sft" / "A" / "MANIFEST.json").read_text())
    assert manifest == json.loads((env["mf"] / "sft_A.json").read_text())
    assert manifest["lines_total"] == 48 and manifest["errors"] == 0 and manifest["complete"] is True
    assert manifest["lines_expected"] == 48 and manifest["model_digest"] == "sha256:abc123"
    for part in manifest["parts"]:
        assert part["sha256"] == sha256_file(env["out"] / "sft" / "A" / part["file"])
        assert part["lines"] == sum(1 for _ in open(env["out"] / "sft" / "A" / part["file"], "rb"))
    assert manifest["runs"][0]["command"] == "test" and manifest["provenance"]["inputs_sha256"]


def test_profile_b_parameters_reach_the_server(env):
    with FakeOllama() as fake:
        go(env, fake, profile="B", limit=1)
    sent = {(c["options"]["temperature"], c["options"].get("top_p"), c["options"]["seed"]) for c in fake.behavior.calls}
    assert sent == {(0.0, None, 0)} | {(1.0, 0.95, 1000 + i) for i in range(1, 8)}


def test_files_use_lf_newlines_and_rotate(env):
    with FakeOllama() as fake:
        go(env, fake, part_size=10)
    names = [p.name for p in part_files(env["out"] / "sft" / "A")]
    assert names == ["part-0000.jsonl", "part-0001.jsonl", "part-0002.jsonl", "part-0003.jsonl", "part-0004.jsonl"]
    raw = (env["out"] / "sft" / "A" / "part-0000.jsonl").read_bytes()
    assert b"\r" not in raw and raw.count(b"\n") == 10


def test_crash_then_restart_skips_finished_work_and_has_no_duplicates(env):
    calls = {"n": 0}
    lock = threading.Lock()

    def crashing(*a, **k):
        with lock:
            calls["n"] += 1
            n = calls["n"]
        if n > 20:
            raise RuntimeError("simulated crash")
        return chat_once_v2(*a, **k)

    with FakeOllama() as fake:
        with pytest.raises(RuntimeError):
            go(env, fake, chat_fn=crashing, threads=2)
        first = len(all_lines(env))
        assert 0 < first < 48
        before = len(fake.behavior.calls)
        go(env, fake, threads=2)
        after = len(fake.behavior.calls)
    lines = all_lines(env)
    assert len(lines) == 48 and len({(l["input_key"], l["sample_idx"]) for l in lines}) == 48
    assert after - before == 48 - first  # only the missing work was generated
    assert json.loads((env["out"] / "sft" / "A" / "MANIFEST.json").read_text())["complete"] is True


def test_unfinished_last_line_is_repaired_on_restart(env):
    with FakeOllama() as fake:
        go(env, fake, limit=1)
        part = env["out"] / "sft" / "A" / "part-0000.jsonl"
        good = part.read_bytes()
        part.write_bytes(good + b'{"input_key": "half writ')
        summary = go(env, fake, limit=1)
    assert summary.repaired_bytes > 0 and summary.jobs_total == 0
    assert part.read_bytes() == good


def test_error_replies_become_valid_error_lines_and_retry_errors_replaces_them(env):
    with FakeOllama() as fake:
        fake.behavior.fail_every = 5
        go(env, fake, limit=2, threads=1, max_consecutive_errors=50)
        lines = all_lines(env)
        errs = [l for l in lines if l["error"]]
        assert len(lines) == 16 and errs
        for l in errs:
            validate_line(l)
            assert l["content"] == "" and l["tokens"] == [] and l["error"].startswith("http_500")
        fake.behavior.fail_every = None
        summary = go(env, fake, limit=2, threads=1, retry_errors=True)
    assert summary.dropped_error_lines == len(errs)
    lines = all_lines(env)
    assert len(lines) == 16 and not [l for l in lines if l["error"]]
    assert len({(l["input_key"], l["sample_idx"]) for l in lines}) == 16


def test_error_lines_without_retry_flag_are_kept(env):
    with FakeOllama() as fake:
        fake.behavior.mode = "http500"
        with pytest.raises(HarvestError):
            go(env, fake, limit=2, threads=1, max_consecutive_errors=5)
        n_err = len(all_lines(env))
        assert n_err >= 5
        fake.behavior.mode = "ok"
        go(env, fake, limit=2, threads=1)  # no --retry-errors: error lines stay, rest is filled in
    lines = all_lines(env)
    assert len(lines) == 16 and sum(1 for l in lines if l["error"]) == n_err


def test_consecutive_error_breaker_stops_the_run_early(env):
    with FakeOllama() as fake:
        fake.behavior.mode = "http500"
        with pytest.raises(HarvestError) as info:
            go(env, fake, threads=1, max_consecutive_errors=4)
    assert "4 errors in a row" in str(info.value)
    assert len(all_lines(env)) < 48
    manifest = json.loads((env["out"] / "sft" / "A" / "MANIFEST.json").read_text())
    assert manifest["runs"][-1]["stopped_early"] is True and manifest["complete"] is False


def test_missing_logprobs_stop_the_run_loudly_and_write_nothing_silently(env):
    with FakeOllama() as fake:
        fake.behavior.mode = "no_logprobs"
        with pytest.raises(LogprobsUnavailable):
            go(env, fake, threads=2)
    assert all_lines(env) == []


def test_two_models_never_share_a_folder(env):
    with FakeOllama() as fake:
        go(env, fake, limit=1)
        with pytest.raises(HarvestError):
            go(env, fake, limit=1, model="another-model")


def test_shards_partition_the_inputs_with_no_overlap_and_no_gap(env):
    rows = env["rows"]
    parts = [select_inputs(rows, None, False, (i, 3)) for i in range(3)]
    keys = [[r["input_key"] for r in p] for p in parts]
    flat = [k for ks in keys for k in ks]
    assert len(flat) == len(set(flat)) == len(rows) and set(flat) == {r["input_key"] for r in rows}
    with pytest.raises(HarvestError):
        select_inputs(rows, None, False, (3, 3))


def test_sharded_runs_write_distinct_part_numbers_and_together_complete(env):
    with FakeOllama() as fake:
        go(env, fake, shard=(0, 2))
        go(env, fake, shard=(1, 2))
    names = [p.name for p in part_files(env["out"] / "sft" / "A")]
    assert names == ["part-0000.jsonl", "part-1000.jsonl"]
    assert json.loads((env["out"] / "sft" / "A" / "MANIFEST.json").read_text())["complete"] is True


def test_stratified_pick_is_round_robin_and_deterministic(env):
    rows = env["rows"]
    picked = stratified_pick(rows, 4)
    assert [r["record"]["rule_id"] for r in picked] == ["a.rule", "b.rule", "c.rule", "a.rule"]
    assert [r["input_key"] for r in stratified_pick(list(reversed(rows)), 4)] == [r["input_key"] for r in picked]
    assert len(stratified_pick(rows, 100)) == len(rows)


def test_limit_without_stratify_takes_the_first_inputs(env):
    assert select_inputs(env["rows"], 2, False, (0, 1)) == sorted(env["rows"][:2], key=lambda r: r["input_key"])


def test_temp_override_is_refused_inside_the_contract_folder(env):
    with FakeOllama() as fake:
        with pytest.raises(HarvestError):
            go(env, fake, out_root=DEFAULT_OUT / "sft_experiment", temperature_override=1.2)
        go(env, fake, limit=1, temperature_override=1.2, profile="B")
    temps = {c["options"]["temperature"] for c in fake.behavior.calls}
    assert temps == {0.0, 1.2}
    assert {l["temperature"] for l in all_lines_b(env)} == {0.0, 1.2}


def all_lines_b(env):
    return [line for _p, line in iter_lines(env["out"] / "sft" / "B")]


def test_cli_main_end_to_end(env, capsys):
    with FakeOllama() as fake:
        code = harvest_run.main(
            ["--generator", "sft", "--model", "argus-m1-sft", "--profile", "A", "--threads", "2", "--top-logprobs", "2",
             "--limit", "2", "--stratify", "--out", str(env["out"]), "--host", fake.host, "--timeout", "5"],
            messages_fn=messages_fn, schema=SCHEMA)
    out = capsys.readouterr().out
    assert code == 0 and "Lines written now: 16" in out
    assert (env["out"] / "manifests" / "sft_A.json").exists()


def test_cli_reports_a_clean_failure(env, capsys):
    with FakeOllama() as fake:
        fake.behavior.mode = "no_logprobs"
        code = harvest_run.main(
            ["--generator", "sft", "--model", "argus-m1-sft", "--profile", "A", "--limit", "1", "--out", str(env["out"]),
             "--host", fake.host], messages_fn=messages_fn, schema=SCHEMA)
    assert code == 2 and "HARVEST STOPPED" in capsys.readouterr().out


def test_strip_pattern_removes_only_pattern_keywords():
    schema = {"properties": {"pattern": {"type": "string"}, "ref": {"type": "string", "pattern": "^x$"}}}
    assert harvest_run.strip_pattern(schema) == {"properties": {"pattern": {"type": "string"}, "ref": {"type": "string"}}}
