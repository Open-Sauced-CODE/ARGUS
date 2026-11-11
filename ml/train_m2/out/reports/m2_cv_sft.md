# Grouped 5-fold CV over non-test clusters (generators: sft)

rows 1512, clusters 189, negative clusters 3, skipped rows 0

## Pooled and per generator (out-of-fold M2 vs base-rate prior)

- pooled: {"auroc_model": 1.0, "auroc_model_ci95": [1.0, 1.0], "auroc_prior": 0.2905897945659377, "diff": 0.7094102054340623, "diff_ci95": [0.5901199465461807, 0.7993675430771192], "negative_clusters": 3, "evidence_ok": false, "model_beats_prior": false}
- sft: {"auroc_model": 1.0, "auroc_model_ci95": [1.0, 1.0], "auroc_prior": 0.2905897945659377, "diff": 0.7094102054340623, "diff_ci95": [0.5901199465461807, 0.7993675430771192], "negative_clusters": 3, "evidence_ok": false, "model_beats_prior": false, "rows": 1512}

## (generator, rule) cells with >= 3 positive and >= 3 negative clusters

- {"cell": "sft/cis.iam_no_full_admin", "positive_clusters": 157, "negative_clusters": 3, "rows": 1256, "auroc": 1.0, "ci95": [1.0, 1.0]}

## Reliability of the out-of-fold score (10 equal-mass bins)

- {"n": 152, "mean_score": 0.9804710824830882, "observed_correct": 0.9802631578947368}
- {"n": 152, "mean_score": 0.9999424335450311, "observed_correct": 1.0}
- {"n": 151, "mean_score": 0.9999552981999223, "observed_correct": 1.0}
- {"n": 151, "mean_score": 0.9999618052831457, "observed_correct": 1.0}
- {"n": 151, "mean_score": 0.9999659835590852, "observed_correct": 1.0}
- {"n": 151, "mean_score": 0.9999711154035387, "observed_correct": 1.0}
- {"n": 151, "mean_score": 0.9999756886153225, "observed_correct": 1.0}
- {"n": 151, "mean_score": 0.999978557788671, "observed_correct": 1.0}
- {"n": 151, "mean_score": 0.9999822055340577, "observed_correct": 1.0}
- {"n": 151, "mean_score": 0.999990643832537, "observed_correct": 1.0}

Brier 5.418762209316489e-06, log-loss 0.00015021356594308299
