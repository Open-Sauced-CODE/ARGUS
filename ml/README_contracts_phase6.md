# Phase 6 contracts (shared file)

The interface between the two Phase 6 tracks is the harvest format, defined in `ml/train_m2/contract/`:

- `CONTRACT_HARVEST.md`: the rules (canonical)
- `harvest_line.schema.json`: machine check for one line
- `harvest_fixture.jsonl`: a valid example
- `harvest_inputs.jsonl`: the 321 inputs to generate for

File ownership is in `ml/train_m2/OWNERS.json`; the guard is `python tools/check_ownership.py --who <name>`.

Interfaces that Phase 7 will call (`confidence`, `decide`, `tau_star.json`) are added below by Shaurya when they are frozen.
The Phase 5 contract file (`ml/README_contracts.md`) is never edited in Phase 6.
