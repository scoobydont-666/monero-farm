#!/usr/bin/env python3
"""
Monero Farm — HTTP Health Check API
Lightweight health check server exposing monerod, p2pool, xmrig status over HTTP.
Binds to 127.0.0.1:8088 (registered in /opt/hydra-project/docs/port-registry.md).
"""

import json
import sys
import time
from http.server import HTTPServer, BaseHTTPRequestHandler
from pathlib import Path

# Health check commands
CHECKS = {
    "monerod_systemd": "systemctl is-active --quiet monerod 2>/dev/null && echo ok || echo fail",
    "monerod_rpc": "curl -s --max-time 2 http://127.0.0.1:18081/json_rpc -d '{\"jsonrpc\":\"2.0\",\"id\":\"0\",\"method\":\"get_info\"}' | grep -q result && echo ok || echo fail",
    "p2pool_systemd": "systemctl is-active --quiet p2pool 2>/dev/null && echo ok || echo fail",
    "p2pool_stratum": "ss -tlnp 2>/dev/null | grep -q ':3333' && echo ok || echo fail",
    "xmrig_api": "curl -s --max-time 2 http://127.0.0.1:8082/2/summary | grep -q hashrate && echo ok || echo fail",
}


def run_check(cmd: str) -> bool:
    """Run shell command, return True if exit code is 0."""
    import subprocess
    try:
        result = subprocess.run(cmd, shell=True, capture_output=True, timeout=5)
        return result.returncode == 0
    except subprocess.TimeoutExpired:
        return False
    except Exception:
        return False


def get_health_status() -> dict:
    """Check all services and return status dict."""
    results = {}
    for name, cmd in CHECKS.items():
        results[name] = "healthy" if run_check(cmd) else "unhealthy"

    healthy_count = sum(1 for v in results.values() if v == "healthy")
    total = len(results)

    # Overall status: healthy if 4+/5 checks pass
    overall = "healthy" if healthy_count >= 4 else "degraded" if healthy_count >= 2 else "unhealthy"

    return {
        "status": overall,
        "checks": results,
        "summary": {
            "total": total,
            "healthy": healthy_count,
            "unhealthy": total - healthy_count,
        },
        "timestamp": time.time(),
    }


class HealthCheckHandler(BaseHTTPRequestHandler):
    """HTTP handler for /health and /metrics endpoints."""

    def do_GET(self):
        """Handle GET requests."""
        if self.path == "/health":
            status = get_health_status()
            http_code = 200 if status["status"] == "healthy" else 503
            self.send_response(http_code)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            self.wfile.write(json.dumps(status).encode())
        elif self.path == "/metrics":
            # Prometheus metrics endpoint
            status = get_health_status()
            metrics = self._build_metrics(status)
            self.send_response(200)
            self.send_header("Content-Type", "text/plain; version=0.0.4")
            self.end_headers()
            self.wfile.write(metrics.encode())
        else:
            self.send_response(404)
            self.end_headers()
            self.wfile.write(b"Not Found")

    def _build_metrics(self, status: dict) -> str:
        """Build Prometheus metrics output."""
        lines = [
            "# HELP monerod_health Health status of monerod (1=healthy, 0=unhealthy)",
            "# TYPE monerod_health gauge",
            f"monerod_health {{service=\"monerod\"}} {1 if status['checks'].get('monerod_rpc') == 'healthy' else 0}",
            "",
            "# HELP p2pool_health Health status of p2pool (1=healthy, 0=unhealthy)",
            "# TYPE p2pool_health gauge",
            f"p2pool_health {{service=\"p2pool\"}} {1 if status['checks'].get('p2pool_stratum') == 'healthy' else 0}",
            "",
            "# HELP xmrig_health Health status of xmrig (1=healthy, 0=unhealthy)",
            "# TYPE xmrig_health gauge",
            f"xmrig_health {{service=\"xmrig\"}} {1 if status['checks'].get('xmrig_api') == 'healthy' else 0}",
            "",
            "# HELP farm_health_total Total services checked",
            "# TYPE farm_health_total gauge",
            f"farm_health_total {status['summary']['total']}",
            "",
            "# HELP farm_health_up Number of healthy services",
            "# TYPE farm_health_up gauge",
            f"farm_health_up {status['summary']['healthy']}",
            "",
            "# HELP farm_health_check_timestamp Health check timestamp",
            "# TYPE farm_health_check_timestamp gauge",
            f"farm_health_check_timestamp {int(status['timestamp'])}",
        ]
        return "\n".join(lines) + "\n"

    def log_message(self, format, *args):
        """Suppress default logging."""
        pass


def main():
    """Start health check HTTP server."""
    host = "127.0.0.1"
    port = 8088

    server = HTTPServer((host, port), HealthCheckHandler)
    print(f"Monero Farm Health Check API listening on {host}:{port}")
    print(f"  GET /health  — JSON health status")
    print(f"  GET /metrics — Prometheus metrics")

    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nShutdown.")
        sys.exit(0)


if __name__ == "__main__":
    main()
