# Harvest validation report

Inputs expected: 321; allow-partial: False; require-manifests: False

## Summary

| generator | profile | lines | coverage | errors | collapse share | verdict |
|---|---|---|---|---|---|---|
| rft | A | 2568 | 100.0% | 0 | 97.2% | PASS |
| rft_v2 | A | 2568 | 100.0% | 0 | 0.0% | WARN |
| sft | A | 2568 | 100.0% | 0 | 60.4% | PASS |
| zeroshot | A | 2568 | 100.0% | 0 | 0.0% | PASS |

## rft / profile A

| check | status | detail |
|---|---|---|
| SCHEMA | PASS | all 2568 lines valid |
| FOLDER_FIELDS | PASS | generator and profile match the folder |
| DUPLICATES | PASS | no duplicate (input_key, sample_idx) |
| KEYS | PASS | all input_keys are known |
| COMPLETENESS | PASS | all 2568 (input, sample) pairs present |
| TEXT_EQ_TOKENS | PASS | tokens spell the content on all 2568 successful lines |
| PROFILE | PASS | all lines follow profile A |
| LOGPROB | PASS | no line has mean logprob below -5 |
| ERRORS | PASS | error-line rate 0.00% |
| VERSIONS | PASS | ollama_version ['0.40.11'], model_digest ['sha256:02e86d0a0b5e35052997c8f4396a8c1e752d1fda7c58abbbccd111e8ea74d53e'] |
| MANIFEST | PASS | 6 part(s): sha256 and line counts match |
| REPLICATION | INFO | 1430/1448 = 98.8% of lines equal the Phase 5 text; by sample index: {0: '179/181', 1: '178/181', 2: '179/181', 3: '179/181', 4: '179/181', 5: '179/181', 6: '179/181', 7: '178/181'} (information only; seeded samples may differ across Ollama versions) |

## rft_v2 / profile A

| check | status | detail |
|---|---|---|
| SCHEMA | PASS | all 2568 lines valid |
| FOLDER_FIELDS | PASS | generator and profile match the folder |
| DUPLICATES | PASS | no duplicate (input_key, sample_idx) |
| KEYS | PASS | all input_keys are known |
| COMPLETENESS | PASS | all 2568 (input, sample) pairs present |
| TEXT_EQ_TOKENS | WARN | 1 of 2568 lines (0.04%) where the tokens do not spell the content (byte-level tokenizer pieces can legitimately differ; above 0.5 percent fails) |
| PROFILE | PASS | all lines follow profile A |
| LOGPROB | PASS | no line has mean logprob below -5 |
| ERRORS | PASS | error-line rate 0.00% |
| VERSIONS | PASS | ollama_version ['0.40.11'], model_digest ['sha256:ddf8f8491255d0db7da445f9d43077f3ba12e62bd9bddcb208ac0a27f044e888'] |
| MANIFEST | PASS | 6 part(s): sha256 and line counts match |
| REPLICATION | INFO | not applicable (only profile A of zeroshot, sft and rft has Phase 5 logs to compare with) |

First examples for TEXT_EQ_TOKENS:
- `part-0001.jsonl:376`

## sft / profile A

| check | status | detail |
|---|---|---|
| SCHEMA | PASS | all 2568 lines valid |
| FOLDER_FIELDS | PASS | generator and profile match the folder |
| DUPLICATES | PASS | no duplicate (input_key, sample_idx) |
| KEYS | PASS | all input_keys are known |
| COMPLETENESS | PASS | all 2568 (input, sample) pairs present |
| TEXT_EQ_TOKENS | PASS | tokens spell the content on all 2568 successful lines |
| PROFILE | PASS | all lines follow profile A |
| LOGPROB | PASS | no line has mean logprob below -5 |
| ERRORS | PASS | error-line rate 0.00% |
| VERSIONS | PASS | ollama_version ['0.40.11'], model_digest ['sha256:ded5fad28aadecc0b2bcdaac695ce47472f8808d1d2f1b6dc66ffe575405aed7'] |
| MANIFEST | PASS | 6 part(s): sha256 and line counts match |
| REPLICATION | INFO | 1320/1440 = 91.7% of lines equal the Phase 5 text; by sample index: {0: '165/180', 1: '165/180', 2: '165/180', 3: '165/180', 4: '165/180', 5: '165/180', 6: '165/180', 7: '165/180'} (information only; seeded samples may differ across Ollama versions) |

## zeroshot / profile A

| check | status | detail |
|---|---|---|
| SCHEMA | PASS | all 2568 lines valid |
| FOLDER_FIELDS | PASS | generator and profile match the folder |
| DUPLICATES | PASS | no duplicate (input_key, sample_idx) |
| KEYS | PASS | all input_keys are known |
| COMPLETENESS | PASS | all 2568 (input, sample) pairs present |
| TEXT_EQ_TOKENS | PASS | tokens spell the content on all 2568 successful lines |
| PROFILE | PASS | all lines follow profile A |
| LOGPROB | PASS | no line has mean logprob below -5 |
| ERRORS | PASS | error-line rate 0.00% |
| VERSIONS | PASS | ollama_version ['0.40.11'], model_digest ['sha256:d8b0f5e9760cd1682034f292d7ef72ec46f432149be0df7574bf2d6e92e38c04'] |
| MANIFEST | PASS | 6 part(s): sha256 and line counts match |
| REPLICATION | INFO | 1310/1448 = 90.5% of lines equal the Phase 5 text; by sample index: {0: '163/181', 1: '165/181', 2: '163/181', 3: '163/181', 4: '163/181', 5: '164/181', 6: '166/181', 7: '163/181'} (information only; seeded samples may differ across Ollama versions) |

## Verdict

ACCEPTED
