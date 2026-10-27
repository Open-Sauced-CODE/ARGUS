"""Phase 6 reference-free oracle: determines correctness without a reference patch.

Contract
--------
CounterfactualOracle(rule_id).classify(record) -> CounterfactualResult
  label  : str  -- "minimal_correct" | "valid_not_minimal" | "wrong" | "unknown"
  state  : dict -- the minimal field-state that silences the rule (or {} if none found)
  edits  : int  -- number of edits in the minimal fix (or -1 if not found)

Algorithm
---------
For each field the target rule reads (from privacy.airlock.projection.load_declarations):
  1. Enumerate a finite domain per field type:
       bool fields      -> {True, False}
       enum fields      -> known values from APPROVED_ALGORITHMS (hidden_checks),
                          PUBLIC_CONSTANTS (gate_stub), INTERNAL_CIDR placeholder,
                          plus the observed values across ml/mutation_engine/bases/manifest.csv
                          and the training dataset.
       lifecycle days   -> the RETENTION_DAYS constant (90, documented in DPDP rule) and its
                          observed value in the dataset.
       free text / CIDR -> {INTERNAL_CIDR} (the gate's only allowed replacement; D12).
  2. BFS from the current field state: at each step apply one edit (field=value) and check
     with OPA whether the target rule is now silent AND no previously-silent rule fires.
     Cache OPA calls by state hash (json-canonical of the dict).
  3. Stop at max_edits=3 edits or max_states=5000 states (whichever is hit first).
  4. Collect all minimal-cardinality solutions.

label assignment:
  "minimal_correct"   -- candidate's resulting state equals one of the minimal states (up to
                         values_equivalent for every modified field)
  "valid_not_minimal" -- the rule is silent but extra edits exist beyond the minimal set
  "wrong"             -- rule still fires or regression triggered
  "unknown"           -- domain not fully enumerable, or search budget exhausted without
                         finding a silent state

Validation note: call compare_with_reference(oracle_result, hidden_result) to check agreement.
"""

from __future__ import annotations

import copy
import json
import logging
from collections import defaultdict
from dataclasses import dataclass, field
from functools import lru_cache
from pathlib import Path
from typing import Any, FrozenSet, Mapping

from ml.mutation_engine.dataset_io import canon
from ml.mutation_engine.qa.gate_stub import ALLOWED_OPS, PLACEHOLDERS
from ml.mutation_engine.qa.hidden_checks import values_equivalent
from ml.real_data.rego_runner import evaluate
from privacy.airlock.projection import load_declarations

LOG = logging.getLogger(__name__)

RETENTION_DAYS = 90          # DPDP documented retention constant
INTERNAL_CIDR = "INTERNAL_CIDR"
MAX_EDITS = 3
MAX_STATES = 5000

# Fields whose only valid replacement in the vocabulary is INTERNAL_CIDR or an approved CIDR
CIDR_FIELDS = frozenset(["ip_range"])

# Fields that represent lifecycle/retention days
DAYS_FIELDS = frozenset(["has_lifecycle_expiration"])

# Pre-approved string values known from the vocabulary
APPROVED_ALGORITHMS = ("AES256", "aws:kms", "aws:kms:dsse")
BOOL_VALUES = (True, False)


def _repo_root() -> Path:
    return Path(__file__).resolve().parents[3]


@lru_cache(maxsize=1)
def _observed_field_values() -> dict[str, set]:
    """Collect per-field observed values from training data (train + val)."""
    root = _repo_root()
    observed: dict[str, set] = defaultdict(set)
    for rel in ("ml/mutation_engine/dataset/train.jsonl", "ml/mutation_engine/dataset/val.jsonl"):
        p = root / rel
        if not p.exists():
            continue
        with open(p, encoding="utf-8", newline="") as fh:
            for line in fh:
                line = line.strip()
                if not line:
                    continue
                try:
                    row = json.loads(line)
                    for fname, val in row["input"]["fields"].items():
                        if isinstance(val, (bool, int, float, str)):
                            observed[fname].add(val)
                        elif isinstance(val, list):
                            for item in val:
                                if isinstance(item, str):
                                    observed[fname].add(item)
                except Exception:  # noqa: BLE001
                    pass
    return dict(observed)


def _domain(fname: str, current_val: Any) -> list[Any]:
    """Enumerate the finite candidate values for a field."""
    if isinstance(current_val, bool):
        return list(BOOL_VALUES)
    if fname in CIDR_FIELDS:
        return [INTERNAL_CIDR]
    if fname == "encryption_algorithm":
        return list(APPROVED_ALGORITHMS)
    observed = _observed_field_values().get(fname, set())
    candidates: list[Any] = []
    # Booleans observed
    for v in (True, False):
        if v not in candidates:
            candidates.append(v)
    # Observed string/numeric values
    for v in sorted(observed, key=str):
        if v not in candidates:
            candidates.append(v)
    # Common lifecycle
    if fname in DAYS_FIELDS or "day" in fname or "lifecycle" in fname:
        for v in (True, RETENTION_DAYS):
            if v not in candidates:
                candidates.append(v)
    return candidates


def _state_hash(fields: dict) -> str:
    return canon(fields)


@dataclass
class CounterfactualResult:
    """Result of the counterfactual oracle for one (record, candidate_patch) pair."""

    label: str               # "minimal_correct" | "valid_not_minimal" | "wrong" | "unknown"
    minimal_states: list[dict] = field(default_factory=list)
    min_edits: int = -1


_GLOBAL_OPA_CACHE: dict[str, Any] = {}


