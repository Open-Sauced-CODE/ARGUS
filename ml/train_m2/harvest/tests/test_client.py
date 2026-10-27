"""Tests for the Ollama client against a fake server."""

import pytest

from ml.train_m2.harvest import client
from ml.train_m2.harvest.client import LogprobsUnavailable, build_payload, chat_once_v2, ollama_meta
from ml.train_m2.harvest.tests.fake_ollama import FakeOllama

MESSAGES = [{"role": "system", "content": "s"}, {"role": "user", "content": "u"}]
SCHEMA = {"type": "object"}
RECORD = {"finding_id": "F-0"}


def call(fake, **kw):
    args = dict(temperature=0.7, top_p=None, seed=3, host=fake.host, num_predict=64, top_logprobs=0, timeout=5.0,
                messages=MESSAGES, schema=SCHEMA)
    args.update(kw)
    return chat_once_v2("argus-m1-sft", RECORD, **args)


@pytest.fixture(autouse=True)
def reset_think_memory():
    client._hosts_without_think.clear()
    yield
    client._hosts_without_think.clear()


def test_payload_shape():
    p = build_payload("m", MESSAGES, SCHEMA, 0.7, 0.95, 5, 100, 5)
    assert p["stream"] is False and p["think"] is False and p["logprobs"] is True and p["top_logprobs"] == 5
    assert p["format"] == SCHEMA and p["messages"] == MESSAGES
    assert p["options"] == {"temperature": 0.7, "seed": 5, "num_predict": 100, "top_p": 0.95}
    q = build_payload("m", MESSAGES, SCHEMA, 0.0, None, 0, 100, 0)
    assert "top_logprobs" not in q and "top_p" not in q["options"]


def test_success_captures_tokens_and_top_alternatives():
    with FakeOllama() as fake:
        r = call(fake, top_logprobs=5)
    assert r["error"] is None and r["content"] and r["eval_count"] > 0 and r["done_reason"] == "stop"
    assert "".join(t["t"] for t in r["tokens"]) == r["content"]
    assert all(t["lp"] <= 0 for t in r["tokens"])
    assert all(len(t["top"]) == 5 and t["top"][0][0] == t["t"] for t in r["tokens"])
    sent = fake.behavior.calls[0]
    assert sent["options"]["seed"] == 3 and sent["top_logprobs"] == 5 and sent["format"] == SCHEMA


def test_top_is_null_when_not_requested():
    with FakeOllama() as fake:
        r = call(fake, top_logprobs=0)
    assert r["tokens"] and all(t["top"] is None for t in r["tokens"])


def test_missing_logprobs_raise_with_the_ollama_version():
    with FakeOllama() as fake:
        fake.behavior.mode = "no_logprobs"
        with pytest.raises(LogprobsUnavailable) as info:
            call(fake)
    assert "0.0.0-test" in str(info.value)


def test_http_error_becomes_an_error_result():
    with FakeOllama() as fake:
        fake.behavior.mode = "http500"
        r = call(fake)
    assert r["error"].startswith("http_500") and r["content"] == "" and r["tokens"] == []


def test_bad_json_and_empty_reply_become_error_results():
    with FakeOllama() as fake:
        fake.behavior.mode = "bad_json"
        assert call(fake)["error"].startswith("bad_json")
        fake.behavior.mode = "empty"
        assert call(fake)["error"] == "empty_response"


def test_timeout_becomes_a_timeout_error():
    with FakeOllama() as fake:
        fake.behavior.mode = "slow"
        fake.behavior.delay = 1.5
        r = call(fake, timeout=0.3)
    assert r["error"] == "timeout" and r["tokens"] == []


def test_connection_refused_becomes_an_error_result():
    r = chat_once_v2("m", RECORD, host="http://127.0.0.1:9", timeout=2.0, messages=MESSAGES, schema=SCHEMA)
    assert r["error"].startswith("connection_error") and r["tokens"] == []


def test_think_field_is_dropped_once_when_the_server_rejects_it():
    with FakeOllama() as fake:
        fake.behavior.mode = "think_reject"
        first = call(fake)
        second = call(fake)
    assert first["error"] is None and second["error"] is None
    assert fake.behavior.think_rejections == 1  # remembered: the second call never sent `think`
    assert "think" not in fake.behavior.calls[-1]


def test_logprobs_inside_message_are_found():
    data = {"message": {"content": "x", "logprobs": [{"token": "x", "logprob": -0.5}]}}
    assert client.extract_logprobs(data) == [{"token": "x", "logprob": -0.5}]
    assert client.extract_logprobs({"message": {"content": "x"}}) is None


def test_logprob_cleaning():
    assert client._clean_lp(1e-9) == 0.0
    assert client._clean_lp(float("-inf")) == client.LP_FLOOR
    with pytest.raises(LogprobsUnavailable):
        client._clean_lp(0.5)
    with pytest.raises(LogprobsUnavailable):
        client._clean_lp("x")


def test_ollama_meta():
    with FakeOllama() as fake:
        assert ollama_meta(fake.host, "argus-m1-sft") == {"version": "0.0.0-test", "model_digest": "sha256:abc123"}
        assert ollama_meta(fake.host, "qwen3.5:4b")["model_digest"] == "sha256:def456"
        assert ollama_meta(fake.host, "nope")["model_digest"] is None
    dead = ollama_meta("http://127.0.0.1:9", "m", timeout=1.0)
    assert dead == {"version": "unknown", "model_digest": None}
