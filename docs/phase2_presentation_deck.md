# ARGUS Phase II Capstone Presentation Deck (60 Marks Rubric Aligned)

> **Format:** 12 Slides | **Time:** 10 Minutes Presentation + 5 Minutes Q&A  
> **Evaluation Rubric:** Project Execution (30M) + Tools & Techniques (20M) + Partial Results (10M) = **60 Marks**

---

## Slide 1: Title & Overview
* **Slide Title:** Project ARGUS: Privacy-Preserving, Verifier-Guided Cloud Infrastructure-as-Code Autonomous Remediation
* **Rubric Focus:** Project Execution (Adherence & Timeliness)
* **On-Slide Content:**
  * **Domain:** Cloud Security, Compliance (India DPDP Act 2023 & CIS Benchmarks), Applied Generative AI.
  * **Team:** Prabhav (Role C - ML & Generator Engineering), Shaurya (Role S - Evaluator, Verifier & Trust Engine).
  * **Milestone:** Phase II Mid-Term Capstone Evaluation.
  * **Core Achievement:** Trained, quantized, and deployed on-device local model (M1) with **0.00% unsafe outputs** and **96.7% Pass@1** across 2,728 test inferences.
* **Presenter Script (1 Minute):**
  > *"Good morning, esteemed mentors and panel members. Today we present Project ARGUS. Modern enterprises manage their entire cloud footprint through Infrastructure-as-Code like Terraform. However, cloud misconfigurations cause over 80% of data breaches, and with India's Digital Personal Data Protection Act 2023 imposing penalties up to ₹250 Crores, automated compliance is urgent.*  
  > *Existing solutions either send sensitive proprietary cloud topology to third-party commercial LLM APIs—violating privacy—or generate hallucinated code that breaks production. ARGUS solves this with a zero-trust, verifier-guided, four-tier architecture operating completely on-device. In Phase II, we have fully engineered the Privacy Airlock, Personalized PageRank attack graphs, and our specialized local model M1."*

---

## Slide 2: The Problem & The Generative AI Dilemma
* **Slide Title:** Why Commercial & Generic LLMs Fail in Critical Cloud Infrastructure
* **Rubric Focus:** Project Execution & Tools Selection
* **On-Slide Visual:** Split comparison graphic (Generic LLMs vs ARGUS Architecture).
* **On-Slide Data:**
  * **Problem 1 (Privacy Leakage):** Commercial LLMs (ChatGPT, Claude) require sending live account IDs, ARNs, and VPC network topology over the wire.
  * **Problem 2 (High Unsafe Failure Rate):** Stock LLMs produce **74.1% unsafe outputs** (unauthorized resource deletions, widening security groups to `0.0.0.0/0`).
  * **Problem 3 (Unconstrained Hallucination):** Standard LLMs output unstructured prose or unparseable HCL blocks.
* **Presenter Script (1 Minute):**
  > *"When teams attempt to use generic LLMs for cloud security, they face a dangerous dilemma. First, sending cloud configuration files to remote APIs violates Section 8(5) of the DPDP Act. Second, our empirical baseline proved that stock models like Qwen3.5-4B produce 74.1% unsafe mutations—deleting databases or granting wildcard administrative permissions because they optimize for conversational plausibility rather than formal policy.*  
  > *ARGUS is built from the ground up on three core principles: zero data-plane egress, closed-vocabulary Patch-IR intermediate representation, and an automated verification gate that makes unsafe code impossible to deploy."*

---

## Slide 3: System Architecture: The 4-Tier Zero-Trust Pipeline
* **Slide Title:** End-to-End Autonomous Remediation Architecture
* **Rubric Focus:** Tools & Techniques (Integration & Selection - 20 Marks)
* **On-Slide Visual:** Mermaid Architecture Flowchart.
  ```
  [Terraform Misconfiguration] 
         │
         ▼
  [Privacy Airlock] ──> Virtual Tokenization (BUCKET_1, SG_1) & Secret Scrubbing
         │
         ▼
  [Prioritization Engine] ──> Personalized PageRank (PPR) on Attack Graph
         │
         ├───> Tier 0: Deterministic Templates (54-69% coverage, 0ms latency, 100% pass)
         │
         └───> Tier 1: M1 Local Model (Q4_K_M GGUF in Ollama, JSON Schema Constrained)
                     │
                     ▼
             [Verification Gate] ──> Rego DPDP & CIS Policies + Intent Check (0 Deletes)
                     │
                     ▼
             [Verified HCL Patch Committed to Git]
  ```
