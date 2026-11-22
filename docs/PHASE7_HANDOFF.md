# Phase 7 Integration Handoff: ARGUS Trust Engine & Safe Auto-Apply

## 1. Overview & Architecture

Phase 7 implements the autonomous and human-in-the-loop remediation runtime (Role B execution engine and Role C trust/audit console). The Phase 6 Trust Engine (M2) sits immediately downstream of candidate generation and the deterministic Rego QA gate:

```
[Cloud Misconfiguration]
           |
           v
   [M1 Patch Generator] (Harvest Profile A)
           |
           v
    [Rego QA Gate]  ---- (Fail) ----> [Reject]
           | (Pass)
           v
 [Escalate-Only Check]  -- (True) --> [Human Review / Escalate]
           | (False, Fix Route)
           v
     [M2 Engine]  (confidence() & decide())
           |
     +-----+------------------------------+
     |                                    |
     v                                    v
[Auto-Apply] (p_hat >= thr)       [Human Review] (p_hat < thr OR uncertified)
```

## 2. Frozen Python Interfaces & Signatures

The decision engine in `ml/train_m2/decide.py` exposes two frozen functions:

### 2.1 Confidence Scoring: `confidence()`

```python
def confidence(
    features: Mapping[str, Any],
    art: dict[str, Any] | None = None,
    model_path: str | Path | None = None,
) -> float:
    """Compute calibrated probability of correctness p_hat in [0, 1].

    Args:
        features: Feature dictionary containing feature spec hash under 'spec_hash'
                  and numeric values matching the 35 feature names in the spec.
        art: Pre-loaded M2 model artifact dictionary (cached).
        model_path: Path to m2.joblib (used if art is None).

    Returns:
        p_hat: Calibrated probability that the patch is strictly correct.

    Raises:
        FeatureSpecMismatch: If features['spec_hash'] does not match art['spec_hash'].
    """
```

### 2.2 Decision Engine: `decide()`

```python
def decide(
    features: Mapping[str, Any],
    *,
    gate_passed: bool,
    escalated_only: bool,
    breaker: str,
    config: Mapping[str, Any],
    tau_info: Mapping[str, Any],
    art: dict[str, Any] | None = None,
) -> Decision:
    """Produce the safe remediation action: auto_apply, human_review, or reject.

    Order of decision logic:
      1. gate_passed is False -> action="reject", reason="gate failed".
      2. escalated_only is True -> action="human_review", reason="escalate-only patch: M2 is not consulted".
      3. tau_info['certified'] is False -> action="human_review", reason="no certified threshold: autonomy off".
      4. breaker != 'CLOSED' -> action="human_review", reason="drift breaker is not closed".
      5. is_ood(features) is True -> action="human_review", reason="ood: input outside the training distribution".
      6. If all checks pass:
           threshold_used = max(tau_info['tau'], bayes_cutoff(config['c_FA'], config['c_esc']))
           If p_hat >= threshold_used -> action="auto_apply".
           Else -> action="human_review", reason="confidence below stricter threshold".

    Returns:
        Decision frozen dataclass.
    """
```

## 3. Data Types & Audit Trust Record (`api_schemas.py`)

All Phase 7 runtime calls must validate payloads against Pydantic models in `ml/train_m2/api_schemas.py`:

```python
class ContributionSchema(BaseModel):
    feature: str
    value: float | None = None
    contribution: float
    text: str

class DecideOutput(BaseModel):
    action: str                        # "auto_apply" | "human_review" | "reject"
    p_hat: float | None = None         # Calibrated confidence in [0, 1]
    tau: float | None = None           # Risk-calibrated LTT threshold
    bayes_cutoff: float                # 1.0 - c_esc / c_FA (cost-optimal cutoff)
    threshold_used: float | None = None # max(tau, bayes_cutoff)
    reasons: list[str]                 # Diagnostic explanation strings
    top_contributors: list[ContributionSchema] # Top-5 feature attributions
    breaker_state: str                 # "CLOSED" | "HALF_OPEN" | "OPEN"
    model_version: str                 # e.g. "m2-v1"
    feature_spec_hash: str             # "0c099708cff3be6d30e2dadeccd7467d7fd4a452088ec81b4600994310959e50"
    alpha: float                       # Nominal error bound (0.05)
    delta: float                       # Failure probability bound (0.05)
    cost_ratio: float                  # c_FA / c_esc (20.0)

class TrustRecord(BaseModel):
    record_id: str | None = None       # Unique remediation execution ID
    timestamp: str                     # ISO 8601 UTC timestamp
    decision: DecideOutput             # Complete decision record
    context: dict[str, Any]            # Environment metadata (account, region, rule)
```

