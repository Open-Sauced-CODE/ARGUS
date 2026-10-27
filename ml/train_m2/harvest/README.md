# ml/train_m2/harvest (Prabhav's track, Phase 6)

Generates M1 candidates with token log-probabilities for the M2 trust engine. Contract: `ml/train_m2/contract/CONTRACT_HARVEST.md`.

| File | Purpose |
|---|---|
| `machine_check.py` | 1-minute check of Ollama version, models, logprobs, parallel requests, disk |
| `client.py` | `chat_once_v2` (one generation with logprobs), `ollama_meta` |
| `profiles.py` | profile A and B sampling parameters, exactly as the contract |
| `schema.py` | validates every line against `harvest_line.schema.json` before it is written |
| `store.py` | append-only part files, resume, rotation, tail repair, manifests |
| `run.py` | the CLI: `python -m ml.train_m2.harvest.run --help` |
| `pilot.py` | the H1 pilot: throughput, replication, diversity, profile B check, report |
| `tests/` | `python -m pytest ml/train_m2/harvest/tests -q` (fake Ollama, no GPU needed) |

Resume rule: if a run stops for any reason, run the same command again. After an Ollama problem add `--retry-errors`.
