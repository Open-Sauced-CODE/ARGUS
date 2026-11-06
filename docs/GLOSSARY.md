# ARGUS Domain Glossary

A reference guide for security engineers, developers, and evaluators detailing terminology used throughout the ARGUS codebase, architecture, and research documentation.

---

### Attack Graph
A directed graph $G = (V, E)$ representing an organization's security posture. Nodes ($V$) represent cloud assets (principals, roles, compute, storage, security groups), and edges ($E$) represent reachable network paths, trust relationships, or IAM permissions that an adversary could exploit.

### Attack Path
A sequential chain of traversable edges in an attack graph that allows an adversary to pivot from an initial entry point (e.g., an internet-facing EC2 instance with an SSRF vulnerability) to high-value assets.

### Blast Radius
The maximum extent of cloud resources, accounts, or services that an attacker could compromise or impact if a specific credential, instance, or role is breached.

### Calibration (Model Calibration)
The statistical property where a model's predicted probability matches its empirical accuracy. A calibrated confidence score of $0.95$ indicates that out of 100 predictions, approximately 95 are correct.

### Cartography
An open-source Python tool (originally by Lyft) that ingests cloud infrastructure assets and dependencies from AWS APIs into a Neo4j graph database.

### Cloud Misconfiguration
An improper or default setting in cloud infrastructure (e.g., public S3 bucket, wildcard IAM action `*`, missing server-side encryption) that exposes systems to unauthorized access or regulatory non-compliance.

### Conformal Threshold / Conformal Prediction
A distribution-free statistical framework providing mathematical error guarantees. In ARGUS, conformal risk control calculates an empirical decision threshold $\hat{\tau}$ ensuring that the defect rate among auto-applied patches is strictly bounded by a predefined risk budget $\epsilon$ (e.g., $\le 1\%$).

### Crown Jewel
A business-critical cloud asset—such as a production database containing customer PII, financial ledgers, or master encryption keys—designated as high-priority target sinks in risk calculations.

### DPDP Act Rules 2025 (India)
Technical safeguard regulations under India's Digital Personal Data Protection (DPDP) Act:
* **Rule 6**: Encryption standards for personal data in transit and at rest.
* **Rule 7**: Access management, principle of least privilege, and role-based access control.
* **Rule 8**: Comprehensive audit logging, monitoring, and tamper resistance.
* **Rule 15**: Visibility over data residency and retention lifecycles.

### GRPO (Group Relative Policy Optimization)
An efficient reinforcement learning algorithm from LLM alignment literature that optimizes candidate generation across sampled output groups without requiring a separate critic model.

### Interdiction (Network Interdiction)
A game-theoretic optimization problem that models a defender allocating a limited budget $K$ of interventions (remediations) to maximize the shortest-path cost or minimize the maximum reachability probability of an attacker attempting to traverse an attack graph.

### Lateral Movement
Techniques used by an attacker to extend access to other compute instances, services, or IAM roles within a cloud environment after gaining initial access.

### M1 (Model 1: Generator)
A specialized small language model (fine-tuned Qwen2.5-Coder) running locally within the customer boundary that drafts structured Patch-IR remediations for cloud misconfigurations.

### M2 (Model 2: Verifier / Confidence Model)
A calibrated tabular machine learning model (e.g., LightGBM) that evaluates fix candidates that have passed deterministic gate checks, computing calibrated confidence scores used by the conformal auto-apply threshold.

### Neo4j
A high-performance graph database that stores ARGUS attack graphs, allowing Cypher queries to model multi-hop lateral movement and IAM permission chains.

### Open Policy Agent (OPA) / Rego
An open-source, general-purpose policy engine. Rego is its declarative query language used by ARGUS to deterministically evaluate whether proposed infrastructure patches satisfy security invariants and DPDP safeguards.

### PageRank / Personalized PageRank (PPR)
A random-walk graph algorithm used by ARGUS to compute asset criticality. Personalized PageRank biases random walks toward crown-jewel target nodes, calculating the steady-state probability that an attacker traversing the attack graph visits a given intermediate node.

### Patch-IR (Patch Intermediate Representation)
A closed, deterministic JSON schema specifying exact infrastructure transformations (e.g., attribute replacement, policy statement injection). Generative models in ARGUS must output Patch-IR rather than arbitrary code or scripts.

### RFT (Reinforcement Fine-Tuning)
Fine-tuning an LLM using reinforcement learning algorithms (such as GRPO or PPO) against a deterministic verification reward signal (the OPA/Rego gate) to improve generation validity on edge cases.

### SFT (Supervised Fine-Tuning)
Training a language model on paired examples of misconfigured infrastructure inputs and verified, passing Patch-IR outputs.

### T0 – T3 (Remediation Tiers)
ARGUS's hierarchical execution strategy:
* **T0**: Deterministic, pre-compiled templates for known standard patterns.
* **T1**: Local fine-tuned model (M1) generating Patch-IR.
* **T2**: Remote cloud LLM (optional, opt-in only, operating solely on scrubbed airlock payloads).
* **T3**: Human approval queue for ambiguous or high-blast-radius actions.

### Terraform
An open-source Infrastructure-as-Code (IaC) tool by HashiCorp used to define, provision, and remediate cloud resources deterministically.
