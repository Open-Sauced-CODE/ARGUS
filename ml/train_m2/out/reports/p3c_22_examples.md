# A_val: per-key (Phase 5 protocol) vs per-example (finding_id aligned)

- phase5: examples 361, per-key weighted pass 243, per-example aligned pass 317, differing examples 74
- harvest: examples 361, per-key weighted pass 243, per-example aligned pass 317, differing examples 74

## Differing examples (phase5 candidates)

| key | rule | finding_id | first finding_id | per-key | per-example | route | record fields differ | reference differs |
|---|---|---|---|---|---|---|---|---|
| c9d93b2e | dpdp.rule6_public_exposure | F-2 | F-2 | False | True | fix | - | False |
| c9d93b2e | dpdp.rule6_public_exposure | F-2 | F-2 | False | True | fix | - | False |
| c9d93b2e | dpdp.rule6_public_exposure | F-1 | F-2 | False | True | fix | - | True |
| c9d93b2e | dpdp.rule6_public_exposure | F-1 | F-2 | False | True | fix | - | True |
| c9d93b2e | dpdp.rule6_public_exposure | F-2 | F-2 | False | True | fix | - | False |
| c9d93b2e | dpdp.rule6_public_exposure | F-1 | F-2 | False | True | fix | - | True |
| c9d93b2e | dpdp.rule6_public_exposure | F-2 | F-2 | False | True | fix | - | False |
| c9d93b2e | dpdp.rule6_public_exposure | F-1 | F-2 | False | True | fix | - | True |
| c9d93b2e | dpdp.rule6_public_exposure | F-2 | F-2 | False | True | fix | - | False |
| c9d93b2e | dpdp.rule6_public_exposure | F-1 | F-2 | False | True | fix | - | True |
| f2abcb0d | dpdp.rule6_logging | F-1 | F-1 | False | True | fix | - | False |
| f2abcb0d | dpdp.rule6_logging | F-0 | F-1 | False | True | fix | - | True |
| f2abcb0d | dpdp.rule6_logging | F-0 | F-1 | False | True | fix | - | True |
| f2abcb0d | dpdp.rule6_logging | F-0 | F-1 | False | True | fix | - | True |
| f2abcb0d | dpdp.rule6_logging | F-0 | F-1 | False | True | fix | - | True |
| f2abcb0d | dpdp.rule6_logging | F-0 | F-1 | False | True | fix | - | True |
| f2abcb0d | dpdp.rule6_logging | F-0 | F-1 | False | True | fix | - | True |
| f2abcb0d | dpdp.rule6_logging | F-0 | F-1 | False | True | fix | - | True |
| f2abcb0d | dpdp.rule6_logging | F-0 | F-1 | False | True | fix | - | True |
| f2abcb0d | dpdp.rule6_logging | F-1 | F-1 | False | True | fix | - | False |
| 2446b0e3 | cis.s3_public_access_block | F-1 | F-1 | False | True | fix | - | False |
| 2446b0e3 | cis.s3_public_access_block | F-1 | F-1 | False | True | fix | - | False |
| 2446b0e3 | cis.s3_public_access_block | F-1 | F-1 | False | True | fix | - | False |
| 2446b0e3 | cis.s3_public_access_block | F-0 | F-1 | False | True | fix | - | True |
| 2446b0e3 | cis.s3_public_access_block | F-0 | F-1 | False | True | fix | - | True |
| 2446b0e3 | cis.s3_public_access_block | F-0 | F-1 | False | True | fix | - | True |
| 2446b0e3 | cis.s3_public_access_block | F-0 | F-1 | False | True | fix | - | True |
| 2446b0e3 | cis.s3_public_access_block | F-0 | F-1 | False | True | fix | - | True |
| bf5568b8 | dpdp.rule6a | F-0 | F-0 | False | True | fix | - | False |
| bf5568b8 | dpdp.rule6a | F-0 | F-0 | False | True | fix | - | False |
| bf5568b8 | dpdp.rule6a | F-0 | F-0 | False | True | fix | - | False |
| bf5568b8 | dpdp.rule6a | F-1 | F-0 | False | True | fix | - | True |
| bf5568b8 | dpdp.rule6a | F-0 | F-0 | False | True | fix | - | False |
| bf5568b8 | dpdp.rule6a | F-0 | F-0 | False | True | fix | - | False |
| bf5568b8 | dpdp.rule6a | F-0 | F-0 | False | True | fix | - | False |
| bf5568b8 | dpdp.rule6a | F-0 | F-0 | False | True | fix | - | False |
| bf5568b8 | dpdp.rule6a | F-0 | F-0 | False | True | fix | - | False |
| bf5568b8 | dpdp.rule6a | F-0 | F-0 | False | True | fix | - | False |
| 0483fc81 | dpdp.rule6_public_exposure | F-2 | F-2 | False | True | fix | - | False |
| 0483fc81 | dpdp.rule6_public_exposure | F-1 | F-2 | False | True | fix | - | True |
| 0483fc81 | dpdp.rule6_public_exposure | F-1 | F-2 | False | True | fix | - | True |
| 0483fc81 | dpdp.rule6_public_exposure | F-2 | F-2 | False | True | fix | - | False |
| 0483fc81 | dpdp.rule6_public_exposure | F-2 | F-2 | False | True | fix | - | False |
| 0483fc81 | dpdp.rule6_public_exposure | F-1 | F-2 | False | True | fix | - | True |
| 0483fc81 | dpdp.rule6_public_exposure | F-2 | F-2 | False | True | fix | - | False |
| 0483fc81 | dpdp.rule6_public_exposure | F-1 | F-2 | False | True | fix | - | True |
| c3ff1836 | dpdp.rule6a | F-3 | F-3 | False | True | fix | - | False |
| c3ff1836 | dpdp.rule6a | F-3 | F-3 | False | True | fix | - | False |
| c3ff1836 | dpdp.rule6a | F-2 | F-3 | False | True | fix | - | True |
| c3ff1836 | dpdp.rule6a | F-3 | F-3 | False | True | fix | - | False |
| 1d97b23a | dpdp.rule6_public_exposure | F-1 | F-1 | False | True | fix | - | False |
| 1d97b23a | dpdp.rule6_public_exposure | F-1 | F-1 | False | True | fix | - | False |
| 1d97b23a | dpdp.rule6_public_exposure | F-1 | F-1 | False | True | fix | - | False |
| 1d97b23a | dpdp.rule6_public_exposure | F-1 | F-1 | False | True | fix | - | False |
| 1d97b23a | dpdp.rule6_public_exposure | F-1 | F-1 | False | True | fix | - | False |
| 1d97b23a | dpdp.rule6_public_exposure | F-1 | F-1 | False | True | fix | - | False |
| 1d97b23a | dpdp.rule6_public_exposure | F-1 | F-1 | False | True | fix | - | False |
| 1d97b23a | dpdp.rule6_public_exposure | F-1 | F-1 | False | True | fix | - | False |
| f4c41079 | dpdp.rule6_logging | F-1 | F-1 | False | True | fix | - | False |
| f4c41079 | dpdp.rule6_logging | F-0 | F-1 | False | True | fix | - | True |
| f4c41079 | dpdp.rule6_logging | F-0 | F-1 | False | True | fix | - | True |
| f4c41079 | dpdp.rule6_logging | F-0 | F-1 | False | True | fix | - | True |
| f4c41079 | dpdp.rule6_logging | F-1 | F-1 | False | True | fix | - | False |
| f4c41079 | dpdp.rule6_logging | F-0 | F-1 | False | True | fix | - | True |
| f4c41079 | dpdp.rule6_logging | F-0 | F-1 | False | True | fix | - | True |
| f4c41079 | dpdp.rule6_logging | F-1 | F-1 | False | True | fix | - | False |
| f4c41079 | dpdp.rule6_logging | F-0 | F-1 | False | True | fix | - | True |
| f4c41079 | dpdp.rule6_logging | F-0 | F-1 | False | True | fix | - | True |
| 26f67ee6 | dpdp.rule6a | F-3 | F-3 | False | True | fix | - | False |
| 26f67ee6 | dpdp.rule6a | F-3 | F-3 | False | True | fix | - | False |
| 26f67ee6 | dpdp.rule6a | F-3 | F-3 | False | True | fix | - | False |
| 26f67ee6 | dpdp.rule6a | F-1 | F-3 | False | True | fix | - | True |
| 26f67ee6 | dpdp.rule6a | F-1 | F-3 | False | True | fix | - | True |
| 26f67ee6 | dpdp.rule6a | F-3 | F-3 | False | True | fix | - | False |

cause counts among differing examples: {'neither': 41, 'reference': 33}
