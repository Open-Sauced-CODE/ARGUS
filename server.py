"""ARGUS Live Web Dashboard Server for AWS Free Tier Deployment
Campus to Cloud Hackathon | Techfest, IIT Bombay & AWS

Zero-dependency HTTP server using standard Python library (http.server).
Runs immediately on any machine (Local Windows / AWS EC2 Free Tier Ubuntu)
without needing any third-party pip packages!

Routes:
  GET /            -> Production React Dashboard SPA
  GET /graph       -> Interactive Neo4j Attack Graph Viewer
  GET /api/...     -> Live REST APIs (Health, Overview, Findings, Compliance, Interdiction, Pipeline)
"""

from __future__ import annotations

import argparse
import os
import sys
from http import HTTPStatus
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent
if str(BASE_DIR) not in sys.path:
    sys.path.insert(0, str(BASE_DIR))

from backend.api_server import ArgusAppHandler, run_server

DASHBOARD_DIR = BASE_DIR / "dashboard" / "previews"


class EnhancedArgusHandler(ArgusAppHandler):
    def do_GET(self):
        url_path = self.path.split("?")[0].rstrip("/")

        # Support standalone Neo4j attack graph viewer HTML if requested
        if url_path == "/graph":
            graph_file = DASHBOARD_DIR / "neo4j_attack_graph_viewer.html"
            if graph_file.exists():
                content = graph_file.read_bytes()
                self.send_response(HTTPStatus.OK)
                self.send_header("Content-Type", "text/html; charset=utf-8")
                self.send_header("Content-Length", str(len(content)))
                self.end_headers()
                self.wfile.write(content)
                return

        return super().do_GET()


def main():
    parser = argparse.ArgumentParser(description="Start ARGUS Web Dashboard Server")
    parser.add_argument("positional_port", nargs="?", type=int, help="Optional port")
    parser.add_argument("--host", default=None, help="Host interface (default: 127.0.0.1 in local_agent, 0.0.0.0 in cloud_showcase)")
    parser.add_argument("--port", type=int, default=None, help="Port to listen on (default: 8000, or 8742 with --local)")
    parser.add_argument("--local", action="store_true", help="Run in zero-egress local_agent mode on 127.0.0.1:8742")
    args = parser.parse_args()

    if args.local:
        os.environ["ARGUS_RUNTIME_MODE"] = "local_agent"

    from backend.api_server import get_runtime_mode

    mode = get_runtime_mode()
    bind_host = args.host or ("127.0.0.1" if mode == "local_agent" else "0.0.0.0")
    port = args.port or args.positional_port or (8742 if mode == "local_agent" else 8000)

    from http.server import ThreadingHTTPServer
    server = ThreadingHTTPServer((bind_host, port), EnhancedArgusHandler)
    print("\n" + "=" * 80)
    print("  ARGUS :: Live Web Dashboard Server (AWS Free Tier Ready)")
    print(f"  Runtime Mode: {mode}")
    print("=" * 80)
    print(f"  • Listening on:        http://{bind_host}:{port}")
    print(f"  • Main Dashboard:      http://localhost:{port}/")
    print(f"  • Attack Graph Map:    http://localhost:{port}/map")
    print(f"  • Standalone Graph:    http://localhost:{port}/graph")
    print(f"  • Empirical Results:   http://localhost:{port}/results")
    print(f"  • Architecture Guide:  http://localhost:{port}/architecture")
    print(f"  • Documentation Hub:   http://localhost:{port}/docs")
    print(f"  • Versions & .exe:     http://localhost:{port}/downloads")
    print(f"  • Health API:          http://localhost:{port}/api/health")
    print("=" * 80 + "\n", flush=True)

    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nStopping server.")
        server.server_close()


if __name__ == "__main__":
    main()
