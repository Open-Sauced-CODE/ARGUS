# ARGUS Phase 5: Dataset Construction and M1 Training
*Execution plan, step-by-step procedure, evaluation protocol and final checklist*

| Item | Detail |
|---|---|
| Phase | Phase 5: ML Track, Part 1, Dataset Generation and Training M1 (Local Remediation Model) |
| Weeks | Weeks 8–12 (Phase 6 starts in Week 11 and depends on this phase) |
| Owner | Role C, with a second reviewer from the team for the gold sample |
| Depends on | Phase 1 (mutation-engine skeleton, graph/schema.md); Phase 4 (Patch-IR, Rego libraries, airlock projection, verification gate) |
| Feeds | Phase 6 (M2 and conformal threshold), Phase 7 (tiered pipeline), Phase 10 (evaluation), the research paper |
| Companion documents | ARGUS v3 solution design (Sections 9.2, 9.5, 9.6, 11) and the Master Execution Guide v3 |
| Prepared | 6 October 2026 |

**Contents**

- 1. Purpose of this document
- 2. The data decision
- 3. Dataset specification
- 4. Step-by-step procedure
- 5. Evaluation protocol
- 6. Timeline for Weeks 8–12
- 7. Risks and how to handle them
- 8. Using Phase 5 in the research paper
- 9. Integration checkpoint
- 10. Final checklist
- Appendix A: Command cheat sheet
- Appendix B: Code skeletons
- Appendix C: Decisions to settle with the team this week


## 1. Purpose of this document

The Master Execution Guide gives Phase 5 twelve steps. They tell the team what to build, but they leave open the question that decides whether the ML track holds up in a research paper: **where does the training and test data come from, and why should a reviewer trust it?** This plan answers that question and then walks the team through the whole phase, step by step, with the commands, files, checks and exit criteria needed to run it without guessing.

It does three things. It records the data-source decision we reached (a mutation engine for training data, real open-source Terraform for testing). It turns that decision into a day-by-day procedure that fits Weeks 8–12. And it ends with a single checklist that extends the Master Guide's Phase 5 checklist, so nothing agreed here is lost when the phase is signed off.

> **How to read the priority tags**
>
> **[Must]** is required for Phase 6 and Phase 7 to work. **[Should]** is expected and goes into the paper, but the project survives without it. **[Stretch]** is attempted only if the Should items are finished, and can be deferred with a written reason. Everything marked as a "suggested" number or setting is our proposal, not a requirement from the ARGUS v3 design document; change it if the first runs show a better value, but write the change down.


## 2. The data decision


### 2.1 Is there a ready-made labelled dataset we can use instead?

Short answer: no single public dataset matches what M1 has to learn, but several real datasets are useful for other parts of the phase. The table lists what exists as of our search, how it fits, and what we do with it. Figures are as reported by each source; confirm the licence and the download link before relying on any of them.

| Source | What it contains | Fit for ARGUS | Planned use |
|---|---|---|---|
| **TerraDS** | About 67,000 open-source Terraform repositories (permissive licences only), 279,344 modules, 1,773,991 resources, roughly 335 MB. No security labels. | Best source of realistic Terraform. Unlabelled, so it supplies inputs, not answers. | Base configs for training data (Tier A) and unseen real repos for testing (Tier C). |
| **Reyes et al. (WISP 2025)** | 6,149 Terraform scripts, 27,557 misconfigurations found by Trivy, 23,906 corrected code blocks used for LoRA fine-tuning of small models. | Closest prior work to M1. Fixes are free-form code and labels come from Trivy, not from DPDP rules. | Cite as related work. Email the authors to ask whether the data is released. |
| **Mengistu (2025 thesis)** | 67,602 Terraform files labelled by tfsec and Terrascan for 60 AWS violation types, plus a 522-file human-verified gold set. | Detection labels only. No fixes. | Check availability. Possible cross-check for Tier C labels. |
| **IEEE DataPort set** | 600 LLM-generated Terraform files with Checkov and tfsec findings. | Small, and the configs are model-written. Scanner labels in one study had about 82% precision on a hand-checked sample. | Optional extra Tier C material if access is easy. |
| **Security Verifiers (E2)** | Gated. Only metadata is public. | Needs an access request. | Not planned. |
| **TerraGoat / CloudGoat** | Intentionally vulnerable, labelled scenarios. | Already in the plan from Phase 1. | Testbed for Phase 10 and a few base configs. Keep any config reused in the Phase 10 testbed out of training. |

**Why no public dataset replaces ours.** Four reasons, and each one is worth a sentence in the paper.

- M1's output is **Patch-IR**, our own closed operation vocabulary. No public set has (finding → Patch-IR) pairs.
- The correctness oracle is **our Rego libraries**, because the verification gate is what decides whether a patch is accepted. Labels from another tool will disagree with our own gate on edge cases, and the model would learn the wrong target.
- **DPDP Rule 6/7/8/15 checks do not exist** in any public dataset. These are the part of ARGUS no one else has.
- Scanner-generated labels are noisy. Training on them would inherit that noise, and we could not tell it apart from model error.


### 2.2 Will a reviewer accept synthetic training data?

Yes, when the data comes from a deterministic generator with a verifiable label, the model is tested on data the generator never produced, and the paper reports the gap between the two honestly. The mutation engine in our design is exactly that kind of generator. A program takes a compliant configuration and breaks it the way one specific rule checks for; the original configuration is the correct answer by construction. No language model writes any training example, and no paid API is called.

| What reviewers accept | What gets papers rejected |
|---|---|
| Synthetic training data with labels that are correct by construction | Training and testing on output from the same generator, which is circular |
| A released generator and a dataset card, so the data can be rebuilt | No evidence the model works on real-world Terraform |
| Held-out real-world evaluation, with the synthetic-versus-real gap reported | Unchecked labels, or train/test leakage through shared repositories |
| Honest statements of scope (AWS Terraform, the rules we built) | Claiming the model generalises to every cloud or every rule |


### 2.3 The three-tier design

Data is split into three tiers with different jobs. Only Tier A ever reaches the training loop.