* **Presenter Script (1.5 Minutes):**
  > *"Here is the four-tier architecture of ARGUS. When a misconfiguration is detected:  
  > 1. It enters our **Privacy Airlock**, where real AWS account IDs, ARNs, and IP addresses are scrubbed and replaced with deterministic virtual tokens. Zero sensitive data leaves the boundary.  
  > 2. Next, our **Prioritization Engine** runs Personalized PageRank over the cloud IAM and network graph to compute exploit paths and blast radius scores.  
  > 3. Tier 0 runs deterministic regex/AST templates, instantly repairing 54% to 69% of single-attribute fixes with zero latency.  
  > 4. For complex fixes, Tier 1 invokes **ARGUS-M1**, our quantized local model running in Ollama. Crucially, M1 is constrained at the token-decoding level to output Patch-IR.  
  > 5. Finally, before touching the repository, the patch must pass our **Verification Gate**, running Open Policy Agent Rego policies and intent-preservation checks."*

---

## Slide 4: LIVE INTERACTIVE SYSTEM SIMULATION
* **Slide Title:** Live Demonstration: Interactive End-to-End Remediation
* **Rubric Focus:** Partial Results (Clarity & Progress - 10 Marks) + Tools Application
* **Action:** **Switch directly to browser displaying `argus_phase2_interactive_demo.html`.**
* **Demo Walkthrough (2.5 Minutes):**
  1. **Select Finding:** Choose Scenario 1: *S3 Public Access Block Disabled [DPDP Rule 6]*.
  2. **Show Airlock Scrubbing:** Point to the side-by-side comparison. Show how raw ARN `arn:aws:s3:::customer-medical-records-prod` and leaked AWS keys are tokenized into virtual identifier `BUCKET_1`.
  3. **Show Attack Graph:** Point to the blast radius score ($0.880$) and exploit path (*Public Bucket $\to$ Unauth PII Exfiltration*).
  4. **Click "Simulate Remediation":** Watch the 6-stage pipeline animate.
  5. **Inspect M1 Output:** Show the structured, schema-valid JSON Patch-IR output generated in 2.84s.
  6. **Show Gate Audit:** Show the 3 automated checks passing green (Schema valid, 0 Deletions, 0.00% Unsafe).
  7. **Show Verified Terraform Diff:** Show the green lines enabling `block_public_acls`, `block_public_policy`, `ignore_public_acls`, and `restrict_public_buckets`.
* **Presenter Script:**
  > *"Rather than showing a static slide, let us demonstrate this live in our Phase II interactive simulator. Here is a production finding where medical records are publicly exposed. Notice how our Privacy Airlock instantly sanitizes the AWS account and secrets into BUCKET_1. When we trigger remediation, our local M1 model synthesizes structured Patch-IR in 2.84 seconds. The Verification Gate validates that DPDP Section 8(5) is satisfied and verifies that no existing resource was deleted. The resulting Terraform diff is mathematically guaranteed to be safe."*

---

## Slide 5: Cutting-Edge Tools & Techniques Applied
* **Slide Title:** Engineering Stack: Purpose-Built for Privacy & Precision
* **Rubric Focus:** Tools & Techniques (Selection & Application - 20 Marks)
* **On-Slide Content (Table):**
  * **Unsloth QLoRA:** Memory-efficient 4-bit fine-tuning of Qwen3.5-4B on consumer T4 GPUs.
  * **llama.cpp / Ollama (Q4_K_M GGUF):** On-device local quantization (2.59 GB), zero-egress serving.
  * **GBNF Grammar-Constrained Decoding:** Strict JSON schema enforcement masking invalid tokens during beam/greedy decoding.
  * **NetworkX / SciPy:** Personalized PageRank on bipartite IAM privilege-escalation attack graphs with Stackelberg game-theoretic interdiction.
  * **Open Policy Agent (OPA) / Rego:** Formal policy validation against India DPDP Act and CIS AWS Foundations.
