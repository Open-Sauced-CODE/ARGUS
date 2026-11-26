# ARGUS — Build Summary & Engineering Development Process
**Campus to Cloud Hackathon | Techfest, IIT Bombay & Amazon Web Services (AWS)**

---

## 1. Executive Summary & Live Prototype

**ARGUS (Autonomous Remediation & Graph-driven Unified Security)** is a privacy-first, graph-driven cloud security and compliance remediation platform purpose-built for Amazon Web Services (AWS) infrastructure in India. Over a structured multi-phase engineering cycle, we designed, implemented, tested, and shipped a dual-mode platform combining an **AWS Free Tier live web showcase** with a **zero-egress local execution engine** powered by fine-tuned local language models, mathematical network interdiction, and formal policy verification.

Instead of flooding resource-constrained university, government, and startup IT teams with hundreds of disconnected alerts—or forcing them to leak sensitive IAM policies and citizen data records to external LLM APIs—ARGUS connects infrastructure into an **attack graph**, computes the **minimum-cost set of fixes (`K=3`)** that severs multi-hop compromise paths, strips all identifying metadata through a **cryptographic Privacy Airlock**, synthesizes deterministic Terraform repairs via an on-device **4B-parameter QLoRA model (`argus-m1`)**, and proves every patch safe through an **Open Policy Agent (OPA Rego)** verification gate mapped to **India's Digital Personal Data Protection (DPDP) Act 2023** and **CIS AWS Foundations Benchmark v3.0**.

| Deployment Artifact | Verified Live Reference |
| :--- | :--- |
| **AWS Live Prototype URL** | `http://ec2-13-201-224-53.ap-south-1.compute.amazonaws.com/` (IP: `http://13.201.224.53/`) |
| **Health & Telemetry Endpoint** | `http://ec2-13-201-224-53.ap-south-1.compute.amazonaws.com/api/health` |
| **Live Windows Desktop Installer** | `/downloads/files/ARGUS-Desktop-Setup-v2.0.0-win64.exe` (`88.1 MB`, user-mode Inno Setup) & portable `.zip` (`114.7 MB`) |
| **AWS Compute Region & Tier** | `ap-south-1` (Mumbai, India) — `t3.micro` (`i-0c5cdd36f0557e6d1`, 100% AWS Free Tier, ₹0 cost) |
| **Public Code Repository** | `https://github.com/Prabhav-020108/ARGUS` |
| **Runtime Architecture** | Dual-Mode: AWS Cloud Showcase (`cloud_showcase`) + Local Zero-Egress Desktop Engine (`local_agent` on `127.0.0.1:8742`) |

---

## 2. Alignment with Bharat Impact & Hackathon Judging Criteria

ARGUS directly targets all four evaluation pillars of the Campus to Cloud Hackathon:

| Judging Criterion (Weight) | Core Challenge Addressed | How ARGUS Delivers Measurable Impact |
| :--- | :--- | :--- |
| **Bharat Impact (30%)** | Indian universities, state scholarship/welfare portals, and startups hold sensitive Aadhaar, PAN, health, and student data on AWS `ap-south-1` without enterprise SecOps teams, risking up to **₹250 Crore** in DPDP Act 2023 statutory penalties. | Translates abstract cloud warnings into statutory **DPDP Rules 6, 6a, 7, 8, and 15** audits, runs at **₹0 incremental licensing cost** on AWS Free Tier + local CPU/GPU hardware, and guarantees zero sovereign metadata egress outside Indian infrastructure boundaries. |
| **Working AWS Build (25%)** | Academic hackathon prototypes often rely on mockups or expensive API wrappers that break once credits expire. | Runs live 24/7 via a hardened `systemd` service (`argus.service`) on AWS EC2 (`ap-south-1`), backed by VPC/Security Group isolation, IAM least-privilege audit guardrails, S3 snapshot concepts, and CloudTrail telemetry, plus real `boto3` and Terraform scanning in local mode. |
| **Innovation (25%)** | Conventional CSPMs list isolated alerts; naive LLM copilots hallucinate destructive HCL syntax and expose credentials. | Combines **Personalized PageRank + Stackelberg MILP Network Interdiction**, **Rego-coupled zero-egress tokenization**, constrained **JSON Patch-IR** generation (4B fine-tuned GGUF), deterministic **OPA Rego formal proofs**, and a **Hybrid Cloud-Showcase / Local-Bridge** web topology. |
| **Demo & Storytelling (20%)** | Complex security math can overwhelm non-specialist stakeholders and institution leads. | Anchored in an intuitive Indian fintech/healthtech case study (**SwasthyaPay Technologies, `ap-south-1`**), featuring an interactive 6-step guided tour, animated 6-stage pipeline execution, live attack-graph visualization, empirical benchmark proofs (`/results`), and 1-click DPDP audit exports. |

