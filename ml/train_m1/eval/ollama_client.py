"""Ask a local Ollama model for Patch-IR with schema-constrained decoding. One function: chat_once()."""

import time

import requests

from ml.train_m1.prompt import SYSTEM_PROMPT, load_schema, user_message

HOST = "http://127.0.0.1:11434"


def chat_once(model, record, temperature=0.0, seed=0, host=HOST, num_predict=400, timeout=600, logprobs=False, session=None):
    """Returns {"content": str, "seconds": float, "logprobs": list|None, "error": str|None}."""
    payload = {"model": model, "stream": False, "think": False, "format": load_schema(),
               "messages": [{"role": "system", "content": SYSTEM_PROMPT}, {"role": "user", "content": user_message(record)}],
               "options": {"temperature": temperature, "seed": seed, "num_predict": num_predict}}
    if logprobs:
        payload["logprobs"] = True
    http = session or requests.Session()
    http.trust_env = False
    started = time.time()
    try:
        r = http.post(host.rstrip("/") + "/api/chat", json=payload, timeout=timeout)
        if r.status_code == 400 and "think" in r.text.lower():
            payload.pop("think")
            r = http.post(host.rstrip("/") + "/api/chat", json=payload, timeout=timeout)
        if r.status_code != 200:
            return {"content": "", "seconds": time.time() - started, "logprobs": None, "error": "HTTP {}: {}".format(r.status_code, r.text[:200])}
        body = r.json()
        return {"content": (body.get("message") or {}).get("content", ""), "seconds": time.time() - started,
                "logprobs": body.get("logprobs"), "error": None}
    except requests.exceptions.RequestException as exc:
        return {"content": "", "seconds": time.time() - started, "logprobs": None, "error": type(exc).__name__}
