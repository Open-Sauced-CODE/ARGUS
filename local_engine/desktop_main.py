"""Windows Desktop entrypoint for ARGUS-Desktop (System Tray + Loopback Server + --smoke-test)."""

from __future__ import annotations

import argparse
import ctypes
import json
import logging
import os
import shutil
import subprocess
import sys
import tempfile
import threading
import time
import urllib.request
import webbrowser
from http.server import ThreadingHTTPServer
from pathlib import Path
from typing import Any, Optional

# Ensure bundle root / repo root is on sys.path
_MEIPASS = getattr(sys, "_MEIPASS", None)
_ROOT = Path(_MEIPASS).resolve() if _MEIPASS else Path(__file__).resolve().parent.parent
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

_NO_PROXY_OPENER = urllib.request.build_opener(urllib.request.ProxyHandler({}))


def _setup_streams_and_logging(log_file: Path, *, smoke_test: bool = False) -> logging.Logger:
    log_file.parent.mkdir(parents=True, exist_ok=True)
    if smoke_test and os.name == "nt" and (sys.stdout is None or sys.stderr is None):
        try:
            if ctypes.windll.kernel32.AttachConsole(-1):
                if sys.stdout is None:
                    sys.stdout = open("CONOUT$", "w", encoding="utf-8", errors="replace")
                if sys.stderr is None:
                    sys.stderr = open("CONOUT$", "w", encoding="utf-8", errors="replace")
        except Exception:
            pass

    if sys.stdout is None:
        sys.stdout = open(log_file, "a", encoding="utf-8", errors="replace")
    if sys.stderr is None:
        sys.stderr = open(log_file, "a", encoding="utf-8", errors="replace")

    logger = logging.getLogger("argus.desktop")
    logger.setLevel(logging.INFO)
    if not logger.handlers:
        fh = logging.FileHandler(log_file, encoding="utf-8")
        fh.setFormatter(logging.Formatter("%(asctime)s [%(levelname)s] %(message)s"))
        logger.addHandler(fh)
    return logger


def _create_shield_icon():
    from PIL import Image, ImageDraw

    size = 64
    img = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)
    # Peacock shield outer polygon
    shield = [(32, 4), (56, 13), (53, 35), (32, 59), (11, 35), (8, 13)]
    draw.polygon(shield, fill=(10, 46, 51, 255), outline=(46, 156, 130, 255))
    # Inner saffron/emerald accent core
    inner = [(32, 13), (47, 19), (45, 34), (32, 50), (19, 34), (17, 19)]
    draw.polygon(inner, fill=(46, 156, 130, 255))
    draw.ellipse((25, 23, 39, 37), fill=(245, 166, 35, 255))
    return img


def _is_instance_running(port: int) -> bool:
    try:
        with _NO_PROXY_OPENER.open(f"http://127.0.0.1:{port}/api/health", timeout=0.9) as resp:
            if resp.status != 200:
                return False
            data = json.loads(resp.read().decode("utf-8"))
            return bool(data.get("can_scan_local")) and data.get("runtime_mode") == "local_agent"
    except Exception:
        return False


def _wait_for_health(port: int, timeout: float = 5.0) -> bool:
    deadline = time.time() + timeout
    while time.time() < deadline:
        try:
            with _NO_PROXY_OPENER.open(f"http://127.0.0.1:{port}/api/health", timeout=0.6) as resp:
                if resp.status == 200:
                    return True
        except Exception:
            time.sleep(0.1)
    return False


def _open_folder(path: Path) -> None:
    path.mkdir(parents=True, exist_ok=True)
    if os.name == "nt":
        os.startfile(str(path))  # type: ignore[attr-defined]
    else:
        webbrowser.open(path.as_uri())


