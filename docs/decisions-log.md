# Decisions & Rationale Log

One entry per non-obvious choice. Future-you (and the paper's Related
Work / Methodology sections) will thank present-you for this.

## 2026-09-28 — Scoped Cartography sync modules
**Decision:** Scoped cartography sync to iam,ec2,kms,s3,rds.
**Why:** Faster runs, covers Phase 1-2 needs; reduces noise from unused service types.
**Alternatives considered:** Full sync (all modules) — too slow and pulls in unrelated resources.

## 2026-09-28 — IAM user instead of role for scanner
**Decision:** Using an IAM user (argus-cartography-scanner) with SecurityAudit instead of a role.
**Why:** Simpler for Phase 1; avoids cross-account assume-role setup overhead.
**Alternatives considered:** AssumeRole from a Lambda/EC2 — to be revisited before the Phase 4 least-privilege test.

## 2026-09-28 — Interdiction MILP as primary prioritizer
**Decision:** Interdiction MILP replaces Stackelberg as the primary prioritizer.
**Why:** Patching is a binary decision (patch or not), which maps cleanly to binary ILP; Stackelberg is better suited to continuous strategy games.
**Alternatives considered:** Stackelberg game — see v3 doc section 7.4 for full comparison.

## 2026-10-02 — Derived attack graph (not raw Cartography)
**Decision:** PPR runs on a derived attack graph, not the raw Cartography structural graph.
**Why:** Cartography edges model ownership/membership, not attacker movement. Trust edges point the wrong direction; structural edges don't carry probability. Running PPR on the raw graph produces meaningless scores.
**Alternatives considered:** PPR on raw graph; custom Cypher path enumeration.

## 2026-10-02 — Absorb node for probability magnitude preservation
**Decision:** Added a virtual `__ABSORB__` sink node. Each node's unused outgoing mass (1 - Sp) flows to ABSORB.
**Why:** Plain row-normalisation would amplify weak edges (a p=0.1 edge becomes w=1.0), making a nearly-impossible step look certain. The absorb node preserves edge-probability magnitude so that short/strong paths genuinely outscore long/weak ones.
**Alternatives considered:** Plain normalisation; removing low-p edges entirely.

## 2026-10-02 — Dangling mass restarts at personalisation vector
**Decision:** Dangling node mass (from ABSORB, ADMIN_EQUIV, buckets) restarts at the personalisation distribution, not uniform.
**Why:** Standard for Personalized PageRank; ensures the dangling= parameter in networkx.pagerank matches exactly so our implementation cross-validates below 1e-6.
**Alternatives considered:** Uniform dangling redistribution.

## 2026-10-02 — Explicit entry-node config, scanner excluded
**Decision:** Entry nodes are an explicit list in risk/config.json; argus-cartography-scanner is in excluded_principals and never treated as an attacker.
**Why:** Auto-detecting all keyed users would include the scanner (Loophole L5); an inadvertent entry node inflates risk scores incorrectly.
**Alternatives considered:** Auto-detect all users with active access keys.

## 2026-10-02 — Escalation-action table for CAN_ESCALATE edges
**Decision:** A fixed risk/privesc_actions.json table maps known IAM privilege-escalation actions to CAN_ESCALATE edge probabilities.
**Why:** Cartography does not ingest non-default IAM policy versions, so Raynor's admin capability (via iam:SetDefaultPolicyVersion) is invisible in the graph without this inference.
**Alternatives considered:** Querying non-default policy versions via extra AWS API calls (out of scope for Phase 2).

## 2026-10-02 — Deny statements and Condition blocks ignored
**Decision:** Only Effect: Allow statements produce edges. Deny statements and Condition blocks are skipped.
**Why:** MVP simplification; building a full IAM policy-evaluation engine (SCPs, permission boundaries, Condition keys) is out of scope. Listed as a limitation in the paper.
**Alternatives considered:** Full IAM policy evaluation engine.

## 2026-10-02 — Top-level risk/ package
**Decision:** risk/ lives at the repo root (not under graph/).
**Why:** Resolves the inconsistency in the master guide (Loophole L9); keeps import paths clean for all four tracks.
**Alternatives considered:** graph/risk/ subfolder.

## 2026-10-02 — score_digraph as a pure function
**Decision:** score_digraph(G, entry_nodes) is a pure function of the graph object; no hidden Neo4j calls inside.
**Why:** Phase 7 needs to simulate a patched graph by calling score_digraph(apply_delta(G, delta)) without live DB access.
**Alternatives considered:** Storing scores back to Neo4j; re-querying inside the scorer.

## 2026-10-02 — Heuristic weights frozen after team review
**Decision:** Edge weights in risk/edge_weights.json are frozen after the Step 7 team review meeting. Changes require a decisions-log entry.
**Why:** Scientific honesty (Loophole L18); tuning weights to make a demo pass destroys result validity.
**Alternatives considered:** Continuous weight tuning; learned weights from GNN (stretch phase).

## 2026-10-02 — Coarse heuristic probability values (0.2 / 0.4 / 0.6 / 0.9)
**Decision:** Probabilities use rounded, interpretable values rather than precise decimal fractions.
**Why:** Precise-looking values (e.g. 0.734) imply calibration that does not exist. Coarse values are honest.
**Alternatives considered:** Calibrated probabilities from real exploit data (not available in this setup).

## 2026-10-02 — Test buckets use versioning-off as shared misconfiguration
**Decision:** The near/far demo buckets share "versioning never enabled" as their misconfiguration, not encryption-off.
**Why:** AWS has enforced default SSE-S3 encryption on all new S3 buckets since January 2023.
**Alternatives considered:** Public-access-block disabled; lack of MFA Delete.

## 2026-10-02 — Crown jewel IDs set via explicit config (fallback to tag)
**Decision:** crown_jewel_ids in risk/config.json lists bucket names explicitly; crown_jewel_tag is a secondary fallback.
**Why:** Cartography 0.141.0 does not store S3 bucket tags as Neo4j node properties (Loophole L6, verified in Phase 2 Step 1).
**Alternatives considered:** Tag-only lookup; writing a Cartography patch to ingest tags (out of scope).

## 2026-10-02 — risk/paths.py module for path utilities
**Decision:** Path-finding helpers (most_probable_path, all_paths_to_target) live in a dedicated risk/paths.py module.
**Why:** Keeps validate.py as a runner script; path logic is reusable by Phase 7 and Phase 10. Eliminates the Pyrefly static-analysis error from the conditional import.
**Alternatives considered:** Inline in validate.py; inline in attack_graph.py.

## 2026-10-25 — Phase 6 Generator & Harvest Contract Decisions (Prabhav Track)
**Decision:** Production M1 model is designated as SFT (`argus-m1-sft`) following EXPERIMENT_PLAN.md Rule 5.2. Harvest interface contract frozen as `m2.harvest.v1`.
**Why:** SFT achieved 96.7% pass@1 and 99.4% pass@8 diversity on A_val. Harvest line schema enforces strict token and logprob verification for M2 trust engine calibration.
**Alternatives considered:** Using RFT-v1 (rejected due to temperature collapse and loss of sampling diversity).