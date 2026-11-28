"""Diagnostic first-JSON prefix extraction for OOF predictions (Shaurya-owned).

Used ONLY as a diagnostic proxy for grammar-constrained (format=schema) generation
when an OOF prediction file contains trailing continuation text (e.g. ``assistant`` /
``<think>``) after the first JSON object.

Never modifies or repairs prediction files on disk. Does NOT search for JSON objects
starting after leading non-JSON text.
"""
from __future__ import annotations

import json
import logging
from functools import lru_cache
from pathlib import Path
from typing import Any, Mapping, Sequence

import jsonschema

from ml.train_m2.common import repo_root
from ml.train_m2.labels.canon import canonical_answer

LOG = logging.getLogger(__name__)
_DECODER = json.JSONDecoder()
_TRAILING_MARKERS: tuple[str, ...] = ("<think>", "</think>", "<|im_end|>", "\nassistant")


@lru_cache(maxsize=1)
def _default_validator() -> jsonschema.Draft7Validator:
    """Load and cache Draft7Validator for remediate/patch_ir/schema.json."""
    schema_path = repo_root() / "remediate" / "patch_ir" / "schema.json"
    schema = json.loads(schema_path.read_text(encoding="utf-8"))
    return jsonschema.Draft7Validator(schema)


def _get_validator(schema: Mapping[str, Any] | None) -> jsonschema.Draft7Validator:
    if schema is None:
        return _default_validator()
    return jsonschema.Draft7Validator(schema)


def first_json_prefix(
    content: str | None,
    schema: Mapping[str, Any] | None = None,
) -> tuple[dict[str, Any] | None, bool]:
    """Extract the first JSON object starting at index 0 of stripped ``content``.

    Uses ``json.JSONDecoder().raw_decode`` on ``content.strip()`` starting strictly at
    index 0 (never searches for later JSON objects). Validates the decoded object
    against ``remediate/patch_ir/schema.json`` (or ``schema`` if provided).

    Returns:
        ``(obj, True)`` if the stripped string starts with a schema-valid JSON object,
        otherwise ``(None, False)``.
    """
    if not isinstance(content, str):
        return None, False
    stripped = content.strip()
    if not stripped:
        return None, False
    try:
        obj, _ = _DECODER.raw_decode(stripped, 0)
    except (json.JSONDecodeError, ValueError):
        return None, False

    if not isinstance(obj, dict):
        return None, False

    validator = _get_validator(schema)
    if not validator.is_valid(obj):
        return None, False

    return obj, True


def has_trailing_text(content: str | None) -> bool:
    """Return True if stripped ``content`` starts with a valid JSON dict followed by non-whitespace text."""
    if not isinstance(content, str):
        return False
    stripped = content.strip()
    if not stripped:
        return False
    try:
        obj, end_idx = _DECODER.raw_decode(stripped, 0)
    except (json.JSONDecodeError, ValueError):
        return False
    if not isinstance(obj, dict):
        return False
    return bool(stripped[end_idx:].strip())


def trailing_text_inside_json(obj: Any) -> bool:
    """Return True if any string field inside ``obj`` contains chat/think continuation markers."""
    if isinstance(obj, str):
        low = obj.lower()
        return any(m in low for m in _TRAILING_MARKERS)
    if isinstance(obj, Mapping):
        return any(trailing_text_inside_json(v) for v in obj.values())
    if isinstance(obj, (list, tuple)):
        return any(trailing_text_inside_json(v) for v in obj)
    return False


def matches_reference_canonical(
    obj: Mapping[str, Any] | None,
    reference: Mapping[str, Any] | None,
) -> bool:
    """Compare canonical (ops, rationale_ref) form ignoring finding_id and resource_ref."""
    if not isinstance(obj, Mapping) or not isinstance(reference, Mapping):
        return False
    cand_key = canonical_answer(json.dumps(dict(obj), sort_keys=True, ensure_ascii=True))
    ref_key = canonical_answer(json.dumps(dict(reference), sort_keys=True, ensure_ascii=True))
    return cand_key == ref_key


def _length_bin_label(length: int, bins: Sequence[tuple[str, int, int]]) -> str:
    for label, lo, hi in bins:
        if lo <= length < hi:
            return label
    return f">={bins[-1][2]}" if bins else "all"


