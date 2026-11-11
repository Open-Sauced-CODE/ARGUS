# Grouped 5-fold CV over non-test clusters (generators: rft_v2)

rows 130, clusters 84, negative clusters 55, skipped rows 0

## Pooled and per generator (out-of-fold M2 vs base-rate prior)

- pooled: {"auroc_model": 0.9939671814671814, "auroc_model_ci95": [0.9825027826995593, 1.0], "auroc_prior": 0.836269305019305, "diff": 0.15769787644787647, "diff_ci95": [0.09258889099406344, 0.23304725589796124], "negative_clusters": 55, "evidence_ok": true, "model_beats_prior": true}
- rft_v2: {"auroc_model": 0.9939671814671814, "auroc_model_ci95": [0.9825027826995593, 1.0], "auroc_prior": 0.836269305019305, "diff": 0.15769787644787647, "diff_ci95": [0.09258889099406344, 0.23304725589796124], "negative_clusters": 55, "evidence_ok": true, "model_beats_prior": true, "rows": 130}

## (generator, rule) cells with >= 3 positive and >= 3 negative clusters

- {"cell": "rft_v2/cis.iam_no_full_admin", "positive_clusters": 7, "negative_clusters": 48, "rows": 55, "auroc": 0.9583333333333334, "ci95": [0.8876946428571428, 1.0]}
- {"cell": "rft_v2/cis.sg_open_ingress", "positive_clusters": 16, "negative_clusters": 4, "rows": 45, "auroc": 1.0, "ci95": [1.0, 1.0]}
- {"cell": "rft_v2/dpdp.rule6_sg_open_ingress", "positive_clusters": 14, "negative_clusters": 3, "rows": 30, "auroc": 1.0, "ci95": [1.0, 1.0]}

## Reliability of the out-of-fold score (10 equal-mass bins)

- {"n": 13, "mean_score": 0.0042622360493974895, "observed_correct": 0.0}
- {"n": 13, "mean_score": 0.015036561698198796, "observed_correct": 0.0}
- {"n": 13, "mean_score": 0.03150874063705788, "observed_correct": 0.0}
- {"n": 13, "mean_score": 0.08599357242894429, "observed_correct": 0.07692307692307693}
- {"n": 13, "mean_score": 0.5663796070894492, "observed_correct": 0.6153846153846154}
- {"n": 13, "mean_score": 0.950567651985624, "observed_correct": 1.0}
- {"n": 13, "mean_score": 0.9756473189800694, "observed_correct": 1.0}
- {"n": 13, "mean_score": 0.990489597702648, "observed_correct": 1.0}
- {"n": 13, "mean_score": 0.9975548254955933, "observed_correct": 1.0}
- {"n": 13, "mean_score": 0.9992383560653236, "observed_correct": 1.0}

Brier 0.032657649090777785, log-loss 0.11305553820126958
