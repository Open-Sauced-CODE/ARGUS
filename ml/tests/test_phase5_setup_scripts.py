"""
Tests for the two Phase 5 Step 3 scripts. They need no Ollama, no GPU and no internet:
the Ollama check is tested against a tiny fake server running on this machine.

Run from the repo root (PowerShell):
    python -m pytest ml/tests/test_phase5_setup_scripts.py -v
"""

import json
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import pytest

from ml.real_data import hcl_smoke_test as hcl
from ml.real_data import ollama_structured_check as oc

hcl2 = pytest.importorskip("hcl2", reason="python-hcl2 is not installed (pip install -r requirements-phase5.txt)")

# ---------------------------------------------------------------------------------------------
# HCL smoke test
# ---------------------------------------------------------------------------------------------

SAMPLE_TF = '''
variable "env" {
  default = "prod"
}

resource "aws_s3_bucket" "data" {
  bucket = "literal-bucket-name"
  tags = {
    owner = "team-a"
  }
}

resource "aws_s3_bucket_versioning" "data" {
  bucket = aws_s3_bucket.data.id
  count  = 1

  versioning_configuration {
    status = "Enabled"
  }
}

resource "aws_security_group" "app" {
  name = "app-${var.env}"

  dynamic "ingress" {
    for_each = var.ports
    content {
      from_port = ingress.value
    }
  }
}
'''


@pytest.fixture
def sample_file(tmp_path):
    path = tmp_path / "sample.tf"
    path.write_text(SAMPLE_TF, encoding="utf-8")
    return path


def test_parse_file_strips_quotes_and_keeps_references(sample_file):
    parsed = hcl.parse_file(sample_file)
    resources = {(t, n): b for t, n, b in hcl.iter_resources(parsed)}
    assert set(resources) == {
        ("aws_s3_bucket", "data"),
        ("aws_s3_bucket_versioning", "data"),
        ("aws_security_group", "app"),
    }
    assert resources[("aws_s3_bucket", "data")]["bucket"] == "literal-bucket-name"
    assert resources[("aws_s3_bucket_versioning", "data")]["bucket"] == "${aws_s3_bucket.data.id}"
    assert not hcl.is_unresolved("aws:kms")
    assert not hcl.is_unresolved(True)
    assert not hcl.is_unresolved(443)
    assert hcl.is_unresolved("${var.env}")


def test_analyse_file_counts(sample_file):
    report = hcl.analyse_file(sample_file)
    assert report["ok"] is True
    assert report["resources"] == 3
    assert report["resource_types"]["aws_s3_bucket"] == 1
    assert report["values_unresolved"] >= 3  # bucket reference, name template, for_each and friends
    assert report["resources_with"]["count"] == 1
    assert report["resources_with"]["dynamic"] == 1


def test_analyse_file_reports_a_parse_error_instead_of_raising(tmp_path):
    bad = tmp_path / "bad.tf"
    bad.write_text('resource "aws_s3_bucket" "x" {\n  bucket = \n', encoding="utf-8")
    report = hcl.analyse_file(bad)
    assert report["ok"] is False
    assert report["error"]


def test_main_exit_codes(sample_file, tmp_path, capsys):
    assert hcl.main([str(sample_file)]) == 0
    bad = tmp_path / "bad.tf"
    bad.write_text('resource "aws_s3_bucket" "x" {\n  bucket = \n', encoding="utf-8")
    assert hcl.main([str(sample_file), str(bad)]) == 1
    assert hcl.main([str(tmp_path / "missing.tf")]) == 2
    assert "python-hcl2 version" in capsys.readouterr().out


def test_phase1_fixtures_parse_if_present():
    fixtures = sorted(hcl.FIXTURES_DIR.glob("*.tf"))
    if not fixtures:
        pytest.skip("no Phase 1 fixtures found")
    for path in fixtures:
        assert hcl.analyse_file(path)["ok"], path.name


# ---------------------------------------------------------------------------------------------
# Ollama structured-output check, against a fake server
# ---------------------------------------------------------------------------------------------

GOOD_PATCH = {
    "finding_id": "F-TOY-1",
    "resource_ref": "BUCKET_1",
    "ops": [{"op": "set_attr", "attr": "versioning_status", "value": "Enabled"}],
    "rationale_ref": "dpdp.rule6_versioning",
}


