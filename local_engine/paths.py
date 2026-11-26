"""Frozen-safe path resolver for ARGUS source execution and future PyInstaller bundles."""

from __future__ import annotations

import json
import os
import shutil
import sys
from pathlib import Path
from typing import Any, Dict, Optional


def get_bundle_root() -> Path:
    """Return read-only asset root (sys._MEIPASS when bundled, else repo root)."""
    meipass = getattr(sys, "_MEIPASS", None)
    if meipass:
        return Path(meipass).resolve()
    return Path(__file__).resolve().parent.parent


def get_data_dir() -> Path:
    """Return writable user data directory (%LocalAppData%\\ARGUS or ~/.argus)."""
    env_dir = os.environ.get("ARGUS_DATA_DIR")
    if env_dir:
        base = Path(env_dir).expanduser().resolve()
    elif os.name == "nt":
        local_app = os.environ.get("LOCALAPPDATA")
        base = (Path(local_app) / "ARGUS") if local_app else (Path.home() / ".argus")
    else:
        base = Path.home() / ".argus"

    base.mkdir(parents=True, exist_ok=True)
    (base / "exports").mkdir(parents=True, exist_ok=True)
    (base / "logs").mkdir(parents=True, exist_ok=True)
    return base


def find_opa_binary() -> Optional[str]:
    """Locate opa / opa.exe across env OPA_BIN, bundled bin/, D:\\opa\\opa.exe, and PATH."""
    bundle_root = get_bundle_root()
    candidates = [
        os.environ.get("OPA_BIN"),
        str(bundle_root / "bin" / ("opa.exe" if os.name == "nt" else "opa")),
        str(bundle_root / ("opa.exe" if os.name == "nt" else "opa")),
        r"D:\opa\opa.exe" if os.name == "nt" else None,
        shutil.which("opa"),
    ]
    for cand in candidates:
        if not cand:
            continue
        p = Path(cand)
        if p.exists() and p.is_file():
            os.environ.setdefault("OPA_BIN", str(p))
            return str(p)
        which_hit = shutil.which(cand)
        if which_hit:
            os.environ.setdefault("OPA_BIN", which_hit)
            return which_hit
    return None


def get_policy_dir() -> Path:
    return get_bundle_root() / "policy"


def get_vault_paths() -> tuple[Path, Path]:
    data_dir = get_data_dir()
    return data_dir / "vault.db", data_dir / ".vault.key"


def get_state_db_path() -> Path:
    return get_data_dir() / "argus_state.db"


def get_exports_dir() -> Path:
    d = get_data_dir() / "exports"
    d.mkdir(parents=True, exist_ok=True)
    return d


def get_m2_status() -> Dict[str, Any]:
    """Inspect M2 conformal calibration state. Autonomy MUST stay OFF while certified=False."""
    root = get_bundle_root()
    tau_path = root / "ml" / "train_m2" / "out" / "tau_star.json"
    model_path = root / "ml" / "train_m2" / "out" / "m2" / "m2.joblib"
    decision_cfg_path = root / "ml" / "train_m2" / "configs" / "decision.json"

    cfg: Dict[str, Any] = {"alpha": 0.05, "delta": 0.05, "c_FA": 20.0, "c_esc": 1.0}
    if decision_cfg_path.exists():
        try:
            cfg = json.loads(decision_cfg_path.read_text(encoding="utf-8"))
        except Exception:
            pass

    if tau_path.exists():
        try:
            tau_info = json.loads(tau_path.read_text(encoding="utf-8"))
            certified = bool(tau_info.get("certified", False)) and model_path.exists()
            return {
                "certified": certified,
                "tau": tau_info.get("tau") if certified else None,
                "model_present": model_path.exists(),
                "tau_file_present": True,
                "alpha": float(cfg.get("alpha", 0.05)),
                "delta": float(cfg.get("delta", 0.05)),
                "status": "CERTIFIED" if certified else "UNCERTIFIED_HUMAN_REVIEW",
                "message": (
                    "M2 conformal LTT certified."
                    if certified
                    else "Autonomy OFF: tau_star.json exists but certified=False or m2.joblib absent."
                ),
            }
        except Exception:
            pass

    return {
        "certified": False,
        "tau": None,
        "model_present": model_path.exists(),
        "tau_file_present": False,
        "alpha": float(cfg.get("alpha", 0.05)),
        "delta": float(cfg.get("delta", 0.05)),
        "status": "PENDING_CALIBRATION",
        "message": "Autonomy OFF: awaiting M2 LTT calibration (tau_star.json & m2.joblib not yet emitted).",
    }
