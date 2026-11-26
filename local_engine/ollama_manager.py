"""Local Ollama status checker, Modelfile synthesizer, GGUF discovery, and registry pull helper."""

from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
import sys
import threading
import time
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any, Dict, List, Optional

import requests

from local_engine.paths import get_bundle_root, get_data_dir

DEFAULT_OLLAMA_URL = "http://127.0.0.1:11434"
_MODEL_NAME_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.:/-]{0,200}$")
_ANSI_RE = re.compile(r"\x1b\[[0-9;?]*[A-Za-z]")
_NO_PROXY_OPENER = urllib.request.build_opener(urllib.request.ProxyHandler({}))
_LOCAL_ARGUS_TAGS = {"argus-m1", "argus-m1-sft", "argus-m1-rft", "argus-m1-rft-v2"}

# Verified Qwen3.5 Modelfile template (matches `ollama show qwen3.5:4b --modelfile` / `argus-m1-sft`)
QWEN35_MODELFILE_TEMPLATE = """FROM {gguf_path}
TEMPLATE {{{{ .Prompt }}}}
RENDERER qwen3.5
PARSER qwen3.5
PARAMETER temperature 1
PARAMETER top_k 20
PARAMETER top_p 0.95
PARAMETER presence_penalty 1.5
"""

_PULL_LOCK = threading.Lock()
_PULL_STATE: Dict[str, Any] = {
    "active": False,
    "model": None,
    "status": "idle",
    "completed_bytes": 0,
    "total_bytes": 0,
    "percent": 0.0,
    "success": None,
    "error": None,
    "started_at": None,
    "finished_at": None,
}


def _win_no_window_kwargs() -> Dict[str, Any]:
    if os.name == "nt":
        return {"creationflags": getattr(subprocess, "CREATE_NO_WINDOW", 0x08000000)}
    return {}


def find_ollama_binary() -> Optional[str]:
    """Locate ollama / ollama.exe on PATH or standard Windows install directories."""
    candidates = [
        os.environ.get("OLLAMA_BIN"),
        shutil.which("ollama"),
    ]
    if os.name == "nt":
        local_app = os.environ.get("LOCALAPPDATA")
        prog_files = os.environ.get("ProgramFiles", r"C:\Program Files")
        if local_app:
            candidates.append(str(Path(local_app) / "Programs" / "Ollama" / "ollama.exe"))
        candidates.append(str(Path.home() / "AppData" / "Local" / "Programs" / "Ollama" / "ollama.exe"))
        candidates.append(str(Path(prog_files) / "Ollama" / "ollama.exe"))

    for cand in candidates:
        if not cand:
            continue
        p = Path(cand)
        if p.exists() and p.is_file():
            return str(p)
        resolved = shutil.which(cand)
        if resolved:
            return resolved
    return None


def normalize_model_ref(model_ref: str) -> str:
    """Normalize user-entered Ollama/HF tag (stripping optional `ollama pull/run ` CLI prefix)."""
    raw = (model_ref or "").strip()
    lower = raw.lower()
    for prefix in ("ollama pull ", "ollama run ", "ollama create "):
        if lower.startswith(prefix):
            raw = raw[len(prefix) :].strip()
            break
    if len(raw) >= 2 and ((raw[0] == '"' and raw[-1] == '"') or (raw[0] == "'" and raw[-1] == "'")):
        raw = raw[1:-1].strip()
    return raw


def ensure_ollama_running(endpoint: str = DEFAULT_OLLAMA_URL, start_timeout: float = 8.0) -> Dict[str, Any]:
    """Ensure local Ollama daemon is reachable; start `ollama serve` detached if installed."""
    status = check_ollama_status(endpoint=endpoint, timeout=1.5)
    if status.get("running"):
        return status

    ollama_bin = find_ollama_binary()
    if not ollama_bin:
        return status

    kwargs: Dict[str, Any] = {
        "stdin": subprocess.DEVNULL,
        "stdout": subprocess.DEVNULL,
        "stderr": subprocess.DEVNULL,
    }
    if os.name == "nt":
        detached = getattr(subprocess, "DETACHED_PROCESS", 0x00000008)
        no_win = getattr(subprocess, "CREATE_NO_WINDOW", 0x08000000)
        kwargs["creationflags"] = no_win | detached
    else:
        kwargs["start_new_session"] = True

    try:
        proc = subprocess.Popen([ollama_bin, "serve"], **kwargs)
    except Exception as exc:
        status["error"] = f"Failed to start Ollama service: {exc}"
        return status

    deadline = time.time() + max(1.0, start_timeout)
    while time.time() < deadline:
        time.sleep(0.35)
        status = check_ollama_status(endpoint=endpoint, timeout=1.2)
        if status.get("running"):
            return status
        if proc.poll() is not None:
            break
    return check_ollama_status(endpoint=endpoint, timeout=1.5)


