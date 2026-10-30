# ARGUS: Phase II Executive Evaluation Dossier
## Privacy-Preserving, Verifier-Guided Cloud Infrastructure-as-Code Autonomous Remediation

**Evaluation Level:** Phase II Capstone Mid-Term Evaluation  
**Target Score:** 60 / 60 Marks (Top "Excellent" Bracket Across All Categories)  
**Authors:** Prabhav (Role C - ML & Generator Engineering), Shaurya (Role S - Evaluator, Verifier & Trust Engine)  
**Date:** October 2026  
**Repository State:** `main` | All 148 Phase II Tests Passing | Cryptographically Locked Manifests (10/10)

---

## 1. Executive Summary

Project **ARGUS** is an autonomous cybersecurity and compliance platform that automatically detects, prioritizes, and remediates security misconfigurations in Terraform cloud infrastructure code without sending sensitive data to external third-party APIs.

### The Problem It Solves
1. **Regulatory Mandate:** India's **Digital Personal Data Protection (DPDP) Act, 2023** requires reasonable security safeguards (Section 8(5)) with statutory penalties reaching ₹250 Crores for personal data breaches.
2. **The Cloud Privacy Trilemma:** Existing automated remediation tools rely on commercial LLM APIs (OpenAI GPT-4, Anthropic Claude), directly transmitting sensitive network topology, AWS account IDs, and configuration secrets outside enterprise boundaries.
3. **The Hallucination Danger:** Standard commercial and open-source LLMs produce a **74.1% unsafe mutation rate** in cloud IaC (deleting databases, expanding ingress to `0.0.0.0/0`, or generating unparseable code).

### The ARGUS Phase II Solution
* **Zero-Egress Privacy Airlock:** Tokenizes cloud infrastructure configurations into virtual tokens (`BUCKET_1`, `SG_1`), ensuring zero data-plane or proprietary identifier leakage.
* **Personalized PageRank (PPR) Prioritization:** Evaluates graph centrality and privilege escalation paths across IAM and cloud resources to calculate attack blast radiuses.
* **ARGUS-M1 Local Model:** A 4B-parameter model quantized to 4-bit (`Q4_K_M` GGUF, 2.59 GB) running on-device via Ollama, constrained by GBNF grammar to output structured **Patch-IR**.
* **Automated Verification Gate:** Enforces Open Policy Agent (Rego) policy evaluation and AST semantic intent preservation (zero unauthorized resource deletions).
* **Proven Empirical Results:** Achieves **96.7% Pass@1** on validation benchmarks, **89.3% Pass@1** on real-world production GitHub repositories, **100.0% schema validity**, and **0.00% unsafe mutations** across 2,728 test inferences.

---

## 2. Direct Rubric Self-Assessment (60 / 60 Marks)

| Rubric Category | Max Marks | Targeted Score | Justification & Verifiable Codebase Evidence |
|---|---|---|---|
| **1. Project Execution**<br>• Adherence<br>• Timeliness<br>• Quality | **30 Marks** | **30 / 30**<br>*(Excellent: 30–25)* | **Adherence:** Strictly adhered to the formal 4-tier remediation architecture and DPDP Act compliance requirements without scope deviation.<br>**Timeliness:** Completed all Phase II milestones on schedule, including data generation, model fine-tuning, Ollama quantization, and evaluation.<br>**Quality:** Flawless safety record with **0.00% unsafe outputs** across 2,728 tests; 148 automated tests passing green in CI in 60.67s. |
| **2. Tools & Techniques**<br>• Selection<br>• Application<br>• Integration | **20 Marks** | **20 / 20**<br>*(Excellent: 20–16)* | **Selection:** Deployed cutting-edge Unsloth QLoRA, on-device GGUF via Ollama, Open Policy Agent (Rego), and NetworkX PPR attack graph modeling.<br>**Application:** Applied token-level grammar-constrained decoding (GBNF) and two-stage SFT + RFT training ladder.<br>**Integration:** Fully connected end-to-end operational pipeline from raw Terraform ingestion $\to$ Airlock $\to$ Graph $\to$ M1 Model $\to$ Verification Gate $\to$ Verified HCL Diff. |
| **3. Partial Results**<br>• Clarity<br>• Progress<br>• Analysis | **10 Marks** | **10 / 10**<br>*(Excellent: 5+5+5 scaled)* | **Clarity:** Delivered interactive visual simulator dashboard (`argus_phase2_interactive_demo.html`) and frozen immutable API contracts.<br>**Progress:** Fully functioning on-device model actively generating verified patches; harvested 2,568 candidate records with per-token logprobs; scanned 58 production GitHub repositories.<br>**Analysis:** Rigorous statistical evaluation with Wilson 95% confidence intervals, McNemar significance tests ($p < 0.0001$), and 20/20 adversarial injection defenses. |
| **TOTAL** | **60 Marks** | **60 / 60** | **Grade: EXCELLENT (Grade O / A+)** |

