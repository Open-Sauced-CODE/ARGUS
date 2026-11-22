from pathlib import Path
import json
import pytest

from ml.train_m1.score_oof import score_oof_file, main
from ml.mutation_engine.build_dataset import DATASET_DIR
from ml.mutation_engine.dataset_io import input_key, read_jsonl


def test_score_oof_matching_train_items(tmp_path: Path):
    train_dataset = read_jsonl(Path(DATASET_DIR) / "train.jsonl")[:5]
    train_items = {}
    train_counts = {}
    for ex in train_dataset:
        k = input_key(ex)
        train_items[k] = ex
        train_counts[k] = train_counts.get(k, 0) + 1

    # Perfect prediction matching targets
    preds_file = tmp_path / "test_preds.jsonl"
    with open(preds_file, "w", encoding="utf-8") as fh:
        for ex in train_dataset:
            k = input_key(ex)
            target_str = json.dumps(ex["target"])
            fh.write(json.dumps({"input_key": k, "content": target_str}) + "\n")

    res = score_oof_file(preds_file, train_items, train_counts)
    assert res["keys_matched"] == len(train_items)
    assert res["pass_at_1"] == 1.0
    assert res["valid_schema"] == len(train_items)
    assert "100.0%" in res["summary"]


def test_score_oof_main_cli(tmp_path: Path, capsys):
    train_dataset = read_jsonl(Path(DATASET_DIR) / "train.jsonl")[:2]
    preds_file = tmp_path / "cli_test_preds.jsonl"
    with open(preds_file, "w", encoding="utf-8") as fh:
        for ex in train_dataset:
            k = input_key(ex)
            fh.write(json.dumps({"input_key": k, "content": json.dumps(ex["target"])}) + "\n")

    code = main([str(preds_file)])
    assert code == 0
    out = capsys.readouterr().out
    assert "100.0%" in out
