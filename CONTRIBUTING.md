# Contributing to ARGUS

Thank you for contributing to ARGUS! We follow a structured, collaborative engineering workflow designed to ensure code hygiene, statistical validity, and zero credential leakage.

---

## 1. Branching & Ownership Model

To prevent conflicts and regressions across parallel tracks, ARGUS enforces strict ownership boundaries:
* **Branch per track**: Always work on an isolated feature branch named after your track or task (e.g., `ml/feature-name`, `graph/ingest-fix`, `docs/polish`).
* **Never commit directly to `main`**: All changes must land via Pull Requests.
* **Track Cross-Review**: Every PR requires review and approval from at least one engineer from another track before merging.

### Ownership Guidelines
* Files under active ownership partitions (e.g., `ml/train_m2/OWNERS.json`) must strictly adhere to their assigned maintainers.
* Before opening a pull request, run the ownership verification script:
  ```bash
  python tools/check_ownership.py --who <your-handle> --base origin/main
  ```

---

## 2. Hard Engineering Rules

1. **Zero Credential or Secret Commits**:
   * Never commit `.env` files, AWS access keys (`AKIA...`), secret keys, private SSH keys (`*.pem`, `*.key`), or session tokens.
   * Verify all secrets are filtered and covered by `.gitignore`.
2. **No Large Model Weights or Data Dumps**:
   * Model weights (`.gguf`, `.safetensors`, `.bin`) and raw dataset archives (`.zip`, `.tar.gz`) belong in designated external storage, never in git history.
3. **Preserve Frozen Contracts**:
   * Never modify frozen Phase 5 schema contracts or public interfaces (`remediate/patch_ir/schema.json`, `privacy/airlock/*`, `policy/**/*.rego`) without formal architectural consensus recorded in `docs/decisions-log.md`.
4. **Reproducible Random Operations**:
   * Any randomized operation (sampling, cross-validation, synthetic mutations) must accept an explicit seed parameter (default: `1337`).

---

## 3. Local Verification & Running Tests

Before submitting a PR, verify all offline test suites pass cleanly:

```bash
# Activate virtual environment
.\.venv\Scripts\activate       # Windows PowerShell
# source .venv/bin/activate    # Linux / macOS

# Run hermetic test suites
pytest risk/tests privacy/tests ml/tests/test_contracts_doc.py -q
```

If your work touches the ML pipeline, ensure your subpackage tests pass:
```bash
pytest ml/train_m2/tests -q
```

---

## 4. Submitting a Pull Request

1. Push your branch to the origin repository:
   ```bash
   git push -u origin <your-branch>
   ```
2. Open a Pull Request using the provided PR template.
3. Complete the checklist confirming that tests pass, no secrets are committed, and documentation is updated.