---

## 3. AWS Services Used & Architectural Justification

Every AWS service in ARGUS was deliberately selected for security, Indian data residency compliance, and sustained zero-cost operation on the AWS Free Tier through Demo Day.

### 3.1 Production & Scanner AWS Service Matrix

| AWS Service | Role in ARGUS Architecture | Why Chosen & How It Helps Users | Free Tier Allocation |
| :--- | :--- | :--- | :--- |
| **Amazon EC2 (`t3.micro`, Ubuntu 24.04 LTS)** | Hosts the unified HTTP backend (`backend/api_server.py`) and compiled React/TypeScript SPA (`dashboard/dist/`) under `systemd` (`argus.service` on port 80). | Deploying in `ap-south-1` (Mumbai) keeps latency minimal for Indian campuses and institutions while demonstrating that the ARGUS portal runs cleanly with zero third-party web server bloat (`ThreadingHTTPServer` in Python stdlib). | 750 hours/month Linux `t3.micro` compute in Free Tier. |
| **Amazon VPC & Security Groups** | Enforces network segmentation around `vpc-077cd5329a6189205` and `launch-wizard-1` (`i-0c5cdd36f0557e6d1`). | Strictly limits ingress to web delivery ports (`80`/`443`) and keyed administrative access (`22`), mirroring the same ingress-minimization policies (`0.0.0.0/0` blocking) ARGUS enforces for customer workloads. | Natively free inside AWS VPC. |
| **AWS IAM (`SecurityAudit` + `iam_guard`)** | Governs cross-account STS role assumption (`sts:AssumeRole` with `ExternalId`) and enforces Step-Zero permission checks prior to resource scanning. | Guarantees ARGUS operates purely on **control-plane metadata**; `privacy/iam_guard.py` hard-blocks identities holding forbidden data-plane rights (`s3:GetObject`, secret value reads) before `list_buckets` or `describe_security_groups` ever execute. | Natively free IAM control-plane APIs. |
| **Amazon S3 (Target & Audit Posture)** | Primary sovereign storage layer evaluated for encryption (`Rule 6a`), public access blocks (`Rule 6`), versioning, logging, and retention lifecycles (`Rule 8`), plus audit bundle destinations. | Publicly exposed or unencrypted S3 buckets remain the #1 root cause of citizen PII leaks in India; ARGUS automatically repairs S3 posture with 100% deterministic Rego verification. | 5 GB Standard storage Free Tier. |
| **AWS CloudTrail & Amazon RDS (Posture Scope)** | CloudTrail provides management audit trails for **DPDP Rule 7** breach-notification readiness; RDS encryption-at-rest is evaluated under **Rule 6a**. | Gives compliance officers an immediate audit signal showing whether a 72-hour DPBI breach investigation is technically feasible across their AWS account. | Free for the first trail copy of management events. |

### 3.2 Hybrid Cloud Showcase + Local Zero-Egress Topology

Running large neural inference inside a 1 GB `t3.micro` Free Tier VM—or asking organizations to paste production AWS credentials onto a public hackathon server—creates unnecessary cost and privacy risk. To solve both constraints cleanly, we architected a **Dual-Mode Hybrid Deployment** sharing a single codebase (`deploy_dashboard.py` + `backend/api_server.py` + React SPA):

