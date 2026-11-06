# ARGUS Architecture & System Design

ARGUS is a privacy-first, graph-driven risk prioritization and compliance verification platform designed for Amazon Web Services (AWS) environments. 

This document details the end-to-end processing pipeline, data flows, security boundaries, and technical guarantees provided by the ARGUS system.

---

## 1. System Overview

Traditional cloud security scanners alert on thousands of individual misconfigurations without understanding how an adversary chains them together. Conversely, naive automated remediation tools risk breaking production infrastructure or leaking sensitive cloud topology to public AI models.

ARGUS resolves this tension through three foundational principles:
1. **Attack Graphs Over Alert Lists**: Model the cloud as a directed graph where edges represent traversable network access, privilege escalation, or IAM trust.
2. **Never Require the AI to be Right**: Generative models propose fixes in a closed intermediate representation (`Patch-IR`), but deterministic policy engines (`OPA/Rego`) verify correctness before any patch touches cloud infrastructure.
3. **Zero Sensitive Data to Models**: A strict Privacy Airlock projects, hashes, and scrubs all environment metadata, ensuring generative models only see abstract topologies.

---

## 2. End-to-End Pipeline Walkthrough

```
┌─────────────────┐     ┌─────────────────┐     ┌─────────────────┐
│   AWS Account   │ ──> │   Cartography   │ ──> │ Neo4j Attack    │
│  (Read-Only)    │     │   Ingestion     │     │     Graph       │
└─────────────────┘     └─────────────────┘     └─────────────────┘
                                                         │
                                                         ▼
┌─────────────────┐     ┌─────────────────┐     ┌─────────────────┐
│     Privacy     │ <── │  Interdiction   │ <── │  Personalized   │
│     Airlock     │     │    Optimizer    │     │    PageRank     │
└─────────────────┘     └─────────────────┘     └─────────────────┘
        │
        ▼
┌─────────────────┐     ┌─────────────────┐     ┌─────────────────┐
│ Remediation     │ ──> │ Verification    │ ──> │ M2 Confidence   │
│ Tiers (T0 / T1) │     │ Gate (OPA/Rego) │     │ & Conformal Risk│
└─────────────────┘     └─────────────────┘     └─────────────────┘
                                                         │
                                       ┌─────────────────┴─────────────────┐
                                       ▼                                   ▼
                             [Auto-Apply Patch]                  [Human Approval Queue]
```