| Tier | Source | Purpose | Label comes from |
|---|---|---|---|
| **A** | Mutation engine applied to real, compliant base configs from the training bucket of TerraDS, terraform-aws-modules and similar | Train M1 (SFT, rejection sampling, GRPO). A small validation slice picks checkpoints. | The un-mutated original is the reference fix. |
| **B** | Mutation engine again, but on repos from the test bucket, using unseen mutator combinations and one entire rule family left out of an ablation model | Shows generalisation beyond the templates the model saw. B1 tests unseen combinations; B2 tests an unseen rule family. | Same as Tier A. |
| **C** | Natural misconfigurations found in real repositories the model never saw, plus real human fixes mined from git history | Shows the model works on real Terraform, not only on our own generator. This tier makes the paper credible. | C-verifier: the Phase 4 gate is the oracle. C-mined: the real commit is the reference, reviewed by hand. |

Two rules keep the tiers honest. First, every base config belongs to exactly one repository, and every repository is assigned to exactly one bucket (train, validation or test) before anything is generated, so a near-duplicate module cannot leak across the split. Second, the evaluation sets are scored once, after every design choice is frozen, and any re-run is logged.


## 3. Dataset specification


### 3.1 What one example looks like

Each line of the JSONL files is one example. The input is the record the model will actually receive at runtime (the airlock-projected finding), the target is the reference Patch-IR, and the metadata block exists for analysis and leakage checks only; it is never shown to the model. The attribute names below follow the Patch-IR example in the v3 design document. **Use the field names that Phase 4's projection function and graph/schema.md really produce**, not the ones in this illustration.

```
{
  "id": "ex-000123",
  "tier": "A",
  "input": {
    "finding_id": "F-0472",
    "rule_id": "dpdp.rule6a",
    "resource_ref": "BUCKET_3",
    "resource_type": "aws_s3_bucket",
    "attributes": { "server_side_encryption_enabled": false, "versioning_enabled": true }
  },
  "target": {
    "finding_id": "F-0472",
    "resource_ref": "BUCKET_3",
    "ops": [
      { "op": "set_attr", "attr": "server_side_encryption_enabled", "value": true },
      { "op": "set_attr", "attr": "sse_algorithm", "value": "aws:kms" }
    ],
    "rationale_ref": "dpdp.rule6a"
  },
  "meta": {
    "base_id": "tfaws-s3/example-1", "repo_bucket": "train",
    "mutators": ["m_dpdp6a_sse_off"], "decoys": ["tags", "force_destroy"],
    "n_violations": 1, "seed": 1337
  }
}
```


### 3.2 How the reference Patch-IR is produced

The labelling function is a diff. For each rule-relevant attribute that differs between the mutated config and the original, the labeler emits the operation that restores it: a changed scalar becomes **set_attr**, a feature toggle becomes **enable_feature**, an added policy statement becomes **remove_policy_statement**, a widened CIDR becomes **restrict_cidr**, and so on through the vocabulary. The mutator that made the change already knows which operation undoes it, so the labeler never has to guess.

- **Identifiers stay tokenised.** If the restored value is an ARN or other identifier, both the input and the target carry the airlock token (for example KEY_1), never the real value. Rehydration happens after generation, locally.
- **Include some escalate examples [Should].** A suggested 3–5% of examples are findings whose correct answer is `escalate` with a reason, because the fix needs an operation outside the vocabulary. A concrete case: turning on storage encryption for an existing RDS instance cannot be done in place and normally means a snapshot copy and restore, which Patch-IR deliberately cannot express. Without these examples the model learns to improvise instead of escalating.
- **One finding can have several valid fixes** (for example SSE-S3 versus KMS). The reference is whatever the original config used, so exact match with the reference is a lower bound. The headline metric is therefore gate pass, with reference-equivalence reported alongside.
- **Drop, don't force.** If the diff cannot be expressed in the vocabulary and the example was not meant to be an escalate case, log it and drop it. The count of dropped examples per rule is a useful diagnostic for the mutators.


### 3.3 Train/serve consistency

The dataset input must be produced by the **same projection code** the airlock uses at runtime, called from the dataset builder. If the training inputs are formatted differently from what the deployed model sees, accuracy measured on the test set will not carry over to the demo. This is the most common silent failure in this kind of pipeline, so it has its own check in the QA gates (Step 8).


### 3.4 Suggested sizes and composition

The Master Guide asks for "at least a few thousand" examples. These targets are our proposal; scale them down evenly if base configs or compute run short, but keep the proportions.

| Set | Suggested size | Notes |
|---|---|---|
| Tier A train | 4,000–6,000 | At least 100 examples for every mutator. Roughly 60% single-violation, 30% two violations, 10% three or four. 3–5% escalate cases. |
| Tier A validation | 400–600 | From validation-bucket repos. Used only to choose checkpoints and settings. |
| Tier B1 (unseen combinations) | 300–500 | Mutator combinations that never appear in train. Test-bucket repos. |
| Tier B2 (unseen rule family) | 200–300 | One whole rule family excluded from an ablation model trained for this test only. |
| Tier C-verifier | As many as the scan yields, report the count | Real violations found by running our rules on unseen repos. No reference patch; scored by the gate and the hidden checks. |
| Tier C-mined | Expect tens, not hundreds | Real before/after fixes from git history. Report the funnel at each filter. |
| Gold sample | 50–100 | Hand-verified by two reviewers, with agreement reported. |


### 3.5 Repository layout

```
ml/
├── mutation_engine/
│   ├── bases/               # compliant bases + manifest.csv
│   ├── mutators/            # one file per rule family; declares inverse ops
│   ├── compose.py           # multi-violation composition and conflict rules
│   ├── decoys.py            # rule-irrelevant perturbations
│   ├── labeler.py           # diff(mutated, original) -> Patch-IR
│   ├── project.py           # thin wrapper over the Phase 4 airlock projection
│   ├── qa/                  # round-trip, fires/clears, gate, dedupe, leakage
│   ├── build_dataset.py     # seeded; writes MANIFEST.sha256
│   ├── dataset/             # train.jsonl, val.jsonl
│   └── held_out/            # tierB1, tierB2, tierC_verifier, tierC_mined, gold
├── real_data/               # filter_terrads, scan_repos, mine_history, funnel_report
└── train_m1/                # 01_sft, 02_rft, 03_grpo notebooks; eval/; DATASET_CARD.md
```


## 4. Step-by-step procedure

The steps are grouped into five stages and numbered continuously. Do them in order within a stage. Stages B and C can run in parallel once Step 4 is done, and Stage C is the only stage that can be handed to a second person without slowing the critical path. Each step lists what to do, the file or result it must produce, and the check that tells you it is finished.


### Stage A: Prepare (Week 8)


