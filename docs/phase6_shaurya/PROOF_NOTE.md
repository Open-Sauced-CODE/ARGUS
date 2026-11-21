# PROOF_NOTE.md - LTT coverage guarantee for M2

## Statement

With probability >= 1 - delta (over the draw of the calibration set), ltt_threshold returns a
threshold tau such that:

    P(oracle_class == wrong | M2 score >= tau, cluster is accepted) <= alpha

where the probability is over a fresh test cluster drawn from the SAME distribution as calibration.

## Assumptions

1. **Exchangeability.** The calibration clusters and test clusters are drawn i.i.d. from the
   same distribution (or are exchangeable). The LTT guarantee is a marginal statement over all
   possible calibration draws; it does not hold per-cluster.

2. **One decision per cluster.** The statistical unit is the cluster (input_key). Rows of the
   same cluster are NEVER treated as independent observations. The M2 score is the FIRST
   gate-passing draft's score.

3. **Pre-specified grid.** The threshold grid (GRID in ml/train_m2/risk/ltt.py) is fixed before
   any data is seen. The grid sha256 is recorded in tau_star.json and EXPERIMENT_PLAN_M2.md.

4. **Labels are the strict oracle** (oracle_class == minimal_correct). No reference-free
   (counterfactual) labels are used in LTT.

5. **Fixed-sequence testing.** ltt_threshold walks the grid from most conservative to least;
   it stops at the first tau that fails the binomial test. No multiple-comparisons correction
   is needed beyond the fixed-sequence structure.

## What is proved

The Monte-Carlo simulation (mc_guarantee.py) confirms that:
- In the exchangeable, low-error-rate regime, LTT coverage is >= 1 - delta - 0.01 = 0.94.
- In the small-n / high-error regime, LTT correctly withholds certification (tau = None).
- The v3-CRC baseline (crc_joint_threshold) does NOT control P(wrong | accepted); in at least
  one regime its conditional error exceeds alpha (see mc_guarantee.md).

## What is NOT proved

- **Distribution shift.** If the deployment distribution differs from calibration, the guarantee
  does not hold. The drift breaker (Stretch) is the first line of defence.
- **Labelling errors.** If the oracle misclassifies a cluster, tau may be too permissive.
- **Model selection.** The tau from ltt_threshold was computed on the CALIBRATION set; nothing
  from the held-out test set was used to choose tau.

## Current status (pre held-out run)

tau_star.json: certified=false (50 cal clusters < rule_of_n(0.05, 0.05) = 59).
Autonomy is OFF. The B6 Monte-Carlo harness is complete; the guarantee will be re-evaluated
after S4 is closed (OOF harvest) if the new cal set reaches >= 59 clusters.