def run_smoke_test(smoke_log: Optional[str] = None) -> int:
    """Headless self-verification inside built .exe or source checkout."""
    temp_data = Path(tempfile.mkdtemp(prefix="argus-smoke-"))
    prev_env = {
        k: os.environ.get(k)
        for k in ("ARGUS_RUNTIME_MODE", "ARGUS_DATA_DIR", "ARGUS_HEADLESS")
    }
    os.environ["ARGUS_RUNTIME_MODE"] = "local_agent"
    os.environ["ARGUS_DATA_DIR"] = str(temp_data)
    os.environ["ARGUS_HEADLESS"] = "1"

    lines: list[str] = []

    def _log(msg: str) -> None:
        lines.append(msg)
        print(msg, flush=True)

    try:
        from local_engine.paths import find_opa_binary, get_bundle_root, get_policy_dir
        from local_engine.scanners.terraform_scanner import scan_terraform_directory
        from cryptography.fernet import Fernet
        from privacy.airlock.airlock import run_airlock
        from privacy.vault.vault import TokenVault
        from remediate.templates import match as t0_match
        from ml.mutation_engine.qa.gate_stub import gate_many
        from backend.api_server import ArgusAppHandler

        bundle_root = get_bundle_root()
        policy_dir = get_policy_dir()
        dist_index = bundle_root / "dashboard" / "dist" / "index.html"
        schema_file = bundle_root / "remediate" / "patch_ir" / "schema.json"
        sample_tf = bundle_root / "testbeds" / "sample_dpdp_infra"

        assert dist_index.exists(), f"Missing bundled UI: {dist_index}"
        assert policy_dir.exists() and any(policy_dir.rglob("*.rego")), f"Missing Rego rules: {policy_dir}"
        assert schema_file.exists(), f"Missing Patch-IR schema: {schema_file}"
        assert sample_tf.exists(), f"Missing sample_dpdp_infra: {sample_tf}"
        _log(f"[SMOKE 1/6] Bundle assets verified under {bundle_root}")

        opa_bin = find_opa_binary()
        assert opa_bin, "OPA binary not found (bundled bin/opa.exe or D:\\opa\\opa.exe)"
        creationflags = getattr(subprocess, "CREATE_NO_WINDOW", 0x08000000) if os.name == "nt" else 0
        opa_ver = subprocess.run(
            [opa_bin, "version"],
            capture_output=True,
            text=True,
            timeout=10,
            creationflags=creationflags,
        )
        assert opa_ver.returncode == 0, f"opa version failed: {opa_ver.stderr}"
        _log(f"[SMOKE 2/6] Bundled OPA verified: {opa_bin}")

        vault = TokenVault(db_path=temp_data / "vault.db", key=Fernet.generate_key())
        raw_rec = {
            "finding_id": "F-SMOKE-01",
            "resource_id": "swasthya-citizen-kyc-pii",
            "resource_type": "AWSS3Bucket",
            "attributes": {
                "name": "swasthya-citizen-kyc-pii",
                "arn": "arn:aws:s3:::swasthya-citizen-kyc-pii",
                "region": "ap-south-1",
                "approved_regions": ["ap-south-1"],
                "personal_data": True,
                "default_encryption": False,
                "encryption_algorithm": "none",
                "tags": {"pii": "aadhaar 4532 8912 0019", "key": "AKIAIOSFODNN7EXAMPLE"},
            },
        }
        sanitized, receipt = run_airlock(raw_rec, "dpdp.rule6a", vault=vault, policy_dir=policy_dir)
        assert receipt.get("leaked_to_network") is False, "Airlock leak check failed"
        assert "swasthya-citizen-kyc-pii" not in json.dumps(sanitized), "Raw bucket leaked past airlock"
        _log("[SMOKE 3/6] Privacy Airlock + TokenVault + Scrubbers verified (0 bytes leaked)")

        patch_ir = t0_match(sanitized)
        assert patch_ir is not None, "T0 template returned None"
        verdict = gate_many([(sanitized, patch_ir)])[0]
        assert verdict.passed and verdict.outcome == "fixed", f"OPA Gate failed: {verdict.reasons}"
        _log("[SMOKE 4/6] Tier 0 + OPA Rego Gate verified")

        tf_res = scan_terraform_directory(sample_tf, approved_regions=["ap-south-1"])
        assert tf_res["opa_used"] is True and len(tf_res["raw_findings"]) >= 5, "Terraform scan failed"
        _log(f"[SMOKE 5/6] Terraform scanner verified ({len(tf_res['raw_findings'])} findings via OPA)")

        srv = ThreadingHTTPServer(("127.0.0.1", 0), ArgusAppHandler)
        port = srv.server_address[1]
        t = threading.Thread(target=srv.serve_forever, daemon=True)
        t.start()
        try:
            with _NO_PROXY_OPENER.open(f"http://127.0.0.1:{port}/api/health", timeout=5) as r:
                health = json.loads(r.read().decode("utf-8"))
                assert r.status == 200 and health["runtime_mode"] == "local_agent"
            with _NO_PROXY_OPENER.open(f"http://127.0.0.1:{port}/api/local/status", timeout=5) as r:
                loc = json.loads(r.read().decode("utf-8"))
                assert r.status == 200 and loc["can_scan_local"] is True and loc["opa_ready"] is True
            with _NO_PROXY_OPENER.open(f"http://127.0.0.1:{port}/api/local/models/discovered", timeout=5) as r:
                assert r.status == 200
            with _NO_PROXY_OPENER.open(f"http://127.0.0.1:{port}/api/local/aws-profiles", timeout=5) as r:
                assert r.status == 200
            with _NO_PROXY_OPENER.open(f"http://127.0.0.1:{port}/", timeout=5) as r:
                html = r.read().decode("utf-8").lower()
                assert r.status == 200 and "<!doctype html>" in html
        finally:
            srv.shutdown()
            srv.server_close()
        _log(f"[SMOKE 6/6] HTTP Server & React SPA verified on ephemeral loopback port {port}")
        _log("ARGUS DESKTOP SMOKE TEST PASSED")
        if smoke_log:
            Path(smoke_log).write_text("\n".join(lines) + "\n", encoding="utf-8")
        return 0
    except Exception as exc:
        _log(f"ARGUS DESKTOP SMOKE TEST FAILED: {type(exc).__name__}: {exc}")
        if smoke_log:
            try:
                Path(smoke_log).write_text("\n".join(lines) + "\n", encoding="utf-8")
            except Exception:
                pass
        return 1
    finally:
        for k, val in prev_env.items():
            if val is None:
                os.environ.pop(k, None)
            else:
                os.environ[k] = val
        shutil.rmtree(temp_data, ignore_errors=True)