def check_ollama_status(endpoint: str = DEFAULT_OLLAMA_URL, timeout: float = 1.5) -> Dict[str, Any]:
    """Non-blocking health probe against local Ollama daemon (bypasses system HTTP proxy)."""
    base = endpoint.rstrip("/")
    version = None
    models: List[str] = []
    running = False
    error: Optional[str] = None

    try:
        with _NO_PROXY_OPENER.open(f"{base}/api/version", timeout=timeout) as resp:
            data = json.loads(resp.read().decode("utf-8"))
            version = data.get("version")
            running = True
    except Exception as exc:
        error = f"Ollama not reachable at {base}: {type(exc).__name__}"
        return {
            "running": False,
            "endpoint": base,
            "version": None,
            "models": [],
            "argus_sft_ready": False,
            "argus_rft_ready": False,
            "ollama_installed": bool(find_ollama_binary()),
            "error": error,
        }

    try:
        with _NO_PROXY_OPENER.open(f"{base}/api/tags", timeout=timeout) as resp:
            tags = json.loads(resp.read().decode("utf-8"))
            models = [m.get("name", "") for m in tags.get("models", []) if m.get("name")]
    except Exception as exc:
        error = str(exc)

    sft_ready = any(m.startswith("argus-m1-sft") or "argus-m1-sft" in m.lower() for m in models)
    rft_ready = any(m.startswith("argus-m1-rft") or "argus-m1-rft" in m.lower() for m in models)

    return {
        "running": running,
        "endpoint": base,
        "version": version,
        "models": models,
        "argus_sft_ready": sft_ready,
        "argus_rft_ready": rft_ready,
        "ollama_installed": True,
        "error": error,
    }


def _rewrite_modelfile_from(base_text: str, gguf_path: str) -> str:
    out: List[str] = []
    done = False
    for line in base_text.splitlines():
        if line.startswith("FROM "):
            if not done:
                out.append(f"FROM {gguf_path}")
                done = True
            continue
        out.append(line)
    if not done:
        out.insert(0, f"FROM {gguf_path}")
    return "\n".join(out) + "\n"


def build_modelfile_text(
    gguf_path: str | Path,
    *,
    base_model: str = "qwen3.5:4b",
    ollama_bin: Optional[str] = None,
) -> tuple[str, str]:
    """Build Modelfile text directly without requiring `sys.executable -m` or base download."""
    resolved = str(Path(gguf_path).expanduser().resolve())
    bin_path = ollama_bin or find_ollama_binary()
    if bin_path and base_model:
        try:
            shown = subprocess.run(
                [bin_path, "show", base_model, "--modelfile"],
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",
                timeout=10,
                **_win_no_window_kwargs(),
            )
            if shown.returncode == 0 and shown.stdout.strip():
                return _rewrite_modelfile_from(shown.stdout, resolved), f"ollama_show:{base_model}"
        except Exception:
            pass
    return QWEN35_MODELFILE_TEMPLATE.format(gguf_path=resolved), "synthesized_qwen35_template"