### Stage 1: Cloud Ingestion (`graph/`)
* **Input**: AWS Account credentials with strict read-only audit permissions (`SecurityAudit` / `ViewOnlyAccess`).
* **Tooling**: [Cartography](https://github.com/lyft/cartography) syncs cloud infrastructure assets into a Neo4j graph database.
* **Graph Model**: Nodes represent AWS principals (IAM Users, Roles), compute instances (EC2, Lambda), data stores (S3, RDS, DynamoDB), and network boundaries (VPCs, Subnets, Security Groups). Edges capture permission relationships (`sts:AssumeRole`, `iam:PassRole`), network reachability (`IN_SUBNET`, `EXPOSES_PORT`), and resource access policies.

### Stage 2: Risk Scoring with Personalized PageRank (`risk/`)
* **Mechanism**: Traditional shortest-path algorithms assume an attacker has global graph knowledge. ARGUS models realistic attacker traversal using **Personalized PageRank (PPR)** with random walk with restart (teleport probability $\alpha = 0.85$).
* **Crown Jewels**: Critical data repositories (e.g., databases containing customer personal data governed under DPDP) are designated as target sinks.
* **Output**: Continuous criticality scores $r_v \in [0, 1]$ assigned to each asset node based on how frequently an attacker moving laterally from initial entry points traverses through that node.

### Stage 3: Game-Theoretic Prioritization (`prioritize/`)
* **Mechanism**: Rather than patching based on arbitrary CVSS severity, ARGUS frames remediation as a **Network Interdiction Optimization** problem.
* **Formulation**: Given a remediation budget of $K$ fixes, find the optimal subset of edges/misconfigurations to sever such that the attacker's maximum reachability probability to crown jewels is minimized:
  $$\min_{x \in \{0, 1\}^E, \sum x_e \le K} \max_{p \in \mathcal{P}} \prod_{e \in p} (1 - x_e) w_e$$
* **Outcome**: A defensible, mathematically optimal cut-set prioritizing the few critical bottlenecks that dismantle chained attack paths.

### Stage 4: Privacy Airlock (`privacy/`)
* **Zero-Knowledge Guarantee**: No raw AWS account IDs, ARNs, bucket names, IP addresses, or environment variables ever reach an LLM.
* **Projection (`privacy/airlock/`)**: Reduces raw cloud findings to an abstract schema containing only the resource type, finding archetype, and structural misconfiguration pattern.
* **Pseudonymization Vault (`privacy/vault/`)**: Replaces real entity names with deterministic HMAC-SHA256 tokens (`res_a8f9c2...`).
* **Regex Secret Scrubbing (`privacy/scrubbers/`)**: Scans payloads for AWS keys (`AKIA...`), bearer tokens, and private keys, replacing them with generic placeholders.

### Stage 5: Multi-Tier Remediation (`remediate/`)
* **T0 (Deterministic Templates)**: Common, unambiguous misconfigurations (e.g., S3 Public Access Block, EBS Default Encryption) are remediated via static, pre-compiled templates with zero LLM involvement.
* **T1 (Local Model M1)**: Complex policy or IAM misconfigurations are routed to a fine-tuned local model (Qwen2.5-Coder) running entirely within the customer perimeter. The model outputs **Patch-IR** (Patch Intermediate Representation)—a strict JSON dialect specifying exact resource transformations, preventing arbitrary or unstructured code generation.
* **T2 (Remote LLM Opt-in)**: For rare, highly esoteric architectures, an administrator can explicitly enable cloud LLM inference. Only scrubbed airlock payloads are transmitted.
* **T3 (Human Escalation)**: High-blast-radius actions (e.g., deleting root IAM policies or modifying active production security groups) are flagged for human operator sign-off.

### Stage 6: Deterministic Verification Gate (`policy/`, `verify/`)
* **Open Policy Agent (OPA) / Rego Engine**: Every candidate patch is tested against formal security invariants before acceptance:
  1. **Generic Safety Invariants**: Fix must not introduce syntax errors, must not broaden existing IAM permissions, and must resolve the original finding.
  2. **India DPDP Act Rules 2025 Safeguards**:
     * **Rule 6**: Encryption in transit and at rest for personal data repositories.
     * **Rule 7**: Access controls, principle of least privilege, and MFA enforcement.
     * **Rule 8**: Audit logging (CloudTrail, VPC Flow Logs, S3 access logging).
     * **Rule 15**: Visibility over data residency and retention lifecycles.

### Stage 7: Trust, Confidence & Conformal Gate (`ml/train_m2/`)
* **M2 Confidence Model**: A calibrated tabular gradient-boosted classifier that scores patch quality based on structural AST diffs, gate invariant metrics, and cluster features.
* **Conformal Risk Control**: Implements distribution-free conformal prediction to establish an auto-apply threshold $\hat{\tau}$ that guarantees the empirical defect rate remains below a strictly specified error tolerance $\epsilon$ (e.g., $\le 1\%$):
  * Patches with confidence $\ge \hat{\tau}$: Marked for **Auto-Apply**.
  * Patches with confidence $< \hat{\tau}$: Queued for **Human Approval**.

---

## 3. Trust Boundaries & Security Model

```
┌─────────────────────────────────────────────────────────────────┐
│                      CUSTOMER TRUST BOUNDARY                     │
│                                                                 │
│  ┌─────────────┐        ┌──────────────┐       ┌─────────────┐  │
│  │ AWS Cloud   │ <====> │ ARGUS Core   │ <===> │ Local M1/M2 │  │
│  │ Environment │ (R/W)  │ (Neo4j, OPA) │       │ (Ollama)    │  │
│  └─────────────┘        └──────────────┘       └─────────────┘  │
│                                │                                │
│                     [ Privacy Airlock ]                         │
│                                │                                │
└────────────────────────────────┼────────────────────────────────┘
                                 │ (Only if T2 explicitly opted in)
                                 ▼
                     ┌───────────────────────┐
                     │ Untrusted Cloud LLM   │
                     │ (Sanitized AST only)  │
                     └───────────────────────┘
```

| Component | Trust Level | Security Controls |
| :--- | :--- | :--- |
| **AWS Cloud Access** | Read-only during discovery; Scoped IAM during remediation | Principle of least privilege; remediation actions require explicit assume-role boundaries. |
| **Attack Graph (Neo4j)** | Trusted (Internal) | Isolated network segment; no external internet ingress. |
| **Privacy Airlock** | Critical Gatekeeper | Hermetic tokenization; cryptographic hashing; high-entropy secret detection. |
| **Local Models (M1, M2)**| Semi-Trusted | Constrained by Patch-IR syntax and OPA Rego verification invariants. |
| **Remote LLMs (T2)** | Untrusted External Service | Completely blind to credentials, IPs, and customer identifiers. Disabled by default. |

---

## 4. Remediation Safety Guarantees

1. **No Free-Form Code Execution**: Generative models cannot output arbitrary shell scripts or unrestricted Terraform blocks. All outputs conform to the strict JSON Patch-IR schema.
2. **Deterministic Gate Invariance**: Even if a generative model suffers from hallucinations, invalid patches are unconditionally rejected by the OPA Rego policy gate.
3. **Rollback Resilience**: Every applied patch records a cryptographically signed provenance receipt and state diff, enabling immediate one-click rollback of infrastructure modifications.
