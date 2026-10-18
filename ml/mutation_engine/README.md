# Mutation engine (Phase 5)

Takes a clean base resource and breaks it exactly the way a Rego rule checks for. The un-mutated resource is the
reference: the fix is the declared inverse of the mutation, so there is no manual labeling.

## Layout

| Path | What it is |
|---|---|
| `bases/` | Tier A bases. `bases.jsonl` + `manifest.csv` from Step 4; `bases_synthetic.jsonl` + `manifest_synthetic.csv` from `synth_bases`. See `bases/README.md`. |
| `model.py` | `Resource`, `Mutation`, `apply_patch`, `diff_attrs` |
| `mutators/` | The 12 mutators named in `ml/README_contracts.md` (43 variants). One module per resource family. |
| `compose.py` | 1 to 4 violations per resource, with conflict rules (no shared attribute, no shared rule) |
| `decoys.py` | Perturbs only attributes no rule reads |
| `labeler.py` | Diff + declared inverse -> schema-valid Patch-IR |
| `project.py` | Thin wrapper over the Phase 4 airlock (`run_airlock`); the model input is exactly its output |
| `examples.py` | Builds the examples of one base: one per rule that fires |
| `synth_bases.py` | Documented synthetic bases: completed S3 buckets and account fixtures (contracts D4, D9) |
| `coverage.py` | Rule coverage report |
| `phase1_skeleton/` | The Phase 1 skeleton (text-replacing mutators, `fixtures/`, its test). Kept for history; superseded by `mutators/`. |

## Commands (from the repo root)

    python -m ml.mutation_engine.synth_bases       # write the synthetic bases
    python -m ml.mutation_engine.coverage          # every rule has a mutator? how many bases per mutator and bucket?
    python -m pytest ml/tests/test_mutation_engine.py -v
    python -m pytest ml/mutation_engine/phase1_skeleton/test_mutators.py -v

Do not add an `__init__.py` to `phase1_skeleton/`: its test imports `mutators` as a top-level module.