#### Step 1: Freeze the contracts the dataset depends on `[Must]`

**What to do**

- Open the Patch-IR schema, the airlock projection function, the Rego rule list and the gate function from Phase 4. Write down their exact names and versions in `ml/README_contracts.md`.
- List every rule ID and group the rules into families (for example encryption at rest, versioning and retention, network exposure, IAM scope, logging and alerting). Mark which rules T0 will cover as a single-attribute fix and which will reach M1.
- Decide which one family is held out for Tier B2. Choose a family large enough to give 200 or more examples, and write the choice down now, before any results exist.

**Produces:** `ml/README_contracts.md` with schema version, function signatures, rule-to-family table, T0-versus-M1 split, and the held-out family.

**Done when:** Anyone on the team can name the mutator for any rule ID without opening code.


#### Step 2: Write the acceptance bars and the experiment plan before generating anything `[Must]`

**What to do**

- Copy the metric list from Section 5 into `ml/train_m1/EXPERIMENT_PLAN.md` and fix, in writing, what result would count as a pass for each. Suggested starting bars: 100% schema-valid output under constrained decoding; 0% accepted patches that delete a resource or add a new principal; SFT best-of-8 gate pass rate clearly above the zero-shot best-of-8 rate on Tier B.
- Commit the file. Changes after test results are visible must be logged as changes, not silently made.

**Produces:** A committed plan with named bars, dated before the first test-set run.

**Done when:** The plan names the models compared, the test sets, the metrics, and the one-time rule for scoring test sets.


#### Step 3: Remove the two biggest unknowns early `[Must]`

**What to do**

- Run Unsloth's example notebook unmodified on its toy dataset in Colab or Kaggle (this is Master Guide step 5, moved to the start). Note the session limit and the GPU you actually receive.
- Pull any small model into Ollama and call it with the Patch-IR JSON Schema through the structured-outputs option. Confirm a deliberately bad prompt still returns schema-valid JSON.
- Install the HCL parser you will use (python-hcl2 is the usual choice; read its README for what it can and cannot write back) and parse three real Terraform files into dictionaries.

**Produces:** A short `ml/real_data/SETUP_NOTES.md` recording GPU type, session limit, Ollama version, parser behaviour.

**Done when:** All three tools run end to end on toy input. If any one fails, fix it now; this is the cheapest week to find out.


### Stage B: Build the synthetic dataset (Weeks 8–9)


#### Step 4: Build the base-config corpus and assign repositories to buckets `[Must]`

**What to do**

- Download TerraDS and read its documentation for the schema and the licence information. Filter to repositories that contain the AWS resource types your rules touch (for example S3 buckets, IAM policies, security groups, RDS, CloudTrail and logging resources).
- Parse each resource into a dictionary. Resolve a variable only when it has a plain default; if the rule-relevant attribute stays unresolved, skip that resource and count the skip.
- Assign every repository to a bucket by hashing the repository name: for example hash mod 100, with 0–69 train, 70–79 validation, 80–99 test. Record the bucket in `manifest.csv` with repo, commit SHA, file path and licence.
- Run the Phase 4 Rego rules over the parsed resources. Keep as Tier A bases only the resources with **zero violations**. Resources that already violate a rule are not wasted: those in test-bucket repos feed Tier C.
- Add terraform-aws-modules examples and any CloudGoat/TerraGoat scenario that is not reserved for the Phase 10 testbed.
- Remove near-duplicates by hashing each resource block after stripping names, tags and comments.

**Produces:** `bases/` with a manifest; a counts table by resource type and bucket.

**Done when:** No repository appears in two buckets. Every Tier A base passes all rules. A resource used in the Phase 10 testbed appears in no training bucket.


#### Step 5: Expand the mutators: one per checkable rule `[Must]`

**What to do**

- For each rule in both Rego libraries, write one mutator that breaks a compliant resource exactly the way that rule checks for, and that declares the Patch-IR operation which undoes it. A skeleton is in Appendix B.
- For each mutator write three tests: **fires/clears** (the target rule fires on the mutated config and is silent on the original), **round trip** (applying the reference patch to the mutated config reproduces the original), and **determinism** (the same seed gives the same output).
- Where a rule can be broken in more than one way (for example a security group opened by 0.0.0.0/0 or by a very wide range), write each way as a separate variant of the mutator, so the model sees the range of real violations.
- **[Should]** Weight the variants by how often each violation pattern shows up in the real scan. Use only train-bucket repositories to estimate those frequencies, so no test-bucket information shapes the training data.
- **[Should]** If the Phase 4 finding record can carry an unresolved reference (a value that comes from a variable or a local), add variants where the broken value is reached through that reference. If it cannot, record that as a stated limitation instead of faking it.

**Produces:** `mutators/` covering every rule, with passing tests.

**Done when:** A coverage script lists every rule ID with the number of mutator variants. No rule shows zero.


#### Step 6: Compose mutators and add decoys `[Must]`

**What to do**

- Write `compose.py` to apply two to four mutators to one resource. Add conflict rules: two mutators must not edit the same attribute, and combinations that make the resource meaningless are skipped.
- Write `decoys.py`: randomise tags, reorder attributes, change unrelated numeric values, add unrelated attributes. Decoys must never touch an attribute any rule reads.
- Assert the decoy rule automatically: after decoys are applied, the set of rules that fire must be unchanged.

**Produces:** Composition and decoy modules with tests.

**Done when:** Running every rule on 200 random decorated configs gives exactly the violations the mutators declared, no more, no fewer.


#### Step 7: Write the labeler and connect the airlock projection `[Must]`

**What to do**

- Implement `labeler.py`: diff the mutated and original configs and emit Patch-IR using each mutator's declared inverse. Validate every output against the schema.
- In `project.py`, call the Phase 4 projection function to build the model input from the mutated config. Do not reimplement it.
- Add the escalate cases (Section 3.2): choose two or three findings whose fix is outside the vocabulary, write mutators for them, and set the target to `escalate` with a reason.

**Produces:** A labeler producing schema-valid Patch-IR for every mutator; projection wired in.

**Done when:** Feeding a dataset input through the deployed airlock code path gives byte-identical output to what the dataset stores.


#### Step 8: Run the QA gates; the build fails if any one fails `[Must]`

**What to do**

