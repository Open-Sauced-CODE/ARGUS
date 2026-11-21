# B6 Monte-Carlo coverage of the LTT guarantee

Regimes: 4  |  Reps per regime: 2000  |  alpha=0.05  delta=0.05

## LTT coverage

Coverage = fraction of certified reps where realised selective risk <= alpha.
Target: >= 1 - delta - 0.01 = 0.94

| Regime | n_cal | true_err | certified_frac | LTT_coverage | mean_risk | max_risk |
|---|---|---|---|---|---|---|
| exchangeable_low_error | 80 | 0.02 | 0.972 | 1.000 | 0.006 | 0.02 |
| exchangeable_at_alpha | 80 | 0.05 | 0.629 | 1.000 | 0.0153 | 0.0395 |
| label_shift_adversarial | 80 | 0.02 | 0.376 | 1.000 | 0.0115 | 0.024 |
| covariate_shift_small_n | 30 | 0.08 | 0.000 | n/a (nothing certified) | nan | nan |

## v3-CRC conditional error baseline

CRC controls E[1(accepted and wrong)] <= alpha over ALL patches, NOT P(wrong|accepted).
At least one regime should show CRC conditional error > alpha by more than Monte-Carlo SE (not a failure of LTT).

| Regime | CRC_coverage | mean_cond_error | max_cond_error | MC_SE | exceeds_alpha |
|---|---|---|---|---|---|
| exchangeable_low_error | 1.000 | 0.0139 | 0.02 | 0.0097 | False |
| exchangeable_at_alpha | 0.997 | 0.0344 | 0.0503 | 0.0097 | False |
| label_shift_adversarial | 1.000 | 0.0185 | 0.0212 | 0.0097 | False |
| covariate_shift_small_n | 0.903 | 0.0271 | 0.0754 | 0.0097 | True |

**CRC exceeds alpha in regime 'covariate_shift_small_n'**: max conditional error 0.0754 exceeds alpha=0.05 by more than the Monte-Carlo standard error (SE = 0.0097, alpha + SE = 0.0597). This demonstrates that CRC's marginal joint-error control does NOT imply conditional error control.

## Notes

- Exchangeability and one-decision-per-cluster are assumed (see PROOF_NOTE.md).
- These simulations use Gaussian score models; real scores may differ.
- The n_cal=50 in production falls below rule_of_n(0.05,0.05)=59, so tau is not certified.
