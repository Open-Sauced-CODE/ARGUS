"""ARGUS Hackathon Production Web Server & Unified Backend
Serves the production React dashboard build and live REST API backend.
Runs on any machine (Local Windows / AWS EC2 Free Tier ap-south-1 Mumbai)
with zero mandatory pip dependencies.

Endpoints:
  GET /                  -> React Dashboard SPA (Overview, Map, Plan, Approvals, Compliance, Proof, Architecture)
  GET /api/health        -> Real-time health & telemetry JSON
  GET /api/overview      -> Overview headline, risk metrics, compliance status
  GET /api/graph         -> Cartographic attack graph topology
  GET /api/findings      -> Security & DPDP compliance findings
  GET /api/compliance    -> Digital Personal Data Protection (DPDP) Act 2023 audit rules
  GET /api/interdiction  -> MILP network interdiction Pareto frontier
  GET /api/approvals     -> Findings awaiting human architect approval
  POST /api/approvals/:id/approve -> Live approval & verification dispatcher
  GET /api/receipts      -> Cryptographic zero-leakage privacy receipts
  GET /api/architecture  -> Comprehensive architecture, deployment guide & startup case study
  POST /api/pipeline/run -> Live autonomous pipeline executor (Ollama + Airlock + Rego)
  POST /api/pipeline/reset -> Reset pipeline state
"""

from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent
if str(BASE_DIR) not in sys.path:
    sys.path.insert(0, str(BASE_DIR))


def main():
    parser = argparse.ArgumentParser(description="ARGUS Dual-Mode Web Server")
    parser.add_argument("positional_port", nargs="?", type=int, help="Optional port (e.g. 80 for EC2)")
    parser.add_argument("--port", type=int, default=None, help="Port to listen on (default: 8000, or 8742 with --local)")
    parser.add_argument("--host", default=None, help="Bind host (default: 127.0.0.1 in local_agent, 0.0.0.0 in cloud_showcase)")
    parser.add_argument("--local", action="store_true", help="Run in zero-egress local_agent mode on 127.0.0.1:8742")
    args = parser.parse_args()

    if args.local:
        os.environ["ARGUS_RUNTIME_MODE"] = "local_agent"

    from backend.api_server import get_runtime_mode, run_server

    mode = get_runtime_mode()
    port = args.port or args.positional_port or (8742 if mode == "local_agent" else 8000)
    host = args.host or ("127.0.0.1" if mode == "local_agent" else "0.0.0.0")
    run_server(host=host, port=port)


if __name__ == "__main__":
    main()