- Write `qa/run_all.py` to run these eight checks on every example (skeleton in Appendix B):
- **Check 1:** the target rule fires on the mutated config.
- **Check 2:** the original config is clean under all rules.
- **Check 3:** applying the reference patch to the mutated config reproduces the original (round trip).
- **Check 4:** the reference patch passes the verification gate (policy checks, risk re-score, intent preservation, no new principal).
- **Check 5:** the target validates against the Patch-IR schema.
- **Check 6:** decoys left every rule-relevant attribute alone.
- **Check 7:** no real identifier appears in any input (use the Phase 4 leak-check).
- **Check 8:** no example in train, validation or any held-out file shares a normalised hash with another split.
- Hand-inspect 50 random examples. Read the input, read the target, and ask whether a security engineer would agree.
- Produce a distribution report: examples per rule, operations per patch, violations per config, token-length histogram.

**Produces:** `qa/report.md` with counts, failures (should be zero) and the distribution tables.

**Done when:** All eight automatic checks pass on 100% of examples. If check 4 fails, the problem is a mutator or a rule, not the example; fix it at the source.


#### Step 9: Generate, split and freeze dataset v1 `[Must]`

**What to do**

- Run `build_dataset.py` with a fixed seed and write the files to `dataset/` and `held_out/` (Tier B1 and B2 only at this point).
- Write `MANIFEST.sha256` with a hash for every file, and tag the repository `dataset-v1`.
- Write `DATASET_CARD.md`: sources and licences, bucket rule, generator version, counts, known gaps, and what the data must not be used for.
- Add a guard to every training notebook: load the held-out hashes and stop with an error if any appears in the training data.

**Produces:** Frozen dataset v1, manifest, dataset card, tag.

**Done when:** Rebuilding from the same seed gives identical hashes.


### Stage C: Build the real-data test set (Weeks 9–10, in parallel with Stage B)


#### Step 10: Select and clone the Tier C repositories `[Must]`

**What to do**

- From the **test bucket only**, choose repositories that contain the resource types your rules cover. Prefer repositories that are actively maintained and have a licence file.
- Clone each one and record the commit SHA in `real_data/tierC_repos.csv` along with the licence. Keep the clone depth full for the ones you will mine for history.

**Produces:** `tierC_repos.csv` and a local clone folder (do not commit the clones).

**Done when:** None of these repositories appears in Tier A training bases.


#### Step 11: Harvest real violations with the verifier (Tier C-verifier) `[Must]`

**What to do**

- Write `scan_repos.py` to parse every file, adapt the result to the input shape your Rego libraries expect (check the policy README for that shape), run the rules and write each violation to a record with repo, file, resource and rule.
- Cross-check with Trivy and Checkov on the same repositories and record, per rule, how often they agree. Disagreements are not errors to hide; they are a result worth a table row.
- Hand-label a random sample of the findings as true violation or not. This gives a precision figure for our own rules on real code, which is a free extra result for the paper.
- Write the findings, projected through the airlock, to `tierC_verifier.jsonl`. These records have no reference patch; they are scored by the gate and the hidden checks (Section 5).

**Produces:** `tierC_verifier.jsonl`, the per-rule agreement table, and the precision estimate.

**Done when:** Every record passes the leak-check and none came from a train or validation repository.


#### Step 12: Mine real fixes from git history (Tier C-mined) `[Should]`

**What to do**

- For each cloned repository, list commits that touched a `.tf` file. For every changed resource, evaluate the rules on the version before and the version after the commit.
- Keep a commit only if the resource violated a rule before, passes that rule after, and still exists (no deletion).
- Convert the diff to Patch-IR with the same labeler used in Step 7. If it cannot be expressed in the vocabulary, count it as out-of-vocabulary and set it aside.
- Read every surviving pair by hand and keep it only if the human fix is a reasonable answer to the finding.
- Write down the **funnel**: repositories scanned, commits touching resources, violating-before and passing-after, in-vocabulary, reviewed and kept. The size of each drop is informative and goes in the paper.

**Produces:** `tierC_mined.jsonl` and `real_data/funnel_report.md`.

**Done when:** Each kept pair has been read by a person. Even a few dozen reviewed pairs are worth more than hundreds of unchecked ones.


#### Step 13: Build the gold sample and measure reviewer agreement `[Should]`

**What to do**

- Take 50–100 items from Tier C (mixed verifier and mined) and have two reviewers judge each one independently: is the finding real, and is the reference or mined fix acceptable.
- Compute Cohen's kappa between the two reviewers and settle disagreements by discussion. Store the settled labels in `gold.jsonl`.

**Produces:** `gold.jsonl` and the agreement figure.

**Done when:** Both reviewers labelled before seeing each other's answers. Where the team size allows, the second reviewer is someone who did not write the mutators for those rules (for example Role D, who owns the DPDP mapping).


### Stage D: Train and serve M1 (Weeks 10–12)


#### Step 14: Format the data and prove the pipeline can learn `[Must]`

**What to do**

- Convert each example to the base model's chat template: a fixed system message, the input record as the user turn, the target Patch-IR (compact JSON) as the assistant turn. Compute loss on the assistant turn only.
- Check token lengths against the model's context window and set the maximum sequence length from the length histogram, not by guessing.
- Run a 50-example overfit test: train until loss is near zero and confirm the model reproduces those 50 targets. If it cannot, the formatting or template is wrong; stop and fix it before any real run.

**Produces:** A formatted dataset and a passing overfit test.

**Done when:** The overfit run reproduces 50 of 50 targets exactly.


#### Step 15: Run the baselines before any fine-tuning `[Must]`

**What to do**

- Evaluate on Tier A validation and Tier B: T0 alone, the base model zero-shot with constrained decoding, and the base model best-of-8 with the gate as verifier. This is the bake-off from the design document (Section 9.6), and the best-of-8 row is the "Option 2" ablation to keep in the paper whichever approach wins.
- Pick the model size for the main runs. A 4B model is a sensible size to iterate on; move to a larger one only if the baselines show headroom and the free GPU allows it.

**Produces:** A baseline table in `train_m1/eval/baselines.md`.

**Done when:** Every baseline row is filled for validation and Tier B, and test-bucket sets were scored once only (Tier C waits for Step 21).


#### Step 16: Supervised fine-tuning (the mandatory rung) `[Must]`

**What to do**