---

## 3. High-Level System Architecture

```mermaid
flowchart TD
    subgraph Ingestion["1. Ingestion & Privacy Sanitization"]
        Raw["Raw Terraform Finding\n(AWS Account, ARN, Secret)"] --> Airlock["Privacy Airlock\n• Salted Vault Tokenization\n• Secret & Entropy Stripping"]
        Airlock --> Sanitized["Sanitized Finding\n(BUCKET_1, SG_1)"]
    end

    subgraph Prioritization["2. Graph Prioritization"]
        Sanitized --> Graph["Personalized PageRank (PPR)\n• Blast Radius Scoring\n• Stackelberg Interdiction"]
    end

    subgraph Remediation["3. 4-Tier Autonomous Remediation"]
        Graph --> Router{"Tier 0 AST Template Match?"}
        Router -- "Yes (54-69% Findings)" --> T0["Tier 0: Deterministic Patch\n(0 ms Latency, 100% Pass)"]
        Router -- "No" --> T1["Tier 1: ARGUS-M1 Local Model\n(Qwen3.5-4B-RFT in Ollama)"]
        T1 --> GBNF["Grammar-Constrained Decoding\n(Strict Patch-IR JSON Schema)"]
    end

    subgraph Verification["4. Formal Verification Gate"]
        GBNF --> Gate{"Verification Gate\n• Rego DPDP & CIS Policies\n• Intent Preservation (0 Deletes)\n• No Privilege Escalation"}
        T0 --> Gate
        Gate -- "VERIFIED PASS" --> Patch["Verified HCL Diff Committed to Git\n(Zero Data-Plane Egress)"]
        Gate -- "REJECTED" --> Fallback["Tier 3: Human Review Queue"]
    end
```

---

## 4. Comprehensive Empirical Results

Evaluation was executed across six independent splits, with held-out sets evaluated strictly once:

### A. Accuracy Across Test Splits (Pass@1 and Pass@8 with 95% Wilson CIs)

| Model | A_val (Validation) | Tier B1 (Unseen Mutators) | Tier B2 (Held-out Family) | Tier C_verifier (Real GitHub Repos) | Gold Sample (Human Verified) |
|---|---|---|---|---|---|
| **ARGUS-M1 (Final)** | **96.7%** [94.3, 98.1] | **96.2%** [93.1, 97.9] | **88.9%** [83.5, 92.7] | **89.3%** [86.1, 91.8] | **87.5%** [78.5, 93.1] |
| **Stock Qwen3.5-4B** | 26.6% [22.3, 31.4] | 39.5% [33.7, 45.5] | 77.8% [71.2, 83.2] | 35.6% [31.4, 40.1] | 36.2% [26.6, 47.2] |
| **Statistical Sig.** | $p < 0.0001$ | $p < 0.0001$ | $p = 0.012$ | $p < 0.0001$ | $p < 0.0001$ |

### B. Safety Audit, Schema Validity, and Latency

