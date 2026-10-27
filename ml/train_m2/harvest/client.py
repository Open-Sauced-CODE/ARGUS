"""Ollama client for the harvest tool.

Why a new client: the frozen Phase 5 client (ml/train_m1/eval/ollama_client.py) does not record top-k
alternatives, eval counts, the model digest or the token list. This module keeps the same request shape
(system prompt + user message from ml.train_m1.prompt, Patch-IR JSON schema as `format`, stream false,
think false) and adds logprobs.

Public functions
    build_payload(...)        -> dict            the JSON body sent to /api/chat
    chat_once_v2(...)         -> dict            content, seconds, error, eval_count, done_reason, tokens
    ollama_meta(host, model)  -> dict            {"version": str, "model_digest": str | None}

Contract of chat_once_v2: it never raises for network or HTTP problems (they become an `error` string with
empty content and empty tokens). It raises LogprobsUnavailable when logprobs were requested, the reply has
text, and no usable logprobs came back. That is deliberate: a silent None is exactly what hid this problem
before, and a harvest without logprobs is worthless to M2.
"""

from __future__ import annotations

import logging
import math
import threading
import time
from typing import Any, Dict, List, Optional

import requests

logger = logging.getLogger(__name__)

DEFAULT_HOST = "http://127.0.0.1:11434"
DEFAULT_NUM_PREDICT = 1024
DEFAULT_TIMEOUT = 600.0
CONNECT_TIMEOUT = 10.0
LP_FLOOR = -9999.0  # Ollama uses -9999 for "impossible"; JSON cannot hold -inf

_think_lock = threading.Lock()
_hosts_without_think: set = set()


class LogprobsUnavailable(RuntimeError):
    """Logprobs were requested but the server returned none (or malformed ones)."""


def build_payload(
    model: str,
    messages: List[Dict[str, Any]],
    schema: Dict[str, Any],
    temperature: float,
    top_p: Optional[float],
    seed: int,
    num_predict: int,
    top_logprobs: int,
    think: Optional[bool] = False,
) -> Dict[str, Any]:
    """Build the /api/chat body. Same shape as Phase 5 plus logprobs=true (and top_logprobs=K when K > 0)."""
    options: Dict[str, Any] = {"temperature": float(temperature), "seed": int(seed), "num_predict": int(num_predict)}
    if top_p is not None:
        options["top_p"] = float(top_p)
    payload: Dict[str, Any] = {
        "model": model,
        "messages": messages,
        "stream": False,
        "format": schema,
        "logprobs": True,
        "options": options,
    }
    if think is not None:
        payload["think"] = bool(think)
    if top_logprobs and top_logprobs > 0:
        payload["top_logprobs"] = int(top_logprobs)
    return payload


def extract_logprobs(data: Dict[str, Any]) -> Optional[List[Dict[str, Any]]]:
    """Find the per-token logprob list in a reply (top level, or inside message). None if absent or empty."""
    found = data.get("logprobs")
    if found is None:
        message = data.get("message")
        if isinstance(message, dict):
            found = message.get("logprobs")
    if isinstance(found, list) and found:
        return found
    return None


def _clean_lp(value: Any) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise LogprobsUnavailable("a logprob entry has a non-numeric logprob: %r" % (value,))
    lp = float(value)
    if math.isnan(lp):
        raise LogprobsUnavailable("a logprob entry is NaN")
    if lp == float("-inf") or lp < LP_FLOOR:
        return LP_FLOOR
    if lp > 0.0:
        if lp <= 1e-6:
            return 0.0  # rounding noise; the schema allows up to 1e-6 anyway
        raise LogprobsUnavailable("a logprob entry is positive (%r): not a log-probability" % (value,))
    return lp


def tokens_from_entries(entries: List[Dict[str, Any]], top_logprobs: int) -> List[Dict[str, Any]]:
    """Convert Ollama logprob entries to the contract shape [{t, lp, top}].

    top is [[token, logprob], ...] when top_logprobs > 0 and the server sent alternatives, else None.
    """
    tokens: List[Dict[str, Any]] = []
    for entry in entries:
        if not isinstance(entry, dict) or not isinstance(entry.get("token"), str):
            raise LogprobsUnavailable("a logprob entry has no token text: %r" % (entry,))
        top: Optional[List[List[Any]]] = None
        alts = entry.get("top_logprobs")
        if top_logprobs and top_logprobs > 0 and isinstance(alts, list) and alts:
            top = []
            for alt in alts:
                if isinstance(alt, dict) and isinstance(alt.get("token"), str):
                    top.append([alt["token"], _clean_lp(alt.get("logprob"))])
            if not top:
                top = None
        tokens.append({"t": entry["token"], "lp": _clean_lp(entry.get("logprob")), "top": top})
    return tokens


def _short(text: str, limit: int = 200) -> str:
    return " ".join(str(text).split())[:limit]


def _error_result(error: str, seconds: float) -> Dict[str, Any]:
    return {"content": "", "seconds": seconds, "error": error, "eval_count": 0, "done_reason": None, "tokens": []}