- Open `01_sft.ipynb` from Unsloth's example, substitute the dataset, and use QLoRA. Suggested starting values, to be checked against the notebook's current defaults: LoRA rank 16, learning rate near 2e-4, one to three epochs, effective batch size set by gradient accumulation, maximum sequence length from Step 14.
- Save the adapter to Google Drive (or a Kaggle output) at every checkpoint so a dropped session costs minutes, not hours.
- After each epoch, score gate pass@1 on Tier A validation. Choose the checkpoint on validation only.
- Export to GGUF at a 4-bit quantisation, write a Modelfile whose first line points at the file, and register it with Ollama. Call the API with the Patch-IR schema in the format field.
- Confirm that every output on 500 validation prompts is schema-valid before measuring correctness.

**Produces:** Adapter weights, the GGUF file (or an external link), the Modelfile, and the SFT row in the results table.

**Done when:** 100% schema-valid outputs through Ollama; validation pass@1 and pass@8 recorded.


#### Step 17: Rejection-sampling fine-tuning `[Should]`

**What to do**

- For every training prompt, sample 8 candidates from the SFT model. Keep a candidate only if it passes gate checks (a) to (d). Do not use the hidden checks to filter; they are reserved for evaluation.
- Remove duplicate candidates, and keep the original reference examples in the mix so the model does not drift away from the labelled data.
- Fine-tune again from the SFT adapter on the filtered set and evaluate exactly as in Step 16.

**Produces:** RFT adapter and its row in the results table.

**Done when:** The filtered set size and the per-rule pass rates are recorded; any rule with very few surviving candidates is flagged for the paper's limitations.


#### Step 18: GRPO round, or a written deferral `[Stretch]`

**What to do**

- Attempt this only if Step 17 is finished by the end of Week 11. Use the gate's pass/fail plus a scaled risk-delta term as the reward, following the recipe the design document cites, and cite it as an existing method, not our contribution.
- Keep the hidden checks out of the reward. Stop the run if validation pass rate stalls while the training reward keeps climbing; that pattern is the first sign of reward hacking.
- If time runs out, write a short deferral note stating the reason. The Phase 5 checklist accepts either outcome.

**Produces:** A GRPO adapter and row, or a one-paragraph deferral note.

**Done when:** Whichever was chosen, it is recorded in `EXPERIMENT_PLAN.md`.


#### Step 19: Audit for reward hacking and measure the gap `[Must]`

**What to do**

- Run the hidden checks on Tier A validation and Tier B for every model: decoy attributes unchanged, patch is minimal (no extra operations beyond what the reference needs), and full-attribute equivalence to the original config, not just the attributes a rule reads.
- Write twenty probing prompts where deleting or replacing the resource would be the easiest way to satisfy a rule. Confirm intent-preservation and no-new-principal checks reject every such output. Stub versions of those checks are enough here; the full versions arrive in Phase 7.
- Compute the training-versus-held-out gap: gate pass rate on 300 sampled training prompts minus the rate on Tier B and Tier C.

**Produces:** `eval/reward_hacking_audit.md` with the gap reported as a headline number.

**Done when:** The gap is reported even if it is unflattering. A small gap is a result; a large gap is also a result.


#### Step 20: Build the T0 templates and route findings correctly `[Must]`

**What to do**

- In `remediate/templates/`, write a lookup keyed by rule ID for every rule whose fix is a single attribute change, and write `match(finding)` to return a Patch-IR or `None`.
- Train M1 on all rules (the easy T0-covered examples are harmless and give a fallback), but compute the **headline M1 numbers on the T0-uncovered subset**, because at runtime only those findings reach M1.
- Measure T0 coverage on Tier A, B and C.

**Produces:** Templates, unit tests, and a coverage table.

**Done when:** Every template output passes the schema and the gate on its own test fixtures.


### Stage E: Evaluate, freeze and hand off (Week 12)


#### Step 21: Final evaluation run, once `[Must]`

**What to do**

