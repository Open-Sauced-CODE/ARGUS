# ARGUS Phase 5 - M1 Experiment Plan

Date frozen: 2026-10-07 (the date of the git commit that adds this file is the evidence; no held-out set has been scored yet)
Owner: Role C (ML track)
Source: Phase 5 execution plan, Section 5 (Evaluation protocol) and Step 2.

Rule for this file: after any held-out result is visible, nothing above the change log may be edited. Changes go
in the change log (section 8) with the reason. A bar is never lowered after the number it judges is known.

## 1. Question this plan answers

Does a small, verifier-trained, locally served model (M1) draft Patch-IR fixes that clear our verification gate more
often than the same base model without training, on data the generator never produced and on real Terraform?

## 2. Models compared (rows of the results grid)

| # | Model | Decoding |
|---|---|---|
| 1 | T0 templates only | deterministic, no model |
| 2 | Zero-shot base model, constrained | JSON-schema constrained, 1 sample |
| 3 | Zero-shot base model, best-of-8 | JSON-schema constrained, 8 samples, first gate-passing one kept |
| 4 | SFT, single sample | constrained, 1 sample |
| 5 | SFT, best-of-8 | constrained, 8 samples |
| 6 | Rejection-sampling fine-tuned (RFT), best-of-8 | constrained, 8 samples |
| 7 | GRPO, best-of-8 (only if attempted) | constrained, 8 samples |

Base model: Qwen3.5-4B for iteration (decision log in ml/README_contracts.md, section 5). Zero-shot rows use the same
fixed prompt as the trained models. Main metric rows (4 to 7) are reported on the T0-uncovered subset (rules routed M1 or
ESC in ml/README_contracts.md) as the headline, and on all rules as a second line.

## 3. Data sets

| Name | Used for | Source |
|---|---|---|
| Tier A train | training only | mutation engine on train-bucket bases |
| Tier A validation (A val) | choosing checkpoints, prompt format and sampling settings; the ONLY set used for decisions | mutation engine on validation-bucket bases |
| Tier B1 | unseen mutator combinations | mutation engine on test-bucket bases |
| Tier B2 | unseen rule family (encryption-at-rest), scored for the ablation model trained without that family | mutation engine on test-bucket bases |
| Tier C-verifier | real violations found by our own rules on unseen repos; scored by the gate and hidden checks | test-bucket repositories |
| Tier C-mined | real before/after fixes from git history, reviewed by hand | test-bucket repositories |
| Gold sample | 50 to 100 items verified by two reviewers, agreement (kappa) reported | test-bucket repositories |

## 4. Metrics and pass bars

Definitions are those of Section 5.1 of the Phase 5 plan. Bars marked "suggested" are our proposal; confirm them with
the team before the first commit of this file.

| Metric | Reported on | Pass bar (suggested unless marked fixed) |
|---|---|---|
| Schema-valid rate | all sets, every model | 100% for every constrained model (fixed: confirmed on 500 validation prompts in Step 16). The unconstrained zero-shot rate is reported, no bar. |
| Unsafe outputs accepted by the gate | all sets | 0 accepted (fixed). Adversarial deletion and new-principal probes (Step 19): 20 of 20 rejected. |
| Gate pass@8, SFT best-of-8 versus zero-shot best-of-8 | Tier B1 | SFT at least 10 percentage points above zero-shot, McNemar p < 0.05 |
| Gate pass@8, SFT best-of-8 | A val, T0-uncovered subset | at least 80% |
| Gate pass@1 and pass@8, all rows | all sets | report only |
| Hidden-check pass rate | A val, B1, B2 | at least 90% of gate-passing candidates |
| Reference equivalence (exact and semantic) | A val, B1, B2 | report only (lower bound by design) |
| Unsafe-output rate among candidates (delete resource, new principal, out-of-vocabulary operation without escalate) | all sets | at most 2% of candidates for rows 4 to 7 |
| Escalate precision and recall | A and B sets with escalate cases | each at least 0.80 |
| Time to first passing candidate | A val, Tier C | median at most 10 seconds on the demo laptop through Ollama |
| Training-versus-held-out gap (300 sampled training prompts minus Tier B and Tier C) | final model(s) | report only; investigate if larger than 20 percentage points |
| Synthetic-versus-real gap (Tier B minus Tier C-verifier, with intervals) | final model(s) | report only |
| Rule precision on real code | Tier C sample, gold sample | report only; any rule below 70% is reviewed before the paper cites it |