def main(argv: Optional[list[str]] = None) -> int:
    parser = argparse.ArgumentParser(description="ARGUS Desktop Agent")
    parser.add_argument("--port", type=int, default=8742, help="Loopback HTTP port (default: 8742)")
    parser.add_argument("--smoke-test", action="store_true", help="Run headless self-verification and exit")
    parser.add_argument("--smoke-log", default=None, help="Optional path to write smoke test output")
    parser.add_argument("--no-browser", action="store_true", help="Do not auto-open browser on startup")
    parser.add_argument("--no-tray", action="store_true", help="Run without system tray icon")
    args = parser.parse_args(argv)

    if args.smoke_test:
        temp_log = Path(tempfile.gettempdir()) / "argus_smoke_boot.log"
        _setup_streams_and_logging(temp_log, smoke_test=True)
        return run_smoke_test(smoke_log=args.smoke_log)

    # Suppress flashing console windows from child CLI tools (e.g., opa.exe) in Windows GUI mode
    if os.name == "nt":
        _orig_popen_init = subprocess.Popen.__init__
        _no_window = getattr(subprocess, "CREATE_NO_WINDOW", 0x08000000)

        def _quiet_popen_init(self, *p_args: Any, **p_kwargs: Any) -> None:
            if not p_kwargs.get("creationflags"):
                p_kwargs["creationflags"] = _no_window
            _orig_popen_init(self, *p_args, **p_kwargs)

        subprocess.Popen.__init__ = _quiet_popen_init  # type: ignore[method-assign]

    os.environ["ARGUS_RUNTIME_MODE"] = "local_agent"
    from local_engine.paths import find_opa_binary, get_data_dir, get_exports_dir

    data_dir = get_data_dir()
    log_path = data_dir / "logs" / "argus_desktop.log"
    logger = _setup_streams_and_logging(log_path, smoke_test=False)
    opa_bin = find_opa_binary()
    logger.info("Starting ARGUS Desktop on 127.0.0.1:%s (OPA=%s)", args.port, opa_bin)

    url = f"http://127.0.0.1:{args.port}/"
    if _is_instance_running(args.port):
        logger.info("Existing ARGUS local instance detected; opening browser to %s", url)
        if not args.no_browser:
            webbrowser.open(url)
        return 0

    from backend.api_server import ArgusAppHandler

    listen_port = args.port
    try:
        server = ThreadingHTTPServer(("127.0.0.1", listen_port), ArgusAppHandler)
    except OSError as exc:
        logger.warning("Port %s unavailable (%s); binding fallback ephemeral loopback port.", listen_port, exc)
        server = ThreadingHTTPServer(("127.0.0.1", 0), ArgusAppHandler)
        listen_port = int(server.server_address[1])
        url = f"http://127.0.0.1:{listen_port}/"

    srv_thread = threading.Thread(target=server.serve_forever, daemon=True)
    srv_thread.start()

    if _wait_for_health(listen_port, timeout=5.0) and not args.no_browser:
        webbrowser.open(url)

    if args.no_tray:
        try:
            while srv_thread.is_alive():
                time.sleep(0.5)
        except KeyboardInterrupt:
            pass
        finally:
            server.shutdown()
            server.server_close()
        return 0

    try:
        import pystray

        def _open_console(_icon: Any = None, _item: Any = None) -> None:
            webbrowser.open(url)

        def _open_connect(_icon: Any = None, _item: Any = None) -> None:
            webbrowser.open(f"{url}?connect=1")

        def _open_models(_icon: Any = None, _item: Any = None) -> None:
            webbrowser.open(f"{url}downloads")

        def _open_exports(_icon: Any = None, _item: Any = None) -> None:
            _open_folder(get_exports_dir())

        def _open_logs(_icon: Any = None, _item: Any = None) -> None:
            _open_folder(data_dir / "logs")

        def _quit(icon_obj: Any, _item: Any = None) -> None:
            logger.info("Quit requested from system tray.")
            try:
                server.shutdown()
                server.server_close()
            finally:
                icon_obj.stop()

        menu = pystray.Menu(
            pystray.MenuItem(f"Open ARGUS Console (127.0.0.1:{listen_port})", _open_console, default=True),
            pystray.MenuItem("Scan GitHub / Terraform / AWS...", _open_connect),
            pystray.MenuItem("Setup / Check Ollama (argus-m1)", _open_models),
            pystray.Menu.SEPARATOR,
            pystray.MenuItem("Open Exports Folder", _open_exports),
            pystray.MenuItem("Open Logs Folder", _open_logs),
            pystray.Menu.SEPARATOR,
            pystray.MenuItem("Quit ARGUS", _quit),
        )
        icon = pystray.Icon("ARGUS", _create_shield_icon(), "ARGUS Zero-Egress Security", menu)
        icon.run()
    except Exception as exc:
        logger.warning("System tray unavailable (%s); running headless server loop.", exc)
        try:
            while srv_thread.is_alive():
                time.sleep(0.5)
        except KeyboardInterrupt:
            pass
        finally:
            server.shutdown()
            server.server_close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