## 4. Configuration Files

Phase 7 loads operational configurations from `ml/train_m2/configs/`:

1. `ml/train_m2/configs/decision.json`:
   ```json
   {
     "alpha": 0.05,
     "delta": 0.05,
     "c_FA": 20.0,
     "c_esc": 1.0,
     "ood_missing_frac": 0.30,
     "ood_range_margin": 0.25,
     "model_path": "ml/train_m2/out/m2/m2.joblib",
     "tau_path": "ml/train_m2/out/tau_star.json",
     "model_version": "m2-v1"
   }
   ```
2. `ml/train_m2/configs/explanations.json`:
   Contains human-readable templates for feature attribution in Role C consoles without leaking private cloud identifiers.

## 5. How `tau_star.json` Governs Behavior

The contents of `ml/train_m2/out/tau_star.json` strictly control system autonomy:

- **Uncertified Status (`certified: false`):**
  - Autonomy is **OFF**.
  - `tau` is `null`.
  - `decide()` guarantees that `action` will be `"human_review"`, appending `"no certified threshold: autonomy off"`.
  - Phase 7 MUST NOT attempt to override `tau = null` with a default numerical threshold.
- **Certified Status (`certified: true`):**
  - Autonomy is **ACTIVE**.
  - `tau` contains a certified numerical cutoff (e.g. 0.950).
  - The effective threshold is `max(tau, bayes_cutoff)`.
  - Patches with `p_hat >= max(tau, bayes_cutoff)` are flagged `"auto_apply"`.

## 6. Generation Contract Phase 7 Must Respect

M2 is calibrated strictly for patches generated under the **Phase 5/6 Harvest Contract**:

- **Model Checkpoint:** `argus-m1-sft` (or specified fold adapters during cross-fit testing).
- **Format:** Patch-IR JSON (`remediate/patch_ir/schema.json`).
- **Generation Parameters (Modelfile):**
  - `presence_penalty 1.5`
  - `top_k 20`
  - `top_p 0.95`
- **Sampling:** Profile A (sample 0 greedy; samples 1-7 at `temperature 0.7` with seeds 1-7).
- Any deviation in prompt structure, temperature, or sampling frequency invalidates M2 confidence calibration and breaks the LTT selective error guarantee.

## 7. What Phase 7 Must NOT Assume

1. **Do NOT assume M2 replaces the QA gate:** M2 has zero authority over invalid or schema-violating patches. The gate must execute first.
2. **Do NOT score escalate-only patches:** Patches whose ops consist exclusively of `escalate` must route to humans without consulting M2 (`escalated_only=True`).
3. **Do NOT assume tau is constant across risk budgets:** If the business risk tolerance changes (e.g. alpha = 0.01 instead of 0.05), `tau` must be re-calibrated via `ml/train_m2/risk/calibrate_tau.py`.
4. **Do NOT assume gate-passing patches are all minimal:** Non-minimal patches (`valid_not_minimal`) pass the gate but introduce extra benign edits. M2 is trained against strict minimality (`strict_minimal_correct_v1`).
5. **Do NOT bypass the drift breaker:** If consecutive errors occur in deployment, the breaker state changes to `OPEN`, forcing all subsequent decisions to `human_review` until reset.

## 8. Integration Checklist for Roles B and C

- [ ] **Dependency Check:** Verify `requirements-phase6.txt` dependencies are installed (scikit-learn, joblib, pydantic, numpy, pandas).
- [ ] **Artifact Verification:** Check SHA256 of `ml/train_m2/out/m2/m2.joblib` and `splits.json` on startup.
- [ ] **Config Load:** Ingest `ml/train_m2/configs/decision.json` and initialize cache for explanations.
- [ ] **Gate Integration (Role B):** Ensure candidate patch runs through `ml.mutation_engine.qa.gate_stub.gate()` before invoking M2.
- [ ] **Route Filtering (Role B):** Escalate-route findings route directly to human queues without invoking M2.
- [ ] **Inference Call (Role B):** Pass extracted 35 features and `spec_hash` into `decide()`.
- [ ] **Audit Emission (Role B):** Package each output into a `TrustRecord` and log to persistent audit storage.
- [ ] **Console Display (Role C):** Render `p_hat`, `threshold_used`, action, and `top_contributors` in the operator console.
- [ ] **Certification Sentinel:** If `tau_star.json` indicates `certified: false`, ensure the UI displays "Autonomous Apply: Disabled (Awaiting Certification)" with all actions defaulting to human review.
