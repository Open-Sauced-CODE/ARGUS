## Summary of Changes

A concise description of what this pull request introduces or resolves.

### Stage / Component
- [ ] Graph Ingestion (`graph/`)
- [ ] Risk Engine & PageRank (`risk/`)
- [ ] Decision & Interdiction (`prioritize/`)
- [ ] Privacy Airlock (`privacy/`)
- [ ] Remediation & Patch-IR (`remediate/`)
- [ ] Policy & DPDP Rego Rules (`policy/`)
- [ ] ML Training & M2 Confidence (`ml/`)
- [ ] Documentation / CI / Tooling (`docs/`, `.github/`, `tools/`)

---

## Pre-Merge Checklist

Please verify and check the following before requesting review:

- [ ] **Tests Pass**: Ran `pytest risk/tests privacy/tests ml/tests/test_contracts_doc.py -q` and all existing tests pass locally.
- [ ] **No Secrets or Credentials**: Verified no `.env`, AWS access keys (`AKIA...`), private keys (`*.pem`), or credentials are committed.
- [ ] **No Large Assets / Weights**: Confirmed no `.gguf`, `.safetensors`, `.bin`, or large archives are included in this PR.
- [ ] **Preserved Frozen Contracts**: Frozen schemas (`patch_ir/schema.json`, `privacy/airlock/*`) remain intact or diff is logged.
- [ ] **Documentation Updated**: README, architecture docs, or inline docstrings updated if applicable.
- [ ] **Deterministic Seed**: Any random operations or tests use an explicit seed (`1337`).
- [ ] **Ownership Verified**: Passed `python tools/check_ownership.py --who <handle> --base origin/main` (if modifying ML paths).
