"""Validation of one harvest line against ml/train_m2/contract/harvest_line.schema.json."""

from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path
from typing import Any, Dict

import jsonschema

from ml.train_m2.harvest.paths import SCHEMA_PATH


class HarvestSchemaError(ValueError):
    """A harvest line does not match the contract. Always a bug in the tool, never silently ignored."""


@lru_cache(maxsize=4)
def _validator(schema_path: str):
    schema = json.loads(Path(schema_path).read_text(encoding="utf-8-sig"))
    cls = getattr(jsonschema, "Draft202012Validator", None) or jsonschema.Draft7Validator
    return cls(schema)


def validate_line(line: Dict[str, Any], schema_path: Path = SCHEMA_PATH) -> None:
    """Raise HarvestSchemaError (listing up to 5 problems) if the line breaks the contract."""
    validator = _validator(str(schema_path))
    errors = sorted(validator.iter_errors(line), key=lambda e: [str(p) for p in e.path])
    if errors:
        parts = ["%s: %s" % ("/".join(str(p) for p in e.path) or "(line)", e.message[:160]) for e in errors[:5]]
        raise HarvestSchemaError("; ".join(parts))


def text_equals_tokens(line: Dict[str, Any]) -> bool:
    """True when the concatenated token texts equal content (the contract requires this)."""
    return "".join(token["t"] for token in line.get("tokens", [])) == line.get("content", "")
