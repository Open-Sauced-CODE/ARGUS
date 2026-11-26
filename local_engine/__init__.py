"""ARGUS Local Zero-Egress Security & Remediation Engine.

Runs strictly on the user's workstation or private VPC (127.0.0.1:8742):
- Resolves frozen-safe bundled and writable local paths
- Scans local Terraform (.tf / .tfstate) and read-only AWS accounts (iam_guard checked)
- Builds attack graphs in-process via frozen risk.attack_graph (no Docker/Neo4j required)
- Solves Personalized PageRank + MILP Network Interdiction
- Runs Privacy Airlock + Tier 0 templates + Local Ollama (argus-m1-sft) + OPA Rego Gate
- Enforces M2 LTT certification guardrails (autonomy OFF while certified=False)
- Exports Terraform .patch diffs and DPDP compliance audit bundles
"""

__all__ = ["paths", "state_store", "ollama_manager", "hcl_writer", "pipeline_orchestrator"]