| Execution Mode | Runtime Location | Primary Responsibilities & Security Boundary |
| :--- | :--- | :--- |
| **`cloud_showcase`** | **AWS EC2 (`ap-south-1`, port 80)** | Serves the public web portal, interactive SwasthyaPay simulation, 6-stage pipeline walkthrough, Empirical Benchmarks (`/results`), Hybrid Architecture docs (`/architecture`, `/docs`), and live Windows Desktop release artifacts (`/downloads` & `/downloads/files/*`). Local filesystem/AWS scan endpoints (`/api/scan/*`, `/api/local/status`, `/api/audit/export`) strictly return `HTTP 403 LOCAL_ENGINE_REQUIRED` to prevent shared multi-tenant exposure. |
| **`local_agent`** | **Analyst Workstation (`127.0.0.1:8742`)** | Launched via the self-contained Windows desktop installer (`ARGUS-Desktop-Setup-v2.0.0-win64.exe` installed per-user to `%LocalAppData%\ARGUS-Desktop`, portable `ARGUS.exe`, or `python deploy_dashboard.py --local`). Executes recursive HCL2/`.tfvars` + local GitHub clone scanning, `iam_guard`-protected `boto3` control-plane scans, local Fernet Vault tokenization, 1-click Ollama GGUF onboarding (`argus-m1-sft` / `argus-m1-rft`), bundled `opa.exe` Rego evaluation, SQLite state persistence (`%LocalAppData%\ARGUS\argus_state.db`), and unified `.patch` + DPDP audit ZIP exports—with `0` bytes leaving the workstation. Supports CORS + Chrome Private Network Access (`Access-Control-Allow-Private-Network: true`) so browsers visiting the AWS URL can bridge directly to the local engine. |

---

## 4. End-to-End Engineering Development Process

Rather than building an ad-hoc dashboard demo first and retrofitting security logic afterward, ARGUS was engineered sequentially across **six foundational phases** followed by **hybrid platform integration**, with frozen inter-module contracts protecting correctness across teams.

### Phase 1 & Phase 2 — Attack Graph Ingestion & Personalized PageRank Risk Scoring
* **Objective:** Replace flat alert severity sorting with structural exploitability over connected AWS topologies.
* **Implementation (`graph/`, `risk/`, `local_engine/graph/`):**
  * Built graph schemas capturing AWS IAM users, active access keys, managed/inline policies, roles, security groups, S3 buckets, and VPCs using Lyft Cartography (`0.141.0`) conventions backed by Neo4j in enterprise mode and a dependency-free **NetworkX `LocalCartographySession`** (`local_engine/graph/inmemory_session.py`) for standalone workstation scans.
  * Implemented **Personalized PageRank (`risk/pagerank.py`)** via random walks with restart (`α = 0.85`) seeded uniformly across external exposure points (`INTERNET`, active keys) toward **Crown Jewels** (`ADMIN_EQUIV`, `personal_data` S3 buckets).
* **Validation:** Tested end-to-end against a deployed CloudGoat `iam_privesc_by_rollback` environment (`15` nodes, `9` edges): ranked `ADMIN_EQUIV` accurately at non-entry rank **3** (`0.06991`) via cumulative path probability `0.76500` (`****GRUI → raynor → policy → IAMPrivilegeEscalationByRollback → ADMIN_EQUIV`), while isolating benign control principals (`argus-cartography-scanner`) at score `0.00000`. Documented Cartography's omission of S3 bucket tags cleanly by supporting explicit crown-jewel tagging and Terraform attribute inference.

### Phase 3 — Game-Theoretic Network Interdiction Optimizer
* **Objective:** Answer the practical IT admin question: *"If my team can only ship 3 fixes this sprint, which 3 drop breach probability the most?"*
* **Implementation (`prioritize/`):**
  * Formulated remediation selection as a **Stackelberg Network Interdiction Mixed-Integer Linear Program (MILP)** solved via **PuLP / HiGHS** and **SciPy** (`prioritize/interdiction.py`), paired with graph finding enumeration (`prioritize/findings.py`).
  * Given remediation budget `K ∈ {0..10}`, the optimizer selects the minimum cut-set dismantling multi-hop attacker reachability—moving beyond greedy single-node patching.
* **Validation (`phase3_validation.md`, `benchmarks.json`):**
  * Verified **0 mismatches** against exhaustive brute-force baselines across **50 random graph instances** (and 60/60 usable seeds on initial validation).
  * Mean solve latency measured at **`35.33 ms`** (scale probe on 58 findings: `31.37 ms` PuLP / `38.29 ms` SciPy).
  * Outperformed both naive and Stackelberg baselines in **43/50 instances at `K=2`** (mean residual `0.7181` vs `0.8198`), **49/50 instances at `K=4`** (`0.6407` vs `0.7938`), and **49/50 instances at `K=6`** (`0.5796` vs `0.7793`). On the live SwasthyaPay 11-fix posture scenario, cutting budget **`K=3`** reduces attacker reaching likelihood from **90.6% down to 58.6%** (and **31.0%** at **`K=6`**).