- Confirm that all choices are frozen: checkpoints, sampling settings, best-of-N value, hidden-check definitions.
- Score every model on Tier B1, Tier B2 (using the ablation model for the held-out family), Tier C-verifier and Tier C-mined, and on the gold sample.
- Report Wilson intervals for proportions and a paired test (McNemar's test) when comparing two models on the same items. Report counts next to every percentage, because the real-data sets are small.

**Produces:** The full results grid (Section 5) and a run log listing every evaluation run with its date.

**Done when:** The log shows each held-out set scored once after the freeze; any repeat is explained.


#### Step 22: Freeze the two interface functions `[Must]`

**What to do**

- Implement `remediate/local_model/generate(tokenized_finding)` returning a list of Patch-IR candidates, and `remediate/templates/match(finding)` returning a Patch-IR or None. Do not change these signatures after this step.
- Phase 6 needs token log-probability statistics and the agreement rate among the N samples as features. Expose them through a separate function (for example `generate_with_stats()`) so the frozen signature stays untouched.
- Add a test that validates every returned candidate against the Patch-IR schema, and measure time to first candidate on the demo laptop.

**Produces:** Both functions committed, tested and documented.

**Done when:** Phase 7 can call them in order (match first, then generate) without reading any other Phase 5 code.


#### Step 23: Package, document and commit `[Must]`

**What to do**

- Commit the generator, the notebooks (kept as a record of what was actually run), the dataset card, the experiment plan, the results grid and the funnel report. Store model weights through Git LFS or an external link.
- Add a one-page `REPRODUCE.md`: the exact commands to rebuild the dataset, retrain and re-run the evaluation.
- Tag the repository `phase5-complete`.

**Produces:** A tagged repository state that a teammate can rebuild.

**Done when:** A teammate who did not work on Phase 5 follows `REPRODUCE.md` and gets matching dataset hashes.


#### Step 24: Hand off to Phase 6, Phase 7 and the paper `[Must]`

**What to do**

- Phase 6 is also Role C's work, so write down for it, while the details are fresh, which files and hidden-check definitions M2's labels must come from: the Tier A/B/C files and the labelled ground truth, since M2's labels must come from a source independent of the gate's own pass/fail.
- Give Role B (who leads the gate in Phase 7) and whoever wires the API the two function signatures and the latency figure.
- Give the paper owner the results grid, the funnel report, the gap figures and the limitations list from Section 8.

**Produces:** Three short handoff notes.

**Done when:** Each recipient confirms they can start without asking Role C a question.


## 5. Evaluation protocol


### 5.1 Metrics

| Metric | Definition | Reported on |
|---|---|---|
| Schema-valid rate | Share of outputs that validate against the Patch-IR schema. Expected 100% under constrained decoding; report it for the unconstrained zero-shot baseline too. | All sets |
| Gate pass@1, pass@8 | Share of prompts where the first candidate (pass@1) or at least one of eight (pass@8) clears gate checks (a) to (d). | All sets |
| Hidden-check pass rate | Share of gate-passing candidates that also pass the hidden checks (Section 5.3). | Tier A validation, B1, B2 |
| Reference equivalence | Normalised exact match with the reference Patch-IR, plus semantic equivalence (applying the patch gives the original config). A lower bound, because several fixes can be valid. | Tier A validation, B1, B2 |
| Unsafe-output rates | Share of candidates that delete a resource, add a new principal, or use an operation outside the vocabulary without escalating. | All sets |
| Escalate precision and recall | Whether the model escalates when it should and only then. | Tier A and B sets containing escalate cases |
| Time to first passing candidate | Seconds on the demo laptop, with the local model served through Ollama. | Tier A validation, Tier C |
| Training-versus-held-out gap | Gate pass rate on 300 sampled training prompts minus the rate on Tier B and on Tier C. | Final model(s) |
| Synthetic-versus-real gap | Gate pass rate on Tier B minus the rate on Tier C-verifier, with intervals. | Final model(s) |
| Rule precision on real code | Share of our own rule findings on Tier C repos that a reviewer judged to be true violations. | Tier C sample, gold sample |


### 5.2 Results grid to fill in

Every cell is filled once, after the freeze in Step 21. Put the count next to the percentage (for example 41/60), because the real-data columns are small. Report the headline M1 numbers on the T0-uncovered subset.

| Model | A val | B1 | B2 | C-verifier | C-mined | Gold |
|---|---|---|---|---|---|---|
| T0 templates only |  |  |  |  |  |  |
| Zero-shot base, constrained |  |  |  |  |  |  |
| Zero-shot base, best-of-8 |  |  |  |  |  |  |
| SFT, single sample |  |  |  |  |  |  |
| SFT, best-of-8 |  |  |  |  |  |  |
| Rejection-sampling FT, best-of-8 |  |  |  |  |  |  |
| GRPO, best-of-8 (if done) |  |  |  |  |  |  |


### 5.3 Hidden checks

The hidden checks are extra assertions that **never appear in the rejection-sampling filter or the GRPO reward**, so a model that learned to satisfy the gate by a shortcut still gets caught. Suggested definitions:

- **Decoys untouched.** Every attribute the mutators and decoys did not change is identical after the patch is applied.
- **Minimal patch.** The patch contains no operation beyond what the reference needs.
- **Full equivalence.** After applying the patch, the whole resource (not only the attributes a rule reads) matches the original config, up to values that have more than one valid choice.
- **No hidden side effects.** No new resource is introduced and no existing resource is removed or replaced.


### 5.4 Statistical reporting

- Proportions come with Wilson intervals. With the real-data sets this small, an interval is more honest than a bare percentage.
- Two models scored on the same items are compared with a paired test (McNemar's test).
- State the number of random seeds used for training. If compute allows only one, say so.
- Never choose a checkpoint, a prompt format or a sampling setting using a held-out set. Validation only.


## 6. Timeline for Weeks 8–12

Phase 6 starts in Week 11 and needs M1's verified candidates, so the dataset must be frozen and SFT finished by the end of Week 10. If anything slips, drop Stretch items first, then Should items, and keep the Must items.

| Week | Must | Should | Stretch | Exit criterion |
|---|---|---|---|---|
| **8** | Steps 1–3 (contracts, acceptance bars, toy runs). Step 4 (base corpus, buckets). Start Step 5 (mutators). | Step 5 frequency weighting (train-bucket repos only). |  | Toy runs pass; bases and manifest exist. |
| **9** | Finish Steps 5–9. Dataset v1 frozen and tagged. Step 10 (select Tier C repos). | Step 5 indirection variants, if the finding record can carry references. |  | Dataset v1 passes all eight QA checks. |
| **10** | Steps 14–16 (format, baselines, SFT, serving). Step 11 (verifier harvest) in parallel. | Step 12 (mined fixes) and Step 13 (gold sample) in parallel. |  | SFT model served through Ollama; Tier C-verifier file ready. |
| **11** | Step 19 (audit) on the SFT model. Step 20 (T0 templates). | Step 17 (rejection sampling). | Step 18 starts only if Step 17 is done. | RFT adapter exists; Phase 6 can start on its features. |
| **12** | Steps 21–24 (final run, interface freeze, packaging, handoff). | Complete Steps 12–13 if still open. | Step 18 finishes or is deferred in writing. | Tag `phase5-complete`; checklist ticked. |


## 7. Risks and how to handle them

| Risk | Why it matters | Response |
|---|---|---|
| Mutators are too regular and the model memorises their shape | Test results on Tier A would look good and real-world results would not. | Decoys, composition, variant mutators, held-out combinations (B1), a held-out family (B2), and Tier C. |
| A mutator and its rule disagree | The label is wrong and the model learns a false target. | QA checks 1, 2 and 4: the rule must fire, the base must be clean, the reference must pass its own gate. |
| Train/serve skew in the projection | Measured accuracy does not carry over to the demo. | Dataset builder calls the airlock’s projection function; byte-identical check in Step 7. |
| Leakage between train and test | Inflated numbers that a reviewer can spot. | Bucket assignment by repository before generation; normalised-hash comparison; hash guard in every notebook. |
| HCL parsing cannot resolve variables, modules or dynamic blocks | Many real resources cannot be turned into clean records. | Resolve only simple defaults, skip the rest, and report the skip rate as a coverage limitation. |
| Real data has few violations of the DPDP-specific rules | Tier C may be thin exactly where ARGUS is most novel. | Report counts per rule honestly; supplement with the generic-rule violations; say plainly where the real evidence is thin. |
| Tier C-mined is tiny | Statistical power is low. | Report the funnel, intervals and counts; treat it as supporting evidence next to C-verifier, not as the main result. |
| Licence problems with scraped code | Redistribution and citation issues. | TerraDS includes permissive-licence repositories only; keep the licence in the manifest; release hashes and IDs rather than raw files if any licence is unclear. |
| Colab or Kaggle session drops mid-training | Lost hours and an unreproducible run. | Checkpoint to Drive every epoch; record session limits in Step 3; keep notebooks as a log. |
| Reward hacking in RFT or GRPO | The model learns a shortcut (for example removing the resource). | Intent-preservation and no-new-principal stubs in the gate; hidden checks excluded from training; report the gap. |
| Rules themselves are wrong | A perfect model would still learn a wrong target. | Rule precision measured on real code (Step 11); mentor review of the DPDP mapping (Phase 1, step 8); legal review stated as a limitation. |
| Time overrun | Phase 6 and 7 wait on M1. | Priority tags, the Week 10 SFT deadline, and Step 18 as a written deferral rather than a rush. |


## 8. Using Phase 5 in the research paper


### 8.1 What we claim, and what we do not

- **Claim:** a verifier-grounded synthetic training set, built without any language model, trains a small local model to produce Patch-IR repairs, and the result holds up on real Terraform from repositories the model never saw.
- **Claim:** the gap between synthetic and real test performance, and between training and held-out performance, is measured and reported.
- **Do not claim:** that the dataset is a general benchmark, that the model works on other clouds or tools, or that it covers rules we did not build.
- **Do not present** SFT plus verifier-guided reinforcement learning as new. That recipe is published for infrastructure-as-code generation; cite it. Our contribution is finding-driven repair scored by security effect, behind a measured privacy boundary, feeding a calibrated auto-apply decision. Check whether the TerraFormer authors released code, data or weights that are worth building on.


### 8.2 Suggested wording for the dataset paragraph

Fill in the bracketed numbers from the manifest once they exist. Do not publish a number you have not measured.

> **Draft paragraph**
>
> We did not use a language model to write any training example. For each checkable rule in our policy libraries we wrote a mutation operator that takes a compliant Terraform resource and breaks it in the specific way that rule detects. The unmodified resource is then the reference fix, and a deterministic diff expresses it as a Patch-IR object. Base resources were drawn from [N] repositories of the TerraDS corpus and from [M] module examples. Before any generation, each repository was assigned to a training, validation or test bucket by hashing its name, so that no repository contributes to more than one split. Every example passed an automated check that the target rule fires on the mutated resource, that the reference patch clears our verification gate, and that applying the patch recovers the original. We evaluate on held-out sets the training loop never saw: unseen mutator combinations, an unseen rule family, and [K] real violations found in repositories from the test bucket, of which [J] were reviewed by hand.


### 8.3 Tables and figures to produce

- **Table 1:** dataset composition (tiers, sizes, sources, licences, per-rule counts).
- **Table 2:** the results grid from Section 5.2, with counts and intervals.
- **Table 3:** real-data funnel (repositories scanned to reviewed fixes kept) and rule agreement with Trivy and Checkov.
- **Figure 1:** pass@k curves (k from 1 to 8) for zero-shot, SFT and rejection-sampling models.
- **Figure 2:** training-versus-held-out gap and synthetic-versus-real gap, side by side.
- **Figure 3 (optional):** per-rule pass rate on Tier B and Tier C, to show where the model is weak.


### 8.4 What to release

- The generator code, the QA scripts and the seeds, so the dataset can be rebuilt.
- A dataset card: sources and licences, bucket rule, counts, known gaps, intended and out-of-scope uses.
- Hashes and identifiers for the real repositories used in Tier C, and the reviewed labels, where licences permit redistribution.
- The training notebooks and the final adapter (or a link), noting the base model's own licence.


### 8.5 Limitations to state plainly

- AWS Terraform only, and only the rules we implemented.
- Mutation-engine data covers the violation patterns we thought to write, which is why Tier C exists.
- The real-data sets are small and the DPDP-specific rules are thinly represented in public code.
- Resources whose attributes depend on unresolved variables, modules or dynamic blocks were skipped, so results describe the resolvable subset.
- Scanner labels (used only as a cross-check) have known precision limits; our own rule precision was measured on a hand-labelled sample, and the DPDP mapping has had no formal legal review.


### 8.6 Questions a reviewer is likely to ask

| Question | Answer we can give |
|---|---|
| Isn’t training and testing on generated data circular? | We train on mutation-engine output and test on repositories the generator never touched and on real violations. The gap between the two is reported. |
| Why not use an existing dataset? | Section 2.1: none has Patch-IR labels, none is tied to our verifier, none covers DPDP rules, and scanner labels are noisy. We use the real datasets where they fit (TerraDS for inputs and for Tier C). |
| Who checks that your rules are right? | Rule precision is measured on a hand-labelled sample of real findings, the mapping was mentor-reviewed, and the absence of formal legal review is stated as a limitation. |
| Is the real-data set big enough to conclude anything? | We report counts, intervals and the funnel, and we make only claims the sample supports. Tier C is supporting evidence, not a benchmark. |
| Could the model have learned to game the verifier? | Hidden checks never used in training, intent-preservation and no-new-principal checks, adversarial probes, and the reported training-versus-held-out gap. |


## 9. Integration checkpoint

Phase 7 calls two functions, in this order, and assumes every candidate is already valid against the Patch-IR schema. It re-checks correctness only, never structure.

| Function | Behaviour |
|---|---|
| `remediate/templates/match(finding)` returns Patch-IR or None | Deterministic T0 lookup keyed by rule ID. Called first. |
| `remediate/local_model/generate(tokenized_finding)` returns a list of Patch-IR candidates | Local M1 through Ollama or llama.cpp with schema-constrained decoding, N candidates (best-of-8 to start). |
| `generate_with_stats()` (separate function) | Returns the same candidates plus log-probability statistics and the agreement rate among samples, for Phase 6’s features. Keeps the frozen signature untouched. |


## 10. Final checklist

Tick every box before signing off Phase 5. The first group repeats the Master Guide's Phase 5 checklist, marked (MG); the rest cover what this plan added.


#### Master Guide items (MG)

- [ ] Mutation engine covers every Rego rule from Phase 4 (MG)
- [ ] Dataset generated with a genuinely held-out, out-of-template test set (MG)
- [ ] SFT model trained and serving locally with schema-constrained decoding (MG)
- [ ] Rejection-sampling round completed (MG, should-do)
- [ ] GRPO round attempted, or explicitly deferred with a stated reason (MG)
- [ ] Training-time versus held-out pass-rate gap measured and recorded (MG)
- [ ] T0 templates built, covering the single-attribute-fix rule set (MG)
- [ ] generate() and match() committed with frozen signatures (MG)


#### Planning and contracts

- [ ] Contracts file lists schema version, projection function, rule families and the T0-versus-M1 split
- [ ] Held-out rule family chosen and written down before any results
- [ ] Acceptance bars and experiment plan committed before the first test-set run
- [ ] Unsloth toy run, Ollama structured-output test and HCL parser all run end to end


#### Synthetic data (Tier A and B)

- [ ] Every repository assigned to exactly one bucket before generation; manifest records repo, commit, path and licence
- [ ] Every Tier A base passes all rules; no Phase 10 testbed config is in training
- [ ] Each mutator has fires/clears, round-trip and determinism tests
- [ ] Composition and decoys applied; decoys proven not to change rule outcomes
- [ ] Escalate examples included (suggested 3–5%)
- [ ] Dataset inputs built by the same projection code the airlock uses at runtime
- [ ] All eight QA checks pass on 100% of examples; 50 random examples hand-inspected
- [ ] Dataset v1 frozen, hashes written, repository tagged, dataset card written
- [ ] Hash guard present in every training notebook


#### Real data (Tier C)

- [ ] Tier C repositories come from the test bucket only; commit SHAs and licences recorded
- [ ] Tier C-verifier file produced; agreement with Trivy and Checkov tabulated
- [ ] Rule precision on real code estimated from a hand-labelled sample
- [ ] Tier C-mined file produced with the full funnel written down (Should)
- [ ] Gold sample of 50–100 items labelled by two reviewers; kappa reported (Should)


#### Training and evaluation

- [ ] Overfit test on 50 examples passed before the first real run
- [ ] Baselines (T0, zero-shot, zero-shot best-of-8) recorded before fine-tuning
- [ ] Checkpoints chosen on validation only; adapters saved outside the session
- [ ] Hidden checks defined and excluded from every filter and reward
- [ ] Reward-hacking audit completed, including adversarial deletion probes
- [ ] Headline M1 numbers reported on the T0-uncovered subset
- [ ] Final evaluation run once per held-out set, with a run log; intervals and counts reported
- [ ] Training-versus-held-out gap and synthetic-versus-real gap both reported


#### Interfaces, documentation and handoff

- [ ] generate_with_stats() exposes log-probabilities and agreement rate for Phase 6
- [ ] Every returned candidate validated against the Patch-IR schema; latency measured
- [ ] REPRODUCE.md followed successfully by a teammate; dataset hashes match
- [ ] Repository tagged phase5-complete; weights stored through Git LFS or an external link
- [ ] Handoff notes delivered to Phase 6, Phase 7 and the paper owner


#### Paper readiness

- [ ] Tables 1–3 and Figures 1–2 drafted from real numbers
- [ ] Dataset paragraph filled in from the manifest
- [ ] Limitations list copied into the paper draft
- [ ] TerraFormer release (code, data, weights) checked, and TerraDS and Reyes et al. cited


## Appendix A: Command cheat sheet

Flags change between versions. Check each against the tool's current documentation before relying on it.

```
# Cross-check a cloned repository with other scanners
trivy config ./repo --format json --output trivy.json
checkov -d ./repo --framework terraform -o json > checkov.json

# Run the Rego libraries against a prepared JSON input
conftest test input.json -p policy/ --output json

# List the history of one Terraform file, with patches
git -C ./repo log --follow -p --format=%H -- path/to/main.tf

# Freeze and verify dataset files
sha256sum ml/mutation_engine/dataset/*.jsonl ml/mutation_engine/held_out/*.jsonl > MANIFEST.sha256
sha256sum -c MANIFEST.sha256

# Serve the fine-tuned model locally (Modelfile contains: FROM ./argus-m1-q4_k_m.gguf)
ollama create argus-m1 -f Modelfile
ollama run argus-m1
# For constrained output, pass the Patch-IR JSON Schema in the "format" field of the API request.
```


## Appendix B: Code skeletons


#### A mutator

Use the attribute names that graph/schema.md and the Rego library actually use; the ones here follow the v3 design document's example.

```
# ml/mutation_engine/mutators/dpdp_6a_sse.py
from dataclasses import dataclass

@dataclass
class Mutation:
    rule_id: str        # "dpdp.rule6a"
    mutator_id: str     # "m_dpdp6a_sse_off"
    path: list          # attribute path that changed
    before: object      # original (compliant) value
    after: object       # broken value
    inverse_op: dict    # Patch-IR op that undoes it

class SseOff:
    rule_id = "dpdp.rule6a"
    mutator_id = "m_dpdp6a_sse_off"
    resource_types = ["aws_s3_bucket"]

    def applies(self, res):
        return res.attrs.get("server_side_encryption_enabled") is True

    def mutate(self, res, rng):
        broken = res.copy()
        broken.attrs["server_side_encryption_enabled"] = False
        broken.attrs.pop("sse_algorithm", None)
        inverse = {"op": "set_attr", "attr": "server_side_encryption_enabled", "value": True}
        return broken, Mutation(self.rule_id, self.mutator_id,
                                ["server_side_encryption_enabled"], True, False, inverse)
```


#### The QA gate loop

```
# qa/run_all.py  (the build fails on the first violation)
for ex in examples:
    assert rules_fire(ex.mutated, ex.rules_violated)             # 1. breaks what it claims
    assert not any_rule_fires(ex.original)                       # 2. base is clean
    assert apply_patch(ex.mutated, ex.target) == ex.original     # 3. round trip
    assert gate(ex.mutated, ex.target).passed                    # 4. reference clears gate
    assert schema_valid(ex.target)                               # 5. schema
    assert decoys_untouched(ex.original, ex.mutated, ex.paths)   # 6. decoys harmless
    assert no_real_identifiers(ex.input)                         # 7. leak-check
assert no_hash_overlap(train, val, held_out)                     # 8. no leakage across splits
```


## Appendix C: Decisions to settle with the team this week

| Decision | Options | Owner and deadline |
|---|---|---|
| Which rule family is held out for Tier B2 | Pick the family with enough rules to give 200+ examples | Role C, end of Week 8 |
| Base model and size | Start at 4B for iteration; consider 9B only if baselines show headroom | Role C, end of Step 15 |
| Whether the finding record can carry unresolved references | Yes (add indirection variants) or No (state as limitation) | Role C with the Phase 4 owner, Week 8 |
| Who reviews the gold sample | Two people, one of whom did not write the mutators | Team, Week 9 |
| Whether to attempt GRPO | Only if Step 17 is done by end of Week 11 | Role C, end of Week 11 |
| Whether to ask Reyes et al. and the TerraFormer authors for data or weights | Send the emails in Week 8; replies may take time | Role C, Week 8 |
