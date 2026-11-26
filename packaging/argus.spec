# -*- mode: python ; coding: utf-8 -*-
"""PyInstaller spec for ARGUS-Desktop (--onedir, bundled opa.exe, Rego, UI, zero heavy ML training libs)."""

from __future__ import annotations

import os
from pathlib import Path
from PyInstaller.utils.hooks import collect_all, collect_data_files, collect_submodules

ROOT = Path(SPECPATH).resolve().parent
OPA_BIN = Path(os.environ.get("OPA_BIN", r"D:\opa\opa.exe"))
ICON_PATH = ROOT / "packaging" / "argus.ico"

if not OPA_BIN.exists():
    raise FileNotFoundError(f"OPA binary not found for bundling: {OPA_BIN}")

datas = [
    (str(ROOT / "dashboard" / "dist"), "dashboard/dist"),
    (str(ROOT / "policy"), "policy"),
    (str(ROOT / "remediate" / "patch_ir" / "schema.json"), "remediate/patch_ir"),
    (str(ROOT / "ml" / "train_m2" / "configs"), "ml/train_m2/configs"),
    (str(ROOT / "releases" / "manifest.json"), "releases"),
    (str(ROOT / "releases" / "benchmarks.json"), "releases"),
    (str(ROOT / "testbeds" / "sample_dpdp_infra"), "testbeds/sample_dpdp_infra"),
    (str(ROOT / "demo.py"), "."),
]

for json_file in (ROOT / "risk").glob("*.json"):
    datas.append((str(json_file), "risk"))
for json_file in (ROOT / "prioritize").glob("*.json"):
    datas.append((str(json_file), "prioritize"))

binaries = [
    (str(OPA_BIN), "bin"),
]

# Collect lark, hcl2, jsonschema/rfc3987_syntax, and pulp non-Python data/binaries
for _pkg in ("lark", "hcl2", "rfc3987_syntax", "jsonschema_specifications", "jsonschema", "referencing", "pulp"):
    _d, _b, _h = collect_all(_pkg)
    datas += _d
    binaries += _b
    _extra_hidden = _h if "_extra_hidden" not in globals() else (_extra_hidden + _h)

hiddenimports = (
    [
        "pystray",
        "pystray._win32",
        "PIL",
        "PIL.Image",
        "PIL.ImageDraw",
        "hcl2",
        "lark",
        "boto3",
        "botocore",
        "scipy",
        "scipy.optimize",
        "scipy.optimize._highs",
        "scipy.sparse",
        "pulp",
        "networkx",
        "cryptography",
        "cryptography.fernet",
        "jsonschema",
        "pydantic",
        "requests",
        "yaml",
        "sqlite3",
        "configparser",
        "demo",
        "ml",
        "ml.mutation_engine",
        "ml.mutation_engine.dataset_io",
        "ml.mutation_engine.labeler",
        "ml.mutation_engine.model",
        "ml.mutation_engine.qa",
        "ml.mutation_engine.qa.gate_stub",
        "ml.mutation_engine.qa.checks",
        "ml.mutation_engine.qa.hidden_checks",
        "ml.real_data",
        "ml.real_data.rego_runner",
        "ml.train_m1",
        "ml.train_m1.prompt",
        "ml.train_m1.eval",
        "ml.train_m1.eval.ollama_client",
    ]
    + _extra_hidden
    + collect_submodules("local_engine")
    + collect_submodules("backend")
    + collect_submodules("privacy")
    + collect_submodules("risk")
    + collect_submodules("prioritize")
    + collect_submodules("remediate")
)

excludes = [
    "torch",
    "torchvision",
    "torchaudio",
    "transformers",
    "unsloth",
    "bitsandbytes",
    "triton",
    "tensorflow",
    "spacy",
    "thinc",
    "blis",
    "presidio_analyzer",
    "checkov",
    "bc_python_hcl2",
    "azure",
    "crowdstrike",
    "docker",
    "matplotlib",
    "IPython",
    "jupyter",
    "notebook",
    "pytest",
    "tkinter",
    "pandas",
    "pyarrow",
    "sklearn",
    "lightgbm",
    "xgboost",
]

a = Analysis(
    [str(ROOT / "local_engine" / "desktop_main.py")],
    pathex=[str(ROOT)],
    binaries=binaries,
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=excludes,
    noarchive=False,
    optimize=0,
)
pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name="ARGUS",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon=str(ICON_PATH) if ICON_PATH.exists() else None,
)

coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    strip=False,
    upx=False,
    upx_exclude=[],
    name="ARGUS",
)