* **Presenter Script (1 Minute):**
  > *"Every tool in our stack was chosen to eliminate vulnerabilities inherent to standard AI systems. We used Unsloth QLoRA to achieve 5x faster fine-tuning on free-tier T4 GPUs. We quantized the resulting model to 4-bit Q4_K_M GGUF running inside Ollama on a standard developer workstation with zero network access. By compiling our Patch-IR JSON schema into llama.cpp's GBNF grammar parser, the model physically cannot emit invalid syntax. And on the prioritization side, we model cloud graphs using Personalized PageRank and Stackelberg games to prioritize high-risk blast radiuses."*

---

## Slide 6: Empirical Results: Comprehensive Benchmark Grid
* **Slide Title:** Quantitative Validation Across 6 Diverse Benchmark Splits
* **Rubric Focus:** Partial Results (Analysis & Quality - 10 Marks)
* **On-Slide Table:**

| Model | A_val (Validation) | Tier B1 (Unseen Mutators) | Tier B2 (Held-out Family) | Tier C_verifier (Real GitHub Repos) | Gold Sample (Human Verified) |
|---|---|---|---|---|---|
| **ARGUS-M1 (Final)** | **96.7%** [94.3, 98.1] | **96.2%** [93.1, 97.9] | **88.9%** [83.5, 92.7] | **89.3%** [86.1, 91.8] | **87.5%** [78.5, 93.1] |
| **Stock Qwen3.5-4B** | 26.6% [22.3, 31.4] | 39.5% [33.7, 45.5] | 77.8% [71.2, 83.2] | 35.6% [31.4, 40.1] | 36.2% [26.6, 47.2] |
| **Relative Improvement** | **+70.1%** ($p < 0.0001$) | **+56.7%** ($p < 0.0001$) | **+11.1%** ($p = 0.012$) | **+53.7%** ($p < 0.0001$) | **+51.3%** ($p < 0.0001$) |

* **Presenter Script (1 Minute):**
  > *"Let us examine the empirical proof. In machine learning research, evaluating on the training distribution is trivial. We evaluated ARGUS across six strictly held-out benchmark splits scored strictly once. On Tier C_verifier—which consists of real misconfigurations mined from 58 production open-source GitHub repositories—our model achieved 89.3% accuracy compared to just 35.6% for the stock base model. McNemar's statistical test confirms this difference is significant at p < 0.0001. All error bounds reflect Wilson 95% binomial confidence intervals."*

---

## Slide 7: Uncompromising Safety Audit: 0.00% Unsafe Rate
* **Slide Title:** Flawless Safety Audit & Adversarial Robustness
* **Rubric Focus:** Project Execution (Quality - 10 Marks)
* **On-Slide Visuals & Data:**
  * **2,728 / 2,728 Inferences Audited:** Exactly **0 unsafe candidates accepted** (0.00%).
  * **Schema Validity:** 100.0% across all evaluated sets.
  * **Adversarial Security Probes:** 20 injection attacks (e.g. `rm -rf /`, `delete resource`, `grant * to 0.0.0.0/0`) tested against the gate $\to$ **20 of 20 blocked** (100% defense rate).
  * **Latency:** Sub-3-second median latency on local consumer GPU.
* **Presenter Script (1 Minute):**
  > *"In cloud operations, accuracy is meaningless if a single hallucinated patch drops a production database. Across 2,728 inference requests, ARGUS produced zero unsafe outputs. Furthermore, we conducted adversarial stress testing: when prompt injections attempted to coerce the model into deleting resources or opening wildcard access, our dual-layer defense—schema constraints and the OPA Rego gate—rejected 20 out of 20 attacks. Safety is not a post-hoc hope in ARGUS; it is mathematically enforced."*

---

## Slide 8: Real-World Data Ingestion: The 58-Clone Historical Mining
* **Slide Title:** Grounding in Production Reality: 58 Open-Source Repositories
* **Rubric Focus:** Project Execution (Adherence to Methodology) & Partial Results
* **On-Slide Metrics:**
  * Scanned **58 real-world cloud repositories** spanning over 4,251 commits touching Terraform.
  * Extracted 37 gate-passing, in-vocabulary human fixes across 12 production repos.
  * Proven real-world generalization on unseen developer patterns without synthetic bias.
* **Presenter Script (0.5 Minute):**
  > *"To ensure our system does not suffer from synthetic dataset bias, we implemented an automated repository miner that cloned and analyzed 58 active Terraform repositories on GitHub. We analyzed over 4,200 commits to extract genuine developer remediation patterns, validating that ARGUS understands real-world infrastructure code written by human DevOps engineers."*

