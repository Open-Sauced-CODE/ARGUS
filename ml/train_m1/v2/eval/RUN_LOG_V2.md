# Run log V2 (one line per scored (model, set) pair for RFT-v2 / Phase 6)

| date | label | set | examples | file sha256 | pass@1 | schema-valid | note |
|---|---|---|---:|---|---|---|---|
| 2026-10-27 | sft-phase5 | A_val | 361 | f68c3ef9447e17c0 | 96.7% (349/361) | 100.0% | reproduction verification matched 349/361 |
| 2026-10-27 | sft | A_val | 361 | 549ce63737ec3a0c | 77.8% (281/361) | 100.0% | harvest profile A evaluation |
| 2026-10-27 | rft | A_val | 361 | e93d7c570b20757a | 79.5% (287/361) | 100.0% | harvest profile A evaluation |
| 2026-10-27 | rft_v2_step18 | A_val | 361 | 62e5e1fe8a19f4c0 | 0.0% (0/361) | 0.0% | Recipe (a) 1-epoch checkpoint; unconstrained decoding schema failure |
| 2026-10-27 | rft_v2 | A_val | 361 | 5e0041318efb90b3 | 12.2% (44/361) | 100.0% | full harvest profile A (2,568 lines), pass@8 51.2%, mean distinct 6.39 |
