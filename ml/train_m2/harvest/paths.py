"""Repository paths used by the harvest tool (all derived from this file's location)."""

from pathlib import Path

# .../<repo>/ml/train_m2/harvest/paths.py -> parents[3] is <repo>
REPO_ROOT = Path(__file__).resolve().parents[3]
CONTRACT_DIR = REPO_ROOT / "ml" / "train_m2" / "contract"
INPUTS_PATH = CONTRACT_DIR / "harvest_inputs.jsonl"
SCHEMA_PATH = CONTRACT_DIR / "harvest_line.schema.json"
FIXTURE_PATH = CONTRACT_DIR / "harvest_fixture.jsonl"
DEFAULT_OUT = REPO_ROOT / "ml" / "train_m2" / "harvest_out"
DEFAULT_MANIFEST_DIR = REPO_ROOT / "ml" / "train_m2" / "harvest_manifests"
PATCH_IR_SCHEMA = REPO_ROOT / "remediate" / "patch_ir" / "schema.json"
PHASE5_RUNS = REPO_ROOT / "ml" / "train_m1" / "eval" / "runs"
PILOT_DIR = REPO_ROOT / "ml" / "train_m1" / "v2" / "out" / "pilot"
DOCS_DIR = REPO_ROOT / "docs" / "phase6_prabhav"