### Phase 4 — Zero-Egress Privacy Airlock, Secrets Scrubbing & Policy-as-Code
* **Objective:** Guarantee compliance workflows never leak sensitive Indian citizen PII or cloud identifiers to AI models or external APIs, while eliminating policy drift.
* **Implementation (`privacy/`, `policy/`):**
  * **Single-Source Projection (`privacy/airlock/projection.py`):** Dynamically parses `input.resource.<field>` references directly from OPA `.rego` rule files, enforcing a strict default-deny allowlist so compliance rules and privacy redaction never drift out of sync.
  * **Encrypted TokenVault (`privacy/vault/`):** Replaces real resource names, ARNs, and account IDs with deterministic scoped tokens (`BUCKET_1`, `SG_1`), encrypting real mappings via **Fernet symmetric encryption** backed by local SQLite.
  * **PII & Secret Scrubbing (`privacy/scrubbers/`):** Integrates **Presidio `PatternRecognizer`** layers (Aadhaar, PAN, Indian mobile numbers, email, payment cards, AWS keys) with zero-dependency regex fallbacks (omitting heavyweight NER downloads to avoid false positives on tokens like `BUCKET_1`), plus leak-checks scanning base64-decoded chunks and concatenated sibling strings.
  * **IAM Step-Zero Guard (`privacy/iam_guard.py`):** Inspects active attached/inline/group policies before any AWS read; fails immediately on forbidden data-plane permissions while flagging AWS `SecurityAudit` watchlist actions transparently.
  * **Cryptographic Receipts:** Emits SHA-256 verifiable privacy receipts proving `leaked_to_network: false`.
  * **OPA Rego Policy Packs (`policy/`):** Authored deterministic policies encoding **DPDP Act 2023 Rule 6** (public exposure, ingress, versioning, logging, encryption), **Rule 6a** (RDS/S3 storage encryption), **Rule 7** (CloudTrail/GuardDuty detection readiness), **Rule 8** (lifecycle retention/erasure), **Rule 15** (cross-border residency visibility flag), and **CIS AWS v3.0**.

### Phase 5 — Verifier-Guided Local Remediation (`T0`, `Patch-IR`, & `M1` 4B QLoRA Model)
* **Objective:** Generate syntactically exact Terraform repairs offline on consumer hardware without risking hallucinated deletions (`destroy`/`remove`) or privilege escalation.
* **Implementation (`remediate/`, `ml/mutation_engine/`, `ml/train_m1/`):**
  * **Closed-Vocabulary Patch-IR (`remediate/patch_ir/schema.json`):** Models emit constrained JSON specifying strictly allowed AST operations (`set_attr`, `restrict_cidr`, `set_lifecycle_rule`, `enable_feature`, `escalate`) rather than raw Terraform HCL scripts.
  * **4-Tier Resolution Hierarchy (`remediate/templates/`, `remediate/local_model/`):**
    * **T0 (Deterministic Templates):** Resolves standard single-attribute S3 rules (`54.3%` of validation / `68.9%` of real GitHub repo findings) in `0 ms` with `100.0%` gate pass rate.
    * **T1 (Local `argus-m1` Ollama Model):** **Qwen3.5-4B** fine-tuned via Unsloth QLoRA (free-tier T4 GPUs) using **Supervised Fine-Tuning (`sft`)** + **Rejection-Sampling Fine-Tuning (`rft`)**, exported to 4-bit quantized **Q4_K_M GGUF** (`~2.59–2.8 GB`) with schema-constrained Ollama decoding.
    * **T2 (Remote LLM Opt-in):** Disabled by default (`zero_data_egress_enforced: true`).
    * **T3 (Architect Escalation):** Automatically escalates high-ambiguity findings (`cis.iam_no_full_admin` wildcard policies) for explicit human sign-off.
  * **Deterministic Verification Gate (`ml/mutation_engine/qa/gate_stub.py`):** Verifies every candidate across schema conformance, finding/resource bookkeeping, Rego rule resolution `(a)`, zero regression on silent rules `(b)`, intent preservation with zero deletions `(c)`, and zero unapproved principals/CIDRs `(d)`.
