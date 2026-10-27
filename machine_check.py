"""Phase 6 machine check (about 15 minutes of reading, 1 minute of running).

Standalone: needs only Python and `requests`. Run it from anywhere:
    python machine_check.py
or, once the harvest package exists:
    python -m ml.train_m2.harvest.machine_check

It records: Ollama version, installed models, whether logprobs and top-k logprobs come back, whether 4
simultaneous requests really run in parallel, and free disk space. The output is also saved to a text file
(UTF-8, ASCII characters only) that you send to Shaurya.
"""

from __future__ import annotations

import argparse
import json
import platform
import shutil
import subprocess
import sys
import threading
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

import requests

REQUIRED_MODELS = ("argus-m1-sft", "argus-m1-rft", "qwen3.5:4b")
PARALLEL_REQUESTS = 4


def chat(host: str, payload: Dict[str, Any], timeout: float = 600.0) -> Dict[str, Any]:
    """POST /api/chat; if this Ollama rejects the `think` field, retry once without it."""
    url = host.rstrip("/") + "/api/chat"
    response = requests.post(url, json=payload, timeout=timeout)
    if response.status_code == 400 and "think" in payload and "think" in response.text.lower():
        payload = {k: v for k, v in payload.items() if k != "think"}
        response = requests.post(url, json=payload, timeout=timeout)
    response.raise_for_status()
    return response.json()


def model_present(installed: List[str], wanted: str) -> bool:
    names = {wanted} | ({wanted + ":latest"} if ":" not in wanted else set())
    return any(n in names for n in installed)


def check_logprobs(host: str, model: str) -> Dict[str, Any]:
    data = chat(host, {"model": model, "stream": False, "think": False, "logprobs": True, "top_logprobs": 5,
                       "messages": [{"role": "user", "content": "Reply with the single word OK."}],
                       "options": {"temperature": 0, "num_predict": 8}})
    entries = data.get("logprobs") or (data.get("message") or {}).get("logprobs")
    first = entries[0] if isinstance(entries, list) and entries else None
    return {
        "done_reason": data.get("done_reason"),
        "top_level_keys": sorted(data.keys()),
        "logprobs_found": bool(first),
        "logprobs_location": "top level" if data.get("logprobs") else ("inside message" if first else "none"),
        "entry_keys": sorted(first.keys()) if isinstance(first, dict) else None,
        "top_logprobs_found": bool(isinstance(first, dict) and first.get("top_logprobs")),
        "n_top": len(first["top_logprobs"]) if isinstance(first, dict) and first.get("top_logprobs") else 0,
        "first_entry": json.dumps(first)[:400] if first else None,
    }


def _slow_request(host: str, model: str) -> float:
    start = time.monotonic()
    chat(host, {"model": model, "stream": False, "think": False,
                "messages": [{"role": "user", "content": "Write the numbers from 1 to 60 separated by commas."}],
                "options": {"temperature": 0, "num_predict": 120, "seed": 0}})
    return time.monotonic() - start


