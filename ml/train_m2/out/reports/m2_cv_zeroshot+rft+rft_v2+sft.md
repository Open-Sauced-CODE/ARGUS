# Grouped 5-fold CV over non-test clusters (generators: zeroshot,rft,rft_v2,sft)

rows 3172, clusters 189, negative clusters 61, skipped rows 0

## Pooled and per generator (out-of-fold M2 vs base-rate prior)

- pooled: {"auroc_model": 0.9281969186746463, "auroc_model_ci95": [0.8025220875871354, 0.9995125063054956], "auroc_prior": 0.9031960462722245, "diff": 0.02500087240242177, "diff_ci95": [-0.05206226444752137, 0.09743928385504613], "negative_clusters": 61, "evidence_ok": true, "model_beats_prior": false}
- rft: {"auroc_model": 0.509478529465205, "auroc_model_ci95": [0.20730897009966778, 1.0], "auroc_prior": 0.30086003270546907, "diff": 0.20861849675973593, "diff_ci95": [-0.024688421771664557, 0.6377460652784657], "negative_clusters": 3, "evidence_ok": false, "model_beats_prior": false, "rows": 1512}
- rft_v2: {"auroc_model": 0.9688706563706564, "auroc_model_ci95": [0.9281586270318042, 0.9943683035714286], "auroc_prior": 0.8357866795366795, "diff": 0.13308397683397688, "diff_ci95": [0.06549688057041, 0.2075457996014226], "negative_clusters": 55, "evidence_ok": true, "model_beats_prior": true, "rows": 130}
- sft: {"auroc_model": 0.9997791031588248, "auroc_model_ci95": [0.9986754966887417, 1.0], "auroc_prior": 0.2905897945659377, "diff": 0.7091893085928871, "diff_ci95": [0.5887946532146192, 0.7993675430771192], "negative_clusters": 3, "evidence_ok": false, "model_beats_prior": false, "rows": 1512}
- zeroshot: {"auroc_model": 1.0, "auroc_model_ci95": [1.0, 1.0], "auroc_prior": 0.4107142857142857, "diff": 0.5892857142857143, "diff_ci95": [0.27000000000000013, 0.9358974358974359], "negative_clusters": 4, "evidence_ok": false, "model_beats_prior": false, "rows": 18}

## (generator, rule) cells with >= 3 positive and >= 3 negative clusters

- {"cell": "rft_v2/cis.iam_no_full_admin", "positive_clusters": 7, "negative_clusters": 48, "rows": 55, "auroc": 0.6934523809523809, "ci95": [0.3680690476190477, 0.9522346153846153]}
- {"cell": "rft_v2/cis.sg_open_ingress", "positive_clusters": 16, "negative_clusters": 4, "rows": 45, "auroc": 1.0, "ci95": [1.0, 1.0]}
- {"cell": "rft/cis.iam_no_full_admin", "positive_clusters": 157, "negative_clusters": 3, "rows": 1256, "auroc": 0.4372398685651698, "ci95": [0.09499914101321545, 1.0]}
- {"cell": "rft_v2/dpdp.rule6_sg_open_ingress", "positive_clusters": 14, "negative_clusters": 3, "rows": 30, "auroc": 1.0, "ci95": [1.0, 1.0]}
- {"cell": "sft/cis.iam_no_full_admin", "positive_clusters": 157, "negative_clusters": 3, "rows": 1256, "auroc": 1.0, "ci95": [1.0, 1.0]}

## Reliability of the out-of-fold score (10 equal-mass bins)

- {"n": 318, "mean_score": 0.7707781936091845, "observed_correct": 0.789308176100629}
- {"n": 318, "mean_score": 0.9963636789433225, "observed_correct": 1.0}
- {"n": 317, "mean_score": 0.997661959609477, "observed_correct": 1.0}
- {"n": 317, "mean_score": 0.9984718783051854, "observed_correct": 1.0}
- {"n": 317, "mean_score": 0.9989055851555405, "observed_correct": 1.0}
- {"n": 317, "mean_score": 0.9993296214678293, "observed_correct": 1.0}
- {"n": 317, "mean_score": 0.999615043382301, "observed_correct": 1.0}
- {"n": 317, "mean_score": 0.9997919018497966, "observed_correct": 0.9779179810725552}
- {"n": 317, "mean_score": 0.9999444474467833, "observed_correct": 1.0}
- {"n": 317, "mean_score": 0.9999846939295507, "observed_correct": 1.0}

Brier 0.005868836770104378, log-loss 0.03522110248273726
