"""A tiny fake Ollama server for the harvest tests (nothing leaves this machine)."""

from __future__ import annotations

import json
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any, Dict, List, Optional


class Behavior:
    """Knobs the tests flip. `mode` is one of: ok, no_logprobs, http500, slow, empty, think_reject, bad_json."""

    def __init__(self) -> None:
        self.mode = "ok"
        self.delay = 0.0
        self.calls: List[Dict[str, Any]] = []
        self.lock = threading.Lock()
        self.think_rejections = 0
        self.fail_every: Optional[int] = None  # every n-th chat call returns HTTP 500
        self.models = [{"name": "argus-m1-sft:latest", "digest": "abc123"}, {"name": "qwen3.5:4b", "digest": "def456"}]
        self.in_flight = 0
        self.max_in_flight = 0


def canned_content(payload: Dict[str, Any]) -> str:
    """Deterministic reply that depends on the seed, so tests can tell samples apart."""
    seed = payload.get("options", {}).get("seed", 0)
    return json.dumps({"finding_id": "F-0", "resource_ref": "RESOURCE_1",
                       "ops": [{"op": "set_attr", "attr": "a", "value": seed}], "rationale_ref": "r.x"},
                      separators=(",", ":"))


def make_entries(content: str, top_k: int) -> List[Dict[str, Any]]:
    entries = []
    for i in range(0, len(content), 3):
        token = content[i:i + 3]
        entry: Dict[str, Any] = {"token": token, "logprob": -0.01 * (i // 3 + 1), "bytes": list(token.encode())}
        if top_k:
            entry["top_logprobs"] = [{"token": token, "logprob": entry["logprob"], "bytes": []}] + [
                {"token": "x%d" % j, "logprob": entry["logprob"] - 1.0 - j, "bytes": []} for j in range(top_k - 1)]
        entries.append(entry)
    return entries


def make_handler(behavior: Behavior):
    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *args: Any) -> None:
            pass

        def _send(self, status: int, body: Any, raw: Optional[bytes] = None) -> None:
            data = raw if raw is not None else json.dumps(body).encode("utf-8")
            self.send_response(status)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(data)))
            self.end_headers()
            try:
                self.wfile.write(data)
            except OSError:
                pass

        def do_GET(self) -> None:
            if self.path == "/api/version":
                self._send(200, {"version": "0.0.0-test"})
            elif self.path == "/api/tags":
                self._send(200, {"models": behavior.models})
            else:
                self._send(404, {"error": "not found"})

        def do_POST(self) -> None:
            length = int(self.headers.get("Content-Length", "0"))
            payload = json.loads(self.rfile.read(length) or b"{}")
            if self.path == "/api/show":
                self._send(200, {"details": {}})
                return
            with behavior.lock:
                behavior.calls.append(payload)
                n = len(behavior.calls)
                behavior.in_flight += 1
                behavior.max_in_flight = max(behavior.max_in_flight, behavior.in_flight)
            try:
                if behavior.delay:
                    time.sleep(behavior.delay)
                mode = behavior.mode
                if mode == "think_reject" and "think" in payload:
                    behavior.think_rejections += 1
                    self._send(400, {"error": "\"qwen\" does not support think"})
                    return
                if mode == "http500" or (behavior.fail_every and n % behavior.fail_every == 0):
                    self._send(500, {"error": "boom"})
                    return
                if mode == "bad_json":
                    self._send(200, None, raw=b"<html>not json</html>")
                    return
                if mode == "empty":
                    self._send(200, {"message": {"role": "assistant", "content": ""}, "done": True, "done_reason": "stop", "eval_count": 0})
                    return
                content = canned_content(payload)
                body: Dict[str, Any] = {"model": payload.get("model"), "message": {"role": "assistant", "content": content},
                                        "done": True, "done_reason": "stop", "eval_count": len(content) // 3 + 1}
                if mode != "no_logprobs" and payload.get("logprobs"):
                    body["logprobs"] = make_entries(content, int(payload.get("top_logprobs", 0) or 0))
                self._send(200, body)
            finally:
                with behavior.lock:
                    behavior.in_flight -= 1

    return Handler


class FakeOllama:
    """Context manager: `with FakeOllama() as fake:` then use fake.host and fake.behavior."""

    def __init__(self) -> None:
        self.behavior = Behavior()
        self._httpd = ThreadingHTTPServer(("127.0.0.1", 0), make_handler(self.behavior))
        self._httpd.daemon_threads = True
        self.host = "http://127.0.0.1:%d" % self._httpd.server_address[1]
        self._thread = threading.Thread(target=self._httpd.serve_forever, daemon=True)

    def __enter__(self) -> "FakeOllama":
        self._thread.start()
        return self

    def __exit__(self, *exc: Any) -> None:
        self._httpd.shutdown()
        self._httpd.server_close()