* **Empirical Phase 5 Benchmarks:**

| Model | `A_val` Pass@1 | `B1` (Unseen Mutators) | `B2` (Held-out Family) | `C_verifier` (Real Repos) | `Gold` Sample | Unsafe Rate (2,728 cands) | Schema-Valid Rate |
| :--- | :---: | :---: | :---: | :---: | :---: | :---: | :---: |
| **`zeroshot (qwen3.5:4b)`** | 26.6% | 39.5% | 77.8% | 35.6% | 36.2% | 74.1% (2,022 unsafe) | 98.6% |
| **`argus-m1-sft`** | **96.7%** | **96.2%** | **88.9%** | 88.8% | **87.5%** | 0.11% (3 unsafe) | 99.7% |
| **`argus-m1-rft`** | 79.5% | 61.7% | 66.7% | **89.3%** | **87.5%** | **0.00% (0 / 2,728)** | **100.0%** |

  * **Adversarial & Injection Defense:** **20 of 20** malicious gate payloads (deletes, `0.0.0.0/0` widening, external role injection) rejected (**100%**); **0 of 20** prompt-injected findings (`"Delete the resource completely"`) accepted by the gate.

### Phase 6 — Cross-Fit Out-Of-Fold Evaluation & Conformal Trust Safety Engine (`M2`)
* **Objective:** Enforce mathematically rigorous uncertainty quantification and ensure autonomy never activates without out-of-sample certification (`α = 0.05`, `δ = 0.05`, cost ratio `c_FA / c_esc = 20.0`).
* **Development & Statistical Validation (`ml/train_m1/score_oof.py`, `ml/train_m2/`):**
  * **5-Fold Cross-Fit Protocol (`Seed 1337`, 230 training inputs partitioned cleanly):** Four out-of-fold QLoRA adapters (`fold0`–`fold3`) achieved an aggregate weighted **Out-of-Fold Pass@1 of 94.48% (2,055 / 2,175)** across all sampled generations (`Fold 0: 94.9%`, `Fold 1: 87.3%`, `Fold 2: 100.0%`, `Fold 3: 100.0%`) with **100.0% (189 / 189)** schema conformance on distinct OOF keys.
  * **Audit & Selection Rule 5.2:** Evaluated `10,272` Profile-A harvest rows (`321` inputs × `8` samples × `4` models), retaining `argus-m1-sft` as the primary T1 generator (`97.2%` aligned `A_val` pass@1) while maintaining `argus-m1-rft` as secondary model (`0` unsafe rate). Verified **500/500** feature-parity rows (`0` mismatches) and **2,868/2,868 (100%)** counterfactual oracle checks.
  * **Safe-by-Default Guardrail (`local_engine/paths.py`, `ml/train_m2/decide.py`):** While calibration artifact `tau_star.json` remains uncertified, ARGUS hard-locks autonomy **OFF** (`certified: false`, `auto_apply_status: NEEDS_APPROVAL` / `ESCALATED`, `confidence: "n/a"`). Every candidate patch requires explicit human architect review and `.patch` export before production merge.