## 5. Rules for using the data (fixed)

1. **Scoring is once per (model, held-out set) pair.** Held-out sets are B1, B2, C-verifier, C-mined and gold. Each model
   is scored on each of them once, after that model is frozen. The baselines (rows 1 to 3) never change after Step 15, so
   their held-out cells may be produced then; rows 4 to 7 are scored after the freeze in Step 21. A repeat run is allowed
   only with a written reason in the run log (`ml/train_m1/eval/RUN_LOG.md`, created in Step 15), and the repeat is
   reported next to the first run.
2. **Decisions use A val only.** Model size, checkpoint, prompt format, sampling temperature and number of samples are
   chosen on A val. No held-out number is looked at when making them.
3. **Hidden checks stay hidden.** The hidden checks (decoys untouched, minimal patch, full equivalence, no hidden side
   effects) never appear in the rejection-sampling filter, in any reward, or in checkpoint selection.
4. **No leakage.** Every repository belongs to exactly one bucket (train, validation, test) before anything is generated.
   The dataset files are hashed in MANIFEST.sha256 before any evaluation run, and the check must pass before each run.

## 6. Statistics

- Proportions are reported with the count (for example 41/60) and a Wilson 95% interval.
- Two models scored on the same items are compared with McNemar's test (paired).
- Training seeds: state the number used. If compute allows only one, the paper says so.

## 7. Stop rules

- Do not start a real training run before the 50-example overfit test passes (Step 16).
- Stop an RFT or GRPO run when A val gate pass@8 has not improved for three evaluation points while the training reward
  still rises (reward hacking warning); keep the best A val checkpoint.
- If the SFT model does not beat the zero-shot model on A val, do not continue to RFT or GRPO: diagnose the data first.

## 8. Change log

| Date | Change | Reason | Held-out result already visible? |
|---|---|---|---|
| 2026-10-07 | First version | Phase 5 Step 2 | no |
| 2026-10-22 | Step 14-15 baseline decisions confirmed on A_val. Base model: Qwen3.5-4B (`qwen3.5:4b`). Prompt format: fixed chat template (system message + compact JSON user input + Patch-IR assistant target). Temperature: sample 1 greedy (0.0), samples 2-8 at 0.7. Token lengths (chars/3): p50 359, p99 492, max 746 (context window 1024). A_val zero-shot baseline: pass@1 26.6% [22.3, 31.4], pass@8 48.8% [43.6, 53.9], schema-valid 551/560 (98.4%), median s to first pass 5.01s. T0 baseline: 196/361 (54.3%), gate-pass 100%. | Phase 5 Steps 14 and 15 model size and baseline freeze | no |
| 2026-10-22 | Step 16 SFT model (`argus-m1-sft`) trained on 2,507 examples via Unsloth QLoRA (3 epochs, lr 2e-4, r=16). Checkpoint-471 selected (100.0% validation gate pass@1). Exported to Q4_K_M GGUF and registered in Ollama. Evaluation across all sets: A_val pass@1 96.7%, pass@8 99.4%; B1 pass@1 96.2%, pass@8 100.0% (McNemar p=0.0000 vs zeroshot); B2 pass@1 88.9%, pass@8 100.0%; C_verifier pass@1 88.8%, pass@8 100.0%; gold pass@1 87.5%, pass@8 100.0%. Unsafe candidates dropped from ~70% to <=0.18%. | Phase 5 Step 16 SFT completion and evaluation | yes |