def check_parallel(host: str, model: str, n: int = PARALLEL_REQUESTS) -> Dict[str, Any]:
    _slow_request(host, model)  # warm-up: loads the model
    single = _slow_request(host, model)
    times: List[float] = []
    errors: List[str] = []

    def one() -> None:
        try:
            times.append(_slow_request(host, model))
        except Exception as exc:  # noqa: BLE001
            errors.append("%s: %s" % (type(exc).__name__, exc))

    start = time.monotonic()
    threads = [threading.Thread(target=one) for _ in range(n)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    wall = time.monotonic() - start
    speedup = (n * single / wall) if wall > 0 and not errors else 0.0
    if errors:
        verdict = "FAILED (%s). If VRAM ran out, use OLLAMA_NUM_PARALLEL=2." % errors[0][:100]
    elif speedup >= 2.0:
        verdict = "PARALLEL works (speedup %.1fx for %d requests)." % (speedup, n)
    elif speedup >= 1.4:
        verdict = "PARTIAL parallelism (speedup %.1fx). Use --threads 2 or check OLLAMA_NUM_PARALLEL." % speedup
    else:
        verdict = "NO parallelism: requests queue (speedup %.1fx). Throughput will be about 1/%d of a parallel server." % (speedup, n)
    return {"single_seconds": round(single, 2), "parallel_wall_seconds": round(wall, 2), "n": n,
            "speedup": round(speedup, 2), "verdict": verdict, "errors": errors}


def run(host: str, model: str, out_dir: Path) -> Dict[str, Any]:
    report: Dict[str, Any] = {"when_utc": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
                              "python": platform.python_version(), "platform": platform.platform(), "ok": True}
    exe = shutil.which("ollama")
    if exe:
        try:
            report["ollama_cli_version"] = subprocess.run([exe, "--version"], capture_output=True, text=True, timeout=20).stdout.strip() \
                or subprocess.run([exe, "--version"], capture_output=True, text=True, timeout=20).stderr.strip()
        except (OSError, subprocess.SubprocessError) as exc:
            report["ollama_cli_version"] = "error: %s" % exc
    else:
        report["ollama_cli_version"] = "ollama is not on PATH (fine if the server is running)"
    try:
        report["server_version"] = requests.get(host.rstrip("/") + "/api/version", timeout=10).json().get("version")
        tags = requests.get(host.rstrip("/") + "/api/tags", timeout=10).json().get("models", [])
    except Exception as exc:  # noqa: BLE001
        report["server_version"] = None
        report["fatal"] = "cannot reach Ollama at %s: %s. Start Ollama and run this again." % (host, exc)
        report["ok"] = False
        return report
    installed = [m.get("name", "") for m in tags]
    report["installed_models"] = installed
    report["required_models"] = {m: model_present(installed, m) for m in REQUIRED_MODELS}
    if not all(report["required_models"].values()):
        report["ok"] = False
    try:
        report["logprobs"] = check_logprobs(host, model)
        if not report["logprobs"]["logprobs_found"]:
            report["ok"] = False
    except Exception as exc:  # noqa: BLE001
        report["logprobs"] = {"error": "%s: %s" % (type(exc).__name__, exc)}
        report["ok"] = False
    try:
        report["parallel"] = check_parallel(host, model)
    except Exception as exc:  # noqa: BLE001
        report["parallel"] = {"error": "%s: %s" % (type(exc).__name__, exc)}
        report["ok"] = False
    target = out_dir if out_dir.exists() else Path.cwd()
    usage = shutil.disk_usage(str(target))
    report["disk_free_gb"] = round(usage.free / 1e9, 1)
    report["disk_note"] = "needs about 0.5 GB for the whole harvest with top-5 alternatives"
    return report


def format_report(report: Dict[str, Any]) -> str:
    lines = ["ARGUS Phase 6 machine check", "=" * 27]
    for key in ("when_utc", "python", "platform", "ollama_cli_version", "server_version"):
        lines.append("%-20s: %s" % (key, report.get(key)))
    if report.get("fatal"):
        lines += ["", "FATAL: " + report["fatal"]]
        return "\n".join(lines) + "\n"
    lines.append("installed models    : %s" % ", ".join(report.get("installed_models", [])))
    for model, ok in report.get("required_models", {}).items():
        lines.append("  %-18s: %s" % (model, "present" if ok else "MISSING  (ollama pull %s, or rebuild it from your Modelfile)" % model))
    lp = report.get("logprobs", {})
    lines += ["", "Logprobs test"]
    if "error" in lp:
        lines.append("  ERROR: " + lp["error"])
    else:
        lines += ["  done_reason       : %s" % lp["done_reason"], "  top-level keys    : %s" % lp["top_level_keys"],
                  "  logprobs found    : %s (%s)" % (lp["logprobs_found"], lp["logprobs_location"]),
                  "  entry keys        : %s" % lp["entry_keys"],
                  "  top-k alternatives: %s (%d per token)" % (lp["top_logprobs_found"], lp["n_top"]),
                  "  first entry       : %s" % lp["first_entry"]]
        if not lp["top_logprobs_found"]:
            lines.append("  NOTE: no top-k alternatives. The contract allows top = null; tell Shaurya.")
    par = report.get("parallel", {})
    lines += ["", "Parallel requests test"]
    if "error" in par:
        lines.append("  ERROR: " + par["error"])
    else:
        lines += ["  one request       : %.2f s" % par["single_seconds"],
                  "  %d at once         : %.2f s" % (par["n"], par["parallel_wall_seconds"]), "  verdict           : " + par["verdict"]]
    lines += ["", "Disk free           : %s GB (%s)" % (report.get("disk_free_gb"), report.get("disk_note")),
              "", "OVERALL: " + ("PASS" if report["ok"] else "PROBLEMS FOUND (read the lines above)")]
    return "\n".join(lines) + "\n"


def main(argv: Optional[List[str]] = None) -> int:
    p = argparse.ArgumentParser(description="Phase 6 machine check")
    p.add_argument("--host", default="http://127.0.0.1:11434")
    p.add_argument("--model", default="argus-m1-sft")
    p.add_argument("--save", default=None, help="output file (default docs/phase6_prabhav/machine_check.txt if that folder exists, else machine_check_output.txt)")
    args = p.parse_args(argv)
    docs = Path("docs") / "phase6_prabhav"
    save = Path(args.save) if args.save else (docs / "machine_check.txt" if docs.exists() else Path("machine_check_output.txt"))
    text = format_report(run(args.host, args.model, docs))
    print(text)
    save.write_bytes(text.encode("ascii", "replace"))
    print("Saved to %s" % save.resolve())
    return 0 if "OVERALL: PASS" in text else 1


if __name__ == "__main__":
    sys.exit(main())