class CounterfactualOracle:
    """BFS reference-free oracle for one rule_id.

    Parameters
    ----------
    rule_id     The rule whose silence we search for.
    max_edits   Maximum edit distance from the original state to search.
    max_states  Maximum distinct field-states to evaluate before giving up.
    """

    def __init__(self, rule_id: str, max_edits: int = MAX_EDITS, max_states: int = MAX_STATES) -> None:
        self.rule_id = rule_id
        self.max_edits = max_edits
        self.max_states = max_states
        self._edit_fields: frozenset[str] = frozenset(
            f for f in load_declarations().get(rule_id, []) if f != "resource_type"
        )
        self._opa_cache = _GLOBAL_OPA_CACHE
        self._states_evaluated = 0

    def _opa_result(self, fields: dict) -> Any:
        """Evaluate `fields` with OPA; cache by state hash."""
        key = _state_hash(fields)
        if key not in self._opa_cache:
            results = evaluate([fields])
            self._opa_cache[key] = results[0]
        return self._opa_cache[key]

    def _evaluate_batch(self, fields_list: Sequence[dict]) -> None:
        """Evaluate a batch of states with OPA; cache by state hash."""
        uncached = [f for f in fields_list if _state_hash(f) not in self._opa_cache]
        if not uncached:
            return
        results = evaluate(uncached)
        for f, res in zip(uncached, results):
            self._opa_cache[_state_hash(f)] = res

    def _silent_and_no_regression(self, before_fired: FrozenSet[str], after_fields: dict) -> bool:
        """True iff the target rule is silent after and no new rule fires."""
        result = self._opa_result(after_fields)
        fired_after = frozenset(result.deny) | frozenset(result.warn)
        new_rules = fired_after - before_fired
        # The target rule must not fire; no NEW rule should fire
        return self.rule_id not in fired_after and not new_rules

    def search_minimal(self, initial_fields: dict) -> list[tuple[int, dict]]:
        """BFS; returns list of (edits, fields) for all minimal silent states."""
        before = self._opa_result(initial_fields)
        before_fired = frozenset(before.deny) | frozenset(before.warn)

        if self.rule_id not in before_fired:
            # Already silent -- no fix needed; treat as unknown (no violation to fix)
            return []

        visited: set[str] = {_state_hash(initial_fields)}
        current_level: list[dict] = [initial_fields]
        solutions: list[tuple[int, dict]] = []

        for depth in range(1, self.max_edits + 1):
            next_candidates: list[dict] = []
            for state in current_level:
                for fname in sorted(self._edit_fields):
                    current_val = state.get(fname)
                    for new_val in _domain(fname, current_val):
                        if new_val == current_val:
                            continue
                        new_state = copy.copy(state)
                        new_state[fname] = new_val
                        h = _state_hash(new_state)
                        if h not in visited:
                            visited.add(h)
                            next_candidates.append(new_state)
                            if len(visited) >= self.max_states:
                                break
                    if len(visited) >= self.max_states:
                        break
                if len(visited) >= self.max_states:
                    break

            if not next_candidates:
                break

            self._evaluate_batch(next_candidates)
            self._states_evaluated += len(next_candidates)

            next_level: list[dict] = []
            for state in next_candidates:
                if self._silent_and_no_regression(before_fired, state):
                    solutions.append((depth, state))
                else:
                    next_level.append(state)

            if solutions:
                # Found minimal solutions at this depth
                break

            current_level = next_level
            if len(visited) >= self.max_states:
                break

        return solutions

    def classify(self, record: Mapping[str, Any], candidate_patch: Any = None) -> CounterfactualResult:
        """Classify a record (and optionally a candidate patch) using the counterfactual search.

        Parameters
        ----------
        record          The airlock record (has "fields" dict).
        candidate_patch The candidate Patch-IR to classify.  When None, only the minimal
                        states are returned (useful for building training examples).
        """
        from ml.mutation_engine.qa.hidden_checks import apply_fields

        initial_fields = dict(record.get("fields", {}))
        solutions = self.search_minimal(initial_fields)

        exhausted = self._states_evaluated >= self.max_states

        if not solutions:
            label = "unknown" if exhausted else "unknown"
            return CounterfactualResult(label=label, minimal_states=[], min_edits=-1)

        min_edits = min(e for e, _ in solutions)
        minimal_states = [s for e, s in solutions if e == min_edits]

        if candidate_patch is None:
            return CounterfactualResult(
                label="unknown",
                minimal_states=minimal_states,
                min_edits=min_edits,
            )

        # Determine candidate's resulting state
        cand_state = apply_fields(initial_fields, candidate_patch)

        # Check if candidate state matches one of the minimal states (up to values_equivalent)
        def states_match(a: dict, b: dict) -> bool:
            all_keys = set(a) | set(b)
            return all(values_equivalent(k, a.get(k), b.get(k)) for k in all_keys)

        in_minimal = any(states_match(cand_state, ms) for ms in minimal_states)

        if in_minimal:
            label = "minimal_correct"
        elif self._silent_and_no_regression(
            frozenset(self._opa_result(initial_fields).deny) | frozenset(self._opa_result(initial_fields).warn),
            cand_state,
        ):
            label = "valid_not_minimal"
        else:
            label = "wrong"

        return CounterfactualResult(
            label=label,
            minimal_states=minimal_states,
            min_edits=min_edits,
        )


def compare_with_reference(cf_label: str, ref_oracle_class: str) -> bool:
    """True when the counterfactual and reference oracles agree on correctness.

    Agreement is defined as: both say "correct" (minimal_correct or valid_not_minimal)
    or both say "not correct" (wrong, unknown).
    """
    cf_positive = cf_label in ("minimal_correct", "valid_not_minimal")
    ref_positive = ref_oracle_class in ("minimal_correct", "valid_not_minimal")
    return cf_positive == ref_positive