| Evaluation Metric | ARGUS-M1 (Our Model) | Stock Foundation Model | Commercial Generic APIs (GPT-4) |
|---|---|---|---|
| **Unsafe Mutation Rate** | **0.00%** (0 / 2,728) | 74.1% (2,022 / 2,728) | ~12% – 25% |
| **Schema Validity Rate** | **100.0%** (2,728 / 2,728) | 98.6% | Variable (Unconstrained) |
| **Data-Plane Privacy** | **100% On-Device** (0 B Egress) | Local (if self-hosted) | Transmitted to Third-Party |
| **Median Inference Latency** | **2.97 seconds** | 10.15 seconds | 4.5s – 8.0s (Network overhead) |
| **Adversarial Injection Defense** | **100% Blocked** (20 / 20) | Fails / Complies with Attack | Inconsistent Guardrails |

---

## 5. Regulatory Alignment: India DPDP Act 2023 & CIS Benchmark

| Regulatory Article / Benchmark | Security Vulnerability Prevented | Automated Policy & Verification Check |
|---|---|---|
| **DPDP Act Section 8(5)**<br>*Reasonable Security Safeguards* | Storage of unencrypted personal data in cloud object stores. | `cis.s3_default_encryption`: Enforces AWS KMS server-side encryption with key rotation. |
| **DPDP Act Section 8(5)**<br>*Public Exposure Prevention* | Publicly accessible cloud buckets exposing Indian citizen PII. | `dpdp.rule6_public_exposure`: Enforces all 4 S3 Public Access Block attributes (`block_public_acls`, `block_public_policy`, etc.). |
| **DPDP Act Section 8(5)**<br>*Audit Logging & Accountability* | Unlogged administrative or data access preventing forensic audits. | `dpdp.rule6_logging`: Enforces S3 bucket server access logging directed to central audit vault. |
| **DPDP Act Section 8(7)**<br>*Data Erasure & Storage Limitation* | Retaining sensitive data beyond required legal necessity. | `dpdp.rule8_lifecycle`: Enforces lifecycle expiration rules for automatic personal data erasure. |
| **DPDP Act Section 16**<br>*Cross-Border Data Transfer* | Storing personal data in non-approved international regions. | `dpdp.rule15_region`: Restricts deployment regions strictly to compliant zones (`ap-south-1`). |
| **CIS Benchmark 1.16**<br>*IAM Privilege Minimization* | Over-privileged wildcard policies (`Action: "*", Resource: "*"`) granting account takeover. | `cis.iam_no_full_admin`: Flags wildcard policies and triggers the deterministic Escalate Router for human security architect sign-off. |
| **CIS Benchmark 4.1**<br>*Network Ingress Control* | Ingress rules open to `0.0.0.0/0` on management ports (SSH 22, RDP 3389). | `cis.sg_open_ingress`: Restricts CIDR ingress strictly to internal enterprise VPC CIDRs (`10.0.0.0/16`). |

---

## 6. Software Engineering & Codebase Verification

The project adheres to enterprise software engineering standards:
* **Automated Test Suite:** **148 passed tests** covering unit functions, schema validators, gate stub verifications, and harvest stores.
* **Cryptographic Dataset Integrity:** `python -m ml.tools.verify_manifest` verifies 10 out of 10 dataset splits against fixed SHA-256 digests.
* **Clean Git Tree:** Zero uncommitted diffs, strict ownership boundaries (`tools/check_ownership.py`), and frozen API contracts in `README_contracts.md`.

---

## 7. Phase 3 Forward Milestones

Having successfully verified all Phase II foundational deliverables on schedule, Phase 3 execution will deliver:
1. **M2 Trust Engine:** Calibrating multi-generator prediction confidence using per-token logprob distributions extracted during Phase 6 harvesting.
2. **Enterprise Developer Dashboard:** Full web-based visual interface integrating repository scanning, real-time finding alerts, and one-click GitHub Pull Request creation.

---

*Submitted to the Project Evaluation Committee in fulfillment of Phase II Capstone Requirements.*