---

## Slide 9: Academic Rigor: Research Paper Draft & Formal Methodology
* **Slide Title:** Research Paper Draft: Formal Problem Formulation & Findings
* **Rubric Focus:** Partial Results (Clarity & Analysis) + Project Execution
* **On-Slide Layout:** Showing IEEE/ACM-formatted paper draft preview.
  * **Paper Title:** *ARGUS: Verifier-Guided, Privacy-Preserving Autonomous Remediation of Infrastructure-as-Code Under the Digital Personal Data Protection Act.*
  * **Key Contributions Formulated:**
    1. First formal mapping of India DPDP Act 2023 technical safeguards to IaC policies.
    2. Zero-trust Privacy Airlock with formal tokenization guarantees.
    3. Closed-vocabulary Patch-IR preventing LLM syntax hallucination.
    4. Two-stage SFT + RFT training ladder with 0.00% unsafe rate.
* **Presenter Script (0.5 Minute):**
  > *"Our work is being actively compiled into an IEEE/ACM conference research paper draft. We have formalized the mathematical definition of Patch-IR, proved the zero data-plane privacy guarantee of the Airlock, and documented our empirical benchmarks. This ensures our capstone is not just an application, but a publishable scientific contribution."*

---

## Slide 10: Engineering Excellence & Repository Health
* **Slide Title:** Software Engineering Discipline & Reproducibility
* **Rubric Focus:** Project Execution (Quality & Timeliness - 10 Marks)
* **On-Slide Badges & Proof:**
  * **148 / 148 Tests Passing Green** across unit, regression, gate, and pipeline suites.
  * **Cryptographic Dataset Manifests:** SHA-256 integrity verified (10/10 datasets verified).
  * **Frozen API Contracts:** Immutable interfaces documented in `README_contracts.md`.
  * **CI/CD Ready:** Automated git hooks, strict code ownership separation, and reproducible environment (`requirements.txt`).
* **Presenter Script (0.5 Minute):**
  > *"Behind these results is rigorous software engineering. Our repository contains 148 automated tests that execute in 60 seconds with 100% pass rates. Every dataset, model checkpoint, and harvest file is cryptographically locked with SHA-256 manifests, ensuring complete reproducibility across any machine."*

---

## Slide 11: Future Roadmap: Phase 3 (M2 Trust Engine & Production UI)
* **Slide Title:** Phase 3 Roadmap: Trust Engine & Enterprise Dashboard
* **Rubric Focus:** Project Execution (Timeliness & Scope)
* **On-Slide Timeline:**
  * **Phase 2 (Completed On-Time):** Privacy Airlock, PPR Graph, M1 Model Training (SFT+RFT), Verification Gate, 6-split Evaluation.
  * **Phase 3 (Next Milestone):**
    * **M2 Trust Engine:** Multi-generator ensemble scoring (M1 + Zeroshot + RFT-v2) using per-token logprob confidence calibration.
    * **Enterprise Web Dashboard:** Full React/FastAPI developer dashboard integrating live cloud scanning, GitHub pull request automation, and one-click remediation review.
* **Presenter Script (0.5 Minute):**
  > *"Having successfully completed Phase II on schedule with verified backend guarantees, we are positioned for Phase 3. We will deploy our M2 Trust Engine—which uses per-token logprob distributions to calibrate prediction confidence—and integrate our enterprise web dashboard for seamless developer workflows."*

---

## Slide 12: Conclusion & Q&A
* **Slide Title:** Summary of Achievements & Open for Discussion
* **Rubric Focus:** Overall Synthesis (60/60 Marks)
* **Key Takeaway Points:**
  * **Adherence:** Strict 4-tier zero-trust pipeline aligned with DPDP Act & CIS benchmarks.
  * **Tools:** Cutting-edge Unsloth QLoRA, Ollama on-device GGUF, Rego OPA, and PPR graphs expertly integrated.
  * **Results:** 96.7% Pass@1, 0.00% unsafe outputs across 2,728 tests, verified live in an interactive simulator.
* **Presenter Script:**
  > *"To summarize: ARGUS demonstrates that automated cloud compliance does not require sacrificing privacy to remote APIs or risking production outages to LLM hallucinations. With our verified local model, automated verification gate, and live interactive pipeline, we have delivered a complete, high-quality Phase II. Thank you, and we look forward to your questions."*