def compute_truncation_diagnostics(
    preds_by_fold: Mapping[int, Sequence[Mapping[str, Any]]],
    key_flags: Mapping[str, Mapping[str, bool]],
    ref_map: Mapping[str, Mapping[str, Any]],
    *,
    all_refs_by_key: Mapping[str, Sequence[Mapping[str, Any]]] | None = None,
    schema: Mapping[str, Any] | None = None,
    runaway_min_len: int = 2000,
) -> dict[str, Any]:
    """Compute counts-only first-JSON prefix diagnostics across folds (zero held-out content)."""
    runaway_bins: tuple[tuple[str, int, int], ...] = (
        ("[2000, 3500)", 2000, 3500),
        ("[3500, 3800)", 3500, 3800),
        ("[3800, 4100)", 3800, 4100),
        ("[4100, 4500)", 4100, 4500),
        (">=4500", 4500, 10**9),
    )

    per_fold: list[dict[str, Any]] = []
    for f in sorted(preds_by_fold.keys()):
        rows = list(preds_by_fold[f])
        valid_first = 0
        extra_text = 0
        inside_json_leak = 0
        clean_clusters = 0
        clean_equal_ref = 0

        runaway_count = 0
        runaway_first_json_complete = 0
        runaway_hist = {label: 0 for label, _, _ in runaway_bins}
        runaway_min = None
        runaway_max = None

        unterm_count = 0
        unterm_first_json_complete = 0
        unterm_hist = {label: 0 for label, _, _ in runaway_bins}
        unterm_min = None
        unterm_max = None

        for r in rows:
            ik = str(r.get("input_key", ""))
            content = str(r.get("content", ""))
            obj, ok = first_json_prefix(content, schema=schema)
            if ok:
                valid_first += 1
                if trailing_text_inside_json(obj):
                    inside_json_leak += 1
            if has_trailing_text(content):
                extra_text += 1

            flags = key_flags.get(ik, {})
            is_clean = not flags.get("in_heldout", False) and not flags.get("in_a_val", False)
            if is_clean:
                clean_clusters += 1
                if ok and obj is not None:
                    refs_to_check: Sequence[Mapping[str, Any]] = ()
                    if all_refs_by_key and ik in all_refs_by_key:
                        refs_to_check = all_refs_by_key[ik]
                    elif ik in ref_map and isinstance(ref_map[ik].get("reference"), Mapping):
                        refs_to_check = [ref_map[ik]["reference"]]
                    if any(matches_reference_canonical(obj, ref) for ref in refs_to_check):
                        clean_equal_ref += 1

            clen = len(content)
            if clen >= runaway_min_len:
                runaway_count += 1
                if ok:
                    runaway_first_json_complete += 1
                runaway_hist[_length_bin_label(clen, runaway_bins)] += 1
                runaway_min = clen if runaway_min is None else min(runaway_min, clen)
                runaway_max = clen if runaway_max is None else max(runaway_max, clen)
                if not content.rstrip().endswith("}"):
                    unterm_count += 1
                    if ok:
                        unterm_first_json_complete += 1
                    unterm_hist[_length_bin_label(clen, runaway_bins)] += 1
                    unterm_min = clen if unterm_min is None else min(unterm_min, clen)
                    unterm_max = clen if unterm_max is None else max(unterm_max, clen)

        per_fold.append({
            "fold": f,
            "rows": len(rows),
            "valid_first_json": valid_first,
            "clean_clusters": clean_clusters,
            "clean_equal_ref_canon": clean_equal_ref,
            "extra_text_after_json": extra_text,
            "trailing_text_inside_json": inside_json_leak,
            "runaway_outputs": {
                "threshold_chars": runaway_min_len,
                "count": runaway_count,
                "first_json_complete": runaway_first_json_complete,
                "min_len": runaway_min,
                "max_len": runaway_max,
                "length_histogram": runaway_hist,
            },
            "unterminated_runaway_outputs": {
                "count": unterm_count,
                "first_json_complete": unterm_first_json_complete,
                "min_len": unterm_min,
                "max_len": unterm_max,
                "length_histogram": unterm_hist,
            },
        })

    return {"per_fold": per_fold}
