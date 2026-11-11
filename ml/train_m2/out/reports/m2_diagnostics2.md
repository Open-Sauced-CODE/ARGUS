# M2 vs the (generator, rule) base-rate predictor (VAL + CAL pooled; prior fitted on TRAIN only)

**M2 does NOT beat a (generator, rule) base-rate predictor: AUROC 0.886 vs 0.924 (difference -0.038, 95% CI -0.138 to +0.075). Its score is who-and-what, not draft quality.**

eval rows 1402, clusters 84, negative clusters 23

## By generator (model AUROC, prior AUROC, difference CI)

- rft: {"auroc_model": 0.4992481203007519, "auroc_model_ci95": [0.4976958525345622, 0.4992481203007519], "auroc_prior": 0.5721804511278196, "diff": -0.07293233082706768, "diff_ci95": [-0.11597984322508396, -0.03684210526315784], "negative_clusters": 1, "evidence_ok": false, "model_beats_prior": false}
- rft_v2: {"auroc_model": 0.9944444444444445, "auroc_model_ci95": [0.9743935751748252, 1.0], "auroc_prior": 0.9182539682539682, "diff": 0.07619047619047625, "diff_ci95": [0.012256112852664619, 0.15791580400276045], "negative_clusters": 21, "evidence_ok": true, "model_beats_prior": true}
- sft: {"auroc_model": 1.0, "auroc_model_ci95": [1.0, 1.0], "auroc_prior": 0.5715350223546944, "diff": 0.42846497764530556, "diff_ci95": [0.386736214605067, 0.45958845976489127], "negative_clusters": 1, "evidence_ok": false, "model_beats_prior": false}
- zeroshot: {"auroc_model": 1.0, "auroc_model_ci95": [1.0, 1.0], "auroc_prior": 0.4, "diff": 0.6, "diff_ci95": [0.09999999999999998, 1.0], "negative_clusters": 2, "evidence_ok": false, "model_beats_prior": false}

## Within (generator, rule) cells (M2); AUROC only where >= 3 positive and >= 3 negative clusters

- {"cell": "rft_v2/cis.iam_no_full_admin", "positive_clusters": 3, "negative_clusters": 20, "rows": 23, "auroc": 0.9583333333333334, "ci95": [0.85, 1.0]}
- {"cell": "rft/cis.iam_no_full_admin", "positive_clusters": 72, "negative_clusters": 1, "rows": 576, "auroc": null}
- {"cell": "rft_v2/cis.sg_open_ingress", "positive_clusters": 6, "negative_clusters": 1, "rows": 18, "auroc": null}
- {"cell": "sft/cis.iam_no_full_admin", "positive_clusters": 72, "negative_clusters": 1, "rows": 576, "auroc": null}
- {"cell": "zeroshot/cis.iam_no_full_admin", "positive_clusters": 0, "negative_clusters": 1, "rows": 1, "auroc": null}
- {"cell": "zeroshot/cis.sg_open_ingress", "positive_clusters": 2, "negative_clusters": 1, "rows": 3, "auroc": null}
- {"cell": "rft/cis.sg_open_ingress", "positive_clusters": 6, "negative_clusters": 0, "rows": 48, "auroc": null}
- {"cell": "rft/dpdp.rule6_sg_open_ingress", "positive_clusters": 6, "negative_clusters": 0, "rows": 48, "auroc": null}
- {"cell": "rft_v2/dpdp.rule6_sg_open_ingress", "positive_clusters": 5, "negative_clusters": 0, "rows": 10, "auroc": null}
- {"cell": "sft/cis.sg_open_ingress", "positive_clusters": 6, "negative_clusters": 0, "rows": 48, "auroc": null}
- {"cell": "sft/dpdp.rule6_sg_open_ingress", "positive_clusters": 6, "negative_clusters": 0, "rows": 48, "auroc": null}
- {"cell": "zeroshot/dpdp.rule6_sg_open_ingress", "positive_clusters": 2, "negative_clusters": 0, "rows": 3, "auroc": null}

## Same cells, base-rate predictor

- {"cell": "rft_v2/cis.iam_no_full_admin", "positive_clusters": 3, "negative_clusters": 20, "rows": 23, "auroc": 0.5, "ci95": [0.5, 0.5]}

## Negatives by oracle class (train+val+cal)

```
generator      oracle_class  rows  clusters
      rft             wrong    11         3
   rft_v2 valid_not_minimal     2         2
   rft_v2             wrong    54        53
      sft valid_not_minimal     1         1
      sft             wrong     2         2
 zeroshot             wrong     4         4
```
