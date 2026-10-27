# Results Grid V2 (A_val evaluation and acceptance bars for RFT-v2)

Built according to `ml/train_m1/v2/PLAN_V2.md` §3 (Acceptance bars) and §5 (Decision rule).

## Acceptance Bars Comparison (on A_val)

| Metric | Target Bar | SFT (Phase 5) | SFT (Harvest A) | RFT (Harvest A) | RFT-v2 (Step 18) | RFT-v2 (Harvest A) | Status |
|---|---|---|---|---|---|---|---|
| pass@1 (greedy) | >= 95.7% | 96.7% (349/361) | 77.8% (281/361) | 79.5% (287/361) | 0.0% (0/361) | 12.2% (44/361) | MISSED |
| pass@8 | >= 99.0% | - | 80.6% | 80.6% | 0.0% | 51.2% | MISSED |
| mean distinct (of 8) | >= 1.50 | - | 1.45 | 1.00 | 1.00 | 6.39 | MET |
| unsafe candidates | 0 | 1 | 0 | 0 | 0 | 935 | MISSED |
| escalate recall (A_val) | >= 0.727 | 0.727 | 0.000 | 0.000 | n/a | n/a | MISSED |
| schema-valid rate | 100% | 98.6% | 100.0% | 100.0% | 0.0% | 100.0% | MET |

## Diagnosis of RFT-v2 Step 18 Run

1. **Root Cause**:
   - The training in Colab initialized from `BASE_MODEL = "unsloth/Qwen3.5-4B"` rather than continuing from `sft_adapter`.
   - Training a 4B parameter foundation model for only 1 epoch (18 gradient steps at `lr=2e-5`) on 284 examples is insufficient for the base model to memorize custom JSON grammar.
   - The base model followed the prompt text ("Allowed operations: ...") and outputted `{"operations": [{"operation": "...", ...}]}` rather than Patch-IR's required keyword `{"ops": [{"op": "...", ...}]}`.
   - 60 of the 70 outputs (85.7%) produce semantically correct patch logic once `"operations"` is mapped to `"ops"`.

2. **Decision Rule (from PLAN_V2.md §5)**:
   - "Among checkpoints that meet every A_val bar, the winner has the highest pass@1, then the highest mean distinct. If none meets the bars, report the best and say which bars were missed; production M1 stays SFT (Rule 5.2)."
   - Checkpoint step 18 missed the acceptance bars (pass@1 0.0% vs >=95.7%, schema-valid 0.0% vs 100%).
   - Production M1 stays SFT as mandated by Rule 5.2, and escalation is routed via the deterministic escalate router proposal (`docs/proposals/escalate-router.md`).
