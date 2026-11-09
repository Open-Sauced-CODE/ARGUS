# M2 pre-registration (frozen before any held-out number is computed)

Target: P(a gate-passing FIX draft is strictly correct). Label: oracle_class == minimal_correct (strict); gate-pass is never
the label. Population: natural fix-route drafts that passed the gate; escalate-route inputs and escalate-only patches bypass M2.
Unit: the cluster (input_key). Decision unit: the first gate-passing draft in sample order per cluster.

Data: harvest drafts (profile A, format=schema, presence_penalty 1.5, Ollama 0.40.x) of the deployment generator (SFT) and,
for training only, the other generators. Corruptor and weak counterfactual labels are not used in this version.
Splits: cluster-level, seed 1337; every input in B1, B2, C_verifier, gold or C_human is test-only; A_val-only inputs
(unseen by SFT) go to cal first; the rest 60/20/20 per rule family. splits.json carries a sha256 that every later step checks.
Model selection: logistic vs LightGBM (monotone, num_leaves <= 15) and calibrator (isotonic, Platt, Beta, Venn-Abers) by
VAL log-loss then ECE only. Nothing uses test or cal for any choice.
Risk control: Learn-then-Test fixed sequence (risk/ltt.py, unchanged), alpha = delta = 0.05, one decision per cluster, CAL only.
If fewer than 59 CAL clusters exist, tau is not certified and autonomy stays OFF; no silent fallback.
Primary metrics (cluster bootstrap CIs): AUROC, ECE, Brier, and selective risk and coverage at the certified tau.
Run rule: held-out sets are scored only through eval/run_once.py, once per (model, set); repeats need a written reason.

Known limitations, stated in advance: the SFT calibration pool is small and the SFT generator was trained on the held-out inputs,
so held-out SFT numbers are not generalisation estimates unless out-of-fold SFT drafts are used; reference-free labels are weak and
unused; the guarantee is scoped to inputs exchangeable with the calibration clusters. Any deviation is appended to
docs/decisions-log.md with a reason before the affected number is computed.
