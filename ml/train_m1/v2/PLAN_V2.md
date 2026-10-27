# RFT-v2 plan (H4) - STOP: needs human approval before any training run

Owner: Prabhav (Role C). Approver: Shaurya. Status: DRAFT until the approval block at the bottom is filled.

## 1. Goal
Produce `argus-m1-rft-v2`: SFT-level fix accuracy, RFT-level escalation on real code, and real sampling diversity.
Existing adapters and GGUFs (`argus-m1-sft`, `argus-m1-rft`) are never touched.

## 2. Diagnosis (measured, Phase 5 files)
- RFT-v1 trained on SFT's 8 samples (T=0.7) for the 230 train inputs. 229 of 230 inputs had exactly ONE distinct answer, so RFT-v1
  saw the same pair eight times: a second epoch at lr 1e-4 with no new information. Final loss 0.000544 = memorisation.
- Effect: mean distinct answers out of 8 is 1.00-1.06 on every set, so best-of-N is useless; pass@1 on A_val fell to 79.5% (SFT 96.7%,
  349/361) and on B1 to 61.7% (SFT 96.2%). Re-measured on the harvest: rft diversity 1.00, sft 1.45, zero-shot 7.05 (pilot report).
- RFT-v1's real gain: it escalates real RDS findings (51/51 on C_verifier, 9/9 on gold) with 0.00% unsafe output. SFT escalates none
  (it attempts a fix on all 51). On C_verifier SFT fixes 414 of 415 fix cases, RFT about 365.
- Train has only 230 distinct inputs and the ESC rules have very few (the RDS rule has 2 distinct train inputs), so "learning to escalate"
  rests on almost no input variety. Escalation numbers per set and rule: `python -m ml.train_m1.v2.escalate_stats`
  (writes docs/proposals/escalate-stats.md). Per-rule A_val pass@1, SFT vs RFT:
  `python -m ml.train_m1.v2.eval_v2 --harvest ml\train_m2\harvest_out\sft\A --label sft` and the same with `rft`
  (writes ml/train_m1/v2/eval/<label>_A_val.md). Paste both tables into section 2 of the final report.

## 3. Acceptance bars (fixed BEFORE the first training run)
On A_val, per checkpoint (the only set used to choose a checkpoint):

| Metric | Bar |
|---|---|
| pass@1 (greedy, frozen scorer) | >= 95.7% (within 1 point of SFT's 96.7%) |
| pass@8 | >= 99.0% |
| mean distinct canonical answers of 8 | >= 1.5 |
| unsafe candidates | 0 |
| escalate recall (A_val) | >= 0.727 (SFT's value) |
| schema-valid rate | 100% (constrained decoding) |

Then, ONCE each, for the single chosen checkpoint, on B1, B2, C_verifier and gold under the RUN_LOG protocol (D6: each (model, set) pair is
scored once): C_verifier escalate recall >= 0.90 and C_verifier overall pass@1 >= 95%. Report every bar as met or missed, including misses.

## 4. Data (ml/train_m1/v2/data/, git-ignored)
Built by `python -m ml.train_m1.v2.build_v2_data` (deterministic, seed 20261029):
1. Pool: SFT profile B and zero-shot profile A harvest lines, only for inputs that have a TRAIN example. A candidate is kept only if the
   Phase 5 GATE accepts it with the outcome that matches the rule's route ('fixed' for T0/M1, 'escalated' for ESC). Hidden checks are never used.
2. Deduplicate by canonical answer (ops + rationale_ref); at most 4 distinct answers per input; the SFT reference is always included.
3. Mix: about 50% original SFT pairs (replay) and 50% diverse verified candidates.
4. Escalation variety: `--extra-dir` (a second dataset built with another seed) adds ESC examples only when their INPUT is new.
   The airlock projects only the fields a rule reads, so ESC inputs are nearly identical by construction; the build reports how many new
   ESC inputs were really added. If the answer is zero, that finding itself supports the escalate-router proposal.
5. Leak guard: the build aborts if any row's full_hash is in held_out_hashes.txt or heldout_hashes.txt; a test checks the real output.
   Never used: C_verifier, gold, B1, B2 content. Caveat (decision D10): identical projected inputs occur in train and in other sets, so
   C_verifier escalation partly measures inputs the model has seen; the router proposal addresses this.

## 5. Recipes (one at a time, compared on A_val only)
(a) REPLAY MIX: data above; Colab QLoRA via Unsloth; lr 2e-5; LoRA r 16 (then r 8); 1 epoch; evaluate on A_val every 50 steps;
    save the adapter to Drive every 50 steps; keep the checkpoint with the best A_val (the Phase 5 stop rule).
(b) PREFERENCE OPTIMISATION: pairs (chosen = gate-passing candidate, rejected = gate-failing candidate for the same input), DPO or ORPO,
    beta 0.1, lr 5e-6 to 1e-5, starting from the SFT adapter. First check that the installed Unsloth/TRL supports the trainer.
(c) combine (a) data with (b) only if both help.
Decision rule: among checkpoints that meet every A_val bar, the winner has the highest pass@1, then the highest mean distinct. If none meets
the bars, report the best and say which bars were missed; production M1 stays SFT (Rule 5.2).

## 6. Evaluation order
1. Reproduce SFT's A_val 349/361 with `eval_v2 --candidates <Phase 5 SFT A_val log> --expect-pass1 349 --expect-n 361` (proves the wrapper).
2. For each checkpoint: export Q4_K_M GGUF, register in Ollama, harvest profile A on all 321 inputs, run `eval_v2 --harvest ... --label <name>`.
3. Pick the winner on A_val. 4. Run B1, B2, C_verifier, gold once each. 5. Harvest `rft_v2` profiles A and B for Shaurya.

## 7. Outputs
ml/train_m1/v2/: data scripts, notebooks/03_rft_v2.ipynb, serve/Modelfile.argus-m1-rft-v2, eval/RUN_LOG_V2.md, eval/results_grid_v2.md.
GGUF on Drive argus/m2_harvest/models/ with its sha256; model registered as argus-m1-rft-v2.

## 8. Risks
Small data (a few thousand rows at most) so overfitting is possible: eval every 50 steps and stop at the best A_val. A_val is reused for
checkpoint choice, so the held-out sets stay untouched until the single final run. Colab session limits: checkpoint to Drive every 50 steps.

## Approval
Approved by: ____________  Date: ____________   Changes requested: ____________