def register_local_gguf(
    gguf_path: str | Path,
    *,
    model_name: str = "argus-m1-sft",
    base_model: str = "qwen3.5:4b",
) -> Dict[str, Any]:
    """Register a local Q4_K_M .gguf file directly via `ollama create` (PyInstaller .exe safe)."""
    model_name = normalize_model_ref(model_name)
    if not _MODEL_NAME_RE.fullmatch(model_name):
        raise ValueError(f"Invalid Ollama model name: {model_name!r}")

    p = Path(gguf_path).expanduser().resolve()
    if not p.exists() or not p.is_file():
        raise FileNotFoundError(f"GGUF file not found: {p}")
    if p.suffix.lower() != ".gguf":
        raise ValueError(f"Expected a .gguf file, got: {p.name}")

    ollama_bin = find_ollama_binary()
    if not ollama_bin:
        raise RuntimeError(
            "Ollama CLI not found on PATH or standard install folder. Install Ollama for Windows first."
        )

    # Auto-start local `ollama serve` if a real binary exists and the daemon isn't running yet
    if Path(ollama_bin).exists():
        try:
            ensure_ollama_running(start_timeout=6.0)
        except Exception:
            pass

    modelfile_text, template_source = build_modelfile_text(
        p, base_model=base_model, ollama_bin=ollama_bin
    )
    modelfiles_dir = get_data_dir() / "modelfiles"
    modelfiles_dir.mkdir(parents=True, exist_ok=True)
    safe_tag = re.sub(r"[^A-Za-z0-9._-]", "_", model_name)
    modelfile_path = modelfiles_dir / f"Modelfile.{safe_tag}"
    modelfile_path.write_text(modelfile_text, encoding="utf-8", newline="\n")

    proc = subprocess.run(
        [ollama_bin, "create", model_name, "-f", str(modelfile_path)],
        cwd=str(modelfiles_dir),
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=300,
        **_win_no_window_kwargs(),
    )
    if proc.returncode != 0:
        err_msg = _ANSI_RE.sub("", (proc.stderr or proc.stdout or "")).strip()
        raise RuntimeError(
            f"ollama create failed (exit {proc.returncode}): {err_msg}"
        )
    clean_out = _ANSI_RE.sub("", (proc.stdout or proc.stderr or "")).strip()
    return {
        "success": True,
        "model_name": model_name,
        "gguf_path": str(p),
        "modelfile_path": str(modelfile_path),
        "template_source": template_source,
        "stdout": clean_out,
    }


def discover_local_ggufs(extra_dirs: Optional[List[str | Path]] = None) -> List[Dict[str, Any]]:
    """Scan common local folders (data dir, exe dir, repo root, Downloads, ARGUS workspace) for .gguf files."""
    candidates: List[Path] = []
    if extra_dirs:
        candidates.extend(Path(d).expanduser() for d in extra_dirs)
    env_models = os.environ.get("ARGUS_MODELS_DIR")
    if env_models:
        candidates.append(Path(env_models).expanduser())
    candidates.extend(
        [
            get_data_dir() / "models",
            Path(sys.executable).resolve().parent,
            Path(sys.executable).resolve().parent / "models",
            get_bundle_root(),
            get_bundle_root() / "models",
            Path.cwd(),
            Path.cwd() / "models",
            Path.home() / "Downloads",
            Path.home() / "Downloads" / "ARGUS",
            Path.home() / "Desktop",
            Path.home() / "Documents" / "ARGUS",
            Path.home() / "ARGUS",
            Path.home() / "models",
        ]
    )
    if os.name == "nt":
        candidates.extend([Path(r"D:\ARGUS"), Path(r"C:\ARGUS")])

    seen_paths: set[str] = set()
    found: List[Dict[str, Any]] = []
    for folder in candidates:
        try:
            if not folder.exists() or not folder.is_dir():
                continue
            search_dirs = [folder]
            models_sub = folder / "models"
            if models_sub.exists() and models_sub.is_dir() and models_sub not in candidates:
                search_dirs.append(models_sub)
            for sdir in search_dirs:
                for item in sdir.iterdir():
                    if not item.is_file() or item.suffix.lower() != ".gguf":
                        continue
                    resolved = item.resolve()
                    key = str(resolved).lower() if os.name == "nt" else str(resolved)
                    if key in seen_paths:
                        continue
                    seen_paths.add(key)
                    size_bytes = resolved.stat().st_size
                    if size_bytes <= 0:
                        continue
                    lname = resolved.name.lower()
                    suggested = "argus-m1-rft" if "rft" in lname else "argus-m1-sft"
                    found.append(
                        {
                            "name": resolved.name,
                            "path": str(resolved),
                            "size_bytes": size_bytes,
                            "size_gb": round(size_bytes / (1024**3), 2),
                            "suggested_model_name": suggested,
                            "priority": 0 if ("argus" in lname or "qwen3.5" in lname) else 1,
                        }
                    )
        except OSError:
            continue

    found.sort(key=lambda x: (x["priority"], -x["size_bytes"], x["name"]))
    for entry in found:
        entry.pop("priority", None)
    return found