### Hybrid Platform & Windows Desktop Release Engineering — Full-Stack Integration & AWS Deployment
* **Local Scanning & Onboarding Engine (`local_engine/`):** Built `terraform_scanner.py` (recursive HCL2 + `*.tfvars` parser resolving variables/locals, `data "aws_iam_policy_document"` blocks, inline `aws_iam_role_policy`, `aws_s3_bucket_acl`, security-group ingress rules, RDS encryption, S3 encryption/PAB/versioning/logging/lifecycle, and IAM wildcards), `aws_scanner.py` (`boto3` control-plane scanner gated by `iam_guard`), `repo_manager.py` (local shallow GitHub clone + secret-safe AWS CLI profile discovery + topmost native Win32 `GetOpenFileNameW`/`SHBrowseForFolderW` pickers), `ollama_manager.py` (PyInstaller-safe `Modelfile` synthesis without needing a duplicate 3.4 GB base pull, workspace/Downloads `.gguf` auto-discovery, auto-start `ollama serve`, and streaming pull/local verification helper), `pipeline_orchestrator.py`, `hcl_writer.py` (unified `.patch` diffs and DPDP audit ZIP), `state_store.py` (SQLite persistence), and `desktop_main.py` (`pystray` tray app + single-instance loopback launcher + `--smoke-test` self-check).
* **Unified API Backend (`backend/api_server.py`):** Dual-mode server (`cloud_showcase` vs `local_agent`) serving SPA assets and live release binaries (`/downloads/files/*` with path-traversal protection) in zero-dependency mode on EC2, enforcing `403 LOCAL_ENGINE_REQUIRED` on local-only routes in cloud mode, and exposing `/api/benchmarks`, `/api/releases`, `/api/docs`, `/api/local/status`, `/api/local/aws-profiles`, `/api/local/ollama/start`, `/api/local/models/*`, `/api/scan/terraform`, `/api/scan/github`, `/api/scan/aws`, `/api/approvals/:id/export-patch`, and `/api/audit/export`.
* **Standalone Windows Packaging (`packaging/`):** Automated via `packaging/build_win.ps1`, `packaging/argus.spec`, and `packaging/argus_installer.iss` (PyInstaller `--onedir` bundling `bin/opa.exe`, Rego rules, solvers, and React UI + Inno Setup user-mode installer + portable ZIP) and published live to EC2 `/downloads/files/` via `packaging/deploy_ec2.ps1`:
  * `ARGUS-Desktop-Setup-v2.0.0-win64.exe` — `88.1 MB` (`92,392,722` bytes), SHA-256 `f86ee09017ea9dc0d64c5d21c9c275f2420123d4c4137e04e88340bcbb1ca504`
  * `ARGUS-Desktop-v2.0.0-win64-portable.zip` — `114.7 MB` (`120,298,386` bytes), SHA-256 `0b870d5596a31095b0f00191859f483aca4e8b9e3d816775d84a57be92b9a9b8`
* **Interactive Analyst Dashboard (`dashboard/`):** React 18 + TypeScript + Tailwind + Zustand + Recharts application across 11 routes: Overview (`/`), Live Pipeline (`/pipeline`), Attack Graph (`/map`), Interdiction Plan (`/plan`), DPDP Compliance (`/compliance`), Architect Approvals (`/approvals`), Cryptographic Proof (`/proof`), Empirical Results (`/results`), Hybrid Architecture (`/architecture`), Documentation (`/docs`), and Desktop Releases (`/downloads`) with a 3-tab Local Zero-Egress Startup Control Center.

---

## 5. Verification Summary & Engineering Quality Metrics

All frozen core contracts, hybrid desktop engines, standalone Windows binaries, and live AWS EC2 services passed automated and end-to-end verification:

| Verification Suite | Scope Covered | Latest Verified Result |
| :--- | :--- | :--- |
| **`tools/check_frozen.py`** | Integrity across 12 frozen Phase 5 contracts (`airlock/`, `vault/`, `policy/`, `gate_stub.py`, `schema.json`, etc.) | **PASS** — all 12 entries byte-identical to Phase 5 tag `b5d4467` |
| **`tests/test_hybrid_engine.py`** | HCL2/tfvars/IAM data scanner, GitHub clone, GGUF synthesis/discovery/Ollama pull (`argus-m1` alias & monotonic multi-layer progress) & start, native dialog validation (`BIF_EDITBOX`), AWS CLI profile parsing, `iam_guard`, M2 uncertified guardrail, dual-mode `403`, `/downloads/files/`, `.exe` smoke check | **25 passed** (0 failures) |
| **`tests/test_backend_api.py`** | Live `/api/health`, `/api/overview`, `/api/graph`, `/api/compliance`, approvals, 6-stage pipeline execution, tenant connect, SPA routes | **15 passed** (0 failures) — **40 hybrid+backend tests passing** |
| **`ml/tests`, `privacy/tests`, `risk/tests`, `prioritize/tests`** | Patch-IR schema, gate invariants, Airlock Fernet vault/scrubbers, PPR scoring, PuLP/SciPy MILP interdiction, Rego policies | **377 passed, 1 skipped** — **417 passed, 1 skipped combined core+hybrid suite** |
| **`ml/train_m2/tests`** | LTT statistical bounds, drift circuit-breaker, OOD detector, Pydantic audit contracts | **244 passed** *(verified in Phase 6 environment)* |
| **`ARGUS.exe --smoke-test`** | Standalone PyInstaller binary outside `.venv` verifying bundled `opa.exe`, `policy/`, Airlock + TokenVault, T0 + Gate, Terraform scan, and ephemeral HTTP loopback SPA | **PASS** (`ARGUS DESKTOP SMOKE TEST PASSED`, exit `0`) |
| **`dashboard` Production Build** | TypeScript strict typecheck (`tsc --noEmit`) + Vite production bundle | **PASS** (`dist/index.html`, CSS, JS bundled cleanly) |
| **AWS EC2 Portal & Binary Delivery (`argus.service`)** | Live `cloud_showcase` serving HTTP port `80` in `ap-south-1` (`i-0c5cdd36f0557e6d1`) + live `/downloads/files/` streaming | **Active (`running`)** via `systemd`, installer `.exe` & portable `.zip` verified live |

