"""Shared bits of the Tier C scripts: folders, permalinks, hash lists."""

from pathlib import Path

from ml.mutation_engine.dataset_io import read_jsonl

REPO_ROOT = Path(__file__).resolve().parents[2]
HELD_OUT_DIR = REPO_ROOT / "ml" / "mutation_engine" / "held_out"
OUT_DIR = REPO_ROOT / "ml" / "real_data" / "out"
REVIEW_DIR = REPO_ROOT / "ml" / "real_data" / "review"
REPOS_CSV = REPO_ROOT / "ml" / "real_data" / "tierC_repos.csv"
STATUS_CSV = REPO_ROOT / "ml" / "real_data" / "tierC_clone_status.csv"


def permalink(repo, commit, path):
    return "https://github.com/{}/blob/{}/{}".format(repo, commit, path)


def update_c_hashes(held_dir=HELD_OUT_DIR):
    """held_out/tierC_base_hashes.txt = norm_hash of every real resource used in a Tier C file (for the leakage guard)."""
    held_dir = Path(held_dir)
    hashes = set()
    for name in ("tierC_verifier.jsonl", "tierC_mined.jsonl"):
        for row in read_jsonl(held_dir / name):
            hashes.add(row["meta"]["base_norm_hash"])
    (held_dir / "tierC_base_hashes.txt").write_text("\n".join(sorted(hashes)) + ("\n" if hashes else ""), encoding="ascii", newline="\n")
    return len(hashes)