def get_pull_status() -> Dict[str, Any]:
    with _PULL_LOCK:
        return dict(_PULL_STATE)


def _match_local_gguf_for_tag(base_tag: str) -> Optional[Dict[str, Any]]:
    ggufs = discover_local_ggufs()
    if not ggufs:
        return None
    if base_tag == "argus-m1-rft-v2":
        for g in ggufs:
            if "rft-v2" in g["name"].lower():
                return g
    if base_tag.startswith("argus-m1-rft"):
        for g in ggufs:
            if g.get("suggested_model_name") == "argus-m1-rft":
                return g
    if base_tag == "argus-m1-sft":
        for g in ggufs:
            if g.get("suggested_model_name") == "argus-m1-sft":
                return g
    return None


def _run_pull_worker(model_ref: str, base_url: str) -> None:
    sess = requests.Session()
    sess.trust_env = False
    try:
        # Handle local fine-tuned ARGUS model aliases cleanly without hitting registry.ollama.ai 404
        base_tag = model_ref.lower().split(":")[0]
        if base_tag == "argus-m1":
            base_tag = "argus-m1-sft"
        if "/" not in model_ref and base_tag in _LOCAL_ARGUS_TAGS:
            st = check_ollama_status(endpoint=base_url, timeout=2.0)
            installed = st.get("models") or []
            if any(m.lower() == base_tag or m.lower().startswith(f"{base_tag}:") for m in installed):
                with _PULL_LOCK:
                    _PULL_STATE.update(
                        {
                            "active": False,
                            "status": f"verified {base_tag} ready in local Ollama",
                            "completed_bytes": 1,
                            "total_bytes": 1,
                            "percent": 100.0,
                            "success": True,
                            "error": None,
                            "finished_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
                        }
                    )
                return

            matched_gguf = _match_local_gguf_for_tag(base_tag)
            if matched_gguf:
                with _PULL_LOCK:
                    _PULL_STATE.update(
                        {
                            "status": f"registering local {matched_gguf['name']} as {base_tag}...",
                            "percent": 40.0,
                        }
                    )
                register_local_gguf(matched_gguf["path"], model_name=base_tag)
                with _PULL_LOCK:
                    _PULL_STATE.update(
                        {
                            "active": False,
                            "status": f"registered {matched_gguf['name']} as {base_tag}",
                            "completed_bytes": matched_gguf["size_bytes"],
                            "total_bytes": matched_gguf["size_bytes"],
                            "percent": 100.0,
                            "success": True,
                            "error": None,
                            "finished_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
                        }
                    )
                return

            with _PULL_LOCK:
                _PULL_STATE.update(
                    {
                        "active": False,
                        "status": "error",
                        "success": False,
                        "error": (
                            f"'{model_ref}' is a local fine-tuned model not hosted on registry.ollama.ai. "
                            "Click 'Browse .gguf...' to import your Q4_K_M .gguf weights, or pull 'qwen3.5:4b' / a public 'hf.co/<org>/<repo>:Q4_K_M' tag."
                        ),
                        "finished_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
                    }
                )
            return

        with sess.post(
            f"{base_url}/api/pull",
            json={"model": model_ref, "stream": True},
            stream=True,
            timeout=(5, 1800),
        ) as resp:
            if resp.status_code != 200:
                err_txt = resp.text[:300]
                with _PULL_LOCK:
                    _PULL_STATE.update(
                        {
                            "active": False,
                            "status": "error",
                            "success": False,
                            "error": f"Ollama pull failed (HTTP {resp.status_code}): {err_txt}",
                            "finished_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
                        }
                    )
                return

            layer_progress: Dict[str, tuple[int, int]] = {}
            for raw_line in resp.iter_lines(decode_unicode=True):
                if not raw_line:
                    continue
                try:
                    chunk = json.loads(raw_line)
                except Exception:
                    continue
                if chunk.get("error"):
                    raw_err = str(chunk["error"])
                    if "file does not exist" in raw_err.lower():
                        raw_err = (
                            f"{raw_err} — verify the model tag exists on Ollama Hub / Hugging Face "
                            "(for example 'qwen3.5:4b'), or click 'Browse .gguf...' for local weights."
                        )
                    with _PULL_LOCK:
                        _PULL_STATE.update(
                            {
                                "active": False,
                                "status": "error",
                                "success": False,
                                "error": raw_err,
                                "finished_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
                            }
                        )
                    return
                digest = chunk.get("digest")
                total = int(chunk.get("total") or 0)
                completed = int(chunk.get("completed") or 0)
                status = str(chunk.get("status") or "pulling")
                if digest and total > 0:
                    prev_c, prev_t = layer_progress.get(digest, (0, total))
                    layer_progress[digest] = (max(prev_c, min(completed, total)), max(prev_t, total))
                with _PULL_LOCK:
                    if layer_progress:
                        cur_done = sum(c for c, _ in layer_progress.values())
                        cur_total = sum(t for _, t in layer_progress.values())
                    else:
                        cur_total = total if total > 0 else int(_PULL_STATE.get("total_bytes") or 0)
                        cur_done = completed if completed > 0 else int(_PULL_STATE.get("completed_bytes") or 0)
                    prev_pct = float(_PULL_STATE.get("percent") or 0.0)
                    raw_pct = round(min(100.0, (cur_done / cur_total) * 100.0), 1) if cur_total > 0 else prev_pct
                    pct = max(prev_pct, raw_pct)
                    _PULL_STATE.update(
                        {
                            "status": status,
                            "total_bytes": cur_total,
                            "completed_bytes": cur_done,
                            "percent": pct,
                        }
                    )

        # Auto-alias pulled HF/hub ARGUS tag so `argus-m1-sft` / `argus-m1-rft` resolves cleanly
        lower_ref = model_ref.lower()
        alias_name = (
            "argus-m1-rft"
            if ("argus-m1-rft" in lower_ref and not lower_ref.startswith("argus-m1-rft"))
            else ("argus-m1-sft" if ("argus-m1-sft" in lower_ref and not lower_ref.startswith("argus-m1-sft")) else None)
        )
        if alias_name:
            try:
                sess.post(
                    f"{base_url}/api/copy",
                    json={"source": model_ref, "destination": alias_name},
                    timeout=10,
                )
            except Exception:
                pass

        with _PULL_LOCK:
            _PULL_STATE.update(
                {
                    "active": False,
                    "status": "success",
                    "percent": 100.0,
                    "success": True,
                    "error": None,
                    "finished_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
                }
            )
    except Exception as exc:
        with _PULL_LOCK:
            _PULL_STATE.update(
                {
                    "active": False,
                    "status": "error",
                    "success": False,
                    "error": f"Ollama pull error: {exc}",
                    "finished_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
                }
            )


