# M2 diagnostics (TRAIN/VAL/CAL only)

**CONFOUNDED: a model that sees only the generator reaches AUROC 0.910 against 1.000 for the full model, so the pooled score mostly identifies the generator. Within sft: AUROC 1.000 (95% CI 1.000-1.000) on 1 negative cluster(s).**

## Prevalence

```
partition generator  rows  clusters  negatives  error_rate
      cal       rft   400        50          7    0.017500
      cal    rft_v2    27        18         12    0.444444
      cal       sft   400        50          0    0.000000
      cal  zeroshot     4         3          2    0.500000
    train       rft   840       105          4    0.004762
    train    rft_v2    79        50         35    0.443038
    train       sft   840       105          2    0.002381
    train  zeroshot    11         9          2    0.181818
      val       rft   272        34          0    0.000000
      val    rft_v2    24        16          9    0.375000
      val       sft   272        34          1    0.003676
      val  zeroshot     3         3          0    0.000000
```

## Negative clusters by generator and rule (train+val+cal)

```
generator                    rule_id  negative_clusters
      rft      cis.iam_no_full_admin                  3
   rft_v2      cis.iam_no_full_admin                 48
   rft_v2        cis.sg_open_ingress                  4
   rft_v2 dpdp.rule6_sg_open_ingress                  3
      sft      cis.iam_no_full_admin                  3
 zeroshot      cis.iam_no_full_admin                  1
 zeroshot        cis.sg_open_ingress                  2
 zeroshot dpdp.rule6_sg_open_ingress                  1
```

## Ablation (val)

- full: AUROC 0.9996, log-loss 0.0072, features 35
- no_generator: AUROC 0.9996, log-loss 0.0072, features 30
- no_consensus: AUROC 0.9957, log-loss 0.0158, features 29
- no_logprob: AUROC 0.9998, log-loss 0.0045, features 26
- structure_and_rule_only: AUROC 0.9988, log-loss 0.0152, features 20

## Within-generator val AUROC

- rft: {"auroc": null, "n": 272, "n_negative_clusters": 0, "note": "single class"}
- rft_v2: {"auroc": 0.9925925925925926, "ci95": [0.9614074074074074, 1.0], "n": 24, "n_negative_clusters": 9}
- sft: {"auroc": 1.0, "ci95": [1.0, 1.0], "n": 272, "n_negative_clusters": 1}
- zeroshot: {"auroc": null, "n": 3, "n_negative_clusters": 0, "note": "single class"}

## Calibration on CAL (calibrator fitted on VAL)

- overall: {"n": 831, "negatives": 21, "ece": 0.01145484824551501, "brier": 0.010648712995421729}
- rft: {"n": 400, "negatives": 7, "ece": 0.02000000000000001, "mean_score": 0.9975, "observed_correct": 0.9825}
- rft_v2: {"n": 27, "negatives": 12, "ece": 0.05625847748233218, "mean_score": 0.4992970780732234, "observed_correct": 0.5555555555555556}
- sft: {"n": 400, "negatives": 0, "ece": 0.0, "mean_score": 1.0, "observed_correct": 1.0}
- zeroshot: {"n": 4, "negatives": 2, "ece": 0.0, "mean_score": 0.5, "observed_correct": 0.5}

## Top single-feature AUROC (train)

- seq_logprob: 0.990
- lp_mean: 0.989
- entropy_mean: 0.988
- agreement_rate: 0.988
- modal_share: 0.987
- cluster_entropy_norm: 0.987
- n_distinct_patches: 0.986
- lp_std: 0.985
- lp_min: 0.975
- top1_top2_margin_mean: 0.946
