# ARGUS Visual Assets

This directory contains visual assets used in repository documentation, presentations, and the GitHub project landing page.

All assets are generated with a fixed seed (`1337`) using [`scripts/make_assets.py`](../../scripts/make_assets.py) with the ARGUS dark palette (`#0d1117` background, `#2dd4bf` teal accent, `#f59e0b` amber warning/risk accent).

---

## Asset Inventory

| File | Resolution | Type | Description |
| :--- | :--- | :--- | :--- |
| [`social_preview.png`](social_preview.png) | 1280 × 640 px | **Decorative** | GitHub repository social preview card featuring project title, core value proposition, key capability badges, and an illustrative attack graph topology. |
| [`architecture.png`](architecture.png) | 1600 × 700 px | **System Diagram** | End-to-end system architectural diagram illustrating the 6-stage pipeline from AWS Cartography ingestion, Personalized PageRank risk scoring, budgeted interdiction decision engine, privacy airlock, multi-tier remediation, and OPA/Rego verification gate. Unbuilt downstream components are marked with dashed borders (*Planned*). |
| [`pipeline_status.png`](pipeline_status.png) | 1500 × 380 px | **Status Tracker** | Roadmap progress tracker spanning all project phases (Phases 0–12), distinguishing completed milestones (Phases 0–5), active development (Phase 6 M2 Risk-Controlled Gate), and planned milestones (Phases 7–12). |
| `attack_graph_scores.png` | — | **Data-Derived** | *Skipped (Honest Reporting)*: Standalone node-level PageRank scores dump is not committed to the repository; fabricated or synthetic graphs are explicitly omitted. |

---

## Regeneration

To regenerate all visual assets in this directory, run:

```bash
python scripts/make_assets.py
```