def start_pull_ollama_model(
    model_ref: str,
    endpoint: str = DEFAULT_OLLAMA_URL,
) -> Dict[str, Any]:
    """Start an asynchronous streaming `ollama pull` against local Ollama daemon."""
    ref = normalize_model_ref(model_ref)
    if not _MODEL_NAME_RE.fullmatch(ref):
        raise ValueError(f"Invalid Ollama / Hugging Face model tag: {model_ref!r}")

    status = check_ollama_status(endpoint=endpoint, timeout=1.5)
    if not status.get("running") and status.get("ollama_installed"):
        status = ensure_ollama_running(endpoint=endpoint, start_timeout=8.0)
    if not status.get("running"):
        raise RuntimeError(status.get("error") or f"Ollama daemon is not running at {endpoint}")

    with _PULL_LOCK:
        if _PULL_STATE.get("active"):
            snapshot = dict(_PULL_STATE)
            snapshot["already_running"] = True
            return snapshot
        _PULL_STATE.update(
            {
                "active": True,
                "model": ref,
                "status": "starting",
                "completed_bytes": 0,
                "total_bytes": 0,
                "percent": 0.0,
                "success": None,
                "error": None,
                "started_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
                "finished_at": None,
            }
        )
        snapshot = dict(_PULL_STATE)

    t = threading.Thread(target=_run_pull_worker, args=(ref, endpoint.rstrip("/")), daemon=True)
    t.start()
    return snapshot
