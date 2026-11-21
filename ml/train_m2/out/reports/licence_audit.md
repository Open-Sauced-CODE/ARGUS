# ARGUS Licence Audit Report

## 1. Summary

- Scanned requirements files: requirements-ci.txt, requirements-m1v2.txt, requirements-phase3.txt, requirements-phase4.txt, requirements-phase5.txt, requirements-phase6.txt, requirements.txt
- Total declared packages: 264
  - Permissive: 250
  - Copyleft: 4
  - Unverified / Not Installed: 10
- Base model (Qwen3.5-4B / Qwen2.5): Apache-2.0 (APPROVED)
- C-mined dataset rows: 37 (Copyleft rows: 1)

## 2. Base Model Licence

- **Model**: Qwen3.5-4B / Qwen2.5
- **Licence**: Apache-2.0
- **Commercial Use**: Yes
- **Notes**: Permissive Apache-2.0 license compatible with commercial redistribution and research.

## 3. Dataset Licences (C-Mined Manifest)

Manifest file: `ml/real_data/diagnostics/out/tierC_mined_v2.jsonl` (total rows: 37)

| Licence | Count | Category |
|---|---|---|
| MIT | 16 | permissive |
| Apache-2.0 | 13 | permissive |
| WTFPL | 4 | permissive |
| BSD-3-Clause | 3 | permissive |
| MPL-2.0 | 1 | copyleft |

### Copyleft dataset rows (flagged for review)

| ID | Repository | Licence |
|---|---|---|
| m-000010 | mozmeao/infra | MPL-2.0 |

## 4. Package Licences (Declared in requirements*.txt)

### Copyleft Packages

| Package | Version | Licence | Declared In |
|---|---|---|---|
| certifi | 2026.7.22 | Mozilla Public License 2.0 (MPL 2.0) | requirements.txt |
| crc32c | 2.8 | GNU Lesser General Public License v2 or later (LGPLv2+) | requirements.txt |
| fqdn | 1.6.0 | MPL-2.0 | requirements.txt |
| jwcrypto | 1.6.1 | LGPL-3.0-or-later | requirements.txt |

### Unverified / Not Installed Packages

| Package | Version | Licence / Reason | Declared In |
|---|---|---|---|
| cartography | N/A | NOT INSTALLED | requirements.txt |
| highspy | N/A | NOT INSTALLED | requirements-phase3.txt |
| jupyter-lsp | N/A | NOT INSTALLED | requirements.txt |
| jupyter_server | N/A | NOT INSTALLED | requirements.txt |
| jupyterlab | N/A | NOT INSTALLED | requirements.txt |
| jupyterlab_server | N/A | NOT INSTALLED | requirements.txt |
| notebook_shim | N/A | NOT INSTALLED | requirements.txt |
| orloge | 1.0.0 | UNKNOWN | requirements.txt |
| pagerduty | 7.0.1 | UNKNOWN | requirements.txt |
| presidio-analyzer | N/A | NOT INSTALLED | requirements-phase4.txt |
