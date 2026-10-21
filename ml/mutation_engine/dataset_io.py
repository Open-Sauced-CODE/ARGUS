"""
ARGUS Phase 5 - small shared helpers for dataset files: canonical JSON, hashes, jsonl reading and writing.
Everything is deterministic: the same data always produces the same bytes and the same hashes.
"""

import hashlib
import json
from pathlib import Path


def canon(obj):
    """Canonical JSON text: sorted keys, no spaces, ASCII only."""
    return json.dumps(obj, sort_keys=True, separators=(",", ":"), ensure_ascii=True)


def sha256_text(text):
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def sha256_file(path):
    digest = hashlib.sha256()
    with open(path, "rb") as handle:
        for block in iter(lambda: handle.read(1 << 20), b""):
            digest.update(block)
    return digest.hexdigest()


def full_hash(rule_id, mutated_plain):
    """Hash of the FULL mutated resource (attrs plus extras) and the rule (contracts D10).
    mutated_plain = {"resource_type", "attrs", "extras"}."""
    return sha256_text(canon({
        "rule_id": rule_id,
        "resource_type": mutated_plain["resource_type"],
        "attrs": mutated_plain["attrs"],
        "extras": mutated_plain["extras"],
    }))


def input_key(example):
    """Identity of what the model sees (finding_id left out: it only says F-0, F-1 ...)."""
    inp = example["input"]
    return canon({"rule_id": inp["rule_id"], "fields": inp["fields"], "resource_ref": inp["resource_ref"]})


def target_key(example):
    target = example.get("target")
    return canon(target["ops"]) if target else ""


def read_jsonl(path):
    path = Path(path)
    if not path.exists():
        return []
    rows = []
    with open(path, "r", encoding="utf-8") as handle:
        for line in handle:
            line = line.strip()
            if line:
                rows.append(json.loads(line))
    return rows


def write_jsonl(path, rows):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8", newline="\n") as handle:
        for row in rows:
            handle.write(json.dumps(row, sort_keys=True, ensure_ascii=True) + "\n")
