# Tier C-Mined Historical Mining Diagnosis (H3)

**Owner**: Prabhav (Role C: Generator, Ollama, M1-v2)  
**Date**: 2026-10-27  
**Artifacts Generated**:
- Probe Log: `docs/phase6_prabhav/cmined_probe_7363082.txt`
- Mined Dataset: `ml/real_data/diagnostics/out/tierC_mined_v2.jsonl` (37 candidate pairs)
- Funnel Metrics: `ml/real_data/diagnostics/out/mined_funnel_v2.json`

---

## 1. Executive Summary & Root Cause

In Phase 5, historical mining across the 58 cloned GitHub repositories yielded 0 candidate pairs. 

Our H3 investigation and probe (`probe_cmined`) established:
1. **Windows Subprocess & Git Plumbing**: Raw git, UTF-8 byte handling, and CRLF normalization operate cleanly on Windows with `core.quotepath = false` and `utf-8-sig` decoding.
2. **Miner Pairing & Funnel Constraints**: The Phase 5 miner had dropped pairs due to restrictive multi-record ambiguity handling and missing cross-commit tracking. With the updated `mine_history` runner, all 58 repositories were scanned.
3. **Outcome**: The mining run extracted **37 gate-passing, in-vocabulary remediation pairs** across 12 distinct repositories, covering 5 distinct rules.

---

## 2. Mining Funnel Across All 58 Clones

Data from `ml/real_data/diagnostics/out/mined_funnel_v2.json`:

| Funnel Stage | Count | Description |
|---|---:|---|
| **Repositories Scanned** | 58 | All 58 target real-world Terraform repositories |
| **Commits Touching `*.tf`** | 4,251 | Total commits in git history modifying Terraform configurations |
| **Commits Dropped by Prefilter** | 735 | Commits filtered out by keyword heuristics |
| **Resource Pairs Extracted** | 6,335 | Before/after resource pairs compared |
| **Ambiguous Multi-Record Drops** | 1,402 | Commits with ambiguous multi-resource mapping discarded |
| **Resource Pairs with Real Diffs** | 55 | Pairs where resource attributes genuinely changed |
| **Violating Before $\to$ Passing After** | 45 | Finding present in parent commit and resolved in child commit |
| **Duplicate Pairs Discarded** | 8 | Exact duplicate remediation pairs filtered out |
| **Final Gate-Passing Candidates** | **37** | Structurally valid, in-vocabulary Patch-IR pairs |

---

## 3. Breakdown of Mined Candidates

The 37 extracted pairs span 12 repositories and 5 rules:

| Rule ID | Candidates | Target Resource Type |
|---|---:|---|
| `dpdp.rule6_logging` | 10 | `aws_s3_bucket` (logging configurations) |
| `dpdp.rule6a` | 10 | `aws_s3_bucket` (server-side encryption configuration) |
| `cis.s3_default_encryption` | 9 | `aws_s3_bucket` (default encryption attributes) |
| `cis.s3_public_access_block` | 4 | `aws_s3_bucket_public_access_block` |
| `dpdp.rule6_public_exposure` | 4 | `aws_s3_bucket_public_access_block` |
| **Total** | **37** | **12 distinct repositories** |

All 37 pairs are saved in `ml/real_data/diagnostics/out/tierC_mined_v2.jsonl`.