class FakeOllama(BaseHTTPRequestHandler):
    # Class-level knobs, reset by the fixture below.
    chat_replies = []          # list of (http_status, body_dict) used in order, last one repeats
    reject_think_once = False
    installed = ["qwen2.5:7b"]
    seen_payloads = []

    def log_message(self, *args):  # keep test output quiet
        pass

    def _send(self, status, body):
        raw = json.dumps(body).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(raw)))
        self.end_headers()
        self.wfile.write(raw)

    def do_GET(self):
        if self.path == "/api/version":
            self._send(200, {"version": "0.0.0-test"})
        elif self.path == "/api/tags":
            self._send(200, {"models": [{"name": n} for n in type(self).installed]})
        else:
            self._send(404, {"error": "not found"})

    def do_POST(self):
        length = int(self.headers.get("Content-Length", "0"))
        payload = json.loads(self.rfile.read(length) or b"{}")
        cls = type(self)
        cls.seen_payloads.append(payload)
        if cls.reject_think_once and "think" in payload:
            cls.reject_think_once = False
            self._send(400, {"error": "model does not support think"})
            return
        index = min(len(cls.seen_payloads) - 1, len(cls.chat_replies) - 1)
        status, body = cls.chat_replies[index]
        self._send(status, body)


def _reply(content, done_reason="stop"):
    return 200, {"message": {"role": "assistant", "content": content}, "done_reason": done_reason}


@pytest.fixture
def server():
    FakeOllama.chat_replies = [_reply(json.dumps(GOOD_PATCH))]
    FakeOllama.reject_think_once = False
    FakeOllama.installed = ["qwen2.5:7b"]
    FakeOllama.seen_payloads = []
    httpd = ThreadingHTTPServer(("127.0.0.1", 0), FakeOllama)
    thread = threading.Thread(target=httpd.serve_forever, daemon=True)
    thread.start()
    yield "http://127.0.0.1:{}".format(httpd.server_address[1])
    httpd.shutdown()
    httpd.server_close()


def test_schema_file_is_the_real_patch_ir_schema():
    schema = oc.load_schema()
    assert schema["properties"]["resource_ref"]["pattern"] == "^[A-Z_]+_[0-9]+$"
    assert "pattern" not in json.dumps(oc.load_schema(strip_pattern=True))


def test_payload_carries_schema_in_format_field():
    payload = oc.build_payload("m", "hello", oc.load_schema())
    assert payload["format"]["required"] == ["finding_id", "resource_ref", "ops", "rationale_ref"]
    assert payload["stream"] is False
    assert payload["think"] is False
    assert payload["options"]["temperature"] == 0


def test_classify_statuses():
    schema = oc.load_schema()
    assert oc.classify(json.dumps(GOOD_PATCH), schema)[0] == "VALID"
    bad_ref = dict(GOOD_PATCH, resource_ref="my-real-bucket")
    status, detail = oc.classify(json.dumps(bad_ref), schema)
    assert status == "SCHEMA_INVALID" and "resource_ref" in detail
    assert oc.classify("{\"finding_id\": \"F", schema)[0] == "NOT_JSON"
    assert oc.classify(json.dumps({"finding_id": "x"}), schema)[0] == "SCHEMA_INVALID"
    unknown_op = dict(GOOD_PATCH, ops=[{"op": "run_command"}])
    assert oc.classify(json.dumps(unknown_op), schema)[0] == "SCHEMA_INVALID"


def test_all_three_prompts_valid(server):
    results = oc.run_checks(server, "qwen2.5:7b")
    assert [r["status"] for r in results] == ["VALID", "VALID", "VALID"]
    assert len(FakeOllama.seen_payloads) == 3


def test_think_field_is_dropped_when_the_server_rejects_it(server):
    FakeOllama.reject_think_once = True
    results = oc.run_checks(server, "qwen2.5:7b")
    assert [r["status"] for r in results] == ["VALID", "VALID", "VALID"]
    assert len(FakeOllama.seen_payloads) == 4  # one rejected attempt, one retry, two more prompts
    assert "think" not in FakeOllama.seen_payloads[1]


def test_invalid_and_truncated_replies_are_reported(server):
    FakeOllama.chat_replies = [
        _reply(json.dumps(dict(GOOD_PATCH, resource_ref="my-real-bucket"))),
        _reply("{\"finding_id\": \"F-TOY-1\", \"reason\": \"aaaa", done_reason="length"),
        (500, {"error": "grammar error"}),
    ]
    results = oc.run_checks(server, "qwen2.5:7b")
    assert [r["status"] for r in results] == ["SCHEMA_INVALID", "NOT_JSON", "HTTP_ERROR"]
    assert "token limit" in results[1]["detail"]
    assert "grammar error" in results[2]["detail"]


def test_main_exit_codes(server, capsys):
    assert oc.main(["--host", server]) == 0
    assert "RESULT: 3/3" in capsys.readouterr().out

    FakeOllama.seen_payloads = []
    FakeOllama.chat_replies = [_reply("not json at all")]
    assert oc.main(["--host", server]) == 1

    FakeOllama.installed = ["some-other-model:latest"]
    assert oc.main(["--host", server]) == 2
    assert "ollama pull qwen2.5:7b" in capsys.readouterr().out


def test_main_reports_unreachable_server(capsys):
    assert oc.main(["--host", "http://127.0.0.1:9"]) == 2
    assert "Could not reach Ollama" in capsys.readouterr().out
