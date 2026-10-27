"""The machine check against the fake server (and against a dead address)."""

from ml.train_m2.harvest import machine_check
from ml.train_m2.harvest.tests.fake_ollama import FakeOllama


def test_machine_check_passes_on_a_healthy_fake_server(tmp_path):
    with FakeOllama() as fake:
        fake.behavior.models = [{"name": "argus-m1-sft:latest", "digest": "a"}, {"name": "argus-m1-rft:latest", "digest": "b"},
                                {"name": "qwen3.5:4b", "digest": "c"}]
        out = tmp_path / "check.txt"
        code = machine_check.main(["--host", fake.host, "--save", str(out)])
    text = out.read_text()
    assert code == 0 and "OVERALL: PASS" in text and "logprobs found    : True" in text and "top-k alternatives: True" in text
    assert "PARALLEL works" in text or "parallelism" in text


def test_machine_check_reports_missing_models_and_missing_logprobs(tmp_path):
    with FakeOllama() as fake:
        fake.behavior.mode = "no_logprobs"
        out = tmp_path / "check.txt"
        code = machine_check.main(["--host", fake.host, "--save", str(out)])
    text = out.read_text()
    assert code == 1 and "MISSING" in text and "logprobs found    : False" in text


def test_machine_check_reports_a_dead_server(tmp_path):
    out = tmp_path / "check.txt"
    assert machine_check.main(["--host", "http://127.0.0.1:9", "--save", str(out)]) == 1
    assert "cannot reach Ollama" in out.read_text()