def chat_once_v2(
    model: str,
    record: Dict[str, Any],
    temperature: float = 0.0,
    top_p: Optional[float] = None,
    seed: int = 0,
    host: str = DEFAULT_HOST,
    num_predict: int = DEFAULT_NUM_PREDICT,
    top_logprobs: int = 0,
    timeout: float = DEFAULT_TIMEOUT,
    *,
    messages: Optional[List[Dict[str, Any]]] = None,
    schema: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """One generation. Returns dict(content, seconds, error, eval_count, done_reason, tokens).

    messages / schema default to ml.train_m1.prompt.chat_messages(record) / load_schema(). The harvest runner
    passes them in so the schema file is read once, not once per call.
    """
    if messages is None or schema is None:
        from ml.train_m1.prompt import chat_messages, load_schema  # frozen Phase 5 module

        if messages is None:
            messages = chat_messages(record)
        if schema is None:
            schema = load_schema()

    url = host.rstrip("/") + "/api/chat"
    with _think_lock:
        skip_think = host in _hosts_without_think
    payload = build_payload(model, messages, schema, temperature, top_p, seed, num_predict, top_logprobs,
                            think=None if skip_think else False)

    start = time.monotonic()
    try:
        response = requests.post(url, json=payload, timeout=(CONNECT_TIMEOUT, timeout))
        if response.status_code == 400 and "think" in payload and "think" in response.text.lower():
            # Older Ollama versions reject the `think` field. Remember that and retry once without it.
            with _think_lock:
                _hosts_without_think.add(host)
            payload.pop("think", None)
            response = requests.post(url, json=payload, timeout=(CONNECT_TIMEOUT, timeout))
    except requests.exceptions.Timeout:
        return _error_result("timeout", time.monotonic() - start)
    except requests.exceptions.RequestException as exc:
        return _error_result("connection_error: %s %s" % (type(exc).__name__, _short(exc, 120)), time.monotonic() - start)
    seconds = time.monotonic() - start

    if response.status_code != 200:
        return _error_result("http_%d: %s" % (response.status_code, _short(response.text)), seconds)
    try:
        data = response.json()
    except ValueError:
        return _error_result("bad_json: %s" % _short(response.text, 100), seconds)
    if not isinstance(data, dict):
        return _error_result("bad_json: reply is not an object", seconds)
    if data.get("error"):
        return _error_result("server_error: %s" % _short(data["error"]), seconds)

    message = data.get("message")
    content = message.get("content") if isinstance(message, dict) else None
    content = content if isinstance(content, str) else ""
    if not content:
        return _error_result("empty_response", seconds)

    entries = extract_logprobs(data)
    if not entries:
        meta = ollama_meta(host)
        raise LogprobsUnavailable(
            "Ollama %s at %s returned text but no logprobs for model %r (requested logprobs=true). "
            "Update Ollama (logprobs need a recent version) and re-run the machine check."
            % (meta["version"], host, model)
        )
    tokens = tokens_from_entries(entries, top_logprobs)

    eval_count = data.get("eval_count")
    eval_count = int(eval_count) if isinstance(eval_count, (int, float)) and not isinstance(eval_count, bool) else len(tokens)
    done_reason = data.get("done_reason")
    return {
        "content": content,
        "seconds": seconds,
        "error": None,
        "eval_count": max(0, eval_count),
        "done_reason": done_reason if isinstance(done_reason, str) else None,
        "tokens": tokens,
    }


def _digest_from_tags(host: str, model: str, timeout: float) -> Optional[str]:
    names = {model}
    if ":" not in model:
        names.add(model + ":latest")
    response = requests.get(host.rstrip("/") + "/api/tags", timeout=timeout)
    for item in response.json().get("models", []):
        if item.get("name") in names or item.get("model") in names:
            digest = item.get("digest")
            if isinstance(digest, str) and digest:
                return digest if digest.startswith("sha256:") else "sha256:" + digest
    return None


def ollama_meta(host: str = DEFAULT_HOST, model: Optional[str] = None, timeout: float = 10.0) -> Dict[str, Any]:
    """Return {"version": str, "model_digest": str | None}. Tolerates every failure (version "unknown")."""
    out: Dict[str, Any] = {"version": "unknown", "model_digest": None}
    try:
        version = requests.get(host.rstrip("/") + "/api/version", timeout=timeout).json().get("version")
        if isinstance(version, str) and version:
            out["version"] = version
    except Exception as exc:  # noqa: BLE001 - metadata is best effort by contract
        logger.warning("could not read the Ollama version: %s", exc)
    if model:
        try:
            out["model_digest"] = _digest_from_tags(host, model, timeout)
        except Exception as exc:  # noqa: BLE001
            logger.warning("could not read the model digest from /api/tags: %s", exc)
        if out["model_digest"] is None:
            try:
                shown = requests.post(host.rstrip("/") + "/api/show", json={"model": model}, timeout=timeout).json()
                digest = shown.get("digest") if isinstance(shown, dict) else None
                if isinstance(digest, str) and digest:
                    out["model_digest"] = digest if digest.startswith("sha256:") else "sha256:" + digest
            except Exception as exc:  # noqa: BLE001
                logger.warning("could not read the model digest from /api/show: %s", exc)
    return out