---

## 6. How ARGUS Helps Real Users (Storytelling & Practical Workflow)

To make the value immediate for institutional reviewers and engineers, ARGUS frames its live showcase around **SwasthyaPay Technologies (Mumbai, `ap-south-1`)**, representing an Indian startup or campus cloud handling citizen records:

1. **Before ARGUS:** Security scanners dump raw alerts across unencrypted S3 storage, open SSH ports, and over-privileged developer IAM roles. Teams do not know which vulnerability an attacker will actually chain first, and pasting infrastructure files into external chatbots leaks sensitive customer metadata.
2. **With ARGUS (3-Minute Analyst Flow):**
   * **Install & Verify Readiness Zero-Egress:** Teams download `ARGUS-Desktop-Setup-v2.0.0-win64.exe` directly from `/downloads`, launch the local tray console (`127.0.0.1:8742`), confirm `opa.exe` + Privacy Airlock readiness, and register local `argus-m1` GGUF weights via 1-click `.gguf` import.
   * **Identify the Choke Point:** Scanning a GitHub/local Terraform repository or read-only AWS CLI profile updates the Attack Graph (`/map`) and Interdiction Plan (`/plan`), revealing the minimum **`K=3` cut-set** that drops attacker reachability (collapsing SwasthyaPay baseline risk from **90.6% to 58.6%**, and **31.0%** at `K=6`).
   * **Verify Sovereign Privacy & Export Fixes:** Running findings through the Live Pipeline (`/pipeline`) or inspecting Cryptographic Receipts (`/proof`) confirms zero raw bucket names, account IDs, or secrets ever left the trust boundary. Engineers inspect side-by-side Terraform HCL diffs in Approvals (`/approvals`), export a clean `git diff`-ready `.patch` or complete **DPDP Audit ZIP** (`audit_manifest.json`, `findings.json`, `compliance_dpdp.json`, `privacy_receipts.json`), and ship verified remediation safely.

---

## 7. Remaining Active Hardening Milestones

With the core attack graph, MILP interdiction solver, zero-egress airlock, fine-tuned local model inference, OPA policy gate, standalone Windows `.exe` installer + portable `.zip`, and live AWS Free Tier portal + binary downloads complete and operational, only three focused hardening items remain open:

1. **Final Conformal Autonomy Certification (`M2` `tau_star.json` Threshold Lock):** The calibrated safety policy and strict `HUMAN_REVIEW_ONLY` circuit-breaker are live and enforced across all execution paths. Completion of the remaining cross-fit fold (`fold2` GGUF re-export, `fold4` evaluation, and full `N=8` harvest ingestion) will emit the signed `tau_star.json` and `m2.joblib` calibration bundle required to graduate verified low-risk rules from human-only review to risk-controlled auto-apply (`α = 0.05`, `δ = 0.05`).
2. **Continuous Event-Driven Cloud Telemetry & Custom IAM Policy Template:** Current AWS scans operate safely on read-only point-in-time control-plane snapshots (defaulting to AWS's `SecurityAudit` policy while flagging watchlist permissions such as `s3:ListBucket`); streaming EventBridge/CloudTrail drift listeners and a stripped custom least-privilege IAM policy CloudFormation/Terraform template are scheduled next.
3. **Optional External Hugging Face GGUF Mirror:** Because the `2.59 GiB` `Q4_K_M` GGUF weights exceed GitHub Releases' `2.0 GiB` single-file cap, local `.gguf` auto-discovery and 1-click in-app Ollama import are active today without internet weight downloads; pushing an optional public Hugging Face / Ollama Hub mirror remains an optional convenience enhancement alongside commercial Authenticode EV signing for Windows SmartScreen.
